/**
 * Deterministic Unicode normalization with an original-offset map (invariant L3, rule C8).
 *
 * Matching runs on an NFKC + locale-approved case-folded projection of the
 * source text, but every substitution and reversal must land on ORIGINAL
 * UTF-16 boundaries. The normalizer therefore groups each base code point with
 * its trailing combining marks, normalizes the group, and records a boundary
 * map from normalized offsets back to the original UTF-16 offsets. A normalized
 * span that does not begin and end exactly on original boundaries maps to
 * `null` and fails closed — it is never clamped or guessed.
 */
import type { Utf16Offset } from "../core/brands";
import type { OriginalOffsetMap, UnicodeNormalizer } from "./ports";

const COMBINING_MARK = /^\p{M}$/u;

const asUtf16 = (value: number): Utf16Offset => value as unknown as Utf16Offset;

interface NormalizationGroup {
  origStart: number;
  origEnd: number;
  folded: string;
}

class BoundaryOffsetMap implements OriginalOffsetMap {
  public readonly normalized: string;
  private readonly boundaryToOriginal: ReadonlyMap<number, number>;

  public constructor(
    normalized: string,
    boundaryToOriginal: ReadonlyMap<number, number>,
  ) {
    this.normalized = normalized;
    this.boundaryToOriginal = boundaryToOriginal;
  }

  public toOriginalSpan(
    startNormalized: number,
    endNormalized: number,
  ): Readonly<{ startUtf16: Utf16Offset; endUtf16: Utf16Offset }> | null {
    const start = this.boundaryToOriginal.get(startNormalized);
    const end = this.boundaryToOriginal.get(endNormalized);
    if (start === undefined || end === undefined || end < start) {
      return null;
    }
    return { startUtf16: asUtf16(start), endUtf16: asUtf16(end) };
  }
}

export class Phase1UnicodeNormalizer implements UnicodeNormalizer {
  public normalizeWithOffsets(
    original: string,
    locale: string,
  ): OriginalOffsetMap {
    const groups: NormalizationGroup[] = [];
    let utf16Offset = 0;

    for (const codePoint of original) {
      const width = codePoint.length;
      const isMark = COMBINING_MARK.test(codePoint);
      const last = groups[groups.length - 1];
      if (isMark && last !== undefined) {
        last.origEnd = utf16Offset + width;
        last.folded = fold(
          original.slice(last.origStart, last.origEnd),
          locale,
        );
      } else {
        groups.push({
          origStart: utf16Offset,
          origEnd: utf16Offset + width,
          folded: fold(codePoint, locale),
        });
      }
      utf16Offset += width;
    }

    let normalized = "";
    let normalizedOffset = 0;
    const boundaryToOriginal = new Map<number, number>();
    for (const group of groups) {
      boundaryToOriginal.set(normalizedOffset, group.origStart);
      normalized += group.folded;
      normalizedOffset += group.folded.length;
    }
    boundaryToOriginal.set(normalizedOffset, original.length);

    return new BoundaryOffsetMap(normalized, boundaryToOriginal);
  }
}

/** NFKC + locale-approved case folding. Diacritics are preserved, not stripped. */
export function fold(value: string, locale: string): string {
  return value.normalize("NFKC").toLocaleLowerCase(locale);
}

/** Canonical display value of an original span: NFKC, case preserved. */
export function canonicalize(value: string): string {
  return value.normalize("NFKC");
}
