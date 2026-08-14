# GLY-346 evidence ledger — Azure Files SpoolVolume adapter + KeyProvider + reclamation cron job

Parent GLY-335; implements GLY-344 reclamation (Lane A). Base a445a50 (origin/main). Worktree
`~/projects/_gbx-worktrees/GLY-346-azure-spool`, branch `GLY-346-azure-files-spool`. Tier T2.

## Stage 0 — G4 estate provisioned (2026-08-12, prerequisite)
- `id-phi-engine` MI (principalId 520ecc84-…, clientId 1762d6c8-…); `phi-engine-kek` RSA-3072 in
  kv-gbs-platform (wrap/unwrap, MI Crypto User key-scoped); `stgbsphispool` FileStorage/Premium_LRS +
  `phi-spool` SMB share (100 GiB, share soft-delete 7d); `phi-spool-account-key` secret; ACR
  `acrgbsadjudicawus.azurecr.io`; ACA env `cae-gbs-wp` (SMB Azure Files mounts already in use).

## Stage 1 — substrate spike (real phi-spool, data-plane via az CLI)
PROVEN: prepared/ + committed/ dir create ✅; `az storage file list` returns per-file `lastModified`
(reclamation enumeration) ✅; `az storage file delete` (reclamation delete) ✅.
NEGATIVE/RISK: `az` CLI has NO atomic rename/move (publish primitive is SDK/SMB-only) ❌; share
soft-delete = 7 days ON (reclaimed ciphertext lingers ≤7d — PHI-retention-tail, flagged to counsel).
Q6 (atomic publish + durable flush + durable nonce) NOT provable from this VM → in-ACA SMB smoke (Lane D).

## Stage 2 — spec authored
`.planning/GLY-346/spec.md` (Claude author). Design: additive `reclaimOrphanedPrepared` port method +
3-part orphan predicate (past-horizon ∧ not durable-mapping-ref ∧ not claim/commit-ref, fail-safe);
Azure adapter = claim-object-create atomicity anchor + ordinal-guarded rename publish, block-allocated
durable nonce, fsync-before-publish; Key Vault KeyProvider (RSA-OAEP-256 wrap/unwrap via MI, bindingDigest
backstop); in-ACA Q6 smoke; control-plane-pointer FALLBACK pre-designed; reclamation cron ACA Job
(dry-run-first, 24h horizon). 4 Lane-A oracles + Lane-B/C mutation set named.

## Stage 3 — GPT-5.6-sol cross-family spec-check → **BLOCK** (5 CRIT + 6 HIGH)
FALSE STARTS: `codex exec` CLI run 1 hijacked by codex's own PAI Algorithm hooks (952 lines of ceremony,
no verdict); clean-CODEX_HOME run 2 produced empty output. **Working path = `mcp__codex__codex` with a
minimal `base-instructions` override (kills the ceremony) + neutral cwd** — produced a real, high-quality
verdict. LESSON: for a codex cross-family gate, use the MCP tool with base-instructions override, not the
`codex exec` CLI (the CLI inherits ~/.codex PAI hooks that force Algorithm ceremony non-deterministically).

**ROOT CAUSE of the BLOCK (mine to own): Azure Files is NOT a transactional substrate.** The spec tried to
reproduce the dev store's SYNCHRONOUS atomic-publish (claim+pointer advance with no await between) on a plain
file share using create-if-not-exists + rename. 5 CRITICALs all root here:
- **F1** single mutable `committed/<mappingKey>` makes a published-but-UNFLUSHED write readable (rename = visibility) → crash rolls it back / a peer overwrite acks a vanished write. Reads must follow ONLY a durable ordinal-advanced pointer; bytes must be immutable-per-commit, separate from the pointer.
- **F2** a durable claim file ≠ dev crash() model: an expired PENDING claim permanently blocks retry (record() rejects EXPIRED before flush) AND pins its prepared bytes forever. Need claim states pending/flushed + recovery.
- **F3** ordinal allocation + "advance only if higher" has no atomic CAS on Files; spec also self-contradicts (claim carries ordinal / ordinal assigned after claim).
- **F4** block-nonce high-water is not an atomic increment; 409-loser behavior undefined → same block handed twice → **GCM nonce reuse (catastrophic)**. Marker-create success must be the SOLE ownership proof; 409→retry next block.
- **F5** reclamation is check-then-delete; a paused publisher past horizon gets its prepared artifact deleted then its claim blocks. Horizon ≠ correctness; need lease/atomic mark-then-exclude.
HIGH: **F7** Azure Files create + content-upload are SEPARATE ops → empty "winner" artifact (permanent block); need temp-then-finalize. **F8** RSA-OAEP-256 has NO AAD → wrapping bare DEK defeats the bindingDigest relocation backstop; must wrap `{ver||bindingDigest||DEK}` + constant-time verify on unwrap. **F9** control-plane fallback not actually a drop-in. **F10** **share soft-delete does NOT recover a file deleted in a LIVE share** — the reclamation job is NOT reversible as specified (need quarantine-rename + delayed hard-delete). **F6** reclaim args need hostile-getter/finite-int scrub (passed-surface threat model). **F11** adapter=HTTPS-SDK but smoke=SMB — must test the real request-path transport.

