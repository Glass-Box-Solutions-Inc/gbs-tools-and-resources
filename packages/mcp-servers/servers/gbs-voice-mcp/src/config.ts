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

export interface GbsVoiceConfig {
  /** Base URL of the gbs-voice service, no trailing slash. */
  baseUrl: string;
  /** Per-consumer Bearer API key (Key Vault: gbs-voice-key-<consumer>). Server-side only. */
  apiKey: string;
  /** Directory where voice_speak writes synthesized audio files. */
  outputDir: string;
}

export function loadConfig(env: NodeJS.ProcessEnv = process.env): GbsVoiceConfig {
  const baseUrl = (env.GBS_VOICE_BASE_URL || DEFAULT_BASE_URL).replace(/\/+$/, '');
  const apiKey = env.GBS_VOICE_API_KEY ?? '';
  const outputDir =
    env.GBS_VOICE_OUTPUT_DIR || path.join(os.tmpdir(), 'gbs-voice-mcp');
  return { baseUrl, apiKey, outputDir };
}
