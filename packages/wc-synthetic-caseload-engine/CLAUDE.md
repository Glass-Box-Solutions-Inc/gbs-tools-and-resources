# wc-synthetic-caseload-engine — Developer Guide

**Seed-driven generator of complete synthetic CA workers' compensation attorney case files.**
Tickets: **AJC-34** (engine), **AJC-36** (docs). See `README.md` for the product surface,
`docs/user-guide/index.html` for the operator guide — including the per-doctrine "needed seeds"
reference — and `ISA.md` for the criteria contract.

---

## ⚠️ CRITICAL GUARDRAILS (READ FIRST)

1. **NEVER push without permission** — Even small fixes require express user permission. No exceptions.
2. **NEVER expose secrets** — No API keys, tokens, credentials in git, logs, or conversation.
3. **NEVER force push or skip tests** — 100% passing tests required.
4. **ALWAYS read parent CLAUDE.md** — `~/CLAUDE.md` for org-wide standards.
5. **ALWAYS use Definition of Ready** — 100% clear requirements before implementation.

---

## Stack decision (read this before "why Python?")

This package is Python 3.12 despite the org's TypeScript-first default. The reusable
substrate — 25 ReportLab template classes, content pools, the lifecycle DAG, the scan
simulator — is Python. A TypeScript rebuild would forfeit roughly 90% of the reuse this
package is built on. Flagged and accepted as an explicit stack decision.

---

## Module map

| Module | Owns |
|--------|------|
| `substrate.py` | The **only** place `sys.path` is touched. Locates and imports the substrate. |
| `seeds.py` | Pydantic models, YAML loader, deep-merge, `auto:` derivation, `ANCHOR_DATE`. |
| `taxonomy.py` | The effective 353-subtype taxonomy, classifier TS parsing, drift detection. |
| `doc_controls.py` | Pure control-precedence resolver. Imports no substrate — fully unit-testable. |
| `lifecycle_bridge.py` | Seed → substrate `CaseParameters`, the walk, vocabulary normalization, deterministic guarantees, `CaseTimeline`. |
| `lien_machine.py` | One `LienTrack` per claimant, claim → notice → conference → resolution. |
| `recon_machine.py` | The petition-for-reconsideration round trip and its post-recon paths. |
| `case_context.py` | The one canonical cast per case (`CaseCast`), including the coined-name substitution for every substrate organization pool. |
| `name_denylist.py` | The shipped real-entity denylist (package data) and the **live** read of the substrate's organization pools. Engine and anti-probes read one list. |
| `perspective.py` | Applicant vs defense **file** POV: the work-product swap table, `PERSPECTIVE_PROFILES` (per-key emission weights + floors), and author/recipient roles. Changes no case fact — the applicant path is a literal identity function. |
| `planner.py` | Composes the three machines through the resolver into an ordered `CasePlan`. |
| `renderer.py` | Template dispatch, format assignment, per-document reproducibility. |
| `determinism.py` | The three reproducibility fixes (hash seed, docx ZIP times, PDF `/ID`). |
| `manifests.py` | Output tree, manifests, `validate --out`. |
| `cli.py` | Click commands. |

Data flow: `seed → timeline → {core, liens, recon} candidates → doc_controls → dated plan → renderer → manifest`.

---

## Substrate bridge notes

The substrate is `../merus-test-data-generator` — consumed as a library, **never copied and
never edited**. Its modules import each other as top-level packages (`data.x`,
`pdf_templates.y`), so the substrate *root* goes on `sys.path`. It is appended, not prepended,
so it can never shadow this package's modules or a same-named test module.

If an import breaks, fix the bridge — not by copying files.

### Where the substrate fights us, and how we win

