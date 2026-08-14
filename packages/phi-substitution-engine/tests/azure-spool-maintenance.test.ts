import { randomUUID } from "node:crypto";
import { Pool, type PoolConfig } from "pg";
import { afterAll, beforeAll, beforeEach, describe, expect, it } from "vitest";
import type { TenantId } from "../src/core/brands";
import { AzureSpoolMaintenance } from "../src/tokens/durable/azure/azure-spool-maintenance";
import type { BlobProperties, BlobStore } from "../src/tokens/durable/azure/blob-store";
import type { ControlPlane } from "../src/tokens/durable/azure/control-plane";
import { PostgresControlPlane, runMigrations } from "../src/tokens/durable/azure/postgres-control-plane";
import { InMemoryControlPlane } from "../src/tokens/durable/dev/in-memory-control-plane";
import type {
  PreparedWriteHandle,
  ReversalIdempotencyKey,
  ReversalMappingKey,
  ReversalScopeDigest,
} from "../src/tokens/durable/ports";

const T0 = 1_700_000_000_000;
const brand = <T>(value: unknown): T => value as unknown as T;
const TENANT = brand<TenantId>("tenant-maintenance");

function notFound(): Error & { readonly statusCode: number } {
  return Object.assign(new Error("fake_not_found"), { statusCode: 404 });
}

class FakeBlobStore implements BlobStore {
  readonly #objects = new Map<string, Uint8Array>();
  readonly #etags = new Map<string, string>();
  readonly #stickyRemovals = new Set<string>();
  #etagSequence = 0;
  public readonly renameCalls: Array<readonly [string, string]> = [];
  public readonly removeCalls: string[] = [];

  public putStaging(path: string, bytes: Uint8Array): Promise<void> {
    this.put(path, bytes);
    return Promise.resolve();
  }

  public finalize(stagingPath: string, blobPath: string): Promise<BlobProperties> {
    const bytes = this.#objects.get(stagingPath);
    if (bytes === undefined || this.#objects.has(blobPath)) {
      return Promise.reject(new Error("fake_finalize_failed"));
    }
    this.#objects.delete(stagingPath);
    this.#etags.delete(stagingPath);
    this.put(blobPath, bytes);
    return this.head(blobPath).then((properties) => {
      if (properties === undefined) throw new Error("fake_finalize_missing");
      return properties;
    });
  }

  public head(path: string): Promise<BlobProperties | undefined> {
    const bytes = this.#objects.get(path);
    const etag = this.#etags.get(path);
    return Promise.resolve(bytes === undefined || etag === undefined
      ? undefined
      : { etag, len: bytes.byteLength });
  }

  public get(path: string): Promise<Uint8Array | undefined> {
    const bytes = this.#objects.get(path);
    return Promise.resolve(bytes === undefined ? undefined : Uint8Array.from(bytes));
  }

  public rename(fromPath: string, toPath: string): Promise<void> {
    this.renameCalls.push([fromPath, toPath]);
    const bytes = this.#objects.get(fromPath);
    const etag = this.#etags.get(fromPath);
    if (bytes === undefined || etag === undefined) {
      return Promise.reject(notFound());
    }
    if (this.#objects.has(toPath)) {
      return Promise.reject(Object.assign(new Error("fake_conflict"), { statusCode: 409 }));
    }
    this.#objects.delete(fromPath);
    this.#etags.delete(fromPath);
    this.#objects.set(toPath, bytes);
    this.#etags.set(toPath, etag);
    return Promise.resolve();
  }

  public remove(path: string): Promise<void> {
    this.removeCalls.push(path);
    if (!this.#objects.has(path)) {
      return Promise.reject(notFound());
    }
    if (this.#stickyRemovals.has(path)) {
      return Promise.resolve();
    }
    this.#objects.delete(path);
    this.#etags.delete(path);
    return Promise.resolve();
  }

  public put(path: string, bytes = Uint8Array.of(1, 2, 3)): void {
    this.#objects.set(path, Uint8Array.from(bytes));
    this.#etags.set(path, `etag-${this.#etagSequence += 1}`);
  }

  public has(path: string): boolean {
    return this.#objects.has(path);
  }

  public clearRenameCalls(): void {
    this.renameCalls.length = 0;
  }

  public keepOnRemove(path: string, keep: boolean): void {
    if (keep) {
      this.#stickyRemovals.add(path);
    } else {
      this.#stickyRemovals.delete(path);
    }
  }
}

