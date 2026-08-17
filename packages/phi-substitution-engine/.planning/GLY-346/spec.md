# GLY-346 spec — Azure Files `SpoolVolume` adapter + Key Vault `KeyProvider` + reclamation cron job

**Author:** Claude (orchestrator/architect). **Cross-family spec-check:** GPT-5.6-sol (pending).
**Tier:** T2 (crown-jewel-adjacent durability layer; touches PHI-at-rest crypto seam).
**Base:** `a445a50` (origin/main, L2.4 merged). **Ticket:** GLY-346 (parent GLY-335; implements GLY-344 reclamation as Lane A).

## 0. Scope & non-goals

Implements the **unblocked** subset of L4 against the FROZEN `SpoolVolume`/`KeyProvider` ports
(`src/tokens/durable/ports.ts`) — **no `core/` change, no port method removed or re-typed**. The only
port change is **additive**: one new `SpoolVolume` method (§2). The protected-service prod deploy
(plan `L4.D`, gated on B2∧B3 + JTT G3) is **explicitly out of scope**; nothing here puts the engine on
the request path in `cae-gbs-wp`. The reclamation cron Job (§6) is a standalone maintenance workload.

**G4 estate this builds on (already provisioned):** `id-phi-engine` (user-assigned MI, clientId
`1762d6c8-f245-4876-b571-7b15f4138a77`); `phi-engine-kek` (RSA-3072 KEK in `kv-gbs-platform`, ops
`wrapKey`/`unwrapKey`, MI scoped Crypto User); `stgbsphispool` FileStorage/Premium_LRS + `phi-spool`
SMB share (100 GiB, **share soft-delete = 7 days**); `phi-spool-account-key` secret; ACR
`acrgbsadjudicawus.azurecr.io`.

Non-goals: DEK rotation (Q4 — v1 single generation stands), KEK/DEK cache TTL (GLY-343), matter-retention
deletion lifecycle (Q8/GLY-345), store-enforced operation-retention binding (GLY-345). These stay
ticketed, not decided in code here.

## 1. Substrate spike — established facts (against real `phi-spool`)

| Primitive | Result | Consequence |
|---|---|---|
| `prepared/` + `committed/` dirs | ✅ create works | layout viable |
| list w/ per-file `lastModified` | ✅ server timestamps returned | **reclamation enumeration** works |
| file delete | ✅ works | **reclamation delete** works |
| atomic rename/move via `az` CLI | ❌ absent | publish primitive is SDK/SMB-only (`@azure/storage-file-share` `ShareFileClient.rename` / SMB `fs.rename`) |
| share soft-delete | ⚠️ **ON, 7 days** | a reclaimed prepared blob's ciphertext lingers ≤7 d in soft-delete before hard-delete — a real PHI-retention-tail fact (surfaced to counsel via the retention audit) |

**Q6 remains the load-bearing unknown:** the addendum §6/Q6 requires *proof* that the mount supports
cross-replica atomic publication, durable nonce reservation, and flush — "container-local `fsync` is not
evidence." The `az` CLI cannot exercise SMB rename/flush semantics; **the proof is an in-ACA SMB smoke
(§5)**, not this VM.

## 2. Lane A — `reclaimOrphanedPrepared` (closes GLY-344 in the dev model)

**Additive** `SpoolVolume` method + dev in-memory impl. This is the only port surface change.

```ts
export interface ReclaimOrphanedPreparedInput {
  /** Reclaim only prepared artifacts first-persisted STRICTLY BEFORE this instant (the tombstone horizon). */
  readonly olderThanEpochMs: number;
  /** Optional per-sweep bound; when omitted, sweep all eligible. A partial sweep is correct, just incomplete. */
  readonly limit?: number;
}
export interface ReclaimOutcome {
  readonly scanned: number;    // prepared artifacts examined. Rev 2026-08-17 (GLY-350): `limit` bounds reclaimable SELECTION per path; Path-1 additionally reports up to `limit` referenced candidates in the metric, so scanned may reach 2×limit while mutation work stays bounded by `limit`.
  readonly reclaimed: number;  // orphaned artifacts deleted
  readonly skippedReferenced: number; // examined but retained because still referenced (observability)
}
// on SpoolVolume:
reclaimOrphanedPrepared(input: ReclaimOrphanedPreparedInput): Promise<ReclaimOutcome>;
```

