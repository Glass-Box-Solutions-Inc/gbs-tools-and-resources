/**
 * Adapter from the dictionary compiler's `TokenAssignmentPort` onto the real
 * tokens leaf (CONTRACT-phase1 §3.1.2, §3.3, invariant L1).
 *
 * Stable subject/role token identity is owned by the tokens module; the
 * compiler never re-invents it. Identity is `tenant + matter + subject + role`
 * and is deliberately independent of the dictionary version and of display
 * text, so a subject keeps its token across versions and equal spellings under
 * distinct identities never coalesce.
 */
import type {
  DictionaryVersion,
  MatterId,
  SubjectId,
  SubstitutionToken,
  TenantId,
  TokenRole,
} from "../core/brands";
import type {
  TokenAssignmentStore,
  TokenGrammar,
  TokenGrammarPolicy,
} from "../tokens/ports";
import type { TokenAssignmentPort } from "./contracts";
import {
  createTokensModule,
  DEFAULT_TOKEN_GRAMMAR_POLICY,
} from "../tokens/index";

export class TokensLeafAssignmentPort implements TokenAssignmentPort {
  public constructor(
    private readonly store: TokenAssignmentStore,
    private readonly grammar: TokenGrammar,
    private readonly policy: TokenGrammarPolicy,
  ) {}

  public async requireAssignment(
    input: Readonly<{
      tenantId: TenantId;
      matterId: MatterId;
      subjectId: SubjectId;
      role: TokenRole;
      dictionaryVersion: DictionaryVersion;
    }>,
  ): Promise<SubstitutionToken> {
    let candidate: unknown;
    try {
      candidate = await this.store.getOrAllocate(input);
    } catch {
      throw new Error("token_assignment_unavailable");
    }

    if (typeof candidate !== "string") {
      throw new Error("token_assignment_unavailable");
    }

    let parsed: ReturnType<TokenGrammar["parse"]>;
    try {
      parsed = this.grammar.parse(candidate, this.policy);
    } catch {
      throw new Error("token_assignment_unavailable");
    }
    if (parsed.kind !== "valid" || parsed.role !== input.role) {
      throw new Error("token_assignment_unavailable");
    }
    return parsed.token;
  }
}

/** A fresh token module + port, so a compile never shares assignment state. */
export function createAssignmentPort(): TokensLeafAssignmentPort {
  const module = createTokensModule(DEFAULT_TOKEN_GRAMMAR_POLICY);
  return new TokensLeafAssignmentPort(
    module.assignmentStore,
    module.grammar,
    module.policy,
  );
}
