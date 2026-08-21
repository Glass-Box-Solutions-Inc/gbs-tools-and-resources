import { randomUUID } from "node:crypto";
import { Pool, type PoolConfig } from "pg";
import {
  afterAll,
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
} from "vitest";
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
import type {
  BlobProperties,
  BlobStore,
} from "../src/tokens/durable/azure/blob-store";
import type {
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
} from "../src/tokens/durable/azure/control-plane";
import {
  PostgresControlPlane,
  runMigrations,
} from "../src/tokens/durable/azure/postgres-control-plane";
import {
  decodeReversalBlob,
  encodeReversalBlob,
} from "../src/tokens/durable/azure/reversal-blob-codec";
import { InMemoryControlPlane } from "../src/tokens/durable/dev/in-memory-control-plane";
import { InMemoryKeyProvider } from "../src/tokens/durable/dev/in-memory-key-provider";
import { ReversalFailedError } from "../src/tokens/index";
import { DurableReversalStore } from "../src/tokens/durable/durable-reversal-store";
import { mappingKeyOf } from "../src/tokens/durable/keys";
import type {
  DekGeneration,
  DekGenerationId,
  EncryptedReversalRecordBlob,
  GcmNonce96,
  PrepareReversalWriteInput,
  PreparedWriteHandle,
  PublishReversalResult,
  PublishedCommitHandle,
  ReversalIdempotencyKey,
  ReversalMappingKey,
  ReversalScopeDigest,
  SpoolVolume,
  WrappedDekMaterial,
  WrappingKeyId,
  WrappingKeyVersion,
} from "../src/tokens/durable/ports";

const T0 = 1_700_000_000_000;
const DETECTOR_TTL_MS = 86_400_000;
const MATTER_EXPIRES_AT = 2n ** 64n - 1n;
const brand = <T>(value: unknown): T => value as unknown as T;

function blobFixture(): EncryptedReversalRecordBlob {
  return {
    ciphertext: Uint8Array.of(0, 1, 2, 0xfe, 0xff),
    authTag: Uint8Array.from({ length: 16 }, (_, index) => index + 10),
    nonce: brand<GcmNonce96>(
      Uint8Array.from({ length: 12 }, (_, index) => 255 - index),
    ),
    wrappedDek: brand<WrappedDekMaterial>(Uint8Array.of(7, 0, 8, 9, 255)),
    dekGenerationId: brand<DekGenerationId>("generation-λ\0one"),
    wrappingKeyId: brand<WrappingKeyId>("https://vault.example/keys/kék"),
    wrappingKeyVersion: brand<WrappingKeyVersion>("version-一"),
    aad: Uint8Array.of(0, 99, 0, 100, 255),
    meta: {
      tenantId: brand<TenantId>("tenant-å"),
      matterId: brand<MatterId>("matter-東京"),
      dictionaryVersion: brand<DictionaryVersion>(4_294_967_297n),
      token: brand<SubstitutionToken>("[[Claimant_😀]]"),
      attemptId: brand<OperationAttemptId>("attempt\0unicode-é"),
      retentionClass: "matter",
      createdAtEpochMs: T0,
      expiresAtEpochMs: MATTER_EXPIRES_AT,
    },
  };
}

class MemoryBlobStore implements BlobStore {
  readonly #objects = new Map<string, Uint8Array>();
  readonly #etags = new Map<string, string>();
  #nextEtag = 0;

  public putStaging(path: string, bytes: Uint8Array): Promise<void> {
    this.#objects.set(path, Uint8Array.from(bytes));
    this.#etags.set(path, `etag-${(this.#nextEtag += 1)}`);
    return Promise.resolve();
  }

