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

import { readFile, writeFile, mkdir, realpath, stat } from 'node:fs/promises';
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
  '.flac': 'audio/flac',
};

/** Only these extensions may be read from disk / accepted as base64 input. */
const AUDIO_EXTENSIONS = new Set(Object.keys(EXT_TO_MIME));

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
          description:
            'Path to an audio file (wav/mp3/m4a/ogg/flac/webm, <=25MB). MUST resolve inside GBS_VOICE_INPUT_DIR (default: cwd) — paths that escape the sandbox, symlinks pointing outside it, non-audio extensions, and non-audio content are rejected without upload.',
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
      const audio = await resolveAudioInput(args, cfg);
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

interface AudioInput {
  data: Uint8Array;
  filename: string;
  mime: string;
}

async function resolveAudioInput(
  args: Record<string, unknown>,
  cfg: GbsVoiceConfig,
): Promise<AudioInput> {
  if (typeof args.audioPath === 'string' && args.audioPath.length > 0) {
    return readSandboxedAudioFile(args.audioPath, cfg);
  }
  if (typeof args.audioBase64 === 'string' && args.audioBase64.length > 0) {
    const data = Buffer.from(args.audioBase64, 'base64');
    if (data.length === 0) {
      throw new Error('voice_transcribe: audioBase64 decoded to zero bytes.');
    }
    assertWithinSize(data.length, cfg.maxAudioBytes);
    const filename =
      typeof args.filename === 'string' && args.filename.length > 0
        ? path.basename(args.filename)
        : 'audio.wav';
    assertAudioExtension(filename);
    const bytes = new Uint8Array(data);
    assertLooksLikeAudio(bytes);
    return { data: bytes, filename, mime: mimeFromFilename(filename) };
  }
  throw new Error('voice_transcribe requires either "audioPath" or "audioBase64".');
}

/**
 * Read an audio file from disk, but ONLY from inside the configured sandbox
 * root (cfg.inputDir). Defends against arbitrary-file exfiltration:
 *   1. Lexical containment — reject `../` traversal (works even for a path
 *      that doesn't exist, with a clear message).
 *   2. Extension allowlist — reject anything that isn't a known audio type
 *      (blocks .env, id_rsa, .pem, /etc/passwd, ...).
 *   3. Symlink defense — realpath() both the file and the root and re-check
 *      containment, so a symlink inside the root that points outside is caught.
 *   4. Size cap — stat() before read, and re-check the read length.
 *   5. Magic-byte sniff — the content must actually look like audio.
 */
async function readSandboxedAudioFile(
  audioPath: string,
  cfg: GbsVoiceConfig,
): Promise<AudioInput> {
  const root = path.resolve(cfg.inputDir);
  const resolved = path.resolve(root, audioPath);

  // (1) lexical containment
  if (resolved !== root && !resolved.startsWith(root + path.sep)) {
    throw new Error(
      'voice_transcribe: audioPath escapes the allowed input directory (set GBS_VOICE_INPUT_DIR).',
    );
  }

  // (2) extension allowlist — before touching the filesystem
  assertAudioExtension(resolved);

  // (3) symlink defense — realpath and re-check containment
  const realRoot = await realpath(root).catch(() => root);
  let real: string;
  try {
    real = await realpath(resolved);
  } catch {
    // ENOENT / EACCES — never echo the absolute path back to the caller
    throw new Error('voice_transcribe: audioPath not found or not readable.');
  }
  if (real !== realRoot && !real.startsWith(realRoot + path.sep)) {
    throw new Error(
      'voice_transcribe: audioPath escapes the allowed input directory via a symlink (set GBS_VOICE_INPUT_DIR).',
    );
  }

  // (4) size cap — stat before read
  const info = await stat(real);
  if (!info.isFile()) {
    throw new Error('voice_transcribe: audioPath is not a regular file.');
  }
  assertWithinSize(info.size, cfg.maxAudioBytes);

  const buf = await readFile(real);
  assertWithinSize(buf.length, cfg.maxAudioBytes);

  const bytes = new Uint8Array(buf);
  // (5) magic-byte sniff
  assertLooksLikeAudio(bytes);

  const filename = path.basename(real);
  return { data: bytes, filename, mime: mimeFromFilename(filename) };
}

function assertAudioExtension(nameOrPath: string): void {
  const ext = path.extname(nameOrPath).toLowerCase();
  if (!AUDIO_EXTENSIONS.has(ext)) {
    throw new Error(
      `voice_transcribe: unsupported audio extension "${ext || '(none)'}". Allowed: ${[
        ...AUDIO_EXTENSIONS,
      ].join(', ')}.`,
    );
  }
}

function assertWithinSize(bytes: number, max: number): void {
  if (bytes > max) {
    throw new Error(
      `voice_transcribe: audio exceeds the ${Math.round(max / (1024 * 1024))}MB limit.`,
    );
  }
}

function assertLooksLikeAudio(buf: Uint8Array): void {
  if (!looksLikeAudio(buf)) {
    throw new Error(
      'voice_transcribe: content is not a recognized audio format (wav/mp3/m4a/ogg/flac/webm).',
    );
  }
}

/** Sniff the leading bytes against known audio-container signatures. */
export function looksLikeAudio(buf: Uint8Array): boolean {
  if (buf.length < 4) return false;
  const ascii = (off: number, s: string): boolean =>
    off + s.length <= buf.length &&
    [...s].every((ch, i) => buf[off + i] === ch.charCodeAt(0));

  if (ascii(0, 'RIFF') && ascii(8, 'WAVE')) return true; // WAV
  if (ascii(0, 'ID3')) return true; // MP3 with ID3 tag
  if (buf[0] === 0xff && (buf[1] & 0xe0) === 0xe0) return true; // MP3 frame sync
  if (ascii(0, 'OggS')) return true; // OGG
  if (ascii(0, 'fLaC')) return true; // FLAC
  if (ascii(4, 'ftyp')) return true; // M4A / MP4 container
  if (buf[0] === 0x1a && buf[1] === 0x45 && buf[2] === 0xdf && buf[3] === 0xa3)
    return true; // WEBM / Matroska (EBML)
  return false;
}
