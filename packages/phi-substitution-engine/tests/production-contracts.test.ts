import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import type { PhiAuditEvent } from "../src/audit/ports";
import { ExactAllowListAuditSerializer } from "../src/audit/serializer";
import { isPhiEngineFailureCode } from "../src/core/errors";

function interruptedEvent(): PhiAuditEvent {
  return {
    eventType: "AI_SUBSTITUTION_ATTEMPT",
    attemptId: "attempt-gly-353" as PhiAuditEvent["attemptId"],
    operationId: "operation-gly-353" as PhiAuditEvent["operationId"],
    tenantId: "tenant-gly-353" as PhiAuditEvent["tenantId"],
    matterId: "matter-gly-353" as PhiAuditEvent["matterId"],
    actorId: "actor-gly-353" as PhiAuditEvent["actorId"],
    operation: "generation",
    dictionaryVersion: null,
    engineVersion: "engine-gly-353" as PhiAuditEvent["engineVersion"],
    counts: {
      PERSON_NAME: 0,
      DOB: 0,
      SSN: 0,
      MRN: 0,
      DEA: 0,
      EMAIL: 0,
      PHONE: 0,
      ADDRESS: 0,
      CLAIM_NUMBER: 0,
      POLICY_NUMBER: 0,
      ACCOUNT_NUMBER: 0,
      OTHER_TAGGED: 0,
    },
    ambiguityCount: 0,
    detectorName: null,
    detectorVersion: null,
    latencyMs: { dictionary: 0, detector: 0, total: 0 },
    outcome: "interrupted",
    failureCode: null,
    occurredAt: "2026-08-18T00:00:00.000Z",
  };
}

describe("GLY-353 production contracts", () => {
  it("ORACLE-PROD-ROOT-CANONICALIZATION-INTERNAL: evidence helpers are not runtime-root capabilities", async () => {
    const root = await import("../src/index") as Record<string, unknown>;
    expect(root["canonicalizeAzureEgressPolicySignedClaims"]).toBeUndefined();
    expect(root["computeAzureEgressPolicySignedClaimsDigest"]).toBeUndefined();
    expect(root["computeEnginePolicyVersion"]).toBeUndefined();
  });

  it("ORACLE-PROD-INTERRUPTED-OUTCOME: interruption is an audit outcome, not a terminal failure code", () => {
    const serializer = new ExactAllowListAuditSerializer();
    const encoded = new TextDecoder().decode(serializer.serialize(interruptedEvent()));

    expect(encoded).toContain('"outcome":"interrupted"');
    expect(encoded).toContain('"failureCode":null');
    expect(isPhiEngineFailureCode("CALL_INTERRUPTED")).toBe(true);
    expect(() => serializer.serialize({
      ...interruptedEvent(),
      failureCode: "CALL_INTERRUPTED",
    } as PhiAuditEvent)).toThrow();
  });

  it("ORACLE-PROD-ABORT-ONCE-LATCH-SHAPE: terminal transitions cannot overwrite an earlier winner", () => {
    const source = readFileSync(new URL("../src/core/wrapper.ts", import.meta.url), "utf8");
    expect(source).toContain('if (this.#terminal === null) this.#terminal = "failure";');
    expect(source).toContain('if (this.#terminal !== null) return;\n    this.#terminal = "interrupted";');
    expect(source).toContain('if (this.#terminal !== null) return false;\n    this.#terminal = "completed";');
  });
});
