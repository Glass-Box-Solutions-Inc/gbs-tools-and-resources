/**
 * Phase-1 deterministic, allow-listed variant expanders (invariant L10).
 *
 * Each expander turns one trusted, schema-tagged case-truth value into the
 * bounded set of surface forms an approved policy permits, and rejects anything
 * ambiguous or lossy with a fixed, value-free code. No nickname, fuzzy name,
 * ambiguous date, partial email, bare extension, or truncated identifier is
 * ever invented, and the same input always produces the same output.
 */
export type { VariantExpansion, VariantRejectionCode } from "./types";

export type { PersonNameVariantRequest } from "./person-name-expander";
export { expandPersonNameVariants } from "./person-name-expander";

export type { DateVariantRequest } from "./date-expander";
export { expandDateVariants } from "./date-expander";

export type {
  StructuredIdPolicy,
  StructuredIdVariantRequest,
  StructuredSeparator,
} from "./structured-id-expander";
export { expandStructuredIdVariants } from "./structured-id-expander";

export { replaceAllowListedVariants } from "./substitution";
