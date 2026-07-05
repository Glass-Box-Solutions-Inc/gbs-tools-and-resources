// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology

/**
 * Thin HTTP client for the gbs-voice service, per docs/SEAM_CONTRACT.md v1.
 *
 * Uses the global `fetch` (Node >= 20) so unit tests can stub it via
 * vi.stubGlobal('fetch', ...). No vendor SDK is imported (contract §1 seam
 * rule 1). No transcript/audio content is ever placed in thrown error
 * messages (contract §3 rule 3 / §7) — only the structured error code.
 */

import type { GbsVoiceConfig } from './config.js';

export class VoiceHttpError extends Error {
  status?: number;
  /** Contract §7 error code, e.g. VOICE_BAA_VIOLATION, when the body carries one. */
  code?: string;
  constructor(message: string, status?: number, code?: string) {
    super(message);
    this.name = 'VoiceHttpError';
    this.status = status;
    this.code = code;
  }
}

function authHeaders(apiKey: string): Record<string, string> {
  return apiKey ? { Authorization: `Bearer ${apiKey}` } : {};
}

/**
 * Build a content-free error from a non-2xx response. Reads the contract
 * error envelope { error: { code, message } } but only surfaces the CODE and
 * HTTP status — never a server-provided message that could echo content.
 */
async function toError(res: Response): Promise<VoiceHttpError> {
  let code: string | undefined;
  try {
    const body = (await res.json()) as { error?: { code?: string } };
    code = body?.error?.code;
  } catch {
    // non-JSON body — ignore, we only need status
  }
  const message = code ? `${code} (HTTP ${res.status})` : `HTTP ${res.status}`;
  return new VoiceHttpError(message, res.status, code);
}

// ---------------------------------------------------------------------------
// /v1/audio/transcriptions
// ---------------------------------------------------------------------------

export interface TranscribeParams {
  audio: { data: Uint8Array; filename: string; mime: string };
  phi: boolean;
  language?: string;
  cleanup?: 'none' | 'format';
  sessionId?: string;
}

export interface TranscribeResult {
  text: string;
  cleaned_text?: string;
  language?: string;
  duration_s?: number;
  provider?: string;
  fallback?: boolean;
  session_id?: string;
}

export async function transcribe(
  cfg: GbsVoiceConfig,
  p: TranscribeParams,
): Promise<TranscribeResult> {
  const form = new FormData();
  // Copy into a fresh ArrayBuffer so the Blob part type is unambiguous
  // (a plain Uint8Array can be backed by a SharedArrayBuffer under TS's lib).
  const bytes = p.audio.data;
  const ab = bytes.buffer.slice(
    bytes.byteOffset,
    bytes.byteOffset + bytes.byteLength,
  ) as ArrayBuffer;
  const blob = new Blob([ab], { type: p.audio.mime });
  form.append('file', blob, p.audio.filename);
  form.append('language', p.language ?? 'en');
  // Fail-closed default asserted by the caller; sent as a form string (§4.1).
  form.append('phi', String(p.phi));
  if (p.cleanup) form.append('cleanup', p.cleanup);
  if (p.sessionId) form.append('session_id', p.sessionId);

  // NB: do NOT set Content-Type — fetch derives the multipart boundary.
  const res = await fetch(`${cfg.baseUrl}/v1/audio/transcriptions`, {
    method: 'POST',
    headers: authHeaders(cfg.apiKey),
    body: form,
  });
  if (!res.ok) throw await toError(res);
  return (await res.json()) as TranscribeResult;
}

// ---------------------------------------------------------------------------
// /v1/audio/speech
// ---------------------------------------------------------------------------

export interface SpeakParams {
  input: string;
  phi: boolean;
  voice?: string;
  style?: string;
  speed?: number;
  responseFormat?: 'mp3' | 'wav' | 'pcm';
  sessionId?: string;
}

export interface SpeakResult {
  audio: Buffer;
  contentType: string;
  provider?: string;
  fallback: boolean;
}

