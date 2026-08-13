import { createHash, randomBytes, randomUUID } from "node:crypto";
import { Pool } from "pg";
import type {
  DictionaryVersion,
  MatterId,
  OperationAttemptId,
  SubstitutionToken,
  TenantId,
} from "../src/core/brands";
import type { ReversalRecordInput } from "../src/core/contracts";
import { AzureFilesBlobStore } from "../src/tokens/durable/azure/azure-files-blob-store";
import { AzureFilesSpoolVolume } from "../src/tokens/durable/azure/azure-files-spool-volume";
import { AzureSpoolMaintenance } from "../src/tokens/durable/azure/azure-spool-maintenance";
import { PostgresControlPlane, runMigrations } from "../src/tokens/durable/azure/postgres-control-plane";
import {
  azureFilesBlobStoreFromEnvironment,
  postgresConfigFromEnvironment,
} from "../src/tokens/durable/azure/runtime-config";
import { InMemoryKeyProvider } from "../src/tokens/durable/dev/in-memory-key-provider";
import { DurableReversalStore } from "../src/tokens/durable/durable-reversal-store";
import { idempotencyKeyOf, mappingKeyOf, scopeDigestOf } from "../src/tokens/durable/keys";
import type {
  DekGenerationId,
  EncryptedReversalRecordBlob,
  GcmNonce96,
  PrepareReversalWriteInput,
  PreparedWriteHandle,
  ReversalIdempotencyKey,
  ReversalMappingKey,
  ReversalScopeDigest,
  SpoolVolume,
  WrappedDekMaterial,
  WrappingKeyId,
  WrappingKeyVersion,
} from "../src/tokens/durable/ports";

const brand = <T>(value: unknown): T => value as unknown as T;
const FIXED_NOW = 1_900_000_000_000;

interface SmokeContext {
  readonly pool: Pool;
  readonly blobStore: AzureFilesBlobStore;
  readonly tenantId: TenantId;
  readonly concurrency: number;
}

function assertSmoke(condition: unknown, detail: string): asserts condition {
  if (!condition) throw new Error(detail);
}

function concurrencyFromEnvironment(): number {
  const value = Number(process.env.SMOKE_CONCURRENCY ?? "8");
  if (!Number.isSafeInteger(value) || value < 2 || value > 128) {
    throw new Error("invalid_SMOKE_CONCURRENCY");
  }
  return value;
}

function runIdentity(): { readonly schema: string; readonly tenantId: TenantId } {
  const supplied = process.env.SMOKE_RUN_ID;
  const raw = supplied === undefined || supplied.length === 0 ? randomUUID() : supplied;
  const digest = createHash("sha256").update(raw, "utf8").digest("hex").slice(0, 24);
  return {
    schema: `q6_smoke_${digest}`,
    tenantId: brand<TenantId>(`q6-${digest}`),
  };
}

function nonceValue(nonce: Uint8Array): bigint {
  const bytes = Buffer.from(nonce);
  return (bytes.readBigUInt64BE(0) << 32n) | BigInt(bytes.readUInt32BE(8));
}

function directBlob(input: {
  readonly tenantId: TenantId;
  readonly matterId: MatterId;
  readonly token: SubstitutionToken;
  readonly attemptId: OperationAttemptId;
  readonly createdAtEpochMs: number;
  readonly expiresAtEpochMs: bigint;
  readonly marker: number;
}): EncryptedReversalRecordBlob {
  return {
    ciphertext: Uint8Array.of(input.marker),
    authTag: new Uint8Array(16),
    nonce: brand<GcmNonce96>(new Uint8Array(12)),
    wrappedDek: brand<WrappedDekMaterial>(new Uint8Array(32)),
    dekGenerationId: brand<DekGenerationId>(`direct-generation-${input.marker}`),
    wrappingKeyId: brand<WrappingKeyId>("direct-key"),
    wrappingKeyVersion: brand<WrappingKeyVersion>("v1"),
    aad: Uint8Array.of(input.marker, 7, 8),
    meta: {
      tenantId: input.tenantId,
      matterId: input.matterId,
      dictionaryVersion: brand<DictionaryVersion>(1n),
      token: input.token,
      attemptId: input.attemptId,
      retentionClass: "detector-only",
      createdAtEpochMs: input.createdAtEpochMs,
      expiresAtEpochMs: input.expiresAtEpochMs,
    },
  };
}

