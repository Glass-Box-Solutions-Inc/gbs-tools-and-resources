// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import os from 'node:os';
import path from 'node:path';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { executeTool, TOOLS, scrub } from '../src/tools.js';
import { loadConfig, DEFAULT_BASE_URL } from '../src/config.js';
import type { GbsVoiceConfig } from '../src/config.js';

const API_KEY = 'sk-gbs-voice-SUPERSECRET-abc123';

let cfg: GbsVoiceConfig;
let tmpDir: string;

beforeEach(async () => {
  tmpDir = await mkdtemp(path.join(os.tmpdir(), 'gbs-voice-mcp-test-'));
  cfg = { baseUrl: 'https://voice.test', apiKey: API_KEY, outputDir: tmpDir };
});

afterEach(async () => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  await rm(tmpDir, { recursive: true, force: true });
});

/** Build a fetch mock that records its call and returns the given Response. */
function stubFetch(response: Response) {
  const fn = vi.fn(async () => response);
  vi.stubGlobal('fetch', fn);
  return fn;
}

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
    ...init,
  });
}

function lastCall(fn: ReturnType<typeof vi.fn>): { url: string; init: RequestInit } {
  const [url, init] = fn.mock.calls.at(-1) as [string, RequestInit];
  return { url, init };
}

function authHeaderOf(init: RequestInit): string | undefined {
  const h = init.headers as Record<string, string> | undefined;
  return h?.Authorization;
}

// ---------------------------------------------------------------------------

describe('tool registry', () => {
  it('exposes exactly the 4 documented tools', () => {
    expect(TOOLS.map((t) => t.name).sort()).toEqual([
      'voice_cleanup',
      'voice_health',
      'voice_speak',
      'voice_transcribe',
    ]);
  });

  it('every tool has an object inputSchema', () => {
    for (const t of TOOLS) {
      expect(t.inputSchema.type).toBe('object');
      expect(typeof t.description).toBe('string');
    }
  });
});

describe('voice_transcribe', () => {
  it('POSTs multipart to /v1/audio/transcriptions with Bearer auth and phi=true by default', async () => {
    const fetchMock = stubFetch(
      jsonResponse({ text: 'so the patient reported pain', language: 'en', provider: 'selfhosted' }),
    );

    const res = await executeTool(
      'voice_transcribe',
      { audioBase64: Buffer.from('fake-audio').toString('base64'), filename: 'note.wav' },
      cfg,
    );

    const { url, init } = lastCall(fetchMock);
    expect(url).toBe('https://voice.test/v1/audio/transcriptions');
    expect(init.method).toBe('POST');
    expect(authHeaderOf(init)).toBe(`Bearer ${API_KEY}`);

    // Body is FormData; assert phi default = "true" (fail-closed).
    const form = init.body as FormData;
    expect(form).toBeInstanceOf(FormData);
    expect(form.get('phi')).toBe('true');
    expect(form.get('language')).toBe('en');

    // multipart Content-Type must be left for fetch to set the boundary.
    const headers = (init.headers ?? {}) as Record<string, string>;
    expect(headers['Content-Type']).toBeUndefined();

    expect(res.isError).toBeUndefined();
    expect(res.content[0].text).toContain('so the patient reported pain');
  });

  it('is PHI-locked: phi stays true even if caller passes phi=false', async () => {
    const fetchMock = stubFetch(jsonResponse({ text: 'x' }));
    await executeTool(
      'voice_transcribe',
      { audioBase64: Buffer.from('a').toString('base64'), phi: false },
      cfg,
    );
    const form = lastCall(fetchMock).init.body as FormData;
    expect(form.get('phi')).toBe('true');
  });

  it('reads audio from a local path and forwards cleanup=format', async () => {
    const audioPath = path.join(tmpDir, 'dictation.mp3');
    await writeFile(audioPath, Buffer.from('bytes'));
    const fetchMock = stubFetch(jsonResponse({ text: 'raw', cleaned_text: 'Raw.' }));

    await executeTool('voice_transcribe', { audioPath, cleanup: 'format' }, cfg);

    const form = lastCall(fetchMock).init.body as FormData;
    expect(form.get('cleanup')).toBe('format');
    expect(form.get('file')).toBeInstanceOf(Blob);
  });

  it('errors when neither audioPath nor audioBase64 is provided', async () => {
    stubFetch(jsonResponse({}));
    const res = await executeTool('voice_transcribe', {}, cfg);
    expect(res.isError).toBe(true);
    expect(res.content[0].text).toMatch(/audioPath.*audioBase64/);
  });
});

