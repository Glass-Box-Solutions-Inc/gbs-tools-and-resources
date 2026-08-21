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
import type { TokenRole, Utf16Offset } from "../core/brands";
import type { IdentifierClass } from "../core/contracts";
import type {
  CompiledDictionaryCache,
  CompileInput,
  DictionaryCompiler,
} from "./contracts";
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
import { safeRead, safeString, intrinsicCopy } from "../core/boundary-snapshot";
import { BracketTokenGrammar } from "../tokens/grammar";
import type { TokenGrammar, TokenGrammarPolicy } from "../tokens/ports";

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

/**
 * §7/N2 (sink a): the SUPERSET of every token role a legitimate allocator can emit — the detector
 * class roles (DETECTOR_ROLE) plus the person/role tokens. Every token about to be spliced into the
 * egressed output is validated against this policy (or a caller-supplied, equally-or-more-restrictive
 * one) BEFORE it can reach the output; a raw-PHI string, a non-string carrier, or a crafted non-role
 * bracket shape is never a "valid" token, so it can never egress. Deliberately a SUPERSET so a token
 * formatted under a NARROWER allocator policy (e.g. the 5-role person default) still validates. This
 * mirrors the boundary role registry; it MUST remain a superset of every role any allocator formats.
 */
const TOKENIZE_VALIDATION_POLICY: TokenGrammarPolicy = {
  allowedRoles: new Set<TokenRole>(
    [
      "Claimant",
      "Witness",
      "Treating_Physician",
      "Adjuster",
      "Employer",
      "Person",
      "DOB",
      "SSN",
      "MRN",
      "DEA",
      "EMAIL",
      "PHONE",
      "ADDRESS",
      "Address",
      "CLAIM",
      "POLICY",
      "ACCOUNT",
      "OTHER",
    ].map((r) => r as unknown as TokenRole),
  ),
  maximumTokenUtf16Length: 64,
  maximumRoleUtf16Length: 48,
  maximumSequence: 9999,
};

