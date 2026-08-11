import type { TokenizedText } from "../core/brands";
import type {
  DetectorArtifactDescriptor,
  DetectorInput,
  DetectorRedactionRequest,
  DetectorRedactionResult,
  DetectorRedactorPort,
  PreparedDetectorPolicyCompiler,
  PreparedPolicyRef,
  RawDetectedSpan,
} from "./ports";

export interface PhileasServiceAdapterConfig {
  /** Loopback in the selected ACA multi-container deployment. */
  readonly baseUrl: string;
  readonly maximumRequestBytes: number;
  readonly requestTimeoutMs: number;
  readonly expectedDescriptor: DetectorArtifactDescriptor & Readonly<{
    name: "phileas-4-gliner";
    localProcessing: true;
  }>;
}

export type PhileasWireRequest =
  | Readonly<{
      kind: "DETECT";
      operationId: string;
      attemptId: string;
      locale: string;
      classes: readonly string[];
      preparedPolicyId: string | null;
      text: string;
    }>
  | Readonly<{
      kind: "APPLY_REPLACEMENTS";
      operationId: string;
      attemptId: string;
      preparedPolicyId: string | null;
      text: string;
      replacements: readonly Readonly<{
        spanId: string;
        startUtf16: number;
        endUtf16: number;
        token: string;
      }>[];
    }>;

export type PhileasWireResponse =
  | Readonly<{
      kind: "DETECTED";
      descriptor: DetectorArtifactDescriptor;
      spans: readonly RawDetectedSpan[];
    }>
  | Readonly<{
      kind: "REDACTED";
      serviceVersion: string;
      text: string;
      appliedSpanIds: readonly string[];
    }>;

export interface BodyLoggingDisabledHttpClient {
  /** The implementation's observability hooks must accept metadata only, never body or headers. */
  postJson(
    path: "/internal/v1/detect" | "/internal/v1/apply-replacements" | "/internal/v1/policies",
    body: unknown,
    signal: AbortSignal,
  ): Promise<unknown>;
  delete(path: string, signal: AbortSignal): Promise<void>;
}

/** Contract declaration only; the real adapter belongs in the package adapter entry point. */
export declare class PhileasServiceAdapter
  implements DetectorRedactorPort, PreparedDetectorPolicyCompiler
{
  readonly descriptor: DetectorArtifactDescriptor & Readonly<{
    name: "phileas-4-gliner";
    localProcessing: true;
  }>;

  constructor(config: PhileasServiceAdapterConfig, http: BodyLoggingDisabledHttpClient);

  detect(input: DetectorInput, signal: AbortSignal): Promise<readonly RawDetectedSpan[]>;
  redact(input: DetectorRedactionRequest, signal: AbortSignal): Promise<DetectorRedactionResult>;
  health(): Promise<"ready" | "degraded" | "unavailable">;
  prepare(input: Parameters<PreparedDetectorPolicyCompiler["prepare"]>[0]): Promise<PreparedPolicyRef>;
  evict(ref: PreparedPolicyRef): Promise<void>;
}

/** Brands a validated sidecar response only after span IDs and applied plan are exact. */
export declare function asSidecarTokenizedText(value: string): TokenizedText;
