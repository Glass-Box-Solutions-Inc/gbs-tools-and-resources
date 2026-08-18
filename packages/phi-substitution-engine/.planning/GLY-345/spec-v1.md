**Model: GPT-5.6-sol**

# GLY-345 specification v1 — durable operation-retention binding and supersede-aware retention

## 1. Status, authority, and normative language

1. This is a **T2 specification only**. It authorizes no implementation, deployment, commit, or source change.
2. Base is `main` at `2adef06`; implementation lane is `GLY-345-lane`.
3. The GLY-346 state-machine ground truth remains `.planning/GLY-346/spec-v2.md`, `spec-v4.md`, and
   `spec-v5.md`, with v3 sections incorporated where v4/v5 refer to them. This document changes only the
   retention binding and committed-record lifecycle described below.
4. `MUST`, `MUST NOT`, `SHOULD`, and `MAY` are normative.
5. Frozen public surfaces:
   - `ports.ts`: `SpoolVolume`, `PrepareReversalWriteInput`, `PublishReversalResult`, and all existing public
     method signatures remain byte-for-byte source compatible.
   - `DurableReversalStore` keeps the existing `ReversalWriteStore` public surface and constructor dependency
     shape. `classifyRetention` remains injected.
   - `SpoolMaintenance.reclaimOrphanedPrepared(input)` and its input/outcome types remain unchanged.
   - Additions are limited to internal control-plane inputs/rows/selectors, internal adapter options, durable
     schema, and dev-only inspection/fault hooks. Superseded selection is folded into existing Path 1; no new
     public maintenance path is required.
6. All request-path failures, including a retention-binding mismatch, exit `DurableReversalStore.record()` as
   a newly constructed `ReversalFailedError` with the existing fixed `REVERSAL_FAILED` surface, no `cause`, and
   no tenant/matter/attempt/token/class/provider/SQL/blob detail.

## 2. Goals and bounded threat model

### 2.1 Part A — operation-retention binding

The control plane MUST durably pin the first successfully anchored retention class for the exact operation key
`(tenantId, attemptId)`. Every later `record()` for that key, on any token, matter, process, or replica, MUST use
the pinned class or fail closed. A same-attempt retry after process death, an ambiguous response, or replica loss
MUST observe the same binding. The first successful binding is the transaction that commits both the binding row
and its `reversal_prepared(state='uploading')` row; invocation start time is not an ordering oracle.

This protects retention governance/TTL consistency against a trusted-but-misbehaving nondeterministic
`classifyRetention` seam. It is not a new PHI-egress defense: a mismatch is detected before Azure Files receives
the new blob, but nonce/key work may already have occurred and gaps remain allowed.

### 2.2 Part B — supersede-aware retention

When a new commit becomes `reversal_current` for an existing `mapping_key`, the prior committed prepared row
MUST atomically cease being current, become `superseded`, and lose all claim/current references. It becomes a
Path-1-analog reclamation candidate only when both of these are true:

1. its authenticated record retention has ended; and
2. the read-consistency drain window following supersession has ended.

The same terminalization applies to an out-of-order flush whose ordinal loses to an already-higher current
pointer: the losing prepared row becomes `superseded` in that flush transaction rather than remaining committed
forever.

### 2.3 Threat boundary

In scope: cross-replica races; transaction rollback/ambiguous commit; process death between DB and Files steps;
nondeterministic classifier output; out-of-order flush; retained old claims; in-flight readers holding a pointer
snapshot; maintenance concurrency; `NUMERIC(20,0)`/MaxUint64 boundaries; live-schema migration and replay.

Out of scope: a compromised PostgreSQL superuser, malicious mutation of JS intrinsics, KEK compromise, physical
Azure loss, retroactively reconstructing an authenticated record creation time from a blob that no longer
exists, and policy for finite matter expiration (the engine continues to consume the authenticated expiry it is
given).

## 3. Required invariants

1. **A-KEY:** the binding key is exactly tenant plus attempt, not tenant/attempt/token and not
   tenant/matter/attempt. The PostgreSQL representation is the existing injective `b64url-v1:` encoding of
   `UTF8(tenantId) || 0x00 || UTF8(attemptId)`; it is not a collision-bearing hash.
2. **A-FIRST:** at most one class (`matter` or `detector-only`) is durably bound per operation key. Equal-class
   replays are no-ops; different-class replays write neither a prepared row nor Files bytes.
3. **A-ATOMIC:** binding creation/verification and insertion of the attempt's `uploading` prepared row are one
   PostgreSQL transaction. A binding is never acknowledged without its first anchor, and an anchor never commits
   without its binding.
4. **A-DURABLE:** operation bindings are durable tombstones and are not reclaimed in GLY-345. Deleting a binding
   merely because all reversal blobs are gone would permit a late retry to change class.
5. **A-ERROR:** mismatch details never cross the fixed store error surface.
6. **B-CURRENT:** a `reversal_current` row references exactly one `reversal_prepared(state='committed')` row and
   exactly one `reversal_claim(state='flushed')` row with the same commit, mapping, prepared id, and ordinal.
7. **B-UNREFERENCED:** a prepared row in `finalized`, `orphaned`, or `superseded` has no
   `reversal_current.prepared_blob_id` reference and no non-null `reversal_claim.prepared_blob_id` reference.
   Every fresh and recovery Path-1 selector rechecks both `NOT EXISTS` predicates under lock.
8. **B-ATOMIC-SUPERSEDE:** pointer advance, new-claim completion, old-claim detachment, and old-prepared
   supersession commit or roll back together. No Files operation occurs in this transaction.
9. **B-CAS-LOSER:** a pending commit that loses the ordinal comparison completes idempotently as a superseded
   tombstone; it never becomes current and never remains a referenced committed blob.
10. **B-RETENTION:** `retention_expires_at_ms` and `reclaim_after_ms` are `NUMERIC(20,0)` in `[0, 2^64-1]`.
    `2^64-1` means never eligible. Detector-only records carry exactly authenticated
    `record_created_at_ms + 86_400_000`; matter records carry their authenticated matter expiry (currently
    `2^64-1`).
11. **B-READ:** no query beginning after the superseding transaction commits can receive the old pointer. A query
    that received the old pointer before commit gets a bounded drain interval while the original blob remains,
    followed by quarantine fallback during grace. It never observes the new pointer paired with old bytes or the
    old pointer paired with new bytes.
12. **B-QUARANTINE:** all Path-1 candidates, including superseded rows, are renamed to quarantine before any hard
    delete. Missing original plus missing quarantine is failure, not successful quarantine.
