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
import { PhiAuditError } from "./errors";
import { preparedToTerminalEvent } from "./event-factory";

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
    // The PREPARED record must itself be metadata-only; reject any leaked value before durability.
    this.#serializer.validatePrepared(record);

    // N3 idempotency: an attempt id that already has a terminal in this process must
    // not be re-prepared — that would permit a second provider egress and a second
    // terminal event for the same logical attempt.
    if (this.#finalized.has(this.#key(record.attemptId))) {
      throw new PhiAuditError("AUDIT_ATTEMPT_ALREADY_FINALIZED", record.operationId, {
        attemptId: record.attemptId,
      });
    }

    const primaryResult = await this.#primary.prepare(record);
    if (primaryResult.status === "stored") {
      const receipt: AuditPreparationReceipt = {
        attemptId: record.attemptId,
        location: "PRIMARY_STORE",
        durableRecordId: primaryResult.durableRecordId,
      };
      this.#remember(receipt, record);
      return receipt;
    }
    if (primaryResult.status === "already_exists") {
      // A durable record for this attempt already exists — never egress or finalize a
      // second time for the same attempt id (N3 exactly-one-terminal / idempotency).
      throw new PhiAuditError("AUDIT_ATTEMPT_ALREADY_FINALIZED", record.operationId, {
        attemptId: record.attemptId,
      });
    }

    // Primary outage alone proceeds through the spool.
    if ((await this.#spool.health()) !== "ready") {
      throw new PhiAuditError("AUDIT_DURABILITY_UNAVAILABLE", record.operationId, {
        attemptId: record.attemptId,
      });
    }
    const receipt = await this.#spool.appendPrepared(record);
    this.#remember(receipt, record);
    return receipt;
  }

  public async finalize(receipt: AuditPreparationReceipt, event: PhiAuditEvent): Promise<void> {
    // N3 one-shot: at most one terminal per attempt. A concurrent reconcile racing a
    // normal completion (or a duplicate finalize) is a no-op after the first terminal.
    if (this.#finalized.has(this.#key(receipt.attemptId))) {
      return;
    }
    // Validate the exact allow-list before anything is published as a terminal event.
    this.#serializer.serialize(event);
    if (receipt.location === "PRIMARY_STORE") {
      await this.#primary.finalize(event);
    } else {
      await this.#spool.finalize(receipt, event);
    }
    this.#finalized.add(this.#key(receipt.attemptId));
    this.#inFlight.delete(this.#key(receipt.attemptId));
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
