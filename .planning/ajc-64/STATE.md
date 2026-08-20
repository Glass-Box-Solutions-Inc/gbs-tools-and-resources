# AJC-64 M5 Lane A build state

Branch: ajc-64-m5-lane-a | Spec: adjudica-documentation-rollback/Plans/research/wcce-medical-story/ajc64-m5-spec.md @ 0f9c62d (rev 13.2, FROZEN)
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
| Fix-round gate bundle | GREEN | full suite 2163 collected / 0 failed; ruff All checks passed; preflight 328 guards 1:1; golden gate PASSED 6/6 (money-showcase deliberately re-recorded for F2 prose labels, named successor 540571c2…7953e633a in test_golden_corpus.py + test_ajc63_validator.py, label-only: facts/seed did not move); m11-1 re-anchored (F2 duplicated its find text) + m24-147..155 all RED alone with anchors verified present and no residue | 08-19 |
| 1 | QC-COMMITTED 3f069e8 (cherry-pick from ajc-64-m5-item1 5e1836c) + c4b4cbe S2 final | Opus supervision F1 fixed; 29/29; golden gate PASSED | 08-19 |
| 2, 3 | PENDING (parallel wave) | — | — |
| 4 | PENDING — GATED on Kopping pin | — | — |
| 5, 7 | PENDING (parallel wave) | — | — |
| 6, 8 | PENDING (parallel wave) | — | — |
| 9 | PENDING | — | — |
| 10, 11, 12 | PENDING (serial) | — | — |

Escalations open: Kopping pin (needs CourtListener API token or alternate provenance — Alex); §4663 pre-2016 residual gap (recorded, mutant-guarded, acceptable unless Alex wants a secondary source).

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