describe('voice_speak', () => {
  const audioResponse = () =>
    new Response(Buffer.from('ID3-fake-mp3-bytes'), {
      status: 200,
      headers: {
        'content-type': 'audio/mpeg',
        'x-gbs-voice-provider': 'selfhosted',
        'x-gbs-voice-fallback': 'false',
      },
    });

  it('POSTs JSON to /v1/audio/speech with Bearer auth, phi=true default, stream=false', async () => {
    const fetchMock = stubFetch(audioResponse());

    await executeTool('voice_speak', { text: 'Log in to view your matter.' }, cfg);

    const { url, init } = lastCall(fetchMock);
    expect(url).toBe('https://voice.test/v1/audio/speech');
    expect(init.method).toBe('POST');
    expect(authHeaderOf(init)).toBe(`Bearer ${API_KEY}`);

    const body = JSON.parse(init.body as string);
    expect(body.phi).toBe(true);
    expect(body.stream).toBe(false);
    expect(body.input).toBe('Log in to view your matter.');
  });

  it('allows an explicit phi=false for non-PHI speak', async () => {
    const fetchMock = stubFetch(audioResponse());
    await executeTool('voice_speak', { text: 'Welcome to Adjudica', phi: false, voice: 'gbs-warm' }, cfg);
    const body = JSON.parse(lastCall(fetchMock).init.body as string);
    expect(body.phi).toBe(false);
    expect(body.voice).toBe('gbs-warm');
  });

  it('writes audio to the output dir and returns the file path by default', async () => {
    stubFetch(audioResponse());
    const res = await executeTool('voice_speak', { text: 'hello' }, cfg);
    const out = JSON.parse(res.content[0].text) as { audioPath: string; bytes: number };
    expect(out.audioPath.startsWith(tmpDir)).toBe(true);
    expect(out.bytes).toBeGreaterThan(0);
    const saved = await readFile(out.audioPath);
    expect(saved.toString()).toBe('ID3-fake-mp3-bytes');
  });

  it('returns base64 audio inline when returnBase64=true', async () => {
    stubFetch(audioResponse());
    const res = await executeTool('voice_speak', { text: 'hi', returnBase64: true }, cfg);
    const out = JSON.parse(res.content[0].text) as { audioBase64: string };
    expect(Buffer.from(out.audioBase64, 'base64').toString()).toBe('ID3-fake-mp3-bytes');
  });

  it('errors when text is missing', async () => {
    stubFetch(audioResponse());
    const res = await executeTool('voice_speak', {}, cfg);
    expect(res.isError).toBe(true);
  });
});

describe('voice_cleanup', () => {
  it('POSTs JSON to /v1/text/cleanup with Bearer auth and phi=true (PHI-locked)', async () => {
    const fetchMock = stubFetch(
      jsonResponse({ text: 'Formatted.', model: 'claude-haiku', verbatim_guard: 'pass' }),
    );

    const res = await executeTool('voice_cleanup', { text: 'um formatted no punctuation' }, cfg);

    const { url, init } = lastCall(fetchMock);
    expect(url).toBe('https://voice.test/v1/text/cleanup');
    expect(init.method).toBe('POST');
    expect(authHeaderOf(init)).toBe(`Bearer ${API_KEY}`);

    const body = JSON.parse(init.body as string);
    expect(body.phi).toBe(true);
    expect(body.mode).toBe('dictation');

    const out = JSON.parse(res.content[0].text) as { verbatim_guard: string };
    expect(out.verbatim_guard).toBe('pass');
  });

  it('surfaces verbatim_guard=fail with the unchanged raw text', async () => {
    stubFetch(jsonResponse({ text: 'raw 42 unchanged', verbatim_guard: 'fail' }));
    const res = await executeTool('voice_cleanup', { text: 'raw 42 unchanged', mode: 'notes' }, cfg);
    const out = JSON.parse(res.content[0].text) as { text: string; verbatim_guard: string };
    expect(out.verbatim_guard).toBe('fail');
    expect(out.text).toBe('raw 42 unchanged');
  });
});

