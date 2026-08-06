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

| Run | Spec | What it is |
|---|---|---|
| **7-case canonical** | `examples/demo-caseload.yaml` | 331 documents, 49.2 MB, all four formats. The shipped example |
| **Stage-delta A** | one seed (`rng_seed: 909090`) generated at `medical_legal` and at `resolved` | Two `case_id`s in one spec |
| **Stage-delta B** | same experiment, `rng_seed: 424242`, same `case_id`, same position, separate spec files | Confound-free replication of A |
| **Gentle pair** | `active_treatment` → `discovery`, same construction as B | The stage pair expected to behave best |
| **DOI shift** | seed `424242` at `resolved`, DOI `2023-03-14` vs `2022-12-29` | Only the injury date differs |
| **Clamp probe** | seed `111111`, `active_treatment`, DOI `2025-06-15`, `eval_type: none` | 200 days of runway to the anchor |

Thirteen case manifests in total. Aggregate figures state which set they cover, because the
two sets do not give the same medians.

---

## 1. `ANCHOR_DATE` is an unrecorded input to every date

```python
# src/wc_caseload_engine/seeds.py:128
ANCHOR_DATE: date = date(2026, 1, 1)
```

**Method:** read the constant; `grep -rn ANCHOR_DATE src/`; read the provenance block written
by `manifests.py`.

**Result.** It is a module constant. There is no CLI flag and no environment override. It is
consumed across `seeds.py`, `case_context.py`, `lifecycle_bridge.py` and `determinism.py` — as
the horizon (`lifecycle_bridge.py:375,584`), as the base for birth dates
(`case_context.py:315,318`), as the ceiling a stated date may not exceed (`seeds.py:1551`), and
as the point every statutory runway floor is measured back from (`seeds.py:1892,1901`).

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
silently incomparable: every date moves, every dependent document changes, all three recorded
identifiers still match, and nothing in the output says why. A `seedHash` collision across
different anchors is not a hypothetical — it is the default.

This is an unrecorded input, not a regression. Recording it would make the contract *more*
verifiable, because a byte diff would become attributable instead of unexplained. Doing so
changes manifest bytes by construction, so any such change must scope its Compatibility note to
*document* bytes and golden-test documents and manifests separately.

> No change is proposed here. This section records the property.

---

## 2. Document mass is front-loaded and decays

**Method:** for each case manifest, take `documents[].documentDate`; count documents in the
first 28 days from the case's earliest date, in the last 28 days up to the case's own latest
date, and the densest 28-day window anywhere inside the final 120 days. Recomputed
2026-08-06 from the manifests directly.

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

| Measure | 7-case canonical | All 13 case manifests |
|---|---|---|
| First 28 days | median **12**, range **9–15** | median **14**, range **9–15** |
| Last 28 days before the case's own horizon | median **2**, range **1–4** | median **2**, range **1–6** |
| Densest 28-day window in the final 120 days | median **3**, range **1–10** | median **2**, range **1–10** |

The 13-case `1–6` upper bound on the trailing window is the clamp probe (§5), where six
documents share the anchor. Excluding it, the trailing range is 1–4 on both sets.

**The shape is the finding, and it is stable across every case measured.** A case's opening
month carries **five to ten times** what its closing month carries. `whitfield-early-intake` —
the one case that is *only* an opening — is the only case whose densest late window reaches
double digits, and that is its intake burst, not a tail.

**Consequence.** Anyone harvesting documents from a date window gets far more by aiming a
case's **start** into the window than its end. A corpus of cases *finishing* in a window
delivers a trickle.

---

## 3. Advancing `target_stage` re-plans the whole chain — it does not append

This is the most expensive thing in this file to learn the hard way.

**Method:** generate one seed at stage L0, generate the same seed at a later stage L1, compare
the two manifests on `md5Checksum` and on the `(subtype, documentDate)` key. Decode selected
PDFs to inspect content.

### Stage-delta A — seed 909090, `medical_legal` → `resolved`

