import type {
  DictionaryVersion,
  MatterId,
  SubjectId,
  SubstitutionToken,
  TenantId,
  TokenRole,
} from "../core/brands";
import type { TokenAssignmentStore, TokenGrammar, TokenGrammarPolicy } from "./ports";

const SEP = String.fromCharCode(0);

interface IdentityInput {
  readonly tenantId: TenantId;
  readonly matterId: MatterId;
  readonly subjectId: SubjectId;
  readonly role: TokenRole;
  readonly dictionaryVersion: DictionaryVersion;
}

interface Assignment {
  readonly token: SubstitutionToken;
  readonly ordinal: number;
}

/**
 * In-memory token assignment (CONTRACT-phase1 L1, §3.3).
 *
 * Identity is `tenant + matter + subject + role` and is NEVER coalesced by
 * display text; the dictionary version is accepted but is deliberately not part
 * of the identity key, so a subject keeps its token across versions. Ordinals
 * are monotonic per `tenant + matter + role` and retired ordinals are never
 * reused.
 */
export class InMemoryTokenAssignmentStore implements TokenAssignmentStore {
  private readonly assigned = new Map<string, Assignment>();
  private readonly nextOrdinal = new Map<string, number>();
  private readonly retired = new Set<string>();

  constructor(
    private readonly grammar: TokenGrammar,
    private readonly policy: TokenGrammarPolicy,
  ) {}

  private identityKey(input: IdentityInput): string {
    return `${input.tenantId}${SEP}${input.matterId}${SEP}${input.subjectId}${SEP}${input.role}`;
  }

  private roleKey(input: IdentityInput): string {
    return `${input.tenantId}${SEP}${input.matterId}${SEP}${input.role}`;
  }

  private retiredKey(roleKey: string, ordinal: number): string {
    return `${roleKey}${SEP}${ordinal}`;
  }

  async getOrAllocate(input: IdentityInput): Promise<SubstitutionToken> {
    const identityKey = this.identityKey(input);
    const existing = this.assigned.get(identityKey);
    if (existing !== undefined) {
      // Stable across versions: identity is subject+role, not text and not version.
      return existing.token;
    }
    const roleKey = this.roleKey(input);
    let ordinal = this.nextOrdinal.get(roleKey) ?? 1;
    while (this.retired.has(this.retiredKey(roleKey, ordinal))) {
      ordinal += 1;
    }
    const token = this.grammar.format(input.role, ordinal === 1 ? null : ordinal, this.policy);
    this.nextOrdinal.set(roleKey, ordinal + 1);
    this.assigned.set(identityKey, { token, ordinal });
    return token;
  }

  async retire(input: IdentityInput): Promise<void> {
    const identityKey = this.identityKey(input);
    const existing = this.assigned.get(identityKey);
    if (existing === undefined) {
      return;
    }
    // The subject relinquishes its label and the ordinal is burned forever, so
    // no future subject can inherit the retired token.
    this.retired.add(this.retiredKey(this.roleKey(input), existing.ordinal));
    this.assigned.delete(identityKey);
  }
}
