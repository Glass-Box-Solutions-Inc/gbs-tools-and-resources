import {
  scrubReclaimOrphanedPreparedInput,
  type ReclaimOrphanedPreparedInput,
  type ReclaimOutcome,
  type SpoolMaintenance,
} from "../maintenance";
import type { PreparedWriteHandle } from "../ports";
import type { BlobStore } from "./blob-store";
import type {
  ControlPlane,
  ReclaimBlobRow,
  ReclaimUploadRow,
} from "./control-plane";

export interface AzureSpoolMaintenanceOptions {
  readonly controlPlane: ControlPlane;
  readonly blobStore: BlobStore;
  readonly uploadHorizonMs: number;
  readonly graceMs: number;
  readonly now?: () => number;
  /** Defaults true. Quarantine-mode jobs disable only Path 3 hard deletion. */
  readonly includeHardDelete?: boolean;
}

function checkedDuration(value: number, label: string): number {
  if (!Number.isSafeInteger(value) || value < 0) {
    throw new Error(`azure_spool_maintenance_invalid_${label}`);
  }
  return value;
}

function checkedNow(value: number): number {
  if (!Number.isSafeInteger(value) || value < 0) {
    throw new Error("azure_spool_maintenance_invalid_now");
  }
  return value;
}

function statusCodeOf(error: unknown): number | undefined {
  if (typeof error !== "object" || error === null || !("statusCode" in error)) {
    return undefined;
  }
  return typeof error.statusCode === "number" ? error.statusCode : undefined;
}

function quarantinePath(preparedBlobId: PreparedWriteHandle): string {
  return `reclaim-quarantine/${preparedBlobId as unknown as string}`;
}

/** Least-authority Azure Files reclamation worker for the three frozen §O paths. */
export class AzureSpoolMaintenance implements SpoolMaintenance {
  readonly #controlPlane: ControlPlane;
  readonly #blobStore: BlobStore;
  readonly #uploadHorizonMs: number;
  readonly #graceMs: number;
  readonly #now: () => number;
  readonly #includeHardDelete: boolean;

  public constructor(options: AzureSpoolMaintenanceOptions) {
    this.#controlPlane = options.controlPlane;
    this.#blobStore = options.blobStore;
    this.#uploadHorizonMs = checkedDuration(options.uploadHorizonMs, "upload_horizon");
    this.#graceMs = checkedDuration(options.graceMs, "grace");
    this.#now = options.now ?? Date.now;
    this.#includeHardDelete = options.includeHardDelete ?? true;
  }

