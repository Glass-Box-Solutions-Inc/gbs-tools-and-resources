import type {
  DetectorArtifactDescriptor,
  DetectedSpan,
  DetectorDeadlineRunner,
  DetectorInput,
  DetectorRedactorPort,
  DetectorSpanNormalizer,
  RawDetectedSpan,
} from "./ports";

/** Fail-closed marker for an exhausted detector belt (maps to `DETECTOR_UNAVAILABLE`). */
export class DetectorDeadlineExceededError extends Error {
  readonly code = "DETECTOR_UNAVAILABLE" as const;
  constructor() {
    super("DETECTOR_UNAVAILABLE");
    this.name = "DetectorDeadlineExceededError";
  }
}

type PortOutcome = Readonly<{
  descriptor: DetectorArtifactDescriptor;
  spans: readonly DetectedSpan[];
}>;

/**
 * Deadline/failover runner (CONTRACT-phase1 §4.1.7, §5 L9): primary and fallback share ONE
 * deadline. A single AbortController drives both attempts, so a slow primary eats into the
 * fallback's budget rather than resetting it. If neither port yields usable, normalized spans
 * before the shared deadline, the belt fails closed — it never proceeds to a provider call.
 */
export class SharedDeadlineDetectorRunner implements DetectorDeadlineRunner {
  async detectWithin(params: Readonly<{
    primary: DetectorRedactorPort;
    fallback: DetectorRedactorPort | null;
    request: DetectorInput;
    deadlineMs: number;
    normalizer: DetectorSpanNormalizer;
  }>): Promise<PortOutcome> {
    const { primary, fallback, request, deadlineMs, normalizer } = params;

    const controller = new AbortController();
    const timer: ReturnType<typeof setTimeout> = setTimeout(() => controller.abort(), deadlineMs);
    try {
      const primaryOutcome = await this.tryPort(primary, request, controller.signal, normalizer);
      if (primaryOutcome) {
        return primaryOutcome;
      }
      // ONE shared deadline: the fallback runs under the SAME signal/budget, never a fresh timer.
      if (fallback && !controller.signal.aborted) {
        const fallbackOutcome = await this.tryPort(fallback, request, controller.signal, normalizer);
        if (fallbackOutcome) {
          return fallbackOutcome;
        }
      }
      throw new DetectorDeadlineExceededError();
    } finally {
      clearTimeout(timer);
    }
  }

  private async tryPort(
    port: DetectorRedactorPort,
    request: DetectorInput,
    signal: AbortSignal,
    normalizer: DetectorSpanNormalizer,
  ): Promise<PortOutcome | null> {
    if (signal.aborted) {
      return null;
    }
    let health: "ready" | "degraded" | "unavailable";
    try {
      health = await port.health();
    } catch {
      return null;
    }
    if (health === "unavailable") {
      return null;
    }

    let raw: readonly RawDetectedSpan[];
    try {
      raw = await port.detect(request, signal);
    } catch {
      return null;
    }
    if (signal.aborted) {
      return null;
    }

    const normalized = normalizer.normalize(request.text, port.descriptor.engineVersion, raw);
    // §7/N2: the normalizer is an injected adapter, so its result is UNTRUSTED. Read `.ok` (and
    // `.spans`) behind a getter-throw guard — a hostile Proxy/getter trap must not throw a PHI canary
    // out of the detector belt (detectWithin has no catch, only a finally). Fail closed on any read
    // failure or non-ok result.
    let spans: readonly DetectedSpan[];
    try {
      if (normalized.ok !== true) {
        return null;
      }
      spans = normalized.spans;
    } catch {
      return null;
    }
    return { descriptor: port.descriptor, spans };
  }
}
