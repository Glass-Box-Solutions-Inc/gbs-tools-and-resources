/**
 * Development reference model for the GLY-346 transactional control plane plus immutable blob plane.
 * All maps are durable substrate state. `crash()` deliberately drops nothing: pending claims survive
 * replica loss and are completed (or expired and detached) by a later retry.
 */
import { createHash } from "node:crypto";
import {
  DEFAULT_RECLAIM_LIMIT_CAP,
  scrubReclaimOrphanedPreparedInput,
  type ReclaimOrphanedPreparedInput,
  type ReclaimOutcome,
  type SpoolMaintenance,
} from "../maintenance";
import type {
  ClaimBlobReference,
  ControlPlane as AzureControlPlane,
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
} from "../azure/control-plane";
import type {
  DekGeneration,
  EncryptedReversalRecordBlob,
  EnsureDekGenerationInput,
  GcmNonce96,
  NonceReservationInput,
  PrepareReversalWriteInput,
  PreparedReversalWrite,
  PreparedWriteHandle,
  PublishReversalResult,
  PublishedCommitHandle,
  ReversalIdempotencyKey,
  ReversalLookupRequest,
  ReversalLookupResult,
  ReversalMappingKey,
  ReversalScopeDigest,
  SpoolVolume,
} from "../ports";

export type PreparedControlPlaneState =
  | "uploading"
  | "finalized"
  | "committed"
  | "superseded"
  | "orphaned"
  | "upload_reclaim_marked"
  | "reclaim_marked"
  | "quarantined";

export type ClaimControlPlaneState = "pending" | "flushed" | "expired" | "superseded";

export type InMemoryControlPlaneFaultPhase =
  | "prepareAfterUploadingInsert"
  | "prepareAfterStagingUpload"
  | "prepareAfterBlobRename"
  | "anchorAfterBindingInsert"
  | "anchorAfterPreparedInsert"
  | "flushAfterLockVerify"
  | "flushAfterNewClaim"
  | "flushAfterPointerCas"
  | "flushAfterOldClaim"
  | "flushAfterOldPrepared"
  | "flushAfterLoserClaim"
  | "flushAfterLoserPrepared"
  | "selfHealAfterLockVerify"
  | "selfHealAfterCte"
  | "reclaimAfterPathOneMark"
  | "reclaimAfterUploadMark"
  | "reclaimAfterStagingDelete"
  | "reclaimAfterBlobDelete";

export interface InMemoryControlPlaneFaults {
  failAt?: InMemoryControlPlaneFaultPhase;
}

export interface InMemoryControlPlaneOptions {
  readonly nowEpochMilliseconds?: () => number;
  /** Stale uploads receive a deliberately longer horizon than ordinary finalized orphans. */
  readonly uploadHorizonMilliseconds?: number;
  readonly quarantineGraceMilliseconds?: number;
  readonly supersedeRetentionMilliseconds?: number;
  readonly readDrainMilliseconds?: number;
  readonly maintenanceLimitCap?: number;
  readonly faults?: InMemoryControlPlaneFaults;
}

interface BlobArtifact {
  readonly encryptedRecord: EncryptedReversalRecordBlob;
  readonly etag: string;
  readonly length: bigint;
}

interface PreparedRow {
  readonly preparedBlobId: PreparedWriteHandle;
  readonly tenant: string;
  readonly mappingKey: ReversalMappingKey;
  readonly idempotencyKey: ReversalIdempotencyKey;
  readonly scopeDigest: ReversalScopeDigest;
  readonly createdAtMs: number;
  readonly operationKey: string | null;
  readonly recordCreatedAtMs: number | null;
  retentionClass: "matter" | "detector-only" | null;
  readonly retentionOrigin: "anchored" | "backfilled" | null;
  retentionExpiresAtMs: bigint | null;
  supersededAtMs?: number;
  reclaimAfterMs?: bigint;
  readonly stagingPath: string;
  readonly blobPath: string;
  state: PreparedControlPlaneState;
  stagingBlob?: BlobArtifact;
  blob?: BlobArtifact;
  quarantineBlob?: BlobArtifact;
  blobEtag?: string;
  blobLen?: bigint;
  quarantinedAtMs?: number;
}

interface ClaimRow {
  readonly idempotencyKey: ReversalIdempotencyKey;
  readonly tenant: string;
  readonly mappingKey: ReversalMappingKey;
  readonly scopeDigest: ReversalScopeDigest;
  readonly commitHandle: PublishedCommitHandle;
  preparedBlobId: PreparedWriteHandle | null;
  readonly ordinal: bigint;
  readonly createdAtMs: number;
  readonly expiresAtMs: bigint;
  state: ClaimControlPlaneState;
}

interface CurrentRow {
  readonly mappingKey: ReversalMappingKey;
  readonly commitHandle: PublishedCommitHandle;
  readonly preparedBlobId: PreparedWriteHandle;
  readonly ordinal: bigint;
  readonly flushedAtMs: number;
}

export interface PreparedControlPlaneSnapshot {
  readonly preparedBlobId: PreparedWriteHandle;
  readonly tenant: string;
  readonly mappingKey: ReversalMappingKey;
  readonly idempotencyKey: ReversalIdempotencyKey;
  readonly scopeDigest: ReversalScopeDigest;
  readonly createdAtMs: number;
  readonly operationKey: string | null;
  readonly recordCreatedAtMs: number | null;
  readonly retentionClass: "matter" | "detector-only" | null;
  readonly retentionOrigin: "anchored" | "backfilled" | null;
  readonly retentionExpiresAtMs: bigint | null;
  readonly supersededAtMs: number | undefined;
  readonly reclaimAfterMs: bigint | undefined;
  readonly stagingPath: string;
  readonly blobPath: string;
  readonly state: PreparedControlPlaneState;
  readonly blobEtag: string | undefined;
  readonly blobLen: bigint | undefined;
  readonly quarantinedAtMs: number | undefined;
  readonly stagingBlobPresent: boolean;
  readonly blobPresent: boolean;
  readonly quarantineBlobPresent: boolean;
}

export interface ClaimControlPlaneSnapshot {
  readonly idempotencyKey: ReversalIdempotencyKey;
  readonly mappingKey: ReversalMappingKey;
  readonly scopeDigest: ReversalScopeDigest;
  readonly commitHandle: PublishedCommitHandle;
  readonly preparedBlobId: PreparedWriteHandle | null;
  readonly ordinal: bigint;
  readonly createdAtMs: number;
  readonly expiresAtMs: bigint;
  readonly state: ClaimControlPlaneState;
}

export interface CurrentControlPlaneSnapshot {
  readonly mappingKey: ReversalMappingKey;
  readonly commitHandle: PublishedCommitHandle;
  readonly preparedBlobId: PreparedWriteHandle;
  readonly ordinal: bigint;
  readonly flushedAtMs: number;
}

const DEFAULT_UPLOAD_HORIZON_MS = 48 * 60 * 60 * 1_000;
const DEFAULT_QUARANTINE_GRACE_MS = 24 * 60 * 60 * 1_000;
const DEFAULT_SUPERSEDE_RETENTION_MS = 30 * 24 * 60 * 60 * 1_000;
const DEFAULT_READ_DRAIN_MS = 60_000;
const MAX_NONCE_COUNTER = 2n ** 96n - 1n;

function asString(value: string): string {
  return value as unknown as string;
}

function cloneBytes<T extends Uint8Array>(value: T): T {
  return Uint8Array.from(value) as T;
}

