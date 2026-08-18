import { randomUUID } from "node:crypto";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import type { Pool, PoolClient, QueryResultRow } from "pg";
import type { TenantId } from "../../../core/brands";
import type {
  DekGeneration,
  DekGenerationId,
  GcmNonce96,
  PreparedWriteHandle,
  PublishReversalResult,
  PublishedCommitHandle,
  ReversalMappingKey,
  ReversalScopeDigest,
  WrappedDekMaterial,
} from "../ports";
import type {
  ClaimControlPlaneState,
  ClaimBlobReference,
  ControlPlane,
  CurrentPointerRow,
  ExpirePendingDetachInput,
  FlushClaimInput,
  InsertPreparedUploadingInput,
  MarkFinalizedInput,
  MarkQuarantinedInput,
  PublishPreparedInput,
  ReclaimBlobRow,
  ReclaimFinalizedOrphansSelection,
  ReclaimLimitInput,
  ReclaimPreviewInput,
  ReclaimPreviewOutcome,
  ReclaimQueryInput,
  ReclaimUploadRow,
  StaleUploadReclaimInput,
} from "./control-plane";

const MIGRATION_PATH = resolve(__dirname, "../../../../migrations/0001_phi_reversal_control_plane.sql");
const KEY_ENCODING_PREFIX = "b64url-v1:";

interface DekRow extends QueryResultRow {
  readonly dek_generation_id: string;
  readonly wrapped_dek: Buffer;
}

interface CounterRow extends QueryResultRow {
  readonly counter: string;
}

interface PreparedPublishRow extends QueryResultRow {
  readonly prepared_blob_id: string;
  readonly tenant_id: string;
  readonly mapping_key: string;
  readonly idempotency_key: string;
  readonly scope_digest: string;
  readonly created_at_ms: string;
  readonly state: string;
  readonly blob_etag: string | null;
  readonly blob_len: string | null;
}

interface ClaimRow extends QueryResultRow {
  readonly idempotency_key: string;
  readonly tenant_id: string;
  readonly mapping_key: string;
  readonly scope_digest: string;
  readonly commit_handle: string;
  readonly prepared_blob_id: string | null;
  readonly ordinal: string;
  readonly created_at_ms: string;
  readonly expires_at_ms: string;
  readonly state: ClaimControlPlaneState;
  readonly is_expired?: boolean;
}

interface ReferenceRow extends QueryResultRow {
  readonly has_current: boolean;
  readonly has_other_claim: boolean;
}

interface PreparedBlobRow extends QueryResultRow {
  readonly prepared_blob_id: string;
  readonly state: string;
  readonly blob_etag: string | null;
  readonly blob_len: string | null;
}

interface ClaimBlobReferenceRow extends QueryResultRow {
  readonly claim_state: ClaimControlPlaneState;
  readonly prepared_blob_id: string | null;
  readonly prepared_state: string | null;
  readonly blob_path: string | null;
  readonly blob_etag: string | null;
  readonly blob_len: string | null;
}

interface PointerRow extends QueryResultRow {
  readonly mapping_key: string;
  readonly tenant_id: string;
  readonly commit_handle: string;
  readonly prepared_blob_id: string;
  readonly ordinal: string;
  readonly flushed_at_ms: string;
  readonly blob_path: string | null;
  readonly blob_etag: string | null;
  readonly blob_len: string | null;
  readonly prepared_state: string | null;
}

interface ReclaimBlobSqlRow extends QueryResultRow {
  readonly prepared_blob_id: string;
  readonly blob_path: string;
}

interface ReclaimUploadSqlRow extends ReclaimBlobSqlRow {
  readonly staging_path: string;
}

interface ReclaimCandidateSqlRow extends ReclaimBlobSqlRow {
  readonly state: "finalized" | "orphaned" | "reclaim_marked";
}

interface ReclaimCountSqlRow extends QueryResultRow {
  readonly count: number;
}

interface ReclaimIdSqlRow extends QueryResultRow {
  readonly prepared_blob_id: string;
}

function encodeTextKey(value: string): string {
  // PostgreSQL TEXT rejects U+0000. The frozen logical keys use NUL fences, so persist a
  // lossless/injective representation while retaining TEXT PK/index semantics.
  return `${KEY_ENCODING_PREFIX}${Buffer.from(value, "utf8").toString("base64url")}`;
}

function decodeTextKey(value: string): string {
  if (!value.startsWith(KEY_ENCODING_PREFIX)) {
    throw new Error("postgres_control_plane_invalid_key_encoding");
  }
  return Buffer.from(value.slice(KEY_ENCODING_PREFIX.length), "base64url").toString("utf8");
}

function safeEpochMs(value: number, label: string): number {
  if (!Number.isSafeInteger(value) || value < 0) {
    throw new Error(`postgres_control_plane_invalid_${label}`);
  }
  return value;
}

function safeLimit(value: number): number {
  if (!Number.isSafeInteger(value) || value <= 0) {
    throw new Error("postgres_control_plane_invalid_limit");
  }
  return value;
}

