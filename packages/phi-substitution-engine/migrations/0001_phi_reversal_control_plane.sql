CREATE TABLE IF NOT EXISTS reversal_dek_generation (
  dek_scope_key TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  matter_id TEXT NOT NULL,
  purpose TEXT NOT NULL,
  dek_generation_id TEXT NOT NULL,
  wrapped_dek BYTEA NOT NULL,
  created_at_ms BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS reversal_nonce_counter (
  tenant_id TEXT NOT NULL,
  dek_generation_id TEXT NOT NULL,
  next_counter BIGINT NOT NULL DEFAULT 0,
  PRIMARY KEY (tenant_id, dek_generation_id)
);

CREATE TABLE IF NOT EXISTS reversal_prepared (
  prepared_blob_id UUID PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  mapping_key TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  scope_digest TEXT NOT NULL,
  staging_path TEXT NOT NULL,
  blob_path TEXT NOT NULL,
  created_at_ms BIGINT NOT NULL,
  state TEXT NOT NULL CHECK (
    state IN (
      'uploading',
      'finalized',
      'committed',
      'orphaned',
      'upload_reclaim_marked',
      'reclaim_marked',
      'quarantined'
    )
  ),
  blob_etag TEXT,
  blob_len BIGINT CHECK (blob_len IS NULL OR blob_len >= 0),
  quarantined_at_ms BIGINT,
  CHECK (
    (state IN ('uploading', 'upload_reclaim_marked') AND blob_etag IS NULL AND blob_len IS NULL)
    OR
    (state IN ('finalized', 'committed', 'orphaned', 'reclaim_marked', 'quarantined')
      AND blob_etag IS NOT NULL AND blob_len IS NOT NULL)
  ),
  CHECK (
    (state = 'quarantined' AND quarantined_at_ms IS NOT NULL)
    OR
    (state <> 'quarantined' AND quarantined_at_ms IS NULL)
  )
);

CREATE TABLE IF NOT EXISTS reversal_claim (
  idempotency_key TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  mapping_key TEXT NOT NULL,
  scope_digest TEXT NOT NULL,
  commit_handle UUID NOT NULL UNIQUE,
  prepared_blob_id UUID REFERENCES reversal_prepared(prepared_blob_id),
  ordinal BIGINT NOT NULL,
  created_at_ms BIGINT NOT NULL,
  expires_at_ms NUMERIC(20,0) NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('pending', 'flushed', 'expired')),
  CHECK (
    (state = 'expired' AND prepared_blob_id IS NULL)
    OR
    (state IN ('pending', 'flushed') AND prepared_blob_id IS NOT NULL)
  )
);

CREATE TABLE IF NOT EXISTS reversal_current (
  mapping_key TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  commit_handle UUID NOT NULL,
  prepared_blob_id UUID NOT NULL REFERENCES reversal_prepared(prepared_blob_id),
  ordinal BIGINT NOT NULL,
  flushed_at_ms BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS reversal_ordinal_seq (
  mapping_key TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  next_ordinal BIGINT NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS reversal_dek_generation_tenant_idx
  ON reversal_dek_generation (tenant_id);
CREATE INDEX IF NOT EXISTS reversal_nonce_counter_tenant_idx
  ON reversal_nonce_counter (tenant_id);
CREATE INDEX IF NOT EXISTS reversal_prepared_tenant_idx
  ON reversal_prepared (tenant_id);
CREATE INDEX IF NOT EXISTS reversal_prepared_reclaim_idx
  ON reversal_prepared (state, created_at_ms);
CREATE INDEX IF NOT EXISTS reversal_claim_tenant_idx
  ON reversal_claim (tenant_id);
CREATE INDEX IF NOT EXISTS reversal_claim_mapping_idx
  ON reversal_claim (mapping_key);
CREATE INDEX IF NOT EXISTS reversal_claim_prepared_idx
  ON reversal_claim (prepared_blob_id) WHERE prepared_blob_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS reversal_current_tenant_idx
  ON reversal_current (tenant_id);
CREATE INDEX IF NOT EXISTS reversal_current_prepared_idx
  ON reversal_current (prepared_blob_id);
CREATE INDEX IF NOT EXISTS reversal_ordinal_seq_tenant_idx
  ON reversal_ordinal_seq (tenant_id);


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
