/**
 * Fixed, value-free failure surface for the matter-dictionary compiler and its
 * serving/orchestration path (CONTRACT-phase1 §7).
 *
 * A `DictionaryError` carries only a declared `PhiEngineFailureCode` and safe
 * metadata (versions, counts, booleans). It NEVER carries input text, matched
 * text, tokens paired with values, variants, offsets, or policy terms, so a
 * fail-closed result can be surfaced and traced without leaking case truth.
 */
import type { PhiEngineFailureCode } from "../core/contracts";

export type DictionaryFailureCode = PhiEngineFailureCode;

export const DICTIONARY_NOT_READY: DictionaryFailureCode =
  "DICTIONARY_NOT_READY";
export const DICTIONARY_UNAVAILABLE: DictionaryFailureCode =
  "DICTIONARY_UNAVAILABLE";
export const MISSING_TRUSTED_CONTEXT: DictionaryFailureCode =
  "MISSING_TRUSTED_CONTEXT";
export const MISSING_TRUSTED_POLICY: DictionaryFailureCode =
  "MISSING_TRUSTED_POLICY";
export const AMBIGUOUS_KNOWN_IDENTIFIER: DictionaryFailureCode =
  "AMBIGUOUS_KNOWN_IDENTIFIER";

/** Safe metadata only; never text/values/variants/offsets/policy terms. */
export type SafeDetails = Readonly<
  Record<string, string | number | boolean | null>
>;

export class DictionaryError extends Error {
  public override readonly name = "PhiEngineError";
  public readonly code: DictionaryFailureCode;
  public readonly safeDetails: SafeDetails;

  public constructor(
    code: DictionaryFailureCode,
    safeDetails: SafeDetails = {},
  ) {
    super(code);
    this.code = code;
    this.safeDetails = safeDetails;
  }
}

/**
 * Narrow an unknown thrown value to a DictionaryError — SAFELY. The `instanceof` test is guarded
 * because a hostile Proxy `getPrototypeOf` / `Symbol.hasInstance` trap could throw a PHI canary
 * during the prototype-chain walk; an unclassifiable value is simply not one of our errors (§7/N2).
 */
export function isDictionaryError(value: unknown): value is DictionaryError {
  try {
    return value instanceof DictionaryError;
  } catch {
    return false;
  }
}
