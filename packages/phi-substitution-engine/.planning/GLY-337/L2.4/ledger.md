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

## Fix round 2 applied — commit `7ee2e50` (orchestrator-authored, reviewer-prescribed; GPT re-gates)
- Fix 1: dev spool durable-vs-provisional current-mapping split (`#durableMappings` written only by flush,
  last-flush-wins, survives `crash()`; reads + attacker-sim follow it). Store unchanged.
- Fix 2: moved `record().canonical` + `resolve()` batch-check/iteration inside the scrub `try`.
- Fix 3: classifier port JSDoc determinism contract + operation-consistency oracle. Store unchanged.
- Addendum: C2-availability + C3-determinism binding clarifications (findings 3,4 → no code change).
- tsc clean; 303 tests.
- **Mutation evidence — 23 guards each reverted → paired oracle RED → restored (tree @ 7ee2e50):**
  core(5): RETURN-BEFORE-FLUSH, SKIP-READ-TTL, REUSE-GCM-NONCE, FALLBACK-TENANTLESS, IGNORE-GCM-TAG;
  fix-round-1(4): F1-NONATOMIC, F2-WARMCACHE-DEK, F2-WARMCACHE-KEYID, F3-CONTAMINATED;
  fix-round-2(4): DURABLE-MAPPING-STEAL, CLASSIFY-PER-TOKEN, MUT-INPUT-OUTSIDE-SCRUB(record), (resolve);
  AAD injectivity(10): field 1..10 each drop → its oracle RED.
  (AAD-tenant/-matter relocation oracles are backstopped by the KeyProvider bindingDigest — known
  redundant survivors; the 10 injectivity oracles are the isolating guard.)

## Gate round 3 (BLOCK) — `l2.4-gate4.out`, gpt-5.6-sol, 177K tokens. VERIFIED fixes 2/3/4; found 2 HIGH in the round-2 mapping model:
- F(3rd)-1 HIGH — unconditional last-flush-wins rolls the durable current canonical BACK. An old-attempt
  replay flushes its original (lower-ordinal) commit and overwrites a newer one; likewise A.publish→
  B.publish→B.flush→A.flush leaves A current. Contradicts spec §9/§10 (current record = atomic publication
  order) + the "different attempts advance the current canonical" test. My "same canonical" assumption was
  WRONG (different attempts UPDATE the canonical). → FIX.
- F(3rd)-2 HIGH (pre-existing, exposed) — flushCommit(unknown commit) was a silent no-op success, so a
  gated peer of an existing-claim commit erased by crash() acks with NO durable mapping (N4). → FIX.
Fix round 3 (commit `d0e146c`): monotonic publication ordinal per commit; durable pointer advances ONLY
to a higher ordinal (MUT-DURABLE-ROLLBACK); flushCommit fails closed on an unknown/lost commit
(MUT-FLUSH-LOST-COMMIT). Store unchanged. tsc clean, 306 tests.
Mutation evidence (tree @ d0e146c): DURABLE-ROLLBACK (kills both replay + late-flush oracles),
FLUSH-LOST-COMMIT, + re-confirmed moved spool guards F1-NONATOMIC, REUSE-GCM-NONCE, DURABLE-MAPPING-STEAL.
25 guards proven total (5 core + 4 fr1 + 4 fr2 + 2 fr3 + 10 AAD injectivity).
Gate round-3 dispositions on my triage: F2 verified fixed; F3 AGREED (reject); F4 AGREED (C2 amendment).

## Gate round 4 (BLOCK) — `l2.4-gate5.out`, gpt-5.6-sol, ~170K tokens. VERIFIED both fix-round-3 durability fixes + all 7 axes; one HIGH:
- F(4th)-1 HIGH — `#handleSeq`/`#publishSeq`/`ordinal`/`#commitOrdinal` were IEEE-754 `number`; at 2^53
  `+= 1` no longer changes the value → repeated commit/prepared handles (commit-index overwrite; a pending
  older flush flushes a later commit's ctx and returns success while its own claim stays unflushed) and
  tied ordinals (strict `>` can't advance the durable pointer for a newer publication). In scope (no
  poisoning — pure sequence exhaustion). → FIX.
Fix round 4 (commit `ecc3749`): converted all four to `bigint` (arbitrary precision — the nonce counter
was already bigint). tsc now enforces the bigint discipline throughout, so a regression to `number` fails
typecheck; a literal 2^53 exhaustion oracle is infeasible and moot (no representable saturation). Store
unchanged. tsc clean, 306 tests. MUT-DURABLE-ROLLBACK re-confirmed red with bigint ordinals.
Gate round-4 dispositions: F(3rd)-1 rollback fix VERIFIED; F(3rd)-2 lost-commit fix VERIFIED; all other axes clear.

## Crown-jewel security review (post-APPROVE) — 2 Claude-family agents, read-only
- security-auditor (OWASP/PHI-egress): NO in-scope PHI-egress/capability/crypto/tenant defect. 2 INFO
  (DEK cache no-eviction → G4/Q5; capability boundary rests on package `exports` allowlist → add a guard).
- Silas (offensive leak probe, claude-opus-4-8): NO valid in-scope attack chain for any of the 4 goals
  (plaintext/DEK extraction, illegitimate reversal, cross-boundary read, egress-without-durable-mapping).
  One fix recommended pre-ship (F1); rest governance-deferred/cosmetic.
Folded in (commit `0cf58df`):
- Silas F1: resolve() now snapshots `{tenantId,matterId,dictionaryVersion}` once at the top of the scrub
  try (symmetry with record()'s F(2nd)-2 hardening); removes the only read-path TOCTOU. Oracle
  MUT-RESOLVE-SCOPE-TOCTOU proven red (flipping dictionaryVersion getter re-read diverges → reject).
- Auditor INFO#2 / Silas capability: strengthened factory-smoke forbidden-root-export list with the L2.4
  durable symbols + new guard asserting package.json `exports` == {".","./package.json"}, no wildcard.
Deferred to G4/governance (NOT this unit): DEK cache TTL/eviction/zeroization (Q5); orphaned prepared-blob
reclamation (Q3); warm/cold cache timing (cosmetic); resolve returns live Map as ReadonlyMap (deliberate C4).
tsc clean, 308 tests, 26 guards mutation-proven (adds MUT-RESOLVE-SCOPE-TOCTOU).
