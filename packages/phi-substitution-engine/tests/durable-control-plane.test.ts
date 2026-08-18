import { describe, expect, it } from "vitest";
import type {
  DekGenerationId,
  EncryptedReversalRecordBlob,
  GcmNonce96,
  PrepareReversalWriteInput,
  PreparedReversalWrite,
  PreparedWriteHandle,
  ReversalIdempotencyKey,
  ReversalMappingKey,
  ReversalScopeDigest,
  WrappedDekMaterial,
  WrappingKeyId,
  WrappingKeyVersion,
} from "../src/tokens/durable/ports";
import { DurableReversalStore } from "../src/tokens/durable/durable-reversal-store";
import { InMemoryKeyProvider } from "../src/tokens/durable/dev/in-memory-key-provider";
import {
  InMemoryControlPlane,
  type InMemoryControlPlaneFaults,
} from "../src/tokens/durable/dev/in-memory-control-plane";
import { idempotencyKeyOf, mappingKeyOf, scopeDigestOf } from "../src/tokens/durable/keys";
import { MATTER_EXPIRES_AT } from "../src/tokens/durable/aad";
import type {
  DictionaryVersion,
  MatterId,
  OperationAttemptId,
  SubstitutionToken,
  TenantId,
} from "../src/core/brands";

const brand = <T>(value: unknown): T => value as unknown as T;
const T0 = 1_700_000_000_000;
const TENANT = brand<TenantId>("tenant-a");
const MATTER = brand<MatterId>("matter-a");
const VERSION = brand<DictionaryVersion>(1n);
const TOKEN = brand<SubstitutionToken>("[[Claimant]]");

interface Clock {
  readonly now: () => number;
  readonly set: (value: number) => void;
  readonly advance: (delta: number) => void;
}

function clock(start = T0): Clock {
  let value = start;
  return {
    now: () => value,
    set: (next) => {
      value = next;
    },
    advance: (delta) => {
      value += delta;
    },
  };
}

interface PreparedFixture {
  readonly prepared: PreparedReversalWrite;
  readonly input: PrepareReversalWriteInput;
}

function writeInput(options: {
  readonly attempt?: string;
  readonly createdAtMs?: number;
  readonly expiresAtMs?: bigint;
  readonly marker?: number;
  readonly mapping?: string;
} = {}): PrepareReversalWriteInput {
  const attemptId = brand<OperationAttemptId>(options.attempt ?? "attempt-a");
  const retentionClass = options.expiresAtMs === undefined || options.expiresAtMs === MATTER_EXPIRES_AT
    ? "matter"
    : "detector-only";
  const createdAtEpochMs = options.createdAtMs ?? (
    retentionClass === "detector-only"
      ? Number(options.expiresAtMs! - 86_400_000n)
      : T0
  );
  const encryptedRecord: EncryptedReversalRecordBlob = {
    ciphertext: Uint8Array.of(options.marker ?? 1),
    authTag: new Uint8Array(16),
    nonce: new Uint8Array(12) as unknown as GcmNonce96,
    wrappedDek: new Uint8Array(32) as unknown as WrappedDekMaterial,
    dekGenerationId: brand<DekGenerationId>("generation-a"),
    wrappingKeyId: brand<WrappingKeyId>("key-a"),
    wrappingKeyVersion: brand<WrappingKeyVersion>("version-a"),
    aad: Uint8Array.of(7, 8, 9),
    meta: {
      tenantId: TENANT,
      matterId: MATTER,
      dictionaryVersion: VERSION,
      token: TOKEN,
      attemptId,
      retentionClass,
      createdAtEpochMs,
      expiresAtEpochMs: options.expiresAtMs ?? MATTER_EXPIRES_AT,
    },
  };
  return {
    idempotencyKey: idempotencyKeyOf(TENANT, attemptId, TOKEN),
    mappingKey: options.mapping === undefined
      ? mappingKeyOf(TENANT, MATTER, VERSION, TOKEN)
      : brand<ReversalMappingKey>(options.mapping),
    immutableScopeDigest: scopeDigestOf(TENANT, MATTER, VERSION),
    encryptedRecord,
  };
}

async function prepare(
  controlPlane: InMemoryControlPlane,
  options: Parameters<typeof writeInput>[0] = {},
): Promise<PreparedFixture> {
  const input = writeInput(options);
  return { input, prepared: await controlPlane.prepare(input) };
}

function nonceValue(nonce: GcmNonce96): bigint {
  const bytes = Buffer.from(nonce);
  return (bytes.readBigUInt64BE(0) << 32n) | BigInt(bytes.readUInt32BE(8));
}

