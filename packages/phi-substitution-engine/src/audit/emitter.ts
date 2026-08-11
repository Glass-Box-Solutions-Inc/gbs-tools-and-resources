import type { OperationAttemptId } from "../core/brands";
import type {
  AuditPreparationReceipt,
  AuditPrimaryStore,
  EncryptedAuditSpool,
  PhiAuditEmitter,
  PhiAuditEvent,
  PhiAuditPreparedRecord,
  PhiAuditSerializer,
} from "./ports";
import { isAuditError, isAuditFailureCode, PhiAuditError } from "./errors";
import { safeCodeString } from "../core/errors";
import { preparedToTerminalEvent } from "./event-factory";
import { sanitizePreparedRecord, sanitizeTerminalEvent } from "./serializer";
import { safeRead, safeString } from "../core/boundary-snapshot";

interface InFlight {
  readonly receipt: AuditPreparationReceipt;
  readonly prepared: PhiAuditPreparedRecord;
}

/**
 * Durability orchestrator for the metadata-only audit event (CONTRACT §5 N3/N4).
 *
 * `prepare` writes a durable PREPARED record before provider egress: the primary store first,
 * then the encrypted local spool on primary outage, and only when BOTH are unavailable does it
 * reject with `AUDIT_DURABILITY_UNAVAILABLE` so the caller fails closed. `finalize` writes exactly
 * one terminal event, at the same location the PREPARED record landed, after the exact allow-list
 * serializer has validated it.
 */
export class DurablePhiAuditEmitter implements PhiAuditEmitter {
  readonly #primary: AuditPrimaryStore;
  readonly #spool: EncryptedAuditSpool;
  readonly #serializer: PhiAuditSerializer;
  readonly #clock: () => string;
  readonly #inFlight = new Map<string, InFlight>();
  /** Attempt ids whose single terminal has already been finalized (N3 one-shot). */
  readonly #finalized = new Set<string>();

  public constructor(
    primary: AuditPrimaryStore,
    spool: EncryptedAuditSpool,
    serializer: PhiAuditSerializer,
    clock: () => string = (): string => new Date().toISOString(),
  ) {
    this.#primary = primary;
    this.#spool = spool;
    this.#serializer = serializer;
    this.#clock = clock;
  }

