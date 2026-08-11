import type {
  DictionaryVersion,
  DisplayText,
  MatterId,
  OperationAttemptId,
  OperationId,
  SubstitutionToken,
  TenantId,
  TokenizedText,
} from "../core/brands";
import type { ReversalHandle, ReversalStore } from "../core/contracts";
import type { EscapedTokenLiteral, TokenGrammar, TokenGrammarPolicy, TokenReverser } from "./ports";
import { ReversalFailedError, ReversalHandleNotSerializableError } from "./errors";
import { restoreSentinelLiterals } from "./escaper";

const SEP = String.fromCharCode(0);

/** Keys that scope every reversal lookup (CONTRACT-phase1 L8: tenant is always present). */
export interface ReversalKeys {
  readonly tenantId: TenantId;
  readonly matterId: MatterId;
  readonly dictionaryVersion: DictionaryVersion;
  readonly operationId: OperationId;
}

/**
 * Non-serializable, in-process reversal capability (CONTRACT-phase1 §7, N2).
 *
 * Holds only references (ids); it never holds a map. `toJSON` throws so the
 * handle cannot be smuggled into a trace, job, provider-metadata, or shared
 * cache payload.
 */
export class InProcessReversalHandle implements ReversalHandle {
  /**
   * §7 / NEW-2: the handle is an OPAQUE in-process capability. EVERY field — the scoping ids,
   * the branded bigint version, AND the escaped source literals — is held in a PRIVATE field.
   * The `ReversalHandle` shape is exposed only through prototype GETTERS, never own-enumerable
   * data properties, so an object spread `{ ...handle }` copies NOTHING: no branded id, no
   * bigint version, and above all no raw token-shaped source literal. The literals are usable
   * solely through the bounded `restoreEscapedLiterals` method (which never hands them back),
   * and the only serialization path, `toJSON`, always throws.
   */
  readonly #tenantId: TenantId;
  readonly #matterId: MatterId;
  readonly #dictionaryVersion: DictionaryVersion;
  readonly #operationId: OperationId;
  readonly #attemptId: OperationAttemptId;
  readonly #literals: readonly EscapedTokenLiteral[];

  constructor(keys: {
    tenantId: TenantId;
    matterId: MatterId;
    dictionaryVersion: DictionaryVersion;
    operationId: OperationId;
    attemptId: OperationAttemptId;
    literals?: readonly EscapedTokenLiteral[];
  }) {
    this.#tenantId = keys.tenantId;
    this.#matterId = keys.matterId;
    this.#dictionaryVersion = keys.dictionaryVersion;
    this.#operationId = keys.operationId;
    this.#attemptId = keys.attemptId;
    this.#literals = keys.literals ?? [];
  }

  get tenantId(): TenantId {
    return this.#tenantId;
  }

  get matterId(): MatterId {
    return this.#matterId;
  }

  get dictionaryVersion(): DictionaryVersion {
    return this.#dictionaryVersion;
  }

  get operationId(): OperationId {
    return this.#operationId;
  }

  get attemptId(): OperationAttemptId {
    return this.#attemptId;
  }

  /**
   * Bounded capability (§7): restores escaped source literals onto already-reversed
   * text. It applies the private literals in place and never returns them, so no raw
   * token-shaped source data can be read off the handle.
   */
  restoreEscapedLiterals(reversed: string): string {
    return restoreSentinelLiterals(reversed, this.#literals);
  }

  toJSON(): never {
    throw new ReversalHandleNotSerializableError();
  }
}

interface ReversalRecordInput {
  readonly tenantId: TenantId;
  readonly matterId: MatterId;
  readonly dictionaryVersion: DictionaryVersion;
  readonly token: SubstitutionToken;
  readonly canonical: string;
}

/**
 * Tenant-scoped reversal store (CONTRACT-phase1 §7, L8, N2).
 *
 * The ONLY read surface is the bounded `resolveEncounteredTokens`; there is no
 * list-all API. Every key includes the tenant id, so a cross-tenant lookup
 * misses even when matter, version, and token text collide.
 */
export class InMemoryReversalStore implements ReversalStore {
  readonly maximumEncounteredTokenBatch: number;
  private readonly canonicalByKey = new Map<string, string>();

