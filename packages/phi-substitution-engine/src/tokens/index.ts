import type { TokenRole } from "../core/brands";
import type { ReversalWriteStore } from "../core/contracts";
import type {
  ReverseStreamFactory,
  SourceTokenEscaper,
  TokenAssignmentStore,
  TokenGrammar,
  TokenGrammarPolicy,
  TokenReverser,
} from "./ports";
import { BracketTokenGrammar, frozenRoleSet } from "./grammar";
import { InMemoryTokenAssignmentStore } from "./assignment-store";
import { SentinelSourceTokenEscaper } from "./escaper";
import {
  AtomicTokenReverser,
  InMemoryReversalStore,
  InProcessReversalHandle,
} from "./reversal";
import { HoldbackReverseStreamFactory } from "./reverse-stream";

export { BracketTokenGrammar, frozenRoleSet, type TokenSpanParse } from "./grammar";
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

// L2.4 durable reversal store (GLY-337) — the §6 productionization of the reversal WRITE seam.
// Internal surface (deep-importable); the capability-tight public root exposes only the port types.
export {
  DurableReversalStore,
  InMemoryKeyProvider,
  InMemoryReversalSpoolBackend,
  InMemoryReversalSpoolVolume,
  buildReversalAad,
  MATTER_EXPIRES_AT,
  mappingKeyOf,
  idempotencyKeyOf,
  scopeDigestOf,
  dekGenerationIdOf,
  dekBindingDigestOf,
  gcmEncrypt,
  gcmDecrypt,
  bytesEqual,
  DEK_BYTES,
} from "./durable/index";

function role(value: string): TokenRole {
  return value as TokenRole;
}

/**
 * Phase-1 grammar policy. Roles are the trusted allow-list; the length and
 * sequence caps bound the `[[Role[_N]]]` shape (and therefore the streaming
 * holdback) for every token surface.
 *
 * §7/N2 (GLY-336 gate, finding 2): DEEP-FROZEN. The role allow-list is the trusted,
 * PHI-free set of structural roles; freezing the policy object AND the role Set makes
 * it immutable so no caller can inject a PHI-bearing role that would make the grammar
 * emit `[[John Smith]]`. The factories never accept a caller-supplied token policy.
 */
export const DEFAULT_TOKEN_GRAMMAR_POLICY: TokenGrammarPolicy = Object.freeze({
  allowedRoles: frozenRoleSet([
    role("Claimant"),
    role("Witness"),
    role("Treating_Physician"),
    role("Adjuster"),
    role("Employer"),
  ]),
  maximumTokenUtf16Length: 64,
  maximumRoleUtf16Length: 48,
  maximumSequence: 9999,
});

/**
 * Assembled token/escape/reversal module over one grammar policy. Fields are typed as the
 * frozen PORT INTERFACES (not the concrete classes) so a `createTokensModule` consumer receives
 * an interface-typed surface — the reversal store is the bounded `ReversalWriteStore`, never a
 * reflectable concrete store (§7/N2 / GLY-336 gate finding 1/7).
 */
export interface TokensModule {
  readonly policy: TokenGrammarPolicy;
  readonly grammar: TokenGrammar;
  readonly assignmentStore: TokenAssignmentStore;
  readonly escaper: SourceTokenEscaper;
  readonly reversalStore: ReversalWriteStore;
  readonly reverser: TokenReverser;
  readonly streamFactory: ReverseStreamFactory;
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
