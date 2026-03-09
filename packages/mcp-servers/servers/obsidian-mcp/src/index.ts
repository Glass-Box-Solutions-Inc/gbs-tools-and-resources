#!/usr/bin/env node
// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology

/**
 * Obsidian MCP Server
 *
 * Bridges Claude (and other MCP clients) to a live Obsidian vault through the
 * Obsidian Local REST API plugin. This lets agents read, write, search, and
 * manage notes without ever needing a filesystem path — the vault is addressed
 * entirely through Obsidian's own REST interface, which handles path resolution,
 * plugin hooks, and live-reload automatically.
 *
 * Prerequisites on the Obsidian side:
 *   1. Obsidian is running (desktop app, not mobile)
 *   2. The "Local REST API" community plugin is installed and enabled
 *   3. OBSIDIAN_API_KEY is set to the token shown in the plugin settings
 */

import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
  type Tool,
} from '@modelcontextprotocol/sdk/types.js';

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const OBSIDIAN_HOST = process.env.OBSIDIAN_HOST || '127.0.0.1';
const OBSIDIAN_PORT = process.env.OBSIDIAN_PORT || '27124';

/**
 * The API key set in Obsidian's Local REST API plugin settings.
 * Without this, every request will return 401. We default to empty string so
 * the server boots even if unconfigured — the error message from the 401 path
 * will guide the user.
 */
const OBSIDIAN_API_KEY = process.env.OBSIDIAN_API_KEY || '';

const BASE_URL = `http://${OBSIDIAN_HOST}:${OBSIDIAN_PORT}`;

/** 15 seconds is generous for local loopback calls, but note operations can
 *  queue if Obsidian is busy saving a large vault. */
const REQUEST_TIMEOUT = 15_000;

// ---------------------------------------------------------------------------
// Tool definitions
// ---------------------------------------------------------------------------

/**
 * The complete list of tools this server exposes.
 * Each tool maps 1:1 to a Local REST API endpoint or a specific combination
 * of endpoint + headers that changes the operation semantics.
 */
