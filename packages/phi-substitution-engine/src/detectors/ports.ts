import type {
  EngineVersion,
  MatterId,
  OperationAttemptId,
  OperationId,
  SubstitutionToken,
  TenantId,
  TokenizedText,
  Utf16Offset,
} from "../core/brands";
import type { IdentifierClass } from "../core/contracts";

export type DetectorProviderName = "phileas-4-gliner" | "azure-ai-language-phi";
export type OffsetEncoding = "UTF16" | "UNICODE_CODE_POINT" | "UTF8_BYTE";

export interface DetectorArtifactDescriptor {
  readonly name: DetectorProviderName;
  readonly serviceVersion: string;
  readonly engineVersion: string;
  readonly modelVersion: string;
  readonly recognizerVersion: string;
  readonly configurationDigest: string;
  readonly residency: string;
  readonly localProcessing: boolean;
}

export interface PreparedPolicyRef {
  /** Opaque ID; never a policy name, customer value, or value-derived digest. */
  readonly id: string;
  readonly tenantId: TenantId;
  readonly matterId: MatterId;
  readonly dictionaryVersion: string;
  readonly schemaVersion: string;
  readonly engineVersion: EngineVersion;
  readonly expiresAt: string;
}

export interface DetectorInput {
  readonly tenantId: TenantId;
  readonly matterId: MatterId;
  readonly operationId: OperationId;
  readonly attemptId: OperationAttemptId;
  readonly text: string;
  readonly locale: string;
  readonly classes: readonly IdentifierClass[];
  readonly preparedPolicy: PreparedPolicyRef | null;
}

export interface RawDetectedSpan {
  /** Opaque response-local span ID, never matched text. */
  readonly id: string;
  readonly start: number;
  readonly end: number;
  readonly offsetEncoding: OffsetEncoding;
  readonly identifierClass: IdentifierClass;
  readonly confidence: number;
  readonly detectorVersion: string;
}

export interface DetectedSpan {
  readonly id: string;
  readonly startUtf16: Utf16Offset;
  readonly endUtf16: Utf16Offset;
  readonly identifierClass: IdentifierClass;
  readonly confidence: number;
  readonly detectorVersion: string;
}

export type SpanNormalizationResult =
  | Readonly<{ ok: true; spans: readonly DetectedSpan[] }>
  | Readonly<{
      ok: false;
      reason:
        | "OUT_OF_RANGE"
        | "INVALID_BOUNDARY"
        | "OVERLAP"
        | "VERSION_MISMATCH"
        | "DUPLICATE_SPAN_ID";
    }>;

export interface DetectorSpanNormalizer {
  /** Validates against original text; never clamps, guesses, reorders, or drops invalid spans. */
  normalize(
    originalText: string,
    expectedDetectorVersion: string,
    raw: readonly RawDetectedSpan[],
  ): SpanNormalizationResult;
}

export interface RedactionInstruction {
  readonly detectedSpanId: string;
  readonly startUtf16: Utf16Offset;
  readonly endUtf16: Utf16Offset;
  readonly replacement: SubstitutionToken;
}

export interface DetectorRedactionRequest {
  readonly tenantId: TenantId;
  readonly matterId: MatterId;
  readonly operationId: OperationId;
  readonly attemptId: OperationAttemptId;
  readonly text: string;
  /** Exact, non-overlapping, original-text spans already validated by TypeScript core. */
  readonly instructions: readonly RedactionInstruction[];
  readonly preparedPolicy: PreparedPolicyRef | null;
}

export interface DetectorRedactionResult {
  readonly text: TokenizedText;
  readonly appliedSpanIds: readonly string[];
  readonly serviceVersion: string;
}

/**
 * Vendor-neutral detection/redaction boundary. Core never imports Phileas, Philter, ONNX,
 * Azure SDK, HTTP, or FPE classes. Phase 1 keeps this port disabled by trusted policy.
 */
export interface DetectorRedactorPort {
  readonly descriptor: DetectorArtifactDescriptor;
  detect(input: DetectorInput, signal: AbortSignal): Promise<readonly RawDetectedSpan[]>;
  /**
   * Applies only the explicit TS-assigned plan. A port may use its native span/redaction engine,
   * but may not invent replacements or return a token/value map.
   */
  redact(
    input: DetectorRedactionRequest,
    signal: AbortSignal,
  ): Promise<DetectorRedactionResult>;
  health(): Promise<"ready" | "degraded" | "unavailable">;
}

export interface PreparedDetectorPolicyCompiler {
  /**
   * Compiles only the current matter/version. Implementations must not place matter values in a
   * shared dictionary and must not log or serialize the source terms outside the sidecar request.
   */
  prepare(input: Readonly<{
    tenantId: TenantId;
    matterId: MatterId;
    dictionaryVersion: string;
    schemaVersion: string;
    engineVersion: EngineVersion;
    termsByClass: Readonly<Partial<Record<IdentifierClass, readonly string[]>>>;
  }>): Promise<PreparedPolicyRef>;
  evict(ref: PreparedPolicyRef): Promise<void>;
}

export interface DetectorDeadlineRunner {
  /** Primary and fallback share one deadline; fallback must be independently eligible. */
  detectWithin(input: Readonly<{
    primary: DetectorRedactorPort;
    fallback: DetectorRedactorPort | null;
    request: DetectorInput;
    deadlineMs: number;
    normalizer: DetectorSpanNormalizer;
  }>): Promise<Readonly<{
    descriptor: DetectorArtifactDescriptor;
    spans: readonly DetectedSpan[];
  }>>;
}

export interface DetectorOnlyTokenAllocator {
  /**
   * Creates stable tokens only for this operation and stores raw values encrypted for at most
   * 24 hours. It never promotes a detected value into permanent matter aliases automatically.
   */
  allocate(input: Readonly<{
    tenantId: TenantId;
    matterId: MatterId;
    operationId: OperationId;
    attemptId: OperationAttemptId;
    originalText: string;
    spans: readonly DetectedSpan[];
  }>): Promise<readonly RedactionInstruction[]>;
}
