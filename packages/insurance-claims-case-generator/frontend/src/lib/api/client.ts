/**
 * API client for the Insurance Claims Case Generator FastAPI backend.
 * Uses NEXT_PUBLIC_API_BASE_URL (default: http://localhost:8001).
 *
 * @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
 */

import type {
  BatchRequest,
  BatchResponse,
  GenerateRequest,
  GenerateResponse,
  HealthResponse,
  JobStatusResponse,
  ScenarioResponse,
} from "./types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8001";

class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const url = `${API_BASE}/api/v1${path}`;
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
      message = body.detail ?? body.message ?? message;
    } catch {
      // ignore parse errors
    }
    throw new ApiError(res.status, message);
  }

  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Scenarios
// ---------------------------------------------------------------------------

export async function listScenarios(): Promise<ScenarioResponse[]> {
  return request<ScenarioResponse[]>("/scenarios");
}

// ---------------------------------------------------------------------------
// Generate (single case — synchronous)
// ---------------------------------------------------------------------------

export async function generateCase(
  req: GenerateRequest,
): Promise<GenerateResponse> {
  return request<GenerateResponse>("/generate", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

// ---------------------------------------------------------------------------
// Batch (async)
// ---------------------------------------------------------------------------

export async function submitBatch(req: BatchRequest): Promise<BatchResponse> {
  return request<BatchResponse>("/batch", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

// ---------------------------------------------------------------------------
// Jobs
// ---------------------------------------------------------------------------

export async function getJobStatus(jobId: string): Promise<JobStatusResponse> {
  return request<JobStatusResponse>(`/jobs/${jobId}`);
}

// ---------------------------------------------------------------------------
// Export
// ---------------------------------------------------------------------------

export function exportUrl(jobId: string): string {
  return `${API_BASE}/api/v1/export/${jobId}`;
}

// ---------------------------------------------------------------------------
// Health
// ---------------------------------------------------------------------------

export async function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/health");
}
