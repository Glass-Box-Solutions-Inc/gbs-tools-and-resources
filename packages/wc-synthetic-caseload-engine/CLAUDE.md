# wc-synthetic-caseload-engine — Developer Guide

**Seed-driven generator of complete synthetic CA workers' compensation attorney case files.**
Ticket: **AJC-34**. See `README.md` for the product surface and `ISA.md` for the criteria contract.

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
| `case_context.py` | The one canonical cast per case (`CaseCast`). |
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
- **Lien and recon templates are variants, not bespoke.** `LIEN_RESOLUTION` and
  `LIEN_STIPULATION_AGREEMENT` both render through `Stipulations`;
  `PETITION_RECONSIDERATION_FILED` renders through `ApplicationForAdjudication`;
  `ORDER_ON_RECONSIDERATION` and `AMENDED_FINDINGS_AWARD` through `MinutesOrders`. Real
  templates, correct-looking documents, but the two lien resolution flavours differ only by
  variant string.

---

## Determinism rules (non-negotiable)

1. **Never read the wall clock.** `ANCHOR_DATE` (2026-01-01) is "today". No manifest carries a
   generation timestamp — that is what keeps the guarantee verifiable.
2. **Never use `hash()` or bare `random`** for anything that affects output. Use
   `seed.rng(salt)` or `derive_seed(rng_seed, salt)` (SHA-256 based).
3. **Every new output format needs a determinism check.** Containers embed timestamps: ZIP
   does, PDF does. Add the normalization to `determinism.py` and a test beside
   `test_normalize_docx_is_stable_and_uses_the_document_date`.
4. **Cross-process is the real test.** In-process double-runs share a hash salt and will pass
   even when a leak exists. `test_same_seed_produces_identical_bytes_across_processes` spawns
   fresh interpreters on purpose.

---

## Testing

```bash
uv venv --python 3.12 && uv pip install -e ".[dev]"
.venv/bin/python -m pytest tests/ -q      # 169 tests
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
| `test_rendering.py` | Four formats open in their own readers, manifests, determinism |

Tests requiring the substrate or the classifier checkout skip cleanly when absent — CI has the
substrate (same monorepo) but not `Adjudica-classifier`.

Fast iteration: assert on the **plan** (`build_case_plan`) rather than rendered files.
Rendering is the slow part; the plan carries every subtype, date, track and format.

---

## Adding a lifecycle path

1. Add the seed fields to `seeds.py` with cross-field validation.
2. Emit `DatedCandidate`s from the owning machine — dates clamped through `timeline.clamp`.
3. If the substrate also emits those subtypes, add them to the machine's `*_OWNED_SUBTYPES`
   so the walk stops competing.
4. Confirm every new subtype is canonical (`effective_taxonomy().is_canonical`) — a
   non-canonical key must be mapped or dropped, never written to a manifest.
5. Add a path test asserting the subtypes appear and the dates order correctly.

---

## Ticket & branch

- Linear: **AJC-34** (AJC, not ADJ — repo precedent for `gbs-tools-and-resources` packages).
- Commits: conventional, scoped `feat(wc-synthetic-caseload-engine)` or `[AJC-34]`.

---

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
