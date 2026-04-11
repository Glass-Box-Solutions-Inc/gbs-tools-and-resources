# Context Handoff: Red Team Realism Upgrade

**Created**: 2026-04-10
**Author**: Opus (planning agent)
**Status**: Plan approved, ready for execution
**Plan file**: `/home/vncuser/.claude/plans/kind-mapping-stroustrup.md`

---

## What This Is

A 7-phase upgrade to the Merus Test Data Generator that transforms it from PDF-only output to realistic multi-format case files matching real California Workers' Compensation case composition.

## Why

Red team review revealed the generator produces 100% PDF. Real WC cases have emails (10-15%), Word drafts (15-20%), scanned PDFs (35-40%), and native PDFs (20-25%). Documents also don't reference each other, volume distribution is imbalanced, and administrative noise is absent.

---

## The 7 Phases (Execute In Order)

### Phase 1: Data Model and Format Routing Infrastructure
**Goal**: Add `OutputFormat` enum, format dispatch, correct file extensions. Shim only — all formats still emit PDF.

**Create**:
- `data/format_assignment.py` — `SUBTYPE_FORMAT_MAP` dict + `assign_output_format(subtype, rng)` function

**Modify**:
- `data/models.py` — Add `OutputFormat` enum (`pdf`, `eml`, `docx`, `scanned_pdf`); add `output_format` field to `DocumentSpec` (default `pdf`)
- `data/fake_data_generator.py` — In `_generate_lifecycle_manifest()` (~line 460), call `assign_output_format()` for each DocumentSpec
- `orchestration/pipeline.py` — Update `_sanitize_filename()` for correct extensions; add format dispatch in generation loop; rename `generate_pdfs()` -> `generate_documents()` (keep alias)
- `orchestration/progress_tracker.py` — Add `output_format` column to documents table
- `service/routes/preview.py` — Serve correct MIME types for .eml/.docx
- `service/routes/download.py` — Change `*.pdf` glob to include all formats

**Format assignment rules** (for `format_assignment.py`):
```
Email (.eml) ~50% probability: ADJUSTER_LETTER_*, DEFENSE_COUNSEL_LETTER_*,
  CLIENT_CORRESPONDENCE_*, CLIENT_STATUS_LETTERS, ADVOCACY_LETTERS_*,
  SETTLEMENT_DEMAND_LETTER, QME_PANEL_STRIKE_LETTER, CLIENT_REPORT_ANALYSIS_LETTER,
  CLIENT_SETTLEMENT_RECOMMENDATION, CLIENT_CASE_VALUATION_LETTER, PTP_REFERRAL_LETTER

Word (.docx) 100%: SETTLEMENT_VALUATION_MEMO, CASE_ANALYSIS_MEMO, TRIAL_BRIEF,
  DEFENSE_TRIAL_BRIEF, MEDICAL_CHRONOLOGY_TIMELINE, DEPOSITION_SUMMARY,
  SETTLEMENT_CONFERENCE_STATEMENT, PRETRIAL_CONFERENCE_STATEMENT,
  JOINT_PRETRIAL_CONFERENCE_STATEMENT

Scanned PDF ~60% probability: TREATING_PHYSICIAN_REPORT_PR2/PR4/FINAL,
  DIAGNOSTICS_*, OPERATIVE_HOSPITAL_RECORDS, DISCHARGE_SUMMARY,
  ACUTE_CARE/EMERGENCY_ROOM, PHARMACY_RECORDS, all *_RECORDS subtypes,
  SUBPOENAED_RECORDS_*, PERSONNEL_FILES, WAGE_STATEMENTS_*

Native PDF: Everything else (filings, orders, settlements, regulatory, billing, UR/IMR)
```

**Test**: `tests/test_format_assignment.py`

---

### Phase 2: Email (.eml) Generation
**Goal**: RFC 2822 .eml files for correspondence. No new deps (Python `email` stdlib).

**Create**:
- `data/email_metadata.py` — `EMAIL_PARTICIPANT_MAP`, `generate_email_address()`, `generate_email_headers()`

**Modify**:
- `pdf_templates/base_template.py`:
  - Refactor `generate()` (line 118) to dispatch by format
  - Move current PDF logic to `_generate_pdf()`
  - Add `generate_eml()` calling `build_story()` then `_story_to_plaintext()`
  - Add `_story_to_plaintext(story)` helper that walks flowables, strips HTML tags from Paragraphs, formats Tables as text, converts Spacers to newlines

