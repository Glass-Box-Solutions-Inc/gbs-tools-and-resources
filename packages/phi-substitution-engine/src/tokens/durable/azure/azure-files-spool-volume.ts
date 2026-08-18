import { randomUUID } from "node:crypto";
import type {
  DekGeneration,
  EnsureDekGenerationInput,
  GcmNonce96,
  NonceReservationInput,
  PrepareReversalWriteInput,
  PreparedReversalWrite,
  PreparedWriteHandle,
  PublishReversalResult,
  PublishedCommitHandle,
  ReversalLookupRequest,
  ReversalLookupResult,
  SpoolVolume,
} from "../ports";
import type { BlobStore } from "./blob-store";
import type { ControlPlane, CurrentPointerRow } from "./control-plane";
import { decodeReversalBlob, encodeReversalBlob } from "./reversal-blob-codec";

function handleOf(value: string): PreparedWriteHandle {
  return value as unknown as PreparedWriteHandle;
}

function blobPath(handle: PreparedWriteHandle): string {
  return `blobs/${handle as unknown as string}`;
}

function stagingPath(handle: PreparedWriteHandle): string {
  return `staging/${handle as unknown as string}`;
}

/** Frozen SpoolVolume adapter over PostgreSQL ordering metadata plus immutable Azure Files bytes. */
export class AzureFilesSpoolVolume implements SpoolVolume {
  readonly #controlPlane: ControlPlane;
  readonly #blobStore: BlobStore;
  readonly #nowEpochMilliseconds: () => number;

  public constructor(controlPlane: ControlPlane, blobStore: BlobStore, nowEpochMilliseconds: () => number = Date.now) {
    this.#controlPlane = controlPlane;
    this.#blobStore = blobStore;
    this.#nowEpochMilliseconds = nowEpochMilliseconds;
  }

  public ensureDekGeneration(input: EnsureDekGenerationInput): Promise<DekGeneration> {
    return this.#controlPlane.ensureDekGeneration(input);
  }

  public reserveNonce(input: NonceReservationInput): Promise<GcmNonce96> {
    return this.#controlPlane.reserveNonce(input);
  }

  public async prepare(input: PrepareReversalWriteInput): Promise<PreparedReversalWrite> {
    const handle = handleOf(randomUUID());
    const staging = stagingPath(handle);
    const blob = blobPath(handle);
    await this.#controlPlane.insertPreparedUploading({
      preparedBlobId: handle,
      tenantId: input.encryptedRecord.meta.tenantId,
      mappingKey: input.mappingKey,
      idempotencyKey: input.idempotencyKey,
      immutableScopeDigest: input.immutableScopeDigest,
      stagingPath: staging,
      blobPath: blob,
      attemptId: input.encryptedRecord.meta.attemptId,
      retentionClass: input.encryptedRecord.meta.retentionClass,
      createdAtEpochMs: input.encryptedRecord.meta.createdAtEpochMs,
      expiresAtEpochMs: input.encryptedRecord.meta.expiresAtEpochMs,
    });
    const encoded = encodeReversalBlob(input.encryptedRecord);
    await this.#blobStore.putStaging(staging, encoded);
    const finalized = await this.#blobStore.finalize(staging, blob);
    await this.#controlPlane.markFinalized({
      preparedBlobId: handle,
      blobEtag: finalized.etag,
      blobLength: BigInt(finalized.len),
    });
    return { handle };
  }

  public async publish(prepared: PreparedReversalWrite): Promise<PublishReversalResult> {
    // The path is derived solely from the globally-unique durable handle. Reading the finalized
    // envelope avoids replica-local prepared context and lets a fresh adapter publish the handle.
    const bytes = await this.#blobStore.get(blobPath(prepared.handle));
    if (bytes === undefined) {
      throw new Error("azure_files_spool_publish_blob_missing");
    }
    const record = decodeReversalBlob(bytes);
    return this.#controlPlane.publish({
      prepared,
      expiresAtEpochMs: record.meta.expiresAtEpochMs,
      nowEpochMilliseconds: this.#nowEpochMilliseconds(),
    });
  }

  public async flush(commit: PublishedCommitHandle): Promise<void> {
    const reference = await this.#controlPlane.readClaimBlobReference(commit);
    if (reference.kind === "superseded") {
      await this.#controlPlane.flushClaim({
        kind: "superseded",
        commit,
        nowEpochMilliseconds: this.#nowEpochMilliseconds(),
      });
      return;
    }
    if (reference.kind === "stale-flushed") {
      await this.#controlPlane.flushClaim({
        kind: "stale-flushed",
        commit,
        nowEpochMilliseconds: this.#nowEpochMilliseconds(),
      });
      return;
    }
    const head = await this.#blobStore.head(reference.blobPath);
    if (
      head === undefined ||
      head.etag !== reference.blobEtag ||
      BigInt(head.len) !== reference.blobLength
    ) {
      throw new Error("azure_files_spool_flush_blob_integrity_failure");
    }
    await this.#controlPlane.flushClaim({
      kind: "blob",
      commit,
      nowEpochMilliseconds: this.#nowEpochMilliseconds(),
      blobEtag: head.etag,
      blobLength: BigInt(head.len),
    });
  }

  public async readCurrent(requests: readonly ReversalLookupRequest[]): Promise<readonly ReversalLookupResult[]> {
    if (requests.length === 0) {
      throw new Error("azure_files_spool_read_requires_exact_keys");
    }
    const pointers = await this.#controlPlane.readCurrentPointers(requests.map((request) => request.mappingKey));
    return Promise.all(pointers.map(async (pointer) => this.#readPointer(pointer)));
  }

  async #readPointer(pointer: CurrentPointerRow): Promise<ReversalLookupResult> {
    const quarantine = `reclaim-quarantine/${pointer.preparedBlobId as unknown as string}`;
    for (const path of [pointer.blobPath, quarantine, pointer.blobPath]) {
      const [head, bytes] = await Promise.all([
        this.#blobStore.head(path),
        this.#blobStore.get(path),
      ]);
      // A rename can race between HEAD and GET. Probe the next bounded location on any partial
      // absence, but never accept present bytes with mismatched durable attributes.
      if (head === undefined || bytes === undefined) {
        continue;
      }
      const isQuarantineFallback = path === quarantine;
      if (
        (!isQuarantineFallback && head.etag !== pointer.blobEtag) ||
        BigInt(head.len) !== pointer.blobLength ||
        BigInt(bytes.byteLength) !== pointer.blobLength
      ) {
        throw new Error("azure_files_spool_read_integrity_failure");
      }
      return { mappingKey: pointer.mappingKey, encryptedRecord: decodeReversalBlob(bytes) };
    }
    throw new Error("azure_files_spool_read_integrity_failure");
  }
}
