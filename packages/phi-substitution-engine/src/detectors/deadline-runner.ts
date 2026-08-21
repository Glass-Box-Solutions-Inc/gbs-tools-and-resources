import type {
  DetectorArtifactDescriptor,
  DetectedSpan,
  DetectorDeadlineRunner,
  DetectorInput,
  DetectorRedactorPort,
  DetectorSpanNormalizer,
  RawDetectedSpan,
} from "./ports";
import { safeRead, safeString, intrinsicCopy } from "../core/boundary-snapshot";

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
  async detectWithin(
    params: Readonly<{
      primary: DetectorRedactorPort;
      fallback: DetectorRedactorPort | null;
      request: DetectorInput;
      deadlineMs: number;
      normalizer: DetectorSpanNormalizer;
    }>,
  ): Promise<PortOutcome> {
    const { primary, fallback, request, deadlineMs, normalizer } = params;

    const controller = new AbortController();
    const timer: ReturnType<typeof setTimeout> = setTimeout(
      () => controller.abort(),
      deadlineMs,
    );
    try {
      const primaryOutcome = await this.tryPort(
        primary,
        request,
        controller.signal,
        normalizer,
      );
      if (primaryOutcome) {
        return primaryOutcome;
      }
      // ONE shared deadline: the fallback runs under the SAME signal/budget, never a fresh timer.
      if (fallback && !controller.signal.aborted) {
        const fallbackOutcome = await this.tryPort(
          fallback,
          request,
          controller.signal,
          normalizer,
        );
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

    // §7/N2: the normalizer is an injected adapter, so BOTH its invocation and its result reads are
    // UNTRUSTED. A `normalize()` that throws, or a `.ok`/`.spans` getter trap, must fail closed
    // (return null) — never throw a PHI canary out of the detector belt (detectWithin has no catch,
    // only a finally).
    let spans: readonly DetectedSpan[];
    let descriptor: DetectorArtifactDescriptor;
    try {
      // §7/N2: `port.descriptor` is an injected-port getter — read every FIELD ONCE here, inside the
      // guard, into an INERT snapshot. Returning the LIVE descriptor would let a field getter that is
      // valid now and THROWS on the caller's next read leak raw PHI at the (unguarded) return below;
      // `detectWithin` has no catch there, only a `finally`. A throwing/missing engineVersion fails
      // closed (return null).
      const d = port.descriptor;
      const engineVersion = safeString(d, "engineVersion");
      if (engineVersion === undefined) {
        return null;
      }
      descriptor = {
        name: (safeString(d, "name") ??
          "") as DetectorArtifactDescriptor["name"],
        serviceVersion: safeString(d, "serviceVersion") ?? "",
        engineVersion,
        modelVersion: safeString(d, "modelVersion") ?? "",
        recognizerVersion: safeString(d, "recognizerVersion") ?? "",
        configurationDigest: safeString(d, "configurationDigest") ?? "",
        residency: safeString(d, "residency") ?? "",
        localProcessing: safeRead(d, "localProcessing") === true,
      };
      const normalized = normalizer.normalize(request.text, engineVersion, raw);
      if (normalized.ok !== true) {
        return null;
      }
      // §7/N2: the normalizer's `spans` is an injected-adapter result — copy it by OWN index/length so
      // a NON-array carrier, an OWN poisoned iterator, or a throwing own-index getter fails closed here
      // rather than returning a live array whose getters could throw raw PHI at the caller's read.
      const copiedSpans = intrinsicCopy<DetectedSpan>(
        safeRead(normalized, "spans"),
      );
      if (copiedSpans === null) {
        return null;
      }
      spans = copiedSpans;
    } catch {
      return null;
    }
    return { descriptor, spans };
  }
}