  public async reclaimOrphanedPrepared(input: ReclaimOrphanedPreparedInput): Promise<ReclaimOutcome> {
    // Scrub the hostile caller-owned surface before reading the clock or touching either substrate.
    const scrubbed = scrubReclaimOrphanedPreparedInput(input);
    const nowEpochMs = checkedNow(this.#now());
    let remaining = scrubbed.limit;
    let scanned = 0;
    let reclaimed = 0;
    let skippedReferenced = 0;

    // Path 1: recovery rows are age-independent; fresh rows use the caller's strict horizon.
    const pathOne = await this.#controlPlane.selectFinalizedOrphansForReclaim({
      olderThanEpochMs: scrubbed.olderThanEpochMs,
      limit: remaining,
    });
    this.#assertWithinBudget(pathOne.rows.length, remaining, "path_one");
    remaining -= pathOne.rows.length;
    scanned += pathOne.rows.length + pathOne.skippedReferenced;
    skippedReferenced += pathOne.skippedReferenced;
    for (const row of pathOne.rows) {
      await this.#quarantine(row);
      await this.#controlPlane.markQuarantined({
        preparedBlobId: row.preparedBlobId,
        quarantinedAtEpochMs: nowEpochMs,
      });
      reclaimed += 1;
    }

    // Path 2b recovery gets priority so a steady stream of fresh stale uploads cannot starve a
    // crash-left upload_reclaim_marked row. This is still one combined Path-2 budget.
    if (remaining > 0) {
      const recovery = await this.#controlPlane.recoverStaleUploads({ limit: remaining });
      this.#assertWithinBudget(recovery.length, remaining, "path_two_recovery");
      remaining -= recovery.length;
      scanned += recovery.length;
      reclaimed += await this.#finishUploadRows(recovery);
    }

    // Path 2a: newly stale uploading rows transition exclusively before Files deletion.
    if (remaining > 0) {
      const freshlyMarked = await this.#controlPlane.markStaleUploads({
        uploadHorizonEpochMs: Math.max(0, nowEpochMs - this.#uploadHorizonMs),
        limit: remaining,
      });
      this.#assertWithinBudget(freshlyMarked.length, remaining, "path_two_mark");
      remaining -= freshlyMarked.length;
      scanned += freshlyMarked.length;
      reclaimed += await this.#finishUploadRows(freshlyMarked);
    }

    // Path 3: grace is based only on the authoritative quarantined_at timestamp.
    if (this.#includeHardDelete && remaining > 0) {
      const hardDelete = await this.#controlPlane.hardDeleteQuarantined({
        olderThanEpochMs: Math.max(0, nowEpochMs - this.#graceMs),
        limit: remaining,
      });
      this.#assertWithinBudget(hardDelete.length, remaining, "path_three");
      remaining -= hardDelete.length;
      scanned += hardDelete.length;
      for (const row of hardDelete) {
        const path = quarantinePath(row.preparedBlobId);
        await this.#removeAndConfirmAbsent(path);
        await this.#controlPlane.completeHardDeleteQuarantined(row.preparedBlobId);
        reclaimed += 1;
      }
    }

    return { scanned, reclaimed, skippedReferenced };
  }

  async #quarantine(row: ReclaimBlobRow): Promise<void> {
    const destination = quarantinePath(row.preparedBlobId);
    if (await this.#blobStore.head(destination) !== undefined) {
      // A prior worker completed the rename. Remove a divergent leftover original defensively.
      await this.#removeIdempotently(row.blobPath);
      return;
    }
    if (await this.#blobStore.head(row.blobPath) === undefined) {
      // Recovery deliberately tolerates a missing source, including a crash after an external move.
      return;
    }
    try {
      await this.#blobStore.rename(row.blobPath, destination);
    } catch (error: unknown) {
      if (statusCodeOf(error) === 404) {
        return;
      }
      // Concurrent recovery may win the same rename after our HEAD. Its destination is success.
      if (await this.#blobStore.head(destination) !== undefined) {
        await this.#removeIdempotently(row.blobPath);
        return;
      }
      throw error;
    }
  }

  async #finishUploadRows(rows: readonly ReclaimUploadRow[]): Promise<number> {
    let reclaimed = 0;
    for (const row of rows) {
      await this.#removeAndConfirmAbsent(row.stagingPath);
      await this.#removeAndConfirmAbsent(row.blobPath);
      await this.#controlPlane.completeStaleUploadReclaim(row.preparedBlobId);
      reclaimed += 1;
    }
    return reclaimed;
  }

  async #removeIdempotently(path: string): Promise<void> {
    try {
      await this.#blobStore.remove(path);
    } catch (error: unknown) {
      if (statusCodeOf(error) !== 404) {
        throw error;
      }
    }
  }

  async #removeAndConfirmAbsent(path: string): Promise<void> {
    await this.#removeIdempotently(path);
    if (await this.#blobStore.head(path) !== undefined) {
      throw new Error("azure_spool_maintenance_remove_not_confirmed");
    }
  }

  #assertWithinBudget(selected: number, remaining: number, path: string): void {
    if (!Number.isSafeInteger(selected) || selected < 0 || selected > remaining) {
      throw new Error(`azure_spool_maintenance_${path}_budget_violation`);
    }
  }
}
