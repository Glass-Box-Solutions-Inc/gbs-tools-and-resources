import type { Utf16Offset } from "../core/brands";
import type {
  DetectedSpan,
  DetectorSpanNormalizer,
  RawDetectedSpan,
  SpanNormalizationResult,
} from "./ports";
import { splitsSurrogatePair } from "./offsets";
import { intrinsicCopy, safeRead, safeString } from "../core/boundary-snapshot";

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

    // §7/N2 / L12: `raw` comes from an INJECTED detector port — read it ONCE by own index/length and
    // read EACH field ONCE, getter-throw-safe, into inert data. An OWN poisoned `Symbol.iterator`
    // must NOT be able to yield ZERO spans (a REQUIRED detector would then "succeed" with nothing and
    // its PHI would egress — a fail-OPEN); a non-array carrier and a throwing/mutating field getter
    // likewise fail closed here rather than pass through.
    const rawSpans = intrinsicCopy<RawDetectedSpan>(raw);
    if (rawSpans === null) {
      return { ok: false, reason: "OUT_OF_RANGE" };
    }
    for (let i = 0; i < rawSpans.length; i += 1) {
      const span = rawSpans[i];
      const detectorVersion = safeString(span, "detectorVersion");
      const id = safeString(span, "id");
      const offsetEncoding = safeString(span, "offsetEncoding");
      const start = safeRead(span, "start");
      const end = safeRead(span, "end");
      const identifierClass = safeRead(span, "identifierClass");
      const confidence = safeRead(span, "confidence");

      if (
        detectorVersion === undefined ||
        detectorVersion !== expectedDetectorVersion
      ) {
        return { ok: false, reason: "VERSION_MISMATCH" };
      }
      if (id === undefined) {
        return { ok: false, reason: "OUT_OF_RANGE" };
      }
      if (seenIds.has(id)) {
        return { ok: false, reason: "DUPLICATE_SPAN_ID" };
      }
      seenIds.add(id);

      // Only pre-normalized UTF-16 offsets are trusted here; any other encoding must have been
      // converted upstream. An unconverted encoding is treated as an invalid offset, not guessed.
      if (offsetEncoding !== "UTF16") {
        return { ok: false, reason: "OUT_OF_RANGE" };
      }
      if (
        typeof start !== "number" ||
        typeof end !== "number" ||
        !Number.isInteger(start) ||
        !Number.isInteger(end)
      ) {
        return { ok: false, reason: "OUT_OF_RANGE" };
      }
      if (start < 0 || end > length || start >= end) {
        return { ok: false, reason: "OUT_OF_RANGE" };
      }
      if (
        splitsSurrogatePair(originalText, start) ||
        splitsSurrogatePair(originalText, end)
      ) {
        return { ok: false, reason: "INVALID_BOUNDARY" };
      }

      spans.push({
        id,
        startUtf16: start as Utf16Offset,
        endUtf16: end as Utf16Offset,
        identifierClass: identifierClass as DetectedSpan["identifierClass"],
        confidence: confidence as DetectedSpan["confidence"],
        detectorVersion,
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
