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
  | "AUDIT_SPOOL_FLUSH_FAILED"
  /** The attempt already has a durable PREPARED/terminal record; re-egress is refused (N3). */
  | "AUDIT_ATTEMPT_ALREADY_FINALIZED";

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

const AUDIT_FAILURE_CODES: ReadonlySet<string> = new Set<AuditFailureCode>([
  "AUDIT_SCHEMA_REJECTED",
  "AUDIT_REQUIRED_FIELD_MISSING",
  "AUDIT_DURABILITY_UNAVAILABLE",
  "AUDIT_SPOOL_FLUSH_FAILED",
  "AUDIT_ATTEMPT_ALREADY_FINALIZED",
]);

/**
 * True only for a RECOGNIZED, fixed, safe `AuditFailureCode`. A `PhiAuditError` whose `code` is not
 * in this allow-list (e.g. an upstream store threw `new PhiAuditError(rawValue as any)`) is NOT
 * safe to surface — its code/message could carry PHI — so callers must re-wrap it (§7/N2). Being a
 * `PhiAuditError` instance is not, by itself, proof of a safe code.
 */
export function isAuditFailureCode(value: unknown): value is AuditFailureCode {
  return typeof value === "string" && AUDIT_FAILURE_CODES.has(value);
}
