# AJC-64 M5 — Item 1 PLAN (Wave 1, solo lane)

Spec of record: /home/vncuser/projects/adjudica-documentation-rollback/Plans/research/wcce-medical-story/ajc64-m5-spec.md (rev 13.2 FROZEN, docs commit 0f9c62d). Read ONLY the sections cited below — never the whole spec. Ambiguity in this excerpt goes back to the orchestrator, never resolved by guessing.

## Scope (spec §8 row 1, line 3484)
Baseline instruments:
1. Capture **S2** — the six golden dicts at the post-pre-lane tree.
2. Prove **S2 − S0-GOLDEN equals the union of the three pre-lane allowlists** (0c money-w2 facts cascade, 0d money-showcase labels, 0a's empty set). S0-GOLDEN and S0-TREE (bb29564f266781455015dfb9063a8e25af3c5343) were captured in item 0a — find them in the committed pre-lane work.
3. Pin `MONEY_CHANNEL_VERSION`, `SUPPORTED_MONEY_CHANNEL_VERSIONS`, `MONEY_V1_2_*` as literal oracles.

## Independent literal oracles (spec §8 row 1)
- Six golden dicts at S2 (byte-level).
- The S2 − S0-GOLDEN set-equality proof (computed, not asserted by hand).
- Literal pre-M5 channel key sets.
- v1.1 / v1.2 dispatch witnesses (each legacy channel version dispatches to its own path — witness fixtures, not just version-string checks).

## Mutant (spec §7 M5-R37, line 2836)
- `m24-23 MONEY-V1_3-GLOBAL-UPGRADE` — register in tests/mutants.toml; must red alone under its named guard and revert clean. Definition context at spec lines ~1645-1660 (M5-R27) — read that range.

## Sections to read (line ranges in the spec)
- §6 M5-R26–R30 (lines 1614–2267): seed gate, channel 1.3.0, caseload contract, golden protocol M5-R30 — the S2/S0 semantics live here.
- §8 implementation order row 1 + dependency notes (lines 3475–3512).
- §13 completion criteria rows touching item 1 (lines 3706+, grep "item 1").

## File map
Engine package: packages/wc-synthetic-caseload-engine/. Expected touches: a new tests/test_ajc64_item1.py, tests/mutants.toml (append only), possibly src/wc_caseload_engine/manifests.py or money.py for the version-constant pins IF the spec requires code-side constants (verify against M5-R27 — do not invent constants the spec doesn't name). No other production files.

## SEQUENCING CAVEAT (binding)
A concurrent fix round (sol round-1 findings F1–F5) is landing on branch ajc-64-m5-lane-a and WILL move goldens again (F2 changes rendered settlement prose). Therefore:
- Build ALL machinery now (equality prover, channel pins, dispatch witnesses, m24-23) against the current tree.
- Mark the captured S2 as PROVISIONAL in a module-level constant + comment.
- Your final report must state that S2 re-capture is required after the fix commits merge; the orchestrator will trigger it.

## Gates (two-stage discipline)
- Per edit cycle: targeted modules only (`env OMP_THREAD_LIMIT=1 timeout 600 .venv/bin/python -m pytest -q tests/test_ajc64_item1.py`).
- Once at the end: full suite (`timeout 2400 ... -m pytest -q`), ruff check, `tools/mutation_gate.py --preflight`, `--only m24-23` (verify it applied — a probe whose anchor didn't match prints a false green), golden gate.
- Ship RAW output for all of the above.

## Contract
Work ONLY in /home/vncuser/projects/gbs-tools-and-resources/.claude/worktrees/ajc-64-item1 (branch ajc-64-m5-item1). NEVER commit, NEVER push, never touch AGENTS.md. Append progress rows to .planning/ajc-64/STATE.md in THIS worktree (item | status | evidence | date) after each milestone. Classify every fix/deviation (shortcut vs better design). The orchestrator commits on receipt after Opus supervision review.
