import { describe, expect, it } from "vitest";
import { loadEvaluationHarness } from "./implementation-under-test";

const PHASE1_COPY = "Client identifiers on file are replaced before AI processing.";

describe("evaluation gates and evidence-bound claims", () => {
  it("SEC-N6-01 / M-N6-OVERCLAIM-ALL-PHI: claims registry rejects unproved copy", async () => {
    const r = await loadEvaluationHarness().run("M-N6-OVERCLAIM-ALL-PHI", {
      requestedCopy: "All PHI is removed before AI processing.",
      phase: 1,
    });
    expect(r.outputs).not.toContain("All PHI is removed before AI processing.");
    expect(r.outputs).toEqual([PHASE1_COPY]);
  });

  it("EVAL-N6-02 / M-N6-CLAIM-WITH-FAILED-CLASS: failed class blocks free-text claim", async () => {
    const r = await loadEvaluationHarness().run("M-N6-CLAIM-WITH-FAILED-CLASS", {
      byClass: {
        SSN: { recallLower: 0.995 },
        DEA: { recallLower: 0.0 },
        PERSON_NAME: { recallLower: 0.99 },
      },
      requestedPhase2Copy: true,
    });
    expect(r.outputs).toEqual([PHASE1_COPY]);
  });

  it("EVAL-L7-01 / M-L7-GATE-ON-MACRO-AVERAGE: minimum class gate beats average", async () => {
    const r = await loadEvaluationHarness().run("M-L7-GATE-ON-MACRO-AVERAGE", {
      macroRecall: 0.999,
      classes: { DEA: { recallPoint: 0, recallLower: 0 }, SSN: { recallPoint: 1, recallLower: 0.999 } },
    });
    expect(r.metrics.eligible).toBe(false);
    expect(r.diagnostics).toContain("CLASS_GATE_FAILED:DEA");
  });

  it("PERF-L9-03: interactive artifact passes P95 and P99 budgets at 32 KiB", async () => {
    const r = await loadEvaluationHarness().run("DETECTOR-LATENCY-ENVELOPE", {
      bytes: 32768,
      requiredP95MsExclusive: 100,
      requiredP99MsInclusive: 100,
    });
    expect(r.metrics.p95Ms).toBeLessThan(100);
    expect(r.metrics.p99Ms).toBeLessThanOrEqual(100);
  });

  it("SEC-CLAIMS-IMAGE-BOUNDARY: phase-1 copy cannot imply image substitution", async () => {
    const r = await loadEvaluationHarness().run("CLAIM-MULTIMODAL-CARVEOUT", {
      claim: PHASE1_COPY,
      documentedCarveouts: ["multimodal-image-egress"],
    });
    expect(r.metrics.imageCoverageClaimed).toBe(false);
    expect(r.outputs).toEqual([PHASE1_COPY]);
  });
});
