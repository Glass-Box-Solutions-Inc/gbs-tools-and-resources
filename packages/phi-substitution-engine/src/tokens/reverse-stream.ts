import type { DisplayText, TokenizedText } from "../core/brands";
import type { ReversalHandle, ReversalStore, ReverseStream } from "../core/contracts";
import type {
  ReverseStreamFactory,
  TokenGrammar,
  TokenGrammarPolicy,
} from "./ports";
import { ReversalFailedError } from "./errors";
import { reverseText, type ReversalKeys, InProcessReversalHandle } from "./reversal";
import { SENTINEL_OPEN, SENTINEL_CLOSE } from "./escaper";

const OPEN = "[[";
const CLOSE = "]]";
const OPEN_BRACKET = 0x5b; // "["

/** Identity restore used when the handle carries no escaped source literals. */
const IDENTITY_RESTORE = (text: string): string => text;

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
function withholdFromSpans(buffer: string, cut: number, open: string, close: string): number {
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
    if (isHighSurrogate(buffer.charCodeAt(cut - 1)) && isLowSurrogate(buffer.charCodeAt(cut))) {
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
function openTokenIsOverlong(buffer: string, policy: TokenGrammarPolicy): boolean {
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
      reversed = await reverseText(this.buffer, this.keys, this.store, this.grammar, this.policy);
    } catch (error) {
      // L4: latch — no later push/end may resume or complete after a reversal failure.
      this.failed = true;
      this.buffer = "";
      throw error instanceof Error ? error : new ReversalFailedError(this.keys.operationId);
    }
    this.buffer = "";
    const restored = this.restore(reversed);
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
      reversed = await reverseText(settled, this.keys, this.store, this.grammar, this.policy);
    } catch (error) {
      // L4: latch — a reversal failure on an emitted prefix stops the stream for good.
      this.failed = true;
      this.buffer = "";
      throw error instanceof Error ? error : new ReversalFailedError(this.keys.operationId);
    }
    this.buffer = this.buffer.slice(cut);
    const restored = this.restore(reversed);
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
    const keys: ReversalKeys = {
      tenantId: input.handle.tenantId,
      matterId: input.handle.matterId,
      dictionaryVersion: input.handle.dictionaryVersion,
      operationId: input.handle.operationId,
    };
    // L6: pull the escaped-literal restore off the handle (bounded capability, never raw
    // literal data) so streamed output restores source literals just like non-stream reversal.
    const restore =
      input.handle instanceof InProcessReversalHandle
        ? (text: string): string => (input.handle as InProcessReversalHandle).restoreEscapedLiterals(text)
        : IDENTITY_RESTORE;
    return new HoldbackReverseStream(keys, input.store, input.grammar, input.policy, input.sink, restore);
  }
}