13. **B-BUDGET:** superseded work shares the existing single global mutation budget in this order: Path-1
    recovery, fresh Path-1 (`finalized`/`orphaned`/`superseded`), Path-2b, Path-2a, Path-3. It gets no private
    budget.
14. **B-RECOVERY:** every non-terminal state has an age-independent recovery selector after it has been claimed
    for cross-substrate work.
15. **IDEMPOTENCY:** existing `(tenant, attempt, token)` first-write-wins behavior, immutable-scope rejection,
    ordinal monotonicity, and non-retryable detector-expiry tombstones remain unchanged. Replaying a superseded
    claim is a successful no-op and cannot roll the pointer back.

## 4. Durable data model and exact migration delta

### 4.1 New metadata

- `reversal_operation_retention` is the durable Part-A binding table.
- `reversal_prepared.operation_key` points to the binding.
- `record_created_at_ms`, `retention_class`, and `retention_expires_at_ms` are copied from the authenticated
  encrypted-record metadata at the control-plane anchor. They are immutable thereafter.
- `superseded_at_ms` records the authoritative pointer transition time.
- `reclaim_after_ms = MAX(retention_expires_at_ms, superseded_at_ms + READ_DRAIN_MS)`, except MaxUint64 remains
  MaxUint64. It is immutable once set and remains present through `reclaim_marked` and `quarantined`.
- `reversal_claim.state` gains terminal tombstone `superseded`; like `expired`, it has
  `prepared_blob_id = NULL`.

`READ_DRAIN_MS` is normatively `60_000` in production. Tests MAY inject a smaller non-negative value through an
internal-only option. Production `RECLAIM_GRACE_MS` MUST be at least `READ_DRAIN_MS`; the current 24-hour default
satisfies this.

### 4.2 Migration execution contract

The delta below MUST be appended to `migrations/0001_phi_reversal_control_plane.sql`, because the existing
`runMigrations()` reads that file as one PostgreSQL transaction. It is additive with respect to stored data:
new table/columns/indexes are added, legacy rows are backfilled, and old checks are replaced only to widen the
state machine while retaining prior predicates. It deletes no row or blob. Running it twice MUST succeed and
produce the same rows and constraints. Any malformed encoded key, mixed historical operation class, or broken
current-pointer invariant raises and rolls back the whole migration.

