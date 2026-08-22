/**
 * Fixed, PHI-free failure signal for the protected provider boundary
 * (CONTRACT-phase1 §7, N2/N4). A `PhiEngineError` carries ONLY the operation id
 * and fixed safe metadata — never input text, matched text, tokens paired with
 * values, variants, excerpts, offsets, or encryption material — so a fail-closed
 * result can be surfaced without leaking a canary.
 */
import type { OperationId } from "./brands";
import type { PhiEngineFailureCode } from "./contracts";

const PLACEHOLDER_OPERATION_ID = "op-unbound" as unknown as OperationId;

export class PhiEngineError extends Error {
  public readonly name = "PhiEngineError";
  public readonly code: PhiEngineFailureCode;
  public readonly operationId: OperationId;
  public readonly safeDetails: Readonly<
    Record<string, string | number | boolean | null>
  >;

  public constructor(
    code: PhiEngineFailureCode,
    operationId: OperationId = PLACEHOLDER_OPERATION_ID,
    safeDetails: Readonly<
      Record<string, string | number | boolean | null>
    > = {},
  ) {
    super(code);
    this.code = code;
    this.operationId = operationId;
    this.safeDetails = safeDetails;
  }
}

export function isPhiEngineError(value: unknown): value is PhiEngineError {
  try {
    return value instanceof PhiEngineError;
  } catch {
    // A hostile Proxy `getPrototypeOf` / `Symbol.hasInstance` trap must not escape the check with a
    // PHI-laden throw (§7/N2). An unclassifiable value is simply not one of our errors.
    return false;
  }
}

const PHI_ENGINE_FAILURE_CODES: ReadonlySet<string> =
  new Set<PhiEngineFailureCode>([
    "MISSING_TRUSTED_CONTEXT",
    "MISSING_TRUSTED_POLICY",
    "DICTIONARY_NOT_READY",
    "DICTIONARY_UNAVAILABLE",
    "AMBIGUOUS_KNOWN_IDENTIFIER",
    "DETECTOR_UNAVAILABLE",
    "INVALID_DETECTOR_OFFSET",
    "UNCLASSIFIED_PROVIDER_FIELD",
    "AUDIT_DURABILITY_UNAVAILABLE",
    "REVERSAL_FAILED",
    "PROVIDER_SAFETY_GATE_FAILED",
    "CALL_INTERRUPTED",
  ]);

/** True only for a recognized, fixed, safe PhiEngineFailureCode (never a raw upstream code). */
export function isPhiEngineFailureCode(
  value: unknown,
): value is PhiEngineFailureCode {
  return typeof value === "string" && PHI_ENGINE_FAILURE_CODES.has(value);
}

/**
 * Reads a thrown value's `code` WITHOUT letting a hostile member escape (§7/N2): a `code` getter (or
 * a Proxy trap) that THROWS — its message could carry PHI — is swallowed and treated as "no code".
 * Returns the code only when it is a plain string; absent / non-string / throwing → undefined.
 */
export function safeCodeString(value: unknown): string | undefined {
  try {
    if (value === null || typeof value !== "object") {
      return undefined;
    }
    const code = (value as { code?: unknown }).code;
    return typeof code === "string" ? code : undefined;
  } catch {
    return undefined;
  }
}

/**
 * Maps a thrown value to a fixed, allow-listed failure code, defaulting to a safe generic code.
 * A `code` is honored ONLY if it is a recognized `PhiEngineFailureCode` — being a `PhiEngineError`
 * instance is NOT sufficient, because an injected component can construct one with an arbitrary
 * (PHI-laden) code via an `as any` cast, or expose it through a throwing getter (§7/N2). Any
 * unrecognized, throwing, or non-string code → the fallback.
 */
export function toFailureCode(
  value: unknown,
  fallback: PhiEngineFailureCode,
): PhiEngineFailureCode {
  const code = safeCodeString(value);
  return code !== undefined && isPhiEngineFailureCode(code) ? code : fallback;
}