function directPrepareInput(
  blob: EncryptedReversalRecordBlob,
): PrepareReversalWriteInput {
  return {
    idempotencyKey: idempotencyKeyOf(blob.meta.tenantId, blob.meta.attemptId, blob.meta.token),
    mappingKey: mappingKeyOf(blob.meta.tenantId, blob.meta.matterId, blob.meta.dictionaryVersion, blob.meta.token),
    immutableScopeDigest: scopeDigestOf(blob.meta.tenantId, blob.meta.matterId, blob.meta.dictionaryVersion),
    encryptedRecord: blob,
  };
}

async function concurrencyCheck(context: SmokeContext): Promise<Record<string, number>> {
  const matterId = brand<MatterId>(`${context.tenantId}-concurrency`);
  const token = brand<SubstitutionToken>("[[Claimant]]");
  const attemptId = brand<OperationAttemptId>(`${context.tenantId}-concurrency-attempt`);
  const input = directPrepareInput(directBlob({
    tenantId: context.tenantId,
    matterId,
    token,
    attemptId,
    createdAtEpochMs: FIXED_NOW,
    expiresAtEpochMs: BigInt(FIXED_NOW + 86_400_000),
    marker: 1,
  }));
  const volumes = Array.from({ length: context.concurrency }, () => new AzureFilesSpoolVolume(
    new PostgresControlPlane(context.pool),
    context.blobStore,
    () => FIXED_NOW,
  ));
  const prepared = await Promise.all(volumes.map((volume) => volume.prepare(input)));
  const results = await Promise.all(prepared.map((item, index) => volumes[index]!.publish(item)));
  const published = results.filter((result) => result.kind === "published");
  const existing = results.filter((result) => result.kind === "existing");
  assertSmoke(published.length === 1, "concurrency_expected_one_published");
  assertSmoke(existing.length === context.concurrency - 1, "concurrency_expected_existing_losers");
  const winner = published[0];
  assertSmoke(winner?.kind === "published", "concurrency_missing_winner");
  assertSmoke(existing.every((result) => result.commit === winner.commit), "concurrency_commit_diverged");
  await volumes[0]!.flush(winner.commit);

  const claims = await context.pool.query<{ readonly count: string }>(
    `SELECT COUNT(*)::text AS count FROM reversal_claim WHERE tenant_id = $1`,
    [context.tenantId],
  );
  const currents = await context.pool.query<{ readonly count: string }>(
    `SELECT COUNT(*)::text AS count FROM reversal_current WHERE tenant_id = $1`,
    [context.tenantId],
  );
  const rows = await context.pool.query<{
    readonly state: string;
    readonly blob_etag: string | null;
    readonly blob_len: string | null;
    readonly staging_path: string;
    readonly blob_path: string;
  }>(
    `SELECT state, blob_etag, blob_len, staging_path, blob_path
     FROM reversal_prepared WHERE tenant_id = $1`,
    [context.tenantId],
  );
  assertSmoke(claims.rows[0]?.count === "1", "concurrency_claim_count");
  assertSmoke(currents.rows[0]?.count === "1", "concurrency_current_count");
  assertSmoke(rows.rows.length === context.concurrency, "concurrency_prepared_count");
  assertSmoke(rows.rows.filter((row) => row.state === "committed").length === 1, "concurrency_committed_count");
  assertSmoke(
    rows.rows.filter((row) => row.state === "finalized").length === context.concurrency - 1,
    "concurrency_finalized_loser_count",
  );
  for (const row of rows.rows) {
    assertSmoke(row.blob_etag !== null && row.blob_len !== null, "concurrency_partial_attributes");
    assertSmoke(await context.blobStore.head(row.staging_path) === undefined, "concurrency_staging_remained");
    assertSmoke(await context.blobStore.head(row.blob_path) !== undefined, "concurrency_blob_missing");
  }
  return { publishers: context.concurrency, published: 1, existing: existing.length, current: 1 };
}