| Problem | Resolution |
|---------|-----------|
| `has_liens` / lien nodes would emit a second, contradictory lien set | `has_liens=False` is forced; `lien_machine` owns the track |
| `appeal` and `post_resolution` nodes emit stray recon documents | `RECON_OWNED_SUBTYPES` stripped from the walk; `recon_machine` owns them |
| `resolution_cr` never emits `ORDER_APPROVING_SETTLEMENT` | Resolution documents are constructed deterministically from the seed |
| `LITIGATION_STAGE_TO_TARGET` predates `pre_trial` / `post_recon` | `TARGET_STAGE_MAP` translates to `settlement` / `resolved` |
| `resolution_type` knows only stipulations/c_and_r/trial | `RESOLUTION_MAP`; `findings_award` and `take_nothing` both map to `trial` |
| UR vocabulary is inverted vs the seed's | `UR_DECISION_MAP`: seed `upheld` (denial stands) → substrate `denied` |
| Complexity scaling multiplies counts 2-3x, including one-per-case paperwork | `SINGLETON_SUBTYPES` trims to the most essential single copy |
| 34 enum members are not classifier vocabulary | `SUBSTRATE_TO_CANONICAL` (11 mapped) + `DROPPED_SUBSTRATE_ONLY` (23 dropped) |
| `generate_case_from_params` rejects unresolved `"random"` fields | `params.resolve_random(seed.rng("params"))` before use |
| `load_template_class` falls back through `orchestration.pipeline`, which needs `dotenv` | `GenericDocumentTemplate` is imported directly |
| Registry `variant` is never wired into the spec | The renderer sets `context["variant"]` itself |
| `get_template_for_subtype` returns `GenericDocumentTemplate` for keys it does not know, so "missing" and "generic" are the same answer | `RenderResult.template` / `.fallback` record which ran; `renderer.OVERLAY_TEMPLATES` resolves the three overlay subtypes the substrate enum lacks |
| **Four** `data/wc_constants.py` pools name real organizations — `INSURANCE_CARRIERS`, `DEFENSE_FIRMS`, `ALL_EMPLOYERS` (Safeway, Costco, Kaiser, UPS, City of LA), `MEDICAL_FACILITIES` | `case_context._replace_real_organizations` substitutes coined names on every one whenever the seed does not name its own, and rebuilds the derived adjuster/defense emails. `name_denylist.substrate_organization_pools()` reads the pools **live** so the sweep cannot go stale |
| Templates draw from the **global** `random` module | Re-seeded per document from `rng_seed` + index |

### Known substrate limitations (documented, not worked around)

- **Applicant firm is hard-coded.** `data/docx_styles.py` renders `Martinez & Associates, APC`
  on the letterhead. `profile.attorneys.applicant_firm` is recorded in the seed and manifest
  but does not change the rendered letterhead. Patching a substrate module's private constant
  at runtime would be shared mutable state across cases; a documented limitation is cheaper
  and honest.
- **`list(set(...))` in `data/content_pools.py`** (lines ~1043 and ~1136) makes substrate
  output non-reproducible across processes. Worked around here with `PYTHONHASHSEED=0`; the
  proper fix is `sorted(...)` upstream.
- **Substrate `date.today()` in rendered content.** Four sites (`fake_data_generator`,
  `qme_ame_report`, `settlement_memo`, `deposition_exchanges`) compute ages and hire dates from
  the *local* wall clock. Rebound at runtime by `determinism.pin_substrate_clock()` — a
  deliberate exception to the no-patching rule, and a narrow one: the anchor is a process-wide
  constant, so it carries none of the shared-mutable-state risk that keeps the letterhead
  unpatched. The proper fix is an injectable clock upstream.
- **Faker's `date_of_birth` is clock-relative.** A seeded Faker is still not deterministic for
  age-relative draws: the window ends at `datetime.now()`. Faker is *not* patched — rebinding
  its `datetime` breaks the `isinstance` checks in its own date parser — so
  `case_context._date_of_birth` owns the field instead, deriving it from `seed.rng("dob")`.
  Any future substrate use of a clock-relative Faker provider needs the same treatment.
- **Lien and recon templates are variants, not bespoke.** `LIEN_RESOLUTION` and
  `LIEN_STIPULATION_AGREEMENT` both render through `Stipulations`;
  `PETITION_RECONSIDERATION_FILED` renders through `ApplicationForAdjudication`;
  `ORDER_ON_RECONSIDERATION` and `AMENDED_FINDINGS_AWARD` through `MinutesOrders`. Real
  templates, correct-looking documents, but the two lien resolution flavours differ only by
  variant string.

---

## Determinism rules (non-negotiable)

