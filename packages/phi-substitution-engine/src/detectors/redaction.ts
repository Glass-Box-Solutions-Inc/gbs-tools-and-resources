import type { TokenizedText } from "../core/brands";
import type { RedactionInstruction } from "./ports";
import { splitsSurrogatePair } from "./offsets";
import { safeRead, safeString, intrinsicCopy } from "../core/boundary-snapshot";

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
  // Copy by OWN index/length FIRST: a NON-array carrier, an OWN poisoned `Symbol.iterator`, OR an own
  // index getter that THROWS (a genuine array can still carry `Object.defineProperty(arr, 0, {get})`)
  // must NOT silently yield an EMPTY plan (which would echo the ORIGINAL text back branded as
  // TokenizedText — a fail-OPEN redaction) or throw raw out of this exported boundary. Fail closed.
  const rawInstructions = intrinsicCopy<unknown>(instructions);
  if (rawInstructions === null) {
    return { ok: false, reason: "OUT_OF_RANGE" };
  }
  // Read EVERY field of EVERY instruction ONCE, getter-throw-safe, into inert plain data. A throwing/
  // mutating field getter (e.g. a `replacement` getter that throws PHI) fails closed here rather than
  // propagating raw out of this exported boundary; nothing downstream ever touches a live getter.
  const copied: { startUtf16: number; endUtf16: number; replacement: string; detectedSpanId: string }[] = [];
  for (let i = 0; i < rawInstructions.length; i += 1) {
    const raw = rawInstructions[i];
    const startUtf16 = safeRead(raw, "startUtf16");
    const endUtf16 = safeRead(raw, "endUtf16");
    const replacement = safeString(raw, "replacement");
    const detectedSpanId = safeString(raw, "detectedSpanId");
    if (
      typeof startUtf16 !== "number" || typeof endUtf16 !== "number" ||
      replacement === undefined || detectedSpanId === undefined
    ) {
      return { ok: false, reason: "OUT_OF_RANGE" };
    }
    copied[copied.length] = { startUtf16, endUtf16, replacement, detectedSpanId };
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
