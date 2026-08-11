/**
 * Phase-1 collision, boundary, citation, and offset policy (invariants L3, L12).
 *
 * Public surface for the deterministic C1–C8 resolver, its rules, the
 * NFKC+offset normalizer, structured-identifier detectors, and the engine that
 * turns trusted known values + original text into a tokenized output and its
 * reversal, failing closed on ambiguous known identifiers.
 */
export type {
  BoundaryRule,
  CitationRule,
  CollisionResolver,
  DetectorCollisionSpan,
  DistinctivenessRule,
  OriginalOffsetMap,
  ResolvedCollisionSet,
  UnicodeNormalizer,
  ValidatedCitationSpan,
} from "./ports";

export { Phase1UnicodeNormalizer, canonicalize, fold } from "./normalizer";
export {
  Phase1BoundaryRule,
  Phase1CitationRule,
  Phase1DistinctivenessRule,
} from "./rules";
export { detectStructuredIdentifiers, inferIdentifierClass } from "./detectors";
export { Phase1CollisionResolver } from "./resolver";
export {
  runCollision,
  type CollisionInput,
  type CollisionResult,
  type KnownValue,
} from "./engine";
