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

Any JSON/YAML object or array is accepted. Extraction systems can improve provenance by supplying
`value`, `field`/`name`, `confidence`, `source_document`/`document_id`, `page`, `excerpt`, and
`evidence` on a claim. A payload without those fields remains usable: the input file and JSON/YAML
path become its provenance, and the engine labels the evidence as limited rather than inventing it.

The package recognizes these generator conventions automatically:

- `manifest.json` with `caseFacts`, `documents`, and `provenance`.
- `case_facts.yaml`, the resolved case ledger that mirrors `manifest.caseFacts`.

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