| | |
|---|---:|
| L0 documents | 54 |
| L1 documents | 81 |
| Byte-identical across both (shared MD5) | **35** |
| L0 documents whose bytes are **not** in L1 | **19** |
| — of those, present in L1 at the **same subtype and the same `documentDate`**, different bytes | **18** |
| — of those, present in L1 at the same subtype **one day later** (`2023-03-14` → `2023-03-15`) | **1** |
| True-new documents in L1 | **28** |
| — of those, dated **at or before the L0 horizon** (backfilled into the past) | **16** |
| L0 horizon → L1 horizon | 2024-07-31 → 2026-01-01 (**+519 days**) |

**Nothing vanishes. Documents are rewritten.** Every one of the 19 exists in L1 under the same
subtype; 18 keep their exact date and 1 moves by a day.

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
| Byte-identical | 46 |
| Changed (17 total): rewritten at identical subtype+date | **16** |
| Changed: same subtype, re-dated by one day | **1** |
| True-new | **30**, of which **12** backfill at or before the L0 horizon |
| Horizon movement | 2024-07-25 → 2025-12-30 (**+523 days**) |

The one re-dated document is a `FIRST_REPORT_OF_INJURY_PHYSICIAN` in both experiments —
the same document class, moving by a single day, in both.

### The gentle pair is the worst pair

`active_treatment` → `discovery` looks like the mildest possible advance. It is the most
destructive of the three tested:

| | |
|---|---:|
| L0 → L1 documents | 51 → 75 |
| Byte-identical | 34 |
| Rewritten at identical subtype+date | **17** |
| True-new | **24** |
| — of those, **backfilled** at or before the L0 horizon | **22** |
| — landing after the L0 horizon | **2** |
| Horizon movement | 2024-09-08 → 2024-09-30 (**+22 days**) |

Discovery paper **interleaves into** the treatment period instead of appending to it. Early
machines — billing, pharmacy, treatment cadence — keep emitting into history while the horizon
barely moves. 92% of the new documents are new *history*.

### Mechanism

`planner.py:1939 build_case_plan` pools candidates from every track machine into a single list
before anything is dated:

```python
core       = build_core_candidates(seed, timeline)
lien_tracks = build_lien_tracks(seed, timeline)
recon      = build_recon_track(seed, timeline)

candidates = [*core, *lien_candidates(lien_tracks), *recon.documents,
              *_penalty_candidates(...), *_delay_chain_candidates(...)]
candidates.extend(_money_candidates(...))
```

The whole timeline is then re-planned from that pool. Re-planning is the design. There is no
append path and no incremental mode.

### Practical consequence

> **Never regenerate a case at a later stage expecting the earlier corpus to survive.**

If earlier output has already been published, loaded into a system, or checked against an
answer key, a later-stage regeneration of the same seed silently invalidates it: same
filenames, same dates, different medicine. Generate at the terminal stage you want, once, and
freeze the seed.

**Refutation strength: n=3**, across two stage pairs and two seeds, with the confound ruled out
by construction in B.

---

## 4. DOI shift is perfectly rigid

**Method:** two runs of seed `424242` at `target_stage: resolved`, identical in every field
except `injury.date_of_injury` — `2023-03-14` versus `2022-12-29`, a difference of 75 days.
Sort both manifests' `documentDate` values and subtract pairwise.

**Result:** both runs produce **92 documents**, and the set of pairwise date differences is a
single value:

```
distinct per-document date deltas: [-75]
```

Every one of the 92 documents moved by exactly 75 days. Not approximately, not in aggregate —
exactly, individually.

**Consequence.** Aiming a case's timeline at a date window is deterministic and exact.
Calibration is a rigid two-pass operation: generate, measure the offset between where the
documents landed and where you want them, shift the DOI by that number of days, regenerate,
freeze. No search loop is needed.

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

Write `eval_type: none` on every seed that does not actually need a medical-legal evaluation.

---

## 7. Only starts, ends, and post-resolution lien tracks are windowable

**Status: a conclusion drawn from §2, §4 and §5, not a separate measurement.**

Given that mass is front-loaded (§2), that DOI aiming shifts a whole timeline rigidly (§4), and
that a timeline overrunning the anchor clamps rather than compressing (§5), the levers that can
put documents into a chosen date window are:

