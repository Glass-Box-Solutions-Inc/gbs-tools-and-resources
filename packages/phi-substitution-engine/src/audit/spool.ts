import { createCipheriv, createDecipheriv, randomBytes } from "node:crypto";
import type { Ciphertext, DictionaryVersion, OperationAttemptId } from "../core/brands";
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
import { intrinsicCopy } from "../core/boundary-snapshot";

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
  /**
   * True once this drain has PREPARED the record in the primary store. A subsequent
   * `already_exists` from primary for an entry the spool itself prepared means a prior
   * finalize failed (partial) and the terminal must still be delivered — never dropped.
   */
  preparedInPrimary: boolean;
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

/** Inverse of `encodeEnvelope`: reconstructs an envelope read back from the durable volume. */
function decodeEnvelope(bytes: Uint8Array): EncryptedSpoolEnvelope {
  const onDisk = JSON.parse(new TextDecoder().decode(bytes)) as Record<string, unknown>;
  return {
    envelopeVersion: onDisk["envelopeVersion"] as 1,
    recordId: onDisk["recordId"] as string,
    attemptId: onDisk["attemptId"] as OperationAttemptId,
    keyVersion: onDisk["keyVersion"] as string,
    cipherSuite: onDisk["cipherSuite"] as "AES-256-GCM",
    nonce: Uint8Array.from(Buffer.from(onDisk["nonce"] as string, "base64")),
    authenticationTag: Uint8Array.from(Buffer.from(onDisk["authenticationTag"] as string, "base64")),
    ciphertext: Uint8Array.from(Buffer.from(onDisk["ciphertext"] as string, "base64")) as Ciphertext,
    createdAt: onDisk["createdAt"] as string,
  };
}

function recordIdFor(attemptId: OperationAttemptId): string {
  return `spool:${attemptId}`;
}

/** Durable prepare-success/finalize-pending marker byte written alongside a record. */
const PRIMED_MARKER = new TextEncoder().encode("1");

/**
 * A PREPARED record read back from the volume carries its bigint identifiers as JSON strings
 * (see `toWireBytes`). Restore the branded `dictionaryVersion` bigint so a drained record is
 * byte-for-type identical to the one that was prepared — the primary store must never receive
 * a string where a branded version bigint is contracted (CONTRACT §5 N3/N4, L2).
 *
 * `dictionaryVersion` is contractually NULLABLE: a fail-closed terminal recorded BEFORE any
 * substitution (see the wrapper's minimal prepared record) stores `null`. Such a record must
 * rehydrate to `null`, never `BigInt(null)` — which would throw and drop the terminal on drain.
 */
