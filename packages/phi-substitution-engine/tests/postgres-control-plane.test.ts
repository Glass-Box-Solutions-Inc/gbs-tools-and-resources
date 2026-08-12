import { randomUUID } from "node:crypto";
import { Pool, type PoolConfig } from "pg";
import { afterAll, beforeAll, beforeEach, describe, expect, it } from "vitest";
import type { MatterId, TenantId } from "../src/core/brands";
import type {
  DekGenerationId,
  PreparedReversalWrite,
  PreparedWriteHandle,
  PublishedCommitHandle,
  ReversalIdempotencyKey,
  ReversalMappingKey,
  ReversalScopeDigest,
  WrappedDekMaterial,
} from "../src/tokens/durable/ports";
import { PostgresControlPlane, runMigrations } from "../src/tokens/durable/azure/postgres-control-plane";

const LIVE = !!process.env.PHI_REVERSAL_PG_TEST;
const T0 = 1_700_000_000_000;
const MATTER_EXPIRES_AT = 2n ** 64n - 1n;
const SEP = "\0";

const brand = <T>(value: unknown): T => value as unknown as T;
const TENANT = brand<TenantId>("tenant-a");

interface PreparedFixture {
  readonly prepared: PreparedReversalWrite;
  readonly mappingKey: ReversalMappingKey;
  readonly idempotencyKey: ReversalIdempotencyKey;
  readonly blobEtag: string;
  readonly blobLength: bigint;
}

function pgConfig(): PoolConfig {
  const port = process.env.PGPORT === undefined ? 5432 : Number(process.env.PGPORT);
  if (!Number.isInteger(port) || port <= 0) {
    throw new Error("invalid_PGPORT");
  }
  return {
    host: process.env.PGHOST,
    user: process.env.PGUSER,
    password: process.env.PGPASSWORD,
    database: process.env.PGDATABASE,
    port,
    ...(process.env.PGSSLMODE === "require" ? { ssl: { rejectUnauthorized: false } } : {}),
  };
}

function nonceValue(nonce: Uint8Array): bigint {
  const bytes = Buffer.from(nonce);
  return (bytes.readBigUInt64BE(0) << 32n) | BigInt(bytes.readUInt32BE(8));
}

