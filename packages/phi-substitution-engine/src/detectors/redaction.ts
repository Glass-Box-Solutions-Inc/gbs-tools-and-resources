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
  const ordered = [...instructions].sort((a, b) => a.startUtf16 - b.startUtf16);

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
