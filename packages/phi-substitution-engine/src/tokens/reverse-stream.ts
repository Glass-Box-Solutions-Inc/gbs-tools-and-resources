import type { DisplayText, TokenizedText } from "../core/brands";
import type {
  ReversalHandle,
  ReversalStore,
  ReverseStream,
} from "../core/contracts";
import type {
  ReverseStreamFactory,
  TokenGrammar,
  TokenGrammarPolicy,
} from "./ports";
import { ReversalFailedError } from "./errors";
import {
  reverseText,
  type ReversalKeys,
  InProcessReversalHandle,
  isInProcessReversalHandle,
  safeOperationIdOf,
} from "./reversal";
import { SENTINEL_OPEN, SENTINEL_CLOSE } from "./escaper";
import { safeRead } from "../core/boundary-snapshot";
import {
  assertTrustedContextIdShape,
  missingTrustedContextError,
} from "../core/errors";

const OPEN = "[[";
const CLOSE = "]]";
const OPEN_BRACKET = 0x5b; // "["

/** Identity restore used when the handle carries no escaped source literals. */
const IDENTITY_RESTORE = (text: string): string => text;

/**
 * True when reversed+restored output still carries an escape sentinel code unit (L6). The
 * sentinels are internal machinery: a COMPLETE escaped literal is replaced by `restore`, so any
 * residual sentinel means a partial/dangling escape that must never reach the display.
 */
function hasResidualSentinel(text: string): boolean {
  return text.includes(SENTINEL_OPEN) || text.includes(SENTINEL_CLOSE);
}

function isHighSurrogate(unit: number): boolean {
  return unit >= 0xd800 && unit <= 0xdbff;
}

function isLowSurrogate(unit: number): boolean {
  return unit >= 0xdc00 && unit <= 0xdfff;
}

/**
 * Index up to which `buffer` can be safely reversed and emitted right now (L4).
 *
 * Two constraints are combined and the smaller cut wins:
 *   1. M-1 holdback: at least `maximumTokenUtf16Length - 1` UTF-16 units are always
 *      retained at the tail, because a token that STARTS in this chunk may only
 *      finish in a later one. This makes emission chunk-independent.
 *   2. Open-token withholding: everything from the first still-open `[[` (or a
 *      trailing lone `[` that could begin one) is withheld.
 * The cut is finally pulled back so it never splits a surrogate pair and never
 * emits a lone leading high surrogate.
 */
function settledBoundary(buffer: string, policy: TokenGrammarPolicy): number {
  const length = buffer.length;
  const holdback = Math.max(0, policy.maximumTokenUtf16Length - 1);
  // 1. M-1 UTF-16 holdback at the tail.
  let cut = Math.max(0, length - holdback);
  // 2. Never split a token: withhold from a still-open `[[`, and never let the M-1 cut
  //    fall INSIDE a complete `[[...]]` token (that would emit a malformed prefix and
  //    abort a perfectly valid stream). Pull the cut back to the token's start instead.
  cut = withholdFromSpans(buffer, cut, OPEN, CLOSE);
  // 3. Escaped source literals are self-delimiting sentinels; the same rule applies so a
  //    sentinel is never split across an emit boundary and its restore stays reliable.
  cut = withholdFromSpans(buffer, cut, SENTINEL_OPEN, SENTINEL_CLOSE);
  // 4. A trailing single "[" could still grow into "[[".
  if (length > 0 && buffer.charCodeAt(length - 1) === OPEN_BRACKET) {
    cut = Math.min(cut, length - 1);
  }
  return avoidSurrogateSplit(buffer, cut);
}

/**
 * Pulls `cut` back so it never lands strictly inside a delimited span (`open`...`close`).
 * An unclosed span withholds everything from its opener; a complete span is never split.
 */
function withholdFromSpans(
  buffer: string,
  cut: number,
  open: string,
  close: string,
): number {
  const length = buffer.length;
  let i = 0;
  while (i < length) {
    const start = buffer.indexOf(open, i);
    if (start < 0) {
      break;
    }
    const closeAt = buffer.indexOf(close, start + open.length);
    if (closeAt < 0) {
      // Unclosed span pending: withhold from its opener until the closer arrives.
      return Math.min(cut, start);
    }
    const end = closeAt + close.length;
    if (cut > start && cut < end) {
      // The cut fell inside a COMPLETE span; retain the whole span for a later flush.
      cut = Math.min(cut, start);
    }
    i = end;
  }
  return cut;
}

