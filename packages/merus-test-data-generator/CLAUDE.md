# MerusCase WC Test Data Generator

**Workers' Compensation test case generator with templated PDFs and MerusCase integration.**

---

## ⚠️ CRITICAL GUARDRAILS (READ FIRST)

1. **NEVER push without permission** — Even small fixes require express user permission. No exceptions.
2. **NEVER expose secrets** — No API keys, tokens, credentials in git, logs, or conversation.
3. **NEVER force push or skip tests** — 100% passing tests required.
4. **ALWAYS read parent CLAUDE.md** — `~/CLAUDE.md` for org-wide standards.
5. **ALWAYS use Definition of Ready** — 100% clear requirements before implementation.

---

## Purpose
Generates 20 realistic Workers' Compensation test cases with 20-50 templated PDFs each (~700 documents total) and populates them in MerusCase via browser automation + API upload.

## Tech Stack
- Python 3.12
- reportlab (PDF generation)
- Faker (realistic test data)
- Pydantic (data models)
- Click (CLI)
- httpx (API client)
- SQLite (progress tracking)

## Commands
```bash
python main.py generate    # Step 1+2: Generate data + PDFs
python main.py create      # Step 3: Create cases in MerusCase
python main.py upload      # Step 4: Upload documents
python main.py run-all     # Steps 1-4
python main.py status      # Show progress
python main.py verify      # Verify cases in MerusCase
```

## Dependencies
- `projects/merus-expert/` — MatterBuilder (browser automation), MerusCaseAPIClient (API)
- Browserless API token for case creation (runs on dev-workstation)

## Environment Variables
- `MERUSCASE_EMAIL` — MerusCase login
- `MERUSCASE_PASSWORD` — MerusCase password
- `BROWSERLESS_API_TOKEN` — Browserless API token
- `MERUSCASE_CLIENT_ID` — API client ID
- `MERUSCASE_CLIENT_SECRET` — API client secret

## Architecture
```
main.py (CLI) → pipeline.py (orchestration)
  → fake_data_generator.py → GeneratedCase objects
  → pdf_templates/ → PDF files in output/
  → case_creator.py → MatterBuilder → MerusCase browser
  → document_uploader.py → MerusCaseAPIClient → MerusCase API
  → progress_tracker.py → SQLite for resumability
```

For company-wide development standards, see the [Root CLAUDE.md](https://github.com/Glass-Box-Solutions-Inc/adjudica-documentation/blob/main/engineering/ROOT_CLAUDE.md).

For centralized business, legal, marketing, and product documentation, see the [Adjudica Documentation Hub](~/Desktop/adjudica-documentation/CLAUDE.md) and the [Quick Index](~/Desktop/adjudica-documentation/ADJUDICA_INDEX.md).

---

## ⚠️ GUARDRAILS REMINDER

Before ANY action, verify:

- [ ] **Push permission?** — Required for every push, no exceptions
- [ ] **Definition of Ready?** — Requirements 100% clear
- [ ] **Tests passing?** — 100% required
- [ ] **Root cause understood?** — For fixes, understand WHY first

---

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