**IMPLICATION:** the correct architecture is an INVERSION — a transactional CONTROL PLANE (Postgres/Table)
holds idempotency claim + claim-state + current pointer + ordinal (CAS) + nonce counter (atomic increment);
Azure Files holds ONLY immutable per-commit ciphertext blobs (temp-then-finalize, quarantine-delete). This
resolves F1/F2/F3/F4/F5/F9 at the root. It adds a transactional-store DEPENDENCY (cost + a new tenant-scoped
metadata store) and is genuinely M4-milestone-depth — surfaced to Alex for the scope/architecture call.
Spec is NOT SPEC-OK; NO implementation started. Full verdict: MCP task k6qbb60l0 result in transcript.

**CORRECTION owed to Alex:** my earlier "reclaimed ciphertext lingers 7d in share soft-delete" (spec §1,
retention surface) is WRONG per F10 — Azure Files share soft-delete recovers a deleted SHARE, not files
deleted inside a live share. No 7-day file-level recovery exists; deletion is effectively permanent.

## Stage 4 — spec v2 (control-plane-primary) → sol re-check **BLOCK** (9 findings), then spec v3
Alex directive (2026-08-12): BUILD IT NOW — many GPT-5.6-sol implementer agents + an Opus-5 reviewer.
Held: team implements against a SPEC-OK spec, not a BLOCKed one. **spec-v2.md** INVERTED to control-plane-
primary (Postgres txn control plane: claims/pointer/ordinal/nonce/prepared; Files = immutable blobs only;
reclamation a separate least-authority SpoolMaintenance iface). sol re-check RESOLVED F3/F6-port/F8/F9/F10/F11
and **validated the architecture** ("can preserve N4 w/o distributed txn, once row-precedes-Files +
serialize-on-row + fail-closed-divergence"), but BLOCKED on 9 refinements: B1 prepared-row-after-blob →
invisible orphan; B2 publish non-conditional prepared transition races maintenance / pins loser blob; B3
expired-PENDING claim hits frozen core throw-before-flush (:168) → pins forever; B4 flush doesn't verify blob
+ readCurrent missing-blob undefined (N4); B5 frozen port carries no tenant (flush(commit)/readCurrent(key));
B6 **Postgres signed BIGINT can't hold matter expiry 2^64-1** → overflow every matter write; B7 nonce first-
insert returns -1; B8 dev crash()-deletes-pending ≠ Postgres durable-pending → vacuous oracles; B9 reclaim
predicate not an exclusive claim. Re-check ran via `mcp__codex__codex` (thread 019ff71c) — see
[[feedback_codex_gate_via_mcp_base_instructions]].
**spec-v3.md** authored resolving all 9, bound to the frozen core exactly (read durable-reversal-store.ts):
§A global-unique handles (mappingKey/idempotencyKey embed tenant via keys.ts; commit/prepared = UUID + tenant
cols) → B5; §B `expires_at_ms NUMERIC(20,0)` → B6; §C uploading-row-BEFORE-Files → B1; §D publish FOR UPDATE
+ winner-only commit transition → B2; §E expired-pending→`expired` tombstone + DETACH blob (keep expires_at +
key; core throws :168; recovery via :174 for non-expired) → B3; §E/§G flush verifies blob + readCurrent
fail-closed on pointer-without-blob → B4; §F nonce INSERT arm returns 0 → B7; §H FOR UPDATE SKIP LOCKED
finalized-only + idempotent recovery → B9; §I durable-pending dev double + ONE shared conformance suite → B8.
Delta re-check (resumed thread 019ff71c) running: task k47yqvh8y. Provision phi_reversal Postgres at SPEC-OK.

## Stage 5 — spec loop CONVERGED → **SPEC-OK** (round 5, thread 019ff71c)
Rounds: v1 BLOCK (Azure Files not transactional) → v2 BLOCK but ARCH VALIDATED, 6/11 resolved → v3 resolves
6/9 (B1,B2,B5,B6,B7,B8) → v4 resolves D1–D5 (state machine: orphaned state, claim-row-locked flush,
etag/len persist, dual-path exclusive reclaim, quarantined_at_ms) → v5 resolves N1 (upload_reclaim_marked
crash-recovery selector) → **SPEC-OK**: "v2 architecture with v3/v4/v5 state machine is sound to implement;
all B, D, and N findings resolved; every non-terminal state has an idempotent recovery selector; no frozen-
core contract violation." Authoritative spec = spec-v2.md (arch/topology/KeyProvider/smoke/cron/lanes/trace)
+ spec-v3/v4/v5.md (addressability, schema, state machine). ~20 real defects caught at spec time.
**NEXT: provision phi_reversal Postgres (deferred — dev double suffices for impl; live PG only for Q6 smoke
in ACA). Fan out the 7 lanes to GPT-5.6-sol implementers (Alex directive) + Opus-5 reviewer, cross-family
gate (GPT author / Claude review). Lane A (reclamation + dev double = GLY-344 core) is unblocked & self-
contained; C (KeyProvider), B1 (PG schema/migrations) also unblocked; B2←B1, B3←A+B1+B2, D←B1+B2+C, E←B3.**

## Stage 6 — Lane A IMPLEMENTED (sol) → **Opus-5 APPROVE** (commit 6450299)
GPT-5.6-sol authored 3 new files (maintenance.ts, dev/in-memory-control-plane.ts, tests/durable-control-
plane.test.ts); NO frozen file touched. Orchestrator re-ran gates clean: tsc clean, 324 tests (308+16).
Opus-5 (claude-opus-4-8) cross-family review: **APPROVE** — ran 6 mutations (A-F), verified all 9 invariants
at file:line, confirmed frozen integrity via git diff 8f339b1, re-ran gates. B8 durable-pending proven
non-vacuous by Mutation C. **Carry-forward (non-blocking):** (1) **B3 MUST preserve the single-global-`limit`
budget semantic** across reclamation passes (dev uses one `remaining` budget across all 5 passes, not
per-path LIMIT) OR the shared conformance suite must not assert per-path counts near the cap — else dev/
adapter diverge. (2) MUT-RECLAIM-COMMITTED is an end-state assertion, not a tight single-mutant oracle
(finalized/orphaned are structurally unreferenced; Mutations E/F survive) — add an explicit "finalized/
orphaned ⇒ unreferenced" invariant test when extending the conformance suite (guard-moves-when-code-moves).
(3) coverage gaps (flush-sees-expired-pending, intra-finishPathTwo crash gates, Path-1 mark-then-crash,
pending-absent-from-readCurrent) — correct code, add oracles as the suite grows. **Lane A DONE. NEXT WAVE:
C (AzureKeyVaultKeyProvider, deps staged) + B1 (PG schema/migrations) in parallel.**

## Stage 7 — Lane C IMPLEMENTED (sol) → **Opus-5 APPROVE** + MEDIUM fixed (commits e95acfb, 48645db)
GPT-5.6-sol authored 4 files (azure/kek-crypto-client.ts, azure/azure-keyvault-key-provider.ts,
azure/azure-kek-crypto-client.ts, tests/azure-keyvault-key-provider.test.ts). F8 fix: DEK wrapped as
{ver(0x01)‖bindingDigest(32)‖dek(32)}, unwrap constant-time-verifies the embedded digest (timingSafeEqual,
length-guarded) + scope/keyId, fails closed BEFORE returning the DEK — restores the cross-tenant/matter
relocation backstop. @azure imports isolated to azure-kek-crypto-client.ts (smoke-tested, not unit); logic
unit-tested via a FAKE opaque KekCryptoClient. Orchestrator re-verified: tsc clean, 331 tests, frozen
integrity empty-diff. **Opus-5 APPROVE** — 3 mutations proven RED (MUT-KEK-BINDING-BYPASS, handle-scope,
+ digest guard); confirmed the fake is a faithful opaque wrap (measures the provider, not itself). **One
MEDIUM: length/version-guard fixtures were non-isolating** (also failed the digest compare → deleting the
guard left all green). Orchestrator applied the reviewer's prescribed fix (embed the matching presented
digest 0x11×32 in each malformed fixture) — MUTATION-PROVEN: neutralizing azure-keyvault-key-provider.ts:71
→ both fixtures RED; restored → 331 green (48645db). **Lane C DONE.**
**NEXT: B1 (Postgres control-plane schema/migrations + ControlPlane port). B1's live validation (conformance
suite vs real PG) needs the phi_reversal Postgres → provisioning + the dedicated-vs-shared isolation decision
surfaced to Alex. Lanes remaining: B1, B2 (Files adapter ←B1), B3 (Azure SpoolMaintenance ←A+B1+B2), D (Q6
smoke ←B1+B2+C), E (cron ←B3).**

