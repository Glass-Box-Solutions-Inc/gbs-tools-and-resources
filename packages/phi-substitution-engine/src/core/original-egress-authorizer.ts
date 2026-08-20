import type { EngineVersion } from "./brands";
import type { AiOperation, MatterAiContext, PhiEngineFailureCode } from "./contracts";
import type {
  AuditPreparationReceipt,
  AuditPrimaryStore,
  EncryptedAuditSpool,
  PhiAuditOutcome,
  PhiAuditPreparedRecord,
} from "../audit/ports";
import { DurablePhiAuditEmitter } from "../audit/emitter";
import { ExactAllowListAuditSerializer } from "../audit/serializer";
import { preparedToTerminalEvent } from "../audit/event-factory";
import { toTotalIdentifierCounts } from "../audit/counts";
import { isPhiEngineError, isPhiEngineFailureCode, PhiEngineError } from "./errors";

export type OriginalEgressProtocol = "HTTPS" | "WSS";
export type OriginalEgressContentClass = "case-identifier" | "tts-text" | "audio-stream";

export interface OriginalEgressPolicyQuery {
  readonly context: MatterAiContext;
  readonly destinationKey: string;
  readonly protocol: OriginalEgressProtocol;
  readonly contentClass: OriginalEgressContentClass;
  readonly enginePolicyVersion: string;
}

export interface AuthorizedOriginalEgressDecision {
  readonly kind: "AUTHORIZED_ORIGINAL";
  readonly decisionId: string;
  readonly evidenceId: string;
  readonly destinationKey: string;
  readonly protocol: OriginalEgressProtocol;
  readonly contentClass: OriginalEgressContentClass;
  readonly enginePolicyVersion: string;
  readonly expiresAt: string;
}

export interface OriginalEgressPolicyPort {
  requireAuthorizedOriginalEgress(
    query: OriginalEgressPolicyQuery,
  ): Promise<AuthorizedOriginalEgressDecision>;
}

export interface OriginalEgressAuthorizationRequest extends OriginalEgressPolicyQuery {
  readonly purpose: AiOperation;
}

export interface OriginalEgressAuthorization {
  readonly tenantId: MatterAiContext["tenantId"];
  readonly matterId: MatterAiContext["matterId"];
  readonly operationId: MatterAiContext["operationId"];
  readonly attemptId: MatterAiContext["attemptId"];
  readonly destinationKey: string;
  readonly protocol: OriginalEgressProtocol;
  readonly contentClass: OriginalEgressContentClass;
  readonly decisionId: string;
  readonly evidenceId: string;
  readonly enginePolicyVersion: string;
  readonly expiresAt: string;
  finalize(outcome: PhiAuditOutcome, failureCode?: PhiEngineFailureCode): Promise<void>;
  toJSON(): never;
}

export interface ProtectedOriginalEgressAuthorizer {
  authorizeOriginalEgress(
    request: OriginalEgressAuthorizationRequest,
  ): Promise<OriginalEgressAuthorization>;
}

export interface CreateProductionProtectedOriginalEgressAuthorizerOptions {
  readonly engineVersion: EngineVersion;
  readonly enginePolicyVersion: string;
  readonly policy: OriginalEgressPolicyPort;
  readonly auditPrimary: AuditPrimaryStore;
  readonly auditSpool: EncryptedAuditSpool;
  readonly clock?: () => string;
}

const ENGINE_VERSION = /^[A-Za-z0-9._-]{1,64}$/;
const ENGINE_POLICY_VERSION = /^sha256:[0-9a-f]{64}$/;
const SAFE_RESULT_IDENTIFIER = /^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$/;
const ISO_8601_UTC = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?Z$/;
const PURPOSES: readonly AiOperation[] = ["generation", "stream", "embedding", "graph_extraction"];
const AUDIT_OUTCOMES: readonly PhiAuditOutcome[] = [
  "completed", "cancelled", "interrupted", "failed_closed", "reversal_failed", "unknown_after_send",
];
const PROTOCOLS: readonly OriginalEgressProtocol[] = ["HTTPS", "WSS"];
const CONTENT_CLASSES: readonly OriginalEgressContentClass[] = [
  "case-identifier",
  "tts-text",
  "audio-stream",
];

