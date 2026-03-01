# MerusCase WC Test Data Generator

Generates 20 realistic California Workers' Compensation test cases with 20-50 templated PDF documents each (~700 documents total), then populates them in MerusCase via browser automation and API upload.

Built for the Merus-to-Adjudica import pipeline testing workflow.

---

## Quick Start

```bash
pip install -r requirements.txt
cp .env.example .env
python main.py generate    # Generate data + PDFs (offline, ~5 min)
python main.py create      # Create cases in MerusCase (~20 min)
python main.py upload      # Upload documents (~12 min)
python main.py run-all     # Or run all steps at once
```

> **Note:** Case creation (Step 3) requires Browserless and must run on `dev-workstation` (GCP VM). Steps 1-2 can run anywhere with Python 3.12+.

## CLI Commands

| Command | Description |
|---------|-------------|
| `python main.py generate` | Steps 1+2: Generate case data and PDF documents |
| `python main.py create [--dry-run]` | Step 3: Create cases in MerusCase via browser |
| `python main.py upload` | Step 4: Upload documents to MerusCase via API |
| `python main.py run-all [--dry-run]` | Full pipeline (all 4 steps) |
| `python main.py status` | Show current progress from SQLite tracker |
| `python main.py verify` | Verify cases exist in MerusCase via API |

## Pipeline Architecture

```
main.py (Click CLI)
    |
    v
orchestration/pipeline.py (4-step flow with SQLite resumability)
    |
    +-- Step 1: Generate Data ---> Faker + Pydantic models
    +-- Step 2: Generate PDFs ---> reportlab + 24 templates
    +-- Step 3: Create Cases  ---> MatterBuilder (browser automation)
    +-- Step 4: Upload Docs   ---> MerusCaseAPIClient (REST API)
```

| Step | What | Time | Infrastructure |
|------|------|------|----------------|
| 1. Generate Data | 20 `GeneratedCase` Pydantic objects from Faker | <1 sec | Offline |
| 2. Generate PDFs | ~700 PDFs across 24 templates in `output/` | ~5 min | Offline |
| 3. Create Cases | 20 cases in MerusCase via Browserless | ~20 min | dev-workstation |
| 4. Upload Docs | ~700 PDFs uploaded via MerusCase REST API | ~12 min | API access |

Each step is independently runnable. SQLite progress tracker enables resume after interruption.

## File Composition

**49 files | 8,036 lines of Python**

### Project Root

| File | Lines | Purpose |
|------|-------|---------|
| `main.py` | 227 | Click CLI with 6 commands (generate, create, upload, run-all, status, verify) |
| `config.py` | 45 | Environment variables, paths, upload/retry settings |
| `requirements.txt` | -- | Dependencies: reportlab, Faker, Pydantic, Click, httpx, structlog, Pillow |
| `.env.example` | -- | Template for required environment variables |
| `CLAUDE.md` | -- | Project documentation for Claude Code |

### `data/` -- Models, Constants, and Generation (4 files, 1,138 lines)

| File | Lines | Purpose |
|------|-------|---------|
| `models.py` | 182 | 14 Pydantic models. `GeneratedCase` as single source of truth. Enums: `LitigationStage` (6 stages), `InjuryType` (specific/CT/death), `DocumentSubtype` (26 types). |
| `wc_constants.py` | 317 | California WC reference data: 25 WCAB districts, ICD-10 codes, CPT codes, medications, WPI ranges, carriers, employers, judges, body parts. |
| `fake_data_generator.py` | 552 | Seeded Faker engine (seed=42). Generates consistent case data: applicant, employer, insurance, injuries, physicians, timeline, document manifest. |
| `case_profiles.py` | 87 | 20 case definitions: 3 intake (18-22 docs), 5 active treatment (25-35), 4 discovery (30-40), 3 med-legal (30-40), 3 settlement (35-45), 2 resolved (45-50). |

### `pdf_templates/` -- PDF Generation System (25 files, 5,592 lines)

**Base Template**

| File | Lines | Purpose |
|------|-------|---------|
| `base_template.py` | 287 | reportlab `SimpleDocTemplate` base class with letterheads, patient headers, claim blocks, signature blocks, lorem generators, and 11 custom paragraph styles. |