## Stage 8 — Control plane PROVISIONED + Lane B1 IMPLEMENTED (sol) → **Opus-5 APPROVE** (commit 5c8422c)
Alex chose DEDICATED Postgres. Provisioned `psql-phi-reversal` (B1ms Burstable, PG16.14, westus2,
GBS-Platform, Ready); db `phi_reversal`; firewall this-VM(20.245.127.237)+AzureServices; admin pw →
kv-gbs-platform secret `phi-reversal-pg-admin-password` (user phipgadmin). ~$12-15/mo. (2 az flag quirks:
`--database-name` is elastic-only on server create → create DB separately; firewall-rule uses `--server-name`
not `--name` → created DB + verified connectivity via node-pg from this VM instead.) B1: sol authored
migrations/0001 + azure/control-plane.ts (ControlPlane iface) + azure/postgres-control-plane.ts (pg impl) +
tests/postgres-control-plane.test.ts (env-guarded, skips w/o live DB). **Orchestrator ran LIVE conformance
from this VM: 8/8 PASS** (racing publish first-writer-wins, ordinal CAS no-rollback, expired-pending
tombstone+detach+orphan, SKIP LOCKED reclaim, Path-2 crash recovery, atomic nonce first=0 no-reuse, NUMERIC
2^64-1). tsc clean, 331 sandbox + 8 skipped. **Opus-5 APPROVE** — RE-RAN the live 8/8 itself, verified all 8
checks at file:line, tx hygiene (COMMIT/ROLLBACK/release all paths), NUL→base64url encode injective +
consistent on every write AND read (no raw-NUL path). Key design: Postgres TEXT rejects NUL, so
mappingKey/idempotencyKey (NUL-separated per keys.ts) are base64url-encoded at the TEXT boundary. Non-blocking:
unreachable defensive branch :345; no deadlock. **B1 DONE — transactional core proven on real Postgres.**
**NEXT: B2 (AzureFilesSpoolVolume — implements frozen SpoolVolume by composing B1 ControlPlane + a Files
blob store on phi-spool via @azure/storage-file-share; prepare=uploading-row→upload→rename→markFinalized,
flush=HEAD blob+etag/len verify→ControlPlane.flushClaim, readCurrent=pointers→GET blobs). Needs the storage
dep + live validation vs real PG + phi-spool from this VM (has both). Then B3 (reclamation Files ops; MUST
keep single-global-limit budget), D (Q6 in-ACA smoke), E (cron).**