export const TOOLS: Tool[] = [
  {
    name: 'obsidian_list_files',
    description:
      'List files and directories in the Obsidian vault root or a specific subdirectory. ' +
      'Returns an array of file/folder names relative to the given path.',
    inputSchema: {
      type: 'object' as const,
      properties: {
        dirPath: {
          type: 'string',
          description:
            'Optional subdirectory path within the vault (e.g. "Projects/2026"). ' +
            'Omit to list the vault root.',
        },
      },
      required: [] as string[],
    },
  },
  {
    name: 'obsidian_read_note',
    description:
      'Read the full markdown content of a note by its vault-relative path. ' +
      'Returns the raw markdown text.',
    inputSchema: {
      type: 'object' as const,
      properties: {
        filePath: {
          type: 'string',
          description:
            'Vault-relative path to the note, including the .md extension (e.g. "Daily/2026-03-09.md").',
        },
      },
      required: ['filePath'],
    },
  },
  {
    name: 'obsidian_search',
    description:
      'Full-text search across all notes in the vault. ' +
      'Returns matching notes with surrounding context snippets. ' +
      'Searches note bodies, not just filenames.',
    inputSchema: {
      type: 'object' as const,
      properties: {
        query: {
          type: 'string',
          description: 'Text to search for across all vault notes.',
        },
        contextLength: {
          type: 'number',
          description:
            'Number of characters of surrounding context to include around each match (default: 100).',
        },
      },
      required: ['query'],
    },
  },
  {
    name: 'obsidian_create_note',
    description:
      'Create a new note at the specified vault path with the given markdown content. ' +
      'Fails with 409 if the file already exists — use obsidian_update_note to modify an existing note.',
    inputSchema: {
      type: 'object' as const,
      properties: {
        filePath: {
          type: 'string',
          description:
            'Vault-relative path for the new note, including the .md extension (e.g. "Projects/new-idea.md"). ' +
            'Intermediate directories are created automatically.',
        },
        content: {
          type: 'string',
          description: 'Full markdown content for the new note.',
        },
      },
      required: ['filePath', 'content'],
    },
  },
  {
    name: 'obsidian_update_note',
    description:
      'Modify an existing note by appending, prepending, or fully overwriting its content. ' +
      'Use "append" to add to the end (e.g. daily log entries), "prepend" to add to the top, ' +
      'or "overwrite" to replace the entire file.',
    inputSchema: {
      type: 'object' as const,
      properties: {
        filePath: {
          type: 'string',
          description: 'Vault-relative path to the existing note, including the .md extension.',
        },
        content: {
          type: 'string',
          description: 'Content to append, prepend, or use as the new full content.',
        },
        mode: {
          type: 'string',
          enum: ['append', 'prepend', 'overwrite'],
          description:
            '"append" adds to the end, "prepend" adds to the beginning, "overwrite" replaces the entire file.',
        },
      },
      required: ['filePath', 'content', 'mode'],
    },
  },
  {
    name: 'obsidian_delete_note',
    description:
      'Permanently delete a note from the vault. This moves the file to the OS trash — ' +
      'it can be recovered from there if deleted by mistake.',
    inputSchema: {
      type: 'object' as const,
      properties: {
        filePath: {
          type: 'string',
          description: 'Vault-relative path to the note to delete, including the .md extension.',
        },
      },
      required: ['filePath'],
    },
  },
  {
    name: 'obsidian_get_frontmatter',
    description:
      'Retrieve the parsed YAML frontmatter of a note as a structured JSON object. ' +
      'Also includes note metadata like creation time, modification time, and tag list. ' +
      'Use this instead of obsidian_read_note when you only need the metadata, not the full body.',
    inputSchema: {
      type: 'object' as const,
      properties: {
        filePath: {
          type: 'string',
          description: 'Vault-relative path to the note, including the .md extension.',
        },
      },
      required: ['filePath'],
    },
  },
  {
    name: 'obsidian_set_frontmatter',
    description:
      'Update specific frontmatter fields on a note without touching the note body. ' +
      'Only the keys you provide will be updated — existing keys not in your payload are preserved. ' +
      'Use this to tag notes, set status fields, or update metadata.',
    inputSchema: {
      type: 'object' as const,
      properties: {
        filePath: {
          type: 'string',
          description: 'Vault-relative path to the note, including the .md extension.',
        },
        frontmatter: {
          type: 'object',
          description:
            'Key-value pairs to set in the frontmatter. ' +
            'Values can be strings, numbers, booleans, or arrays.',
          additionalProperties: true,
        },
      },
      required: ['filePath', 'frontmatter'],
    },
  },
];

// ---------------------------------------------------------------------------
// HTTP helper
// ---------------------------------------------------------------------------

/**
 * Wraps native fetch with the Obsidian API key auth header and a configurable
 * timeout. We avoid axios to keep the dependency footprint minimal — this
 * server should be lightweight enough to spin up instantly as an MCP subprocess.
 *
 * @param path - API path relative to BASE_URL (e.g. "/vault/Notes/foo.md")
 * @param options - Standard RequestInit options; headers will be merged, not replaced
 * @returns The raw fetch Response — callers decide how to parse the body
 * @throws Error if the request times out or the network connection is refused
 */
export async function obsidianFetch(path: string, options: RequestInit = {}): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT);

  const headers: Record<string, string> = {
    // The Local REST API plugin requires Bearer auth on every request
    ...(OBSIDIAN_API_KEY ? { Authorization: `Bearer ${OBSIDIAN_API_KEY}` } : {}),
    ...(options.headers as Record<string, string> | undefined ?? {}),
  };

  try {
    const response = await fetch(`${BASE_URL}${path}`, {
      ...options,
      headers,
      signal: controller.signal,
    });
    return response;
  } finally {
    clearTimeout(timer);
  }
}

// ---------------------------------------------------------------------------
// Tool execution
// ---------------------------------------------------------------------------

/**
 * Routes a named tool call to the appropriate Obsidian REST API endpoint and
 * returns the MCP-standard content block. All user-facing error messages are
 * crafted here so callers get actionable guidance rather than raw HTTP codes.
 *
 * @param name - MCP tool name (must match a key in TOOLS)
 * @param args - Validated arguments from the MCP client
 * @returns MCP content array, with isError=true on failure
 */
