# MerusCase WC Test Data Generator

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

For company-wide development standards, see the main CLAUDE.md at ~/Desktop/CLAUDE.md.

For centralized business, legal, marketing, and product documentation, see the [Adjudica Documentation Hub](~/Desktop/adjudica-documentation/CLAUDE.md) and the [Quick Index](~/Desktop/adjudica-documentation/ADJUDICA_INDEX.md).

---

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
