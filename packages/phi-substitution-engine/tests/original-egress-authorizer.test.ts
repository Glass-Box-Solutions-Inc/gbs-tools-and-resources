import { describe, expect, it } from "vitest";
import {
  createProductionProtectedOriginalEgressAuthorizer,
  isPhiEngineError,
  type AuditPreparationReceipt,
  type AuditPrimaryStore,
  type AuthorizedOriginalEgressDecision,
  type CreateProductionProtectedOriginalEgressAuthorizerOptions,
  type EncryptedAuditSpool,
  type MatterAiContext,
  type OriginalEgressAuthorizationRequest,
  type OriginalEgressPolicyQuery,
  type PhiAuditEvent,
  type PhiAuditPreparedRecord,
} from "../src/index";

const POLICY_VERSION = `sha256:${"a".repeat(64)}`;
const CONTEXT = {
  tenantId: "tenant-gly-355",
  matterId: "matter-gly-355",
  actorId: "actor-gly-355",
  operationId: "operation-gly-355",
  attemptId: "attempt-gly-355",
} as unknown as MatterAiContext;

const REQUEST: OriginalEgressAuthorizationRequest = {
  context: CONTEXT,
  destinationKey: "azure-speech-westus",
  protocol: "WSS",
  contentClass: "audio-stream",
  enginePolicyVersion: POLICY_VERSION,
  purpose: "stream",
};

const DECISION: AuthorizedOriginalEgressDecision = {
  kind: "AUTHORIZED_ORIGINAL",
  decisionId: "decision-gly-355",
  evidenceId: "evidence-gly-355",
  destinationKey: REQUEST.destinationKey,
  protocol: REQUEST.protocol,
  contentClass: REQUEST.contentClass,
  enginePolicyVersion: POLICY_VERSION,
  expiresAt: "2027-08-18T00:00:00.000Z",
};

class Primary implements AuditPrimaryStore {
  public prepared: PhiAuditPreparedRecord[] = [];
  public finalized: PhiAuditEvent[] = [];
  public unavailable = false;
  public finalizeFailures = 0;
  public gate: Promise<void> | undefined;

  public async prepare(record: PhiAuditPreparedRecord) {
    this.prepared.push(record);
    if (this.gate !== undefined) await this.gate;
    return this.unavailable
      ? { status: "unavailable" as const, fixedFailureCode: "down" }
      : { status: "stored" as const, durableRecordId: "audit-gly-355" };
  }

  public finalize(event: PhiAuditEvent): Promise<void> {
    if (this.finalizeFailures > 0) {
      this.finalizeFailures -= 1;
      return Promise.reject(new Error("transient finalize outage"));
    }
    this.finalized.push(event);
    return Promise.resolve();
  }
}

class Spool implements EncryptedAuditSpool {
  public ready = true;
  public prepared: PhiAuditPreparedRecord[] = [];
  public finalized: PhiAuditEvent[] = [];

  public appendPrepared(record: PhiAuditPreparedRecord): Promise<AuditPreparationReceipt> {
    this.prepared.push(record);
    return Promise.resolve({
      attemptId: record.attemptId,
      location: "ENCRYPTED_LOCAL_SPOOL",
      durableRecordId: "spool-gly-355",
    });
  }
  public finalize(_receipt: AuditPreparationReceipt, event: PhiAuditEvent): Promise<void> {
    this.finalized.push(event);
    return Promise.resolve();
  }
  public drainTo() { return Promise.resolve({ examined: 0, delivered: 0, duplicates: 0, remaining: 0 }); }
  public inspectEnvelope(): Promise<never> { return Promise.reject(new Error("not used")); }
  public health(): Promise<"ready" | "unavailable"> {
    return Promise.resolve(this.ready ? "ready" : "unavailable");
  }
}

function rig(decision: AuthorizedOriginalEgressDecision = DECISION) {
  const primary = new Primary();
  const spool = new Spool();
  const queries: OriginalEgressPolicyQuery[] = [];
  const options: CreateProductionProtectedOriginalEgressAuthorizerOptions = {
    engineVersion: "engine-gly-355" as CreateProductionProtectedOriginalEgressAuthorizerOptions["engineVersion"],
    enginePolicyVersion: POLICY_VERSION,
    policy: {
      requireAuthorizedOriginalEgress: async (query) => {
        queries.push(query);
        return decision;
      },
    },
    auditPrimary: primary,
    auditSpool: spool,
    clock: () => "2026-08-18T00:00:00.000Z",
  };
  return {
    primary,
    spool,
    queries,
    authorizer: createProductionProtectedOriginalEgressAuthorizer(options),
  };
}

