import type { MatterAiContextAccessor, MatterAiPolicyAccessor, PhiSubstitutionEngine } from "./contracts";
import type { TokenizedText } from "./brands";
import type { PhiAuditEmitter } from "../audit/ports";

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

export interface ProtectedAiProviderDependencies<GenerateOptions, RawProvider> {
  readonly engine: PhiSubstitutionEngine;
  readonly context: MatterAiContextAccessor;
  readonly policy: MatterAiPolicyAccessor;
  readonly options: AiProviderOptionProjector<GenerateOptions>;
  readonly router: OriginalContentProviderRouter<GenerateOptions, RawProvider>;
  readonly safeTrace: SafeAiTrace;
  readonly audit: PhiAuditEmitter;
  /** Private adapter supplied by the product; it MUST NOT be exported as an application binding. */
  readonly invokeRaw: RawProvider;
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
