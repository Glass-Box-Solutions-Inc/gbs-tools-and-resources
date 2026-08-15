/** Maximum number of rows one in-process reclamation call may inspect. */
export const DEFAULT_RECLAIM_LIMIT_CAP = 10_000;

export interface ReclaimOrphanedPreparedInput {
  readonly olderThanEpochMs: number;
  readonly limit?: number;
}

export interface ReclaimOutcome {
  readonly scanned: number;
  readonly reclaimed: number;
  readonly skippedReferenced: number;
}

export interface SpoolMaintenance {
  reclaimOrphanedPrepared(input: ReclaimOrphanedPreparedInput): Promise<ReclaimOutcome>;
}

export interface ScrubbedReclaimOrphanedPreparedInput {
  readonly olderThanEpochMs: number;
  readonly limit: number;
}

/**
 * Snapshots the passed surface before validating it. In particular, neither field is ever re-read:
 * callers may supply accessors and reclamation authority must not widen between validation and use.
 */
export function scrubReclaimOrphanedPreparedInput(
  input: ReclaimOrphanedPreparedInput,
  limitCap = DEFAULT_RECLAIM_LIMIT_CAP,
): ScrubbedReclaimOrphanedPreparedInput {
  const snapshot = {
    olderThanEpochMs: input.olderThanEpochMs,
    limit: input.limit,
  };

  if (!Number.isSafeInteger(limitCap) || limitCap <= 0) {
    throw new Error("invalid_reclaim_limit_cap");
  }
  if (!Number.isFinite(snapshot.olderThanEpochMs) ||
      !Number.isSafeInteger(snapshot.olderThanEpochMs) ||
      snapshot.olderThanEpochMs < 0) {
    throw new Error("invalid_reclaim_older_than");
  }

  const limit = snapshot.limit ?? limitCap;
  if (!Number.isFinite(limit) || !Number.isSafeInteger(limit) || limit <= 0 || limit > limitCap) {
    throw new Error("invalid_reclaim_limit");
  }

  return { olderThanEpochMs: snapshot.olderThanEpochMs, limit };
}
