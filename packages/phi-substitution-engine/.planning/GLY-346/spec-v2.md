# GLY-346 spec v2 — control-plane-primary durable reversal store (supersedes spec.md)

**Author:** Claude (architect). **v1 verdict:** GPT-5.6-sol cross-family spec-check **BLOCKED** spec.md
(5 CRIT + 6 HIGH) — root cause: Azure Files is not a transactional substrate, so create-if-not-exists +
rename cannot reproduce the frozen store's synchronous atomic-publish. v2 INVERTS the architecture: a
transactional **control plane** owns all ordering/claim/pointer/nonce state; Azure Files holds only
immutable ciphertext blobs. Every v1 finding is traced to its v2 resolution in §9.

**Tier:** T2. **Base:** a445a50. **Ticket:** GLY-346 (parent GLY-335; implements GLY-344 reclamation).
**Build team (Alex 2026-08-12):** many GPT-5.6-sol implementer agents (author) + an Opus-5 reviewer
(cross-family), orchestrator integrates → PR → cross-family review → green CI → merge.

## 1. Architecture

Two substrates sit BEHIND the frozen `SpoolVolume` port (the port is UNCHANGED — the Azure impl composes
both internally; core never sees either). Reclamation is a SEPARATE `SpoolMaintenance` interface (least
authority; the request-path store never holds delete authority — F6).

```
                 DurableReversalStore (frozen core, unchanged)
                          │ depends only on SpoolVolume + KeyProvider (frozen)
        ┌─────────────────┴──────────────────┐
   AzureFilesSpoolVolume (new)          AzureKeyVaultKeyProvider (new)
        │                                     │
   ┌────┴─────────────┐                  Key Vault phi-engine-kek
   │                  │                  wrap {ver‖bindingDigest‖DEK}
Control plane      Data plane
= Azure Postgres  = Azure Files phi-spool
(txn: claims,      (immutable ciphertext
 pointer, ordinal,  blobs ONLY;
 nonce, prepared)   temp→finalize; quarantine-delete)
```

**Why Postgres:** the frozen port's guarantees (atomic claim+pointer, ordinal "advance-only-if-higher",
durable nonce no-reuse, reads-follow-durable-pointer-only) are exactly single-row/single-tx transactional
operations. Postgres gives them natively (unique constraints = first-writer-wins; `RETURNING` atomic
increment; conditional UPDATE = CAS). Fighting this on a file share is what produced every v1 CRITICAL.

**Provisioning (at SPEC-OK, not before):** reuse an existing Azure Database for PostgreSQL in
sub 18f7d3e6/GBS-Platform if one exists (recon first — memory notes Azure PG in the estate); else a small
Flexible Server. A dedicated **`phi_reversal`** database/schema, tenant-scoped rows, accessed by
`id-phi-engine` (AAD auth) or a KV-stored connection secret. This store holds NO canonical PHI — only
tenant/matter-scoped metadata + ciphertext-blob references (its own retention lands under GLY-345).

## 2. Control-plane schema (all rows tenant-scoped; tenant_id in every PK/index)

