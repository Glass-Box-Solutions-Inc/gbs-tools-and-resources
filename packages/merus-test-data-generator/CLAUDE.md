# MerusCase WC Test Data Generator v2.0

**Lifecycle-aware Workers' Compensation test case simulation engine with 188-subtype taxonomy, AMA Guides 5th Edition content, specialty-specific clinical pools, deposition exchange templates, dynamic generation, FastAPI backend, and Next.js web UI.**

---

## CRITICAL GUARDRAILS (READ FIRST)

1. **NEVER push without permission** — Even small fixes require express user permission. No exceptions.
2. **NEVER expose secrets** — No API keys, tokens, credentials in git, logs, or conversation.
3. **NEVER force push or skip tests** — 100% passing tests required.
4. **ALWAYS read parent CLAUDE.md** — `~/CLAUDE.md` for org-wide standards.
5. **ALWAYS use Definition of Ready** — 100% clear requirements before implementation.

---

## Purpose

Generates 1-500+ realistic Workers' Compensation test cases with lifecycle-aware document generation using the canonical 188-subtype Adjudica Classifier taxonomy. Produces 10,000+ templated PDFs across 97+ of 188 subtypes and optionally populates cases in MerusCase via Browserless cloud browser automation + API upload. Supports both standard case generation and hand-crafted edge case scenarios covering complex CA WC legal and procedural patterns.

## Tech Stack

- **Python 3.12** — Core engine
- **reportlab** — PDF generation (25 Tier 1 templates + Tier 2 variants + generic fallback)
- **Faker** — Realistic test data
- **Pydantic** — Data models & validation
- **Click** — CLI framework
- **FastAPI** — REST API with SSE progress streaming
- **Next.js 16** — App Router web UI with shadcn/ui
- **SQLite** — Progress tracking & audit logging
- **Browserless** — Cloud browser for MerusCase reCAPTCHA bypass

## Scale

| Batch | Cases | Documents | Subtypes |
|-------|-------|-----------|----------|
| Batch 1 (standard, 30 complex cases) | 30 | ~7,750 | 97+ |
| Batch 2 (edge cases, 30 custom profiles) | 30 | ~2,554 | varies |
| **Total** | **60** | **10,000+** | **97+** |

## Architecture

```
main.py (CLI)
  ├── generate --count N --seed S --stages preset
  ├── create / upload / run-all / status / verify / audit
  └── serve (FastAPI on port 5520)

batch_create_cases.py        # Single-session Browserless case creation (bypasses reCAPTCHA)
batch2_edge_cases.py         # 30 hand-crafted edge case scenarios

data/
  ├── taxonomy.py                  # 188 subtypes + 12 types (from Adjudica-classifier)
  ├── taxonomy_compat.py           # Old 27→new 188 mapping
  ├── lifecycle_engine.py          # DAG state machine with probabilistic branching
  ├── case_profile_generator.py    # Dynamic 1-500 case generation
  ├── fake_data_generator.py       # Faker engine (v2: lifecycle-aware)
  ├── case_profiles.py             # Legacy 20 hardcoded profiles
  ├── models.py                    # Pydantic models (GeneratedCase, DocumentSpec, etc.)
  ├── wc_constants.py              # CA WC reference data
  ├── template_hints.py            # Structure hints for generic template
  ├── ama_guides_content.py        # AMA Guides 5th Edition impairment tables (NEW)
  ├── content_pools.py             # Specialty-specific clinical exam findings (NEW)
  └── deposition_exchanges.py      # Deposition Q&A templates (NEW)

orchestration/
  ├── pipeline.py           # 4-step pipeline with progress callbacks
  ├── progress_tracker.py   # SQLite resumability
  ├── audit.py              # SOC2 HMAC audit logging
  ├── case_creator.py       # MerusCase browser automation (Browserless cloud)
  └── document_uploader.py  # MerusCase API upload

pdf_templates/
  ├── base_template.py      # reportlab base class (utility methods added)
  ├── registry.py           # Centralized subtype→template mapping (188 entries)
  ├── generic_template.py   # Tier 3 fallback template (enhanced)
  ├── medical/ (7)          # TPR, diagnostic, operative, QME/AME, UR, pharmacy, billing
  ├── legal/ (5)            # Application, DOR, minutes, stipulations, C&R
  ├── correspondence/ (4)   # Adjuster, defense, court notice, client intake
  ├── discovery/ (4)        # Subpoena, deposition notice/transcript, records
  ├── employment/ (3)       # Wage, job description, personnel
  └── summaries/ (2)        # Medical chronology, settlement memo

service/                    # FastAPI REST API (Phase 3)
  ├── app.py                # App factory
  ├── config.py             # Port 5520, CORS
  ├── dependencies.py       # DI: Pipeline, ProgressTracker
  ├── sse.py                # SSE streaming helper
  ├── models/               # Request/response Pydantic models
  └── routes/               # health, taxonomy, generation, runs, preview, download, meruscase

frontend/                   # Next.js 16 App Router (Phase 4)
  └── src/
      ├── app/              # Dashboard, Generate, Progress, Results, Upload pages
      ├── components/       # Layout, UI primitives, feature components
      └── lib/              # API client, types, utils
```

