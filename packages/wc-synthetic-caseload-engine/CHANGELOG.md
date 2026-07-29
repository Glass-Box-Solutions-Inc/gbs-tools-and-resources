# Changelog

All notable changes to `wc-synthetic-caseload-engine` are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added — treatment trajectory and diagnostics depth (ticket **AJC-37**, Phase 2)

Phase 1 gave the case a ledger. It could say what was imaged and whether an
operation happened, and the documents agreed with it. What it could not say was
what the *course of care* looked like — and that is the axis most real files
turn on. A defense file is usually built around a treatment gap; an applicant
file is usually built around continuity. The engine could render neither,
because it had no notion of either.

- **`scenario.treatment {status, providers}`.** `ongoing`, `discharged`, `gap`,
  `never_treated`. The status is resolved once at plan time, like surgery, and
  both the planner and the ledger read that one answer.

  `never_treated` suppresses at the *planner*, filtering candidates rather than
  making the seed author write thirty `exclude:` keys. What survives is named
  explicitly in `NEVER_TREATED_TIER` — the first-report tier, because an
  applicant who never treated still generated an injury report and a claim form,
  and may well have gone to an emergency department once. An allowlist rather
  than a denylist: a subtype missing from a denylist silently survives and
  contradicts the seed, whereas one missing from an allowlist is merely absent
  from a file the seed already says is sparse.

  `gap` opens a hole in the ledger's visit series, drawn on the `facts:`
  namespace and **clamped to the runway the timeline actually has**. A case that
  settles four months after injury cannot hold a seven-month gap; it gets a
  shorter one rather than none. The first version of this appended a gap to a
  full visit schedule, and every gap fell past the horizon and vanished —
  producing gap-status cases with no gap in them.

  `discharged` emits a discharge summary at the discharge date and drops any
  treating document that post-dates it.

- **Trajectory instead of per-document mood.** The substrate drew a status
  phrase per report from a flat list, so a three-PR case could read "worsening
  despite treatment", then "slowly improving", then "worsening" again — each
  document plausible, the sequence incoherent. The ledger picks an arc and walks
  it monotonically, holding at the end rather than wrapping.

- **`surgery: recommended | denied_by_ur`.** Both mean no operation happened and
  both still name a CPT, because a procedure was requested. `denied_by_ur`
  requires a `lifecycle.ur_dispute` and is **refused with an actionable error**
  when one is absent rather than auto-enabling it: a UR dispute pulls in an RFA,
  a determination and an IMR window, and the seed is the contract.

- **The UR chain names the procedure.** `UtilizationReview._build_request_details`
  drew one to three CPTs from the whole code table, so a determination on a
  lumbar case could adjudicate a cervical MRI. When the ledger names a
  procedure, the RFA, the determination and the treating report all name that
  one.

- **Per-study body-part attribution (ISC-110).** The imaging report now prints
  the region *this* study covered. The ISC-90 body-part clause, deferred in
  Phase 1 because the substrate prints every injured region and attributes the
  study to none of them, is closed by adding the line rather than intercepting a
  draw — there was no draw to intercept.

- **The QME history is governed (ISC-111).** A third independent modality draw,
  in the history narrative, which is how a QME could announce an MRI in
  paragraph two and review only X-rays four pages later.

- **A modality audit table (`modality_audit.py`).** Every substrate site that
  names a modality, each either governed by an override or documented with the
  reason it is left alone — and a test that greps the substrate and fails if it
  finds a site the table does not list. Phase 1 governed the diagnostic report
  and believed the job done; the QME turned out to name modalities in three
  other places, each found one failing test at a time. This is the alternative
  to discovering the fourth the same way.

### ⚠️ Compatibility — version bumped to 0.4.0

`0.3.0` → `0.4.0`.

1. **Two newly-governed subtypes move; nothing else does.** Regenerating the
   demo at 0.3.0 and at this commit: 331 documents both times, identical
   filenames, no documents added or removed, **307 byte-identical and 24
   changed**. All 24 are registry-covered: `QME_REPORT_INITIAL` (16) and
   `QME_REPORT_SUPPLEMENTAL` (5) from the history override, and
   `TREATING_PHYSICIAN_REPORT_PR2` (3) from the trajectory override. **Zero
   unexplained.**

   No demo seed carries a `scenario` block, so this measures exactly what it
   should: the byte cost of the new *governance*, with none of the new knobs
   engaged.

2. **The registry grew from nine subtypes to fifteen.** Added:
   `DISCHARGE_SUMMARY`, `MEDICAL_TREATMENT_AUTHORIZATION`,
   `MEDICAL_TREATMENT_DENIAL_UR`, `UTILIZATION_REVIEW_DECISION`,
   `UTILIZATION_REVIEW_DECISION_REGULAR`,
   `UTILIZATION_REVIEW_DECISION_EXPEDITED`.