function avoidSurrogateSplit(buffer: string, cut: number): number {
  if (cut <= 0) {
    return cut;
  }
  if (cut < buffer.length) {
    if (
      isHighSurrogate(buffer.charCodeAt(cut - 1)) &&
      isLowSurrogate(buffer.charCodeAt(cut))
    ) {
      return cut - 1;
    }
    return cut;
  }
  // cut === buffer.length: never emit a trailing lone high surrogate.
  if (isHighSurrogate(buffer.charCodeAt(cut - 1))) {
    return cut - 1;
  }
  return cut;
}

/** True when an unterminated `[[` has already grown too long to ever be a valid token. */
function openTokenIsOverlong(
  buffer: string,
  policy: TokenGrammarPolicy,
): boolean {
  const open = buffer.indexOf(OPEN);
  if (open < 0) {
    return false;
  }
  if (buffer.indexOf(CLOSE, open + OPEN.length) >= 0) {
    return false;
  }
  return buffer.length - open > policy.maximumTokenUtf16Length;
}

class HoldbackReverseStream implements ReverseStream {
  private buffer = "";
  private failed = false;
  private ended = false;

  constructor(
    private readonly keys: ReversalKeys,
    private readonly store: ReversalStore,
    private readonly grammar: TokenGrammar,
    private readonly policy: TokenGrammarPolicy,
    private readonly sink: (safe: DisplayText) => void | Promise<void>,
    // L6: restores escaped source literals onto the reversed output so a streamed echo of
    // an escaped `[[Role]]` literal round-trips to itself, never leaking the escape sentinel.
    private readonly restore: (text: string) => string = IDENTITY_RESTORE,
  ) {}

  async push(chunk: TokenizedText): Promise<void> {
    if (this.failed || this.ended) {
      return;
    }
    // §7/N2: `chunk` is a PUBLIC input — a NON-STRING carrier (whose toString/toPrimitive yields PHI)
    // must NOT be coerced by `this.buffer += chunk`. Fail closed (latch) rather than concatenate raw.
    if (typeof (chunk as unknown) !== "string") {
      await this.fail();
      return;
    }
    this.buffer += chunk;
    if (openTokenIsOverlong(this.buffer, this.policy)) {
      await this.fail();
    }
    const cut = settledBoundary(this.buffer, this.policy);
    if (cut > 0) {
      await this.emitPrefix(cut);
    }
  }

  async end(): Promise<void> {
    if (this.failed || this.ended) {
      return;
    }
    this.ended = true;
    if (this.buffer.length === 0) {
      return;
    }
    // The entire remainder is validated before anything is emitted: an unknown,
    // malformed, nested, overlong, or terminal-partial token fails here and the
    // buffered suffix is never displayed.
    let reversed: string;
    try {
      reversed = await reverseText(
        this.buffer,
        this.keys,
        this.store,
        this.grammar,
        this.policy,
      );
    } catch {
      // L4: latch — no later push/end may resume or complete after a reversal failure. §7/N2: the
      // rejected error is NEVER forwarded (a raw store rejection's message/`.code` could carry PHI,
      // and `error instanceof Error` would happily pass a hostile carrier through); a fresh
      // fixed-code error carrying only the operation id is thrown instead.
      this.failed = true;
      this.buffer = "";
      throw new ReversalFailedError(this.keys.operationId);
    }
    this.buffer = "";
    let restored: string;
    try {
      const candidate = this.restore(reversed);
      // §7/N2: the catch wraps only the CALL. `restore` (a bounded handle capability, replaceable on a
      // hostile REAL handle) can SUCCESSFULLY return a NON-STRING whose `.includes` in hasResidualSentinel
      // below throws raw (PHI) — require a genuine string, fail closed otherwise.
      if (typeof candidate !== "string") {
        throw new ReversalFailedError(this.keys.operationId);
      }
      restored = candidate;
    } catch {
      // §7/N2: the captured `restore` capability could throw a raw (PHI) message on a hostile REAL
      // handle — fail closed with a fixed-code error, never forward the raw throw to the display.
      this.failed = true;
      throw new ReversalFailedError(this.keys.operationId);
    }
    if (hasResidualSentinel(restored)) {
      // L6: a dangling/partial escape sentinel never completed into a literal — fail closed
      // rather than leak internal sentinel machinery to the display.
      this.failed = true;
      throw new ReversalFailedError(this.keys.operationId);
    }
    if (restored.length > 0) {
      await this.sink(restored as DisplayText);
    }
  }