| Lever | Measured density into the window | Character |
|---|---|---|
| Case **opens** in the window (intake burst) | 9–15 documents | FROI, claim forms, initial reports, benefit notices |
| Case **ends** in the window (terminal trickle) | median 2, range 1–4 | one small cluster, then silence |
| Post-resolution lien track | **unmeasured** — see §10 | the one native past-anchor emitter |

**What does not work: aiming mid-life flow.** There is no lever that makes a case emit its
*middle* into a chosen window. A case whose timeline merely crosses the window clamps at the
anchor (§5); a case labelled `active_treatment` does not thereby deliver treatment paper into a
window — its label sets a runway floor, not an emission target. A stage label is a statement
about how far the file got, not about when its documents arrive.

Corollary for any date-windowed corpus: realism comes from **breadth across cases**, not depth
within one. A single case's window contribution is single-digit and then goes quiet.

---

## 8. Corpus economics

**Method:** sum `documents[].fileSize` across the seven manifests of the canonical run; count
by `format`.

| Metric | Measured (7 cases) | Per case | Extrapolated to 400 cases |
|---|---:|---:|---:|
| Documents | 331 | 47.3 | **18,914** |
| Bytes | 49,205,937 (49.2 MB) | 7.03 MB | **2.81 GB** |
| Mean document size | 145.2 KB | — | — |
| Documents over 30 MB | 0 | 0 | 0 |

**Format split of the canonical run** (this spec's `format_mix`, which is not the engine
default — see §9):

| Format | Count | Share |
|---|---:|---:|
| pdf | 207 | 62.5% |
| scanned_pdf | 75 | **22.7%** |
| eml | 37 | 11.2% |
| docx | 12 | 3.6% |

At 22.7%, a 400-case corpus carries roughly **4,300 scanned documents** requiring OCR.

> A figure of "~25% scanned / ~4,700 documents" circulates from an earlier pass. It is the
> measured 22.7% rounded up. The measured number is 22.7%; 25% is what you get if you *set*
> `scanned_pdf: 0.25` in `format_mix`.

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

Stated here so it is not mistaken for a gap in the sections above.

### The post-resolution lien track's past-anchor document count

**Mechanism verified. Count never taken.**

`lien_machine.py:180-207` (`_track_window`) is the only path in the engine that lets documents
run past the anchor, and it does so deliberately:

```python
floor = resolution_date + timedelta(days=1) if post_resolution else timeline.injury_date
if post_resolution:
    needed  = max(proposed) if proposed else floor
    ceiling = max(timeline.horizon, needed, floor + timedelta(days=len(proposed)))
else:
    ceiling = timeline.horizon
```

With `lifecycle.liens.post_resolution_litigation: true`, the ceiling is extended past the case
horizon to whatever the chain needs. `README.md` documents this as intentional and notes a test
(`test_liens_without_post_resolution_litigation_run_alongside_the_case`) asserting the default
path never crosses the horizon.

**What is unknown: how many documents such a track actually places after the anchor, and over
what span.** No seed was generated with `post_resolution_litigation: true` during this
measurement session. Any plan that depends on the lien track as a source of post-anchor
document flow is depending on an unmeasured quantity. It is one seed away from being known.

### Other things not measured

- Whether an applicant-perspective file realistically receives post-resolution lien traffic at
  all — a domain question, not just a count.
- Document mass distribution for stage mixes other than the seven canonical cases.
- Anything about generation wall-clock time or throughput.

---

## Summary — the five that cost the most to relearn

1. **Advancing a stage rewrites history.** Same subtype, same date, different medicine. Generate
   at the terminal stage once; never regenerate a case forward. (§3)
2. **Mass is front-loaded 5–10×.** Aim a case's start into your window, not its end. (§2)
3. **DOI shifting is exact.** One measure-and-shift pass aims a whole timeline. (§4)
4. **`eval_type` defaults to `qme`**, so every default lifecycle silently needs 240 days of
   runway. Write `eval_type: none` when you do not need an evaluation. (§6)
5. **The anchor is a real input that provenance does not record.** Two runs at different anchors
   are silently incomparable with all three recorded identifiers matching. (§1)

---

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