function abandoningFlush(spool: SpoolVolume): SpoolVolume {
  return {
    ensureDekGeneration: (input) => spool.ensureDekGeneration(input),
    reserveNonce: (input) => spool.reserveNonce(input),
    prepare: (input) => spool.prepare(input),
    publish: (prepared) => spool.publish(prepared),
    flush: () => Promise.reject(new Error("simulated_replica_death_before_flush")),
    readCurrent: (requests) => spool.readCurrent(requests),
  };
}

function durableStore(
  spoolVolume: SpoolVolume,
  kek: Uint8Array,
): DurableReversalStore {
  return new DurableReversalStore({
    keyProvider: new InMemoryKeyProvider({ kek, keyId: "q6-smoke-kek", keyVersion: "v1" }),
    spoolVolume,
    classifyRetention: async () => "matter",
    nowEpochMilliseconds: () => FIXED_NOW,
    maximumEncounteredTokenBatch: 32,
  });
}

async function crashRecoveryCheck(context: SmokeContext): Promise<Record<string, number>> {
  const matterId = brand<MatterId>(`${context.tenantId}-recovery`);
  const token = brand<SubstitutionToken>("[[Witness]]");
  const attemptId = brand<OperationAttemptId>(`${context.tenantId}-recovery-attempt`);
  const record: ReversalRecordInput = {
    tenantId: context.tenantId,
    matterId,
    dictionaryVersion: brand<DictionaryVersion>(1n),
    token,
    canonical: "Q6 Recovery Canonical",
    attemptId,
  };
  const kek = randomBytes(32);
  const firstVolume = new AzureFilesSpoolVolume(
    new PostgresControlPlane(context.pool),
    context.blobStore,
    () => FIXED_NOW,
  );
  let abandoned = false;
  try {
    await durableStore(abandoningFlush(firstVolume), kek).record(record);
  } catch {
    abandoned = true;
  }
  assertSmoke(abandoned, "recovery_first_replica_was_not_abandoned");

  const freshControlPlane = new PostgresControlPlane(context.pool);
  const freshStore = durableStore(
    new AzureFilesSpoolVolume(freshControlPlane, context.blobStore, () => FIXED_NOW),
    kek,
  );
  await freshStore.record(record);
  const resolved = await freshStore.resolveEncounteredTokens({
    tenantId: context.tenantId,
    matterId,
    dictionaryVersion: record.dictionaryVersion,
    tokens: [token],
  });
  assertSmoke(resolved.get(token) === record.canonical, "recovery_acked_record_not_resolvable");
  const pointers = await freshControlPlane.readCurrentPointers([
    mappingKeyOf(context.tenantId, matterId, record.dictionaryVersion, token),
  ]);
  assertSmoke(pointers.length === 1, "recovery_pointer_count");
  return { abandonedReplicas: 1, recoveredRecords: 1, resolvedRecords: 1 };
}