interface SeededPrepared {
  readonly handle: PreparedWriteHandle;
  readonly stagingPath: string;
  readonly blobPath: string;
  readonly etag: string;
  readonly length: bigint;
}

let fixtureSequence = 0;

async function seedUploading(
  controlPlane: ControlPlane,
  blobs: FakeBlobStore,
  createdAtEpochMs: number,
  withStaging = true,
): Promise<SeededPrepared> {
  fixtureSequence += 1;
  const handle = brand<PreparedWriteHandle>(randomUUID());
  const stagingPath = `staging/${handle as unknown as string}`;
  const blobPath = `blobs/${handle as unknown as string}`;
  await controlPlane.insertPreparedUploading({
    preparedBlobId: handle,
    tenantId: TENANT,
    mappingKey: brand<ReversalMappingKey>(`mapping-${fixtureSequence}`),
    idempotencyKey: brand<ReversalIdempotencyKey>(`idempotency-${fixtureSequence}`),
    immutableScopeDigest: brand<ReversalScopeDigest>(`scope-${fixtureSequence}`),
    stagingPath,
    blobPath,
    createdAtEpochMs: createdAtEpochMs,
  });
  if (withStaging) {
    await blobs.putStaging(stagingPath, Uint8Array.of(fixtureSequence & 0xff, 2, 3));
  }
  const properties = await blobs.head(stagingPath);
  return {
    handle,
    stagingPath,
    blobPath,
    etag: properties?.etag ?? "unused-upload-etag",
    length: BigInt(properties?.len ?? 0),
  };
}

async function seedFinalized(
  controlPlane: ControlPlane,
  blobs: FakeBlobStore,
  createdAtEpochMs = T0,
): Promise<SeededPrepared> {
  const seeded = await seedUploading(controlPlane, blobs, createdAtEpochMs);
  const finalized = await blobs.finalize(seeded.stagingPath, seeded.blobPath);
  await controlPlane.markFinalized({
    preparedBlobId: seeded.handle,
    blobEtag: finalized.etag,
    blobLength: BigInt(finalized.len),
  });
  return { ...seeded, etag: finalized.etag, length: BigInt(finalized.len) };
}

async function seedQuarantined(
  controlPlane: ControlPlane,
  blobs: FakeBlobStore,
  quarantinedAtEpochMs: number,
): Promise<SeededPrepared> {
  const seeded = await seedFinalized(controlPlane, blobs);
  const selected = await controlPlane.selectFinalizedOrphansForReclaim({
    olderThanEpochMs: T0 + 1,
    limit: 1,
  });
  expect(selected.rows.map((row) => row.preparedBlobId)).toEqual([seeded.handle]);
  await blobs.rename(seeded.blobPath, `reclaim-quarantine/${seeded.handle as unknown as string}`);
  await controlPlane.markQuarantined({
    preparedBlobId: seeded.handle,
    quarantinedAtEpochMs,
  });
  return seeded;
}

function maintenance(
  controlPlane: ControlPlane,
  blobStore: BlobStore,
  now = T0 + 1_000,
  uploadHorizonMs = 100,
  graceMs = 100,
): AzureSpoolMaintenance {
  return new AzureSpoolMaintenance({
    controlPlane,
    blobStore,
    uploadHorizonMs,
    graceMs,
    now: () => now,
  });
}

