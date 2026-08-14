# GLY-346 spec v3 — control-plane state machine + ordering (supersedes v2 §2/§3/§5)

v2's control-plane-primary ARCHITECTURE is validated (sol re-check: "the two-substrate design can preserve
N4 without a distributed transaction, but only after the control-plane row precedes Files work, all
transitions serialize on that row, and divergence is fail-closed"). v2 resolved F3/F6/F8/F9/F10/F11. This v3
nails the 9 remaining findings (B1–B9) with an exact state machine, write-ordering, addressability, and
type fixes, all bound to the FROZEN core (`durable-reversal-store.ts`, unchanged). v2 §1 (topology), §4
(KeyProvider), §6 (smoke), §7 (cron), §8 (lanes), §9 (F1–F11 trace) still stand.

## A. Addressability — no replica-local tenant, globally-unique handles (B5)

The frozen port methods carry no tenant, so ALL durable addressing uses globally-unique keys:
- `mappingKey` and `idempotencyKey` are built by `keys.ts` as `\0`-joined strings that **embed `tenantId`**
  (`mappingKeyOf = tenant\0matter\0dictVer\0token`; `idempotencyKeyOf = tenant\0attempt\0token`) → globally
  unique across tenants. Tables key on the FULL string; `readCurrent(mappingKey)` / the idempotency claim
  need no external tenant.
- `PreparedWriteHandle` and `PublishedCommitHandle` are minted by the Azure volume as **UUIDs** (globally
  unique), stored with their row. `publish(prepared.handle)` and `flush(commit)` look the row up by the
  UUID; `tenant_id` + `mapping_key` + `idempotency_key` + `scope_digest` are COLUMNS on the prepared row
  (captured at `prepare` from its input), so remount needs no replica-local map.
- Constraints: `prepared_blob_id` PK (UUID, global); `reversal_claim.commit_handle` UNIQUE (global);
  `reversal_claim.prepared_blob_id` FK→`reversal_prepared`; `reversal_current.prepared_blob_id`
  FK→`reversal_prepared`; `reversal_claim` PK = `idempotency_key` (global); `reversal_current` PK =
  `mapping_key` (global). `tenant_id` retained as a column for indexing / row-level-security / least-auth.

## B. Schema v3 (types + states corrected)

```sql
reversal_dek_generation(dek_scope_key TEXT PK, tenant_id, matter_id, purpose, dek_generation_id,
  wrapped_dek BYTEA, created_at_ms BIGINT)                         -- dek_scope_key = tenant\0matter\0purpose (global)

reversal_nonce_counter(tenant_id, dek_generation_id, next_counter BIGINT NOT NULL DEFAULT 0,
  PRIMARY KEY (tenant_id, dek_generation_id))

reversal_prepared(prepared_blob_id UUID PRIMARY KEY, tenant_id, mapping_key, idempotency_key, scope_digest,
  staging_path TEXT, blob_path TEXT, created_at_ms BIGINT NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('uploading','finalized','committed','reclaim_marked','quarantined')))

reversal_claim(idempotency_key TEXT PRIMARY KEY, tenant_id, mapping_key, scope_digest,
  commit_handle UUID NOT NULL UNIQUE, prepared_blob_id UUID REFERENCES reversal_prepared(prepared_blob_id),
  ordinal BIGINT NOT NULL, created_at_ms BIGINT NOT NULL,
  expires_at_ms NUMERIC(20,0) NOT NULL,                            -- B6: matter = 2^64-1 needs NUMERIC, not BIGINT
  state TEXT NOT NULL CHECK (state IN ('pending','flushed','expired')))

reversal_current(mapping_key TEXT PRIMARY KEY, tenant_id, commit_handle UUID,
  prepared_blob_id UUID REFERENCES reversal_prepared(prepared_blob_id), ordinal BIGINT NOT NULL, flushed_at_ms BIGINT)

reversal_ordinal_seq(mapping_key TEXT PRIMARY KEY, tenant_id, next_ordinal BIGINT NOT NULL DEFAULT 1)
```
`expires_at_ms NUMERIC(20,0)` losslessly holds detector `createdAt+86_400_000` AND matter `2^64-1`
(`MATTER_EXPIRES_AT`); the `now >= expires_at` compare is `$now::numeric >= expires_at_ms` (B6). Detector
boundary + exactly-`2^64-1` oracles required.

## C. Write ordering — control-plane row BEFORE Files (B1)

