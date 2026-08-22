-- =============================================================================================
-- GLY-373 §3.2.4 — HISTORICAL ROW AUDIT.  READ-ONLY.  RELEASE PRECONDITION.
--
-- THIS FILE PERFORMS NO SCHEMA MIGRATION, NO DATA REWRITE, AND NO WRITE OF ANY KIND.
--
-- WHAT IT LOOKS FOR.  The NUL joins that scope reversal keys were documented as injective but
-- nothing enforced it: ("a", "b\0c") and ("a\0b", "c") produce the IDENTICAL joined string, so two
-- distinct tenants could alias onto one reversal row.  §3.2.2 stops NEW aliased rows at ingestion;
-- it does nothing about rows already persisted, because the aliasing happens in `mappingKeyOf` /
-- `idempotencyKeyOf` BEFORE persistence and `encodeTextKey` faithfully base64url-encodes the
-- already-aliased logical key.  A decoded key whose NUL count EXCEEDS its separator count contains
-- a NUL *inside* a field, which is exactly the aliasing signature.
--
-- COVERAGE: all SEVEN key-bearing tables and all ELEVEN encoded key columns.  No exclusions remain.
-- Two earlier exclusions (`reversal_nonce_counter`, `reversal_dek_generation.dek_generation_id`)
-- were WITHDRAWN on evidence: both ARE `b64url-v1:`-encoded four-field joins, and one is half a
-- composite primary key.
--
-- FROZEN ENCODING FACTS (inputs to this audit; if either changes the audit is invalid and must be
-- re-derived):
--   * key prefix literal `b64url-v1:`            — postgres-control-plane.ts:43
--   * payload `Buffer.from(v,"utf8").toString("base64url")` — :168-172
-- Base64url is unpadded and uses `-`/`_`, so the SQL translates the alphabet and re-pads.
--
-- WHY NUL COUNTING IS DONE ON `bytea` VIA `get_byte`, NOT `convert_from(…,'UTF8')`: PostgreSQL
-- `text` CANNOT HOLD U+0000, so converting an aliased key would RAISE rather than count it — the
-- audit would fail to see precisely the rows it exists to find.
--
-- WHY THE `decodable` PRE-FILTER IS NORMATIVE, NOT DEFENSIVE STYLE: `decode(…,'base64')` RAISES on
-- a malformed payload, so ONE corrupt row would abort the entire BLOCKING query rather than
-- returning a result — the release precondition would be unevaluable exactly when the store is in
-- the state most worth inspecting.  Such rows are routed into a separate `undecodable_payload`
-- count instead, and ONLY the filtered set is decoded.
--
-- THE CHECK IS TWO-STAGE AND THE SECOND STAGE IS NOT OPTIONAL.  Stage one (`shape_ok`) is an
-- alphabet-and-length test: necessary but NOT sufficient, because it admits NON-CANONICAL TAIL BITS
-- the encoder can never emit (executed: "AB" -> 00 -> re-encodes as "AA"; "AAB" -> "AAA";
-- "A-" -> "Aw").  Stage two (`decodable`) RE-ENCODES the decoded bytes and requires byte equality
-- with the stored payload, which is exactly canonicality.  The two `replace` calls are required
-- because PostgreSQL's `encode(…,'base64')` wraps output with newlines every 76 characters — the
-- same idiom migration 0001:249 already uses for the same reason.  A row failing EITHER stage is
-- counted as `undecodable_payload`; the NULL from a skipped decode propagates through
-- `shape_ok AND …` as FALSE, never as NULL, so no row escapes classification.
--
-- NORMATIVE RUN ORDERING.  On any durable store that PREDATES the GLY-345 `operation_key` delta,
-- Query 1 MUST be run BEFORE any migration that reads `operation_key` — that is, before
-- migrations/0001 is applied — over the columns that exist there (`mapping_key`,
-- `idempotency_key`), with the `operation_key` and `reversal_operation_retention` rows DROPPED from
-- the statement for that run and the omission RECORDED IN THE MANIFEST.  Running the audit only
-- AFTER migration would let `gly345_operation_key_tenant_mismatch` abort the whole transaction, or
-- let the backfill bind two logically distinct operations to one retention row, pre-empting the
-- finding this audit exists to produce.
--
-- RESULT HANDLING
--   Query 1  — excess NUL *and* undecodable payload ... BLOCKING, must return zero rows
--   Query 1b — unexpected encoding .................... BLOCKING, must return zero rows
--   Query 2  — U+FFFD suspects ....................... NON-BLOCKING, report for principal review
--   Query 2a — decodable-key export .................. NON-BLOCKING, input feed for Query 2b;
--              a non-empty result is NORMAL and is NOT a finding; an empty result is legitimate on
--              an empty or newly-provisioned store.  THE PREDICATE MUST NOT BE NARROWED.
--   Query 2b — UTF-8 round-trip suspects ............. NON-BLOCKING, run OUTSIDE SQL, see
--              jobs/gly373-key-audit-2b.ts
--
-- Queries 2, 2a and 2b are REPORTING OBLIGATIONS, NOT A GATE: their rows CANNOT be distinguished
-- from legitimate U+FFFD content after the fact, so blocking on them would block on evidence that
-- can never be resolved either way.  NO ROW MAY BE DELETED OR REWRITTEN ON THAT EVIDENCE.
-- Attach the Query 2a export and the Query 2b output to the release manifest WHETHER OR NOT EITHER
-- IS EMPTY — what the manifest establishes is that the export was UNFILTERED, never that it was
-- non-empty.
--
-- ON ANY BLOCKING FINDING: halt the release and enumerate the offending rows with Query 1c below.
-- =============================================================================================

