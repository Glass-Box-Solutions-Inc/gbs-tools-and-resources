import { describe, expect, it } from "vitest";
import { loadAuditHarness } from "./implementation-under-test";
import { expectExactlyOneProviderCall, expectFailedClosed, expectNoCanary, serialized } from "./test-helpers";

describe("metadata-only audit, primary durability, and encrypted local spool", () => {
  it("SEC-N3-01 / M-N3-AUDIT-INCLUDES-VALUE: exact recursive allow-list rejects sensitive fields", async () => {
    const r = await loadAuditHarness().run("M-N3-AUDIT-INCLUDES-VALUE", {
      extraKeys: ["matchedValue", "excerpt", "offsetText", "valueFingerprint", "tokenMap"],
    });
    expect(r.auditEvents).toHaveLength(0);
    expect(r.errorCode).toBe("AUDIT_SCHEMA_REJECTED");
  });

  it("SEC-N3-02 / M-N3-SKIP-FAILED-AUDIT: failed-closed attempts are audited", async () => {
    const r = await loadAuditHarness().run("M-N3-SKIP-FAILED-AUDIT", {
      dictionaryHealth: "unavailable",
      attemptId: "attempt-1",
    });
    expect(r.providerCalls).toBe(0);
    expect(r.auditEvents).toHaveLength(1);
    expect(serialized(r.auditEvents[0])).toContain("failed_closed");
  });

  it("SEC-N3-03 / M-N3-OMIT-REQUIRED-FIELD: audit requires versions, total counts, latency, outcome", async () => {
    const r = await loadAuditHarness().run("M-N3-OMIT-REQUIRED-FIELD", {
      omitEach: ["dictionaryVersion", "engineVersion", "counts", "latencyMs", "outcome"],
    });
    expect(r.buildPassed).toBe(false);
    expect(r.diagnostics).toContain("AUDIT_REQUIRED_FIELD_MISSING");
  });

  it("SEC-N3-04 / M-N3-EMIT-PREPARED-AND-FINAL: one logical event per attempt", async () => {
    const r = await loadAuditHarness().run("M-N3-EMIT-PREPARED-AND-FINAL", {
      attemptId: "attempt-2",
      primaryAvailable: true,
    });
    expect(r.auditEvents).toHaveLength(1);
    expect(serialized(r.auditEvents[0])).not.toContain("PREPARED");
  });

  it("SEC-N4-04A / M-N4-AUDIT-PRIMARY-DOWN-SPOOL-PROCEEDS: primary outage durably spools and calls provider", async () => {
    const r = await loadAuditHarness().run("M-N4-AUDIT-PRIMARY-DOWN-SPOOL-PROCEEDS", {
      primaryAvailable: false,
      spoolAvailable: true,
      attemptId: "attempt-3",
    });
    expect(r.primaryAuditAttempts).toBe(1);
    expect(r.spoolRecords).toHaveLength(1);
    expect(r.spoolRecords[0]?.attemptId).toBe("attempt-3");
    expectExactlyOneProviderCall(r);
  });

  it("SEC-N4-04B / M-N4-AUDIT-PRIMARY-AND-SPOOL-DOWN: no durability anywhere fails closed", async () => {
    const r = await loadAuditHarness().run("M-N4-AUDIT-PRIMARY-AND-SPOOL-DOWN", {
      primaryAvailable: false,
      spoolAvailable: false,
    });
    expectFailedClosed(r, "AUDIT_DURABILITY_UNAVAILABLE");
  });

  it("SEC-N4-04-LEGACY / M-N4-AUDIT-OUTBOX-BEST-EFFORT: errors are never ignored when both durability paths fail", async () => {
    const r = await loadAuditHarness().run("M-N4-AUDIT-OUTBOX-BEST-EFFORT", {
      primaryAvailable: false,
      spoolAvailable: false,
      mutationBehavior: "ignore-durability-and-call-provider",
    });
    expectFailedClosed(r, "AUDIT_DURABILITY_UNAVAILABLE");
  });

  it("SEC-N3-05 / M-N3-SPOOL-DRAIN-LOSES-OR-DUPLICATES: drain is lossless and idempotent", async () => {
    const r = await loadAuditHarness().run("M-N3-SPOOL-DRAIN-LOSES-OR-DUPLICATES", {
      spooledAttemptIds: ["a1", "a2", "a3"],
      existingPrimaryAttemptIds: ["a2"],
      drainTwice: true,
    });
    expect(r.drain).toEqual({ delivered: 2, duplicates: 1, remaining: 0 });
    expect(r.auditEvents).toHaveLength(3);
  });

  it("SEC-N3-06 / M-N3-SPOOL-PLAINTEXT-OR-SENSITIVE: spool is encrypted and metadata-only", async () => {
    const r = await loadAuditHarness().run("M-N3-SPOOL-PLAINTEXT-OR-SENSITIVE", {
      primaryAvailable: false,
      inputCanaries: true,
      cipherSuite: "AES-256-GCM",
      storage: "durable-azure-mounted-volume",
      atomicPublishAndFlush: true,
    });
    expect(r.spoolRecords).toHaveLength(1);
    expect(r.spoolRecords[0]?.plaintextOnDisk).toBeNull();
    expect(r.spoolRecords[0]?.ciphertextBytes).toBeGreaterThan(0);
    expectNoCanary([serialized(r.spoolRecords[0]?.decrypted)]);
    expect(r.metrics.survivesReplicaRestart).toBe(true);
  });

  it("SEC-N3-07: explicit zeroes exist for every identifier class", async () => {
    const r = await loadAuditHarness().run("AUDIT-TOTAL-COUNT-RECORD", {
      matchedClasses: { PERSON_NAME: 1 },
    });
    const event = serialized(r.auditEvents[0]);
    for (const identifierClass of [
      "PERSON_NAME", "DOB", "SSN", "MRN", "DEA", "EMAIL", "PHONE", "ADDRESS",
      "CLAIM_NUMBER", "POLICY_NUMBER", "ACCOUNT_NUMBER", "OTHER_TAGGED",
    ]) {
      expect(event).toContain(identifierClass);
    }
  });
});
