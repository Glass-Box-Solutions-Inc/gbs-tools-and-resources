import { createCipheriv, createDecipheriv, randomBytes } from "node:crypto";
import type { Ciphertext, OperationAttemptId } from "../core/brands";
import type {
  AuditPreparationReceipt,
  AuditPrimaryStore,
  EncryptedAuditSpool,
  EncryptedSpoolEnvelope,
  PhiAuditEvent,
  PhiAuditPreparedRecord,
  SpoolDrainReport,
} from "./ports";
import type { SpoolKeyProvider, SpoolVolume } from "./spool-ports";
import { PhiAuditError } from "./errors";
import { preparedToTerminalEvent } from "./event-factory";

const CIPHER_SUITE = "AES-256-GCM" as const;
const NONCE_BYTES = 12;
const KEY_BYTES = 32;

interface SpoolEntry {
  readonly recordId: string;
  readonly attemptId: OperationAttemptId;
  /** Metadata-only, held in-process to publish on drain; the durable copy is ciphertext. */
  readonly prepared: PhiAuditPreparedRecord;
  event: PhiAuditEvent | null;
  preparedEnvelope: EncryptedSpoolEnvelope;
  eventEnvelope: EncryptedSpoolEnvelope | null;
}

/** JSON-safe wire form: bigint identifiers (dictionary version) become strings. */
function toWireBytes(value: unknown): Uint8Array {
  const json = JSON.stringify(value, (_key, v) => (typeof v === "bigint" ? v.toString() : v));
  return new TextEncoder().encode(json);
}

function fromWireBytes(bytes: Uint8Array): unknown {
  return JSON.parse(new TextDecoder().decode(bytes));
}

function encodeEnvelope(envelope: EncryptedSpoolEnvelope): Uint8Array {
  const onDisk = {
    envelopeVersion: envelope.envelopeVersion,
    recordId: envelope.recordId,
    attemptId: envelope.attemptId,
    keyVersion: envelope.keyVersion,
    cipherSuite: envelope.cipherSuite,
    nonce: Buffer.from(envelope.nonce).toString("base64"),
    authenticationTag: Buffer.from(envelope.authenticationTag).toString("base64"),
    ciphertext: Buffer.from(envelope.ciphertext).toString("base64"),
    createdAt: envelope.createdAt,
  };
  return new TextEncoder().encode(JSON.stringify(onDisk));
}

function recordIdFor(attemptId: OperationAttemptId): string {
  return `spool:${attemptId}`;
}

/**
 * Local AES-256-GCM encrypted spool. Plaintext is accepted only at this boundary and is never
 * written to disk: only authenticated ciphertext envelopes reach the volume. Draining is
 * idempotent by attemptId and publishes only terminal events — never the PREPARED marker as a
 * second logical audit event (CONTRACT §5 N3, §6).
 */
export class Aes256GcmAuditSpool implements EncryptedAuditSpool {
  readonly #volume: SpoolVolume;
  readonly #keys: SpoolKeyProvider;
  readonly #entries = new Map<string, SpoolEntry>();
  readonly #clock: () => string;
  #acknowledgedLoss = false;

  public constructor(
    volume: SpoolVolume,
    keys: SpoolKeyProvider,
    clock: () => string = (): string => new Date().toISOString(),
  ) {
    this.#volume = volume;
    this.#keys = keys;
    this.#clock = clock;
  }

  public async health(): Promise<"ready" | "unavailable"> {
    return this.#volume.durable ? "ready" : "unavailable";
  }