-- ---------------------------------------------------------------------------------------------
-- QUERY 1 — excess-NUL count AND undecodable payload.  BLOCKING.  MUST RETURN ZERO ROWS.
-- Both finding kinds are BLOCKING: an `undecodable_payload` row is a `b64url-v1:`-prefixed value
-- whose payload is NOT canonical base64url, i.e. a value `encodeTextKey` COULD NOT HAVE EMITTED.
--
-- SCOPED TO CANONICALITY AND NO FURTHER: `encodeTextKey` also guarantees VALID UTF-8, and canonical
-- base64url does not.  Executed counterexample — `b64url-v1:gA` decodes to the single byte 0x80,
-- which is canonical base64url, carries zero NULs and contains no EF BF BD, so NONE of the three
-- finding-producing statements (1, 1b, 2) returns a row for it.  PostgreSQL cannot close that in
-- the same statement (`convert_from(…,'UTF8')` RAISES on invalid bytes, which is why NUL counting
-- is done on `bytea` in the first place).  Query 2b closes it outside SQL.
-- ---------------------------------------------------------------------------------------------
WITH keys AS (
  SELECT 'reversal_prepared'            AS tbl, 'mapping_key'     AS col, 3 AS max_nul, mapping_key     AS enc FROM reversal_prepared
  UNION ALL SELECT 'reversal_prepared',            'idempotency_key', 2, idempotency_key FROM reversal_prepared
  UNION ALL SELECT 'reversal_prepared',            'operation_key',   1, operation_key   FROM reversal_prepared WHERE operation_key IS NOT NULL
  UNION ALL SELECT 'reversal_claim',               'mapping_key',     3, mapping_key     FROM reversal_claim
  UNION ALL SELECT 'reversal_claim',               'idempotency_key', 2, idempotency_key FROM reversal_claim
  UNION ALL SELECT 'reversal_current',             'mapping_key',     3, mapping_key     FROM reversal_current
  UNION ALL SELECT 'reversal_ordinal_seq',         'mapping_key',     3, mapping_key     FROM reversal_ordinal_seq
  UNION ALL SELECT 'reversal_operation_retention', 'operation_key',   1, operation_key   FROM reversal_operation_retention
  UNION ALL SELECT 'reversal_dek_generation',      'dek_scope_key',   2, dek_scope_key   FROM reversal_dek_generation
  UNION ALL SELECT 'reversal_dek_generation',      'dek_generation_id', 3, dek_generation_id FROM reversal_dek_generation
  UNION ALL SELECT 'reversal_nonce_counter',       'dek_generation_id', 3, dek_generation_id FROM reversal_nonce_counter
),
stripped AS (
  SELECT tbl, col, max_nul, enc,
         substring(enc from length('b64url-v1:') + 1) AS b64u,
         enc LIKE 'b64url-v1:%'                       AS has_prefix
  FROM keys
),
classified AS (
  SELECT s.tbl, s.col, s.max_nul, s.enc, s.b64u, s.has_prefix,
         (s.has_prefix
          AND s.b64u ~ '^[A-Za-z0-9_-]*$'
          AND length(s.b64u) % 4 <> 1) AS shape_ok
  FROM stripped s
),
decoded AS (
  SELECT c.tbl, c.col, c.max_nul, c.enc, c.b64u, c.has_prefix, c.shape_ok,
         CASE WHEN c.shape_ok THEN
           decode(
             translate(c.b64u, '-_', '+/')
             || repeat('=', (4 - (length(c.b64u) % 4)) % 4),
             'base64')
         END AS raw
  FROM classified c
),
checked AS (
  SELECT d.tbl, d.col, d.max_nul, d.enc, d.b64u, d.has_prefix, d.shape_ok, d.raw,
         (d.shape_ok
          AND rtrim(
                translate(
                  replace(replace(encode(d.raw, 'base64'), E'\n', ''), E'\r', ''),
                  '+/', '-_'),
                '=') = d.b64u) AS decodable
  FROM decoded d
)
SELECT d.tbl, d.col, 'excess_nul' AS finding, count(*) AS offending_rows
FROM checked d
WHERE d.decodable
  AND (SELECT count(*) FROM generate_series(0, octet_length(d.raw) - 1) g
       WHERE get_byte(d.raw, g) = 0) > d.max_nul
