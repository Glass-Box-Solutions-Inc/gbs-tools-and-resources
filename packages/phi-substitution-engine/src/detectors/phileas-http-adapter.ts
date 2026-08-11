import type {
  BodyLoggingDisabledHttpClient,
  PhileasWireResponse,
} from "./phileas-service-adapter";
import type {
  DetectorArtifactDescriptor,
  DetectorInput,
  DetectorRedactionRequest,
  DetectorRedactionResult,
  DetectorRedactorPort,
  RawDetectedSpan,
} from "./ports";
import { applyReplacementPlan } from "./redaction";

/**
 * Metadata-only observability event. There is intentionally NO `body`, `headers`, or `text`
 * field, so it is type-impossible to log a request body (CONTRACT-phase1 §3.2.4, N2).
 */
export interface DetectorRequestMeta {
  readonly path: string;
  readonly kind: "DETECT" | "APPLY_REPLACEMENTS";
  readonly requestBytes: number;
}

function utf8ByteLength(text: string): number {
  return new TextEncoder().encode(text).length;
}

function sameIds(a: readonly string[], b: readonly string[]): boolean {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i += 1) {
    if (a[i] !== b[i]) return false;
  }
  return true;
}

/**
 * Vendor port implementation over an injected, body-logging-disabled HTTP client
 * (CONTRACT-phase1 §3.3). Core never imports Phileas/ONNX/Azure/HTTP classes directly — it depends
 * only on `DetectorRedactorPort`. The transport is injected, so this class performs no network I/O
 * of its own and is exercised with a fake wire in tests.
 */
export class PhileasHttpAdapter implements DetectorRedactorPort {
  readonly descriptor: DetectorArtifactDescriptor;
  private readonly http: BodyLoggingDisabledHttpClient;
  private readonly observe: (meta: DetectorRequestMeta) => void;

  constructor(
    config: Readonly<{ descriptor: DetectorArtifactDescriptor }>,
    http: BodyLoggingDisabledHttpClient,
    observe: (meta: DetectorRequestMeta) => void = () => {},
  ) {
    this.descriptor = config.descriptor;
    this.http = http;
    this.observe = observe;
  }

  async detect(input: DetectorInput, signal: AbortSignal): Promise<readonly RawDetectedSpan[]> {
    const body = {
      kind: "DETECT" as const,
      operationId: String(input.operationId),
      attemptId: String(input.attemptId),
      locale: input.locale,
      classes: input.classes.map((identifierClass) => String(identifierClass)),
      preparedPolicyId: input.preparedPolicy ? input.preparedPolicy.id : null,
      text: input.text,
    };
    // Metadata only — the request text is counted but never handed to the observer.
    this.observe({ path: "/internal/v1/detect", kind: "DETECT", requestBytes: utf8ByteLength(input.text) });

    const raw = await this.http.postJson("/internal/v1/detect", body, signal);
    const response = raw as PhileasWireResponse;
    if (response.kind !== "DETECTED") {
      throw new Error("DETECTOR_PROTOCOL_ERROR");
    }
    // Pin the artifact identity the response claims to the one this adapter was configured for.
    if (
      response.descriptor.name !== this.descriptor.name ||
      response.descriptor.engineVersion !== this.descriptor.engineVersion ||
      response.descriptor.modelVersion !== this.descriptor.modelVersion
    ) {
      throw new Error("DETECTOR_ARTIFACT_MISMATCH");
    }
    return response.spans;
  }

  async redact(
    input: DetectorRedactionRequest,
    signal: AbortSignal,
  ): Promise<DetectorRedactionResult> {
    // The protected reversal boundary owns substitution. Compute the authoritative tokenized text
    // in TS from the explicit plan; the sidecar echo is validated against it, never trusted to
    // invent replacements.
    const plan = applyReplacementPlan(input.text, input.instructions);
    if (!plan.ok) {
      throw new Error("INVALID_DETECTOR_OFFSET");
    }

    // §7/N2: build the wire replacements by OWN index/length, NEVER `instructions.map` — an OWN `.map`
    // override could return [] so the sidecar echoes the ORIGINAL text. The authoritative `plan` above
    // is computed the same intrinsic way, so any divergence still fails closed at the echo check below.
    const wireReplacements: { spanId: string; startUtf16: number; endUtf16: number; token: string }[] = [];
    for (let i = 0; i < (input.instructions as { length: number }).length; i += 1) {
      const instruction = input.instructions[i]!;
      wireReplacements[wireReplacements.length] = {
        spanId: instruction.detectedSpanId,
        startUtf16: instruction.startUtf16 as number,
        endUtf16: instruction.endUtf16 as number,
        token: instruction.replacement as string,
      };
    }
    const body = {
      kind: "APPLY_REPLACEMENTS" as const,
      operationId: String(input.operationId),
      attemptId: String(input.attemptId),
      preparedPolicyId: input.preparedPolicy ? input.preparedPolicy.id : null,
      text: input.text,
      replacements: wireReplacements,
    };
    this.observe({
      path: "/internal/v1/apply-replacements",
      kind: "APPLY_REPLACEMENTS",
      requestBytes: utf8ByteLength(input.text),
    });

    const raw = await this.http.postJson("/internal/v1/apply-replacements", body, signal);
    const response = raw as PhileasWireResponse;
    if (response.kind !== "REDACTED") {
      throw new Error("DETECTOR_PROTOCOL_ERROR");
    }
    if (response.text !== (plan.text as string) || !sameIds(response.appliedSpanIds, plan.appliedSpanIds)) {
      throw new Error("DETECTOR_REPLACEMENT_MISMATCH");
    }
    return { text: plan.text, appliedSpanIds: plan.appliedSpanIds, serviceVersion: response.serviceVersion };
  }

  async health(): Promise<"ready" | "degraded" | "unavailable"> {
    return "ready";
  }
}
