# Insurance Claims Case Generator

**Lifecycle-aware California Workers' Compensation synthetic claims generator.**
Produces JSON manifests (Phase 1) and PDF case folders (Phase 2+) for pipeline testing and staging seeding.

**Parent package:** `gbs-tools-and-resources/packages/insurance-claims-case-generator/`
**Linear ticket:** AJC-20
**GBS Root:** See [ROOT_CLAUDE.md](https://github.com/Glass-Box-Solutions-Inc/adjudica-documentation/blob/main/engineering/ROOT_CLAUDE.md)

---

## CRITICAL GUARDRAILS

1. **NEVER push without permission**
2. **NEVER expose secrets** — GCP Secret Manager only
3. **NEVER force push or skip tests** — 100% passing + ≥80% coverage required
4. **Synthetic data ONLY** — no real PHI, PII, or claimant information

---

## Tech Stack Override

| Component | Library | Note |
|---|---|---|
| Language | Python 3.12 | GBS standard |
| API | FastAPI 0.115+ | Phase 3+ |
| PDF | reportlab 4.2+ | Phase 2+ |
| Data gen | Faker 33+ | |
| Models | Pydantic v2 | |
| CLI | Click 8.1 | |
| HTTP client | httpx 0.28+ | Phase 4 AdjudiCLAIMS integration |
| Testing | pytest 8, pytest-cov | |
| Linting | ruff, mypy | |
| Container | Docker multi-stage python:3.12 | |

**Frontend:** Next.js 14 (Phase 5) — matching merus-test-data-generator monorepo convention.
GBS default is React Router 7 but this package uses Next.js for monorepo consistency with merus-test-data-generator.

---

## GCP Service Account

- SA name: `sa-claims-generator@<gcp-project>.iam.gserviceaccount.com`
- Minimum IAM: `roles/secretmanager.secretAccessor` (scoped to specific secrets)
- NEVER use Compute Engine default SA

---

## Commands

```bash
# Install
pip install -e ".[dev]"

# CLI
claims-gen generate --scenario litigated_qme --seed 42

# Tests (must pass 100% with ≥80% coverage)
pytest tests/ -v

# Lint
ruff check src/ tests/
mypy src/

# Pre-commit (after install)
pre-commit run --all-files
```

---

## Critical Reference Files

| File | Used For |
|---|---|
| `AdjudiCLAIMS-ai-app/prisma/schema.prisma` | DocumentType enum — 24 values MUST match exactly |
| `AdjudiCLAIMS-ai-app/server/services/benefit-calculator.service.ts` | TD rate tables — MUST match exactly |

---

## Phase 1 Scope (Current)

Data layer + lifecycle DAG engine. CLI outputs valid JSON. No PDFs.

Exit test: `claims-gen generate --scenario litigated_qme --seed 42 | python -m json.tool`
→ valid JSON, 18-30 document_events, dates ascending, deadlines met.

---

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
