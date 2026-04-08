# MerusCase WC Test Data Generator v2.1

**Lifecycle-aware Workers' Compensation case simulation engine** — generates 1-500 realistic CA WC cases with the Adjudica Classifier's 350-subtype document taxonomy, templated PDFs, and optional MerusCase population.

Built for the Merus-to-Adjudica import pipeline testing workflow.

---

## What's New in v2.1

- **AMA Guides 5th Edition Content** — DRE spine, upper/lower extremity, psychiatric GAF, cardiovascular, and pulmonary impairment ratings embedded in QME/AME and treating physician templates
- **Clinical Exam Pools** — 200+ specialty-specific orthopedic and psychiatric examination findings
- **Deposition Exchange Templates** — 13 topic categories covering 600+ exchanges (causation, apportionment, treatment necessity, permanent disability, vocational rehab, and more)
- **Batch Case Creation Scripts** — `batch_create_cases.py` for efficient single-session Browserless MerusCase population; `batch2_edge_cases.py` for 30 custom WC edge case scenarios
- **30 Edge Case Scenarios** — death claims, PTD with VR experts, Kite (CVC rebuttal), split carriers (LC 5500.5), pro per applicants, LC 4553 S&W, LC 5814 penalties, complex liens, UR/IMR chains, Almaraz/Guzman rebuttal, firefighter presumptions (LC 3212), sexual assault workplace claims
- **Enhanced Templates** — QME/AME reports with AMA Guides impairment ratings, treating physician reports with specialty dispatch, utilization review, depositions, subpoenaed records, medical chronology, and settlement memo
- **Scale** — 10,000+ documents generated across 97+ of 350 subtypes

## What's New in v2.0

- **350-Subtype Taxonomy** — aligned with the Adjudica Classifier (was 27 subtypes)
- **Lifecycle Engine** — probabilistic DAG models realistic CA WC case lifecycles
- **Dynamic Generation** — 1-500 cases with configurable stage distribution and constraints
- **FastAPI Backend** — REST API with SSE progress streaming on port 5520
- **Next.js Web UI** — professional web interface for configuration, progress, and results
- **Template Registry** — 350 subtype-to-template mappings (Tier 1, 2, and generic)

---

## Quick Start

### CLI (Generation Only)

```bash
pip install -r requirements.txt
cp .env.example .env

# Generate 20 cases (legacy mode)
python main.py generate

# Generate 50 dynamic cases via lifecycle engine
python main.py generate --count 50

# Generate with constraints
python main.py generate --count 100 --seed 42 --stages settlement_heavy

# MerusCase integration
python main.py create [--dry-run]  # Create cases in MerusCase
python main.py upload              # Upload documents
```

### Web UI

```bash
# Terminal 1: Start FastAPI backend
python main.py serve

# Terminal 2: Start Next.js frontend
cd frontend && npm install && npm run dev
```

Open http://localhost:3000 for the web interface.

### Docker

```bash
docker-compose up
# FastAPI: http://localhost:5520
# Next.js: http://localhost:3000
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `python main.py generate` | Generate data + PDFs (legacy 20 or dynamic with `--count N`) |
| `python main.py generate --count 50` | Dynamic generation via lifecycle engine |
| `python main.py generate --count 50 --stages settlement_heavy` | Preset stage distribution |
| `python main.py create [--dry-run]` | Create cases in MerusCase via browser |
| `python main.py upload` | Upload documents to MerusCase via API |
| `python main.py run-all [--dry-run]` | Full pipeline (all 4 steps) |
| `python main.py status` | Show current progress |
| `python main.py verify [--visual]` | Verify cases in MerusCase |
| `python main.py audit [--verify-chain]` | SOC2 audit log management |
| `python main.py serve [--port 5520]` | Start FastAPI REST API |
| `python batch_create_cases.py` | Efficient single-session Browserless case creation |
| `python batch2_edge_cases.py` | Create 30 custom WC edge case scenarios |

## Lifecycle Engine

Cases are modeled as a DAG with probabilistic branching at each decision point:

```
INJURY -> CLAIM_FILED -> CLAIM_RESPONSE
  +-- accepted (55%) -> ACTIVE_TREATMENT
  +-- delayed (30%) -> INVESTIGATION
  +-- denied (15%) -> APPEAL
  -> UR_DISPUTE (40%) -> UR_DECISION -> IMR_APPEAL
  -> APPLICATION_FILED (if attorney, 70%)
  -> QME (50%) / AME (20%) EVALUATION
  -> DISCOVERY (depositions, subpoenas)
  -> LIEN_FILING (30%) -> LIEN_CONFERENCE
  -> RESOLUTION: Stipulations (45%) / C&R (40%) / Trial (15%)
  -> POST_RESOLUTION
