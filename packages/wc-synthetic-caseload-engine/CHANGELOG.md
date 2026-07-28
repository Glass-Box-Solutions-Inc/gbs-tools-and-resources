# Changelog

All notable changes to `wc-synthetic-caseload-engine` are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Fixed

**Second release-review round** (ticket **AJC-34**) — three reproduced findings from a second
independent GPT-5.6-Sol release review. Each is the previous round's fix examined one level
up, and each is closed with the exact reproduction kept as a regression.

- **The eval and UR/IMR chains are fitted, not clamped** (blocker). The first round added
  runway floors that reject a seed too short for its branch, and fixed the denial chain
  structurally — but the evaluation and UR/IMR chains were still built with independent
  per-date clamping, so a seed sitting *exactly* on its floor still collapsed. 84 of 90
  boundary-valid seeds produced a non-increasing chain, most with every document on the
  anchor: a QME panel request, the order appointing the panel and the report all 2026-01-01;
  an RFA, the UR decision answering it and the denial issuing from it likewise. Both chains now
  build unclamped and pass through `fit_track` in legal order (RFA < UR decision < IMR
  application < IMR determination; panel request < panel issuance < report), the same
  treatment the denial, lien and reconsideration chains already had. `MEDICAL_TREATMENT_DENIAL_UR`
  also stopped being dated *on* the UR decision — an unconditional two-document collapse
  independent of runway — and now follows it by the one to two working days LC 4610(g)(3)(A)
  allows.
- **A pre-set `WC_CASELOAD_HASH_PINNED` no longer waives the hash-seed check** (major). The
  previous round made `PYTHONHASHSEED=0` the only accepted value; the guard still read its own
  re-exec sentinel *first*, so anything that pre-set that variable — a wrapper script, a CI job
  copying a child's environment — reinstated the bypass, and `=1` versus `=2` again produced
  two different caseloads. The seed is now checked before the sentinel, and the sentinel is
  demoted from a certificate of stability to a hop counter bounded by `MAX_REEXEC_HOPS` (2),
  past which the run fails with an error naming the variable rather than exec-looping.
- **A seeded employer industry now reaches the whole employer** (medium). `profile.employer.industry`
  was applied *after* the coined-name substitution and the substrate's position draw, so it
  changed the department and nothing else: `rng_seed=2` with `industry: healthcare` produced a
  construction-suffixed company name, a healthcare department and a construction job title. The
  industry is applied before anything derives from it, and the position is re-drawn from the
  seeded industry's own titles (read live from the substrate's `EMPLOYER_TEMPLATES`). A seed
  naming `applicant.occupation` still outranks it, and a free-text industry the substrate has
  no titles for degrades to the neutral suffix pool rather than raising.

**Release-review round** (ticket **AJC-34**) — five reproduced findings from an independent
GPT-5.6-Sol release review, each closed with a regression test using the exact reproduction.

- **Real-organization substitution now covers every substrate pool.** It covered carriers and
  defense firms; `data/wc_constants.py` has four organization pools, and `ALL_EMPLOYERS`
  (Safeway, Costco, Kaiser Permanente, UPS, City of Los Angeles) and `MEDICAL_FACILITIES` were
  reaching output under `zeroRealPii: true` — the employer being the *named defendant* in
  every caption. All four are now coined with seed-stable names, the employer suffix matching
  the substrate's own industry key. `castProvenance` no longer misfiles a pool draw as a Faker
  draw. Seed-declared names are kept (the seed is the contract) but checked against the
  denylist with a `cast.seed_name_on_denylist` warning.
- **`name_denylist.py`** — the denylist moved from `tests/data/` into package data so the
  engine and the anti-probes read one list, and `substrate_organization_pools()` now reads the
  substrate's pools **live**, so the sweep cannot go stale when a pool grows upstream.