**Email addresses already exist on model**:
- `case.applicant.email` (models.py:42)
- `case.insurance.adjuster_email` (models.py:73)
- `case.insurance.defense_email` (models.py:77)

**Test**: `tests/test_eml_generation.py`

---

### Phase 3: Word (.docx) Generation
**Goal**: Word documents with firm letterhead for attorney work product.

**Deps**: Add `python-docx>=1.1,<2.0` to `requirements.txt`

**Create**:
- `data/docx_styles.py` — reportlab -> docx style mapping, letterhead config

**Modify**:
- `pdf_templates/base_template.py`:
  - Add `generate_docx()` calling `build_story()` then `_story_to_docx()`
  - Add `_story_to_docx(story, doc)` converter mapping: Paragraph -> docx paragraph, Table -> docx table, bold/italic tags -> docx runs
  - Letterhead in document header section (firm name + address + phone)
  - Footer: "CONFIDENTIAL" + page number

**Style mapping**:
- CenterBold -> Title
- SectionHeader -> Heading 2
- BodyText14 -> Normal (12pt Times New Roman)
- DoubleSpaced -> Normal with double spacing
- SmallItalic -> Normal italic 9pt
- Transcript -> Normal Courier 10pt

**Test**: `tests/test_docx_generation.py`

---

### Phase 4: Scan-Simulated PDF Generation
**Goal**: Image-based PDFs with scan artifacts for medical/external records.

**Deps**: Add `pymupdf>=1.24,<2.0` to `requirements.txt`

**Create**:
- `pdf_templates/scan_simulator.py` — `simulate_scan(pdf_bytes, rng) -> bytes`:
  1. Render PDF pages to images via pymupdf at 150-200 DPI
  2. Per-page transforms (Pillow): rotation (-1.5 to +1.5 deg), brightness jitter (0.90-1.10), JPEG compression (quality 72-88), light noise
  3. Optional fax header (15%): "FAX TRANSMISSION — [date] — PAGE n OF total"
  4. Reassemble images into PDF via reportlab

**Modify**:
- `pdf_templates/base_template.py` — Add `generate_scanned_pdf()` that calls `_generate_pdf()` then pipes through `simulate_scan()`

**Test**: `tests/test_scan_simulation.py`

---

### Phase 4A: Document Artifact Layer
**Goal**: ANY document can acquire physical artifacts — POS stapled to front, fax cover prepended, attorney handwritten annotations (margin notes, highlights, sticky notes), RECEIVED stamps, Bates stamps, COPY watermarks, staple shadows, redaction bars. This makes the ENTIRE case file messy, not just scanned records.

**Create**:
- `data/artifact_profiles.py` — `ScanProfile` dataclass controlling which artifacts to apply; `select_artifact_profile(subtype, rng)` with probability tables per subtype category

**Modify**:
- `pdf_templates/scan_simulator.py` — Add `apply_scan_profile(pdf_bytes, profile, rng)`, `prepend_pos_page()`, `prepend_fax_cover()`, `apply_handwritten_annotations()`, `apply_stamps()`, `apply_staple_shadow()`, `apply_redaction()`
- `pdf_templates/base_template.py` — After PDF build, check `doc_spec.context.get("artifact_profile")` and apply. ALL templates get artifacts.
- `data/fake_data_generator.py` — In `_generate_lifecycle_manifest()`, call `select_artifact_profile()` for each DocumentSpec

**Key probabilities**: QME reports: 30% POS prepend, 20% annotations, 35% RECEIVED stamp, 50% staple shadow. Adjuster letters: 25% fax cover, 40% RECEIVED stamp. Psychiatric records: 30% redaction.

**Test**: `tests/test_artifact_layer.py`

**Depends on**: Phase 4

---

### Phase 4B: Case-File Messiness Engine
**Goal**: Case-level noise — duplicates from multiple sources, misfiled documents, multi-document PDFs (several docs scanned as one), incomplete documents, date errors. This is what makes the case file feel assembled by busy humans.