function parseEpochMs(value: string, label: string): number {
  return safeEpochMs(Number(value), label);
}

function nonce96(counter: bigint): GcmNonce96 {
  if (counter < 0n || counter > 2n ** 96n - 1n) {
    throw new Error("nonce_counter_exhausted");
  }
  const nonce = Buffer.alloc(12);
  nonce.writeBigUInt64BE(counter >> 32n, 0);
  nonce.writeUInt32BE(Number(counter & 0xffff_ffffn), 8);
  return new Uint8Array(nonce) as unknown as GcmNonce96;
}

function preparedHandle(value: string): PreparedWriteHandle {
  return value as unknown as PreparedWriteHandle;
}

function commitHandle(value: string): PublishedCommitHandle {
  return value as unknown as PublishedCommitHandle;
}

function mappingKey(value: string): ReversalMappingKey {
  return decodeTextKey(value) as unknown as ReversalMappingKey;
}

async function transaction<T>(pool: Pool, operation: (client: PoolClient) => Promise<T>): Promise<T> {
  const client = await pool.connect();
  try {
    await client.query("BEGIN");
    try {
      const result = await operation(client);
      await client.query("COMMIT");
      return result;
    } catch (error: unknown) {
      await client.query("ROLLBACK");
      throw error;
    }
  } finally {
    client.release();
  }
}

/** Apply the idempotent Lane-B1 control-plane migration in the pool's configured search_path. */
export async function runMigrations(pool: Pool): Promise<void> {
  const sql = await readFile(MIGRATION_PATH, "utf8");
  await transaction(pool, async (client) => {
    await client.query(sql);
  });
}

/** node-postgres implementation of the GLY-346 transactional control plane. */
export class PostgresControlPlane implements ControlPlane {
  readonly #pool: Pool;

  public constructor(pool: Pool) {
    this.#pool = pool;
  }

  public async ensureDekGeneration(input: Parameters<ControlPlane["ensureDekGeneration"]>[0]): Promise<DekGeneration> {
    const scopeKey = encodeTextKey(`${input.scope.tenantId}\0${input.scope.matterId}\0${input.scope.purpose}`);
    const existing = await this.#pool.query<DekRow>(
      `SELECT dek_generation_id, wrapped_dek
       FROM reversal_dek_generation
       WHERE dek_scope_key = $1`,
      [scopeKey],
    );
    const first = existing.rows[0];
    if (first !== undefined) {
      return this.#dekGeneration(first);
    }

