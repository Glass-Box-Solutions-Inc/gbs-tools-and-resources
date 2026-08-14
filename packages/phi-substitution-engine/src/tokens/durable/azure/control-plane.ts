import type { TenantId } from "../../../core/brands";
import type {
  DekGeneration,
  EnsureDekGenerationInput,
  GcmNonce96,
  NonceReservationInput,
  PreparedReversalWrite,
  PreparedWriteHandle,
  PublishReversalResult,
  PublishedCommitHandle,
  ReversalIdempotencyKey,
  ReversalMappingKey,
  ReversalScopeDigest,
} from "../ports";

export type PreparedControlPlaneState =
  | "uploading"
  | "finalized"
  | "committed"
  | "orphaned"
  | "upload_reclaim_marked"
  | "reclaim_marked"
  | "quarantined";

export type ClaimControlPlaneState = "pending" | "flushed" | "expired";

export interface InsertPreparedUploadingInput {
  readonly preparedBlobId: PreparedWriteHandle;
  readonly tenantId: TenantId;
  readonly mappingKey: ReversalMappingKey;
  readonly idempotencyKey: ReversalIdempotencyKey;
  readonly immutableScopeDigest: ReversalScopeDigest;
  readonly stagingPath: string;
  readonly blobPath: string;
  readonly createdAtEpochMs: number;
}

export interface MarkFinalizedInput {
  readonly preparedBlobId: PreparedWriteHandle;
  readonly blobEtag: string;
  readonly blobLength: bigint;
}

export interface PublishPreparedInput {
  readonly prepared: PreparedReversalWrite;
  readonly expiresAtEpochMs: bigint;
  readonly nowEpochMilliseconds: number;
}

export interface FlushClaimInput {
  readonly commit: PublishedCommitHandle;
  readonly nowEpochMilliseconds: number;
  /** HEAD attributes read by the blob-plane adapter immediately before this call. */
  readonly blobEtag: string;
  readonly blobLength: bigint;
}

export interface ExpirePendingDetachInput {
  readonly commit: PublishedCommitHandle;
  readonly nowEpochMilliseconds: number;
}

export interface PreparedControlPlaneRow {
  readonly preparedBlobId: PreparedWriteHandle;
  readonly tenantId: TenantId;
  readonly mappingKey: ReversalMappingKey;
  readonly idempotencyKey: ReversalIdempotencyKey;
  readonly immutableScopeDigest: ReversalScopeDigest;
  readonly stagingPath: string;
  readonly blobPath: string;
  readonly createdAtEpochMs: number;
  readonly state: PreparedControlPlaneState;
  readonly blobEtag: string | null;
  readonly blobLength: bigint | null;
  readonly quarantinedAtEpochMs: number | null;
}

export interface ClaimControlPlaneRow {
  readonly idempotencyKey: ReversalIdempotencyKey;
  readonly tenantId: TenantId;
  readonly mappingKey: ReversalMappingKey;
  readonly immutableScopeDigest: ReversalScopeDigest;
  readonly commit: PublishedCommitHandle;
  readonly preparedBlobId: PreparedWriteHandle | null;
  readonly ordinal: bigint;
  readonly createdAtEpochMs: number;
  readonly expiresAtEpochMs: bigint;
  readonly state: ClaimControlPlaneState;
}

/** Pointer metadata used by B2 to fetch and integrity-check an immutable blob. */
export interface CurrentPointerRow {
  readonly mappingKey: ReversalMappingKey;
  readonly tenantId: TenantId;
  readonly commit: PublishedCommitHandle;
  readonly preparedBlobId: PreparedWriteHandle;
  readonly ordinal: bigint;
  readonly flushedAtEpochMs: number;
  readonly blobPath: string;
  readonly blobEtag: string;
  readonly blobLength: bigint;
}

/** Durable blob address for a pending/flushed claim; used to HEAD before `flushClaim`. */
export interface ClaimBlobReference {
  readonly blobPath: string;
  readonly blobEtag: string;
  readonly blobLength: bigint;
}

export interface ReclaimQueryInput {
  readonly olderThanEpochMs: number;
  readonly limit: number;
}