  async abort(_reason: unknown): Promise<void> {
    // Release sensitive references and emit nothing buffered. Idempotent.
    this.failed = true;
    this.buffer = "";
  }

  private async emitPrefix(cut: number): Promise<void> {
    const settled = this.buffer.slice(0, cut);
    let reversed: string;
    try {
      reversed = await reverseText(
        settled,
        this.keys,
        this.store,
        this.grammar,
        this.policy,
      );
    } catch {
      // L4: latch — a reversal failure on an emitted prefix stops the stream for good. §7/N2: the
      // rejected error is NEVER forwarded (see end()); a fresh fixed-code error is thrown instead.
      this.failed = true;
      this.buffer = "";
      throw new ReversalFailedError(this.keys.operationId);
    }
    this.buffer = this.buffer.slice(cut);
    let restored: string;
    try {
      const candidate = this.restore(reversed);
      // §7/N2: the catch wraps only the CALL. A SUCCESSFUL non-string return whose `.includes` in
      // hasResidualSentinel below throws raw (PHI) must fail closed here — require a genuine string.
      if (typeof candidate !== "string") {
        throw new ReversalFailedError(this.keys.operationId);
      }
      restored = candidate;
    } catch {
      // §7/N2: a throw from the captured `restore` capability (hostile REAL handle) fails closed with
      // a fixed-code error, never a raw (PHI) message to the display.
      this.failed = true;
      this.buffer = "";
      throw new ReversalFailedError(this.keys.operationId);
    }
    if (hasResidualSentinel(restored)) {
      // L6: never emit a partial/dangling escape sentinel (defensive — settledBoundary already
      // withholds unclosed sentinels, but a mid-emit residual must still fail closed).
      this.failed = true;
      this.buffer = "";
      throw new ReversalFailedError(this.keys.operationId);
    }
    if (restored.length > 0) {
      await this.sink(restored as DisplayText);
    }
  }

  private async fail(): Promise<never> {
    // L4: latch — an overlong open token permanently stops the stream.
    this.failed = true;
    this.buffer = "";
    throw new ReversalFailedError(this.keys.operationId);
  }
}

