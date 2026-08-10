import type { Utf16Offset } from "../core/brands";
import type {
  DetectedSpan,
  DetectorSpanNormalizer,
  RawDetectedSpan,
  SpanNormalizationResult,
} from "./ports";
import { splitsSurrogatePair } from "./offsets";

/**
 * Validates raw detector spans against the ORIGINAL UTF-16 text (CONTRACT-phase1 §3.3, L12).
 *
 * Fail-closed by construction: an out-of-range offset, a surrogate-splitting boundary, a
 * version mismatch, a duplicate span ID, or an overlap returns a typed rejection. It NEVER
 * clamps, guesses, reorders, or silently drops an invalid span — any one bad span rejects
 * the whole batch so a partially-trusted plan can never reach substitution.
 */
export class Utf16SpanNormalizer implements DetectorSpanNormalizer {
  normalize(
    originalText: string,
    expectedDetectorVersion: string,
    raw: readonly RawDetectedSpan[],
  ): SpanNormalizationResult {
    const length = originalText.length;
    const seenIds = new Set<string>();
    const spans: DetectedSpan[] = [];

    for (const span of raw) {
      if (span.detectorVersion !== expectedDetectorVersion) {
        return { ok: false, reason: "VERSION_MISMATCH" };
      }
      if (seenIds.has(span.id)) {
        return { ok: false, reason: "DUPLICATE_SPAN_ID" };
      }
      seenIds.add(span.id);

      // Only pre-normalized UTF-16 offsets are trusted here; any other encoding must have been
      // converted upstream. An unconverted encoding is treated as an invalid offset, not guessed.
      if (span.offsetEncoding !== "UTF16") {
        return { ok: false, reason: "OUT_OF_RANGE" };
      }
      if (!Number.isInteger(span.start) || !Number.isInteger(span.end)) {
        return { ok: false, reason: "OUT_OF_RANGE" };
      }
      if (span.start < 0 || span.end > length || span.start >= span.end) {
        return { ok: false, reason: "OUT_OF_RANGE" };
      }
      if (splitsSurrogatePair(originalText, span.start) || splitsSurrogatePair(originalText, span.end)) {
        return { ok: false, reason: "INVALID_BOUNDARY" };
      }

      spans.push({
        id: span.id,
        startUtf16: span.start as Utf16Offset,
        endUtf16: span.end as Utf16Offset,
        identifierClass: span.identifierClass,
        confidence: span.confidence,
        detectorVersion: span.detectorVersion,
      });
    }

    // Reject any overlap; dictionary precedence and leftmost-longest resolution happen in core,
    // never by silently coalescing detector spans here.
    const sorted = [...spans].sort((a, b) => a.startUtf16 - b.startUtf16);
    let previousEnd = -1;
    for (const span of sorted) {
      if (span.startUtf16 < previousEnd) {
        return { ok: false, reason: "OVERLAP" };
      }
      previousEnd = span.endUtf16;
    }

    return { ok: true, spans };
  }
}
