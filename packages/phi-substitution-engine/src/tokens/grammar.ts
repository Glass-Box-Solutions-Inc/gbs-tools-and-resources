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

/**
 * A GENUINELY immutable, tamper-proof role allow-list (GLY-336 gate finding 2, capability-level).
 *
 * Two layers of hardening, both required:
 *
 * 1. WRITE-proof. `Object.freeze(new Set(...))` is NOT enough: `Set.prototype.add.call(frozenSet,
 *    role)` still mutates the internal `[[SetData]]` slot (freezing only locks own properties). The
 *    oracle returned here is a FROZEN plain object with NO `[[SetData]]` slot, so no `Set.prototype`
 *    mutator can operate on it, and it exposes no `add`/`delete`/`clear`.
 *
 * 2. READ-proof (poison-resistant). The security-critical membership check (`has`) must NOT route
 *    through `Set.prototype.has`, which a consumer can replace globally — even before this module is
 *    imported — to make an arbitrary (PHI-bearing) role pass the allow-list and be emitted as a
 *    token label. Membership is therefore backed by a FROZEN NULL-PROTOTYPE record read *directly*:
 *    an `Object.create(null)` object has no prototype chain and no inherited/poisonable accessors,
 *    so `record[value]` is a pure data read that cannot be diverted by `Set.prototype`,
 *    `Object.prototype`, or import-order tampering. `__proto__`/`constructor` as role names resolve
 *    to own data properties (or `undefined`), never to inherited members. No live `Set` is retained.
 */
export function frozenRoleSet(
  roles: Iterable<TokenRole>,
): ReadonlySet<TokenRole> {
  const membership: Record<string, true> = Object.create(null) as Record<
    string,
    true
  >;
  const list: TokenRole[] = [];
  for (const role of roles) {
    if (membership[role as unknown as string] !== true) {
      membership[role as unknown as string] = true;
      list.push(role);
    }
  }
  Object.freeze(membership); // closure-private; never exposed; no [[SetData]], null prototype
  const frozenList: readonly TokenRole[] = Object.freeze(list);
  const iterate = (): IterableIterator<TokenRole> =>
    frozenList[Symbol.iterator]();
  const result: ReadonlySet<TokenRole> = Object.freeze({
    has: (value: TokenRole): boolean =>
      membership[value as unknown as string] === true,
    get size(): number {
      return frozenList.length;
    },
    keys: iterate,
    values: iterate,
    *entries(): IterableIterator<[TokenRole, TokenRole]> {
      for (const role of frozenList) yield [role, role];
    },
    forEach(
      callbackfn: (
        value: TokenRole,
        value2: TokenRole,
        set: ReadonlySet<TokenRole>,
      ) => void,
      thisArg?: unknown,
    ): void {
      for (const role of frozenList)
        callbackfn.call(thisArg, role, role, result);
    },
    [Symbol.iterator]: iterate,
  });
  return result;
}

/** Spans returned by `scan` are always token-like: valid or malformed, never `not_token`. */
export type TokenSpanParse = Exclude<
  ParsedToken,
  Readonly<{ kind: "not_token" }>
>;

function asToken(value: string): SubstitutionToken {
  return value as SubstitutionToken;
}

/** GLY-373 §3.1: the DETECTOR-namespace marker and its delimiter. */
const DETECTOR_PREFIX = "D~";
const NS_DELIMITER = "~";
/** GLY-373 §3.1: `ns ::= [0-9a-f]{16}` — exactly 16 lowercase hex characters. */
const NS_UTF16_LENGTH = 16;

/**
 * GLY-373 §3.1: `ns` shape test by OWN-property indexed reads and comparisons against fixed
 * literals only — never `RegExp.prototype.test` (which parks the whole subject in the legacy
 * `RegExp.input`/`RegExp.$_` global statics) and never a `String.prototype` method (poisonable).
 * Same poison-resistant idiom, and the same reason, as `frozenRoleSet` above.
 */
function isNamespaceLabel(value: string): boolean {
  if (value.length !== NS_UTF16_LENGTH) {
    return false;
  }
  for (let i = 0; i < NS_UTF16_LENGTH; i += 1) {
    const c = value[i] as string;
    const isDigit = c >= "0" && c <= "9";
    const isLowerHex = c >= "a" && c <= "f";
    if (!isDigit && !isLowerHex) {
      return false;
    }
  }
  return true;
}

/** The inner-text prefix a namespace contributes: `""` for AUTHORITY, `D~<ns>~` for DETECTOR. */
function namespacePrefix(namespace: string | null): string {
  return namespace === null
    ? ""
    : `${DETECTOR_PREFIX}${namespace}${NS_DELIMITER}`;
}

/**
 * Role-and-sequence classification — GLY-373 §3.1 step 6. This is the 0.2.0 logic verbatim,
 * shared by BOTH namespaces so the role and sequence rules have exactly one implementation;
 * `namespace` only decides the emitted token text and the reported `namespace` field.
 */
