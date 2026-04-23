/**
 * API types for the Insurance Claims Case Generator FastAPI backend.
 *
 * @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
 */

// ---------------------------------------------------------------------------
// Scenario
// ---------------------------------------------------------------------------

export interface ScenarioResponse {
  slug: string;
  display_name: string;
  description: string;
  litigated: boolean;
  attorney_represented: boolean;
  ct: boolean;
  denied_scenario: boolean;
  death_claim: boolean;
  ptd_claim: boolean;
  psych_overlay: boolean;
  multi_employer: boolean;
  split_carrier: boolean;
  high_liens: boolean;
  sjdb_dispute: boolean;
  expedited: boolean;
  investigation_active: boolean;
  expected_doc_min: number;
  expected_doc_max: number;
}

// ---------------------------------------------------------------------------
// Generate (single case)
// ---------------------------------------------------------------------------

export interface GenerateRequest {
  scenario: string;
  seed?: number;
  generate_pdfs?: boolean;
}

export interface DocumentEventSummary {
  event_id: string;
  document_type: string;
  subtype_slug: string;
  title: string;
  event_date: string;
  stage: string;
  access_level: string;
  deadline_date: string | null;
  deadline_statute: string | null;
  metadata: Record<string, unknown>;
}

export interface GenerateResponse {
  case_id: string;
  scenario_slug: string;
  seed: number;
  document_count: number;
  stages_visited: string[];
  document_events: DocumentEventSummary[];
  zip_size_bytes: number;
}

// ---------------------------------------------------------------------------
// Batch
// ---------------------------------------------------------------------------

export interface BatchJobSpec {
  scenario: string;
  seed: number;
}

export interface BatchRequest {
  jobs: BatchJobSpec[];
  generate_pdfs?: boolean;
  max_workers?: number;
}

export type JobStatus = "pending" | "running" | "done" | "failed";

export interface BatchResponse {
  job_id: string;
  status: JobStatus;
  total: number;
  message: string;
}

// ---------------------------------------------------------------------------
// Job status
// ---------------------------------------------------------------------------

export interface JobStatusResponse {
  job_id: string;
  status: JobStatus;
  progress: number;
  total: number;
  completed: number;
  error: string | null;
}

// ---------------------------------------------------------------------------
// Health
// ---------------------------------------------------------------------------

export interface HealthResponse {
  status: string;
  version: string;
  scenario_count: number;
  active_jobs: number;
}
