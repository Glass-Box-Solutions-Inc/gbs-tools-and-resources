import type { SubstitutionToken, TokenRole } from "../core/brands";
import type { ParsedToken, TokenGrammar, TokenGrammarPolicy } from "./ports";

/**
 * `[[Role]]` / `[[Role_N]]` grammar (CONTRACT-phase1 §3.3, L6, N5).
 *
 * - Sequence 1 is rendered bare (`[[Role]]`); N >= 2 is rendered `[[Role_N]]`.
 *   `_1`, leading zeros, and out-of-range sequences are malformed on parse so a
 *   provider echo can never smuggle in an off-registry token shape.
 * - Roles themselves may contain underscores (`Treating_Physician`), so the
 *   optional `_N` suffix is only split off when the remaining prefix is an
 *   allow-listed role; otherwise the whole inner text is treated as a role.
 */

const OPEN = "[[";
const CLOSE = "]]";

/** Spans returned by `scan` are always token-like: valid or malformed, never `not_token`. */
export type TokenSpanParse = Exclude<ParsedToken, Readonly<{ kind: "not_token" }>>;

function asToken(value: string): SubstitutionToken {
  return value as SubstitutionToken;
}

function classifyInner(inner: string, policy: TokenGrammarPolicy): TokenSpanParse {
  if (inner.length === 0) {
    return { kind: "malformed", reason: "BAD_DELIMITER" };
  }
  if (inner.length + OPEN.length + CLOSE.length > policy.maximumTokenUtf16Length) {
    return { kind: "malformed", reason: "OVERLONG" };
  }
  const roles = policy.allowedRoles as ReadonlySet<string>;

  // Exact role → bare token (sequence 1, rendered without a suffix).
  if (inner.length <= policy.maximumRoleUtf16Length && roles.has(inner)) {
    return { kind: "valid", token: asToken(`${OPEN}${inner}${CLOSE}`), role: inner as TokenRole, sequence: null };
  }

  // Trailing `_<digits>` with an allow-listed role prefix → sequenced token.
  const match = /^(.+)_(\d+)$/.exec(inner);
  if (match) {
    const role = match[1] as string;
    const digits = match[2] as string;
    if (role.length <= policy.maximumRoleUtf16Length && roles.has(role)) {
      if (digits.length > 1 && digits.startsWith("0")) {
        return { kind: "malformed", reason: "BAD_SEQUENCE" };
      }
      const sequence = Number(digits);
      if (!Number.isSafeInteger(sequence) || sequence < 2 || sequence > policy.maximumSequence) {
        return { kind: "malformed", reason: "BAD_SEQUENCE" };
      }
      return {
        kind: "valid",
        token: asToken(`${OPEN}${role}_${sequence}${CLOSE}`),
        role: role as TokenRole,
        sequence,
      };
    }
  }

  return { kind: "malformed", reason: "UNKNOWN_ROLE" };
}

export class BracketTokenGrammar implements TokenGrammar {
  parse(candidate: string, policy: TokenGrammarPolicy): ParsedToken {
    if (candidate.length < OPEN.length + CLOSE.length) {
      return { kind: "not_token" };
    }
    if (!candidate.startsWith(OPEN) || !candidate.endsWith(CLOSE)) {
      return { kind: "not_token" };
    }
    const inner = candidate.slice(OPEN.length, candidate.length - CLOSE.length);
    if (inner.includes(OPEN)) {
      return { kind: "malformed", reason: "NESTED" };
    }
    return classifyInner(inner, policy);
  }

  format(role: TokenRole, sequence: number | null, policy: TokenGrammarPolicy): SubstitutionToken {
    if (!(policy.allowedRoles as ReadonlySet<string>).has(role)) {
      throw new Error("token_grammar_unknown_role");
    }
    if (sequence === null || sequence === 1) {
      return asToken(`${OPEN}${role}${CLOSE}`);
    }
    if (!Number.isSafeInteger(sequence) || sequence < 2 || sequence > policy.maximumSequence) {
      throw new Error("token_grammar_bad_sequence");
    }
    return asToken(`${OPEN}${role}_${sequence}${CLOSE}`);
  }

  scan(
    text: string,
    policy: TokenGrammarPolicy,
  ): readonly Readonly<{ startUtf16: number; endUtf16: number; parsed: TokenSpanParse }>[] {
    const spans: { startUtf16: number; endUtf16: number; parsed: TokenSpanParse }[] = [];
    let i = 0;
    while (i < text.length) {
      const open = text.indexOf(OPEN, i);
      if (open < 0) {
        break;
      }
      const close = text.indexOf(CLOSE, open + OPEN.length);
      if (close < 0) {
        // Opened but never closed: a terminal partial token shape.
        spans.push({
          startUtf16: open,
          endUtf16: text.length,
          parsed: { kind: "malformed", reason: "BAD_DELIMITER" },
        });
        break;
      }
      const nested = text.indexOf(OPEN, open + OPEN.length);
      if (nested >= 0 && nested < close) {
        spans.push({
          startUtf16: open,
          endUtf16: close + CLOSE.length,
          parsed: { kind: "malformed", reason: "NESTED" },
        });
        i = close + CLOSE.length;
        continue;
      }
      const inner = text.slice(open + OPEN.length, close);
      spans.push({
        startUtf16: open,
        endUtf16: close + CLOSE.length,
        parsed: classifyInner(inner, policy),
      });
      i = close + CLOSE.length;
    }
    return spans;
  }
}
