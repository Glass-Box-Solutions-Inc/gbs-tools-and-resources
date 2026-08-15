# GLY-346 spec v4 — state-machine closure (supersedes v3 §B/§E/§H)

v3 resolved B1/B2/B5/B6/B7/B8. v4 closes the 3 residuals (B3/B4/B9) and the 5 narrow findings they spawned
(D1–D5). All architecture (v2 §1/§4/§6/§7/§8) and v3 §A/§C/§D/§F/§G still stand. These are localized:
add two columns, one prepared state, and make flush + stale-upload cleanup lock-then-conditional.

## K. Prepared state set (finalized so every transition is exclusive & lock-guarded)

`reversal_prepared.state ∈ {uploading, finalized, committed, orphaned, upload_reclaim_marked, reclaim_marked, quarantined}`
```
uploading ──prepare ok──▶ finalized ──publish WINS──▶ committed ──expired-pending detach──▶ orphaned
    │                         │                                                                 │
    └─stale-upload reclaim─▶ upload_reclaim_marked      finalized/orphaned ──reclaim──▶ reclaim_marked ──▶ quarantined ──grace──▶ (deleted)
                              (Files+row deleted)
```
New columns on `reversal_prepared`: `blob_etag TEXT`, `blob_len BIGINT` (captured at finalize — D3),
`quarantined_at_ms BIGINT` (D5). New claim column semantics: `prepared_blob_id` is `NOT NULL` while claim
`state IN ('pending','flushed')`, `NULL` only when `state='expired'` (D2). `reversal_current` all pointer
columns `NOT NULL` (D2). `reversal_claim.state ∈ {pending, flushed, expired}`.

## L. finalize captures durable verification attributes (D3)

The `uploading→finalized` transition (v3 §C step 4) is: after the atomic rename `staging→blob_path`, **HEAD
`blob_path` to read its ETag + length**, then `UPDATE reversal_prepared SET state='finalized', blob_etag=$et,
blob_len=$len WHERE prepared_blob_id=$id AND state='uploading'` — and **require exactly ONE row affected**
before returning from `prepare` (D4: else a concurrent stale-upload reclaim won; abort/retry). Attributes are
read AFTER the final rename (rename may change the ETag). flush and readCurrent compare HEAD/GET results to
these durable `blob_etag`/`blob_len`; a mismatch is an integrity failure (throw). With no durable attributes
the check would be a vacuous existence test (D3) — this makes it real.

## M. flush — lock the claim row, conditional transitions only (B3/B4/D2)

`flush(commit)` in ONE serialized transaction:
1. `c := SELECT * FROM reversal_claim WHERE commit_handle=$commit FOR UPDATE`. Unknown → fail closed (dev parity).
2. **Conditional on `c.state` + expiry (all under the row lock):**
   - `flushed` → idempotent no-op success (re-flush of an already-durable commit).
   - `expired` → **fail closed** (never resurrect; the tombstone stands). [core would only reach flush here via a stale in-flight call — reject it.]
   - `pending` AND `$now >= c.expires_at_ms` → this is an expired-pending seen by flush: **atomically expire+detach** (run §N transition) and **fail closed** (do NOT publish an expired detector — D2). Never mark flushed.
   - `pending` AND `$now < c.expires_at_ms` → **the only path that publishes:** HEAD `blob_path`, verify it exists and `etag/len` match the stored `blob_etag/blob_len` (B4/D3) — mismatch/absent → fail closed; then `UPDATE reversal_claim SET state='flushed'`; `INSERT reversal_current(... prepared_blob_id=c.prepared_blob_id ...) ON CONFLICT (mapping_key) DO UPDATE SET ... WHERE excluded.ordinal > reversal_current.ordinal` (CAS). `prepared_blob_id` is guaranteed NON-NULL here (state=pending invariant), so the pointer never gets a NULL blob (D2).
Holding `FOR UPDATE` on the claim across verify + pointer-commit serializes flush against the §N expiry
transition (D2 race closed): expiry can't run while flush holds the lock, and vice-versa.

## N. Expired-pending transition — detach AND make the winner blob reclaimable (B3/D1)