```sql
-- GLY-345 additive delta. This file is already run inside one BEGIN/COMMIT by runMigrations().
CREATE TABLE IF NOT EXISTS reversal_operation_retention (
  operation_key TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  retention_class TEXT NOT NULL,
  bound_at_ms BIGINT NOT NULL,
  CONSTRAINT reversal_operation_retention_class_check
    CHECK (retention_class IN ('matter', 'detector-only')),
  CONSTRAINT reversal_operation_retention_bound_at_check CHECK (bound_at_ms >= 0)
);

ALTER TABLE reversal_prepared ADD COLUMN IF NOT EXISTS operation_key TEXT;
ALTER TABLE reversal_prepared ADD COLUMN IF NOT EXISTS record_created_at_ms BIGINT;
ALTER TABLE reversal_prepared ADD COLUMN IF NOT EXISTS retention_class TEXT;
ALTER TABLE reversal_prepared ADD COLUMN IF NOT EXISTS retention_expires_at_ms NUMERIC(20,0);
ALTER TABLE reversal_prepared ADD COLUMN IF NOT EXISTS superseded_at_ms BIGINT;
ALTER TABLE reversal_prepared ADD COLUMN IF NOT EXISTS reclaim_after_ms NUMERIC(20,0);

-- The current anonymous checks have these PostgreSQL-generated names in 0001. Drop only the checks
-- that must be widened. Re-adding under the same names makes reruns deterministic.
ALTER TABLE reversal_prepared DROP CONSTRAINT IF EXISTS reversal_prepared_state_check;
ALTER TABLE reversal_prepared DROP CONSTRAINT IF EXISTS reversal_prepared_check;
ALTER TABLE reversal_prepared DROP CONSTRAINT IF EXISTS reversal_prepared_retention_check;
ALTER TABLE reversal_prepared DROP CONSTRAINT IF EXISTS reversal_prepared_supersession_check;
ALTER TABLE reversal_prepared DROP CONSTRAINT IF EXISTS reversal_prepared_operation_fk;
ALTER TABLE reversal_claim DROP CONSTRAINT IF EXISTS reversal_claim_state_check;
ALTER TABLE reversal_claim DROP CONSTRAINT IF EXISTS reversal_claim_check;

-- Validate and decode legacy b64url-v1:(tenant NUL attempt NUL token) keys. A bad legacy key is
-- migration-fatal; guessing an operation boundary would weaken the binding.
DO $$
BEGIN
  IF EXISTS (
    WITH decoded AS (
      SELECT prepared_blob_id,
             decode(
               translate(substr(idempotency_key, 11), '-_', '+/') ||
               repeat('=', (4 - length(substr(idempotency_key, 11)) % 4) % 4),
               'base64'
             ) AS raw_key
      FROM reversal_prepared
      WHERE operation_key IS NULL
        AND left(idempotency_key, 10) = 'b64url-v1:'
    ), fenced AS (
      SELECT prepared_blob_id, raw_key,
             position(decode('00', 'hex') IN raw_key) AS first_fence
      FROM decoded
    )
    SELECT 1
    FROM reversal_prepared p
    LEFT JOIN fenced f USING (prepared_blob_id)
    WHERE p.operation_key IS NULL
      AND (
        left(p.idempotency_key, 10) <> 'b64url-v1:' OR
        f.first_fence IS NULL OR f.first_fence = 0 OR
        position(
          decode('00', 'hex') IN substring(f.raw_key FROM f.first_fence + 1)
        ) = 0
      )
  ) THEN
    RAISE EXCEPTION 'gly345_invalid_legacy_idempotency_key';
  END IF;
END $$;

WITH decoded AS (
  SELECT prepared_blob_id,
         decode(
           translate(substr(idempotency_key, 11), '-_', '+/') ||
           repeat('=', (4 - length(substr(idempotency_key, 11)) % 4) % 4),
           'base64'
         ) AS raw_key
  FROM reversal_prepared
  WHERE operation_key IS NULL
), fenced AS (
  SELECT prepared_blob_id, raw_key,
         position(decode('00', 'hex') IN raw_key) AS first_fence
  FROM decoded
), operation_bytes AS (
  SELECT prepared_blob_id,
         substring(
           raw_key FROM 1 FOR
           first_fence + position(
             decode('00', 'hex') IN substring(raw_key FROM first_fence + 1)
           ) - 1
         ) AS raw_operation_key
  FROM fenced
)
UPDATE reversal_prepared p
SET operation_key = 'b64url-v1:' || rtrim(
  translate(
    replace(replace(encode(o.raw_operation_key, 'base64'), E'\n', ''), E'\r', ''),
    '+/', '-_'
  ),
  '='
)
FROM operation_bytes o
WHERE p.prepared_blob_id = o.prepared_blob_id;

DO $$
BEGIN
  IF EXISTS (
    SELECT operation_key
    FROM reversal_prepared
    GROUP BY operation_key
    HAVING count(DISTINCT tenant_id) <> 1
  ) THEN
    RAISE EXCEPTION 'gly345_operation_key_tenant_mismatch';
  END IF;

  IF EXISTS (
    SELECT p.operation_key
    FROM reversal_prepared p
    JOIN reversal_claim c ON c.idempotency_key = p.idempotency_key
    GROUP BY p.operation_key
    HAVING count(DISTINCT CASE
      WHEN c.expires_at_ms = 18446744073709551615::numeric THEN 'matter'
      ELSE 'detector-only'
    END) <> 1
  ) THEN
    RAISE EXCEPTION 'gly345_mixed_legacy_operation_retention';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM reversal_claim c
    WHERE c.expires_at_ms <> 18446744073709551615::numeric
      AND c.expires_at_ms < 86400000::numeric
  ) THEN
    RAISE EXCEPTION 'gly345_invalid_legacy_detector_expiry';
  END IF;
END $$;

-- Claimed rows carry the historical authenticated expiry. Seed those bindings first.
INSERT INTO reversal_operation_retention (
  operation_key, tenant_id, retention_class, bound_at_ms
)
SELECT p.operation_key,
       min(p.tenant_id),
       CASE
         WHEN c.expires_at_ms = 18446744073709551615::numeric THEN 'matter'
         ELSE 'detector-only'
       END,
       min(p.created_at_ms)
FROM reversal_prepared p
JOIN reversal_claim c ON c.idempotency_key = p.idempotency_key
GROUP BY p.operation_key,
         CASE
           WHEN c.expires_at_ms = 18446744073709551615::numeric THEN 'matter'
           ELSE 'detector-only'
         END
ON CONFLICT (operation_key) DO NOTHING;

-- Unclaimed legacy uploads/finalized losers have no SQL-visible authenticated expiry. If no claimed
-- sibling exists, bind fail-safe to matter (longer retention, never premature deletion).
INSERT INTO reversal_operation_retention (
  operation_key, tenant_id, retention_class, bound_at_ms
)
SELECT p.operation_key, min(p.tenant_id), 'matter', min(p.created_at_ms)
FROM reversal_prepared p
LEFT JOIN reversal_operation_retention b ON b.operation_key = p.operation_key
WHERE b.operation_key IS NULL
GROUP BY p.operation_key
ON CONFLICT (operation_key) DO NOTHING;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM reversal_prepared p
    JOIN reversal_claim c ON c.idempotency_key = p.idempotency_key
    JOIN reversal_operation_retention b ON b.operation_key = p.operation_key
    WHERE b.retention_class <> CASE
      WHEN c.expires_at_ms = 18446744073709551615::numeric THEN 'matter'
      ELSE 'detector-only'
    END
  ) THEN
    RAISE EXCEPTION 'gly345_binding_conflicts_with_legacy_claim';
  END IF;
END $$;

WITH historical AS (
  SELECT p.prepared_blob_id,
         b.retention_class AS bound_class,
         c.expires_at_ms AS claim_expiry,
         p.created_at_ms AS control_created_at_ms
  FROM reversal_prepared p
  JOIN reversal_operation_retention b ON b.operation_key = p.operation_key
  LEFT JOIN reversal_claim c ON c.idempotency_key = p.idempotency_key
)
UPDATE reversal_prepared p
SET retention_class = h.bound_class,
    record_created_at_ms = CASE
      WHEN h.claim_expiry IS NOT NULL
       AND h.claim_expiry <> 18446744073709551615::numeric
        THEN (h.claim_expiry - 86400000::numeric)::bigint
      ELSE h.control_created_at_ms
    END,
    retention_expires_at_ms = CASE
      WHEN h.claim_expiry IS NOT NULL THEN h.claim_expiry
      WHEN h.bound_class = 'detector-only'
        THEN h.control_created_at_ms::numeric + 86400000::numeric
      ELSE 18446744073709551615::numeric
    END
FROM historical h
WHERE p.prepared_blob_id = h.prepared_blob_id
  AND (
    p.retention_class IS NULL OR
    p.record_created_at_ms IS NULL OR
    p.retention_expires_at_ms IS NULL
  );

-- Validate the pre-GLY-345 pointer/claim relation before converting old non-current flushed rows.
DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM reversal_current cur
    LEFT JOIN reversal_claim c ON c.commit_handle = cur.commit_handle
    LEFT JOIN reversal_prepared p ON p.prepared_blob_id = cur.prepared_blob_id
    WHERE c.commit_handle IS NULL
       OR c.state <> 'flushed'
       OR c.prepared_blob_id IS DISTINCT FROM cur.prepared_blob_id
       OR c.mapping_key <> cur.mapping_key
       OR c.ordinal <> cur.ordinal
       OR p.prepared_blob_id IS NULL
       OR p.state <> 'committed'
  ) THEN
    RAISE EXCEPTION 'gly345_invalid_legacy_current_invariant';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM reversal_claim c
    LEFT JOIN reversal_current cur ON cur.mapping_key = c.mapping_key
    LEFT JOIN reversal_prepared p ON p.prepared_blob_id = c.prepared_blob_id
    WHERE c.state = 'flushed'
      AND (
        cur.mapping_key IS NULL OR
        p.prepared_blob_id IS NULL OR
        p.state <> 'committed' OR
        cur.ordinal < c.ordinal
      )
  ) THEN
    RAISE EXCEPTION 'gly345_invalid_legacy_flushed_invariant';
  END IF;
END $$;

WITH legacy_superseded AS (
  SELECT p.prepared_blob_id,
         cur.flushed_at_ms AS superseded_at_ms,
         CASE
           WHEN p.retention_expires_at_ms = 18446744073709551615::numeric
             THEN 18446744073709551615::numeric
           ELSE greatest(
             p.retention_expires_at_ms,
             cur.flushed_at_ms::numeric + 60000::numeric
           )
         END AS reclaim_after_ms
  FROM reversal_claim c
  JOIN reversal_prepared p ON p.prepared_blob_id = c.prepared_blob_id
  JOIN reversal_current cur ON cur.mapping_key = c.mapping_key
  WHERE c.state = 'flushed'
    AND cur.prepared_blob_id <> c.prepared_blob_id
    AND cur.ordinal > c.ordinal
    AND p.state = 'committed'
)
UPDATE reversal_prepared p
SET state = 'superseded',
    superseded_at_ms = s.superseded_at_ms,
    reclaim_after_ms = s.reclaim_after_ms
FROM legacy_superseded s
WHERE p.prepared_blob_id = s.prepared_blob_id;

UPDATE reversal_claim c
SET state = 'superseded', prepared_blob_id = NULL
FROM reversal_prepared p
WHERE c.prepared_blob_id = p.prepared_blob_id
  AND c.state = 'flushed'
  AND p.state = 'superseded';

ALTER TABLE reversal_prepared ALTER COLUMN operation_key SET NOT NULL;
ALTER TABLE reversal_prepared ALTER COLUMN record_created_at_ms SET NOT NULL;
ALTER TABLE reversal_prepared ALTER COLUMN retention_class SET NOT NULL;
ALTER TABLE reversal_prepared ALTER COLUMN retention_expires_at_ms SET NOT NULL;

ALTER TABLE reversal_prepared ADD CONSTRAINT reversal_prepared_operation_fk
  FOREIGN KEY (operation_key) REFERENCES reversal_operation_retention(operation_key);

ALTER TABLE reversal_prepared ADD CONSTRAINT reversal_prepared_state_check CHECK (
  state IN (
    'uploading', 'finalized', 'committed', 'superseded', 'orphaned',
    'upload_reclaim_marked', 'reclaim_marked', 'quarantined'
  )
);

ALTER TABLE reversal_prepared ADD CONSTRAINT reversal_prepared_check CHECK (
  (state IN ('uploading', 'upload_reclaim_marked') AND blob_etag IS NULL AND blob_len IS NULL)
  OR
  (state IN (
     'finalized', 'committed', 'superseded', 'orphaned', 'reclaim_marked', 'quarantined'
   ) AND blob_etag IS NOT NULL AND blob_len IS NOT NULL)
);

ALTER TABLE reversal_prepared ADD CONSTRAINT reversal_prepared_retention_check CHECK (
  record_created_at_ms >= 0
  AND retention_class IN ('matter', 'detector-only')
  AND retention_expires_at_ms BETWEEN 0::numeric AND 18446744073709551615::numeric
  AND (
    retention_class = 'matter'
    OR retention_expires_at_ms = record_created_at_ms::numeric + 86400000::numeric
  )
  AND (
    reclaim_after_ms IS NULL
    OR reclaim_after_ms BETWEEN 0::numeric AND 18446744073709551615::numeric
  )
);

ALTER TABLE reversal_prepared ADD CONSTRAINT reversal_prepared_supersession_check CHECK (
  (
    state = 'superseded'
    AND superseded_at_ms IS NOT NULL
    AND superseded_at_ms >= 0
    AND reclaim_after_ms IS NOT NULL
  )
  OR
  (
    state IN ('reclaim_marked', 'quarantined')
    AND (
      (superseded_at_ms IS NULL AND reclaim_after_ms IS NULL)
      OR
      (superseded_at_ms IS NOT NULL AND superseded_at_ms >= 0 AND reclaim_after_ms IS NOT NULL)
    )
  )
  OR
  (
    state NOT IN ('superseded', 'reclaim_marked', 'quarantined')
    AND superseded_at_ms IS NULL
    AND reclaim_after_ms IS NULL
  )
);

ALTER TABLE reversal_claim ADD CONSTRAINT reversal_claim_state_check
  CHECK (state IN ('pending', 'flushed', 'expired', 'superseded'));

ALTER TABLE reversal_claim ADD CONSTRAINT reversal_claim_check CHECK (
  (state IN ('expired', 'superseded') AND prepared_blob_id IS NULL)
  OR
  (state IN ('pending', 'flushed') AND prepared_blob_id IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS reversal_operation_retention_tenant_idx
  ON reversal_operation_retention (tenant_id);
CREATE INDEX IF NOT EXISTS reversal_prepared_operation_idx
  ON reversal_prepared (operation_key);
CREATE INDEX IF NOT EXISTS reversal_prepared_superseded_reclaim_idx
  ON reversal_prepared (reclaim_after_ms, prepared_blob_id)
  WHERE state = 'superseded';
CREATE UNIQUE INDEX IF NOT EXISTS reversal_claim_prepared_unique_idx
  ON reversal_claim (prepared_blob_id)
  WHERE prepared_blob_id IS NOT NULL;
```

