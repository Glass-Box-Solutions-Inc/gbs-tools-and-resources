**Model: GPT-5.6-sol**

# GLY-345 specification v3 — durable operation-retention binding and supersede-aware retention

## 1. Status, authority, and normative language

1. This is a **T2 specification only**. It authorizes no implementation, deployment, commit, or source change.
2. Base is `main` at `2adef06`; implementation lane is `GLY-345-lane`.
3. This v3 supersedes GLY-345 spec-v2, retaining F1–F11 and resolving delta findings D1–D6 under the final
   orchestrator rulings.
   The GLY-346 state-machine ground truth remains `.planning/GLY-346/spec-v2.md`, `spec-v4.md`, and
   `spec-v5.md`, with v3 sections incorporated where v4/v5 refer to them.
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
MUST atomically cease being current, become `superseded`, and lose all claim/current references. A superseded
record has no reversal function: current-record latest-wins is the frozen reversal contract, so retaining the old
record is pure encrypted-blob leakage. Hard delete remains double-gated by quarantine grace and operator-enabled
`full` maintenance mode. Let `S = SUPERSEDE_RETENTION_MS` and `R = READ_DRAIN_MS`. The exact Path-1
**candidacy deadline** is:

1. matter: `superseded_at_ms + MAX(S, R)`; and
2. detector-only:
   `MAX(superseded_at_ms + R, MIN(retention_expires_at_ms, superseded_at_ms + S))`.

The detector `MIN(...)` is a defensive floor. It is inert at production settings because
`S >= graceMs = 24h` and a detector record expires 24 hours after creation, so its authenticated record expiry
always wins. The `superseded_at_ms + R` term independently delays rename. Correctness across a rename comes from
original→quarantine→original fallback while quarantine grace preserves the bytes; the heuristic is not a lease.

For either class, define `L_sweep` as the aggregate non-negative scheduler/execution latency from reaching
candidacy through the quarantine and subsequent eligible hard-delete sweep. The end-to-end lower bound is
`T_bytes_gone >= T_candidacy + graceMs + L_sweep`, and bytes are deleted only in operator `full` mode. The worst legal
configuration therefore stacks the supersede/drain candidacy wait, quarantine grace, and scheduler/sweep latency
additively. None of those physical-lifecycle delays extends reversal functionality: the current-record reversal
function still ends exactly at the authenticated record expiry. A superseded record has already lost its reversal
function when latest-wins current advances.

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
10. **B-RETENTION:** MaxUint64 remains never-expiring only for a non-superseded committed matter row, which is
    not a maintenance candidate. Supersession removes the reversal function and therefore removes that carve-out:
    matter uses the configured supersede window; detector-only uses the earlier of its original 24-hour expiry
    and that window. `retention_expires_at_ms` is never converted through JS `number`.
11. **B-READ:** the current non-transactional `pool.query` pointer read pins neither a PostgreSQL transaction nor
    a reader. `READ_DRAIN_MS` is therefore a rename-delay heuristic, not a lease. Correctness across a rename
    comes from original→quarantine→original fallback while quarantine grace preserves the bytes;
    `graceMs >= READ_DRAIN_MS` is startup-validated.
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
16. **NO-OVERRIDE:** the first-seen binding has no in-band override. A wrong binding is remediated by a new
    `attemptId` (a new operation). Any future class-widening-only audited override needs its own authorized ticket
    because a PHI-retention override path is itself a new attack surface.

## 4. Durable data model and exact migration delta

### 4.1 New metadata

- `reversal_operation_retention` is the durable Part-A binding table.
- `reversal_prepared.operation_key` points to the binding.
- `record_created_at_ms`, `retention_class`, and `retention_expires_at_ms` are copied from the authenticated
  encrypted-record metadata at the control-plane anchor. `retention_origin` is `anchored` for those rows and
  `backfilled` for migration-derived rows. Code MUST NOT use `record_created_at_ms` from a backfilled row to make
  a superseded-reclamation decision; only its class, numeric expiry (detector-only), and DB-clock
  `superseded_at_ms` participate.
- `superseded_at_ms` records the authoritative pointer transition time.
- `reclaim_after_ms` is a nullable materialized-at-mark audit value containing the effective **candidacy
  deadline**. Let `S = SUPERSEDE_RETENTION_MS` and `R = READ_DRAIN_MS`. Matter uses
  `superseded_at_ms + MAX(S, R)`. Detector-only uses
  `MAX(superseded_at_ms + R, MIN(retention_expires_at_ms, superseded_at_ms + S))`. The detector `MIN(...)` is a
  defensive floor retained for non-production/test configurations; at production settings
  `S >= graceMs = 24h`, so the record's 24-hour authenticated expiry always wins. The transition to
  `reclaim_marked` writes this computed deadline atomically. There is no MaxUint64 exclusion for superseded
  matter.
- `reversal_claim.state` gains terminal tombstone `superseded`; like `expired`, it has
  `prepared_blob_id = NULL`.

`SUPERSEDE_RETENTION_MS` defaults to `2_592_000_000` (30 days) and is configurable through internal maintenance
options. Construction/startup MUST validate `SUPERSEDE_RETENTION_MS >= graceMs >= READ_DRAIN_MS`. The supersede
window is a retention policy; `READ_DRAIN_MS` remains a 60,000ms rename-delay heuristic. Tests MAY inject smaller
non-negative values. The production profile uses `graceMs = 86_400_000` (24 hours); the 30-day supersede default
satisfies both inequalities. Candidacy does not delete bytes: with `L_sweep` defined as the aggregate non-negative
scheduler/execution latency across the quarantine and later eligible delete sweeps, the exact lower bound is
`T_bytes_gone >= T_candidacy + graceMs + L_sweep`, and deletion occurs only in operator `full` mode. Thus the worst
legal configuration stacks those delays additively even though reversal functionality still ends exactly at the
authenticated record expiry.

### 4.2 Migration execution contract

The delta below MUST be appended to `migrations/0001_phi_reversal_control_plane.sql`, because the existing
`runMigrations()` reads that file as one PostgreSQL transaction. This is an expand/contract rollout: the GLY-345
application/control-plane code MUST be deployed to every writer **before** this migration runs anywhere those
writers exist. Every new-code `reversal_prepared` `INSERT`/`UPDATE` supplies all five metadata columns
(`operation_key`, `record_created_at_ms`, `retention_class`, `retention_origin`, and
`retention_expires_at_ms`). This migration deliberately does not impose DB-level requiredness while an old writer
could still exist; that enforcement belongs to the separately named post-rollout validation/enforcement
migration. The operation FK remains `NOT VALID`; SQL NULL `operation_key` satisfies it during the expand phase.
Today the only migration runners are the reclaim job and smoke, and there are no production application writers,
so the current-world mixed-version exposure is nil.

The rollout order is normative: (1) deploy the GLY-345-capable application/control-plane release everywhere,
with writer traffic stopped or the new write path held dormant until schema readiness; (2) run this migration;
(3) enable writer traffic/new-code writes; and only after the full fleet is proven upgraded may a separately
authorized **GLY-345 follow-up validation/enforcement migration** validate historical rows and add DB-level
requiredness. No environment with writers may run step 2 before step 1. The temporary nullable contract buys
availability during an accidental rolling overlap: neither a legacy row nor a not-yet-upgraded writer is rejected
by a new GLY-345 retention constraint arm.

