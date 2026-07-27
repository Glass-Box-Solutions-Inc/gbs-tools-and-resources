# Changelog

All notable changes to `wc-synthetic-caseload-engine` are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.1.0] — 2026-07-27

First release. Ticket **AJC-34**.

### Added

**Package & CLI**
- Python 3.12 package with `src/` layout and the `wc-caseload` console script.
- `generate`, `seed`, `validate` and `taxonomy-check` commands.
- Documented `sys.path` bridge to `merus-test-data-generator`, consumed as a library —
  no substrate module is copied or edited.

**Seed schema**
- Pydantic v2 `CaseSeed` / `CaseloadSpec` models with `extra="forbid"`, so a typo fails
  loudly with the dotted field path, the allowed values and the offending input.
- Profile, injury (specific / cumulative trauma / death), lifecycle, document controls and
  output sections; everything omitted is derived deterministically from `rng_seed`.
- `defaults:` deep-merge, explicit `cases[]`, and `auto:` derivation from four calibrated
  distributions (`balanced`, `early_stage`, `settlement_heavy`, `complex_litigation`).
- Auto-derived seeds are always materialized to `<out>/<case_id>/seed.yaml`.
- 14 doctrine hooks from the KB PRD.

**Document controls**
- `include_only`, `exclude`, per-subtype exact counts, per-type `min`/`max`, `global_cap`
  and `format_mix`, with documented precedence and an audit trail of every decision.
- A control demanding a lifecycle-invalid subtype emits it anyway with a WARN.

