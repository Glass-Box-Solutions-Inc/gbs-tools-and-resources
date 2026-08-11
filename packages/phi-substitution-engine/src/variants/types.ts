/**
 * Phase-1 variant expander types (invariant L10).
 *
 * These expanders operate ONLY on trusted, schema-tagged case-truth display
 * values. For a single tagged value they emit a bounded, deterministic,
 * allow-listed set of surface forms. They never invent a nickname, a fuzzy
 * name, an ambiguous date interpretation, a partial email, a bare
 * domain/extension, or any lossy identifier. The same input always yields the
 * same output. Anything outside the allow-list is rejected with a fixed,
 * value-free code rather than guessed.
 */

/** Fixed rejection codes. They carry no input text, matched text, or excerpts. */
export type VariantRejectionCode =
  | "AMBIGUOUS_LOCALE"
  | "LOSSY_FORM"
  | "UNAPPROVED_ALIAS"
  | "UNSUPPORTED_FORMAT";

/** Deterministic result of expanding one tagged value into approved forms. */
export interface VariantExpansion {
  /** Ordered, de-duplicated allow-listed surface forms. Empty on rejection. */
  readonly candidates: readonly string[];
  /** Fixed rejection code, or null on success. */
  readonly errorCode: VariantRejectionCode | null;
}