`prepare(input)` (frozen sig returns `{handle}`):
1. `handle := uuid`; `blob_id := handle`; `staging := staging/<uuid>`; `blob_path := blobs/<blob_id>`.
2. **`INSERT reversal_prepared(blob_id, tenant, mapping_key, idempotency_key, scope_digest, staging, blob_path,
   created_at_ms, state='uploading')` FIRST** (control-plane knows the blob before it exists in Files).
3. Upload ciphertext to `staging`, flush (durable), **atomic rename `staging`→`blob_path`** (immutable).
4. `UPDATE reversal_prepared SET state='finalized' WHERE prepared_blob_id=blob_id AND state='uploading'`.
5. return `{handle}`.
A crash at any step leaves a durable `uploading`/`finalized` row → reclamation finds EVERY Files object via
its row (no orphan invisible to the control plane — B1). Reclamation of a stale `uploading` row deletes both
`staging` and `blob_path` idempotently.

## D. Publish — one transaction, winner-only prepared transition, serialized on the row (B2/B9)

`publish(prepared.handle)`:
1. `p := SELECT reversal_prepared WHERE prepared_blob_id=handle FOR UPDATE` (row lock — serializes vs
   maintenance). If `p.state NOT IN ('finalized','committed')` → fail closed (blob not durable).
2. `ord := UPDATE reversal_ordinal_seq .. RETURNING` (atomic; see F).
3. `INSERT reversal_claim(idempotency_key=p.idempotency_key, commit_handle=uuid, prepared_blob_id=handle,
   ordinal=ord, expires_at_ms=<from blob.meta>, state='pending', ...) ON CONFLICT (idempotency_key) DO NOTHING`.
4. **If inserted (WINNER):** `UPDATE reversal_prepared SET state='committed' WHERE prepared_blob_id=handle`;
   return `{kind:'published', commit: <new commit_handle>}`.
5. **If conflict (LOSER):** do NOT touch `p` (the loser's own `finalized` blob stays reclaimable — never
   pinned); `e := SELECT reversal_claim WHERE idempotency_key=p.idempotency_key`; return
   `{kind:'existing', commit: e.commit_handle, immutableScopeDigest: e.scope_digest,
   expired: computeExpired(e)}` — see E for `computeExpired` and the expired-pending transition.
Because maintenance only ever marks `state='finalized'` rows (D-lock excludes `committed`), and publish holds
`FOR UPDATE` on `p`, a blob referenced by a live claim can never be quarantined (B2/B4/B9 race closed).

## E. Claim state machine + expired-pending tombstone (B3) — bound to frozen core :161-181