## Parallel — data-retention legal audit (Sonnet agent, background)
Launched per Alex to review our data-retention policy vs law (HIPAA/CMIA/CCPA-CPRA/§632/State-Bar/WC).
Report → scratchpad/retention-audit.md. Relevant to this lane: the 7-day soft-delete tail + the
detector-24h/matter-until-deletion retention classes + indefinite tombstone horizon.

## Stage 9 — Lane B2 cross-family review (2026-08-13)
Reviewer change of record: Claude subagent quota exhausted (resets 2026-08-18); spawned reviewer =
**Gemini (agy, Antigravity)** — still cross-family vs the GPT-5.6-sol author. Optional terminal Opus
pass deferrable to post-08-18 before merge.
- Orchestrator gate re-run on b1f8867: `tsc --noEmit` clean; `Tests 334 passed | 12 skipped (346)`.
- Gemini verdict: **APPROVE, zero findings** (scratchpad b2-gemini-review.md). Notes traced
  #readPointer fail-closed etag/len verify (§G/B4), §L attrs capture, codec 2^64-1 round-trip,
  frozen-file invariance. First agy attempt produced empty output (headless read_file auto-denied);
  re-run with fully-inline prompt (spec v3+v5 + diff, 63.5KB) from /tmp/azwork.

## Stage 10 — Lane B3: AzureSpoolMaintenance (2026-08-13)
Author: GPT-5.6-sol (codex MCP thread 019ffc2b-…-0470), orchestrator-committed.
- **68f8c4c**: additive ControlPlane maintenance ops (selectFinalizedOrphansForReclaim w/
  skippedReferenced accounting, markStaleUploads + recoverStaleUploads = §O Phase-2a/2b split,
  markQuarantined, completeStaleUploadReclaim, hardDeleteQuarantined ops); AzureSpoolMaintenance
  runs Path 1 → 2b → 2a → 3 under ONE global inspection budget; dev double extended (publish
  overload preserves frozen signature). Sol also stubbed B2's fake ControlPlane for the wider
  interface (7 additive lines — in scope).
