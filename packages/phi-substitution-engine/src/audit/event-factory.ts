import type { PhiAuditEvent, PhiAuditOutcome, PhiAuditPreparedRecord } from "./ports";
import { safeRead } from "../core/boundary-snapshot";

/**
 * Builds a terminal audit event from a durable PREPARED record. It copies only counts/IDs/versions/
 * latency metadata and adds the terminal `outcome`/`failureCode`/`occurredAt`. The bigint dictionary
 * version is projected to its string form so the event is JSON-safe and metadata-only.
 *
 * §7/N2: `prepared` may be an UNTRUSTED injected-plan record whose NESTED field getters throw/mutate
 * PHI. The coordinator builds terminals from it OUTSIDE any guard, so every field is read EXACTLY
 * ONCE, getter-throw-safe; a throwing getter yields `undefined` here (which the exact allow-list
 * serializer then rejects as AUDIT_SCHEMA_REJECTED downstream) rather than propagating raw.
 */
export function preparedToTerminalEvent(
  prepared: PhiAuditPreparedRecord,
  outcome: PhiAuditOutcome,
  failureCode: string | null,
  occurredAt: string,
): PhiAuditEvent {
  const dictionaryVersion = safeRead(prepared, "dictionaryVersion");
  let dictionaryVersionString: string | null = null;
  if (dictionaryVersion !== null && dictionaryVersion !== undefined) {
    try {
      dictionaryVersionString = String(dictionaryVersion);
    } catch {
      dictionaryVersionString = null;
    }
  }
  return {
    eventType: "AI_SUBSTITUTION_ATTEMPT",
    attemptId: safeRead(prepared, "attemptId") as PhiAuditEvent["attemptId"],
    operationId: safeRead(prepared, "operationId") as PhiAuditEvent["operationId"],
    tenantId: safeRead(prepared, "tenantId") as PhiAuditEvent["tenantId"],
    matterId: safeRead(prepared, "matterId") as PhiAuditEvent["matterId"],
    actorId: safeRead(prepared, "actorId") as PhiAuditEvent["actorId"],
    operation: safeRead(prepared, "operation") as PhiAuditEvent["operation"],
    dictionaryVersion: dictionaryVersionString,
    engineVersion: safeRead(prepared, "engineVersion") as PhiAuditEvent["engineVersion"],
    counts: safeRead(prepared, "counts") as PhiAuditEvent["counts"],
    ambiguityCount: safeRead(prepared, "ambiguityCount") as PhiAuditEvent["ambiguityCount"],
    detectorName: safeRead(prepared, "detectorName") as PhiAuditEvent["detectorName"],
    detectorVersion: safeRead(prepared, "detectorVersion") as PhiAuditEvent["detectorVersion"],
    latencyMs: safeRead(prepared, "latencyMs") as PhiAuditEvent["latencyMs"],
    outcome,
    failureCode,
    occurredAt,
  };
}