```

Each node emits documents with configurable probability, count ranges, and date anchors using the 350-subtype taxonomy.

## Stage Distribution Presets

| Preset | Intake | Active Tx | Discovery | Med-Legal | Settlement | Resolved |
|--------|--------|-----------|-----------|-----------|------------|----------|
| balanced | 15% | 25% | 20% | 15% | 15% | 10% |
| early_stage | 30% | 35% | 15% | 10% | 7% | 3% |
| settlement_heavy | 5% | 10% | 15% | 20% | 30% | 20% |
| complex_litigation | 5% | 10% | 25% | 25% | 20% | 15% |

## API Endpoints (Port 5520)

| Method | Path | Description |
|--------|------|-------------|
| GET | /health | Health check |
| GET | /api/taxonomy/types | 15 parent types |
| GET | /api/taxonomy/subtypes | All 350 subtypes |
| POST | /api/generate | Start generation run |
| GET | /api/generate/{id}/status | SSE progress stream |
| GET | /api/runs | List all runs |
| GET | /api/preview/{id}/cases | List cases for a run |
| GET | /api/download/{id} | Download run as ZIP |
| POST | /api/meruscase/create-cases/{id} | Create in MerusCase |
| POST | /api/meruscase/upload-documents/{id} | Upload to MerusCase |

## Template Hierarchy

| Tier | Strategy | Count | Quality |
|------|----------|-------|---------|
| Tier 1 | Dedicated `build_story()` per subtype | 25 | High — custom layouts |
| Tier 2 | Parameterized variants of Tier 1 | ~100 | Medium — variant parameter |
| Tier 3 | Generic template with hint-driven structure | ~63 | Acceptable — correct structure |

**Total: 350 subtypes covered** (100% of Adjudica Classifier taxonomy)

### Enhanced Template Capabilities (v2.1)

| Template | Enhancement |
|----------|-------------|
| QME/AME Report | AMA Guides 5th Ed. impairment ratings (DRE spine, upper/lower extremity, psychiatric GAF, cardiovascular, pulmonary) |
| Treating Physician Report | Specialty dispatch to orthopedic, psychiatric, and general clinical exam pools (200+ findings) |
| Deposition Transcript | 13 topic categories, 600+ exchange variants (causation, apportionment, PD, VR, treatment necessity) |
| Utilization Review | UR/IMR chain modeling with realistic reviewer language |
| Subpoenaed Records | Records custodian certification and chain-of-custody formatting |
| Medical Chronology | Chronological narrative with AMA Guides cross-references |
| Settlement Memo | Almaraz/Guzman rebuttal language, apportionment analysis, LC 5814 penalty flags |

### Edge Case Coverage (v2.1)

The `batch2_edge_cases.py` script generates 30 scenarios that stress-test the Adjudica Classifier against atypical but valid CA WC case patterns:

- Death claims (LC 4700–4706) and PTD with vocational rehabilitation experts
- Kite (CVC §1871.7 rebuttal) and split carrier liability (LC 5500.5)
- Pro per applicants, LC 4553 serious and willful misconduct, LC 5814 unreasonable delay penalties
- Complex lien stacks, multi-carrier UR/IMR chains, Almaraz/Guzman impairment rebuttal
- Firefighter presumptions (LC 3212/3212.1) and sexual assault workplace claims

## Dependencies

### Python

| Package | Purpose |
|---------|---------|
| reportlab | PDF generation |
| Faker | Realistic test data |
| pydantic | Data models |
| click | CLI framework |
| httpx | Async HTTP client |
| fastapi | REST API |
| uvicorn | ASGI server |
| structlog | Structured logging |

### External

| Dependency | Required For |
|------------|--------------|
| merus-expert | MerusCase browser automation + API |
| Browserless API | Case creation (Step 3) |
| MerusCase API | Document upload (Step 4) |
| Adjudica-classifier | Taxonomy source |

---

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
