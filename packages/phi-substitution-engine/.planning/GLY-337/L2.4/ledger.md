# L2.4 durable reversal store — evidence ledger (GLY-337 M2)

Author: Claude Engineer. Gate: GPT-5.6-sol (`codex exec`, read-only), cross-family. Orchestrator: Fable-5 (main context).
Base: M1 merged `7a50418`. Branch `GLY-337-durable-reversal-store` (worktree `_gbx-worktrees/GLY-337-L2.4`), not pushed.

## Gate round 1 (BLOCK) — findings F1–F4, all fixed by author
- F1 cross-replica atomic publication → `40354d4` (shared backend + synchronous `publishAtomic`).
- F2 warm-DEK-cache substituted material → `e52ff0f` (cache key binds wrappedDek fingerprint + keyId).
- F3 C1 scrub re-exports contaminated ReversalFailedError → `3f7aaf4` (both catches discard + fresh error).
- F4 (MEDIUM) new oracles miss the blocking paths → resolved (warm-cache + two-mount + contaminated-error oracles added).

## Orchestrator verification of the fix round (before re-gate)
- Found + fixed raw-NUL hygiene: author used literal 0x00 as injective separators → binary source files. `52e7034` replaces with `\0` escape (runtime-identical). Zero NUL bytes remain in patch/source.
- Found + fixed AAD injectivity coverage gap: MUT-AAD-DROP-TENANT/-MATTER SURVIVED the relocation oracles (DEK bindingDigest backstops tenant+matter). Added pure per-field injectivity oracle `d6708b5`. No live vuln.
- Independently mutation-proved 20 oracles RED (6 core + 4 fix-round + 10 AAD-field). tsc clean, 299 tests.

## Gate round 2 (BLOCK) — `l2.4-gate3.out`, gpt-5.6-sol, 285K tokens. Orchestrator triage:
- **F(2nd)-1 HIGH — different-attempt/same-mapping-key publish→flush race. VALID → FIX.**
  Mechanism CONFIRMED: two attempts A,B on the same mappingKey (same tenant/matter/version/token, different attemptId — the SAME PHI value tokenized in two concurrent operations of one matter). A.publish, B.publish overwrites `#mappings[key]→B` (`in-memory-spool-volume.ts:181`). A.flush → `#persistPublicationMetadata` marks A's bytes+claim durable but the mapping guard `mapping.commit===A` is FALSE (points to B) so the mapping is NOT marked durable (`:216-219`). A's `record()` acks. Reads follow B (unflushed) → absent; if B never flushes + `crash()` deletes unflushed mapping→B while A's flushed claim survives → token PERMANENTLY unresolvable despite ack. N4 (durable-before-egress) violation. No realm poisoning → in scope.
  Required: dev spool tracks a DURABLE current-mapping separately from the provisional last-writer pointer; `flushCommit(X)` promotes the durable mapping→X unconditionally (X is committed); `crash()` keeps durable mappings, discards provisional; committed reads resolve via the durable mapping. Store must not ack while the durable-readable mapping is absent. New oracle: two-mount, different-attempt, A.flush released while B stays gated / then B.flush fails + crash → A's token still resolves.
- **F(2nd)-2 HIGH — F3 boundary input read outside the scrub try. VALID → FIX.**
  `record()`: `const canonical = input.canonical` at `:78` precedes `try{` at `:79`. `resolve()`: `input.tokens.length` (`:206`) and `for (const token of input.tokens)` (`:212`) precede `try{` at `:222`. A throwing getter/iterator escapes with its original message/cause/PHI, violating C1's fixed surface. Not intrinsic poisoning (property of the passed argument, not a global) → in scope.
  Required: snapshot/validate ALL boundary input inside the scrubbed method boundary; always emit a fresh ReversalFailedError. Oracles: throwing `canonical` getter (record) + throwing `tokens` iterator/`length` getter (resolve) → both reject with a cause-free REVERSAL_FAILED.
- **F(2nd)-3 HIGH — per-token retention → mixed retention. REJECT as code defect.**
  False premise (gate never got prior-F4 text, fabricated "retention" as F4; real F4 = missing-oracles, resolved). And `classifyRetention` at `:89` is called with `{tenantId,matterId,attemptId}` ONLY — never the token — so it is operation-scoped by construction (satisfies C3 "property of the OPERATION, never inferred from token shape"). A deterministic classifier CANNOT mix retention across tokens of one operation; replays are pinned by first-write-wins idempotency. Mixed retention requires a NON-DETERMINISTIC trusted classifier = a misbehaving trusted seam, out of the ratified bounded threat model; and its effect is a TTL/governance inconsistency, not PHI egress. → Strengthen classifier port JSDoc to state the determinism/operation-consistency contract; add an operation-consistency oracle (two record()s of one op observe one class); TICKET the "store-enforced operation-retention binding vs classifier-determinism reliance" as governance follow-up (peer of addendum Q3/Q4/Q8).
- **F(2nd)-4 MEDIUM — C2 converts infra failures to REVERSAL_FAILED. Binding amendment, no code change.**
  Under the sole all-or-nothing consumer (`reverseText`), store-throw-on-infra ≡ partial-map-then-reverser-throws end-to-end (both → whole reversal REVERSAL_FAILED); the F3 scrub discards the cause, so no PHI leaks; an explicit REVERSAL_FAILED on a genuine outage is a clearer signal than silently omitting the token. C2's enumerated throw-conditions addressed distinguishing TAMPER from ABSENCE, not availability. → Amend addendum with a C2-availability clarification (fail-closed on infra/availability failure is correct); flag for revisit IF a partial-map-tolerating caller is ever added.

## Rulings summary
FIX: F(2nd)-1 (durable-vs-provisional mapping model + oracle), F(2nd)-2 (scrub-boundary + throwing-input oracles), F(2nd)-3-oracle+JSDoc.
NO-CODE: F(2nd)-3-enforcement (governance ticket), F(2nd)-4 (C2-availability amendment).
Cross-family split preserved: Claude Engineer authors the fixes; GPT-5.6-sol re-gates.
