// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology

/**
 * Tool definitions and dispatch for the gbs-voice MCP server.
 *
 * PHI posture (contract §3/§5, fail-closed):
 *   - voice_transcribe and voice_cleanup are PHI-LOCKED: phi is always `true`,
 *     never exposed as an input. They can only be served by BAA-covered
 *     providers, and can never route to a non-BAA engine.
 *   - voice_speak defaults phi=true and accepts an explicit `phi: false` ONLY
 *     for non-PHI text (e.g. UI chrome), which unlocks premium non-BAA TTS.
 *
 * The Bearer API key is held server-side in GbsVoiceConfig and is NEVER
 * written to tool output. scrub() is a belt-and-suspenders guard that redacts
 * the key value from any string that leaves this module.
 */

import { readFile, writeFile, mkdir } from 'node:fs/promises';
import path from 'node:path';
import type { GbsVoiceConfig } from './config.js';
import * as client from './client.js';
import { VoiceHttpError } from './client.js';

export interface ToolResult {
  content: Array<{ type: 'text'; text: string }>;
  isError?: boolean;
}

const EXT_TO_MIME: Record<string, string> = {
  '.wav': 'audio/wav',
  '.webm': 'audio/webm',
  '.ogg': 'audio/ogg',
  '.mp3': 'audio/mpeg',
  '.m4a': 'audio/mp4',
};

const FORMAT_TO_EXT: Record<string, string> = {
  mp3: 'mp3',
  wav: 'wav',
  pcm: 'pcm',
};

/** Redact the API key value from any text that could be returned or logged. */
export function scrub(text: string, apiKey: string): string {
  if (!apiKey) return text;
  return text.split(apiKey).join('***REDACTED***');
}

function mimeFromFilename(filename: string): string {
  return EXT_TO_MIME[path.extname(filename).toLowerCase()] ?? 'application/octet-stream';
}

// ---------------------------------------------------------------------------
// Tool schemas (advertised via ListTools)
// ---------------------------------------------------------------------------

export const TOOLS = [
  {
    name: 'voice_transcribe',
    description:
      'Transcribe an audio file to text via the gbs-voice service (POST /v1/audio/transcriptions). PHI-LOCKED: always sent with phi=true, so only BAA-covered providers ever see the audio. Provide either audioPath (a local file) or audioBase64. Returns the raw transcript (and a formatted transcript when cleanup="format").',
    inputSchema: {
      type: 'object' as const,
      properties: {
        audioPath: {
          type: 'string',
          description: 'Local filesystem path to an audio file (wav/webm/ogg/mp3/m4a, <=25MB / <=60min).',
        },
        audioBase64: {
          type: 'string',
          description: 'Base64-encoded audio bytes (alternative to audioPath).',
        },
        filename: {
          type: 'string',
          description: 'Filename hint used with audioBase64 to infer MIME type (default "audio.wav").',
        },
        language: {
          type: 'string',
          description: 'BCP-47 language code (default "en").',
        },
        cleanup: {
          type: 'string',
          enum: ['none', 'format'],
          description: 'Run the verbatim-preserving cleanup pass server-side (default "none").',
        },
        sessionId: {
          type: 'string',
          description: 'Optional correlation id surfaced in logs/traces (metadata only).',
        },
      },
      required: [] as string[],
    },
  },
  {
    name: 'voice_speak',
    description:
      'Synthesize speech from text via the gbs-voice service (POST /v1/audio/speech). Defaults phi=true. Pass phi=false ONLY when the text contains no PHI (e.g. UI copy) to unlock premium non-BAA voices. By default writes an audio file and returns its path; set returnBase64=true to get base64 audio instead.',
    inputSchema: {
      type: 'object' as const,
      properties: {
        text: {
          type: 'string',
          description: 'Text to synthesize (<=4096 chars).',
        },
        voice: {
          type: 'string',
          description: 'Named GBS voice (e.g. "gbs-default", "gbs-warm"). Per-consumer default otherwise.',
        },
        style: {
          type: 'string',
          description: 'Emotional overlay (e.g. neutral, excited, insight, urgent). Provider-neutral.',
        },
        speed: {
          type: 'number',
          description: 'Speaking rate 0.5-2.0 (default 1.0).',
        },
        responseFormat: {
          type: 'string',
          enum: ['mp3', 'wav', 'pcm'],
          description: 'Audio container (default "mp3").',
        },
        phi: {
          type: 'boolean',
          description: 'PHI flag. Defaults true (fail-closed). Set false ONLY for non-PHI text.',
        },
        returnBase64: {
          type: 'boolean',
          description: 'If true, return base64 audio inline instead of writing a file (default false).',
        },
        sessionId: {
          type: 'string',
          description: 'Optional correlation id (metadata only).',
        },
      },
      required: ['text'],
    },
  },
  {
    name: 'voice_cleanup',
    description:
      'Format a raw transcript (punctuation, casing, disfluency removal) WITHOUT rewriting meaning, via the gbs-voice service (POST /v1/text/cleanup). PHI-LOCKED: always phi=true, BAA-covered cleanup models only. Returns the formatted text plus verbatim_guard status ("pass" | "fail"); on "fail" the raw text is returned unchanged.',
    inputSchema: {
      type: 'object' as const,
      properties: {
        text: {
          type: 'string',
          description: 'Raw transcript to format.',
        },
        mode: {
          type: 'string',
          enum: ['dictation', 'notes', 'verbatim-punctuation'],
          description: 'Cleanup mode (default "dictation").',
        },
        sessionId: {
          type: 'string',
          description: 'Optional correlation id (metadata only).',
        },
      },
      required: ['text'],
    },
  },
  {
    name: 'voice_health',
    description:
      'Check gbs-voice service health and per-provider readiness (GET /health, unauthenticated). Returns { status, providers: { selfhosted, azure-speech, ... } } with each provider "ready" | "cold" | "down".',
    inputSchema: {
      type: 'object' as const,
      properties: {},
      required: [] as string[],
    },
  },
];

