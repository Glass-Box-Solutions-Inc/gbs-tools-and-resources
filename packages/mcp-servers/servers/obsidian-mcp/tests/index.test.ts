// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology

/**
 * Unit tests for the Obsidian MCP server.
 *
 * We mock global.fetch so tests never require a live Obsidian instance. Every
 * test exercises executeTool() end-to-end — the same code path the MCP runtime
 * calls — so we're testing real behaviour rather than implementation internals.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { executeTool, TOOLS } from '../src/index.js';

// ---------------------------------------------------------------------------
// Fetch mock helpers
// ---------------------------------------------------------------------------

/**
 * Builds a minimal Response-like object that satisfies the parts of the
 * Response interface our code actually touches.
 */
function mockResponse(
  status: number,
  body: unknown,
  contentType = 'application/json',
): Response {
  const isOk = status >= 200 && status < 300;
  const bodyText = typeof body === 'string' ? body : JSON.stringify(body);

  return {
    ok: isOk,
    status,
    headers: new Headers({ 'Content-Type': contentType }),
    text: async () => bodyText,
    json: async () => (typeof body === 'string' ? JSON.parse(body) : body),
  } as unknown as Response;
}

/** Installs a one-shot fetch mock returning the given response. */
function mockFetch(response: Response) {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(response));
}

/** Installs a fetch mock that rejects with the given error. */
function mockFetchError(error: Error) {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValueOnce(error));
}

// ---------------------------------------------------------------------------
// Setup / teardown
// ---------------------------------------------------------------------------

beforeEach(() => {
  // Start each test with a clean fetch mock so tests don't bleed into each other
  vi.stubGlobal('fetch', vi.fn());
});