  public finalize(
    stagingPath: string,
    blobPath: string,
  ): Promise<BlobProperties> {
    const bytes = this.#objects.get(stagingPath);
    if (bytes === undefined || this.#objects.has(blobPath))
      throw new Error("fake_finalize_failed");
    this.#objects.delete(stagingPath);
    this.#etags.delete(stagingPath);
    this.#objects.set(blobPath, bytes);
    const etag = `etag-${(this.#nextEtag += 1)}`;
    this.#etags.set(blobPath, etag);
    return Promise.resolve({ etag, len: bytes.byteLength });
  }

  public head(path: string): Promise<BlobProperties | undefined> {
    const bytes = this.#objects.get(path);
    const etag = this.#etags.get(path);
    return Promise.resolve(
      bytes === undefined || etag === undefined
        ? undefined
        : { etag, len: bytes.byteLength },
    );
  }

  public get(path: string): Promise<Uint8Array | undefined> {
    const bytes = this.#objects.get(path);
    return Promise.resolve(
      bytes === undefined ? undefined : Uint8Array.from(bytes),
    );
  }

  public rename(fromPath: string, toPath: string): Promise<void> {
    const bytes = this.#objects.get(fromPath);
    const etag = this.#etags.get(fromPath);
    if (bytes === undefined || etag === undefined || this.#objects.has(toPath))
      throw new Error("fake_rename_failed");
    this.#objects.delete(fromPath);
    this.#etags.delete(fromPath);
    this.#objects.set(toPath, bytes);
    this.#etags.set(toPath, etag);
    return Promise.resolve();
  }

  public remove(path: string): Promise<void> {
    this.#objects.delete(path);
    this.#etags.delete(path);
    return Promise.resolve();
  }
}

class FailingPutBlobStore extends MemoryBlobStore {
  public override putStaging(): Promise<void> {
    return Promise.reject(new Error("simulated_staging_write_failure"));
  }
}

interface FakePrepared {
  readonly input: InsertPreparedUploadingInput;
  state: "uploading" | "finalized" | "committed";
  etag?: string;
  len?: bigint;
}

interface FakeClaim {
  readonly commit: PublishedCommitHandle;
  readonly prepared: FakePrepared;
  readonly expires: bigint;
  state: "pending" | "flushed";
}

class MemoryControlPlane implements ControlPlane {
  readonly #prepared = new Map<string, FakePrepared>();
  readonly #claimsByCommit = new Map<string, FakeClaim>();
  readonly #claimsByIdempotency = new Map<string, FakeClaim>();
  readonly #current = new Map<string, CurrentPointerRow>();
  #dek: DekGeneration | undefined;
  #nonce = 0n;

  public async ensureDekGeneration(
    input: Parameters<ControlPlane["ensureDekGeneration"]>[0],
  ): Promise<DekGeneration> {
    this.#dek ??= await input.mint();
    return this.#dek;
  }

  public reserveNonce(): Promise<GcmNonce96> {
    const value = this.#nonce;
    this.#nonce += 1n;
    const nonce = Buffer.alloc(12);
    nonce.writeBigUInt64BE(value >> 32n, 0);
    nonce.writeUInt32BE(Number(value & 0xffff_ffffn), 8);
    return Promise.resolve(brand<GcmNonce96>(nonce));
  }

  public insertPreparedUploading(
    input: InsertPreparedUploadingInput,
  ): Promise<void> {
    this.#prepared.set(input.preparedBlobId as unknown as string, {
      input,
      state: "uploading",
    });
    return Promise.resolve();
  }

  public markFinalized(input: MarkFinalizedInput): Promise<void> {
    const row = this.#prepared.get(input.preparedBlobId as unknown as string);
    if (row === undefined || row.state !== "uploading")
      throw new Error("fake_finalize_lost");
    row.state = "finalized";
    row.etag = input.blobEtag;
    row.len = input.blobLength;
    return Promise.resolve();
  }

