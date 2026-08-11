/**
 * Phase-1 collision engine — the deterministic path from trusted known values
 * plus original text to a tokenized output, its reversal, and a fail-closed
 * ambiguity signal (invariants L3, L12).
 *
 * The engine wires the real normalizer, C1–C3 rules, structured detectors, and
 * the C1–C8 resolver. It does no probabilistic name inference: PERSON_NAME
 * spans come only from trusted known values; structured identifiers come only
 * from rigid-format detectors. Every substitution and reversal lands on
 * ORIGINAL UTF-16 offsets recovered through the normalizer's boundary map.
 */
import type { IdentifierClass } from "../core/contracts";
import type {
  BoundaryMode,
  DictionaryMatchCandidate,
  VariantCandidate,
} from "../dictionary/contracts";
import type { SubjectId, SubstitutionToken, Utf16Offset } from "../core/brands";
import type { DetectorCollisionSpan } from "./ports";
import { detectStructuredIdentifiers } from "./detectors";
import { canonicalize, fold, Phase1UnicodeNormalizer } from "./normalizer";
import {
  Phase1BoundaryRule,
  Phase1CitationRule,
  Phase1DistinctivenessRule,
} from "./rules";
import { Phase1CollisionResolver } from "./resolver";
import { intrinsicCopy, safeRead, safeString } from "../core/boundary-snapshot";

const AMBIGUOUS_KNOWN_IDENTIFIER = "AMBIGUOUS_KNOWN_IDENTIFIER";