```sql
-- first-writer-wins DEK generation (ensureDekGeneration)
reversal_dek_generation(tenant_id, matter_id, purpose, dek_generation_id, wrapped_dek BYTEA, created_at)
  PRIMARY KEY (tenant_id, matter_id, purpose)          -- INSERT .. ON CONFLICT DO NOTHING; racer SELECTs winner

-- durable, atomic nonce counter (reserveNonce) — real atomic increment, NEVER reused (F4)
reversal_nonce_counter(tenant_id, dek_generation_id, next_counter BIGINT NOT NULL DEFAULT 0)
  PRIMARY KEY (tenant_id, dek_generation_id)
  -- reserve: INSERT .. ON CONFLICT .. DO UPDATE SET next_counter = reversal_nonce_counter.next_counter + 1
  --          RETURNING next_counter - 1;  (single-statement atomic; gaps impossible, reuse impossible)

-- prepared-blob intent (prepare) — lets reclamation decide orphan-ness transactionally (F5)
reversal_prepared(tenant_id, prepared_blob_id UUID, created_at, state TEXT CHECK (state IN
  ('prepared','committed','reclaim_marked')))
  PRIMARY KEY (tenant_id, prepared_blob_id)

-- idempotency claim + state machine (publish/flush) — atomic first-writer-wins (F1/F2/F3)
reversal_claim(tenant_id, idempotency_key, mapping_key, scope_digest, commit_handle,
  prepared_blob_id UUID, ordinal BIGINT NOT NULL, state TEXT CHECK (state IN ('pending','flushed')),
  created_at, expires_at BIGINT)
  PRIMARY KEY (tenant_id, idempotency_key)             -- INSERT .. ON CONFLICT DO NOTHING = first-writer-wins

-- DURABLE current pointer — the ONLY thing readCurrent follows (F1)
reversal_current(tenant_id, mapping_key, commit_handle, prepared_blob_id UUID, ordinal BIGINT, flushed_at)
  PRIMARY KEY (tenant_id, mapping_key)

-- per-mapping ordinal source (monotonic, gap-ok)
reversal_ordinal_seq(tenant_id, mapping_key, next_ordinal BIGINT NOT NULL DEFAULT 1)
  PRIMARY KEY (tenant_id, mapping_key)                  -- atomic RETURNING, same pattern as nonce
```

## 3. Protocol (maps each frozen SpoolVolume method to a transactional op)

- **ensureDekGeneration** — `INSERT reversal_dek_generation .. ON CONFLICT DO NOTHING; SELECT` → the durable
  winner's `{dek_generation_id, wrapped_dek}`. Remounted replica recovers the same generation.
- **reserveNonce** — single-statement atomic increment `RETURNING`. 96-bit BE encode of the counter (matches
  dev `nonce96`). Durable before return; gaps impossible, **reuse impossible** (F4).
- **prepare** — mint `prepared_blob_id = uuid`; write the ciphertext to Files `staging/<id>`, **flush**, then
  **atomic rename to `blobs/<id>`** (immutable, never overwritten → temp-then-finalize, F7); `INSERT
  reversal_prepared(state='prepared')`. A crash before finalize leaves a `staging/<id>` orphan (reclaimed);
  the blob is durable & complete before any claim references it (N4).
- **publish** — ONE transaction: allocate ordinal from `reversal_ordinal_seq` (RETURNING); `INSERT
  reversal_claim(state='pending', ordinal, ...) ON CONFLICT (tenant, idempotency_key) DO NOTHING`. If
  inserted → `kind:"published"`. If conflict → `SELECT` the existing claim, return `kind:"existing"` with
  `expired = now >= expires_at` (F1/F3 — claim+ordinal atomic; no filesystem race). `UPDATE reversal_prepared
  SET state='committed' WHERE prepared_blob_id = ...`.
- **flush** — ONE transaction: require the claim exists & is not lost (fail closed on unknown — dev parity);
  `UPDATE reversal_claim SET state='flushed'`; `INSERT reversal_current .. ON CONFLICT (tenant, mapping_key)
  DO UPDATE SET commit_handle=excluded.commit_handle, ordinal=excluded.ordinal, prepared_blob_id=
  excluded.prepared_blob_id WHERE excluded.ordinal > reversal_current.ordinal` (**CAS: advance only if higher
  ordinal** — an out-of-order/replay flush makes bytes durable but never rolls the pointer back, F1/F3).
- **readCurrent** — `SELECT reversal_current WHERE (tenant, mapping_key) IN (...)` exact-key bounded; then GET
  the Files blob by `prepared_blob_id`. Reads follow ONLY `reversal_current` (never `pending` — F1). Empty/all
  selector rejected; never scans.