Fresh code MUST reject a new prepared anchor unless its metadata satisfies the same class/expiry checks before
issuing SQL. The database constraints are defense in depth, not the primary error-scrubbing boundary.

## 5. Part A protocol — exact transaction placement

### 5.1 Internal input only

`AzureFilesSpoolVolume.prepare()` extracts `attemptId`, `retentionClass`, `createdAtEpochMs`, and
`expiresAtEpochMs` from `input.encryptedRecord.meta` and supplies them to the internal
`ControlPlane.insertPreparedUploading` input. No field is added to `PrepareReversalWriteInput` or any frozen
port. The control plane computes `operation_key` from the tenant and attempt; callers cannot supply an arbitrary
pre-encoded binding key.

### 5.2 Anchor transaction

`insertPreparedUploading` becomes one transaction:

1. Snapshot and validate all internal input once. Require a non-empty tenant/attempt, recognized class,
   non-negative safe-integer record creation time, uint64 expiry, exact detector TTL, and matter expiry as
   supplied by the authenticated record.
2. `INSERT reversal_operation_retention(operation_key, tenant_id, retention_class, bound_at_ms=DB_NOW)
   ON CONFLICT (operation_key) DO NOTHING`. PostgreSQL's unique-index conflict wait serializes replicas.
3. `SELECT tenant_id, retention_class FROM reversal_operation_retention WHERE operation_key=$1 FOR SHARE`.
   Missing row, tenant mismatch, or class mismatch throws. A different class never updates the winner.