The migration is additive with respect to stored data:
new nullable/no-default columns and non-unique indexes are added, legacy rows are convergently backfilled only
where fields are null, and old state checks are definition-discovered and replaced by `NOT VALID` checks/FK.
There is no `SET NOT NULL`, constraint validation, or hot-table unique-index build. A first-statement row-count
guard aborts above 100,000 prepared rows with instructions to schedule an offline/batched window. At or below the
guard, availability exposure is bounded to one at-most-100,000-row transactional backfill plus brief DDL locks;
there is no unbounded validation scan and no constraint arm that rejects legacy/in-flight old-writer null
metadata. The delta deletes no row/blob. Running it twice MUST converge. Malformed
keys, ambiguous legacy expiry, mixed historical class, or broken pointer invariants roll back the whole migration.

```sql
-- GLY-345 v3 additive delta. runMigrations() already wraps this file in one transaction.
-- Online-safety guard: today this table is tiny. Refuse an unbounded hot-table backfill later.
DO $$
DECLARE
  prepared_count BIGINT;
BEGIN
  SELECT count(*) INTO prepared_count
  FROM (SELECT 1 FROM reversal_prepared LIMIT 100001) bounded_count;
  IF prepared_count > 100000 THEN
    RAISE EXCEPTION
      'gly345_online_migration_row_limit_exceeded: % rows; schedule an offline migration window, backfill in bounded batches, then apply GLY-345 validation separately',
      prepared_count;
  END IF;
END $$;

-- This is a new empty/tiny table, so its primary-key index is not a hot-table index build.
CREATE TABLE IF NOT EXISTS reversal_operation_retention (
  operation_key TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  retention_class TEXT NOT NULL,
  bound_at_ms BIGINT NOT NULL
);

-- Nullable, no-default columns are metadata-only additions on supported PostgreSQL versions.
ALTER TABLE reversal_prepared ADD COLUMN IF NOT EXISTS operation_key TEXT;
ALTER TABLE reversal_prepared ADD COLUMN IF NOT EXISTS record_created_at_ms BIGINT;
ALTER TABLE reversal_prepared ADD COLUMN IF NOT EXISTS retention_class TEXT;
ALTER TABLE reversal_prepared ADD COLUMN IF NOT EXISTS retention_origin TEXT;
ALTER TABLE reversal_prepared ADD COLUMN IF NOT EXISTS retention_expires_at_ms NUMERIC(20,0);
ALTER TABLE reversal_prepared ADD COLUMN IF NOT EXISTS superseded_at_ms BIGINT;
ALTER TABLE reversal_prepared ADD COLUMN IF NOT EXISTS reclaim_after_ms NUMERIC(20,0);

-- Drop every legacy anonymous state-dependent check by definition, never by PostgreSQL-generated
-- name. The quarantine-timestamp check is intentionally rebuilt below so no unknown state check survives.
DO $$
DECLARE
  constraint_row RECORD;
BEGIN
  FOR constraint_row IN
    SELECT c.conname
    FROM pg_constraint c
    WHERE c.conrelid = 'reversal_prepared'::regclass
      AND c.contype = 'c'
      AND position('state' IN lower(pg_get_constraintdef(c.oid))) > 0
  LOOP
    EXECUTE format(
      'ALTER TABLE reversal_prepared DROP CONSTRAINT %I',
      constraint_row.conname
    );
  END LOOP;

  FOR constraint_row IN
    SELECT c.conname
    FROM pg_constraint c
    WHERE c.conrelid = 'reversal_claim'::regclass
      AND c.contype = 'c'
      AND position('state' IN lower(pg_get_constraintdef(c.oid))) > 0
  LOOP
    EXECUTE format(
      'ALTER TABLE reversal_claim DROP CONSTRAINT %I',
      constraint_row.conname
    );
  END LOOP;
END $$;

-- Named v3 constraints/FK may exist on a rerun. Recreate them NOT VALID; do not validate here.
ALTER TABLE reversal_operation_retention
  DROP CONSTRAINT IF EXISTS reversal_operation_retention_class_check;
ALTER TABLE reversal_operation_retention
  DROP CONSTRAINT IF EXISTS reversal_operation_retention_bound_at_check;
ALTER TABLE reversal_prepared DROP CONSTRAINT IF EXISTS reversal_prepared_gly345_state_check;
ALTER TABLE reversal_prepared DROP CONSTRAINT IF EXISTS reversal_prepared_gly345_blob_state_check;
ALTER TABLE reversal_prepared DROP CONSTRAINT IF EXISTS reversal_prepared_gly345_quarantine_check;
ALTER TABLE reversal_prepared DROP CONSTRAINT IF EXISTS reversal_prepared_gly345_retention_check;
ALTER TABLE reversal_prepared DROP CONSTRAINT IF EXISTS reversal_prepared_gly345_supersession_check;
ALTER TABLE reversal_prepared DROP CONSTRAINT IF EXISTS reversal_prepared_gly345_operation_fk;
ALTER TABLE reversal_claim DROP CONSTRAINT IF EXISTS reversal_claim_gly345_state_check;
ALTER TABLE reversal_claim DROP CONSTRAINT IF EXISTS reversal_claim_gly345_prepared_check;

-- Validate and decode legacy b64url-v1:(tenant NUL attempt NUL token) keys. A bad key is fatal.
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
WHERE p.prepared_blob_id = o.prepared_blob_id
  AND p.operation_key IS NULL;

-- F7: current code has only two legal historical expiry forms. Anything else may be a finite-matter
-- record and must abort instead of being silently classified detector-only.
DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM reversal_claim c
    WHERE c.expires_at_ms <> 18446744073709551615::numeric
      AND c.expires_at_ms <> c.created_at_ms::numeric + 86400000::numeric
  ) THEN
    RAISE EXCEPTION
      'gly345_ambiguous_legacy_expiry: expected MaxUint64 or created_at_ms + 86400000; classify offline';
  END IF;
END $$;

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
END $$;

-- Claimed rows carry the historical class after the F7 guard.
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

-- An unclaimed legacy row has no SQL-visible authenticated class. Bind fail-safe to matter: this may
-- reject a detector retry, but it cannot shorten PHI retention. The caller must use a new attemptId.
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
         c.created_at_ms AS claim_created_at_ms,
         p.created_at_ms AS control_created_at_ms
  FROM reversal_prepared p
  JOIN reversal_operation_retention b ON b.operation_key = p.operation_key
  LEFT JOIN reversal_claim c ON c.idempotency_key = p.idempotency_key
)
UPDATE reversal_prepared p
SET retention_class = COALESCE(p.retention_class, h.bound_class),
    retention_origin = COALESCE(p.retention_origin, 'backfilled'),
    record_created_at_ms = COALESCE(
      p.record_created_at_ms,
      h.claim_created_at_ms,
      h.control_created_at_ms
    ),
    retention_expires_at_ms = COALESCE(
      p.retention_expires_at_ms,
      h.claim_expiry,
      CASE
        WHEN h.bound_class = 'detector-only'
          THEN h.control_created_at_ms::numeric + 86400000::numeric
        ELSE 18446744073709551615::numeric
      END
    )
FROM historical h
WHERE p.prepared_blob_id = h.prepared_blob_id
  AND (
    p.retention_class IS NULL OR
    p.retention_origin IS NULL OR
    p.record_created_at_ms IS NULL OR
    p.retention_expires_at_ms IS NULL
  );

-- Validate the old current/claim relation before converting preexisting non-current flushed rows.
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

-- Every legacy superseded row receives a full supersede window beginning at migration DB time. Replica-written
-- flushed_at_ms is deliberately ignored. reclaim_after_ms remains NULL until maintenance materializes candidacy.
WITH migration_clock AS (
  SELECT (extract(epoch FROM clock_timestamp()) * 1000)::bigint AS db_now_ms
), legacy_superseded AS (
  SELECT p.prepared_blob_id,
         mc.db_now_ms AS migration_superseded_at_ms
  FROM reversal_claim c
  JOIN reversal_prepared p ON p.prepared_blob_id = c.prepared_blob_id
  JOIN reversal_current cur ON cur.mapping_key = c.mapping_key
  CROSS JOIN migration_clock mc
  WHERE c.state = 'flushed'
    AND cur.prepared_blob_id <> c.prepared_blob_id
    AND cur.ordinal > c.ordinal
    AND p.state = 'committed'
)
UPDATE reversal_prepared p
SET state = 'superseded',
    superseded_at_ms = s.migration_superseded_at_ms,
    reclaim_after_ms = NULL
FROM legacy_superseded s
WHERE p.prepared_blob_id = s.prepared_blob_id
  AND p.state = 'committed';

UPDATE reversal_claim c
SET state = 'superseded', prepared_blob_id = NULL
FROM reversal_prepared p
WHERE c.prepared_blob_id = p.prepared_blob_id
  AND c.state = 'flushed'
  AND p.state = 'superseded';

-- Added constraints are deliberately NOT VALID: they govern new writes without scanning/validating
-- historical rows in this online migration. A separate validation migration is out of scope.
ALTER TABLE reversal_operation_retention
  ADD CONSTRAINT reversal_operation_retention_class_check
  CHECK (retention_class IN ('matter', 'detector-only')) NOT VALID;
ALTER TABLE reversal_operation_retention
  ADD CONSTRAINT reversal_operation_retention_bound_at_check
  CHECK (bound_at_ms >= 0) NOT VALID;

ALTER TABLE reversal_prepared
  ADD CONSTRAINT reversal_prepared_gly345_state_check CHECK (
    state IN (
      'uploading', 'finalized', 'committed', 'superseded', 'orphaned',
      'upload_reclaim_marked', 'reclaim_marked', 'quarantined'
    )
  ) NOT VALID;

ALTER TABLE reversal_prepared
  ADD CONSTRAINT reversal_prepared_gly345_blob_state_check CHECK (
    (state IN ('uploading', 'upload_reclaim_marked') AND blob_etag IS NULL AND blob_len IS NULL)
    OR
    (state IN (
       'finalized', 'committed', 'superseded', 'orphaned', 'reclaim_marked', 'quarantined'
     ) AND blob_etag IS NOT NULL AND blob_len IS NOT NULL)
  ) NOT VALID;

ALTER TABLE reversal_prepared
  ADD CONSTRAINT reversal_prepared_gly345_quarantine_check CHECK (
    (state = 'quarantined' AND quarantined_at_ms IS NOT NULL)
    OR
    (state IN (
       'uploading', 'finalized', 'committed', 'superseded', 'orphaned',
       'upload_reclaim_marked', 'reclaim_marked'
     ) AND quarantined_at_ms IS NULL)
  ) NOT VALID;

-- Expand phase: an old/not-yet-upgraded writer may still supply none of the five GLY-345 metadata columns.
-- If any is NULL this migration's retention check is inert; new control-plane code supplies all five and is
-- checked by the inner arm. DB-level requiredness is deferred until all writers are upgraded.
ALTER TABLE reversal_prepared
  ADD CONSTRAINT reversal_prepared_gly345_retention_check CHECK (
    operation_key IS NULL
    OR record_created_at_ms IS NULL
    OR retention_class IS NULL
    OR retention_origin IS NULL
    OR retention_expires_at_ms IS NULL
    OR (
      record_created_at_ms >= 0
      AND retention_class IN ('matter', 'detector-only')
      AND retention_origin IN ('anchored', 'backfilled')
      AND retention_expires_at_ms BETWEEN 0::numeric AND 18446744073709551615::numeric
      AND (
        retention_origin = 'backfilled'
        OR retention_class = 'matter'
        OR retention_expires_at_ms = record_created_at_ms::numeric + 86400000::numeric
      )
      AND (
        reclaim_after_ms IS NULL
        OR reclaim_after_ms BETWEEN 0::numeric AND 18446744073709551615::numeric
      )
    )
  ) NOT VALID;

ALTER TABLE reversal_prepared
  ADD CONSTRAINT reversal_prepared_gly345_supersession_check CHECK (
    (
      state = 'superseded'
      AND superseded_at_ms IS NOT NULL
      AND superseded_at_ms >= 0
      AND reclaim_after_ms IS NULL
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
  ) NOT VALID;

ALTER TABLE reversal_prepared
  ADD CONSTRAINT reversal_prepared_gly345_operation_fk
  FOREIGN KEY (operation_key)
  REFERENCES reversal_operation_retention(operation_key) NOT VALID;

ALTER TABLE reversal_claim
  ADD CONSTRAINT reversal_claim_gly345_state_check
  CHECK (state IN ('pending', 'flushed', 'expired', 'superseded')) NOT VALID;
ALTER TABLE reversal_claim
  ADD CONSTRAINT reversal_claim_gly345_prepared_check CHECK (
    (state IN ('expired', 'superseded') AND prepared_blob_id IS NULL)
    OR
    (state IN ('pending', 'flushed') AND prepared_blob_id IS NOT NULL)
  ) NOT VALID;

-- Non-unique bounded-selector indexes only; no hot-table unique index is built in this migration.
CREATE INDEX IF NOT EXISTS reversal_operation_retention_tenant_idx
  ON reversal_operation_retention (tenant_id);
CREATE INDEX IF NOT EXISTS reversal_prepared_operation_idx
  ON reversal_prepared (operation_key);
CREATE INDEX IF NOT EXISTS reversal_prepared_superseded_reclaim_idx
  ON reversal_prepared (superseded_at_ms, prepared_blob_id)
  WHERE state = 'superseded';

-- F9 post-condition: because every state-dependent check was rebuilt above, every surviving
-- state-dependent check must explicitly account for superseded. Anything else is migration-fatal.
DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM pg_constraint c
    WHERE c.conrelid = 'reversal_prepared'::regclass
      AND c.contype = 'c'
      AND position('state' IN lower(pg_get_constraintdef(c.oid))) > 0
      AND position('superseded' IN lower(pg_get_constraintdef(c.oid))) = 0
  ) OR EXISTS (
    SELECT 1
    FROM pg_constraint c
    WHERE c.conrelid = 'reversal_claim'::regclass
      AND c.contype = 'c'
      AND position('state' IN lower(pg_get_constraintdef(c.oid))) > 0
      AND position('superseded' IN lower(pg_get_constraintdef(c.oid))) = 0
  ) THEN
    RAISE EXCEPTION 'gly345_surviving_check_rejects_superseded';
  END IF;
END $$;
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

1. `BEGIN; SET TRANSACTION ISOLATION LEVEL READ COMMITTED`. READ COMMITTED is normative for this protocol, not
   an ambient-default assumption.
2. Snapshot and validate all internal input once. Require a non-empty tenant/attempt, recognized class,
   non-negative safe-integer record creation time, uint64 expiry, exact detector TTL, and matter expiry as
   supplied by the authenticated record.
3. Capture `tx_now_ms` from PostgreSQL `clock_timestamp()`; use it for `bound_at_ms` and control-plane
   `created_at_ms`.
4. `INSERT reversal_operation_retention(operation_key, tenant_id, retention_class, bound_at_ms=tx_now_ms)
   ON CONFLICT (operation_key) DO NOTHING`. Under READ COMMITTED, PostgreSQL speculative insertion on the unique
   operation-key index waits for an in-progress conflicting speculative tuple/transaction. If that transaction
   commits, this statement takes the conflict/DO-NOTHING arm; if it aborts, this statement may insert. This wait
   is the cross-replica first-winner serialization and MUST NOT be simplified to SELECT-then-INSERT, `DO UPDATE`,
   or an application-memory check.
5. `SELECT tenant_id, retention_class FROM reversal_operation_retention WHERE operation_key=$1 FOR SHARE`.
   Missing row, tenant mismatch, or class mismatch throws. A different class never updates the winner.
6. `INSERT reversal_prepared(... operation_key, record_created_at_ms, retention_class,
   retention_origin='anchored', retention_expires_at_ms, state='uploading', created_at_ms=tx_now_ms)`. Require
   exactly one row.
7. Commit, then and only then upload to `staging/` and continue the unchanged finalize protocol.

If step 6 fails, steps 3–6 roll back, so a bare binding is not created by a failed first anchor. Once any anchor
commits, its binding remains even if the upload crashes and the `uploading` row is later reclaimed.

There is no administrative or dependency-driven override through this transaction. If policy supplied the wrong
first class, remediation is a new attempt ID. The existing wrong attempt remains a durable tombstone.

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
`tx_now_ms` with `SELECT (extract(epoch FROM clock_timestamp()) * 1000)::bigint` after acquiring the mapping
mutex. The DB clock—not `FlushClaimInput.nowEpochMilliseconds`, a replica clock, or Files metadata—is normative
for expiry comparison, `flushed_at_ms`, and `superseded_at_ms`. The maintenance selector computes the later
effective candidacy deadline from that DB-clock supersession time and its configured policy/drain windows.

Blob HEAD/ETag/length verification remains before the control-plane transaction. No network operation is held
inside the transaction.

### 6.2 Conditional completion

After locking:

- `claim.state='expired'`: fail closed; never resurrect.
- `claim.state='superseded'`: direct `flush` is idempotent success. The tombstone proves the historical attempt
  completed but can no longer change current. On a `publish` conflict, the existing `expires_at_ms` is still
  compared: an expired detector returns `expired:true` exactly as it did while flushed; an unexpired/matter
  replay reaches the no-op flush. Supersession never refreshes the detector window.
- `claim.state='flushed'` and current still references the same commit/prepared/ordinal: idempotent success.
- `claim.state='flushed'` but current is a different commit of equal/higher ordinal: whether discovered by the
  `publish` conflict branch or direct `flush`, self-heal the stale pair in place. **This branch MUST reuse gate
  F-A verbatim before executing the CTE:** while holding the mapping mutex/current lock, issue `SELECT ... FROM
  reversal_claim WHERE commit_handle=$1 FOR UPDATE` for the stale old claim and then `SELECT ... FROM
  reversal_prepared WHERE prepared_blob_id=$2 FOR UPDATE` for its old prepared row; require old
  claim=`flushed`, old prepared=`committed`, exact old claim/prepared identity, different current with equal/higher
  ordinal, and no other claim/current reference. The mapping mutex alone is insufficient, and neither `FOR
  UPDATE` lock may be dropped or folded into an unlocked preflight. Then execute this **single
  data-modifying CTE statement**, require both counts are one, and commit; any error rolls both changes back:

  ```sql
  WITH detached AS (
    UPDATE reversal_claim
    SET state = 'superseded', prepared_blob_id = NULL
    WHERE commit_handle = $1
      AND state = 'flushed'
      AND prepared_blob_id = $2
    RETURNING $2::uuid AS prepared_blob_id
  ), superseded AS (
    UPDATE reversal_prepared p
    SET state = 'superseded',
        superseded_at_ms = $3::bigint,
        reclaim_after_ms = NULL
    FROM detached d
    WHERE p.prepared_blob_id = d.prepared_blob_id
      AND p.state = 'committed'
    RETURNING 1
  )
  SELECT (SELECT count(*) FROM detached) AS detached_count,
         (SELECT count(*) FROM superseded) AS superseded_count;
  ```

  Direct flush returns success. A publish conflict then returns the same existing commit/scope and computes
  `expired` from the unchanged original expiry: unexpired/matter replay reaches the superseded no-op flush and
  succeeds; an expired detector remains the existing non-retryable fixed failure, but its stale blob is now
  detached. A flushed claim with no current row, a lower current ordinal, or any competing reference remains
  fail-closed; those cases do not prove supersession.
- `claim.state='pending' AND tx_now >= expires_at`: perform the existing atomic
  pending-to-expired/detach and committed-to-orphaned transition, then fail closed after commit.
- `claim.state='pending' AND unexpired`: verify the prepared row is `committed` and the supplied HEAD attributes
  match, then compare ordinals under the mapping mutex.

For an absent current row, insert the new pointer and set the new claim to `flushed` in the same transaction.

For `new.ordinal > current.ordinal`, execute these separately fault-injectable statements in this exact order:

1. **F-A LOCK/VERIFY:** lock the old claim and old prepared; require old claim=`flushed`, old
   prepared=`committed`, exact pointer identity, and no additional non-null claim reference.
2. **F-B NEW-CLAIM:** update the new claim `pending -> flushed`; require one row.
3. **F-C POINTER-CAS:** update current to the new commit/prepared/ordinal with `flushed_at_ms=tx_now_ms`, guarded
   by the previously observed old identity and lower ordinal; require one row. Old-row supersession is forbidden
   unless this statement wins.
4. **F-D OLD-CLAIM:** update the old claim `flushed -> superseded, prepared_blob_id=NULL`; require one row.
5. **F-E OLD-PREPARED:** update old prepared `committed -> superseded`, set
   `superseded_at_ms=tx_now_ms`, leave `reclaim_after_ms=NULL`; require one row.
6. **F-F COMMIT:** commit. Fault gates exist after F-A, F-B, F-C, F-D, F-E, and immediately after server commit
   before client acknowledgement. Before F-F, every injected failure rolls the entire transaction back; after
   F-F, all five effects are durable.

For `new.ordinal <= current.ordinal`, current is unchanged; update the new claim directly
`pending -> superseded, prepared_blob_id=NULL` (**L-A**) and its prepared row `committed -> superseded,
superseded_at_ms=tx_now_ms, reclaim_after_ms=NULL` (**L-B**), require one row each, then commit (**L-C**).
Fault gates after L-A/L-B roll back both until L-C. `flush()` returns success after commit. This closes the
out-of-order loser leak.

The implementation MUST NOT retain the current one-statement pointer upsert if it cannot return and lock the old
pointer/claim/prepared identities. The mapping mutex plus explicit compare/update is the required CAS.

The internal flush preflight must also stop assuming every idempotent commit still has a blob. Internally,
`readClaimBlobReference` becomes a discriminated result: `{kind:'blob', path, etag, length}` for pending/flushed,
`{kind:'stale-flushed'}` when a flushed claim has a different equal/higher current, or `{kind:'superseded'}` for
the terminal tombstone. Unknown/expired/inconsistent remains failure. `AzureFilesSpoolVolume.flush()` skips HEAD
for `superseded` and returns success; for `stale-flushed` it invokes the transactional §6.2 self-heal without blob
attributes; for `blob` it preserves current HEAD verification and calls normal completion. The internal
`FlushClaimInput` may therefore become a discriminated union. No frozen `SpoolVolume.flush(commit)` signature
changes, and a stale row can self-heal even if its no-longer-functional blob is absent.

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
| `committed` | higher ordinal advances current | old claim/pointer/prepared exact-match; all row counts one | `superseded` | same PG tx as new flushed claim and pointer CAS; DB-clock superseded time; candidacy not yet materialized | fresh Path-1 at computed candidacy deadline |
| `committed` | own ordinal loses current CAS | subject claim pending; current ordinal is greater/equal | `superseded` | claim→superseded/null + prepared transition in same PG tx; DB-clock superseded time | fresh Path-1 at computed candidacy deadline |
| `committed` | stale non-current flushed claim discovered | different current has equal/higher ordinal; F-A old-claim+old-prepared `FOR UPDATE` locks; no other references | `superseded` | §6.2 one-statement claim-detach+prepared-supersede CTE, then commit | fresh Path-1 at computed candidacy deadline |
| `orphaned` | Path-1 fresh claim | ordinary horizon passed; no references | `reclaim_marked` | PG tx | Path-1 recovery |
| `superseded` | Path-1 fresh claim | effective candidacy deadline from class/window and DB-clock rename-delay floor is due; no references | `reclaim_marked` | PG tx atomically materializes effective candidacy in `reclaim_after_ms` and marks | Path-1 recovery |
| `reclaim_marked` | quarantine complete | destination exists with expected length; original absent; no references | `quarantined` | idempotent Files rename/verification first; PG timestamp update second | Path-1 recovery before DB update; Path-3 afterward |
| `quarantined` | grace hard-delete | `quarantined_at_ms + grace <= DB now`; `full` mode; no references | absent/deleted | quarantine delete+absence proof first; PG row delete second | Path-3 until row deletion commits |

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
| `flushed` | replay finds different equal/higher current | `superseded` with null prepared | §6.2 one-statement self-heal supersedes old prepared; current unchanged | succeeds after atomic heal |
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

There is no binding deletion or override transition in this ticket. A wrong winner requires a new attempt ID.

## 8. Retention selection, reader consistency, and quarantine

### 8.1 Path-1 predicate and ordering

The internal Path-1/preview input gains `supersedeRetentionMs` (internal only), supplied by the scrubbed
maintenance option. PostgreSQL captures its own `db_now_ms = clock_timestamp()` once in a one-row
`selector_clock` CTE in the selector transaction; that CTE also computes
`matter_superseded_before_ms = db_now_ms - MAX(S, R)`. The job/replica clock is not authoritative. Define
`effective_reclaim_after_ms` (the candidacy deadline) without consulting `record_created_at_ms`:

```sql
p.state = 'reclaim_marked'
OR (p.state IN ('finalized', 'orphaned') AND p.created_at_ms < $olderThan)
OR (
  p.state = 'superseded'
  AND (
    (
      COALESCE(p.retention_class, 'matter') = 'matter'
      AND p.superseded_at_ms <= selector_clock.matter_superseded_before_ms
    )
    OR (
      p.retention_class = 'detector-only'
      AND greatest(
        p.superseded_at_ms::numeric + $readDrainMs::numeric,
        least(
          p.retention_expires_at_ms,
          p.superseded_at_ms::numeric + $supersedeRetentionMs::numeric
        )
      ) <= selector_clock.db_now_ms::numeric
    )
  )
)
```

The mark UPDATE materializes the same effective candidacy expression:

```sql
CASE p.retention_class
  WHEN 'detector-only' THEN greatest(
    p.superseded_at_ms::numeric + $readDrainMs::numeric,
    least(
      p.retention_expires_at_ms,
      p.superseded_at_ms::numeric + $supersedeRetentionMs::numeric
    )
  )
  ELSE p.superseded_at_ms::numeric + greatest(
    $supersedeRetentionMs::numeric,
    $readDrainMs::numeric
  )