function includes<T extends string>(values: readonly T[], candidate: unknown): candidate is T {
  if (typeof candidate !== "string") return false;
  for (let index = 0; index < values.length; index += 1) {
    if (values[index] === candidate) return true;
  }
  return false;
}

function reject(request: Pick<OriginalEgressAuthorizationRequest, "context">): never {
  throw new PhiEngineError("PROVIDER_SAFETY_GATE_FAILED", request.context.operationId);
}

function snapshotRequest(input: OriginalEgressAuthorizationRequest): OriginalEgressAuthorizationRequest {
  try {
    const context = input.context;
    const tenantId = context.tenantId;
    const matterId = context.matterId;
    const actorId = context.actorId;
    const operationId = context.operationId;
    const attemptId = context.attemptId;
    const destinationKey = input.destinationKey;
    const protocol = input.protocol;
    const contentClass = input.contentClass;
    const enginePolicyVersion = input.enginePolicyVersion;
    const purpose = input.purpose;
    if (
      typeof tenantId !== "string" || typeof matterId !== "string" || typeof actorId !== "string" ||
      typeof operationId !== "string" || typeof attemptId !== "string" ||
      typeof destinationKey !== "string" || !SAFE_RESULT_IDENTIFIER.test(destinationKey) ||
      !includes(PROTOCOLS, protocol) || !includes(CONTENT_CLASSES, contentClass) ||
      !ENGINE_POLICY_VERSION.test(enginePolicyVersion) || !includes(PURPOSES, purpose)
    ) throw new Error();
    return Object.freeze({
      context: Object.freeze({ tenantId, matterId, actorId, operationId, attemptId }),
      destinationKey,
      protocol,
      contentClass,
      enginePolicyVersion,
      purpose,
    });
  } catch {
    throw new PhiEngineError("PROVIDER_SAFETY_GATE_FAILED");
  }
}

function snapshotDecision(
  candidate: AuthorizedOriginalEgressDecision,
  request: OriginalEgressAuthorizationRequest,
): AuthorizedOriginalEgressDecision {
  try {
    const decision = Object.freeze({
      kind: candidate.kind,
      decisionId: candidate.decisionId,
      evidenceId: candidate.evidenceId,
      destinationKey: candidate.destinationKey,
      protocol: candidate.protocol,
      contentClass: candidate.contentClass,
      enginePolicyVersion: candidate.enginePolicyVersion,
      expiresAt: candidate.expiresAt,
    });
    if (
      decision.kind !== "AUTHORIZED_ORIGINAL" ||
      typeof decision.decisionId !== "string" || decision.decisionId.length === 0 ||
      typeof decision.evidenceId !== "string" || decision.evidenceId.length === 0 ||
      typeof decision.expiresAt !== "string" || !ISO_8601_UTC.test(decision.expiresAt)
    ) reject(request);
    return decision;
  } catch (error) {
    if (isPhiEngineError(error)) throw error;
    reject(request);
  }
}

function decisionMatches(
  decision: AuthorizedOriginalEgressDecision,
  request: OriginalEgressAuthorizationRequest,
): boolean {
  return decision.destinationKey === request.destinationKey &&
    decision.protocol === request.protocol &&
    decision.contentClass === request.contentClass &&
    decision.enginePolicyVersion === request.enginePolicyVersion;
}