export async function executeTool(
  name: string,
  args: Record<string, unknown>,
): Promise<{ content: Array<{ type: string; text: string }>; isError?: boolean }> {
  try {
    switch (name) {
      // -----------------------------------------------------------------------
      case 'obsidian_list_files': {
        const dir = args.dirPath ? String(args.dirPath).replace(/^\/+/, '') : '';
        // Trailing slash tells the plugin to treat the path as a directory
        const apiPath = dir ? `/vault/${encodePathSegments(dir)}/` : '/vault/';
        const res = await obsidianFetch(apiPath);
        await assertOk(res, apiPath);
        const data = await res.json();
        return ok(JSON.stringify(data, null, 2));
      }

      // -----------------------------------------------------------------------
      case 'obsidian_read_note': {
        const filePath = requireString(args, 'filePath');
        const apiPath = `/vault/${encodePathSegments(filePath)}`;
        const res = await obsidianFetch(apiPath, {
          headers: { Accept: 'text/markdown' },
        });
        await assertOk(res, filePath);
        const text = await res.text();
        return ok(text);
      }

      // -----------------------------------------------------------------------
      case 'obsidian_search': {
        const query = requireString(args, 'query');
        const contextLength = typeof args.contextLength === 'number' ? args.contextLength : 100;
        const res = await obsidianFetch('/search/simple/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query, contextLength }),
        });
        await assertOk(res, 'search');
        const data = await res.json();
        return ok(JSON.stringify(data, null, 2));
      }

      // -----------------------------------------------------------------------
      case 'obsidian_create_note': {
        const filePath = requireString(args, 'filePath');
        const content = requireString(args, 'content');
        const apiPath = `/vault/${encodePathSegments(filePath)}`;
        const res = await obsidianFetch(apiPath, {
          method: 'PUT',
          headers: { 'Content-Type': 'text/markdown' },
          body: content,
        });
        await assertOk(res, filePath);
        return ok(`Note created: ${filePath}`);
      }

      // -----------------------------------------------------------------------
      case 'obsidian_update_note': {
        const filePath = requireString(args, 'filePath');
        const content = requireString(args, 'content');
        const mode = requireString(args, 'mode') as 'append' | 'prepend' | 'overwrite';
        const apiPath = `/vault/${encodePathSegments(filePath)}`;

        if (mode === 'overwrite') {
          // PUT replaces the entire file — same as create but file must exist
          const res = await obsidianFetch(apiPath, {
            method: 'PUT',
            headers: { 'Content-Type': 'text/markdown' },
            body: content,
          });
          await assertOk(res, filePath);
          return ok(`Note overwritten: ${filePath}`);
        }

        // append and prepend use POST with an X-Insert-Position header
        // so Obsidian handles the merge atomically inside the plugin
        const insertPosition = mode === 'append' ? 'end' : 'beginning';
        const res = await obsidianFetch(apiPath, {
          method: 'POST',
          headers: {
            'Content-Type': 'text/markdown',
            'X-Insert-Position': insertPosition,
          },
          body: content,
        });
        await assertOk(res, filePath);
        return ok(`Note updated (${mode}): ${filePath}`);
      }

      // -----------------------------------------------------------------------
      case 'obsidian_delete_note': {
        const filePath = requireString(args, 'filePath');
        const apiPath = `/vault/${encodePathSegments(filePath)}`;
        const res = await obsidianFetch(apiPath, { method: 'DELETE' });
        await assertOk(res, filePath);
        return ok(`Note deleted: ${filePath}`);
      }

      // -----------------------------------------------------------------------
      case 'obsidian_get_frontmatter': {
        const filePath = requireString(args, 'filePath');
        const apiPath = `/vault/${encodePathSegments(filePath)}`;
        // The application/vnd.olrapi.note+json accept type causes the plugin to
        // return parsed frontmatter + metadata rather than raw markdown
        const res = await obsidianFetch(apiPath, {
          headers: { Accept: 'application/vnd.olrapi.note+json' },
        });
        await assertOk(res, filePath);
        const data = await res.json();
        return ok(JSON.stringify(data, null, 2));
      }

      // -----------------------------------------------------------------------
      case 'obsidian_set_frontmatter': {
        const filePath = requireString(args, 'filePath');
        const frontmatter = args.frontmatter;
        if (!frontmatter || typeof frontmatter !== 'object' || Array.isArray(frontmatter)) {
          return err('obsidian_set_frontmatter requires a "frontmatter" object');
        }
        const apiPath = `/vault/${encodePathSegments(filePath)}`;
        // PATCH with this content type tells the plugin to merge only the
        // provided keys into the existing frontmatter, leaving other keys alone
        const res = await obsidianFetch(apiPath, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/vnd.olrapi.note+json' },
          body: JSON.stringify(frontmatter),
        });
        await assertOk(res, filePath);
        return ok(`Frontmatter updated: ${filePath}`);
      }

      // -----------------------------------------------------------------------
      default:
        return err(`Unknown tool: ${name}`);
    }
  } catch (error: unknown) {
    // Network-level errors (connection refused, timeout) land here
    const message = error instanceof Error ? error.message : String(error);

    if (message.includes('ECONNREFUSED') || message.includes('fetch failed')) {
      return err(
        'Cannot connect to Obsidian — is it running with the Local REST API plugin enabled? ' +
          `Expected at ${BASE_URL}`,
      );
    }

    if (message.includes('aborted') || message.includes('AbortError')) {
      return err(`Request timed out after ${REQUEST_TIMEOUT / 1000}s — Obsidian may be busy`);
    }

    return err(`Unexpected error in ${name}: ${message}`);
  }
}

