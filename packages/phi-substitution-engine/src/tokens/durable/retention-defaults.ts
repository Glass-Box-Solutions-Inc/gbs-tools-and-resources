// HIPAA 45 CFR §164.530(j) / §164.316(b)(2)(i) — 6-year retention for required documentation,
// adopted as the conservative floor for PHI-processing artifacts under the org's BAA posture;
// superseded reversal records may be needed to reconstruct historical egress, so they retain for
// 6 years after supersession by default; deployments may adjust via the SUPERSEDE_RETENTION_MS env
// knob subject to counsel. Six years is modeled as 6 * 365 days (189_216_000_000 ms); leap-day
// precision is immaterial and simplicity wins for this fixed conservative floor.
// Single shared source: azure adapter, Postgres control plane, and the dev double all import this
// constant, so a partial default change (split-brain) is structurally impossible.
export const DEFAULT_SUPERSEDE_RETENTION_MS = 6 * 365 * 24 * 60 * 60 * 1_000;