function rehydratePrepared(value: unknown): PhiAuditPreparedRecord {
  const record = value as PhiAuditPreparedRecord & { dictionaryVersion: unknown };
  const version = record.dictionaryVersion;
  return {
    ...record,
    dictionaryVersion:
      version === null || version === undefined
        ? (null as unknown as DictionaryVersion)
        : (BigInt(version as string | number | bigint) as unknown as DictionaryVersion),
  };
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
    // N3 durable idempotency: after a restart the in-process finalized-set is empty, so the
    // durable `.final` marker on the volume is the only source of truth. A fresh append for an
    // attempt already finalized on the volume must be refused — never permit a second egress.
    if ((await this.#volume.read(`${recordId}.final`)) !== null) {
      throw new PhiAuditError("AUDIT_ATTEMPT_ALREADY_FINALIZED", record.operationId, {
        attemptId: record.attemptId,
      });
    }
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
      preparedInPrimary: false,
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
    // N3/N4: drain reads the DURABLE volume so records survive a replica restart —
    // never only the in-memory index. §7/N2: a RAW volume rejection during rebuild (a hostile or
    // failing `list`/`read` adapter whose message could carry PHI) must never surface from this
    // background drain — proceed best-effort with whatever the index already holds and re-drive on a
    // later drain.
    try {
      await this.rebuildFromVolume();
    } catch {
      /* volume outage during rebuild; drain what is already indexed, retry the rest later. */
    }

    let examined = 0;
    let delivered = 0;
    let duplicates = 0;
    let remaining = 0;

    for (const entry of [...this.#entries.values()]) {
      examined += 1;
      try {
        // §7/N2: EVERYTHING that touches the untrusted primary store or the volume adapter lives
        // inside this guard, so ANY raw rejection — a store/volume error, a throwing/mutating
        // `status` getter, a `.primed` marker flush failure — is caught below and NEVER propagated
        // from this background drain (it could carry an upstream message/code). The durable entry is
        // kept and re-driven idempotently on a later drain.
        const outcome = await primary.prepare(entry.prepared);
        const status: unknown = outcome.status; // read the untrusted status EXACTLY ONCE
        if (status === "unavailable") {
          remaining += 1;
          continue;
        }
        if (status === "already_exists" && !entry.preparedInPrimary) {
          // The attempt is already durable in primary from ELSEWHERE (not this spool's own prior
          // prepare). Idempotent: never publish a second terminal. Discard first so a discard
          // failure keeps the entry (re-driven, deduped) rather than dropping it.
          await this.#discard(entry.recordId);
          duplicates += 1;
          continue;
        }
        // Either freshly `stored`, or `already_exists` after this spool prepared it on a prior drain
        // whose finalize failed (a partial). Deliver the terminal, and only discard after finalize
        // succeeds so a partial retry can never drop it.
        entry.preparedInPrimary = true;
        // Persist prepare-success/finalize-pending durably BEFORE finalize. After a restart the
        // in-memory `preparedInPrimary` is lost; without this marker an `already_exists` from primary
        // would be misread as an unrelated duplicate and the terminal dropped. If the durable flush
        // fails, keep the entry and retry on a later drain rather than proceed.
        if (!(await this.#persistPrimedMarker(entry))) {
          remaining += 1;
          continue;
        }
        const event = entry.event ?? preparedToTerminalEvent(entry.prepared, "unknown_after_send", null, this.#clock());
        await primary.finalize(event);
        // Discard BEFORE counting `delivered` so a discard failure keeps the entry (idempotent retry).
        await this.#discard(entry.recordId);
        delivered += 1;
      } catch {
        // A store/volume/finalize/status failure on this entry keeps it for a future retry; a raw
        // message/code is NEVER surfaced from the drain.
        remaining += 1;
      }
    }

    return { examined, delivered, duplicates, remaining };
  }

  /**
   * Rebuilds the in-memory index from the durable volume so acknowledged records survive a
   * replica restart / scale-in (CONTRACT §6). Decrypts each stored PREPARED envelope (and its
   * terminal, if present) that is not already tracked in-process.
   */
  public async rebuildFromVolume(): Promise<void> {
    // §7/N2: `list()` is an injected-volume result — a NON-array carrier, an OWN poisoned
    // `Symbol.iterator`, or a throwing own-index getter must not throw a raw (PHI) value out of this
    // PUBLIC method (the guarded `drainTo` already tolerates it; this sibling must too). `intrinsicCopy`
    // reads it ONCE by own index/length, getter-throw-safe; a hostile carrier fails closed to no-op.
    const idList = intrinsicCopy<string>(await this.#volume.list());
    if (idList === null) {
      return;
    }
    for (let i = 0; i < idList.length; i += 1) {
      const recordId = idList[i]!;
      if (recordId.endsWith(".final") || recordId.endsWith(".primed")) {
        continue;
      }
      if (this.#entries.has(recordId)) {
        continue;
      }
      const preparedBytes = await this.#volume.read(recordId);
      if (preparedBytes === null) {
        continue;
      }
      const preparedEnvelope = decodeEnvelope(preparedBytes);
      const prepared = rehydratePrepared(fromWireBytes(this.#decrypt(preparedEnvelope)));
      const finalBytes = await this.#volume.read(`${recordId}.final`);
      let event: PhiAuditEvent | null = null;
      let eventEnvelope: EncryptedSpoolEnvelope | null = null;
      if (finalBytes !== null) {
        eventEnvelope = decodeEnvelope(finalBytes);
        event = fromWireBytes(this.#decrypt(eventEnvelope)) as PhiAuditEvent;
      }
      // Restore the durable prepare-success/finalize-pending flag so a partial (prepared in
      // primary, finalize failed) drained on a PRIOR replica is recognised as OUR own attempt
      // after restart — its terminal is still owed and must not be dropped as a duplicate.
      const preparedInPrimary = (await this.#volume.read(`${recordId}.primed`)) !== null;
      this.#entries.set(recordId, {
        recordId,
        attemptId: preparedEnvelope.attemptId,
        prepared,
        event,
        preparedEnvelope,
        eventEnvelope,
        preparedInPrimary,
      });
    }
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

  /**
   * Persist the prepare-success/finalize-pending marker durably BEFORE finalize is attempted.
   * After a restart the in-memory `preparedInPrimary` flag is gone; `rebuildFromVolume` reads
   * this marker to restore it, so an `already_exists` from primary is recognised as OUR partial
   * (terminal still owed) rather than misread as an unrelated external duplicate and dropped.
   * Returns false on flush failure so the caller keeps the entry for a later retry.
   */
  async #persistPrimedMarker(entry: SpoolEntry): Promise<boolean> {
    const { flushed } = await this.#volume.putAtomic(`${entry.recordId}.primed`, PRIMED_MARKER);
    return flushed;
  }

  async #discard(recordId: string): Promise<void> {
    const entry = this.#entries.get(recordId);
    this.#entries.delete(recordId);
    await this.#volume.remove(recordId);
    await this.#volume.remove(`${recordId}.primed`);
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