// ---------------------------------------------------------------------------
// Dispatch
// ---------------------------------------------------------------------------

async function runTool(
  name: string,
  args: Record<string, unknown>,
  cfg: GbsVoiceConfig,
): Promise<ToolResult> {
  switch (name) {
    case 'voice_transcribe': {
      const audio = await resolveAudioInput(args);
      const result = await client.transcribe(cfg, {
        audio,
        phi: true, // PHI-LOCKED (fail-closed)
        language: typeof args.language === 'string' ? args.language : undefined,
        cleanup: args.cleanup === 'format' ? 'format' : undefined,
        sessionId: typeof args.sessionId === 'string' ? args.sessionId : undefined,
      });
      return jsonResult(result);
    }

    case 'voice_speak': {
      if (typeof args.text !== 'string' || args.text.length === 0) {
        throw new Error('voice_speak requires a non-empty "text" string.');
      }
      // Fail-closed: only an explicit boolean false downgrades PHI.
      const phi = args.phi === false ? false : true;
      const responseFormat = normalizeFormat(args.responseFormat);
      const result = await client.speak(cfg, {
        input: args.text,
        phi,
        voice: typeof args.voice === 'string' ? args.voice : undefined,
        style: typeof args.style === 'string' ? args.style : undefined,
        speed: typeof args.speed === 'number' ? args.speed : undefined,
        responseFormat,
        sessionId: typeof args.sessionId === 'string' ? args.sessionId : undefined,
      });

      if (args.returnBase64 === true) {
        return jsonResult({
          audioBase64: result.audio.toString('base64'),
          contentType: result.contentType,
          provider: result.provider,
          fallback: result.fallback,
          phi,
        });
      }

      const ext = FORMAT_TO_EXT[responseFormat ?? 'mp3'] ?? 'mp3';
      await mkdir(cfg.outputDir, { recursive: true });
      const outPath = path.join(
        cfg.outputDir,
        `gbs-voice-${Date.now()}-${Math.random().toString(36).slice(2, 8)}.${ext}`,
      );
      await writeFile(outPath, result.audio);
      return jsonResult({
        audioPath: outPath,
        bytes: result.audio.length,
        contentType: result.contentType,
        provider: result.provider,
        fallback: result.fallback,
        phi,
      });
    }

    case 'voice_cleanup': {
      if (typeof args.text !== 'string' || args.text.length === 0) {
        throw new Error('voice_cleanup requires a non-empty "text" string.');
      }
      const result = await client.cleanup(cfg, {
        text: args.text,
        phi: true, // PHI-LOCKED (fail-closed)
        mode: normalizeMode(args.mode),
        sessionId: typeof args.sessionId === 'string' ? args.sessionId : undefined,
      });
      return jsonResult({
        text: result.text,
        model: result.model,
        verbatim_guard: result.verbatim_guard,
      });
    }

    case 'voice_health': {
      const result = await client.health(cfg);
      return jsonResult(result);
    }

    default:
      return { content: [{ type: 'text', text: `Unknown tool: ${name}` }], isError: true };
  }
}

/**
 * Public entry point. Wraps runTool with error mapping and — critically —
 * scrubs the API key from every string that leaves the module, whether the
 * result is success or an error.
 */
export async function executeTool(
  name: string,
  args: Record<string, unknown>,
  cfg: GbsVoiceConfig,
): Promise<ToolResult> {
  try {
    const result = await runTool(name, args, cfg);
    return {
      ...result,
      content: result.content.map((c) => ({ ...c, text: scrub(c.text, cfg.apiKey) })),
    };
  } catch (err: unknown) {
    let detail: string;
    if (err instanceof VoiceHttpError) {
      detail = err.message; // code + status only, never content
    } else if (err instanceof Error) {
      detail = err.message;
    } else {
      detail = 'Unknown error';
    }
    return {
      content: [{ type: 'text', text: scrub(`Error calling ${name}: ${detail}`, cfg.apiKey) }],
      isError: true,
    };
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function jsonResult(data: unknown): ToolResult {
  return { content: [{ type: 'text', text: JSON.stringify(data, null, 2) }] };
}

function normalizeFormat(v: unknown): 'mp3' | 'wav' | 'pcm' | undefined {
  return v === 'mp3' || v === 'wav' || v === 'pcm' ? v : undefined;
}

function normalizeMode(
  v: unknown,
): 'dictation' | 'notes' | 'verbatim-punctuation' | undefined {
  return v === 'dictation' || v === 'notes' || v === 'verbatim-punctuation' ? v : undefined;
}

async function resolveAudioInput(
  args: Record<string, unknown>,
): Promise<{ data: Uint8Array; filename: string; mime: string }> {
  if (typeof args.audioPath === 'string' && args.audioPath.length > 0) {
    const data = await readFile(args.audioPath);
    const filename = path.basename(args.audioPath);
    return { data: new Uint8Array(data), filename, mime: mimeFromFilename(filename) };
  }
  if (typeof args.audioBase64 === 'string' && args.audioBase64.length > 0) {
    const data = Buffer.from(args.audioBase64, 'base64');
    const filename =
      typeof args.filename === 'string' && args.filename.length > 0
        ? args.filename
        : 'audio.wav';
    return { data: new Uint8Array(data), filename, mime: mimeFromFilename(filename) };
  }
  throw new Error('voice_transcribe requires either "audioPath" or "audioBase64".');
}
