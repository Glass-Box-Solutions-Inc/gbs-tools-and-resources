# wc-synthetic-caseload-engine — Programming Practices

**Last Updated:** 2026-07-27

---

## Tech Stack

- **Python 3.12** — inherited from the substrate whose templates this package reuses.
- **Pydantic v2** — seed schema, with `extra="forbid"` everywhere.
- **Click** — CLI.
- **structlog** — structured logging.
- **ReportLab / PyMuPDF / python-docx / Pillow / Faker** — via the substrate's templates.
- **pytest + ruff** (line length 100) — quality gates.
- **uv** — environment management.

---

## Architecture Patterns

- **The seed is the interface.** Anything that changes output is expressible in the seed and
  is surfaced back to disk. No hidden knobs.
- **One bridge module.** `substrate.py` is the only place `sys.path` is touched. The substrate
  path is appended, never prepended, so it cannot shadow this package.
- **Pure core, impure edges.** `doc_controls.py` imports no substrate and touches no disk, so
  the whole precedence matrix is unit-testable in isolation. Rendering and file writing live at
  the edges.
- **Machines own their tracks.** The lien and reconsideration machines own every document of
  their kind; competing substrate emissions are stripped rather than merged.
- **Counts, then dates.** The control resolver works in counts so its precedence rules stay
  pure; the planner re-attaches dates afterwards from the proposing candidate.

---

## Code Conventions

- Module docstrings explain *why*, not *what* — especially where the code fights the substrate.
- Constants that encode a legal rule cite it (`LC 5903`, `LC 5909`, `LC 4610`).
- Public functions carry Google-style docstrings with Args/Returns where the signature is not
  self-evident.
- `__all__` on every module.
- Dataclasses are `frozen=True, slots=True` unless mutation is required.
- Type hints everywhere; `from __future__ import annotations` at the top.
- Every markdown file ends with the GBS footer.

---

## Key Dependencies

Runtime: `pydantic`, `click`, `pyyaml`, `faker`, `reportlab`, `Pillow`, `python-docx`,
`pymupdf`, `structlog`. Dev: `pytest`, `ruff`.

The substrate (`packages/merus-test-data-generator`) is a **path dependency, not a package
dependency** — it has no `pyproject.toml` and is discovered on disk.

---

## Testing Approach

- **Never touch the network.** Generation must succeed fully offline.
- **Never depend on the wall clock.** `ANCHOR_DATE` is "today"; a test that would pass only on
  a particular date is a bug.
- **Assert on the plan, render only when rendering is the subject.** `build_case_plan` carries
  every subtype, date, track and format, and is orders of magnitude faster than rendering.
- **Skip cleanly, never fail spuriously.** Tests needing the substrate or the classifier
  checkout are marked `requires_substrate` / `requires_classifier`.
- **Determinism is tested across processes.** An in-process double-run shares a hash salt and
  passes even when a real leak exists; the cross-process test spawns fresh interpreters.
- Test names read as sentences describing the guarantee, not the function under test.

---

## Project-Specific Notes

- **Never use `hash()` or bare `random`** for anything affecting output — use `seed.rng(salt)`
  or `derive_seed(...)`, both SHA-256 based.
- **Never write a non-canonical subtype to a manifest.** Map it or drop it. A wrong mapping
  silently poisons the classifier accuracy corpus this engine exists to feed, so when in doubt,
  drop.
- **Never edit or copy the substrate.** Fix the bridge, or work around it here and document the
  limitation in `CLAUDE.md`.
- **Any new output format needs a determinism check** — containers embed timestamps.

---

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