  public publish(input: PublishPreparedInput): Promise<PublishReversalResult> {
    const row = this.#prepared.get(input.prepared.handle as unknown as string);
    if (row === undefined || row.state !== "finalized")
      return Promise.reject(new Error("fake_publish_failed"));
    const idempotency = row.input.idempotencyKey as unknown as string;
    const existing = this.#claimsByIdempotency.get(idempotency);
    if (existing !== undefined) {
      return Promise.resolve({
        kind: "existing",
        commit: existing.commit,
        immutableScopeDigest: existing.prepared.input.immutableScopeDigest,
        expired: BigInt(input.nowEpochMilliseconds) >= existing.expires,
      });
    }
    const commit = brand<PublishedCommitHandle>(randomUUID());
    const claim: FakeClaim = {
      commit,
      prepared: row,
      expires: input.expiresAtEpochMs,
      state: "pending",
    };
    row.state = "committed";
    this.#claimsByCommit.set(commit as unknown as string, claim);
    this.#claimsByIdempotency.set(idempotency, claim);
    return Promise.resolve({ kind: "published", commit });
  }

  public readClaimBlobReference(
    commit: PublishedCommitHandle,
  ): Promise<ClaimBlobReference> {
    const claim = this.#claimsByCommit.get(commit as unknown as string);
    if (claim === undefined)
      return Promise.reject(new Error("fake_unknown_commit"));
    if (claim.prepared.etag === undefined || claim.prepared.len === undefined) {
      return Promise.reject(new Error("fake_missing_blob_attributes"));
    }
    return Promise.resolve({
      kind: "blob",
      blobPath: claim.prepared.input.blobPath,
      blobEtag: claim.prepared.etag,
      blobLength: claim.prepared.len,
    });
  }

  public flushClaim(input: FlushClaimInput): Promise<void> {
    const claim = this.#claimsByCommit.get(input.commit as unknown as string);
    if (
      claim === undefined ||
      claim.prepared.etag !== input.blobEtag ||
      claim.prepared.len !== input.blobLength
    )
      return Promise.reject(new Error("fake_flush_integrity"));
    claim.state = "flushed";
    const prepared = claim.prepared;
    this.#current.set(prepared.input.mappingKey as unknown as string, {
      mappingKey: prepared.input.mappingKey,
      tenantId: prepared.input.tenantId,
      commit: claim.commit,
      preparedBlobId: prepared.input.preparedBlobId,
      ordinal: 0n,
      flushedAtEpochMs: input.nowEpochMilliseconds,
      blobPath: prepared.input.blobPath,
      blobEtag: prepared.etag!,
      blobLength: prepared.len!,
    });
    return Promise.resolve();
  }

  public expirePendingDetach(
    _input: ExpirePendingDetachInput,
  ): Promise<boolean> {
    return Promise.resolve(false);
  }

  public readCurrentPointers(
    keys: readonly ReversalMappingKey[],
  ): Promise<readonly CurrentPointerRow[]> {
    return Promise.resolve(
      keys.flatMap((key) => {
        const row = this.#current.get(key as unknown as string);
        return row === undefined ? [] : [row];
      }),
    );
  }

  public reclaimFinalizedOrphans(
    _input: ReclaimQueryInput,
  ): Promise<readonly ReclaimBlobRow[]> {
    return Promise.resolve([]);
  }
  public selectFinalizedOrphansForReclaim(
    _input: ReclaimQueryInput,
  ): Promise<ReclaimFinalizedOrphansSelection> {
    return Promise.resolve({ rows: [], skippedReferenced: 0 });
  }
  public markQuarantined(_input: MarkQuarantinedInput): Promise<void> {
    return Promise.resolve();
  }
  public reclaimStaleUploads(
    _input: StaleUploadReclaimInput,
  ): Promise<readonly ReclaimUploadRow[]> {
    return Promise.resolve([]);
  }
  public markStaleUploads(
    _input: StaleUploadReclaimInput,
  ): Promise<readonly ReclaimUploadRow[]> {
    return Promise.resolve([]);
  }
  public recoverStaleUploads(
    _input: ReclaimLimitInput,
  ): Promise<readonly ReclaimUploadRow[]> {
    return Promise.resolve([]);
  }
  public completeStaleUploadReclaim(
    _preparedBlobId: PreparedWriteHandle,
  ): Promise<void> {
    return Promise.resolve();
  }
  public hardDeleteQuarantined(
    _input: ReclaimQueryInput,
  ): Promise<readonly ReclaimBlobRow[]> {
    return Promise.resolve([]);
  }
  public completeHardDeleteQuarantined(
    _preparedBlobId: PreparedWriteHandle,
  ): Promise<void> {
    return Promise.resolve();
  }
  public previewReclamation(
    _input: ReclaimPreviewInput,
  ): Promise<ReclaimPreviewOutcome> {
    return Promise.resolve({ scanned: 0, reclaimed: 0, skippedReferenced: 0 });
  }
}

