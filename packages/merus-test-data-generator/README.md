# MerusCase WC Test Data Generator v2.0

**Lifecycle-aware Workers' Compensation case simulation engine** — generates 1-500 realistic CA WC cases with the Adjudica Classifier's 188-subtype document taxonomy, templated PDFs, and optional MerusCase population.

Built for the Merus-to-Adjudica import pipeline testing workflow.

---

## What's New in v2.0

- **188-Subtype Taxonomy** — aligned with the Adjudica Classifier (was 27 subtypes)
- **Lifecycle Engine** — probabilistic DAG models realistic CA WC case lifecycles
- **Dynamic Generation** — 1-500 cases with configurable stage distribution and constraints
- **FastAPI Backend** — REST API with SSE progress streaming on port 5520
- **Next.js Web UI** — professional web interface for configuration, progress, and results
- **Template Registry** — 188 subtype-to-template mappings (Tier 1, 2, and generic)

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

Each node emits documents with configurable probability, count ranges, and date anchors using the 188-subtype taxonomy.

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
| GET | /api/taxonomy/types | 12 parent types |
| GET | /api/taxonomy/subtypes | All 188 subtypes |
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

**Total: 188 subtypes covered** (100% of Adjudica Classifier taxonomy)

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