1. **Never read the wall clock.** `ANCHOR_DATE` (2026-01-01) is "today". No manifest carries a
   generation timestamp — that is what keeps the guarantee verifiable. This binds our *and*
   the substrate's code: `determinism.pin_substrate_clock()` rebinds the four substrate names
   that call `date.today()`, and any new one must be added to `CLOCK_PINNED_ATTRIBUTES` /
   `CLOCK_PINNED_CALLABLES`.
2. **Never use `hash()` or bare `random`** for anything that affects output. Use
   `seed.rng(salt)` or `derive_seed(rng_seed, salt)` (SHA-256 based).
3. **Never build a timestamp from local time.** No `datetime.now`, `date.today`,
   `time.localtime`, `time.mktime`, `.timestamp()` or `.astimezone()` anywhere in a rendering
   path. Every timestamp goes through `determinism.fixed_utc_datetime()` /
   `pdf_date_string()` / `zip_date_time()`, all pinned to noon UTC on the document's own date.
4. **Every new output format needs a determinism check.** Containers embed timestamps: ZIP
   does, PDF does, RFC 2822 headers do. Add the normalization to `determinism.py` and a test
   beside `test_normalize_docx_is_stable_and_uses_the_document_date`.
5. **Cross-process is the real test, and so is cross-timezone.** In-process double-runs share a
   hash salt and will pass even when a leak exists;
   `test_same_seed_produces_identical_bytes_across_processes` spawns fresh interpreters on
   purpose, and `test_timezone_determinism.py` renders the same case under
   `America/Los_Angeles` and `Australia/Sydney`. The TZ probe is what caught the substrate's
   `date.today()` content and Faker's clock-relative `date_of_birth`; a same-machine gate had
   been passing over both for the whole of Phase B.
6. **Library mode does not self-pin.** `ensure_stable_hashing()` works by re-executing the
   process and only the CLI entry point calls it. Anything importing this package as a library
   must call it first, or set `PYTHONHASHSEED=0` before the interpreter starts. Document this
   wherever a new entry point is added.

### Date-spine rules

1. **Floors before ceilings.** Bound a date with `max(floor, min(proposed, ceiling))`, never a
   bare `min(...)`. A bare clamp is what dated a reconsideration petition 80 days before the
   Application it appealed from.
2. **A sequenced chain is fitted, not clamped.** Every chain whose documents cause each other —
   lien tracks, the recon round trip, the denial response, the QME/AME evaluation, the UR/IMR
   appeal — builds its intended dates unclamped and passes the whole list through
   `lifecycle_bridge.fit_track()`, which compresses in order with strictly increasing dates.
   Clamping a chain date-by-date stacks it on the horizon. `CaseTimeline.clamp` is only for the
   parallel core track, whose documents have no ordering relationship.

   **A floor is not a substitute for a fit.** The runway floors (rule 4) reject a seed too short
   for its chain; they say nothing about a seed sitting *on* the floor, where the chain fills
   the window exactly and per-date clamping still collapses it. Both rounds of this defect were
   found the same way — boundary-valid seeds, one per branch, asserting strict ordering — so a
   new chain needs that test, not just a floor. Two documents dated the same day is the smell.
3. **Impossible seeds are rejected, not absorbed.** `CaseSeed._check_runway` fails loudly when
   the injury sits too close to the anchor for the seeded story. Adding a lifecycle feature that
   consumes calendar time means adding its floor to `seeds.STAGE_RUNWAY_DAYS` (or the
   resolution/post-resolution constants) *and* to `_stage_runway_floor`, so auto-derivation
   stays compliant by construction.
4. **A branch is a chain, so a branch has a floor.** The stage and the resolution are not the
   only things that consume calendar. `seeds.runway_demands()` enumerates every demand —
   stage, `claim_response: denied` (90d), `ur_dispute` (65d), `imr` (120d), `eval_type`
   qme/ame (240d), resolution (540d), recon / post-resolution liens (720d) — and the error
   names whichever one binds. Each floor is derived from the minimum its own document chain
   can be drawn at, not estimated: read the machine before choosing the number.
