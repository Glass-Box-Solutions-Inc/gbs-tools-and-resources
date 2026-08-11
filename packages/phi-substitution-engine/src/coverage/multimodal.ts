/**
 * Multimodal carve-out classification (CONTRACT §2, §5 N7).
 *
 * Image egress to a vision model is a reviewed BAA / minimum-necessary
 * carve-out, never claimed text coverage: deterministic text substitution
 * cannot cover an image surface because the identifiers remain pixels. A
 * surface that claims text substitution over an image is therefore an invalid
 * coverage claim and must not build.
 */
export type CarveOutMitigation = "BAA_PROVIDER" | "MINIMUM_NECESSARY" | "SEPARATE_TICKET";

export interface MultimodalCarveOutInput {
  readonly surfaceKind: string;
  readonly substitutionClaimed: boolean;
  readonly mitigation: readonly string[];
}

export interface MultimodalCarveOutResult {
  readonly buildPassed: boolean;
  readonly engineCovered: boolean;
  readonly reviewedCarveout: boolean;
}

const IMAGE_SURFACE_PATTERN = /image|vision|multimodal|ocr|pixel/i;

export function classifyMultimodalCarveOut(
  input: MultimodalCarveOutInput,
): MultimodalCarveOutResult {
  const isImageSurface = IMAGE_SURFACE_PATTERN.test(input.surfaceKind);
  const hasBaa = input.mitigation.includes("BAA_PROVIDER");
  const hasMinimumNecessary = input.mitigation.includes("MINIMUM_NECESSARY");

  // Names remain pixels: text substitution can only cover a text surface.
  const engineCovered = !isImageSurface && input.substitutionClaimed;
  const reviewedCarveout =
    isImageSurface && !input.substitutionClaimed && hasBaa && hasMinimumNecessary;

  return {
    buildPassed: reviewedCarveout && !engineCovered,
    engineCovered,
    reviewedCarveout,
  };
}