describe("AzureSpoolMaintenance unit", () => {
  it("Path 1 quarantines old unreferenced finalized rows and counts referenced candidates", async () => {
    const controlPlane = new InMemoryControlPlane();
    const blobs = new FakeBlobStore();
    const unreferenced = await seedFinalized(controlPlane, blobs);
    const referenced = await seedFinalized(controlPlane, blobs);
    const published = await controlPlane.publish({
      prepared: { handle: referenced.handle },
      expiresAtEpochMs: BigInt(T0 + 10_000),
      nowEpochMilliseconds: T0,
    });
    if (published.kind !== "published") throw new Error("expected published");
    await controlPlane.flushClaim({
      commit: published.commit,
      nowEpochMilliseconds: T0,
      blobEtag: referenced.etag,
      blobLength: referenced.length,
    });
    controlPlane.debugSetPreparedState(referenced.handle, "finalized");

    const outcome = await maintenance(controlPlane, blobs, T0 + 100, 10_000, 10_000)
      .reclaimOrphanedPrepared({ olderThanEpochMs: T0 + 1, limit: 10 });

    expect(outcome).toEqual({ scanned: 2, reclaimed: 1, skippedReferenced: 1 });
    expect(controlPlane.debugPrepared(unreferenced.handle)?.state).toBe("quarantined");
    expect(blobs.has(unreferenced.blobPath)).toBe(false);
    expect(blobs.has(`reclaim-quarantine/${unreferenced.handle as unknown as string}`)).toBe(true);
    expect(controlPlane.debugPrepared(referenced.handle)?.state).toBe("finalized");
    expect(blobs.has(referenced.blobPath)).toBe(true);
  });

  it("never quarantines a finalized row still referenced by a live claim/current pointer", async () => {
    const controlPlane = new InMemoryControlPlane();
    const blobs = new FakeBlobStore();
    const referenced = await seedFinalized(controlPlane, blobs);
    const published = await controlPlane.publish({
      prepared: { handle: referenced.handle },
      expiresAtEpochMs: BigInt(T0 + 10_000),
      nowEpochMilliseconds: T0,
    });
    if (published.kind !== "published") throw new Error("expected published");
    await controlPlane.flushClaim({
      commit: published.commit,
      nowEpochMilliseconds: T0,
      blobEtag: referenced.etag,
      blobLength: referenced.length,
    });
    controlPlane.debugSetPreparedState(referenced.handle, "finalized");

    const outcome = await maintenance(controlPlane, blobs, T0 + 100, 10_000, 10_000)
      .reclaimOrphanedPrepared({ olderThanEpochMs: T0 + 1, limit: 1 });

    expect(outcome).toEqual({ scanned: 1, reclaimed: 0, skippedReferenced: 1 });
    expect(controlPlane.debugPrepared(referenced.handle)?.state).toBe("finalized");
    expect(blobs.has(referenced.blobPath)).toBe(true);
    expect(blobs.has(`reclaim-quarantine/${referenced.handle as unknown as string}`)).toBe(false);
    expect(blobs.renameCalls).toEqual([]);
  });

  it("does not let referenced Path 1 rows starve Path 3 across sweeps", async () => {
    const controlPlane = new InMemoryControlPlane();
    const blobs = new FakeBlobStore();
    const quarantined = await seedQuarantined(controlPlane, blobs, T0 + 700);

    for (let index = 0; index < 2; index += 1) {
      const referenced = await seedFinalized(controlPlane, blobs);
      const published = await controlPlane.publish({
        prepared: { handle: referenced.handle },
        expiresAtEpochMs: BigInt(T0 + 10_000),
        nowEpochMilliseconds: T0,
      });
      if (published.kind !== "published") throw new Error("expected published");
      await controlPlane.flushClaim({
        commit: published.commit,
        nowEpochMilliseconds: T0,
        blobEtag: referenced.etag,
        blobLength: referenced.length,
      });
      controlPlane.debugSetPreparedState(referenced.handle, "finalized");
    }

    await expect(controlPlane.previewReclamation({
      olderThanEpochMs: T0 + 1,
      uploadHorizonEpochMs: 0,
      quarantinedBeforeEpochMs: T0 + 900,
      limit: 2,
      includeHardDelete: true,
    })).resolves.toEqual({ scanned: 3, reclaimed: 1, skippedReferenced: 2 });

    const worker = maintenance(controlPlane, blobs, T0 + 1_000, 100, 100);
    const first = await worker.reclaimOrphanedPrepared({ olderThanEpochMs: T0 + 1, limit: 2 });
    const second = await worker.reclaimOrphanedPrepared({ olderThanEpochMs: T0 + 1, limit: 2 });

    expect(first).toEqual({ scanned: 3, reclaimed: 1, skippedReferenced: 2 });
    expect(second).toEqual({ scanned: 2, reclaimed: 0, skippedReferenced: 2 });
    expect(controlPlane.debugPrepared(quarantined.handle)).toBeUndefined();
    expect(blobs.has(`reclaim-quarantine/${quarantined.handle as unknown as string}`)).toBe(false);
  });

  it("Path 2b completes a crash-left upload mark and tolerates absent staging/blob paths", async () => {
    const controlPlane = new InMemoryControlPlane();
    const blobs = new FakeBlobStore();
    const uploading = await seedUploading(controlPlane, blobs, T0);
    const marked = await controlPlane.markStaleUploads({
      uploadHorizonEpochMs: T0 + 1,
      limit: 1,
    });
    expect(marked.map((row) => row.preparedBlobId)).toEqual([uploading.handle]);
    blobs.keepOnRemove(uploading.stagingPath, true);
    await expect(maintenance(controlPlane, blobs)
      .reclaimOrphanedPrepared({ olderThanEpochMs: 0, limit: 10 }))
      .rejects.toThrow("remove_not_confirmed");
    expect(controlPlane.debugPrepared(uploading.handle)?.state).toBe("upload_reclaim_marked");

    blobs.keepOnRemove(uploading.stagingPath, false);
    await blobs.remove(uploading.stagingPath);

    const outcome = await maintenance(controlPlane, blobs)
      .reclaimOrphanedPrepared({ olderThanEpochMs: 0, limit: 10 });

    expect(outcome).toEqual({ scanned: 1, reclaimed: 1, skippedReferenced: 0 });
    expect(controlPlane.debugPrepared(uploading.handle)).toBeUndefined();
    expect(blobs.has(uploading.stagingPath)).toBe(false);
    expect(blobs.has(uploading.blobPath)).toBe(false);
    expect(blobs.removeCalls).toContain(uploading.stagingPath);
    expect(blobs.removeCalls).toContain(uploading.blobPath);
  });

  it("Path 3 keeps young quarantine rows and hard-deletes only rows past grace", async () => {
    const controlPlane = new InMemoryControlPlane();
    const blobs = new FakeBlobStore();
    const young = await seedQuarantined(controlPlane, blobs, T0 + 950);
    const old = await seedQuarantined(controlPlane, blobs, T0 + 800);

    const outcome = await maintenance(controlPlane, blobs, T0 + 1_000, 100, 100)
      .reclaimOrphanedPrepared({ olderThanEpochMs: 0, limit: 10 });

    expect(outcome).toEqual({ scanned: 1, reclaimed: 1, skippedReferenced: 0 });
    expect(controlPlane.debugPrepared(young.handle)?.state).toBe("quarantined");
    expect(blobs.has(`reclaim-quarantine/${young.handle as unknown as string}`)).toBe(true);
    expect(controlPlane.debugPrepared(old.handle)).toBeUndefined();
    expect(blobs.has(`reclaim-quarantine/${old.handle as unknown as string}`)).toBe(false);
  });

  it("quarantine mode runs without Path 3 hard deletion", async () => {
    const controlPlane = new InMemoryControlPlane();
    const blobs = new FakeBlobStore();
    const old = await seedQuarantined(controlPlane, blobs, T0 + 700);
    const worker = new AzureSpoolMaintenance({
      controlPlane,
      blobStore: blobs,
      uploadHorizonMs: 100,
      graceMs: 100,
      now: () => T0 + 1_000,
      includeHardDelete: false,
    });

    const outcome = await worker.reclaimOrphanedPrepared({ olderThanEpochMs: 0, limit: 10 });

    expect(outcome).toEqual({ scanned: 0, reclaimed: 0, skippedReferenced: 0 });
    expect(controlPlane.debugPrepared(old.handle)?.state).toBe("quarantined");
    expect(blobs.has(`reclaim-quarantine/${old.handle as unknown as string}`)).toBe(true);
  });

  it("shares one global inspection budget across Paths 1, 2, and 3", async () => {
    const controlPlane = new InMemoryControlPlane();
    const blobs = new FakeBlobStore();
    const quarantined = await seedQuarantined(controlPlane, blobs, T0 + 700);
    const finalized = await seedFinalized(controlPlane, blobs);
    const uploading = await seedUploading(controlPlane, blobs, T0);

    const outcome = await maintenance(controlPlane, blobs, T0 + 1_000, 100, 100)
      .reclaimOrphanedPrepared({ olderThanEpochMs: T0 + 1, limit: 2 });

    expect(outcome.scanned).toBe(2);
    expect(outcome.scanned).toBeLessThanOrEqual(2);
    expect(outcome.reclaimed).toBe(2);
    expect(controlPlane.debugPrepared(finalized.handle)?.state).toBe("quarantined");
    expect(controlPlane.debugPrepared(uploading.handle)).toBeUndefined();
    expect(controlPlane.debugPrepared(quarantined.handle)?.state).toBe("quarantined");
    expect(blobs.has(`reclaim-quarantine/${quarantined.handle as unknown as string}`)).toBe(true);
  });

  it("recovers a reclaim_marked row whose source was already renamed without renaming twice", async () => {
    const controlPlane = new InMemoryControlPlane();
    const blobs = new FakeBlobStore();
    const finalized = await seedFinalized(controlPlane, blobs);
    const selected = await controlPlane.selectFinalizedOrphansForReclaim({
      olderThanEpochMs: T0 + 1,
      limit: 1,
    });
    expect(selected.rows.map((row) => row.preparedBlobId)).toEqual([finalized.handle]);
    const quarantinePath = `reclaim-quarantine/${finalized.handle as unknown as string}`;
    await blobs.rename(finalized.blobPath, quarantinePath);
    blobs.clearRenameCalls();

    const outcome = await maintenance(controlPlane, blobs, T0 + 100, 10_000, 10_000)
      .reclaimOrphanedPrepared({ olderThanEpochMs: 0, limit: 10 });

    expect(outcome).toEqual({ scanned: 1, reclaimed: 1, skippedReferenced: 0 });
    expect(controlPlane.debugPrepared(finalized.handle)?.state).toBe("quarantined");
    expect(blobs.has(quarantinePath)).toBe(true);
    expect(blobs.renameCalls).toEqual([]);
  });
});

