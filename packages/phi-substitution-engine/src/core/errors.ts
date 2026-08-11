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
  public readonly safeDetails: Readonly<Record<string, string | number | boolean | null>>;

  public constructor(
    code: PhiEngineFailureCode,
    operationId: OperationId = PLACEHOLDER_OPERATION_ID,
    safeDetails: Readonly<Record<string, string | number | boolean | null>> = {},
  ) {
    super(code);
    this.code = code;
    this.operationId = operationId;
    this.safeDetails = safeDetails;
  }
}

export function isPhiEngineError(value: unknown): value is PhiEngineError {
  return value instanceof PhiEngineError;
}

const PHI_ENGINE_FAILURE_CODES: ReadonlySet<string> = new Set<PhiEngineFailureCode>([
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
]);

/** True only for a recognized, fixed, safe PhiEngineFailureCode (never a raw upstream code). */
export function isPhiEngineFailureCode(value: unknown): value is PhiEngineFailureCode {
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
export function toFailureCode(value: unknown, fallback: PhiEngineFailureCode): PhiEngineFailureCode {
  const code = safeCodeString(value);
  return code !== undefined && isPhiEngineFailureCode(code) ? code : fallback;
}
