import type {
  DetectorArtifactDescriptor,
  DetectedSpan,
  DetectorDeadlineRunner,
  DetectorInput,
  DetectorRedactorPort,
  DetectorSpanNormalizer,
} from "./ports";

export type DetectorRequirement = "DISABLED_PHASE_1" | "REQUIRED";

/**
 * A fallback port is eligible only after it has independently passed the SAME per-class, offset,
 * BAA/residency, no-body-logging, and latency gates as the primary (CONTRACT-phase1 §3.3).
 */
export interface FallbackEligibility {
  readonly eligible: boolean;
  readonly residencyApproved: boolean;
  readonly baaApproved: boolean;
}

export type BeltResult =
  | Readonly<{ invoked: false }>
  | Readonly<{
      invoked: true;
      descriptor: DetectorArtifactDescriptor;
      spans: readonly DetectedSpan[];
    }>;

export interface DetectionBeltParams {
  readonly detectorRequirement: DetectorRequirement;
  readonly primary: DetectorRedactorPort;
  readonly fallback: DetectorRedactorPort | null;
  readonly fallbackEligibility: FallbackEligibility | null;
  readonly request: DetectorInput;
  readonly deadlineMs: number;
  readonly runner: DetectorDeadlineRunner;
  readonly normalizer: DetectorSpanNormalizer;
}

/** Fail-closed error for a required-but-unavailable detector belt. */
export class DetectorBeltUnavailableError extends Error {
  readonly code = "DETECTOR_UNAVAILABLE" as const;
  constructor() {
    super("DETECTOR_UNAVAILABLE");
    this.name = "DetectorBeltUnavailableError";
  }
}

function isFallbackEligible(eligibility: FallbackEligibility | null): boolean {
  return (
    eligibility !== null &&
    eligibility.eligible &&
    eligibility.residencyApproved &&
    eligibility.baaApproved
  );
}

/**
 * The core-side detection belt gate (CONTRACT-phase1 §3.3, §4.1.7).
 *
 * Under the phase-1 trusted policy (`DISABLED_PHASE_1`) the core MUST NOT call either adapter for
 * a customer claim — it returns without ever touching a port. When the belt is `REQUIRED`, it runs
 * the shared-deadline runner over the primary and an independently-eligible fallback, and fails
 * closed (`DETECTOR_UNAVAILABLE`) if neither yields usable spans in time.
 */
export async function runDetectionBelt(params: DetectionBeltParams): Promise<BeltResult> {
  if (params.detectorRequirement === "DISABLED_PHASE_1") {
    return { invoked: false };
  }

  const eligibleFallback = isFallbackEligible(params.fallbackEligibility) ? params.fallback : null;

  try {
    const outcome = await params.runner.detectWithin({
      primary: params.primary,
      fallback: eligibleFallback,
      request: params.request,
      deadlineMs: params.deadlineMs,
      normalizer: params.normalizer,
    });
    return { invoked: true, descriptor: outcome.descriptor, spans: outcome.spans };
  } catch {
    throw new DetectorBeltUnavailableError();
  }
}
