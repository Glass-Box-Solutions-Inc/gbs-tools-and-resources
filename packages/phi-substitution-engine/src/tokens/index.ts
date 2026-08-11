import type { TokenRole } from "../core/brands";
import type { TokenGrammarPolicy } from "./ports";
import { BracketTokenGrammar } from "./grammar";
import { InMemoryTokenAssignmentStore } from "./assignment-store";
import { SentinelSourceTokenEscaper } from "./escaper";
import {
  AtomicTokenReverser,
  InMemoryReversalStore,
  InProcessReversalHandle,
} from "./reversal";
import { HoldbackReverseStreamFactory } from "./reverse-stream";

export { BracketTokenGrammar, type TokenSpanParse } from "./grammar";
export { InMemoryTokenAssignmentStore } from "./assignment-store";
export { SentinelSourceTokenEscaper, SENTINEL_OPEN, SENTINEL_CLOSE } from "./escaper";
export {
  AtomicTokenReverser,
  InMemoryReversalStore,
  InProcessReversalHandle,
  isInProcessReversalHandle,
  reverseText,
  type ReversalKeys,
} from "./reversal";
export { HoldbackReverseStreamFactory } from "./reverse-stream";
export {
  ReversalFailedError,
  ReversalHandleNotSerializableError,
  REVERSAL_FAILED,
  DIAG_REVERSAL_HANDLE_NOT_SERIALIZABLE,
} from "./errors";

function role(value: string): TokenRole {
  return value as TokenRole;
}

/**
 * Phase-1 grammar policy. Roles are the trusted allow-list; the length and
 * sequence caps bound the `[[Role[_N]]]` shape (and therefore the streaming
 * holdback) for every token surface.
 */
export const DEFAULT_TOKEN_GRAMMAR_POLICY: TokenGrammarPolicy = {
  allowedRoles: new Set<TokenRole>([
    role("Claimant"),
    role("Witness"),
    role("Treating_Physician"),
    role("Adjuster"),
    role("Employer"),
  ]),
  maximumTokenUtf16Length: 64,
  maximumRoleUtf16Length: 48,
  maximumSequence: 9999,
};

/** Assembled token/escape/reversal module over one grammar policy. */
export interface TokensModule {
  readonly policy: TokenGrammarPolicy;
  readonly grammar: BracketTokenGrammar;
  readonly assignmentStore: InMemoryTokenAssignmentStore;
  readonly escaper: SentinelSourceTokenEscaper;
  readonly reversalStore: InMemoryReversalStore;
  readonly reverser: AtomicTokenReverser;
  readonly streamFactory: HoldbackReverseStreamFactory;
}

export function createTokensModule(
  policy: TokenGrammarPolicy = DEFAULT_TOKEN_GRAMMAR_POLICY,
): TokensModule {
  const grammar = new BracketTokenGrammar();
  const reversalStore = new InMemoryReversalStore();
  return {
    policy,
    grammar,
    assignmentStore: new InMemoryTokenAssignmentStore(grammar, policy),
    escaper: new SentinelSourceTokenEscaper(grammar),
    reversalStore,
    reverser: new AtomicTokenReverser(reversalStore, grammar, policy),
    streamFactory: new HoldbackReverseStreamFactory(),
  };
}