4. `INSERT reversal_prepared(... operation_key, record_created_at_ms, retention_class,
   retention_expires_at_ms, state='uploading', created_at_ms=DB_NOW)`. Require exactly one row.
5. Commit, then and only then upload to `staging/` and continue the unchanged finalize protocol.

If step 4 fails, steps 2–4 roll back, so a bare binding is not created by a failed first anchor. Once any anchor
commits, its binding remains even if the upload crashes and the `uploading` row is later reclaimed.

### 5.3 Dev-double mirror

Both dev substrates used by tests (`dev/in-memory-control-plane.ts` and the legacy
`dev/in-memory-spool-volume.ts` where it remains a direct `SpoolVolume`) MUST hold a durable
`Map<tenant NUL attempt, retentionClass>`. The map survives `crash()`. Their `prepare()` operation atomically
checks/inserts the binding with creation of the uploading/prepared model row; injected faults before commit mutate
neither, and faults after commit preserve both. Debug access may reveal identifiers only in test builds and is not
added to a public export.

## 6. Part B protocol — serialized pointer completion

### 6.1 Lock order and transaction clock

All flushes for one mapping MUST use `reversal_ordinal_seq` as the mapping mutex. The universal order is:

1. begin; read the claim without a lock only to learn immutable `mapping_key`;
2. lock `reversal_ordinal_seq(mapping_key) FOR UPDATE`;
3. re-read and lock the subject claim `FOR UPDATE`, verifying its mapping did not change;
4. lock `reversal_current(mapping_key) FOR UPDATE` if present;
5. lock required prepared rows and, for an advance, the old claim row;
6. execute state/pointer writes and commit.

Publish MUST use the same mapping-mutex-before-prepared ordering after a non-locking prepared lookup, preventing
a same-handle `publish`/`flush` deadlock. Expiry/detach paths that never acquire the mapping mutex may finish
while a flush waits, but they do not wait back on that mutex. Capture one authoritative transaction time
`tx_now_ms` and use it for expiry comparison, `flushed_at_ms`, `superseded_at_ms`, and reclaim-after calculation.

Blob HEAD/ETag/length verification remains before the control-plane transaction. No network operation is held
inside the transaction.

### 6.2 Conditional completion

After locking:

- `claim.state='expired'`: fail closed; never resurrect.
- `claim.state='superseded'`: direct `flush` is idempotent success. The tombstone proves the historical attempt
  completed but can no longer change current. On a `publish` conflict, the existing `expires_at_ms` is still
  compared: an expired detector returns `expired:true` exactly as it did while flushed; an unexpired/matter
  replay reaches the no-op flush. Supersession never refreshes the detector window.
- `claim.state='flushed'`: idempotent success only if current still references the same commit/prepared/ordinal.
  A non-current flushed claim is an invariant failure after the migration; do not silently return.
- `claim.state='pending' AND tx_now >= expires_at`: perform the existing atomic
  pending-to-expired/detach and committed-to-orphaned transition, then fail closed after commit.
- `claim.state='pending' AND unexpired`: verify the prepared row is `committed` and the supplied HEAD attributes
  match, then compare ordinals under the mapping mutex.

For an absent current row, insert the new pointer and set the new claim to `flushed` in the same transaction.

For `new.ordinal > current.ordinal`:

1. require the old current's claim is `flushed` and its prepared row is `committed`;
   the partial unique index proves no second non-null claim can reference that prepared row;
2. update the new claim `pending -> flushed`;
3. CAS-update current to the new commit/prepared/ordinal with `flushed_at_ms=tx_now_ms`;
4. update the old claim `flushed -> superseded, prepared_blob_id=NULL`;
5. update the old prepared `committed -> superseded`, set `superseded_at_ms=tx_now_ms`, and set
   `reclaim_after_ms` as defined in §4.1;
6. require one affected row for every transition and commit.

For `new.ordinal <= current.ordinal`, current is unchanged; update the new claim directly
`pending -> superseded, prepared_blob_id=NULL` and its prepared row `committed -> superseded` with the same
timestamps. `flush()` returns success after commit. This closes the out-of-order loser leak.

The implementation MUST NOT retain the current one-statement pointer upsert if it cannot return and lock the old
pointer/claim/prepared identities. The mapping mutex plus explicit compare/update is the required CAS.

The internal flush preflight must also stop assuming every idempotent commit still has a blob. Internally,
`readClaimBlobReference` becomes a discriminated result: `{kind:'blob', path, etag, length}` for pending/flushed,
or `{kind:'superseded'}` for the terminal superseded tombstone. Unknown/expired/inconsistent remains failure.
`AzureFilesSpoolVolume.flush()` skips HEAD for `superseded` and returns success; for `blob` it preserves current
HEAD verification and calls the transactional completion. This is an internal control-plane change only and does
not alter the frozen `SpoolVolume.flush(commit)` signature.

## 7. Exact state machines

### 7.1 Prepared-record transition table

| From | Event | Guard while locked | To | Transaction/cross-substrate boundary | Recovery selector |
|---|---|---|---|---|---|
| absent | anchor prepare | operation binding absent/equal; valid metadata; unique UUID | `uploading` | binding + prepared insert in one PG tx; no Files bytes yet | writer by handle; otherwise Path-2a after upload horizon |
| `uploading` | finalize | final blob exists; post-rename ETag/length valid; exactly one row | `finalized` | Files staging→blob first; conditional PG update second | writer retry; Path-2a if stale |
| `uploading` | stale-upload claim | older than upload horizon; row lock won | `upload_reclaim_marked` | PG tx | Path-2b, age-independent |
| `upload_reclaim_marked` | complete stale cleanup | staging and final paths both confirmed absent | absent/deleted | Files deletes first; PG row delete second | Path-2b until row deletion commits |
| `finalized` | winning publish | binding/expiry consistent; idempotency insert wins | `committed` | claim insert + prepared transition in one PG tx | pending-claim replay/flush/expiry |
| `finalized` | Path-1 fresh claim | `created_at_ms < olderThan`; no claim/current reference | `reclaim_marked` | PG tx | Path-1 recovery, age-independent |
| `committed` | pending expiry detach | subject pending claim expired; no current/other reference | `orphaned` | claim→expired/null + prepared transition in one PG tx | Path-1 after ordinary horizon |
| `committed` | higher ordinal advances current | old claim/pointer/prepared exact-match; all row counts one | `superseded` | same PG tx as new flushed claim and pointer CAS | fresh Path-1 after `reclaim_after_ms` |
| `committed` | own ordinal loses current CAS | subject claim pending; current ordinal is greater/equal | `superseded` | claim→superseded/null + prepared transition in same PG tx | fresh Path-1 after `reclaim_after_ms` |
| `orphaned` | Path-1 fresh claim | ordinary horizon passed; no references | `reclaim_marked` | PG tx | Path-1 recovery |
| `superseded` | Path-1 fresh claim | `reclaim_after_ms != MaxUint64`; `tx_now >= reclaim_after_ms`; no references | `reclaim_marked` | PG tx | Path-1 recovery |
| `reclaim_marked` | quarantine complete | destination exists with expected length; original absent; no references | `quarantined` | idempotent Files rename/verification first; PG timestamp update second | Path-1 recovery before DB update; Path-3 afterward |
| `quarantined` | grace hard-delete | `quarantined_at_ms + grace <= tx_now`; no references | absent/deleted | quarantine delete+absence proof first; PG row delete second | Path-3 until row deletion commits |