5. **`__pycache__` is a write.** `sys.dont_write_bytecode = True` is set on the first
   executable line of `__init__.py` (and again in `cli.py` / `__main__.py`), and
   `PYTHONDONTWRITEBYTECODE=1` rides through the re-exec. Without it, importing the substrate
   scatters bytecode across a read-only dependency's source tree — outside `--out`, and
   outside the guarantee.

---

## Testing

```bash
uv venv --python 3.12 && uv pip install -e ".[dev]"
.venv/bin/python -m pytest tests/         # 527 tests, ~95s (pyproject already passes -q)
.venv/bin/ruff check .
```

| File | Covers |
|------|--------|
| `test_seed_schema.py` | Models, validation errors, deep-merge, `auto:` derivation |
| `test_doc_controls.py` | The precedence matrix in isolation |
| `test_taxonomy_sync.py` | 353-subtype parity and drift detection |
| `test_substrate_bridge.py` | The bridge imports cleanly (fail fast, clear message) |
| `test_cli_surface.py` | Command surface, exit codes, templates |
| `test_lifecycle_paths.py` | Lien resolutions, recon outcomes, statutory windows, dates |
| `test_date_spine.py` | Runway validation, timeline invariants, ordering-preserving track fitting |
| `test_timezone_determinism.py` | Cross-timezone byte identity, clock pinning, synthetic markers, `-m` re-exec |
| `test_rendering.py` | Four formats open in their own readers, manifests, determinism |
| `test_render_coverage.py` | **All 353 subtypes forced through the dispatch path** — zero fallbacks, zero stubs (~25 s) |
| `test_template_provenance.py` | `template` / `fallback` manifest fields, `validate --allow-fallback` gating |
| `test_anti_probes.py` | Real-entity denylist sweep, computed `zeroRealPii`, sentinel-tree write check |
| `test_coherence.py` | Full-case identity sweep + cross-case contamination guard |
| `test_format_mix.py` | Chi-square of realized vs seeded format distribution |
| `test_entrypoint_parity.py` | `-m` and console-script output are byte-identical |
| `test_doctrine_content.py` | Doctrine content table, prerequisites, plan flags, per-hook language on the page, hook-free anti-probe, and the `examples/doctrine-showcase.yaml` pins (every hook seeded, zero warnings, every hook landing, no forced subtypes) |
| `test_manifest_integrity.py` | `zeroRealPii` vs the denylist, canonical control keys at generate, emitted-vs-proposed track counts |

The demo caseload is generated **once per session** by the `demo_caseload` fixture in
`conftest.py` (~70 s, 331 documents) and shared by four modules. Add demo-based assertions to
that fixture rather than regenerating.

Tests requiring the substrate or the classifier checkout skip cleanly when absent — CI has the
substrate (same monorepo) but not `Adjudica-classifier`.

Fast iteration: assert on the **plan** (`build_case_plan`) rather than rendered files.
Rendering is the slow part; the plan carries every subtype, date, track and format.

---

## Adding a lifecycle path

1. Add the seed fields to `seeds.py` with cross-field validation.
2. Emit `DatedCandidate`s from the owning machine. Decide first which kind of path it is: a
   **sequence** (documents that cause each other) builds unclamped and goes through
   `fit_track`; only a **parallel** set with no ordering relationship uses `timeline.clamp`.
   When in doubt it is a sequence — that is the assumption that fails safely.
3. If the path consumes calendar time, add its floor per date-spine rule 4.
4. If the substrate also emits those subtypes, add them to the machine's `*_OWNED_SUBTYPES`
   so the walk stops competing.
5. Confirm every new subtype is canonical (`effective_taxonomy().is_canonical`) — a
   non-canonical key must be mapped or dropped, never written to a manifest.
6. Add a path test asserting the subtypes appear, plus a **boundary** test: an injury sitting
   exactly on the new floor, asserting strict ordering across ~30 `rng_seed` draws. A single
   draw of an `rng.randint` chain proves nothing about the chain.

---

## Ticket & branch

- Linear: **AJC-34** (engine), **AJC-36** (user guide + doctrine showcase). AJC, not ADJ —
  repo precedent for `gbs-tools-and-resources` packages.
- Commits: conventional, scoped `feat(wc-synthetic-caseload-engine)` or `[AJC-NN]`.

---

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
