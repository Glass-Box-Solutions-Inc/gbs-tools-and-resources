---
task: "Seed-driven WC synthetic attorney case-file engine"
project: wc-synthetic-caseload-engine
slug: 20260727-143600_wc-synthetic-caseload-engine
effort: E4
effort_source: classifier
phase: complete
progress: 83/84
mode: interactive
started: 2026-07-27T14:36:00-07:00
updated: 2026-07-28T00:10:00-07:00
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
- Non-California jurisdictions. (Defense-POV caseloads were originally out of scope; Alex pulled them IN scope 2026-07-27 evening — see ISC-75..84.)
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
- Linear ticket AJC-34 (moved from ADJ-1818, see Decisions); conventional commits scoped `feat(wc-synthetic-caseload-engine)`.

## Goal

A new installable package whose CLI turns a caseload spec (defaults + distributions + per-case seeds) into complete synthetic CA WC attorney case files — with per-case seeds surfaced as reviewable YAML, fine-grained document type/count/format controls, lifecycles that reach lien resolution with lien agreements and reconsideration round-trips with post-recon litigation or settlement — validated by taxonomy round-trip and demonstrated by a generated example caseload committed as evidence.

## Criteria

### Package & CLI
- [x] ISC-1: `packages/wc-synthetic-caseload-engine/pyproject.toml` exists with `src/` layout and console script `wc-caseload`
- [x] ISC-2: `pip install -e .` (or `uv pip install -e .`) succeeds in a 3.12 venv
- [x] ISC-3: `wc-caseload --help` lists `generate`, `seed`, `validate`, `taxonomy-check` commands
- [x] ISC-4: `wc-caseload seed --template` writes an annotated example CaseSeed YAML covering every controllable field
- [x] ISC-5: `wc-caseload generate --spec <yaml> --out <dir>` runs end-to-end without network access
- [x] ISC-6: README.md documents seed schema, controls, lifecycle paths, and all CLI commands
- [x] ISC-7: CLAUDE.md, CHANGELOG.md, PLANS_APPROVED.md, PROGRAMMING_PRACTICES.md, .planning/STATE.md exist per repo convention
- [x] ISC-8: All package markdown files end with the GBS footer
- [x] ISC-9: Root README.md package table + root CLAUDE.md registry include the new package
- [x] ISC-10: `.github/workflows/ci.yml` has a paths-filter entry and quality-gate job for the package

### Seed schema (the surfaced "needed seed")
- [x] ISC-11: Pydantic `CaseSeed` model exists with profile, injury, lifecycle, documents, output sections
- [x] ISC-12: `CaseSeed.rng_seed` fully determines generation: two runs with the same seed produce identical manifests (hash-compared), across processes, across timezones, and **across any inherited `PYTHONHASHSEED`** — only `"0"` is accepted as stable, so `1`, `2` and `random` all re-exec instead of being trusted as deliberate, and **no pre-set environment variable can waive that check**: the re-exec sentinel is a bounded hop counter, never a certificate of stability (subprocess regressions compare whole trees under `=1` vs `=2`, both with and without `WC_CASELOAD_HASH_PINNED` pre-set)
- [x] ISC-13: Injury section supports `specific | cumulative_trauma | death` with 1–5 body parts each carrying ICD-10
- [x] ISC-14: Lifecycle section supports `claim_response: accepted | delayed | denied`
- [x] ISC-15: Lifecycle section supports `eval_type: qme | ame | none`
- [x] ISC-16: Resolution supports `stipulations | c_and_r | findings_award | take_nothing | pending`
- [x] ISC-17: `CaseloadSpec` model supports defaults + explicit `cases[]` + `auto: {count, distribution}` derivation
- [x] ISC-18: Auto-derived cases write their resolved CaseSeed YAML to the output dir (the seed is always surfaced per case)
- [x] ISC-19: Seed loader rejects unknown fields and invalid enum values with actionable errors (probe: bad seed → nonzero exit + named field)
- [x] ISC-20: Every distribution preset from the KB PRD (§3) is available (`balanced`, `early_stage`, `settlement_heavy`, `complex_litigation` at minimum)
- [DEFERRED-VERIFY] ISC-21: Doctrine hooks field accepts the 12 KB PRD §6 landmark hooks and injects matching content flags into the document plan

### Fine-grained document controls
- [x] ISC-22: `documents.include_only` whitelist restricts emission to named subtypes/types
- [x] ISC-23: `documents.exclude` blacklist suppresses named subtypes/types
- [x] ISC-24: Per-subtype count override (`{subtype, count}`) emits exactly that count
- [x] ISC-25: Per-parent-type min/max override bounds emission for that type
- [x] ISC-26: `documents.global_cap` bounds total documents per case
- [x] ISC-27: `documents.format_mix` weights pdf/scanned_pdf/eml/docx assignment and is honored within tolerance (probe: 100-doc case, chi-square sanity)
- [x] ISC-28: Controls compose: whitelist + override + cap resolve deterministically with documented precedence
- [x] ISC-29: A control demanding a subtype invalid for the case's lifecycle emits it anyway with a WARN (explicit control wins, loudly)