No other prepared transition is legal. In particular: `committed` is never directly selected by maintenance;
`superseded` never returns to committed/current; `reclaim_marked` recovery ignores age but never ignores
references; and no state hard-deletes the original blob without quarantine except stale incomplete uploads.

### 7.2 Claim transition table

| From | Event/guard | To | Prepared/pointer effect | Idempotent replay |
|---|---|---|---|---|
| absent | publish idempotency insert wins | `pending` | prepared `finalized -> committed`; pointer unchanged | conflict returns existing commit |
| `pending` | unexpired flush; no current or higher than current | `flushed` | pointer becomes this commit; prior current atomically superseded if any | `flushed` validates exact current then succeeds |
| `pending` | unexpired flush; ordinal loses | `superseded` with null prepared | own prepared becomes superseded; pointer unchanged | succeeds without pointer mutation |
| `pending` | expiry boundary reached | `expired` with null prepared | prepared becomes orphaned; pointer must not reference it | publish reports expired; flush fails fixed-surface |
| `flushed` | higher commit advances same mapping | `superseded` with null prepared | old prepared becomes superseded; pointer becomes new | succeeds without pointer mutation |
| `flushed` | same commit replay and exact current match | `flushed` | none | succeeds |
| `superseded` | unexpired/matter same-attempt replay | `superseded` | none | publish returns existing; no-blob flush succeeds and cannot roll back |
| `superseded` | detector replay at/after original expiry | `superseded` | none | publish returns `expired:true`; fixed non-retryable failure, window not refreshed |
| `expired` | any same-attempt replay | `expired` | none | non-retryable failure |

`expired` and `superseded` are durable terminal tombstones. Neither releases the idempotency key.

### 7.3 Operation-binding state

| Existing binding | Candidate class | Result |
|---|---|---|
| absent | valid matter/detector | insert binding atomically with first uploading row |
| same | same | keep binding; insert uploading row |
| same | different/invalid | rollback prepared insertion and fail fixed-surface |

There is no binding deletion transition in this ticket.

## 8. Retention selection, reader consistency, and quarantine

### 8.1 Path-1 predicate and ordering

The internal `ReclaimQueryInput`/preview input gains required `nowEpochMilliseconds` (internal only). The Path-1
candidate predicate becomes:

```sql
p.state = 'reclaim_marked'
OR (p.state IN ('finalized', 'orphaned') AND p.created_at_ms < $olderThan)
OR (
  p.state = 'superseded'
  AND p.reclaim_after_ms <> 18446744073709551615::numeric
  AND p.reclaim_after_ms <= $now::numeric
)
```

Every arm is additionally guarded by both existing `NOT EXISTS` reference predicates. Order recovery first,
then due fresh candidates by the effective deadline (`created_at_ms` for finalized/orphaned,
`reclaim_after_ms` for superseded), then `prepared_blob_id`. The transaction locks with
`FOR UPDATE OF p SKIP LOCKED LIMIT $remaining` and conditionally changes only fresh candidates to
`reclaim_marked`. Preview uses the identical predicate/order but no locks/mutations. Referenced candidates retain
the existing independently capped `skippedReferenced` accounting and do not consume mutation budget.

### 8.2 Read-consistency window

PostgreSQL statement snapshot semantics define the handoff:

1. `readCurrentPointers` either sees the old pointer before the superseding transaction commits or the new
   pointer after commit, never a half-transition.
2. The old original blob cannot be selected for quarantine until both retention and
   `superseded_at_ms + READ_DRAIN_MS` have passed. No post-commit reader can newly acquire it.
3. `AzureFilesSpoolVolume.readCurrent` MUST bound pointer-to-bytes completion to `READ_DRAIN_MS`. Before that
   deadline it reads the original path and validates the persisted ETag/length as today.
4. If original-path lookup races the quarantine rename, the adapter performs bounded
   original→quarantine→original probing. Quarantine fallback is derived only from the prepared UUID, requires
   exact stored byte length, decodes the immutable envelope, and relies on the existing AAD byte comparison and
   GCM authentication before plaintext is returned. It never treats both locations absent as a normal miss.
5. `graceMs >= READ_DRAIN_MS` is constructor/startup validation. Thus quarantine retains a full additional read
   window after `quarantined_at_ms`; Path 3 cannot hard-delete bytes needed by a valid in-flight old-pointer read.

This is a bounded read lease without durable reader rows. A read exceeding its deadline fails closed with
`REVERSAL_FAILED`; it does not justify retaining blobs without bound.

### 8.3 Quarantine completion strengthening

For all Path-1 rows, maintenance may set `quarantined` only after one of these is proven:

- original was renamed and destination HEAD reports the expected length; or
- recovery finds destination already present with expected length and confirms original absent.

If both are absent, lengths disagree, or original remains after recovery removal, leave `reclaim_marked` and fail
the sweep. Path-1's age-independent recovery retries. Quarantine is never equated with hard delete.

## 9. Failure and crash matrix