  constructor(maximumEncounteredTokenBatch = 256) {
    this.maximumEncounteredTokenBatch = maximumEncounteredTokenBatch;
  }

  private key(
    tenantId: TenantId,
    matterId: MatterId,
    dictionaryVersion: DictionaryVersion,
    token: SubstitutionToken,
  ): string {
    return `${tenantId}${SEP}${matterId}${SEP}${dictionaryVersion.toString()}${SEP}${token}`;
  }

  /** Write the current canonical value for a token (compiler-side truth write). */
  record(input: ReversalRecordInput): void {
    this.canonicalByKey.set(
      this.key(input.tenantId, input.matterId, input.dictionaryVersion, input.token),
      input.canonical,
    );
  }

  async resolveEncounteredTokens(input: {
    tenantId: TenantId;
    matterId: MatterId;
    dictionaryVersion: DictionaryVersion;
    tokens: readonly SubstitutionToken[];
  }): Promise<ReadonlyMap<SubstitutionToken, string>> {
    if (input.tokens.length > this.maximumEncounteredTokenBatch) {
      throw new ReversalFailedError();
    }
    const resolved = new Map<SubstitutionToken, string>();
    const seen = new Set<string>();
    for (const token of input.tokens) {
      if (seen.has(token)) {
        continue;
      }
      seen.add(token);
      const canonical = this.canonicalByKey.get(
        this.key(input.tenantId, input.matterId, input.dictionaryVersion, token),
      );
      if (canonical !== undefined) {
        resolved.set(token, canonical);
      }
    }
    return resolved;
  }
}

/**
 * Atomically reverse tokenized text to display text (CONTRACT-phase1 N5).
 *
 * Any malformed/nested/overlong/unclosed token shape, or any grammar-valid but
 * unknown token, fails the WHOLE reversal with no partial DisplayText. Only
 * distinct, grammar-validated tokens encountered in this one text are resolved,
 * in a single bounded batch (N2: no per-token or list-all lookups).
 */
export async function reverseText(
  text: string,
  keys: ReversalKeys,
  store: ReversalStore,
  grammar: TokenGrammar,
  policy: TokenGrammarPolicy,
): Promise<string> {
  const spans = grammar.scan(text, policy);

  for (const span of spans) {
    if (span.parsed.kind === "malformed") {
      throw new ReversalFailedError(keys.operationId);
    }
  }

  const distinct: SubstitutionToken[] = [];
  const seen = new Set<string>();
  for (const span of spans) {
    if (span.parsed.kind === "valid") {
      const token = span.parsed.token;
      if (!seen.has(token)) {
        seen.add(token);
        distinct.push(token);
      }
    }
  }

  if (distinct.length > store.maximumEncounteredTokenBatch) {
    throw new ReversalFailedError(keys.operationId);
  }

  const resolved =
    distinct.length === 0
      ? new Map<SubstitutionToken, string>()
      : await store.resolveEncounteredTokens({
          tenantId: keys.tenantId,
          matterId: keys.matterId,
          dictionaryVersion: keys.dictionaryVersion,
          tokens: distinct,
        });

  for (const token of distinct) {
    if (!resolved.has(token)) {
      // Known-shape but unknown token: fail visibly, never display the raw chunk.
      throw new ReversalFailedError(keys.operationId);
    }
  }

  let out = "";
  let cursor = 0;
  for (const span of spans) {
    if (span.parsed.kind !== "valid") {
      continue;
    }
    out += text.slice(cursor, span.startUtf16);
    out += resolved.get(span.parsed.token) as string;
    cursor = span.endUtf16;
  }
  out += text.slice(cursor);
  return out;
}

/** Adapts the shared `reverseText` to the frozen `TokenReverser` port. */
export class AtomicTokenReverser implements TokenReverser {
  constructor(
    private readonly store: ReversalStore,
    private readonly grammar: TokenGrammar,
    private readonly policy: TokenGrammarPolicy,
  ) {}

  async reverse(text: TokenizedText, handle: ReversalHandle): Promise<DisplayText> {
    const reversed = await reverseText(
      text,
      {
        tenantId: handle.tenantId,
        matterId: handle.matterId,
        dictionaryVersion: handle.dictionaryVersion,
        operationId: handle.operationId,
      },
      this.store,
      this.grammar,
      this.policy,
    );
    return reversed as DisplayText;
  }
}
