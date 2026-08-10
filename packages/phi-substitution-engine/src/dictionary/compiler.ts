/**
 * The matter dictionary compiler (CONTRACT-phase1 §3.1.2, §5 L1/L3/L10).
 *
 * For one `tenant + matter + version + truth-revision` it:
 *   1. reads tagged case truth (via a `CaseTruthReader`);
 *   2. allocates a STABLE subject/role token per subject (via the tokens leaf);
 *   3. expands only ALLOW-LISTED, deterministic surface forms (via the variants
 *      leaf) — no fuzzy name, ambiguous date, or lossy identifier is invented;
 *   4. builds one immutable Aho–Corasick automaton over the folded forms.
 *
 * The C1–C8 distinctiveness/citation/collision policy is the collision leaf's;
 * it is applied at match time (see `tokenize`), not here. Token allocation runs
 * in a CANONICAL subject order so a fresh compile is byte-identical regardless
 * of the order case truth was read in (invariant L3).
 */
import type { DictionaryVersion, MatterId, TenantId } from "../core/brands";
import type { IdentifierClass } from "../core/contracts";
import type {
  BoundaryMode,
  CaseTruthReader,
  CompiledDictionary,
  CompileInput,
  DictionaryCompiler,
  TaggedValue,
  TokenAssignmentPort,
  VariantSource,
} from "./contracts";
import { AhoCorasickBuilder } from "./aho-corasick";
import { AhoCorasickCompiledDictionary, type CompiledEntry } from "./compiled-dictionary";
import { foldCached } from "./normalize";
import { createAssignmentPort } from "./token-port";
import {
  expandDateVariants,
  expandPersonNameVariants,
  type VariantExpansion,
} from "../variants/index";
import { dedupeInOrder } from "../variants/support";

function boundaryModeFor(identifierClass: IdentifierClass): BoundaryMode {
  switch (identifierClass) {
    case "PERSON_NAME":
      return "unicode_word";
    case "SSN":
    case "DOB":
      return "unicode_digit";
    default:
      return "structured";
  }
}

/** Only staff-approved and structurally-deterministic forms; never a guess. */
function expandForms(value: TaggedValue, locale: string): readonly string[] {
  const canonical = value.canonicalDisplayValue;
  const aliases = value.approvedAliases;
  let expansion: VariantExpansion | null = null;
  switch (value.field.expander) {
    case "person-name":
      expansion = expandPersonNameVariants({ canonical, approvedAliases: aliases, locale });
      break;
    case "date":
      expansion = expandDateVariants({ canonical, locale });
      break;
    default:
      expansion = null;
  }
  if (expansion !== null && expansion.errorCode === null && expansion.candidates.length > 0) {
    return expansion.candidates;
  }
  // Literal fallback: the exact trusted value plus any approved aliases. This is
  // still allow-listed and lossless — it never fabricates a partial form.
  return dedupeInOrder([canonical, ...aliases].filter((form) => form.trim().length > 0));
}

function sourceFor(form: string, value: TaggedValue): VariantSource {
  if (form === value.canonicalDisplayValue) return "canonical";
  if (value.approvedAliases.includes(form)) return "approved_alias";
  return "expanded";
}

/** Stable, total order over subjects so ordinal assignment is deterministic. */
function compareBySubject(a: TaggedValue, b: TaggedValue): number {
  const left = a.subjectId as unknown as string;
  const right = b.subjectId as unknown as string;
  if (left < right) return -1;
  if (left > right) return 1;
  return 0;
}

export class MatterDictionaryCompiler implements DictionaryCompiler {
  public constructor(
    private readonly truthReader: CaseTruthReader,
    private readonly assignmentPortFactory: () => TokenAssignmentPort = createAssignmentPort,
  ) {}

  public async compile(input: CompileInput): Promise<CompiledDictionary> {
    const locale = input.policy.locale as unknown as string;
    const values = await this.truthReader.readTaggedValues({
      tenantId: input.tenantId,
      matterId: input.matterId,
      dictionaryVersion: input.dictionaryVersion,
      sourceTruthRevision: input.sourceTruthRevision,
    });

    // L3 determinism: allocate ordinals in a canonical subject order so a fresh
    // rebuild is byte-identical regardless of the case-truth read order.
    const orderedValues = [...values].sort(compareBySubject);

    const assignmentPort = this.assignmentPortFactory();
    const builder = new AhoCorasickBuilder();
    const entries: CompiledEntry[] = [];

    for (const value of orderedValues) {
      const token = await assignmentPort.requireAssignment({
        tenantId: input.tenantId,
        matterId: input.matterId,
        subjectId: value.subjectId,
        role: value.field.tokenRole,
        dictionaryVersion: input.dictionaryVersion,
      });
      const identifierClass = value.field.identifierClass;
      const boundaryMode = boundaryModeFor(identifierClass);
      const seen = new Set<string>();
      for (const form of expandForms(value, locale)) {
        const normalized = foldCached(form, locale);
        if (normalized.length === 0 || seen.has(normalized)) continue;
        seen.add(normalized);
        const patternId = builder.add(normalized);
        entries.push({
          patternId,
          normalized,
          subjectId: value.subjectId,
          token,
          identifierClass,
          source: sourceFor(form, value),
          specificity: [...normalized].length,
          suffixMode: form.endsWith("'s") ? "possessive" : "none",
          boundaryMode,
          canonicalDisplayValue: value.canonicalDisplayValue,
        });
      }
    }

    const automaton = builder.build();
    return new AhoCorasickCompiledDictionary({
      tenantId: input.tenantId,
      matterId: input.matterId,
      dictionaryVersion: input.dictionaryVersion,
      engineVersion: input.engineVersion,
      schemaVersion: input.schemaVersion,
      locale,
      automaton,
      entries,
    });
  }
}

/** In-memory tagged-truth source keyed by tenant/matter/version/revision. */
export class InMemoryCaseTruthReader implements CaseTruthReader {
  private readonly byKey = new Map<string, readonly TaggedValue[]>();

  private key(input: Readonly<{
    tenantId: TenantId;
    matterId: MatterId;
    dictionaryVersion: DictionaryVersion;
    sourceTruthRevision: string;
  }>): string {
    return [
      input.tenantId,
      input.matterId,
      String(input.dictionaryVersion),
      input.sourceTruthRevision,
    ].join(" ");
  }

  public set(
    input: Readonly<{
      tenantId: TenantId;
      matterId: MatterId;
      dictionaryVersion: DictionaryVersion;
      sourceTruthRevision: string;
    }>,
    values: readonly TaggedValue[],
  ): void {
    this.byKey.set(this.key(input), values);
  }

  public readTaggedValues(input: Readonly<{
    tenantId: TenantId;
    matterId: MatterId;
    dictionaryVersion: DictionaryVersion;
    sourceTruthRevision: string;
  }>): Promise<readonly TaggedValue[]> {
    return Promise.resolve(this.byKey.get(this.key(input)) ?? []);
  }
}