const LIVE = !!process.env.PHI_REVERSAL_PG_TEST;

function pgConfig(): PoolConfig {
  const port = process.env.PGPORT === undefined ? 5432 : Number(process.env.PGPORT);
  if (!Number.isInteger(port) || port <= 0) throw new Error("invalid_PGPORT");
  return {
    host: process.env.PGHOST,
    user: process.env.PGUSER,
    password: process.env.PGPASSWORD,
    database: process.env.PGDATABASE,
    port,
    ...(process.env.PGSSLMODE === "require" ? { ssl: { rejectUnauthorized: false } } : {}),
  };
}

describe.skipIf(!LIVE)("AzureSpoolMaintenance live Postgres", () => {
  const schema = `phi_maintenance_${process.pid}_${Date.now()}`;
  let adminPool: Pool;
  let pool: Pool;
  let controlPlane: PostgresControlPlane;

  beforeAll(async () => {
    adminPool = new Pool(pgConfig());
    await adminPool.query(`CREATE SCHEMA "${schema}"`);
    pool = new Pool({ ...pgConfig(), options: `-c search_path=${schema}` });
    controlPlane = new PostgresControlPlane(pool);
    await runMigrations(pool);
  });

  beforeEach(async () => {
    await pool.query(
      `TRUNCATE TABLE
         reversal_current,
         reversal_claim,
         reversal_ordinal_seq,
         reversal_prepared,
         reversal_nonce_counter,
         reversal_dek_generation
       CASCADE`,
    );
  });

  afterAll(async () => {
    await pool?.end();
    if (adminPool !== undefined) {
      await adminPool.query(`DROP SCHEMA IF EXISTS "${schema}" CASCADE`);
      await adminPool.end();
    }
  });

  it("runs Path 1 quarantine and Path 2 stale-upload deletion against real metadata", async () => {
    const blobs = new FakeBlobStore();
    const finalized = await seedFinalized(controlPlane, blobs, T0);
    const uploading = await seedUploading(controlPlane, blobs, T0);

    const outcome = await maintenance(controlPlane, blobs, T0 + 1_000, 100, 10_000)
      .reclaimOrphanedPrepared({ olderThanEpochMs: T0 + 1, limit: 10 });

    expect(outcome).toEqual({ scanned: 2, reclaimed: 2, skippedReferenced: 0 });
    const finalizedState = await pool.query<{
      readonly state: string;
      readonly quarantined_at_ms: string;
    }>(
      `SELECT state, quarantined_at_ms::text AS quarantined_at_ms
       FROM reversal_prepared WHERE prepared_blob_id = $1`,
      [finalized.handle],
    );
    expect(finalizedState.rows[0]).toEqual({ state: "quarantined", quarantined_at_ms: String(T0 + 1_000) });
    expect(blobs.has(`reclaim-quarantine/${finalized.handle as unknown as string}`)).toBe(true);
    expect((await pool.query(
      `SELECT 1 FROM reversal_prepared WHERE prepared_blob_id = $1`,
      [uploading.handle],
    )).rowCount).toBe(0);
    expect(blobs.has(uploading.stagingPath)).toBe(false);
    expect(blobs.has(uploading.blobPath)).toBe(false);
  });
});
