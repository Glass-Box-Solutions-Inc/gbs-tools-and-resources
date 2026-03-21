/**
 * API client for the MerusCase WC Test Data Generator.
 * All requests go through Next.js API routes which proxy to FastAPI at localhost:5520.
 *
 * @developed Glass Box Solutions, Inc.
 */

import type {
  CaseDetail,
  CasePreview,
  GenerateRequest,
  GenerateResponse,
  RunStatus,
  TaxonomySubtype,
  TaxonomyType,
} from "./types";

class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });

  if (!res.ok) {
    let message = `Request failed with status ${res.status}`;
    try {
      const body = await res.json();
      message = body.detail || body.message || message;
    } catch {
      // ignore parse errors
    }
    throw new ApiError(res.status, message);
  }

  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Generation
// ---------------------------------------------------------------------------

export async function generateCases(
  config: GenerateRequest,
): Promise<GenerateResponse> {
  return request<GenerateResponse>("/api/generate", {
    method: "POST",
    body: JSON.stringify(config),
  });
}

// ---------------------------------------------------------------------------
// Runs
// ---------------------------------------------------------------------------

export async function listRuns(): Promise<RunStatus[]> {
  return request<RunStatus[]>("/api/runs");
}

export async function getRunStatus(runId: number): Promise<RunStatus> {
  return request<RunStatus>(`/api/runs/${runId}`);
}

export async function deleteRun(runId: number): Promise<void> {
  await request<unknown>(`/api/runs/${runId}`, { method: "DELETE" });
}

// ---------------------------------------------------------------------------
// Preview (cases + documents)
// ---------------------------------------------------------------------------

export async function listCases(runId: number): Promise<CasePreview[]> {
  return request<CasePreview[]>(`/api/preview/${runId}/cases`);
}

export async function getCaseDetail(
  runId: number,
  caseId: string,
): Promise<CaseDetail> {
  return request<CaseDetail>(`/api/preview/${runId}/cases/${caseId}`);
}

// ---------------------------------------------------------------------------
// Download
// ---------------------------------------------------------------------------

export function downloadRunUrl(runId: number): string {
  return `/api/download/${runId}`;
}

export function downloadCaseUrl(runId: number, caseId: string): string {
  return `/api/download/${runId}/${caseId}`;
}

// ---------------------------------------------------------------------------
// Taxonomy
// ---------------------------------------------------------------------------

export async function getTypes(): Promise<TaxonomyType[]> {
  return request<TaxonomyType[]>("/api/taxonomy?endpoint=types");
}

export async function getSubtypes(): Promise<TaxonomySubtype[]> {
  return request<TaxonomySubtype[]>("/api/taxonomy?endpoint=subtypes");
}

// ---------------------------------------------------------------------------
// MerusCase integration
// ---------------------------------------------------------------------------

export async function createMerusCases(
  runId: number,
  dryRun: boolean = false,
): Promise<{ status: string; run_id: number; dry_run: boolean }> {
  return request(`/api/meruscase/create-cases/${runId}`, {
    method: "POST",
    body: JSON.stringify({ dry_run: dryRun }),
  });
}

export async function uploadMerusDocuments(
  runId: number,
): Promise<{ status: string; run_id: number }> {
  return request(`/api/meruscase/upload-documents/${runId}`, {
    method: "POST",
  });
}

// ---------------------------------------------------------------------------
// SSE helper
// ---------------------------------------------------------------------------

export function connectSSE(
  url: string,
  handlers: {
    onPhase?: (data: Record<string, unknown>) => void;
    onCase?: (data: Record<string, unknown>) => void;
    onDoc?: (data: Record<string, unknown>) => void;
    onComplete?: (data: Record<string, unknown>) => void;
    onError?: (data: Record<string, unknown>) => void;
    onHeartbeat?: () => void;
  },
): EventSource {
  const es = new EventSource(url);

  if (handlers.onPhase) {
    es.addEventListener("phase", (e) => {
      handlers.onPhase!(JSON.parse(e.data));
    });
  }
  if (handlers.onCase) {
    es.addEventListener("case_generated", (e) => {
      handlers.onCase!(JSON.parse(e.data));
    });
  }
  if (handlers.onDoc) {
    es.addEventListener("doc_generated", (e) => {
      handlers.onDoc!(JSON.parse(e.data));
    });
  }
  if (handlers.onComplete) {
    es.addEventListener("complete", (e) => {
      handlers.onComplete!(JSON.parse(e.data));
      es.close();
    });
  }
  if (handlers.onError) {
    es.addEventListener("error", (e) => {
      if (e instanceof MessageEvent) {
        handlers.onError!(JSON.parse(e.data));
      }
      es.close();
    });
  }
  if (handlers.onHeartbeat) {
    es.addEventListener("heartbeat", () => {
      handlers.onHeartbeat!();
    });
  }

  return es;
}
