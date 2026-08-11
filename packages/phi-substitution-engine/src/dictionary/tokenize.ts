/**
 * Match-time composition (CONTRACT-phase1 §4.1 steps 6–8, §5 L3/L9/L12).
 *
 * `getOrCompile` is the warm-cache serving path: a warm dictionary is reused, so
 * identical calls never rebuild the automaton (invariant L9). `tokenize` runs
 * the cached Aho–Corasick matcher, then delegates the C1–C8 collision policy —
 * boundary, distinctiveness, citation, leftmost-longest, class precedence,
 * ambiguity quarantine, and dictionary-over-detector precedence (L12) — to the
 * collision leaf's resolver. Dictionary matches ALWAYS override overlapping
 * detector spans; a detector-only span keeps its own operation token. The final
 * splice order is by ascending original offset, so output is independent of
 * candidate discovery order (L3).
 */
import type { Utf16Offset } from "../core/brands";
import type { IdentifierClass } from "../core/contracts";
import type { CompiledDictionaryCache, CompileInput, DictionaryCompiler } from "./contracts";
import type { DetectorCollisionSpan } from "../collision/index";
import {
  Phase1BoundaryRule,
  Phase1CitationRule,
  Phase1CollisionResolver,
  Phase1DistinctivenessRule,
  canonicalize,
} from "../collision/index";
import { AhoCorasickCompiledDictionary } from "./compiled-dictionary";
import { AMBIGUOUS_KNOWN_IDENTIFIER, DictionaryError } from "./errors";

const resolver = new Phase1CollisionResolver(
  new Phase1BoundaryRule(),
  new Phase1DistinctivenessRule(),
  new Phase1CitationRule(),
);

const DETECTOR_ROLE: Readonly<Record<IdentifierClass, string>> = {
  PERSON_NAME: "Claimant",
  DOB: "DOB",
  SSN: "SSN",
  MRN: "MRN",
  DEA: "DEA",
  EMAIL: "EMAIL",
  PHONE: "PHONE",
  ADDRESS: "ADDRESS",
  CLAIM_NUMBER: "CLAIM",
  POLICY_NUMBER: "POLICY",
  ACCOUNT_NUMBER: "ACCOUNT",
  OTHER_TAGGED: "OTHER",
};

export interface DetectorSpanInput {
  readonly startUtf16: number;
  readonly endUtf16: number;
  readonly identifierClass: IdentifierClass;
  readonly confidence: number;
  /** Operation token already allocated for this detector-only span (§4.1 step 7). */
  readonly token: string;
}

export interface TokenizeResult {
  readonly tokenizedText: string;
  readonly reversedText: string;
}

interface SelectedSpan {
  readonly start: number;
  readonly end: number;
  readonly token: string;
  readonly canonical: string;
}

const num = (value: Utf16Offset): number => value as unknown as number;

function splice(
  originalText: string,
  ordered: readonly SelectedSpan[],
  pick: (span: SelectedSpan) => string,
): string {
  let out = "";
  let cursor = 0;
  for (const span of ordered) {
    out += originalText.slice(cursor, span.start) + pick(span);
    cursor = span.end;
  }
  return out + originalText.slice(cursor);
}

export function tokenize(
  dictionary: AhoCorasickCompiledDictionary,
  originalText: string,
  locale: string,
  detectorSpans: readonly DetectorSpanInput[] = [],
): TokenizeResult {
  // The compiled Aho–Corasick matcher is the sole source of dictionary spans.
  const dictionaryCandidates = dictionary.match(originalText);
  // Intrinsic index iteration (own-index + own-`length`), NEVER `Array.prototype.map` (§7/N2 / L12):
  // a hostile `map` override that dropped detector candidates would make a detected structured
  // identifier (e.g. an email) pass through untokenized and egress raw.
  const detectorCandidates: DetectorCollisionSpan[] = [];
  for (let i = 0; i < (detectorSpans as { length: number }).length; i += 1) {
    const span = detectorSpans[i]!;
    detectorCandidates[detectorCandidates.length] = {
      startUtf16: span.startUtf16 as Utf16Offset,
      endUtf16: span.endUtf16 as Utf16Offset,
      identifierClass: span.identifierClass,
      confidence: span.confidence,
    };
  }

  // L3/L12: the collision leaf applies C1–C8 and dictionary-over-detector
  // precedence over BOTH candidate sets in a fixed, order-independent way.
  const resolved = resolver.resolve({
    originalText,
    locale,
    dictionaryCandidates,
    detectorCandidates,
  });
  if (resolved.mustFailClosed) {
    throw new DictionaryError(AMBIGUOUS_KNOWN_IDENTIFIER, {
      ambiguityCount: resolved.quarantinedAmbiguities.length,
    });
  }

  const detectorTokenBySpan = new Map<string, string>();
  for (const span of detectorSpans) {
    detectorTokenBySpan.set(`${span.startUtf16}:${span.endUtf16}`, span.token);
  }

  const spans: SelectedSpan[] = [];
  for (const candidate of resolved.selectedDictionary) {
    const start = num(candidate.startUtf16);
    const end = num(candidate.endUtf16);
    const token = candidate.candidate.token as unknown as string;
    // N5: reverse to the subject's CURRENT canonical value.
    const canonical = dictionary.canonicalForToken(token) ?? canonicalize(originalText.slice(start, end));
    spans.push({ start, end, token, canonical });
  }
  for (const span of resolved.selectedDetector) {
    const start = num(span.startUtf16);
    const end = num(span.endUtf16);
    const token =
      detectorTokenBySpan.get(`${start}:${end}`) ?? `[[${DETECTOR_ROLE[span.identifierClass]}]]`;
    spans.push({ start, end, token, canonical: canonicalize(originalText.slice(start, end)) });
  }

  // Deterministic splice: ascending original offset, independent of entry order.
  const ordered = [...spans].sort((a, b) => a.start - b.start);
  return {
    tokenizedText: splice(originalText, ordered, (span) => span.token),
    reversedText: splice(originalText, ordered, (span) => span.canonical),
  };
}

/**
 * Warm-cache serving (L9): reuse the cached automaton when present; only a cold
 * key compiles and publishes. Skipping the cache read is exactly the recompile-
 * per-call regression the invariant forbids.
 */
export async function getOrCompile(
  cache: CompiledDictionaryCache,
  compiler: DictionaryCompiler,
  input: CompileInput,
): Promise<AhoCorasickCompiledDictionary> {
  const key = {
    tenantId: input.tenantId,
    matterId: input.matterId,
    dictionaryVersion: input.dictionaryVersion,
    engineVersion: input.engineVersion,
    schemaVersion: input.schemaVersion,
  };
  const cached = await cache.get(key);
  if (cached !== null) {
    return cached as AhoCorasickCompiledDictionary;
  }
  const built = await compiler.compile(input);
  await cache.publish(built);
  return built as AhoCorasickCompiledDictionary;
}
