import { describe, expect, it } from "vitest";
import { loadVariantsHarness } from "./implementation-under-test";

describe("phase-1 deterministic variant expanders", () => {
  it("VAR-L10-01 / M-L10-INVENT-FUZZY-NAME: emits only allow-listed name variants", async () => {
    const h = loadVariantsHarness();
    const r = await h.run("M-L10-INVENT-FUZZY-NAME", {
      canonical: "Robert O'Neil",
      approvedAliases: [],
      locale: "en-US",
      expected: ["Robert O'Neil", "O'Neil, Robert", "R. O'Neil", "Robert O'Neil's"],
    });
    expect(r.candidates).toEqual(["Robert O'Neil", "O'Neil, Robert", "R. O'Neil", "Robert O'Neil's"]);
    expect(r.candidates).not.toContain("Bob O'Neil");
    expect(r.candidates).not.toContain("Robert Oneil");
  });

  it("VAR-L10-02 / M-L10-GUESS-BOTH-DATE-LOCALES: never guesses an ambiguous date locale", async () => {
    const h = loadVariantsHarness();
    const r = await h.run("M-L10-GUESS-BOTH-DATE-LOCALES", {
      canonical: "03/04/1989",
      locale: null,
      forbiddenInterpretations: ["1989-03-04", "1989-04-03"],
    });
    expect(r.candidates).toEqual([]);
    expect(r.errorCode).toBe("AMBIGUOUS_LOCALE");
  });

  it("VAR-L10-03 / M-L10-LOSSY-STRUCTURED-ID: retains required prefix and explicit separators", async () => {
    const h = loadVariantsHarness();
    const r = await h.run("M-L10-LOSSY-STRUCTURED-ID", {
      canonical: "CLM-00421",
      policy: {
        requiredAlphaPrefix: "CLM",
        permittedSeparators: ["-", " "],
        allowCompactForm: false,
        minimumAlphanumericLength: 8,
      },
      unrelatedText: "See legal section 00421 and account 421.",
    });
    expect(r.candidates).toEqual(["CLM-00421", "CLM 00421"]);
    expect(r.candidates).not.toContain("CLM00421");
    expect(r.candidates).not.toContain("00421");
    expect(r.providerPayloads.join("\n")).toContain("legal section 00421");
  });
});