### Lifecycle — core
- [x] ISC-30: Lifecycle walk reaches every `target_stage` value (probe: one seed per stage, stage recorded in manifest)
- [x] ISC-31: Denied-claim path emits `CLAIM_DENIAL_LETTER` and applicant-side response documents
- [x] ISC-32: UR dispute path emits RFA → UR decision → written denial/authorization → (optional) IMR application/determination in **strictly increasing** date order, including on a seed whose injury sits exactly on the `ur_dispute` / `imr` runway floor (the chain is fitted, not clamped)
- [x] ISC-33: Medical-legal path emits QME panel forms and QME/AME reports consistent with `eval_type`, with panel request → panel issuance → report in **strictly increasing** date order, including on a seed sitting exactly on the 240-day eval runway floor
- [x] ISC-34: C&R resolution emits `COMPROMISE_AND_RELEASE_*` + `ORDER_APPROVING_SETTLEMENT`
- [x] ISC-35: Stips resolution emits `STIPULATIONS_WITH_REQUEST_FOR_AWARD_*` + award order
- [x] ISC-36: Trial resolution emits `MINUTES_OF_HEARING`/`FINDINGS_AND_AWARD` + `OPINION_ON_DECISION`
- [x] ISC-37: Every emitted document's date is consistent with the lifecycle ordering (probe: manifest dates monotone within statutory windows; **every sequenced chain — denial response, lien tracks, recon round trip — is fitted via `fit_track` rather than clamped per document**, and each branch that consumes calendar has a runway floor in `seeds.runway_demands()` so a seed too short for its own chain is rejected at load instead of collapsing onto the anchor)
- [x] ISC-38: Document dates respect key statutory windows encoded in the substrate (90-day denial, QME timelines) — spot-probe two windows

### Lifecycle — liens through resolution (new capability)
- [x] ISC-39: `liens.count` N > 0 creates N distinct lien claimant tracks with claimant-type from `liens.claimants`
- [x] ISC-40: Each lien track emits `NOTICE_OF_LIEN_FILING` (or `LIEN_*` claim subtype matching claimant type)
- [x] ISC-41: Lien conference path emits `NOTICE_OF_LIEN_CONFERENCE` and `PRETRIAL_CONFERENCE_STATEMENT_LIEN` when seeded
- [x] ISC-42: Lien resolution `lien_resolution_agreement` emits `LIEN_RESOLUTION` ("Lien Resolution Agreement") — the explicitly requested artifact
- [x] ISC-43: Lien resolution `lien_stipulation` emits `LIEN_STIPULATION_AGREEMENT`
- [x] ISC-44: Lien resolutions `dismissal` and `order_on_lien` emit `LIEN_DISMISSAL` / `ORDER_ON_LIEN` respectively
- [x] ISC-45: Lien documents post-date case-in-chief resolution when seeded as post-resolution lien litigation (the common real-world shape)
- [x] ISC-46: EDD lien claimant type emits `LIEN_EDD_OVERPAYMENT`

### Lifecycle — reconsideration round-trip (new capability)
- [x] ISC-47: `reconsideration.enabled` after a trial/award emits `PETITION_RECONSIDERATION_FILED`
- [x] ISC-48: Recon track emits `PETITION_RECONSIDERATION_OPPOSITION` and (probabilistic, seedable) `PETITION_RECONSIDERATION_REPLY`, **strictly ordered petition < opposition < reply < order** — the chain is built in legal sequence and the dates fitted to it, never sorted into whatever order independent draws produced (property test over 50 seeds)
- [x] ISC-49: Recon track emits `ORDER_ON_RECONSIDERATION` with outcome from seed (`denied | granted_remand | granted_reversed`)
- [x] ISC-50: `granted_remand` + `post_recon: further_litigation` emits post-recon litigation documents (new DOR, hearing minutes, amended F&A)
- [x] ISC-51: `granted_remand` + `post_recon: settled` emits a post-recon C&R or Stips with approval order dated after the recon order
- [x] ISC-52: `denied` + `post_recon: affirmed_final` closes the case with no post-recon litigation documents
- [x] ISC-53: Recon document dates honor the 20/25-day petition window and sequence (petition ≤ 25 days after F&A service; probe manifest dates). The LC 5909 sixty-day order window is honoured **except** where the briefing schedule outruns it: the ruling is floored at the day after the last brief, because an order a few days late is an ordinary file and an order predating the briefing is not one at all (counted, ≤10 in 50 seeds)

### Rendering & realism
- [x] ISC-54: Every canonical subtype renders without fallback — all-353 forced-render test drives each subtype through this engine's dispatch path and asserts zero `GenericDocumentTemplate` resolutions, zero `RenderResult.fallback`, and non-trivial output (>500 B, PDF parses with ≥1 page)
- [x] ISC-55: All four output formats are produced when seeded (pdf, scanned_pdf, eml, docx) — probe file magic bytes
- [x] ISC-56: Every generated PDF exceeds 500 bytes and opens (pymupdf page count ≥ 1)
- [x] ISC-57: Scan-simulation seeding is derived from `rng_seed` + doc index, not `hash()`/wall clock (fixes the substrate's PYTHONHASHSEED leak within this engine's calls)
- [x] ISC-58: Case-level narrative coherence: applicant name, ADJ number, DOI, employer, carrier identical across all documents in a case (probe: grep manifest fields against sampled rendered text)
- [x] ISC-59: Party block includes applicant attorney + firm (applicant-side POV) on pleadings and correspondence

