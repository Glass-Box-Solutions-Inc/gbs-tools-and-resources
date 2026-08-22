/**
 * GLY-373 §3.2.6 — the ONE branded, frozen conflict sentinel.
 *
 * Two deliberate PHI-scrub seams sit between the reversal-key conflict of §3.2.5 and the caller:
 *   S1 — `DurableReversalStore.record()`'s blanket `catch { throw new ReversalFailedError(); }`
 *   S2 — the orchestrator's `catch { throw new PhiEngineError("REVERSAL_FAILED", …); }`
 * Both exist to stop an untrusted value riding out of a failure, and BOTH KEEP DOING THAT for
 * every value except this one. Without a pass-through the ruled `AMBIGUOUS_KNOWN_IDENTIFIER`
 * disposition is unobservable and ruling C (§10.2) is unverifiable.
 *
 * WHY AN OBJECT AND NOT A STRING. The sentinel must be IDENTITY-BEARING AND NON-FORGEABLE. A
 * primitive string/number/bigint/boolean sentinel is PROHIBITED: executed evidence shows
 * `Object.freeze()` accepts a string, an injected dependency can simply throw the equal string,
 * `===` passes, and the conflict disposition is observed —
 * `{"ObjectFreezeAcceptsString":true,"attackerCanThrowEqualValue":true}`. A value an untrusted
 * dependency can CONSTRUCT is not an identity check; only one it cannot OBTAIN is. This binding is
 * module-private in the sense that matters: it is never exported from the package root (OR-08 pins
 * that surface) and never returned to a caller.
 *
 * It carries ZERO own properties — no canonical, token, id, or caught error — so there is nothing
 * for it to leak. It is not an `Error`, not a `PhiEngineError`, and is not constructed per call.
 *
 * Seam contract (all six clauses of §3.2.6):
 *   - the conflict path throws THIS EXACT VALUE and nothing else;
 *   - each seam compares by IDENTITY (`caught === REVERSAL_CANONICAL_CONFLICT`) against this
 *     binding — never by `code`/`name`/`message`, never `instanceof`, never a duck-type check,
 *     any of which an untrusted injected dependency could forge (OR-16(b));
 *   - on a match S1 rethrows the sentinel unchanged and S2 constructs a FRESH frozen
 *     `PhiEngineError("AMBIGUOUS_KNOWN_IDENTIFIER", operationId, { conflict: … })`;
 *   - on EVERY non-match the existing blanket scrub is unchanged, verbatim;
 *   - the sentinel never reaches a caller, `safeDetails`, a log, or the audit record.
 * MUT-37 makes a seam propagate the upstream error object instead and MUST go RED.
 */
export const REVERSAL_CANONICAL_CONFLICT: object = Object.freeze(
  Object.create(null) as object,
);

/**
 * The fixed, PHI-free triage discriminator carried in `safeDetails.conflict`.
 *
 * `AMBIGUOUS_KNOWN_IDENTIFIER` is shared with dictionary ambiguity and is an honest approximation:
 * no `PhiEngineFailureCode` member denotes a persistence conflict, and the ruling forbids widening
 * the published union. `AUDIT_DURABILITY_UNAVAILABLE` was rejected (it would send an operator to
 * check store health when the store is healthy and the write was refused deliberately) and
 * `REVERSAL_FAILED` was rejected (it names the wrong operation — this fails during `substitute()`).
 * A dedicated code is recommended for the next major. This literal is what disambiguates triage
 * without a union change, and it is projected into the durable audit record (OR-15(i)/OR-16(f)) so
 * the disposition survives to the record an operator reads weeks later.
 */
export const REVERSAL_CANONICAL_CONFLICT_DETAIL =
  "reversal-key-canonical-mismatch";

/** Identity comparison against the module-private binding. Never a shape or `code` test. */
export function isReversalCanonicalConflict(value: unknown): boolean {
  return value === REVERSAL_CANONICAL_CONFLICT;
}