**Medical Templates (7 files, 1,123 lines)**

| File | Lines | Description |
|------|-------|-------------|
| `treating_physician_report.py` | 149 | PR-2/PR-3 format with ICD-10 codes, CPT codes, work restrictions |
| `diagnostic_report.py` | 106 | MRI/CT/X-ray findings with impressions and measurements |
| `operative_record.py` | 134 | Pre/post-op diagnosis, procedure narrative, anesthesia |
| `qme_ame_report.py` | 188 | 5-12 page QME: history, exam, AMA Guides ratings, WPI%, apportionment |
| `utilization_review.py` | 173 | UR with ACOEM criteria, decision (approve/modify/deny), appeal rights |
| `pharmacy_records.py` | 169 | Drug table: name, dosage, fill dates, pharmacy, prescriber, NDC codes |
| `billing_records.py` | 204 | UB-04/HCFA: CPT codes, charges, dates of service, diagnosis pointers |

**Legal Templates (5 files, 1,142 lines)**

| File | Lines | Description |
|------|-------|-------------|
| `application_for_adjudication.py` | 233 | WCAB application: parties, injury, body parts, ADJ number |
| `declaration_of_readiness.py` | 210 | DOR: hearing type, issues for determination, service list |
| `minutes_orders.py` | 230 | Hearing minutes: judge, appearances, orders, next hearing |
| `stipulations.py` | 240 | Stipulated award: PD rating, amounts, body parts, future medical |
| `compromise_and_release.py` | 359 | C&R: gross/net amounts, Medicare set-aside, third-party credits |

**Correspondence Templates (4 files, 822 lines)**

| File | Lines | Description |
|------|-------|-------------|
| `adjuster_letter.py` | 173 | Accept/deny, PD advances, settlement offers |
| `defense_counsel_letter.py` | 198 | Defense firm letterhead, legal analysis, recommendations |
| `court_notice.py` | 230 | WCAB hearing notices: date/time/location, hearing type |
| `client_intake.py` | 221 | Retainer reference, case summary, next steps |

**Discovery Templates (4 files, 797 lines)**

| File | Lines | Description |
|------|-------|-------------|
| `subpoena.py` | 145 | Subpoena duces tecum: records requested, custodian, dates |
| `subpoenaed_records.py` | 210 | Responsive records: custodian certification, records index |
| `deposition_notice.py` | 154 | Date, location, deponent, document requests |
| `deposition_transcript.py` | 288 | Q&A format with line numbers, examination, certification |

**Employment Templates (3 files, 836 lines)**

| File | Lines | Description |
|------|-------|-------------|
| `wage_statement.py` | 224 | Pay periods, rates, hours, overtime, employer certification |
| `job_description.py` | 271 | Duties, physical requirements, essential functions, ADA |
| `personnel_file.py` | 341 | Position history, performance reviews, leave, disciplinary |

**Summary Templates (2 files, 623 lines)**

| File | Lines | Description |
|------|-------|-------------|
| `medical_chronology.py` | 268 | Timeline: date, provider, event, body part, significance |
| `settlement_memo.py` | 355 | PD analysis, life pension calc, medical costs, recommendations |

### `orchestration/` -- Pipeline and Tracking (4 files, 847 lines)

| File | Lines | Purpose |
|------|-------|---------|
| `progress_tracker.py` | 294 | SQLite tracking. Tables: `runs`, `cases`, `documents`. Full resumability. |
| `pipeline.py` | 259 | 4-step orchestration. Template registry maps subtypes to modules. Dynamic import. |
| `document_uploader.py` | 168 | MerusCase API wrapper. Rate limiting with exponential backoff on 429. |
| `case_creator.py` | 126 | Browser automation wrapper. MatterBuilder with retry and session re-login. |

## Data Model Hierarchy