export interface StaleUploadReclaimInput {
  readonly uploadHorizonEpochMs: number;
  readonly limit: number;
}

export interface ReclaimBlobRow {
  readonly preparedBlobId: PreparedWriteHandle;
  readonly blobPath: string;
}

export interface ReclaimUploadRow extends ReclaimBlobRow {
  readonly stagingPath: string;
}

export interface MarkQuarantinedInput {
  readonly preparedBlobId: PreparedWriteHandle;
  readonly quarantinedAtEpochMs: number;
}

export interface ReclaimLimitInput {
  readonly limit: number;
}

/** Path-1 inspection result, including candidates rejected by the live-reference invariant. */
export interface ReclaimFinalizedOrphansSelection {
  readonly rows: readonly ReclaimBlobRow[];
  readonly skippedReferenced: number;
}

export interface ReclaimPreviewInput {
  readonly olderThanEpochMs: number;
  readonly uploadHorizonEpochMs: number;
  readonly quarantinedBeforeEpochMs: number;
  readonly limit: number;
  readonly includeHardDelete: boolean;
}

export interface ReclaimPreviewOutcome {
  readonly scanned: number;
  readonly reclaimed: number;
  readonly skippedReferenced: number;
}

/**
 * Transactional metadata seam for the Azure Files SpoolVolume and its least-authority maintenance
 * worker. Files operations deliberately stay outside this interface; state markers make each
 * cross-substrate sequence crash-recoverable.
 */
export interface ControlPlane {
  ensureDekGeneration(input: EnsureDekGenerationInput): Promise<DekGeneration>;
  reserveNonce(input: NonceReservationInput): Promise<GcmNonce96>;
  insertPreparedUploading(input: InsertPreparedUploadingInput): Promise<void>;
  markFinalized(input: MarkFinalizedInput): Promise<void>;
  publish(input: PublishPreparedInput): Promise<PublishReversalResult>;
  readClaimBlobReference(commit: PublishedCommitHandle): Promise<ClaimBlobReference>;
  flushClaim(input: FlushClaimInput): Promise<void>;
  /** Returns true for an existing/just-created tombstone, false when the claim is not yet expired. */
  expirePendingDetach(input: ExpirePendingDetachInput): Promise<boolean>;
  readCurrentPointers(mappingKeys: readonly ReversalMappingKey[]): Promise<readonly CurrentPointerRow[]>;

  /** Path 1, including age-independent recovery of rows already in reclaim_marked. */
  reclaimFinalizedOrphans(input: ReclaimQueryInput): Promise<readonly ReclaimBlobRow[]>;
  markQuarantined(input: MarkQuarantinedInput): Promise<void>;

  /**
   * Path 1 with inspection accounting. The global maintenance budget counts both selected rows
   * and eligible rows excluded because a claim/current pointer still references them.
   */
  selectFinalizedOrphansForReclaim(
    input: ReclaimQueryInput,
  ): Promise<ReclaimFinalizedOrphansSelection>;

  /** Path 2a + v5 Path 2b recovery. Files must be absent before completion. */
  reclaimStaleUploads(input: StaleUploadReclaimInput): Promise<readonly ReclaimUploadRow[]>;
  completeStaleUploadReclaim(preparedBlobId: PreparedWriteHandle): Promise<void>;

  /** Path 2a only: exclusively transition newly stale uploading rows. */
  markStaleUploads(input: StaleUploadReclaimInput): Promise<readonly ReclaimUploadRow[]>;
  /** Path 2b only: recover marked rows regardless of their age. */
  recoverStaleUploads(input: ReclaimLimitInput): Promise<readonly ReclaimUploadRow[]>;

  /** Path 3 selector; caller deletes Files bytes before completing the row deletion. */
  hardDeleteQuarantined(input: ReclaimQueryInput): Promise<readonly ReclaimBlobRow[]>;
  completeHardDeleteQuarantined(preparedBlobId: PreparedWriteHandle): Promise<void>;

  /** Read-only, globally-budgeted preview used by the dry-run reclamation job. */
  previewReclamation(input: ReclaimPreviewInput): Promise<ReclaimPreviewOutcome>;
}