const CLASS_ROLE: Readonly<Record<IdentifierClass, string>> = {
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

const asToken = (value: string): SubstitutionToken => value as unknown as SubstitutionToken;
const asSubject = (value: string): SubjectId => value as unknown as SubjectId;
const asUtf16 = (value: number): Utf16Offset => value as unknown as Utf16Offset;
const num = (value: Utf16Offset): number => value as unknown as number;

function tokenFor(identifierClass: IdentifierClass): SubstitutionToken {
  return asToken(`[[${CLASS_ROLE[identifierClass]}]]`);
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

export interface KnownValue {
  /** A literal trusted value (variant / surname / shared variant). */
  readonly literal?: string;
  /** A pre-normalized value matched directly against the NFKC-folded text. */
  readonly normalizedForm?: string;
  readonly identifierClass: IdentifierClass;
  readonly subjectId: string;
  /** Canonical display value for reversal; derived from the match when absent. */
  readonly canonicalDisplayValue?: string;
}

export interface CollisionInput {
  readonly originalText: string;
  readonly locale: string;
  readonly knownValues: readonly KnownValue[];
  readonly shuffleSeed?: number;
}

export interface CollisionResult {
  readonly tokenizedText: string | null;
  readonly reversedText: string | null;
  readonly candidates: readonly string[];
  readonly ambiguityCount: number;
  readonly errorCode: string | null;
}

interface SelectedSpan {
  readonly start: number;
  readonly end: number;
  readonly token: string;
  readonly canonical: string;
  readonly matchText: string;
}

const normalizer = new Phase1UnicodeNormalizer();
const resolver = new Phase1CollisionResolver(
  new Phase1BoundaryRule(),
  new Phase1DistinctivenessRule(),
  new Phase1CitationRule(),
);

function findAll(haystack: string, needle: string): number[] {
  const out: number[] = [];
  if (needle.length === 0) return out;
  let from = 0;
  for (;;) {
    const at = haystack.indexOf(needle, from);
    if (at < 0) break;
    out.push(at);
    from = at + needle.length;
  }
  return out;
}

/** mulberry32: deterministic PRNG so entry-order shuffles are reproducible per seed. */
function seededShuffle<T>(items: readonly T[], seed: number): T[] {
  const out = items.slice();
  let state = (seed >>> 0) || 0x9e3779b9;
  const next = (): number => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(next() * (i + 1));
    const a = out[i];
    const b = out[j];
    if (a !== undefined && b !== undefined) {
      out[i] = b;
      out[j] = a;
    }
  }
  return out;
}

export function runCollision(input: CollisionInput): CollisionResult {
  const { originalText, locale } = input;
  const offsetMap = normalizer.normalizeWithOffsets(originalText, locale);
  const normalizedText = offsetMap.normalized;

  const dictionaryCandidates: DictionaryMatchCandidate[] = [];
  const canonicalByKey = new Map<string, string>();

  // §7/N2 / L12: `knownValues` is caller-controlled boundary data — read the PARENT getter ONCE
  // getter-throw-safe, THEN copy by OWN index/length. A throwing `knownValues` getter, a NON-array
  // carrier, an OWN poisoned iterator, or a mutating getter (real array on the check read, then `[]`)
  // must NOT silently drop a known value that would then egress RAW, nor throw raw out of here.
  const knownValues = intrinsicCopy<KnownValue>(safeRead(input, "knownValues"));
  if (knownValues === null) {
    throw new Error("known_values_not_an_array");
  }
  for (let ki = 0; ki < knownValues.length; ki += 1) {
    const known = knownValues[ki]!;
    // §7/N2: read each element's key fields getter-throw-safe (a throwing `literal`/`normalizedForm`
    // getter must not propagate raw out of this boundary).
    const rawKey = safeString(known, "literal") ?? safeString(known, "normalizedForm");
    if (rawKey === undefined) continue;
    const foldedKey = fold(rawKey, locale);
    for (const normalizedStart of findAll(normalizedText, foldedKey)) {
      const normalizedEnd = normalizedStart + foldedKey.length;
      const originalSpan = offsetMap.toOriginalSpan(normalizedStart, normalizedEnd);
      if (originalSpan === null) continue; // C8: must land on original boundaries.
      const start = num(originalSpan.startUtf16);
      const end = num(originalSpan.endUtf16);
      const matchText = originalText.slice(start, end);
      const canonical = known.canonicalDisplayValue ?? canonicalize(matchText);
      const candidate: VariantCandidate = {
        normalized: foldedKey,
        matchText,
        identifierClass: known.identifierClass,
        subjectId: asSubject(known.subjectId),
        token: tokenFor(known.identifierClass),
        source: "canonical",
        specificity: [...foldedKey].length,
        suffixMode: "none",
        boundaryMode: boundaryModeFor(known.identifierClass),
      };
      dictionaryCandidates.push({
        startUtf16: originalSpan.startUtf16,
        endUtf16: originalSpan.endUtf16,
        candidate,
      });
      canonicalByKey.set(`${start}:${end}:dict:${known.subjectId}`, canonical);
    }
  }

  const detectorCandidates: DetectorCollisionSpan[] = [];
  for (const span of detectStructuredIdentifiers(originalText)) {
    detectorCandidates.push(span);
    const start = num(span.startUtf16);
    const end = num(span.endUtf16);
    canonicalByKey.set(`${start}:${end}:det`, canonicalize(originalText.slice(start, end)));
  }

  const orderedDict =
    input.shuffleSeed === undefined
      ? dictionaryCandidates
      : seededShuffle(dictionaryCandidates, input.shuffleSeed);
  const orderedDet =
    input.shuffleSeed === undefined
      ? detectorCandidates
      : seededShuffle(detectorCandidates, input.shuffleSeed ^ 0x5bd1e995);

  const resolved = resolver.resolve({
    originalText,
    locale,
    dictionaryCandidates: orderedDict,
    detectorCandidates: orderedDet,
  });

  if (resolved.mustFailClosed) {
    return {
      tokenizedText: null,
      reversedText: null,
      candidates: [],
      ambiguityCount: resolved.quarantinedAmbiguities.length,
      errorCode: AMBIGUOUS_KNOWN_IDENTIFIER,
    };
  }

  const selected: SelectedSpan[] = [];
  for (const candidate of resolved.selectedDictionary) {
    const start = num(candidate.startUtf16);
    const end = num(candidate.endUtf16);
    const subjectId = candidate.candidate.subjectId as unknown as string;
    selected.push({
      start,
      end,
      token: candidate.candidate.token as unknown as string,
      canonical:
        canonicalByKey.get(`${start}:${end}:dict:${subjectId}`) ??
        canonicalize(candidate.candidate.matchText),
      matchText: candidate.candidate.matchText,
    });
  }
  for (const span of resolved.selectedDetector) {
    const start = num(span.startUtf16);
    const end = num(span.endUtf16);
    const matchText = originalText.slice(start, end);
    selected.push({
      start,
      end,
      token: tokenFor(span.identifierClass) as unknown as string,
      canonical: canonicalByKey.get(`${start}:${end}:det`) ?? canonicalize(matchText),
      matchText,
    });
  }

  // C5 determinism: splice by ascending original offset, independent of entry order.
  const ordered = [...selected].sort((a, b) => a.start - b.start);

  const tokenizedText = spliceWith(originalText, ordered, (span) => span.token);
  const reversedText = spliceWith(originalText, ordered, (span) => span.canonical);

  return {
    tokenizedText,
    reversedText,
    candidates: ordered.map((span) => span.matchText),
    ambiguityCount: 0,
    errorCode: null,
  };
}

function spliceWith(
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
  out += originalText.slice(cursor);
  return out;
}

export { asUtf16 };