afterEach(() => {
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// TOOLS array sanity checks
// ---------------------------------------------------------------------------

describe('TOOLS definition', () => {
  it('exports exactly 8 tools', () => {
    expect(TOOLS).toHaveLength(8);
  });

  it('every tool has a name, description, and inputSchema', () => {
    for (const tool of TOOLS) {
      expect(tool.name).toBeTruthy();
      expect(tool.description).toBeTruthy();
      expect(tool.inputSchema).toBeTruthy();
    }
  });

  it('tool names match expected set', () => {
    const names = TOOLS.map((t) => t.name).sort();
    expect(names).toEqual([
      'obsidian_create_note',
      'obsidian_delete_note',
      'obsidian_get_frontmatter',
      'obsidian_list_files',
      'obsidian_read_note',
      'obsidian_search',
      'obsidian_set_frontmatter',
      'obsidian_update_note',
    ]);
  });
});

// ---------------------------------------------------------------------------
// obsidian_list_files
// ---------------------------------------------------------------------------

describe('obsidian_list_files', () => {
  it('returns file list for vault root when no dirPath given', async () => {
    const payload = { files: ['note1.md', 'note2.md', 'subfolder/'] };
    mockFetch(mockResponse(200, payload));

    const result = await executeTool('obsidian_list_files', {});

    expect(result.isError).toBeFalsy();
    expect(result.content[0].text).toContain('note1.md');
  });

  it('requests the correct path for a subdirectory', async () => {
    const fetchSpy = vi.fn().mockResolvedValueOnce(mockResponse(200, { files: [] }));
    vi.stubGlobal('fetch', fetchSpy);

    await executeTool('obsidian_list_files', { dirPath: 'Projects/2026' });

    const calledUrl = fetchSpy.mock.calls[0][0] as string;
    // Trailing slash is required so Obsidian treats it as a directory listing
    expect(calledUrl).toContain('/vault/Projects/2026/');
  });

  it('handles empty vault gracefully', async () => {
    mockFetch(mockResponse(200, { files: [] }));

    const result = await executeTool('obsidian_list_files', {});

    expect(result.isError).toBeFalsy();
    expect(result.content[0].text).toContain('"files"');
  });
});

// ---------------------------------------------------------------------------
// obsidian_read_note
// ---------------------------------------------------------------------------

describe('obsidian_read_note', () => {
  it('returns the note markdown content on success', async () => {
    const noteContent = '# Hello\n\nThis is my note.';
    mockFetch(mockResponse(200, noteContent, 'text/markdown'));

    const result = await executeTool('obsidian_read_note', { filePath: 'Notes/hello.md' });

    expect(result.isError).toBeFalsy();
    expect(result.content[0].text).toBe(noteContent);
  });

  it('returns an error when the note does not exist (404)', async () => {
    mockFetch(mockResponse(404, 'Not Found'));

    const result = await executeTool('obsidian_read_note', { filePath: 'Missing/note.md' });

    expect(result.isError).toBe(true);
    expect(result.content[0].text).toContain('File not found');
    expect(result.content[0].text).toContain('Missing/note.md');
  });

  it('sends the Accept: text/markdown header', async () => {
    const fetchSpy = vi.fn().mockResolvedValueOnce(mockResponse(200, '# Note', 'text/markdown'));
    vi.stubGlobal('fetch', fetchSpy);

    await executeTool('obsidian_read_note', { filePath: 'Daily/log.md' });

    const headers = fetchSpy.mock.calls[0][1].headers as Record<string, string>;
    expect(headers['Accept']).toBe('text/markdown');
  });
});

// ---------------------------------------------------------------------------
// obsidian_search
// ---------------------------------------------------------------------------

describe('obsidian_search', () => {
  it('returns search matches on success', async () => {
    const searchResult = [
      { filename: 'Notes/meeting.md', matches: [{ context: 'discussed the budget', match: { start: 10, end: 18 } }] },
    ];
    mockFetch(mockResponse(200, searchResult));

    const result = await executeTool('obsidian_search', { query: 'budget' });

    expect(result.isError).toBeFalsy();
    expect(result.content[0].text).toContain('meeting.md');
  });

  it('returns an empty array when no results match', async () => {
    mockFetch(mockResponse(200, []));

    const result = await executeTool('obsidian_search', { query: 'xyzzy_no_match' });

    expect(result.isError).toBeFalsy();
    expect(result.content[0].text).toBe('[]');
  });

  it('sends the contextLength parameter in the request body', async () => {
    const fetchSpy = vi.fn().mockResolvedValueOnce(mockResponse(200, []));
    vi.stubGlobal('fetch', fetchSpy);

    await executeTool('obsidian_search', { query: 'test', contextLength: 250 });

    const body = JSON.parse(fetchSpy.mock.calls[0][1].body as string);
    expect(body.contextLength).toBe(250);
    expect(body.query).toBe('test');
  });

  it('defaults contextLength to 100 when not provided', async () => {
    const fetchSpy = vi.fn().mockResolvedValueOnce(mockResponse(200, []));
    vi.stubGlobal('fetch', fetchSpy);

    await executeTool('obsidian_search', { query: 'default context' });

    const body = JSON.parse(fetchSpy.mock.calls[0][1].body as string);
    expect(body.contextLength).toBe(100);
  });
});

// ---------------------------------------------------------------------------
// obsidian_create_note
// ---------------------------------------------------------------------------

describe('obsidian_create_note', () => {
  it('sends PUT request with correct content type', async () => {
    const fetchSpy = vi.fn().mockResolvedValueOnce(mockResponse(200, ''));
    vi.stubGlobal('fetch', fetchSpy);

    await executeTool('obsidian_create_note', {
      filePath: 'New/note.md',
      content: '# New Note',
    });

    const [url, options] = fetchSpy.mock.calls[0];
    expect(url).toContain('/vault/New/note.md');
    expect(options.method).toBe('PUT');
    const headers = options.headers as Record<string, string>;
    expect(headers['Content-Type']).toBe('text/markdown');
    expect(options.body).toBe('# New Note');
  });

  it('returns success message with file path', async () => {
    mockFetch(mockResponse(200, ''));

    const result = await executeTool('obsidian_create_note', {
      filePath: 'Projects/roadmap.md',
      content: '# Roadmap',
    });

    expect(result.isError).toBeFalsy();
    expect(result.content[0].text).toContain('Projects/roadmap.md');
  });

  it('returns conflict error when file already exists (409)', async () => {
    mockFetch(mockResponse(409, 'Conflict'));

    const result = await executeTool('obsidian_create_note', {
      filePath: 'Existing/note.md',
      content: '# Duplicate',
    });

    expect(result.isError).toBe(true);
    expect(result.content[0].text).toContain('already exists');
    expect(result.content[0].text).toContain('obsidian_update_note');
  });
});

// ---------------------------------------------------------------------------
// obsidian_update_note
// ---------------------------------------------------------------------------

describe('obsidian_update_note', () => {
  it('sends POST with X-Insert-Position: end for append mode', async () => {
    const fetchSpy = vi.fn().mockResolvedValueOnce(mockResponse(200, ''));
    vi.stubGlobal('fetch', fetchSpy);

    await executeTool('obsidian_update_note', {
      filePath: 'Daily/log.md',
      content: '\n- new entry',
      mode: 'append',
    });

    const [, options] = fetchSpy.mock.calls[0];
    expect(options.method).toBe('POST');
    const headers = options.headers as Record<string, string>;
    expect(headers['X-Insert-Position']).toBe('end');
  });

  it('sends POST with X-Insert-Position: beginning for prepend mode', async () => {
    const fetchSpy = vi.fn().mockResolvedValueOnce(mockResponse(200, ''));
    vi.stubGlobal('fetch', fetchSpy);

    await executeTool('obsidian_update_note', {
      filePath: 'Daily/log.md',
      content: '# Header\n',
      mode: 'prepend',
    });

    const [, options] = fetchSpy.mock.calls[0];
    expect(options.method).toBe('POST');
    const headers = options.headers as Record<string, string>;
    expect(headers['X-Insert-Position']).toBe('beginning');
  });

  it('sends PUT for overwrite mode', async () => {
    const fetchSpy = vi.fn().mockResolvedValueOnce(mockResponse(200, ''));
    vi.stubGlobal('fetch', fetchSpy);

    await executeTool('obsidian_update_note', {
      filePath: 'Notes/replaced.md',
      content: '# Fresh Start',
      mode: 'overwrite',
    });

    const [, options] = fetchSpy.mock.calls[0];
    expect(options.method).toBe('PUT');
    // Overwrite should NOT set X-Insert-Position
    const headers = options.headers as Record<string, string>;
    expect(headers['X-Insert-Position']).toBeUndefined();
  });

  it('returns success message indicating the mode used', async () => {
    mockFetch(mockResponse(200, ''));

    const result = await executeTool('obsidian_update_note', {
      filePath: 'Notes/log.md',
      content: 'appended text',
      mode: 'append',
    });

    expect(result.isError).toBeFalsy();
    expect(result.content[0].text).toContain('append');
  });
});

// ---------------------------------------------------------------------------
// obsidian_delete_note
// ---------------------------------------------------------------------------

describe('obsidian_delete_note', () => {
  it('sends DELETE request to the correct path', async () => {
    const fetchSpy = vi.fn().mockResolvedValueOnce(mockResponse(204, ''));
    vi.stubGlobal('fetch', fetchSpy);

    await executeTool('obsidian_delete_note', { filePath: 'Archive/old.md' });

    const [url, options] = fetchSpy.mock.calls[0];
    expect(options.method).toBe('DELETE');
    expect(url).toContain('/vault/Archive/old.md');
  });

  it('returns success message on successful delete', async () => {
    mockFetch(mockResponse(204, ''));

    const result = await executeTool('obsidian_delete_note', { filePath: 'Archive/old.md' });

    expect(result.isError).toBeFalsy();
    expect(result.content[0].text).toContain('Archive/old.md');
  });

  it('returns not-found error when file is missing', async () => {
    mockFetch(mockResponse(404, 'Not Found'));

    const result = await executeTool('obsidian_delete_note', { filePath: 'Ghost/note.md' });

    expect(result.isError).toBe(true);
    expect(result.content[0].text).toContain('File not found');
  });
});

// ---------------------------------------------------------------------------
// obsidian_get_frontmatter
// ---------------------------------------------------------------------------

describe('obsidian_get_frontmatter', () => {
  it('sends the vnd.olrapi.note+json Accept header', async () => {
    const fetchSpy = vi.fn().mockResolvedValueOnce(
      mockResponse(200, { frontmatter: { tags: ['work'] }, content: '' }),
    );
    vi.stubGlobal('fetch', fetchSpy);

    await executeTool('obsidian_get_frontmatter', { filePath: 'Notes/tagged.md' });

    const headers = fetchSpy.mock.calls[0][1].headers as Record<string, string>;
    expect(headers['Accept']).toBe('application/vnd.olrapi.note+json');
  });

  it('returns parsed frontmatter JSON', async () => {
    const noteJson = {
      frontmatter: { title: 'My Note', tags: ['important'], status: 'active' },
      stat: { ctime: 1700000000000, mtime: 1700000001000 },
    };
    mockFetch(mockResponse(200, noteJson));

    const result = await executeTool('obsidian_get_frontmatter', { filePath: 'Notes/meta.md' });

    expect(result.isError).toBeFalsy();
    const parsed = JSON.parse(result.content[0].text);
    expect(parsed.frontmatter.title).toBe('My Note');
    expect(parsed.frontmatter.tags).toContain('important');
  });

  it('returns not-found error for missing note', async () => {
    mockFetch(mockResponse(404, 'Not Found'));

    const result = await executeTool('obsidian_get_frontmatter', { filePath: 'Missing/note.md' });

    expect(result.isError).toBe(true);
    expect(result.content[0].text).toContain('File not found');
  });
});

// ---------------------------------------------------------------------------
// obsidian_set_frontmatter
// ---------------------------------------------------------------------------

describe('obsidian_set_frontmatter', () => {
  it('sends PATCH with application/vnd.olrapi.note+json content type', async () => {
    const fetchSpy = vi.fn().mockResolvedValueOnce(mockResponse(200, ''));
    vi.stubGlobal('fetch', fetchSpy);

    await executeTool('obsidian_set_frontmatter', {
      filePath: 'Notes/update.md',
      frontmatter: { status: 'done', reviewed: true },
    });

    const [, options] = fetchSpy.mock.calls[0];
    expect(options.method).toBe('PATCH');
    const headers = options.headers as Record<string, string>;
    expect(headers['Content-Type']).toBe('application/vnd.olrapi.note+json');
  });

  it('serializes the frontmatter object as the request body', async () => {
    const fetchSpy = vi.fn().mockResolvedValueOnce(mockResponse(200, ''));
    vi.stubGlobal('fetch', fetchSpy);

    const frontmatter = { priority: 1, tags: ['urgent', 'review'] };
    await executeTool('obsidian_set_frontmatter', {
      filePath: 'Notes/priority.md',
      frontmatter,
    });

    const body = JSON.parse(fetchSpy.mock.calls[0][1].body as string);
    expect(body.priority).toBe(1);
    expect(body.tags).toEqual(['urgent', 'review']);
  });

  it('returns validation error when frontmatter is not an object', async () => {
    const result = await executeTool('obsidian_set_frontmatter', {
      filePath: 'Notes/bad.md',
      frontmatter: 'not-an-object',
    });

    expect(result.isError).toBe(true);
    expect(result.content[0].text).toContain('frontmatter');
  });

  it('returns success message with file path', async () => {
    mockFetch(mockResponse(200, ''));

    const result = await executeTool('obsidian_set_frontmatter', {
      filePath: 'Notes/fm.md',
      frontmatter: { key: 'value' },
    });

    expect(result.isError).toBeFalsy();
    expect(result.content[0].text).toContain('Notes/fm.md');
  });
});

// ---------------------------------------------------------------------------
// Error handling — connection / auth failures
// ---------------------------------------------------------------------------

describe('connection and auth error handling', () => {
  it('returns actionable message when Obsidian is not running (ECONNREFUSED)', async () => {
    const connError = new Error('fetch failed');
    (connError as NodeJS.ErrnoException).code = 'ECONNREFUSED';
    // The error message needs to include the substring the code checks
    const fetchError = Object.assign(new Error('fetch failed'), { cause: connError });
    mockFetchError(fetchError);

    const result = await executeTool('obsidian_read_note', { filePath: 'any.md' });

    expect(result.isError).toBe(true);
    expect(result.content[0].text).toContain('Cannot connect to Obsidian');
  });

  it('returns auth error message on 401', async () => {
    mockFetch(mockResponse(401, 'Unauthorized'));

    const result = await executeTool('obsidian_read_note', { filePath: 'secure.md' });

    expect(result.isError).toBe(true);
    expect(result.content[0].text).toContain('Unauthorized');
    expect(result.content[0].text).toContain('OBSIDIAN_API_KEY');
  });

  it('returns timeout message when fetch is aborted', async () => {
    // Simulate AbortController firing — fetch rejects with an AbortError
    const abortError = new DOMException('The operation was aborted.', 'AbortError');
    mockFetchError(abortError);

    const result = await executeTool('obsidian_read_note', { filePath: 'slow.md' });

    expect(result.isError).toBe(true);
    expect(result.content[0].text).toContain('timed out');
  });

  it('returns unknown tool error for unrecognized tool names', async () => {
    const result = await executeTool('obsidian_does_not_exist', {});

    expect(result.isError).toBe(true);
    expect(result.content[0].text).toContain('Unknown tool');
  });
});

// ---------------------------------------------------------------------------
// Path encoding
// ---------------------------------------------------------------------------

describe('path encoding', () => {
  it('encodes spaces in file paths correctly', async () => {
    const fetchSpy = vi.fn().mockResolvedValueOnce(mockResponse(200, '# Note', 'text/markdown'));
    vi.stubGlobal('fetch', fetchSpy);

    await executeTool('obsidian_read_note', { filePath: 'My Notes/space note.md' });

    const url = fetchSpy.mock.calls[0][0] as string;
    // Space should be encoded as %20
    expect(url).toContain('My%20Notes/space%20note.md');
  });

  it('preserves directory separators when encoding', async () => {
    const fetchSpy = vi.fn().mockResolvedValueOnce(mockResponse(200, '# Note', 'text/markdown'));
    vi.stubGlobal('fetch', fetchSpy);

    await executeTool('obsidian_read_note', { filePath: 'Projects/2026/Q1/kickoff.md' });

    const url = fetchSpy.mock.calls[0][0] as string;
    // Slashes should NOT be encoded — they are directory separators
    expect(url).toContain('/vault/Projects/2026/Q1/kickoff.md');
  });
});
