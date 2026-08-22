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
export type AiOperation =
  | "generation"
  | "stream"
  | "embedding"
  | "graph_extraction";

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
  /**
   * GLY-373 §4.1 — governs whether the DETERMINISTIC STRUCTURED-IDENTIFIER pass executes. It does
   * NOT gate the ML detector belt beyond the unchanged `"REQUIRED"` fail-closed; at 0.2.0 the name
   * promised suppression it never delivered (F-J1), and §4.2 is where the mapping is now exact.
   *
   * CONSUMER-VISIBLE BEHAVIOUR CHANGES, STATED RATHER THAN DENIED: a consumer that leaves its
   * existing literal untouched WILL observe different results. The alias preserves the TYPE, not
   * the behaviour — baseline injected detection fixed-failed, whereas the alias now succeeds with
   * namespaced substitution, and default-mode detector token text changes from `[[SSN_2]]` to
   * `[[D~<ns>~SSN_2]]` (AMB-GLY373-01).
   */
  readonly detectorRequirement: /** NEW canonical name for today's behaviour: the deterministic structured pass RUNS. */
    | "DETERMINISTIC_STRUCTURED_ONLY"
    /**
     * DEPRECATED ALIAS — identical behaviour to `DETERMINISTIC_STRUCTURED_ONLY`, retained for pin
     * compatibility (AMB-GLY373-05: Glassy and the dev factory both emit it; removing it would
     * make 0.3.0 a breaking release requiring a lockstep three-repo edit). Remove in a later major.
     */
    | "DISABLED_PHASE_1"
    /**
     * NEW — HARD SUPPRESSION. `detectStructuredIdentifiers` is NOT INVOKED. Untagged identifiers
     * in free text pass through unsubstituted, so this is raw egress of anything the dictionary
     * does not cover; ruling g8 expressly REJECTED it for both consumers for that reason.
     */
    | "STRUCTURED_DETECTION_OFF"
    /** Unchanged: the belt is not wired, so this fixed-fails `DETECTOR_UNAVAILABLE`. */
    | "REQUIRED";
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
  readonly latencyMs: Readonly<{
    dictionary: number;
    detector: number;
    total: number;
  }>;
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
  | "PROVIDER_SAFETY_GATE_FAILED"
  | "CALL_INTERRUPTED";

export interface PhiEngineError extends Error {
  readonly name: "PhiEngineError";
  readonly code: PhiEngineFailureCode;
  readonly operationId: OperationId;
  /** Always safe fixed metadata; never text, values, variants, excerpts, or maps. */
  readonly safeDetails: Readonly<
    Record<string, string | number | boolean | null>
  >;
}

/** The only legal reversal lookup: distinct, validated tokens encountered in one response. */
export interface ReversalStore {
  readonly maximumEncounteredTokenBatch: number;
  resolveEncounteredTokens(
    input: Readonly<{
      tenantId: TenantId;
      matterId: MatterId;
      dictionaryVersion: DictionaryVersion;
      tokens: readonly SubstitutionToken[];
    }>,
  ): Promise<ReadonlyMap<SubstitutionToken, string>>;
}

/**
 * One reversal mapping write (CONTRACT-phase1 §3.1.3 reversal, §6 persistence, N5, L8).
 * A token reverses to its CURRENT canonical value; every write carries the full
 * tenant/matter/version scope (L8) plus the attempt it was written under.
 */
export interface ReversalRecordInput {
  readonly tenantId: TenantId;
  readonly matterId: MatterId;
  readonly dictionaryVersion: DictionaryVersion;
  readonly token: SubstitutionToken;
  /** The current canonical value the token reverses to before display/storage (N5). */
  readonly canonical: string;
  /**
   * Idempotency key (§6 durable PREPARE, §3.1.3). Recording the same (attemptId, token)
   * again MUST be a no-op — a replay/retry never creates a duplicate or divergent mapping,
   * so a token can never egress without exactly one durable reversible mapping. Durable
   * implementations key their idempotent upsert on this; the in-process dev store honors it
   * too (a same-attempt replay is a no-op that keeps the first canonical).
   */
  readonly attemptId: OperationAttemptId;
}

/**
 * WRITE seam of the reversal store (GLY-335 Wave 0 seam-freeze; roadmap defect A#3).
 *
 * The orchestrator depends on THIS port, never on a concrete store class: it writes each
 * `token → current canonical` mapping through `record` and reads it back only through the
 * encounter-bounded `resolveEncounteredTokens` it inherits from `ReversalStore`. Freezing
 * the write as an interface lets the durable, tenant-scoped, envelope-encrypted store (§6,
 * later lane L2.4) be swapped in without re-typing core; `InMemoryReversalStore` stays the
 * in-process dev implementation.
 *
 * §7 / N2 (frozen): there is deliberately NO list-all / enumerate-all / snapshot method —
 * the only read is the bounded, encountered-tokens-only `resolveEncounteredTokens`. A durable
 * implementation MUST NOT widen this surface. `record` returns `void | Promise<void>`: a
 * completed return means the mapping is DURABLY committed. The orchestrator awaits it, so a
 * durable (§6 / L2.4) store persists the mapping BEFORE the token can egress and its rejection
 * fails closed; the in-process dev store completes synchronously (returns `void`).
 */
export interface ReversalWriteStore extends ReversalStore {
  record(input: ReversalRecordInput): void | Promise<void>;
}
