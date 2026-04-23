# ISSUES — Insurance Claims Case Generator

Deferred out-of-scope improvements (append-only during execution).

---

## Deferred to Phase 2

- PDF generation for all 24 DocumentType values (reportlab Tier A/B/C) — **COMPLETED in Phase 2**
- DWC-1 form-accurate overlay using PNG blank + JSON field coordinate map — **NOT COMPLETED**
  - PNG blank forms were not available in `assets/` at Phase 2 implementation time
  - Table-layout approximation used instead (see `documents/form_renderer.py`)
  - Forms affected: DWC-1, UB-04, CMS-1500, Form 105, DEU Rating Form
  - Backlog item: Obtain official blank PDF/PNG forms and implement pixel-accurate overlay
  - Workaround logged per Phase 2 plan: "if PNG blanks missing → use table approximation"
- UB-04, CMS-1500 Tier A forms — **PARTIALLY COMPLETED**
  - Table-layout approximations provided in `documents/billing_statement_forms.py`
  - CMS-1500 and UB-04 generators available as helper functions (not direct registry entries)
  - Full form-accurate overlay deferred pending PNG blank availability

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