3. **`DISCHARGE_SUMMARY` no longer renders as an operative report.** The
   substrate maps it to `OperativeRecord` with a `discharge` variant the
   template never reads, so every discharge summary was headed "OPERATIVE
   REPORT". On a discharged case with no surgery that is not a cosmetic problem:
   it is an operation appearing in a file whose ledger denies one.

4. **The operative-document floor applies to *stated* surgery only.**
   `scenario.surgery: performed` now guarantees at least one operative document
   (closing ISC-92.1, and with it the validator's forward direction). A
   *derived* surgery keeps the substrate's probabilistic emission untouched,
   which is precisely what leaves 0.3.0 bytes alone for every seed that states
   nothing. `validate` tells the two apart by reading the seed beside the
   manifest.

5. **The ledger publishes a `treatment` block** — status, trajectory, discharge
   date, gap bounds — all governed, all rendered somewhere.

6. **Overriding a substrate exclusion now warns.** Stating surgery on a death or
   psych claim is still honoured, but it lands in `manifest.warnings` with the
   denylist and doctrine-hook warnings. The demo is unaffected: no demo seed
   states surgery, and its warning count is unchanged at 2.

### Fixed — guards that bound on one path only (PR #24 review)

Three defects of one shape: the explicit path rejected actionably and the
adjacent path passed in silence. A guard that fires only when the author already
spelled out the problem is a guard against typing, not against incoherence.

7. **`never_treated` now binds on derived liens.** Naming a hospital claimant was
   rejected; leaving `claimants: []` with `count: 6` loaded cleanly and planned
   `LIEN_HOSPITAL` and `LIEN_PHARMACY` into a file whose ledger says nobody
   treated. The derived pool now drops treatment claimants — dropped rather than
   rejected, because nobody *asked* for a hospital lien, the engine was about to
   invent one. Stated conflicts stay errors.

8. **`denied_by_ur` now requires the denial to stand.** The guard checked
   `ur_dispute.enabled` and not `decision`, so `decision: overturned` loaded with
   zero warnings and produced a file holding an authorization *and* a treating
   report describing the same request as denied and under appeal. `overturned` is
   now refused — and so is an unset decision, which maps to the substrate's
   `rng.choice(["approved", "denied"])` and can therefore become an approval on
   some seeds and not others. The same contradiction, one level down and
   non-deterministic.

9. **`never_treated` publishes an empty record.** It was publishing a
   four-provider treating roster and an initial visit as governed ledger facts. A
   reported injury is not a treatment visit, and a published fact reads as a
   verified one. Subpoena attribution degrades to the substrate's own
   treating-physician fallback, which the renderer already took whenever the
   roster is empty.

10. **The `denied_by_ur` error suggested a value outside the enum.** It said to
    add `decision: denied`; the legal values are `upheld` and `overturned`, so
    following the message produced a second error. An error that sends the reader
    somewhere that also fails is worse than a terse one. A test now *follows*
    each actionable message's suggested edit and asserts the seed then loads.

11. **The modality audit walked third-party code.** `EXCLUDED_PATHS` lacked
    `site-packages/` and the virtualenv directories, so a substrate checkout with
    its own venv dragged faker's "Diagnostic radiographer" into the audit — a
    gate whose result depended on the reviewer's directory layout rather than on
    the code, and the reason a clean local run did not reproduce for them.

12. **Audit rows are no longer vacuous.** Nothing asserted that a row's marker
    matched any real line, so a row could claim to govern a site that did not
    exist while the file-level checks still passed. Adding the per-row assertion
    immediately found five such rows, which have been removed.

### Known scope limits (Phase 2)

- **A gap is clamped by the timeline.** Every lifecycle this engine builds has a
  runway shorter than the largest gap in the pool, so seed-level gaps are
  routinely shortened. The unclamped path is tested directly against
  `_derive_visits` with a long horizon, because no seed can reach it.
- **Shared content pools are still ungoverned.** `content_pools.py`,
  `ama_guides_content.py` and `deposition_exchanges.py` name modalities inside
  narrative and rating text drawn by many templates. Governing them needs a
  per-draw ledger channel rather than a template override — Phase 3. Every one
  of those sites is listed in the audit table with that reason.
- **Prior-provider records are deliberately ungoverned.** Subpoenaed records
  describe medical history predating the claim, which the ledger does not model.
  Forcing them would assert that the applicant's entire medical past agrees with
  one injury's imaging.

### Added — the CaseFacts ledger (ticket **AJC-37**, Phase 1)

Before this, every template that wanted a clinical detail invented one. A QME
drew `random.choice(["MRI", "X-ray", "CT scan"])` per body part and asserted
imaging no diagnostic report in the same case had produced; the diagnostic
report drew its own modality independently; and `has_surgery` gated six document
*rules* while reaching no document *content*, so post-operative progress reports
described conservative care — "surgical" was not even in the choice list.

Nothing was wrong with any single draw. What was missing was a place for the
case to agree with itself.

- **`case_facts.py` — the ledger.** Derived once per case at plan time from the
  seed and the timeline: diagnostics performed *and deliberately absent*
  (modality + body part + date), surgery status with a chosen CPT, providers,
  a dated visit series, MMI, WPI/PD. Carried on `CasePlan`, published in the
  manifest as `caseFacts`, and written beside the seed as `case_facts.yaml` —
  the seed states what was asked for, the ledger states what was decided.

- **`scenario:` seed block (Phase-1 subset).** `scenario.diagnostics
  {performed, absent}` and `scenario.surgery`. Entries accept a bare modality
  (meaning the primary body part) or `{modality, body_part}`. Unknown modalities
  and performed/absent overlap are refused at load with actionable errors; the
  overlap check is body-part aware, because a study performed on one region and
  absent on another is coherent, not a clash.

- **Fact-aware template registry.** `FACT_AWARE_TEMPLATES` maps nine subtypes to
  engine-owned subclasses that override the narrowest method rolling the
  offending draw and delegate everything else to the substrate, which stays
  read-only. Unregistered subtypes take the original dispatch unchanged, and
  the manifest keeps naming the substrate class — the subclass renders the same
  document, it is not different provenance.

- **Determinism re-verified at this version.** The demo caseload generated
  three times — twice under UTC, once under `TZ=Australia/Sydney` — produced
  331 files with an identical tree digest (`603fd9f6…`) and zero differing
  files across all three pairs.

### ⚠️ Compatibility — version bumped to 0.3.0

`0.2.0` → `0.3.0`. Bytes are stable within a version (and within a
`substrateSha` — see README), and this release moves some.

1. **Two sources move bytes, and only two.** Measured by regenerating the demo
   caseload at `867ea88` (the merged 0.2.0 tree) and at this commit: 331
   documents both times, identical filenames, **303 byte-identical, 28
   changed**. Every one of the 28 traces to a source declared below:

   - **23 are registry-covered** — `QME_REPORT_INITIAL` (16),
     `QME_REPORT_SUPPLEMENTAL` (5), `TREATING_PHYSICIAN_REPORT_PR2` (2). These
     are templates this release deliberately subclasses.
   - **5 are `SUBPOENAED_RECORDS_MEDICAL`**, which the registry does *not*
     cover. They moved because of the provider round-robin in item 4 — a
     context key, not a template override. The substrate's
     `SubpoenaedRecords._select_provider` has always read `provider_index`;
     the engine path never set it, so every packet silently fell back to the
     treating physician. Setting it correctly is the fix, and the fix changes
     bytes. This is intended, not leakage.

   The distinction matters: a byte change is acceptable when it is *named*.
   Anything outside these two sources would be an unaccounted-for change and a
   defect. There is none — a probe classifies all 28 by source and fails on any
   remainder. One covered document was unchanged: a treating report on a case
   with no surgery, which takes the substrate path verbatim by design.

   That is structural rather than lucky. Every ledger draw is namespaced under
   `facts:` via `derive_seed`, so it cannot perturb a stream an existing draw
   consumes; the renderer re-seeds the global stream per document
   (`render:{index}`), so a registered template's content cannot shift its
   neighbours; and `_load_template` only consults the registry when a ledger is
   present.

2. **The registry-covered subtypes (nine).** `DIAGNOSTICS_IMAGING`,
   `OPERATIVE_HOSPITAL_RECORDS`, `QME_COMPREHENSIVE_REPORT`,
   `AME_COMPREHENSIVE_REPORT`, `QME_REPORT_INITIAL`, `QME_REPORT_SUPPLEMENTAL`,
   `SUPPLEMENTAL_QME_AME_REPORT`, `TREATING_PHYSICIAN_REPORT_PR2`,
   `TREATING_PHYSICIAN_REPORT_PR4`.

3. **Surgery is resolved once, and `scenario.surgery` actually reaches the
   plan.** `case_facts.resolve_has_surgery` is the single answer; both
   `CaseParameters.has_surgery` (which gates whether operative documents are
   planned) and the ledger (which decides what documents say) read it.

   They used to be computed independently, and the review caught what that
   allows: `performed` plus a false coin produced a ledger asserting an
   operation with no operative record behind it, and `none` plus a true coin
   left an operation rendered that the ledger denied. The headline knob reached
   the prose and not the plan.

   A seed that says nothing still gets the substrate's 35% coin off the same
   `clinical` stream at the same position, reproducing the psych rule term for
   term, so unspecified seeds keep their bytes. The coin is drawn even when the
   scenario decides the answer, and discarded — skipping it would move every
   later draw on that stream the moment a seed stated `surgery:`, turning a
   content knob into a silent byte change across unrelated documents. A stated
   value also beats the substrate's death/psych exclusions: refusing silently
   would be the same defect in a different place.

4. **Subpoenaed-records packets are now answered by different providers.**
   Each packet takes `provider_index = packet_ordinal % len(providers)` over
   the ledger's roster, which is sourced from `cast.case.prior_providers` — the
   same list the substrate indexes into. Before this, a case with four record
   subpoenas returned four packets from the same physician, which is not what
   a subpoena to four custodians produces. This is the change behind the five
   `SUBPOENAED_RECORDS_MEDICAL` documents in item 1.

5. **One CPT per case, across every document that names it.** The ledger picks
   from the substrate's own body-part-coherent pool
   (`operative_record._select_surgical_cpts`), and the operative record, QME
   and treating report are all pinned to that choice. Previously each drew
   independently, so a case could be operated on at one spinal level and
   followed up at another.

6. **The manifest publishes only facts a document renders.** `caseFacts` used to
   carry `wpi`, `pd`, `mmiDate`, `visits`, and a body part and date per
   diagnostic — all derived, none rendered anywhere. A published fact reads as a
   verified one, so publishing unrendered ones let the manifest state things its
   own documents contradicted. The governed set is now declared in
   `case_facts.GOVERNED_LEDGER_FIELDS` and asserted by test; the rest stay on
   the model for later phases.

   Diagnostics are also published one entry per *modality* rather than per
   study, since without body parts two entries for the same modality with
   opposite `performed` flags would read as a contradiction rather than as
   "scanned one region, not the other".

7. **`validate --out` now checks the ledger.** It requires `caseFacts` and
   `case_facts.yaml`, cross-compares the two published copies, and enforces what
   is visible from the output alone: modalities are legal vocabulary, no
   modality is both performed and absent, no ungoverned field is published, a
   performed surgery names a CPT, and no operative document sits in a case whose
   ledger denies surgery. Malformed, missing and self-contradictory ledgers fail
   rather than being skipped.

8. **EMG is no longer assignable to an imaging report.** The imaging template
   selects its technique paragraph from the exam type and falls through to
   radiographic projections for anything it does not recognise, so a forced EMG
   rendered a nerve conduction study in X-ray language. Derivation and
   assignment are now restricted to `IMAGING_MODALITIES` (`mri`, `ct`, `xray`) —
   the same treatment `labs` already had. EMG remains a ledger fact and the QME
   still governs its presence and absence.

### Known scope limits (Phase 1)

Stated because the coherence harness asserts exactly what the code enforces and
nothing wider.

- **The absence rule is scoped to governed documents.** No `DIAGNOSTICS_IMAGING`
  document reports a study the ledger calls absent; the QME *records* the
  absence in its diagnostic review rather than silently omitting it; and the
  QME's neurology exam drops its electrodiagnostic paragraph when the ledger
  says no EMG was performed. That last one took a second override
  (`_build_neuro_exam`) because it is a different method from the diagnostic
  review — the absence rule was initially scoped around it, and closing it
  properly was cheaper than documenting the hole.

  It is still not asserted over *every* document: the substrate's AMA-guides
  and narrative pools name modalities inside impairment language, which needs
  its own overrides in Phase 2. Claiming the broader rule now would assert a
  guarantee the code does not make.
- **The treating-report rule is about the treatment plan.** A post-surgical case
  gets a plan describing post-operative rehabilitation and naming the CPT. The
  word "conservative" is not banned file-wide: it is legitimate in history and
  pre-operative sections this override does not govern.
- **`DIAGNOSTICS_IMAGING` governs modality, not date.** The document keeps its
  planned date so filename, manifest and content stay consistent; the ledger
  entry's date is informational until the planner learns to place imaging
  documents on ledger dates.
- **A performed surgery does not guarantee an operative document.** The
  validator enforces the rule one way only — an operative record in a case whose
  ledger denies surgery is a failure — because the converse is not a property of
  this system. The substrate's lifecycle walk gates several rules on
  `has_surgery` without ever guaranteeing an `OPERATIVE_HOSPITAL_RECORDS`
  document, and two of the seven demo cases resolve surgery true while emitting
  none, with no document controls and nothing unusual in the seed. That is a
  real coherence gap and it belongs to the document set rather than the ledger;
  asserting the biconditional here would only make `validate` red on this
  package's own examples. Phase 2.
- Phase 1 carries `surgery: none|performed` only. The ticket's `recommended` and
  `denied_by_ur` need UR wiring that belongs with the treatment phase.
- No adjuster/attorney personas, discovery-volume knobs, or treatment-gap
  statuses — Phases 2-4.


### ⚠️ Compatibility — version bumped to 0.2.0

`0.1.0` → `0.2.0`. The reproducibility guarantee is *bytes are stable within a
version*; three behavioural changes below cross that line, so the version moves
with them. A caseload regenerated at `0.2.0` should be compared against a
`0.2.0` baseline, not a `0.1.0` one.

1. **Auto-derived output moves for 75 of 975 measured seeds — and only those.**
   `_derive_body_parts` now rejects repeats, so any derived case that previously
   received the same region twice gets a different part list, and everything
   drawn after it shifts. The fix was deliberately written to shuffle the
   fallback pool *behind the same condition it has always been behind*, so a
   seed whose category pool already held enough distinct parts consumes exactly
   the RNG it used to. Verified by deriving 975 seeds under the last released
   behaviour — `seeds.py` and `doctrine.py` as of **`fefa3a4`**, the final
   `0.1.0` tree — and again under this one: 900 byte-identical, and the 75 that
   changed are exactly the 75 that previously carried a duplicate. (`fefa3a4`
   rather than this commit's parent: the parent is the in-flight commit that
   introduced the unconditional shuffle, so it is not a `0.1.0` baseline. The
   comparison is clean because `seeded_hooks` was never populated during
   derivation, which makes the `gfpa` gate change a no-op on that path.) An
   earlier draft shuffled unconditionally and would have moved **all 975**; that
   was measured and rejected rather than disclosed.

   The two-revision probe cannot live in the test suite, but the property that
   produced the result can: `TestTheCommonPathConsumesTheRngItAlwaysDid` counts
   shuffle calls through a wrapping RNG and pins them at one when the category
   pool suffices and two when it comes up short. Re-introducing the
   unconditional shuffle fails all three of its cases.

2. **Seeds that used to load are now refused.** `injury.body_parts` naming the
   same region twice raises at load. Both shipped specs are clean, and a test
   keeps them that way, but a hand-written seed relying on the old leniency will
   now fail with an actionable error naming the case.

3. **`psyche` is matched case- and whitespace-insensitively.** A seed spelling it
   `Psyche` or `" psyche "` previously did *not* register as a psychiatric claim,
   so `lc3208_3_psych` and `gfpa` warned as unsupported on it. Such a seed now
   registers and stops warning. This is a correctness fix — the seed plainly
   meant `psyche` — but it is a visible behaviour change for anyone whose
   expected-warning fixtures encode the old spelling sensitivity.

### Fixed — doctrine gate coherence (ticket **AJC-35**, items #23–#25)

Three gates were letting through cases they describe as impossible. Each was
reproduced as a failing test first.

- **#23 — a warning named a value the schema rejects.** `_RATING_PREREQUISITE`
  told users `lifecycle.eval_type` could be `qme, ame or ime`; `EvalType` is
  `Literal["qme", "ame", "none"]`. Five hooks shared that description, so five
  warnings advised a fix that fails validation. Corrected, and the existing
  wording is now gated: a sweep reads each `Literal` alias and asserts that
  every value a prerequisite description enumerates is legal for the field it
  names. The defect had already escaped twice — here and in the user guide that
  copied it — which is the signature of something needing a gate rather than
  another correction.

  Scope is narrow and documented as such: the matcher reads the one prose form
  these descriptions actually use (`must be` / `must not be` / `to be` followed
  by a comma-or-`or` list) against a hand-maintained map of three fields. It is
  a regression gate on the current wording, **not** a general prose checker — a
  description invented in a new phrasing, or naming a fourth field, is not
  inspected. Two guards stop that from becoming silent vacuity: the exact set of
  descriptions the matcher reaches is pinned, so lost coverage fails loudly
  rather than passing on an empty match, and planted-bad-value cases in each
  prose form prove the matcher can fail at all.

- **#24 — `gfpa` could be satisfied by another hook.** Its predicate accepted
  `"lc3208_3_psych" in facts.seeded_hooks` as a substitute for a psychiatric
  claim. Removed as **incoherent**, not merely weak: on a lumbar-only seed
  naming both hooks, `lc3208_3_psych` failed its own gate and warned while
  `gfpa` — whose entire subject is defending against the claim `lc3208_3_psych`
  describes — passed silently by pointing at the hook that had just failed. A
  defence cannot be better supported than the claim it answers.

  The branch's strongest defence was measured before removing it: `lifecycle_bridge`
  does force `has_psych_component=True` when the hook is seeded, and that does move
  content — psychiatric documents appeared for 46 of 60 rng seeds, against 0 of 60
  with no hook. But a genuine `psyche` body part scores *identically*, the same
  46/60 on the same barren seeds, because the substrate's psych document rules are
  probabilistic either way. The branch bought no content capability the primary
  branch lacks; it only let a seed skip recording the claim.

  `DoctrineFacts.seeded_hooks` is deleted rather than merely unread, so a gate that
  answers differently depending on which *other* doctrines were seeded is now
  unrepresentable. The unsupported-`gfpa` warning no longer advises the removed
  route.

- **#25 — a body part could be claimed twice, and often was.** `[lumbar_spine,
  lumbar_spine]` loaded fine and then counted as two for `benson` and `kite`,
  whose premise is two *distinct* impairments — so Kite could argue a synergistic
  effect between a region and itself, silently. Four layers now:
  `CaseSeed` rejects a repeated part at load with an error naming the case;
  `InjurySpec` enforces the same invariant on its own, because it is public API
  (it is in `__all__`) and a bare construction must not hold a state the rest of
  the engine treats as impossible; `DoctrineFacts.body_part_count` counts
  distinct parts (case- and whitespace-insensitive) at both construction sites;
  and `_derive_body_parts` now delivers the distinctness its docstring already
  promised.

  The two validators are not redundant. Pydantic validates a nested model before
  the outer model's `after` validators, so an `InjurySpec`-only check would win
  the race and produce a message without the case name — and in a caseload of
  thirty, "some injury has a duplicate" is not actionable. The seed-level check
  therefore runs `mode="before"`, ahead of the nested construction, and the
  ordering is pinned by a test rather than left to be rediscovered.

  That last one was a live bug, not a precaution: `BODY_PART_CATALOG` lists
  `psyche` twice, `head` twice and `internal` three times *within their own
  category*, so shuffling a category pool and slicing it returned repeats. About
  8% of auto-derived seeds carried one (75 of 975 measured). Without this fix the
  new validator would have turned a silent modelling error into a hard crash of
  `auto:` derivation. A narrow category now yields fewer parts rather than
  repeats.

### Known gap — `firefighter_presumption` is never auto-drawn

Found while fixing the above and **left unfixed deliberately**. `derive_case_seed`
builds `DoctrineFacts` without `occupation` or `industry` because a derived seed
carries no `profile` block at all — the cast is drawn later, in `case_context`,
and never written back. `_SAFETY_MEMBER_PREREQUISITE` reads exactly those two
fields, so the hook is filtered out of every draw: 0 occurrences across 975
derived seeds, while the other thirteen appear between 6 and 60 times.

This fails *closed* — derivation never produces a case arguing a presumption it
cannot support — so it is a coverage gap rather than the incoherence class above.
Closing it needs an occupation/industry distribution and a profile in the
materialized seed, which changes the bytes of every auto-derived caseload; that is
auto-derivation work, not gate work, and is tracked as its own AJC-35 item.
`TestFirefighterPresumptionCannotBeAutoDrawn` pins the current behaviour so the gap
cannot close or widen silently, and explicitly-seeded firefighter cases are
unaffected.

### Added

**Operator user guide and a doctrine showcase caseload** (ticket **AJC-36**).

- **`docs/user-guide/index.html`** — a 14-section operator guide, brought current with the
  merged engine. New material: *Doctrine hooks* (the two registers and their headings, which
  subtypes each hook targets, `contentFlags` provenance, the fourteen citations and markers,
  prerequisite gating, and the determinism properties of injection); the *needed-seeds
  reference*, one block per hook giving the doctrine, its citation, exactly what the seed must
  establish, a minimal runnable seed and the subtypes that carry the language; *manifest
  truthfulness* (`documentCount` vs `plannedDocumentCount`, `petitionDate`/`orderDate` vs their
  `planned*` twins, the `warnings` array, and `zeroRealPii` as a computed measurement of
  `castProvenance` rather than an asserted constant); and *control-key canonicalization*,
  including the alias-collision check that catches one subtype written two ways.
- **`examples/doctrine-showcase.yaml`** — six cases grouped by prerequisite that exercise all
  fourteen hooks with **zero warnings** and no `documents.overrides` anywhere: every hook
  reaches a target document through its case's own lifecycle. Verified at 210 documents,
  `validate --out` clean with zero fallbacks, and every hook's marker present in a rendered PDF.
  Four assertions in `tests/test_doctrine_content.py` pin it — every hook seeded, the run
  warning-free, every hook landing on a document, and no forced subtypes — because a showcase
  that silently stops showcasing is worse than none.

### Changed

- Corrected stale claims in the guide against the merged code: the *Doctrine-hook content depth*
  limitation (content injection now ships and is verified end to end, replaced by the two limits
  that are actually real — the prose is fixed text, and some gates approximate their doctrine);
  the demo caseload totals (7 cases / 331 documents / 83 subtypes, not 6 / 276 / 78); and the
  per-case manifest field lists, which omitted `contentFlags`, `template`, `fallback`,
  `castProvenance`, `warnings` and every `planned*` field.
- Scoped the README's doctrine-prose claim from "no paragraph anywhere asserts a fact its own
  gate does not establish" to "no paragraph asserts the doctrinal predicate its gate
  approximates" — the narrower statement is the one the tests actually enforce (AJC-35 #22).
- **Derived the exact/approximation split for all 14 doctrine gates instead of counting it.**
  The README table named four (`benson`, `sibtf`, `lc4664_prior_award`,
  `firefighter_presumption`) and explicitly grouped `gfpa` with `lc3208_3_psych` as "gated on
  exactly what it needs" — but `gfpa`'s doctrine needs a good faith personnel action while its
  gate establishes only a psychiatric claim. Reclassified by one stated test, applied to all
  fourteen: **does the truth of the gate entail the truth of the doctrinal predicate?** The
  answer is **seven exact, seven approximations**, the three additions being `gfpa`,
  `going_and_coming` and `ab5_dynamex`. The approximations turn out to have two shapes, and the
  second is what three successive versions of this table missed: four are missing a discrete
  *entity* the seed has no field for, three are missing the *nature of the dispute*
  (`claim_response: denied` says a claim is contested but never why). The README now carries one
  authoritative 14-row table — predicate, gate, verdict — and the guide describes the class and
  points at it, holding no enumeration or count of its own.
  `BANNED_ASSERTIONS` already carried entries for all three additions, so the shipped prose was
  correct throughout; only the table was stale. No doctrine content changed.
  Every cell is written against the predicate lambda rather than its human-readable
  `description`, and the two **disjunctive** gates now spell out both branches. `gfpa` is
  satisfied by `psyche` in `body_parts` **or** by `lc3208_3_psych` appearing in the same seed's
  `doctrine_hooks` — a branch that establishes no case fact at all, since naming one hook
  satisfies another hook's gate (confirmed live: `[lc3208_3_psych, gfpa]` on a lumbar-only claim
  reports `gfpa` supported with zero warnings). `firefighter_presumption` is satisfied by
  `industry == "government"` **or** a substring match of `fire`/`police`/`peace officer`/
  `sheriff`/`deputy` against the occupation, so `Deputy Comptroller` passes. Both are documented
  as defects of the gate, not of the prose; the `gfpa` weakness is ticketed on the merits in
  AJC-35.
- Corrected the guide's `distinctTemplates` description: the implementation counts
  `template_label(class_name, variant)` strings, so it counts recorded **labels**, not template
  classes. `LIEN_RESOLUTION` and `LIEN_STIPULATION_AGREEMENT` share the one `Stipulations` class
  but record `Stipulations/lien_resolution` and `Stipulations/lien_stipulation` and count as two
  — the opposite of what the row previously claimed.

### Fixed

**Cross-model release review — six blocking findings** (ticket **AJC-34**). Each was reproduced
as a failing test before it was fixed.

- **A denylist hit no longer inherits `zeroRealPii: true`.** `case_context` called
  `warn_if_denylisted(...)` and discarded the return, so a seed naming a real organization was
  recorded as provenance `seed` — a value inside `SYNTHETIC_PROVENANCE` — and the manifest went
  on asserting zero real PII about a name the engine had itself just identified as real. The
  only evidence was a log line, and a corpus does not ship with the log. Such a field is now
  `seed_denylisted`, which is outside that set and therefore computes the flag false, and the
  finding travels through `CaseCast.warnings` into `plan.warnings` and the manifest. Retention
  is unchanged: the seed is still the contract, now loudly. The pre-existing test asserting the
  old behaviour asserted the bug, and was rewritten.
- **A non-canonical control key can no longer reach a manifest.** Control keys were checked only
  by `wc-caseload validate --spec`, which `generate` never calls, and the check admitted
  substrate-only vocabulary. `planner.normalize_control_keys` now runs at plan time:
  substrate keys with an unambiguous equivalent are translated through `SUBSTRATE_TO_CANONICAL`
  (so `FAX_COVER_SHEET` emits as `FAX_CORRESPONDENCE`), and anything else — an unmapped
  substrate key, a typo — raises `ControlKeyError` naming every offending key and the control
  that holds it. `build_case_plan` additionally fails closed before constructing any
  `PlannedDocument`, so a future path that skips normalization still cannot write a
  non-canonical subtype.
- **Lien and reconsideration summaries count emitted documents, not proposals.** Both machines
  run before perspective suppression and control resolution, and the manifest wrote
  `len(track.documents)` — so a case that excluded every lien document still reported a lien
  track full of them. `documentCount` is now what the plan actually emitted, matched back to
  each track by `(subtype, date)`; the proposal is kept as `plannedDocumentCount`, because the
  difference between "no liens" and "liens the controls removed" is worth having.
- **`RenderResult.content_flags` records what was applied, not what was requested.**
  `render_document` is public and stored its `content_flags` argument verbatim, while the
  injection itself skips hooks with no content for the subtype — so a document containing no
  doctrine language could carry flags claiming two. Flags are now canonicalized through
  `content_flags_for` before anything is decided by them: unknown hooks dropped, duplicates
  collapsed, order normalized, non-targeting hooks removed.
- **Doctrine paragraphs no longer assert facts the seed cannot establish.** The first cut had
  Benson paragraphs asserting "two distinct industrial injuries" and "the two dates of injury"
  when a `CaseSeed` models exactly one `InjurySpec`, a section 4664 paragraph asserting a prior
  award as fact, and paragraphs asserting tenure, commute specifics, imaging findings and a
  disciplinary history — none of which the generator produces. Every one was rewritten into
  contention framing ("Where a prior award is established...", "if a separate industrial injury
  is established"), which is how these read in a real file anyway, and a test enumerates the
  banned phrases so they cannot return. Alongside it, each hook now declares a
  `DoctrinePrerequisite`: `auto:` derivation draws only hooks whose prerequisite the case
  satisfies (a living applicant no longer draws death benefits; a case that never went to IMR no
  longer draws an IMR due-process challenge), while an explicitly seeded hook is kept and warned
  about, per ISC-29. Benson's prerequisite is deliberately weaker than the doctrine — multiple
  impaired regions rather than multiple injuries — because a seed cannot express a second date
  of injury at all; modelling one is the real fix and belongs in the seed schema.
- **`ci.yml` gates on this package.** The `wc-synthetic-caseload-engine` job was missing from
  both `ci-gate.needs` and its `results` array, so the package's own suite could fail without
  failing CI. All sixteen package jobs are now in both.

### Added

**KB-grounding: doctrine content injection** (ticket **AJC-34**, ISC-21.1–21.6) — seeded
doctrine hooks now produce doctrine language in the rendered documents. ISC-21 shipped
DEFERRED-VERIFY because only half of it was true: `lifecycle.doctrine_hooks` validated, forced
the psych component and reached the manifest, while a caseload seeded `[kite, escobedo]`
rendered a corpus in which neither word appeared anywhere. A classifier corpus built from it
could not be used to measure whether a model finds doctrine language, because the language was
not in it.

- **New `doctrine.py`** — a content table covering all fourteen `DoctrineHook` values. Each
  carries the controlling authority, a short **marker** chosen to survive PDF text extraction
  (`Guzman`, `3208.3`, `personnel action`), three paragraphs written in the register of a
  med-legal evaluator's discussion, three in the register of points and authorities, and the
  canonical subtypes each register targets — 36 subtypes in all. Which register a document
  draws from is decided by the document's own subtype, and a subtype has one register across
  every hook, so a document flagged with two hooks carries one heading rather than two
  contradictory ones.
- **`PlannedDocument.content_flags`** — the sorted, deduplicated subset of the seed's hooks
  that has content for that document's subtype. Order-independent, so two seeds naming the same
  hooks produce the same document.
- **Renderer injection by subclassing, not patching.** A flagged document's template class is
  subclassed at render time and `build_story` extended: `super()` produces the document the
  template would otherwise have produced, and a trailing authorities section is appended from
  the base class's own style sheet. The appended flowables are plain `Paragraph`/`Spacer`/
  `HRFlowable`, so the substrate's `_story_to_plaintext` and `_story_to_docx` carry them into
  eml and docx with no further work. The paragraph is drawn from a **private** `random.Random`
  seeded from `rng_seed` and the hook name — never the re-seeded global stream the substrate
  templates draw from — so a flagged document's pre-existing content is bit-for-bit what it
  would have been unflagged, and a flagged case still regenerates byte-identically.
- **`contentFlags` in the manifest**, written per document and only when non-empty, so a
  caseload that seeds no doctrines produces byte-identical manifests to the ones it produced
  before the field existed.
- **Unflagged is the original code path.** With no flags no wrapper class is built at all —
  asserted by making the factory raise rather than by inspecting output, because bytes alone
  cannot distinguish "the wrapper was never built" from "the wrapper was built and appended
  nothing".
- **110 new tests** (`tests/test_doctrine_content.py`), mapped to ISC-21.1–21.6: the table
  (every hook has content; every paragraph carries its marker; every target is one of the 353
  canonical subtypes), the plan (all fourteen hooks reach a planned document), the page (all
  fourteen markers, in both registers, survive into extracted PDF text), the anti-criterion, and
  determinism.
- **Documented, not discovered later:** hook *count* has always fed the substrate's clinical
  complexity — two or more hooks flip a case from `standard` to `complex`, which changes every
  document in it, including documents no doctrine targets. That predates this change and is not
  content injection, but it is what makes a naive "flagged case versus unflagged case" diff
  misread. It is now pinned by a test and stated in the README.

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
