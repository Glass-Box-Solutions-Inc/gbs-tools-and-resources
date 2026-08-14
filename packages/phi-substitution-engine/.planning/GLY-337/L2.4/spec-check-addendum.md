# L2.4 spec — Opus spec-check addendum (binding corrections to sol's spec)

Verdict: **APPROVE with corrections.** sol's spec (`L2.4-spec.out`) is strong — the binary AAD
composition, tenant-scoped idempotency with the unflushed-race branch, nonce uniqueness,
atomic-publish/durable-flush, and the 25 named mutations are all correct and adopted. The
following corrections are **binding** and were verified against the merged `main` code
(commit 7a50418). The Engineer implements sol's spec AS AMENDED HERE.

## C1 — Error codes (resolves sol Blocking Q1). VERIFIED against `core/errors.ts` + `orchestrator.ts`.
The frozen `PHI_ENGINE_FAILURE_CODES` registry has **no** write/expiry-specific code and may not be
widened (§5: no weakening without principal+security approval). Bind ALL of sol's aliases to the
existing reversal-subsystem code:
- `WRITE_FAIL` → **`REVERSAL_FAILED`**. Authoritative: `orchestrator.ts` already wraps a `record()`
  throw/rejection in `new PhiEngineError("REVERSAL_FAILED", operationId, {})`. The store rejects via
  `ReversalFailedError` (= `REVERSAL_FAILED`); the orchestrator contains it. Do NOT use
  `AUDIT_DURABILITY_UNAVAILABLE` — that is the N3 **audit** store, a different subsystem.
- `RESOLVE_FAIL` → **`REVERSAL_FAILED`**.
- `EXPIRED_FAIL` → **`REVERSAL_FAILED`** (a record-side expired-replay rejection is contained by the
  orchestrator catch anyway). No distinct code.
Error surface stays fixed/safe per §7 (no cause, no canonical/token/provider text).

## C2 — Resolve is PARTIAL-MAP, not reject-all (corrects sol req 14 & 17, MUT-PARTIAL-RESOLVE, and the
"resolution is all-or-nothing" oracle). VERIFIED against `tokens/reversal.ts`.
sol specified the STORE rejects the whole lookup on any missing/expired token. That **contradicts the
frozen layering** and breaks the swap-in invariant:
- `InMemoryReversalStore.resolveEncounteredTokens` returns a **PARTIAL map** — a token not found is
  simply ABSENT from the returned map; it throws only on **batch-size violation**.