**An artifact is ORPHANED (deletable) iff ALL hold** (fail-safe: any doubt ⇒ retain):
1. its prepared-time `< olderThanEpochMs` (the horizon protects in-flight prepare→publish→flush windows);
2. it is **not** the `preparedHandle` of any **durable current mapping** (would be a committed record — reads follow it);
3. it is **not** the `preparedHandle` referenced by any **idempotency claim** whose commit is still reachable (a published/flushed commit's bytes), **regardless of claim expiry** — an expired *detector* claim keeps its non-retryable tombstone, and its bytes may be purged by the separate matter-retention lifecycle (Q8/GLY-345), NOT by orphan reclamation.

Reclamation **never** touches `committed/` (Azure) / `#committedRecords` (dev), **never** deletes a
referenced prepared artifact, and **never** deletes an artifact newer than the horizon. It removes ONLY
prepared artifacts left by a crash-between-prepare-and-publish or a divergent-scope replay — the exact
`#preparedBlobs` leak in the ticket.

**Dev-impl mechanics:** the backend records prepared-time per handle (thread `nowEpochMilliseconds` from
the volume through `prepare` → `putPreparedBlob`). The sweep walks `#preparedBlobs`, applies the 3-part
predicate against `#durableMappings` + `#claims` + `#commitIndex`, deletes the orphans. `crash()` still
discards unflushed claims/mappings; a prepared blob whose claim was lost to `crash()` becomes an orphan
and is reclaimed on the next sweep past the horizon — precisely the intended GC.

### Lane-A oracles (each mutation-proven RED)
- `MUT-RECLAIM-COMMITTED` — reclamation deletes a committed record's prepared bytes ⇒ a prior `readCurrent` hit now misses. Guard: exclude durable-mapping-referenced handles.
- `MUT-RECLAIM-LIVE-CLAIM` — reclamation deletes a prepared artifact backing a reachable claim commit ⇒ a later flush/read breaks. Guard: exclude claim/commit-referenced handles (expiry-independent).
- `MUT-RECLAIM-HORIZON` — reclamation deletes an artifact newer than `olderThanEpochMs` ⇒ an in-flight publish loses its bytes. Guard: strict `<` horizon check.
- `MUT-RECLAIM-NOOP` — the sweep never deletes (returns `reclaimed:0` always) ⇒ the leak persists. Guard: an actual orphan (unreferenced, past horizon) IS deleted and `readCurrent` for it stays absent while a sibling committed record survives. (This is the "guard actually does something" anti-tautology oracle.)

## 3. Lane B — `AzureFilesSpoolVolume`

Implements the frozen `SpoolVolume` on `phi-spool` via `@azure/storage-file-share` (data-plane over
HTTPS 443 for the reclamation job; the request-path store, when it later deploys, uses the SMB mount).
No Azure type escapes this adapter (CONTRACT §3.3).

**On-share layout (all tenant-scoped in the path):**
```
dek/<scopeDigest>                       # durable DEK generation artifact {dekGenerationId, wrappedDek}
nonce/<dekGenerationId>/<blockId>       # claimed nonce blocks (block allocation)
prepared/<preparedHandle>               # prepared encrypted record — INVISIBLE to readCurrent
committed/<mappingKey>                  # current record (bytes + publication metadata) — the read target
claims/<idempotencyKey>                 # idempotency tombstone {commit, mappingKey, scopeDigest, preparedHandle, ordinal, expiresAt}
```

**`ensureDekGeneration`** — first-writer-wins: `create` `dek/<scopeDigest>` with **no-overwrite**
(Azure Files rejects create-over-existing ⇒ 409). Winner writes the minted `{dekGenerationId, wrappedDek}`;
a racer that gets 409 reads the existing artifact. Remounted replica recovers the same generation.

**`reserveNonce` — BLOCK ALLOCATION (durable, gaps-ok, reuse-forbidden):** a replica atomically claims a
disjoint block by no-overwrite `create` of `nonce/<dekGenerationId>/<blockId>` (block index from a durable
high-water file advanced by the same first-writer-wins create), then hands out the `2^k` nonces of that
block from replica-local memory. A crash abandons the block's unused tail (gap — permitted); a block is
NEVER reclaimed or re-handed (no reuse). This trades one durable op per block (not per nonce) for the
port's "gaps allowed, reuse forbidden" contract — no atomic-increment primitive needed on Files.

**`prepare`** — write the encrypted blob to `prepared/<preparedHandle>` and **fsync/flush to the service**
before returning (data durable before it can be published). Invisible to `readCurrent` (only `committed/`).

**`publish` — atomic first-writer-wins via the CLAIM object (the atomicity anchor, NOT rename):**
1. no-overwrite `create` `claims/<idempotencyKey>` carrying `{commit, mappingKey, scopeDigest, preparedHandle, ordinal, expiresAt, createdAt}`. **This create is the atomic serialization point** — Azure Files create-if-not-exists is a single server-side op; exactly one caller wins the idempotency race. 409 ⇒ read the existing claim, return `kind:"existing"` (+ `expired` from its `expiresAt` vs now).
2. winner assigns the publication `ordinal` from a durable per-mapping high-water (advanced monotonically; a `bigint`-decimal string so it never saturates — mirrors §9/§10 + `MUT-ORDINAL-NUMBER-OVERFLOW`), then **atomic rename** `prepared/<preparedHandle>` → `committed/<mappingKey>` with replace-if-exists, guarded so the pointer advances ONLY to a higher ordinal (a late/replayed lower-ordinal publish makes bytes durable but does NOT roll the current pointer back — `MUT-DURABLE-ROLLBACK`).
   **Crash between (1) and (2):** the claim exists, the committed pointer may be missing. Recovery: `flush`/read completes the pending rename from the claim's `preparedHandle` (idempotent — replace-if-exists tolerates a redo). A prepared artifact of a *lost* (crash-discarded before durable) claim becomes an orphan for Lane-A reclamation.

**`flush`** — durable barrier over BOTH the committed record bytes AND the publication metadata: ensure
the `committed/<mappingKey>` rename is materialized and its parent-directory metadata flushed to the
service (not merely a client-side buffer flush). Fail-closed if the commit is unknown/lost
(`MUT-FLUSH-LOST-COMMIT` parity).

**`readCurrent`** — exact-key bounded `GET committed/<mappingKey>` per request; empty/all selector rejected;
never lists/iterates. A published-but-unrenamed (crash-window) mapping reads as absent until recovery.

### Lane-B oracles (in-ACA smoke, §5, + adapter unit tests with a Files test double)
Parity with the dev store's proven invariants, re-anchored on Azure semantics:
`MUT-NONATOMIC-PUBLISH` (two racers both win a first claim), `MUT-CONTAINER-SCRATCH` (prepared on local
disk, lost on remount), `MUT-FLUSH-FILE-ONLY` (bytes flushed, pointer metadata not), `MUT-DURABLE-ROLLBACK`,
`MUT-FLUSH-LOST-COMMIT`, `MUT-NONCE-REUSE` (a reclaimed/re-handed block repeats a nonce), plus the Lane-A
reclamation set on the real share.

## 4. Lane C — `AzureKeyVaultKeyProvider`

Implements the frozen `KeyProvider` via `@azure/keyvault-keys` `CryptographyClient` against
`phi-engine-kek`, authenticated by `id-phi-engine` (`ManagedIdentityCredential` with the MI clientId;
`DefaultAzureCredential` locally for the smoke). `wrap`/`unwrap` use RSA-OAEP-256 `wrapKey`/`unwrapKey`
(the only ops granted). The KEK never enters app memory (Key Vault performs the wrap/unwrap). The
`bindingDigest` is enforced as the wrap-AAD substitute exactly as the dev provider does (bind
tenant+matter+purpose+keyId+keyVersion; unwrap fails closed on digest mismatch — the cross-tenant/matter
relocation backstop). No KEK/DEK caching in v1 (cache TTL is GLY-343).

### Lane-C oracles
`MUT-KEK-BINDING-BYPASS` (unwrap ignores bindingDigest ⇒ cross-scope unwrap succeeds), `MUT-WRAP-ALG-DOWNGRADE`,
smoke: a real wrap→unwrap round-trips against `phi-engine-kek`; a digest-mismatched unwrap fails closed.

## 5. Lane D — Q6 durability smoke (in ACA, the actual proof)

A short-lived ACA workload (reuse the reclamation job image, `--command` override) mounted on `phi-spool`
via **SMB** that exercises, against the real service:
1. **Atomic publish** — N concurrent replicas race one `idempotencyKey`; exactly one `committed/` record, exactly one claim, no partial mapping.
2. **Durable flush** — publish+flush, then the container is killed and a fresh replica resolves every acknowledged record (the "ack survives new replica on mounted volume" / `MUT-CONTAINER-SCRATCH` proof).
3. **Replica-loss** — scale-in during in-flight writes leaves no readable partial mapping and no dangling blocking tombstone; orphaned prepared artifacts are then reclaimed by a Lane-A sweep past the horizon.
4. **Nonce non-reuse** across a crash+remount (blocks abandoned, never repeated).

**Exit criterion for Lane B:** all four pass on real `phi-spool`. **If atomic-publish or durable-flush
CANNOT be proven** (SMB rename non-atomic / cache-deferred), fall back to the **control-plane-pointer**
variant (idempotency claim + current-record pointer + ordinal in a transactional store — Azure Table
Storage or the app Postgres — with Files holding only immutable `prepared/` blobs; reclamation unchanged).
This fallback is pre-designed so a failed proof is a switch, not a redesign.

## 6. Lane E — reclamation cron ACA Job

- **Image:** a minimal Node entrypoint (`bin/reclaim-spool.ts`) that constructs `AzureFilesSpoolVolume`
  (account `stgbsphispool`, share `phi-spool`, key from `phi-spool-account-key` via KV ref) and calls
  `reclaimOrphanedPrepared({ olderThanEpochMs: now - HORIZON })`, logs `{scanned, reclaimed, skippedReferenced}`
  as one structured line, exits 0 (non-zero on unexpected error — the job's failure signal).
- **Build/push:** `az acr build` → `acrgbsadjudicawus.azurecr.io/phi-spool-reclaim:<gitsha>` (no local Docker needed).
- **Provision:** `az containerapp job create --environment cae-gbs-wp --trigger-type Schedule
  --cron-expression "<daily>" --mi-user-assigned id-phi-engine --replica-timeout ... ` with a `phi-spool`
  SMB mount (env storage) and the KV secret ref for the account key. Precedent: `migrate-*` / `ops-query-*`
  jobs already run in this env.
- **HORIZON:** default **24 h** (≫ any plausible prepare→publish→flush window; also ≥ the detector 24 h TTL
  so a sweep never races a just-expired detector's bytes). Governance may tune it (GLY-344 disposition).
- **Reversibility:** the job only deletes prepared *orphans*; with share soft-delete = 7 d, an erroneous
  delete is recoverable for 7 days. First production run ships with `--dry-run` (log-only) until one clean
  cycle is observed, then flips to enforcing.

## 7. Acceptance & pipeline

- `tsc` clean; all 308 existing tests preserved (no frozen test weakened); Lane-A oracles unit-green +
  mutation-proven; Lane-B/C/D proven by the in-ACA smoke; Lane-E job runs dry then enforcing.
- **T2 pipeline:** this spec → GPT-5.6-sol cross-family spec-check → iterate to SPEC-OK → author/oracle-split
  impl (Claude author code / oracles cross-checked) → GPT gate → review loop → ONE push → PR → cross-family
  review → green CI → merge. Mutation evidence shipped raw. Infra provisioning (ACR image, ACA Job) is the
  tail, after the code merges.
- **Invariants:** no direct push to protected branches (PR only); no secret printed (account key/KEK never
  logged); az from `/tmp/azwork`, `--subscription 18f7d3e6…` pinned; the bounded threat model (no
  realm/intrinsic poisoning premise) governs which findings BLOCK.

## 8. Open decisions for the spec-check to stress
1. Is the **claim-object create** a sound atomicity anchor for "claim+mapping advance atomically", given the mapping (rename) is a *second* op? (crash-window recovery correctness — §3 publish step 2.)
2. Is **block-allocated nonce** reuse-safe under concurrent replicas racing the block high-water via no-overwrite create? Any interleaving that hands the same block twice?
3. Does the **3-part orphan predicate** (§2) have a gap where a still-needed prepared artifact is reclaimed — e.g., a published-but-not-yet-flushed commit whose claim survived but whose rename hasn't happened, sitting past the horizon?
4. Is **24 h horizon** safe against the longest legitimate prepare→publish→flush + recovery latency?
