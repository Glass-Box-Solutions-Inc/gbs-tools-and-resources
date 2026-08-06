# TEMPORAL_BEHAVIOUR — measured date behaviour of wc-synthetic-caseload-engine

**Engine version measured:** v0.8.0 (`pyproject.toml`)
**Measured:** 2026-08-06
**Status:** measurement record. Every result below states the method that produced it.

`README.md` is the product surface, `CLAUDE.md` the developer guide, `ISA.md` the criteria
contract. This file is the fourth thing: **what the engine actually does to dates**, measured
rather than described, for anyone planning a corpus around a calendar.

The motivating question was narrow — *can WCCE output be partitioned into an initial load plus
a 28-day stream of daily arrivals?* — but most of what fell out is general. If you are choosing
seeds so documents land in a date window, or regenerating a case at a later stage, or comparing
two runs, read this before you generate anything.

---

## How to read this file

- Every claim names the run, the seed, and the comparison that produced it.
- Where a figure depends on which cases you measure, both figures are given.
- Anything not measured is in [§10 Explicitly unmeasured](#10-explicitly-unmeasured) and is not
  softened into a claim elsewhere.
- Source citations are `file:line` against the tree at the time of measurement. Line numbers
  age; the constant names do not.

## The runs behind these numbers

An `rng_seed` on its own does not reproduce a run — lifecycle, `date_of_injury`, document
controls, `format_mix` and perspective all change the output. **Every spec named here is
committed**, under `docs/measurements/`, byte-identical to what was run. Regenerate any row
with `wc-caseload generate --spec <spec> --out <dir>`.

| Run | Spec | Case manifests | What it is |
|---|---|---:|---|
| **7-case canonical** | `examples/demo-caseload.yaml` | 7 | 331 documents, 49.2 MB, all four formats. The shipped example |
| **Stage-delta A** | `docs/measurements/stage-delta-a.yaml` | 2 | `rng_seed: 909090` at `medical_legal` (`delta-l0-medlegal`) and at `resolved` (`delta-l1-resolved`) — two `case_id`s in one spec |
| **Stage-delta B** | `docs/measurements/stage-delta-b-l0-medical-legal.yaml` + `…-b-l1-resolved.yaml` | 2 | `rng_seed: 424242`, same `case_id` (`probe`), same position, separate spec files. Confound-free replication of A |
| **Gentle pair** | `docs/measurements/gentle-pair-l0-active-treatment.yaml` + `…-l1-discovery.yaml` | 2 | `rng_seed: 111111`, `active_treatment` → `discovery`, same construction as B. The stage pair expected to behave best |
| **DOI shift** | `docs/measurements/doi-shift.yaml` | 1 | seed `424242` at `resolved`, DOI `2022-12-29`. Compared against stage-delta B's L1 run (DOI `2023-03-14`), which is its baseline — no separate manifest |
| **Clamp probe** | `docs/measurements/clamp-probe.yaml` | 1 | seed `111111`, `active_treatment`, DOI `2025-06-15`, `eval_type: none` — 200 days of runway to the anchor |
| **DOI rigidity** | `docs/measurements/doi-rigidity.yaml` | 4 | Added in review round 1 for §4: `rng_seed: 555001` at `resolved` under three DOIs, plus a different-seed control at DOI A |
| **Surgery past-anchor** | `docs/measurements/surgery-past-anchor.yaml` | 1 | Added in review round 5 for §10: seed `660001`, `intake`, `eval_type: none`, `surgery: performed`, DOI `2025-11-20`. **Not** part of the §2 aggregate — a single-purpose probe |

`docs/measurements/clamp-probe-eval-qme-rejected.yaml` is the same clamp probe without
`eval_type: none`. It is committed because it **does not load** — it is the §6 footgun as a
runnable artefact, and it produces no manifest.

**Fifteen case manifests** back the aggregate column in §2: the 7 canonical plus the 8 above
from stage-delta A, stage-delta B, the gentle pair, the DOI shift and the clamp probe.

> **Correction (review round 1).** An earlier draft said "thirteen case manifests in total".
> The count was wrong — the roster describes 15, and 19 including the DOI-rigidity run added
> in this round. The §2 aggregate figures are unchanged: they reproduce exactly on the
> 15-manifest set, so the error was in the count, not in the sample.

The four DOI-rigidity manifests are **excluded** from every §2 aggregate. They are one seed
re-dated three times plus a control; including them would weight a single case four ways in a
distribution statistic.

---

## 1. `ANCHOR_DATE` is an unrecorded input

```python
# src/wc_caseload_engine/seeds.py:128
ANCHOR_DATE: date = date(2026, 1, 1)
```

**Method:** read the constant; `grep -rn ANCHOR_DATE src/`; read the provenance block written
by `manifests.py`. The behavioural half — what actually moves when the injury date moves —
comes from the DOI-rigidity run in §4.

**Result.** It is a module constant. There is no CLI flag and no environment override. Five
kinds of consumer read it, and it is worth being exact about which, because they are narrower
than "every date":

| Site | What the anchor governs |
|---|---|
| `seeds.py:1892,1901` | **Load-time runway validation** — the point every statutory floor is measured back from, and the number in the rejection message |
| `lifecycle_bridge.py:375,584` + `CaseTimeline.clamp` (`:401`) | **The horizon** — the ceiling a core-track date is pinned to. `clamp` bounds only dates *outside* `[injury_date, horizon]`; a date already inside the case window passes through untouched |
| `seeds.py:1551` | **The ceiling a stated settlement date may not exceed**, rejected at load if it does |
| `seeds.py:2510`, `case_context.py:315,318` | **Derived dates** — an `auto:` injury onset is `ANCHOR_DATE − age_days`, and every date of birth is derived back from the anchor |
| `determinism.py:466-469` | **The pinned substrate clock** — the "today" four substrate templates compute ages and hire dates from, so it reaches rendered *content*, not only dates |

**What the anchor does not govern.** Dates in a seed with an explicit `date_of_injury` are
derived from the **DOI**, not from the anchor. §4 measures this directly: the same seed at two
different DOIs, with 1082 and 1310 days of runway, produced byte-for-byte identical
DOI-relative offsets for all 94 documents. Offsets are DOI-relative; the anchor enters as a
validation floor and a ceiling, not as a term in the offset.

> **Correction (review round 1).** An earlier draft of this section was headed
> "an unrecorded input to **every date**" and said that editing the literal moves *every* date.
> Both were over-claims. What follows from the call sites above is that editing the literal
> shifts derived dates (`auto:` onset, dates of birth), shifts substrate-rendered ages and hire
> dates, moves the clamp ceiling — so any document that was pinned to the old anchor moves, and
> some that were not may become pinned — and changes which seeds load at all. A seed with an
> explicit DOI and slack to spare keeps its DOI-relative offsets. **No run varied the anchor**
> — there is no override to vary it with — so this paragraph is read off the call sites plus
> the §4 DOI experiment, not off an anchor-shift measurement.

**And it is absent from `provenance`.** The block written per case
(`manifests.py:208-215`) carries exactly:

```
zeroRealPii, castProvenance, generator, substrateSha, seedHash, rngSeed
```

The caseload-level block (`manifests.py:400-404`) carries `zeroRealPii`, `generator`,
`substrateSha`. No anchor in either.

**Why this matters.** The determinism contract in `README.md` is *same seed + same version +
same `substrateSha` ⇒ identical bytes*. That currently holds **because the anchor is a
literal**, not because the contract accounts for it. Edit the literal and two runs become
silently incomparable: derived dates move, clamped documents move, rendered ages and hire dates
move, all three recorded identifiers still match, and nothing in the output says why. A
`seedHash` collision across different anchors is not a hypothetical — it is the default.

This is an unrecorded input, not a regression. Recording it would make the contract *more*
verifiable, because a byte diff would become attributable instead of unexplained. Doing so
changes manifest bytes by construction, so any such change must scope its Compatibility note to
*document* bytes and golden-test documents and manifests separately.

> No change is proposed here. This section records the property.

---

## 2. Document mass is front-loaded and decays

**Method:** for each case manifest, take `documents[].documentDate`; count documents in the
first 28 days from the case's earliest date (`date < first + 28d`), in the last 28 days up to
the case's own latest date (`date > last − 28d`), and the densest 28-day window anywhere inside
the final 120 days. Both windows are half-open — the convention matters, see the note below the
ratio table. Recomputed 2026-08-06 from the manifests directly.

**7-case canonical run:**

| Case | n | Span | First 28d | Last 28d | Best 28d in final 120d |
|---|---:|---|---:|---:|---:|
| alvarez-denied-recon-remand | 55 | 2022-03-14 → 2024-11-20 | 13 | 1 | 1 |
| castellanos-trial-recon-denied | 55 | 2022-11-08 → 2025-05-10 | 15 | 1 | 5 |
| nguyen-cr-three-liens | 60 | 2022-08-03 → 2025-04-11 | 9 | 2 | 3 |
| okafor-ct-ur-imr | 50 | 2024-02-29 → 2025-09-17 | 12 | 4 | 4 |
| ramirez-death-dependency | 40 | 2023-01-19 → 2025-06-20 | 14 | 1 | 1 |
| whitaker-defense-qme-surveillance | 55 | 2022-06-21 → 2025-01-21 | 9 | 2 | 2 |
| whitfield-early-intake | 16 | 2025-10-07 → 2025-12-13 | 10 | 3 | 10 |

**Medians depend on the case set, so both are stated:**

| Measure | 7-case canonical | All 15 case manifests |
|---|---|---|
| First 28 days | median **12**, range **9–15** | median **14**, range **9–15** |
| Last 28 days before the case's own horizon | median **2**, range **1–4** | median **2**, range **1–6** |
| Densest 28-day window in the final 120 days | median **3**, range **1–10** | median **2**, range **1–10** |

The 15-manifest column covers the 7 canonical cases plus the 8 experimental manifests listed in
the roster (stage-delta A ×2, stage-delta B ×2, gentle pair ×2, DOI shift, clamp probe); the
four DOI-rigidity manifests are excluded. Those 8 experimental manifests come from only **three
distinct seeds** — 909090, 424242 and 111111 — so the 15-manifest column is not a sample of 15
independent cases. Quote the canonical column when independence matters.

The `1–6` upper bound on the trailing window is the clamp probe (§5), where six documents share
the anchor. Excluding it, the trailing range is 1–4 on both sets.

**The shape is the finding, and it is stable across every case measured — but the multiple is
not.** Dividing the First 28d column by the Last 28d column of the 7-case table above, case by
case:

| Case | First 28d ÷ last 28d |
|---|---:|
| okafor-ct-ur-imr | 3.0 |
| whitfield-early-intake | 3.3 |
| nguyen-cr-three-liens | 4.5 |
| whitaker-defense-qme-surveillance | 4.5 |
| alvarez-denied-recon-remand | 13.0 |
| ramirez-death-dependency | 14.0 |
| castellanos-trial-recon-denied | 15.0 |

**The range is 3×–15×, and it is bimodal** — four cases cluster at 3–4.5, three at 13–15, and
nothing lands in between. The **ratio of the medians** on the canonical seven is 12 ÷ 2 = **6×**;
that single number is a ratio of medians, not a typical case, and no measured case is near it.

> **Correction (review round 1).** An earlier draft said a case's opening month carries "five to
> ten times" what its closing month carries. That band contains **none** of the seven measured
> ratios. It has been replaced by the measured range and its shape.

A note on the boundary, since it moves individual ratios: the columns above count the opening
window half-open (`date < first + 28d`) and the closing window half-open (`date > last − 28d`).
Counting the opening window inclusively (`date <= first + 28d`) raises three cases —
alvarez 13→14, okafor 12→14, whitfield 10→11 — giving a range of 3.5×–15×. The finding is the
same under either convention; the convention is stated so the table and the ratios agree.

`whitfield-early-intake` — the one case that is *only* an opening — is the only case whose
densest late window reaches double digits, and that is its intake burst, not a tail.

**Consequence.** Anyone harvesting documents from a date window gets far more by aiming a
case's **start** into the window than its end. A corpus of cases *finishing* in a window
delivers a trickle.

---

## 3. Advancing `target_stage` re-plans the whole chain — it does not append

This is the most expensive thing in this file to learn the hard way.

**Method:** generate one seed at stage L0, generate the same seed at a later stage L1, then
match L1 against L0 in three passes, **each pass consuming the L1 documents it matches** so no
document can be counted twice:

1. **Carried over** — same `md5Checksum` (byte-identical).
2. **Rewritten in place** — of the L0 documents left over, those present in L1 at the *same*
   `subtype` and the *same* `documentDate`, different bytes.
3. **Re-dated** — of the L0 documents still left over, those present in L1 at the same
   `subtype` and the nearest unconsumed date.

Anything in L0 still unmatched has **vanished**; anything in L1 never consumed is
**genuinely new**. The four L0 classes partition L0, and carried-over + rewritten + re-dated +
genuinely-new partitions L1, so both totals must close. Decode selected PDFs to inspect content.

> **Correction (review round 1).** The first version of this table did not consume matches, so
> its "true-new" count absorbed the L1 counterpart of the re-dated document — an off-by-one in
> both experiments. The genuinely-new and backfill figures below are recomputed with disjoint
> categories, and each table now shows its arithmetic closing.

### Stage-delta A — seed 909090, `medical_legal` → `resolved`

| | |
|---|---:|
| L0 documents | 54 |
| L1 documents | 81 |
| **Carried over** — byte-identical in both | **35** |
| **Rewritten in place** — same subtype, same `documentDate`, different bytes | **18** |
| **Re-dated** — same subtype, moved (`FIRST_REPORT_OF_INJURY_PHYSICIAN`, `2023-03-14` → `2023-03-15`) | **1** |
| **Vanished** — in L0, nowhere in L1 | **0** |
| **Genuinely new** — in L1, not the counterpart of any L0 document | **27** |
| — of those, dated **at or before the L0 horizon** (backfilled into the past) | **15** |
| — of those, landing after the L0 horizon | **12** |
| L0 horizon → L1 horizon | 2024-07-31 → 2026-01-01 (**+519 days**) |

L0 closes: 35 + 18 + 1 + 0 = 54. L1 closes: 35 + 18 + 1 + 27 = 81.

**Nothing vanishes. Documents are rewritten.** Every one of the 19 L0 documents whose bytes are
not in L1 exists in L1 under the same subtype; 18 keep their exact date and 1 moves by a day.

An earlier account of this experiment said the 19 documents "vanish." That was wrong, and the
correction makes the behaviour *worse*, not better — missing paper is visible, rewritten paper
is not.

**The rewrite is a content rewrite, verified by decoding the PDFs.** The
`QME_REPORT_INITIAL` dated `2023-12-17` exists in both runs, same doctor, same patient, same
date, different MD5:

| | L0 (`medical_legal`) | L1 (`resolved`) |
|---|---|---|
| Blood pressure | 136/86 (pre-hypertensive) | 128/82 (normal) |
| Heart rate | 80 bpm | 72 bpm |
| Respiratory rate | 14 | 18 |

Different physical-exam findings and vitals under an identical header. Advancing the stage
re-rolls document **content** through RNG-stream coupling, not just document **membership**.

### Stage-delta B — seed 424242, confound-free replication

Same `case_id`, same position in the spec, separate spec files, so nothing about ordering or
sibling cases can explain the result:

| | |
|---|---:|
| L0 → L1 documents | 63 → 92 |
| **Carried over** — byte-identical | **46** |
| **Rewritten in place** — same subtype, same `documentDate` | **16** |
| **Re-dated** — same subtype, moved (`2023-03-15` → `2023-03-14`) | **1** |
| **Vanished** | **0** |
| **Genuinely new** | **29**, of which **11** backfill at or before the L0 horizon and **18** land after |
| Horizon movement | 2024-07-25 → 2025-12-30 (**+523 days**) |

L0 closes: 46 + 16 + 1 + 0 = 63. L1 closes: 46 + 16 + 1 + 29 = 92.

The one re-dated document is a `FIRST_REPORT_OF_INJURY_PHYSICIAN` in both experiments — the
same document class, moving by a single day, in both. The **direction differs**: A moves it one
day later, B one day earlier. Whatever perturbs it is not a systematic shift.

### The gentle pair is the worst pair

`active_treatment` → `discovery` looks like the mildest possible advance. It is the most
destructive of the three tested:

| | |
|---|---:|
| L0 → L1 documents | 51 → 75 |
| **Carried over** — byte-identical | **34** |
| **Rewritten in place** — same subtype, same `documentDate` | **17** |
| **Re-dated** | **0** |
| **Vanished** | **0** |
| **Genuinely new** | **24** |
| — of those, **backfilled** at or before the L0 horizon | **22** |
| — landing after the L0 horizon | **2** |
| Horizon movement | 2024-09-08 → 2024-09-30 (**+22 days**) |

L0 closes: 34 + 17 + 0 + 0 = 51. L1 closes: 34 + 17 + 0 + 24 = 75. This pair needed no
correction — with no re-dated document there was nothing for the old method to double-count.

Discovery paper **interleaves into** the treatment period instead of appending to it. Early
machines — billing, pharmacy, treatment cadence — keep emitting into history while the horizon
barely moves. 92% of the new documents are new *history*.

### Mechanism

Each track machine **dates its own candidates** against the timeline, and `build_case_plan`
(`planner.py:1939`) then rebuilds the entire plan from scratch out of what they return:

```python
# planner.py:1974-1986
core        = build_core_candidates(seed, timeline)
lien_tracks = build_lien_tracks(seed, timeline)
recon       = build_recon_track(seed, timeline)

candidates = [*core, *lien_candidates(lien_tracks), *recon.documents,
              *_penalty_candidates(...), *_delay_chain_candidates(...)]
candidates.extend(_money_candidates(...))
```

Every one of those calls returns **already-dated** `DatedCandidate`s. The core track's dating,
clamp included, happens inside the machine:

```python
# lifecycle_bridge.py:758-767 — inside build_core_candidates
anchor = timeline.anchor(getattr(rule, "date_anchor", "doi"))
offset = _offset(date_rng, getattr(rule, "date_offset_days", (0, 30)))
...
doc_date=timeline.clamp(anchor + timedelta(days=offset)),
```

(The local `anchor` there is the substrate's `date_anchor` for that document — the DOI, the
claim-filed date, and so on — not `ANCHOR_DATE`. `ANCHOR_DATE` enters this line only as the
horizon inside `timeline.clamp`.)

So the pool is a pool of dated documents, and the plan built from it is a **fresh** plan: the
whole set is re-drawn, re-shaped and re-rendered from the seed at the new stage. Advancing the
stage changes what the machines are asked for, which changes the RNG streams they draw from,
which is why documents that already existed come back different. Re-planning is the design.
There is no append path and no incremental mode.

> **Correction (review round 1).** This section previously read "`planner.py:1939
> build_case_plan` pools candidates from every track machine into a single list **before
> anything is dated**". That is wrong on both counts: `:1939` is the function definition, the
> collection is at `:1974-1986`, and the candidates arriving there are already dated. The
> conclusion — a later-stage run is a re-plan, not an append — is unchanged; only the mechanism
> was described incorrectly.

### Practical consequence

> **Never regenerate a case at a later stage expecting the earlier corpus to survive.**

If earlier output has already been published, loaded into a system, or checked against an
answer key, a later-stage regeneration of the same seed silently invalidates it: same
filenames, same dates, different medicine. Generate at the terminal stage you want, once, and
freeze the seed.

**Refutation strength: n=3**, across two stage pairs and two seeds, with the confound ruled out
by construction in B.

---

## 4. DOI shift is rigid **while there is slack** — and clamps when there is not

**Method, part 1 (the original probe).** Two runs of seed `424242` at `target_stage: resolved`,
identical in every field except `injury.date_of_injury` — `2023-03-14` versus `2022-12-29`, a
difference of 75 days. Sort both manifests' `documentDate` values and subtract pairwise.

**Result:** both runs produce **92 documents**, and the set of pairwise date differences is a
single value:

```
distinct per-document date deltas: [-75]
```

Every one of the 92 documents moved by exactly 75 days. Not approximately, not in aggregate —
exactly, individually. Matching by `(subtype, DOI-relative offset)` confirms it: the two sets
are identical.

**Method, part 2 (`docs/measurements/doi-rigidity.yaml`, review round 1).** The probe above
shifts the DOI *away* from the anchor, so it can only ever gain room. To find the boundary,
seed `555001` at `target_stage: resolved` was run at three DOIs. Definitions, all measured
from the DOI so the arithmetic is visible: **available runway** = anchor − DOI; **natural span** =
the length the plan wants, which equals `last document date − DOI` **only on an unclamped run**
(see the note under the table — on a clamped run that subtraction returns the clamped span, not
the requirement); **slack** = runway − span, and it may be negative.

| Case | DOI | Available runway | Natural span | Slack | Result |
|---|---|---:|---:|---:|---|
| `doi-a-2023-01-15` | 2023-01-15 | 1082 | 1019 | 63 | rigid |
| `doi-c-earlier` | 2022-06-01 | 1310 | 1019 | 291 | rigid — DOI-relative offsets **identical to A**, all 94 documents, subtype for subtype |
| `doi-b-plus105` | 2023-04-30 | 977 | 1019 | **−42** | **the tail clamps** |

**On B's natural span.** It is **1019**, not the 977 it emitted. 977 is B's *clamped* span — the
length it was forced into — and reading that back as its requirement would be circular. The
natural span is established by A and C, which ran the same seed unclamped and both wanted 1019.
So B is **42 days short**, and that number predicts the result exactly: the two documents the
plan wanted at +994 and +1019 are the two that exceed 977, and both are pinned onto the anchor.
Slack is negative, not zero. *(Corrected in review round 2 — an earlier draft recorded span 977 /
slack 0, which is the clamped output mistaken for the requirement.)*

In `doi-b-plus105`, 92 of the 94 documents keep their DOI-relative offset exactly. The other
two do not:

| Subtype | Offset in A | Offset in B | Where it lands in B |
|---|---:|---:|---|
| `CASE_ANALYSIS_MEMO` | +994 | +977 | 2026-01-01 |
| `CLAIMS_CLOSURE_SUMMARY` | +1019 | +977 | 2026-01-01 |

Both are pinned to the anchor: this is the §5 clamp, reached by moving the DOI rather than by
seeding a short runway. The distortion is 17 and 42 days, and it is silent — the run succeeds,
the manifest looks normal, and the closing documents of the file are stacked on one day.

**All three DOIs clear the 540-day resolution floor** (977, 1082 and 1310 days against a floor
of 540). **Clearing the statutory floor therefore does not mean the timeline is uncompressed.**
The floor asks whether the *chain* fits; slack asks whether the *whole plan* fits.

> **Correction (review round 1).** This section was headed "DOI shift is perfectly rigid" and
> presented rigidity as a calibration guarantee. It is not universal. It held in the original
> probe because that probe moved the DOI away from the anchor from a starting position with
> **2 days of slack** (seed 424242 at DOI 2023-03-14: runway 1024, natural span 1022). Shifting
> the same case a few days *later* would have clamped it. The rigidity is real, and it is
> conditional.

**Consequence.** Measure-and-shift is valid while

```
available_runway >= natural_span + margin
```

where `natural_span` is measured **per seed** — but it can only be measured from a run that was
**not itself clamped**. `last − DOI` is the natural span only when the plan was never truncated;
on a clamped run it returns the *clamped* span and silently understates the requirement. Measuring
B directly would yield 977 and report zero slack, hiding the same 42-day shortfall this section
exists to expose. **A single generation is not sufficient**, and an earlier draft of this procedure
said it was.

**The procedure, stated so it cannot return a clamped baseline:**

1. Generate the seed at a DOI **well earlier** than you intend to use — early enough that the case
   plainly cannot reach 2026-01-01.
2. **Take the latest date, excluding only an intentionally-extended lien track.** The partition
   depends on one flag:
   - `liens.post_resolution_litigation: false` (or absent) — **measure over all documents.**
     Ordinary concurrent liens are bounded by the anchor like anything else and can legitimately
     be the plan's true tail, so excluding them would let a clamped lien pass unnoticed.
   - `liens.post_resolution_litigation: true` — **exclude that track only.** It is *designed* to
     run past the anchor (§10), so counting it would make a legitimately-extended case look
     permanently unmeasurable.

   *(An earlier draft excluded **every** lien document. That was overbroad and reintroduced the
   very defect this section exists to prevent: a concurrent lien could clamp while the non-lien
   tail sat before the anchor, and step 4 would accept the clamped baseline.)*
3. **If that date is on _or after_ the anchor, reject the run: the measurement is invalid.** Shift
   the DOI earlier and repeat from step 1. Both branches matter — a case whose core clamps while
   its lien track overruns has a latest date *after* the anchor, and an earlier draft of this
   procedure tested only for *equal to* and was therefore undefined for that configuration.
4. Only once that date falls **strictly before** the anchor is `natural_span = that_date − DOI`
   the true requirement.
5. Choose the working DOI so `available_runway >= natural_span + margin`.

> **Why reject a date sitting exactly on the anchor?** It does not *prove* clamping — a plan can
> legitimately end there with zero slack. But the two cases are indistinguishable from the output
> alone, and treating a clamped run as natural is the error this whole section exists to prevent.
> Rejecting is conservative, and the only cost is one more generation at an earlier DOI.

Shifting the DOI *later* (toward the anchor) spends slack and begins clamping the tail. Shifting it
*earlier* is safe for shape **on seeds with no authored absolute dates** — see the caveat below —
and costs only calendar realism.

**Not covered by this measurement:** a seed with authored absolute dates — for example
`scenario.settlement.approval_date` — where the DOI moves but the authored date does not. Those
runs were not measured here, and the rigid translation above says nothing about them. See §5
for the clamp on its own terms.

---

## 5. Timelines crossing the anchor clamp — they do not compress

**Method:** seed `111111`, `target_stage: active_treatment`, `eval_type: none`,
`date_of_injury: 2025-06-15` — 200 days of runway to the 2026-01-01 anchor. Count documents
per date.

**Result:** 45 documents, of which **6 sit on exactly 2026-01-01**. The last document before
that pile is dated **2025-11-16** — a **46-day gap** with nothing in it.

```
… 2025-10-27, 2025-10-29, 2025-11-03, 2025-11-16,
2026-01-01 ×6
```

The engine does not spread over-horizon documents backwards across the empty November and
December. It pins them to the ceiling. The result reads as a quiet autumn followed by an
impossibly busy New Year's Day.

This probe reaches the clamp by seeding a short runway. §4's `doi-b-plus105` reaches the *same*
clamp from the opposite direction — a comfortable-looking 977-day runway, exhausted by shifting
the DOI toward the anchor, with two documents pinned. Same mechanism, two ways in, and the
second one is easy to walk into while calibrating.

**Consequences.** A clamped pile is not mail flow, and must be excluded from any density count
that is trying to model arrival rate — counting it inflates the window total while making the
distribution obviously synthetic. Note also that `README.md` §Statutory runway describes
sequenced chains (lien tracks, the reconsideration round trip, the denial response) as being
fitted **as a whole** with strictly increasing dates; this probe shows that guarantee does not
extend to the unsequenced remainder of the plan.

---

## 6. `eval_type` defaults to `"qme"`, imposing a hidden 240-day DOI floor

```python
# src/wc_caseload_engine/seeds.py:491
class LifecycleSpec(_Model):
    target_stage: TargetStage = "medical_legal"
    claim_response: ClaimResponse = "accepted"
    eval_type: EvalType = "qme"
```

**Method:** read the model default; read `runway_demands()` and `EVAL_RUNWAY_DAYS`
(`seeds.py:198`).

```python
if lifecycle.eval_type in {"qme", "ame"}:
    demands.append((EVAL_RUNWAY_DAYS, f"lifecycle.eval_type {lifecycle.eval_type!r}"))
```

`EVAL_RUNWAY_DAYS = 240`. Required runway is the **maximum** of all demands, so any seed that
does not explicitly write `eval_type: none` inherits a **240-day floor between the injury date
and the anchor** — even when its `target_stage` needs far less.

**This is a genuine footgun.** A seed aimed near the anchor is rejected at load with a message
naming `lifecycle.eval_type 'qme'` as the driver — a field the author never wrote. The floor is
correct and the error message is honest; the trap is that the demand comes from a default. The
clamp probe in §5 works only because it sets `eval_type: none` explicitly.

Both halves of that are committed. `docs/measurements/clamp-probe-eval-qme-rejected.yaml` is
the version that leaves the default in place: it fails to load, naming
`lifecycle.eval_type 'qme'`. `docs/measurements/clamp-probe.yaml` differs from it by that one
line and generates the 45 documents of §5.

Write `eval_type: none` on every seed that does not actually need a medical-legal evaluation.

---

## 7. Starts and ends are the strong levers; mid-life is thin

**Status: a conclusion drawn from §2, §4 and §5, plus one measurement taken for this section.**

Given that mass is front-loaded (§2), that DOI aiming shifts a whole timeline rigidly while
there is slack (§4), and that a timeline overrunning the anchor clamps rather than compressing
(§5), the levers that put documents into a chosen date window rank like this:

| Lever | Measured density into a 28-day window | Character |
|---|---|---|
| Case **opens** in the window (intake burst) | 9–15 documents | FROI, claim forms, initial reports, benefit notices |
| Case's **middle** falls in the window | median 4, range 2–7 | treatment, billing, correspondence — thin but not empty |
| Case **ends** in the window (terminal trickle) | median 2, range 1–4 | one small cluster, then silence |
| Post-resolution lien track | measured once, **zero** past-anchor documents — see §10 | the only native past-anchor emitter, and it did not emit |

**Mid-life is thin in the cases measured.** *Method (review round 1): for each of the seven
canonical cases, take the middle third of its own span — `[first + span/3, first + 2·span/3]` —
and find the densest 28-day window inside it.* The result is a median of **4** documents
(range 2–7), against a median of 12 in the opening window. A window aimed at a case's middle
collects real paper, just several times less of it than the same window aimed at the opening.

> **Correction (review round 1).** This section previously asserted that "there is no lever that
> makes a case emit its *middle* into a chosen window" and that "a case whose timeline merely
> crosses the window clamps at the anchor". Both were inferences, not measurements, and the
> second misreads the source: `CaseTimeline.clamp` (`lifecycle_bridge.py:401-413`) bounds only
> dates falling **outside** `[injury_date, horizon]`. A date inside the case window passes
> through untouched — crossing an arbitrary target window causes no clamping at all. The
> replacement above is the measured version: mid-life density is low, which is a different
> claim from mid-life being unaimable. **Whether mid-life can be aimed was not measured** and
> is listed in §10.

What does remain true is that a stage label is not an emission target: a case labelled
`active_treatment` does not thereby deliver treatment paper into a window — the label sets a
runway floor (§6) and a stopping point, not an arrival schedule.

Corollary for any date-windowed corpus: realism comes from **breadth across cases**, not depth
within one. One case contributes at most 9–15 documents to its best window and then falls to a
handful.

---

## 8. Corpus economics

**Method:** sum `documents[].fileSize` across the seven manifests of the canonical run; count
by `format`.

All byte figures are **decimal** (MB = 10⁶ bytes, GB = 10⁹, kB = 10³), consistently.

| Metric | Measured (7 cases) | Per case | Extrapolated to 400 cases |
|---|---:|---:|---:|
| Documents | 331 | 47.3 | **18,914** |
| Bytes | 49,205,937 (49.2 MB) | 7.03 MB | **2.81 GB** |
| Mean document size | 148.7 kB (145.2 KiB) | — | — |
| Documents over 30 MB | 0 | 0 | 0 |

> **Correction (review round 1).** The mean was previously given as "145.2 KB" while every
> other size in this file is decimal. 49,205,937 ÷ 331 = 148,658 bytes: **148.7 kB** decimal, or
> 145.2 **KiB** binary. The old figure was the binary value wearing a decimal label.

**Format split of the canonical run** (this spec's `format_mix`, which is not the engine
default — see §9):

| Format | Count | Share |
|---|---:|---:|
| pdf | 207 | 62.5% |
| scanned_pdf | 75 | **22.7%** |
| eml | 37 | 11.2% |
| docx | 12 | 3.6% |

At 22.7%, a 400-case corpus carries roughly **4,300 scanned documents** requiring OCR.

**25% is the configured weight; 22.7% is the realized share.** `examples/demo-caseload.yaml:23`
already sets `format_mix: {pdf: 0.6, scanned_pdf: 0.25, eml: 0.1, docx: 0.05}` — so 25% is the
input, and 22.7% is what 331 documents assigned from that distribution actually came out at.
The gap is sampling, not disagreement.

> **Correction (review round 1).** An earlier note here framed "~25% scanned / ~4,700
> documents" as a rounding error and said 25% "is what you get if you *set* `scanned_pdf: 0.25`"
> — as though the canonical run had not. It had. Both numbers describe the same run: 25%
> requested, 22.7% realized. Extrapolate from the realized share.

Extrapolation caveat: 400 cases drawn from a different stage mix will not hold 47.3
documents/case. `whitfield-early-intake` is 16 documents; `nguyen-cr-three-liens` is 60. The
per-case figure is an average over this specific seven-case mix.

---

## 9. Adjudica interop — two things that bite

For anyone feeding WCCE output into `adjudica-ai-app`. **Verified 2026-08-06 against that
repository; re-verify before relying on it, as it is a separate codebase on its own history.**

### `.eml` is rejected

WCCE's default `format_mix` emits `eml`, and the canonical run produced 37 of 331 documents in
that format. Adjudica will not accept them.

The enforcement is an **allowlist**, in `adjudica-ai-app/shared/constants/file-upload.ts`:

- `ALLOWED_FILE_EXTENSIONS` — `.pdf .doc .docx .txt .jpg .jpeg .png .msg .webp`
- `ALLOWED_FILE_TYPES` — the corresponding MIME types

Neither contains `.eml` or `message/rfc822`. `shared/schemas/file-upload.ts` enforces both in
`processedFileSchema` (`z.enum(ALLOWED_FILE_TYPES)`, plus an extension check rejecting with
"File extension not supported").

> **Correction to an earlier account.** The rejection is often attributed to
> `UNSUPPORTED_EXTENSIONS` / `UNSUPPORTED_MIME_TYPES` in the same file. Those exist and do name
> `.eml` with a friendly message, but at the time of measurement they are consumed **only** by
> `server/utils/meruscase-document-sync.ts` — the MerusCase sync path — not by the upload
> schema. The outcome is the same; the mechanism cited matters if you go looking for it.
> Note `.msg` **is** allowed, so an Outlook-format email would pass where `.eml` does not.
> The route-level wiring of `processedFileSchema` to each upload endpoint was not traced
> end to end.

**Mitigation:** set `format_mix` without `eml` and drop `eml` from `output.formats`.

### Defense `.docx` carries the applicant firm's letterhead

Already documented at `README.md` §"Known limitation: defense letterhead": the substrate
hard-codes `Martinez & Associates, APC` on the docx letterhead, so a defense-perspective docx
is rendered under the applicant firm's name. Scope is the rendered docx letterhead only — the
manifest, the seed and the subtype set are unaffected.

**Consequence for anything downstream that reads the page.** A classifier or router keying on
letterhead will read defense work product as applicant work product. If the corpus is being
used to exercise document routing, set defense `format_mix` docx to 0; the subtype mix survives
in the other formats.

---

## 10. Explicitly unmeasured

Stated here so it is not mistaken for a gap in the sections above. The first entry is now
*partly* measured — the measurement is given, and what remains unmeasured is named separately,
because the two are easy to conflate and the difference is the whole point of the entry.

### The post-resolution lien track as a past-anchor source

**Mechanism verified. Measured once, and it produced nothing past the anchor.**

`lien_machine.py:180-207` (`_track_window`) is the only *deliberate* path past the anchor:

```python
floor = resolution_date + timedelta(days=1) if post_resolution else timeline.injury_date
if post_resolution:
    needed  = max(proposed) if proposed else floor
    ceiling = max(timeline.horizon, needed, floor + timedelta(days=len(proposed)))
else:
    ceiling = timeline.horizon
```

With `lifecycle.liens.post_resolution_litigation: true`, the ceiling is extended past the case
horizon **to whatever the chain needs** — and no further. `README.md` documents this as
intentional and notes a test
(`test_liens_without_post_resolution_litigation_run_alongside_the_case`) asserting the default
path never crosses the horizon.

> **A second, undeliberate path exists — and it is not a lien.** *(Found in review round 5; not
> previously documented anywhere.)* `planner.py:1908-1912` floors an operative document when
> `scenario.surgery: "performed"` and the walk produced none:
>
> ```python
> when = facts.surgery.date or timeline.injury_date + timedelta(days=210)
> shaped.append((when, "OPERATIVE_HOSPITAL_RECORDS", TRACK_CORE, "treating_physician"))
> ```
>
> This append carries **no `timeline.clamp(...)`**, unlike the per-machine dating at
> `lifecycle_bridge.py:766`. So an accepted seed whose validated runway is shorter than 210 days —
> `target_stage: intake` needs only 30 — emits a **core, non-lien** document past the anchor.
>
> **Measured** (`docs/measurements/surgery-past-anchor.yaml`, review round 5). Seed `660001`,
> `target_stage: intake`, `eval_type: none`, `scenario.surgery: performed`, DOI **2025-11-20** —
> 42 days of runway against a 30-day floor, so the seed **validates and generates cleanly**:
>
> | | |
> |---|---|
> | Documents | 14 |
> | Liens | 0 |
> | Documents past 2026-01-01 | **1** |
> | The document | `OPERATIVE_HOSPITAL_RECORDS`, **2026-06-18** = DOI + 210 exactly, **169 days past the anchor** |
>
> Unlike the lien extension, this looks unintended — a missing clamp rather than a declared
> exception — and it means **runway validation does not bound output**: a seed can pass every
> floor and still emit past the horizon. Worth an **AJC ticket against the engine**; the tracker is
> AJC and no ticket number is invented here.

**What was measured.** `examples/demo-caseload.yaml:82` sets
`post_resolution_litigation: true` on `nguyen-cr-three-liens` — one of the seven canonical
cases. Its output:

| | |
|---|---|
| Documents | 60 |
| Span | 2022-08-03 → 2025-04-11 |
| Documents after the 2026-01-01 anchor | **0** |
| Lien-track documents | **15** — three tracks of five — running 2024-07-26 → 2025-04-11 |

The last lien document lands 265 days *before* the anchor. The ceiling extension is
`max(timeline.horizon, needed, …)` — it engages only when the chain genuinely needs to overrun,
and this chain fit comfortably inside the horizon, so the extension never took effect.

> **Correction (review round 1).** This section previously said "no seed was generated with
> `post_resolution_litigation: true` during this measurement session". That was false — one of
> the seven canonical cases sets it, and its numbers are above. The corrected reading is
> **weaker** evidence for liens as a past-anchor source than the mechanism alone suggests: the
> one measured case with the flag on emitted nothing past the anchor.

**What is still unknown: whether a lien chain that genuinely needs to overrun places documents
after the anchor, how many, and over what span.** No seed exercising an actual past-anchor
overrun has been measured — that needs a resolution date late enough that the chain cannot fit
before 2026-01-01. Any plan depending on the lien track for post-anchor document flow is still
depending on an unmeasured quantity.

### Other things not measured

- Whether mid-life document flow can be *aimed* into a chosen window at all (§7 measures only
  how dense mid-life is, not whether any lever targets it).
- The effect of moving `ANCHOR_DATE` itself — there is no override, so no run varied it (§1).
- Behaviour of a DOI shift on a seed carrying authored absolute dates, such as
  `scenario.settlement.approval_date` (§4).
- Whether an applicant-perspective file realistically receives post-resolution lien traffic at
  all — a domain question, not just a count.
- Document mass distribution for stage mixes other than the seven canonical cases.
- Anything about generation wall-clock time or throughput.

---

## Summary — the five that cost the most to relearn

1. **Advancing a stage rewrites history.** Same subtype, same date, different medicine. Generate
   at the terminal stage once; never regenerate a case forward. (§3)
2. **Mass is front-loaded 3×–15×**, bimodally — not a smooth band. Aim a case's start into your
   window, not its end. (§2)
3. **DOI shifting is exact while there is slack.** One measure-and-shift pass aims a whole
   timeline — but measure the natural span from a run that was **not clamped**, or you will read
   the clamped span back as the requirement and miss the shortfall entirely. Shifting toward the
   anchor clamps the tail silently. (§4)
4. **`eval_type` defaults to `qme`**, so every default lifecycle silently needs 240 days of
   runway. Write `eval_type: none` when you do not need an evaluation. (§6)
5. **The anchor is a real input that provenance does not record.** Two runs at different anchors
   are silently incomparable with all three recorded identifiers matching. (§1)

---

## Review history

**Round 1 — cross-model review, 2026-08-06.** This file was reviewed by a model outside the
family that wrote it, and the review returned BLOCK on eight findings. All eight were
independently reproduced from the manifests and the source before being applied. The corrections:

| § | What was wrong | Now |
|---|---|---|
| Roster | "Thirteen case manifests"; no spec committed, so no run was reproducible from an `rng_seed` alone | 15 manifests, itemised; every spec committed under `docs/measurements/` |
| §1 | "unrecorded input to **every date**"; "every date moves" | Scoped to what the anchor actually governs, site by site; the "every date" half is refuted by the §4 DOI result |
| §2 | "five to ten times" — a band containing none of the seven measured ratios | Measured range 3×–15×, bimodal, with the window convention stated |
| §3 | Non-disjoint categories: "true-new" absorbed the re-dated document's counterpart, off by one in both experiments | Three consuming passes; genuinely-new 28→**27** (A) and 30→**29** (B), backfill recomputed, both totals shown closing |
| §3 | Mechanism: "pools candidates … before anything is dated" at `planner.py:1939` | `:1939` is the definition, collection is `:1974-1986`, and candidates arrive already dated (`lifecycle_bridge.py:758-767`) |
| §4 | "DOI shift is perfectly rigid" stated as a universal guarantee | Rigid **while slack is positive**; new 4-case run shows the tail clamping at **negative** slack, with all three DOIs clearing the statutory floor |
| §7 | "Mid-life flow cannot be aimed" — an inference presented as a finding, resting on a misreading of `clamp` | Replaced with the measured density (median 4, range 2–7); aimability moved to §10 as unmeasured |
| §8/§10 | "145.2 KB" (binary value, decimal label); 25% presented as an outcome; "no seed was generated with `post_resolution_litigation: true`" | 148.7 kB decimal; 25% configured vs 22.7% realized; one canonical case **does** set the flag and produced **zero** past-anchor documents |

Every correction is labelled as a correction in place, and nothing measured in this round was
folded into an earlier claim without saying so. Two findings made the document's conclusions
weaker rather than stronger (§4 rigidity, §10 liens); both are stated in the weaker form.

---

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
