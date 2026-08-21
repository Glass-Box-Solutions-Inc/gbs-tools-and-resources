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
import {
  AhoCorasickCompiledDictionary,
  type CompiledEntry,
} from "./compiled-dictionary";
import { foldCached } from "./normalize";
import { createAssignmentPort } from "./token-port";
import {
  expandDateVariants,
  expandPersonNameVariants,
  expandStructuredIdVariants,
  type StructuredIdPolicy,
  type StructuredSeparator,
  type VariantExpansion,
} from "../variants/index";
import { dedupeInOrder } from "../variants/support";
import { intrinsicCopy, safeRead } from "../core/boundary-snapshot";

const KNOWN_STRUCTURED_SEPARATORS: readonly StructuredSeparator[] = [
  "-",
  " ",
  "/",
  ".",
];

/** Parses the permitted-separator scalar (`field.options` is frozen to scalars) — a string whose
 *  characters are the allowed separators — into the policy's separator list. */
function parseSeparators(value: unknown): readonly StructuredSeparator[] {
  if (typeof value !== "string") return [];
  const out: StructuredSeparator[] = [];
  for (const ch of value) {
    if (
      (KNOWN_STRUCTURED_SEPARATORS as readonly string[]).includes(ch) &&
      !out.includes(ch as StructuredSeparator)
    ) {
      out.push(ch as StructuredSeparator);
    }
  }
  return out;
}

/**
 * Derives a structured-id class policy from the tagged field's frozen scalar `options`. When a
 * field carries no explicit separator allow-list, the class default is every standard separator:
 * a bounded, deterministic, NON-lossy set (separator swaps only, never a truncated/fuzzy form),
 * which is the allow-list L10 intends — not an invented guess.
 */
function structuredIdPolicyFromOptions(
  options: Readonly<Record<string, boolean | number | string>> | undefined,
): StructuredIdPolicy {
  const separators = parseSeparators(options?.["permittedSeparators"]);
  return {
    requiredAlphaPrefix:
      typeof options?.["requiredAlphaPrefix"] === "string"
        ? (options["requiredAlphaPrefix"] as string)
        : null,
    permittedSeparators:
      separators.length > 0 ? separators : KNOWN_STRUCTURED_SEPARATORS,
    allowCompactForm: options?.["allowCompactForm"] === true,
    minimumAlphanumericLength:
      typeof options?.["minimumAlphanumericLength"] === "number"
        ? (options["minimumAlphanumericLength"] as number)
        : 0,
  };
}

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
  // §7/N2 / L12: `approvedAliases` is boundary data (an injected CaseTruthReader's return). Read the
  // PARENT getter ONCE and DISTINGUISH three cases: GENUINELY-ABSENT (undefined/null → this subject has
  // no aliases → []), UNREADABLE (a throwing getter), and MALFORMED (a non-array, or an array with a
  // throwing own-index getter). Unreadable/malformed MUST FAIL CLOSED — silently defaulting to `[]`
  // would compile an INCOMPLETE dictionary and egress the omitted alias RAW to the trace/provider (a
  // fail-OPEN; this is exactly the regression an earlier `safeRead(...) ?? []` introduced). The throw
  // carries a FIXED, PHI-free message and is caught by the orchestrator's fail-closed try/catch
  // (→ DICTIONARY_UNAVAILABLE); a direct compiler caller likewise sees only the fixed message.
  let rawAliases: unknown;
  try {
    rawAliases = (value as { approvedAliases?: unknown }).approvedAliases;
  } catch {
    throw new Error("approved_aliases_unreadable");
  }
  let aliases: string[];
  if (rawAliases === undefined || rawAliases === null) {
    aliases = [];
  } else {
    const copied = intrinsicCopy<string>(rawAliases);
    if (copied === null) {
      throw new Error("approved_aliases_not_an_array");
    }
    aliases = copied;
  }
  let expansion: VariantExpansion | null = null;
  switch (value.field.expander) {
    case "person-name":
      expansion = expandPersonNameVariants({
        canonical,
        approvedAliases: aliases,
        locale,
      });
      break;
    case "date":
      expansion = expandDateVariants({ canonical, locale });
      break;
    case "structured-id":
    case "ssn":
      // Deterministic, allow-listed separator variants of the identifier (e.g. `CLM-00421` →
      // `CLM 00421`, `CLM/00421`). Previously these expanders were never invoked, so a permitted
      // separator variant of a tagged identifier egressed RAW to the provider (NEW-1).
      expansion = expandStructuredIdVariants({
        canonical,
        policy: structuredIdPolicyFromOptions(value.field.options),
      });
      break;
    default:
      expansion = null;
  }
  // The canonical value and approved aliases are ALWAYS substitutable — they are the trusted
  // truth. Expander candidates are ADDITIONAL deterministic forms merged on top; a policy that
  // omits the canonical's own separator can therefore never drop the canonical itself.
  const candidates =
    expansion !== null && expansion.errorCode === null
      ? expansion.candidates
      : [];
  return dedupeInOrder(
    [canonical, ...aliases, ...candidates].filter(
      (form) => form.trim().length > 0,
    ),
  );
}

