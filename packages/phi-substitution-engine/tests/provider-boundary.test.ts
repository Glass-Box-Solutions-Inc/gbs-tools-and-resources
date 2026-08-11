import { describe, expect, it } from "vitest";
import { loadProviderBoundaryHarness } from "./implementation-under-test";
import { expectExactlyOneProviderCall, expectFailedClosed, expectNoCanary } from "./test-helpers";

describe("Glassy ProtectedAiProvider boundary", () => {
  it("SEC-N1-01 / M-N1-DIRECT-GENERATE: all generation crosses wrapper", async () => {
    const r = await loadProviderBoundaryHarness().run("M-N1-DIRECT-GENERATE", {
      method: "generateText",
      canaryPaths: ["system", "messages[0].content[0].text", "tools[0].description"],
    });
    expectExactlyOneProviderCall(r);
  });

  it("SEC-N1-02 / M-N1-DIRECT-STREAM: stream egress is tokenized before provider", async () => {
    const r = await loadProviderBoundaryHarness().run("M-N1-DIRECT-STREAM", {
      method: "generateStream",
      input: "Maria García MRN-A7719",
    });
    expectExactlyOneProviderCall(r);
  });

  it("SEC-N1-03 / M-N1-DIRECT-EMBED: embeddings cross wrapper", async () => {
    const r = await loadProviderBoundaryHarness().run("M-N1-DIRECT-EMBED", {
      method: "embedText",
      input: "078-05-1120 MRN-A7719",
    });
    expectExactlyOneProviderCall(r);
  });

  it("SEC-N2-01 / M-N2-TRACE-BEFORE-SUBSTITUTE: request traces accept safe text only", async () => {
    const r = await loadProviderBoundaryHarness().run("M-N2-TRACE-BEFORE-SUBSTITUTE", {
      input: "Maria García at 412 May Street",
    });
    expectNoCanary(r.tracePayloads);
    expect(r.tracePayloads.join("\n")).toContain("[[Claimant]]");
  });

  it("SEC-N2-02 / M-N2-TRACE-AFTER-REVERSE: output traces remain tokenized", async () => {
    const r = await loadProviderBoundaryHarness().run("M-N2-TRACE-AFTER-REVERSE", {
      providerOutput: "[[Claimant]] lives at [[Address]].",
    });
    expectNoCanary(r.tracePayloads);
    expect(r.displayText).toContain("Maria García");
  });

  it("SEC-L5-01 / M-L5-SKIP-SYSTEM-PROMPT: every known text option path is projected", async () => {
    const r = await loadProviderBoundaryHarness().run("M-L5-SKIP-SYSTEM-PROMPT", {
      optionsVariant: "all-current-text-fields",
      canaryInEachPath: true,
    });
    expectExactlyOneProviderCall(r);
    expect(r.metrics.classifiedPathCount).toBe(r.metrics.expectedTextPathCount);
  });

  it("SEC-L5-02 / M-L5-ALLOW-UNKNOWN-TEXT-FIELD: new text field fails before egress", async () => {
    const r = await loadProviderBoundaryHarness().run("M-L5-ALLOW-UNKNOWN-TEXT-FIELD", {
      options: { futureProviderField: "Maria García" },
      projectorKnowsField: false,
    });
    expectFailedClosed(r, "UNCLASSIFIED_PROVIDER_FIELD");
  });

  it("SEC-L11-01 / M-L11-TOKENIZED-MEANS-PRODUCTION-SAFE: safety gates remain conjunctive", async () => {
    const r = await loadProviderBoundaryHarness().run("M-L11-TOKENIZED-MEANS-PRODUCTION-SAFE", {
      selectedProvider: "anthropic",
      isProductionSafe: false,
      claudeBaaEnabled: false,
      substitutionSucceeded: true,
    });
    expectFailedClosed(r, "PROVIDER_SAFETY_GATE_FAILED");
  });

  it("SEC-L11-02 / M-L11-ROUTE-AFTER-SUBSTITUTE: BAA routing inspects original content", async () => {
    const original = "Claimant Maria García has MRN-A7719.";
    const r = await loadProviderBoundaryHarness().run("M-L11-ROUTE-AFTER-SUBSTITUTE", {
      original,
      substituted: "Claimant [[Claimant]] has [[MRN]].",
      phiTaggedMatter: true,
    });
    expect(r.routerInput).toBe(original);
    expect(r.selectedProvider).toBe("azure-openai-baa");
    expectExactlyOneProviderCall(r);
  });
});