// ---------------------------------------------------------------------------
// Private helpers
// ---------------------------------------------------------------------------

/**
 * Encodes a vault-relative file path for use in URL segments. We encode each
 * path component individually so that forward slashes that form the directory
 * structure are preserved, while spaces and special characters are encoded.
 */
function encodePathSegments(filePath: string): string {
  return filePath
    .split('/')
    .map((segment) => encodeURIComponent(segment))
    .join('/');
}

/**
 * Throws a descriptive error for non-2xx HTTP responses so callers don't need
 * to repeat status-code handling logic. The error message is designed to be
 * surfaced directly to the MCP client user.
 */
async function assertOk(res: Response, context: string): Promise<void> {
  if (res.ok) return;

  if (res.status === 401) {
    throw new Error(
      'Unauthorized — check OBSIDIAN_API_KEY matches the token in the Local REST API plugin settings',
    );
  }

  if (res.status === 404) {
    throw new Error(`File not found: ${context}`);
  }

  if (res.status === 409) {
    throw new Error(
      `Conflict: ${context} already exists. Use obsidian_update_note to modify an existing note.`,
    );
  }

  // Attempt to include any body text in the error for debugging
  let body = '';
  try {
    body = await res.text();
  } catch {
    // Swallow — we just won't include a body excerpt
  }

  throw new Error(
    `Obsidian API error ${res.status} for ${context}${body ? ': ' + body.slice(0, 200) : ''}`,
  );
}

/** Extracts a required string argument and throws a clear error if missing. */
function requireString(args: Record<string, unknown>, key: string): string {
  const val = args[key];
  if (typeof val !== 'string' || val.trim() === '') {
    throw new Error(`Missing required argument: "${key}"`);
  }
  return val;
}

/** Constructs a successful MCP content response. */
function ok(text: string): { content: Array<{ type: string; text: string }> } {
  return { content: [{ type: 'text', text }] };
}

/** Constructs a failed MCP content response. */
function err(text: string): { content: Array<{ type: string; text: string }>; isError: boolean } {
  return { content: [{ type: 'text', text }], isError: true };
}

// ---------------------------------------------------------------------------
// Server bootstrap
// ---------------------------------------------------------------------------

const server = new Server(
  { name: 'obsidian-mcp', version: '1.0.0' },
  { capabilities: { tools: {} } },
);

server.setRequestHandler(ListToolsRequestSchema, async () => ({ tools: TOOLS }));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;
  return executeTool(name, (args ?? {}) as Record<string, unknown>);
});

server.onerror = (error) => {
  console.error('[obsidian-mcp] Server error:', error);
};

process.on('SIGINT', async () => {
  await server.close();
  process.exit(0);
});

// Guard: only connect transport when run as CLI, not when imported by tests.
// VITEST is set in the environment by vitest runner, so we can detect it reliably.
const isDirectRun = process.env.VITEST === undefined;
if (isDirectRun) {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error(`[obsidian-mcp] Connected — vault at ${BASE_URL}`);
}
