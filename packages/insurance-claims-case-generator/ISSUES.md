# ISSUES — Insurance Claims Case Generator

Deferred out-of-scope improvements (append-only during execution).

---

## Deferred to Phase 2

- PDF generation for all 24 DocumentType values (reportlab Tier A/B/C)
- DWC-1 form-accurate overlay using PNG blank + JSON field coordinate map
- UB-04, CMS-1500, Form 105, DEU rating Tier A forms

## Deferred to Phase 3

- FastAPI service endpoints (POST /api/v1/generate, /api/v1/batch, etc.)
- SSE streaming job progress
- All 10 remaining scenarios (cumulative_trauma, death_claim, ptd_claim, psychiatric_overlay, multi_employer, split_carrier, complex_lien, expedited_hearing, qme_dispute_only, sjdb_voucher)
- In-memory async job store

## Deferred to Phase 4

- AdjudiCLAIMS integration client (httpx, login → create claim → upload docs)
- GCP Secret Manager integration
- `claims-gen seed` command
- Docker multi-stage build finalization
- CI coverage enforcement wired to 80% gate

## Deferred to Phase 5

- Next.js 14 frontend (scenario selector, generate form, job poller, batch page)
- Docker-compose with Next.js hot reload

---

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