The frozen core does: existing+scopeMismatch→throw(:164); existing+`expired`→throw(:168, non-retryable);
existing+!expired→`flush(existing.commit)`(:174, RECOVERY); new→`flush`(:180). So:
- **`computeExpired(claim)`** at publish-conflict:
  - `state='flushed'` & `now>=expires_at` → return `expired:true` (core throws; bytes GC'd later by matter-retention lifecycle). Pointer already durable — untouched.
  - `state='flushed'` & `now<expires_at` → `expired:false` → core re-`flush`es (idempotent no-op).
  - `state='pending'` & `now<expires_at` → `expired:false` → core `flush`es the existing commit = **completes the interrupted publish (recovery)**. Works because the pending claim's `prepared_blob_id`/`commit_handle` are intact.
  - `state='pending'` & `now>=expires_at` → **atomically transition** `state='pending'→'expired'`, set
    `prepared_blob_id=NULL` (DETACH the blob so it becomes reclaimable), **keep `expires_at` and the
    idempotency_key** (never reset the 24h window, never release the key); return `expired:true` (core throws,
    non-retryable). The detached blob's `reversal_prepared` row (state left `committed`/`finalized`) is now
    unreferenced by any claim/current → reclaimed past horizon. This is the B3 fix: no permanent pin, no
    fresh detector window, key stays claimed.
- **`state='expired'`** on any later retry → return `expired:true` (core throws). Stays non-retryable.
`flush(commit)` (frozen sig): `c := SELECT reversal_claim WHERE commit_handle=commit`; unknown → fail closed
(dev parity). **Verify the Files blob exists** (HEAD `blob_path`, check length/ETag) BEFORE the pointer
write (B4). One tx: `UPDATE reversal_claim SET state='flushed'`; `INSERT reversal_current(mapping_key,
commit_handle, prepared_blob_id, ordinal) ON CONFLICT (mapping_key) DO UPDATE SET ... WHERE
excluded.ordinal > reversal_current.ordinal` (CAS advance-only-if-higher; first insert always succeeds).

## F. Nonce — atomic, first-value 0, no reuse (B7)

```sql
INSERT INTO reversal_nonce_counter(tenant_id, dek_generation_id, next_counter) VALUES ($t,$g,1)
ON CONFLICT (tenant_id, dek_generation_id) DO UPDATE SET next_counter = reversal_nonce_counter.next_counter + 1
RETURNING next_counter - 1;
```
Insert arm returns `0` (stores 1); conflict arm returns prior value (stores prior+1). Monotonic, gaps allowed
(a lost commit-response = a skipped value, never a repeat), reuse impossible. Commit BEFORE returning the
nonce. Oracles: first-call=0, concurrent-replica strictly-increasing-distinct, rollback, ambiguous-commit.

## G. readCurrent integrity — pointer-without-blob is fail-closed, never a miss (B4)

`readCurrent(requests)`: `SELECT reversal_current WHERE mapping_key IN (...)`. For each hit, GET `blob_path`.
If the pointer row exists but the Files blob is **absent / quarantined / length-or-ETag mismatch** →
**throw** (integrity failure — the frozen `resolveEncounteredTokens` catch turns it into `REVERSAL_FAILED`,
fail-closed per addendum C2-availability; NEVER a silent absent-token). A mapping_key with no
`reversal_current` row IS a normal miss (absent from the partial map). Reconciliation NEVER silently deletes
or rolls back an acknowledged pointer; a divergence raises an alert/repair signal.

## H. Reclamation — exclusive claim, idempotent recovery (B5/B9)

```sql
-- claim ONLY finalized-and-unreferenced, exclusively:
UPDATE reversal_prepared SET state='reclaim_marked'
WHERE prepared_blob_id IN (
  SELECT prepared_blob_id FROM reversal_prepared
  WHERE state='finalized' AND created_at_ms < $olderThan
    AND prepared_blob_id NOT IN (SELECT prepared_blob_id FROM reversal_claim WHERE prepared_blob_id IS NOT NULL)
    AND prepared_blob_id NOT IN (SELECT prepared_blob_id FROM reversal_current WHERE prepared_blob_id IS NOT NULL)
  FOR UPDATE SKIP LOCKED LIMIT $limit)
RETURNING prepared_blob_id, blob_path, staging_path;
```
Only `finalized` rows are claimable (never `committed`/`uploading`/already-`reclaim_marked` — B9). Then per
marked row: rename `blob_path`→`reclaim-quarantine/<id>` (reversible — F10), `UPDATE state='quarantined'`. A
worker that died after mark, before rename → an already-`reclaim_marked` row is picked up by a SEPARATE
idempotent recovery transition that tolerates original/quarantine/missing source locations (no double-rename
failure). Stale `uploading` rows older than a longer horizon → delete both `staging` and `blob_path`,
`DELETE` the row. A separate later pass hard-deletes `reclaim-quarantine/*` older than the grace window.
**Input scrub (F6):** snapshot `{olderThanEpochMs, limit}` once; require finite safe-int; positive bounded
`limit`; reject NaN/±Inf/negative.

## I. Dev parity — one conformance suite, dev models the durable state machine (B8)

The GLY-346 dev double is a NEW in-memory control-plane that models durable-pending claims (a pending claim
SURVIVES replica-loss, unlike the L2.4 `in-memory-spool-volume.ts` crash() which deletes unflushed claims),
plus states uploading/finalized/committed/reclaim_marked/quarantined/pending/flushed/expired and the exact
conditional transitions above. ONE shared conformance suite runs against BOTH the dev double and the real
Postgres+Files adapter, with explicit phase gates for: publish-loss (pending survives), expired-pending
(tombstone+detach, no fresh window, key held), concurrent mark-vs-publish (row lock wins), mark-before-rename
crash (idempotent recovery), missing-current-blob (readCurrent fail-closed), nonce first-call/concurrent,
ordinal out-of-order flush (no rollback), matter expiry `2^64-1` (no overflow). Oracles that pass in dev
because dev deletes pending claims are VACUOUS — the shared suite + durable-pending dev model kill that
(B8; guard-moves-when-code-moves).

## J. Finding trace (B1–B9)
B1→§C row-before-Files+uploading state | B2→§D winner-only transition+FOR UPDATE | B3→§E expired-pending
tombstone+detach bound to core :168/:174 | B4→§E flush verifies blob + §G readCurrent fail-closed | B5→§A
global handles + tenant columns | B6→§B NUMERIC(20,0) | B7→§F insert=0 arm | B8→§I durable-pending dev +
shared conformance suite | B9→§H FOR UPDATE SKIP LOCKED, finalized-only, idempotent recovery.