async function noPinnedPartialsCheck(context: SmokeContext): Promise<Record<string, number>> {
  const controlPlane = new PostgresControlPlane(context.pool);
  const partialHandle = brand<PreparedWriteHandle>(randomUUID());
  const partialStaging = `staging/${partialHandle as unknown as string}`;
  const partialBlob = `blobs/${partialHandle as unknown as string}`;
  const partialMapping = brand<ReversalMappingKey>(`${context.tenantId}\0partial-mapping`);
  await controlPlane.insertPreparedUploading({
    preparedBlobId: partialHandle,
    tenantId: context.tenantId,
    mappingKey: partialMapping,
    idempotencyKey: brand<ReversalIdempotencyKey>(`${context.tenantId}\0partial-idempotency`),
    immutableScopeDigest: brand<ReversalScopeDigest>("partial-scope"),
    stagingPath: partialStaging,
    blobPath: partialBlob,
    createdAtEpochMs: FIXED_NOW - 1_000,
  });
  await context.blobStore.putStaging(partialStaging, Uint8Array.of(1, 2, 3));
  const maintenance = new AzureSpoolMaintenance({
    controlPlane,
    blobStore: context.blobStore,
    uploadHorizonMs: 1,
    graceMs: 86_400_000,
    now: () => FIXED_NOW,
    includeHardDelete: false,
  });
  await maintenance.reclaimOrphanedPrepared({ olderThanEpochMs: 0, limit: 100 });
  assertSmoke(await context.blobStore.head(partialStaging) === undefined, "partial_staging_pinned");
  assertSmoke(await context.blobStore.head(partialBlob) === undefined, "partial_blob_pinned");
  assertSmoke((await context.pool.query(
    `SELECT 1 FROM reversal_prepared WHERE prepared_blob_id = $1`,
    [partialHandle],
  )).rowCount === 0, "partial_row_pinned");
  assertSmoke((await controlPlane.readCurrentPointers([partialMapping])).length === 0, "partial_became_readable");

  const matterId = brand<MatterId>(`${context.tenantId}-expired`);
  const token = brand<SubstitutionToken>("[[Adjuster]]");
  const attemptId = brand<OperationAttemptId>(`${context.tenantId}-expired-attempt`);
  const expiredInput = directPrepareInput(directBlob({
    tenantId: context.tenantId,
    matterId,
    token,
    attemptId,
    createdAtEpochMs: FIXED_NOW - 2_000,
    expiresAtEpochMs: BigInt(FIXED_NOW - 1),
    marker: 9,
  }));
  const volume = new AzureFilesSpoolVolume(controlPlane, context.blobStore, () => FIXED_NOW);
  const prepared = await volume.prepare(expiredInput);
  const published = await volume.publish(prepared);
  assertSmoke(published.kind === "published", "expired_expected_publication");
  const expired = await controlPlane.expirePendingDetach({
    commit: published.commit,
    nowEpochMilliseconds: FIXED_NOW,
  });
  assertSmoke(expired, "expired_claim_not_tombstoned");
  await maintenance.reclaimOrphanedPrepared({ olderThanEpochMs: FIXED_NOW - 1_000, limit: 100 });
  const state = await context.pool.query<{
    readonly state: string;
  }>(`SELECT state FROM reversal_prepared WHERE prepared_blob_id = $1`, [prepared.handle]);
  const claim = await context.pool.query<{
    readonly state: string;
    readonly prepared_blob_id: string | null;
  }>(`SELECT state, prepared_blob_id FROM reversal_claim WHERE commit_handle = $1`, [published.commit]);
  const quarantinePath = `reclaim-quarantine/${prepared.handle as unknown as string}`;
  assertSmoke(state.rows[0]?.state === "quarantined", "expired_blob_not_reclaimable");
  assertSmoke(
    claim.rows[0]?.state === "expired" && claim.rows[0].prepared_blob_id === null,
    "expired_tombstone_still_pinned",
  );
  assertSmoke(await context.blobStore.head(`blobs/${prepared.handle as unknown as string}`) === undefined, "expired_original_remained");
  assertSmoke(await context.blobStore.head(quarantinePath) !== undefined, "expired_quarantine_missing");
  assertSmoke((await controlPlane.readCurrentPointers([expiredInput.mappingKey])).length === 0, "expired_became_readable");
  return { abandonedUploadsReclaimed: 1, expiredTombstonesDetached: 1, orphanedBlobsQuarantined: 1 };
}