**Create**:
- `data/messiness_engine.py` — `CaseMessinessEngine` class with:
  - `inject_duplicates()` — 5-15% of docs duplicated with different scan quality (QME/AME at 30%)
  - `inject_misfiled_documents()` — 2-5% get wrong subtype label (within same broad category)
  - `create_merged_pdfs()` — 8-12% merged with adjacent docs into one file (POS+filing, adjuster letter+medical report, fax cover+UR decision)
  - `inject_date_errors()` — 3-7% have wrong year, transposed digits, or late upload
  - `inject_incomplete_documents()` — 3-5% truncated (page 1 of 3, pages 2-3 missing)

**Modify**:
- `data/models.py` — Add to DocumentSpec: `is_duplicate`, `is_misfiled`, `is_incomplete`, `merged_subtypes`, `page_count_override`
- `data/fake_data_generator.py` — After lifecycle manifest is built (~line 496), pass through `CaseMessinessEngine.apply()`
- `orchestration/pipeline.py` — Handle merged PDFs (concatenate stories with PageBreak), incomplete docs (truncate), duplicates (different artifact profile)

Standard cases: 5-10% duplicates, 2-3% misfiled, 5-8% merged. Complex cases: 15-25% duplicates, 5-8% misfiled, 10-15% merged.

**Test**: `tests/test_messiness_engine.py`

**Depends on**: Phase 1, Phase 4A

---

### Phase 5: Volume Rebalancing
**Goal**: Match real WC case volumes. Reduce PR-4/POS over-generation, increase email/correspondence.

**Modify**:
- `data/lifecycle_engine.py`:
  - TREATING_PHYSICIAN_REPORT_PR4 in active_treatment: (2,5) -> (1,3)
  - PROOF_OF_SERVICE everywhere: (1,2)/(1,3) -> (1,1)
  - CLIENT_CORRESPONDENCE_INFORMATIONAL: (1,3) p=0.7 -> (2,4) p=0.9
  - CLIENT_STATUS_LETTERS: (0,1) p=0.4 -> (1,3) p=0.8
  - ADJUSTER_LETTER_INFORMATIONAL at discovery+: (1,2) -> (2,3)
  - DEFENSE_COUNSEL_LETTER_INFORMATIONAL at discovery: (0,1) p=0.5 -> (1,3) p=0.8
  - Add ADVOCACY_LETTERS_PTP at active_treatment: (1,2) p=0.5
  - Add CLIENT_CASE_VALUATION_LETTER at discovery: (0,1) p=0.6
  - STANDARD_GLOBAL_CAP: 80 -> 120
  - COMPLEX_GLOBAL_CAP: 150 -> 200

- `data/case_profile_generator.py` — Update STAGE_DOC_RANGES:
  - intake: (15, 25), active_treatment: (30, 55), discovery: (45, 80)
  - medical_legal: (40, 70), settlement: (60, 110), resolved: (80, 180)

- `tests/test_lifecycle.py` + `tests/test_quality_fixes.py` — Update cap assertions

---

### Phase 6: Interdocument Coherence
**Goal**: Documents reference each other. Settlement memos cite actual QME WPI ratings.

**Create**:
- `data/case_context.py` — `CaseContextAccumulator` class:
  - `wpi_rating`, `pd_percentage`, `mmi_date`, `settlement_range`
  - `generated_docs: list[tuple[title, date, subtype]]`
  - `record_document(doc_spec, summary)`, `get_prior_docs()`, `get_cross_reference()`

**Modify**:
- `orchestration/pipeline.py` — Create accumulator per case, pass via `doc_spec.context["_accumulator"]`, call `record_document()` after each doc
- `pdf_templates/base_template.py` — Add `_get_accumulator()` + `_format_cross_references()` helpers
- `pdf_templates/summaries/settlement_memo.py` — Use accumulated WPI, cite medical reports by title
- `pdf_templates/correspondence/adjuster_letter.py` — Reference specific medical reports
- `pdf_templates/correspondence/defense_counsel_letter.py` — Reference depositions/QME
- `pdf_templates/medical/qme_ame_report.py` — Record WPI to accumulator, list TP reports reviewed

**Test**: `tests/test_case_context.py`

---

### Phase 7: Administrative Noise Documents
**Goal**: Fax covers, file notes, blank pages (3-8% of total docs).