function classifyRoleAndSequence(
  text: string,
  policy: TokenGrammarPolicy,
  namespace: string | null,
): TokenSpanParse {
  const roles = policy.allowedRoles as ReadonlySet<string>;
  const prefix = namespacePrefix(namespace);

  // Exact role → bare token (sequence 1, rendered without a suffix).
  if (text.length <= policy.maximumRoleUtf16Length && roles.has(text)) {
    return {
      kind: "valid",
      token: asToken(`${OPEN}${prefix}${text}${CLOSE}`),
      role: text as TokenRole,
      sequence: null,
      namespace,
    };
  }

  // Trailing `_<digits>` with an allow-listed role prefix → sequenced token.
  const match = /^(.+)_(\d+)$/.exec(text);
  if (match) {
    const role = match[1] as string;
    const digits = match[2] as string;
    if (role.length <= policy.maximumRoleUtf16Length && roles.has(role)) {
      if (digits.length > 1 && digits.startsWith("0")) {
        return { kind: "malformed", reason: "BAD_SEQUENCE" };
      }
      const sequence = Number(digits);
      if (
        !Number.isSafeInteger(sequence) ||
        sequence < 2 ||
        sequence > policy.maximumSequence
      ) {
        return { kind: "malformed", reason: "BAD_SEQUENCE" };
      }
      return {
        kind: "valid",
        token: asToken(`${OPEN}${prefix}${role}_${sequence}${CLOSE}`),
        role: role as TokenRole,
        sequence,
        namespace,
      };
    }
  }

  return { kind: "malformed", reason: "UNKNOWN_ROLE" };
}

/**
 * GLY-373 §3.1 — the ORDER OF THESE STEPS IS NORMATIVE.
 *
 * The namespace layer FULLY VALIDATES before it delegates. Delegating first would send
 * `"SSN~X"` to the role branch (→ `UNKNOWN_ROLE`) and `""` to the empty branch
 * (→ `BAD_DELIMITER`), so `[[D~ns~SSN~X]]` and `[[D~ns~]]` would report neither
 * `BAD_NAMESPACE`. MUT-38 kills a delegate-first implementation; OR-GLY373-01's
 * parse-order rows assert the REASON STRING, not merely that the input was rejected.
 *
 * 1. no `D~` prefix → 0.2.0 logic verbatim with `namespace = null`;
 * 2. `maximumTokenUtf16Length` against the WHOLE token, before any splitting;
 * 3. a first `~` must exist after `D~`, else `BAD_NAMESPACE`;
 * 4. `ns` must be exactly 16 lowercase hex characters, else `BAD_NAMESPACE`;
 * 5. the remainder must be non-empty and contain no further `~`, else `BAD_NAMESPACE`;
 * 6. only THEN delegate the remainder to the shared role/sequence rules.
 */
function classifyInner(
  inner: string,
  policy: TokenGrammarPolicy,
): TokenSpanParse {
  if (inner.length === 0) {
    return { kind: "malformed", reason: "BAD_DELIMITER" };
  }
  // Step 2: the length bound is applied ONCE, to the whole token, so the namespace's own
  // units are counted. Worst case `[[D~<16 hex>~Treating_Physician_9999]]` is 46 of 64.
  if (
    inner.length + OPEN.length + CLOSE.length >
    policy.maximumTokenUtf16Length
  ) {
    return { kind: "malformed", reason: "OVERLONG" };
  }
  // Step 1: AUTHORITY namespace — unchanged, byte-identical to 0.2.0.
  if (!inner.startsWith(DETECTOR_PREFIX)) {
    return classifyRoleAndSequence(inner, policy, null);
  }
  // Step 3.
  const rest = inner.slice(DETECTOR_PREFIX.length);
  const delimiter = rest.indexOf(NS_DELIMITER);
  if (delimiter < 0) {
    return { kind: "malformed", reason: "BAD_NAMESPACE" };
  }
  // Step 4.
  const ns = rest.slice(0, delimiter);
  if (!isNamespaceLabel(ns)) {
    return { kind: "malformed", reason: "BAD_NAMESPACE" };
  }
  // Step 5.
  const remainder = rest.slice(delimiter + NS_DELIMITER.length);
  if (remainder.length === 0 || remainder.indexOf(NS_DELIMITER) >= 0) {
    return { kind: "malformed", reason: "BAD_NAMESPACE" };
  }
  // Step 6.
  return classifyRoleAndSequence(remainder, policy, ns);
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

  /**
   * GLY-373 §3.1: `namespace` absent/`undefined` → the AUTHORITY production, byte-identical to
   * 0.2.0. Present → validated against `[0-9a-f]{16}` and emitted as `D~<ns>~`; a violation
   * throws the fixed `token_grammar_bad_namespace` so an UNVALIDATED namespace can never be
   * emitted into a token.
   */
  format(
    role: TokenRole,
    sequence: number | null,
    policy: TokenGrammarPolicy,
    namespace?: string,
  ): SubstitutionToken {
    if (!(policy.allowedRoles as ReadonlySet<string>).has(role)) {
      throw new Error("token_grammar_unknown_role");
    }
    let prefix = "";
    if (namespace !== undefined) {
      if (typeof namespace !== "string" || !isNamespaceLabel(namespace)) {
        throw new Error("token_grammar_bad_namespace");
      }
      prefix = namespacePrefix(namespace);
    }
    if (sequence === null || sequence === 1) {
      return asToken(`${OPEN}${prefix}${role}${CLOSE}`);
    }
    if (
      !Number.isSafeInteger(sequence) ||
      sequence < 2 ||
      sequence > policy.maximumSequence
    ) {
      throw new Error("token_grammar_bad_sequence");
    }
    return asToken(`${OPEN}${prefix}${role}_${sequence}${CLOSE}`);
  }

  scan(
    text: string,
    policy: TokenGrammarPolicy,
  ): readonly Readonly<{
    startUtf16: number;
    endUtf16: number;
    parsed: TokenSpanParse;
  }>[] {
    const spans: {
      startUtf16: number;
      endUtf16: number;
      parsed: TokenSpanParse;
    }[] = [];
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
