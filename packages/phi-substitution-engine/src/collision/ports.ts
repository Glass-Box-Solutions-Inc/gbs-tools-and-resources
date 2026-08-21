import type { Utf16Offset } from "../core/brands";
import type { IdentifierClass } from "../core/contracts";
import type { DictionaryMatchCandidate } from "../dictionary/contracts";

export interface OriginalOffsetMap {
  readonly normalized: string;
  /** Returns null unless the normalized span maps exactly to valid original UTF-16 boundaries. */
  toOriginalSpan(
    startNormalized: number,
    endNormalized: number,
  ): Readonly<{
    startUtf16: Utf16Offset;
    endUtf16: Utf16Offset;
  }> | null;
}

export interface UnicodeNormalizer {
  /** NFKC + locale-approved case folding; no default diacritic stripping. */
  normalizeWithOffsets(original: string, locale: string): OriginalOffsetMap;
}

export interface BoundaryRule {
  accepts(originalText: string, candidate: DictionaryMatchCandidate): boolean;
}

export interface DistinctivenessRule {
  accepts(candidate: DictionaryMatchCandidate, locale: string): boolean;
}

export interface ValidatedCitationSpan {
  readonly startUtf16: Utf16Offset;
  readonly endUtf16: Utf16Offset;
  readonly kind: "PUBLISHED_CASE_CITATION";
}

export interface CitationRule {
  /** Requires adversarial party form, v./vs., reporter or tribunal marker, and citation/year structure. */
  validatedSpans(
    originalText: string,
    locale: string,
  ): readonly ValidatedCitationSpan[];
  /** True only for a PERSON_NAME surname candidate wholly inside a validated span. */
  suppresses(
    candidate: DictionaryMatchCandidate,
    spans: readonly ValidatedCitationSpan[],
  ): boolean;
}

export interface DetectorCollisionSpan {
  readonly startUtf16: Utf16Offset;
  readonly endUtf16: Utf16Offset;
  readonly identifierClass: IdentifierClass;
  readonly confidence: number;
}

export interface ResolvedCollisionSet {
  readonly selectedDictionary: readonly DictionaryMatchCandidate[];
  readonly selectedDetector: readonly DetectorCollisionSpan[];
  readonly quarantinedAmbiguities: readonly Readonly<{
    startUtf16: Utf16Offset;
    endUtf16: Utf16Offset;
    identifierClass: IdentifierClass;
    subjectCount: number;
  }>[];
  /** True when known raw bytes remain because equal-specificity subjects are ambiguous. */
  readonly mustFailClosed: boolean;
}

export interface CollisionResolver {
  /**
   * Applies C1–C8 in fixed order. Selection is leftmost-longest, specificity, then explicit
   * class precedence; dictionary spans always beat overlapping detector spans.
   */
  resolve(
    input: Readonly<{
      originalText: string;
      locale: string;
      dictionaryCandidates: readonly DictionaryMatchCandidate[];
      detectorCandidates: readonly DetectorCollisionSpan[];
    }>,
  ): ResolvedCollisionSet;
}
