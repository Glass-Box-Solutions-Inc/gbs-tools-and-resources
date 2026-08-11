import type { VariantExpansion, VariantRejectionCode } from "./types";
import { alphanumericLength, dedupeInOrder } from "./support";

export type StructuredSeparator = "-" | " " | "/" | ".";

export interface StructuredIdPolicy {
  /** Required leading alpha prefix, or null when the class has no prefix. */
  readonly requiredAlphaPrefix: string | null;
  /** Separators explicitly permitted between prefix and core. */
  readonly permittedSeparators: readonly StructuredSeparator[];
  /** Whether a separatorless (compact) form is allowed. */
  readonly allowCompactForm: boolean;
  /** Any candidate below this alphanumeric length is a lossy form and dropped. */
  readonly minimumAlphanumericLength: number;
}

export interface StructuredIdVariantRequest {
  readonly canonical: string;
  readonly policy: StructuredIdPolicy;
}

/**
 * Expands a structured identifier into ONLY the forms the class policy permits:
 * one prefix-preserving form per permitted separator, plus the compact form
 * when explicitly allowed. The required alpha prefix must be present and exact —
 * a form that drops the prefix, or that falls below the policy's minimum
 * alphanumeric length, is a lossy identifier and is never emitted. Arbitrary
 * punctuation stripping is forbidden.
 */
export function expandStructuredIdVariants(
  request: StructuredIdVariantRequest,
): VariantExpansion {
  const { canonical, policy } = request;
  const trimmed = canonical.trim();

  // A structured identifier is an alpha prefix, exactly one separator, and an
  // alphanumeric core. Anything else is an unsupported shape.
  const parsed = /^([A-Za-z]+)([-/. ])([A-Za-z0-9]+)$/.exec(trimmed);
  if (parsed === null) {
    return { candidates: [], errorCode: "UNSUPPORTED_FORMAT" };
  }
  const prefix = parsed[1];
  const core = parsed[3];
  if (prefix === undefined || core === undefined) {
    return { candidates: [], errorCode: "UNSUPPORTED_FORMAT" };
  }

  // The required alpha prefix must be present and exact. Dropping or altering it
  // would produce a lossy, ambiguous identifier.
  if (policy.requiredAlphaPrefix !== null && prefix !== policy.requiredAlphaPrefix) {
    const code: VariantRejectionCode = "LOSSY_FORM";
    return { candidates: [], errorCode: code };
  }

  const generated: string[] = [];

  // One prefix-preserving form per explicitly permitted separator.
  for (const separator of policy.permittedSeparators) {
    generated.push(`${prefix}${separator}${core}`);
  }

  // The compact (separatorless) form is emitted ONLY when policy allows it.
  if (policy.allowCompactForm) {
    generated.push(`${prefix}${core}`);
  }

  // Never keep a form that falls below the policy minimum: a bare core or any
  // truncated identifier is exactly the lossy form L10 forbids.
  const kept = dedupeInOrder(generated).filter(
    (candidate) => alphanumericLength(candidate) >= policy.minimumAlphanumericLength,
  );

  return { candidates: kept, errorCode: null };
}
