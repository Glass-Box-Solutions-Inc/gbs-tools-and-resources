/**
 * The opaque, immutable READY compiled dictionary (CONTRACT-phase1 §3.1.2, §7).
 *
 * A compiled dictionary is the cached Aho–Corasick automaton for one
 * `tenant + matter + dictionaryVersion + engineVersion + schemaVersion`, plus
 * the per-pattern metadata needed to turn a raw automaton hit into a
 * `DictionaryMatchCandidate` on ORIGINAL UTF-16 offsets. Expanded surface forms
 * and canonical case-truth values are never serialized or logged; `toJSON`
 * throws so the automaton cannot leak into a trace, job, or shared cache.
 *
 * `match` is pure boundary-agnostic candidate discovery. Distinctiveness,
 * citation, boundary, leftmost-longest, class precedence, and ambiguity
 * quarantine are the collision leaf's C1–C8 policy, applied by the caller.
 */
import type {
  DictionaryVersion,
  EngineVersion,
  MatterId,
  SchemaVersion,
  SubjectId,
  SubstitutionToken,
  TenantId,
} from "../core/brands";
import type {
  BoundaryMode,
  CompiledDictionary,
  DictionaryMatchCandidate,
  VariantCandidate,
  VariantSource,
} from "./contracts";
import { AhoCorasickAutomaton } from "./aho-corasick";
import { normalizeWithOffsets } from "./normalize";

/** Per-pattern metadata carried alongside the automaton (never serialized). */
export interface CompiledEntry {
  readonly patternId: number;
  readonly normalized: string;
  readonly subjectId: SubjectId;
  readonly token: SubstitutionToken;
  readonly identifierClass: VariantCandidate["identifierClass"];
  readonly source: VariantSource;
  readonly specificity: number;
  readonly suffixMode: "none" | "possessive";
  readonly boundaryMode: BoundaryMode;
  /** Current canonical display value of the subject, for reversal (N5). */
  readonly canonicalDisplayValue: string;
}

export interface CompiledDictionaryInit {
  readonly tenantId: TenantId;
  readonly matterId: MatterId;
  readonly dictionaryVersion: DictionaryVersion;
  readonly engineVersion: EngineVersion;
  readonly schemaVersion: SchemaVersion;
  readonly locale: string;
  readonly automaton: AhoCorasickAutomaton;
  readonly entries: readonly CompiledEntry[];
}

export class AhoCorasickCompiledDictionary implements CompiledDictionary {
  public readonly tenantId: TenantId;
  public readonly matterId: MatterId;
  public readonly dictionaryVersion: DictionaryVersion;
  public readonly engineVersion: EngineVersion;
  public readonly schemaVersion: SchemaVersion;
  public readonly status = "READY" as const;

  private readonly locale: string;
  private readonly automaton: AhoCorasickAutomaton;
  private readonly entriesById: ReadonlyMap<number, CompiledEntry>;
  private readonly canonicalByToken: ReadonlyMap<string, string>;

  public constructor(init: CompiledDictionaryInit) {
    this.tenantId = init.tenantId;
    this.matterId = init.matterId;
    this.dictionaryVersion = init.dictionaryVersion;
    this.engineVersion = init.engineVersion;
    this.schemaVersion = init.schemaVersion;
    this.locale = init.locale;
    this.automaton = init.automaton;

    const byId = new Map<number, CompiledEntry>();
    const byToken = new Map<string, string>();
    for (const entry of init.entries) {
      byId.set(entry.patternId, entry);
      // Token identity is 1:1 with a subject+role; canonical is the subject's.
      byToken.set(
        entry.token as unknown as string,
        entry.canonicalDisplayValue,
      );
    }
    this.entriesById = byId;
    this.canonicalByToken = byToken;
  }

  /** Number of compiled patterns; used only by tests/metrics, never egress. */
  public get patternCount(): number {
    return this.automaton.patternCount;
  }

  /** Current canonical value for an assigned token, or null when unknown. */
  public canonicalForToken(token: string): string | null {
    return this.canonicalByToken.get(token) ?? null;
  }

  public match(originalText: string): readonly DictionaryMatchCandidate[] {
    const offsetMap = normalizeWithOffsets(originalText, this.locale);
    const out: DictionaryMatchCandidate[] = [];
    for (const hit of this.automaton.match(offsetMap.normalized)) {
      const normalizedStart = hit.end - hit.length;
      const span = offsetMap.toOriginalSpan(normalizedStart, hit.end);
      if (span === null) continue; // C8: must land exactly on original boundaries.
      const entry = this.entriesById.get(hit.patternId);
      if (entry === undefined) continue;
      const start = span.startUtf16 as unknown as number;
      const end = span.endUtf16 as unknown as number;
      const candidate: VariantCandidate = {
        normalized: entry.normalized,
        matchText: originalText.slice(start, end),
        identifierClass: entry.identifierClass,
        subjectId: entry.subjectId,
        token: entry.token,
        source: entry.source,
        specificity: entry.specificity,
        suffixMode: entry.suffixMode,
        boundaryMode: entry.boundaryMode,
      };
      out.push({
        startUtf16: span.startUtf16,
        endUtf16: span.endUtf16,
        candidate,
      });
    }
    return out;
  }

  /** The automaton is an in-process capability, never a serializable payload. */
  public toJSON(): never {
    throw new Error("compiled_dictionary_not_serializable");
  }
}
