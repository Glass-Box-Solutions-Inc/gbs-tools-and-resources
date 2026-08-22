import { describe, expect, it } from "vitest";
import { BracketTokenGrammar } from "../src/tokens/grammar";
import { BOUNDARY_TOKEN_GRAMMAR_POLICY } from "../src/core/orchestrator";

/**
 * GLY-373 CAND-1 contract test. The `[[...]]` inner text comes from UNTRUSTED model/provider
 * output and may carry PHI. Parsing or scanning it must NOT park that text in the legacy RegExp
 * global statics (`RegExp.input` / `RegExp.$_` / `RegExp.lastMatch` / `RegExp.lastParen`), which
 * every in-process actor — including every injected port the threat model declares UNTRUSTED —
 * can read afterwards. This asserts the CONTRACT (the statics are unchanged across the call),
 * never the implementation, so any future non-leaking implementation still passes.
 */
const SENTINEL = "GLY373_SENTINEL_NO_PHI";

function parkSentinel(): void {
  /GLY373_SENTINEL_NO_PHI/.exec(SENTINEL);
}

function readStatics(): Record<string, unknown> {
  const legacy = RegExp as unknown as Record<string, unknown>;
  return {
    input: legacy["input"],
    dollarUnderscore: legacy["$_"],
    lastMatch: legacy["lastMatch"],
    lastParen: legacy["lastParen"],
  };
}

describe("GLY-373 CAND-1 — untrusted span text never reaches the RegExp legacy statics", () => {
  const grammar = new BracketTokenGrammar();
  const PHI_TOKEN = "[[Jane Doe SSN 123-45-6789_7]]";
  const PHI_TEXT = "note: patient [[MRN 55-99-1234 Doe_3]] discharged";

  it("parse() leaves the legacy statics untouched", () => {
    parkSentinel();
    const before = readStatics();
    grammar.parse(PHI_TOKEN, BOUNDARY_TOKEN_GRAMMAR_POLICY);
    const after = readStatics();
    expect(after).toEqual(before);
    expect(JSON.stringify(after)).not.toContain("123-45-6789");
    expect(after["input"]).toBe(SENTINEL);
  });

  it("scan() leaves the legacy statics untouched", () => {
    parkSentinel();
    const before = readStatics();
    grammar.scan(PHI_TEXT, BOUNDARY_TOKEN_GRAMMAR_POLICY);
    const after = readStatics();
    expect(after).toEqual(before);
    expect(JSON.stringify(after)).not.toContain("55-99-1234");
    expect(after["input"]).toBe(SENTINEL);
  });

  it("a valid sequenced token parses identically to before the containment change", () => {
    const parsed = grammar.parse(
      "[[Claimant_7]]",
      BOUNDARY_TOKEN_GRAMMAR_POLICY,
    );
    expect(parsed).toEqual({
      kind: "valid",
      token: "[[Claimant_7]]",
      role: "Claimant",
      sequence: 7,
      namespace: null,
    });
  });
});
