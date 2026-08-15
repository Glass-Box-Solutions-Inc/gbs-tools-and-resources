# GLY-346 spec v5 — upload-reclaim crash recovery (supersedes v4 §O Path-2)

v4 resolved D1–D5. v5 closes the single new finding N1: `upload_reclaim_marked` had no recovery selector, so
a worker dying after marking (before/between the two Files deletes) pins the row + any residual ciphertext
forever. Everything else in v2/v3/v4 stands. This is the last mechanical closure — every intermediate state
now has an idempotent recovery selector.

## §O Path-2 (revised) — stale-upload reclaim, crash-recoverable (N1)

Path-2 selects BOTH freshly-stale uploads AND orphaned in-progress reclaims, so no marked row is ever lost:

```sql
-- Phase 2a: claim newly-stale uploading rows past the upload-horizon
UPDATE reversal_prepared SET state='upload_reclaim_marked'
WHERE prepared_blob_id IN (
  SELECT prepared_blob_id FROM reversal_prepared
  WHERE state='uploading' AND created_at_ms < $uploadHorizon
  FOR UPDATE SKIP LOCKED LIMIT $limit)
RETURNING prepared_blob_id, staging_path, blob_path;

-- Phase 2b: RECOVERY — re-select ANY upload_reclaim_marked row (regardless of age: a crash
-- may have left it), lock it, and finish. This is the selector N1 said was missing.
SELECT prepared_blob_id, staging_path, blob_path FROM reversal_prepared
WHERE state='upload_reclaim_marked'
FOR UPDATE SKIP LOCKED LIMIT $limit;
```

Per claimed/recovered row, in order, idempotently (absence = success at each step):
1. delete `staging_path` (404 = already gone = success);
2. delete `blob_path` (404 = success);
3. **only after BOTH are confirmed absent**, `DELETE FROM reversal_prepared WHERE prepared_blob_id=$id`.

A crash after marking, after deleting one path, or before the row delete leaves the row in
`upload_reclaim_marked`; the next sweep's Phase 2b re-selects it and completes — the row and its ciphertext
are never pinned. `FOR UPDATE SKIP LOCKED` keeps two concurrent workers off the same row. Crash gates
required after marking, after each Files delete, and before the row delete (dev double + real adapter, one
shared conformance suite per §I).

## Invariant recap (every non-terminal state is recoverable)
- `uploading` → finalize (exactly-one-row) OR Phase-2a mark. `upload_reclaim_marked` → Phase-2b recovery → deleted.
- `finalized`/`orphaned` (unreferenced, past horizon) → Path-1 `reclaim_marked`. `reclaim_marked` → idempotent
  quarantine recovery (v4 §O Path-1 tail). `quarantined` → Path-3 grace hard-delete.
- `committed` (live) → protected by the publish `FOR UPDATE` lock; only leaves to `orphaned` via §N under lock.
- claim `pending` → flush(recover) or expire+detach; `flushed` terminal-durable; `expired` terminal-tombstone.
No state is a dead end; every intermediate state has exactly one idempotent recovery selector.

## Finding trace
N1 → §O Phase-2b recovery selector + confirmed-absent-before-row-delete + crash gates.