describe('voice_health', () => {
  it('GETs /health unauthenticated and returns the provider map', async () => {
    const fetchMock = stubFetch(
      jsonResponse({ status: 'ok', providers: { selfhosted: 'ready', 'azure-speech': 'ready' } }),
    );

    const res = await executeTool('voice_health', {}, cfg);

    const { url, init } = lastCall(fetchMock);
    expect(url).toBe('https://voice.test/health');
    expect(init.method).toBe('GET');
    // /health is unauthenticated — no Bearer header sent.
    expect(authHeaderOf(init)).toBeUndefined();

    const out = JSON.parse(res.content[0].text) as { providers: Record<string, string> };
    expect(out.providers.selfhosted).toBe('ready');
  });
});

describe('error mapping', () => {
  it('maps a 403 BAA violation to an isError result carrying only the code', async () => {
    stubFetch(
      jsonResponse({ error: { code: 'VOICE_BAA_VIOLATION' } }, { status: 403 }),
    );
    const res = await executeTool('voice_speak', { text: 'x', phi: false, provider: 'elevenlabs' }, cfg);
    expect(res.isError).toBe(true);
    expect(res.content[0].text).toContain('VOICE_BAA_VIOLATION');
    expect(res.content[0].text).toContain('403');
  });

  it('maps a 401 on transcribe', async () => {
    stubFetch(jsonResponse({ error: { code: 'VOICE_UNAUTHENTICATED' } }, { status: 401 }));
    const res = await executeTool(
      'voice_transcribe',
      { audioBase64: Buffer.from('a').toString('base64') },
      cfg,
    );
    expect(res.isError).toBe(true);
    expect(res.content[0].text).toContain('VOICE_UNAUTHENTICATED');
  });

  it('handles a non-JSON error body without throwing', async () => {
    stubFetch(new Response('gateway timeout', { status: 504 }));
    const res = await executeTool('voice_health', {}, cfg);
    expect(res.isError).toBe(true);
    expect(res.content[0].text).toContain('504');
  });

  it('returns isError for an unknown tool', async () => {
    stubFetch(jsonResponse({}));
    const res = await executeTool('voice_nonexistent', {}, cfg);
    expect(res.isError).toBe(true);
    expect(res.content[0].text).toContain('Unknown tool');
  });
});

describe('key safety — the API key never leaks', () => {
  it('scrub() redacts the key value', () => {
    expect(scrub(`Bearer ${API_KEY} failed`, API_KEY)).not.toContain(API_KEY);
    expect(scrub(`Bearer ${API_KEY} failed`, API_KEY)).toContain('***REDACTED***');
  });

  it('no successful tool output contains the key', async () => {
    stubFetch(jsonResponse({ status: 'ok', providers: { selfhosted: 'ready' } }));
    const res = await executeTool('voice_health', {}, cfg);
    expect(res.content[0].text).not.toContain(API_KEY);
  });

  it('no error output contains the key even if the server echoes it back', async () => {
    // Malicious/buggy server echoes the key inside the error body.
    stubFetch(
      jsonResponse(
        { error: { code: `LEAK ${API_KEY}`, message: `token ${API_KEY}` } },
        { status: 500 },
      ),
    );
    const res = await executeTool('voice_cleanup', { text: 'hi' }, cfg);
    expect(res.isError).toBe(true);
    expect(res.content[0].text).not.toContain(API_KEY);
  });

  it('no console log emits the key during a request', async () => {
    const errSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    const logSpy = vi.spyOn(console, 'log').mockImplementation(() => {});
    stubFetch(jsonResponse({ status: 'ok' }));

    await executeTool('voice_health', {}, cfg);

    for (const spy of [errSpy, logSpy]) {
      for (const call of spy.mock.calls) {
        expect(JSON.stringify(call)).not.toContain(API_KEY);
      }
    }
  });
});

describe('config defaults', () => {
  it('falls back to the live service URL when GBS_VOICE_BASE_URL is unset', () => {
    const c = loadConfig({} as NodeJS.ProcessEnv);
    expect(c.baseUrl).toBe(DEFAULT_BASE_URL);
    expect(c.apiKey).toBe('');
  });

  it('strips a trailing slash from a custom base URL', () => {
    const c = loadConfig({ GBS_VOICE_BASE_URL: 'https://x.test/' } as NodeJS.ProcessEnv);
    expect(c.baseUrl).toBe('https://x.test');
  });
});
