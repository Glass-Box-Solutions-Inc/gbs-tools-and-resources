import { describe, expect, it } from "vitest";
import { loadDictionaryHarness } from "./implementation-under-test";
import { expectFailedClosed, expectNoCanary } from "./test-helpers";

describe("phase-1 dictionary compiler, cache, versioning, and orchestration", () => {
  it("SEC-L2-01 / M-L2-TTL-ONLY-INVALIDATION: committed tagged write blocks stale dictionary", async () => {
    const r = await loadDictionaryHarness().run("M-L2-TTL-ONLY-INVALIDATION", {
      readyVersion: "7",
      committedVersion: "8",
      oldValue: "Maria García",
      newValue: "Maria Santos",
    });
    expectFailedClosed(r, "DICTIONARY_NOT_READY");
    expect(r.dictionaryVersion).toBe("8");
  });

  it("SEC-L2-02 / M-L2-SERVE-OLD-WHILE-BUILDING: old READY version cannot serve", async () => {
    const r = await loadDictionaryHarness().run("M-L2-SERVE-OLD-WHILE-BUILDING", {
      active: { version: "8", status: "BUILDING" },
      prior: { version: "7", status: "READY" },
    });
    expectFailedClosed(r, "DICTIONARY_NOT_READY");
  });

  it("SEC-N4-01 / M-N4-RAW-FALLBACK-DICTIONARY: dictionary outage never invokes raw provider", async () => {
    const r = await loadDictionaryHarness().run("M-N4-RAW-FALLBACK-DICTIONARY", {
      dictionaryHealth: "unavailable",
      rawText: "Maria García MRN-A7719",
    });
    expectFailedClosed(r, "DICTIONARY_UNAVAILABLE");
  });

  it("SEC-N4-02 / M-N4-MISSING-CONTEXT-MEANS-OFF: missing trusted policy fails closed", async () => {
    const r = await loadDictionaryHarness().run("M-N4-MISSING-CONTEXT-MEANS-OFF", {
      context: null,
      callerPhiFlag: false,
    });
    expectFailedClosed(r, "MISSING_TRUSTED_CONTEXT");
  });

  it("SEC-L8-01 / M-L8-DROP-TENANT-FROM-CACHE-KEY: compiled cache is tenant isolated", async () => {
    const r = await loadDictionaryHarness().run("M-L8-DROP-TENANT-FROM-CACHE-KEY", {
      tenantA: { matter: "same-id", version: "4", value: "Maria García" },
      tenantB: { matter: "same-id", version: "4", value: "Robert O'Neil" },
    });
    expectNoCanary(r.providerPayloads);
    expect(r.metrics.crossTenantCacheHit).toBe(false);
  });

  it("PERF-L9-01 / M-L9-RECOMPILE-PER-CALL: warm dictionary is reused", async () => {
    const r = await loadDictionaryHarness().run("M-L9-RECOMPILE-PER-CALL", {
      identicalCalls: 100,
      warmed: true,
      payloadBytes: 32768,
    });
    expect(r.compileCount).toBe(0);
    expect(r.metrics.p50Ms).toBeLessThan(5);
    expect(r.metrics.p99Ms).toBeLessThan(20);
  });

  it("SEC-L12-01 / M-L12-DETECTOR-OVERRIDES-DICTIONARY: exact dictionary identity wins", async () => {
    const r = await loadDictionaryHarness().run("M-L12-DETECTOR-OVERRIDES-DICTIONARY", {
      text: "Maria García appeared.",
      dictionary: { span: [0, 12], token: "[[Claimant]]" },
      detector: { span: [0, 12], token: "[[Detected_Person_1]]", confidence: 0.99 },
    });
    expect(r.tokenizedText).toBe("[[Claimant]] appeared.");
    expect(r.reversedText).toBe("Maria García appeared.");
  });

  it("SEC-L3-ORDER: candidate order, cache state, and restart do not change bytes", async () => {
    const r = await loadDictionaryHarness().run("DETERMINISM-ENTRY-ORDER", {
      entryOrderSeeds: [1, 2, 3, 5, 8, 13],
      cacheStates: ["cold", "warm", "restarted"],
    });
    expect(new Set(r.outputs).size).toBe(1);
  });

  it("SEC-PHILEAS-POLICY-ISOLATION: prepared policy key includes tenant/matter/version", async () => {
    const r = await loadDictionaryHarness().run("M-PHILEAS-POLICY-NAME-ONLY", {
      samePolicyName: "default",
      tenants: ["tenant-a", "tenant-b"],
      matters: ["matter-1", "matter-1"],
      versions: ["3", "4"],
    });
    expect(r.metrics.preparedPolicyIsolation).toBe(true);
    expect(r.metrics.sharedDictionaryContainsMatterValues).toBe(false);
  });
});
