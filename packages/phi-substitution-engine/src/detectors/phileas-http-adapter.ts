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
  RedactionInstruction,
} from "./ports";
import { applyReplacementPlan } from "./redaction";
import { intrinsicCopy, safeRead, safeString } from "../core/boundary-snapshot";

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

  async detect(
    input: DetectorInput,
    signal: AbortSignal,
  ): Promise<readonly RawDetectedSpan[]> {
    // §7/N2: `classes` is boundary data — read it ONCE by own index/length (never `.map`, which an OWN
    // override could empty so the sidecar detects nothing and required PHI passes undetected). A
    // non-array carrier or a non-string class fails closed here rather than fail-OPEN detection.
    const rawClasses = intrinsicCopy<unknown>(input.classes);
    if (rawClasses === null) {
      throw new Error("DETECTOR_PROTOCOL_ERROR");
    }
    const classes: string[] = [];
    for (let i = 0; i < rawClasses.length; i += 1) {
      const identifierClass = rawClasses[i];
      if (typeof identifierClass !== "string") {
        throw new Error("DETECTOR_PROTOCOL_ERROR");
      }
      classes[classes.length] = identifierClass;
    }
    const body = {
      kind: "DETECT" as const,
      operationId: String(input.operationId),
      attemptId: String(input.attemptId),
      locale: input.locale,
      classes,
      preparedPolicyId: input.preparedPolicy ? input.preparedPolicy.id : null,
      text: input.text,
    };
    // Metadata only — the request text is counted but never handed to the observer.
    this.observe({
      path: "/internal/v1/detect",
      kind: "DETECT",
      requestBytes: utf8ByteLength(input.text),
    });

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
    // §7/N2: snapshot the boundary instructions ONCE, getter-throw-safe, into inert plain data, so the
    // authoritative `plan` AND the wire body read the SAME values — a mutating index/field getter (or
    // an OWN `.map`) cannot show a valid instruction to the plan and a throwing/PHI one to the wire.
    const rawInstr = intrinsicCopy<unknown>(input.instructions);
    if (rawInstr === null) {
      throw new Error("INVALID_DETECTOR_OFFSET");
    }
    const instr: {
      detectedSpanId: string;
      startUtf16: number;
      endUtf16: number;
      replacement: string;
    }[] = [];
    for (let i = 0; i < rawInstr.length; i += 1) {
      const r = rawInstr[i];
      const detectedSpanId = safeString(r, "detectedSpanId");
      const startUtf16 = safeRead(r, "startUtf16");
      const endUtf16 = safeRead(r, "endUtf16");
      const replacement = safeString(r, "replacement");
      if (
        detectedSpanId === undefined ||
        typeof startUtf16 !== "number" ||
        typeof endUtf16 !== "number" ||
        replacement === undefined
      ) {
        throw new Error("INVALID_DETECTOR_OFFSET");
      }
      instr[instr.length] = {
        detectedSpanId,
        startUtf16,
        endUtf16,
        replacement,
      };
    }
    const plan = applyReplacementPlan(
      input.text,
      instr as unknown as readonly RedactionInstruction[],
    );
    if (!plan.ok) {
      throw new Error("INVALID_DETECTOR_OFFSET");
    }
    const wireReplacements: {
      spanId: string;
      startUtf16: number;
      endUtf16: number;
      token: string;
    }[] = [];
    for (let i = 0; i < instr.length; i += 1) {
      const r = instr[i]!;
      wireReplacements[wireReplacements.length] = {
        spanId: r.detectedSpanId,
        startUtf16: r.startUtf16,
        endUtf16: r.endUtf16,
        token: r.replacement,
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

    const raw = await this.http.postJson(
      "/internal/v1/apply-replacements",
      body,
      signal,
    );
    const response = raw as PhileasWireResponse;
    if (response.kind !== "REDACTED") {
      throw new Error("DETECTOR_PROTOCOL_ERROR");
    }
    if (
      response.text !== (plan.text as string) ||
      !sameIds(response.appliedSpanIds, plan.appliedSpanIds)
    ) {
      throw new Error("DETECTOR_REPLACEMENT_MISMATCH");
    }
    return {
      text: plan.text,
      appliedSpanIds: plan.appliedSpanIds,
      serviceVersion: response.serviceVersion,
    };
  }

  async health(): Promise<"ready" | "degraded" | "unavailable"> {
    return "ready";
  }
}
