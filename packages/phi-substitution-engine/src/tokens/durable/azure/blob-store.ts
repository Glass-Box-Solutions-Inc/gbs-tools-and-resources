/** Immutable ciphertext data-plane seam used by the Azure spool and maintenance adapters. */
export interface BlobProperties {
  readonly etag: string;
  readonly len: number;
}

export interface BlobStore {
  /** Creates/replaces a unique staging object and returns only after its bytes are durable. */
  putStaging(stagingPath: string, bytes: Uint8Array): Promise<void>;
  /** Atomically renames a staging object to its immutable final path. */
  finalize(stagingPath: string, blobPath: string): Promise<BlobProperties>;
  head(blobPath: string): Promise<BlobProperties | undefined>;
  get(blobPath: string): Promise<Uint8Array | undefined>;
  rename(fromPath: string, toPath: string): Promise<void>;
  /** Idempotent: an absent object is already removed. */
  remove(path: string): Promise<void>;
}
