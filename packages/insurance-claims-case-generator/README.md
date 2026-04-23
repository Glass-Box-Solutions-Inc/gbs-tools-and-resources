# Insurance Claims Case Generator

Lifecycle-aware synthetic California Workers' Compensation claims case generator.
Produces realistic claim profiles, regulatory timelines, and PDF documents for
AdjudiCLAIMS staging environment seeding, QA, and ML training data.

> Developed and documented by Glass Box Solutions, Inc. using human ingenuity and modern technology.

---

## Quick Start

### Install

```bash
cd packages/insurance-claims-case-generator
pip install -e ".[dev]"
```

### Generate a single case (JSON to stdout)

```bash
claims-gen generate --scenario standard_claim --seed 42
```

### Generate a case with PDFs (JSON + ZIP)

```bash
claims-gen generate --scenario litigated_qme --seed 7 \
  --output case.json \
  --zip-output case_pdfs.zip
```

### Seed a case into AdjudiCLAIMS staging

```bash
export ADJUDICLAIMS_URL=https://staging.adjudiclaims.com
export ADJUDICLAIMS_EMAIL=seed@example.com
export ADJUDICLAIMS_PASSWORD=secret

claims-gen seed --scenario standard_claim --seed 42 --env staging
```

### List all scenarios

```bash
claims-gen scenarios
```

### Run tests

```bash
python -m pytest tests/ -v --cov=claims_generator --cov-report=term-missing
```

### Build Docker image

```bash
docker build -t insurance-claims-case-generator .
```

### Run with Docker

```bash
# Generate case
docker run --rm insurance-claims-case-generator generate --scenario standard_claim

# Seed to staging
docker run --rm \
  -e ADJUDICLAIMS_URL=https://staging.adjudiclaims.com \
  -e ADJUDICLAIMS_EMAIL=seed@example.com \
  -e ADJUDICLAIMS_PASSWORD=secret \
  insurance-claims-case-generator seed --scenario standard_claim --env staging

# Start API server
docker run --rm -p 8001:8001 insurance-claims-case-generator api
```

---

## AdjudiCLAIMS API Reference

All endpoints require cookie-based session authentication via `POST /api/auth/login`.

| # | Method | Endpoint | Body / Fields | Success |
|---|--------|----------|---------------|---------|
| 1 | POST | `/api/auth/login` | `{ email, password }` | 200 + `Set-Cookie: session=...` |
| 2 | POST | `/api/claims` | `{ claimNumber, claimantName, dateOfInjury, bodyParts[], employer, insurer, dateReceived }` | 201 `{ id, claimNumber, status, ... }` |
| 3 | PATCH | `/api/claims/:id` | Any subset of `{ isLitigated, hasApplicantAttorney, isCumulativeTrauma, status, ... }` | 200 `{ id, ... }` |
| 4 | POST | `/api/claims/:claimId/documents` | `multipart/form-data`: `file=<bytes>`, `documentType=<enum>` | 201 `{ id, claimId, ocrStatus, ... }` |
| 5 | GET | `/api/claims` | Query: `?take=50&skip=0` | 200 `{ claims[], total }` |
| 6 | GET | `/api/claims/:id` | — | 200 full claim object |

### Claim Status Enum

`OPEN` | `UNDER_INVESTIGATION` | `ACCEPTED` | `DENIED` | `CLOSED` | `REOPENED`

### DocumentType Enum (25 values)

`DWC1_CLAIM_FORM` | `MEDICAL_REPORT` | `BILLING_STATEMENT` | `LEGAL_CORRESPONDENCE` |
`EMPLOYER_REPORT` | `INVESTIGATION_REPORT` | `UTILIZATION_REVIEW` | `AME_QME_REPORT` |
`DEPOSITION_TRANSCRIPT` | `IMAGING_REPORT` | `PHARMACY_RECORD` | `WAGE_STATEMENT` |
`BENEFIT_NOTICE` | `SETTLEMENT_DOCUMENT` | `CORRESPONDENCE` | `OTHER` |
`WCAB_FILING` | `LIEN_CLAIM` | `DISCOVERY_REQUEST` | `RETURN_TO_WORK` |
`PAYMENT_RECORD` | `DWC_OFFICIAL_FORM` | `WORK_PRODUCT` | `MEDICAL_CHRONOLOGY` |
`CLAIM_ADMINISTRATION`

---

## Scenario Catalog

All 13 scenarios and their flag matrix:

| Slug | Litigated | Attorney | CT | Denied | Death | PTD | Docs |
|------|-----------|----------|----|--------|-------|-----|------|
| `standard_claim` | No | No | No | No | No | No | 8–14 |
| `cumulative_trauma` | No | No | Yes | No | No | No | 12–18 |
| `litigated_qme` | Yes | Yes | No | No | No | No | 18–30 |
| `denied_claim` | No | No | No | Yes | No | No | 10–16 |
| `death_claim` | No | No | No | No | Yes | No | 12–20 |
| `ptd_claim` | Yes | Yes | No | No | No | Yes | 20–35 |
| `psychiatric_overlay` | No | No | No | No | No | No | 14–22 |
| `multi_employer` | No | No | Yes | No | No | No | 16–26 |
| `split_carrier` | No | No | No | No | No | No | 10–18 |
| `complex_lien` | Yes | Yes | No | No | No | No | 20–32 |
| `expedited_hearing` | No | No | No | No | No | No | 10–16 |
| `qme_dispute_only` | No | No | No | No | No | No | 8–14 |
| `sjdb_voucher` | No | No | No | No | No | No | 10–16 |

**CT** = Cumulative Trauma. **PTD** = Permanent Total Disability.

---

## Seed Instructions

### Prerequisites

1. A running AdjudiCLAIMS instance (staging or production)
2. A seed account with `CLAIMS_ADMIN` role
3. Set the three environment variables:

   ```bash
   export ADJUDICLAIMS_URL=https://staging.adjudiclaims.com
   export ADJUDICLAIMS_EMAIL=seed@your-org.com
   export ADJUDICLAIMS_PASSWORD=<seed account password>
   ```

   In production (Cloud Run), set these via GCP Secret Manager. The client resolves:
   - `ADJUDICLAIMS_EMAIL` → secret `adjudiclaims-seed-email`
   - `ADJUDICLAIMS_PASSWORD` → secret `adjudiclaims-seed-password`
   - `ADJUDICLAIMS_URL` → secret `adjudiclaims-staging-url`

### Seed a single scenario

```bash
claims-gen seed --scenario standard_claim --seed 42 --env staging
```

Output (JSON to stdout):

```json
{
  "claim_id": "cla_abc123",
  "claim_number": "SCIF-2026-00123",
  "documents_uploaded": 11,
  "document_ids": ["doc_1", "doc_2", ...]
}
```

### Seed all scenarios (bash loop)

```bash
for scenario in standard_claim cumulative_trauma litigated_qme denied_claim \
  death_claim ptd_claim psychiatric_overlay multi_employer split_carrier \
  complex_lien expedited_hearing qme_dispute_only sjdb_voucher; do
  claims-gen seed --scenario "$scenario" --seed 42 --env staging
done
```

### Seed operation order

For each `seed` invocation the client executes:

1. `POST /api/auth/login` — authenticate, store session cookie
2. `POST /api/claims` — create claim from generated profile
3. `PATCH /api/claims/:id` — apply scenario flags (litigated, attorney, CT, status)
4. `POST /api/claims/:id/documents` — upload each generated PDF (one request per document)

---

## Architecture

```
src/claims_generator/
├── models/          — Pydantic models (ClaimCase, ClaimProfile, DocumentEvent, enums)
├── scenarios/       — 13 scenario presets + registry
├── core/            — Lifecycle DAG engine + timeline builder
├── profile/         — Profile generators (claimant, employer, financial, medical)
├── documents/       — 25 PDF document generators (ReportLab)
├── integrations/
│   ├── gcp_secrets.py         — Secret Manager client with env var fallback
│   └── adjudiclaims_client.py — Async httpx client for AdjudiCLAIMS REST API
├── api/             — FastAPI application (Phase 3)
├── cli.py           — Click CLI (generate, batch, seed, scenarios)
├── case_builder.py  — Orchestrates profile → DAG → timeline → PDFs
├── batch_builder.py — Parallel batch generation
└── exporter.py      — ZIP export
```

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ADJUDICLAIMS_URL` | For `seed` | AdjudiCLAIMS base URL |
| `ADJUDICLAIMS_EMAIL` | For `seed` | Seed account email |
| `ADJUDICLAIMS_PASSWORD` | For `seed` | Seed account password |
| `GCP_PROJECT` | Optional | GCP project for Secret Manager fallback |

No secrets are baked into the Docker image.

---

## CLI Reference

```
claims-gen generate  --scenario SLUG --seed INT [--output PATH] [--zip-output PATH] [--compact] [--no-pdfs]
claims-gen batch     --scenario SLUG --count INT [--seed-start INT] [--workers INT] [--output-dir DIR] [--zip-output PATH]
claims-gen seed      --scenario SLUG --seed INT --env [staging|production] [--url URL] [--email EMAIL] [--password PASS]
claims-gen scenarios
claims-gen --version
```