  public async prepare(record: PhiAuditPreparedRecord): Promise<AuditPreparationReceipt> {
    // The PREPARED record is itself UNTRUSTED — its fields may be mutating/throwing getters or a
    // poisoned own iterator. Validate AND read-once snapshot it into an inert record here; a bad
    // record is AUDIT_SCHEMA_REJECTED, and ONLY the inert snapshot is keyed on, remembered, or handed
    // to a durable store (§7/N2) — so the store can never re-read a getter into a PHI value.
    const durableRecord = sanitizePreparedRecord(record);
    // Injected-serializer allow-list runs on the INERT snapshot (never a re-read of a live getter).
    // §7/N2: the serializer is an INJECTED port — a rejection could itself carry PHI, so it is caught
    // and re-thrown as a FRESH fixed-code error (a recognized audit code is preserved; anything else
    // becomes AUDIT_SCHEMA_REJECTED). The original instance is never forwarded.
    try {
      this.#serializer.validatePrepared(durableRecord);
    } catch (error) {
      if (isAuditError(error)) {
        const code = safeCodeString(error);
        if (code !== undefined && isAuditFailureCode(code)) {
          throw new PhiAuditError(code, durableRecord.operationId, { attemptId: durableRecord.attemptId });
        }
      }
      throw new PhiAuditError("AUDIT_SCHEMA_REJECTED", durableRecord.operationId, {
        attemptId: durableRecord.attemptId,
      });
    }

    // N3 idempotency: an attempt id that already has a terminal in this process must
    // not be re-prepared — that would permit a second provider egress and a second
    // terminal event for the same logical attempt.
    if (this.#finalized.has(this.#key(durableRecord.attemptId))) {
      throw new PhiAuditError("AUDIT_ATTEMPT_ALREADY_FINALIZED", durableRecord.operationId, {
        attemptId: durableRecord.attemptId,
      });
    }

    try {
      const primaryResult = await this.#primary.prepare(durableRecord);
      if (primaryResult.status === "stored") {
        // §7/N2: the injected primary store is UNTRUSTED — read `durableRecordId` getter-throw-safe and
        // require a genuine string; a throwing/non-string carrier fails closed (durability unavailable)
        // rather than placing a raw (PHI) value onto the returned receipt.
        const durableRecordId = safeString(primaryResult, "durableRecordId");
        if (durableRecordId === undefined) {
          throw new PhiAuditError("AUDIT_DURABILITY_UNAVAILABLE", durableRecord.operationId, {
            attemptId: durableRecord.attemptId,
          });
        }
        const receipt: AuditPreparationReceipt = {
          attemptId: durableRecord.attemptId,
          location: "PRIMARY_STORE",
          durableRecordId,
        };
        this.#remember(receipt, durableRecord);
        return receipt;
      }
      if (primaryResult.status === "already_exists") {
        // A durable record for this attempt already exists — never egress or finalize a
        // second time for the same attempt id (N3 exactly-one-terminal / idempotency).
        throw new PhiAuditError("AUDIT_ATTEMPT_ALREADY_FINALIZED", durableRecord.operationId, {
          attemptId: durableRecord.attemptId,
        });
      }

      // Primary outage alone proceeds through the spool.
      if ((await this.#spool.health()) !== "ready") {
        throw new PhiAuditError("AUDIT_DURABILITY_UNAVAILABLE", durableRecord.operationId, {
          attemptId: durableRecord.attemptId,
        });
      }
      const receipt = await this.#spool.appendPrepared(durableRecord);
      this.#remember(receipt, durableRecord);
      return receipt;
    } catch (error) {
      // A fixed-code audit failure thrown above is preserved ONLY if its code is a RECOGNIZED
      // AuditFailureCode — and even then a FRESH error carrying the ONCE-read, validated code is
      // thrown, never the original instance (a `.code` getter could return a valid code on the
      // check read and a PHI value on the caller's read). A store that throws
      // `new PhiAuditError(rawValue as any)` is thus never trusted for being an instance (§7/N2).
      if (isAuditError(error)) {
        const code = safeCodeString(error); // read ONCE, getter-throw-safe
        if (code !== undefined && isAuditFailureCode(code)) {
          throw new PhiAuditError(code, durableRecord.operationId, { attemptId: durableRecord.attemptId });
        }
      }
      // §7/N2 + N3: a RAW store/spool rejection must never surface an upstream message/code, and it
      // must be recognizable to the caller as an audit-layer failure (a `PhiAuditError`) so a failed
      // PREPARE is never re-attempted into a second durable record (no double-prepare).
      throw new PhiAuditError("AUDIT_DURABILITY_UNAVAILABLE", durableRecord.operationId, {
        attemptId: durableRecord.attemptId,
      });
    }
  }

  public async finalize(receipt: AuditPreparationReceipt, event: PhiAuditEvent): Promise<void> {
    // §7/N2: read the receipt's routing scalars ONCE, getter-throw-safe. finalize receives the receipt
    // THIS emitter returned from prepare(), but reading its members live would let a fabricated receipt
    // throw raw out of this method — snapshot `attemptId`/`location` into inert locals. A receipt with
    // no usable attempt id / location cannot be finalized against, so fail closed silently (the durable
    // record can still be drained/reconciled) rather than propagate a raw throw.
    const attemptId = safeRead(receipt, "attemptId") as OperationAttemptId | undefined;
    const location = safeString(receipt, "location");
    if (attemptId === undefined || location === undefined) {
      return;
    }
    // N3 one-shot: at most one terminal per attempt. A concurrent reconcile racing a
    // normal completion (or a duplicate finalize) is a no-op after the first terminal.
    if (this.#finalized.has(this.#key(attemptId))) {
      return;
    }
    // §7/N2: read the live event EXACTLY ONCE into a validated, inert snapshot, then run the injected
    // serializer's allow-list on the SNAPSHOT (plain data — never a second read of a live getter) and
    // persist the SNAPSHOT, never the live event. This closes the validate-then-reread TOCTOU: a
    // mutating getter (valid on the check read, PHI on the persistence read) can no longer land a
    // canary in the durable record, because the store only ever sees inert data.
    const durable = sanitizeTerminalEvent(event);
    // §7/N2: the injected serializer is a port — a `serialize` rejection could carry PHI, so it is
    // caught and re-thrown as a FRESH fixed-code error, never forwarded raw.
    try {
      this.#serializer.serialize(durable);
    } catch (error) {
      if (isAuditError(error)) {
        const code = safeCodeString(error);
        if (code !== undefined && isAuditFailureCode(code)) {
          throw new PhiAuditError(code, null, {});
        }
      }
      throw new PhiAuditError("AUDIT_SCHEMA_REJECTED", null, {});
    }
    try {
      if (location === "PRIMARY_STORE") {
        await this.#primary.finalize(durable);
      } else {
        await this.#spool.finalize(receipt, durable);
      }
    } catch (error) {
      // §7/N2: a RAW store/spool finalize rejection must never surface an upstream message/code to
      // any caller (a rejecting finalizer could carry PHI). The terminal is NOT marked written, so a
      // later drain/reconcile can still deliver it; the caller sees only this fixed, safe code. A
      // recognized code is preserved by throwing a FRESH error carrying the ONCE-read, validated
      // code — never the original instance (its `.code` getter could change between reads).
      if (isAuditError(error)) {
        const code = safeCodeString(error); // read ONCE, getter-throw-safe
        if (code !== undefined && isAuditFailureCode(code)) {
          throw new PhiAuditError(code, null, {});
        }
      }
      throw new PhiAuditError("AUDIT_SPOOL_FLUSH_FAILED", null, {});
    }
    this.#finalized.add(this.#key(attemptId));
    this.#inFlight.delete(this.#key(attemptId));
  }

  public async reconcileUnknownAfterSend(attemptId: OperationAttemptId, occurredAt: string): Promise<void> {
    const inFlight = this.#inFlight.get(this.#key(attemptId));
    if (inFlight === undefined) {
      // No in-process PREPARED record: a sweeper drains the durable spool/primary record instead.
      return;
    }
    const event = preparedToTerminalEvent(inFlight.prepared, "unknown_after_send", null, occurredAt || this.#clock());
    await this.finalize(inFlight.receipt, event);
  }

  #remember(receipt: AuditPreparationReceipt, prepared: PhiAuditPreparedRecord): void {
    this.#inFlight.set(this.#key(receipt.attemptId), { receipt, prepared });
  }

  #key(attemptId: OperationAttemptId): string {
    return attemptId as string;
  }
}