**Lifecycle**
- Core track mapped onto the substrate DAG, with deterministic guarantees where the
  probabilistic walk contradicts the seed (denial, UR/IMR chain, evaluation, death
  paperwork, and each resolution's signature documents).
- **Lien machine** — one track per claimant: claim subtype by claimant type, notice of lien
  filing, optional lien conference and pretrial statement, and a resolution document
  (`LIEN_RESOLUTION`, `LIEN_STIPULATION_AGREEMENT`, `LIEN_DISMISSAL`, `ORDER_ON_LIEN`, or
  per-track choice under `mixed`). `post_resolution_litigation` dates every lien document
  after the case-in-chief resolution.
- **Reconsideration machine** — petition within the LC 5903 25-day window, opposition,
  seed-drawn reply, and an order within the LC 5909 60-day window, followed by the seeded
  post-recon path (further litigation, settlement, or a final affirmance).
- `SINGLETON_SUBTYPES` prevents the substrate's 2-3x complexity scaling from producing three
  denial letters or two Compromise and Release agreements on one claim.

**Rendering**
- Dispatch through the substrate template registry with the registry's `variant` wired into
  the document context (the substrate never does this itself).
- All four formats — `pdf`, `scanned_pdf`, `eml`, `docx` — assigned from `format_mix`, with a
  pdf fallback plus WARN when a template cannot render a requested format.
- One canonical cast per case: applicant, employer, carrier, both firms, physicians, judge,
  venue and an `ADJ` + 8-digit number identical across every document in the case.

**Outputs**
- Per-case `seed.yaml`, `manifest.json` and `documents/`, plus an aggregate
  `caseload_manifest.json`.
- Manifests carry per-document `{filename, subtype, type, format, documentDate,
  md5Checksum, fileSize, mimeType}` and a `provenance` block asserting `zeroRealPii: true`.
- `neutral` filenames (default, no subtype leak) and `corpus` filenames matching the
  classifier's sampling regex.
- `validate --out` re-checks every subtype against the taxonomy and re-hashes every file.

**Taxonomy**
- 353-subtype effective taxonomy: the substrate enum minus 34 substrate-only realism
  subtypes, plus a 3-subtype overlay for what the substrate lacks.
- The 34 non-canonical subtypes never reach a manifest — 11 map to an unambiguous canonical
  equivalent, 23 are dropped rather than guessed at.

**Determinism**
- Same seed and version produce byte-identical output, including every manifest MD5.
  Manifests carry no generation timestamp, which is what keeps the guarantee verifiable.
- Three substrate-side leaks closed without editing the substrate: salted string hashing
  (`PYTHONHASHSEED` pinned via a single re-exec), wall-clock ZIP timestamps in `.docx`
  (repacked from the document date), and PDF `/CreationDate` and `/ID` (ReportLab invariant
  mode plus a length-preserving `/ID` rewrite that keeps xref offsets valid).
- Scan simulation seeded from `sha256(rng_seed, "scan:<index>")` rather than the substrate's
  `PYTHONHASHSEED`-dependent `hash()`.

**Quality**
- 225 pytest tests; `ruff` clean; no network access in any test.
- `examples/demo-caseload.yaml` — six cases, 276 documents, all four formats.

### Hardening (cross-model review)

**Date spine**
- Seeds whose injury sits too close to the fixed anchor for their own lifecycle are now
  **rejected at load time**, naming the field, the driver, the minimum runway and the latest
  acceptable date. Floors: 30 days (`intake`), 180 (`active_treatment` / `discovery`), 365
  (`medical_legal` / `pre_trial`), 540 (any real resolution), 720 (reconsideration or
  post-resolution lien litigation). Auto-derivation satisfies them by construction.
- `build_timeline` uses `max()` floors instead of bare clamps, and `CaseTimeline` enforces its
  ordering at construction. This fixes a spine inversion: a `2025-06-01` injury seeded as
  resolved produced `application_filed=2025-09-12` with `resolution=2025-06-01`, after which
  the reconsideration machine dated its petition 80 days before the Application.
- Sequenced chains (each lien track, the recon round trip) are fitted as a whole through
  `fit_track()` — ordering-preserving compression with strictly increasing dates — instead of
  being clamped date by date, which had stacked five lien documents on one day. A lien track
  with `post_resolution_litigation` extends past the anchor rather than compressing, because
  post-resolution lien practice genuinely outlives the case-in-chief.

**Determinism**
- Output is now byte-identical **across timezones and across days**, not only across processes
  on one machine. Under `TZ=Australia/Sydney` 55 of 289 demo files had differed from the same
  command under UTC.
- Three further leaks closed: substrate content computed from local `date.today()` (four sites
  rebound to the anchor by `pin_substrate_clock()`), `.eml` `Date:` headers built through
  local-zone `datetime.timestamp()` (rewritten to noon UTC by `normalize_eml()`), and Faker's
  clock-relative `date_of_birth` (the field is now owned by `case_context` and derived from
  `seed.rng("dob")`).
- Every timestamp derivation goes through `fixed_utc_datetime()` / `pdf_date_string()` /
  `zip_date_time()`; no `localtime`, `mktime`, `astimezone` or `.timestamp()` remains in a
  rendering path.
- `python -m wc_caseload_engine` added, and the `PYTHONHASHSEED` re-exec now re-enters through
  the module form, so a `python -m` start no longer degrades into the console-script form.

**Provenance & honesty**
- `provenance.substrateSha` on every manifest, plus `substrate_pin.txt` and a WARN (never a
  failure) when the substrate has moved off the pinned commit.
- `caseload_manifest.json` gains `subtypeCoverage` — `{distinctSubtypesEmitted, totalCanonical,
  percent}` — so a 353-subtype *vocabulary* is never read as 353 subtypes *emitted*.
- Synthetic-data markers on every artifact: PDF `/Subject` and `/Producer`, `.docx`
  `core_properties.comments`, and an `X-Synthetic-Data: true` header on `.eml`. All applied
  before hashing, so no manifest checksum is invalidated.

### Known limitations

- `profile.attorneys.applicant_firm` is recorded but not rendered: the substrate hard-codes
  the applicant firm on its letterhead.
- Lien and reconsideration subtypes render through substrate template *variants* rather than
  bespoke templates, so the two lien resolution flavours differ only by variant string.
- Format assignment is uniform across subtypes, so a pleading can be assigned `eml`. The seed's
  `format_mix` is the contract; constrain it per case with `output.formats` where that matters.
- Synthetic-data marking is metadata-only. A visible page watermark would have to come from the
  substrate's page templates, which this package does not edit.
- Library consumers do not get the `PYTHONHASHSEED` pin for free: only the CLI re-execs. Call
  `determinism.ensure_stable_hashing()` first, or set `PYTHONHASHSEED=0` before starting the
  interpreter.

---

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