describe("GLY-346 Lane A — reclamation oracles", () => {
  it("previews reclamation with the global budget without mutating candidates", async () => {
    const controlPlane = new InMemoryControlPlane({ nowEpochMilliseconds: () => T0 });
    const { prepared } = await prepare(controlPlane, { createdAtMs: T0 });

    const outcome = await controlPlane.previewReclamation({
      olderThanEpochMs: T0 + 1,
      uploadHorizonEpochMs: 0,
      quarantinedBeforeEpochMs: 0,
      limit: 1,
      includeHardDelete: true,
    });

    expect(outcome).toEqual({ scanned: 1, reclaimed: 1, skippedReferenced: 0 });
    expect(controlPlane.debugPrepared(prepared.handle)?.state).toBe("finalized");
    expect(controlPlane.debugPrepared(prepared.handle)?.blobPresent).toBe(true);
  });

  it("keeps referenced rows outside the in-memory maintenance budget", async () => {
    const c = clock(T0);
    const controlPlane = new InMemoryControlPlane({
      nowEpochMilliseconds: c.now,
      quarantineGraceMilliseconds: 100,
      supersedeRetentionMilliseconds: 100,
      readDrainMilliseconds: 0,
    });
    const { prepared: quarantined } = await prepare(controlPlane, {
      attempt: "quarantine-candidate",
      createdAtMs: T0,
    });
    for (let index = 0; index < 2; index += 1) {
      const { prepared: referenced } = await prepare(controlPlane, {
        attempt: `referenced-${index}`,
        mapping: `mapping-referenced-${index}`,
        createdAtMs: T0,
      });
      const published = await controlPlane.publish(referenced);
      if (published.kind !== "published") throw new Error("expected published");
      await controlPlane.flush(published.commit);
      controlPlane.debugSetPreparedState(referenced.handle, "finalized");
    }
    c.set(T0 + 100);
    await controlPlane.reclaimOrphanedPrepared({ olderThanEpochMs: T0 + 1, limit: 1 });
    c.advance(101);

    const first = await controlPlane.reclaimOrphanedPrepared({ olderThanEpochMs: T0 + 1, limit: 2 });
    const second = await controlPlane.reclaimOrphanedPrepared({ olderThanEpochMs: T0 + 1, limit: 2 });

    expect(first).toEqual({ scanned: 3, reclaimed: 1, skippedReferenced: 2 });
    expect(second).toEqual({ scanned: 2, reclaimed: 0, skippedReferenced: 2 });
    expect(controlPlane.debugPrepared(quarantined.handle)).toBeUndefined();
  });

  it("does not let referenced Path-1 rows fill selection slots ahead of a reclaimable row", async () => {
    const c = clock(T0);
    const controlPlane = new InMemoryControlPlane({ nowEpochMilliseconds: c.now });

    for (let index = 0; index < 2; index += 1) {
      const { prepared: referenced } = await prepare(controlPlane, {
        attempt: `selection-slot-reference-${index}`,
        mapping: `mapping-selection-slot-${index}`,
        createdAtMs: T0 - 2 + index,
      });
      const published = await controlPlane.publish(referenced);
      if (published.kind !== "published") throw new Error("expected published");
      await controlPlane.flush(published.commit);
      controlPlane.debugSetPreparedState(referenced.handle, "finalized");
    }
    const { prepared: reclaimable } = await prepare(controlPlane, {
      attempt: "selection-slot-reclaimable",
      createdAtMs: T0,
    });
    c.set(T0 + 100);

    const outcome = await controlPlane.reclaimOrphanedPrepared({
      olderThanEpochMs: T0 + 1,
      limit: 2,
    });

    expect(outcome).toEqual({ scanned: 3, reclaimed: 1, skippedReferenced: 2 });
    expect(controlPlane.debugPrepared(reclaimable.handle)?.state).toBe("quarantined");
  });

  it("caps Path-1 reference metrics when candidates exceed the selection limit", async () => {
    const limit = 2;
    const c = clock(T0);
    const controlPlane = new InMemoryControlPlane({ nowEpochMilliseconds: c.now });

    for (let index = 0; index < 5; index += 1) {
      const { prepared: referenced } = await prepare(controlPlane, {
        attempt: `reference-metric-cap-${index}`,
        mapping: `mapping-reference-cap-${index}`,
        createdAtMs: T0 - 10 + index,
      });
      const published = await controlPlane.publish(referenced);
      if (published.kind !== "published") throw new Error("expected published");
      await controlPlane.flush(published.commit);
      controlPlane.debugSetPreparedState(referenced.handle, "finalized");
    }
    c.set(T0 + 100);

    const outcome = await controlPlane.reclaimOrphanedPrepared({
      olderThanEpochMs: T0 + 1,
      limit,
    });

    expect(outcome.reclaimed).toBe(0);
    expect(outcome.skippedReferenced).toBeLessThanOrEqual(limit);
    expect(outcome.skippedReferenced).toBeLessThanOrEqual(outcome.scanned);
    expect(outcome.scanned).toBeLessThanOrEqual(limit * 2);
  });

  it("caps Path-1 selection when unreferenced candidates exceed the limit", async () => {
    const limit = 2;
    const selectionPlane = new InMemoryControlPlane({ nowEpochMilliseconds: () => T0 });
    for (let index = 0; index < 5; index += 1) {
      await prepare(selectionPlane, {
        attempt: `selection-cap-${index}`,
        createdAtMs: T0 - 10 + index,
      });
    }
    const selection = await selectionPlane.selectFinalizedOrphansForReclaim({
      olderThanEpochMs: T0 + 1,
      limit,
    });
    expect(selection.rows).toHaveLength(limit);
    expect(selection.skippedReferenced).toBe(0);

    const workerPlane = new InMemoryControlPlane({ nowEpochMilliseconds: () => T0 });
    for (let index = 0; index < 5; index += 1) {
      await prepare(workerPlane, {
        attempt: `selection-cap-worker-${index}`,
        createdAtMs: T0 - 10 + index,
      });
    }
    const outcome = await workerPlane.reclaimOrphanedPrepared({
      olderThanEpochMs: T0 + 1,
      limit,
    });
    expect(outcome.reclaimed).toBeLessThanOrEqual(limit);
    expect(outcome.scanned).toBeLessThanOrEqual(limit * 2);
  });

  it("MUT-RECLAIM-COMMITTED: a committed/current-referenced blob is never reclaimed", async () => {
    const c = clock(T0);
    const controlPlane = new InMemoryControlPlane({ nowEpochMilliseconds: c.now });
    const { prepared, input } = await prepare(controlPlane, { createdAtMs: T0 });
    const published = await controlPlane.publish(prepared);
    expect(published.kind).toBe("published");
    if (published.kind !== "published") throw new Error("expected published");
    await controlPlane.flush(published.commit);
    c.set(T0 + 100);

    await controlPlane.reclaimOrphanedPrepared({ olderThanEpochMs: T0 + 1 });

    expect(controlPlane.debugPrepared(prepared.handle)?.state).toBe("committed");
    const read = await controlPlane.readCurrent([{ mappingKey: input.mappingKey }]);
    expect(read).toHaveLength(1);
    expect(read[0]?.encryptedRecord.ciphertext[0]).toBe(1);
  });

  it("MUT-RECLAIM-PENDING-CLAIM: a blob backing a pending claim is not reclaimed", async () => {
    const c = clock(T0);
    const controlPlane = new InMemoryControlPlane({ nowEpochMilliseconds: c.now });
    const { prepared, input } = await prepare(controlPlane, { createdAtMs: T0 });
    const published = await controlPlane.publish(prepared);
    expect(published.kind).toBe("published");
    c.set(T0 + 100);

    await controlPlane.reclaimOrphanedPrepared({ olderThanEpochMs: T0 + 1 });

    expect(controlPlane.debugPrepared(prepared.handle)?.state).toBe("committed");
    expect(controlPlane.debugClaim(input.idempotencyKey)?.state).toBe("pending");
    expect(controlPlane.debugClaim(input.idempotencyKey)?.preparedBlobId).toBe(prepared.handle);
  });

  it("MUT-RECLAIM-HORIZON: a blob newer than olderThan is not reclaimed", async () => {
    const c = clock(T0 + 50);
    const controlPlane = new InMemoryControlPlane({ nowEpochMilliseconds: c.now });
    const { prepared } = await prepare(controlPlane, { createdAtMs: T0 + 50 });

    const outcome = await controlPlane.reclaimOrphanedPrepared({ olderThanEpochMs: T0 });

    expect(outcome.reclaimed).toBe(0);
    expect(controlPlane.debugPrepared(prepared.handle)?.state).toBe("finalized");
  });

  it("MUT-RECLAIM-NOOP: a genuine orphan past horizon is quarantined", async () => {
    const c = clock(T0);
    const controlPlane = new InMemoryControlPlane({ nowEpochMilliseconds: c.now });
    const { prepared } = await prepare(controlPlane, { createdAtMs: T0 });
    c.set(T0 + 100);

    const outcome = await controlPlane.reclaimOrphanedPrepared({ olderThanEpochMs: T0 + 1 });

    expect(outcome.reclaimed).toBe(1);
    expect(controlPlane.debugPrepared(prepared.handle)).toMatchObject({
      state: "quarantined",
      blobPresent: false,
      quarantineBlobPresent: true,
      quarantinedAtMs: T0 + 100,
    });
  });

  it("MUT-RECLAIM-ARG-GETTER: a changing getter cannot widen the sweep", async () => {
    const c = clock(T0 + 50);
    const controlPlane = new InMemoryControlPlane({ nowEpochMilliseconds: c.now });
    const { prepared } = await prepare(controlPlane, { createdAtMs: T0 + 50 });
    let reads = 0;
    const hostile = {
      get olderThanEpochMs(): number {
        reads += 1;
        return reads === 1 ? T0 : T0 + 1_000;
      },
    };

    const outcome = await controlPlane.reclaimOrphanedPrepared(hostile);

    expect(reads).toBe(1);
    expect(outcome.reclaimed).toBe(0);
    expect(controlPlane.debugPrepared(prepared.handle)?.state).toBe("finalized");
  });

  it("MUT-QUARANTINE-NOT-HARDDELETE: quarantine is recoverable within grace and deleted only past grace", async () => {
    const c = clock(T0);
    const controlPlane = new InMemoryControlPlane({
      nowEpochMilliseconds: c.now,
      quarantineGraceMilliseconds: 100,
      supersedeRetentionMilliseconds: 100,
      readDrainMilliseconds: 0,
    });
    const { prepared } = await prepare(controlPlane, { createdAtMs: T0 });
    c.set(T0 + 100);
    await controlPlane.reclaimOrphanedPrepared({ olderThanEpochMs: T0 + 1 });
    expect(controlPlane.debugPrepared(prepared.handle)?.quarantineBlobPresent).toBe(true);

    controlPlane.debugRestoreQuarantined(prepared.handle);
    expect(controlPlane.debugPrepared(prepared.handle)).toMatchObject({ state: "finalized", blobPresent: true });
    await controlPlane.reclaimOrphanedPrepared({ olderThanEpochMs: T0 + 1 });

    c.advance(100);
    await controlPlane.reclaimOrphanedPrepared({ olderThanEpochMs: T0 + 1 });
    expect(controlPlane.debugPrepared(prepared.handle)?.state).toBe("quarantined");
    c.advance(1);
    await controlPlane.reclaimOrphanedPrepared({ olderThanEpochMs: T0 + 1 });
    expect(controlPlane.debugPrepared(prepared.handle)).toBeUndefined();
  });

  it("reclamation arguments reject non-finite, negative, unsafe, and out-of-cap values", async () => {
    const controlPlane = new InMemoryControlPlane();
    await expect(controlPlane.reclaimOrphanedPrepared({ olderThanEpochMs: Number.NaN })).rejects.toThrow();
    await expect(controlPlane.reclaimOrphanedPrepared({ olderThanEpochMs: Number.POSITIVE_INFINITY })).rejects.toThrow();
    await expect(controlPlane.reclaimOrphanedPrepared({ olderThanEpochMs: -1 })).rejects.toThrow();
    await expect(controlPlane.reclaimOrphanedPrepared({ olderThanEpochMs: 0, limit: 0 })).rejects.toThrow();
    await expect(controlPlane.reclaimOrphanedPrepared({ olderThanEpochMs: 0, limit: 10_001 })).rejects.toThrow();
  });
});