```
GeneratedCase
+-- case_number: str                     (e.g., "WC-2024-001")
+-- litigation_stage: LitigationStage    (INTAKE -> RESOLVED)
+-- applicant: GeneratedApplicant
|   +-- full_name, date_of_birth, ssn_last4
|   +-- phone, email, address (CA addresses)
+-- employer: GeneratedEmployer
|   +-- company_name, address, position, hire_date
+-- insurance: GeneratedInsurance
|   +-- carrier_name, claim_number, policy_number
|   +-- adjuster (name, phone, email)
|   +-- defense_counsel (name, firm, phone, email)
+-- injuries: list[GeneratedInjury]
|   +-- date_of_injury, injury_type (SPECIFIC/CT/DEATH)
|   +-- body_parts: list[str], adj_number, mechanism
|   +-- icd10_codes: list[tuple[str,str]]
+-- physicians: list[GeneratedPhysician]
|   +-- full_name, specialty, facility, license_number
|   +-- role (treating/QME/AME)
+-- timeline: GeneratedCaseTimeline
|   +-- 15+ chronological milestones (DOI -> case closed)
+-- document_specs: list[DocumentSpec]
    +-- doc_type, doc_subtype, title, date
    +-- template_class, context dict
```

## Document Distribution by Stage

| Document Type | Intake | Active Tx | Discovery | Med-Legal | Settlement | Resolved |
|---|---|---|---|---|---|---|
| Client Intake | 2 | 2 | 2 | 2 | 2 | 2 |
| Adjuster Letters | 1-2 | 2-3 | 3-4 | 3-4 | 4-5 | 5-6 |
| Treating Physician Reports | 2-3 | 4-6 | 5-7 | 5-7 | 5-7 | 5-7 |
| Diagnostics | 1-2 | 2-4 | 3-4 | 3-4 | 3-4 | 3-4 |
| Billing Records | 1-2 | 3-4 | 3-5 | 3-5 | 3-5 | 3-5 |
| Application for Adjudication | -- | 1 | 1 | 1 | 1 | 1 |
| Subpoenas/SDTs | -- | -- | 2-3 | 2-3 | 2-3 | 2-3 |
| Deposition Transcripts | -- | -- | 0-1 | 1-2 | 1-2 | 1-2 |
| QME/AME Reports | -- | -- | -- | 1-2 | 1-2 | 1-2 |
| Settlement Memo | -- | -- | -- | -- | 1 | 1 |
| Stips / C&R | -- | -- | -- | -- | 0-1 | 0-1 |

## Dependencies

### Python Packages

| Package | Version | Purpose |
|---------|---------|---------|
| reportlab | >=4.2 | PDF generation engine |
| Pillow | >=11.0 | Image handling for reportlab |
| Faker | >=33.0 | Realistic fake data generation |
| pydantic | >=2.10 | Data models with validation |
| click | >=8.1 | CLI framework |
| httpx[http2] | >=0.28 | Async HTTP client for API uploads |
| python-dotenv | >=1.0 | Environment variable loading |
| structlog | >=24.4 | Structured logging |

### External Dependencies

| Dependency | What | Required For |
|------------|------|--------------|
| merus-expert | MatterBuilder + MerusCaseAPIClient | Steps 3 and 4 |
| Browserless API | Headless Chrome | Step 3 (browser automation) |
| MerusCase API | REST API credentials | Step 4 (document upload) |

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `MERUSCASE_EMAIL` | Step 3 | MerusCase login email |
| `MERUSCASE_PASSWORD` | Step 3 | MerusCase login password |
| `BROWSERLESS_API_TOKEN` | Step 3 | Browserless.io API token |
| `MERUSCASE_CLIENT_ID` | Step 4 | MerusCase API client ID |
| `MERUSCASE_CLIENT_SECRET` | Step 4 | MerusCase API client secret |
| `OUTPUT_DIR` | Optional | PDF output directory (default: `./output`) |
| `DB_PATH` | Optional | SQLite database path (default: `./progress.db`) |

## Resumability

The SQLite progress tracker (`progress.db`) records which cases and documents have been generated, created, and uploaded. Re-running any command skips completed work and resumes from where it left off.

## Runtime Estimates

| Step | Time | Output |
|------|------|--------|
| Generate data | <1 sec | 20 GeneratedCase objects |
| Generate ~700 PDFs | ~5 min | 35-70 MB in `output/` |
| Create 20 cases | ~20 min | 20 cases in MerusCase |
| Upload ~700 docs | ~12 min | ~700 documents attached |
| **Total** | **~37 min** | Resumable at any step |

---

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