/**
 * GLY-373 §3.2.4 — the ONE pinned zero-argument factory for the trusted-context guard error.
 *
 * A FROZEN `PhiEngineError`, NO SUBCLASS. `PhiEngineError` pins `public readonly name =
 * "PhiEngineError"` (:14) and the published interface pins `readonly name: "PhiEngineError"`
 * (`core/contracts.ts:153-160`), so a subclass could never carry its own name; with the name pinned
 * anyway a subclass buys nothing the fixed `code` does not already provide. `ContextValidationError`
 * was withdrawn by the spec and MUST NOT exist.
 *
 * The code is the EXISTING `MISSING_TRUSTED_CONTEXT` — deliberately NOT a new
 * `PhiEngineFailureCode` member, which would change a published union and force both consumers to
 * widen their code allow-lists and switches. That deviation from the ruling's suggested
 * `"CONTEXT_VALIDATION_FAILED"` literal is flagged in the spec (§3.2.4) and in the build ledger.
 *
 * The own-property graph is exactly `{ name, message, code, operationId, safeDetails, stack }` with
 * `operationId` the fixed `PLACEHOLDER_OPERATION_ID` — never a rejected handle's id (MUT-27) — and
 * `safeDetails` a FROZEN zero-key object, frozen so it cannot be populated after the shape oracle
 * runs (MUT-29(d)). No `cause` of any kind (MUT-28). OR-GLY373-14(f) is the shape oracle.
 */
export function missingTrustedContextError(): PhiEngineError {
  const error = new PhiEngineError("MISSING_TRUSTED_CONTEXT");
  Object.freeze(error.safeDetails);
  Object.freeze(error);
  return error;
}

/** Fixed single-code-unit literals the guard compares against (OR-14(h) allow-list B). */
const NUL_UNIT = "\u0000";
const HIGH_SURROGATE_FIRST = "\uD800";
const HIGH_SURROGATE_LAST = "\uDBFF";
const LOW_SURROGATE_FIRST = "\uDC00";
const LOW_SURROGATE_LAST = "\uDFFF";

/**
 * GLY-373 §3.2.2 / OR-GLY373-14(h) allow-list item C — THE single pinned validation helper.
 *
 * Rejects a trusted-context routing id that is NUL-bearing or ill-formed UTF-16. Applied at ALL
 * THREE context-id entry points (`#ingestContext`, the atomic `reverse()` handle, the
 * `createReverseStream` handle), always on an ALREADY-SNAPSHOTTED local and always BEFORE any key
 * derivation, namespace derivation, readiness gate, or store call.
 *
 * IMPLEMENTATION IS CONSTRAINED BY (h) ALLOW-LIST B: own-property indexed reads (`value[i]`), the
 * own `length`, `typeof`, and relational/equality comparisons against fixed single-code-unit
 * literals. NOTHING ELSE TOUCHES THE VALUE. Specifically NOT `includes`, `indexOf`, `isWellFormed`,
 * `charCodeAt`, `codePointAt`, or `RegExp.prototype.test` — MUT-33 kills each of those, and the
 * reason is executed, not stylistic:
 *   - a regex test leaves the ENTIRE subject string reachable in the legacy global statics
 *     `RegExp.input` / `RegExp.$_` — a process-global slot no oracle on the thrown error can see;
 *   - every `String.prototype` method is POISONABLE, and the value is caller-controlled: an
 *     executed probe returned `LEAKED_BY_POISONED_PROTOTYPE=includes,indexOf,isWellFormed,
 *     charCodeAt,codePointAt,RegExp.test`.
 * On a string, index and `length` resolve as OWN properties of the String exotic object, so they
 * never route through `String.prototype` and cannot be diverted — the same poison-resistant idiom
 * `frozenRoleSet` (`tokens/grammar.ts:19-36`) already uses, for the same reason.
 *
 * This helper closes over nothing, stores nothing, and returns nothing derived from `value`
 * (MUT-32). `fieldName` is the validated field NAME — a fixed literal at every call site — and is
 * deliberately never interpolated into the error; it exists so the pinned signature can carry a
 * name without ever carrying a value.
 */
export function assertTrustedContextIdShape(
  fieldName: string,
  value: string,
): void {
  const length = value.length;
  for (let i = 0; i < length; i += 1) {
    const unit = value[i] as string;
    // Check 1 — NUL-free. Defence in depth for the reversal-key NUL join (§3.2.2), which the
    // namespace preimage's length prefixing already immunises the LABEL against (MUT-19).
    if (unit === NUL_UNIT) {
      throw missingTrustedContextError();
    }
    // Check 2 — well-formed UTF-16. A high surrogate must be followed by a low surrogate; any
    // unpaired surrogate rejects. Load-bearing for the §3.2.1 injectivity claim (MUT-22/MUT-34).
    if (unit >= HIGH_SURROGATE_FIRST && unit <= HIGH_SURROGATE_LAST) {
      const next = i + 1 < length ? (value[i + 1] as string) : "";
      if (!(next >= LOW_SURROGATE_FIRST && next <= LOW_SURROGATE_LAST)) {
        throw missingTrustedContextError();
      }
      i += 1;
      continue;
    }
    if (unit >= LOW_SURROGATE_FIRST && unit <= LOW_SURROGATE_LAST) {
      throw missingTrustedContextError();
    }
  }
}
