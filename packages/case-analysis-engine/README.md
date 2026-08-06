# Case Analysis Engine

`case-analysis-engine` turns document-intake extraction JSON/YAML and
`wc-synthetic-caseload-engine` artifacts into one deterministic, evidence-first case view.
It is a standalone package: it does not import either upstream engine and it does not make legal
conclusions.

## What it does

- Normalizes every scalar claim into a fact with source, source location, and confidence.
- Recognizes generator `manifest.json` and `case_facts.yaml` as first-class input while accepting
  generic extraction payloads.
- Detects conflicting assertions, repeated assertions, weak or missing evidence, and potentially
  inconsistent chronology.
- Reviews identity/parties, injury/employment, medical treatment and diagnostics, procedure and
  deadlines, financial facts, evidence quality, and applicant/defense/neutral angles.
- Produces byte-stable JSON and Markdown reports. All observations are traceable to fact IDs.

The reports are evidence organization and issue-spotting tools, not legal advice. An angle records
what the supplied evidence tends to support, undermine, or leave unresolved; it never asserts an
unsourced legal rule or outcome.

## Install and use

```bash
cd packages/case-analysis-engine
python -m pip install -e ".[dev]"

# Preserve the canonical ledger as normalized facts.
case-analysis normalize path/to/intake.json --out normalized.json

# Review intake plus a generated case manifest and ledger together.
case-analysis analyze intake.json generated/TC-001/manifest.json generated/TC-001/case_facts.yaml \
  --json-out report.json --markdown-out report.md

# Print only applicant, defense, or neutral observations.
case-analysis angles intake.yaml --angle defense

# Return nonzero only for error-severity integrity failures.
case-analysis validate intake.json
```

## Input conventions

**Claim promotion.** A mapping with an explicit `field` key beside `value` is a
claim record wherever it appears. The `name`/`key` shorthand promotes only
inside a recognized claim container (`facts[]`, `claims[]`, `assertions[]`,
`extractions[]`) — `{"name": "td_payment", "value": 800}` in any other list is
an entity row, never an assertion, so itemized lists cannot manufacture
conflicts.

**Metadata scope.** Metadata vocabulary (`confidence`, `source_document`,
`page`, `evidence`, …) is treated as claim metadata only where it has sibling
data to describe; a mapping holding nothing but metadata-named keys is data in
its own right (`referral.source` is an assertion, not provenance). Every key
skipped as metadata is recorded — in `normalize` output under `skipped`, in
analysis reports under `skippedKeys` with an info finding — never dropped
silently. A bare string in `evidence` names the source document.

Any JSON/YAML object or array is accepted. Unquoted YAML dates — values and
keys — are canonicalized to ISO strings at load. Mapping keys are forced to
strings; a key whose canonical form duplicates a sibling's (a date key beside
its quoted twin, `1` beside `"1"`) is rejected with a clear error, because it
would make two distinct assertions share one fact ID. Keys containing
path-structural characters (`$schema`, `patient.name`, `items[0]`) are
legitimate input: they are kept as field provenance and escaped
JSON-Pointer-style inside source paths, so they can never collide with the
path grammar. `normalize` output carries `"version": 1` so future schema
changes can migrate deterministically. Extraction systems can improve provenance by supplying
`value`, `field`/`name`, `confidence`, `source_document`/`document_id`, `page`, `excerpt`, and
`evidence` on a claim. A payload without those fields remains usable: the input file and JSON/YAML
path become its provenance, and the engine labels the evidence as limited rather than inventing it.

The package recognizes these conventions automatically:

- `manifest.json` with `caseFacts`, `documents`, and `provenance`.
- `case_facts.yaml`, the resolved case ledger that mirrors `manifest.caseFacts`.
- Its own `normalize` output (`{"facts": [...]}`), deserialized losslessly — a
  normalize-then-analyze pipeline keeps every fact ID, scope, source, location,
  page, excerpt, and confidence exactly as first recorded.

## Confidence policy

A claim keeps the confidence its input supplied. Generator artifacts default to
`1.0` because the generator ledger is its own system of record — but only when
no confidence key is present at all. A generic claim with no supplied score is
recorded with `confidence: null` — the engine never invents a probability — and
validation reports it as a `limited_evidence` warning so unscored claims stay
visible rather than silently passing. A confidence that is supplied but unusable
(a boolean, an unparseable string, a value outside `[0, 1]`) is also recorded as
`null` and reported; malformed metadata is never promoted to a default score.
An explicit `confidence: null` is the author's statement that the claim is
unscored and is preserved as such — the generator default applies only when the
key is entirely absent.

## Source identity and reproducibility

Facts are identified by a logical source label, not by the path the caller
typed: the shortest trailing path suffix that distinguishes the inputs from one
another (`manifest.json`, or `TC-001/manifest.json` when two cases each supply
one). The same inputs therefore produce byte-identical reports whether they are
referenced relatively, absolutely, or from a different checkout, so long as the
distinguishing directories travel with the corpus.

## Conflict scope

Every fact carries a `scope` decided at normalization: `claim` (an explicit
claim record naming its own field, wherever it lives — including inside a
`facts[]` list), `case` (a scalar flattened from an unindexed path), or
`entity` (an attribute of one element of a repeated collection). Conflict and
duplicate detection compares `claim` and `case` facts; `entity` facts describe
distinct things (`documents[0].subtype` vs `documents[1].subtype`) and are
never reported as contradictions.

Within one canonical field — camelCase, PascalCase, and snake_case merge into
one vocabulary — two facts are the same property only when their qualifier
chains are suffix-compatible: `caseFacts.money.averageWeeklyWage` matches
`money.averageWeeklyWage`, bare `employer` matches `case.employer`, and a claim
record compares everywhere its field appears; `applicant.phone_number` never
merges with `adjuster.phone_number`.

## Library API

```python
from pathlib import Path
from case_analysis_engine import analyze_paths, render_json, render_markdown

report = analyze_paths([Path("intake.json"), Path("manifest.json")])
Path("report.json").write_text(render_json(report), encoding="utf-8")
Path("report.md").write_text(render_markdown(report), encoding="utf-8")
```

## Development

```bash
python -m pytest
```

The package deliberately has no dependency on a legal knowledge base. Legal authority should be
added only through a separately sourced, versioned authority adapter; until then, reports retain
explicit caveats instead of attempting legal determinations.
