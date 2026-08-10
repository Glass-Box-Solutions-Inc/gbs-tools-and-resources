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

/** Maps a thrown value to its fixed failure code, defaulting to a safe generic code. */
export function toFailureCode(value: unknown, fallback: PhiEngineFailureCode): PhiEngineFailureCode {
  if (isPhiEngineError(value)) {
    return value.code;
  }
  if (
    value !== null &&
    typeof value === "object" &&
    "code" in value &&
    typeof (value as { code?: unknown }).code === "string"
  ) {
    return (value as { code: PhiEngineFailureCode }).code;
  }
  return fallback;
}