When publish's conflict branch (v3 §E) OR flush (§M) sees `pending & now>=expires_at`, in ONE transaction:
1. `SELECT reversal_claim WHERE commit_handle FOR UPDATE` (serialize vs flush).
2. `p := SELECT reversal_prepared WHERE prepared_blob_id=c.prepared_blob_id FOR UPDATE`.
3. Verify NO `reversal_current` and NO OTHER `reversal_claim` references `p.prepared_blob_id` (the detector's
   pointer was never advanced — a pending claim never wrote `reversal_current`).
4. `UPDATE reversal_claim SET state='expired', prepared_blob_id=NULL WHERE commit_handle=$commit` (keep
   `expires_at_ms` and `idempotency_key` — never reset the 24h window, never release the key — B3).
5. `UPDATE reversal_prepared SET state='orphaned' WHERE prepared_blob_id=$id` (D1 — the winner's committed
   blob is now explicitly reclaimable; §O claims `orphaned` too, so it is NOT pinned forever).
Return `expired:true` (core throws non-retryable at durable-reversal-store.ts:168). A later retry sees
`state='expired'` → `expired:true` → core throws. Non-expired pending recovery is unchanged (core flushes the
existing commit at :174 via §M's publish path).

## O. Reclamation — exclusive lock for BOTH finalized-orphan AND stale-upload paths (B9/D1/D4/D5)

**Path 1 — finalized/orphaned unreferenced blobs (past horizon):**
```sql
UPDATE reversal_prepared SET state='reclaim_marked'
WHERE prepared_blob_id IN (
  SELECT prepared_blob_id FROM reversal_prepared
  WHERE state IN ('finalized','orphaned') AND created_at_ms < $olderThan
    AND prepared_blob_id NOT IN (SELECT prepared_blob_id FROM reversal_claim WHERE prepared_blob_id IS NOT NULL)
    AND prepared_blob_id NOT IN (SELECT prepared_blob_id FROM reversal_current)
  FOR UPDATE SKIP LOCKED LIMIT $limit)
RETURNING prepared_blob_id, blob_path;
```
Then per row: rename `blob_path`→`reclaim-quarantine/<id>`; `UPDATE state='quarantined',
quarantined_at_ms=$now` (D5 — authoritative clock, NOT source mtime). A worker that died after mark, before
rename → an already-`reclaim_marked` row is handled by an idempotent recovery transition tolerating
original/quarantine/missing source (no double-rename).

**Path 2 — stale `uploading` rows (past a LONGER upload-horizon) — lock-then-transition, not check-then-delete (D4):**
```sql
UPDATE reversal_prepared SET state='upload_reclaim_marked'
WHERE prepared_blob_id IN (
  SELECT prepared_blob_id FROM reversal_prepared
  WHERE state='uploading' AND created_at_ms < $uploadHorizon
  FOR UPDATE SKIP LOCKED LIMIT $limit)
RETURNING prepared_blob_id, staging_path, blob_path;
```
Then delete BOTH `staging_path` and `blob_path` (idempotent — either may be absent), `DELETE` the row. Because
prepare's `uploading→finalized` requires exactly-one-row-affected (§L) and this claims `state='uploading'`
exclusively via `FOR UPDATE SKIP LOCKED`, exactly one of {prepare-finalize, stale-upload-reclaim} wins; the
loser sees zero rows affected and aborts — a live/finalized blob can never be deleted (D4 race closed).

**Path 3 — grace hard-delete:** `SELECT ... WHERE state='quarantined' AND quarantined_at_ms < $now - $grace`
→ hard-delete `reclaim-quarantine/<id>`, `DELETE` row. Grace measured from `quarantined_at_ms` ONLY (D5).

## P. Finding trace (D1–D5 + residuals)
B3→§N (expired tombstone keeps key/expiry) + §M (flush conditional) | B4→§M (flush verifies blob+etag under
lock) + §G | B9→§O Path-1 exclusive | D1→§N step-5 winner blob→orphaned, §O claims orphaned | D2→§M claim-row
lock + conditional flush + NOT NULL invariants | D3→§L persist blob_etag/blob_len, compare on flush/read |
D4→§O Path-2 lock-then-transition + §L exactly-one-row | D5→§O quarantined_at_ms authoritative clock.
