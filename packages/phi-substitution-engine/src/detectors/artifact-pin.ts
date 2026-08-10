/**
 * Detector artifact pinning (CONTRACT-phase1 §5 L7): the deployed detector artifact must be
 * byte-identical to the one the per-class eligibility was evaluated against. Any drift in engine,
 * model, recognizer set, or configuration digest fails the build so an unevaluated artifact can
 * never silently serve traffic.
 */

export interface DetectorArtifactIdentity {
  readonly engine: string;
  readonly model: string;
  readonly recognizers: string;
  readonly configDigest: string;
}

export interface ArtifactPinResult {
  readonly buildPassed: boolean;
  readonly diagnostics: readonly string[];
}

export function verifyDetectorArtifact(
  evaluated: DetectorArtifactIdentity,
  deployed: DetectorArtifactIdentity,
): ArtifactPinResult {
  const mismatches: string[] = [];
  if (evaluated.engine !== deployed.engine) mismatches.push("engine");
  if (evaluated.model !== deployed.model) mismatches.push("model");
  if (evaluated.recognizers !== deployed.recognizers) mismatches.push("recognizers");
  if (evaluated.configDigest !== deployed.configDigest) mismatches.push("configDigest");

  if (mismatches.length === 0) {
    return { buildPassed: true, diagnostics: [] };
  }
  return {
    buildPassed: false,
    diagnostics: ["DETECTOR_ARTIFACT_MISMATCH", ...mismatches.map((field) => `mismatch:${field}`)],
  };
}
