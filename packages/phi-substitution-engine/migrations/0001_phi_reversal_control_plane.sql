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