END
```

Every arm is additionally guarded by both existing `NOT EXISTS` reference predicates. Order recovery first,
then due fresh candidates by the effective deadline (`created_at_ms` for finalized/orphaned,
the CASE expression for superseded), then `prepared_blob_id`. The transaction locks with
`FOR UPDATE OF p SKIP LOCKED LIMIT $remaining` and conditionally changes only fresh candidates to
`reclaim_marked`; for each superseded winner the same UPDATE materializes that exact CASE result into
`reclaim_after_ms`. Preview uses the identical expression/order but no locks/mutations. There is no MaxUint64
special case in this superseded arm. The detector `least()` remains as a defensive floor for test/non-production
configurations; it is inert in the production profile because `SUPERSEDE_RETENTION_MS >= graceMs = 24h`, making
the authenticated 24-hour record expiry the lesser term. The `greatest()` drain term is only a DB-clock
rename-delay heuristic; it does not create a reader lease. Referenced candidates retain the existing
independently capped `skippedReferenced` accounting and do not consume mutation budget.

### 8.2 Read-consistency window

The current adapter uses a non-transactional `pool.query` at the pointer-read boundary. It does not expose or pin
a reader transaction, so this specification does not invent a reader lease or completion deadline:

1. `readCurrentPointers` either sees the old pointer before the superseding transaction commits or the new
   pointer after commit, never a half-transition.
2. `READ_DRAIN_MS` delays rename only as a heuristic. The stronger configured relation
   `SUPERSEDE_RETENTION_MS >= graceMs >= READ_DRAIN_MS` ensures ordinary matter supersession cannot rename before
   that delay; the separate selector floor also delays a detector whose base policy time is earlier. Correctness
   MUST NOT depend on that heuristic.
3. If original-path lookup races or follows the quarantine rename, the adapter performs bounded
   original→quarantine→original probing. Quarantine fallback is derived only from the prepared UUID, requires
   exact stored byte length, decodes the immutable envelope, and relies on the existing AAD byte comparison and
   GCM authentication before plaintext is returned. It never treats both locations absent as a normal miss.
4. Quarantine is retained for at least `graceMs`; hard deletion additionally requires operator `full` mode.
   `graceMs >= READ_DRAIN_MS` is constructor/job-startup validation and the adapter probe remains available for
   the entire quarantine grace.
5. A read stalled until after grace and a full-mode hard delete has no unbounded guarantee; it fails fixed-surface
   if both paths are absent. It never returns a silent miss or unauthenticated bytes.

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
| after F-A old-row lock/verify | no writes; rollback releases locks | retry same commit |
| after F-B new claim is set flushed, before pointer CAS | uncommitted claim update rolls back | retry sees pending; old current/prepared unchanged |
| after F-C pointer CAS wins, before old-claim detach | uncommitted pointer+claim updates roll back together | retry; old row MUST NOT be superseded outside a winning CAS tx (`MUT-SUPERSEDE-BEFORE-CAS-WINS` gate) |
| after F-D old-claim detach, before old-prepared supersede | all F-B/F-C/F-D writes roll back | retry sees exact old current pair |
| after F-E old-prepared supersede, before F-F commit | all new/old claim, pointer, and prepared writes roll back | retry executes the full branch |
| flush commit response lost after pointer advance | new current+flushed and old superseded+detached all durable | replay sees flushed exact-current and succeeds, or superseded tombstone succeeds |
| after L-A losing-claim detach, before L-B | both losing-branch writes roll back | retry sees pending committed loser |
| after L-B losing-prepared supersede, before L-C | both losing-branch writes roll back | retry sees pending committed loser |
| flush commit response lost after ordinal loses | new claim/prepared both superseded; pointer unchanged | replay superseded tombstone succeeds |
| after self-heal F-A verbatim old-claim+old-prepared `FOR UPDATE` lock/verify, before F11 CTE | stale flushed/non-current pair unchanged; rollback releases both row locks | retry re-enters F-A then self-heal; neither lock may be skipped |
| after F11 CTE statement, before commit | claim-detach and prepared-supersede both roll back | retry re-enters self-heal |
| F11 commit response lost | both self-heal changes durable | replay sees superseded tombstone and succeeds |
| expiry/detach commit response lost | claim expired/null + prepared orphaned both durable | replay reports expired; Path 1 later reclaims |
| superseded row before effective candidacy deadline | row remains superseded with null materialized candidacy | no selector may mark it |
| after Path-1 mark commit, before rename | `reclaim_marked`, source original | age-independent Path-1 recovery |
| rename commits, process dies before destination verification/DB update | `reclaim_marked`, destination likely present | Path-1 recovery verifies destination and original absence |
| quarantine DB update response lost | either `reclaim_marked` or `quarantined`; bytes in quarantine | Path-1 recovery or Path 3, respectively |
| hard delete fails/before absence proof | `quarantined`; bytes may remain | Path 3 retries after grace |
| quarantine removed, before row-delete commit | `quarantined`; quarantine absent | Path 3 treats absence as idempotent and completes row delete |
| Path-2a mark/individual deletes/row delete | exactly GLY-346 v5 `upload_reclaim_marked` semantics | Path-2b, age-independent, until both paths absent and row gone |
| process dies while old reader holds pointer | source or quarantine may hold immutable bytes; no reader lease exists | original→quarantine→original bounded probe during grace; never silent miss |
| migration row-count guard exceeds 100,000 | outer transaction aborts before schema/backfill mutation | schedule named offline/batched window; do not bypass guard |
| migration statement/data check fails | outer migration transaction rolls back completely | repair data or spec; rerun unchanged migration |

Selectors therefore cover every new non-terminal state: `superseded` by due fresh Path 1,
`reclaim_marked` by Path-1 recovery, and existing `upload_reclaim_marked`/`quarantined` by Paths 2b/3.

## 10. Interface and file-level implementation boundaries

Expected implementation touch points (not authorization to edit in this round):

- `migrations/0001_phi_reversal_control_plane.sql`: append §4.2.
- `src/tokens/durable/azure/control-plane.ts`: add internal binding/retention fields, `superseded` states,
  supersede-retention input, and any internal snapshot fields; no frozen port edit.
- `src/tokens/durable/azure/postgres-control-plane.ts`: anchor transaction, shared mapping mutex/CAS completion,
  supersession, updated selectors/preview, and idempotent tombstone handling.
- `src/tokens/durable/azure/azure-files-spool-volume.ts`: pass authenticated retention metadata internally;
  old-pointer original/quarantine fallback without inventing a reader deadline.
- `src/tokens/durable/azure/azure-spool-maintenance.ts`: fold superseded into Path 1, configure the 30-day default,
  enforce `supersedeRetention >= grace >= drain`, rely on DB time, and strengthen quarantine proof.
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
7. **ORACLE-BIND-PERSISTS-WITHOUT-BLOB:** reclaim every blob for an operation, restart all replicas, then retry
   the old attempt with the opposite class: it still fails against the durable binding. This kills
   `MUT-RETENTION-BIND-GC-AFTER-BLOB`.
8. **ORACLE-OPERATION-KEY-INJECTIVE:** bind crafted aliasing pairs `(tenant='ab', attempt='c')` and
   `(tenant='a', attempt='bc')`. A delimiter-free
   concatenation aliases both as `abc`; the required NUL-fenced base64url keys differ and bind independently.
   This is the oracle for `MUT-RETENTION-BINDING-KEY-NONINJECTIVE`.
9. A wrong first binding cannot be altered in band; the old attempt remains rejected while a new attempt ID binds
   normally.

### 11.2 Shared dev-double conformance oracles

Run one parameterized state-machine suite against the durable dev model and Postgres adapter:

1. current A, flush B: current=B; A prepared=superseded; A claim=superseded/null; B committed/flushed.
2. Flush higher ordinal B before lower A: B is current; later A completes superseded/null and never becomes
   current.
3. Replay A after supersession succeeds without blob restoration or pointer rollback.
4. Crash gate after every statement named in §9 gives only the two allowed transaction outcomes.
5. Matter candidacy is exactly `superseded_at + MAX(SUPERSEDE_RETENTION_MS, READ_DRAIN_MS)`, including
   MaxUint64 records. Detector-only candidacy is exactly
   `MAX(superseded_at + READ_DRAIN_MS, MIN(numeric 24-hour expiry, superseded_at +
   SUPERSEDE_RETENTION_MS))`; selection is inclusive at that deadline. Prove the detector `MIN` is retained as a
   defensive floor, and prove it is inert under the production relation `S >= grace = 24h` because authenticated
   record expiry wins. A non-superseded committed MaxUint64 matter row is never selected because committed is
   not a candidate. This kills `MUT-SUPERSEDE-CANDIDACY-OMITS-DRAIN-MAX` and
   `MUT-DETECTOR-SUPERSEDE-DROPS-EXPIRY-FLOOR`.
6. Changing `record_created_at_ms` on a `retention_origin='backfilled'` row does not change superseded eligibility;
   selection uses DB-clock `superseded_at_ms` and, only for detector, stored numeric expiry.
7. A referenced synthetic `superseded` row is counted skipped and not marked (defense-in-depth corruption
   oracle); finalized/orphaned equivalent remains green.
8. Superseded rows, old Path-1 rows, Path 2, and Path 3 exhaust one shared limit in normative priority order;
   preview and mutating outcomes match.
9. Pause a reader after old pointer snapshot, commit supersession, quarantine the old blob, and resume **within
   quarantine grace**: original→quarantine→original fallback returns the authenticated old canonical. A
   post-commit reader returns only the new canonical. No oracle assumes a pinned reader or adapter deadline; after
   grace+full deletion, both-path absence fails fixed-surface rather than returning a miss.
10. Crash after mark, rename, destination verification, quarantine update, hard delete, and row delete is
    idempotently recovered with no hard-delete-before-quarantine path.
11. **ORACLE-MAINTENANCE-WINDOW-ORDER:** startup accepts equality boundaries and rejects either
    `graceMs < READ_DRAIN_MS` or
    `SUPERSEDE_RETENTION_MS < graceMs` before DB/Files mutation.
12. Seed an unexpired/matter flushed claim whose mapping current is a different higher/equal ordinal. Publish
    replay first takes the §6.2/F-A `FOR UPDATE` locks on the stale old claim and old prepared, then performs the
    one-statement self-heal, returns success through the superseded no-op flush, detaches the claim, supersedes the
    prepared row, and does not move current; repeat with the stale blob absent. A concurrent writer targeting
    either old row MUST block until this transaction ends. An expired-detector replay performs the same heal
    before preserving its non-retryable error. Fault before commit leaves both rows unchanged.
    This kills `MUT-SELF-HEAL-DROPS-F-A-ROW-LOCK`.
13. For both classes, observe that no quarantine rename occurs before candidacy. After rename, prove bytes remain
    through `graceMs`; only a later operator-`full` sweep deletes them. Assert the end-to-end lower bound
    `candidacy deadline + graceMs + measured sweep latency`, including a worst-legal-configuration case where the
    delays stack additively. Reversal functionality nevertheless ends at authenticated record expiry. This kills
    `MUT-SUPERSEDE-HARD-DELETE-OMITS-GRACE`.

### 11.3 Live PostgreSQL oracles

1. Apply 0001+delta to an empty DB twice and compare catalog definitions/counts; all added hot-table CHECK/FK
   constraints remain `convalidated=false`, added columns remain nullable, no
   `reversal_prepared_gly345_required_check` exists, and no hot-table unique index exists.
2. Seed a pre-GLY-345 schema with live current rows, an older committed/flushed row for the same mapping,
   pending, expired/orphaned, finalized, upload, reclaim-marked, and quarantined rows. Migration preserves all
   rows, changes only the old non-current committed/flushed pair to superseded/null, backfills bindings/retention,
   and leaves current readable.
3. Seed historical mixed classes for one decoded tenant/attempt; migration fails and the surrounding transaction
   leaves the pre-migration schema/data intact.
4. Seed a legacy expiry that is neither MaxUint64 nor exactly claim `created_at_ms + 86_400_000`; migration fails
   atomically rather than treating it as detector. Seed each legal form and verify correct backfill origin/class.
5. Seed 100,001 prepared rows; the first guard aborts with offline/batched-window instructions and no schema/data
   mutation. Seed exactly 100,000 to exercise the documented bounded online path.
6. Race N READ COMMITTED pools on one operation with alternating classes, including a winner paused in
   PostgreSQL speculative insertion. Losers wait for the unique-index outcome: winner commit yields DO NOTHING;
   winner rollback permits one waiter to insert. Exactly one class and no bare binding/anchor remain.
7. Race out-of-order flushes on one mapping. The mapping mutex prevents deadlock and yields maximum ordinal
   current; every other completed claim/prepared pair is superseded/unreferenced.
8. Terminate a session before commit at each named F-A…F-F/L-A…L-C/F11 gate; verify rollback. Terminate after
   server commit but before client acknowledgement; verify replay convergence.
9. Write two legacy non-current flushed rows, one with a future `flushed_at_ms` and one with a sane past value.
   Migration ignores both values and seeds both `superseded_at_ms` values from the migration transaction's DB
   `clock_timestamp()` (within the captured statement interval), giving each a full supersede window from
   migration time. Runtime supersession likewise uses DB `clock_timestamp()`, not supplied replica time. This
   kills `MUT-MIGRATION-TRUST-LEGACY-FLUSHED-AT`.
10. Catalog-test the definition-based legacy-check removal and post-condition: arbitrary anonymous constraint
    names are handled, and no surviving old state check rejects `superseded`.
11. Run preview and mutating selectors over more than the limit across every path; prove single-budget order and
   `SKIP LOCKED` cross-worker exclusivity.
12. `EXPLAIN` confirms operation PK, mapping mutex PK, and reference indexes are used. For the superseded selector,
    the **matter arm** MUST be served by `reversal_prepared_superseded_reclaim_idx
    (superseded_at_ms, prepared_blob_id) WHERE state='superseded'`. The detector `least()` arm MAY use a bitmap or
    sequential scan within superseded rows; its live-migration population is bounded by the 100,000-row guard.
    A future CASE-expression index is an optional optimization, not a GLY-345 requirement.
13. **ORACLE-EXPAND-CONTRACT-OLD-WRITER:** after the new application code is staged but before contract
    enforcement, emulate a not-yet-upgraded writer inserting/updating a legacy-shape prepared row with all five
    GLY-345 metadata columns NULL; this migration's NOT VALID checks/FK accept it. Drive that row through
    `committed -> superseded -> Path-1 selector` and assert the selector treats NULL class as safe matter via
    `COALESCE(retention_class, 'matter')`, marks it when the matter candidacy deadline is due, and never strands
    it. New-code inserts/updates always supply all five and invalid complete metadata is rejected. Catalog
    inspection proves requiredness remains absent until the named post-rollout validation/enforcement migration.
    This kills
    `MUT-MIGRATION-ADDS-REQUIRED-CHECK-DURING-EXPAND` and
    `MUT-MIGRATION-RETENTION-CHECK-REJECTS-NULL-METADATA`.

### 11.4 Real Azure Files adapter/Q6 extension

1. Hold an old pointer between DB select and Files GET, supersede it from another replica, and exercise both the
   original source and within-grace quarantine fallback without a reader deadline.
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
- `MUT-RETENTION-BINDING-KEY-NONINJECTIVE`
- `MUT-RETENTION-BIND-INBAND-OVERRIDE`
- `MUT-ANCHOR-NON-READ-COMMITTED`
- `MUT-ANCHOR-SELECT-THEN-INSERT`

Part B/migration/read safety:

- `MUT-SUPERSEDE-LEAVE-OLD-COMMITTED`
- `MUT-SUPERSEDE-LEAVE-CLAIM-REFERENCE`
- `MUT-SUPERSEDE-NONATOMIC-WITH-CAS`
- `MUT-SUPERSEDE-BEFORE-CAS-WINS`
- `MUT-CAS-LOSER-STAYS-COMMITTED`
- `MUT-SUPERSEDED-FLUSH-RESURRECTS`
- `MUT-SUPERSEDED-FLUSH-FAILS-IDEMPOTENCY`
- `MUT-FLUSHED-NONCURRENT-NO-SELF-HEAL`
- `MUT-SUPERSEDE-RECLAIM-BEFORE-WINDOW`
- `MUT-SUPERSEDE-CANDIDACY-OMITS-DRAIN-MAX`
- `MUT-DETECTOR-SUPERSEDE-DROPS-EXPIRY-FLOOR`
- `MUT-SUPERSEDED-MATTER-NEVER`
- `MUT-NONSUPERSEDED-MATTER-RECLAIMABLE`
- `MUT-RETENTION-NUMERIC-TO-BIGINT`
- `MUT-RETENTION-ORIGIN-TRUST-BACKFILLED-CREATED`
- `MUT-TX-NOW-REPLICA-CLOCK`
- `MUT-SUPERSEDE-SKIP-UNREFERENCED-GUARD`
- `MUT-SUPERSEDE-PRIVATE-BUDGET`
- `MUT-SUPERSEDE-RECOVERY-SELECTOR-OMITTED`
- `MUT-READ-OLD-POINTER-NO-QUARANTINE-FALLBACK`
- `MUT-READ-INVENTS-UNENFORCEABLE-DEADLINE`
- `MUT-QUARANTINE-GRACE-SHORTER-THAN-DRAIN`
- `MUT-SUPERSEDE-WINDOW-SHORTER-THAN-GRACE`
- `MUT-SUPERSEDE-HARD-DELETE-DIRECT`
- `MUT-SUPERSEDE-HARD-DELETE-OMITS-GRACE`
- `MUT-QUARANTINE-MISSING-BOTH-AS-SUCCESS`
- `MUT-MIGRATION-NONIDEMPOTENT`
- `MUT-MIGRATION-DELETE-LEGACY-ROW`
- `MUT-MIGRATION-IGNORE-MIXED-LEGACY-CLASS`
- `MUT-MIGRATION-SILENT-FINITE-MATTER-AS-DETECTOR`
- `MUT-MIGRATION-SKIP-ROW-COUNT-GUARD`
- `MUT-MIGRATION-VALIDATE-HOT-CONSTRAINTS`
- `MUT-MIGRATION-ADDS-REQUIRED-CHECK-DURING-EXPAND`
- `MUT-MIGRATION-RETENTION-CHECK-REJECTS-NULL-METADATA`
- `MUT-MIGRATION-ASSUME-CONSTRAINT-NAME`
- `MUT-MIGRATION-TRUST-LEGACY-FLUSHED-AT`
- `MUT-SELF-HEAL-DROPS-F-A-ROW-LOCK`

The implementer ledger MUST include raw output for typecheck, full tests, live-PG gates, and each named mutant
run alone RED followed by revert/green. Claims are not evidence; logs are.

## 12. Acceptance criteria

1. All invariants in §3 have direct green oracles and named mutation coverage.
2. Public frozen signatures are unchanged; only internal control-plane additions exist.
3. A classifier cannot create mixed operation classes across replicas or crash/replay.
4. Every old committed row either remains exact current/pending or is transactionally superseded and detached;
   no completed non-current committed blob is pinned.
5. Superseded matter candidacy is `superseded_at + MAX(SUPERSEDE_RETENTION_MS, READ_DRAIN_MS)`, including
   MaxUint64 records; detector candidacy is
   `MAX(superseded_at + READ_DRAIN_MS, MIN(original expiry, superseded_at + SUPERSEDE_RETENTION_MS))`.
   The detector `MIN` is a defensive floor and is inert at production `window >= grace = 24h`. Bytes disappear
   no earlier than candidacy plus quarantine `graceMs` plus sweep latency, and only in operator `full` mode;
   worst legal configuration stacks those waits. Reversal functionality still ends exactly at authenticated
   record expiry, and non-superseded committed matter remains outside every selector.
6. An old-pointer read racing rename succeeds from original or quarantine while bytes remain in grace; no
   unimplementable lease/deadline is claimed, both-path absence is fixed-surface, and quarantine precedes delete.
7. Existing claim expiry/idempotency, ordinal CAS, three-path recovery, global budget, and fixed error surface do
   not regress.
8. The additive migration succeeds twice on empty and bounded populated databases, leaves new hot-table
   constraints NOT VALID/columns nullable, contains no DB requiredness check, accepts old-writer null metadata,
   and fails atomically on row-count, expiry, class, key, or pointer ambiguity. The GLY-345 application release
   precedes migration everywhere writers exist; writer activation follows migration.
9. Typecheck, full Vitest, shared dev/PG conformance, live PG, Azure/Q6 extensions, and all named mutations are
   evidenced before review approval.

## 13. Explicit non-goals

1. No source implementation, infrastructure change, database execution, commit, push, PR, or deployment in this
   round.
2. No change to how business policy chooses `matter` versus `detector-only`; only enforcement of consistency.
3. No operation-binding garbage collection. A future design needs an explicit attempt-reuse horizon and cannot
   infer safety from blob absence.
4. No in-band first-binding override. Remediation is a new attempt ID. A future class-widening-only audited
   governance override requires a separate authorized ticket because it creates a new PHI-retention attack
   surface.
5. No direct deletion API, list/export/debug widening, raw-canonical storage, or PHI in control-plane metadata.
6. No reclamation of live current matter records and no reinterpretation of MaxUint64 for those committed rows;
   superseded matter is intentionally governed by the independent 30-day window.
7. No durable per-reader lease, adapter deadline, or claim that a non-transactional pointer read pins a reader.
   Rename delay plus original/quarantine fallback and grace are the chosen model.
8. No `reversal_prepared_gly345_required_check`, `VALIDATE CONSTRAINT`, `SET NOT NULL`, or hot-table unique-index
   build in this online migration. The DB-level requiredness check and constraint validation belong only to a
   separately authorized **GLY-345 follow-up validation/enforcement migration**, gated on proof that the
   application/control-plane code was deployed to the full writer fleet before this migration and that no old
   writer remains. That follow-up migration and its rollout/window are explicitly out of scope. Today only the
   reclaim job and smoke run migrations and there are no production application writers, so this repository's
   current-world writer-exposure interval is nil.
9. No replacement of PostgreSQL/Azure Files topology, encryption/AAD format, KEK/DEK behavior, or nonce scheme.
10. No cleanup of unrelated pre-existing worktree changes.

## 14. Open questions

None for the principal. This v3 adopts all F1–F11 and D1–D6 rulings. Superseded matter gets a configurable 30-day
default window; detector retains its defensive expiry floor; effective candidacy also includes the drain
heuristic. The online expand migration is nullable/NOT VALID with a 100,000-row guard and no requiredness check;
application code precedes migration anywhere writers exist. First-seen bindings have no in-band override. DB
time is authoritative, and quarantine fallback+grace carry read correctness.

## 15. Opus finding disposition

| Finding | Disposition and normative section(s) |
|---|---|
| F1 | Adopted independent supersede retention: rationale/formula §2.2, invariant §3.10, options/materialization §4.1, selector §8.1, acceptance §12.5. |
| F2 | Drain demoted to heuristic; no lease/deadline: §3.11, §8.2, read oracle §11.2.9, non-goal §13.7. |
| F3 | Nullable columns, NOT VALID constraints/FK, no hot unique build, 100,000-row fatal guard and availability bound: §4.2; validation non-goal §13.8. |
| F4 | Normative READ COMMITTED plus PostgreSQL speculative-insertion wait and forbidden simplifications: §5.2; live race oracle §11.3.6. |
| F5 | DB `clock_timestamp()` is authoritative; legacy supersession starts at migration DB time: migration SQL §4.2, runtime §6.1, selector §8.1, oracle §11.3.9. |
| F6 | `retention_origin=anchored|backfilled`; backfilled creation time forbidden for superseded decisions: §§4.1–4.2, §8.1, oracle §11.2.6. |
| F7 | Migration-fatal expiry-form guard prevents silent finite-matter misclassification: §4.2, oracle §11.3.4. |
| F8 | No in-band override; wrong winner requires new attempt; future widening-only audited path needs a ticket: §3.16, §5.2, §7.3, §13.4. |
| F9 | Legacy checks dropped by `pg_constraint` definition lookup with post-condition: §4.2, oracle §11.3.10. |
| F10 | Injective-key mutant+crafted alias oracle §11.1.8/§11.5; intra-flush gates §6.2/§9; startup inequality oracle §11.2.11; blob-absent retry §11.1.7. |
| F11 | Non-current flushed claims self-heal through one data-modifying CTE and return success: §6.2, state tables §7.1–§7.2, crash gates §9, oracle §11.2.12. |

## 16. Delta finding disposition

| Finding | Disposition and normative section(s) |
|---|---|
| D1 | Expand/contract removes the requiredness check and makes retention validation NULL-tolerant; code-before-migration rollout and nil current-world exposure are explicit: migration contract/DDL §4.2, oracle §11.3.1/§11.3.13, acceptance §12.8, non-goal §13.8. |
| D2 | Exact candidacy and end-to-end byte-deletion formulas, additive worst case, operator-full gate, and unchanged functional expiry: §2.2, §4.1, selector §8.1, oracle §11.2.5/§11.2.13, acceptance §12.5. |
| D3 | Every migrated legacy superseded row is seeded from migration DB now, ignoring `flushed_at_ms`: DDL §4.2, oracle §11.3.9. |
| D4 | The matter arm must use the superseded partial index; detector scan flexibility and optional future CASE index are explicit: §11.3.12. |
| D5 | Self-heal reuses F-A verbatim, including old claim/prepared `FOR UPDATE` locks: protocol §6.2, state table §7.1, crash gate §9, oracle §11.2.12. |
| D6 | Detector `least()` remains a defensive floor and is inert at production `window >= grace = 24h`: §2.2, §4.1, selector §8.1, oracle §11.2.5, acceptance §12.5. |