describe("GLY-346 Lane A — control-plane state-machine conformance", () => {
  it("uses the plane clock so stale producer metadata cannot age fresh Path-2a or Path-1 rows", async () => {
    const oneHundredHours = 100 * 60 * 60 * 1_000;
    const uploadHorizon = 48 * 60 * 60 * 1_000;
    const c = clock(T0);
    const faults: InMemoryControlPlaneFaults = { failAt: "prepareAfterUploadingInsert" };
    const controlPlane = new InMemoryControlPlane({
      nowEpochMilliseconds: c.now,
      uploadHorizonMilliseconds: uploadHorizon,
      faults,
    });
    const skewedMeta = { createdAtMs: T0 - oneHundredHours };

    await expect(controlPlane.prepare(writeInput(skewedMeta))).rejects.toThrow("prepareAfterUploadingInsert");
    const uploadingHandle = controlPlane.debugPreparedHandles()[0];
    expect(uploadingHandle).toBeDefined();
    if (uploadingHandle === undefined) throw new Error("expected uploading row");

    delete faults.failAt;
    const { prepared: finalized } = await prepare(controlPlane, {
      ...skewedMeta,
      attempt: "skewed-finalized",
    });
    const outcome = await controlPlane.reclaimOrphanedPrepared({
      olderThanEpochMs: T0 - uploadHorizon,
    });

    expect(outcome.reclaimed).toBe(0);
    expect(controlPlane.debugPrepared(uploadingHandle)?.state).toBe("uploading");
    expect(controlPlane.debugPrepared(finalized.handle)?.state).toBe("finalized");
  });

  it("uses an old plane clock so Path-2a and Path-1 become eligible despite fresh producer metadata", async () => {
    const oneHundredHours = 100 * 60 * 60 * 1_000;
    const uploadHorizon = 48 * 60 * 60 * 1_000;
    const c = clock(T0 - oneHundredHours);
    const faults: InMemoryControlPlaneFaults = { failAt: "prepareAfterUploadingInsert" };
    const controlPlane = new InMemoryControlPlane({
      nowEpochMilliseconds: c.now,
      uploadHorizonMilliseconds: uploadHorizon,
      faults,
    });
    const freshMeta = { createdAtMs: T0 };

    await expect(controlPlane.prepare(writeInput(freshMeta))).rejects.toThrow("prepareAfterUploadingInsert");
    const uploadingHandle = controlPlane.debugPreparedHandles()[0];
    expect(uploadingHandle).toBeDefined();
    if (uploadingHandle === undefined) throw new Error("expected uploading row");

    delete faults.failAt;
    const { prepared: finalized } = await prepare(controlPlane, {
      ...freshMeta,
      attempt: "old-plane-finalized",
    });
    c.set(T0);
    const outcome = await controlPlane.reclaimOrphanedPrepared({
      olderThanEpochMs: T0 - uploadHorizon,
    });

    expect(outcome.reclaimed).toBe(2);
    expect(controlPlane.debugPrepared(uploadingHandle)).toBeUndefined();
    expect(controlPlane.debugPrepared(finalized.handle)?.state).toBe("quarantined");
  });

  it("orders Path-1 recovery and fresh candidates like Postgres, not insertion order", async () => {
    const controlPlane = new InMemoryControlPlane({ nowEpochMilliseconds: () => T0 });
    const freshLaterId = brand<PreparedWriteHandle>("00000000-0000-4000-8000-000000000002");
    const freshEarlierId = brand<PreparedWriteHandle>("00000000-0000-4000-8000-000000000001");
    const recoveryId = brand<PreparedWriteHandle>("00000000-0000-4000-8000-000000000003");
    const insert = async (handle: PreparedWriteHandle, suffix: string): Promise<void> => {
      await controlPlane.insertPreparedUploading({
        preparedBlobId: handle,
        tenantId: TENANT,
        mappingKey: brand<ReversalMappingKey>(`mapping-${suffix}`),
        idempotencyKey: brand<ReversalIdempotencyKey>(`idempotency-${suffix}`),
        immutableScopeDigest: brand<ReversalScopeDigest>(`scope-${suffix}`),
        stagingPath: `staging/${handle as unknown as string}`,
        blobPath: `blobs/${handle as unknown as string}`,
        attemptId: brand(`attempt-${suffix}`),
        retentionClass: "matter",
        createdAtEpochMs: T0,
        expiresAtEpochMs: MATTER_EXPIRES_AT,
      });
      await controlPlane.markFinalized({ preparedBlobId: handle, blobEtag: `etag-${suffix}`, blobLength: 1n });
    };
    await insert(freshLaterId, "later");
    await insert(freshEarlierId, "earlier");
    await insert(recoveryId, "recovery");
    controlPlane.debugSetPreparedState(recoveryId, "reclaim_marked");

    const selected = await controlPlane.selectFinalizedOrphansForReclaim({
      olderThanEpochMs: T0 + 1,
      limit: 3,
    });

    expect(selected.rows.map((row) => row.preparedBlobId)).toEqual([
      recoveryId,
      freshEarlierId,
      freshLaterId,
    ]);
  });

  it("publish-loss then crash preserves pending claim and retry recovers through flush", async () => {
    const c = clock(T0);
    const controlPlane = new InMemoryControlPlane({ nowEpochMilliseconds: c.now });
    const { prepared, input } = await prepare(controlPlane);
    const first = await controlPlane.publish(prepared);
    expect(first.kind).toBe("published");
    expect(controlPlane.debugClaim(input.idempotencyKey)?.state).toBe("pending");

    controlPlane.crash();
    const retry = await controlPlane.publish(prepared);
    expect(retry).toMatchObject({ kind: "existing", expired: false });
    if (retry.kind !== "existing") throw new Error("expected existing");
    await controlPlane.flush(retry.commit);

    expect(controlPlane.debugClaim(input.idempotencyKey)?.state).toBe("flushed");
    expect(await controlPlane.readCurrent([{ mappingKey: input.mappingKey }])).toHaveLength(1);
  });

  it("expired-pending tombstones and detaches, preserves expiry/key, orphans and remains expired", async () => {
    const c = clock(T0);
    const controlPlane = new InMemoryControlPlane({ nowEpochMilliseconds: c.now });
    const winner = await prepare(controlPlane, { expiresAtMs: BigInt(T0 + 10) });
    const first = await controlPlane.publish(winner.prepared);
    expect(first.kind).toBe("published");
    const before = controlPlane.debugClaim(winner.input.idempotencyKey);
    const loser = await prepare(controlPlane, { expiresAtMs: BigInt(T0 + 10) });
    c.set(T0 + 10);

    const conflict = await controlPlane.publish(loser.prepared);
    expect(conflict).toMatchObject({ kind: "existing", expired: true });
    const expired = controlPlane.debugClaim(winner.input.idempotencyKey);
    expect(expired).toMatchObject({ state: "expired", preparedBlobId: null });
    expect(expired?.expiresAtMs).toBe(before?.expiresAtMs);
    expect(expired?.idempotencyKey).toBe(before?.idempotencyKey);
    expect(controlPlane.debugPrepared(winner.prepared.handle)?.state).toBe("orphaned");
    const later = await controlPlane.publish(loser.prepared);
    expect(later).toMatchObject({ kind: "existing", expired: true });

    const reclaimed = await controlPlane.reclaimOrphanedPrepared({ olderThanEpochMs: T0 + 1 });
    expect(reclaimed.reclaimed).toBe(2);
    expect(controlPlane.debugPrepared(winner.prepared.handle)?.state).toBe("quarantined");
  });

  it("concurrent mark-vs-publish: publish wins committed transition and maintenance cannot quarantine it", async () => {
    const c = clock(T0);
    const controlPlane = new InMemoryControlPlane({ nowEpochMilliseconds: c.now });
    const { prepared, input } = await prepare(controlPlane, { createdAtMs: T0 });
    c.set(T0 + 100);

    const [published] = await Promise.all([
      controlPlane.publish(prepared),
      controlPlane.reclaimOrphanedPrepared({ olderThanEpochMs: T0 + 1 }),
    ]);

    expect(published.kind).toBe("published");
    expect(controlPlane.debugPrepared(prepared.handle)?.state).toBe("committed");
    expect(controlPlane.debugClaim(input.idempotencyKey)?.preparedBlobId).toBe(prepared.handle);
  });

  it("upload_reclaim_marked crash is recovered by the next age-independent sweep (N1)", async () => {
    const c = clock(T0);
    const faults: InMemoryControlPlaneFaults = { failAt: "prepareAfterUploadingInsert" };
    const controlPlane = new InMemoryControlPlane({
      nowEpochMilliseconds: c.now,
      uploadHorizonMilliseconds: 10,
      faults,
    });
    await expect(controlPlane.prepare(writeInput({ createdAtMs: T0 }))).rejects.toThrow("prepareAfterUploadingInsert");
    const handle = controlPlane.debugPreparedHandles()[0];
    expect(handle).toBeDefined();
    if (handle === undefined) throw new Error("expected uploading row");
    c.set(T0 + 100);
    faults.failAt = "reclaimAfterUploadMark";
    await expect(controlPlane.reclaimOrphanedPrepared({ olderThanEpochMs: T0 + 1 })).rejects.toThrow("reclaimAfterUploadMark");
    expect(controlPlane.debugPrepared(handle)?.state).toBe("upload_reclaim_marked");

    controlPlane.crash();
    delete faults.failAt;
    const recovered = await controlPlane.reclaimOrphanedPrepared({ olderThanEpochMs: 0 });
    expect(recovered.reclaimed).toBe(1);
    expect(controlPlane.debugPrepared(handle)).toBeUndefined();
  });

  it("readCurrent throws when a durable current pointer has no blob", async () => {
    const controlPlane = new InMemoryControlPlane({ nowEpochMilliseconds: () => T0 });
    const { prepared, input } = await prepare(controlPlane);
    const published = await controlPlane.publish(prepared);
    if (published.kind !== "published") throw new Error("expected published");
    await controlPlane.flush(published.commit);
    controlPlane.debugDeleteBlob(prepared.handle);

    await expect(controlPlane.readCurrent([{ mappingKey: input.mappingKey }])).rejects.toThrow("integrity");
  });

  it("nonce first reservation is zero and subsequent values strictly increase without repeat across crash", async () => {
    const controlPlane = new InMemoryControlPlane();
    const request = {
      tenantId: TENANT,
      matterId: MATTER,
      dekGenerationId: brand<DekGenerationId>("generation-a"),
    };
    const first = await controlPlane.reserveNonce(request);
    const second = await controlPlane.reserveNonce(request);
    controlPlane.crash();
    const third = await controlPlane.reserveNonce(request);

    expect([nonceValue(first), nonceValue(second), nonceValue(third)]).toEqual([0n, 1n, 2n]);
    expect(new Set([Buffer.from(first).toString("hex"), Buffer.from(second).toString("hex"), Buffer.from(third).toString("hex")]).size).toBe(3);
  });

  it("ordinal out-of-order flush does not roll the current pointer back", async () => {
    const controlPlane = new InMemoryControlPlane({ nowEpochMilliseconds: () => T0 });
    const older = await prepare(controlPlane, { attempt: "attempt-1", marker: 1 });
    const newer = await prepare(controlPlane, { attempt: "attempt-2", marker: 2 });
    const oldPublish = await controlPlane.publish(older.prepared);
    const newPublish = await controlPlane.publish(newer.prepared);
    if (oldPublish.kind !== "published" || newPublish.kind !== "published") throw new Error("expected publications");

    await controlPlane.flush(newPublish.commit);
    await controlPlane.flush(oldPublish.commit);

    const current = controlPlane.debugCurrent(older.input.mappingKey);
    expect(current?.commitHandle).toBe(newPublish.commit);
    expect(current?.ordinal).toBeGreaterThan(controlPlane.debugClaim(older.input.idempotencyKey)?.ordinal ?? 0n);
    const read = await controlPlane.readCurrent([{ mappingKey: older.input.mappingKey }]);
    expect(read[0]?.encryptedRecord.ciphertext[0]).toBe(2);
  });

  it("matter expiry exactly 2^64-1 stores and compares without overflow", async () => {
    const controlPlane = new InMemoryControlPlane({ nowEpochMilliseconds: () => Number.MAX_SAFE_INTEGER });
    const fixture = await prepare(controlPlane, { expiresAtMs: 2n ** 64n - 1n });
    const published = await controlPlane.publish(fixture.prepared);
    expect(controlPlane.debugClaim(fixture.input.idempotencyKey)?.expiresAtMs).toBe(2n ** 64n - 1n);
    const retry = await controlPlane.publish(fixture.prepared);
    expect(retry).toMatchObject({ kind: "existing", expired: false });
    expect(controlPlane.debugClaim(fixture.input.idempotencyKey)?.state).toBe("pending");
    expect(published.kind).toBe("published");
  });

  it("implements frozen SpoolVolume for DurableReversalStore record-to-resolve round trip", async () => {
    const controlPlane = new InMemoryControlPlane({ nowEpochMilliseconds: () => T0 });
    const store = new DurableReversalStore({
      keyProvider: new InMemoryKeyProvider(),
      spoolVolume: controlPlane,
      classifyRetention: async () => "matter",
      nowEpochMilliseconds: () => T0,
      maximumEncounteredTokenBatch: 32,
    });
    await store.record({
      tenantId: TENANT,
      matterId: MATTER,
      dictionaryVersion: VERSION,
      token: TOKEN,
      canonical: "Maria García",
      attemptId: brand<OperationAttemptId>("round-trip"),
    });

    const resolved = await store.resolveEncounteredTokens({
      tenantId: TENANT,
      matterId: MATTER,
      dictionaryVersion: VERSION,
      tokens: [TOKEN],
    });
    expect(resolved.get(TOKEN)).toBe("Maria García");
  });
});

