import { describe, expect, it } from "vitest";
import { loadCollisionHarness } from "./implementation-under-test";

describe("phase-1 collision, boundary, citation, and offset rules", () => {
  it("COL-C1-01 / M-C1-REMOVE-WORD-BOUNDARY: blocks name and digit substrings", async () => {
    const r = await loadCollisionHarness().run("M-C1-REMOVE-WORD-BOUNDARY", {
      text: "Ann met Annette; IDs 078051120 and 90780511204.",
      variants: ["Ann", "078051120"],
    });
    expect(r.tokenizedText).toBe("[[Claimant]] met Annette; IDs [[SSN]] and 90780511204.");
  });

  it("COL-C2-01 / M-C2-ALLOW-BARE-YEAR: rejects indistinct standalone variants", async () => {
    const r = await loadCollisionHarness().run("M-C2-ALLOW-BARE-YEAR", {
      text: "In 1989 May said Will met J.",
      variants: ["1989", "May", "Will", "J"],
    });
    expect(r.tokenizedText).toBe("In 1989 May said Will met J.");
    expect(r.candidates).toEqual([]);
  });

  it("COL-C3-01 / M-C3-DISABLE-CITATION-EXCEPTION: preserves claimant surname in a validated citation", async () => {
    const r = await loadCollisionHarness().run("M-C3-DISABLE-CITATION-EXCEPTION", {
      text: "Garcia was discussed in Garcia v. WCAB (1989).",
      surname: "Garcia",
    });
    expect(r.tokenizedText).toBe("[[Claimant]] was discussed in Garcia v. WCAB (1989).");
  });

  it("COL-C3-02 / M-C3-BROAD-CITATION-EXCEPTION: near-citations do not suppress substitution", async () => {
    const r = await loadCollisionHarness().run("M-C3-BROAD-CITATION-EXCEPTION", {
      text: "Garcia v. insurer in 1989 over delayed benefits.",
      surname: "Garcia",
    });
    expect(r.tokenizedText).toBe("[[Claimant]] v. insurer in 1989 over delayed benefits.");
  });

  it("COL-C3-03 / M-C3-SUPPRESS-NONNAME-IN-CITATION: suppresses only a PERSON_NAME surname", async () => {
    const r = await loadCollisionHarness().run("M-C3-SUPPRESS-NONNAME-IN-CITATION", {
      text: "Garcia v. WCAB, MRN-A7719 (1989), DOB 03/04/1989.",
    });
    expect(r.tokenizedText).toBe("Garcia v. WCAB, [[MRN]] (1989), DOB [[DOB]].");
  });

  it("COL-C4-01 / M-C4-FIRST-MATCH-NOT-LONGEST: full name wins at a shared start", async () => {
    const r = await loadCollisionHarness().run("M-C4-FIRST-MATCH-NOT-LONGEST", {
      text: "Maria Garcia filed.",
      variants: ["Maria", "Maria Garcia", "Garcia"],
    });
    expect(r.tokenizedText).toBe("[[Claimant]] filed.");
  });

  it("COL-C5-01 / M-C5-ITERATION-ORDER-PRECEDENCE: output is independent of entry order", async () => {
    const r = await loadCollisionHarness().run("M-C5-ITERATION-ORDER-PRECEDENCE", {
      text: "Maria Garcia, 078-05-1120, maria@example.test",
      randomOrderSeeds: [1, 2, 3, 5, 8, 13, 21],
    });
    expect(new Set(r.outputs).size).toBe(1);
  });

  it("COL-C6-01 / M-C6-PICK-AMBIGUOUS-FIRST: equal-specificity subjects are quarantined and fail closed", async () => {
    const r = await loadCollisionHarness().run("M-C6-PICK-AMBIGUOUS-FIRST", {
      text: "Maria Garcia appeared.",
      subjects: ["claimant-1", "witness-2"],
      sameVariant: "Maria Garcia",
    });
    expect(r.tokenizedText).toBeNull();
    expect(r.ambiguityCount).toBe(1);
    expect(r.errorCode).toBe("AMBIGUOUS_KNOWN_IDENTIFIER");
    expect(r.providerCalls).toBe(0);
  });

  it("COL-C8-01 / M-C8-USE-NORMALIZED-OFFSETS: maps NFKC matches back to original UTF-16 offsets", async () => {
    const r = await loadCollisionHarness().run("M-C8-USE-NORMALIZED-OFFSETS", {
      text: "Before Ｍａｒｉａ Garci\u0301a 😀 after",
      normalizedVariant: "maria garcía",
    });
    expect(r.tokenizedText).toBe("Before [[Claimant]] 😀 after");
    expect(r.reversedText).toBe("Before Maria García 😀 after");
  });
});
