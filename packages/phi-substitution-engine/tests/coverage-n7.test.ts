import { describe, expect, it } from "vitest";
import { loadCoverageHarness } from "./implementation-under-test";

describe("N7 total LLM-egress coverage", () => {
  it("SEC-N7-01 / M-N7-RAW-FETCH-NEW-FILE: egress lint rejects new raw provider fetch", async () => {
    const r = await loadCoverageHarness().run("M-N7-RAW-FETCH-NEW-FILE", {
      addedFile: "backend/src/modules/new-feature/leak.service.ts",
      source: "fetch('https://example.openai.azure.com/openai/deployments/x/chat/completions')",
      registered: false,
    });
    expect(r.buildPassed).toBe(false);
    expect(r.diagnostics).toContain("UNPROTECTED_PROVIDER_HOST");
  });

  it("SEC-N7-02 / M-N7-CONSTRUCT-OUTSIDE-WRAPPER: architecture test rejects raw SDK/model handle", async () => {
    const r = await loadCoverageHarness().run("M-N7-CONSTRUCT-OUTSIDE-WRAPPER", {
      addedFile: "backend/src/modules/new-feature/model.ts",
      sourceKind: "new AzureOpenAI",
      outsideProtectedModule: true,
    });
    expect(r.buildPassed).toBe(false);
    expect(r.diagnostics).toContain("RAW_PROVIDER_CONSTRUCTION_FORBIDDEN");
  });

  it("SEC-N7-03 / M-N7-STALE-REGISTRY-ENTRY: surface registry drift fails", async () => {
    const r = await loadCoverageHarness().run("M-N7-STALE-REGISTRY-ENTRY", {
      registryEntry: { file: "deleted.ts", symbol: "oldCall", classification: "engine-covered" },
      liveSymbols: [],
    });
    expect(r.buildPassed).toBe(false);
    expect(r.diagnostics).toContain("SURFACE_REGISTRY_DRIFT");
  });

  it("SEC-N7-04: every discovered surface is exactly covered or carve-out", async () => {
    const r = await loadCoverageHarness().run("N7-TOTAL-CLASSIFICATION", {
      discoverCurrentTree: true,
      allowedClasses: ["engine-covered", "reviewed-carve-out"],
      exactMembership: true,
    });
    expect(r.buildPassed).toBe(true);
    expect(r.metrics.unregisteredSurfaces).toBe(0);
    expect(r.metrics.multiplyClassifiedSurfaces).toBe(0);
  });

  it("SEC-N7-05: multimodal is a reviewed BAA/minimum-necessary carve-out, not text coverage", async () => {
    const r = await loadCoverageHarness().run("N7-MULTIMODAL-CARVEOUT", {
      surfaceKind: "image-base64-to-vision-model",
      substitutionClaimed: false,
      mitigation: ["BAA_PROVIDER", "MINIMUM_NECESSARY"],
    });
    expect(r.buildPassed).toBe(true);
    expect(r.metrics.engineCovered).toBe(false);
    expect(r.metrics.reviewedCarveout).toBe(true);
  });
});
