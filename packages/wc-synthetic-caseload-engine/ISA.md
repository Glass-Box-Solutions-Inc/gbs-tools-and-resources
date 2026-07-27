---
task: "Seed-driven WC synthetic attorney case-file engine"
project: wc-synthetic-caseload-engine
slug: 20260727-143600_wc-synthetic-caseload-engine
effort: E4
effort_source: classifier
phase: build
progress: 0/74
mode: interactive
started: 2026-07-27T14:36:00-07:00
updated: 2026-07-27T15:05:00-07:00
ticket: AJC-34
---

# ISA — WC Synthetic Caseload Engine

## Problem

Adjudica demo accounts hold five document-free matters and one hand-populated case (Garcia). There is no repeatable way to produce complete, realistic, synthetic CA workers' compensation attorney case files on demand. The closest tool, `merus-test-data-generator`, generates documents at scale but takes only CLI flags (no per-case seed artifact), models no reconsideration round-trips, models lien resolution thinly, is 3 subtypes stale against the classifier (350 vs 353), and offers no fine-grained per-case document type/count controls. The classifier's accuracy corpus covers only 97 of 353 subtypes for the same reason: nothing can generate targeted documents per specification.

## Vision

Alex writes (or auto-derives) a small YAML seed per case — who was hurt, how, how far the case went, which doctrines flavor it, exactly which documents in what quantities and formats — runs one command, and gets back complete attorney case files that read like a real applicant-side firm produced them: through lien conferences and executed lien agreements, through a petition for reconsideration that came back remanded and settled on remand. The same seeds regenerate byte-similar caseloads forever; the demo accounts stop being empty shells.

## Out of Scope

- Modifying `merus-test-data-generator` in place (Alex: "this becomes a new tool in that same repo"); it is consumed as a library.
- Adjudica-side ingestion code (generalizing `copy-garcia-to-prod.ts` to N matters lives in adjudica-ai-app; this engine only emits a compatible manifest).
- MerusCase push execution in v1 (reuse of the existing orchestration is wired as an optional export target, but Browserless case-creation runs are a separate operational task).
- Pixel-accurate official DWC form overlays (ReportLab approximations inherited from the substrate; form-overlay work remains unstarted upstream).
- Non-California jurisdictions; carrier/defense-POV caseloads as a primary product (defense documents appear inside applicant files, as they do in reality).
- Frontend UI; live LLM-generated prose in v1 (deterministic template substrate first; KB grounding hooks are structured, not free-generated).

## Principles

- The seed IS the interface: everything a case needs must be expressible — and is surfaced — in one reviewable artifact per case.
- Determinism before flourish: same seed + same version → same caseload; realism features (scan noise, messiness) must be seed-derived, never wall-clock-derived.
- The classifier taxonomy is the vocabulary of record: generate what the classifier can name, validate round-trip against it.
- Reuse the proven substrate: templates, content pools, and lifecycle machinery come from merus-test-data-generator; this engine adds control, not duplication.
- Synthetic data only — no real PHI/PII ever; `zeroRealPii: true` must be honestly assertable on every manifest.

## Constraints

