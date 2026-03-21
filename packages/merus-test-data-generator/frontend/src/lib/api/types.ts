/**
 * TypeScript interfaces mirroring the FastAPI backend models.
 *
 * @developed Glass Box Solutions, Inc.
 */

// ---------------------------------------------------------------------------
// Request types
// ---------------------------------------------------------------------------

export interface GenerateRequest {
  count: number;
  seed?: number | null;
  stage_distribution?: Record<string, number> | null;
  constraints?: CaseConstraints | null;
}

export interface CaseConstraints {
  min_surgery_cases?: number;
  min_psych_cases?: number;
  min_lien_cases?: number;
  min_ur_dispute_cases?: number;
  attorney_rate?: number;
  surgery_rate?: number;
  psych_rate?: number;
  ur_dispute_rate?: number;
  lien_rate?: number;
  imr_rate?: number;
}

export interface MerusCaseUploadRequest {
  dry_run: boolean;
}

// ---------------------------------------------------------------------------
// Response types
// ---------------------------------------------------------------------------

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
}

export interface RunStatus {
  run_id: number;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  total_cases: number;
  total_docs: number;
  cases_data_generated: number;
  cases_pdfs_generated: number;
  docs_pdf_generated: number;
  docs_uploaded: number;
  errors: number;
}

export interface GenerateResponse {
  run_id: number;
  status: string;
  message: string;
}

export interface CasePreview {
  internal_id: string;
  case_number: number;
  applicant_name: string;
  employer_name: string;
  litigation_stage: string;
  status: string;
  total_docs: number;
  docs_generated: number;
}

export interface DocumentPreview {
  filename: string;
  subtype: string;
  title: string;
  doc_date: string;
  pdf_generated: boolean;
  pdf_path: string | null;
}

export interface CaseDetail {
  case: CasePreview;
  documents: DocumentPreview[];
  timeline: Record<string, unknown>;
}

export interface TaxonomyType {
  value: string;
  label: string;
  subtype_count: number;
}

export interface TaxonomySubtype {
  value: string;
  label: string;
  parent_type: string;
}

// ---------------------------------------------------------------------------
// SSE event types
// ---------------------------------------------------------------------------

export interface SSEPhaseEvent {
  phase: string;
  status: string;
  total_docs?: number;
}

export interface SSECaseEvent {
  case_number: number;
  applicant_name: string;
  stage: string;
  docs: number;
}

export interface SSEDocEvent {
  case_number: number;
  filename: string;
  subtype: string;
}

export interface SSECompleteEvent {
  cases: number;
  docs_generated: number;
  docs_skipped: number;
  errors: number;
}

export interface SSEErrorEvent {
  message: string;
}

// ---------------------------------------------------------------------------
// Stage presets (mirroring backend PRESETS)
// ---------------------------------------------------------------------------

export const STAGE_PRESETS: Record<string, Record<string, number>> = {
  balanced: {
    intake: 0.15,
    active_treatment: 0.25,
    discovery: 0.20,
    medical_legal: 0.15,
    settlement: 0.15,
    resolved: 0.10,
  },
  early_stage: {
    intake: 0.30,
    active_treatment: 0.35,
    discovery: 0.15,
    medical_legal: 0.10,
    settlement: 0.07,
    resolved: 0.03,
  },
  settlement_heavy: {
    intake: 0.05,
    active_treatment: 0.10,
    discovery: 0.15,
    medical_legal: 0.20,
    settlement: 0.30,
    resolved: 0.20,
  },
  complex_litigation: {
    intake: 0.05,
    active_treatment: 0.10,
    discovery: 0.25,
    medical_legal: 0.25,
    settlement: 0.20,
    resolved: 0.15,
  },
};

export const ALL_STAGES = [
  "intake",
  "active_treatment",
  "discovery",
  "medical_legal",
  "settlement",
  "resolved",
] as const;

export type Stage = (typeof ALL_STAGES)[number];