export async function speak(cfg: GbsVoiceConfig, p: SpeakParams): Promise<SpeakResult> {
  const body: Record<string, unknown> = {
    input: p.input,
    phi: p.phi,
    // Request the complete body (not chunked) so the tool can save/return it.
    stream: false,
  };
  if (p.voice) body.voice = p.voice;
  if (p.style) body.style = p.style;
  if (p.speed !== undefined) body.speed = p.speed;
  if (p.responseFormat) body.response_format = p.responseFormat;
  if (p.sessionId) body.session_id = p.sessionId;

  const res = await fetch(`${cfg.baseUrl}/v1/audio/speech`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders(cfg.apiKey) },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw await toError(res);

  // Fast reject on a declared oversize length (before reading any bytes).
  const declared = Number(res.headers.get('content-length'));
  if (Number.isFinite(declared) && declared > cfg.maxAudioBytes) {
    throw responseTooLarge(res.status);
  }
  // Stream the body with a running cap so a missing/false Content-Length can
  // never make us buffer an unbounded response (memory-DoS guard).
  const audio = await readBoundedBody(res, cfg.maxAudioBytes);
  return {
    audio,
    contentType: res.headers.get('content-type') ?? 'audio/mpeg',
    provider: res.headers.get('x-gbs-voice-provider') ?? undefined,
    fallback: res.headers.get('x-gbs-voice-fallback') === 'true',
  };
}

function responseTooLarge(status?: number): VoiceHttpError {
  return new VoiceHttpError(
    status ? `VOICE_RESPONSE_TOO_LARGE (HTTP ${status})` : 'VOICE_RESPONSE_TOO_LARGE',
    status,
    'VOICE_RESPONSE_TOO_LARGE',
  );
}

/**
 * Read a fetch Response body into a Buffer, aborting the stream the instant
 * cumulative bytes exceed `max`. We never accumulate more than `max` (plus one
 * final chunk) before rejecting, and we cancel the reader so the remote stops
 * sending — no unbounded buffering regardless of Content-Length.
 */
async function readBoundedBody(res: Response, max: number): Promise<Buffer> {
  const body = res.body;
  if (!body) {
    // No stream exposed (edge/mocked case): buffer, then post-check.
    const buf = Buffer.from(await res.arrayBuffer());
    if (buf.length > max) throw responseTooLarge();
    return buf;
  }

  const reader = body.getReader();
  const chunks: Buffer[] = [];
  let total = 0;
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      if (!value) continue;
      total += value.byteLength;
      if (total > max) {
        // Stop the remote from sending the rest, then reject.
        await reader.cancel('VOICE_RESPONSE_TOO_LARGE').catch(() => undefined);
        throw responseTooLarge();
      }
      chunks.push(Buffer.from(value)); // copy — do not retain the stream's view
    }
  } finally {
    reader.releaseLock();
  }
  return Buffer.concat(chunks, total);
}

// ---------------------------------------------------------------------------
// /v1/text/cleanup
// ---------------------------------------------------------------------------

export interface CleanupParams {
  text: string;
  phi: boolean;
  mode?: 'dictation' | 'notes' | 'verbatim-punctuation';
  sessionId?: string;
}

export interface CleanupResult {
  text: string;
  model?: string;
  verbatim_guard?: 'pass' | 'fail';
}

export async function cleanup(
  cfg: GbsVoiceConfig,
  p: CleanupParams,
): Promise<CleanupResult> {
  const body: Record<string, unknown> = {
    text: p.text,
    mode: p.mode ?? 'dictation',
    phi: p.phi,
  };
  if (p.sessionId) body.session_id = p.sessionId;

  const res = await fetch(`${cfg.baseUrl}/v1/text/cleanup`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders(cfg.apiKey) },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw await toError(res);
  return (await res.json()) as CleanupResult;
}

// ---------------------------------------------------------------------------
// /health  (unauthenticated per contract §4.6)
// ---------------------------------------------------------------------------

export interface HealthResult {
  status?: string;
  providers?: Record<string, string>;
  [k: string]: unknown;
}

export async function health(cfg: GbsVoiceConfig): Promise<HealthResult> {
  const res = await fetch(`${cfg.baseUrl}/health`, { method: 'GET' });
  if (!res.ok) throw await toError(res);
  return (await res.json()) as HealthResult;
}