  public async appendPrepared(record: PhiAuditPreparedRecord): Promise<AuditPreparationReceipt> {
    const recordId = recordIdFor(record.attemptId);
    const envelope = this.#encrypt(recordId, record.attemptId, toWireBytes(record));
    const { flushed } = await this.#volume.putAtomic(recordId, encodeEnvelope(envelope));
    if (!flushed) {
      throw new PhiAuditError("AUDIT_SPOOL_FLUSH_FAILED", record.operationId, { attemptId: record.attemptId });
    }
    this.#entries.set(recordId, {
      recordId,
      attemptId: record.attemptId,
      prepared: record,
      event: null,
      preparedEnvelope: envelope,
      eventEnvelope: null,
    });
    return { attemptId: record.attemptId, location: "ENCRYPTED_LOCAL_SPOOL", durableRecordId: recordId };
  }

  public async finalize(receipt: AuditPreparationReceipt, event: PhiAuditEvent): Promise<void> {
    const entry = this.#entries.get(receipt.durableRecordId);
    if (entry === undefined) {
      throw new PhiAuditError("AUDIT_DURABILITY_UNAVAILABLE", event.operationId, { attemptId: event.attemptId });
    }
    const finalId = `${entry.recordId}.final`;
    const envelope = this.#encrypt(finalId, event.attemptId, toWireBytes(event));
    const { flushed } = await this.#volume.putAtomic(finalId, encodeEnvelope(envelope));
    if (!flushed) {
      throw new PhiAuditError("AUDIT_SPOOL_FLUSH_FAILED", event.operationId, { attemptId: event.attemptId });
    }
    entry.event = event;
    entry.eventEnvelope = envelope;
  }

  public async drainTo(primary: AuditPrimaryStore): Promise<SpoolDrainReport> {
    let examined = 0;
    let delivered = 0;
    let duplicates = 0;
    let remaining = 0;

    for (const entry of [...this.#entries.values()]) {
      examined += 1;
      const outcome = await primary.prepare(entry.prepared);
      if (outcome.status === "unavailable") {
        remaining += 1;
        continue;
      }
      if (outcome.status === "already_exists") {
        // Idempotent: the attempt is already durable in primary — never publish it twice.
        duplicates += 1;
        await this.#discard(entry.recordId);
        continue;
      }
      const event = entry.event ?? preparedToTerminalEvent(entry.prepared, "unknown_after_send", null, this.#clock());
      await primary.finalize(event);
      delivered += 1;
      await this.#discard(entry.recordId);
    }

    return { examined, delivered, duplicates, remaining };
  }

  public async inspectEnvelope(recordId: string): Promise<EncryptedSpoolEnvelope> {
    const entry = this.#entries.get(recordId);
    if (entry === undefined) {
      throw new PhiAuditError("AUDIT_DURABILITY_UNAVAILABLE", null, { recordId });
    }
    return entry.eventEnvelope ?? entry.preparedEnvelope;
  }

  /** Metadata-only introspection used by audit/oracle tooling: decrypts the durable envelope. */
  public async decryptForAudit(recordId: string): Promise<unknown> {
    const envelope = await this.inspectEnvelope(recordId);
    return fromWireBytes(this.#decrypt(envelope));
  }

  public recordIds(): readonly string[] {
    return [...this.#entries.keys()];
  }

  public durabilityMetrics(): Readonly<{ survivesReplicaRestart: boolean }> {
    return { survivesReplicaRestart: this.#volume.durable && !this.#acknowledgedLoss };
  }

  async #discard(recordId: string): Promise<void> {
    const entry = this.#entries.get(recordId);
    this.#entries.delete(recordId);
    await this.#volume.remove(recordId);
    if (entry?.eventEnvelope) {
      await this.#volume.remove(`${recordId}.final`);
    }
  }

  #encrypt(recordId: string, attemptId: OperationAttemptId, plaintext: Uint8Array): EncryptedSpoolEnvelope {
    const key = this.#keys.dataKey();
    if (key.length !== KEY_BYTES) {
      throw new PhiAuditError("AUDIT_SPOOL_FLUSH_FAILED", null, { reason: "invalid_key_length" });
    }
    const nonce = randomBytes(NONCE_BYTES);
    const cipher = createCipheriv("aes-256-gcm", Buffer.from(key), nonce);
    const ciphertext = Buffer.concat([cipher.update(Buffer.from(plaintext)), cipher.final()]);
    const authenticationTag = cipher.getAuthTag();
    return {
      envelopeVersion: 1,
      recordId,
      attemptId,
      keyVersion: this.#keys.keyVersion,
      cipherSuite: CIPHER_SUITE,
      nonce: Uint8Array.from(nonce),
      authenticationTag: Uint8Array.from(authenticationTag),
      ciphertext: Uint8Array.from(ciphertext) as Ciphertext,
      createdAt: this.#clock(),
    };
  }

  #decrypt(envelope: EncryptedSpoolEnvelope): Uint8Array {
    const key = this.#keys.dataKey();
    const decipher = createDecipheriv("aes-256-gcm", Buffer.from(key), Buffer.from(envelope.nonce));
    decipher.setAuthTag(Buffer.from(envelope.authenticationTag));
    const plaintext = Buffer.concat([decipher.update(Buffer.from(envelope.ciphertext)), decipher.final()]);
    return Uint8Array.from(plaintext);
  }
}
