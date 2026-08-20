import { randomUUID } from "node:crypto";
import { readFileSync } from "node:fs";
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
const MIGRATION_SQL = readFileSync(
  new URL("../migrations/0001_phi_reversal_control_plane.sql", import.meta.url),
  "utf8",
);
const BASE_MIGRATION_SQL = MIGRATION_SQL.slice(0, MIGRATION_SQL.indexOf("-- GLY-345 v3 additive delta"));

function encodeTextKey(value: string): string {
  return `b64url-v1:${Buffer.from(value, "utf8").toString("base64url")}`;
}

interface PreparedFixture {
  readonly prepared: PreparedReversalWrite;
  readonly mappingKey: ReversalMappingKey;
  readonly idempotencyKey: ReversalIdempotencyKey;
  readonly blobEtag: string;
  readonly blobLength: bigint;
  readonly expiresAtEpochMs: bigint;
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

interface ScriptedQueryResult {
  readonly rowCount: number;
  readonly rows: readonly unknown[];
}

function scriptedControlPlane(results: readonly ScriptedQueryResult[]): {
  readonly controlPlane: PostgresControlPlane;
  readonly statements: string[];
  readonly boundParameters: Array<readonly unknown[] | undefined>;
} {
  const pending = [...results];
  const statements: string[] = [];
  const boundParameters: Array<readonly unknown[] | undefined> = [];
  const query = (sql: string, parameters?: readonly unknown[]): Promise<ScriptedQueryResult> => {
    statements.push(sql.trim());
    boundParameters.push(parameters);
    if (sql === "BEGIN" || sql === "COMMIT" || sql === "ROLLBACK" ||
        sql === "SET TRANSACTION ISOLATION LEVEL READ COMMITTED") {
      return Promise.resolve({ rowCount: 0, rows: [] });
    }
    const result = pending.shift();
    if (result === undefined) {
      return Promise.reject(new Error("unexpected_scripted_query"));
    }
    return Promise.resolve(result);
  };
  const client = {
    query,
    release: (): void => undefined,
  };
  const pool = { connect: () => Promise.resolve(client), query } as unknown as Pool;
  return { controlPlane: new PostgresControlPlane(pool), statements, boundParameters };
}

/**
 * GLY-345 §8.1 candidacy arithmetic is otherwise pinned only by live-gated PG oracles;
 * this SQL-shape assertion keeps the default (credential-free) gate from going blind to
 * a dropped drain-MAX in the matter arm or a de-COALESCEd NULL-class fallback.
 */
function expectSupersededCandidacyShape(statement: string): void {
  expect(statement).toContain("- greatest($4::numeric, $5::numeric))");
  expect(statement).toContain("COALESCE(p.retention_class, 'matter') = 'matter'");
}

function expectReferenceFiltersBeforeLimit(statement: string): void {
  const claimFilter = statement.indexOf("AND NOT EXISTS (\n             SELECT 1 FROM reversal_claim");
  const currentFilter = statement.indexOf("AND NOT EXISTS (\n             SELECT 1 FROM reversal_current");
  const limit = statement.lastIndexOf("LIMIT $2");
  expect(claimFilter).toBeGreaterThan(-1);
  expect(currentFilter).toBeGreaterThan(claimFilter);
  expect(limit).toBeGreaterThan(currentFilter);
}

describe("GLY-345 SQL protocol and expand-contract source oracles", () => {
  it("keeps the READ COMMITTED speculative-insertion anchor transaction verbatim", () => {
    const source = readFileSync(
      new URL("../src/tokens/durable/azure/postgres-control-plane.ts", import.meta.url),
      "utf8",
    );
    const isolation = source.indexOf("SET TRANSACTION ISOLATION LEVEL READ COMMITTED");
    const insert = source.indexOf("INSERT INTO reversal_operation_retention", isolation);
    const conflict = source.indexOf("ON CONFLICT (operation_key) DO NOTHING", insert);
    const share = source.indexOf("FOR SHARE", conflict);
    const prepared = source.indexOf("INSERT INTO reversal_prepared", share);
    expect(isolation).toBeGreaterThan(-1);
    expect(insert).toBeGreaterThan(isolation);
    expect(conflict).toBeGreaterThan(insert);
    expect(share).toBeGreaterThan(conflict);
    expect(prepared).toBeGreaterThan(share);
    expect(source.slice(Math.max(0, isolation - 300), prepared)).toContain("speculative-insertion waiting");
    expect(source.slice(insert, share)).not.toContain("DO UPDATE");
  });

  it("keeps the expand migration nullable/NOT VALID, guarded first, idempotent, and free of requiredness", () => {
    const delta = MIGRATION_SQL.slice(MIGRATION_SQL.indexOf("-- GLY-345 v3 additive delta"));
    const guard = delta.indexOf("gly345_online_migration_row_limit_exceeded");
    const firstDdl = delta.indexOf("ALTER TABLE reversal_prepared ADD COLUMN");
    expect(guard).toBeGreaterThan(-1);
    expect(guard).toBeLessThan(firstDdl);
    expect(delta).toContain("LIMIT 100001");
    expect(delta).toContain("IF prepared_count > 100000 THEN");
    for (const column of [
      "operation_key TEXT",
      "record_created_at_ms BIGINT",
      "retention_class TEXT",
      "retention_origin TEXT",
      "retention_expires_at_ms NUMERIC(20,0)",
    ]) {
      expect(delta).toContain(`ADD COLUMN IF NOT EXISTS ${column}`);
      expect(delta).not.toContain(`ADD COLUMN IF NOT EXISTS ${column} NOT NULL`);
    }
    expect(delta).not.toContain("reversal_prepared_gly345_required_check");
    expect(delta).not.toMatch(/VALIDATE\s+CONSTRAINT/i);
    expect(delta).not.toMatch(/SET\s+NOT\s+NULL/i);
    expect(delta).toContain("operation_key IS NULL\n    OR record_created_at_ms IS NULL");
    expect(delta).toContain("FOREIGN KEY (operation_key)");
    expect(delta).toContain("REFERENCES reversal_operation_retention(operation_key) NOT VALID");
    expect((delta.match(/NOT VALID/g) ?? []).length).toBeGreaterThanOrEqual(9);
    const stateCheck = delta.slice(
      delta.indexOf("ADD CONSTRAINT reversal_prepared_gly345_state_check"),
      delta.indexOf("ADD CONSTRAINT reversal_prepared_gly345_blob_state_check"),
    );
    expect(stateCheck).toContain("NOT VALID");
    expect(delta).toContain("CREATE TABLE IF NOT EXISTS reversal_operation_retention");
    expect(delta).toContain("CREATE INDEX IF NOT EXISTS reversal_prepared_superseded_reclaim_idx");
    expect(delta).not.toMatch(/^\s*DELETE\s+FROM\s+reversal_prepared/gim);
  });

  it("discovers anonymous state checks by definition and seeds legacy supersession from DB now", () => {
    const delta = MIGRATION_SQL.slice(MIGRATION_SQL.indexOf("-- GLY-345 v3 additive delta"));
    expect(delta).toContain("pg_get_constraintdef(c.oid)");
    expect(delta).toContain("format(\n      'ALTER TABLE reversal_prepared DROP CONSTRAINT %I'");
    expect(delta).toContain("gly345_surviving_check_rejects_superseded");
    const seed = delta.slice(delta.indexOf("WITH migration_clock AS"), delta.indexOf("-- Added constraints"));
    expect(seed).toContain("clock_timestamp()");
    expect(seed).not.toContain("flushed_at_ms");
    expect(seed).toContain("SET state = 'superseded'");
    expect(seed).toContain("SET state = 'superseded', prepared_blob_id = NULL");
  });

  it("contains fatal legacy class/expiry guards and the E1 NULL-safe matter selector", () => {
    expect(MIGRATION_SQL).toContain("gly345_ambiguous_legacy_expiry");
    expect(MIGRATION_SQL).toContain("gly345_mixed_legacy_operation_retention");
    expect(MIGRATION_SQL).toContain("gly345_operation_key_tenant_mismatch");
    expect(MIGRATION_SQL).toContain("c.expires_at_ms <> c.created_at_ms::numeric + 86400000::numeric");
    expect(MIGRATION_SQL).toContain("HAVING count(DISTINCT CASE");
    const source = readFileSync(
      new URL("../src/tokens/durable/azure/postgres-control-plane.ts", import.meta.url),
      "utf8",
    );
    expect((source.match(/COALESCE\(p\.retention_class, 'matter'\) = 'matter'/g) ?? [])).toHaveLength(3);
    expect(source).toContain("p.superseded_at_ms::numeric + greatest($4::numeric, $5::numeric)");
    expect(source).toContain("least(p.retention_expires_at_ms");
    expect(source).toContain("FOR UPDATE OF p SKIP LOCKED");
    const selfHeal = source.slice(source.indexOf("async #selfHealFlushedClaim"), source.indexOf("async #expireLockedPending"));
    expect(selfHeal).toContain("FROM reversal_prepared\n       WHERE prepared_blob_id = $1\n       FOR UPDATE");
    expect(selfHeal).toContain("WITH detached AS");
    const flush = source.slice(source.indexOf("public async flushClaim"), source.indexOf("public expirePendingDetach"));
    expect(flush).toContain("clock_timestamp()");
    expect(flush).not.toContain("superseded_at_ms = input.nowEpochMilliseconds");
  });
});

describe("PostgresControlPlane maintenance completion idempotency", () => {
  const handle = brand<PreparedWriteHandle>("00000000-0000-4000-8000-000000000001");

  it("uses the database clock for DEK-generation lifecycle metadata", async () => {
    const generationId = "generation-a";
    const fixture = scriptedControlPlane([
      { rowCount: 0, rows: [] },
      { rowCount: 1, rows: [] },
      {
        rowCount: 1,
        rows: [{
          dek_generation_id: `b64url-v1:${Buffer.from(generationId).toString("base64url")}`,
          wrapped_dek: Buffer.from([1, 2, 3]),
        }],
      },
    ]);

    await fixture.controlPlane.ensureDekGeneration({
      scope: {
        tenantId: TENANT,
        matterId: brand<MatterId>("matter-a"),
        purpose: "reversal-v1",
      },
      mint: async () => ({
        dekGenerationId: brand<DekGenerationId>(generationId),
        wrappedDek: brand<WrappedDekMaterial>(Uint8Array.of(1, 2, 3)),
      }),
    });

    expect(fixture.statements[1]).toContain("EXTRACT(EPOCH FROM clock_timestamp()) * 1000");
    expect(fixture.boundParameters[1]).toHaveLength(6);
  });

  it("uses the database clock instead of binding producer time into prepared lifecycle age", async () => {
    const fixture = scriptedControlPlane([
      { rowCount: 1, rows: [{ db_now_ms: String(T0) }] },
      { rowCount: 1, rows: [] },
      { rowCount: 1, rows: [{ tenant_id: "tenant-a", retention_class: "matter" }] },
      { rowCount: 1, rows: [] },
    ]);

    await fixture.controlPlane.insertPreparedUploading({
      preparedBlobId: handle,
      tenantId: TENANT,
      mappingKey: brand<ReversalMappingKey>("mapping-a"),
      idempotencyKey: brand<ReversalIdempotencyKey>("idempotency-a"),
      immutableScopeDigest: brand<ReversalScopeDigest>("scope-a"),
      stagingPath: `staging/${handle as unknown as string}`,
      blobPath: `blobs/${handle as unknown as string}`,
      attemptId: brand("attempt-a"),
      retentionClass: "matter",
      createdAtEpochMs: T0 - 100 * 60 * 60 * 1_000,
      expiresAtEpochMs: MATTER_EXPIRES_AT,
    });

    expect(fixture.statements).toContain("SET TRANSACTION ISOLATION LEVEL READ COMMITTED");
    expect(fixture.statements.some((statement) => statement.includes("EXTRACT(EPOCH FROM clock_timestamp()) * 1000"))).toBe(true);
    const anchor = fixture.statements.findIndex((statement) => statement.includes("INSERT INTO reversal_prepared"));
    expect(anchor).toBeGreaterThan(-1);
    expect(fixture.boundParameters[anchor]).toHaveLength(12);
  });

  it("accepts markQuarantined after another worker already reached quarantined", async () => {
    const fixture = scriptedControlPlane([
      { rowCount: 0, rows: [] },
      { rowCount: 1, rows: [{ state: "quarantined" }] },
    ]);

    await expect(fixture.controlPlane.markQuarantined({
      preparedBlobId: handle,
      quarantinedAtEpochMs: T0,
    })).resolves.toBeUndefined();
    expect(fixture.statements).toEqual([
      "BEGIN",
      expect.stringContaining("UPDATE reversal_prepared"),
      expect.stringContaining("SELECT state FROM reversal_prepared"),
      "COMMIT",
    ]);
  });

  it("accepts completeStaleUploadReclaim after another worker already deleted the row", async () => {
    const fixture = scriptedControlPlane([
      { rowCount: 0, rows: [] },
      { rowCount: 0, rows: [] },
    ]);

    await expect(fixture.controlPlane.completeStaleUploadReclaim(handle)).resolves.toBeUndefined();
    expect(fixture.statements).toEqual([
      "BEGIN",
      expect.stringContaining("DELETE FROM reversal_prepared"),
      expect.stringContaining("SELECT 1 FROM reversal_prepared"),
      "COMMIT",
    ]);
  });

  it("accepts completeHardDeleteQuarantined after another worker already deleted the row", async () => {
    const fixture = scriptedControlPlane([
      { rowCount: 0, rows: [] },
      { rowCount: 0, rows: [] },
    ]);

    await expect(fixture.controlPlane.completeHardDeleteQuarantined(handle)).resolves.toBeUndefined();
    expect(fixture.statements).toEqual([
      "BEGIN",
      expect.stringContaining("DELETE FROM reversal_prepared"),
      expect.stringContaining("SELECT 1 FROM reversal_prepared"),
      "COMMIT",
    ]);
  });

  it.each([
    {
      name: "markQuarantined",
      expectedError: "mark_quarantined_invalid_state",
      results: [
        { rowCount: 0, rows: [] },
        { rowCount: 1, rows: [{ state: "finalized" }] },
      ],
      complete: (controlPlane: PostgresControlPlane) => controlPlane.markQuarantined({
        preparedBlobId: handle,
        quarantinedAtEpochMs: T0,
      }),
    },
    {
      name: "completeStaleUploadReclaim",
      expectedError: "complete_stale_upload_invalid_state",
      results: [
        { rowCount: 0, rows: [] },
        { rowCount: 1, rows: [{}] },
      ],
      complete: (controlPlane: PostgresControlPlane) => controlPlane.completeStaleUploadReclaim(handle),
    },
    {
      name: "completeHardDeleteQuarantined",
      expectedError: "complete_hard_delete_invalid_state",
      results: [
        { rowCount: 0, rows: [] },
        { rowCount: 1, rows: [{}] },
      ],
      complete: (controlPlane: PostgresControlPlane) => controlPlane.completeHardDeleteQuarantined(handle),
    },
  ])("keeps $name loud when the row remains in an unexpected state", async ({ complete, expectedError, results }) => {
    const fixture = scriptedControlPlane(results);

    await expect(complete(fixture.controlPlane)).rejects.toThrow(expectedError);
    expect(fixture.statements.at(-1)).toBe("ROLLBACK");
  });

  it("filters Path-1 references before LIMIT in both live selection and preview SQL", async () => {
    const first = brand<PreparedWriteHandle>("00000000-0000-4000-8000-000000000011");
    const second = brand<PreparedWriteHandle>("00000000-0000-4000-8000-000000000012");
    const selected = scriptedControlPlane([
      { rowCount: 1, rows: [{ db_now_ms: String(T0) }] },
      { rowCount: 1, rows: [{ count: 2 }] },
      {
        rowCount: 1,
        rows: [{ prepared_blob_id: first, blob_path: `blobs/${first}`, blob_len: "1", state: "reclaim_marked", effective_reclaim_after_ms: null }],
      },
    ]);

    await expect(selected.controlPlane.selectFinalizedOrphansForReclaim({
      olderThanEpochMs: T0 + 1,
      limit: 2,
    })).resolves.toEqual({
      rows: [{ preparedBlobId: first, blobPath: `blobs/${first}`, blobLength: 1n }],
      skippedReferenced: 2,
    });
    const liveSelectorSql = selected.statements.find((statement) => statement.includes("FOR UPDATE OF p SKIP LOCKED"));
    expect(liveSelectorSql).toBeDefined();
    expectReferenceFiltersBeforeLimit(liveSelectorSql ?? "");
    expectSupersededCandidacyShape(liveSelectorSql ?? "");

    const previewed = scriptedControlPlane([
      { rowCount: 0, rows: [] },
      { rowCount: 1, rows: [{ db_now_ms: String(T0) }] },
      { rowCount: 1, rows: [{ count: 2 }] },
      {
        rowCount: 2,
        rows: [
          { prepared_blob_id: first, blob_path: `blobs/${first}`, blob_len: "1", state: "reclaim_marked", effective_reclaim_after_ms: null },
          { prepared_blob_id: second, blob_path: `blobs/${second}`, blob_len: "1", state: "finalized", effective_reclaim_after_ms: null },
        ],
      },
    ]);
    await expect(previewed.controlPlane.previewReclamation({
      olderThanEpochMs: T0 + 1,
      uploadHorizonEpochMs: 0,
      quarantinedBeforeEpochMs: 0,
      limit: 2,
      includeHardDelete: false,
    })).resolves.toEqual({ scanned: 4, reclaimed: 2, skippedReferenced: 2 });
    const previewSql = previewed.statements.find((statement) =>
      statement.includes("SELECT p.prepared_blob_id, p.blob_path, p.blob_len, p.state") &&
      !statement.includes("FOR UPDATE")
    );
    expect(previewSql).toBeDefined();
    expectReferenceFiltersBeforeLimit(previewSql ?? "");
    expectSupersededCandidacyShape(previewSql ?? "");
  });
});

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
         reversal_operation_retention,
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
    /** Test-only control-plane age override; authenticated record creation remains class-derived. */
    readonly lifecycleCreatedAtMs?: number;
    readonly createdAtMs?: number;
    readonly etag?: string;
    readonly length?: bigint;
    readonly expiresAtMs?: bigint;
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
    const expiresAtEpochMs = options.expiresAtMs ?? MATTER_EXPIRES_AT;
    const retentionClass = expiresAtEpochMs === MATTER_EXPIRES_AT ? "matter" : "detector-only";
    const recordCreatedAtMs = options.createdAtMs ?? (
      retentionClass === "detector-only" ? Number(expiresAtEpochMs - 86_400_000n) : T0
    );
    await controlPlane.insertPreparedUploading({
      preparedBlobId: handle,
      tenantId: TENANT,
      mappingKey,
      idempotencyKey,
      immutableScopeDigest: brand<ReversalScopeDigest>("scope-digest-a"),
      stagingPath: `staging/${handle as unknown as string}`,
      blobPath: `blobs/${handle as unknown as string}`,
      attemptId: brand(options.attempt ?? "attempt-default"),
      retentionClass,
      createdAtEpochMs: recordCreatedAtMs,
      expiresAtEpochMs,
    });
    const lifecycleCreatedAtMs = options.lifecycleCreatedAtMs ?? options.createdAtMs;
    if (lifecycleCreatedAtMs !== undefined) {
      await pool.query(
        `UPDATE reversal_prepared SET created_at_ms = $2 WHERE prepared_blob_id = $1`,
        [handle, lifecycleCreatedAtMs],
      );
    }
    await controlPlane.markFinalized({ preparedBlobId: handle, blobEtag, blobLength });
    return { prepared: { handle }, mappingKey, idempotencyKey, blobEtag, blobLength, expiresAtEpochMs };
  }

  async function publish(
    fixture: PreparedFixture,
    expiresAtEpochMs = fixture.expiresAtEpochMs,
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

  it("catalog-proves idempotent expand DDL with nullable columns and unvalidated constraints", async () => {
    const before = await pool.query<{
      readonly conname: string;
      readonly convalidated: boolean;
    }>(
      `SELECT conname, convalidated
       FROM pg_constraint
       WHERE conrelid IN ('reversal_prepared'::regclass, 'reversal_claim'::regclass)
         AND conname LIKE '%gly345%'
       ORDER BY conname`,
    );
    await runMigrations(pool);
    const after = await pool.query<{ readonly conname: string; readonly convalidated: boolean }>(
      `SELECT conname, convalidated
       FROM pg_constraint
       WHERE conrelid IN ('reversal_prepared'::regclass, 'reversal_claim'::regclass)
         AND conname LIKE '%gly345%'
       ORDER BY conname`,
    );
    expect(after.rows).toEqual(before.rows);
    expect(after.rows.length).toBeGreaterThan(0);
    expect(after.rows.every((row) => row.convalidated === false)).toBe(true);
    expect(after.rows.some((row) => row.conname === "reversal_prepared_gly345_required_check")).toBe(false);
    const columns = await pool.query<{ readonly column_name: string; readonly is_nullable: string }>(
      `SELECT column_name, is_nullable
       FROM information_schema.columns
       WHERE table_schema = current_schema()
         AND table_name = 'reversal_prepared'
         AND column_name = ANY($1::text[])
       ORDER BY column_name`,
      [["operation_key", "record_created_at_ms", "retention_class", "retention_origin", "retention_expires_at_ms"]],
    );
    expect(columns.rows).toHaveLength(5);
    expect(columns.rows.every((row) => row.is_nullable === "YES")).toBe(true);
  });

  it("pins one durable class per exact tenant/attempt and rolls a mismatch anchor back", async () => {
    await prepare({ attempt: "binding-mismatch" });
    const detectorExpiry = BigInt(Date.now() + 86_400_000);
    await expect(new PostgresControlPlane(pool).insertPreparedUploading({
      preparedBlobId: brand<PreparedWriteHandle>(randomUUID()),
      tenantId: TENANT,
      mappingKey: brand<ReversalMappingKey>("binding-mismatch-second-token"),
      idempotencyKey: brand<ReversalIdempotencyKey>("binding-mismatch-second-idempotency"),
      immutableScopeDigest: brand<ReversalScopeDigest>("binding-mismatch-scope"),
      stagingPath: "staging/binding-mismatch-second",
      blobPath: "blobs/binding-mismatch-second",
      attemptId: brand("binding-mismatch"),
      retentionClass: "detector-only",
      createdAtEpochMs: Number(detectorExpiry - 86_400_000n),
      expiresAtEpochMs: detectorExpiry,
    })).rejects.toThrow("retention_binding_mismatch");
    expect((await pool.query(`SELECT 1 FROM reversal_operation_retention`)).rowCount).toBe(1);
    expect((await pool.query(`SELECT 1 FROM reversal_prepared`)).rowCount).toBe(1);
  });

  it("waits on speculative operation insertion and follows winner commit or rollback", async () => {
    const makeAnchor = (attempt: string, retentionClass: "matter" | "detector-only") => {
      const createdAtEpochMs = Date.now();
      return {
        preparedBlobId: brand<PreparedWriteHandle>(randomUUID()),
        tenantId: TENANT,
        mappingKey: brand<ReversalMappingKey>(`mapping-${attempt}-${retentionClass}`),
        idempotencyKey: brand<ReversalIdempotencyKey>(`idempotency-${attempt}-${retentionClass}`),
        immutableScopeDigest: brand<ReversalScopeDigest>(`scope-${attempt}`),
        stagingPath: `staging/${attempt}-${retentionClass}`,
        blobPath: `blobs/${attempt}-${retentionClass}`,
        attemptId: brand(attempt),
        retentionClass,
        createdAtEpochMs,
        expiresAtEpochMs: retentionClass === "matter"
          ? MATTER_EXPIRES_AT
          : BigInt(createdAtEpochMs) + 86_400_000n,
      } as const;
    };
    for (const outcome of ["commit", "rollback"] as const) {
      const attempt = `speculative-${outcome}`;
      const operationKey = encodeTextKey(`tenant-a${SEP}${attempt}`);
      const blocker = await pool.connect();
      try {
        await blocker.query("BEGIN");
        await blocker.query("SET TRANSACTION ISOLATION LEVEL READ COMMITTED");
        await blocker.query(
          `INSERT INTO reversal_operation_retention (
             operation_key, tenant_id, retention_class, bound_at_ms
           ) VALUES ($1, 'tenant-a', 'matter', 0)`,
          [operationKey],
        );
        let settled = false;
        const waiter = new PostgresControlPlane(pool)
          .insertPreparedUploading(makeAnchor(attempt, "detector-only"))
          .finally(() => { settled = true; });
        await new Promise((resolve) => setTimeout(resolve, 50));
        expect(settled).toBe(false);
        await blocker.query(outcome === "commit" ? "COMMIT" : "ROLLBACK");
        if (outcome === "commit") {
          await expect(waiter).rejects.toThrow("retention_binding_mismatch");
        } else {
          await expect(waiter).resolves.toBeUndefined();
        }
      } finally {
        try { await blocker.query("ROLLBACK"); } catch { /* already completed */ }
        blocker.release();
      }
      const classes = await pool.query<{ readonly retention_class: string }>(
        `SELECT retention_class FROM reversal_operation_retention WHERE operation_key = $1`,
        [operationKey],
      );
      expect(classes.rows).toEqual([{ retention_class: outcome === "commit" ? "matter" : "detector-only" }]);
    }
  });

  it("makes publish first-writer-wins across racing connections", async () => {
    const attempt = "race-attempt";
    const left = await prepare({ attempt });
    const right = await prepare({ attempt });
    const [leftResult, rightResult] = await Promise.all([
      new PostgresControlPlane(pool).publish({
        prepared: left.prepared,
        expiresAtEpochMs: MATTER_EXPIRES_AT,
        nowEpochMilliseconds: T0,
      }),
      new PostgresControlPlane(pool).publish({
        prepared: right.prepared,
        expiresAtEpochMs: MATTER_EXPIRES_AT,
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
    const claims = await pool.query<{ readonly state: string; readonly prepared_blob_id: string | null }>(
      `SELECT state, prepared_blob_id FROM reversal_claim ORDER BY ordinal`,
    );
    expect(claims.rows).toEqual([
      { state: "superseded", prepared_blob_id: null },
      { state: "flushed", prepared_blob_id: newer.prepared.handle as unknown as string },
    ]);
    const oldPrepared = await pool.query<{ readonly state: string; readonly superseded_at_ms: string | null }>(
      `SELECT state, superseded_at_ms FROM reversal_prepared WHERE prepared_blob_id = $1`,
      [older.prepared.handle],
    );
    expect(oldPrepared.rows[0]?.state).toBe("superseded");
    expect(oldPrepared.rows[0]?.superseded_at_ms).not.toBeNull();
  });

  it("tombstones expired pending, detaches and orphans its blob, and later retries stay expired", async () => {
    const attempt = "expired-attempt";
    const detectorExpiry = BigInt(Date.now() + 86_400_000);
    const winner = await prepare({ attempt, expiresAtMs: detectorExpiry });
    const commit = await publish(winner);
    await pool.query(`UPDATE reversal_claim SET expires_at_ms = 0 WHERE commit_handle = $1`, [commit]);
    const loser = await prepare({ attempt, expiresAtMs: detectorExpiry });

    const conflict = await controlPlane.publish({
      prepared: loser.prepared,
      expiresAtEpochMs: detectorExpiry,
      nowEpochMilliseconds: T0,
    });
    expect(conflict).toMatchObject({ kind: "existing", commit, expired: true });
    const claim = await pool.query<{
      readonly state: string;
      readonly prepared_blob_id: string | null;
      readonly expires_at_ms: string;
    }>(`SELECT state, prepared_blob_id, expires_at_ms FROM reversal_claim WHERE commit_handle = $1`, [commit]);
    expect(claim.rows[0]).toEqual({ state: "expired", prepared_blob_id: null, expires_at_ms: "0" });
    const prepared = await pool.query<{ readonly state: string }>(
      `SELECT state FROM reversal_prepared WHERE prepared_blob_id = $1`,
      [winner.prepared.handle],
    );
    expect(prepared.rows[0]?.state).toBe("orphaned");

    const later = await controlPlane.publish({
      prepared: loser.prepared,
      expiresAtEpochMs: detectorExpiry,
      nowEpochMilliseconds: T0,
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

    const orphanExpiry = BigInt(Date.now() + 86_400_000);
    const orphanWinner = await prepare({ lifecycleCreatedAtMs: T0, attempt: "orphan", expiresAtMs: orphanExpiry });
    const orphanCommit = await publish(orphanWinner);
    await pool.query(`UPDATE reversal_claim SET expires_at_ms = 0 WHERE commit_handle = $1`, [orphanCommit]);
    const orphanLoser = await prepare({ lifecycleCreatedAtMs: T0, attempt: "orphan", expiresAtMs: orphanExpiry });
    await controlPlane.publish({
      prepared: orphanLoser.prepared,
      expiresAtEpochMs: orphanExpiry,
      nowEpochMilliseconds: T0,
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

  it("ORACLE-EXPAND-CONTRACT-OLD-WRITER admits NULL metadata and reclaims it after supersession", async () => {
    const oldPrepared = randomUUID();
    const oldCommit = randomUUID();
    const rawMapping = `tenant-a${SEP}matter-a${SEP}1${SEP}[[LegacyNull]]`;
    const encodedMapping = encodeTextKey(rawMapping);
    const oldIdempotency = encodeTextKey(`tenant-a${SEP}legacy-null-attempt${SEP}[[LegacyNull]]`);
    await pool.query(
      `INSERT INTO reversal_prepared (
         prepared_blob_id, tenant_id, mapping_key, idempotency_key, scope_digest,
         staging_path, blob_path, created_at_ms, state, blob_etag, blob_len
       ) VALUES ($1, 'tenant-a', $2, $3, 'legacy-null-scope', $4, $5, 0,
                 'committed', 'legacy-null-etag', 3)`,
      [oldPrepared, encodedMapping, oldIdempotency, `staging/${oldPrepared}`, `blobs/${oldPrepared}`],
    );
    await pool.query(
      `INSERT INTO reversal_claim (
         idempotency_key, tenant_id, mapping_key, scope_digest, commit_handle,
         prepared_blob_id, ordinal, created_at_ms, expires_at_ms, state
       ) VALUES ($1, 'tenant-a', $2, 'legacy-null-scope', $3, $4, 1, 0,
                 18446744073709551615, 'flushed')`,
      [oldIdempotency, encodedMapping, oldCommit, oldPrepared],
    );
    await pool.query(
      `INSERT INTO reversal_current (
         mapping_key, tenant_id, commit_handle, prepared_blob_id, ordinal, flushed_at_ms
       ) VALUES ($1, 'tenant-a', $2, $3, 1, 0)`,
      [encodedMapping, oldCommit, oldPrepared],
    );
    await pool.query(
      `INSERT INTO reversal_ordinal_seq (mapping_key, tenant_id, next_ordinal)
       VALUES ($1, 'tenant-a', 2)`,
      [encodedMapping],
    );

    const fresh = await prepare({ attempt: "new-writer-after-null", mapping: rawMapping });
    const freshCommit = await publish(fresh);
    await controlPlane.flushClaim({
      commit: freshCommit,
      nowEpochMilliseconds: 0,
      blobEtag: fresh.blobEtag,
      blobLength: fresh.blobLength,
    });
    const transitioned = await pool.query<{
      readonly prepared_state: string;
      readonly claim_state: string;
      readonly prepared_blob_id: string | null;
      readonly retention_class: string | null;
    }>(
      `SELECT p.state AS prepared_state, c.state AS claim_state, c.prepared_blob_id,
              p.retention_class
       FROM reversal_prepared p
       JOIN reversal_claim c ON c.idempotency_key = p.idempotency_key
       WHERE p.prepared_blob_id = $1`,
      [oldPrepared],
    );
    expect(transitioned.rows[0]).toEqual({
      prepared_state: "superseded",
      claim_state: "superseded",
      prepared_blob_id: null,
      retention_class: null,
    });
    await pool.query(`UPDATE reversal_prepared SET superseded_at_ms = 0 WHERE prepared_blob_id = $1`, [oldPrepared]);
    const selected = await controlPlane.selectFinalizedOrphansForReclaim({
      olderThanEpochMs: 0,
      limit: 10,
      supersedeRetentionMs: 1,
      readDrainMs: 0,
    });
    expect(selected.rows.map((row) => row.preparedBlobId)).toContain(oldPrepared);
    const marked = await pool.query<{ readonly state: string; readonly reclaim_after_ms: string }>(
      `SELECT state, reclaim_after_ms::text AS reclaim_after_ms
       FROM reversal_prepared WHERE prepared_blob_id = $1`,
      [oldPrepared],
    );
    expect(marked.rows[0]).toEqual({ state: "reclaim_marked", reclaim_after_ms: "1" });
  });

  it("EXPLAIN serves the superseded matter arm from its partial index", async () => {
    const fixture = await prepare({ attempt: "explain-superseded-matter" });
    await pool.query(
      `UPDATE reversal_prepared
       SET state = 'superseded', superseded_at_ms = 0
       WHERE prepared_blob_id = $1`,
      [fixture.prepared.handle],
    );
    const explainClient = await pool.connect();
    try {
      await explainClient.query(`SET enable_seqscan = off`);
      const explain = await explainClient.query(
        `EXPLAIN (FORMAT JSON)
         SELECT prepared_blob_id
         FROM reversal_prepared
         WHERE state = 'superseded'
           AND COALESCE(retention_class, 'matter') = 'matter'
           AND superseded_at_ms <= 1
         ORDER BY superseded_at_ms, prepared_blob_id`,
      );
      expect(JSON.stringify(explain.rows)).toContain("reversal_prepared_superseded_reclaim_idx");
    } finally {
      await explainClient.query(`RESET enable_seqscan`);
      explainClient.release();
    }
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
      attemptId: brand("upload-attempt"),
      retentionClass: "matter",
      createdAtEpochMs: T0,
      expiresAtEpochMs: MATTER_EXPIRES_AT,
    });
    await pool.query(
      `UPDATE reversal_prepared SET created_at_ms = $2 WHERE prepared_blob_id = $1`,
      [handle, T0],
    );
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

  it("keeps a new uploading row fresh despite a client timestamp skewed 100 hours behind", async () => {
    const handle = brand<PreparedWriteHandle>(randomUUID());
    const oneHundredHours = 100 * 60 * 60 * 1_000;
    const uploadHorizon = 48 * 60 * 60 * 1_000;
    const before = await pool.query<{ readonly db_now_ms: string }>(
      `SELECT (EXTRACT(EPOCH FROM clock_timestamp()) * 1000)::bigint::text AS db_now_ms`,
    );
    const dbBeforeMs = Number(before.rows[0]?.db_now_ms);

    await controlPlane.insertPreparedUploading({
      preparedBlobId: handle,
      tenantId: TENANT,
      mappingKey: brand<ReversalMappingKey>(`tenant-a${SEP}matter-a${SEP}1${SEP}[[Skewed]]`),
      idempotencyKey: brand<ReversalIdempotencyKey>("tenant-a\0skewed-attempt\0[[Skewed]]"),
      immutableScopeDigest: brand<ReversalScopeDigest>("skewed-scope"),
      stagingPath: `staging/${handle as unknown as string}`,
      blobPath: `blobs/${handle as unknown as string}`,
      attemptId: brand("skewed-attempt"),
      retentionClass: "matter",
      createdAtEpochMs: dbBeforeMs - oneHundredHours,
      expiresAtEpochMs: MATTER_EXPIRES_AT,
    });

    const marked = await controlPlane.markStaleUploads({
      uploadHorizonEpochMs: dbBeforeMs - uploadHorizon,
      limit: 10,
    });
    const stored = await pool.query<{ readonly created_at_ms: string; readonly db_now_ms: string }>(
      `SELECT created_at_ms::text AS created_at_ms,
              (EXTRACT(EPOCH FROM clock_timestamp()) * 1000)::bigint::text AS db_now_ms
       FROM reversal_prepared
       WHERE prepared_blob_id = $1`,
      [handle],
    );
    const createdAtMs = Number(stored.rows[0]?.created_at_ms);
    const dbAfterMs = Number(stored.rows[0]?.db_now_ms);

    expect(marked).toEqual([]);
    expect(createdAtMs).toBeGreaterThanOrEqual(dbBeforeMs);
    expect(createdAtMs).toBeLessThanOrEqual(dbAfterMs);
    expect(dbAfterMs - createdAtMs).toBeLessThan(10_000);
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

describe.skipIf(!LIVE)("GLY-345 live migration guards", () => {
  let adminPool: Pool;

  beforeAll(() => {
    adminPool = new Pool(pgConfig());
  });

  afterAll(async () => {
    await adminPool?.end();
  });

  async function withBaseSchema<T>(label: string, run: (pool: Pool) => Promise<T>): Promise<T> {
    const schema = `phi_gly345_${label}_${process.pid}_${Date.now()}_${Math.floor(Math.random() * 1_000_000)}`;
    await adminPool.query(`CREATE SCHEMA "${schema}"`);
    const scoped = new Pool({ ...pgConfig(), options: `-c search_path=${schema}` });
    try {
      await scoped.query(BASE_MIGRATION_SQL);
      return await run(scoped);
    } finally {
      await scoped.end();
      await adminPool.query(`DROP SCHEMA IF EXISTS "${schema}" CASCADE`);
    }
  }

  async function seedLegacyClaim(
    pool: Pool,
    options: { readonly attempt: string; readonly token: string; readonly expires: bigint },
  ): Promise<void> {
    const prepared = randomUUID();
    const mapping = encodeTextKey(`tenant-a${SEP}matter-a${SEP}1${SEP}${options.token}`);
    const idempotency = encodeTextKey(`tenant-a${SEP}${options.attempt}${SEP}${options.token}`);
    await pool.query(
      `INSERT INTO reversal_prepared (
         prepared_blob_id, tenant_id, mapping_key, idempotency_key, scope_digest,
         staging_path, blob_path, created_at_ms, state, blob_etag, blob_len
       ) VALUES ($1, 'tenant-a', $2, $3, 'scope', $4, $5, 100, 'committed', 'etag', 1)`,
      [prepared, mapping, idempotency, `staging/${prepared}`, `blobs/${prepared}`],
    );
    await pool.query(
      `INSERT INTO reversal_claim (
         idempotency_key, tenant_id, mapping_key, scope_digest, commit_handle,
         prepared_blob_id, ordinal, created_at_ms, expires_at_ms, state
       ) VALUES ($1, 'tenant-a', $2, 'scope', $3, $4, 1, 100, $5, 'pending')`,
      [idempotency, mapping, randomUUID(), prepared, options.expires.toString()],
    );
  }

  it("aborts ambiguous finite legacy expiry atomically before schema mutation", async () => {
    await withBaseSchema("ambiguous_expiry", async (scoped) => {
      await seedLegacyClaim(scoped, { attempt: "ambiguous", token: "[[One]]", expires: 999n });
      await expect(runMigrations(scoped)).rejects.toThrow("gly345_ambiguous_legacy_expiry");
      const added = await scoped.query(
        `SELECT 1 FROM information_schema.columns
         WHERE table_schema = current_schema() AND table_name = 'reversal_prepared'
           AND column_name = 'operation_key'`,
      );
      expect(added.rowCount).toBe(0);
      expect((await scoped.query(`SELECT 1 FROM reversal_prepared`)).rowCount).toBe(1);
    });
  });

  it("aborts mixed legal legacy classes for one decoded operation atomically", async () => {
    await withBaseSchema("mixed_class", async (scoped) => {
      await seedLegacyClaim(scoped, {
        attempt: "mixed",
        token: "[[One]]",
        expires: MATTER_EXPIRES_AT,
      });
      await seedLegacyClaim(scoped, {
        attempt: "mixed",
        token: "[[Two]]",
        expires: 86_400_100n,
      });
      await expect(runMigrations(scoped)).rejects.toThrow("gly345_mixed_legacy_operation_retention");
      expect((await scoped.query(`SELECT 1 FROM reversal_prepared`)).rowCount).toBe(2);
      expect((await scoped.query(
        `SELECT 1 FROM information_schema.columns
         WHERE table_schema = current_schema() AND table_name = 'reversal_prepared'
           AND column_name = 'operation_key'`,
      )).rowCount).toBe(0);
    });
  });

  it("drops arbitrary anonymous legacy state checks by definition", async () => {
    await withBaseSchema("anonymous_check", async (scoped) => {
      await scoped.query(
        `ALTER TABLE reversal_prepared
         ADD CONSTRAINT arbitrary_old_writer_state_guard CHECK (state <> 'superseded')`,
      );
      await runMigrations(scoped);
      const surviving = await scoped.query<{ readonly definition: string }>(
        `SELECT pg_get_constraintdef(oid) AS definition
         FROM pg_constraint
         WHERE conrelid = 'reversal_prepared'::regclass AND contype = 'c'
           AND position('state' IN lower(pg_get_constraintdef(oid))) > 0`,
      );
      expect(surviving.rows.length).toBeGreaterThan(0);
      expect(surviving.rows.every((row) => row.definition.toLowerCase().includes("superseded"))).toBe(true);
    });
  });

  it("preserves every legacy lifecycle row and seeds only non-current flushed rows from migration DB now", async () => {
    await withBaseSchema("legacy_preservation", async (scoped) => {
      const mapping = encodeTextKey(`tenant-a${SEP}matter-a${SEP}1${SEP}[[LegacyCurrent]]`);
      const oldPrepared = randomUUID();
      const currentPrepared = randomUUID();
      const oldCommit = randomUUID();
      const currentCommit = randomUUID();
      const oldId = encodeTextKey(`tenant-a${SEP}legacy-old${SEP}[[LegacyCurrent]]`);
      const currentId = encodeTextKey(`tenant-a${SEP}legacy-current${SEP}[[LegacyCurrent]]`);
      for (const [prepared, id] of [[oldPrepared, oldId], [currentPrepared, currentId]] as const) {
        await scoped.query(
          `INSERT INTO reversal_prepared (
             prepared_blob_id, tenant_id, mapping_key, idempotency_key, scope_digest,
             staging_path, blob_path, created_at_ms, state, blob_etag, blob_len
           ) VALUES ($1, 'tenant-a', $2, $3, 'scope', $4, $5, 100,
                     'committed', 'etag', 1)`,
          [prepared, mapping, id, `staging/${prepared}`, `blobs/${prepared}`],
        );
      }
      await scoped.query(
        `INSERT INTO reversal_claim (
           idempotency_key, tenant_id, mapping_key, scope_digest, commit_handle,
           prepared_blob_id, ordinal, created_at_ms, expires_at_ms, state
         ) VALUES
           ($1, 'tenant-a', $3, 'scope', $4, $5, 1, 100, 18446744073709551615, 'flushed'),
           ($2, 'tenant-a', $3, 'scope', $6, $7, 2, 100, 18446744073709551615, 'flushed')`,
        [oldId, currentId, mapping, oldCommit, oldPrepared, currentCommit, currentPrepared],
      );
      await scoped.query(
        `INSERT INTO reversal_current (
           mapping_key, tenant_id, commit_handle, prepared_blob_id, ordinal, flushed_at_ms
         ) VALUES ($1, 'tenant-a', $2, $3, 2, $4)`,
        [mapping, currentCommit, currentPrepared, Number.MAX_SAFE_INTEGER],
      );

      const preserved = [
        { state: "uploading", blob: false, quarantine: false },
        { state: "finalized", blob: true, quarantine: false },
        { state: "orphaned", blob: true, quarantine: false },
        { state: "upload_reclaim_marked", blob: false, quarantine: false },
        { state: "reclaim_marked", blob: true, quarantine: false },
        { state: "quarantined", blob: true, quarantine: true },
      ] as const;
      const preservedIds: Array<{ readonly prepared: string; readonly state: string }> = [];
      for (const [index, row] of preserved.entries()) {
        const prepared = randomUUID();
        const idempotency = encodeTextKey(`tenant-a${SEP}preserved-${index}${SEP}[[T${index}]]`);
        const rowMapping = encodeTextKey(`tenant-a${SEP}matter-a${SEP}1${SEP}[[T${index}]]`);
        await scoped.query(
          `INSERT INTO reversal_prepared (
             prepared_blob_id, tenant_id, mapping_key, idempotency_key, scope_digest,
             staging_path, blob_path, created_at_ms, state, blob_etag, blob_len, quarantined_at_ms
           ) VALUES ($1, 'tenant-a', $2, $3, 'scope', $4, $5, 100, $6,
                     $7, $8, $9)`,
          [
            prepared,
            rowMapping,
            idempotency,
            `staging/${prepared}`,
            `blobs/${prepared}`,
            row.state,
            row.blob ? "etag" : null,
            row.blob ? 1 : null,
            row.quarantine ? 100 : null,
          ],
        );
        preservedIds.push({ prepared, state: row.state });
      }
      const before = await scoped.query<{ readonly db_now_ms: string }>(
        `SELECT (extract(epoch FROM clock_timestamp()) * 1000)::bigint::text AS db_now_ms`,
      );
      await runMigrations(scoped);
      const after = await scoped.query<{ readonly db_now_ms: string }>(
        `SELECT (extract(epoch FROM clock_timestamp()) * 1000)::bigint::text AS db_now_ms`,
      );
      const old = await scoped.query<{
        readonly prepared_state: string;
        readonly superseded_at_ms: string;
        readonly claim_state: string;
        readonly prepared_blob_id: string | null;
      }>(
        `SELECT p.state AS prepared_state, p.superseded_at_ms::text AS superseded_at_ms,
                c.state AS claim_state, c.prepared_blob_id
         FROM reversal_prepared p
         JOIN reversal_claim c ON c.idempotency_key = p.idempotency_key
         WHERE p.prepared_blob_id = $1`,
        [oldPrepared],
      );
      expect(old.rows[0]?.prepared_state).toBe("superseded");
      expect(old.rows[0]?.claim_state).toBe("superseded");
      expect(old.rows[0]?.prepared_blob_id).toBeNull();
      expect(BigInt(old.rows[0]!.superseded_at_ms)).toBeGreaterThanOrEqual(BigInt(before.rows[0]!.db_now_ms));
      expect(BigInt(old.rows[0]!.superseded_at_ms)).toBeLessThanOrEqual(BigInt(after.rows[0]!.db_now_ms));
      const current = await scoped.query<{ readonly state: string }>(
        `SELECT state FROM reversal_prepared WHERE prepared_blob_id = $1`,
        [currentPrepared],
      );
      expect(current.rows[0]?.state).toBe("committed");
      for (const expected of preservedIds) {
        const actual = await scoped.query<{ readonly state: string }>(
          `SELECT state FROM reversal_prepared WHERE prepared_blob_id = $1`,
          [expected.prepared],
        );
        expect(actual.rows[0]?.state).toBe(expected.state);
      }
      expect((await scoped.query(`SELECT 1 FROM reversal_prepared`)).rowCount).toBe(8);
    });
  });
});

describe.skipIf(!LIVE || process.env.PHI_REVERSAL_PG_STRESS !== "1")(
  "GLY-345 live 100k migration availability guard",
  () => {
    let adminPool: Pool;
    beforeAll(() => { adminPool = new Pool(pgConfig()); });
    afterAll(async () => { await adminPool?.end(); });

    it.each([
      { rows: 100_001, succeeds: false },
      { rows: 100_000, succeeds: true },
    ])("enforces the exact $rows row boundary", async ({ rows, succeeds }) => {
      const schema = `phi_gly345_stress_${rows}_${process.pid}_${Date.now()}`;
      await adminPool.query(`CREATE SCHEMA "${schema}"`);
      const scoped = new Pool({ ...pgConfig(), options: `-c search_path=${schema}` });
      try {
        await scoped.query(BASE_MIGRATION_SQL);
        await scoped.query(
          `INSERT INTO reversal_prepared (
             prepared_blob_id, tenant_id, mapping_key, idempotency_key, scope_digest,
             staging_path, blob_path, created_at_ms, state
           )
           SELECT (substr(md5(g::text),1,8)||'-'||substr(md5(g::text),9,4)||'-4'||
                   substr(md5(g::text),14,3)||'-8'||substr(md5(g::text),18,3)||'-'||
                   substr(md5(g::text),21,12))::uuid,
                  'tenant-a', 'mapping-'||g,
                  'b64url-v1:' || rtrim(translate(encode(
                    convert_to('tenant-a', 'UTF8') || decode('00', 'hex') ||
                    convert_to('attempt-'||g, 'UTF8') || decode('00', 'hex') ||
                    convert_to('[[Token]]', 'UTF8'), 'base64'), '+/', '-_'), '='),
                  'scope', 'staging/'||g, 'blobs/'||g, 100, 'uploading'
           FROM generate_series(1, $1) g`,
          [rows],
        );
        if (succeeds) {
          await expect(runMigrations(scoped)).resolves.toBeUndefined();
        } else {
          await expect(runMigrations(scoped)).rejects.toThrow("gly345_online_migration_row_limit_exceeded");
          expect((await scoped.query(
            `SELECT 1 FROM information_schema.columns
             WHERE table_schema=current_schema() AND table_name='reversal_prepared'
               AND column_name='operation_key'`,
          )).rowCount).toBe(0);
        }
      } finally {
        await scoped.end();
        await adminPool.query(`DROP SCHEMA IF EXISTS "${schema}" CASCADE`);
      }
    }, 180_000);
  },
);