GROUP BY d.tbl, d.col
UNION ALL
SELECT d.tbl, d.col, 'undecodable_payload' AS finding, count(*) AS offending_rows
FROM checked d
WHERE d.has_prefix AND NOT d.decodable
GROUP BY d.tbl, d.col
ORDER BY 1, 2, 3;

-- ---------------------------------------------------------------------------------------------
-- QUERY 1b — unexpected encoding.  BLOCKING.  MUST RETURN ZERO ROWS.
-- Decodes NOTHING, so it needs no `decodable` filter and CANNOT raise on a corrupt payload — which
-- is the point: it must remain runnable on precisely the store Query 1's decode step would refuse.
-- A row without the `b64url-v1:` prefix would make `decodeTextKey` throw
-- (postgres-control-plane.ts:174-177); it is a separate defect and MUST be reported rather than
-- skipped by Query 1's `has_prefix` guard.
-- ---------------------------------------------------------------------------------------------
WITH keys AS (
  SELECT 'reversal_prepared'            AS tbl, 'mapping_key'     AS col, 3 AS max_nul, mapping_key     AS enc FROM reversal_prepared
  UNION ALL SELECT 'reversal_prepared',            'idempotency_key', 2, idempotency_key FROM reversal_prepared
  UNION ALL SELECT 'reversal_prepared',            'operation_key',   1, operation_key   FROM reversal_prepared WHERE operation_key IS NOT NULL
  UNION ALL SELECT 'reversal_claim',               'mapping_key',     3, mapping_key     FROM reversal_claim
  UNION ALL SELECT 'reversal_claim',               'idempotency_key', 2, idempotency_key FROM reversal_claim
  UNION ALL SELECT 'reversal_current',             'mapping_key',     3, mapping_key     FROM reversal_current
  UNION ALL SELECT 'reversal_ordinal_seq',         'mapping_key',     3, mapping_key     FROM reversal_ordinal_seq
  UNION ALL SELECT 'reversal_operation_retention', 'operation_key',   1, operation_key   FROM reversal_operation_retention
  UNION ALL SELECT 'reversal_dek_generation',      'dek_scope_key',   2, dek_scope_key   FROM reversal_dek_generation
  UNION ALL SELECT 'reversal_dek_generation',      'dek_generation_id', 3, dek_generation_id FROM reversal_dek_generation
  UNION ALL SELECT 'reversal_nonce_counter',       'dek_generation_id', 3, dek_generation_id FROM reversal_nonce_counter
),
stripped AS (
  SELECT tbl, col, max_nul, enc,
         substring(enc from length('b64url-v1:') + 1) AS b64u,
         enc LIKE 'b64url-v1:%'                       AS has_prefix
  FROM keys
)
SELECT tbl, col, count(*) AS unprefixed_rows
FROM stripped
WHERE NOT has_prefix
GROUP BY tbl, col
ORDER BY 1, 2;