**Modify taxonomy** (`data/taxonomy.py`):
- Add `INTERNAL_FILE_NOTE`, `BLANK_SCANNED_PAGE` to DocumentSubtype enum + labels + mappings
- Note: `FAX_CORRESPONDENCE` (line 407) and `EVALUATION_COVER_LETTER` (line 398) already exist

**Create**:
- `pdf_templates/administrative/__init__.py`
- `pdf_templates/administrative/fax_cover_sheet.py` — 1-page: sender/recipient, page count, short message
- `pdf_templates/administrative/file_note.py` — 1-2 sentences: date, author, brief note
- `pdf_templates/administrative/blank_page.py` — Nearly-empty page (always scanned_pdf format)
- `pdf_templates/administrative/cover_letter_enclosure.py` — "Enclosed please find..." with doc titles from accumulator

**Modify**:
- `pdf_templates/registry.py` — Register new templates
- `data/lifecycle_engine.py` — Add rules: FAX p=0.15-0.20, FILE_NOTE p=0.10-0.15, BLANK_PAGE p=0.05, COVER_LETTER p=0.15
- `data/format_assignment.py` — FAX/BLANK -> scanned_pdf, others -> pdf
- `data/fake_data_generator.py` — Update SUBTYPE_TO_TEMPLATE + title generation

**Test**: `tests/test_administrative_noise.py`

---

### Phase 8: Mega Subpoenaed Records (Kaiser/Blue Shield Medical History Dumps)
**Goal**: Generate 50-2000+ page subpoenaed medical records simulating a full health system records dump. These are the single largest documents in any WC case and the hardest for timeline extraction.

**Critical fix**: Current `subpoenaed_records.py` generates 3-8 pages. Those are the **copy service cover/custodian declaration** — NOT the records. Real subpoenaed records are NEVER 5-7 pages. The copy service paperwork is 5-7 pages. BEHIND it is the patient's entire medical life.

**Create**:
- `data/medical_history_generator.py` — `MedicalHistoryGenerator` class: generates age-correlated chronic conditions, prior surgeries, medication lists, visit timelines spanning 3-10 years, prior complaints to SAME body parts as industrial injury (critical for apportionment testing)
- `data/health_plan_constants.py` — Kaiser, Blue Shield of CA, Anthem Blue Cross, Health Net facility names, department names, provider pools, common non-industrial diagnoses, medication formularies
- `data/non_industrial_content_pools.py` — Annual physical templates, chronic disease management (diabetes/HTN/hyperlipidemia), OB/GYN, behavioral health (PHQ-9/GAD-7/therapy notes), ER visits (MVA, flu, lacerations), dental referrals, ophthalmology
- `pdf_templates/discovery/mega_record_sections/` — Section generators:
  - `cover_sheet.py` (2-5 pages) — Custodian declaration, TOC matching actual content
  - `primary_care.py` (50-150 pages) — Office visits, chronic disease mgmt, vitals trending
  - `specialty_consults.py` (30-80 pages) — Ortho, neuro, cardio, GI, derm
  - `laboratory.py` (40-80 pages) — Lab panels in tabular format, flagged abnormals, trending
  - `diagnostic_imaging.py` (20-40 pages) — Full radiology reads, comparison to priors
  - `pharmacy_log.py` (30-60 pages) — Every Rx filled for 3-10 years, 50-150+ items/year
  - `emergency_department.py` (20-50 pages) — ED triage, physician notes, discharge instructions for non-industrial visits (MVA, flu, allergic reaction)
  - `hospital_records.py` (30-100 pages) — Admit H&P, daily progress notes, nursing flowsheets, operative reports for non-industrial admissions (appendectomy, childbirth)
  - `behavioral_health.py` (20-50 pages) — Psychiatric evals, therapy session notes, PHQ-9/GAD-7 scores
  - `physical_therapy.py` (15-30 pages) — PT for pre-existing non-industrial complaints
  - `ob_gyn.py` (15-30 pages) — Annual exams, mammograms, prenatal care (~50% of female patients)
  - `miscellaneous.py` (20-40 pages) — Immunizations, allergy lists, HIPAA consent, patient portal messages, duplicate pages, blank separators, occasional wrong-patient pages