async function nonceMonotonicityCheck(context: SmokeContext): Promise<Record<string, number>> {
  const matterId = brand<MatterId>(`${context.tenantId}-nonce`);
  const request = {
    tenantId: context.tenantId,
    matterId,
    dekGenerationId: brand<DekGenerationId>(`${context.tenantId}\0nonce-generation`),
  };
  const firstMount = new PostgresControlPlane(context.pool);
  const secondMount = new PostgresControlPlane(context.pool);
  const values = [
    nonceValue(await firstMount.reserveNonce(request)),
    nonceValue(await firstMount.reserveNonce(request)),
    nonceValue(await secondMount.reserveNonce(request)),
    nonceValue(await secondMount.reserveNonce(request)),
  ];
  assertSmoke(values.every((value, index) => index === 0 || value > values[index - 1]!), "nonce_not_strictly_increasing");
  assertSmoke(new Set(values).size === values.length, "nonce_repeated_after_remount");
  return { reservations: values.length, distinct: new Set(values).size };
}

async function cleanupBlobs(pool: Pool, blobStore: AzureFilesBlobStore): Promise<void> {
  const prepared = await pool.query<{
    readonly prepared_blob_id: string;
    readonly staging_path: string;
    readonly blob_path: string;
  }>(`SELECT prepared_blob_id::text, staging_path, blob_path FROM reversal_prepared`);
  const paths = new Set<string>();
  for (const row of prepared.rows) {
    paths.add(row.staging_path);
    paths.add(row.blob_path);
    paths.add(`reclaim-quarantine/${row.prepared_blob_id}`);
  }
  await Promise.all([...paths].map(async (path) => blobStore.remove(path).catch(() => undefined)));
}

function failureDetail(error: unknown): string {
  const message = error instanceof Error ? error.message : "unknown_failure";
  return JSON.stringify({ error: message.replace(/[\r\n]+/g, " ").slice(0, 300) });
}

async function main(): Promise<void> {
  const identity = runIdentity();
  let basePool: Pool | undefined;
  let scopedPool: Pool | undefined;
  let blobStore: AzureFilesBlobStore | undefined;
  let passed = true;
  try {
    const baseConfig = postgresConfigFromEnvironment();
    basePool = new Pool(baseConfig);
    await basePool.query(`CREATE SCHEMA IF NOT EXISTS "${identity.schema}"`);
    scopedPool = new Pool({ ...baseConfig, options: `-c search_path=${identity.schema}` });
    blobStore = azureFilesBlobStoreFromEnvironment();
    await runMigrations(scopedPool);
    await cleanupBlobs(scopedPool, blobStore);
    await scopedPool.query(
      `TRUNCATE TABLE
         reversal_current, reversal_claim, reversal_ordinal_seq, reversal_prepared,
         reversal_nonce_counter, reversal_dek_generation CASCADE`,
    );
    const context: SmokeContext = {
      pool: scopedPool,
      blobStore,
      tenantId: identity.tenantId,
      concurrency: concurrencyFromEnvironment(),
    };
    const checks: ReadonlyArray<readonly [string, () => Promise<Record<string, number>>]> = [
      ["CONCURRENCY", () => concurrencyCheck(context)],
      ["CRASH_RECOVERY", () => crashRecoveryCheck(context)],
      ["NO_PINNED_PARTIALS", () => noPinnedPartialsCheck(context)],
      ["NONCE_MONOTONICITY", () => nonceMonotonicityCheck(context)],
    ];
    for (const [name, check] of checks) {
      try {
        console.log(`SMOKE ${name} PASS ${JSON.stringify(await check())}`);
      } catch (error: unknown) {
        passed = false;
        console.log(`SMOKE ${name} FAIL ${failureDetail(error)}`);
      }
    }
  } catch (error: unknown) {
    passed = false;
    console.log(`SMOKE SETUP FAIL ${failureDetail(error)}`);
  }

  console.log(`Q6_SMOKE_RESULT ${passed ? "PASS" : "FAIL"}`);
  process.exitCode = passed ? 0 : 1;

  if (scopedPool !== undefined && blobStore !== undefined) {
    await cleanupBlobs(scopedPool, blobStore).catch(() => undefined);
  }
  await scopedPool?.end().catch(() => undefined);
  await basePool?.query(`DROP SCHEMA IF EXISTS "${identity.schema}" CASCADE`).catch(() => undefined);
  await basePool?.end().catch(() => undefined);
}

void main();
