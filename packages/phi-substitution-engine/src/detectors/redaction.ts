import type { TokenizedText } from "../core/brands";
import type { RedactionInstruction } from "./ports";
import { splitsSurrogatePair } from "./offsets";

export type ReplacementPlanResult =
  | Readonly<{ ok: true; text: TokenizedText; appliedSpanIds: readonly string[] }>
  | Readonly<{ ok: false; reason: "OUT_OF_RANGE" | "OVERLAP" | "INVALID_BOUNDARY" }>;

/**
 * Applies an explicit, TS-assigned replacement plan through the protected reversal boundary
 * (CONTRACT-phase1 §3.3, L12: "detector-only replacements use the same protected reversal
 * boundary").
 *
 * The tokens come only from the caller-supplied instructions — nothing is invented, no native
 * FPE/context output is trusted, and the original text is never echoed in place of a token.
 * Invalid or overlapping spans fail closed rather than partially redacting.
 */
export function applyReplacementPlan(
  originalText: string,
  instructions: readonly RedactionInstruction[],
): ReplacementPlanResult {
  const length = originalText.length;
  // §7/N2: `instructions` is boundary data. A NON-array carrier, or a REAL array with an OWN poisoned
  // `Symbol.iterator`, must NOT silently yield an EMPTY plan — that would echo the ORIGINAL text back
  // branded as TokenizedText (a fail-OPEN redaction). Copy by OWN index/length, then sort the copy.
  if (!Array.isArray(instructions)) {
    return { ok: false, reason: "OUT_OF_RANGE" };
  }
  const copied: RedactionInstruction[] = [];
  for (let i = 0; i < (instructions as { length: number }).length; i += 1) {
    copied[copied.length] = instructions[i]!;
  }
  const ordered = copied.sort((a, b) => a.startUtf16 - b.startUtf16);

  let cursor = 0;
  let out = "";
  const appliedSpanIds: string[] = [];

  for (const instruction of ordered) {
    const start = instruction.startUtf16;
    const end = instruction.endUtf16;

    if (!Number.isInteger(start) || !Number.isInteger(end) || start < 0 || end > length || start >= end) {
      return { ok: false, reason: "OUT_OF_RANGE" };
    }
    if (start < cursor) {
      return { ok: false, reason: "OVERLAP" };
    }
    if (splitsSurrogatePair(originalText, start) || splitsSurrogatePair(originalText, end)) {
      return { ok: false, reason: "INVALID_BOUNDARY" };
    }

    out += originalText.slice(cursor, start);
    out += instruction.replacement;
    appliedSpanIds.push(instruction.detectedSpanId);
    cursor = end;
  }

  out += originalText.slice(cursor);
  return { ok: true, text: out as TokenizedText, appliedSpanIds };
}