function snapshotOptions(
  input: CreateProductionProtectedOriginalEgressAuthorizerOptions,
): Required<CreateProductionProtectedOriginalEgressAuthorizerOptions> {
  try {
    const engineVersion = input.engineVersion;
    const enginePolicyVersion = input.enginePolicyVersion;
    const policy = input.policy;
    const auditPrimary = input.auditPrimary;
    const auditSpool = input.auditSpool;
    const clock = input.clock ?? ((): string => new Date().toISOString());
    if (typeof engineVersion !== "string" || !ENGINE_VERSION.test(engineVersion)) throw new Error();
    if (typeof enginePolicyVersion !== "string" || !ENGINE_POLICY_VERSION.test(enginePolicyVersion)) throw new Error();
    if (typeof policy?.requireAuthorizedOriginalEgress !== "function") throw new Error();
    if (typeof auditPrimary?.prepare !== "function" || typeof auditPrimary?.finalize !== "function") throw new Error();
    if (
      typeof auditSpool?.appendPrepared !== "function" || typeof auditSpool?.finalize !== "function" ||
      typeof auditSpool?.drainTo !== "function" || typeof auditSpool?.inspectEnvelope !== "function" ||
      typeof auditSpool?.health !== "function" || typeof clock !== "function"
    ) throw new Error();
    return { engineVersion, enginePolicyVersion, policy, auditPrimary, auditSpool, clock };
  } catch {
    throw new PhiEngineError("PROVIDER_SAFETY_GATE_FAILED");
  }
}

function preparedRecord(
  request: OriginalEgressAuthorizationRequest,
  engineVersion: EngineVersion,
  preparedAt: string,
): PhiAuditPreparedRecord {
  return {
    state: "PREPARED",
    attemptId: request.context.attemptId,
    operationId: request.context.operationId,
    tenantId: request.context.tenantId,
    matterId: request.context.matterId,
    actorId: request.context.actorId,
    operation: request.purpose,
    dictionaryVersion: null,
    engineVersion,
    counts: toTotalIdentifierCounts({}),
    ambiguityCount: 0,
    detectorName: null,
    detectorVersion: null,
    latencyMs: { dictionary: 0, detector: 0, total: 0 },
    preparedAt,
  };
}

function asEpoch(instant: string): number | null {
  if (!ISO_8601_UTC.test(instant)) return null;
  const epoch = Date.parse(instant);
  return Number.isFinite(epoch) ? epoch : null;
}

function authorizationHandle(
  request: OriginalEgressAuthorizationRequest,
  decision: AuthorizedOriginalEgressDecision,
  receipt: AuditPreparationReceipt,
  audit: DurablePhiAuditEmitter,
  prepared: PhiAuditPreparedRecord,
  clock: () => string,
): OriginalEgressAuthorization {
  let finalized = false;
  let finalizing = false;
  const handle = Object.assign(Object.create(null) as object, {
    tenantId: request.context.tenantId,
    matterId: request.context.matterId,
    operationId: request.context.operationId,
    attemptId: request.context.attemptId,
    destinationKey: decision.destinationKey,
    protocol: decision.protocol,
    contentClass: decision.contentClass,
    decisionId: decision.decisionId,
    evidenceId: decision.evidenceId,
    enginePolicyVersion: decision.enginePolicyVersion,
    expiresAt: decision.expiresAt,
    finalize: async (outcome: PhiAuditOutcome, failureCode?: PhiEngineFailureCode): Promise<void> => {
      if (finalized || finalizing) reject(request);
      if (!includes(AUDIT_OUTCOMES, outcome)) reject(request);
      if (failureCode !== undefined && !isPhiEngineFailureCode(failureCode)) reject(request);
      const occurredAt = clock();
      const safeFailure = failureCode === undefined ? null : failureCode;
      finalizing = true;
      try {
        await audit.finalize(receipt, preparedToTerminalEvent(prepared, outcome, safeFailure, occurredAt));
        // The handle owns concurrent/finalize-once admission; the emitter owns durable idempotency.
        // Latch only after persistence so a transient terminal-write failure remains retryable.
        finalized = true;
      } catch {
        throw new PhiEngineError("AUDIT_DURABILITY_UNAVAILABLE", request.context.operationId);
      } finally {
        finalizing = false;
      }
    },
    toJSON: (): never => {
      throw new PhiEngineError("PROVIDER_SAFETY_GATE_FAILED", request.context.operationId);
    },
  });
  return Object.freeze(handle) as OriginalEgressAuthorization;
}