## Commands

```bash
# CLI — Generation
python main.py generate                         # Legacy 20 cases
python main.py generate --count 50              # Dynamic 50 cases via lifecycle engine
python main.py generate --count 100 --seed 123  # Reproducible
python main.py generate --count 50 --stages settlement_heavy
python main.py generate --count 50 --constraints '{"min_surgery_cases": 10}'

# Batch Scripts
python batch_create_cases.py     # Single-session Browserless: create all cases (bypasses reCAPTCHA)
python batch2_edge_cases.py      # 30 hand-crafted edge case scenarios

# CLI — MerusCase Integration
python main.py create [--dry-run]    # Create cases in MerusCase
python main.py upload                # Upload documents to MerusCase
python main.py run-all [--dry-run]   # Full pipeline

# CLI — Status & Verification
python main.py status                # Show progress
python main.py verify [--visual]     # Verify cases in MerusCase
python main.py audit [--verify-chain] [--stats] [--recent N]

# API Server
python main.py serve [--port 5520]   # Start FastAPI server

# Frontend
cd frontend && npm install && npm run dev  # Start Next.js dev server (port 3000)

# Docker
docker-compose up                    # FastAPI + Next.js with hot reload

# Taxonomy sync
python scripts/sync_taxonomy.py --check  # Check for drift from classifier
```

## API Endpoints (Port 5520)

```
GET  /health
GET  /api/taxonomy/types              # 12 parent types
GET  /api/taxonomy/subtypes           # All 188 subtypes
GET  /api/taxonomy/subtypes/{type}    # Subtypes for one type
POST /api/generate                    # Start generation (returns run_id)
GET  /api/generate/{run_id}/status    # SSE progress stream
GET  /api/runs                        # List runs
GET  /api/runs/{run_id}              # Run details
DELETE /api/runs/{run_id}            # Delete run
GET  /api/preview/{run_id}/cases     # List cases
GET  /api/preview/{run_id}/cases/{caseId}  # Case detail
GET  /api/preview/{run_id}/documents/{caseId}/{filename}  # Serve PDF
GET  /api/download/{run_id}          # ZIP download (all cases)
GET  /api/download/{run_id}/{caseId} # ZIP download (single case)
POST /api/meruscase/create-cases/{run_id}    # Create in MerusCase
POST /api/meruscase/upload-documents/{run_id} # Upload to MerusCase
GET  /api/meruscase/status/{run_id}  # Upload progress SSE
```

## Lifecycle Engine

The lifecycle engine models CA WC cases as a DAG with probabilistic branching:

```
INJURY → CLAIM_FILED → CLAIM_RESPONSE
  ├── accepted (55%) → ACTIVE_TREATMENT
  ├── delayed (30%) → INVESTIGATION
  └── denied (15%) → APPEAL
→ UR_DISPUTE (40%) → UR_DECISION → IMR_APPEAL
→ APPLICATION_FILED (if attorney)
→ QME/AME EVALUATION → DISCOVERY
→ LIEN_FILING (30%) → LIEN_CONFERENCE
→ RESOLUTION: Stipulations (45%) / C&R (40%) / Trial (15%)
→ POST_RESOLUTION
```

