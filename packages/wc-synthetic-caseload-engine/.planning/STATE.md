# wc-synthetic-caseload-engine — Project State

**Last Updated:** 2026-07-27
**Status:** v0.1.0 complete
**Current Phase:** Phase B complete — ready for review
**Ticket:** AJC-34

---

## Current Focus

Phase B landed: lifecycle bridge, lien machine, reconsideration machine, canonical case cast,
renderer, manifests, example caseload and documentation. The CLI runs end to end and the
output is byte-reproducible.

---

## Progress

### Completed

**Phase A**
- Package scaffold, `pyproject.toml`, `src/` layout, `wc-caseload` console script
- Substrate bridge (`substrate.py`) with actionable failure messages
- 353-subtype effective taxonomy + classifier drift detection
- `CaseSeed` / `CaseloadSpec` schema, YAML loader, deep-merge, `auto:` derivation
- Document-control precedence resolver
- CLI skeleton: `seed --template`, `taxonomy-check`, `validate --spec`

**Phase B**
- `lifecycle_bridge.py` — seed → substrate `CaseParameters`, walk, normalization,
  deterministic guarantees, `CaseTimeline`
- `lien_machine.py` — N claimant tracks through executed resolutions, post-resolution dating
- `recon_machine.py` — petition round trip with LC 5903 / LC 5909 windows and all post-recon paths
- `case_context.py` — one canonical cast per case
- `renderer.py` — registry dispatch, four formats, per-document reproducibility
- `determinism.py` — hash-seed pinning, docx ZIP repack, PDF `/ID` normalization
- `planner.py` / `manifests.py` — composition, output tree, `validate --out`
- `examples/demo-caseload.yaml` — six cases, 276 documents
- Documentation quartet + root registry entries + CI quality gate

### In Progress

*None.*

### Blocked

*None.*

---

## Verification

| Gate | Result |
|------|--------|
| `pytest` | 169 passed |
| `ruff check .` | clean |
| Demo caseload | 6 cases, 276 documents (170 pdf, 62 scanned_pdf, 32 eml, 12 docx) |
| `validate --out` | OK — every subtype canonical, every checksum matches |
| Determinism | Two full runs byte-identical, including all manifest MD5s |

---

## Next

- Review and merge AJC-34.
- Optional follow-ups, none blocking: bespoke lien/recon templates upstream (currently
  substrate variants), and a `sorted(...)` fix for `list(set(...))` in the substrate's
  `data/content_pools.py` so the `PYTHONHASHSEED` pin becomes belt-and-braces.
- Downstream consumers: Adjudica demo-account ingestion and classifier accuracy corpus
  expansion beyond the current 97-of-353 subtype coverage.

---

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
