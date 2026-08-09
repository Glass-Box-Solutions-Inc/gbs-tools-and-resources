# Golden corpora

One file per shipped corpus in `examples/`, recording what that corpus produced
when it was last deliberately accepted. `tools/golden_gate.py` writes them and
checks them; nothing else should edit them by hand.

The point is asymmetry. **Unintended drift is loud** — a regression that moves
one document in one case fails a named CI step that says which case and which
axis moved. **Intended drift is a commit** — you re-record, and a reviewer sees
the change as a diff instead of as a line in a log nobody read.

## The corpus drifted and I meant it to

```bash
python tools/golden_gate.py --check              # confirm what moved, and where
python tools/golden_gate.py --record --only demo-caseload
git add tests/golden/demo-caseload.json
```

`--record` prints the changes it wrote, so the commit message can say what
actually moved rather than "update goldens". Re-record only the corpora you
meant to change: re-recording all four to silence one is how a real regression
rides along with an intended one.

## The corpus drifted and I did not mean it to

Read the report. It names the case and the axis:

| axis | moved because |
|---|---|
| `rendered documents` | a document's bytes, filename, order or count changed |
| `seed.yaml` | seed materialization or auto-derivation changed |
| `case_facts.yaml` | the resolved ledger, or its YAML serialization, changed |
| `manifest.json` | any of the above, or the published ledger, cast, counts or track summaries |

If only `manifest.json` moved, the rendered documents are untouched and the
change is in the metadata around them. If `rendered documents` moved too, a
template or a content pool did.

`--check --keep DIR` retains the regenerated tree so you can open the files.

## Why the report keeps mentioning dependency versions

Every golden records the versions that decide rendered bytes — ReportLab,
python-docx, PyMuPDF, Pillow, Faker — and prints them beside a failure when
they differ from the recording environment. All are pinned by range in
`pyproject.toml`, so CI resolves the newest compatible release and a corpus can
drift because a dependency shipped. That is real drift and the gate should
surface it; naming the version turns an inscrutable red into a one-line answer.

The same list carries `systemFonts`, and that one earns its place by being
*silent*. The substrate's scan simulator draws its fax-header strip with
`/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf` and catches `OSError` to
fall back on PIL's default font. On a machine without the DejaVu package the
fallback substitutes different pixels into every scanned PDF, warns nobody, and
the only symptom is a golden that will not reproduce. A recorded digest — or
`absent` — answers that in one line.

## What is deliberately not compared

The engine version and the substrate SHA are recorded and never digested. A
golden is valid for one `(engine version, substrateSha)` pair, but treating the
pair as *content* would redden every case on a version bump — and the re-record
that forced would silently absorb any real drift shipped alongside it. They are
context that explains a failure, not part of what fails.

`substrateSha` has a second problem that settles it: it comes from `git log -1`
over the substrate directory, so it describes the checkout rather than the
substrate's content. It already disagrees with the committed `substrate_pin.txt`
in a clean tree, and a shallow CI checkout can answer differently again.

## Adding a corpus

Register it in `CORPORA` in `tools/golden_gate.py`, pick a tier, and record it.
`tests/test_golden_corpus.py` fails if an `examples/*.yaml` has no entry, so a
new showcase cannot ship ungated by accident.

Tiers decide *which process pays*, never whether a corpus is gated:

- `suite` — checked by `tests/test_golden_corpus.py`, so on every `pytest tests/`
  and in CI.
- `ci` — checked by a dedicated step in the package's CI job, keeping the two
  largest trees out of every local run.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