/** Production-only, selective original-egress authorization. It never accepts original content. */
export function createProductionProtectedOriginalEgressAuthorizer(
  options: CreateProductionProtectedOriginalEgressAuthorizerOptions,
): ProtectedOriginalEgressAuthorizer {
  const deps = snapshotOptions(options);
  const audit = new DurablePhiAuditEmitter(
    deps.auditPrimary,
    deps.auditSpool,
    new ExactAllowListAuditSerializer(),
    deps.clock,
  );
  // Kept for the authorizer lifetime: a finalized operation must never obtain a second capability.
  // Reserve before any await so concurrent calls cannot both reach emitter.prepare/#inFlight.set.
  const issuedAttemptIds = new Set<string>();
  const authorizer = Object.assign(Object.create(null) as object, {
    authorizeOriginalEgress: async (
      input: OriginalEgressAuthorizationRequest,
    ): Promise<OriginalEgressAuthorization> => {
      const request = snapshotRequest(input);
      const attemptKey = request.context.attemptId as string;
      if (issuedAttemptIds.has(attemptKey)) reject(request);
      issuedAttemptIds.add(attemptKey);
      let durablePrepared = false;
      try {
        if (request.enginePolicyVersion !== deps.enginePolicyVersion) reject(request);
        let rawDecision: AuthorizedOriginalEgressDecision;
        const query: OriginalEgressPolicyQuery = Object.freeze({
          context: request.context,
          destinationKey: request.destinationKey,
          protocol: request.protocol,
          contentClass: request.contentClass,
          enginePolicyVersion: request.enginePolicyVersion,
        });
        try {
          rawDecision = await deps.policy.requireAuthorizedOriginalEgress(query);
        } catch {
          reject(request);
        }
        const decision = snapshotDecision(rawDecision, request);
        if (!decisionMatches(decision, request)) reject(request);
        const preparedAt = deps.clock();
        const now = asEpoch(preparedAt);
        const expiry = asEpoch(decision.expiresAt);
        if (now === null || expiry === null || expiry <= now) reject(request);
        const prepared = preparedRecord(request, deps.engineVersion, preparedAt);
        let receipt: AuditPreparationReceipt;
        try {
          receipt = await audit.prepare(prepared);
          durablePrepared = true;
        } catch {
          throw new PhiEngineError("AUDIT_DURABILITY_UNAVAILABLE", request.context.operationId);
        }
        const afterPrepare = asEpoch(deps.clock());
        if (afterPrepare === null || expiry <= afterPrepare) {
          try {
            await audit.finalize(
              receipt,
              preparedToTerminalEvent(prepared, "failed_closed", "PROVIDER_SAFETY_GATE_FAILED", deps.clock()),
            );
          } catch { /* the caller still receives only the fixed authorization rejection */ }
          reject(request);
        }
        return authorizationHandle(request, decision, receipt, audit, prepared, deps.clock);
      } catch (error) {
        // Before a durable PREPARE there is no issued capability/attempt, so a corrected retry is legal.
        // Once PREPARE lands the key stays reserved permanently, preventing #inFlight overwrite.
        if (!durablePrepared) issuedAttemptIds.delete(attemptKey);
        if (isPhiEngineError(error)) throw error;
        throw new PhiEngineError("PROVIDER_SAFETY_GATE_FAILED", request.context.operationId);
      }
    },
  });
  return Object.freeze(authorizer) as ProtectedOriginalEgressAuthorizer;
}