- **Runway validation now accounts for lifecycle branches.** A 30-day `intake` + `denied` seed
  validated and then dated its denial letter, Application and Declaration of Readiness all on
  the anchor. `seeds.runway_demands()` adds floors for `claim_response: denied` (90d),
  `ur_dispute` (65d), `imr` (120d) and `eval_type` qme/ame (240d), each derived from the
  minimum its own encoded chain can be drawn at, and the error names the binding branch.
- **The denial-response chain is fitted, not clamped** — it is a sequence, so it goes through
  `fit_track` like the lien and reconsideration chains.
- **`PYTHONHASHSEED` is only trusted when it is exactly `0`.** Any other value — including
  `random`, and including two different salts like `1` and `2` — now re-execs. `1` and `2`
  previously produced two different caseloads from one seed. `WC_CASELOAD_NO_REEXEC` still
  opts out, now with a warning naming the consequence.
- **Reconsideration briefing is ordered structurally.** The order was drawn independently of
  the briefing schedule and the chain sorted by date, producing a Board ruling filed before
  the reply it had considered. The chain is now built in legal order and the dates fitted to
  it; the ruling is floored at the day after the last brief.
- **`__pycache__` no longer escapes `--out`.** `sys.dont_write_bytecode` is set on the first
  executable line of `__init__.py` and `PYTHONDONTWRITEBYTECODE=1` rides through the re-exec;
  13 `__pycache__` directories across the package and substrate source trees became zero in
  the substrate and one interpreter-written file in the package.

### Documented

- Post-resolution lien tracks extending past the case horizon under
  `post_resolution_litigation: true` is **intended** behaviour, now stated in README with the
  floor/ceiling table and asserted at its boundary: without the flag the horizon still binds.
- The caption assertion's exemption is now keyed to the *template* (`ClientIntake` renders no
  case caption for any of the ~60 subtypes routed to it) rather than to a growing subtype
  list, with a companion test capping the exemption at a third of the case file.

### Added

**Perspective — applicant vs defense case files** (ISC-75..84, ticket **AJC-34**)
- `CaseSeed.perspective: applicant | defense`, a top-level field defaulting to `applicant`.
  Every seed written before it loads, plans and renders unchanged.
- `perspective.py` — the whole feature as data: `WORK_PRODUCT_SWAP` (privileged analysis
  renamed to the file owner's vocabulary), `PERSPECTIVE_PROFILES` (per subtype-or-type
  `{applicant_weight, defense_weight}` emission multipliers, plus a `floor` for paper a
  multiplier cannot conjure from zero), and author/recipient role resolution.
- Defense files emit `DEFENSE_CASE_ANALYSIS` / `DEFENSE_MSC_STATEMENT` / `DEFENSE_TRIAL_BRIEF`
  in place of `CASE_ANALYSIS_MEMO` / `SETTLEMENT_VALUATION_MEMO` / `TRIAL_BRIEF`, carry ~2.5x
  the carrier's claims-administration paper and always carry investigation/surveillance, and
  carry no client intake or physician advocacy letters at all.
- An explicit `documents.overrides` entry still forces applicant-only paper into a defense
  file through the existing forced-emission path, with a WARN naming the perspective.
- `manifest.json` carries `perspective`; `caseload_manifest.json` carries it per case plus a
  `perspectiveCounts` summary.
- `examples/demo-caseload.yaml` gains a seventh case — `whitaker-defense-qme-surveillance`.

**Perspective changes no case fact.** Same `rng_seed` → identical cast (both firms exist in
both files), ADJ number and lifecycle dates across perspectives. Enforced structurally: the
value never enters a fact-feeding RNG salt, and the applicant path is an identity function
that draws no randomness.

### Known limitation

- The substrate hard-codes `Martinez & Associates, APC` on the docx letterhead, so `.docx`
  files in a **defense** case file show the applicant firm's letterhead. Manifest, seed,
  subtypes, roles and all other formats are unaffected. Same root cause as the existing
  `profile.attorneys.applicant_firm` limitation; the fix belongs upstream.

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