function cloneRecord(record: EncryptedReversalRecordBlob): EncryptedReversalRecordBlob {
  return {
    ...record,
    ciphertext: cloneBytes(record.ciphertext),
    authTag: cloneBytes(record.authTag),
    nonce: cloneBytes(record.nonce),
    wrappedDek: cloneBytes(record.wrappedDek),
    aad: cloneBytes(record.aad),
    meta: { ...record.meta },
  };
}

function artifactFor(recordInput: EncryptedReversalRecordBlob): BlobArtifact {
  const record = cloneRecord(recordInput);
  const hash = createHash("sha256");
  let length = 0n;
  const addBytes = (bytes: Uint8Array): void => {
    hash.update(bytes);
    length += BigInt(bytes.byteLength);
  };
  const addText = (text: string): void => {
    const bytes = Buffer.from(text, "utf8");
    addBytes(bytes);
  };
  addBytes(record.ciphertext);
  addBytes(record.authTag);
  addBytes(record.nonce);
  addBytes(record.wrappedDek);
  addBytes(record.aad);
  addText(asString(record.dekGenerationId));
  addText(asString(record.wrappingKeyId));
  addText(asString(record.wrappingKeyVersion));
  addText(asString(record.meta.tenantId));
  addText(asString(record.meta.matterId));
  addText(record.meta.dictionaryVersion.toString());
  addText(asString(record.meta.token));
  addText(asString(record.meta.attemptId));
  addText(record.meta.retentionClass);
  addText(record.meta.createdAtEpochMs.toString());
  addText(record.meta.expiresAtEpochMs.toString());
  return { encryptedRecord: record, etag: hash.digest("hex"), length };
}

/** Big-endian 96-bit nonce from the durable per-(tenant, DEK generation) counter. */
function nonce96(counter: bigint): GcmNonce96 {
  const buffer = Buffer.alloc(12);
  buffer.writeBigUInt64BE(counter >> 32n, 0);
  buffer.writeUInt32BE(Number(counter & 0xffff_ffffn), 8);
  return new Uint8Array(buffer) as unknown as GcmNonce96;
}

function checkedDuration(value: number, label: string): number {
  if (!Number.isSafeInteger(value) || value < 0) {
    throw new Error(`invalid_${label}`);
  }
  return value;
}

function checkedLimit(value: number): number {
  if (!Number.isSafeInteger(value) || value <= 0) {
    throw new Error("invalid_maintenance_limit");
  }
  return value;
}

/** In-memory implementation of both the frozen request-path port and least-authority maintenance port. */
export class InMemoryControlPlane implements SpoolVolume, SpoolMaintenance, AzureControlPlane {
  readonly #nowEpochMilliseconds: () => number;
  readonly #uploadHorizonMilliseconds: number;
  readonly #quarantineGraceMilliseconds: number;
  readonly #supersedeRetentionMilliseconds: number;
  readonly #readDrainMilliseconds: number;
  readonly #maintenanceLimitCap: number;
  readonly #dekGenerations = new Map<string, DekGeneration>();
  readonly #nonceNext = new Map<string, bigint>();
  readonly #prepared = new Map<string, PreparedRow>();
  readonly #operationRetention = new Map<string, "matter" | "detector-only">();
  readonly #claims = new Map<string, ClaimRow>();
  readonly #claimsByCommit = new Map<string, ClaimRow>();
  readonly #current = new Map<string, CurrentRow>();
  readonly #ordinalNext = new Map<string, bigint>();
  #idSequence = 0n;

  /** Mutable only to let conformance tests inject and then clear crash points. */
  public readonly faults: InMemoryControlPlaneFaults;

