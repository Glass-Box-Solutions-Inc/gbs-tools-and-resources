import { describe, expect, it } from "vitest";
import { loadDetectorHarness } from "./implementation-under-test";
import { expectFailedClosed, expectNoCanary } from "./test-helpers";

describe("vendor-neutral Phileas/Azure detector-redactor port", () => {
  it("SEC-PHASE1-01: detector is not called when trusted policy says DISABLED_PHASE_1", async () => {
    const r = await loadDetectorHarness().run("PHASE1-DETECTOR-DISABLED", {
      detectorRequirement: "DISABLED_PHASE_1",
      configuredPrimary: "phileas-4-gliner",
      input: "An untagged name appears only in text.",
    });
    expect(r.detectorCalls).toBe(0);
    expect(r.detectorName).toBeNull();
  });

  it("SEC-PHILEAS-01: Phileas adapter returns versioned typed spans and never logs bodies", async () => {
    const r = await loadDetectorHarness().run("PHILEAS-WIRE-CONTRACT", {
      descriptor: {
        name: "phileas-4-gliner",
        engineVersion: "4.2.0",
        modelVersion: "gliner-pinned",
        localProcessing: true,
      },
      text: "Maria García",
      responseOffsetEncoding: "UTF16",
    });
    expect(r.detectorName).toBe("phileas-4-gliner");
    expect(r.detectorRequestBodiesLogged).toBe(0);
    expect(r.metrics.localProcessing).toBe(true);
    expect(r.metrics.engineVersion).toBe("4.2.0");
  });

  it("SEC-PHILEAS-02: explicit replacement plan is applied exactly, not invented by FPE/context", async () => {
    const r = await loadDetectorHarness().run(
      "PHILEAS-EXPLICIT-REPLACEMENT-PLAN",
      {
        text: "Maria García, MRN-A7719",
        instructions: [
          { id: "s1", span: [0, 12], token: "[[Detected_Person_1]]" },
          { id: "s2", span: [14, 23], token: "[[Detected_MRN_1]]" },
        ],
        forbidNativeReplacementAsAuthority: true,
      },
    );
    expect(r.tokenizedText).toBe("[[Detected_Person_1]], [[Detected_MRN_1]]");
    expect(r.appliedSpanIds).toEqual(["s1", "s2"]);
    expect(r.tokenizedText).not.toMatch(/^[A-Za-z0-9-]+$/);
  });

  it("SEC-L12-02 / M-L12-TRUST-INVALID-DETECTOR-OFFSET: invalid offsets fail closed", async () => {
    const r = await loadDetectorHarness().run(
      "M-L12-TRUST-INVALID-DETECTOR-OFFSET",
      {
        text: "A😀B Maria García",
        rawSpans: [
          { id: "inside-surrogate", start: 2, end: 3, encoding: "UTF16" },
          { id: "out-of-range", start: 100, end: 120, encoding: "UTF16" },
        ],
      },
    );
    expectFailedClosed(r, "INVALID_DETECTOR_OFFSET");
  });

  it("SEC-N4-03 / M-N4-BELT-FAIL-OPEN: required belt outage fails closed", async () => {
    const r = await loadDetectorHarness().run("M-N4-BELT-FAIL-OPEN", {
      detectorRequirement: "REQUIRED",
      primary: "unavailable",
      fallback: "unavailable",
      freeTextCanary: "Robert O'Neil",
    });
    expectFailedClosed(r, "DETECTOR_UNAVAILABLE");
  });

  it("PERF-L9-02 / M-L9-BELT-NO-DEADLINE: primary and fallback share one deadline", async () => {
    const r = await loadDetectorHarness().run("M-L9-BELT-NO-DEADLINE", {
      deadlineMs: 100,
      primaryDelayMs: 90,
      fallbackDelayMs: 90,
      sequentialFallbackWouldExceed: true,
    });
    expect(r.latencyMs).toBeLessThanOrEqual(110);
    expect(r.errorCode).toBe("DETECTOR_UNAVAILABLE");
    expect(r.providerCalls).toBe(0);
  });

  it("SEC-L7-02 / M-L7-UNPIN-DETECTOR-VERSION: response artifact equals evaluated artifact", async () => {
    const r = await loadDetectorHarness().run("M-L7-UNPIN-DETECTOR-VERSION", {
      evaluated: {
        engine: "4.2.0",
        model: "gliner-a",
        recognizers: "wc-7",
        configDigest: "sha256:abc",
      },
      deployed: {
        engine: "4.2.0",
        model: "gliner-b",
        recognizers: "wc-7",
        configDigest: "sha256:abc",
      },
    });
    expect(r.buildPassed).toBe(false);
    expect(r.diagnostics).toContain("DETECTOR_ARTIFACT_MISMATCH");
  });

  it("SEC-AZURE-01: Azure fallback is replaceable and independently eligible", async () => {
    const r = await loadDetectorHarness().run("AZURE-INDEPENDENT-FALLBACK", {
      primary: "phileas-4-gliner",
      primaryHealth: "unavailable",
      fallback: "azure-ai-language-phi",
      fallbackEligible: true,
      residencyApproved: true,
      baaApproved: true,
    });
    expect(r.detectorName).toBe("azure-ai-language-phi");
    expectNoCanary(r.providerPayloads);
  });
});
