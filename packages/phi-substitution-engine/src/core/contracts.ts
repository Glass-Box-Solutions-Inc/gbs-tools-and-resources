import type {
  ActorId,
  DictionaryVersion,
  DisplayText,
  EngineVersion,
  KnownLocale,
  MatterId,
  OperationAttemptId,
  OperationId,
  SchemaVersion,
  SubstitutionToken,
  TenantId,
  TokenizedText,
} from "./brands";

export type IdentifierClass =
  | "PERSON_NAME"
  | "DOB"
  | "SSN"
  | "MRN"
  | "DEA"
  | "EMAIL"
  | "PHONE"
  | "ADDRESS"
  | "CLAIM_NUMBER"
  | "POLICY_NUMBER"
  | "ACCOUNT_NUMBER"
  | "OTHER_TAGGED";

/** A total count record: every IdentifierClass key is present, including zeroes. */
export type IdentifierCounts = Readonly<Record<IdentifierClass, number>>;
export type AiOperation = "generation" | "stream" | "embedding" | "graph_extraction";

/** Trusted, opaque request/job identity. It contains no caller-controlled policy switch. */
export interface MatterAiContext {
  readonly tenantId: TenantId;
  readonly matterId: MatterId;
  readonly actorId: ActorId;
  readonly operationId: OperationId;
  readonly attemptId: OperationAttemptId;
}

export interface TrustedMatterAiPolicy {
  readonly mode: "REQUIRED" | "OFF_APPROVED";
  readonly locale: KnownLocale;
  readonly activeDictionaryVersion: DictionaryVersion;
  readonly schemaVersion: SchemaVersion;
  readonly detectorRequirement: "DISABLED_PHASE_1" | "REQUIRED";
  /** Present only for an authorized, unexpired OFF_APPROVED decision. */
  readonly approvedOffDecisionId: string | null;
}

/** Missing transport/job context is an error; there is deliberately no optional getter. */
export interface MatterAiContextAccessor {
  require(): Promise<MatterAiContext>;
}

/** Loads policy from trusted matter metadata, never from provider options or user input. */
export interface MatterAiPolicyAccessor {
  require(context: MatterAiContext): Promise<TrustedMatterAiPolicy>;
}

export type TextSegmentKind =
  | "system"
  | "transcript"
  | "document"
  | "user"
  | "tool"
  | "embedding";

export interface TextSegment {
  /** Stable, unique option path such as `messages[2].content[0].text`. */
  readonly path: string;
  readonly kind: TextSegmentKind;
  readonly text: string;
}

export interface TokenizedTextSegment extends Omit<TextSegment, "text"> {
  readonly text: TokenizedText;
}

export interface SubstitutionRequest {
  readonly context: MatterAiContext;
  readonly policy: TrustedMatterAiPolicy;
  readonly segments: readonly TextSegment[];
  readonly purpose: AiOperation;
}

/**
 * Non-serializable operation capability. It contains references only, never a map.
 * Implementations MUST throw from `toJSON` and reject use after release/abort.
 */
export interface ReversalHandle {
  readonly tenantId: TenantId;
  readonly matterId: MatterId;
  readonly dictionaryVersion: DictionaryVersion;
  readonly operationId: OperationId;
  readonly attemptId: OperationAttemptId;
  toJSON(): never;
}

export interface SubstitutionResult {
  readonly segments: readonly TokenizedTextSegment[];
  readonly dictionaryVersion: DictionaryVersion;
  readonly engineVersion: EngineVersion;
  readonly counts: IdentifierCounts;
  readonly ambiguityCount: number;
  readonly detector: Readonly<{ name: string; version: string }> | null;
  readonly latencyMs: Readonly<{ dictionary: number; detector: number; total: number }>;
  readonly reversalHandle: ReversalHandle;
}

export interface ReverseStream {
  /** Accepts provider text only; no chunk may be forwarded directly to a display sink. */
  push(chunk: TokenizedText): Promise<void>;
  /** Validates and reverses the entire remainder before emitting it. */
  end(): Promise<void>;
  /** Releases sensitive references and emits no buffered text. Idempotent. */
  abort(reason: unknown): Promise<void>;
}

export interface PhiSubstitutionEngine {
  substitute(request: SubstitutionRequest): Promise<SubstitutionResult>;
  reverse(text: TokenizedText, handle: ReversalHandle): Promise<DisplayText>;
  createReverseStream(
    handle: ReversalHandle,
    sink: (safe: DisplayText) => void | Promise<void>,
  ): ReverseStream;
}

export type PhiEngineFailureCode =
  | "MISSING_TRUSTED_CONTEXT"
  | "MISSING_TRUSTED_POLICY"
  | "DICTIONARY_NOT_READY"
  | "DICTIONARY_UNAVAILABLE"
  | "AMBIGUOUS_KNOWN_IDENTIFIER"
  | "DETECTOR_UNAVAILABLE"
  | "INVALID_DETECTOR_OFFSET"
  | "UNCLASSIFIED_PROVIDER_FIELD"
  | "AUDIT_DURABILITY_UNAVAILABLE"
  | "REVERSAL_FAILED"
  | "PROVIDER_SAFETY_GATE_FAILED";

export interface PhiEngineError extends Error {
  readonly name: "PhiEngineError";
  readonly code: PhiEngineFailureCode;
  readonly operationId: OperationId;
  /** Always safe fixed metadata; never text, values, variants, excerpts, or maps. */
  readonly safeDetails: Readonly<Record<string, string | number | boolean | null>>;
}

/** The only legal reversal lookup: distinct, validated tokens encountered in one response. */
export interface ReversalStore {
  readonly maximumEncounteredTokenBatch: number;
  resolveEncounteredTokens(input: Readonly<{
    tenantId: TenantId;
    matterId: MatterId;
    dictionaryVersion: DictionaryVersion;
    tokens: readonly SubstitutionToken[];
  }>): Promise<ReadonlyMap<SubstitutionToken, string>>;
}