| Gate | Durable observation after crash/failure | Required next action/selector |
|---|---|---|
| classifier throws/returns unknown before anchor | no binding/prepared/blob from this call | fixed `REVERSAL_FAILED`; caller may retry |
| anchor tx before binding insert | no change | retry prepare |
| after binding statement, before prepared insert/commit | transaction rollback removes binding | retry; competing successful tx may become first |
| after prepared insert, before anchor commit | binding and prepared both roll back | retry |
| anchor commit response lost | binding + `uploading` row durable | same-class retry allowed; stale row Path-2a; mismatch rejected |
| after anchor commit, before/during staging upload | `uploading`; zero/partial staging possible | writer retry or Path-2a→Path-2b |
| after final rename, before finalized update | `uploading`, final blob may exist | writer conditional finalize or Path-2a deletes both paths |
| finalized update response lost | `finalized` durable | publish retry by handle or Path 1 after horizon |
| anywhere inside publish tx | all claim/prepared/ordinal changes roll back, or all commit | replay publish; no half-committed winner |
| publish commit response lost | pending claim + committed prepared durable | idempotency conflict returns same commit; flush/expiry recovers |
| HEAD fails/mismatches before flush tx | no control-plane change | fixed failure; retry after repair |
| before mapping mutex / any flush statement | no change | retry same commit |
| after any flush/supersede statement but before commit | whole tx rolls back | retry; old pointer/claim/prepared remain exact |
| flush commit response lost after pointer advance | new current+flushed and old superseded+detached all durable | replay sees flushed exact-current and succeeds, or superseded tombstone succeeds |
| flush commit response lost after ordinal loses | new claim/prepared both superseded; pointer unchanged | replay superseded tombstone succeeds |
| expiry/detach commit response lost | claim expired/null + prepared orphaned both durable | replay reports expired; Path 1 later reclaims |
| superseded row before retention/read deadline | row remains superseded | no selector may mark it |
| after Path-1 mark commit, before rename | `reclaim_marked`, source original | age-independent Path-1 recovery |
| rename commits, process dies before destination verification/DB update | `reclaim_marked`, destination likely present | Path-1 recovery verifies destination and original absence |
| quarantine DB update response lost | either `reclaim_marked` or `quarantined`; bytes in quarantine | Path-1 recovery or Path 3, respectively |
| hard delete fails/before absence proof | `quarantined`; bytes may remain | Path 3 retries after grace |
| quarantine removed, before row-delete commit | `quarantined`; quarantine absent | Path 3 treats absence as idempotent and completes row delete |
| Path-2a mark/individual deletes/row delete | exactly GLY-346 v5 `upload_reclaim_marked` semantics | Path-2b, age-independent, until both paths absent and row gone |
| process dies while old reader holds pointer | source retained through drain; then quarantine through grace | original/quarantine bounded probe; never silent miss |
| migration statement/data check fails | outer migration transaction rolls back completely | repair data or spec; rerun unchanged migration |

Selectors therefore cover every new non-terminal state: `superseded` by due fresh Path 1,
`reclaim_marked` by Path-1 recovery, and existing `upload_reclaim_marked`/`quarantined` by Paths 2b/3.

## 10. Interface and file-level implementation boundaries

Expected implementation touch points (not authorization to edit in this round):

- `migrations/0001_phi_reversal_control_plane.sql`: append §4.2.
- `src/tokens/durable/azure/control-plane.ts`: add internal binding/retention fields, `superseded` states,
  reclaim-now input, and any internal snapshot fields; no frozen port edit.
- `src/tokens/durable/azure/postgres-control-plane.ts`: anchor transaction, shared mapping mutex/CAS completion,
  supersession, updated selectors/preview, and idempotent tombstone handling.
- `src/tokens/durable/azure/azure-files-spool-volume.ts`: pass authenticated retention metadata internally;
  bounded old-pointer quarantine fallback.
- `src/tokens/durable/azure/azure-spool-maintenance.ts`: fold superseded into Path 1, pass one now snapshot,
  enforce drain/grace relation, and strengthen quarantine proof.
- `src/tokens/durable/dev/in-memory-control-plane.ts` and `dev/in-memory-spool-volume.ts`: exact durable-model
  mirror and crash hooks.
- Tests/mutations only beyond those files. `ports.ts` comments MAY be corrected to remove the obsolete statement
  that determinism is merely trusted, but its public types/signatures MUST NOT change.

## 11. Oracle plan and required raw evidence

### 11.1 Unit and store-surface oracles

1. Sequential classifier flip on one tenant/attempt across two tokens: first class commits; second rejects with a
   fresh fixed-surface error; second prepared/current/blob is absent.
2. Concurrent cross-replica matter-vs-detector race: exactly one class/anchor wins; every successful row for the
   operation has that class; loser exposes no detail.
3. Crash/remount after anchor commit and before upload: a new store instance accepts only the persisted class.
4. Same attempt under different tenants binds independently; different attempts under one tenant bind
   independently; changing matter does not create a second binding key.
5. Equal-class same-attempt/token replay retains first-write-wins and does not allocate a replacement current.
6. Existing unknown/throwing classifier and contaminated dependency errors still produce only a newly allocated
   `REVERSAL_FAILED`.

### 11.2 Shared dev-double conformance oracles

Run one parameterized state-machine suite against the durable dev model and Postgres adapter:

1. current A, flush B: current=B; A prepared=superseded; A claim=superseded/null; B committed/flushed.
2. Flush higher ordinal B before lower A: B is current; later A completes superseded/null and never becomes
   current.
3. Replay A after supersession succeeds without blob restoration or pointer rollback.
4. Crash gate after every statement named in §9 gives only the two allowed transaction outcomes.
5. Detector superseded before expiry is not selected; at exact expiry but before drain is not selected; at exact
   `reclaim_after` is selected. Use inclusive `<=` for retention and drain boundary.
6. Finite matter expiry follows its numeric deadline. Exact `18446744073709551615` is never selected at any safe
   JS/PostgreSQL current time and never converts through `number`.
7. A referenced synthetic `superseded` row is counted skipped and not marked (defense-in-depth corruption
   oracle); finalized/orphaned equivalent remains green.
8. Superseded rows, old Path-1 rows, Path 2, and Path 3 exhaust one shared limit in normative priority order;
   preview and mutating outcomes match.
9. Pause a reader after old pointer snapshot, commit supersession, advance through drain, run quarantine, resume
   reader: it returns the authenticated old canonical from source or quarantine. A post-commit reader returns only
   the new canonical. After grace, an over-deadline old read fails fixed-surface, never returns a miss.
10. Crash after mark, rename, destination verification, quarantine update, hard delete, and row delete is
    idempotently recovered with no hard-delete-before-quarantine path.

### 11.3 Live PostgreSQL oracles

1. Apply 0001+delta to an empty DB twice and compare catalog definitions/counts.
2. Seed a pre-GLY-345 schema with live current rows, an older committed/flushed row for the same mapping,
   pending, expired/orphaned, finalized, upload, reclaim-marked, and quarantined rows. Migration preserves all
   rows, changes only the old non-current committed/flushed pair to superseded/null, backfills bindings/retention,
   and leaves current readable.