- Orchestrator gates: tsc clean; sandbox `340 passed | 13 skipped`; frozen zero-diff vs b1f8867.
- **Mutation A**: neutralize dev #isReferenced → invariant test "finalized/orphaned ⇒ unreferenced"
  RED (2 failed); restore → green. Oracle non-vacuous.
- LIVE conformance: maintenance + control-plane + spool-volume = **22/22** vs real
  psql-phi-reversal + stgbsphispool/phi-spool.
- Gemini review: **APPROVE-WITH-NOTES** (b3-gemini-review.md). MEDIUM: Postgres completion ops
  crashed the losing worker of a concurrent-maintenance race (0 rows affected) where the dev double
  succeeded idempotently — Phase-2b re-selection makes the race real. Classified: legitimately
  better design (align Postgres to idempotent-success on already-terminal; unexpected states stay
  loud). LOW: dev-double Path-1 ordering nondeterministic.
- **47ef7c8**: sol fix round (same thread). Transactional post-race state verification; deterministic
  dev ordering (reclaim_marked, createdAtMs, id); race/unexpected-state/ordering-parity tests.
  Gates: tsc clean; `347 passed | 13 skipped (360)`.
- **Mutation B** (live): restore strict-throw in markQuarantined → race test RED (1 failed | 13
  passed); restore → green.
- Gemini delta re-check: **APPROVE, both findings RESOLVED** (b3-delta-review.md).
Lane B3 CLOSED. Remaining: Lane D (in-ACA smoke), Lane E (reclamation cron ACA Job), one push → PR.

## Stage 11 — Lanes D + E: Q6 smoke + reclamation cron (2026-08-13/14)
Author: GPT-5.6-sol (same thread); orchestrator committed fccf49b (harness+entrypoint+Dockerfile)
and ab36e47 (fix: entrypoints run idempotent migrations; sanitized error detail — root cause of the
first dry-run failure was `relation "reversal_prepared" does not exist` hidden by a bare catch{}).
- Local live: Q6 smoke ALL FOUR checks PASS; reclaim dry-run `{"mode":"dry-run","scanned":0,...}` exit 0.
- Image: `az acr build` → acrgbsadjudicawus.azurecr.io/phi-engine/reclaim:gly346-ab36e47 (Run cf11, 55s).
- AcrPull granted to id-phi-engine on the registry.
- **Lane D exit criterion (in-ACA, real adapters)**: job-phi-q6-smoke execution g0su6qe **Succeeded**;
  Log Analytics: CONCURRENCY PASS {8 publishers, 1 published, 7 existing, 1 current}; CRASH_RECOVERY
  PASS; NO_PINNED_PARTIALS PASS {1 reclaimed, 1 detached, 1 quarantined}; NONCE_MONOTONICITY PASS;
  Q6_SMOKE_RESULT PASS.
- **Lane E**: job-phi-reclaim created in cae-gbs-wp, Schedule "0 3 * * *", RECLAIM_MODE=dry-run
  (spec §7 ships dry-run first), id-phi-engine identity, KV-sourced secrets as job secrets.
  Manual execution whz5qlv **Succeeded**: `{"mode":"dry-run","scanned":0,"reclaimed":0,
  "skippedReferenced":0,"horizonMs":86400000,"durationMs":128}`.
- Gemini review of the D+E delta: **APPROVE, zero findings** (de-gemini-review.md) — non-vacuous
  smoke oracles, read-only dry-run, no secret leakage, Path-3 gated by includeHardDelete.
Mode promotion dry-run → quarantine → full is a deliberate later gesture (not part of this PR).
ALL LANES CLOSED (A, C, B1, B2, B3, D, E). Next: one push → PR → green CI → merge.
