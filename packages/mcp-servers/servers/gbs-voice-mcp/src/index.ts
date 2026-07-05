#!/usr/bin/env node
// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology

/**
 * gbs-voice MCP Server
 *
 * Exposes the live gbs-voice service (transcription, TTS, transcript cleanup,
 * health) as MCP tools over stdio, so Claude Code / Pulse / any MCP client can
 * call voice operations through the frozen VoiceProvider seam contract
 * (gbs-voice/docs/SEAM_CONTRACT.md v1) — never a vendor SDK.
 *
 * Auth: the per-consumer Bearer API key is read from GBS_VOICE_API_KEY, held
 * server-side, and never logged or returned. PHI defaults are fail-closed:
 * transcribe/cleanup are PHI-locked; speak defaults phi=true.
 *
 * Env:
 *   GBS_VOICE_API_KEY    (required for authenticated tools)  Bearer key
 *   GBS_VOICE_BASE_URL   (optional)  overrides the default service URL
 *   GBS_VOICE_OUTPUT_DIR (optional)  where voice_speak writes audio files
 */

import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
  type CallToolResult,
} from '@modelcontextprotocol/sdk/types.js';
import { loadConfig } from './config.js';
import { TOOLS, executeTool, scrub } from './tools.js';

const config = loadConfig();

const server = new Server(
  { name: 'gbs-voice-mcp', version: '1.0.0' },
  { capabilities: { tools: {} } },
);

server.setRequestHandler(ListToolsRequestSchema, async () => ({ tools: TOOLS }));

server.setRequestHandler(
  CallToolRequestSchema,
  async (request): Promise<CallToolResult> => {
    const { name, arguments: args } = request.params;
    const result = await executeTool(
      name,
      (args ?? {}) as Record<string, unknown>,
      config,
    );
    // executeTool returns a valid CallToolResult shape (content + isError);
    // the cast bridges the SDK's broader task-aware result union.
    return result as CallToolResult;
  },
);

server.onerror = (error) => {
  // Log only the scrubbed message (never the stack/detail, which could in
  // theory carry the key), and redact the key value defensively.
  const msg = error instanceof Error ? error.message : String(error);
  console.error('[gbs-voice-mcp] Server error:', scrub(msg, config.apiKey));
};

process.on('SIGINT', async () => {
  await server.close();
  process.exit(0);
});

const transport = new StdioServerTransport();
await server.connect(transport);

// Log the service URL and whether a key is configured — never the key itself.
console.error(
  `[gbs-voice-mcp] Connected. Service: ${config.baseUrl} | API key: ${
    config.apiKey ? 'set' : 'MISSING (authenticated tools will 401)'
  }`,
);
