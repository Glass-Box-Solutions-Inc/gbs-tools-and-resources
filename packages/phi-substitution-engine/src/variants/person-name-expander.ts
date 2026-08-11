import type { VariantExpansion, VariantRejectionCode } from "./types";
import { dedupeInOrder } from "./support";

/**
 * Locales whose personal-name convention is given-name-first ("Western order").
 * Phase-1 reordering, initialization, and the English possessive suffix are
 * defined only for these. An unknown or absent locale is rejected, never
 * guessed — we do not invent a name-order convention we cannot justify.
 */
const WESTERN_ORDER_LOCALES: ReadonlySet<string> = new Set([
  "en-US",
  "en-GB",
  "en-CA",
  "es-US",
  "es-MX",
  "fr-FR",
  "de-DE",
]);

export interface PersonNameVariantRequest {
  readonly canonical: string;
  /** Staff-approved aliases only (e.g. an approved nickname). Never inferred. */
  readonly approvedAliases: readonly string[];
  readonly locale: string | null;
}

/** First Unicode code point of a non-empty string, or null when empty. */
function firstGrapheme(value: string): string | null {
  for (const ch of value) return ch;
  return null;
}

/**
 * Expands a canonical personal name into ONLY its allow-listed surface forms:
 * the canonical itself, a "Family, Given" reordering, a "G. Family" initial
 * form (both only for a simple two-part name), and one deterministic English
 * possessive. Nicknames and alternate spellings arrive solely through
 * `approvedAliases`; none is ever fabricated.
 */
export function expandPersonNameVariants(
  request: PersonNameVariantRequest,
): VariantExpansion {
  const { canonical, approvedAliases, locale } = request;
  const trimmed = canonical.trim();

  // Never guess a name-order convention we do not know.
  if (locale === null || !WESTERN_ORDER_LOCALES.has(locale)) {
    const code: VariantRejectionCode = "UNSUPPORTED_FORMAT";
    return { candidates: [], errorCode: code };
  }
  if (trimmed.length === 0) {
    return { candidates: [], errorCode: "UNSUPPORTED_FORMAT" };
  }

  const parts = trimmed.split(/\s+/).filter((part) => part.length > 0);
  const generated: string[] = [];

  // The canonical display form is always allow-listed.
  generated.push(trimmed);

  // Reordering and initialization are defined only for a simple given+family
  // pair. A multi-part name is NOT reduced to a two-name form, because dropping
  // interior names would be a lossy invention.
  if (parts.length === 2) {
    const given = parts[0];
    const family = parts[1];
    if (given !== undefined && family !== undefined) {
      generated.push(`${family}, ${given}`);
      const initial = firstGrapheme(given);
      if (initial !== null) {
        generated.push(`${initial}. ${family}`);
      }
    }
  }

  // Deterministic English possessive: one fixed rule, never an ambiguous style
  // choice, only for Western-order (English-adjacent) locales.
  generated.push(`${trimmed}'s`);

  // Staff-approved aliases are the ONLY path to a nickname/alternate spelling.
  for (const alias of approvedAliases) {
    const normalized = alias.trim();
    if (normalized.length > 0) {
      generated.push(normalized);
    }
  }

  return { candidates: dedupeInOrder(generated), errorCode: null };
}
