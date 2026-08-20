# AJC-64 M5 Lane A build state

Branch: ajc-64-m5-lane-a | Spec: adjudica-documentation-rollback/Plans/research/wcce-medical-story/ajc64-m5-spec.md @ rev 13.3 (FROZEN + administrative mutant allocation @ docs 9d4bb54)
S0-TREE: bb29564f266781455015dfb9063a8e25af3c5343 | Seating: Sonnet implements, sol review loop, Gemini after 3 non-approving rounds, Fable orchestrates/QCs/commits

| item | status | evidence | last update |
|---|---|---|---|
| 0a §4751 correction (M5-R39) | QC-COMMITTED b2a65a7 | agent a7cda03c report; QC re-run 226 pass | 08-19 |
| 0b rating-lane pins (M5-R42) | QC-COMMITTED faa2159 | same bundle; PDRS re-parse 800/215/808/1000/5085 | 08-19 |
| 0c authority_status (M5-R40) | QC-COMMITTED 5d9af4d | golden movement money-w2 facts-only verified | 08-19 |
| 0d settlement labelling (M5-R41) | QC-COMMITTED 911f91e | m24-29 re-run RED by orchestrator; named successor SHAs | 08-19 |
| 0e statute pinning (M5-R47) | QC-COMMITTED 53db2ad; Kopping ESCALATED | M5_KOPPING_PIN_ABSENT; §4663 pre-2016 partial (SB 1171) | 08-19 |
| goldens re-record (0c/0d) | QC-COMMITTED (post-0e commit) | 6 corpora byte-identical after re-record | 08-19 |
| pre-lane sol review round 1 | FIX ROUND DONE — QC-COMMITTED ccd4f12 | F1-F5 all fixed; m24-148..155 RED; money-showcase successor 540571c2 | 08-19 |
| F1 0e regulatory cross-check (BLOCKER) | FIXED | REAL regulatory_sections rows pulled from wc-kb Postgres (4663=1805ch/2016-01-01, 4664=1479ch); vendored tests/fixtures/regulatory-sections/ + provenance.json; comparator now EXACT both directions; probes: truncate/append/1-char x2/absent/narrow-heading; m24-149 RED, m24-148 RED | 08-19 |
| F2 prose deductions unlabelled (MAJOR) | FIXED | _label_prose_deductions() in fact_templates (OUTSIDE 0d AST-frozen regions); fee+costs+MSA prose on C&R, fee prose on stips; rendered anti-probes x4 variants + positive controls; m24-150 RED, m24-151 RED | 08-19 |
| F3 render-path property oracle (MAJOR) | FIXED | TestRenderedFigureProperty: 8 sha256(case_id)-derived grosses x MSA on/off x both families, figures read BACK OFF the rendered page vs literal equations; m24-152 RED (stips fee base) | 08-19 |
| F4 m24-147 repoint withdrawn (MAJOR) | FIXED | repoint was based on WRONG function (clamp in _reimbursement_nearest_five_percent, not derived-gross branch); contractual formula guard built on money.py:1785-1803 derived branch; m24-147 RED (naive drops td_total); leak probe split to m24-153 RED | 08-19 |
| F5 0b provenance not reproducible (MAJOR) | FIXED | tools/pdrs_extract.py in-tree (pdftotext -layout, poppler 22.02.0 pinned, both ends digest-pinned); source PDF vendored cfabf43b… (4,005,811 B) + extracted text 827d6644… both in PDRS_VENDORED_ARTIFACTS; skippable gate replaced by 3 mandatory tests + oracle-completeness guard; m24-154 RED, m24-155 RED | 08-19 |
| R2-1 property incomplete (MAJOR) | FIXED | render_one_subtype() drives renderer.render_document per subtype (seeds' planner can only emit 2-3 of the 11); TestForcedSubtypeFigureProperty = 11 subtypes x MSA on/off x 6 generated grosses, no next() selection; PROPERTY_GROSSES from seeded PRNG + floor/41 boundaries; coverage asserted as data (22-cell matrix == registry); superseded next()-based class deleted; m24-202 repointed, RED | 08-19 |
| R2-2 F4 oracle loosened (MAJOR) | FIXED | 6 literal fixtures (case_id, rng_seed, pd_rate, td_total, gross, weeks) at base_weekly_wage=500/td_weeks=8 -> pd 290.00 + integral TD so whole-dollar step is a no-op; EXACT equality, zero tolerance, no _rng/_whole_dollars/money; AST self-check bans those identifiers; m24-147 repointed RED, m24-208 (reintroduce _rng) RED | 08-19 |
| R2-3 fake leak mutant (MAJOR) | FIXED | oracle now inspects OUTWARD SURFACES: truth-manifest key set (build_case_truth_manifest), money pydantic model_fields, generated manifest keys + case_facts.yaml + every rendered page; m24-203 moved to truth_manifest.py _money_channel settlement block (a real outward path), RED | 08-19 |
| R2-4 missing canonical digests (MAJOR) | FIXED | CANONICAL_SHA256 literals pinned in the consuming test (4663=9ab13ad0..., 4664=9ff019d5...); BOTH sources hashed separately after identical canonicalization; separation probe asserts the digest appears nowhere in the fixture dir; m24-207 (read from provenance.json) RED | 08-19 |
| R2-5 mutant-id namespace collision (MAJOR) | FIXED | m24-150..155 renumbered to m24-200..205 across mutants.toml + 2 test modules; Lane-B block 150-169 verified EMPTY, 170+ untouched, no dupe ids; allocation-ruling comment in mutants.toml; preflight 332 guards 1:1 | 08-19 |
| R2-6 prose labelling not idempotent (MAJOR->MINOR) | FIXED | guard moved from callback into the PATTERNS (_NOT_ALREADY_LABELLED on all four) + _PROSE_MONEY made possessive: the lookahead alone still let the regex backtrack to the PREFIX $816.0 and double-label; twice-applied test per pattern + structural completeness test; m24-206 RED | 08-19 |
| R2-7 stale comments (MINOR) | FIXED | item0e module docstring: regulatory_sections escalation DISCHARGED (Kopping remains, with the 401/403/410 evidence); item1 PROVISIONAL-S2 caveat marked discharged + re-captured, byte-identity test docstring corrected | 08-19 |
| Round-2 gate bundle | GREEN | full suite 2332 collected / 0 failed (EXIT=0, +169 vs round 1); ruff All checks passed; preflight 332 guards 1:1; golden gate PASSED 6/6 UNCHANGED (R2-6 was latent — production invokes the pass once); m24-147/148/149/200-208 + m11-1 all RED alone; 421 mutants, every anchor present exactly once, no residue, no dupe ids | 08-19 |
| R3-1 sample still frozen (MAJOR) | FIXED | per-run seed (SystemRandom, replay via AJC64_PROPERTY_SEED, reported in every failure message); 50 draws PER CELL over the FULL literal [3, 10_000_000] admissible range (was 6 memoized values to 400k = 4% of range) + boundaries floor/floor+1/ceiling-1/ceiling always tried; per-cell seeding so 22 cells draw different values; measured budget 0.147s/render -> ~162s; DELETED PROPERTY_CASE_IDS, gross_for_case, PROPERTY_GROSSES, hashed-grid block; m24-202 repointed RED, m24-209 (re-freeze the sampler) RED | 08-19 |
| R3-2 stale S2 wording (MINOR) | FIXED | test_ajc64_item1.py:111 'PROVISIONAL' -> 'FINAL S2 capture' | 08-19 |
| R3-3 blank line at EOF (MINOR) | FIXED | trailing newline trimmed; git diff --check CLEAN | 08-19 |
| Round-3 gate bundle | GREEN | full suite 2225 collected / 0 failed (EXIT=0); ruff All checks passed; git diff --check CLEAN; preflight 333 guards 1:1; golden gate PASSED 6/6 unchanged; m24-202 + m24-209 RED-alone; 422 mutants, every anchor present exactly once | 08-19 |
| G-1 run-seed refreeze unguarded (MAJOR) | FIXED | m24-209's guard monkeypatches PROPERTY_SEED so it proves only that sample_grosses READS it; added test_the_run_seed_itself_is_not_constant (8 draws must all differ with the override absent) + m24-210 (`return 42`) RED; sibling probe m24-909 (getrandbits(1)) also RED | 08-20 |
| G-2 subdivision_text slices at inline cross-refs (MINOR) | RECORDED, NOT FIXED | VERIFIED by execution: subdivision_text(4663,'(e)') returns '(e) Subdivisions' — truncated at the inline '(a)' at offset 1491. Latent only while SECTION_4663_MODELLED_SUBDIVISIONS == ('(a)','(c)'); guard warning added AT that constant naming the exact failure; orchestrator tickets the fix | 08-20 |
| G-3 one-time mutant audit (14 mutants) | DONE | 14 sibling probes executed (m24-901..914, all removed after); 11 guards reddened under a second spelling; 3 GAPS found and closed: m24-211 (leak to PAPER not envelope), m24-212 (cells collapsed, sample still per-run), m24-213 (expectation recomputed in the corroboration — UNCOVERED anywhere, new structural guard added). No baseline mutant lost; 423 -> 426 | 08-20 |
| 0e Kopping pin (M5-R20a) | PINNED — escalation DISCHARGED | CourtListener REST v4 cluster 2296517 authenticated (token via Secret.ts, never printed): 200; case_name 'Kopping v. Workers' Compensation Appeals Board', filed 2006-09-11, Published, 142 Cal.App.4th 1099. Artifact vendored VERBATIM data/statutes/case-kopping-2006-142-cal-app-4th-1099.html (52,292 B) raw sha256 381f76f7…41faf81a + canonical sha256 0f352b8f…35863d72, both pinned in module AND test. HOLDING replaced with a LITERAL opinion sentence — the prior paraphrase appears NOWHERE in the text, so M5-R20a's substring contract would have failed. require_kopping_pin() returns; require_kopping_holding() green; m24-214 (self-compare) + m24-215 (decorative substring) RED | 08-20 |
| Fix-round gate bundle | GREEN | full suite 2163 collected / 0 failed; ruff All checks passed; preflight 328 guards 1:1; golden gate PASSED 6/6 (money-showcase deliberately re-recorded for F2 prose labels, named successor 540571c2…7953e633a in test_golden_corpus.py + test_ajc63_validator.py, label-only: facts/seed did not move); m11-1 re-anchored (F2 duplicated its find text) + m24-147..155 all RED alone with anchors verified present and no residue | 08-19 |
| 1 | QC-COMMITTED 3f069e8 (cherry-pick from ajc-64-m5-item1 5e1836c) + c4b4cbe S2 final | Opus supervision F1 fixed; 29/29; golden gate PASSED | 08-19 |
| 2, 3 | PENDING (parallel wave) | — | — |
| 4 | UNGATED — Kopping PINNED 08-20 (cluster 2296517, raw 381f76f7, canonical 0f352b8f; verbatim holding of record, register ce9f170) | pin + m24-214/215 in d6e8530 | 08-20 |
| 5, 7 | PENDING (parallel wave) | — | — |
| 6, 8 | PENDING (parallel wave) | — | — |
| 9 | PENDING | — | — |
| 10, 11, 12 | PENDING (serial) | — | — |

Escalations: NONE OPEN. Kopping pin DISCHARGED 08-20 (Alex token via JTT g4; pinned d6e8530). §4663 residual ACCEPTED by Alex 08-20 (JTT g5, register 578c3c0). Mutant count: 422 at 5a6d1d8 → 428 at e22e128 (sol round-4 corrected figure). Vendored-artifact exception: case-kopping-2006-142-cal-app-4th-1099.html carries source-verbatim trailing whitespace (raw-digest-pinned; NEVER trim; range-scoped git diff --check excludes vendored artifacts by design).

## Review log
| round | reviewer | verdict | disposition |
|---|---|---|---|
| 1 | sol (GPT-5.6, thread 01a01c33-f28a-76d1-a04f-71af099b4a58) | FINDINGS 2B/4M | F1-F5 ruled FIX, dispatched to owning implementer 08-19; F6 (exec attestation) satisfied by orchestrator gates + fix-round bundle |
# AJC-64 item 1 build state (worktree ajc-64-item1, branch ajc-64-m5-item1)

| item | status | evidence | date |
|---|---|---|---|
| 1 | BUILT — PROVISIONAL S2, re-capture required post F1-F5 merge | tests/test_ajc64_item1.py 29/29 pass; m24-23 RED-alone + clean revert; ruff clean; preflight 322/322; golden gate 5/6 OK (demo-caseload FAILED — pre-existing pymupdf 1.28.0-vs-1.28.2/substrate env drift, untouched by item 1, not caused by this work); full suite 1 failed (same demo-caseload drift) / rest green; never committed | 08-19 |
| 1 fix round | F1-HIGH (Opus supervision) FIXED | recordedWith exemption narrowed from block-prefix to exact-leaf ($.recordedWith.substrateSha only); money-showcase's substratePin movement now explicit authorized-not-filtered entry citing commit e5e0874 (verified ancestor + git show matches before/after values); 2 new tests added (authorization exactness + e5e0874 positive control); re-run: targeted 29/29, ruff clean, preflight 322/322, m24-23 RED+clean-revert | 08-19 |
| 2 | sol (delta re-check, same thread) | IN-FLIGHT | scope ccd4f12+3f069e8+c4b4cbe | 08-19 |