-- ---------------------------------------------------------------------------------------------
-- QUERY 2 — U+FFFD "suspect" listing.  NON-BLOCKING.
-- U+FFFD is EF BF BD in UTF-8, matched on `bytea` without decoding to `text`.
-- A returned row is SUSPECT, NOT PROVEN ALIASED: after the U+FFFD substitution, a key derived from
-- a lone surrogate and a key derived from GENUINE U+FFFD content are byte-identical and cannot be
-- told apart after the fact.  Undecodable rows are not silently dropped by the filter here —
-- Query 1 counts them as a blocking finding, so every prefixed row is accounted for by exactly one
-- of the two statements.
-- ---------------------------------------------------------------------------------------------
WITH keys AS (
  SELECT 'reversal_prepared'            AS tbl, 'mapping_key'     AS col, 3 AS max_nul, mapping_key     AS enc FROM reversal_prepared
  UNION ALL SELECT 'reversal_prepared',            'idempotency_key', 2, idempotency_key FROM reversal_prepared
  UNION ALL SELECT 'reversal_prepared',            'operation_key',   1, operation_key   FROM reversal_prepared WHERE operation_key IS NOT NULL
  UNION ALL SELECT 'reversal_claim',               'mapping_key',     3, mapping_key     FROM reversal_claim
  UNION ALL SELECT 'reversal_claim',               'idempotency_key', 2, idempotency_key FROM reversal_claim
  UNION ALL SELECT 'reversal_current',             'mapping_key',     3, mapping_key     FROM reversal_current
  UNION ALL SELECT 'reversal_ordinal_seq',         'mapping_key',     3, mapping_key     FROM reversal_ordinal_seq
  UNION ALL SELECT 'reversal_operation_retention', 'operation_key',   1, operation_key   FROM reversal_operation_retention
  UNION ALL SELECT 'reversal_dek_generation',      'dek_scope_key',   2, dek_scope_key   FROM reversal_dek_generation
  UNION ALL SELECT 'reversal_dek_generation',      'dek_generation_id', 3, dek_generation_id FROM reversal_dek_generation
  UNION ALL SELECT 'reversal_nonce_counter',       'dek_generation_id', 3, dek_generation_id FROM reversal_nonce_counter
),
stripped AS (
  SELECT tbl, col, max_nul, enc,
         substring(enc from length('b64url-v1:') + 1) AS b64u,
         enc LIKE 'b64url-v1:%'                       AS has_prefix
  FROM keys
),
classified AS (
  SELECT s.tbl, s.col, s.max_nul, s.enc, s.b64u, s.has_prefix,
         (s.has_prefix
          AND s.b64u ~ '^[A-Za-z0-9_-]*$'
          AND length(s.b64u) % 4 <> 1) AS shape_ok
  FROM stripped s
),
decoded AS (
  SELECT c.tbl, c.col, c.max_nul, c.enc, c.b64u, c.has_prefix, c.shape_ok,
         CASE WHEN c.shape_ok THEN
           decode(
             translate(c.b64u, '-_', '+/')
             || repeat('=', (4 - (length(c.b64u) % 4)) % 4),
             'base64')
         END AS raw
  FROM classified c
),
checked AS (
  SELECT d.tbl, d.col, d.max_nul, d.enc, d.b64u, d.has_prefix, d.shape_ok, d.raw,
         (d.shape_ok
          AND rtrim(
                translate(
                  replace(replace(encode(d.raw, 'base64'), E'\n', ''), E'\r', ''),
                  '+/', '-_'),
                '=') = d.b64u) AS decodable
  FROM decoded d
)
SELECT d.tbl, d.col, d.enc AS encoded_key
FROM checked d
WHERE d.decodable
  AND position('\xefbfbd'::bytea in d.raw) > 0
ORDER BY 1, 2, 3;