/** Builds `M-1`-holdback reverse streams over the shared reversal boundary (L4). */
export class HoldbackReverseStreamFactory implements ReverseStreamFactory {
  create(input: {
    handle: ReversalHandle;
    store: ReversalStore;
    grammar: TokenGrammar;
    policy: TokenGrammarPolicy;
    sink: (safe: DisplayText) => void | Promise<void>;
  }): ReverseStream {
    // GLY-373 §3.2.2 — ENTRY POINT 3 of 3, and this path gains its FIRST structural validation.
    //
    // BASELINE CORRECTION: the claim that this path "already fails closed on a bad handle" is
    // FALSE. It read these scalars with `safeRead` and CAST them into `ReversalKeys` with no type
    // validation whatsoever; a forged handle yielded `undefined`/arbitrary values that were simply
    // carried into the keys. The comment reasoning about a "store miss" is not a guard: for text
    // containing NO MAPPED TOKENS the stream can complete successfully over a garbage key.
    //
    // SNAPSHOT ONCE, THEN VALIDATE, THEN BUILD. Each routing field is read exactly once into a
    // local BEFORE validation, and every downstream use reads only those locals — the bytes
    // validated are the exact bytes used to derive a key (MUT-30/MUT-31). The guard runs
    // SYNCHRONOUSLY here, before the `ReversalKeys` object is constructed and before any `push`;
    // deferring to `push`/`end` is MUT-25 and is NOT acceptable, because by then the keys have
    // been built from unvalidated input. Dropping only the well-formedness half is MUT-34, whose
    // vector is security-relevant and not cosmetic: `tenant\uD800` and `tenant\uFFFD` produce
    // DISTINCT JavaScript mapping keys but IDENTICAL `b64url-v1:` durable keys.
    const tenantId = safeRead(input.handle, "tenantId");
    const matterId = safeRead(input.handle, "matterId");
    const dictionaryVersion = safeRead(input.handle, "dictionaryVersion");
    // The RAW operation id, snapshotted ONCE. It is validated BELOW, BEFORE the slug filter runs.
    const rawOperationId = safeRead(input.handle, "operationId");

    // The guard error is the FIXED, PHI-FREE `MISSING_TRUSTED_CONTEXT` of §3.2.4 with the fixed
    // placeholder operation id — never this path's legacy `ReversalFailedError`, whose
    // own-enumerable `operationId` plus the SSN-admitting `SAFE_OPERATION_ID` slug filter would
    // turn a fail-closed branch into a fresh PHI-egress route (MUT-27). No handle scalar is echoed.
    //
    // SHAPE VALIDATION IS PART OF THE GUARD, not a downstream concern. The baseline CAST these
    // scalars into `ReversalKeys` with no type validation whatsoever, so a forged handle yielded
    // `undefined`/arbitrary values that were carried straight into the keys; `dictionaryVersion` in
    // particular is a branded BIGINT whose `toString` is called during key derivation, so a
    // non-bigint carrier is a raw-throw route.
    if (
      typeof tenantId !== "string" ||
      typeof matterId !== "string" ||
      typeof rawOperationId !== "string" ||
      typeof dictionaryVersion !== "bigint"
    ) {
      throw missingTrustedContextError();
    }
    // ORDER IS LOAD-BEARING. The §3.2.2 scan runs on the RAW operation id and runs BEFORE
    // `safeHandleOperationId`, which applies `SAFE_OPERATION_ID.test(...)`. Validating the
    // slug-FILTERED value instead — as an earlier revision did — was wrong twice over: a
    // NUL-bearing or lone-surrogate id silently became the `op-unknown` placeholder and was
    // ACCEPTED rather than rejected, and the regex ran on the rejected value first, parking the
    // ENTIRE subject string in the legacy globals `RegExp.input` / `RegExp.$_` — a process-global
    // slot no oracle on the thrown error can see. That is exactly the MUT-33(c) leak the
    // own-property scan exists to avoid. A rejected value now never reaches the regex at all.
    assertTrustedContextIdShape("tenantId", tenantId);
    assertTrustedContextIdShape("matterId", matterId);
    assertTrustedContextIdShape("operationId", rawOperationId);

    // §7/N2: only NOW shape-restrict the operation id, and restrict THE SNAPSHOT — never the
    // handle. `safeHandleOperationId` would read `input.handle.operationId` a SECOND time, and a
    // getter returning a benign slug on read 1 and PHI on read 2 defeats the validation above
    // outright: the bytes checked would not be the bytes used, and the slug regex would park the
    // second value in `RegExp.input` / `RegExp.$_`. Executed pre-fix at the public boundary:
    // `{"operationIdReads":2,"regexpInput":"123-45-6789"}`. Snapshot-once means snapshot once.
    const operationId = safeOperationIdOf(rawOperationId);
    const keys: ReversalKeys = {
      tenantId: tenantId as unknown as ReversalKeys["tenantId"],
      matterId: matterId as unknown as ReversalKeys["matterId"],
      dictionaryVersion:
        dictionaryVersion as unknown as ReversalKeys["dictionaryVersion"],
      operationId,
    };
    // L6: pull the escaped-literal restore off the handle (bounded capability, never raw
    // literal data) so streamed output restores source literals just like non-stream reversal.
    const restore = isInProcessReversalHandle(input.handle)
      ? (text: string): string =>
          (input.handle as InProcessReversalHandle).restoreEscapedLiterals(text)
      : IDENTITY_RESTORE;
    return new HoldbackReverseStream(
      keys,
      input.store,
      input.grammar,
      input.policy,
      input.sink,
      restore,
    );
  }
}
