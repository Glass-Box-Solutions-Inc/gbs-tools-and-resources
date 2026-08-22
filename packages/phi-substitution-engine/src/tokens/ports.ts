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
      /**
       * GLY-373 §3.1: the DETECTOR namespace label (16 lowercase hex characters) for a
       * `[[D~ns~Role_N]]` token, or `null` for an AUTHORITY-namespace token (`[[Role]]` /
       * `[[Role_N]]`, byte-identical to 0.2.0).
       *
       * REQUIRED, deliberately not optional: an internal reader or an external implementer
       * must not be able to silently ignore the field and treat a namespaced detector token
       * as an authority token — that is the whole invariant the field carries.
       */
      namespace: string | null;
    }>
  | Readonly<{
      kind: "malformed";
      reason:
        | "UNKNOWN_ROLE"
        | "NESTED"
        | "OVERLONG"
        | "BAD_SEQUENCE"
        | "BAD_DELIMITER"
        | "BAD_NAMESPACE";
    }>
  | Readonly<{ kind: "not_token" }>;

export interface TokenGrammar {
  parse(candidate: string, policy: TokenGrammarPolicy): ParsedToken;
  /**
   * GLY-373 §3.1: `namespace` is OPTIONAL. Absent/`undefined` emits the AUTHORITY production,
   * byte-identical to 0.2.0. When present it MUST be exactly 16 lowercase hex characters;
   * a violation throws the fixed `token_grammar_bad_namespace` rather than emitting an
   * unvalidated namespace into a token.
   */
  format(
    role: TokenRole,
    sequence: number | null,
    policy: TokenGrammarPolicy,
    namespace?: string,
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
