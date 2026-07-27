# wc-synthetic-caseload-engine — Plans Approved

**Last Updated:** 2026-07-27
**Ticket:** AJC-34

---

## Recent Plans

### [PLAN-2026-07-27-01] Seed-driven WC synthetic attorney case-file engine

**Approved:** 2026-07-27
**Status:** Completed (v0.1.0)

#### Summary

New standalone package producing complete synthetic CA workers' compensation attorney case
files from a reviewable YAML seed per case. Built in two phases on top of
`merus-test-data-generator`, which is consumed as a library.

- **Phase A** — packaging, substrate bridge, 353-subtype taxonomy sync, seed schema,
  document-control resolver, CLI skeleton.
- **Phase B** — lifecycle bridge, lien machine, reconsideration machine, canonical case cast,
  renderer, manifests, example caseload, documentation.

#### Key Decisions

- New package rather than extending `merus-test-data-generator` in place — the substrate stays
  a general-purpose generator; control logic lives here.
- Python 3.12 despite the org's TypeScript-first default, to preserve ~90% reuse of the
  substrate's ReportLab templates, content pools and lifecycle DAG. Explicit stack decision.
- The seed is the interface: everything a case needs is expressible in one reviewable
  artifact, and auto-derived seeds are always materialized to disk.
- The classifier taxonomy (353 subtypes) is the vocabulary of record. The substrate's 34
  non-classifier realism subtypes are mapped or dropped, never written to a manifest.
- Where the substrate's probabilistic walk contradicts a seed decision, the seed wins by
  deterministic construction rather than by re-rolling the walk.
- Lien and reconsideration tracks are owned entirely by this package; the substrate's
  competing emissions for those subtypes are stripped from the walk.
- Determinism is a product guarantee, not a best effort: manifests carry no timestamp, and
  three substrate-side reproducibility leaks are closed here rather than by editing the
  substrate.

#### Result

169 tests, `ruff` clean, six-case example caseload generating 276 documents across all four
output formats, byte-identical across runs.

---

## Archive

*Plans older than 90 days are archived automatically.*

---

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
