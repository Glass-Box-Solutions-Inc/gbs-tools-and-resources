/**
 * The fixed collision policy rules C1–C3 (invariant L3).
 *
 * C1 BoundaryRule       — a known value only matches on a Unicode boundary of
 *                         its own family; it never fires on a substring inside a
 *                         longer word or digit run.
 * C2 DistinctivenessRule — an indistinct standalone form (single character,
 *                         bare year, or a common/ambiguous lexicon word) is
 *                         rejected rather than substituted.
 * C3 CitationRule       — a claimant surname wholly inside a *validated*
 *                         published-case citation is suppressed; near-citations
 *                         do not suppress, and only PERSON_NAME is ever
 *                         suppressed inside a citation.
 */
import type { DictionaryMatchCandidate } from "../dictionary/contracts";
import type {
  BoundaryRule,
  CitationRule,
  DistinctivenessRule,
  ValidatedCitationSpan,
} from "./ports";
import type { Utf16Offset } from "../core/brands";

const LETTER = /\p{L}/u;
const MARK = /\p{M}/u;
const DIGIT = /\p{Nd}/u;
const BARE_YEAR = /^[12]\d{3}$/;

/**
 * Common / ambiguous standalone forms. Membership makes a single-token variant
 * indistinct as an identifier (C2). Distinct surnames such as "ann" or "garcia"
 * are deliberately absent.
 */
const AMBIGUOUS_LEXICON: ReadonlySet<string> = new Set([
  "january", "february", "march", "april", "may", "june",
  "july", "august", "september", "october", "november", "december",
  "will", "may", "can", "could", "would", "should", "shall", "must", "might",
  "met", "said", "and", "the", "in", "of", "to", "is", "are", "was", "were",
  "be", "been", "on", "at", "for", "with", "as", "by", "it", "he", "she",
  "they", "we", "you", "over", "filed", "appeared",
]);

/** Reads the code point ending at `offset` (the char immediately before a span). */
function codePointBefore(text: string, offset: number): string | null {
  if (offset <= 0) return null;
  const code = text.codePointAt(offset - 1);
  if (code === undefined) return null;
  // A low surrogate means the real code point starts one unit earlier.
  if (code >= 0xdc00 && code <= 0xdfff && offset - 2 >= 0) {
    const full = text.codePointAt(offset - 2);
    if (full !== undefined) return String.fromCodePoint(full);
  }
  return String.fromCodePoint(code);
}

function codePointAt(text: string, offset: number): string | null {
  if (offset >= text.length) return null;
  const code = text.codePointAt(offset);
  if (code === undefined) return null;
  return String.fromCodePoint(code);
}

function isWordChar(ch: string | null): boolean {
  return ch !== null && (LETTER.test(ch) || MARK.test(ch));
}

function isDigitChar(ch: string | null): boolean {
  return ch !== null && DIGIT.test(ch);
}

function isAlnumChar(ch: string | null): boolean {
  return ch !== null && (LETTER.test(ch) || DIGIT.test(ch) || MARK.test(ch));
}

export class Phase1BoundaryRule implements BoundaryRule {
  public accepts(originalText: string, candidate: DictionaryMatchCandidate): boolean {
    const start = candidate.startUtf16 as unknown as number;
    const end = candidate.endUtf16 as unknown as number;
    const before = codePointBefore(originalText, start);
    const after = codePointAt(originalText, end);

    switch (candidate.candidate.boundaryMode) {
      case "unicode_word":
        return !isWordChar(before) && !isWordChar(after);
      case "unicode_digit":
        return !isDigitChar(before) && !isDigitChar(after);
      case "structured":
        return !isAlnumChar(before) && !isAlnumChar(after);
      default:
        return false;
    }
  }
}

export class Phase1DistinctivenessRule implements DistinctivenessRule {
  public accepts(candidate: DictionaryMatchCandidate, _locale: string): boolean {
    const normalized = candidate.candidate.normalized.trim();
    if ([...normalized].length <= 1) return false;
    if (BARE_YEAR.test(normalized)) return false;
    if (AMBIGUOUS_LEXICON.has(normalized)) return false;
    return true;
  }
}

/**
 * A validated published-case citation requires, in order: an adversarial party
 * form, a `v.`/`vs.` connective, a reporter or tribunal marker, and a
 * parenthesized year. All four must be present; a near-citation is not enough.
 */
const CITATION = new RegExp(
  [
    "\\b[A-Z][\\w'’.\\-]*(?:\\s+[A-Z][\\w'’.\\-]*)*", // party A (capitalized)
    "\\s+vs?\\.\\s+", // v. / vs.
    "[A-Za-z][\\w'’.\\-]*(?:[,]?\\s+[A-Za-z0-9'’.\\-]+)*?", // party B / reporter
    "\\s*\\(\\d{4}\\)", // (YYYY)
  ].join(""),
  "gu",
);

/** An all-caps abbreviation (WCAB, US, F3d) marks a reporter/tribunal. */
const TRIBUNAL_MARKER = /\b[A-Z]{2,}\b/;

const asUtf16 = (value: number): Utf16Offset => value as unknown as Utf16Offset;

export class Phase1CitationRule implements CitationRule {
  public validatedSpans(originalText: string, _locale: string): readonly ValidatedCitationSpan[] {
    const spans: ValidatedCitationSpan[] = [];
    CITATION.lastIndex = 0;
    let match: RegExpExecArray | null;
    while ((match = CITATION.exec(originalText)) !== null) {
      const text = match[0];
      if (!TRIBUNAL_MARKER.test(text)) continue;
      spans.push({
        startUtf16: asUtf16(match.index),
        endUtf16: asUtf16(match.index + text.length),
        kind: "PUBLISHED_CASE_CITATION",
      });
    }
    return spans;
  }

  public suppresses(
    candidate: DictionaryMatchCandidate,
    spans: readonly ValidatedCitationSpan[],
  ): boolean {
    if (candidate.candidate.identifierClass !== "PERSON_NAME") return false;
    const start = candidate.startUtf16 as unknown as number;
    const end = candidate.endUtf16 as unknown as number;
    for (const span of spans) {
      const spanStart = span.startUtf16 as unknown as number;
      const spanEnd = span.endUtf16 as unknown as number;
      if (start >= spanStart && end <= spanEnd) return true;
    }
    return false;
  }
}