    const minted = await input.mint();
    await this.#pool.query(
      `INSERT INTO reversal_dek_generation (
         dek_scope_key, tenant_id, matter_id, purpose, dek_generation_id, wrapped_dek, created_at_ms
       ) VALUES ($1, $2, $3, $4, $5, $6,
                 (EXTRACT(EPOCH FROM clock_timestamp()) * 1000)::bigint)
       ON CONFLICT (dek_scope_key) DO NOTHING`,
      [
        scopeKey,
        input.scope.tenantId,
        input.scope.matterId,
        input.scope.purpose,
        encodeTextKey(minted.dekGenerationId as unknown as string),
        Buffer.from(minted.wrappedDek),
      ],
    );
    const winner = await this.#pool.query<DekRow>(
      `SELECT dek_generation_id, wrapped_dek
       FROM reversal_dek_generation
       WHERE dek_scope_key = $1`,
      [scopeKey],
    );
    const row = winner.rows[0];
    if (row === undefined) {
      throw new Error("ensure_dek_generation_missing_winner");
    }
    return this.#dekGeneration(row);
  }

  public async reserveNonce(input: Parameters<ControlPlane["reserveNonce"]>[0]): Promise<GcmNonce96> {
    const result = await this.#pool.query<CounterRow>(
      `INSERT INTO reversal_nonce_counter (tenant_id, dek_generation_id, next_counter)
       VALUES ($1, $2, 1)
       ON CONFLICT (tenant_id, dek_generation_id) DO UPDATE
       SET next_counter = reversal_nonce_counter.next_counter + 1
       RETURNING next_counter - 1 AS counter`,
      [input.tenantId, encodeTextKey(input.dekGenerationId as unknown as string)],
    );
    const row = result.rows[0];
    if (row === undefined) {
      throw new Error("nonce_reservation_missing_counter");
    }
    return nonce96(BigInt(row.counter));
  }

  public async insertPreparedUploading(input: InsertPreparedUploadingInput): Promise<void> {
    // Fail closed on producer metadata validity; it gates no persisted lifecycle-age value.
    safeEpochMs(input.createdAtEpochMs, "created_at_ms");
    // Reclamation and prepared-row age share the database clock. This assumes the Azure job and
    // PostgreSQL clocks are NTP-tight infrastructure, unlike arbitrary application replicas.
    const result = await this.#pool.query(
      `INSERT INTO reversal_prepared (
         prepared_blob_id, tenant_id, mapping_key, idempotency_key, scope_digest,
         staging_path, blob_path, created_at_ms, state
       ) VALUES ($1, $2, $3, $4, $5, $6, $7,
                 (EXTRACT(EPOCH FROM clock_timestamp()) * 1000)::bigint, 'uploading')
       ON CONFLICT (prepared_blob_id) DO NOTHING`,
      [
        input.preparedBlobId,
        input.tenantId,
        encodeTextKey(input.mappingKey as unknown as string),
        encodeTextKey(input.idempotencyKey as unknown as string),
        input.immutableScopeDigest,
        input.stagingPath,
        input.blobPath,
      ],
    );
    if (result.rowCount !== 1) {
      throw new Error("insert_prepared_duplicate_handle");
    }
  }

  public async markFinalized(input: MarkFinalizedInput): Promise<void> {
    if (input.blobEtag.length === 0 || input.blobLength < 0n) {
      throw new Error("mark_finalized_invalid_blob_attributes");
    }
    const result = await this.#pool.query(
      `UPDATE reversal_prepared
       SET state = 'finalized', blob_etag = $2, blob_len = $3
       WHERE prepared_blob_id = $1 AND state = 'uploading'`,
      [input.preparedBlobId, input.blobEtag, input.blobLength.toString()],
    );
    if (result.rowCount !== 1) {
      throw new Error("prepare_finalize_lost_race");
    }
  }

  public publish(input: PublishPreparedInput): Promise<PublishReversalResult> {
    safeEpochMs(input.nowEpochMilliseconds, "now_ms");
    if (input.expiresAtEpochMs < 0n || input.expiresAtEpochMs > 2n ** 64n - 1n) {
      return Promise.reject(new Error("publish_invalid_expiry"));
    }
    return transaction(this.#pool, async (client) => {
      const preparedResult = await client.query<PreparedPublishRow>(
        `SELECT prepared_blob_id, tenant_id, mapping_key, idempotency_key, scope_digest,
                created_at_ms, state, blob_etag, blob_len
         FROM reversal_prepared
         WHERE prepared_blob_id = $1
         FOR UPDATE`,
        [input.prepared.handle],
      );
      const prepared = preparedResult.rows[0];
      if (prepared === undefined) {
        throw new Error("publish_unknown_prepared");
      }
      if (prepared.state !== "finalized" && prepared.state !== "committed") {
        throw new Error("publish_prepared_not_finalized");
      }

      const ordinalResult = await client.query<CounterRow>(
        `INSERT INTO reversal_ordinal_seq (mapping_key, tenant_id, next_ordinal)
         VALUES ($1, $2, 1)
         ON CONFLICT (mapping_key) DO UPDATE
         SET next_ordinal = reversal_ordinal_seq.next_ordinal + 1
         RETURNING next_ordinal - 1 AS counter`,
        [prepared.mapping_key, prepared.tenant_id],
      );
      const ordinal = ordinalResult.rows[0]?.counter;
      if (ordinal === undefined) {
        throw new Error("publish_missing_ordinal");
      }

      const newCommit = randomUUID();
      const inserted = await client.query<ClaimRow>(
        `INSERT INTO reversal_claim (
           idempotency_key, tenant_id, mapping_key, scope_digest, commit_handle,
           prepared_blob_id, ordinal, created_at_ms, expires_at_ms, state
         ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'pending')
         ON CONFLICT (idempotency_key) DO NOTHING
         RETURNING *`,
        [
          prepared.idempotency_key,
          prepared.tenant_id,
          prepared.mapping_key,
          prepared.scope_digest,
          newCommit,
          prepared.prepared_blob_id,
          ordinal,
          prepared.created_at_ms,
          input.expiresAtEpochMs.toString(),
        ],
      );

      if (inserted.rowCount === 1) {
        if (prepared.state !== "finalized" || prepared.blob_etag === null || prepared.blob_len === null) {
          throw new Error("publish_prepared_not_durable");
        }
        const committed = await client.query(
          `UPDATE reversal_prepared
           SET state = 'committed'
           WHERE prepared_blob_id = $1 AND state = 'finalized'`,
          [prepared.prepared_blob_id],
        );
        if (committed.rowCount !== 1) {
          throw new Error("publish_prepared_transition_lost");
        }
        return { kind: "published", commit: commitHandle(newCommit) };
      }

      const existingResult = await client.query<ClaimRow>(
        `SELECT *, ($2::numeric >= expires_at_ms) AS is_expired FROM reversal_claim
         WHERE idempotency_key = $1
         FOR UPDATE`,
        [prepared.idempotency_key, input.nowEpochMilliseconds.toString()],
      );
      const existing = existingResult.rows[0];
      if (existing === undefined) {
        throw new Error("publish_conflict_missing_claim");
      }
      const expired = await this.#computeExpiredAndDetach(client, existing);
      return {
        kind: "existing",
        commit: commitHandle(existing.commit_handle),
        immutableScopeDigest: existing.scope_digest as unknown as ReversalScopeDigest,
        expired,
      };
    });
  }

  public async readClaimBlobReference(commit: PublishedCommitHandle): Promise<ClaimBlobReference> {
    const result = await this.#pool.query<ClaimBlobReferenceRow>(
      `SELECT c.state AS claim_state, c.prepared_blob_id, p.state AS prepared_state,
              p.blob_path, p.blob_etag, p.blob_len
       FROM reversal_claim c
       LEFT JOIN reversal_prepared p ON p.prepared_blob_id = c.prepared_blob_id
       WHERE c.commit_handle = $1`,
      [commit],
    );
    const row = result.rows[0];
    if (
      row === undefined ||
      (row.claim_state !== "pending" && row.claim_state !== "flushed") ||
      row.prepared_blob_id === null ||
      row.prepared_state !== "committed" ||
      row.blob_path === null ||
      row.blob_etag === null ||
      row.blob_len === null
    ) {
      throw new Error("flush_claim_blob_reference_integrity_failure");
    }
    return { blobPath: row.blob_path, blobEtag: row.blob_etag, blobLength: BigInt(row.blob_len) };
  }

  public async flushClaim(input: FlushClaimInput): Promise<void> {
    safeEpochMs(input.nowEpochMilliseconds, "now_ms");
    if (input.blobEtag.length === 0 || input.blobLength < 0n) {
      throw new Error("flush_invalid_blob_attributes");
    }
    const client = await this.#pool.connect();
    let expiredPending = false;
    try {
      await client.query("BEGIN");
      try {
        const claimResult = await client.query<ClaimRow>(
          `SELECT *, ($2::numeric >= expires_at_ms) AS is_expired FROM reversal_claim
           WHERE commit_handle = $1
           FOR UPDATE`,
          [input.commit, input.nowEpochMilliseconds.toString()],
        );
        const claim = claimResult.rows[0];
        if (claim === undefined) {
          throw new Error("flush_unknown_commit");
        }
        if (claim.state === "flushed") {
          await client.query("COMMIT");
          return;
        }
        if (claim.state === "expired") {
          throw new Error("flush_expired_commit");
        }
        if (claim.is_expired === undefined) {
          throw new Error("flush_missing_expiry_comparison");
        }
        if (claim.is_expired) {
          await this.#expireLockedPending(client, claim);
          await client.query("COMMIT");
          expiredPending = true;
        } else {
          if (claim.prepared_blob_id === null) {
            throw new Error("flush_pending_without_prepared");
          }
          const preparedResult = await client.query<PreparedBlobRow>(
            `SELECT prepared_blob_id, state, blob_etag, blob_len
             FROM reversal_prepared
             WHERE prepared_blob_id = $1
             FOR UPDATE`,
            [claim.prepared_blob_id],
          );
          const prepared = preparedResult.rows[0];
          if (
            prepared === undefined ||
            prepared.state !== "committed" ||
            prepared.blob_etag === null ||
            prepared.blob_len === null ||
            prepared.blob_etag !== input.blobEtag ||
            BigInt(prepared.blob_len) !== input.blobLength
          ) {
            throw new Error("flush_blob_integrity_failure");
          }
          const flushed = await client.query(
            `UPDATE reversal_claim
             SET state = 'flushed'
             WHERE commit_handle = $1 AND state = 'pending'`,
            [claim.commit_handle],
          );
          if (flushed.rowCount !== 1) {
            throw new Error("flush_claim_transition_lost");
          }
          await client.query(
            `INSERT INTO reversal_current (
               mapping_key, tenant_id, commit_handle, prepared_blob_id, ordinal, flushed_at_ms
             ) VALUES ($1, $2, $3, $4, $5, $6)
             ON CONFLICT (mapping_key) DO UPDATE
             SET tenant_id = EXCLUDED.tenant_id,
                 commit_handle = EXCLUDED.commit_handle,
                 prepared_blob_id = EXCLUDED.prepared_blob_id,
                 ordinal = EXCLUDED.ordinal,
                 flushed_at_ms = EXCLUDED.flushed_at_ms
             WHERE EXCLUDED.ordinal > reversal_current.ordinal`,
            [
              claim.mapping_key,
              claim.tenant_id,
              claim.commit_handle,
              claim.prepared_blob_id,
              claim.ordinal,
              input.nowEpochMilliseconds,
            ],
          );
          await client.query("COMMIT");
        }
      } catch (error: unknown) {
        await client.query("ROLLBACK");
        throw error;
      }
    } finally {
      client.release();
    }
    if (expiredPending) {
      throw new Error("flush_expired_pending_commit");
    }
  }

  public expirePendingDetach(input: ExpirePendingDetachInput): Promise<boolean> {
    safeEpochMs(input.nowEpochMilliseconds, "now_ms");
    return transaction(this.#pool, async (client) => {
      const result = await client.query<ClaimRow>(
        `SELECT *, ($2::numeric >= expires_at_ms) AS is_expired FROM reversal_claim
         WHERE commit_handle = $1
         FOR UPDATE`,
        [input.commit, input.nowEpochMilliseconds.toString()],
      );
      const claim = result.rows[0];
      if (claim === undefined) {
        throw new Error("expire_unknown_commit");
      }
      return this.#computeExpiredAndDetach(client, claim);
    });
  }

  public async readCurrentPointers(mappingKeys: readonly ReversalMappingKey[]): Promise<readonly CurrentPointerRow[]> {
    if (mappingKeys.length === 0) {
      throw new Error("read_current_requires_exact_keys");
    }
    const encoded = [...new Set(mappingKeys.map((key) => {
      const value = key as unknown as string;
      if (value.length === 0) {
        throw new Error("read_current_requires_nonempty_key");
      }
      return encodeTextKey(value);
    }))];
    const result = await this.#pool.query<PointerRow>(
      `SELECT c.mapping_key, c.tenant_id, c.commit_handle, c.prepared_blob_id,
              c.ordinal, c.flushed_at_ms, p.blob_path, p.blob_etag, p.blob_len,
              p.state AS prepared_state
       FROM reversal_current c
       LEFT JOIN reversal_prepared p ON p.prepared_blob_id = c.prepared_blob_id
       WHERE c.mapping_key = ANY($1::text[])`,
      [encoded],
    );
    return result.rows.map((row) => {
      if (
        row.prepared_state !== "committed" ||
        row.blob_path === null ||
        row.blob_etag === null ||
        row.blob_len === null
      ) {
        throw new Error("read_current_pointer_integrity_failure");
      }
      return {
        mappingKey: mappingKey(row.mapping_key),
        tenantId: row.tenant_id as unknown as TenantId,
        commit: commitHandle(row.commit_handle),
        preparedBlobId: preparedHandle(row.prepared_blob_id),
        ordinal: BigInt(row.ordinal),
        flushedAtEpochMs: parseEpochMs(row.flushed_at_ms, "flushed_at_ms"),
        blobPath: row.blob_path,
        blobEtag: row.blob_etag,
        blobLength: BigInt(row.blob_len),
      };
    });
  }

  public reclaimFinalizedOrphans(input: ReclaimQueryInput): Promise<readonly ReclaimBlobRow[]> {
    safeEpochMs(input.olderThanEpochMs, "older_than_ms");
    const limit = safeLimit(input.limit);
    return transaction(this.#pool, async (client) => {
      const recovered = await client.query<ReclaimBlobSqlRow>(
        `SELECT p.prepared_blob_id, p.blob_path
         FROM reversal_prepared p
         WHERE p.state = 'reclaim_marked'
           AND NOT EXISTS (
             SELECT 1 FROM reversal_claim c WHERE c.prepared_blob_id = p.prepared_blob_id
           )
           AND NOT EXISTS (
             SELECT 1 FROM reversal_current c WHERE c.prepared_blob_id = p.prepared_blob_id
           )
         FOR UPDATE OF p SKIP LOCKED
         LIMIT $1`,
        [limit],
      );
      const remaining = limit - recovered.rows.length;
      const fresh = remaining === 0
        ? { rows: [] as ReclaimBlobSqlRow[] }
        : await client.query<ReclaimBlobSqlRow>(
          `UPDATE reversal_prepared
           SET state = 'reclaim_marked'
           WHERE prepared_blob_id IN (
             SELECT p.prepared_blob_id
             FROM reversal_prepared p
             WHERE p.state IN ('finalized', 'orphaned')
               AND p.created_at_ms < $1
               AND NOT EXISTS (
                 SELECT 1 FROM reversal_claim c WHERE c.prepared_blob_id = p.prepared_blob_id
               )
               AND NOT EXISTS (
                 SELECT 1 FROM reversal_current c WHERE c.prepared_blob_id = p.prepared_blob_id
               )
             FOR UPDATE OF p SKIP LOCKED
             LIMIT $2
           )
           RETURNING prepared_blob_id, blob_path`,
          [input.olderThanEpochMs, remaining],
        );
      return [...recovered.rows, ...fresh.rows].map((row) => this.#reclaimBlob(row));
    });
  }

  public selectFinalizedOrphansForReclaim(
    input: ReclaimQueryInput,
  ): Promise<ReclaimFinalizedOrphansSelection> {
    safeEpochMs(input.olderThanEpochMs, "older_than_ms");
    const limit = safeLimit(input.limit);
    return transaction(this.#pool, async (client) => {
      const skippedReferenced = await this.#countReferencedPathOneCandidates(
        client,
        input.olderThanEpochMs,
        limit,
      );
      const candidates = await client.query<ReclaimCandidateSqlRow>(
        `SELECT p.prepared_blob_id, p.blob_path, p.state
         FROM reversal_prepared p
         WHERE (
              p.state = 'reclaim_marked'
              OR (
                p.state IN ('finalized', 'orphaned')
                AND p.created_at_ms < $1
              )
            )
           AND NOT EXISTS (
             SELECT 1 FROM reversal_claim c WHERE c.prepared_blob_id = p.prepared_blob_id
           )
           AND NOT EXISTS (
             SELECT 1 FROM reversal_current c WHERE c.prepared_blob_id = p.prepared_blob_id
           )
         ORDER BY CASE WHEN p.state = 'reclaim_marked' THEN 0 ELSE 1 END,
                  p.created_at_ms,
                  p.prepared_blob_id
         FOR UPDATE OF p SKIP LOCKED
         LIMIT $2`,
        [input.olderThanEpochMs, limit],
      );

      const rows: ReclaimBlobRow[] = [];
      for (const candidate of candidates.rows) {
        if (candidate.state !== "reclaim_marked") {
          const marked = await client.query(
            `UPDATE reversal_prepared p
             SET state = 'reclaim_marked'
             WHERE p.prepared_blob_id = $1
               AND p.state IN ('finalized', 'orphaned')
               AND p.created_at_ms < $2
               AND NOT EXISTS (
                 SELECT 1 FROM reversal_claim c WHERE c.prepared_blob_id = p.prepared_blob_id
               )
               AND NOT EXISTS (
                 SELECT 1 FROM reversal_current c WHERE c.prepared_blob_id = p.prepared_blob_id
               )`,
            [candidate.prepared_blob_id, input.olderThanEpochMs],
          );
          if (marked.rowCount !== 1) {
            throw new Error("reclaim_finalized_orphan_transition_lost");
          }
        }
        rows.push(this.#reclaimBlob(candidate));
      }
      return { rows, skippedReferenced };
    });
  }

  public markQuarantined(input: MarkQuarantinedInput): Promise<void> {
    safeEpochMs(input.quarantinedAtEpochMs, "quarantined_at_ms");
    return transaction(this.#pool, async (client) => {
      const result = await client.query(
        `UPDATE reversal_prepared
         SET state = 'quarantined', quarantined_at_ms = $2
         WHERE prepared_blob_id = $1 AND state = 'reclaim_marked'`,
        [input.preparedBlobId, input.quarantinedAtEpochMs],
      );
      if (result.rowCount === 1) {
        return;
      }
      const current = await client.query<{ readonly state: string }>(
        `SELECT state FROM reversal_prepared WHERE prepared_blob_id = $1`,
        [input.preparedBlobId],
      );
      if (current.rows[0]?.state !== "quarantined") {
        throw new Error("mark_quarantined_invalid_state");
      }
    });
  }

  public reclaimStaleUploads(input: StaleUploadReclaimInput): Promise<readonly ReclaimUploadRow[]> {
    safeEpochMs(input.uploadHorizonEpochMs, "upload_horizon_ms");
    const limit = safeLimit(input.limit);
    return transaction(this.#pool, async (client) => {
      const recovered = await client.query<ReclaimUploadSqlRow>(
        `SELECT prepared_blob_id, staging_path, blob_path
         FROM reversal_prepared
         WHERE state = 'upload_reclaim_marked'
         FOR UPDATE SKIP LOCKED
         LIMIT $1`,
        [limit],
      );
      const remaining = limit - recovered.rows.length;
      const fresh = remaining === 0
        ? { rows: [] as ReclaimUploadSqlRow[] }
        : await client.query<ReclaimUploadSqlRow>(
          `UPDATE reversal_prepared
           SET state = 'upload_reclaim_marked'
           WHERE prepared_blob_id IN (
             SELECT prepared_blob_id
             FROM reversal_prepared
             WHERE state = 'uploading' AND created_at_ms < $1
             FOR UPDATE SKIP LOCKED
             LIMIT $2
           )
           RETURNING prepared_blob_id, staging_path, blob_path`,
          [input.uploadHorizonEpochMs, remaining],
        );
      return [...recovered.rows, ...fresh.rows].map((row) => ({
        preparedBlobId: preparedHandle(row.prepared_blob_id),
        stagingPath: row.staging_path,
        blobPath: row.blob_path,
      }));
    });
  }

  public markStaleUploads(input: StaleUploadReclaimInput): Promise<readonly ReclaimUploadRow[]> {
    safeEpochMs(input.uploadHorizonEpochMs, "upload_horizon_ms");
    const limit = safeLimit(input.limit);
    return transaction(this.#pool, async (client) => {
      const result = await client.query<ReclaimUploadSqlRow>(
        `UPDATE reversal_prepared
         SET state = 'upload_reclaim_marked'
         WHERE prepared_blob_id IN (
           SELECT prepared_blob_id
           FROM reversal_prepared
           WHERE state = 'uploading' AND created_at_ms < $1
           FOR UPDATE SKIP LOCKED
           LIMIT $2
         )
         RETURNING prepared_blob_id, staging_path, blob_path`,
        [input.uploadHorizonEpochMs, limit],
      );
      return result.rows.map((row) => this.#reclaimUpload(row));
    });
  }

  public recoverStaleUploads(input: ReclaimLimitInput): Promise<readonly ReclaimUploadRow[]> {
    const limit = safeLimit(input.limit);
    return transaction(this.#pool, async (client) => {
      const result = await client.query<ReclaimUploadSqlRow>(
        `SELECT prepared_blob_id, staging_path, blob_path
         FROM reversal_prepared
         WHERE state = 'upload_reclaim_marked'
         FOR UPDATE SKIP LOCKED
         LIMIT $1`,
        [limit],
      );
      return result.rows.map((row) => this.#reclaimUpload(row));
    });
  }

  public completeStaleUploadReclaim(preparedBlobId: PreparedWriteHandle): Promise<void> {
    return this.#deleteInState(preparedBlobId, "upload_reclaim_marked", "complete_stale_upload_invalid_state");
  }

  public hardDeleteQuarantined(input: ReclaimQueryInput): Promise<readonly ReclaimBlobRow[]> {
    safeEpochMs(input.olderThanEpochMs, "older_than_ms");
    const limit = safeLimit(input.limit);
    return transaction(this.#pool, async (client) => {
      const result = await client.query<ReclaimBlobSqlRow>(
        `SELECT prepared_blob_id, blob_path
         FROM reversal_prepared
         WHERE state = 'quarantined' AND quarantined_at_ms < $1
         FOR UPDATE SKIP LOCKED
         LIMIT $2`,
        [input.olderThanEpochMs, limit],
      );
      return result.rows.map((row) => this.#reclaimBlob(row));
    });
  }

  public completeHardDeleteQuarantined(preparedBlobId: PreparedWriteHandle): Promise<void> {
    return this.#deleteInState(preparedBlobId, "quarantined", "complete_hard_delete_invalid_state");
  }

  public previewReclamation(input: ReclaimPreviewInput): Promise<ReclaimPreviewOutcome> {
    safeEpochMs(input.olderThanEpochMs, "older_than_ms");
    safeEpochMs(input.uploadHorizonEpochMs, "upload_horizon_ms");
    safeEpochMs(input.quarantinedBeforeEpochMs, "quarantined_before_ms");
    const limit = safeLimit(input.limit);
    return transaction(this.#pool, async (client) => {
      await client.query("SET TRANSACTION READ ONLY");
      let remaining = limit;
      let scanned = 0;
      let reclaimed = 0;
      const skippedReferenced = await this.#countReferencedPathOneCandidates(
        client,
        input.olderThanEpochMs,
        remaining,
      );

      const pathOne = await client.query<ReclaimCandidateSqlRow>(
        `SELECT p.prepared_blob_id, p.blob_path, p.state
         FROM reversal_prepared p
         WHERE (
              p.state = 'reclaim_marked'
              OR (p.state IN ('finalized', 'orphaned') AND p.created_at_ms < $1)
            )
           AND NOT EXISTS (
             SELECT 1 FROM reversal_claim c WHERE c.prepared_blob_id = p.prepared_blob_id
           )
           AND NOT EXISTS (
             SELECT 1 FROM reversal_current c WHERE c.prepared_blob_id = p.prepared_blob_id
           )
         ORDER BY CASE WHEN p.state = 'reclaim_marked' THEN 0 ELSE 1 END,
                  p.created_at_ms,
                  p.prepared_blob_id
         LIMIT $2`,
        [input.olderThanEpochMs, remaining],
      );
      scanned += pathOne.rows.length + skippedReferenced;
      reclaimed += pathOne.rows.length;
      remaining -= pathOne.rows.length;

      if (remaining > 0) {
        const uploadRecovery = await client.query<ReclaimIdSqlRow>(
          `SELECT prepared_blob_id
           FROM reversal_prepared
           WHERE state = 'upload_reclaim_marked'
           ORDER BY created_at_ms, prepared_blob_id
           LIMIT $1`,
          [remaining],
        );
        scanned += uploadRecovery.rows.length;
        reclaimed += uploadRecovery.rows.length;
        remaining -= uploadRecovery.rows.length;
      }

      if (remaining > 0) {
        const staleUploads = await client.query<ReclaimIdSqlRow>(
          `SELECT prepared_blob_id
           FROM reversal_prepared
           WHERE state = 'uploading' AND created_at_ms < $1
           ORDER BY created_at_ms, prepared_blob_id
           LIMIT $2`,
          [input.uploadHorizonEpochMs, remaining],
        );
        scanned += staleUploads.rows.length;
        reclaimed += staleUploads.rows.length;
        remaining -= staleUploads.rows.length;
      }

      if (input.includeHardDelete && remaining > 0) {
        const quarantined = await client.query<ReclaimIdSqlRow>(
          `SELECT prepared_blob_id
           FROM reversal_prepared
           WHERE state = 'quarantined' AND quarantined_at_ms < $1
           ORDER BY quarantined_at_ms, prepared_blob_id
           LIMIT $2`,
          [input.quarantinedBeforeEpochMs, remaining],
        );
        scanned += quarantined.rows.length;
        reclaimed += quarantined.rows.length;
      }

      return { scanned, reclaimed, skippedReferenced };
    });
  }

  async #countReferencedPathOneCandidates(
    client: PoolClient,
    olderThanEpochMs: number,
    limit: number,
  ): Promise<number> {
    // Count a LIMITed, identically ordered subquery rather than LEAST(COUNT(*), limit):
    // this bounds candidate inspection as well as the observable skippedReferenced metric.
    const result = await client.query<ReclaimCountSqlRow>(
      `SELECT COUNT(*)::int AS count
       FROM (
         SELECT p.prepared_blob_id
         FROM reversal_prepared p
         WHERE (
              p.state = 'reclaim_marked'
              OR (p.state IN ('finalized', 'orphaned') AND p.created_at_ms < $1)
            )
           AND (
             EXISTS (
               SELECT 1 FROM reversal_claim c WHERE c.prepared_blob_id = p.prepared_blob_id
             )
             OR EXISTS (
               SELECT 1 FROM reversal_current c WHERE c.prepared_blob_id = p.prepared_blob_id
             )
           )
         ORDER BY CASE WHEN p.state = 'reclaim_marked' THEN 0 ELSE 1 END,
                  p.created_at_ms,
                  p.prepared_blob_id
         LIMIT $2
       ) referenced_candidates`,
      [olderThanEpochMs, limit],
    );
    const count = result.rows[0]?.count;
    if (!Number.isSafeInteger(count) || count === undefined || count < 0 || count > limit) {
      throw new Error("reclaim_referenced_candidate_count_invalid");
    }
    return count;
  }

  async #computeExpiredAndDetach(client: PoolClient, claim: ClaimRow): Promise<boolean> {
    if (claim.state === "expired") {
      return true;
    }
    if (claim.is_expired === undefined) {
      throw new Error("claim_missing_expiry_comparison");
    }
    const expired = claim.is_expired;
    if (claim.state === "pending" && expired) {
      await this.#expireLockedPending(client, claim);
    }
    return expired;
  }

  async #expireLockedPending(client: PoolClient, claim: ClaimRow): Promise<void> {
    if (claim.state !== "pending" || claim.prepared_blob_id === null) {
      throw new Error("expire_non_pending_claim");
    }
    const prepared = await client.query<PreparedBlobRow>(
      `SELECT prepared_blob_id, state, blob_etag, blob_len
       FROM reversal_prepared
       WHERE prepared_blob_id = $1
       FOR UPDATE`,
      [claim.prepared_blob_id],
    );
    if (prepared.rows[0]?.state !== "committed") {
      throw new Error("expire_missing_committed_prepared");
    }
    const references = await client.query<ReferenceRow>(
      `SELECT
         EXISTS (
           SELECT 1 FROM reversal_current WHERE prepared_blob_id = $1
         ) AS has_current,
         EXISTS (
           SELECT 1 FROM reversal_claim
           WHERE prepared_blob_id = $1 AND idempotency_key <> $2
         ) AS has_other_claim`,
      [claim.prepared_blob_id, claim.idempotency_key],
    );
    const reference = references.rows[0];
    if (reference === undefined || reference.has_current || reference.has_other_claim) {
      throw new Error("expire_pending_prepared_is_referenced");
    }
    const expired = await client.query(
      `UPDATE reversal_claim
       SET state = 'expired', prepared_blob_id = NULL
       WHERE commit_handle = $1 AND state = 'pending' AND prepared_blob_id = $2`,
      [claim.commit_handle, claim.prepared_blob_id],
    );
    const orphaned = await client.query(
      `UPDATE reversal_prepared
       SET state = 'orphaned'
       WHERE prepared_blob_id = $1 AND state = 'committed'`,
      [claim.prepared_blob_id],
    );
    if (expired.rowCount !== 1 || orphaned.rowCount !== 1) {
      throw new Error("expire_pending_transition_lost");
    }
  }

  async #deleteInState(preparedBlobId: PreparedWriteHandle, state: string, error: string): Promise<void> {
    return transaction(this.#pool, async (client) => {
      const deleted = await client.query(
        `DELETE FROM reversal_prepared
         WHERE prepared_blob_id = $1 AND state = $2`,
        [preparedBlobId, state],
      );
      if (deleted.rowCount === 1) {
        return;
      }
      const present = await client.query(
        `SELECT 1 FROM reversal_prepared WHERE prepared_blob_id = $1`,
        [preparedBlobId],
      );
      if (present.rowCount !== 0) {
        throw new Error(error);
      }
    });
  }

  #dekGeneration(row: DekRow): DekGeneration {
    return {
      dekGenerationId: decodeTextKey(row.dek_generation_id) as unknown as DekGenerationId,
      wrappedDek: new Uint8Array(row.wrapped_dek) as unknown as WrappedDekMaterial,
    };
  }

  #reclaimBlob(row: ReclaimBlobSqlRow): ReclaimBlobRow {
    return { preparedBlobId: preparedHandle(row.prepared_blob_id), blobPath: row.blob_path };
  }

  #reclaimUpload(row: ReclaimUploadSqlRow): ReclaimUploadRow {
    return {
      preparedBlobId: preparedHandle(row.prepared_blob_id),
      stagingPath: row.staging_path,
      blobPath: row.blob_path,
    };
  }
}
