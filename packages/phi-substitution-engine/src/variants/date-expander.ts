import type { VariantExpansion, VariantRejectionCode } from "./types";
import { dedupeInOrder } from "./support";

export interface DateVariantRequest {
  readonly canonical: string;
  readonly locale: string | null;
}

/** Locales that read a two-small-component numeric date as month-first. */
const MONTH_FIRST_LOCALES: ReadonlySet<string> = new Set(["en-US", "en-CA"]);
/** Locales that read a two-small-component numeric date as day-first. */
const DAY_FIRST_LOCALES: ReadonlySet<string> = new Set([
  "en-GB",
  "es-MX",
  "es-ES",
  "fr-FR",
  "de-DE",
]);

const MAX_DAY_BY_MONTH: readonly number[] = [
  31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31,
];

function pad2(value: number): string {
  return value < 10 ? `0${value}` : `${value}`;
}

function isValidCalendarDay(month: number, day: number): boolean {
  if (day < 1) return false;
  const max = MAX_DAY_BY_MONTH[month - 1];
  if (max === undefined) return false;
  return day <= max;
}

/**
 * Expands a full numeric date into a single canonical ISO form. A date whose
 * first two components could each be a month is genuinely ambiguous; without a
 * known locale to fix the order we reject it with AMBIGUOUS_LOCALE rather than
 * guess either interpretation. Partial or non-calendar inputs are rejected too.
 */
export function expandDateVariants(request: DateVariantRequest): VariantExpansion {
  const trimmed = request.canonical.trim();
  const parsed = /^(\d{1,2})([/.-])(\d{1,2})\2(\d{4})$/.exec(trimmed);
  if (parsed === null) {
    return { candidates: [], errorCode: "UNSUPPORTED_FORMAT" };
  }

  const first = Number(parsed[1]);
  const second = Number(parsed[3]);
  const year = Number(parsed[4]);
  if (!Number.isInteger(first) || !Number.isInteger(second) || !Number.isInteger(year)) {
    return { candidates: [], errorCode: "UNSUPPORTED_FORMAT" };
  }

  const firstCouldBeMonth = first >= 1 && first <= 12;
  const secondCouldBeMonth = second >= 1 && second <= 12;

  let month: number;
  let day: number;

  if (firstCouldBeMonth && secondCouldBeMonth && first !== second) {
    // Genuinely ambiguous: each ordering yields a different valid-looking date.
    const locale = request.locale;
    if (locale !== null && MONTH_FIRST_LOCALES.has(locale)) {
      month = first;
      day = second;
    } else if (locale !== null && DAY_FIRST_LOCALES.has(locale)) {
      day = first;
      month = second;
    } else {
      // No known locale to disambiguate — never guess an interpretation.
      const code: VariantRejectionCode = "AMBIGUOUS_LOCALE";
      return { candidates: [], errorCode: code };
    }
  } else if (firstCouldBeMonth && !secondCouldBeMonth) {
    month = first;
    day = second;
  } else if (!firstCouldBeMonth && secondCouldBeMonth) {
    day = first;
    month = second;
  } else if (first === second && firstCouldBeMonth) {
    // Same value both positions: order is irrelevant, not ambiguous.
    month = first;
    day = second;
  } else {
    // Neither component can be a month — not a real calendar date.
    return { candidates: [], errorCode: "UNSUPPORTED_FORMAT" };
  }

  if (!isValidCalendarDay(month, day)) {
    return { candidates: [], errorCode: "UNSUPPORTED_FORMAT" };
  }

  const iso = `${year}-${pad2(month)}-${pad2(day)}`;
  return { candidates: dedupeInOrder([iso]), errorCode: null };
}
