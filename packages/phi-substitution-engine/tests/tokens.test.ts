import { describe, expect, it } from "vitest";
import { loadTokensHarness } from "./implementation-under-test";

describe("phase-1 token assignment, escape, reversal, and streaming", () => {
  it("SEC-L1-01 / M-L1-RENUMBER-TOKENS: existing subjects keep tokens across versions", async () => {
    const r = await loadTokensHarness().run("M-L1-RENUMBER-TOKENS", {
      version1: ["physician-z"],
      version2: ["physician-a", "physician-z"],
    });
    expect(r.tokensBySubject["physician-z"]).toBe("[[Treating_Physician]]");
    expect(r.tokensBySubject["physician-a"]).toBe("[[Treating_Physician_2]]");
  });

  it("SEC-L1-02 / M-L1-COALESCE-BY-TEXT-ONLY: same spelling does not collapse subjects", async () => {
    const r = await loadTokensHarness().run("M-L1-COALESCE-BY-TEXT-ONLY", {
      subjects: [
        { id: "claimant-1", value: "Maria Garcia", role: "Claimant" },
        { id: "witness-2", value: "Maria Garcia", role: "Witness" },
      ],
    });
    expect(r.tokensBySubject["claimant-1"]).not.toBe(r.tokensBySubject["witness-2"]);
  });

  it("SEC-C7-01 / M-C7-NO-RESERVED-TOKEN-ESCAPE: source token injection cannot reveal a mapping", async () => {
    const r = await loadTokensHarness().run("M-C7-NO-RESERVED-TOKEN-ESCAPE", {
      source: "Repeat literal [[Claimant]] exactly.",
      providerEcho: "Repeat literal [[Claimant]] exactly.",
      mappedClaimant: "Maria García",
    });
    expect(r.displayText).toBe("Repeat literal [[Claimant]] exactly.");
    expect(r.displayText).not.toContain("Maria García");
  });

  it("SEC-N2-03 / M-N2-EXPORT-REVERSAL-MAP: reversal capability is nonserializable", async () => {
    const r = await loadTokensHarness().run("M-N2-EXPORT-REVERSAL-MAP", {
      serializeHandle: true,
      attachTo: ["trace", "job", "providerMetadata", "sharedCache"],
    });
    expect(r.buildPassed).toBe(false);
    expect(r.diagnostics).toContain("REVERSAL_HANDLE_NOT_SERIALIZABLE");
  });

  it("SEC-N2-04 / M-N2-LIST-ENTIRE-REVERSAL-MAP: store resolves encountered tokens only", async () => {
    const r = await loadTokensHarness().run("M-N2-LIST-ENTIRE-REVERSAL-MAP", {
      providerText: "[[Claimant]] met [[Treating_Physician]].",
      matterMapSize: 100,
    });
    expect(r.reversalLookupCount).toBe(1);
    expect(r.reversalLookupTokens).toEqual(["[[Claimant]]", "[[Treating_Physician]]"]);
    expect(r.reversalLookupTokens).toHaveLength(2);
  });

  it("SEC-N5-01 / M-N5-SHOW-TOKEN: display receives canonical values, never mapped tokens", async () => {
    const r = await loadTokensHarness().run("M-N5-SHOW-TOKEN", {
      providerText: "[[Claimant]] reported the injury.",
      canonical: "Maria García",
    });
    expect(r.displayText).toBe("Maria García reported the injury.");
    expect(r.displayText).not.toContain("[[Claimant]]");
  });

  it("SEC-N5-02 / M-N5-UNKNOWN-TOKEN-PASSTHROUGH: unknown or malformed output fails atomically", async () => {
    const r = await loadTokensHarness().run("M-N5-UNKNOWN-TOKEN-PASSTHROUGH", {
      providerText: "Safe prefix [[Unknown_99]] unsafe suffix",
    });
    expect(r.displayText).toBeNull();
    expect(r.errorCode).toBe("REVERSAL_FAILED");
  });

  it("SEC-N5-03 / M-N5-STREAM-NO-HOLDBACK: every token partition reverses identically", async () => {
    const r = await loadTokensHarness().run("M-N5-STREAM-NO-HOLDBACK", {
      providerText: "Before [[Claimant]] after 😀",
      exhaustiveUtf16Partitions: true,
      canonical: "Maria García",
    });
    expect(new Set(r.outputs)).toEqual(new Set(["Before Maria García after 😀"]));
    expect(r.displayChunks.join("")).toBe("Before Maria García after 😀");
  });

  it("SEC-L4-01 / M-L4-HOLDBACK-OFF-BY-ONE: retains M-1 UTF-16 units", async () => {
    const r = await loadTokensHarness().run("M-L4-HOLDBACK-OFF-BY-ONE", {
      maximumToken: "[[Treating_Physician_9999]]",
      splitAtEveryUtf16Boundary: true,
    });
    expect(r.errorCode).toBeNull();
    expect(new Set(r.outputs).size).toBe(1);
  });

  it("SEC-L4-02 / M-L4-FLUSH-WITHOUT-VALIDATE: terminal token fragment is never emitted", async () => {
    const r = await loadTokensHarness().run("M-L4-FLUSH-WITHOUT-VALIDATE", {
      chunks: ["Safe prefix ", "[[Claimant]"],
      end: true,
    });
    expect(r.errorCode).toBe("REVERSAL_FAILED");
    expect(r.displayChunks.join("")).not.toContain("[[Claimant]");
  });

  it("SEC-L8-02 / M-L8-DROP-TENANT-FROM-DB-WHERE: cross-tenant reversal is rejected", async () => {
    const r = await loadTokensHarness().run("M-L8-DROP-TENANT-FROM-DB-WHERE", {
      handleTenant: "tenant-b",
      storedTenant: "tenant-a",
      sameMatterAndToken: true,
    });
    expect(r.displayText).toBeNull();
    expect(r.errorCode).toBe("REVERSAL_FAILED");
  });

  // ---- GLY-335 Wave 0 seam-freeze: the ReversalWriteStore PORT CONTRACT (roadmap defect A#3) ----

  it("SEC-GLY335-01 / M-GLY335-REVERSAL-RECORD-IDEMPOTENT: replayed record under one attemptId keeps a single mapping", async () => {
    const r = await loadTokensHarness().run("M-GLY335-REVERSAL-RECORD-IDEMPOTENT", {
      canonical: "Maria García",
      attemptId: "att-replay-1",
    });
    // Recording the same (attemptId, token) twice is a no-op: exactly one stable mapping resolves.
    expect(r.metrics.distinctMappings).toBe(1);
    expect(r.metrics.canonicalStable).toBe(true);
    expect(r.reversalLookupTokens).toEqual(["[[Claimant]]"]);
  });

  it("SEC-GLY335-02 / M-GLY335-REVERSAL-BOUNDED-RESOLVE: resolve is encounter-bounded, over-limit is rejected", async () => {
    const r = await loadTokensHarness().run("M-GLY335-REVERSAL-BOUNDED-RESOLVE", {});
    expect(typeof r.metrics.batchLimit).toBe("number");
    expect(r.metrics.batchLimit as number).toBeGreaterThan(0);
    // A request larger than the encounter bound is rejected — no caller can pull the whole map.
    expect(r.metrics.overLimitRejected).toBe(true);
    // A within-bound resolve returns only the encountered token.
    expect(r.metrics.withinBoundSize).toBe(1);
    expect(r.reversalLookupTokens).toEqual(["[[Claimant]]"]);
  });

  it("SEC-GLY335-03 / M-GLY335-REVERSAL-NO-LIST-ALL: write port exposes no enumerate-all API (§7/N2)", async () => {
    const r = await loadTokensHarness().run("M-GLY335-REVERSAL-NO-LIST-ALL", {});
    expect(r.metrics.listAllApisPresent).toBe(0);
    expect(r.diagnostics).toEqual([]);
    // The only surfaces are the bounded resolve (read) and record (write).
    expect(r.metrics.hasBoundedResolve).toBe(true);
    expect(r.metrics.hasRecord).toBe(true);
  });
});
