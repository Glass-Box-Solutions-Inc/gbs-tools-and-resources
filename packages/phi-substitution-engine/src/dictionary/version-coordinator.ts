/**
 * In-memory dictionary version coordinator (CONTRACT-phase1 §5 L2).
 *
 * Models the product persistence adapter's version/outbox transitions:
 *   - a committed tagged-truth write atomically ADVANCES the active version and
 *     enqueues its outbox entry, leaving the new version BUILDING;
 *   - a completed build marks that version READY;
 *   - serving REQUIRES the active version to be READY.
 *
 * The L2 invariant lives in {@link InMemoryDictionaryVersionCoordinator.requireActiveReady}:
 * once a newer version is committed (BUILDING/FAILED), the previous READY version
 * must NOT serve. Rejecting a non-READY active version fails closed with
 * `DICTIONARY_NOT_READY` and reports the active version for a value-free trace.
 */
import type {
  DictionaryVersion,
  MatterId,
  SchemaVersion,
  TenantId,
} from "../core/brands";
import type { DictionaryVersionCoordinator } from "./contracts";
import { DICTIONARY_NOT_READY, DictionaryError } from "./errors";

type VersionStatus = "BUILDING" | "READY" | "FAILED";

interface ActiveVersion {
  readonly version: bigint;
  readonly status: VersionStatus;
}

const asVersion = (value: bigint): DictionaryVersion =>
  value as unknown as DictionaryVersion;

export class InMemoryDictionaryVersionCoordinator implements DictionaryVersionCoordinator {
  private readonly active = new Map<string, ActiveVersion>();
  private readonly lastReady = new Map<string, bigint>();
  private outboxDepth = 0;

  private key(tenantId: TenantId, matterId: MatterId): string {
    return `${tenantId} ${matterId}`;
  }

  /** Enqueued outbox entries not yet drained; asserted by version-safety tests. */
  public get pendingOutbox(): number {
    return this.outboxDepth;
  }

  /** A completed build publishes a READY version and becomes servable. */
  public noteReady(
    input: Readonly<{ tenantId: TenantId; matterId: MatterId }>,
    version: bigint,
  ): void {
    const key = this.key(input.tenantId, input.matterId);
    this.active.set(key, { version, status: "READY" });
    this.lastReady.set(key, version);
  }

  /** A build in progress for `version`; the prior READY version must not serve. */
  public noteBuilding(
    input: Readonly<{ tenantId: TenantId; matterId: MatterId }>,
    version: bigint,
  ): void {
    this.active.set(this.key(input.tenantId, input.matterId), {
      version,
      status: "BUILDING",
    });
  }

  public advanceForCommittedTruthWrite(
    input: Readonly<{
      tenantId: TenantId;
      matterId: MatterId;
      schemaVersion: SchemaVersion;
      sourceTruthRevision: string;
    }>,
  ): Promise<DictionaryVersion> {
    const key = this.key(input.tenantId, input.matterId);
    const current = this.active.get(key);
    // Atomic with the tagged write: advance the version and enqueue the outbox;
    // the new version starts BUILDING and cannot serve until its build is READY.
    const nextVersion = (current?.version ?? 0n) + 1n;
    this.active.set(key, { version: nextVersion, status: "BUILDING" });
    this.outboxDepth += 1;
    return Promise.resolve(asVersion(nextVersion));
  }

  public requireActiveReady(
    input: Readonly<{
      tenantId: TenantId;
      matterId: MatterId;
    }>,
  ): Promise<DictionaryVersion> {
    const key = this.key(input.tenantId, input.matterId);
    const active = this.active.get(key);
    if (active === undefined) {
      throw new DictionaryError(DICTIONARY_NOT_READY, { activeVersion: null });
    }
    // L2: reject BUILDING/FAILED. An old READY version must NEVER serve while a
    // newer committed version is not yet READY.
    if (active.status !== "READY") {
      throw new DictionaryError(DICTIONARY_NOT_READY, {
        activeVersion: active.version.toString(),
      });
    }
    return Promise.resolve(asVersion(active.version));
  }
}
