/**
 * Deterministic structured-identifier detection (rule support for L3/L12).
 *
 * Phase 1 does NOT do probabilistic free-text / name inference — that stays
 * disabled per the frozen contract. These detectors recognize only rigid,
 * self-delimiting identifier formats (SSN, MRN, full date, e-mail) whose shape
 * is unambiguous. They run against the ORIGINAL text and emit ORIGINAL UTF-16
 * offsets, so downstream substitution never validates against a normalized copy.
 */
import type { IdentifierClass } from "../core/contracts";
import type { Utf16Offset } from "../core/brands";
import type { DetectorCollisionSpan } from "./ports";

const asUtf16 = (value: number): Utf16Offset => value as unknown as Utf16Offset;

interface DetectorRule {
  readonly identifierClass: IdentifierClass;
  readonly pattern: RegExp;
}

const DETECTOR_RULES: readonly DetectorRule[] = [
  {
    identifierClass: "EMAIL",
    pattern: /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/gu,
  },
  { identifierClass: "MRN", pattern: /\bMRN-[A-Za-z0-9]+\b/gu },
  { identifierClass: "DOB", pattern: /\b\d{1,2}\/\d{1,2}\/\d{4}\b/gu },
  { identifierClass: "SSN", pattern: /\b\d{3}-\d{2}-\d{4}\b/gu },
];

function pushMatches(
  rule: DetectorRule,
  text: string,
  out: DetectorCollisionSpan[],
): void {
  rule.pattern.lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = rule.pattern.exec(text)) !== null) {
    if (match[0].length === 0) {
      rule.pattern.lastIndex += 1;
      continue;
    }
    out.push({
      startUtf16: asUtf16(match.index),
      endUtf16: asUtf16(match.index + match[0].length),
      identifierClass: rule.identifierClass,
      confidence: 1,
    });
  }
}

/** A compact 9-digit run bounded by non-digits is a phase-1 SSN. */
function detectCompactSsn(text: string, out: DetectorCollisionSpan[]): void {
  const runs = /\d+/gu;
  let match: RegExpExecArray | null;
  while ((match = runs.exec(text)) !== null) {
    if (match[0].length === 9) {
      out.push({
        startUtf16: asUtf16(match.index),
        endUtf16: asUtf16(match.index + 9),
        identifierClass: "SSN",
        confidence: 1,
      });
    }
  }
}

export function detectStructuredIdentifiers(
  text: string,
): readonly DetectorCollisionSpan[] {
  const spans: DetectorCollisionSpan[] = [];
  for (const rule of DETECTOR_RULES) {
    pushMatches(rule, text, spans);
  }
  detectCompactSsn(text, spans);
  return dedupe(spans);
}

function dedupe(
  spans: readonly DetectorCollisionSpan[],
): readonly DetectorCollisionSpan[] {
  const seen = new Set<string>();
  const out: DetectorCollisionSpan[] = [];
  for (const span of spans) {
    const key = `${span.startUtf16 as unknown as number}:${span.endUtf16 as unknown as number}:${span.identifierClass}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(span);
  }
  return out;
}

/** Infers the identifier class of a trusted variant string from its rigid shape. */
export function inferIdentifierClass(value: string): IdentifierClass {
  const trimmed = value.trim();
  if (/@/.test(trimmed)) return "EMAIL";
  if (/^MRN-/i.test(trimmed)) return "MRN";
  if (/^\d{1,2}\/\d{1,2}\/\d{4}$/.test(trimmed)) return "DOB";
  if (/^\d{3}-\d{2}-\d{4}$/.test(trimmed) || /^\d{9}$/.test(trimmed))
    return "SSN";
  if (/^[12]\d{3}$/.test(trimmed)) return "OTHER_TAGGED"; // bare year -> C2 rejects it
  if (/^\+?[\d\s()-]{7,}$/.test(trimmed)) return "PHONE";
  return "PERSON_NAME";
}
