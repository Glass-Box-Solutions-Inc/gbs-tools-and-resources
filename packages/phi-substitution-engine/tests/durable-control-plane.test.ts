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
} = {}): PrepareReversalWriteInput {
  const attemptId = brand<OperationAttemptId>(options.attempt ?? "attempt-a");
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
      retentionClass: options.expiresAtMs === undefined ? "matter" : "detector-only",
      createdAtEpochMs: options.createdAtMs ?? T0,
      expiresAtEpochMs: options.expiresAtMs ?? MATTER_EXPIRES_AT,
    },
  };
  return {
    idempotencyKey: idempotencyKeyOf(TENANT, attemptId, TOKEN),
    mappingKey: mappingKeyOf(TENANT, MATTER, VERSION, TOKEN),
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
    const controlPlane = new InMemoryControlPlane();
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
    const c = clock(T0 + 100);
    const controlPlane = new InMemoryControlPlane({
      nowEpochMilliseconds: c.now,
      quarantineGraceMilliseconds: 100,
    });
    const { prepared: quarantined } = await prepare(controlPlane, {
      attempt: "quarantine-candidate",
      createdAtMs: T0,
    });
    await controlPlane.reclaimOrphanedPrepared({ olderThanEpochMs: T0 + 1, limit: 1 });

    for (let index = 0; index < 2; index += 1) {
      const { prepared: referenced } = await prepare(controlPlane, {
        attempt: `referenced-${index}`,
        createdAtMs: T0,
      });
      const published = await controlPlane.publish(referenced);
      if (published.kind !== "published") throw new Error("expected published");
      await controlPlane.flush(published.commit);
      controlPlane.debugSetPreparedState(referenced.handle, "finalized");
    }
    c.advance(101);

    const first = await controlPlane.reclaimOrphanedPrepared({ olderThanEpochMs: T0 + 1, limit: 2 });
    const second = await controlPlane.reclaimOrphanedPrepared({ olderThanEpochMs: T0 + 1, limit: 2 });

    expect(first).toEqual({ scanned: 3, reclaimed: 1, skippedReferenced: 2 });
    expect(second).toEqual({ scanned: 2, reclaimed: 0, skippedReferenced: 2 });
    expect(controlPlane.debugPrepared(quarantined.handle)).toBeUndefined();
  });

  it("does not let referenced Path-1 rows fill selection slots ahead of a reclaimable row", async () => {
    const c = clock(T0 + 100);
    const controlPlane = new InMemoryControlPlane({ nowEpochMilliseconds: c.now });

    for (let index = 0; index < 2; index += 1) {
      const { prepared: referenced } = await prepare(controlPlane, {
        attempt: `selection-slot-reference-${index}`,
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

    const outcome = await controlPlane.reclaimOrphanedPrepared({
      olderThanEpochMs: T0 + 1,
      limit: 2,
    });

    expect(outcome).toEqual({ scanned: 3, reclaimed: 1, skippedReferenced: 2 });
    expect(controlPlane.debugPrepared(reclaimable.handle)?.state).toBe("quarantined");
  });

  it("caps Path-1 reference metrics when candidates exceed the selection limit", async () => {
    const limit = 2;
    const controlPlane = new InMemoryControlPlane({ nowEpochMilliseconds: () => T0 + 100 });

    for (let index = 0; index < 5; index += 1) {
      const { prepared: referenced } = await prepare(controlPlane, {
        attempt: `reference-metric-cap-${index}`,
        createdAtMs: T0 - 10 + index,
      });
      const published = await controlPlane.publish(referenced);
      if (published.kind !== "published") throw new Error("expected published");
      await controlPlane.flush(published.commit);
      controlPlane.debugSetPreparedState(referenced.handle, "finalized");
    }

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
    const selectionPlane = new InMemoryControlPlane({ nowEpochMilliseconds: () => T0 + 100 });
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

    const workerPlane = new InMemoryControlPlane({ nowEpochMilliseconds: () => T0 + 100 });
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
    const c = clock(T0 + 100);
    const controlPlane = new InMemoryControlPlane({ nowEpochMilliseconds: c.now });
    const { prepared, input } = await prepare(controlPlane, { createdAtMs: T0 });
    const published = await controlPlane.publish(prepared);
    expect(published.kind).toBe("published");
    if (published.kind !== "published") throw new Error("expected published");
    await controlPlane.flush(published.commit);

    await controlPlane.reclaimOrphanedPrepared({ olderThanEpochMs: T0 + 1 });

    expect(controlPlane.debugPrepared(prepared.handle)?.state).toBe("committed");
    const read = await controlPlane.readCurrent([{ mappingKey: input.mappingKey }]);
    expect(read).toHaveLength(1);
    expect(read[0]?.encryptedRecord.ciphertext[0]).toBe(1);
  });

  it("MUT-RECLAIM-PENDING-CLAIM: a blob backing a pending claim is not reclaimed", async () => {
    const c = clock(T0 + 100);
    const controlPlane = new InMemoryControlPlane({ nowEpochMilliseconds: c.now });
    const { prepared, input } = await prepare(controlPlane, { createdAtMs: T0 });
    const published = await controlPlane.publish(prepared);
    expect(published.kind).toBe("published");

    await controlPlane.reclaimOrphanedPrepared({ olderThanEpochMs: T0 + 1 });

    expect(controlPlane.debugPrepared(prepared.handle)?.state).toBe("committed");
    expect(controlPlane.debugClaim(input.idempotencyKey)?.state).toBe("pending");
    expect(controlPlane.debugClaim(input.idempotencyKey)?.preparedBlobId).toBe(prepared.handle);
  });

  it("MUT-RECLAIM-HORIZON: a blob newer than olderThan is not reclaimed", async () => {
    const c = clock(T0 + 100);
    const controlPlane = new InMemoryControlPlane({ nowEpochMilliseconds: c.now });
    const { prepared } = await prepare(controlPlane, { createdAtMs: T0 + 50 });

    const outcome = await controlPlane.reclaimOrphanedPrepared({ olderThanEpochMs: T0 });

    expect(outcome.reclaimed).toBe(0);
    expect(controlPlane.debugPrepared(prepared.handle)?.state).toBe("finalized");
  });

  it("MUT-RECLAIM-NOOP: a genuine orphan past horizon is quarantined", async () => {
    const c = clock(T0 + 100);
    const controlPlane = new InMemoryControlPlane({ nowEpochMilliseconds: c.now });
    const { prepared } = await prepare(controlPlane, { createdAtMs: T0 });

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
    const c = clock(T0 + 100);
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
    const c = clock(T0 + 100);
    const controlPlane = new InMemoryControlPlane({
      nowEpochMilliseconds: c.now,
      quarantineGraceMilliseconds: 100,
    });
    const { prepared } = await prepare(controlPlane, { createdAtMs: T0 });
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
  it("orders Path-1 recovery and fresh candidates like Postgres, not insertion order", async () => {
    const controlPlane = new InMemoryControlPlane();
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
        createdAtEpochMs: T0,
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
    const winner = await prepare(controlPlane, { expiresAtMs: BigInt(T0 + 10), createdAtMs: T0 });
    const first = await controlPlane.publish(winner.prepared);
    expect(first.kind).toBe("published");
    const before = controlPlane.debugClaim(winner.input.idempotencyKey);
    c.set(T0 + 10);

    const loser = await prepare(controlPlane, { expiresAtMs: BigInt(T0 + 10), createdAtMs: T0 });
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
    const c = clock(T0 + 100);
    const controlPlane = new InMemoryControlPlane({ nowEpochMilliseconds: c.now });
    const { prepared, input } = await prepare(controlPlane, { createdAtMs: T0 });

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