**Modify**:
- `pdf_templates/discovery/subpoenaed_records.py` — Rename `_build_medical_records()` to `_build_copy_service_cover()`. Add `_build_actual_records()` calling MedicalHistoryGenerator. Cover always followed by actual records (the cover alone is never a complete document).
- `data/lifecycle_engine.py` — SUBPOENAED_RECORDS_MEDICAL with `mega_records=True` context at discovery stage, p=0.3-0.5 for attorney cases. Volume splitting: 20-30% of >400 page records split into 2-3 volumes.
- `pdf_templates/scan_simulator.py` — Add `simulate_scan_variable_quality()` with DIFFERENT degradation per section (Kaiser EMR = clean; old records = poor; faxed referrals = bad; handwritten = variable; 5-10% of pages upside-down; 2-5% sideways)

**Facility format profiles**: Kaiser EMR (clean monospaced), small private clinic (handwritten on forms), hospital system (mixed typed/handwritten), community health center (template-based forms). Assigned per-provider, consistent across all their pages.

**Page targets**: Simple case 50-150; standard 200-500; complex 400-800; complex+hospital 600-1200; Salerno mega 1000-2000.

**Test**: `tests/test_mega_subpoenaed_records.py`

**Depends on**: Phase 4, Phase 4B

---

## Key Architecture Decisions

1. **All formats reuse `build_story()`** — Email extracts text, Word converts flowables, scanned PDF post-processes. Zero duplicate content generation.
2. **Format assignment is probabilistic** — 50% of letters are email, 60% of medical records are scanned. Creates realistic mix.
3. **Accumulator is optional** — Templates check for it and degrade gracefully. Backward compat preserved.
4. **No system dependencies** — `pymupdf` and `python-docx` are pure Python wheels.
5. **Backward compat** — `output_format` defaults to `pdf`. `generate_pdfs()` aliased to `generate_documents()`.
6. **Artifact layer is cross-cutting** — Applied to ALL document types in `generate()`, not just scanned PDFs. Any document can have POS prepended, stamps, annotations.
7. **Messiness engine mutates the manifest** — Runs after lifecycle engine produces clean output, introduces duplicates/misfiled/merged/incomplete/date errors at data level.
8. **Subpoenaed records = copy service cover + actual records** — The 3-8 page cover is just the beginning. Actual records are 50-2000+ pages behind it.
9. **Non-industrial content is the majority of subpoenaed records** — 80-90% is routine care. The WC-relevant treatment is buried. This tests timeline extraction's ability to find the needle.

## Existing Model Fields for Email Generation

```python
GeneratedApplicant.email            # models.py:42
GeneratedInsurance.adjuster_email   # models.py:73
GeneratedInsurance.defense_email    # models.py:77
```

## Key File Locations

```
data/models.py                          # DocumentSpec (line 126)
data/lifecycle_engine.py                # All emission rules
data/fake_data_generator.py             # _generate_lifecycle_manifest() (line 414)
data/taxonomy.py                        # 380 subtypes
orchestration/pipeline.py               # generate_pdfs() generation loop
pdf_templates/base_template.py          # generate() method (line 118)
pdf_templates/registry.py               # Template registry
pdf_templates/scan_simulator.py         # NEW
data/format_assignment.py               # NEW
data/email_metadata.py                  # NEW
data/docx_styles.py                     # NEW
data/case_context.py                    # NEW
pdf_templates/administrative/*.py       # NEW
requirements.txt                        # Dependencies
```

## Run Commands

```bash
cd /home/vncuser/projects/gbs-tools-and-resources/packages/merus-test-data-generator

# Install deps (after adding to requirements.txt)
pip install -r requirements.txt

# Run tests
python -m pytest tests/ -v

# Generate test cases to verify
python main.py generate --count 10 --seed 42

# Check output formats
find output/ -type f | sed 's/.*\.//' | sort | uniq -c | sort -rn
```

## Verification Checklist

- [ ] Output contains .pdf, .eml, .docx files
- [ ] .eml files parse with `email.parser.Parser`
- [ ] .docx files have firm letterhead in header
- [ ] Some PDFs are image-based (scanned)
- [ ] Settlement memos reference QME reports by title
- [ ] Email correspondence is 10-15% of total documents
- [ ] Word work product is 15-20%
- [ ] Noise documents are 3-8%
- [ ] Total volume per resolved case is 80-180 documents
- [ ] All existing tests still pass
- [ ] `python main.py generate --count 10` completes without errors

---

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