### Taxonomy & classifier integration
- [x] ISC-60: Engine taxonomy import matches Adjudica-classifier at exactly 353 subtypes (probe: count + set-diff test = ∅)
- [x] ISC-61: `wc-caseload taxonomy-check` compares against the classifier source tree and exits nonzero on drift
- [x] ISC-62: `wc-caseload validate --out <dir>` verifies every manifest subtype is a valid classifier key with valid parent mapping, and fails on any `fallback: true` document unless `--allow-fallback` is passed
- [x] ISC-63: Optional corpus filename mode emits `TC-###_###_<SUBTYPE>_<YYYY-MM-DD>.pdf` names accepted by the classifier's sampling regex
- [x] ISC-64: Default filename mode is neutral (no subtype leak) for honest classification measurement

### Outputs & manifests
- [x] ISC-65: Per-case output folder contains rendered documents + `seed.yaml` + `manifest.json`
- [x] ISC-66: `manifest.json` carries per-document `{filename, subtype, type, format, documentDate, md5Checksum, fileSize, mimeType, template, fallback}`
- [x] ISC-67: Manifest carries a `provenance` block with a computed `zeroRealPii`, its `castProvenance` derivation, and generator version + seed hash
- [x] ISC-68: Caseload-level `caseload_manifest.json` aggregates cases with stage/resolution/lien/recon summary fields
- [x] ISC-69: Example caseload spec in `examples/` regenerates deterministically (committed spec, verified hashes)

