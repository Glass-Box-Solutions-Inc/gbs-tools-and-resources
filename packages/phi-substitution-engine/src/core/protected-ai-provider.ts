import type { MatterAiContextAccessor, MatterAiPolicyAccessor, PhiSubstitutionEngine } from "./contracts";
import type { DisplayText, EngineVersion, TokenizedText } from "./brands";
import type {
  AuditPrimaryStore,
  EncryptedAuditSpool,
  PhiAuditEmitter,
} from "../audit/ports";

/** Structural mirror of Glassy's existing application-facing AiProvider. */
export interface AiProvider<
  GenerateOptions,
  GenerateTextResult,
  GenerateStreamResult,
  EmbeddingKind,
  EmbeddingResult,
> {
  generateText(options: GenerateOptions): GenerateTextResult;
  generateStream(options: GenerateOptions): GenerateStreamResult;
  embedText(text: string, kind: EmbeddingKind): EmbeddingResult;
}

export interface ClassifiedProviderOptions<GenerateOptions> {
  readonly segments: readonly import("./contracts").TextSegment[];
  /** Rebuilds options from exactly one tokenized value for every classified segment path. */
  rebuild(tokenized: readonly import("./contracts").TokenizedTextSegment[]): GenerateOptions;
}

/**
 * Exhaustive adapter over Glassy's option union. Unknown object variants or new text-bearing
 * fields MUST return UNCLASSIFIED_PROVIDER_FIELD; no permissive passthrough is allowed.
 */
export interface AiProviderOptionProjector<GenerateOptions> {
  classify(options: GenerateOptions): ClassifiedProviderOptions<GenerateOptions>;
}

/** Provider choice/safety gates inspect ORIGINAL content and are fixed before substitution. */
export interface OriginalContentProviderRouter<GenerateOptions, RawProvider> {
  selectUsingOriginalContent(options: GenerateOptions): Promise<Readonly<{
    provider: RawProvider;
    isProductionSafe: boolean;
    baaSatisfied: boolean;
    providerId: string;
  }>>;
}

/** Content-bearing safe observability accepts branded tokenized text only. */
export interface SafeAiTrace {
  request(paths: readonly Readonly<{ path: string; text: TokenizedText }>[]): Promise<void>;
  response(text: TokenizedText): Promise<void>;
  metadata(values: Readonly<Record<string, string | number | boolean | null>>): Promise<void>;
}

/** Provider-neutral, PHI-free usage metadata copied into a protected result. */
export interface ProtectedAiUsage {
  readonly inputTokens?: number;
  readonly outputTokens?: number;
  readonly totalTokens?: number;
}

/** A tool call whose arguments have already been reversed in-package. */
export interface ProtectedAiToolCall {
  readonly id: string;
  readonly name: string;
  readonly arguments: DisplayText;
}

/** Completion metadata shared by generated text and streaming completion. */
export interface ProtectedAiResultTail {
  /** Authoritative id from the original-content routing decision. */
  readonly providerId: string;
  readonly model?: string;
  readonly usage?: ProtectedAiUsage;
  readonly toolCalls?: readonly ProtectedAiToolCall[];
}

/** Exact application-facing result; no tokenized provider value may inhabit this shape. */
export interface ProtectedAiTextResult extends ProtectedAiResultTail {
  readonly display: DisplayText;
}

/** Private-provider tool call. Its tokenized arguments exist only behind the protected boundary. */
export interface ProductionRawToolCall {
  readonly id: string;
  readonly name: string;
  readonly arguments: TokenizedText;
}

export interface ProductionRawResultTail {
  readonly model?: string;
  readonly usage?: ProtectedAiUsage;
  readonly toolCalls?: readonly ProductionRawToolCall[];
}

export interface ProductionRawTextResult extends ProductionRawResultTail {
  readonly text: TokenizedText;
}

/** Type-only private provider seam used by production composition. */
export interface ProductionRawProviderPort<GenerateOptions, EmbeddingKind = string> {
  generateText(options: GenerateOptions, signal: AbortSignal): Promise<ProductionRawTextResult>;
  generateStream(
    options: GenerateOptions,
    onChunk: (chunk: TokenizedText) => void | Promise<void>,
    signal: AbortSignal,
  ): Promise<ProductionRawResultTail>;
  embedText(text: TokenizedText, kind: EmbeddingKind): Promise<readonly number[]>;
}

export type DisplayChunkSink = (chunk: DisplayText) => void | Promise<void>;

/** Provider-agnostic protected surface for product-owned adapters. */
export interface ProtectedAiCallSurface<GenerateOptions, EmbeddingKind = string> {
  generateText(options: GenerateOptions, signal?: AbortSignal): Promise<ProtectedAiTextResult>;
  streamText(
    options: GenerateOptions,
    sink: DisplayChunkSink,
    signal?: AbortSignal,
  ): Promise<ProtectedAiResultTail>;
  embedText(text: string, kind: EmbeddingKind): Promise<readonly number[]>;
}

/** Required production composition inputs. No development provider or engine default is legal. */
export interface CreateProductionProtectedAiProviderOptions<
  GenerateOptions,
  EmbeddingKind = string,
> {
  readonly engine: PhiSubstitutionEngine;
  readonly engineVersion: EngineVersion;
  /** Consumer boot-config digest of normalized engine mode and BAA matrix. */
  readonly enginePolicyVersion: string;
  readonly context: MatterAiContextAccessor;
  readonly policy: MatterAiPolicyAccessor;
  readonly projector: AiProviderOptionProjector<GenerateOptions>;
  readonly router: OriginalContentProviderRouter<
    GenerateOptions,
    ProductionRawProviderPort<GenerateOptions, EmbeddingKind>
  >;
  readonly safeTrace: SafeAiTrace;
  readonly auditPrimary: AuditPrimaryStore;
  readonly auditSpool: EncryptedAuditSpool;
  readonly embeddingOptionsFactory: (text: string) => GenerateOptions;
  readonly clock?: () => string;
}

export interface ProtectedAiProviderDependencies<GenerateOptions, RawProvider> {
  readonly engine: PhiSubstitutionEngine;
  readonly context: MatterAiContextAccessor;
  readonly policy: MatterAiPolicyAccessor;
  readonly options: AiProviderOptionProjector<GenerateOptions>;
  readonly router: OriginalContentProviderRouter<GenerateOptions, RawProvider>;
  readonly safeTrace: SafeAiTrace;
  readonly audit: PhiAuditEmitter;
  /**
   * Legacy private adapter. Optional widening (GLY-353): production obtains the request-local
   * provider from its router and MUST NOT construct or default a fallback adapter.
   */
  readonly invokeRaw?: RawProvider;
}

/**
 * Public phase-1 shape. Its three methods intentionally match Glassy's existing AiProvider:
 * `generateText(options)`, `generateStream(options)`, and `embedText(text, kind)`.
 */
export declare class ProtectedAiProvider<
  GenerateOptions,
  GenerateTextResult,
  GenerateStreamResult,
  EmbeddingKind,
  EmbeddingResult,
  RawProvider,
> implements AiProvider<GenerateOptions, GenerateTextResult, GenerateStreamResult, EmbeddingKind, EmbeddingResult> {
  constructor(dependencies: ProtectedAiProviderDependencies<GenerateOptions, RawProvider>);
  generateText(options: GenerateOptions): GenerateTextResult;
  generateStream(options: GenerateOptions): GenerateStreamResult;
  embedText(text: string, kind: EmbeddingKind): EmbeddingResult;
}