  public constructor(options: InMemoryControlPlaneOptions = {}) {
    this.#nowEpochMilliseconds = options.nowEpochMilliseconds ?? Date.now;
    this.#uploadHorizonMilliseconds = checkedDuration(
      options.uploadHorizonMilliseconds ?? DEFAULT_UPLOAD_HORIZON_MS,
      "upload_horizon",
    );
    this.#quarantineGraceMilliseconds = checkedDuration(
      options.quarantineGraceMilliseconds ?? DEFAULT_QUARANTINE_GRACE_MS,
      "quarantine_grace",
    );
    this.#supersedeRetentionMilliseconds = checkedDuration(
      options.supersedeRetentionMilliseconds ?? DEFAULT_SUPERSEDE_RETENTION_MS,
      "supersede_retention",
    );
    this.#readDrainMilliseconds = checkedDuration(
      options.readDrainMilliseconds ?? DEFAULT_READ_DRAIN_MS,
      "read_drain",
    );
    if (
      this.#supersedeRetentionMilliseconds < this.#quarantineGraceMilliseconds ||
      this.#quarantineGraceMilliseconds < this.#readDrainMilliseconds
    ) {
      throw new Error("invalid_retention_window_order");
    }
    this.#maintenanceLimitCap = checkedDuration(
      options.maintenanceLimitCap ?? DEFAULT_RECLAIM_LIMIT_CAP,
      "maintenance_limit_cap",
    );
    if (this.#maintenanceLimitCap === 0) {
      throw new Error("invalid_maintenance_limit_cap");
    }
    this.faults = options.faults ?? {};
  }

  #fault(phase: InMemoryControlPlaneFaultPhase): void {
    if (this.faults.failAt === phase) {
      throw new Error(`control_plane_fault_${phase}`);
    }
  }

  #nextUuidLike(): string {
    this.#idSequence += 1n;
    const tail = this.#idSequence.toString(16).padStart(12, "0");
    if (tail.length > 12) {
      throw new Error("control_plane_id_exhausted");
    }
    return `00000000-0000-4000-8000-${tail}`;
  }

  #nextPreparedHandle(): PreparedWriteHandle {
    return this.#nextUuidLike() as unknown as PreparedWriteHandle;
  }

  #nextCommitHandle(): PublishedCommitHandle {
    return this.#nextUuidLike() as unknown as PublishedCommitHandle;
  }

  public async ensureDekGeneration(input: EnsureDekGenerationInput): Promise<DekGeneration> {
    const scopeKey = `${input.scope.tenantId}\0${input.scope.matterId}\0${input.scope.purpose}`;
    const existing = this.#dekGenerations.get(scopeKey);
    if (existing !== undefined) {
      return existing;
    }
    const minted = await input.mint();
    const raced = this.#dekGenerations.get(scopeKey);
    if (raced !== undefined) {
      return raced;
    }
    this.#dekGenerations.set(scopeKey, minted);
    return minted;
  }

  public reserveNonce(input: NonceReservationInput): Promise<GcmNonce96> {
    const counterKey = `${input.tenantId}\0${input.dekGenerationId}`;
    const reservation = this.#nonceNext.get(counterKey) ?? 0n;
    if (reservation > MAX_NONCE_COUNTER) {
      return Promise.reject(new Error("nonce_counter_exhausted"));
    }
    // Advance durable state before returning. A lost response burns a value; it never permits reuse.
    this.#nonceNext.set(counterKey, reservation + 1n);
    return Promise.resolve(nonce96(reservation));
  }

  #retentionMetadata(input: {
    readonly tenantId: string;
    readonly attemptId: string;
    readonly retentionClass: "matter" | "detector-only";
    readonly createdAtEpochMs: number;
    readonly expiresAtEpochMs: bigint;
  }): { readonly operationKey: string; readonly recordCreatedAtMs: number } {
    const recordCreatedAtMs = checkedDuration(input.createdAtEpochMs, "record_created_at_ms");
    if (input.attemptId.length === 0) throw new Error("invalid_attempt_id");
    if (input.expiresAtEpochMs < 0n || input.expiresAtEpochMs > 2n ** 64n - 1n) {
      throw new Error("invalid_retention_expiry");
    }
    if (
      input.retentionClass === "detector-only" &&
      input.expiresAtEpochMs !== BigInt(recordCreatedAtMs) + 86_400_000n
    ) {
      throw new Error("invalid_detector_expiry");
    }
    if (input.retentionClass === "matter" && input.expiresAtEpochMs !== 2n ** 64n - 1n) {
      throw new Error("invalid_matter_expiry");
    }
    return { operationKey: `${input.tenantId}\0${input.attemptId}`, recordCreatedAtMs };
  }

  #anchorPrepared(row: PreparedRow): void {
    const operationKey = row.operationKey;
    if (operationKey === null || row.retentionClass === null) {
      throw new Error("anchor_retention_metadata_missing");
    }
    const existing = this.#operationRetention.get(operationKey);
    if (existing !== undefined && existing !== row.retentionClass) {
      throw new Error("insert_prepared_retention_binding_mismatch");
    }
    const insertedBinding = existing === undefined;
    if (insertedBinding) this.#operationRetention.set(operationKey, row.retentionClass);
    try {
      this.#fault("anchorAfterBindingInsert");
      const key = asString(row.preparedBlobId);
      if (this.#prepared.has(key)) throw new Error("insert_prepared_duplicate_handle");
      this.#prepared.set(key, row);
      this.#fault("anchorAfterPreparedInsert");
    } catch (error: unknown) {
      this.#prepared.delete(asString(row.preparedBlobId));
      if (insertedBinding) this.#operationRetention.delete(operationKey);
      throw error;
    }
  }

  public insertPreparedUploading(input: InsertPreparedUploadingInput): Promise<void> {
    const retention = this.#retentionMetadata({
      tenantId: asString(input.tenantId),
      attemptId: asString(input.attemptId),
      retentionClass: input.retentionClass,
      createdAtEpochMs: input.createdAtEpochMs,
      expiresAtEpochMs: input.expiresAtEpochMs,
    });
    const createdAtMs = checkedDuration(this.#nowEpochMilliseconds(), "created_at_ms");
    const row: PreparedRow = {
      preparedBlobId: input.preparedBlobId,
      tenant: asString(input.tenantId),
      mappingKey: input.mappingKey,
      idempotencyKey: input.idempotencyKey,
      scopeDigest: input.immutableScopeDigest,
      createdAtMs,
      operationKey: retention.operationKey,
      recordCreatedAtMs: retention.recordCreatedAtMs,
      retentionClass: input.retentionClass,
      retentionOrigin: "anchored",
      retentionExpiresAtMs: input.expiresAtEpochMs,
      stagingPath: input.stagingPath,
      blobPath: input.blobPath,
      state: "uploading",
    };
    this.#anchorPrepared(row);
    return Promise.resolve();
  }

  public markFinalized(input: MarkFinalizedInput): Promise<void> {
    if (input.blobEtag.length === 0 || input.blobLength < 0n) {
      return Promise.reject(new Error("mark_finalized_invalid_blob_attributes"));
    }
    const row = this.#prepared.get(asString(input.preparedBlobId));
    if (row === undefined || row.state !== "uploading") {
      return Promise.reject(new Error("prepare_finalize_lost_race"));
    }
    row.blobEtag = input.blobEtag;
    row.blobLen = input.blobLength;
    row.state = "finalized";
    return Promise.resolve();
  }

  public async prepare(input: PrepareReversalWriteInput): Promise<PreparedReversalWrite> {
    const handle = this.#nextPreparedHandle();
    // Prepared-row lifecycle age belongs to the plane clock. The producer timestamp remains
    // metadata inside the encrypted record and must not drive reclamation eligibility.
    const createdAtMs = checkedDuration(this.#nowEpochMilliseconds(), "created_at_ms");
    const retention = this.#retentionMetadata({
      tenantId: asString(input.encryptedRecord.meta.tenantId),
      attemptId: asString(input.encryptedRecord.meta.attemptId),
      retentionClass: input.encryptedRecord.meta.retentionClass,
      createdAtEpochMs: input.encryptedRecord.meta.createdAtEpochMs,
      expiresAtEpochMs: input.encryptedRecord.meta.expiresAtEpochMs,
    });
    const row: PreparedRow = {
      preparedBlobId: handle,
      tenant: asString(input.encryptedRecord.meta.tenantId),
      mappingKey: input.mappingKey,
      idempotencyKey: input.idempotencyKey,
      scopeDigest: input.immutableScopeDigest,
      createdAtMs,
      operationKey: retention.operationKey,
      recordCreatedAtMs: retention.recordCreatedAtMs,
      retentionClass: input.encryptedRecord.meta.retentionClass,
      retentionOrigin: "anchored",
      retentionExpiresAtMs: input.encryptedRecord.meta.expiresAtEpochMs,
      stagingPath: `staging/${asString(handle)}`,
      blobPath: `blobs/${asString(handle)}`,
      state: "uploading",
    };

    // Control-plane intent is durable before either data-plane location exists.
    this.#anchorPrepared(row);
    this.#fault("prepareAfterUploadingInsert");

    row.stagingBlob = artifactFor(input.encryptedRecord);
    this.#fault("prepareAfterStagingUpload");

    // Atomic staging -> final rename. The final artifact's attributes are captured afterwards.
    row.blob = row.stagingBlob;
    delete row.stagingBlob;
    this.#fault("prepareAfterBlobRename");
    if (row.state !== "uploading" || row.blob === undefined) {
      throw new Error("prepare_finalize_lost_race");
    }
    row.blobEtag = row.blob.etag;
    row.blobLen = row.blob.length;
    row.state = "finalized";
    return { handle };
  }

  public publish(prepared: PreparedReversalWrite): Promise<PublishReversalResult>;
  public publish(input: PublishPreparedInput): Promise<PublishReversalResult>;
  public publish(input: PreparedReversalWrite | PublishPreparedInput): Promise<PublishReversalResult> {
    const prepared = "prepared" in input ? input.prepared : input;
    if ("prepared" in input) checkedDuration(input.nowEpochMilliseconds, "now_ms");
    const nowEpochMilliseconds = checkedDuration(this.#nowEpochMilliseconds(), "now_ms");
    const suppliedExpiry = "prepared" in input ? input.expiresAtEpochMs : undefined;
    if (suppliedExpiry !== undefined && (suppliedExpiry < 0n || suppliedExpiry > 2n ** 64n - 1n)) {
      return Promise.reject(new Error("publish_invalid_expiry"));
    }
    const row = this.#prepared.get(asString(prepared.handle));
    if (row === undefined) {
      return Promise.reject(new Error("publish_unknown_prepared"));
    }
    // This synchronous section models SELECT ... FOR UPDATE through commit.
    if (row.state !== "finalized" && row.state !== "committed") {
      return Promise.reject(new Error("publish_prepared_not_finalized"));
    }

    const mappingKey = asString(row.mappingKey);
    const ordinal = this.#ordinalNext.get(mappingKey) ?? 1n;
    this.#ordinalNext.set(mappingKey, ordinal + 1n);

    const idempotencyKey = asString(row.idempotencyKey);
    const existing = this.#claims.get(idempotencyKey);
    if (existing !== undefined) {
      this.#selfHealIfStale(existing, nowEpochMilliseconds);
      const expired = this.#computeExpired(existing, nowEpochMilliseconds);
      return Promise.resolve({
        kind: "existing",
        commit: existing.commitHandle,
        immutableScopeDigest: existing.scopeDigest,
        expired,
      });
    }

    if (
      row.state !== "finalized" ||
      row.blobEtag === undefined ||
      row.blobLen === undefined ||
      (suppliedExpiry === undefined && row.blob === undefined)
    ) {
      return Promise.reject(new Error("publish_prepared_not_durable"));
    }
    const effectiveExpiry = suppliedExpiry ?? row.blob!.encryptedRecord.meta.expiresAtEpochMs;
    if (row.retentionExpiresAtMs === null || row.retentionExpiresAtMs !== effectiveExpiry) {
      return Promise.reject(new Error("publish_retention_metadata_mismatch"));
    }
    const claim: ClaimRow = {
      idempotencyKey: row.idempotencyKey,
      tenant: row.tenant,
      mappingKey: row.mappingKey,
      scopeDigest: row.scopeDigest,
      commitHandle: this.#nextCommitHandle(),
      preparedBlobId: row.preparedBlobId,
      ordinal,
      createdAtMs: row.createdAtMs,
      expiresAtMs: effectiveExpiry,
      state: "pending",
    };
    this.#claims.set(idempotencyKey, claim);
    this.#claimsByCommit.set(asString(claim.commitHandle), claim);
    row.state = "committed";
    return Promise.resolve({ kind: "published", commit: claim.commitHandle });
  }

  #computeExpired(claim: ClaimRow, nowEpochMs: number): boolean {
    if (claim.state === "expired") {
      return true;
    }
    const expired = BigInt(nowEpochMs) >= claim.expiresAtMs;
    if (claim.state === "pending" && expired) {
      this.#expirePending(claim);
      return true;
    }
    return expired;
  }

  #expirePending(claim: ClaimRow): void {
    if (claim.state !== "pending" || claim.preparedBlobId === null) {
      throw new Error("expire_non_pending_claim");
    }
    const preparedId = asString(claim.preparedBlobId);
    const row = this.#prepared.get(preparedId);
    if (row === undefined || row.state !== "committed") {
      throw new Error("expire_missing_committed_prepared");
    }
    for (const current of this.#current.values()) {
      if (asString(current.preparedBlobId) === preparedId) {
        throw new Error("expire_pending_has_current_reference");
      }
    }
    for (const other of this.#claims.values()) {
      if (other !== claim && other.preparedBlobId !== null && asString(other.preparedBlobId) === preparedId) {
        throw new Error("expire_pending_has_other_claim_reference");
      }
    }
    claim.state = "expired";
    claim.preparedBlobId = null;
    row.state = "orphaned";
  }

  public readClaimBlobReference(commit: PublishedCommitHandle): Promise<ClaimBlobReference> {
    const claim = this.#claimsByCommit.get(asString(commit));
    if (claim?.state === "superseded") {
      return Promise.resolve({ kind: "superseded" });
    }
    if (claim?.state === "flushed") {
      const current = this.#current.get(asString(claim.mappingKey));
      if (
        current !== undefined &&
        asString(current.commitHandle) !== asString(claim.commitHandle) &&
        current.ordinal >= claim.ordinal
      ) {
        return Promise.resolve({ kind: "stale-flushed" });
      }
    }
    const row = claim?.preparedBlobId === null || claim?.preparedBlobId === undefined
      ? undefined
      : this.#prepared.get(asString(claim.preparedBlobId));
    if (
      claim === undefined ||
      (claim.state !== "pending" && claim.state !== "flushed") ||
      row === undefined ||
      row.state !== "committed" ||
      row.blobEtag === undefined ||
      row.blobLen === undefined
    ) {
      return Promise.reject(new Error("flush_claim_blob_reference_integrity_failure"));
    }
    return Promise.resolve({
      kind: "blob",
      blobPath: row.blobPath,
      blobEtag: row.blobEtag,
      blobLength: row.blobLen,
    });
  }

  #transactionalLifecycle<T>(operation: () => T): T {
    const claims = new Map([...this.#claims].map(([key, value]) => [key, { ...value }]));
    const prepared = new Map([...this.#prepared].map(([key, value]) => [key, { ...value }]));
    const current = new Map([...this.#current].map(([key, value]) => [key, { ...value }]));
    try {
      return operation();
    } catch (error: unknown) {
      this.#claims.clear();
      this.#claimsByCommit.clear();
      for (const [key, value] of claims) {
        this.#claims.set(key, value);
        this.#claimsByCommit.set(asString(value.commitHandle), value);
      }
      this.#prepared.clear();
      for (const [key, value] of prepared) this.#prepared.set(key, value);
      this.#current.clear();
      for (const [key, value] of current) this.#current.set(key, value);
      throw error;
    }
  }

  #assertNoOtherReference(row: PreparedRow, subject: ClaimRow, allowedCurrentMapping?: string): void {
    for (const other of this.#claims.values()) {
      if (
        other !== subject &&
        other.preparedBlobId !== null &&
        asString(other.preparedBlobId) === asString(row.preparedBlobId)
      ) {
        throw new Error("supersede_prepared_is_referenced");
      }
    }
    for (const current of this.#current.values()) {
      if (
        asString(current.preparedBlobId) === asString(row.preparedBlobId) &&
        (allowedCurrentMapping === undefined || asString(current.mappingKey) !== allowedCurrentMapping)
      ) {
        throw new Error("supersede_prepared_is_referenced");
      }
    }
  }

  #selfHealIfStale(claim: ClaimRow, nowEpochMs: number): void {
    if (claim.state !== "flushed" || claim.preparedBlobId === null) return;
    const current = this.#current.get(asString(claim.mappingKey));
    if (
      current === undefined ||
      asString(current.commitHandle) === asString(claim.commitHandle) ||
      current.ordinal < claim.ordinal
    ) {
      return;
    }
    this.#transactionalLifecycle(() => {
      const row = this.#prepared.get(asString(claim.preparedBlobId!));
      if (row === undefined || row.state !== "committed") {
        throw new Error("self_heal_prepared_invariant_failure");
      }
      this.#assertNoOtherReference(row, claim);
      this.#fault("selfHealAfterLockVerify");
      claim.state = "superseded";
      claim.preparedBlobId = null;
      row.state = "superseded";
      row.supersededAtMs = nowEpochMs;
      delete row.reclaimAfterMs;
      this.#fault("selfHealAfterCte");
    });
  }

  #flushAtomic(
    commit: PublishedCommitHandle,
    attributes?: { readonly blobEtag: string; readonly blobLength: bigint },
  ): boolean {
    return this.#transactionalLifecycle(() => {
      const claim = this.#claimsByCommit.get(asString(commit));
      if (claim === undefined) throw new Error("flush_unknown_commit");
      const nowEpochMs = checkedDuration(this.#nowEpochMilliseconds(), "now_ms");
      if (claim.state === "superseded") return false;
      if (claim.state === "expired") throw new Error("flush_expired_commit");
      if (claim.state === "flushed") {
        const current = this.#current.get(asString(claim.mappingKey));
        if (
          current !== undefined &&
          asString(current.commitHandle) === asString(claim.commitHandle) &&
          current.preparedBlobId === claim.preparedBlobId &&
          current.ordinal === claim.ordinal
        ) return false;
        this.#selfHealIfStale(claim, nowEpochMs);
        if (claim.preparedBlobId === null) return false;
        throw new Error("flush_flushed_current_invariant_failure");
      }
      if (BigInt(nowEpochMs) >= claim.expiresAtMs) {
        this.#expirePending(claim);
        return true;
      }
      if (claim.preparedBlobId === null) throw new Error("flush_pending_without_prepared");
      const row = this.#prepared.get(asString(claim.preparedBlobId));
      if (
        attributes === undefined ||
        row === undefined ||
        row.state !== "committed" ||
        row.blobEtag === undefined ||
        row.blobLen === undefined ||
        row.blobEtag !== attributes.blobEtag ||
        row.blobLen !== attributes.blobLength
      ) {
        throw new Error("flush_blob_integrity_failure");
      }
      const mapping = asString(claim.mappingKey);
      const current = this.#current.get(mapping);
      if (current === undefined) {
        claim.state = "flushed";
        this.#current.set(mapping, {
          mappingKey: claim.mappingKey,
          commitHandle: claim.commitHandle,
          preparedBlobId: claim.preparedBlobId,
          ordinal: claim.ordinal,
          flushedAtMs: nowEpochMs,
        });
        return false;
      }
      if (claim.ordinal > current.ordinal) {
        const oldClaim = this.#claimsByCommit.get(asString(current.commitHandle));
        const oldPrepared = this.#prepared.get(asString(current.preparedBlobId));
        if (
          oldClaim === undefined || oldClaim.state !== "flushed" ||
          oldClaim.preparedBlobId !== current.preparedBlobId ||
          oldPrepared === undefined || oldPrepared.state !== "committed"
        ) {
          throw new Error("flush_old_pointer_invariant_failure");
        }
        this.#assertNoOtherReference(oldPrepared, oldClaim, mapping);
        this.#fault("flushAfterLockVerify");
        claim.state = "flushed";
        this.#fault("flushAfterNewClaim");
        this.#current.set(mapping, {
          mappingKey: claim.mappingKey,
          commitHandle: claim.commitHandle,
          preparedBlobId: claim.preparedBlobId,
          ordinal: claim.ordinal,
          flushedAtMs: nowEpochMs,
        });
        this.#fault("flushAfterPointerCas");
        oldClaim.state = "superseded";
        oldClaim.preparedBlobId = null;
        this.#fault("flushAfterOldClaim");
        oldPrepared.state = "superseded";
        oldPrepared.supersededAtMs = nowEpochMs;
        delete oldPrepared.reclaimAfterMs;
        this.#fault("flushAfterOldPrepared");
        return false;
      }
      claim.state = "superseded";
      claim.preparedBlobId = null;
      this.#fault("flushAfterLoserClaim");
      row.state = "superseded";
      row.supersededAtMs = nowEpochMs;
      delete row.reclaimAfterMs;
      this.#fault("flushAfterLoserPrepared");
      return false;
    });
  }

  public flushClaim(input: FlushClaimInput): Promise<void> {
    checkedDuration(input.nowEpochMilliseconds, "now_ms");
    if ("blobEtag" in input && (input.blobEtag.length === 0 || input.blobLength < 0n)) {
      return Promise.reject(new Error("flush_invalid_blob_attributes"));
    }
    try {
      const expired = this.#flushAtomic(
        input.commit,
        "blobEtag" in input ? { blobEtag: input.blobEtag, blobLength: input.blobLength } : undefined,
      );
      if (expired) return Promise.reject(new Error("flush_expired_pending_commit"));
      return Promise.resolve();
    } catch (error: unknown) {
      return Promise.reject(error);
    }
  }

  public expirePendingDetach(input: ExpirePendingDetachInput): Promise<boolean> {
    checkedDuration(input.nowEpochMilliseconds, "now_ms");
    const claim = this.#claimsByCommit.get(asString(input.commit));
    if (claim === undefined) {
      return Promise.reject(new Error("expire_unknown_commit"));
    }
    return Promise.resolve(this.#computeExpired(
      claim,
      checkedDuration(this.#nowEpochMilliseconds(), "now_ms"),
    ));
  }

  public flush(commit: PublishedCommitHandle): Promise<void> {
    const claim = this.#claimsByCommit.get(asString(commit));
    if (claim === undefined) {
      return Promise.reject(new Error("flush_unknown_commit"));
    }
    if (claim.state === "superseded") return Promise.resolve();
    if (claim.state === "expired") return Promise.reject(new Error("flush_expired_commit"));
    if (claim.state === "flushed") {
      try {
        this.#flushAtomic(commit);
        return Promise.resolve();
      } catch (error: unknown) {
        return Promise.reject(error);
      }
    }
    if (claim.preparedBlobId === null) return Promise.reject(new Error("flush_pending_without_prepared"));
    const row = this.#prepared.get(asString(claim.preparedBlobId));
    if (row === undefined || row.state !== "committed" || row.blob === undefined ||
        row.blobEtag === undefined || row.blobLen === undefined ||
        row.blob.etag !== row.blobEtag || row.blob.length !== row.blobLen) {
      return Promise.reject(new Error("flush_blob_integrity_failure"));
    }
    try {
      const expired = this.#flushAtomic(commit, { blobEtag: row.blobEtag, blobLength: row.blobLen });
      return expired
        ? Promise.reject(new Error("flush_expired_pending_commit"))
        : Promise.resolve();
    } catch (error: unknown) {
      return Promise.reject(error);
    }
  }

  public readCurrent(requests: readonly ReversalLookupRequest[]): Promise<readonly ReversalLookupResult[]> {
    if (requests.length === 0) {
      return Promise.reject(new Error("read_current_requires_exact_keys"));
    }
    const results: ReversalLookupResult[] = [];
    const seen = new Set<string>();
    for (const request of requests) {
      const key = asString(request.mappingKey);
      if (key.length === 0) {
        return Promise.reject(new Error("read_current_requires_nonempty_key"));
      }
      if (seen.has(key)) {
        continue;
      }
      seen.add(key);
      const current = this.#current.get(key);
      if (current === undefined) {
        continue;
      }
      const row = this.#prepared.get(asString(current.preparedBlobId));
      if (row === undefined || row.state === "quarantined" || row.blob === undefined ||
          row.blobEtag === undefined || row.blobLen === undefined ||
          row.blob.etag !== row.blobEtag || row.blob.length !== row.blobLen) {
        return Promise.reject(new Error("read_current_blob_integrity_failure"));
      }
      results.push({ mappingKey: request.mappingKey, encryptedRecord: cloneRecord(row.blob.encryptedRecord) });
    }
    return Promise.resolve(results);
  }

  public readCurrentPointers(mappingKeys: readonly ReversalMappingKey[]): Promise<readonly CurrentPointerRow[]> {
    if (mappingKeys.length === 0) {
      return Promise.reject(new Error("read_current_requires_exact_keys"));
    }
    const rows: CurrentPointerRow[] = [];
    const seen = new Set<string>();
    for (const mappingKey of mappingKeys) {
      const key = asString(mappingKey);
      if (key.length === 0) {
        return Promise.reject(new Error("read_current_requires_nonempty_key"));
      }
      if (seen.has(key)) {
        continue;
      }
      seen.add(key);
      const current = this.#current.get(key);
      if (current === undefined) {
        continue;
      }
      const prepared = this.#prepared.get(asString(current.preparedBlobId));
      const claim = this.#claimsByCommit.get(asString(current.commitHandle));
      if (
        prepared === undefined ||
        prepared.state !== "committed" ||
        prepared.blobEtag === undefined ||
        prepared.blobLen === undefined ||
        claim === undefined
      ) {
        return Promise.reject(new Error("read_current_pointer_integrity_failure"));
      }
      rows.push({
        mappingKey: current.mappingKey,
        tenantId: prepared.tenant as CurrentPointerRow["tenantId"],
        commit: current.commitHandle,
        preparedBlobId: current.preparedBlobId,
        ordinal: current.ordinal,
        flushedAtEpochMs: current.flushedAtMs,
        blobPath: prepared.blobPath,
        blobEtag: prepared.blobEtag,
        blobLength: prepared.blobLen,
      });
    }
    return Promise.resolve(rows);
  }

  /** Replica loss only ends in-flight process work; every control-plane row and blob location survives. */
  public crash(): void {
    // Intentionally empty. In particular, pending claims are durable and must survive.
  }

  #isReferenced(preparedBlobId: PreparedWriteHandle): boolean {
    const id = asString(preparedBlobId);
    for (const claim of this.#claims.values()) {
      if (claim.preparedBlobId !== null && asString(claim.preparedBlobId) === id) {
        return true;
      }
    }
    for (const current of this.#current.values()) {
      if (asString(current.preparedBlobId) === id) {
        return true;
      }
    }
    return false;
  }

  #supersededCandidacy(
    row: PreparedRow,
    supersedeRetentionMs: number,
    readDrainMs: number,
  ): bigint | undefined {
    if (row.state !== "superseded" || row.supersededAtMs === undefined) return undefined;
    const supersededAt = BigInt(row.supersededAtMs);
    const window = supersededAt + BigInt(supersedeRetentionMs);
    const drain = supersededAt + BigInt(readDrainMs);
    if (row.retentionClass === "detector-only" && row.retentionExpiresAtMs !== null) {
      const policy = row.retentionExpiresAtMs < window ? row.retentionExpiresAtMs : window;
      return drain > policy ? drain : policy;
    }
    return supersededAt + BigInt(Math.max(supersedeRetentionMs, readDrainMs));
  }

  #orderedPathOneCandidates(
    olderThanEpochMs: number,
    supersedeRetentionMs: number,
    readDrainMs: number,
    nowEpochMs: number,
  ): PreparedRow[] {
    return [...this.#prepared.values()]
      .filter((row) =>
        row.state === "reclaim_marked" ||
        ((row.state === "finalized" || row.state === "orphaned") && row.createdAtMs < olderThanEpochMs) ||
        (row.state === "superseded" &&
          (this.#supersededCandidacy(row, supersedeRetentionMs, readDrainMs) ?? (2n ** 64n)) <= BigInt(nowEpochMs))
      )
      .sort((left, right) => {
        const stateOrder = Number(left.state !== "reclaim_marked") - Number(right.state !== "reclaim_marked");
        if (stateOrder !== 0) return stateOrder;
        const leftDeadline = this.#supersededCandidacy(left, supersedeRetentionMs, readDrainMs) ?? BigInt(left.createdAtMs);
        const rightDeadline = this.#supersededCandidacy(right, supersedeRetentionMs, readDrainMs) ?? BigInt(right.createdAtMs);
        if (leftDeadline !== rightDeadline) return leftDeadline < rightDeadline ? -1 : 1;
        const leftId = asString(left.preparedBlobId);
        const rightId = asString(right.preparedBlobId);
        return leftId < rightId ? -1 : leftId > rightId ? 1 : 0;
      });
  }

  #selectPathOneCandidates(
    olderThanEpochMs: number,
    limit: number,
    supersedeRetentionMs: number,
    readDrainMs: number,
    nowEpochMs: number,
  ): { readonly rows: readonly PreparedRow[]; readonly skippedReferenced: number } {
    const candidates = this.#orderedPathOneCandidates(
      olderThanEpochMs,
      supersedeRetentionMs,
      readDrainMs,
      nowEpochMs,
    );

    // Match Postgres's separate COUNT over a LIMITed referenced-candidate subquery.
    // The metric is bounded independently; references never occupy reclaimable selection slots.
    let skippedReferenced = 0;
    for (const row of candidates) {
      if (skippedReferenced === limit) break;
      if (this.#isReferenced(row.preparedBlobId)) {
        skippedReferenced += 1;
      }
    }

    const rows: PreparedRow[] = [];
    for (const row of candidates) {
      if (rows.length === limit) break;
      if (!this.#isReferenced(row.preparedBlobId)) {
        rows.push(row);
      }
    }
    return { rows, skippedReferenced };
  }

  public async selectFinalizedOrphansForReclaim(
    input: ReclaimQueryInput,
  ): Promise<ReclaimFinalizedOrphansSelection> {
    checkedDuration(input.olderThanEpochMs, "older_than_ms");
    const limit = checkedLimit(input.limit);
    const supersedeRetentionMs = checkedDuration(
      input.supersedeRetentionMs ?? this.#supersedeRetentionMilliseconds,
      "supersede_retention_ms",
    );
    const readDrainMs = checkedDuration(
      input.readDrainMs ?? this.#readDrainMilliseconds,
      "read_drain_ms",
    );
    const nowEpochMs = checkedDuration(this.#nowEpochMilliseconds(), "now_ms");
    const rows: ReclaimBlobRow[] = [];
    const selected = this.#selectPathOneCandidates(
      input.olderThanEpochMs,
      limit,
      supersedeRetentionMs,
      readDrainMs,
      nowEpochMs,
    );
    for (const row of selected.rows) {
      if (row.state !== "reclaim_marked") {
        if (row.state === "superseded") {
          const candidacy = this.#supersededCandidacy(row, supersedeRetentionMs, readDrainMs);
          if (candidacy === undefined) throw new Error("superseded_candidacy_missing");
          row.reclaimAfterMs = candidacy;
        }
        row.state = "reclaim_marked";
        this.#fault("reclaimAfterPathOneMark");
      }
      if (row.blobLen === undefined) throw new Error("reclaim_blob_length_missing");
      rows.push({ preparedBlobId: row.preparedBlobId, blobPath: row.blobPath, blobLength: row.blobLen });
    }
    return { rows, skippedReferenced: selected.skippedReferenced };
  }

  public async reclaimFinalizedOrphans(input: ReclaimQueryInput): Promise<readonly ReclaimBlobRow[]> {
    return (await this.selectFinalizedOrphansForReclaim(input)).rows;
  }

  public markQuarantined(input: MarkQuarantinedInput): Promise<void> {
    checkedDuration(input.quarantinedAtEpochMs, "quarantined_at_ms");
    const row = this.#prepared.get(asString(input.preparedBlobId));
    if (row?.state === "quarantined") {
      return Promise.resolve();
    }
    if (row === undefined || row.state !== "reclaim_marked") {
      return Promise.reject(new Error("mark_quarantined_invalid_state"));
    }
    row.state = "quarantined";
    row.quarantinedAtMs = input.quarantinedAtEpochMs;
    return Promise.resolve();
  }

  public recoverStaleUploads(input: ReclaimLimitInput): Promise<readonly ReclaimUploadRow[]> {
    const limit = checkedLimit(input.limit);
    return Promise.resolve([...this.#prepared.values()]
      .filter((row) => row.state === "upload_reclaim_marked")
      .slice(0, limit)
      .map((row) => ({
        preparedBlobId: row.preparedBlobId,
        stagingPath: row.stagingPath,
        blobPath: row.blobPath,
      })));
  }

  public async markStaleUploads(input: StaleUploadReclaimInput): Promise<readonly ReclaimUploadRow[]> {
    checkedDuration(input.uploadHorizonEpochMs, "upload_horizon_ms");
    const limit = checkedLimit(input.limit);
    const rows: ReclaimUploadRow[] = [];
    for (const row of this.#prepared.values()) {
      if (rows.length === limit) {
        break;
      }
      if (row.state !== "uploading" || row.createdAtMs >= input.uploadHorizonEpochMs) {
        continue;
      }
      row.state = "upload_reclaim_marked";
      this.#fault("reclaimAfterUploadMark");
      rows.push({
        preparedBlobId: row.preparedBlobId,
        stagingPath: row.stagingPath,
        blobPath: row.blobPath,
      });
    }
    return rows;
  }

  public async reclaimStaleUploads(input: StaleUploadReclaimInput): Promise<readonly ReclaimUploadRow[]> {
    const limit = checkedLimit(input.limit);
    const recovered = await this.recoverStaleUploads({ limit });
    const remaining = limit - recovered.length;
    const fresh = remaining === 0
      ? []
      : await this.markStaleUploads({ ...input, limit: remaining });
    return [...recovered, ...fresh];
  }

  public completeStaleUploadReclaim(preparedBlobId: PreparedWriteHandle): Promise<void> {
    const key = asString(preparedBlobId);
    const row = this.#prepared.get(key);
    if (row === undefined) {
      return Promise.resolve();
    }
    if (row.state !== "upload_reclaim_marked") {
      return Promise.reject(new Error("complete_stale_upload_invalid_state"));
    }
    this.#prepared.delete(key);
    return Promise.resolve();
  }

  public hardDeleteQuarantined(input: ReclaimQueryInput): Promise<readonly ReclaimBlobRow[]> {
    checkedDuration(input.olderThanEpochMs, "older_than_ms");
    const limit = checkedLimit(input.limit);
    return Promise.resolve([...this.#prepared.values()]
      .filter((row) =>
        row.state === "quarantined" &&
        row.quarantinedAtMs !== undefined &&
        row.quarantinedAtMs < input.olderThanEpochMs
      )
      .slice(0, limit)
      .map((row) => {
        if (row.blobLen === undefined) throw new Error("reclaim_blob_length_missing");
        return { preparedBlobId: row.preparedBlobId, blobPath: row.blobPath, blobLength: row.blobLen };
      }));
  }

  public completeHardDeleteQuarantined(preparedBlobId: PreparedWriteHandle): Promise<void> {
    const key = asString(preparedBlobId);
    const row = this.#prepared.get(key);
    if (row === undefined) {
      return Promise.resolve();
    }
    if (row.state !== "quarantined") {
      return Promise.reject(new Error("complete_hard_delete_invalid_state"));
    }
    this.#prepared.delete(key);
    return Promise.resolve();
  }

  public previewReclamation(input: ReclaimPreviewInput): Promise<ReclaimPreviewOutcome> {
    checkedDuration(input.olderThanEpochMs, "older_than_ms");
    checkedDuration(input.uploadHorizonEpochMs, "upload_horizon_ms");
    checkedDuration(input.quarantinedBeforeEpochMs, "quarantined_before_ms");
    const supersedeRetentionMs = checkedDuration(
      input.supersedeRetentionMs ?? this.#supersedeRetentionMilliseconds,
      "supersede_retention_ms",
    );
    const readDrainMs = checkedDuration(
      input.readDrainMs ?? this.#readDrainMilliseconds,
      "read_drain_ms",
    );
    const nowEpochMs = checkedDuration(this.#nowEpochMilliseconds(), "now_ms");
    let remaining = checkedLimit(input.limit);
    let scanned = 0;
    let reclaimed = 0;
    const pathOne = this.#selectPathOneCandidates(
      input.olderThanEpochMs,
      remaining,
      supersedeRetentionMs,
      readDrainMs,
      nowEpochMs,
    );
    const skippedReferenced = pathOne.skippedReferenced;
    scanned += pathOne.rows.length + skippedReferenced;
    reclaimed += pathOne.rows.length;
    remaining -= pathOne.rows.length;

    const count = (predicate: (row: PreparedRow) => boolean): void => {
      if (remaining === 0) return;
      const selected = [...this.#prepared.values()].filter(predicate).slice(0, remaining).length;
      scanned += selected;
      reclaimed += selected;
      remaining -= selected;
    };
    count((row) => row.state === "upload_reclaim_marked");
    count((row) => row.state === "uploading" && row.createdAtMs < input.uploadHorizonEpochMs);
    if (input.includeHardDelete) {
      count((row) =>
        row.state === "quarantined" &&
        row.quarantinedAtMs !== undefined &&
        row.quarantinedAtMs < input.quarantinedBeforeEpochMs
      );
    }
    return Promise.resolve({ scanned, reclaimed, skippedReferenced });
  }

  #finishPathOne(row: PreparedRow, nowEpochMs: number): void {
    if (row.state !== "reclaim_marked") {
      throw new Error("invalid_path_one_recovery_state");
    }
    if (row.blobLen === undefined) throw new Error("reclaim_blob_length_missing");
    if (row.quarantineBlob === undefined && row.blob === undefined) {
      throw new Error("quarantine_both_paths_absent");
    }
    if (row.quarantineBlob !== undefined && row.quarantineBlob.length !== row.blobLen) {
      throw new Error("quarantine_length_mismatch");
    }
    if (row.blob !== undefined && row.blob.length !== row.blobLen) {
      throw new Error("quarantine_length_mismatch");
    }
    if (row.quarantineBlob === undefined && row.blob !== undefined) {
      row.quarantineBlob = row.blob;
      delete row.blob;
    } else if (row.quarantineBlob !== undefined) {
      delete row.blob;
    }
    row.state = "quarantined";
    row.quarantinedAtMs = nowEpochMs;
  }

  #finishPathTwo(row: PreparedRow): void {
    if (row.state !== "upload_reclaim_marked") {
      throw new Error("invalid_path_two_recovery_state");
    }
    delete row.stagingBlob;
    this.#fault("reclaimAfterStagingDelete");
    delete row.blob;
    this.#fault("reclaimAfterBlobDelete");
    if (row.stagingBlob === undefined && row.blob === undefined) {
      this.#prepared.delete(asString(row.preparedBlobId));
    }
  }

  public async reclaimOrphanedPrepared(input: ReclaimOrphanedPreparedInput): Promise<ReclaimOutcome> {
    const scrubbed = scrubReclaimOrphanedPreparedInput(input, this.#maintenanceLimitCap);
    const now = this.#nowEpochMilliseconds();
    let remaining = scrubbed.limit;
    let scanned = 0;
    let reclaimed = 0;
    let skippedReferenced = 0;
    const visit = (): boolean => {
      if (remaining === 0) {
        return false;
      }
      remaining -= 1;
      scanned += 1;
      return true;
    };
    // Path 1: recover marked rows first, then fresh finalized/orphaned rows, while references
    // contribute only to the independently capped metric and never consume the global budget.
    const pathOne = this.#selectPathOneCandidates(
      scrubbed.olderThanEpochMs,
      scrubbed.limit,
      this.#supersedeRetentionMilliseconds,
      this.#readDrainMilliseconds,
      now,
    );
    skippedReferenced = pathOne.skippedReferenced;
    scanned += skippedReferenced;
    for (const row of pathOne.rows) {
      if (!visit()) break;
      if (row.state !== "reclaim_marked") {
        if (row.state === "superseded") {
          const candidacy = this.#supersededCandidacy(
            row,
            this.#supersedeRetentionMilliseconds,
            this.#readDrainMilliseconds,
          );
          if (candidacy === undefined) throw new Error("superseded_candidacy_missing");
          row.reclaimAfterMs = candidacy;
        }
        row.state = "reclaim_marked";
        this.#fault("reclaimAfterPathOneMark");
      }
      this.#finishPathOne(row, now);
      reclaimed += 1;
    }

    // Path 2b first: any crash-left upload_reclaim_marked row is recoverable regardless of age.
    for (const row of [...this.#prepared.values()]) {
      if (remaining === 0) {
        break;
      }
      if (row.state !== "upload_reclaim_marked") {
        continue;
      }
      visit();
      this.#finishPathTwo(row);
      reclaimed += 1;
    }

    // Path 2a: claim stale uploads using the separate, longer upload horizon.
    const uploadThreshold = now - this.#uploadHorizonMilliseconds;
    for (const row of [...this.#prepared.values()]) {
      if (remaining === 0) {
        break;
      }
      if (row.state !== "uploading" || row.createdAtMs >= uploadThreshold) {
        continue;
      }
      visit();
      row.state = "upload_reclaim_marked";
      this.#fault("reclaimAfterUploadMark");
      this.#finishPathTwo(row);
      reclaimed += 1;
    }

    // Path 3: quarantine grace is measured exclusively from authoritative quarantinedAtMs.
    const quarantineThreshold = now - this.#quarantineGraceMilliseconds;
    for (const row of [...this.#prepared.values()]) {
      if (remaining === 0) {
        break;
      }
      if (row.state !== "quarantined" || row.quarantinedAtMs === undefined || row.quarantinedAtMs >= quarantineThreshold) {
        continue;
      }
      visit();
      delete row.quarantineBlob;
      if (row.quarantineBlob === undefined) {
        this.#prepared.delete(asString(row.preparedBlobId));
        reclaimed += 1;
      }
    }

    return { scanned, reclaimed, skippedReferenced };
  }

  // ---- dev-only inspection and corruption affordances (not part of either port) ----------------

  public debugPrepared(preparedBlobId: PreparedWriteHandle): PreparedControlPlaneSnapshot | undefined {
    const row = this.#prepared.get(asString(preparedBlobId));
    if (row === undefined) {
      return undefined;
    }
    return {
      preparedBlobId: row.preparedBlobId,
      tenant: row.tenant,
      mappingKey: row.mappingKey,
      idempotencyKey: row.idempotencyKey,
      scopeDigest: row.scopeDigest,
      createdAtMs: row.createdAtMs,
      operationKey: row.operationKey,
      recordCreatedAtMs: row.recordCreatedAtMs,
      retentionClass: row.retentionClass,
      retentionOrigin: row.retentionOrigin,
      retentionExpiresAtMs: row.retentionExpiresAtMs,
      supersededAtMs: row.supersededAtMs,
      reclaimAfterMs: row.reclaimAfterMs,
      stagingPath: row.stagingPath,
      blobPath: row.blobPath,
      state: row.state,
      blobEtag: row.blobEtag,
      blobLen: row.blobLen,
      quarantinedAtMs: row.quarantinedAtMs,
      stagingBlobPresent: row.stagingBlob !== undefined,
      blobPresent: row.blob !== undefined,
      quarantineBlobPresent: row.quarantineBlob !== undefined,
    };
  }

  public debugPreparedHandles(): readonly PreparedWriteHandle[] {
    return [...this.#prepared.values()].map((row) => row.preparedBlobId);
  }

  public debugClaim(idempotencyKey: ReversalIdempotencyKey): ClaimControlPlaneSnapshot | undefined {
    const claim = this.#claims.get(asString(idempotencyKey));
    if (claim === undefined) {
      return undefined;
    }
    return {
      idempotencyKey: claim.idempotencyKey,
      mappingKey: claim.mappingKey,
      scopeDigest: claim.scopeDigest,
      commitHandle: claim.commitHandle,
      preparedBlobId: claim.preparedBlobId,
      ordinal: claim.ordinal,
      createdAtMs: claim.createdAtMs,
      expiresAtMs: claim.expiresAtMs,
      state: claim.state,
    };
  }

  public debugCurrent(mappingKey: ReversalMappingKey): CurrentControlPlaneSnapshot | undefined {
    const current = this.#current.get(asString(mappingKey));
    return current === undefined ? undefined : { ...current };
  }

  public debugDeleteBlob(preparedBlobId: PreparedWriteHandle): void {
    const row = this.#prepared.get(asString(preparedBlobId));
    if (row === undefined) {
      throw new Error("debug_prepared_absent");
    }
    delete row.blob;
  }

  public debugSetPreparedCreatedAtMs(preparedBlobId: PreparedWriteHandle, createdAtMs: number): void {
    checkedDuration(createdAtMs, "debug_created_at_ms");
    const key = asString(preparedBlobId);
    const row = this.#prepared.get(key);
    if (row === undefined) {
      throw new Error("debug_prepared_absent");
    }
    this.#prepared.set(key, { ...row, createdAtMs });
  }

  public debugSetRecordRetentionOrigin(
    preparedBlobId: PreparedWriteHandle,
    recordCreatedAtMs: number,
    retentionOrigin: "anchored" | "backfilled",
  ): void {
    checkedDuration(recordCreatedAtMs, "debug_record_created_at_ms");
    const key = asString(preparedBlobId);
    const row = this.#prepared.get(key);
    if (row === undefined) throw new Error("debug_prepared_absent");
    this.#prepared.set(key, { ...row, recordCreatedAtMs, retentionOrigin });
  }

  public debugSetClaimLifecycle(
    idempotencyKey: ReversalIdempotencyKey,
    state: ClaimControlPlaneState,
    preparedBlobId: PreparedWriteHandle | null,
  ): void {
    const claim = this.#claims.get(asString(idempotencyKey));
    if (claim === undefined) throw new Error("debug_claim_absent");
    claim.state = state;
    claim.preparedBlobId = preparedBlobId;
  }

  public debugSetPreparedState(
    preparedBlobId: PreparedWriteHandle,
    state: PreparedControlPlaneState,
    quarantinedAtMs?: number,
  ): void {
    const row = this.#prepared.get(asString(preparedBlobId));
    if (row === undefined) {
      throw new Error("debug_prepared_absent");
    }
    if (state === "quarantined") {
      if (quarantinedAtMs === undefined) {
        throw new Error("debug_quarantine_time_required");
      }
      checkedDuration(quarantinedAtMs, "debug_quarantined_at_ms");
      row.quarantinedAtMs = quarantinedAtMs;
    } else {
      delete row.quarantinedAtMs;
    }
    if (state !== "superseded" && state !== "reclaim_marked" && state !== "quarantined") {
      delete row.supersededAtMs;
      delete row.reclaimAfterMs;
    }
    row.state = state;
  }

  public debugSetSupersededMetadata(
    preparedBlobId: PreparedWriteHandle,
    supersededAtMs: number,
    retentionClass: "matter" | "detector-only" | null,
    retentionExpiresAtMs: bigint | null,
  ): void {
    checkedDuration(supersededAtMs, "debug_superseded_at_ms");
    const row = this.#prepared.get(asString(preparedBlobId));
    if (row === undefined) throw new Error("debug_prepared_absent");
    row.state = "superseded";
    row.supersededAtMs = supersededAtMs;
    row.retentionClass = retentionClass;
    row.retentionExpiresAtMs = retentionExpiresAtMs;
    delete row.reclaimAfterMs;
  }

  public debugOperationRetention(tenant: string, attempt: string): "matter" | "detector-only" | undefined {
    return this.#operationRetention.get(`${tenant}\0${attempt}`);
  }

  public debugCorruptBlob(preparedBlobId: PreparedWriteHandle): void {
    const row = this.#prepared.get(asString(preparedBlobId));
    if (row?.blob === undefined) {
      throw new Error("debug_blob_absent");
    }
    const changed = cloneRecord(row.blob.encryptedRecord);
    const ciphertext = Uint8Array.from(changed.ciphertext);
    if (ciphertext.length === 0) {
      throw new Error("debug_blob_empty");
    }
    ciphertext[0] = ciphertext[0]! ^ 1;
    row.blob = artifactFor({ ...changed, ciphertext });
  }

  /** Demonstrates that quarantine is reversible during grace; restoration is an operator action. */
  public debugRestoreQuarantined(preparedBlobId: PreparedWriteHandle): void {
    const row = this.#prepared.get(asString(preparedBlobId));
    if (row?.state !== "quarantined" || row.quarantineBlob === undefined) {
      throw new Error("debug_quarantine_absent");
    }
    row.blob = row.quarantineBlob;
    delete row.quarantineBlob;
    delete row.quarantinedAtMs;
    row.state = "finalized";
  }
}