-- ---------------------------------------------------------------------------------------------
-- QUERY 2a — decodable-key export.  NON-BLOCKING.  THE INPUT FEED FOR QUERY 2b.
--
-- WHY THIS STATEMENT EXISTS (ruling A-01).  Query 2b iterates "each (tbl, col, enc) exported by the
-- audit run", and before this statement NO statement exported that set: Queries 1 and 1b are
-- GROUP BY aggregates projecting only (tbl, col, count), Query 2 is gated on the U+FFFD match, and
-- Query 1c runs only when a blocking finding has ALREADY halted the release.  The class 2b exists
-- to detect is exactly the class none of them emits, so 2b's input set was EMPTY for that class and
-- the check was VACUOUS.
--
-- `decodable` here has EXACTLY the semantics it has in Queries 1 and 2 — shape test AND canonicality
-- re-encode — so non-canonical rows are excluded here as they are there and remain Query 1's
-- blocking finding.  The two sets are disjoint by construction.  Row volume scales with the store;
-- the export may be streamed or paged, but THE PREDICATE MUST NOT BE NARROWED — a filtered export
-- reintroduces exactly the empty-input-set defect this statement was added to fix.
-- Keys are exported AS STORED, never decoded.
-- ---------------------------------------------------------------------------------------------
WITH keys AS (
  SELECT 'reversal_prepared'            AS tbl, 'mapping_key'     AS col, 3 AS max_nul, mapping_key     AS enc FROM reversal_prepared
  UNION ALL SELECT 'reversal_prepared',            'idempotency_key', 2, idempotency_key FROM reversal_prepared
  UNION ALL SELECT 'reversal_prepared',            'operation_key',   1, operation_key   FROM reversal_prepared WHERE operation_key IS NOT NULL
  UNION ALL SELECT 'reversal_claim',               'mapping_key',     3, mapping_key     FROM reversal_claim
  UNION ALL SELECT 'reversal_claim',               'idempotency_key', 2, idempotency_key FROM reversal_claim
  UNION ALL SELECT 'reversal_current',             'mapping_key',     3, mapping_key     FROM reversal_current
  UNION ALL SELECT 'reversal_ordinal_seq',         'mapping_key',     3, mapping_key     FROM reversal_ordinal_seq
  UNION ALL SELECT 'reversal_operation_retention', 'operation_key',   1, operation_key   FROM reversal_operation_retention
  UNION ALL SELECT 'reversal_dek_generation',      'dek_scope_key',   2, dek_scope_key   FROM reversal_dek_generation
  UNION ALL SELECT 'reversal_dek_generation',      'dek_generation_id', 3, dek_generation_id FROM reversal_dek_generation
  UNION ALL SELECT 'reversal_nonce_counter',       'dek_generation_id', 3, dek_generation_id FROM reversal_nonce_counter
),
stripped AS (
  SELECT tbl, col, max_nul, enc,
         substring(enc from length('b64url-v1:') + 1) AS b64u,
         enc LIKE 'b64url-v1:%'                       AS has_prefix
  FROM keys
),
classified AS (
  SELECT s.tbl, s.col, s.max_nul, s.enc, s.b64u, s.has_prefix,
         (s.has_prefix
          AND s.b64u ~ '^[A-Za-z0-9_-]*$'
          AND length(s.b64u) % 4 <> 1) AS shape_ok
  FROM stripped s
),
decoded AS (
  SELECT c.tbl, c.col, c.max_nul, c.enc, c.b64u, c.has_prefix, c.shape_ok,
         CASE WHEN c.shape_ok THEN
           decode(
             translate(c.b64u, '-_', '+/')
             || repeat('=', (4 - (length(c.b64u) % 4)) % 4),
             'base64')
         END AS raw
  FROM classified c
),
checked AS (
  SELECT d.tbl, d.col, d.max_nul, d.enc, d.b64u, d.has_prefix, d.shape_ok, d.raw,
         (d.shape_ok
          AND rtrim(
                translate(
                  replace(replace(encode(d.raw, 'base64'), E'\n', ''), E'\r', ''),
                  '+/', '-_'),
                '=') = d.b64u) AS decodable
  FROM decoded d
)
SELECT d.tbl, d.col, d.enc FROM checked d WHERE d.decodable;