describe.skipIf(!LIVE)("PostgresControlPlane live conformance", () => {
  const schema = `phi_reversal_${process.pid}_${Date.now()}`;
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

  async function prepare(options: {
    readonly attempt?: string;
    readonly mapping?: string;
    readonly createdAtMs?: number;
    readonly etag?: string;
    readonly length?: bigint;
  } = {}): Promise<PreparedFixture> {
    const handle = brand<PreparedWriteHandle>(randomUUID());
    const mappingKey = brand<ReversalMappingKey>(
      options.mapping ?? `tenant-a${SEP}matter-a${SEP}1${SEP}[[Claimant]]`,
    );
    const idempotencyKey = brand<ReversalIdempotencyKey>(
      `tenant-a\0${options.attempt ?? randomUUID()}\0[[Claimant]]`,
    );
    const blobEtag = options.etag ?? `etag-${randomUUID()}`;
    const blobLength = options.length ?? 123n;
    await controlPlane.insertPreparedUploading({
      preparedBlobId: handle,
      tenantId: TENANT,
      mappingKey,
      idempotencyKey,
      immutableScopeDigest: brand<ReversalScopeDigest>("scope-digest-a"),
      stagingPath: `staging/${handle as unknown as string}`,
      blobPath: `blobs/${handle as unknown as string}`,
      createdAtEpochMs: options.createdAtMs ?? T0,
    });
    await controlPlane.markFinalized({ preparedBlobId: handle, blobEtag, blobLength });
    return { prepared: { handle }, mappingKey, idempotencyKey, blobEtag, blobLength };
  }

  async function publish(
    fixture: PreparedFixture,
    expiresAtEpochMs = BigInt(T0 + 10_000),
    nowEpochMilliseconds = T0,
  ): Promise<PublishedCommitHandle> {
    const result = await controlPlane.publish({
      prepared: fixture.prepared,
      expiresAtEpochMs,
      nowEpochMilliseconds,
    });
    expect(result.kind).toBe("published");
    if (result.kind !== "published") throw new Error("expected published");
    return result.commit;
  }

  it("elects one DEK generation and reserves first=0 monotonic nonces concurrently without reuse", async () => {
    const scope = {
      tenantId: TENANT,
      matterId: brand<MatterId>("matter-a"),
      purpose: "reversal-v1" as const,
    };
    const [generationA, generationB] = await Promise.all([
      controlPlane.ensureDekGeneration({
        scope,
        mint: async () => ({
          dekGenerationId: brand<DekGenerationId>("tenant-a\0matter-a\0reversal-v1\0gen-a"),
          wrappedDek: brand<WrappedDekMaterial>(Uint8Array.of(1, 2, 3)),
        }),
      }),
      controlPlane.ensureDekGeneration({
        scope,
        mint: async () => ({
          dekGenerationId: brand<DekGenerationId>("tenant-a\0matter-a\0reversal-v1\0gen-b"),
          wrappedDek: brand<WrappedDekMaterial>(Uint8Array.of(4, 5, 6)),
        }),
      }),
    ]);
    expect(generationB).toEqual(generationA);

    const request = {
      tenantId: TENANT,
      matterId: scope.matterId,
      dekGenerationId: generationA.dekGenerationId,
    };
    const first = await controlPlane.reserveNonce(request);
    const [second, third] = await Promise.all([
      new PostgresControlPlane(pool).reserveNonce(request),
      new PostgresControlPlane(pool).reserveNonce(request),
    ]);
    expect(nonceValue(first)).toBe(0n);
    expect(new Set([nonceValue(first), nonceValue(second), nonceValue(third)])).toEqual(new Set([0n, 1n, 2n]));
  });

  it("makes publish first-writer-wins across racing connections", async () => {
    const attempt = "race-attempt";
    const left = await prepare({ attempt });
    const right = await prepare({ attempt });
    const [leftResult, rightResult] = await Promise.all([
      new PostgresControlPlane(pool).publish({
        prepared: left.prepared,
        expiresAtEpochMs: BigInt(T0 + 10_000),
        nowEpochMilliseconds: T0,
      }),
      new PostgresControlPlane(pool).publish({
        prepared: right.prepared,
        expiresAtEpochMs: BigInt(T0 + 10_000),
        nowEpochMilliseconds: T0,
      }),
    ]);
    const winner = [leftResult, rightResult].find((result) => result.kind === "published");
    const loser = [leftResult, rightResult].find((result) => result.kind === "existing");
    expect(winner?.kind).toBe("published");
    expect(loser?.kind).toBe("existing");
    if (winner?.kind !== "published" || loser?.kind !== "existing") throw new Error("missing race result");
    expect(loser.commit).toBe(winner.commit);

    const states = await pool.query<{ readonly state: string; readonly count: string }>(
      `SELECT state, COUNT(*)::text AS count FROM reversal_prepared GROUP BY state`,
    );
    expect(Object.fromEntries(states.rows.map((row) => [row.state, row.count]))).toEqual({ committed: "1", finalized: "1" });
  });

  it("flushes pending claims and CAS prevents an out-of-order lower ordinal rollback", async () => {
    const mapping = `tenant-a${SEP}matter-a${SEP}1${SEP}[[Shared]]`;
    const older = await prepare({ attempt: "attempt-1", mapping, etag: "etag-old", length: 11n });
    const newer = await prepare({ attempt: "attempt-2", mapping, etag: "etag-new", length: 22n });
    const olderCommit = await publish(older);
    const newerCommit = await publish(newer);

    await controlPlane.flushClaim({
      commit: newerCommit,
      nowEpochMilliseconds: T0 + 1,
      blobEtag: newer.blobEtag,
      blobLength: newer.blobLength,
    });
    await controlPlane.flushClaim({
      commit: olderCommit,
      nowEpochMilliseconds: T0 + 2,
      blobEtag: older.blobEtag,
      blobLength: older.blobLength,
    });

    const pointers = await controlPlane.readCurrentPointers([older.mappingKey]);
    expect(pointers).toHaveLength(1);
    expect(pointers[0]).toMatchObject({
      commit: newerCommit,
      preparedBlobId: newer.prepared.handle,
      blobEtag: "etag-new",
      blobLength: 22n,
    });
    const claims = await pool.query<{ readonly state: string }>(`SELECT state FROM reversal_claim`);
    expect(claims.rows.every((row) => row.state === "flushed")).toBe(true);
  });

  it("tombstones expired pending, detaches and orphans its blob, and later retries stay expired", async () => {
    const attempt = "expired-attempt";
    const winner = await prepare({ attempt });
    const commit = await publish(winner, BigInt(T0 + 10), T0);
    const loser = await prepare({ attempt });

    const conflict = await controlPlane.publish({
      prepared: loser.prepared,
      expiresAtEpochMs: BigInt(T0 + 10),
      nowEpochMilliseconds: T0 + 10,
    });
    expect(conflict).toMatchObject({ kind: "existing", commit, expired: true });
    const claim = await pool.query<{
      readonly state: string;
      readonly prepared_blob_id: string | null;
      readonly expires_at_ms: string;
    }>(`SELECT state, prepared_blob_id, expires_at_ms FROM reversal_claim WHERE commit_handle = $1`, [commit]);
    expect(claim.rows[0]).toEqual({ state: "expired", prepared_blob_id: null, expires_at_ms: String(T0 + 10) });
    const prepared = await pool.query<{ readonly state: string }>(
      `SELECT state FROM reversal_prepared WHERE prepared_blob_id = $1`,
      [winner.prepared.handle],
    );
    expect(prepared.rows[0]?.state).toBe("orphaned");

    const later = await controlPlane.publish({
      prepared: loser.prepared,
      expiresAtEpochMs: BigInt(T0 + 10),
      nowEpochMilliseconds: T0 + 11,
    });
    expect(later).toMatchObject({ kind: "existing", commit, expired: true });
  });

  it("readCurrentPointers is exact-key, returns durable integrity attributes, and rejects a mismatched flush", async () => {
    const fixture = await prepare({ etag: "durable-etag", length: 456n });
    const commit = await publish(fixture);
    await expect(controlPlane.flushClaim({
      commit,
      nowEpochMilliseconds: T0 + 1,
      blobEtag: "wrong-etag",
      blobLength: fixture.blobLength,
    })).rejects.toThrow("integrity");
    await controlPlane.flushClaim({
      commit,
      nowEpochMilliseconds: T0 + 1,
      blobEtag: fixture.blobEtag,
      blobLength: fixture.blobLength,
    });

    const missing = brand<ReversalMappingKey>(`tenant-a${SEP}matter-a${SEP}1${SEP}[[Missing]]`);
    const rows = await controlPlane.readCurrentPointers([missing, fixture.mappingKey, fixture.mappingKey]);
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({
      mappingKey: fixture.mappingKey,
      commit,
      preparedBlobId: fixture.prepared.handle,
      blobEtag: "durable-etag",
      blobLength: 456n,
    });
  });

  it("Path-1 marks only old finalized/orphaned unreferenced rows and Path-3 uses quarantine time", async () => {
    const finalized = await prepare({ createdAtMs: T0, attempt: "finalized" });
    const recent = await prepare({ createdAtMs: T0 + 100, attempt: "recent" });
    const committed = await prepare({ createdAtMs: T0, attempt: "committed" });
    const committedHandle = await publish(committed);
    await controlPlane.flushClaim({
      commit: committedHandle,
      nowEpochMilliseconds: T0 + 1,
      blobEtag: committed.blobEtag,
      blobLength: committed.blobLength,
    });

    const orphanWinner = await prepare({ createdAtMs: T0, attempt: "orphan" });
    await publish(orphanWinner, BigInt(T0 + 1), T0);
    const orphanLoser = await prepare({ createdAtMs: T0, attempt: "orphan" });
    await controlPlane.publish({
      prepared: orphanLoser.prepared,
      expiresAtEpochMs: BigInt(T0 + 1),
      nowEpochMilliseconds: T0 + 1,
    });

    const marked = await controlPlane.reclaimFinalizedOrphans({ olderThanEpochMs: T0 + 50, limit: 20 });
    const ids = new Set(marked.map((row) => row.preparedBlobId));
    expect(ids).toEqual(new Set([finalized.prepared.handle, orphanWinner.prepared.handle, orphanLoser.prepared.handle]));
    expect(ids.has(recent.prepared.handle)).toBe(false);
    expect(ids.has(committed.prepared.handle)).toBe(false);

    await controlPlane.markQuarantined({
      preparedBlobId: finalized.prepared.handle,
      quarantinedAtEpochMs: T0 + 200,
    });
    expect(await controlPlane.hardDeleteQuarantined({ olderThanEpochMs: T0 + 200, limit: 10 })).toEqual([]);
    const hardDelete = await controlPlane.hardDeleteQuarantined({ olderThanEpochMs: T0 + 201, limit: 10 });
    expect(hardDelete.map((row) => row.preparedBlobId)).toEqual([finalized.prepared.handle]);
    await controlPlane.completeHardDeleteQuarantined(finalized.prepared.handle);
  });

  it("Path-2 reselects upload_reclaim_marked rows regardless of age after a simulated crash", async () => {
    const handle = brand<PreparedWriteHandle>(randomUUID());
    await controlPlane.insertPreparedUploading({
      preparedBlobId: handle,
      tenantId: TENANT,
      mappingKey: brand<ReversalMappingKey>(`tenant-a${SEP}matter-a${SEP}1${SEP}[[Upload]]`),
      idempotencyKey: brand<ReversalIdempotencyKey>("tenant-a\0upload-attempt\0[[Upload]]"),
      immutableScopeDigest: brand<ReversalScopeDigest>("upload-scope"),
      stagingPath: `staging/${handle as unknown as string}`,
      blobPath: `blobs/${handle as unknown as string}`,
      createdAtEpochMs: T0,
    });
    const marked = await controlPlane.reclaimStaleUploads({ uploadHorizonEpochMs: T0 + 1, limit: 10 });
    expect(marked.map((row) => row.preparedBlobId)).toEqual([handle]);

    const recovered = await new PostgresControlPlane(pool).reclaimStaleUploads({
      uploadHorizonEpochMs: 0,
      limit: 10,
    });
    expect(recovered.map((row) => row.preparedBlobId)).toEqual([handle]);
    await controlPlane.completeStaleUploadReclaim(handle);
    expect((await pool.query(`SELECT 1 FROM reversal_prepared WHERE prepared_blob_id = $1`, [handle])).rowCount).toBe(0);
  });

  it("stores NUMERIC(20,0) matter expiry exactly and compares without BIGINT overflow", async () => {
    const matter = await prepare({ attempt: "matter-expiry" });
    const commit = await publish(matter, MATTER_EXPIRES_AT, T0);
    const raw = await pool.query<{ readonly expires_at_ms: string; readonly pg_typeof: string }>(
      `SELECT expires_at_ms::text AS expires_at_ms, pg_typeof(expires_at_ms)::text AS pg_typeof
       FROM reversal_claim WHERE commit_handle = $1`,
      [commit],
    );
    expect(raw.rows[0]).toEqual({ expires_at_ms: MATTER_EXPIRES_AT.toString(), pg_typeof: "numeric" });

    const retry = await controlPlane.publish({
      prepared: matter.prepared,
      expiresAtEpochMs: MATTER_EXPIRES_AT,
      nowEpochMilliseconds: Number.MAX_SAFE_INTEGER,
    });
    expect(retry).toMatchObject({ kind: "existing", commit, expired: false });
    const boundary = await pool.query<{ readonly at_boundary: boolean; readonly before_boundary: boolean }>(
      `SELECT
         ($1::numeric >= expires_at_ms) AS at_boundary,
         ($2::numeric >= expires_at_ms) AS before_boundary
       FROM reversal_claim WHERE commit_handle = $3`,
      [MATTER_EXPIRES_AT.toString(), (MATTER_EXPIRES_AT - 1n).toString(), commit],
    );
    expect(boundary.rows[0]).toEqual({ at_boundary: true, before_boundary: false });
  });
});
