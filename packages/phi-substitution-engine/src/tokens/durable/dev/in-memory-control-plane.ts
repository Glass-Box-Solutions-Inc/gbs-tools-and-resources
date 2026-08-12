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
  | "orphaned"
  | "upload_reclaim_marked"
  | "reclaim_marked"
  | "quarantined";

export type ClaimControlPlaneState = "pending" | "flushed" | "expired";

export type InMemoryControlPlaneFaultPhase =
  | "prepareAfterUploadingInsert"
  | "prepareAfterStagingUpload"
  | "prepareAfterBlobRename"
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

/** In-memory implementation of both the frozen request-path port and least-authority maintenance port. */
export class InMemoryControlPlane implements SpoolVolume, SpoolMaintenance {
  readonly #nowEpochMilliseconds: () => number;
  readonly #uploadHorizonMilliseconds: number;
  readonly #quarantineGraceMilliseconds: number;
  readonly #maintenanceLimitCap: number;
  readonly #dekGenerations = new Map<string, DekGeneration>();
  readonly #nonceNext = new Map<string, bigint>();
  readonly #prepared = new Map<string, PreparedRow>();
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

  public async prepare(input: PrepareReversalWriteInput): Promise<PreparedReversalWrite> {
    const handle = this.#nextPreparedHandle();
    const key = asString(handle);
    const row: PreparedRow = {
      preparedBlobId: handle,
      tenant: asString(input.encryptedRecord.meta.tenantId),
      mappingKey: input.mappingKey,
      idempotencyKey: input.idempotencyKey,
      scopeDigest: input.immutableScopeDigest,
      createdAtMs: input.encryptedRecord.meta.createdAtEpochMs,
      state: "uploading",
    };

    // Control-plane intent is durable before either data-plane location exists.
    this.#prepared.set(key, row);
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

  public publish(prepared: PreparedReversalWrite): Promise<PublishReversalResult> {
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
      const expired = this.#computeExpired(existing, this.#nowEpochMilliseconds());
      return Promise.resolve({
        kind: "existing",
        commit: existing.commitHandle,
        immutableScopeDigest: existing.scopeDigest,
        expired,
      });
    }

    if (row.state !== "finalized" || row.blob === undefined || row.blobEtag === undefined || row.blobLen === undefined) {
      return Promise.reject(new Error("publish_prepared_not_durable"));
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
      expiresAtMs: row.blob.encryptedRecord.meta.expiresAtEpochMs,
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

  public flush(commit: PublishedCommitHandle): Promise<void> {
    const claim = this.#claimsByCommit.get(asString(commit));
    if (claim === undefined) {
      return Promise.reject(new Error("flush_unknown_commit"));
    }
    if (claim.state === "flushed") {
      return Promise.resolve();
    }
    if (claim.state === "expired") {
      return Promise.reject(new Error("flush_expired_commit"));
    }
    if (BigInt(this.#nowEpochMilliseconds()) >= claim.expiresAtMs) {
      this.#expirePending(claim);
      return Promise.reject(new Error("flush_expired_pending_commit"));
    }
    if (claim.preparedBlobId === null) {
      return Promise.reject(new Error("flush_pending_without_prepared"));
    }
    const row = this.#prepared.get(asString(claim.preparedBlobId));
    if (row === undefined || row.state !== "committed" || row.blob === undefined ||
        row.blobEtag === undefined || row.blobLen === undefined ||
        row.blob.etag !== row.blobEtag || row.blob.length !== row.blobLen) {
      return Promise.reject(new Error("flush_blob_integrity_failure"));
    }

    claim.state = "flushed";
    const mappingKey = asString(claim.mappingKey);
    const current = this.#current.get(mappingKey);
    if (current === undefined || claim.ordinal > current.ordinal) {
      this.#current.set(mappingKey, {
        mappingKey: claim.mappingKey,
        commitHandle: claim.commitHandle,
        preparedBlobId: claim.preparedBlobId,
        ordinal: claim.ordinal,
        flushedAtMs: this.#nowEpochMilliseconds(),
      });
    }
    return Promise.resolve();
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

  #finishPathOne(row: PreparedRow, nowEpochMs: number): void {
    if (row.state !== "reclaim_marked") {
      throw new Error("invalid_path_one_recovery_state");
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

    // Recovery selector: reclaim_marked is age-independent after a worker has exclusively claimed it.
    for (const row of [...this.#prepared.values()]) {
      if (row.state !== "reclaim_marked" || !visit()) {
        continue;
      }
      if (this.#isReferenced(row.preparedBlobId)) {
        skippedReferenced += 1;
        continue;
      }
      this.#finishPathOne(row, now);
      reclaimed += 1;
    }

    // Path 1: only finalized/orphaned rows past the caller's strict horizon may be marked.
    for (const row of [...this.#prepared.values()]) {
      if (remaining === 0) {
        break;
      }
      if ((row.state !== "finalized" && row.state !== "orphaned") || row.createdAtMs >= scrubbed.olderThanEpochMs) {
        continue;
      }
      visit();
      if (this.#isReferenced(row.preparedBlobId)) {
        skippedReferenced += 1;
        continue;
      }
      row.state = "reclaim_marked";
      this.#fault("reclaimAfterPathOneMark");
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
