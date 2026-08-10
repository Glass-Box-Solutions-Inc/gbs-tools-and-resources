import type { OperationId } from "../core/brands";

/**
 * Fixed, safe failure codes for the audit module. These are the only strings that ever
 * leave the audit boundary as an error identity. They never carry input text, matched
 * values, tokens, offsets, excerpts, or encryption material (CONTRACT §7).
 */
export type AuditFailureCode =
  | "AUDIT_SCHEMA_REJECTED"
  | "AUDIT_REQUIRED_FIELD_MISSING"
  | "AUDIT_DURABILITY_UNAVAILABLE"
  | "AUDIT_SPOOL_FLUSH_FAILED";

/**
 * The audit module's error type. It carries only the operation id and fixed safe metadata,
 * exactly as CONTRACT §7 requires: no text, values, variants, excerpts, offsets, or maps.
 */
export class PhiAuditError extends Error {
  public override readonly name = "PhiAuditError";
  public readonly code: AuditFailureCode;
  public readonly operationId: OperationId | null;
  public readonly safeDetails: Readonly<Record<string, string | number | boolean | null>>;

  public constructor(
    code: AuditFailureCode,
    operationId: OperationId | null,
    safeDetails: Readonly<Record<string, string | number | boolean | null>> = {},
  ) {
    super(code);
    this.code = code;
    this.operationId = operationId;
    this.safeDetails = safeDetails;
    Object.setPrototypeOf(this, PhiAuditError.prototype);
  }
}

/** Narrow an unknown thrown value to a PhiAuditError carrying a specific code. */
export function isAuditError(value: unknown, code?: AuditFailureCode): value is PhiAuditError {
  if (!(value instanceof PhiAuditError)) {
    return false;
  }
  return code === undefined || value.code === code;
}