-- ---------------------------------------------------------------------------------------------
-- QUERY 1c — THE ENUMERATION ITSELF.  Run ONLY when Query 1 or 1b has returned a finding.
--
-- Queries 1 and 1b are GROUP BY aggregates and cannot produce the per-row record the escalation
-- mandates.  Run each blocking finding kind this way — `excess_nul`, `undecodable_payload` AND
-- Query 1b's `missing_prefix` alike; all three are projected below in a single statement.
--
-- TWO CONSTRAINTS ON THE RESULT:
--   1. The encoded key is reported AS STORED, never decoded into the ticket — a NUL-bearing or
--      ill-formed key is exactly what must not be re-emitted as text.  DO NOT project
--      `encode(raw,'base64')`: that emits PADDED STANDARD base64 WITHOUT the prefix
--      ({"stored":"b64url-v1:YQA","projection":"YQA="}), a different string from the one on disk,
--      which would send an investigator looking for a row that does not exist.
--   2. The tenant is ALWAYS AVAILABLE: every audited table stores `tenant_id` as its own column
--      (migrations/0001:3,12,20,56,74,83,127), independent of the key encoding.  An earlier claim
--      that the tenant was carried by the encoding prefix and could be unrecoverable was WRONG, and
--      the correction matters — it would have licensed reporting NULL tenants for exactly the rows
--      most in need of attribution.
--
-- NO AUTOMATIC REWRITE, NO MERGE, NO KEY-SHAPE MIGRATION.  Any remediation is a separately
-- specified and ruled work item.  The expected result is ZERO, because both consumers generate ids
-- from internal identifier schemes; a non-zero count is a CROSS-TENANT PHI FINDING and escalates
-- immediately.
--
-- COVERS ALL SEVEN TABLES AND ALL ELEVEN (table, column) PAIRS, and ALL THREE blocking finding
-- kinds.  An earlier draft enumerated only `reversal_prepared.mapping_key` and left the escalation
-- unable to name the offending rows for the other ten pairs, and had no enumeration at all for
-- Query 1b's `missing_prefix` finding — so the one query the release halt depends on covered less
-- than a tenth of the surface the halt is triggered from.  The `keys` union below is BYTE-FOR-BYTE
-- the union of Queries 1 and 1b, extended only with `tenant_id`, so the three statements cannot
-- drift out of coverage with one another.
--
-- `missing_prefix` rows are projected from `stripped`, NOT from `checked`: a row without the
-- `b64url-v1:` prefix has no payload to shape-test, and routing it through the decode chain would
-- report it as `undecodable_payload` and lose the distinction Query 1b exists to draw.
-- ---------------------------------------------------------------------------------------------
WITH keys AS (
  SELECT 'reversal_prepared'            AS tbl, 'mapping_key'     AS col, 3 AS max_nul, tenant_id, mapping_key     AS enc FROM reversal_prepared
  UNION ALL SELECT 'reversal_prepared',            'idempotency_key',   2, tenant_id, idempotency_key   FROM reversal_prepared
  UNION ALL SELECT 'reversal_prepared',            'operation_key',     1, tenant_id, operation_key     FROM reversal_prepared WHERE operation_key IS NOT NULL
  UNION ALL SELECT 'reversal_claim',               'mapping_key',       3, tenant_id, mapping_key       FROM reversal_claim
  UNION ALL SELECT 'reversal_claim',               'idempotency_key',   2, tenant_id, idempotency_key   FROM reversal_claim
  UNION ALL SELECT 'reversal_current',             'mapping_key',       3, tenant_id, mapping_key       FROM reversal_current
  UNION ALL SELECT 'reversal_ordinal_seq',         'mapping_key',       3, tenant_id, mapping_key       FROM reversal_ordinal_seq
  UNION ALL SELECT 'reversal_operation_retention', 'operation_key',     1, tenant_id, operation_key     FROM reversal_operation_retention
  UNION ALL SELECT 'reversal_dek_generation',      'dek_scope_key',     2, tenant_id, dek_scope_key     FROM reversal_dek_generation
  UNION ALL SELECT 'reversal_dek_generation',      'dek_generation_id', 3, tenant_id, dek_generation_id FROM reversal_dek_generation
  UNION ALL SELECT 'reversal_nonce_counter',       'dek_generation_id', 3, tenant_id, dek_generation_id FROM reversal_nonce_counter
),
stripped AS (
  SELECT tbl, col, max_nul, tenant_id, enc,
         substring(enc from length('b64url-v1:') + 1) AS b64u,
         enc LIKE 'b64url-v1:%'                       AS has_prefix
  FROM keys
),
classified AS (
  SELECT s.*, (s.has_prefix AND s.b64u ~ '^[A-Za-z0-9_-]*$' AND length(s.b64u) % 4 <> 1) AS shape_ok
  FROM stripped s
),
decoded AS (
  SELECT c.*, CASE WHEN c.shape_ok THEN
           decode(translate(c.b64u, '-_', '+/') || repeat('=', (4 - (length(c.b64u) % 4)) % 4), 'base64')
         END AS raw
  FROM classified c
),
checked AS (
  SELECT d.*, (d.shape_ok AND rtrim(translate(replace(replace(encode(d.raw,'base64'), E'\n',''), E'\r',''), '+/','-_'), '=') = d.b64u) AS decodable
  FROM decoded d
)
SELECT tbl, col, tenant_id, enc AS stored_key, 'excess_nul' AS finding
FROM checked
WHERE decodable
  AND (SELECT count(*) FROM generate_series(0, octet_length(raw) - 1) g WHERE get_byte(raw, g) = 0) > max_nul
UNION ALL
SELECT tbl, col, tenant_id, enc AS stored_key, 'undecodable_payload' AS finding
FROM checked
WHERE has_prefix AND NOT decodable
UNION ALL
SELECT tbl, col, tenant_id, enc AS stored_key, 'missing_prefix' AS finding
FROM stripped
WHERE NOT has_prefix
ORDER BY 1, 2, 5, 3;