Each node emits documents with configurable probability, count ranges, and date anchors.

## AMA Guides 5th Edition Content

`data/ama_guides_content.py` provides structured impairment rating content used by QME/AME reports and medical templates:

- **DRE Spine Categories** — Cervical, thoracic, and lumbar DRE category I–V with WPI ranges, criteria, and clinical findings
- **Upper Extremity ROM** — Shoulder, elbow, wrist, and hand ROM measurements with diagnosis-based ratings
- **Lower Extremity ROM** — Hip, knee, and ankle ROM measurements with diagnosis-based ratings
- **Psychiatric GAF Scoring** — GAF score ranges mapped to functional impairment levels for psychiatric WPI calculations
- **Cardiovascular & Pulmonary** — METs-based cardiac impairment tables and pulmonary function classification
- **Apportionment Templates** — Pre-existing condition language templates for apportionment analysis
- **Combined Values Chart** — Programmatic combined values for multi-region WPI calculations

## Clinical Content Pools

`data/content_pools.py` provides 200+ specialty-specific clinical findings consumed by medical PDF templates:

- **Orthopedic findings** organized by body region (cervical, lumbar, shoulder, elbow, wrist/hand, hip, knee, ankle/foot)
- **Psychiatric exam findings** (MSE elements, functional descriptors, GAF narrative language)
- **Treatment narratives** (physical therapy, chiropractic, pain management, surgical)
- **Functional capacity descriptions** (work restriction language, ADL impact, vocational overlays)

## Deposition Exchange Templates

`data/deposition_exchanges.py` provides realistic Q&A content used by deposition transcript templates:

- **13 topic categories** — Background, injury mechanism, medical history, treatment, symptoms, daily activities, return to work, prior injuries, vocational, expert qualification, medical opinion, legal procedure, and closing
- **600+ realistic exchanges** — Attorney-witness dialogues with realistic WC terminology
- **Objections** — Foundation, relevance, calls for speculation, hearsay, asked-and-answered, compound, assumes facts
- **Procedural elements** — Opening statements, stipulations, exhibit marking, recess language

## Edge Case Scenarios (batch2_edge_cases.py)

30 hand-crafted profiles covering complex CA WC legal and procedural patterns:

| Category | Scenarios |
|----------|-----------|
| CT + Special Circumstances | Multiple specific injuries, sexual assault, firefighter presumption (LC 3212 et seq.) |
| Death Claims | Dubious AOE/COE, disabled minor child dependent, lien-heavy estate |
| Permanent Total Disability | 100% PTD with strong VR expert, 100% PTD with weak VR rebuttal |
| Kite Cases | CVC rebuttal, ADL synergy analysis per Vigil v. County of Kern |
| Multiple Injuries Same Extremity | LC 4664(c) apportionment, overlapping impairment |
| Pro Per Applicants | Self-represented claimant, fired attorney mid-case scenario |
| Split Carrier CT | LC 5500.5 multi-employer exposure period allocation |
| Serious & Willful | LC 4553 misconduct, penalty enhancement |
| Unreasonable Delay Penalties | LC 5814 delay chains, penalty calculation |
| Complex Liens | $280K+ multi-provider lien scenarios, lien conference posture |
| UR/IMR Dispute Chains | Multi-level denial, IMR appeal, independent medical review |
| Almaraz/Guzman Rebuttal | DRE vs ROM methodology dispute, whole-person impairment rebuttal |

## Port Registry

| Service | Port |
|---------|------|
| FastAPI | 5520 |
| Next.js | 3000 |

## Dependencies

- `packages/merus-expert/` — MatterBuilder (browser automation), MerusCaseAPIClient (API)
- `~/Desktop/Adjudica-classifier/` — Taxonomy source (types.ts, subtypes.ts, mapping.ts)
- Browserless API token for case creation (cloud browser, bypasses MerusCase reCAPTCHA on login)

## Environment Variables

See `.env.example` for all variables.

---

For company-wide development standards, see the [Root CLAUDE.md](https://github.com/Glass-Box-Solutions-Inc/adjudica-documentation/blob/main/engineering/ROOT_CLAUDE.md).

---

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