### Quality gates
- [x] ISC-70: `pytest` suite passes with ≥ 25 tests covering seeds, controls, lifecycle paths, determinism
- [x] ISC-71: `ruff check` passes clean on the package
- [x] ISC-72: Anti: no module from merus-test-data-generator is copied into this package (probe: no duplicated file contents; bridge imports only)
- [x] ISC-73: Anti: no real names/PHI patterns in generated output (probe: **two** sweeps — the curated `src/wc_caseload_engine/data/name_denylist.txt` against extracted text of every text-bearing demo document **and** every manifest cast field, plus a dynamic sweep of **all four** substrate organization pools read live via `name_denylist.substrate_organization_pools()` (`INSURANCE_CARRIERS`, `DEFENSE_FIRMS`, `ALL_EMPLOYERS`, `MEDICAL_FACILITIES`) against manifests, document text and 200 generated casts; `zeroRealPii` computed from `CaseCast.provenance`, not asserted; seed-declared names kept but warned via `cast.seed_name_on_denylist`)
- [x] ISC-74: Anti: generation never writes outside `--out` (probe: sentinel `HOME`/`TMPDIR`/XDG tree snapshotted before and after a subprocess generate — created, modified and removed files all fail; **plus** the package `src/` and substrate source trees snapshotted for stray `__pycache__` — zero in the substrate, and only `__init__`'s own interpreter-written bytecode in the package, named explicitly rather than exempted by directory)

### Perspective (applicant vs defense files — added 2026-07-27 evening)
- [x] ISC-75: `CaseSeed.perspective` accepts `applicant | defense`, defaults to `applicant`; all pre-existing seeds load unchanged
- [x] ISC-76: Defense perspective makes the defense firm the file owner in the cast and `perspective` is recorded in the case manifest
- [x] ISC-77: Defense cases emit DEFENSE_TRIAL_BRIEF / DEFENSE_MSC_STATEMENT / DEFENSE_CASE_ANALYSIS as the privileged work product in place of applicant-side memos
- [x] ISC-78: Client correspondence targets the worker on applicant side and the employer/carrier contact on defense side (author/recipient roles in rendered docs + manifest)
- [x] ISC-79: Defense files emit CLAIMS_ADMINISTRATION and INVESTIGATION subtypes at materially higher frequency than mirrored applicant files (comparative probe)
- [x] ISC-80: Applicant-only material (client intake, advocacy letters to treaters, applicant client status letters) is absent from defense files by default, present only via explicit override
- [x] ISC-81: Demo caseload gains a defense-perspective case; all gates stay green (pytest, ruff, double-run + TZ determinism, validate)
- [x] ISC-82: Anti: flipping perspective never changes case facts — mirrored seeds (same rng_seed/injury/lifecycle) produce identical cast, ADJ number, and event dates (probe: manifest field diff)
- [x] ISC-83: README + user guide document perspective semantics and the defense-side docx letterhead limitation
- [x] ISC-84: Tests cover default, swap logic, applicant-only absence, and the mirrored-facts invariant

## Test Strategy

| isc | type | check | threshold | tool |
|---|---|---|---|---|
| 1–10 | structural | files/commands exist and run | exact | Bash/Read |
| 11–21 | unit | Pydantic validation + seed resolution | exact | pytest |
| 12, 69 | determinism | manifest hash equality across runs | identical | Bash sha256 |
| 22–29 | unit+integration | control matrix cases | exact counts | pytest |
| 30–53 | integration | one seed per path; manifest assertions | subtype presence + date order | pytest + jq |
| 54–59 | integration | all-353 forced render + full-case text sweep | 0 fallbacks; 0 cross-case intrusions | pytest |
| 60–64 | cross-repo | set-diff vs classifier source | ∅ drift | pytest + Bash |
| 65–69 | integration | manifest schema validation | schema-valid | pytest |
| 70–71 | gate | pytest, ruff | pass | Bash |
| 72–74 | anti | denylist sweep over output; sentinel-tree diff | zero hits; zero files outside `--out` | pytest |

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
| perspective | applicant vs defense file POV: cast owner, work-product swap, emission profiles | 75–84 | lifecycle-bridge, renderer-bridge | no |

## Decisions

- 2026-07-27 15:05 — New package (`wc-synthetic-caseload-engine`) rather than updating merus-test-data-generator in place, per Alex's mid-session direction "This becomes a new tool in that same repo."
- 2026-07-27 15:05 — Python 3.12 despite the TypeScript-first PAI rule: the reusable substrate (25 ReportLab template classes, content pools, lifecycle DAG, scan simulator) is Python; a TS rebuild would forfeit ~90% reuse. Surfaced to Alex as an explicit stack decision needing his ack.
- 2026-07-27 15:05 — Seed schema designed as a superset of the KB PRD `CaseParameters` (17 fields, `docs/PRD-WC-ATTORNEY-MOCK-CASELOAD.md`) so the 47-case mock caseload becomes directly expressible.
- 2026-07-27 15:05 — ISC count 74 < E4 soft floor 128 (show-your-math): criteria are already single-probe atomic; further splitting would enumerate per-subtype render checks (353 rows) adding count without information. The full-range render test (ISC-54) covers that surface as one probe.
- 2026-07-27 15:05 — Ticket created before branch per standing feedback memory; initially filed as ADJ-1818 (AdjudicaAI) reasoning from consumers.
- 2026-07-27 15:40 — Alex: "This is not an ADJ ticket." Moved to AJC (repo precedent: gbs-tools-and-resources packages ticket under AJC, e.g. AJC-20..24) → now **AJC-34**; branch renamed `ajc-34-wc-synthetic-caseload-engine`.
- 2026-07-27 15:05 — Branch based on `docs/glass-box-code-reviewer-agent` HEAD (dirty unrelated tree); PR will be re-based onto origin/main via clean cherry-pick at completion.
- 2026-07-27 15:05 — Skipped reading `Examples/canonical-isa.md` (Scaffold step 2) — twelve-section contract already loaded from skill doc this session; time-budget trade documented.
- 2026-07-27 17:10 — Phase B deviations accepted: `planner.py` + `determinism.py` as dedicated owners; `SINGLETON_SUBTYPES` (one denial letter / one C&R per case, liens/recon exempt); substrate lien/recon emissions suppressed so seed-owned machines are sole source; PYTHONHASHSEED re-exec chosen over per-site sorting (fixes the class).
- 2026-07-27 17:25 — Advisor (Rule 2) verdict: 4 blockers → accepted: substrate-SHA pin in manifest, subtype-coverage stats, clock-shifted determinism probe, synthetic-data marker (metadata-level; visible watermark needs substrate → surfaced). Letterhead provenance (substrate hardcodes "Martinez & Associates, APC") → surfaced to Alex, not fixable from this package.
- 2026-07-27 17:30 — Clock-shift probe (TZ=Australia/Sydney) CONFIRMED advisor: ~60/289 files drift (EML Date local offsets; PDF/docx timestamp normalization TZ-dependent). Same-machine determinism real; cross-TZ broken. Fix: pin all timestamp derivations to fixed zone. Advisor and empirics agree — no Rule 3 conflict.
- 2026-07-27 19:05 — refined: Alex: "I want this engine to be able to produce Applicant sided cases or defense sided cases." Defense POV moved from Out of Scope to ISC-75..84. Design: `perspective` seed field flips file ownership, work-product authorship, and emission profiles — never the case facts (ISC-82 anti-criterion guards this).
- 2026-07-27 20:10 — Perspective builder authored parallel ISC-75..84 wording in its worktree (it branched before master's criteria were committed). Master numbering wins per ID-stability; its criteria map 1:1 onto master's and all evidence carries over. Its `floor` addition to PERSPECTIVE_PROFILES (weights can't multiply zero-proposal subtypes like INVESTIGATION into existence) accepted as a design improvement; cap-vs-floor bug found and fixed by its own demo gate.
- 2026-07-27 17:35 — Forge interim: re-exec safe (os.execve, double loop-guard; `-m` form not preserved — noted), manifest md5s hash final bytes (normalize-then-hash order verified), `py.typed` declared but missing.
- 2026-07-27 18:20 — Runway validation placed at the **seed boundary** (fail loud), not as a lifecycle repair. The seed is the interface, so an impossible story is rejected where it is written; the lifecycle then only has to enforce invariants it can always satisfy. Floors keyed on three independent drivers (stage, real resolution, post-resolution litigation) because a seed answers to all three at once.
- 2026-07-27 18:20 — `CaseTimeline` validates its own ordering in `__post_init__` and raises `TimelineInvariantError` rather than asserting — asserts vanish under `python -O`, and a silently inverted spine is the exact defect being fixed.
- 2026-07-27 18:25 — Track dates are now built **unclamped** and fitted once per chain (`fit_track`), instead of clamped per document. Per-document clamping is what collapsed a five-document lien track onto one date; a two-pass isotonic fit keeps the order and only compresses the spacing.
- 2026-07-27 18:25 — Post-resolution lien tracks **extend past** the anchor rather than compress. The anchor is an artifact of determinism, not a fact about the file, and legible ordering is worth more than a document dated after "today".
- 2026-07-27 18:40 — Substrate clock pinned at runtime (`pin_substrate_clock`), a deliberate exception to the no-patching rule. Distinguished from the letterhead case (left unpatched): the anchor is a process-wide constant, not per-case mutable state. The alternative was abandoning the cross-machine determinism promise.
- 2026-07-27 18:50 — Faker deliberately **not** patched. Rebinding `faker.providers.date_time.datetime`/`dtdate` breaks the `isinstance` checks in Faker's own date parser (`ParseError: Invalid format for date`). Since `date_of_birth` is the substrate's only clock-relative Faker call, the field is owned in `case_context._date_of_birth` and derived from `seed.rng("dob")` instead.
- 2026-07-27 18:55 — Empirics beat the fix plan: the CLI-level TZ gate reported 0 drift while an in-process two-zone probe still found 3 files drifting (a DOB one day apart). The in-process regression test was kept as the sharper instrument; the CLI gate alone would have shipped the Faker leak.
- 2026-07-27 19:05 — `substrate_git_sha()` scoped to the substrate **path** (`git log -1 -- .`) rather than the briefed bare `rev-parse HEAD`. In a monorepo bare HEAD moves on every unrelated commit, so the pin would warn constantly — an alarm that always fires is an alarm nobody reads. Deviation surfaced in the handoff.
- 2026-07-27 late — **Cato remediation round.** One line per change:
  - ISC-54 rewritten to its honest scope and evidenced by `test_render_coverage.py`, which drives all 353 canonical subtypes through `render_document` directly (~25 s, kept in the default suite) rather than inferring coverage from a caseload.
  - The audit's predicted exceptions list came back with exactly three entries — `PETITION_FOR_PENALTIES`, `NOTICE_OF_PENALTY_5814`, `NOTICE_OF_PENALTY_5814_5` — and they were **fixed rather than recorded**: they are the engine's own `OVERLAY_SUBTYPES`, invented here to reach classifier parity, so `renderer.OVERLAY_TEMPLATES` now owns their dispatch (`ApplicationForAdjudication` for the petition, mirroring the substrate's own `PETITION_FOR_PENALTIES_LC_5814` entry; `CourtNotice` variants for the two notices). `KNOWN_UNRENDERABLE_SUBTYPES` ships empty with an assertion that it never grows.
  - `registry.get_template_for_subtype` returns `GenericDocumentTemplate` for unknown keys, so "no template" and "generic on purpose" were the same value; `RenderResult.template` and `.fallback` now separate them, and both reach every manifest document entry.
  - `validate --out` fails on any `fallback: true` and gained `--allow-fallback`; the report line `fallbacks : N` is always printed. The caseload manifest gained `distinctTemplates` and `fallbackCount`.
  - ISC-74 upgraded from a `git status` observation to a sentinel-tree diff: `HOME`, `TMPDIR`, `TMP`, `TEMP` and the three XDG dirs are redirected into one monitored sandbox, seeded with sentinel files, and diffed on size+mtime after a subprocess generate. Zero creations, modifications or deletions — no font-cache or temp-spool leak.
  - ISC-73 upgraded from an assertion about the generator to a sweep of its output: `tests/data/name_denylist.txt` (real CA WC carriers and defense firms, with `Martinez & Associates` explicitly ALLOWed as the substrate letterhead) is checked against extracted text from all 256 text-bearing demo documents and against every manifest cast field, with a positive control proving the probe fires.
  - **Real-entity leak found and closed at source.** The substrate's `data/wc_constants.py` pools `INSURANCE_CARRIERS` and `DEFENSE_FIRMS` are *actual* companies (State Fund, Zenith, Bradford & Barthel, Laughlin Falbo…), drawn whenever a seed does not name its own. `case_context._replace_real_organizations` substitutes coined names on that path and rebuilds the derived adjuster/defense emails, which carried the old domain even when the name was overridden. The demo's seven real carriers and two real defense firms were renamed to coined equivalents. Substrate untouched.
  - `zeroRealPii` is now computed from `CaseCast.provenance` (`faker` | `seed` | `engine`) instead of being a hardcoded `true`, with the derivation published as `provenance.castProvenance` and a test that constructs an unvouched cast to prove the flag can be false.
  - ISC-58 upgraded from a 3-document sample to a full-case sweep with a cross-contamination guard against the other six casts. **Scope correction found by the sweep:** an ADJ number does not exist before the Application for Adjudication is filed, so 10 of the 11 documents lacking it are correctly pre-filing. The assertion is keyed to the filing date; `MEDICAL_CHRONOLOGY_TIMELINE` is the single documented uncaptioned exception.
  - ISC-27 evidenced by a chi-square test over a 120-document case (α = 0.001, computed inline — SciPy is not worth a dependency for six lines), with a positive control that rejects a skewed draw, plus the same statistic applied to the shipped demo.
  - ISC-12 gained entrypoint parity: `python -m wc_caseload_engine`, `-m wc_caseload_engine.cli` and the `wc-caseload` console script produce byte-identical trees, closing Forge's note that the `-m` form is not preserved across the `PYTHONHASHSEED` re-exec.
  - Rider: `perspective` added to both shipped seed templates (`seed --template`, `--kind caseload`).
- 2026-07-27 19:20 — Harness deviation: the agent was fenced into a git worktree that predates this package, so the briefed "work in the main checkout" was impossible (Edit and git both refused shared-checkout paths). Worktree fast-forwarded to the `ajc-34` tip, the four uncommitted review fixes carried across by content, and the result committed as a cleanly cherry-pickable delta.
- 2026-07-27 night — **GPT release-review FAIL round.** One line per fix:
  - **Org-pool sweep (BLOCKER).** The substitution covered carriers and defense firms; the substrate has *four* organization pools, and `ALL_EMPLOYERS` (Safeway, Costco, Kaiser Permanente, UPS, City of Los Angeles) plus `MEDICAL_FACILITIES` were flowing straight through — a real employer named as defendant in every caption under `zeroRealPii: true`. All four are now coined with seed-stable names; the employer suffix is chosen by the substrate's own industry key so the (industry, company, position) trio stays coherent. Root bookkeeping error fixed too: `employer` was classified `faker` when it was a *pool* draw, so the flag vouched for a channel it had never checked.
  - **Denylist made one list, and the pool audit made dynamic.** `name_denylist.txt` moved from `tests/data/` into package data — the engine reads it (to warn) and the probes read it (to sweep), and two copies of a safety list is one copy plus a liability. The structural guarantee is `substrate_organization_pools()`, which reads `data/wc_constants.py` **live**, so a pool that grows upstream is swept without anyone editing a fixture; a renamed constant raises rather than silently sweeping nothing.
  - **Seed-declared names: kept, warned, never overridden.** The seed is the contract, so a name its author wrote stands; it is checked against the denylist and logs `cast.seed_name_on_denylist`, and `castProvenance` already distinguishes `seed` from `engine` so a reviewer can see whose choice it was. Both directions tested — the warning fires on `Costco Wholesale` and stays silent on a coined name.
  - **Branch runway floors (BLOCKER).** Runway was validated against stage and resolution only, so a 30-day `intake` + `denied` seed passed and then stacked its denial letter, Application and DOR all on 2026-01-01. `runway_demands()` now enumerates every demand and the error names the binding one. Numbers derived from the encoded chains, not estimated: denied 90, ur_dispute 65, imr 120, **eval 240**. The review proposed 120 for the evaluation; `_guaranteed_eval_documents` draws the panel at injury+180 and the report at +60, so 120 cannot hold the sequence — the code was believed over the estimate, and `_stage_runway_floor` + `_STAGE_AGE_DAYS` were widened to match so auto-derivation stays compliant by construction.
  - **Denial chain fitted, not clamped (BLOCKER, second half).** Denial → Application → DOR is a *sequence* — each document exists because of the one before it — so it now goes through `fit_track` like the lien and recon chains. Per-date clamping is only sound for the parallel core track; applied to a chain it pins every overrun onto the horizon, which is precisely the reproduction.
  - **PYTHONHASHSEED guard (BLOCKER).** The guard deferred to any pre-set value, reading `PYTHONHASHSEED=random` — the default spelled out longhand — as a deliberate determinism choice, and treating `1` and `2` as equivalent when they are two different salts producing two different caseloads. Only `"0"` is accepted now; everything else re-execs. `WC_CASELOAD_NO_REEXEC` still opts out, now with a warning naming the consequence, because a silent opt-out is one nobody knows they took.
  - **Recon briefing order (MAJOR).** The order was drawn independently of the briefing schedule and the chain was then sorted by `(date, subtype)`, so the sort faithfully recorded a Board ruling filed before the reply it had supposedly considered. The chain is now built in *legal* order and the dates fitted to the sequence, never the reverse; `_order_date` floors the ruling at the day after the last brief. Trade accepted and measured: constraining the order can push it past the LC 5909 sixty-day window, so the test counts how often (≤10 in 50) — a ruling a few days late is an ordinary file, one that predates the briefing is not a file at all.
  - **Bytecode containment (MAJOR).** Importing the substrate scattered 13 `__pycache__` directories through a read-only dependency's source tree — writes outside `--out`, from a tool whose contract is that there are none. `sys.dont_write_bytecode` is set on the first executable line of `__init__.py` (earliest reachable point; `cli.py`/`__main__.py` set it too for direct import paths) and `PYTHONDONTWRITEBYTECODE=1` rides through the re-exec. Substrate tree: zero. Package tree: one file, `__init__`'s own bytecode, which CPython writes while compiling the file that would set the flag. Named explicitly in the anti-probe rather than exempting a directory, because it is an interpreter floor, not a gap.
  - **Post-resolution liens: documented, not changed (DESIGN).** Tracks extending past the case-in-chief resolution under `post_resolution_litigation: true` is intended — real lien practice outlives the case, and the anchor is an artifact of determinism. The boundary is now asserted, not just described: without the flag the horizon still binds, so the extension cannot leak into ordinary cases.
  - **Caption exemption made structural (found by this round).** The recon fix shifted format assignment and exposed a latent gap: `QME_PANEL_REQUEST_FORM_105` renders through the substrate's `ClientIntake` letter template, which prints no case caption for any of the ~60 subtypes routed to it. Exempting by *template* rather than by subtype names the cause instead of enumerating symptoms, and a companion test caps the exemption at a third of the file so it can never grow large enough to hide a regression.
- 2026-07-28 — second release-review round: eval/UR chains through fit_track, sentinel requires hashseed=0, industry-first coining. The first round fixed each defect where it was *found*; this round fixed the two it had left one level up. (a) The branch runway floors reject a seed too short for its chain but say nothing about a seed sitting **on** the floor, and the eval and UR/IMR chains were still clamped per date — so boundary-valid seeds collapsed panel request/order/report and RFA/decision/denial onto 2026-01-01 (84 of 90 boundary seeds). Both now build unclamped and go through `fit_track` in legal order, the same treatment the denial, lien and recon chains already had; `MEDICAL_TREATMENT_DENIAL_UR` also stopped sharing the UR decision's date outright (LC 4610(g)(3)(A) gives it two working days). (b) `ensure_stable_hashing` read the re-exec sentinel **before** `PYTHONHASHSEED`, so pre-setting `WC_CASELOAD_HASH_PINNED` reinstated the exact bypass the value check had just closed. Order was the whole fix: the seed is checked first and the sentinel is demoted from certificate to hop counter, capped at `MAX_REEXEC_HOPS=2` with a hard error past it rather than an exec loop. (c) `profile.employer.industry` was applied *after* the coining sweep and the position draw, so a seed naming an industry got a company suffix and a job title from the substrate's pre-override industry — `rng_seed=2` + `healthcare` produced a construction name, a healthcare department and a construction title. The industry is now applied first and the position re-drawn from the seeded industry's own titles, read live from `EMPLOYER_TEMPLATES`; a seeded `applicant.occupation` still outranks it.

## Changelog

- **conjectured:** same-machine double-run md5 comparison proves generation determinism (Phase B gate design).
  **refuted by:** advisor-demanded clock-shift probe — TZ=Australia/Sydney drifted 55-60 of 289 files (EML Date offsets, PDF/docx timestamp normalization, substrate date.today() content, Faker clock-relative date_of_birth); the CLI-level gate also masked an in-process leak the two-zone test caught.
  **learned:** determinism gates must vary the environment axes the guarantee spans — process, hash seed, timezone, entrypoint — not just repeat the run; a passing gate that shares the leak's precondition proves nothing about the class.
  **criterion now:** ISC-12 evidence requires cross-process AND cross-timezone md5 identity (test_timezone_determinism.py + CI-runnable probes), and every new output format must add a container-timestamp normalization with its own test.
- **conjectured:** a "full-range render test" (ISC-54 as one probe) covers the per-subtype render surface, justifying the ISC-floor waiver.
  **refuted by:** Cato audit — the probe ran over the 78 subtypes the demo emits (22.1% of 353); 275 subtypes have never been rendered; no automated no-fallback assertion exists.
  **learned:** a scope-limiting qualifier ("full-range" = full range of the demo) reads as total coverage to both executor and same-family reviewers; the waiver reasoning rationalized away exactly the probe that would have caught it.
  **criterion now:** ISC-54 states the all-353 scope and is evidenced by `test_render_coverage.py`; template provenance and a fallback flag reach every manifest entry; `validate --out` refuses a fallback by default. **Resolved 2026-07-27 late** — the forced render found exactly 3 fall-throughs (the engine's own overlay subtypes) and they were fixed at dispatch rather than recorded as exceptions.
- **conjectured:** `zeroRealPii: true` and "generation writes nothing outside `--out`" are properties the generator can assert about itself.
  **refuted by:** Cato audit + this round's probes — the PII flag was a hardcoded literal that no input could falsify, and the write check watched `git status` on a repository working tree, which is the one place a stray temp file, font cache or dotfile would never land. Sweeping the *output* then found the leak both had missed: the substrate draws carrier and defense-firm names from pools of real California companies, so every seed that did not name its own carrier shipped a real organization on a fabricated claim file.
  **learned:** an anti-criterion has to be measured on the artifact, not asserted about the process that made it — and it must be able to fail, which means building the input that makes it fail and keeping that as a test.
  **criterion now:** ISC-73 is a denylist sweep over extracted document text plus every manifest cast field, with a positive control; `zeroRealPii` is computed from `CaseCast.provenance` and published with its derivation; ISC-74 diffs a sentinel `HOME`/`TMPDIR`/XDG tree around a subprocess generate.

## Verification

Evidence is grouped; every probe was run in the main checkout on the fast-forwarded branch (commits f9e4ed7, 170fe9e, dac1d8a) unless noted.

- ISC-1..10: Bash — `wc-caseload --help` lists all four commands; venv install clean; root README/CLAUDE rows + ci.yml paths-filter and quality-gate job present (rg probe); docs quartet on disk with GBS footers.
- ISC-11..20, 22..29: pytest — 225-test suite covers schema, validation errors, deep-merge, auto-derivation determinism, distribution presets, full control-precedence matrix; `seed --template` round-trips through the loader.
- ISC-12/69: Bash — demo caseload double-run: 289 files md5-identical; cross-process and cross-TZ (`TZ=Australia/Sydney`) runs also identical (initially FAILED with 55-60 drifting files; fixed in dac1d8a; re-probed clean). Entrypoint parity added: `python -m wc_caseload_engine`, `-m wc_caseload_engine.cli` and the `wc-caseload` console script write byte-identical trees (test_entrypoint_parity). **Second review round:** the sentinel bypass reproduced first — `WC_CASELOAD_HASH_PINNED=1` with `PYTHONHASHSEED=1` vs `=2` gave tree md5 `86f0a84…` vs `62ccd53…` (3 files drifted: 2 PDFs + the manifest) — and is now identical at `4cf9286…` with zero per-file drift. Three subprocess regressions in `TestHashSeedGuard`: the sentinel buys no bypass, a sentinel already at `MAX_REEXEC_HOPS` exits non-zero naming both `PYTHONHASHSEED` and the guard variable instead of exec-looping, and one hop still suffices on the ordinary path. Demo gate re-run after all three fixes: 346 files, tree md5 `8af3070…` identical across a double-run and a `TZ=Australia/Sydney` third run, zero per-file drift; `validate --out` OK at 7 manifests / 331 documents / **0 fallbacks**.
- ISC-27: chi-square over a 120-document case against a 0.5/0.25/0.15/0.10 seeded mix, α = 0.001; positive control rejects an all-pdf draw; the shipped demo's 331 documents pass the same test against its own 0.6/0.25/0.1/0.05 mix (test_format_mix).
- ISC-30..38: pytest test_lifecycle_paths + test_date_spine; live manifest probes: denial path docs present; recon windows 23d/18d (≤25) and 42d/49d (≤60). **ISC-32/33, second review round:** the boundary collapse reproduced first — 84 of 90 boundary-valid seeds (30 rng draws × qme / ur / ur+imr, injury exactly on each branch's floor) produced a non-increasing chain, most of them every document on 2026-01-01 — and is now 0 of 90. `TestBranchChainsAreFittedNotClamped` asserts strict ordering on the QME, UR-upheld, UR-overturned and UR+IMR chains at their floors, each as a single seed and as a 30-seed property test, because one passing draw of an `rng.randint` chain is an anecdote.
- ISC-39..46: live probe — nguyen case: 3 lien tracks (medical/hospital/pharmacy), 3× LIEN_RESOLUTION agreements, conference + lien pretrial statement docs, 17/17 distinct lien dates after the ordering fix.
- ISC-47..53: live probes above + tests per recon outcome (denied/granted_remand×settled/further_litigation).
- ISC-54..59: test_render_coverage — **all 353 canonical subtypes forced through `render_document`: 0 raised, 0 `GenericDocumentTemplate` resolutions, 0 fallbacks, 0 under 500 B, 353/353 PDFs parse with ≥1 page; `KNOWN_UNRENDERABLE_SUBTYPES` is empty** (~25 s). test_rendering (four formats open in native readers). ISC-58 by full-case sweep: 40/40 text-bearing documents of `alvarez-denied-recon-remand` name the applicant; every post-filing captioned document carries the ADJ number; 0 intrusions from the other six casts (test_coherence). **Second review round:** employer-trio coherence added to the same file — the reproduction (`rng_seed=2` + `industry: healthcare`) gave "Ashvale Construction Group" / healthcare / "Laborer" and now gives "Ashvale Care Network" / healthcare / "Medical Assistant"; asserted across four industries × ten draws, plus a seeded `applicant.occupation` still outranking the industry and a free-text industry degrading without raising.
- ISC-60..64: Bash — `taxonomy-check` exit 0 at 353/353 parity; `validate --out` OK (276 docs canonical, checksums match); corpus filename regex 0 failures on 50 PDFs; neutral naming is default.
- ISC-65..68: manifest probes — per-doc fields incl. md5/fileSize/mimeType; provenance {zeroRealPii: true, substrateSha, seedHash}; caseload manifest carries stage/resolution/lien/recon summaries + subtypeCoverage {78, 353, 22.1%}.
- ISC-70..74: 307 tests; ruff clean; anti-probes — no substrate file copied (content-hash test + Forge trace); ISC-73 denylist sweep clean over 256 text-bearing demo documents and all 7 manifests' cast fields, positive control fires, 400 engine-coined organization names checked against the list; `zeroRealPii` computed and provably falsifiable; ISC-74 sentinel `HOME`/`TMPDIR`/XDG tree shows 0 created, 0 modified, 0 removed files after a subprocess generate (test_anti_probes).
- ISC-75..82, 84: perspective build (commit 217b6d2) — 257 tests (+32) incl. mirrored-facts invariant (identical cast/ADJ/dates across perspectives), work-product swap, applicant-only absence + forced-override WARN path, comparative frequency probe (defense CLAIMS_ADMINISTRATION=9, INVESTIGATION=3 vs applicant baseline), 7-case demo double-run + TZ run MD5-identical (346 files), validate OK (331 docs), six pre-existing cases byte-stable (only intended manifest deltas: perspective field + seedHash).
- ISC-83: README/CHANGELOG + HTML user guide Section 4 (Case perspective) — guide live-verified against perspective.py and a 7-case run.
- ISC-21: DEFERRED-VERIFY — doctrine_hooks accepted by schema and wired into the plan; content-depth probe (per-hook language in rendered docs) deferred to the KB-grounding follow-up under AJC-34.
