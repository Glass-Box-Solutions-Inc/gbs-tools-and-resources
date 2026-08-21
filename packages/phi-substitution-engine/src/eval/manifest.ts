/**
 * Evidence-bound claims/artifact manifest (invariants N6 + L7).
 *
 * The release manifest binds every eligible claim to concrete evidence: a pinned
 * detector artifact identity (exact model/recognizer/config), per-class recall
 * gates, and the interactive latency envelope. `EvidenceBoundClaims` implements
 * the frozen `ClaimsEligibility` port over that manifest, so the copy a release
 * may publish is a pure function of the evidence it carries — nothing more.
 */
import type { EngineVersion } from "../core/brands";
import type { IdentifierClass } from "../core/contracts";
import type {
  ClaimsEligibility,
  DetectorArtifactIdentity,
  EvaluationManifest,
  PerClassEvaluation,
} from "./contracts";
import { gateClasses, type ClassRecallEvidence } from "./eligibility";
import { PHASE1_TEXT_CLAIM, PHASE2_FREETEXT_CLAIM } from "./claims";
import { envelopeWithinBudget, MAXIMUM_INTERACTIVE_BYTES } from "./latency";
import { wilsonLowerBound } from "./wilson";

/** L7: eligibility is pinned to the EXACT model/recognizer/config identity. */
export function isArtifactPinned(artifact: DetectorArtifactIdentity): boolean {
  const identityFields: readonly string[] = [
    artifact.detectorName,
    artifact.serviceVersion,
    artifact.engineVersion,
    artifact.modelVersion,
    artifact.recognizerVersion,
    artifact.configurationDigest,
    artifact.containerImageDigest,
  ];
  return identityFields.every(
    (value) => typeof value === "string" && value.length > 0,
  );
}

/** Interactive latency budget derived from L9. */
const INTERACTIVE_BUDGET = {
  p95ExclusiveMs: 100,
  p99InclusiveMs: 100,
} as const;

/**
 * The release claims registry over a full evaluation manifest. The phase-1 copy
 * always holds under trusted policy; the phase-2 free-text copy is added only
 * when the artifact is pinned, every class clears its per-class gate, and the
 * interactive latency envelope is within budget.
 */
export class EvidenceBoundClaims implements ClaimsEligibility {
  eligibleCopy(manifest: EvaluationManifest): readonly string[] {
    const copies: string[] = [PHASE1_TEXT_CLAIM];

    const classes: ClassRecallEvidence[] = manifest.byClass.map((entry) => ({
      identifierClass: entry.identifierClass,
      recallWilsonLower95: entry.recallWilsonLower95,
    }));
    const gate = gateClasses(classes);
    const latencyOk = envelopeWithinBudget(
      {
        p95Ms: manifest.latencyP95Ms,
        p99Ms: manifest.latencyP99Ms,
        sampleCount: 0,
      },
      INTERACTIVE_BUDGET,
    );

    if (
      manifest.byClass.length > 0 &&
      isArtifactPinned(manifest.artifact) &&
      gate.eligible &&
      latencyOk
    ) {
      copies.push(PHASE2_FREETEXT_CLAIM);
    }
    return copies;
  }
}

/** Build a `PerClassEvaluation` from raw counts, computing Wilson lower bounds. */
export function perClassFromCounts(input: {
  readonly identifierClass: IdentifierClass;
  readonly recallSuccesses: number;
  readonly recallTrials: number;
  readonly precisionSuccesses: number;
  readonly precisionTrials: number;
}): PerClassEvaluation {
  const recallPoint =
    input.recallTrials > 0 ? input.recallSuccesses / input.recallTrials : 0;
  const precisionPoint =
    input.precisionTrials > 0
      ? input.precisionSuccesses / input.precisionTrials
      : 0;
  return {
    identifierClass: input.identifierClass,
    recallPoint,
    recallWilsonLower95: wilsonLowerBound(
      input.recallSuccesses,
      input.recallTrials,
    ),
    precisionPoint,
    precisionWilsonLower95: wilsonLowerBound(
      input.precisionSuccesses,
      input.precisionTrials,
    ),
    sampleCount: input.recallTrials,
  };
}

export interface EvaluationManifestInput {
  readonly engineVersion: string;
  readonly corpusDigest: string;
  readonly artifact: DetectorArtifactIdentity;
  readonly byClass: readonly PerClassEvaluation[];
  readonly latencyP95Ms: number;
  readonly latencyP99Ms: number;
}

/** Assemble a frozen evaluation manifest, pinning the interactive ceiling. */
export function buildEvaluationManifest(
  input: EvaluationManifestInput,
): EvaluationManifest {
  return {
    engineVersion: input.engineVersion as EngineVersion,
    corpusDigest: input.corpusDigest,
    artifact: input.artifact,
    byClass: input.byClass,
    latencyP95Ms: input.latencyP95Ms,
    latencyP99Ms: input.latencyP99Ms,
    maximumInteractiveBytes: MAXIMUM_INTERACTIVE_BYTES,
  };
}
