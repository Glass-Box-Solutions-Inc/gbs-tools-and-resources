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
import { restoreSentinelLiterals, SENTINEL_CLOSE, SENTINEL_OPEN } from "./escaper";

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

  // §7/N2: the reversal store is an INJECTED port and its OWN behavior is UNTRUSTED — a throwing
  // `maximumEncounteredTokenBatch` getter, a `resolveEncounteredTokens` REJECTION, or a returned map
  // whose `has`/`get` throws could carry raw PHI. Contain ALL of it here: the composed engine calls
  // reverseText DIRECTLY (without the atomic/streaming adapters' outer guard), so this function must
  // never propagate a raw store error — only a fixed-code ReversalFailedError.
  let batchLimit: unknown;
  try {
    batchLimit = store.maximumEncounteredTokenBatch;
  } catch {
    throw new ReversalFailedError(keys.operationId);
  }
  if (typeof batchLimit !== "number" || distinct.length > batchLimit) {
    throw new ReversalFailedError(keys.operationId);
  }

  let resolved: ReadonlyMap<SubstitutionToken, string>;
  try {
    resolved =
      distinct.length === 0
        ? new Map<SubstitutionToken, string>()
        : await store.resolveEncounteredTokens({
            tenantId: keys.tenantId,
            matterId: keys.matterId,
            dictionaryVersion: keys.dictionaryVersion,
            tokens: distinct,
          });
  } catch {
    throw new ReversalFailedError(keys.operationId);
  }

  for (const token of distinct) {
    let present: boolean;
    try {
      present = resolved.has(token);
    } catch {
      throw new ReversalFailedError(keys.operationId);
    }
    if (!present) {
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
    // §7/N2: read the canonical getter-throw-safe and require a genuine string — an object whose
    // toString/toPrimitive yields PHI must NOT be coerced by `out +=` and emitted as DisplayText.
    let canonical: unknown;
    try {
      canonical = resolved.get(span.parsed.token);
    } catch {
      throw new ReversalFailedError(keys.operationId);
    }
    if (typeof canonical !== "string") {
      throw new ReversalFailedError(keys.operationId);
    }
    out += text.slice(cursor, span.startUtf16);
    out += canonical;
    cursor = span.endUtf16;
  }
  out += text.slice(cursor);
  return out;
}

/**
 * Guarded `instanceof InProcessReversalHandle` (§7/N2): a hostile Proxy `getPrototypeOf` /
 * `Symbol.hasInstance` trap could throw a PHI canary during the prototype-chain walk. An
 * unclassifiable handle is simply treated as not-in-process (identity restore), never a throw.
 */
export function isInProcessReversalHandle(value: unknown): value is InProcessReversalHandle {
  try {
    return value instanceof InProcessReversalHandle;
  } catch {
    return false;
  }
}

/** A fixed placeholder id used when a hostile handle's `operationId` getter itself throws (§7/N2). */
const UNKNOWN_OPERATION_ID = "op-unknown" as unknown as OperationId;

/** A conservative operation-id shape (§7/N2): engine/caller operation ids are UUID/ULID/`op-…`
 *  slugs (no whitespace, no underscores, no free text), so a hostile handle cannot smuggle a raw
 *  (PHI) string into a fixed-code error's public `operationId` and out through a trace/log sink. */
const SAFE_OPERATION_ID = /^[A-Za-z0-9.:-]{1,128}$/;

/** Reads a reversal handle's `operationId` ONCE, getter-throw-safe AND shape-restricted — every
 *  fixed-code failure below carries only this id, so a getter that throws/mutates, or a hostile
 *  handle carrying free-text PHI as its `operationId`, can't turn a fixed failure into a PHI leak.
 *  Absent / non-string / non-slug / throwing → a fixed placeholder. */
export function safeHandleOperationId(handle: ReversalHandle): OperationId {
  try {
    const id = (handle as { operationId?: unknown }).operationId;
    return typeof id === "string" && SAFE_OPERATION_ID.test(id)
      ? (id as unknown as OperationId)
      : UNKNOWN_OPERATION_ID;
  } catch {
    return UNKNOWN_OPERATION_ID;
  }
}

/** Adapts the shared `reverseText` to the frozen `TokenReverser` port. */
export class AtomicTokenReverser implements TokenReverser {
  constructor(
    private readonly store: ReversalStore,
    private readonly grammar: TokenGrammar,
    private readonly policy: TokenGrammarPolicy,
  ) {}

  async reverse(text: TokenizedText, handle: ReversalHandle): Promise<DisplayText> {
    // §7/N2: read the operation id ONCE, getter-throw-safe — every fixed-code failure below carries
    // only this id, so a handle whose `operationId` getter throws (or changes between reads) can't
    // turn a fixed-code failure back into a raw PHI throw.
    const opId = safeHandleOperationId(handle);
    let reversed: string;
    try {
      reversed = await reverseText(
        text,
        {
          tenantId: handle.tenantId,
          matterId: handle.matterId,
          dictionaryVersion: handle.dictionaryVersion,
          operationId: opId,
        },
        this.store,
        this.grammar,
        this.policy,
      );
    } catch {
      // §7/N2: a raw store rejection (its message/`.code` could carry PHI) is NEVER forwarded — fail
      // closed with a fixed-code error carrying only the operation id, exactly as the streaming
      // reverser does. `reverseText` itself only throws fixed-code ReversalFailedErrors, but an
      // injected store's `resolveEncounteredTokens` rejection would otherwise propagate raw.
      throw new ReversalFailedError(opId);
    }
    // L6/§7: restore escaped source-token literals via the handle's bounded capability, then FAIL
    // CLOSED on any residual escape sentinel. The `restoreEscapedLiterals` call is an injected
    // capability even on a REAL handle, so a throw from it must fail closed here rather than
    // propagate a raw PHI message/code (the residual-sentinel check is likewise fail-closed).
    let restored: string;
    try {
      const candidate = isInProcessReversalHandle(handle)
        ? handle.restoreEscapedLiterals(String(reversed))
        : String(reversed);
      // §7/N2: the guard above wraps only the CALL. A hostile handle whose `restoreEscapedLiterals`
      // was replaced can SUCCESSFULLY return a NON-STRING carrier whose `.includes` (below) throws a
      // raw (PHI) message — require a genuine string so the residual-sentinel check runs only on one.
      if (typeof candidate !== "string") {
        throw new ReversalFailedError(opId);
      }
      restored = candidate;
    } catch {
      throw new ReversalFailedError(opId);
    }
    if (restored.includes(SENTINEL_OPEN) || restored.includes(SENTINEL_CLOSE)) {
      throw new ReversalFailedError(opId);
    }
    return restored as DisplayText;
  }
}