describe("GLY-355 production original-egress authorizer", () => {
  it("ORACLE-ORIGINAL-EGRESS-ROOT/SHAPE: root factory returns the exact metadata-only authorization", async () => {
    const value = rig();
    expect(Object.getPrototypeOf(value.authorizer)).toBeNull();
    expect(Object.isFrozen(value.authorizer)).toBe(true);
    const authorization = await value.authorizer.authorizeOriginalEgress(REQUEST);
    expect(Object.keys(value.queries[0]!).sort()).toEqual([
      "contentClass", "context", "destinationKey", "enginePolicyVersion", "protocol",
    ]);
    expect(authorization).toMatchObject({
      tenantId: CONTEXT.tenantId,
      matterId: CONTEXT.matterId,
      operationId: CONTEXT.operationId,
      attemptId: CONTEXT.attemptId,
      destinationKey: REQUEST.destinationKey,
      protocol: REQUEST.protocol,
      contentClass: REQUEST.contentClass,
      decisionId: DECISION.decisionId,
      evidenceId: DECISION.evidenceId,
      enginePolicyVersion: POLICY_VERSION,
      expiresAt: DECISION.expiresAt,
    });
    expect(value.primary.prepared).toHaveLength(1);
  });

  it("ORACLE-EVIDENCE-MISMATCH-REJECT/CALLER-BOOLEAN: exact decision binding has no permissive bypass", async () => {
    const value = rig({ ...DECISION, destinationKey: "different-destination" });
    const candidate = { ...REQUEST, baaSatisfied: true } as OriginalEgressAuthorizationRequest;
    await expect(value.authorizer.authorizeOriginalEgress(candidate)).rejects.toMatchObject({
      code: "PROVIDER_SAFETY_GATE_FAILED",
    });
    expect(value.primary.prepared).toHaveLength(0);
  });

  it("ORACLE-EVIDENCE-MISSING-EXPIRED: denial and expired evidence reject before PREPARE", async () => {
    const expired = rig({ ...DECISION, expiresAt: "2025-08-18T00:00:00.000Z" });
    await expect(expired.authorizer.authorizeOriginalEgress(REQUEST)).rejects.toMatchObject({
      code: "PROVIDER_SAFETY_GATE_FAILED",
    });
    expect(expired.primary.prepared).toHaveLength(0);

    const denied = rig();
    const authorizer = createProductionProtectedOriginalEgressAuthorizer({
      engineVersion: "engine-gly-355" as CreateProductionProtectedOriginalEgressAuthorizerOptions["engineVersion"],
      enginePolicyVersion: POLICY_VERSION,
      policy: { requireAuthorizedOriginalEgress: () => Promise.reject(new Error("raw denial")) },
      auditPrimary: denied.primary,
      auditSpool: denied.spool,
      clock: () => "2026-08-18T00:00:00.000Z",
    });
    await expect(authorizer.authorizeOriginalEgress(REQUEST)).rejects.toMatchObject({
      code: "PROVIDER_SAFETY_GATE_FAILED",
      message: "PROVIDER_SAFETY_GATE_FAILED",
    });
  });

  it("ORACLE-AUTH-AWAITS-PREPARE: authorization cannot resolve while durable PREPARE is pending", async () => {
    const value = rig();
    let release!: () => void;
    value.primary.gate = new Promise<void>((resolve) => { release = resolve; });
    let settled = false;
    const pending = value.authorizer.authorizeOriginalEgress(REQUEST).then((authorization) => {
      settled = true;
      return authorization;
    });
    await Promise.resolve();
    await Promise.resolve();
    expect(value.primary.prepared).toHaveLength(1);
    expect(settled).toBe(false);
    release();
    await pending;
  });

  it("ORACLE-AUDIT-DURABILITY-FAIL-CLOSED: primary plus spool outage rejects authorization", async () => {
    const value = rig();
    value.primary.unavailable = true;
    value.spool.ready = false;
    await expect(value.authorizer.authorizeOriginalEgress(REQUEST)).rejects.toSatisfy((error: unknown) =>
      isPhiEngineError(error) && error.code === "AUDIT_DURABILITY_UNAVAILABLE",
    );
  });

  it("ORACLE-SECOND-AUTHORIZATION-PER-ATTEMPT: one attempt receives one capability and one PREPARE", async () => {
    const value = rig();
    await value.authorizer.authorizeOriginalEgress(REQUEST);
    await expect(value.authorizer.authorizeOriginalEgress(REQUEST)).rejects.toMatchObject({
      code: "PROVIDER_SAFETY_GATE_FAILED",
    });
    expect(value.primary.prepared).toHaveLength(1);
  });

  it("ORACLE-DESTINATION-KEY-GRAMMAR: unsafe destination metadata rejects before policy and PREPARE", async () => {
    const value = rig();
    await expect(value.authorizer.authorizeOriginalEgress({
      ...REQUEST,
      destinationKey: " unsafe destination ",
    })).rejects.toMatchObject({ code: "PROVIDER_SAFETY_GATE_FAILED" });
    expect(value.queries).toHaveLength(0);
    expect(value.primary.prepared).toHaveLength(0);
  });

  it("ORACLE-AUTH-FINALIZE-ONCE/NONSERIALIZABLE: capability throws on serialization and second finalization", async () => {
    const value = rig();
    const authorization = await value.authorizer.authorizeOriginalEgress(REQUEST);
    expect(() => JSON.stringify(authorization)).toThrowError("PROVIDER_SAFETY_GATE_FAILED");
    await authorization.finalize("completed");
    expect(value.primary.finalized).toHaveLength(1);
    await expect(authorization.finalize("completed")).rejects.toMatchObject({
      code: "PROVIDER_SAFETY_GATE_FAILED",
    });
    expect(value.primary.finalized).toHaveLength(1);
  });

  it("ORACLE-FINALIZE-DURABILITY-RETRY: a failed terminal write can retry through emitter idempotency", async () => {
    const value = rig();
    const authorization = await value.authorizer.authorizeOriginalEgress(REQUEST);
    value.primary.finalizeFailures = 1;
    await expect(authorization.finalize("completed")).rejects.toMatchObject({
      code: "AUDIT_DURABILITY_UNAVAILABLE",
    });
    expect(value.primary.finalized).toHaveLength(0);
    await authorization.finalize("completed");
    expect(value.primary.finalized).toHaveLength(1);
  });
});