- New standalone package `packages/wc-synthetic-caseload-engine/` following repo conventions (README/CLAUDE/CHANGELOG/PLANS_APPROVED/PROGRAMMING_PRACTICES quartet, GBS footer, registry entries in root README/CLAUDE/ci.yml).
- Python 3.12, `pyproject.toml` + `src/` layout + console script (the insurance-claims-case-generator packaging pattern) — Python is inherited from the substrate whose templates we must reuse; flagged to Alex as an explicit stack decision.
- merus-test-data-generator consumed via documented `sys.path` bridge (the repo's existing cross-package pattern); no file copying of its modules.
- Taxonomy keys must match `Adjudica-classifier` v2 (353 subtypes) exactly; umbrella subtypes emitted only when explicitly seeded.
- KB access is network-optional: generation must succeed fully offline; grounding enrichment degrades gracefully.
- Linear ticket ADJ-1818; conventional commits scoped `feat(wc-synthetic-caseload-engine)`.

## Goal

A new installable package whose CLI turns a caseload spec (defaults + distributions + per-case seeds) into complete synthetic CA WC attorney case files — with per-case seeds surfaced as reviewable YAML, fine-grained document type/count/format controls, lifecycles that reach lien resolution with lien agreements and reconsideration round-trips with post-recon litigation or settlement — validated by taxonomy round-trip and demonstrated by a generated example caseload committed as evidence.

## Criteria

### Package & CLI
- [ ] ISC-1: `packages/wc-synthetic-caseload-engine/pyproject.toml` exists with `src/` layout and console script `wc-caseload`
- [ ] ISC-2: `pip install -e .` (or `uv pip install -e .`) succeeds in a 3.12 venv
- [ ] ISC-3: `wc-caseload --help` lists `generate`, `seed`, `validate`, `taxonomy-check` commands
- [ ] ISC-4: `wc-caseload seed --template` writes an annotated example CaseSeed YAML covering every controllable field
- [ ] ISC-5: `wc-caseload generate --spec <yaml> --out <dir>` runs end-to-end without network access
- [ ] ISC-6: README.md documents seed schema, controls, lifecycle paths, and all CLI commands
- [ ] ISC-7: CLAUDE.md, CHANGELOG.md, PLANS_APPROVED.md, PROGRAMMING_PRACTICES.md, .planning/STATE.md exist per repo convention
- [ ] ISC-8: All package markdown files end with the GBS footer
- [ ] ISC-9: Root README.md package table + root CLAUDE.md registry include the new package
- [ ] ISC-10: `.github/workflows/ci.yml` has a paths-filter entry and quality-gate job for the package

### Seed schema (the surfaced "needed seed")
- [ ] ISC-11: Pydantic `CaseSeed` model exists with profile, injury, lifecycle, documents, output sections
- [ ] ISC-12: `CaseSeed.rng_seed` fully determines generation: two runs with the same seed produce identical manifests (hash-compared)
- [ ] ISC-13: Injury section supports `specific | cumulative_trauma | death` with 1–5 body parts each carrying ICD-10
- [ ] ISC-14: Lifecycle section supports `claim_response: accepted | delayed | denied`
- [ ] ISC-15: Lifecycle section supports `eval_type: qme | ame | none`
- [ ] ISC-16: Resolution supports `stipulations | c_and_r | findings_award | take_nothing | pending`
- [ ] ISC-17: `CaseloadSpec` model supports defaults + explicit `cases[]` + `auto: {count, distribution}` derivation
- [ ] ISC-18: Auto-derived cases write their resolved CaseSeed YAML to the output dir (the seed is always surfaced per case)
- [ ] ISC-19: Seed loader rejects unknown fields and invalid enum values with actionable errors (probe: bad seed → nonzero exit + named field)
- [ ] ISC-20: Every distribution preset from the KB PRD (§3) is available (`balanced`, `early_stage`, `settlement_heavy`, `complex_litigation` at minimum)
- [ ] ISC-21: Doctrine hooks field accepts the 12 KB PRD §6 landmark hooks and injects matching content flags into the document plan

### Fine-grained document controls
- [ ] ISC-22: `documents.include_only` whitelist restricts emission to named subtypes/types
- [ ] ISC-23: `documents.exclude` blacklist suppresses named subtypes/types
- [ ] ISC-24: Per-subtype count override (`{subtype, count}`) emits exactly that count
- [ ] ISC-25: Per-parent-type min/max override bounds emission for that type
- [ ] ISC-26: `documents.global_cap` bounds total documents per case
- [ ] ISC-27: `documents.format_mix` weights pdf/scanned_pdf/eml/docx assignment and is honored within tolerance (probe: 100-doc case, chi-square sanity)
- [ ] ISC-28: Controls compose: whitelist + override + cap resolve deterministically with documented precedence
- [ ] ISC-29: A control demanding a subtype invalid for the case's lifecycle emits it anyway with a WARN (explicit control wins, loudly)

### Lifecycle — core
- [ ] ISC-30: Lifecycle walk reaches every `target_stage` value (probe: one seed per stage, stage recorded in manifest)
- [ ] ISC-31: Denied-claim path emits `CLAIM_DENIAL_LETTER` and applicant-side response documents
- [ ] ISC-32: UR dispute path emits RFA → UR decision → (optional) IMR application/determination in date order
- [ ] ISC-33: Medical-legal path emits QME panel forms and QME/AME reports consistent with `eval_type`
- [ ] ISC-34: C&R resolution emits `COMPROMISE_AND_RELEASE_*` + `ORDER_APPROVING_SETTLEMENT`
- [ ] ISC-35: Stips resolution emits `STIPULATIONS_WITH_REQUEST_FOR_AWARD_*` + award order
- [ ] ISC-36: Trial resolution emits `MINUTES_OF_HEARING`/`FINDINGS_AND_AWARD` + `OPINION_ON_DECISION`
- [ ] ISC-37: Every emitted document's date is consistent with the lifecycle ordering (probe: manifest dates monotone within statutory windows)
- [ ] ISC-38: Document dates respect key statutory windows encoded in the substrate (90-day denial, QME timelines) — spot-probe two windows

### Lifecycle — liens through resolution (new capability)
- [ ] ISC-39: `liens.count` N > 0 creates N distinct lien claimant tracks with claimant-type from `liens.claimants`
- [ ] ISC-40: Each lien track emits `NOTICE_OF_LIEN_FILING` (or `LIEN_*` claim subtype matching claimant type)
- [ ] ISC-41: Lien conference path emits `NOTICE_OF_LIEN_CONFERENCE` and `PRETRIAL_CONFERENCE_STATEMENT_LIEN` when seeded
- [ ] ISC-42: Lien resolution `lien_resolution_agreement` emits `LIEN_RESOLUTION` ("Lien Resolution Agreement") — the explicitly requested artifact
- [ ] ISC-43: Lien resolution `lien_stipulation` emits `LIEN_STIPULATION_AGREEMENT`
- [ ] ISC-44: Lien resolutions `dismissal` and `order_on_lien` emit `LIEN_DISMISSAL` / `ORDER_ON_LIEN` respectively
- [ ] ISC-45: Lien documents post-date case-in-chief resolution when seeded as post-resolution lien litigation (the common real-world shape)
- [ ] ISC-46: EDD lien claimant type emits `LIEN_EDD_OVERPAYMENT`

### Lifecycle — reconsideration round-trip (new capability)
- [ ] ISC-47: `reconsideration.enabled` after a trial/award emits `PETITION_RECONSIDERATION_FILED`
- [ ] ISC-48: Recon track emits `PETITION_RECONSIDERATION_OPPOSITION` and (probabilistic, seedable) `PETITION_RECONSIDERATION_REPLY`
- [ ] ISC-49: Recon track emits `ORDER_ON_RECONSIDERATION` with outcome from seed (`denied | granted_remand | granted_reversed`)
- [ ] ISC-50: `granted_remand` + `post_recon: further_litigation` emits post-recon litigation documents (new DOR, hearing minutes, amended F&A)
- [ ] ISC-51: `granted_remand` + `post_recon: settled` emits a post-recon C&R or Stips with approval order dated after the recon order
- [ ] ISC-52: `denied` + `post_recon: affirmed_final` closes the case with no post-recon litigation documents
- [ ] ISC-53: Recon document dates honor the 20/25-day petition window and sequence (petition ≤ 25 days after F&A service; probe manifest dates)

### Rendering & realism
- [ ] ISC-54: Renderer bridge resolves every emitted subtype through the substrate template registry (0 unresolved subtypes on a full-range test caseload)
- [ ] ISC-55: All four output formats are produced when seeded (pdf, scanned_pdf, eml, docx) — probe file magic bytes
- [ ] ISC-56: Every generated PDF exceeds 500 bytes and opens (pymupdf page count ≥ 1)
- [ ] ISC-57: Scan-simulation seeding is derived from `rng_seed` + doc index, not `hash()`/wall clock (fixes the substrate's PYTHONHASHSEED leak within this engine's calls)
- [ ] ISC-58: Case-level narrative coherence: applicant name, ADJ number, DOI, employer, carrier identical across all documents in a case (probe: grep manifest fields against sampled rendered text)
- [ ] ISC-59: Party block includes applicant attorney + firm (applicant-side POV) on pleadings and correspondence

### Taxonomy & classifier integration
- [ ] ISC-60: Engine taxonomy import matches Adjudica-classifier at exactly 353 subtypes (probe: count + set-diff test = ∅)
- [ ] ISC-61: `wc-caseload taxonomy-check` compares against the classifier source tree and exits nonzero on drift
- [ ] ISC-62: `wc-caseload validate --out <dir>` verifies every manifest subtype is a valid classifier key with valid parent mapping
- [ ] ISC-63: Optional corpus filename mode emits `TC-###_###_<SUBTYPE>_<YYYY-MM-DD>.pdf` names accepted by the classifier's sampling regex
- [ ] ISC-64: Default filename mode is neutral (no subtype leak) for honest classification measurement

### Outputs & manifests
- [ ] ISC-65: Per-case output folder contains rendered documents + `seed.yaml` + `manifest.json`
- [ ] ISC-66: `manifest.json` carries per-document `{filename, subtype, type, format, documentDate, md5Checksum, fileSize, mimeType}`
- [ ] ISC-67: Manifest carries a `provenance` block with `zeroRealPii: true` and generator version + seed hash
- [ ] ISC-68: Caseload-level `caseload_manifest.json` aggregates cases with stage/resolution/lien/recon summary fields
- [ ] ISC-69: Example caseload spec in `examples/` regenerates deterministically (committed spec, verified hashes)

### Quality gates
- [ ] ISC-70: `pytest` suite passes with ≥ 25 tests covering seeds, controls, lifecycle paths, determinism
- [ ] ISC-71: `ruff check` passes clean on the package
- [ ] ISC-72: Anti: no module from merus-test-data-generator is copied into this package (probe: no duplicated file contents; bridge imports only)
- [ ] ISC-73: Anti: no real names/PHI patterns in generated output (Faker-sourced only; probe: generated names absent from CONTACTS/known-person list)
- [ ] ISC-74: Anti: generation never writes outside `--out` (probe: strace-free check via before/after tree diff of cwd)

## Test Strategy

| isc | type | check | threshold | tool |
|---|---|---|---|---|
| 1–10 | structural | files/commands exist and run | exact | Bash/Read |
| 11–21 | unit | Pydantic validation + seed resolution | exact | pytest |
| 12, 69 | determinism | manifest hash equality across runs | identical | Bash sha256 |
| 22–29 | unit+integration | control matrix cases | exact counts | pytest |
| 30–53 | integration | one seed per path; manifest assertions | subtype presence + date order | pytest + jq |
| 54–59 | integration | full-range render + sampled text grep | 0 unresolved; coherent fields | pytest/Bash |
| 60–64 | cross-repo | set-diff vs classifier source | ∅ drift | pytest + Bash |
| 65–69 | integration | manifest schema validation | schema-valid | pytest |
| 70–71 | gate | pytest, ruff | pass | Bash |
| 72–74 | anti | negative probes | zero hits | Bash |

## Features

| name | description | satisfies | depends_on | parallelizable |
|---|---|---|---|---|
| package-scaffold | pyproject, src layout, CLI skeleton, doc quartet | 1–10 | — | yes |
| seed-schema | CaseSeed/CaseloadSpec models, loader, templater, distributions | 11–21 | package-scaffold | yes |
| doc-controls | include/exclude/override/cap/format-mix resolver | 22–29 | seed-schema | no |
| lifecycle-bridge | substrate DAG wrapper + stage mapping | 30–38 | seed-schema | yes |
| lien-machine | lien claimant tracks through resolution | 39–46 | lifecycle-bridge | no |
| recon-machine | recon round-trip + post-recon paths | 47–53 | lifecycle-bridge | no |
| renderer-bridge | sys.path bridge, registry resolution, deterministic scan seed | 54–59 | doc-controls | yes |
| taxonomy-sync | 353-subtype import + drift check + validate cmd | 60–64 | package-scaffold | yes |
| manifests | per-case + caseload manifests, provenance | 65–69 | renderer-bridge | no |
| quality | tests, ruff, example caseload | 70–74 | all | no |

## Decisions

- 2026-07-27 15:05 — New package (`wc-synthetic-caseload-engine`) rather than updating merus-test-data-generator in place, per Alex's mid-session direction "This becomes a new tool in that same repo."
- 2026-07-27 15:05 — Python 3.12 despite the TypeScript-first PAI rule: the reusable substrate (25 ReportLab template classes, content pools, lifecycle DAG, scan simulator) is Python; a TS rebuild would forfeit ~90% reuse. Surfaced to Alex as an explicit stack decision needing his ack.
- 2026-07-27 15:05 — Seed schema designed as a superset of the KB PRD `CaseParameters` (17 fields, `docs/PRD-WC-ATTORNEY-MOCK-CASELOAD.md`) so the 47-case mock caseload becomes directly expressible.
- 2026-07-27 15:05 — ISC count 74 < E4 soft floor 128 (show-your-math): criteria are already single-probe atomic; further splitting would enumerate per-subtype render checks (353 rows) adding count without information. The full-range render test (ISC-54) covers that surface as one probe.
- 2026-07-27 15:05 — Ticket created before branch per standing feedback memory; initially filed as ADJ-1818 (AdjudicaAI) reasoning from consumers.
- 2026-07-27 15:40 — Alex: "This is not an ADJ ticket." Moved to AJC (repo precedent: gbs-tools-and-resources packages ticket under AJC, e.g. AJC-20..24) → now **AJC-34**; branch renamed `ajc-34-wc-synthetic-caseload-engine`.
- 2026-07-27 15:05 — Branch based on `docs/glass-box-code-reviewer-agent` HEAD (dirty unrelated tree); PR will be re-based onto origin/main via clean cherry-pick at completion.
- 2026-07-27 15:05 — Skipped reading `Examples/canonical-isa.md` (Scaffold step 2) — twelve-section contract already loaded from skill doc this session; time-budget trade documented.

## Changelog

- (pending first LEARN entry)

## Verification

- (populated at VERIFY)