3. Seed historical mixed classes for one decoded tenant/attempt; migration fails and the surrounding transaction
   leaves the pre-migration schema/data intact.
4. Race N pools on one operation with alternating classes. The unique binding plus anchor transaction yields one
   class and no bare binding/anchor.
5. Race out-of-order flushes on one mapping. The mapping mutex prevents deadlock and yields maximum ordinal
   current; every other completed claim/prepared pair is superseded/unreferenced.
6. Terminate a session before commit at each anchor/flush transaction gate; verify rollback. Terminate after
   server commit but before client acknowledgement; verify replay convergence.
7. Exercise detector exact boundary, finite matter numeric boundary, and MaxUint64-never SQL predicates without
   any JS `number` conversion.
8. Run preview and mutating selectors over more than the limit across every path; prove single-budget order and
   `SKIP LOCKED` cross-worker exclusivity.
9. `EXPLAIN` confirms operation PK, mapping mutex PK, prepared superseded partial index, and reference indexes are
   used for bounded selectors.

### 11.4 Real Azure Files adapter/Q6 extension

1. Hold an old pointer between DB select and Files GET, supersede it from another replica, and exercise both the
   pre-drain source and post-rename quarantine fallback.
2. Kill maintenance after rename and before DB update; recovery verifies destination and does not hard-delete.
3. Assert destination-missing+source-missing and length mismatch leave `reclaim_marked` and fail the job.
4. Restart a request replica and the maintenance job independently; both converge using only PostgreSQL + Files,
   with no process-local retention authority.

### 11.5 Named mutations — each alone RED, then reverted

Part A:

- `MUT-RETENTION-BIND-PROCESS-MEMORY`
- `MUT-RETENTION-BIND-TOKEN-SCOPED`
- `MUT-RETENTION-BIND-MATTER-SCOPED`
- `MUT-RETENTION-BIND-LAST-WRITER-WINS`
- `MUT-RETENTION-BIND-NONATOMIC-ANCHOR`
- `MUT-RETENTION-MISMATCH-ACCEPT`
- `MUT-RETENTION-BIND-DROP-ON-CRASH`
- `MUT-RETENTION-BIND-GC-AFTER-BLOB`
- `MUT-RETENTION-MISMATCH-LEAK-DETAIL`
- `MUT-RETENTION-BINDING-KEY-HASH-COLLISION`

Part B/migration/read safety:

- `MUT-SUPERSEDE-LEAVE-OLD-COMMITTED`
- `MUT-SUPERSEDE-LEAVE-CLAIM-REFERENCE`
- `MUT-SUPERSEDE-NONATOMIC-WITH-CAS`
- `MUT-SUPERSEDE-BEFORE-CAS-WINS`
- `MUT-CAS-LOSER-STAYS-COMMITTED`
- `MUT-SUPERSEDED-FLUSH-RESURRECTS`
- `MUT-SUPERSEDED-FLUSH-FAILS-IDEMPOTENCY`
- `MUT-FLUSHED-NONCURRENT-SILENT-SUCCESS`
- `MUT-SUPERSEDE-RECLAIM-BEFORE-RETENTION`
- `MUT-SUPERSEDE-RECLAIM-BEFORE-DRAIN`
- `MUT-MATTER-MAX-RECLAIMABLE`
- `MUT-RETENTION-NUMERIC-TO-BIGINT`
- `MUT-SUPERSEDE-SKIP-UNREFERENCED-GUARD`
- `MUT-SUPERSEDE-PRIVATE-BUDGET`
- `MUT-SUPERSEDE-RECOVERY-SELECTOR-OMITTED`
- `MUT-READ-OLD-POINTER-NO-QUARANTINE-FALLBACK`
- `MUT-QUARANTINE-GRACE-SHORTER-THAN-DRAIN`
- `MUT-SUPERSEDE-HARD-DELETE-DIRECT`
- `MUT-QUARANTINE-MISSING-BOTH-AS-SUCCESS`
- `MUT-MIGRATION-NONIDEMPOTENT`
- `MUT-MIGRATION-DELETE-LEGACY-ROW`
- `MUT-MIGRATION-IGNORE-MIXED-LEGACY-CLASS`

The implementer ledger MUST include raw output for typecheck, full tests, live-PG gates, and each named mutant
run alone RED followed by revert/green. Claims are not evidence; logs are.

## 12. Acceptance criteria

1. All invariants in §3 have direct green oracles and named mutation coverage.
2. Public frozen signatures are unchanged; only internal control-plane additions exist.
3. A classifier cannot create mixed operation classes across replicas or crash/replay.
4. Every old committed row either remains exact current/pending or is transactionally superseded and detached;
   no completed non-current committed blob is pinned.
5. Detector/finite-matter superseded rows become Path-1 candidates only at their exact retention+drain deadline;
   MaxUint64 matter rows never do.
6. In-flight old-pointer reads are correct within the bounded lease, and quarantine precedes deletion.
7. Existing claim expiry/idempotency, ordinal CAS, three-path recovery, global budget, and fixed error surface do
   not regress.
8. The additive migration succeeds twice on empty and populated live databases and fails atomically on unsafe
   legacy ambiguity.
9. Typecheck, full Vitest, shared dev/PG conformance, live PG, Azure/Q6 extensions, and all named mutations are
   evidenced before review approval.

## 13. Explicit non-goals

1. No source implementation, infrastructure change, database execution, commit, push, PR, or deployment in this
   round.
2. No change to how business policy chooses `matter` versus `detector-only`; only enforcement of consistency.
3. No operation-binding garbage collection. A future design needs an explicit attempt-reuse horizon and cannot
   infer safety from blob absence.
4. No direct deletion API, list/export/debug widening, raw-canonical storage, or PHI in control-plane metadata.
5. No reclamation of live current matter records and no reinterpretation of MaxUint64.
6. No durable per-reader lease table; the bounded drain plus quarantine grace is the chosen consistency model.
7. No replacement of PostgreSQL/Azure Files topology, encryption/AAD format, KEK/DEK behavior, or nonce scheme.
8. No cleanup of unrelated pre-existing worktree changes.

## 14. Open questions

None for the principal. This v1 deliberately chooses: a permanent metadata-only binding tombstone; exact
tenant+attempt keying; migration-fatal historical mixed classes; a 60-second bounded read drain; superseded work
folded into Path 1; and the existing 24-hour quarantine default (validated to exceed the drain).