describe("reversal blob codec", () => {
  it("round-trips every byte/string field and the exact MaxUint64 matter expiry", () => {
    const original = blobFixture();
    const encoded = encodeReversalBlob(original);
    const decoded = decodeReversalBlob(encoded);

    expect(decoded).toEqual(original);
    expect(decoded.meta.expiresAtEpochMs).toBe(2n ** 64n - 1n);
    expect(decoded.meta.dictionaryVersion).toBe(4_294_967_297n);
    expect(decoded.ciphertext).not.toBe(original.ciphertext);
    expect(decoded.aad).not.toBe(original.aad);
  });
});

describe("AzureFilesSpoolVolume unit", () => {
  it("uses plane time for adapter-prepared Path-1 and crash-left Path-2a rows", async () => {
    const oneHundredHours = 100 * 60 * 60 * 1_000;
    const uploadHorizon = 48 * 60 * 60 * 1_000;
    const controlPlane = new InMemoryControlPlane({
      nowEpochMilliseconds: () => T0,
    });
    const input = (suffix: string): PrepareReversalWriteInput => {
      const encryptedRecord = blobFixture();
      return {
        idempotencyKey: brand<ReversalIdempotencyKey>(`idempotency-${suffix}`),
        mappingKey: brand<ReversalMappingKey>(`mapping-${suffix}`),
        immutableScopeDigest: brand<ReversalScopeDigest>(`scope-${suffix}`),
        encryptedRecord: {
          ...encryptedRecord,
          meta: {
            ...encryptedRecord.meta,
            createdAtEpochMs: T0 - oneHundredHours,
          },
        },
      };
    };

    const interrupted = new AzureFilesSpoolVolume(
      controlPlane,
      new FailingPutBlobStore(),
      () => T0,
    );
    await expect(interrupted.prepare(input("uploading"))).rejects.toThrow(
      "simulated_staging_write_failure",
    );
    const uploadingHandle = controlPlane.debugPreparedHandles()[0];
    expect(uploadingHandle).toBeDefined();
    if (uploadingHandle === undefined)
      throw new Error("expected uploading row");

    const completed = new AzureFilesSpoolVolume(
      controlPlane,
      new MemoryBlobStore(),
      () => T0,
    );
    const finalized = await completed.prepare(input("finalized"));
    const threshold = T0 - uploadHorizon;

    await expect(
      controlPlane.markStaleUploads({
        uploadHorizonEpochMs: threshold,
        limit: 10,
      }),
    ).resolves.toEqual([]);
    await expect(
      controlPlane.selectFinalizedOrphansForReclaim({
        olderThanEpochMs: threshold,
        limit: 10,
      }),
    ).resolves.toEqual({ rows: [], skippedReferenced: 0 });
    expect(controlPlane.debugPrepared(uploadingHandle)).toMatchObject({
      state: "uploading",
      createdAtMs: T0,
    });
    expect(controlPlane.debugPrepared(finalized.handle)).toMatchObject({
      state: "finalized",
      createdAtMs: T0,
    });
  });

  it("prepares, publishes, flushes, and reads the exact encrypted record", async () => {
    const controlPlane = new MemoryControlPlane();
    const blobs = new MemoryBlobStore();
    const volume = new AzureFilesSpoolVolume(controlPlane, blobs, () => T0);
    const record = blobFixture();
    const mappingKey = brand<ReversalMappingKey>(
      "tenant\u0000matter\u00001\u0000[[Claimant]]",
    );
    const input: PrepareReversalWriteInput = {
      idempotencyKey: brand<ReversalIdempotencyKey>(
        "tenant\0attempt\0[[Claimant]]",
      ),
      mappingKey,
      immutableScopeDigest: brand<ReversalScopeDigest>("scope"),
      encryptedRecord: record,
    };

    const prepared = await volume.prepare(input);
    const published = await volume.publish(prepared);
    expect(published.kind).toBe("published");
    if (published.kind !== "published") throw new Error("expected_publish");
    await volume.flush(published.commit);

    await expect(volume.readCurrent([])).rejects.toThrow("requires_exact_keys");
    await expect(volume.readCurrent([{ mappingKey }])).resolves.toEqual([
      { mappingKey, encryptedRecord: record },
    ]);
  });

  it("fails closed when a durable pointer's immutable blob is absent", async () => {
    const controlPlane = new MemoryControlPlane();
    const blobs = new MemoryBlobStore();
    const volume = new AzureFilesSpoolVolume(controlPlane, blobs, () => T0);
    const mappingKey = brand<ReversalMappingKey>(
      "tenant\u0000matter\u00001\u0000[[Missing]]",
    );
    const prepared = await volume.prepare({
      idempotencyKey: brand<ReversalIdempotencyKey>(
        "tenant\0attempt\0[[Missing]]",
      ),
      mappingKey,
      immutableScopeDigest: brand<ReversalScopeDigest>("scope"),
      encryptedRecord: blobFixture(),
    });
    const published = await volume.publish(prepared);
    if (published.kind !== "published") throw new Error("expected_publish");
    await volume.flush(published.commit);
    await blobs.remove(`blobs/${prepared.handle as unknown as string}`);

    await expect(volume.readCurrent([{ mappingKey }])).rejects.toThrow(
      "integrity",
    );
  });

  it("reads a snapshotted old pointer through original-to-quarantine fallback during grace", async () => {
    const controlPlane = new MemoryControlPlane();
    const blobs = new MemoryBlobStore();
    const volume = new AzureFilesSpoolVolume(controlPlane, blobs, () => T0);
    const mappingKey = brand<ReversalMappingKey>(
      "tenant\u0000matter\u00001\u0000[[OldPointer]]",
    );
    const record = blobFixture();
    const prepared = await volume.prepare({
      idempotencyKey: brand<ReversalIdempotencyKey>(
        "tenant\0attempt-old\0[[OldPointer]]",
      ),
      mappingKey,
      immutableScopeDigest: brand<ReversalScopeDigest>("scope-old-pointer"),
      encryptedRecord: record,
    });
    const published = await volume.publish(prepared);
    if (published.kind !== "published") throw new Error("expected_publish");
    await volume.flush(published.commit);

    const original = `blobs/${prepared.handle as unknown as string}`;
    const quarantine = `reclaim-quarantine/${prepared.handle as unknown as string}`;
    await blobs.rename(original, quarantine);
    const quarantinedBytes = await blobs.get(quarantine);
    if (quarantinedBytes === undefined)
      throw new Error("expected quarantine bytes");
    // Azure Files may assign a destination ETag during rename; fallback authenticates the immutable
    // envelope after enforcing the durable length rather than assuming ETag preservation.
    await blobs.putStaging(quarantine, quarantinedBytes);
    await expect(volume.readCurrent([{ mappingKey }])).resolves.toEqual([
      { mappingKey, encryptedRecord: record },
    ]);

    await blobs.remove(quarantine);
    await expect(volume.readCurrent([{ mappingKey }])).rejects.toThrow(
      "integrity",
    );
  });
});

