import {
  ShareServiceClient,
  StorageSharedKeyCredential,
  type ShareDirectoryClient,
  type ShareFileClient,
} from "@azure/storage-file-share";
import type { BlobProperties, BlobStore } from "./blob-store";

const ROOT_DIRECTORIES = ["staging", "blobs", "reclaim-quarantine"] as const;
const MAX_RANGE_BYTES = 4 * 1024 * 1024;

interface ParsedPath {
  readonly directory: (typeof ROOT_DIRECTORIES)[number];
  readonly name: string;
}

function parsePath(path: string): ParsedPath {
  const parts = path.split("/");
  const directory = parts[0];
  const name = parts[1];
  if (
    parts.length !== 2 ||
    name === undefined ||
    name.length === 0 ||
    name === "." ||
    name === ".." ||
    !ROOT_DIRECTORIES.some((candidate) => candidate === directory)
  ) {
    throw new Error("azure_files_blob_store_invalid_path");
  }
  return { directory: directory as ParsedPath["directory"], name };
}

function statusCodeOf(error: unknown): number | undefined {
  if (typeof error !== "object" || error === null || !("statusCode" in error)) {
    return undefined;
  }
  const statusCode = error.statusCode;
  return typeof statusCode === "number" ? statusCode : undefined;
}

function propertiesOf(etag: string | undefined, contentLength: number | undefined): BlobProperties {
  if (etag === undefined || etag.length === 0 || contentLength === undefined || !Number.isSafeInteger(contentLength) || contentLength < 0) {
    throw new Error("azure_files_blob_store_invalid_properties");
  }
  return { etag, len: contentLength };
}

/** Azure Files implementation for the immutable `phi-spool` data plane. */
export class AzureFilesBlobStore implements BlobStore {
  readonly #share;
  readonly #directories = new Map<ParsedPath["directory"], ShareDirectoryClient>();
  #ready: Promise<void> | undefined;

  public constructor(accountName: string, accountKey: string, shareName = "phi-spool") {
    if (accountName.length === 0 || accountKey.length === 0 || shareName.length === 0) {
      throw new Error("azure_files_blob_store_invalid_configuration");
    }
    const credential = new StorageSharedKeyCredential(accountName, accountKey);
    const service = new ShareServiceClient(`https://${accountName}.file.core.windows.net`, credential);
    this.#share = service.getShareClient(shareName);
    for (const root of ROOT_DIRECTORIES) {
      this.#directories.set(root, this.#share.getDirectoryClient(root));
    }
  }

  async #initialize(): Promise<void> {
    if (this.#ready === undefined) {
      this.#ready = (async () => {
        await this.#share.createIfNotExists();
        await Promise.all([...this.#directories.values()].map(async (directory) => directory.createIfNotExists()));
      })();
    }
    try {
      await this.#ready;
    } catch (error: unknown) {
      this.#ready = undefined;
      throw error;
    }
  }

  #file(path: string): ShareFileClient {
    const parsed = parsePath(path);
    const directory = this.#directories.get(parsed.directory);
    if (directory === undefined) {
      throw new Error("azure_files_blob_store_missing_directory");
    }
    return directory.getFileClient(parsed.name);
  }

  public async putStaging(stagingPath: string, bytes: Uint8Array): Promise<void> {
    const parsed = parsePath(stagingPath);
    if (parsed.directory !== "staging") {
      throw new Error("azure_files_blob_store_requires_staging_path");
    }
    await this.#initialize();
    const file = this.#file(stagingPath);
    await file.create(bytes.byteLength);
    for (let offset = 0; offset < bytes.byteLength; offset += MAX_RANGE_BYTES) {
      const length = Math.min(MAX_RANGE_BYTES, bytes.byteLength - offset);
      await file.uploadRange(bytes.subarray(offset, offset + length), offset, length);
    }
  }

  public async finalize(stagingPath: string, blobPath: string): Promise<BlobProperties> {
    if (parsePath(stagingPath).directory !== "staging" || parsePath(blobPath).directory !== "blobs") {
      throw new Error("azure_files_blob_store_invalid_finalize_paths");
    }
    await this.#initialize();
    await this.#file(stagingPath).rename(blobPath, { replaceIfExists: false });
    const finalized = await this.head(blobPath);
    if (finalized === undefined) {
      throw new Error("azure_files_blob_store_finalize_missing_target");
    }
    return finalized;
  }

  public async head(blobPath: string): Promise<BlobProperties | undefined> {
    await this.#initialize();
    try {
      const properties = await this.#file(blobPath).getProperties();
      return propertiesOf(properties.etag, properties.contentLength);
    } catch (error: unknown) {
      if (statusCodeOf(error) === 404) {
        return undefined;
      }
      throw error;
    }
  }

  public async get(blobPath: string): Promise<Uint8Array | undefined> {
    await this.#initialize();
    try {
      return Uint8Array.from(await this.#file(blobPath).downloadToBuffer());
    } catch (error: unknown) {
      if (statusCodeOf(error) === 404) {
        return undefined;
      }
      throw error;
    }
  }

  public async rename(fromPath: string, toPath: string): Promise<void> {
    parsePath(toPath);
    await this.#initialize();
    await this.#file(fromPath).rename(toPath, { replaceIfExists: false });
  }

  public async remove(path: string): Promise<void> {
    await this.#initialize();
    await this.#file(path).deleteIfExists();
  }
}
