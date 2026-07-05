// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology

/**
 * Runtime configuration for the gbs-voice MCP server.
 *
 * The API key is read from the environment (GBS_VOICE_API_KEY) — supplied by
 * the MCP client's config `env` block — and is NEVER hardcoded, logged, or
 * echoed into any tool output. See scrub() in tools.ts.
 */

import os from 'node:os';
import path from 'node:path';

/** Live gbs-voice service (Azure Container App), used when GBS_VOICE_BASE_URL is unset. */
export const DEFAULT_BASE_URL =
  'https://gbs-voice.wittycliff-d624a17c.westus2.azurecontainerapps.io';

/** Hard ceiling on audio bytes read from disk / base64 and on TTS responses. */
export const DEFAULT_MAX_AUDIO_BYTES = 25 * 1024 * 1024; // 25 MB

export interface GbsVoiceConfig {
  /** Base URL of the gbs-voice service, no trailing slash. */
  baseUrl: string;
  /** Per-consumer Bearer API key (Key Vault: gbs-voice-key-<consumer>). Server-side only. */
  apiKey: string;
  /** Directory where voice_speak writes synthesized audio files. */
  outputDir: string;
  /**
   * Sandbox root for voice_transcribe's `audioPath`. Any path that resolves
   * (after symlink realpath) outside this directory is REJECTED — this is the
   * guard against arbitrary-file exfiltration (e.g. ~/.ssh/id_rsa, .env).
   * Defaults to the process working directory.
   */
  inputDir: string;
  /** Max bytes for any audio read (audioPath / audioBase64) or TTS response. */
  maxAudioBytes: number;
}

function positiveIntOr(fallback: number, raw: string | undefined): number {
  if (!raw) return fallback;
  const n = Number(raw);
  return Number.isFinite(n) && n > 0 ? Math.floor(n) : fallback;
}

export function loadConfig(env: NodeJS.ProcessEnv = process.env): GbsVoiceConfig {
  const baseUrl = (env.GBS_VOICE_BASE_URL || DEFAULT_BASE_URL).replace(/\/+$/, '');
  const apiKey = env.GBS_VOICE_API_KEY ?? '';
  const outputDir =
    env.GBS_VOICE_OUTPUT_DIR || path.join(os.tmpdir(), 'gbs-voice-mcp');
  const inputDir = path.resolve(env.GBS_VOICE_INPUT_DIR || process.cwd());
  const maxAudioBytes = positiveIntOr(
    DEFAULT_MAX_AUDIO_BYTES,
    env.GBS_VOICE_MAX_AUDIO_BYTES,
  );
  return { baseUrl, apiKey, outputDir, inputDir, maxAudioBytes };
}
