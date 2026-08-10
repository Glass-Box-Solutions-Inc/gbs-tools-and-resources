import type { PhiAuditEvent, PhiAuditOutcome, PhiAuditPreparedRecord } from "./ports";

/**
 * Builds a terminal audit event from a durable PREPARED record. It copies only counts/IDs/versions/
 * latency metadata and adds the terminal `outcome`/`failureCode`/`occurredAt`. The bigint dictionary
 * version is projected to its string form so the event is JSON-safe and metadata-only.
 */
export function preparedToTerminalEvent(
  prepared: PhiAuditPreparedRecord,
  outcome: PhiAuditOutcome,
  failureCode: string | null,
  occurredAt: string,
): PhiAuditEvent {
  return {
    eventType: "AI_SUBSTITUTION_ATTEMPT",
    attemptId: prepared.attemptId,
    operationId: prepared.operationId,
    tenantId: prepared.tenantId,
    matterId: prepared.matterId,
    actorId: prepared.actorId,
    operation: prepared.operation,
    dictionaryVersion: prepared.dictionaryVersion === null ? null : prepared.dictionaryVersion.toString(),
    engineVersion: prepared.engineVersion,
    counts: prepared.counts,
    ambiguityCount: prepared.ambiguityCount,
    detectorName: prepared.detectorName,
    detectorVersion: prepared.detectorVersion,
    latencyMs: prepared.latencyMs,
    outcome,
    failureCode,
    occurredAt,
  };
}