const LIVE =
  !!process.env.PHI_REVERSAL_PG_TEST && !!process.env.PHI_SPOOL_ACCOUNT;

function pgConfig(): PoolConfig {
  const port =
    process.env.PGPORT === undefined ? 5432 : Number(process.env.PGPORT);
  if (!Number.isInteger(port) || port <= 0) throw new Error("invalid_PGPORT");
  return {
    host: process.env.PGHOST,
    user: process.env.PGUSER,
    password: process.env.PGPASSWORD,
    database: process.env.PGDATABASE,
    port,
    ...(process.env.PGSSLMODE === "require"
      ? { ssl: { rejectUnauthorized: false } }
      : {}),
  };
}

function requiredEnv(
  name: "PHI_SPOOL_ACCOUNT" | "PHI_SPOOL_KEY" | "PHI_SPOOL_SHARE",
): string {
  const value = process.env[name];
  if (value === undefined || value.length === 0)
    throw new Error(`missing_${name}`);
  return value;
}

function failFlush(spool: SpoolVolume): SpoolVolume {
  return {
    ensureDekGeneration: (input) => spool.ensureDekGeneration(input),
    reserveNonce: (input) => spool.reserveNonce(input),
    prepare: (input) => spool.prepare(input),
    publish: (prepared) => spool.publish(prepared),
    flush: () => Promise.reject(new Error("simulated_publish_response_loss")),
    readCurrent: (requests) => spool.readCurrent(requests),
  };
}