/** Trusted engine-internal grammar used to validate spliced tokens when a caller supplies none. */
const DEFAULT_VALIDATION_GRAMMAR: TokenGrammar = new BracketTokenGrammar();

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
  grammar: TokenGrammar = DEFAULT_VALIDATION_GRAMMAR,
  policy: TokenGrammarPolicy = TOKENIZE_VALIDATION_POLICY,
): TokenizeResult {
  // The compiled Aho–Corasick matcher is the sole source of dictionary spans.
  const dictionaryCandidates = dictionary.match(originalText);
  // §7/N2 / L12: `detectorSpans` is boundary data. Read EACH span's fields EXACTLY ONCE into an inert
  // snapshot here — a NON-array carrier or an OWN poisoned `Symbol.iterator` cannot hide spans, and a
  // mutating own-index/own-field getter cannot show a benign span to the collision resolver (the
  // candidate set) while feeding a DIFFERENT `token` to the splice map below. BOTH consumers read
  // only this snapshot, never the live `detectorSpans` array again.
  // Copy by OWN index/length FIRST: a NON-array carrier, an OWN poisoned `Symbol.iterator`, OR an own
  // index getter that THROWS (a genuine array can still carry `Object.defineProperty(arr, 0, {get})`)
  // all fail closed here rather than throwing raw out of this exported boundary.
  const rawSpans = intrinsicCopy<unknown>(detectorSpans);
  if (rawSpans === null) {
    throw new DictionaryError(AMBIGUOUS_KNOWN_IDENTIFIER, {
      ambiguityCount: 0,
    });
  }
  const detectorSpanSnapshot: {
    startUtf16: Utf16Offset;
    endUtf16: Utf16Offset;
    identifierClass: DetectorCollisionSpan["identifierClass"];
    confidence: DetectorCollisionSpan["confidence"];
    token: string;
  }[] = [];
  for (let i = 0; i < rawSpans.length; i += 1) {
    const span = rawSpans[i];
    // Every field is read ONCE, getter-throw-safe. A throwing/mutating field getter (e.g. a `token`
    // getter that throws PHI) fails closed with a fixed code here rather than propagating raw out of
    // this exported boundary; a non-numeric offset or non-string token is likewise rejected.
    const startUtf16 = safeRead(span, "startUtf16");
    const endUtf16 = safeRead(span, "endUtf16");
    const identifierClass = safeRead(span, "identifierClass");
    const confidence = safeRead(span, "confidence");
    const token = safeString(span, "token");
    if (
      typeof startUtf16 !== "number" ||
      typeof endUtf16 !== "number" ||
      token === undefined
    ) {
      throw new DictionaryError(AMBIGUOUS_KNOWN_IDENTIFIER, {
        ambiguityCount: 0,
      });
    }
    detectorSpanSnapshot[detectorSpanSnapshot.length] = {
      startUtf16: startUtf16 as Utf16Offset,
      endUtf16: endUtf16 as Utf16Offset,
      identifierClass:
        identifierClass as DetectorCollisionSpan["identifierClass"],
      confidence: confidence as DetectorCollisionSpan["confidence"],
      token,
    };
  }

  const detectorCandidates: DetectorCollisionSpan[] = [];
  for (let i = 0; i < detectorSpanSnapshot.length; i += 1) {
    const span = detectorSpanSnapshot[i]!;
    detectorCandidates[detectorCandidates.length] = {
      startUtf16: span.startUtf16,
      endUtf16: span.endUtf16,
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

  // The token map is built from the SAME inert snapshot the candidate set used, so the offsets and
  // the token can never diverge under a mutating boundary getter (§7/N2 / L12).
  const detectorTokenBySpan = new Map<string, string>();
  for (let i = 0; i < detectorSpanSnapshot.length; i += 1) {
    const span = detectorSpanSnapshot[i]!;
    detectorTokenBySpan.set(`${span.startUtf16}:${span.endUtf16}`, span.token);
  }

  const spans: SelectedSpan[] = [];
  for (const candidate of resolved.selectedDictionary) {
    const start = num(candidate.startUtf16);
    const end = num(candidate.endUtf16);
    const token = candidate.candidate.token as unknown as string;
    // N5: reverse to the subject's CURRENT canonical value.
    const canonical =
      dictionary.canonicalForToken(token) ??
      canonicalize(originalText.slice(start, end));
    spans.push({ start, end, token, canonical });
  }
  for (const span of resolved.selectedDetector) {
    const start = num(span.startUtf16);
    const end = num(span.endUtf16);
    const token =
      detectorTokenBySpan.get(`${start}:${end}`) ??
      `[[${DETECTOR_ROLE[span.identifierClass]}]]`;
    spans.push({
      start,
      end,
      token,
      canonical: canonicalize(originalText.slice(start, end)),
    });
  }

  // §7/N2 (sink a): EVERY token about to be spliced into the egressed `tokenizedText` must be a
  // genuine, grammar-VALID token. All three sources feeding `span.token` above are UNTRUSTED at this
  // boundary — a `detectorSpans[].token` from a direct caller, a `candidate.token` from an INJECTED
  // compiled dictionary's `match()` (a fabricated cache/compiler result), or the class fallback — so a
  // raw-PHI string, a non-string carrier, or a crafted non-role bracket shape that reached `span.token`
  // would otherwise splice straight into the output (and out through SubstitutionResult.segments[].text
  // / decideEgress egressText). A bracketed token can only carry an allow-listed role + numeric
  // sequence, structurally incapable of holding raw PHI. Validate at this single splice chokepoint;
  // anything not grammar-valid fails closed (contained by both callers as a fixed-code failure).
  for (const span of spans) {
    if (
      typeof span.token !== "string" ||
      grammar.parse(span.token, policy).kind !== "valid"
    ) {
      throw new DictionaryError(AMBIGUOUS_KNOWN_IDENTIFIER, {
        ambiguityCount: 0,
      });
    }
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