function sourceFor(form: string, value: TaggedValue): VariantSource {
  if (form === value.canonicalDisplayValue) return "canonical";
  // §7/N2: read `approvedAliases` getter-throw-safe and match by OWN index (never `Array.prototype`
  // methods, which are ACE-overridable), so a throwing getter cannot propagate raw out of this label.
  const aliases = intrinsicCopy<string>(safeRead(value, "approvedAliases"));
  if (aliases !== null) {
    for (let i = 0; i < aliases.length; i += 1) {
      if (aliases[i] === form) return "approved_alias";
    }
  }
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

    // §7/N2 / L12: the CaseTruthReader is an injected port — its result is UNTRUSTED. A NON-array
    // carrier, a REAL array with an OWN poisoned `Symbol.iterator`, or a throwing element getter must
    // NOT silently compile an EMPTY dictionary (which would egress every known value RAW). `intrinsicCopy`
    // reads the array ONCE by own index/length, getter-throw-safe; a non-array or throwing element
    // fails closed here (caught upstream as DICTIONARY_UNAVAILABLE / zero egress).
    const materializedValues = intrinsicCopy<TaggedValue>(values);
    if (materializedValues === null) {
      throw new Error("case_truth_values_not_an_array");
    }

    // L3 determinism: allocate ordinals in a canonical subject order so a fresh
    // rebuild is byte-identical regardless of the case-truth read order.
    const orderedValues = materializedValues.sort(compareBySubject);

    const assignmentPort = this.assignmentPortFactory();
    const builder = new AhoCorasickBuilder();
    const entries: CompiledEntry[] = [];

    for (const value of orderedValues) {
      // #6 / L1: the composed engine reserves the NUL byte to fence the detector-only synthetic
      // subject namespace, and the assignment store joins key components with NUL. A tagged (real)
      // subject id carrying NUL would blur those boundaries and could share a token-assignment key
      // with a synthetic subject. Real subject ids are system-generated and NUL-free; enforce it
      // (fail closed) so the synthetic/real namespaces are PROVABLY disjoint, not merely assumed.
      if ((value.subjectId as unknown as string).includes("\u0000")) {
        throw new Error("subject_id_contains_reserved_nul");
      }
      const token = await assignmentPort.requireAssignment({
        tenantId: input.tenantId,
        matterId: input.matterId,
        subjectId: value.subjectId,
        role: value.field.tokenRole,
        dictionaryVersion: input.dictionaryVersion,
      });
      const identifierClass = value.field.identifierClass;
      const boundaryMode = boundaryModeFor(identifierClass);
      // Intra-value form dedup. Not required to be poison-resistant: a consumer that can
      // replace `Set.prototype.has` controls the realm and already holds this plaintext —
      // out of scope for N2 per CONTRACT/THREAT-MODEL.md (ratified GLY-336, 2026-08-12).
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
  // §7/N2 (GLY-336 gate): TRUE runtime-private (#). This map holds RAW tagged case-truth
  // (canonicalDisplayValue, approved aliases). A TS `private` field is still enumerable via
  // reflection, so the backing MUST be a #field — a returned reader instance never leaks values.
  readonly #byKey = new Map<string, readonly TaggedValue[]>();

  #key(
    input: Readonly<{
      tenantId: TenantId;
      matterId: MatterId;
      dictionaryVersion: DictionaryVersion;
      sourceTruthRevision: string;
    }>,
  ): string {
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
    this.#byKey.set(this.#key(input), values);
  }

  public readTaggedValues(
    input: Readonly<{
      tenantId: TenantId;
      matterId: MatterId;
      dictionaryVersion: DictionaryVersion;
      sourceTruthRevision: string;
    }>,
  ): Promise<readonly TaggedValue[]> {
    return Promise.resolve(this.#byKey.get(this.#key(input)) ?? []);
  }
}
