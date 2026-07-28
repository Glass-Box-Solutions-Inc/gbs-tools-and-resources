# BUILD_NOTES — wc-synthetic-caseload-engine (AJC-34)

Architecture briefing for implementing agents. Read alongside `ISA.md` (the criteria contract).
This file is a build-time artifact; it may be deleted after v1 ships.

## What this package is

Seed-driven generator of complete synthetic CA workers' compensation **attorney** case files.
Consumers: Adjudica demo-account caseloads, classifier accuracy corpus, future synthetic needs.

## The substrate (reuse, never copy)

`../merus-test-data-generator` (Python 3.12, no pyproject — bridge via sys.path):

| Asset | Path (relative to substrate root) | Use |
|---|---|---|
| Taxonomy enums (15 types / ~350 subtypes — STALE vs classifier's 353) | `data/taxonomy.py` | import; this package overlays the 3 missing subtypes until upstream re-syncs |
| Lifecycle DAG (19 stages, emission rules, caps) | `data/lifecycle_engine.py` | wrap `walk_lifecycle`/`collect_documents_for_case`; extend with lien/recon machines HERE (do not edit substrate) |
| Case profiles/constraints | `data/case_profile_generator.py` (`CaseConstraints`, presets) | map our distributions onto its presets where possible |
| Fake data engine | `data/fake_data_generator.py` (`FakeDataGenerator(seed=...)` → `GeneratedCase`) | cast generation |
| Models | `data/models.py` (`GeneratedCase`, `DocumentSpec`, `OutputFormat`) | interop types |
| Format assignment | `data/format_assignment.py` | default format probabilities; our `format_mix` overrides |
| Template registry (all subtypes → template class) | `pdf_templates/registry.py` | render dispatch |
| Base template + 4-format dispatch | `pdf_templates/base_template.py` (`generate()`) | rendering |
| Scan simulator | `pdf_templates/scan_simulator.py` | pass an explicit seed derived from `rng_seed`+doc index (substrate's own `hash()` seeding is PYTHONHASHSEED-unstable — do NOT rely on it; call with deterministic inputs) |
| Content pools | `data/content_pools.py`, `ama_guides_content.py`, `deposition_exchanges.py`, `wc_constants.py`, `template_hints.py` | realism |
| Email metadata / docx styles | `data/email_metadata.py`, `data/docx_styles.py` | eml/docx |

Bridge pattern (existing precedent: substrate's `orchestration/case_creator.py` does this to merus-expert):
```python
# src/wc_caseload_engine/substrate.py — ONLY place sys.path is touched
SUBSTRATE = Path(__file__).resolve().parents[3] / "merus-test-data-generator"
sys.path.insert(0, str(SUBSTRATE))
```
Verify early that substrate modules import cleanly this way (they import each other as `data.x` / `pdf_templates.y` — confirm and adapt: you may need to insert the substrate ROOT so `data`/`pdf_templates` resolve as top-level packages).
**Pin check:** if any substrate import fails, fix by adjusting the bridge, never by copying files.

## Classifier (vocabulary of record)

`/home/vncuser/projects/Adjudica-classifier`:
- `src/taxonomy/{types,subtypes,mapping}.ts` — 15 types / **353 subtypes** (tests assert 353). `taxonomy-check` command parses these TS files (regex on `KEY: "Label"` entries is fine) and diffs against our effective taxonomy.
- Gotchas to encode in tests: `CLAIM_FORM` and `CLAIM_FORM_DWC1` share a label; `OFFER_OF_WORK_REGULAR_AD_10133_53`/`OFFER_OF_WORK_MODIFIED_AD_10118` labels are swapped vs keys (key is truth); `PETITION_FOR_PENALTIES` lives under CORRESPONDENCE.
- Corpus filename convention (optional output mode): `TC-###_###_<SUBTYPE_KEY>_<YYYY-MM-DD>.pdf` (regex `^(TC-\d{3})_(\d{3})_(.+)_(\d{4}-\d{2}-\d{2})\.pdf$`). Default mode: neutral filenames (no subtype leak).

## Seed schema (the product's core — implement exactly)

`CaseSeed` (Pydantic v2, `extra="forbid"`), YAML-loaded:

```yaml
case_id: martinez-001
rng_seed: 12345
profile:                    # all optional; derived from rng_seed when omitted
  applicant: {name?, age?, occupation?, tenure_years?}
  employer: {name?, industry?, county?}
  carrier: {name?}
  attorneys: {applicant_firm?, defense_firm?}
  physicians: {ptp_specialty?, qme_specialty?}
injury:
  type: specific | cumulative_trauma | death
  date_of_injury: 2023-04-12          # or ct_start/ct_end for CT
  body_parts: [{part: lumbar_spine, icd10: M54.5, detail: "L4-L5"}]   # 1..5
  mechanism: auto | <free text>
lifecycle:
  target_stage: intake|active_treatment|discovery|medical_legal|pre_trial|resolved|post_recon
  claim_response: accepted | delayed | denied
  eval_type: qme | ame | none
  ur_dispute: {enabled: bool, decision: upheld|overturned, imr: bool, imr_outcome: upheld|overturned}
  resolution: {type: stipulations|c_and_r|findings_award|take_nothing|pending, msa: bool}
  reconsideration:
    enabled: bool
    outcome: denied | granted_remand | granted_reversed
    post_recon: further_litigation | settled | affirmed_final
  liens:
    count: 0..8
    claimants: [medical_provider|hospital|pharmacy|ambulance|edd|attorney_costs|self_procured]
    resolution: lien_stipulation | lien_resolution_agreement | dismissal | order_on_lien | mixed | pending
    post_resolution_litigation: bool     # lien fight continues after case-in-chief resolves (common reality)
  doctrine_hooks: []   # subset of: ogilvie almaraz_guzman benson escobedo kite going_and_coming sibtf
                       # death_dependency lc3208_3_psych gfpa firefighter_presumption imr_constitutionality
                       # ab5_dynamex lc4664_prior_award
documents:
  global_cap: 120
  format_mix: {pdf: 0.6, scanned_pdf: 0.25, eml: 0.1, docx: 0.05}
  include_only: []          # subtype keys and/or parent type keys
  exclude: []
  overrides:                # highest precedence
    - {subtype: DEPOSITION_TRANSCRIPT, count: 2}
    - {type: MEDICAL_CLINICAL, min: 8, max: 25}
output:
  filename_style: neutral | corpus      # corpus → TC-style names
  formats: [pdf, scanned_pdf, eml, docx]  # allowed output formats
```

**Control precedence (document in README + test):** per-subtype override > include_only/exclude > per-type min/max > lifecycle emission defaults > global_cap (cap trims lowest-priority filler last-in). A control demanding a lifecycle-invalid subtype emits anyway + WARN log (ISC-29).

`CaseloadSpec`:
```yaml
caseload_id: demo-2026q3
defaults: {<partial CaseSeed>}          # deep-merged under each case
cases: [<CaseSeed>, ...]                # explicit seeds
auto: {count: 20, distribution: balanced, rng_seed: 777}   # derives additional CaseSeeds
```
Distributions: implement `balanced`, `early_stage`, `settlement_heavy`, `complex_litigation` — calibrate from `/home/vncuser/projects/wc-knowledge-base/docs/PRD-WC-ATTORNEY-MOCK-CASELOAD.md` §3/Appendices (17-field CaseParameters; our schema must remain a superset of it). **Auto-derived seeds are always materialized to `<out>/<case_id>/seed.yaml`** — the seed is the surfaced contract (ISC-18).

## Lifecycle extension (this package's own module, not substrate edits)

`lifecycle_ext.py`: post-process/extend the substrate walk:
1. Map seed lifecycle fields → substrate `CaseParameters`/`CaseConstraints` for the core walk (injury→resolution).
2. **Lien machine**: per lien claimant → track of events: lien claim filing (subtype by claimant type: LIEN_MEDICAL_PROVIDER/LIEN_HOSPITAL/LIEN_PHARMACY/LIEN_AMBULANCE_TRANSPORT/LIEN_EDD_OVERPAYMENT/LIEN_ATTORNEY_COSTS/LIEN_SELF_PROCUREMENT_MEDICAL) → NOTICE_OF_LIEN_FILING → optional NOTICE_OF_LIEN_CONFERENCE + PRETRIAL_CONFERENCE_STATEMENT_LIEN → resolution doc (LIEN_RESOLUTION | LIEN_STIPULATION_AGREEMENT | LIEN_DISMISSAL | ORDER_ON_LIEN). If `post_resolution_litigation`, lien dates fall AFTER case-in-chief resolution date.
3. **Recon machine**: requires an award-type event (FINDINGS_AND_AWARD or ORDER_APPROVING_SETTLEMENT after trial): PETITION_RECONSIDERATION_FILED (≤25 days after award service) → PETITION_RECONSIDERATION_OPPOSITION → optional PETITION_RECONSIDERATION_REPLY → ORDER_ON_RECONSIDERATION (60-day statutory window). Outcomes:
   - denied + affirmed_final → close
   - granted_remand + further_litigation → DECLARATION_OF_READINESS, NOTICE_OF_HEARING_COURT_ISSUED, MINUTES_OF_HEARING, AMENDED_FINDINGS_AWARD
   - granted_remand + settled → COMPROMISE_AND_RELEASE_* or STIPULATIONS_* + ORDER_APPROVING_SETTLEMENT dated post-recon
   - granted_reversed → ORDER_ON_RECONSIDERATION + AMENDED_FINDINGS_AWARD
4. Emit a normalized `PlannedDocument{subtype, type, date, author_role, format, track}` list; date engine keeps monotone order within tracks and statutory windows.

## Rendering

`renderer.py`: for each PlannedDocument resolve template via substrate `pdf_templates/registry.py`; build the substrate's expected case context from our cast (one canonical `CaseContext` built once per case — names/ADJ/DOI/employer/carrier identical everywhere, ISC-58); dispatch by format via `BaseTemplate.generate()`. Scan seed = `sha256(f"{rng_seed}:{doc_index}") % 2**32` passed explicitly.

## Outputs

```
<out>/<case_id>/
  seed.yaml
  manifest.json        # {caseId, adjNumber, applicant, stage, resolution, liens[], recon{},
                       #  documents:[{filename, subtype, type, format, documentDate, md5Checksum, fileSize, mimeType}],
                       #  provenance:{zeroRealPii: true, generator: "wc-synthetic-caseload-engine@<version>", seedHash}}
  documents/<files>
<out>/caseload_manifest.json
```
Manifest shape aligns with adjudica-ai-app `scripts/export-garcia-manifest.ts` document fields (objectKey omitted — assigned at ingest).

## CLI (click)

- `wc-caseload generate --spec spec.yaml --out DIR [--seed N override]`
- `wc-caseload seed --template [--out FILE]` (annotated full-surface example)
- `wc-caseload validate --out DIR` (taxonomy validity of manifests + determinism check option)
- `wc-caseload taxonomy-check [--classifier-path PATH]` (drift vs classifier TS source; nonzero exit on drift)

## Quality bar

- `pyproject.toml`: ruff (line 100), pytest; deps mirror substrate's requirements + pyyaml.
- ≥25 pytest tests: schema validation, precedence matrix, one test per lifecycle path (liens each resolution type, recon each outcome), determinism (same seed → identical manifest minus md5? NO — md5 included, must be identical too), taxonomy 353 check, render smoke (small case, all four formats, PDF >500 bytes & ≥1 page).
- Tests must not require network. Substrate import test first (fail fast with clear message if bridge breaks).
- `examples/demo-caseload.yaml`: 6 cases exercising: denied+recon-remand-settled, C&R with 3 liens through lien agreements, CT multi-part with UR/IMR, death+dependency, early-stage intake, trial+recon-denied.
- Repo docs quartet + GBS footer on every md; update root README/CLAUDE/ci.yml registries.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