**Claim-state recovery (F2):** a `pending` claim whose flush never completed is recoverable — a retry with
the same attempt re-runs flush (idempotent). Expiry creates a non-retryable tombstone ONLY for a claim that
reached `flushed`; a still-`pending` expired claim is treated as recoverable/abortable (a maintenance
transition may reset it), never a permanent block that pins bytes. Distinct claim states remove the v1
"expired pending claim blocks forever" defect.

## 4. KeyProvider (Lane C, F8)

`AzureKeyVaultKeyProvider` implements the frozen `KeyProvider` via `@azure/keyvault-keys` CryptographyClient
against `phi-engine-kek` (RSA-OAEP-256 wrapKey/unwrapKey), auth = `id-phi-engine` ManagedIdentityCredential.
**RSA-OAEP has no AAD**, so bind by ENCODING: `wrap` computes `plaintext = ver(1) ‖ bindingDigest(32) ‖ DEK(32)`
and wraps the whole 65 bytes. `unwrap` unwraps, parses, **constant-time compares** the embedded digest to the
presented `bindingDigest` and validates keyId/keyVersion/scope, and **fails closed BEFORE returning the DEK**
on any mismatch — restoring the cross-tenant/matter relocation backstop the dev provider gives via AAD.

## 5. Reclamation (Lane A, separate `SpoolMaintenance` interface — F5/F6/F10)

```ts
export interface ReclaimOrphanedPreparedInput { readonly olderThanEpochMs: number; readonly limit?: number; }
export interface ReclaimOutcome { readonly scanned: number; readonly reclaimed: number; readonly skippedReferenced: number; }
export interface SpoolMaintenance { reclaimOrphanedPrepared(input: ReclaimOrphanedPreparedInput): Promise<ReclaimOutcome>; }
```
`reclaimOrphanedPrepared` — **input scrub (F6):** snapshot `{olderThanEpochMs, limit}` once; require finite
safe-integer `olderThanEpochMs`, and `limit` a positive bounded safe-integer (default cap); reject NaN/±Inf/
negative (hostile-getter defense per the ratified passed-surface threat model). **Orphan determination is
TRANSACTIONAL (F5):** in one tx, SELECT `reversal_prepared` rows with `created_at < olderThanEpochMs` AND
`state != 'committed'` AND `prepared_blob_id` NOT referenced by any `reversal_claim`/`reversal_current`, and
UPDATE them to `state='reclaim_marked'` (claiming them). `publish`/`prepare` refuse to reference a
`reclaim_marked` blob (they mint fresh ids anyway), closing the check-then-delete race. **Reversible delete
(F10):** for each marked blob, `blobs/<id>` → **rename to `reclaim-quarantine/<id>`** (recoverable), then a
SEPARATE later pass hard-deletes quarantine entries older than a grace window. Committed records
(`reversal_current`-referenced) are NEVER touched. Dev in-memory impl mirrors this (models `reversal_prepared`
+ the transactional predicate) — closing the original GLY-344 `#preparedBlobs` leak in the reference store.