describe("GLY-345 Part B — superseded lifecycle conformance", () => {
  async function publishAndFlush(controlPlane: InMemoryControlPlane, fixture: PreparedFixture) {
    const published = await controlPlane.publish(fixture.prepared);
    if (published.kind !== "published") throw new Error("expected publication");
    await controlPlane.flush(published.commit);
    return published.commit;
  }

  it("advances current and atomically supersedes/detaches the prior committed pair", async () => {
    const c = clock(T0);
    const controlPlane = new InMemoryControlPlane({ nowEpochMilliseconds: c.now });
    const old = await prepare(controlPlane, { attempt: "supersede-old", marker: 1 });
    const oldCommit = await publishAndFlush(controlPlane, old);
    const fresh = await prepare(controlPlane, { attempt: "supersede-new", marker: 2 });
    const freshPublish = await controlPlane.publish(fresh.prepared);
    if (freshPublish.kind !== "published") throw new Error("expected publication");
    c.set(T0 + 25);
    await controlPlane.flush(freshPublish.commit);

    expect(controlPlane.debugCurrent(old.input.mappingKey)).toMatchObject({
      commitHandle: freshPublish.commit,
      preparedBlobId: fresh.prepared.handle,
    });
    expect(controlPlane.debugClaim(old.input.idempotencyKey)).toMatchObject({
      state: "superseded",
      preparedBlobId: null,
      commitHandle: oldCommit,
    });
    expect(controlPlane.debugPrepared(old.prepared.handle)).toMatchObject({
      state: "superseded",
      supersededAtMs: T0 + 25,
      reclaimAfterMs: undefined,
    });
    expect(controlPlane.debugClaim(fresh.input.idempotencyKey)?.state).toBe("flushed");
    expect(controlPlane.debugPrepared(fresh.prepared.handle)?.state).toBe("committed");

    controlPlane.debugDeleteBlob(old.prepared.handle);
    await expect(controlPlane.flush(oldCommit)).resolves.toBeUndefined();
    expect(controlPlane.debugCurrent(old.input.mappingKey)?.commitHandle).toBe(freshPublish.commit);
  });

  it("makes every intra-flush advance gate atomic and replay-recoverable", async () => {
    const phases = [
      "flushAfterLockVerify",
      "flushAfterNewClaim",
      "flushAfterPointerCas",
      "flushAfterOldClaim",
      "flushAfterOldPrepared",
    ] as const;
    for (const phase of phases) {
      const c = clock(T0);
      const faults: InMemoryControlPlaneFaults = {};
      const controlPlane = new InMemoryControlPlane({ nowEpochMilliseconds: c.now, faults });
      const old = await prepare(controlPlane, { attempt: `advance-old-${phase}` });
      const oldCommit = await publishAndFlush(controlPlane, old);
      const fresh = await prepare(controlPlane, { attempt: `advance-new-${phase}`, marker: 2 });
      const freshPublish = await controlPlane.publish(fresh.prepared);
      if (freshPublish.kind !== "published") throw new Error("expected publication");

      faults.failAt = phase;
      await expect(controlPlane.flush(freshPublish.commit)).rejects.toThrow(phase);
      expect(controlPlane.debugCurrent(old.input.mappingKey)?.commitHandle, phase).toBe(oldCommit);
      expect(controlPlane.debugClaim(old.input.idempotencyKey), phase).toMatchObject({
        state: "flushed",
        preparedBlobId: old.prepared.handle,
      });
      expect(controlPlane.debugPrepared(old.prepared.handle)?.state, phase).toBe("committed");
      expect(controlPlane.debugClaim(fresh.input.idempotencyKey), phase).toMatchObject({
        state: "pending",
        preparedBlobId: fresh.prepared.handle,
      });
      expect(controlPlane.debugPrepared(fresh.prepared.handle)?.state, phase).toBe("committed");

      delete faults.failAt;
      await controlPlane.flush(freshPublish.commit);
      expect(controlPlane.debugCurrent(old.input.mappingKey)?.commitHandle, phase).toBe(freshPublish.commit);
      expect(controlPlane.debugClaim(old.input.idempotencyKey)?.state, phase).toBe("superseded");
    }
  });

  it("makes both losing-CAS gates atomic and replay-recoverable", async () => {
    for (const phase of ["flushAfterLoserClaim", "flushAfterLoserPrepared"] as const) {
      const faults: InMemoryControlPlaneFaults = {};
      const controlPlane = new InMemoryControlPlane({ nowEpochMilliseconds: () => T0, faults });
      const older = await prepare(controlPlane, { attempt: `loser-old-${phase}`, marker: 1 });
      const newer = await prepare(controlPlane, { attempt: `loser-new-${phase}`, marker: 2 });
      const oldPublish = await controlPlane.publish(older.prepared);
      const newPublish = await controlPlane.publish(newer.prepared);
      if (oldPublish.kind !== "published" || newPublish.kind !== "published") throw new Error("expected publications");
      await controlPlane.flush(newPublish.commit);

      faults.failAt = phase;
      await expect(controlPlane.flush(oldPublish.commit)).rejects.toThrow(phase);
      expect(controlPlane.debugCurrent(older.input.mappingKey)?.commitHandle, phase).toBe(newPublish.commit);
      expect(controlPlane.debugClaim(older.input.idempotencyKey), phase).toMatchObject({
        state: "pending",
        preparedBlobId: older.prepared.handle,
      });
      expect(controlPlane.debugPrepared(older.prepared.handle)?.state, phase).toBe("committed");

      delete faults.failAt;
      await controlPlane.flush(oldPublish.commit);
      expect(controlPlane.debugClaim(older.input.idempotencyKey), phase).toMatchObject({
        state: "superseded",
        preparedBlobId: null,
      });
      expect(controlPlane.debugPrepared(older.prepared.handle)?.state, phase).toBe("superseded");
    }
  });

  it("computes matter and detector candidacy exactly and never selects live committed matter", async () => {
    const c = clock(T0);
    const controlPlane = new InMemoryControlPlane({
      nowEpochMilliseconds: c.now,
      quarantineGraceMilliseconds: 50,
      supersedeRetentionMilliseconds: 100,
      readDrainMilliseconds: 20,
    });
    const matter = await prepare(controlPlane, { attempt: "matter-old" });
    await publishAndFlush(controlPlane, matter);
    const detectorExpiry = BigInt(T0 + 40);
    const detector = await prepare(controlPlane, { attempt: "detector-old", expiresAtMs: detectorExpiry });
    const detectorPublish = await controlPlane.publish(detector.prepared);
    if (detectorPublish.kind !== "published") throw new Error("expected publication");
    await controlPlane.flush(detectorPublish.commit);
    const winner = await prepare(controlPlane, { attempt: "winner", marker: 3 });
    await publishAndFlush(controlPlane, winner);

    expect(controlPlane.debugPrepared(matter.prepared.handle)?.supersededAtMs).toBe(T0);
    expect(controlPlane.debugPrepared(detector.prepared.handle)?.supersededAtMs).toBe(T0);
    c.set(T0 + 39);
    await expect(controlPlane.previewReclamation({
      olderThanEpochMs: 0,
      uploadHorizonEpochMs: 0,
      quarantinedBeforeEpochMs: 0,
      limit: 10,
      includeHardDelete: false,
      supersedeRetentionMs: 100,
      readDrainMs: 20,
    })).resolves.toEqual({ scanned: 0, reclaimed: 0, skippedReferenced: 0 });

    c.set(T0 + 40);
    const detectorDue = await controlPlane.selectFinalizedOrphansForReclaim({
      olderThanEpochMs: 0,
      limit: 10,
      supersedeRetentionMs: 100,
      readDrainMs: 20,
    });
    expect(detectorDue.rows.map((row) => row.preparedBlobId)).toEqual([detector.prepared.handle]);
    expect(controlPlane.debugPrepared(detector.prepared.handle)?.reclaimAfterMs).toBe(BigInt(T0 + 40));
    await controlPlane.markQuarantined({
      preparedBlobId: detector.prepared.handle,
      quarantinedAtEpochMs: T0 + 40,
    });
    await controlPlane.completeHardDeleteQuarantined(detector.prepared.handle);

    c.set(T0 + 99);
    expect((await controlPlane.selectFinalizedOrphansForReclaim({
      olderThanEpochMs: 0,
      limit: 10,
      supersedeRetentionMs: 100,
      readDrainMs: 20,
    })).rows).toEqual([]);
    c.set(T0 + 100);
    const matterDue = await controlPlane.selectFinalizedOrphansForReclaim({
      olderThanEpochMs: 0,
      limit: 10,
      supersedeRetentionMs: 100,
      readDrainMs: 20,
    });
    expect(matterDue.rows.map((row) => row.preparedBlobId)).toEqual([matter.prepared.handle]);
    expect(matterDue.skippedReferenced).toBe(0);
    expect(controlPlane.debugPrepared(matter.prepared.handle)?.reclaimAfterMs).toBe(BigInt(T0 + 100));
    expect(controlPlane.debugPrepared(winner.prepared.handle)?.state).toBe("committed");
  });

  it("keeps the drain MAX floor and ignores backfilled record-created time", async () => {
    const c = clock(T0);
    const controlPlane = new InMemoryControlPlane({
      nowEpochMilliseconds: c.now,
      quarantineGraceMilliseconds: 80,
      supersedeRetentionMilliseconds: 100,
      readDrainMilliseconds: 80,
    });
    const detector = await prepare(controlPlane, {
      attempt: "drain-floor-detector",
      expiresAtMs: BigInt(T0 + 10),
    });
    await publishAndFlush(controlPlane, detector);
    const winner = await prepare(controlPlane, { attempt: "drain-floor-winner" });
    await publishAndFlush(controlPlane, winner);
    controlPlane.debugSetRecordRetentionOrigin(detector.prepared.handle, 0, "backfilled");

    c.set(T0 + 79);
    expect((await controlPlane.selectFinalizedOrphansForReclaim({
      olderThanEpochMs: Number.MAX_SAFE_INTEGER,
      limit: 10,
      supersedeRetentionMs: 100,
      readDrainMs: 80,
    })).rows).toEqual([]);
    controlPlane.debugSetRecordRetentionOrigin(detector.prepared.handle, T0 + 1_000_000, "backfilled");
    c.set(T0 + 80);
    expect((await controlPlane.selectFinalizedOrphansForReclaim({
      olderThanEpochMs: 0,
      limit: 10,
      supersedeRetentionMs: 100,
      readDrainMs: 80,
    })).rows.map((row) => row.preparedBlobId)).toEqual([detector.prepared.handle]);
  });

  it("keeps the detector floor inert at production windows because authenticated expiry wins", async () => {
    const day = 86_400_000;
    const c = clock(T0);
    const controlPlane = new InMemoryControlPlane({
      nowEpochMilliseconds: c.now,
      quarantineGraceMilliseconds: day,
      supersedeRetentionMilliseconds: 30 * day,
      readDrainMilliseconds: 60_000,
    });
    const detector = await prepare(controlPlane, {
      attempt: "production-detector-floor",
      createdAtMs: T0,
      expiresAtMs: BigInt(T0 + day),
    });
    await publishAndFlush(controlPlane, detector);
    const winner = await prepare(controlPlane, { attempt: "production-detector-winner" });
    await publishAndFlush(controlPlane, winner);

    c.set(T0 + day - 1);
    expect((await controlPlane.selectFinalizedOrphansForReclaim({
      olderThanEpochMs: 0,
      limit: 10,
      supersedeRetentionMs: 30 * day,
      readDrainMs: 60_000,
    })).rows).toEqual([]);
    c.set(T0 + day);
    expect((await controlPlane.selectFinalizedOrphansForReclaim({
      olderThanEpochMs: 0,
      limit: 10,
      supersedeRetentionMs: 30 * day,
      readDrainMs: 60_000,
    })).rows.map((row) => row.preparedBlobId)).toEqual([detector.prepared.handle]);
    expect(controlPlane.debugPrepared(detector.prepared.handle)?.reclaimAfterMs).toBe(BigInt(T0 + day));
  });

  it.each([
    { name: "matter", expiresAtMs: MATTER_EXPIRES_AT, candidacyDelta: 10 },
    { name: "detector", expiresAtMs: BigInt(T0 + 5), candidacyDelta: 5 },
  ])("stacks $name candidacy, quarantine grace, and later full-sweep latency", async ({ name, expiresAtMs, candidacyDelta }) => {
    const c = clock(T0);
    const controlPlane = new InMemoryControlPlane({
      nowEpochMilliseconds: c.now,
      quarantineGraceMilliseconds: 10,
      supersedeRetentionMilliseconds: 10,
      readDrainMilliseconds: 0,
    });
    const old = await prepare(controlPlane, { attempt: `stack-old-${name}`, expiresAtMs });
    await publishAndFlush(controlPlane, old);
    const winner = await prepare(controlPlane, { attempt: `stack-winner-${name}` });
    await publishAndFlush(controlPlane, winner);

    c.set(T0 + candidacyDelta - 1);
    await controlPlane.reclaimOrphanedPrepared({ olderThanEpochMs: 0 });
    expect(controlPlane.debugPrepared(old.prepared.handle)).toMatchObject({
      state: "superseded",
      blobPresent: true,
      quarantineBlobPresent: false,
    });
    c.set(T0 + candidacyDelta);
    await controlPlane.reclaimOrphanedPrepared({ olderThanEpochMs: 0 });
    expect(controlPlane.debugPrepared(old.prepared.handle)).toMatchObject({
      state: "quarantined",
      blobPresent: false,
      quarantineBlobPresent: true,
      quarantinedAtMs: T0 + candidacyDelta,
    });
    c.set(T0 + candidacyDelta + 10);
    await controlPlane.reclaimOrphanedPrepared({ olderThanEpochMs: 0 });
    expect(controlPlane.debugPrepared(old.prepared.handle)?.state).toBe("quarantined");
    c.advance(1); // measured later-sweep latency; strict grace boundary remains preserved.
    await controlPlane.reclaimOrphanedPrepared({ olderThanEpochMs: 0 });
    expect(controlPlane.debugPrepared(old.prepared.handle)).toBeUndefined();
  });

  it("keeps a durable operation binding after every prepared byte/row is reclaimed", async () => {
    const c = clock(T0);
    const controlPlane = new InMemoryControlPlane({
      nowEpochMilliseconds: c.now,
      uploadHorizonMilliseconds: 1,
      quarantineGraceMilliseconds: 1,
      supersedeRetentionMilliseconds: 1,
      readDrainMilliseconds: 0,
    });
    const anchored = await prepare(controlPlane, { attempt: "binding-survives-gc" });
    c.set(T0 + 1);
    await controlPlane.reclaimOrphanedPrepared({ olderThanEpochMs: T0 + 1 });
    c.set(T0 + 3);
    await controlPlane.reclaimOrphanedPrepared({ olderThanEpochMs: T0 + 1 });
    expect(controlPlane.debugPrepared(anchored.prepared.handle)).toBeUndefined();
    expect(controlPlane.debugOperationRetention(String(TENANT), "binding-survives-gc")).toBe("matter");

    await expect(controlPlane.prepare(writeInput({
      attempt: "binding-survives-gc",
      expiresAtMs: BigInt(T0 + 86_400_000),
    }))).rejects.toThrow("retention_binding_mismatch");
  });

  it("counts but never marks a referenced synthetic superseded row", async () => {
    const c = clock(T0 + 1_000);
    const controlPlane = new InMemoryControlPlane({ nowEpochMilliseconds: c.now });
    const fixture = await prepare(controlPlane, { attempt: "referenced-superseded" });
    const published = await controlPlane.publish(fixture.prepared);
    if (published.kind !== "published") throw new Error("expected publication");
    controlPlane.debugSetSupersededMetadata(fixture.prepared.handle, T0, "matter", MATTER_EXPIRES_AT);

    const selected = await controlPlane.selectFinalizedOrphansForReclaim({
      olderThanEpochMs: Number.MAX_SAFE_INTEGER,
      limit: 1,
      supersedeRetentionMs: 1,
      readDrainMs: 0,
    });
    expect(selected).toEqual({ rows: [], skippedReferenced: 1 });
    expect(controlPlane.debugPrepared(fixture.prepared.handle)?.state).toBe("superseded");
  });

  it("self-heals a stale non-current flushed pair under both crash gates, even without its blob", async () => {
    for (const phase of ["selfHealAfterLockVerify", "selfHealAfterCte"] as const) {
      const faults: InMemoryControlPlaneFaults = {};
      const controlPlane = new InMemoryControlPlane({ nowEpochMilliseconds: () => T0, faults });
      const old = await prepare(controlPlane, { attempt: `self-heal-old-${phase}` });
      const oldCommit = await publishAndFlush(controlPlane, old);
      const fresh = await prepare(controlPlane, { attempt: `self-heal-new-${phase}`, marker: 2 });
      const freshCommit = await publishAndFlush(controlPlane, fresh);
      controlPlane.debugSetPreparedState(old.prepared.handle, "committed");
      controlPlane.debugSetClaimLifecycle(old.input.idempotencyKey, "flushed", old.prepared.handle);
      controlPlane.debugDeleteBlob(old.prepared.handle);

      faults.failAt = phase;
      await expect(Promise.resolve().then(() => controlPlane.publish(old.prepared))).rejects.toThrow(phase);
      expect(controlPlane.debugClaim(old.input.idempotencyKey), phase).toMatchObject({
        state: "flushed",
        preparedBlobId: old.prepared.handle,
        commitHandle: oldCommit,
      });
      expect(controlPlane.debugPrepared(old.prepared.handle)?.state, phase).toBe("committed");
      expect(controlPlane.debugCurrent(old.input.mappingKey)?.commitHandle, phase).toBe(freshCommit);

      delete faults.failAt;
      await expect(controlPlane.publish(old.prepared)).resolves.toMatchObject({
        kind: "existing",
        commit: oldCommit,
      });
      expect(controlPlane.debugClaim(old.input.idempotencyKey), phase).toMatchObject({
        state: "superseded",
        preparedBlobId: null,
      });
      expect(controlPlane.debugPrepared(old.prepared.handle)?.state, phase).toBe("superseded");
      await expect(controlPlane.flush(oldCommit)).resolves.toBeUndefined();
      expect(controlPlane.debugCurrent(old.input.mappingKey)?.commitHandle, phase).toBe(freshCommit);
    }
  });
});

describe("GLY-345 Part A — dev anchor transaction crash gates", () => {
  it.each(["anchorAfterBindingInsert", "anchorAfterPreparedInsert"] as const)(
    "rolls back both binding and prepared row at %s",
    async (phase) => {
      const faults: InMemoryControlPlaneFaults = { failAt: phase };
      const controlPlane = new InMemoryControlPlane({ nowEpochMilliseconds: () => T0, faults });
      await expect(Promise.resolve().then(() => controlPlane.prepare(writeInput({ attempt: `anchor-${phase}` }))))
        .rejects.toThrow(phase);
      expect(controlPlane.debugOperationRetention(String(TENANT), `anchor-${phase}`)).toBeUndefined();
      expect(controlPlane.debugPreparedHandles()).toEqual([]);

      delete faults.failAt;
      await expect(controlPlane.prepare(writeInput({
        attempt: `anchor-${phase}`,
        expiresAtMs: BigInt(T0 + 86_400_000),
      }))).resolves.toBeDefined();
      expect(controlPlane.debugOperationRetention(String(TENANT), `anchor-${phase}`)).toBe("detector-only");
    },
  );
});
