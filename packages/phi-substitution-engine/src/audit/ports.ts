import type {
  ActorId,
  Ciphertext,
  DictionaryVersion,
  EngineVersion,
  MatterId,
  OperationAttemptId,
  OperationId,
  TenantId,
} from "../core/brands";
import type { AiOperation, IdentifierCounts } from "../core/contracts";

export type PhiAuditOutcome =
  | "completed"
  | "cancelled"
  | "interrupted"
  | "failed_closed"
  | "reversal_failed"
  | "unknown_after_send";

/** Exact recursive allow-list. Extra properties are invalid even when nested. */
export interface PhiAuditEvent {
  readonly eventType: "AI_SUBSTITUTION_ATTEMPT";
  readonly attemptId: OperationAttemptId;
  readonly operationId: OperationId;
  readonly tenantId: TenantId;
  readonly matterId: MatterId;
  readonly actorId: ActorId;
  readonly operation: AiOperation;
  readonly dictionaryVersion: string | null;
  readonly engineVersion: EngineVersion;
  readonly counts: IdentifierCounts;
  readonly ambiguityCount: number;
  readonly detectorName: string | null;
  readonly detectorVersion: string | null;
  readonly latencyMs: Readonly<{ dictionary: number; detector: number; total: number }>;
  readonly outcome: PhiAuditOutcome;
  readonly failureCode: string | null;
  readonly occurredAt: string;
}

/** Counts/IDs only. No values, hashes of values, text, tokens, offsets, excerpts, or payloads. */
export interface PhiAuditPreparedRecord {
  readonly state: "PREPARED";
  readonly attemptId: OperationAttemptId;
  readonly operationId: OperationId;
  readonly tenantId: TenantId;
  readonly matterId: MatterId;
  readonly actorId: ActorId;
  readonly operation: AiOperation;
  readonly dictionaryVersion: DictionaryVersion | null;
  readonly engineVersion: EngineVersion;
  readonly counts: IdentifierCounts;
  readonly ambiguityCount: number;
  readonly detectorName: string | null;
  readonly detectorVersion: string | null;
  readonly latencyMs: Readonly<{ dictionary: number; detector: number; total: number }>;
  readonly preparedAt: string;
}

export type AuditDurabilityLocation = "PRIMARY_STORE" | "ENCRYPTED_LOCAL_SPOOL";

export interface AuditPreparationReceipt {
  readonly attemptId: OperationAttemptId;
  readonly location: AuditDurabilityLocation;
  readonly durableRecordId: string;
}

export interface PhiAuditSerializer {
  /** Rejects missing/extra keys recursively and returns only the canonical event byte form. */
  serialize(event: PhiAuditEvent): Uint8Array;
  validatePrepared(record: PhiAuditPreparedRecord): void;
}

export interface AuditPrimaryStore {
  /** Returns unavailable rather than treating an outage as successful durability. */
  prepare(record: PhiAuditPreparedRecord): Promise<
    | Readonly<{ status: "stored"; durableRecordId: string }>
    | Readonly<{ status: "already_exists"; durableRecordId: string }>
    | Readonly<{ status: "unavailable"; fixedFailureCode: string }>
  >;
  finalize(event: PhiAuditEvent): Promise<void>;
}

export interface EncryptedSpoolEnvelope {
  readonly envelopeVersion: 1;
  readonly recordId: string;
  readonly attemptId: OperationAttemptId;
  readonly keyVersion: string;
  readonly cipherSuite: "AES-256-GCM";
  readonly nonce: Uint8Array;
  readonly authenticationTag: Uint8Array;
  readonly ciphertext: Ciphertext;
  readonly createdAt: string;
}

export interface SpoolDrainReport {
  readonly examined: number;
  readonly delivered: number;
  readonly duplicates: number;
  readonly remaining: number;
}

/**
 * Local, encrypted-at-rest fallback. Plaintext events are accepted only at this boundary and
 * must not be written to disk. Draining is idempotent by attemptId and never publishes PREPARED
 * as a second logical audit event.
 */
export interface EncryptedAuditSpool {
  appendPrepared(record: PhiAuditPreparedRecord): Promise<AuditPreparationReceipt>;
  finalize(receipt: AuditPreparationReceipt, event: PhiAuditEvent): Promise<void>;
  drainTo(primary: AuditPrimaryStore): Promise<SpoolDrainReport>;
  inspectEnvelope(recordId: string): Promise<EncryptedSpoolEnvelope>;
  health(): Promise<"ready" | "unavailable">;
}

export interface PhiAuditEmitter {
  /**
   * Must complete before provider egress. It first tries the primary store, then the encrypted
   * spool. It rejects with AUDIT_DURABILITY_UNAVAILABLE only when both are unavailable.
   */
  prepare(record: PhiAuditPreparedRecord): Promise<AuditPreparationReceipt>;
  /** Finalizes the same logical attempt once. A crash reconciles to unknown_after_send. */
  finalize(receipt: AuditPreparationReceipt, event: PhiAuditEvent): Promise<void>;
  reconcileUnknownAfterSend(attemptId: OperationAttemptId, occurredAt: string): Promise<void>;
}