### Lane-A oracles (mutation-proven RED)
MUT-RECLAIM-COMMITTED, MUT-RECLAIM-PENDING-CLAIM, MUT-RECLAIM-HORIZON, MUT-RECLAIM-NOOP (anti-tautology:
a real orphan IS quarantined), MUT-RECLAIM-RACE (a blob marked-then-referenced, or referenced-then-marked,
never double-resolves), MUT-RECLAIM-ARG-GETTER (Infinity-on-2nd-read horizon getter can't widen the sweep),
MUT-QUARANTINE-NOT-HARDDELETE (delete goes to quarantine, recoverable within grace).

## 6. Lane D — Q6 durability smoke (in ACA, the real proof — F11)

Transport is **HTTPS SDK uniformly** (no SMB), so the smoke runs the REAL adapter code. In an ACA workload
with the real Postgres + phi-spool: (1) N concurrent replicas race one idempotency key → exactly one claim,
one pointer, no partial; (2) publish+flush, kill container, fresh replica resolves every acked record; (3)
scale-in mid-write leaves no readable partial and no pinned tombstone; orphans reclaimed past horizon; (4)
nonce strictly increases with no repeat across crash+remount (DB counter). Exit criterion for the adapter.

## 7. Lane E — reclamation cron ACA Job

Node entrypoint constructs the Azure `SpoolMaintenance` (Postgres + phi-spool via KV secret / MI), runs
`reclaimOrphanedPrepared({olderThanEpochMs: now - HORIZON})` + the quarantine hard-delete pass, logs
`{scanned, reclaimed, skippedReferenced}`. Image → `acrgbsadjudicawus` via `az acr build`; `az containerapp
job create --environment cae-gbs-wp --trigger-type Schedule --mi-user-assigned id-phi-engine`. **HORIZON
default 24h**, but now a SAFETY MARGIN over a transactionally-correct predicate, not the correctness
mechanism. **Ships dry-run (log-only) first**, then quarantine-enforcing, then enables the hard-delete pass.

## 8. Lane plan for the sol implementation fan-out (author = GPT-5.6-sol; review = Opus-5)
| Lane | Deliverable | Depends |
|---|---|---|
| A | `SpoolMaintenance` iface + dev in-memory reclamation + oracles | — (unblocked; = GLY-344) |
| C | `AzureKeyVaultKeyProvider` (wrap-encoding + verify) + oracles | — |
| B1 | Postgres control-plane schema + migrations + a `ControlPlane` port impl | — |
| B2 | `AzureFilesSpoolVolume` (blob temp→finalize + readCurrent) over B1+data plane | B1 |
| B3 | Azure `SpoolMaintenance` impl (txn orphan predicate + quarantine delete) | A, B1, B2 |
| D | in-ACA Q6 smoke harness | B1,B2,C |
| E | reclamation cron job + provisioning | B3 |
Each lane: sol authors code+oracles → executes gates (tsc, tests, named mutations) shipping RAW output →
Opus-5 adversarial review → fix loop → orchestrator integrates. Cross-family gate preserved (GPT author,
Claude review). Mutation evidence mandatory on every security/durability guard.

## 9. Finding-by-finding resolution (traceability to the v1 BLOCK)
| v1 finding | v2 resolution |
|---|---|
| F1 reads see unflushed / rollback | reads follow `reversal_current` only; flush CAS-advances by ordinal; bytes immutable-per-commit in Files |
| F2 expired pending claim blocks + pins | claim state machine (pending/flushed); expiry tombstones only `flushed`; pending is recoverable/abortable |
| F3 no atomic ordinal CAS / self-contradiction | ordinal from a txn sequence allocated AT the atomic claim; flush UPDATE .. WHERE excluded.ordinal > current |
| F4 block-nonce reuse | single-statement atomic `RETURNING` counter — no blocks, no 409-loser ambiguity, no reuse |
| F5 reclamation check-then-delete race | transactional orphan-mark (`reclaim_marked`) + publish/prepare refuse marked blobs |
| F6 reclaim args unscrubbed / over-authority | snapshot-once + finite-safe-int validation; separate least-authority `SpoolMaintenance` iface |
| F7 create+upload separate → empty winner | temp-then-finalize (staging→atomic rename); control plane is existence-of-truth, blob only referenced once finalized |
| F8 RSA-OAEP no AAD → relocation | wrap `{ver‖bindingDigest‖DEK}`, constant-time verify + key/scope check on unwrap, fail-closed |
| F9 fallback not a drop-in | control plane IS the primary now (Postgres), fully specified — not a vague fallback |
| F10 share soft-delete ≠ file recovery | quarantine-rename + delayed hard-delete = real reversibility on Files |
| F11 adapter HTTPS vs smoke SMB | HTTPS SDK uniformly; smoke runs the real adapter |
```
