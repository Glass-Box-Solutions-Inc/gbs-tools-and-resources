/**
 * Evaluation-and-claims module (invariants N6, L7; latency gate L9).
 *
 * Genuinely enforces the two release invariants this module owns:
 *  - N6: claims are limited to passing evidence; the only phase-1 text claim is
 *    the exact §2 sentence, images are an explicit carve-out, and an ineligible
 *    class blocks a free-text claim.
 *  - L7: detector eligibility is per class, pinned to the exact artifact
 *    identity, and a macro-average can never hide a weak class.
 */
export { wilsonLowerBound, Z_95 } from "./wilson";

export {
  gateClasses,
  MINIMUM_CLASS_RECALL_LOWER,
  type AggregateEligibility,
  type ClassGateResult,
  type ClassRecallEvidence,
} from "./eligibility";

export {
  eligibleClaims,
  resolveRequestedClaim,
  PHASE1_TEXT_CLAIM,
  PHASE2_FREETEXT_CLAIM,
  type ClaimDecision,
  type ClaimEvidence,
} from "./claims";

export {
  measureBeltEnvelope,
  modelBeltLatencyMs,
  nearestRankPercentile,
  envelopeWithinBudget,
  MAXIMUM_INTERACTIVE_BYTES,
  type LatencyBudget,
  type LatencyEnvelope,
} from "./latency";

export {
  EvidenceBoundClaims,
  buildEvaluationManifest,
  isArtifactPinned,
  perClassFromCounts,
  type EvaluationManifestInput,
} from "./manifest";