- N5 all-or-nothing lives in the **reverser** (`reverseText`), which already iterates the distinct
  tokens and throws `ReversalFailedError` on ANY absent token ("Known-shape but unknown token: fail
  visibly"), and already CONTAINS an untrusted store's rejection/throwing-map in try/catch.
Therefore the durable store MUST behave identically to `InMemoryReversalStore`:
- **Missing token** (never recorded) → **absent from the returned partial map**. NOT a throw.
- **Expired detector token** → **absent from the returned partial map** (treated as not-present). NOT
  a throw. The reverser fails closed on the absence → same safe outcome, correct layer.
- The store throws `REVERSAL_FAILED` ONLY on: (a) **batch-size violation** (matches existing), and
  (b) **crypto-integrity failure** — GCM tag / AAD-mismatch = tamper evidence, a hard security event
  (contained by `reverseText`). Distinguishing tamper (throw) from absence (partial) preserves the
  security signal without conflating "not recorded" with "attack".
Update the oracles: the STORE-level oracle asserts **partial-map parity with `InMemoryReversalStore`**
(missing/expired absent) + **fail-closed-on-tamper**; the **all-or-nothing** oracle moves to the
reverser/integration level (absent token → whole reversal `REVERSAL_FAILED`, no partial DisplayText).

## C3 — Retention discriminator (resolves sol Blocking Q2). ACCEPT with tightening.
`ReversalRecordInput` is frozen and carries no retention field; widening it needs principal+security
approval, so sol's injected identifier-only `classifyRetention(tenantId, matterId, attemptId)`
dependency is the correct non-breaking choice. Tighten: the retention class is a property of the
**operation** (attemptId), determined once from **trusted operation context** set at operation start,
**consistent across every `record()` in that operation**, **fail-closed on unknown/error**, and
**never inferred** from token shape, matter-ID convention, or branding. The classifier receives
identifiers only — never canonical or token (sol already requires this).

## C4 — Hardened returned map (sol req 18 & MUT-NATIVE-MAP-RESULT / MUT-FORGEABLE-VIEW-CTOR).
DOWNGRADE to optional defense-in-depth. **Behavioral parity with `InMemoryReversalStore`'s returned
map is REQUIRED** (swap-in invariant); `InMemoryReversalStore` returns a plain `Map`, and the map
never crosses an untrusted boundary (the reverser consumes it in-process and produces DisplayText). A
hardened `#private`-backed `ReadonlyMap` view is acceptable but MUST NOT change observable behavior or
diverge from the dev store. Do not block the lane on it. (The #private requirement for the store's own
**DEK cache / retained canonical / wrapped-key** fields — req 19 — STANDS; keep those mutations.)

## Open questions — dispositions (sol §E 3-9)
- Q6 (mounted-volume atomic-publish/durable-nonce/flush guarantees): **BLOCKING for DEPLOY (L4.D/G4)**,
  NOT for the store built against the `SpoolVolume` port + a dev impl. Flag for G4: prove Azure Files
  (Premium) supports cross-replica atomic rename + durable flush; container-local fsync is not evidence.
- Q3 (tombstone retention duration), Q4 (DEK rotation), Q5 (KEK/DEK cache TTL), Q7 (clock authority),
  Q8 (matter-retention deletion mechanism), Q9 (namespace disjointness): **v1 defaults acceptable**,
  not blocking implementation. v1: single DEK generation per (tenant,matter) with the DEK-generation-id
  in AAD already supporting rotation later; injected `nowEpochMilliseconds` clock; tombstones persist
  until tenant/matter deletion; sol's "absent + fail closed" namespace default. Ticket the governance
  decisions (rotation policy, tombstone horizon, deletion lifecycle) as follow-ups; do not silently
  decide them in code.

## C2-availability — infra/availability failures fail closed as REVERSAL_FAILED (amendment, 2026-08-12)
Raised by the GPT-5.6-sol gate round 2: `resolveEncounteredTokens` catches `readCurrent` outages and
non-authentication key-provider failures and converts them to `REVERSAL_FAILED`, whereas C2 enumerates
store-throw only for (a) batch-size and (b) crypto-integrity. **Ruling: current behavior is correct and
binding.** C2's enumeration was written to distinguish TAMPER (throw) from ABSENCE (partial map) — it did
not contemplate a third category, transport/availability failure. Under the sole consumer of the store's
map — `reverseText`, which enforces N5 all-or-nothing and throws `REVERSAL_FAILED` on ANY absent token —
throwing at the store on an infra failure is END-TO-END IDENTICAL to returning a partial map and letting
the reverser throw (both yield a whole-reversal `REVERSAL_FAILED`, no partial DisplayText). The F3 scrub
discards the underlying cause, so no PHI/provider/DB text egresses either way. An explicit
`REVERSAL_FAILED` on a genuine outage is a clearer fail-closed signal than silently omitting a token.
**Constraint:** this equivalence holds ONLY while every consumer of the store's partial map is
all-or-nothing. If a future caller consumes partial maps WITHOUT all-or-nothing (e.g. best-effort
resolve), this MUST be revisited with typed integrity-vs-availability outcomes so a transient outage is
not misread as "token absent." Ticket that as a precondition of any such caller.

## C3-determinism — classifier determinism is a trusted-seam contract (clarification, 2026-08-12)
Same gate round raised per-token retention drift. `classifyRetention` is invoked with
`{tenantId, matterId, attemptId}` ONLY (never the token), so it is operation-scoped by construction and a
DETERMINISTIC classifier yields one class for every `record()` of an operation — satisfying C3's
"determined once, consistent across every record()". The store relies on classifier determinism rather
than pinning + enforcing a per-operation class in durable cross-record state. That reliance is acceptable
under the bounded threat model (the classifier is a trusted injected seam; a non-deterministic classifier
is a misbehaving trusted dependency, and mixed retention is a TTL/governance inconsistency, not PHI
egress). **Binding:** the `classifyRetention` port contract REQUIRES determinism/operation-consistency
(documented in its JSDoc); an operation-consistency oracle records the invariant. Store-enforced
operation-retention binding (first-seen class per (tenant,attempt), reject mismatch, cross-replica
consistent) is a GOVERNANCE follow-up ticket, not an M2 blocker.

## Everything else in sol's spec is ADOPTED as written
Exact surface (no listAll/snapshot), AES-256-GCM envelope, the 10-field binary AAD + rationale,
durable prepare→publish→flush, nonce durability, tenant-scoped keys, idempotency (first-write-wins,
divergent same-attempt no-op, cross-scope reject, flush-before-ack race), detector 24h TTL +
non-retryable tombstone, KeyProvider/SpoolVolume dev-prod seam, and the bounded-threat-model scope
(no intrinsic-poisoning resilience required). The named-mutation table stands except as amended by C2.