describe.skipIf(!LIVE)("AzureFilesSpoolVolume live", () => {
  const schema = `phi_spool_b2_${process.pid}_${Date.now()}`;
  let adminPool: Pool;
  let pool: Pool;
  let controlPlane: PostgresControlPlane;
  let blobs: AzureFilesBlobStore;
  let keyProvider: InMemoryKeyProvider;
  let now = T0;

  const makeStore = (
    spool: SpoolVolume,
    retention: "matter" | "detector-only",
  ) =>
    new DurableReversalStore({
      keyProvider,
      spoolVolume: spool,
      classifyRetention: async () => retention,
      nowEpochMilliseconds: () => now,
      maximumEncounteredTokenBatch: 32,
    });

  const makeInput = (suffix: string): ReversalRecordInput => ({
    tenantId: brand<TenantId>(`tenant-${suffix}-${randomUUID()}`),
    matterId: brand<MatterId>(`matter-${suffix}-${randomUUID()}`),
    dictionaryVersion: brand<DictionaryVersion>(1n),
    token: brand<SubstitutionToken>(`[[Claimant_${randomUUID()}]]`),
    canonical: `María García ${suffix}`,
    attemptId: brand<OperationAttemptId>(`attempt-${randomUUID()}`),
  });

  beforeAll(async () => {
    adminPool = new Pool(pgConfig());
    await adminPool.query(`CREATE SCHEMA "${schema}"`);
    pool = new Pool({ ...pgConfig(), options: `-c search_path=${schema}` });
    await runMigrations(pool);
    controlPlane = new PostgresControlPlane(pool);
    blobs = new AzureFilesBlobStore(
      requiredEnv("PHI_SPOOL_ACCOUNT"),
      requiredEnv("PHI_SPOOL_KEY"),
      requiredEnv("PHI_SPOOL_SHARE"),
    );
  }, 120_000);

  beforeEach(async () => {
    now = T0;
    keyProvider = new InMemoryKeyProvider();
    await pool.query(
      `TRUNCATE TABLE reversal_current, reversal_claim, reversal_ordinal_seq, reversal_prepared,
       reversal_operation_retention, reversal_nonce_counter, reversal_dek_generation CASCADE`,
    );
  });

  afterEach(async () => {
    const paths = await pool.query<{
      readonly staging_path: string;
      readonly blob_path: string;
    }>(`SELECT staging_path, blob_path FROM reversal_prepared`);
    await Promise.all(
      paths.rows.flatMap((row) => [
        blobs.remove(row.staging_path),
        blobs.remove(row.blob_path),
        blobs.remove(
          `reclaim-quarantine/${row.blob_path.slice(row.blob_path.indexOf("/") + 1)}`,
        ),
      ]),
    );
  }, 120_000);

  afterAll(async () => {
    await pool?.end();
    if (adminPool !== undefined) {
      await adminPool.query(`DROP SCHEMA IF EXISTS "${schema}" CASCADE`);
      await adminPool.end();
    }
  }, 120_000);

  it("round-trips record through the frozen DurableReversalStore", async () => {
    const input = makeInput("roundtrip");
    const spool = new AzureFilesSpoolVolume(controlPlane, blobs, () => now);
    const store = makeStore(spool, "matter");
    await store.record(input);

    const resolved = await store.resolveEncounteredTokens({
      tenantId: input.tenantId,
      matterId: input.matterId,
      dictionaryVersion: input.dictionaryVersion,
      tokens: [input.token],
    });
    expect(resolved.get(input.token)).toBe(input.canonical);
  }, 120_000);

  it("recovers a durable pending publication from a fresh store instance", async () => {
    const input = makeInput("recovery");
    const firstSpool = new AzureFilesSpoolVolume(
      controlPlane,
      blobs,
      () => now,
    );
    await expect(
      makeStore(failFlush(firstSpool), "matter").record(input),
    ).rejects.toBeInstanceOf(ReversalFailedError);

    const freshStore = makeStore(
      new AzureFilesSpoolVolume(
        new PostgresControlPlane(pool),
        blobs,
        () => now,
      ),
      "matter",
    );
    await freshStore.record(input);
    const resolved = await freshStore.resolveEncounteredTokens({
      tenantId: input.tenantId,
      matterId: input.matterId,
      dictionaryVersion: input.dictionaryVersion,
      tokens: [input.token],
    });
    expect(resolved.get(input.token)).toBe(input.canonical);
  }, 120_000);

  it("tombstones an expired detector publication that was lost before flush", async () => {
    const input = makeInput("expired-pending");
    const firstSpool = new AzureFilesSpoolVolume(
      controlPlane,
      blobs,
      () => now,
    );
    await expect(
      makeStore(failFlush(firstSpool), "detector-only").record(input),
    ).rejects.toBeInstanceOf(ReversalFailedError);
    now += DETECTOR_TTL_MS;

    const freshStore = makeStore(
      new AzureFilesSpoolVolume(
        new PostgresControlPlane(pool),
        blobs,
        () => now,
      ),
      "detector-only",
    );
    await expect(freshStore.record(input)).rejects.toBeInstanceOf(
      ReversalFailedError,
    );
    const claim = await pool.query<{
      readonly state: string;
      readonly prepared_blob_id: string | null;
    }>(`SELECT state, prepared_blob_id FROM reversal_claim`);
    expect(claim.rows).toEqual([{ state: "expired", prepared_blob_id: null }]);
    const prepared = await pool.query<{ readonly state: string }>(
      `SELECT state FROM reversal_prepared ORDER BY created_at_ms, prepared_blob_id`,
    );
    expect(prepared.rows.some((row) => row.state === "orphaned")).toBe(true);
  }, 120_000);

  it("fails readCurrent integrity when the pointed Azure Files blob is removed", async () => {
    const input = makeInput("integrity");
    const store = makeStore(
      new AzureFilesSpoolVolume(controlPlane, blobs, () => now),
      "matter",
    );
    await store.record(input);
    const mappingKey = mappingKeyOf(
      input.tenantId,
      input.matterId,
      input.dictionaryVersion,
      input.token,
    );
    const pointer = (await controlPlane.readCurrentPointers([mappingKey]))[0];
    if (pointer === undefined) throw new Error("missing_live_pointer");
    await blobs.remove(pointer.blobPath);

    await expect(
      store.resolveEncounteredTokens({
        tenantId: input.tenantId,
        matterId: input.matterId,
        dictionaryVersion: input.dictionaryVersion,
        tokens: [input.token],
      }),
    ).rejects.toBeInstanceOf(ReversalFailedError);
  }, 120_000);

  it("preserves a snapshotted old pointer across supersession, rename crash, and fresh-job recovery", async () => {
    const oldInput = makeInput("old-pointer-fallback");
    const freshInput: ReversalRecordInput = {
      ...oldInput,
      canonical: `${oldInput.canonical} newer`,
      attemptId: brand<OperationAttemptId>(`attempt-new-${randomUUID()}`),
    };
    const firstVolume = new AzureFilesSpoolVolume(
      controlPlane,
      blobs,
      () => now,
    );
    await makeStore(firstVolume, "matter").record(oldInput);
    const mappingKey = mappingKeyOf(
      oldInput.tenantId,
      oldInput.matterId,
      oldInput.dictionaryVersion,
      oldInput.token,
    );
    const snapshotted = await controlPlane.readCurrentPointers([mappingKey]);
    expect(snapshotted).toHaveLength(1);
    const oldPointer = snapshotted[0]!;

    await makeStore(
      new AzureFilesSpoolVolume(
        new PostgresControlPlane(pool),
        blobs,
        () => now,
      ),
      "matter",
    ).record(freshInput);
    await pool.query(
      `UPDATE reversal_prepared SET superseded_at_ms = 0
       WHERE prepared_blob_id = $1 AND state = 'superseded'`,
      [oldPointer.preparedBlobId],
    );
    const freshPlane = new PostgresControlPlane(pool);
    const selected = await freshPlane.selectFinalizedOrphansForReclaim({
      olderThanEpochMs: 0,
      limit: 1,
      supersedeRetentionMs: 100,
      readDrainMs: 0,
    });
    expect(selected.rows.map((row) => row.preparedBlobId)).toEqual([
      oldPointer.preparedBlobId,
    ]);
    const quarantine = `reclaim-quarantine/${oldPointer.preparedBlobId as unknown as string}`;
    await blobs.rename(oldPointer.blobPath, quarantine); // simulated process death before DB update

    const pinnedPlane = new Proxy(freshPlane, {
      get(target, property, receiver) {
        if (property === "readCurrentPointers")
          return () => Promise.resolve([oldPointer]);
        const value = Reflect.get(target, property, receiver) as unknown;
        return typeof value === "function" ? value.bind(target) : value;
      },
    }) as ControlPlane;
    const staleRead = await new AzureFilesSpoolVolume(
      pinnedPlane,
      blobs,
      () => now,
    ).readCurrent([{ mappingKey }]);
    expect(staleRead[0]?.encryptedRecord.meta.attemptId).toBe(
      oldInput.attemptId,
    );
    const currentRead = await new AzureFilesSpoolVolume(
      freshPlane,
      blobs,
      () => now,
    ).readCurrent([{ mappingKey }]);
    expect(currentRead[0]?.encryptedRecord.meta.attemptId).toBe(
      freshInput.attemptId,
    );

    const recovery = await new AzureSpoolMaintenance({
      controlPlane: freshPlane,
      blobStore: blobs,
      uploadHorizonMs: 86_400_000,
      graceMs: 100,
      supersedeRetentionMs: 100,
      readDrainMs: 0,
      now: Date.now,
      includeHardDelete: false,
    }).reclaimOrphanedPrepared({ olderThanEpochMs: 0, limit: 1 });
    expect(recovery.reclaimed).toBe(1);
    const state = await pool.query<{ readonly state: string }>(
      `SELECT state FROM reversal_prepared WHERE prepared_blob_id = $1`,
      [oldPointer.preparedBlobId],
    );
    expect(state.rows).toEqual([{ state: "quarantined" }]);
    expect(await blobs.head(quarantine)).toBeDefined();
  }, 120_000);
});
