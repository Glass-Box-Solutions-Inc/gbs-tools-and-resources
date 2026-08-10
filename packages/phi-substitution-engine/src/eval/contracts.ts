import type { EngineVersion } from "../core/brands";
import type { IdentifierClass } from "../core/contracts";

export interface PerClassEvaluation {
  readonly identifierClass: IdentifierClass;
  readonly recallPoint: number;
  readonly recallWilsonLower95: number;
  readonly precisionPoint: number;
  readonly precisionWilsonLower95: number;
  readonly sampleCount: number;
}

export interface DetectorArtifactIdentity {
  readonly detectorName: string;
  readonly serviceVersion: string;
  readonly engineVersion: string;
  readonly modelVersion: string;
  readonly recognizerVersion: string;
  readonly configurationDigest: string;
  readonly containerImageDigest: string;
}

export interface EvaluationManifest {
  readonly engineVersion: EngineVersion;
  readonly corpusDigest: string;
  readonly artifact: DetectorArtifactIdentity;
  readonly byClass: readonly PerClassEvaluation[];
  readonly latencyP95Ms: number;
  readonly latencyP99Ms: number;
  readonly maximumInteractiveBytes: 32768;
}

export interface ClaimsEligibility {
  eligibleCopy(manifest: EvaluationManifest): readonly string[];
}
