import type {
  DictionaryVersion,
  DisplayText,
  EscapedSourceText,
  MatterId,
  SubjectId,
  SubstitutionToken,
  TenantId,
  TokenizedText,
  TokenRole,
} from "../core/brands";
import type {
  ReversalHandle,
  ReversalStore,
  ReverseStream,
} from "../core/contracts";

export interface TokenGrammarPolicy {
  readonly allowedRoles: ReadonlySet<TokenRole>;
  readonly maximumTokenUtf16Length: number;
  readonly maximumRoleUtf16Length: number;
  readonly maximumSequence: number;
}

export type ParsedToken =
  | Readonly<{
      kind: "valid";
      token: SubstitutionToken;
      role: TokenRole;
      sequence: number | null;
    }>
  | Readonly<{
      kind: "malformed";
      reason:
        | "UNKNOWN_ROLE"
        | "NESTED"
        | "OVERLONG"
        | "BAD_SEQUENCE"
        | "BAD_DELIMITER";
    }>
  | Readonly<{ kind: "not_token" }>;

export interface TokenGrammar {
  parse(candidate: string, policy: TokenGrammarPolicy): ParsedToken;
  format(
    role: TokenRole,
    sequence: number | null,
    policy: TokenGrammarPolicy,
  ): SubstitutionToken;
  /** Returns all complete or token-like/malformed spans; nested and overlong input is not ignored. */
  scan(
    text: string,
    policy: TokenGrammarPolicy,
  ): readonly Readonly<{
    startUtf16: number;
    endUtf16: number;
    parsed: Exclude<ParsedToken, Readonly<{ kind: "not_token" }>>;
  }>[];
}

export interface TokenAssignmentStore {
  /**
   * Linearizable acquire-or-return-existing. A durable implementation commits before resolving.
   * Identity is tenant+matter+subject+role, never normalized display text; dictionaryVersion is
   * mandatory fencing/association context but does not renumber an existing identity.
   */
  getOrAllocate(
    input: Readonly<{
      tenantId: TenantId;
      matterId: MatterId;
      subjectId: SubjectId;
      role: TokenRole;
      dictionaryVersion: DictionaryVersion;
    }>,
  ): Promise<SubstitutionToken>;
  /** Atomic, idempotent retirement. Monotonic ordinals are durably burned and never reused. */
  retire(
    input: Readonly<{
      tenantId: TenantId;
      matterId: MatterId;
      subjectId: SubjectId;
      role: TokenRole;
      dictionaryVersion: DictionaryVersion;
    }>,
  ): Promise<void>;
}

export interface EscapedTokenLiteral {
  readonly internalStartUtf16: number;
  readonly internalEndUtf16: number;
  readonly originalLiteral: string;
}

export interface SourceTokenEscaper {
  /** Escapes every reserved-token-shaped source sequence before dictionary matching. */
  escape(
    source: string,
    policy: TokenGrammarPolicy,
  ): Readonly<{
    text: EscapedSourceText;
    literals: readonly EscapedTokenLiteral[];
  }>;
  /** Restores source literals as literals without making them reversal-capable. */
  restoreLiterals(
    text: TokenizedText,
    literals: readonly EscapedTokenLiteral[],
  ): TokenizedText;
}

export interface TokenReverser {
  /** Atomic: any unknown/malformed/nested/overlong token fails with no partial DisplayText. */
  reverse(text: TokenizedText, handle: ReversalHandle): Promise<DisplayText>;
}

export interface ReverseStreamFactory {
  /**
   * Uses M-1 UTF-16 holdback where M is the maximum mapped token length capped by grammar;
   * never splits a surrogate pair and validates the complete remainder on end().
   */
  create(
    input: Readonly<{
      handle: ReversalHandle;
      store: ReversalStore;
      grammar: TokenGrammar;
      policy: TokenGrammarPolicy;
      sink: (safe: DisplayText) => void | Promise<void>;
    }>,
  ): ReverseStream;
}
