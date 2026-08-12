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

## Parallel — data-retention legal audit (Sonnet agent, background)
Launched per Alex to review our data-retention policy vs law (HIPAA/CMIA/CCPA-CPRA/§632/State-Bar/WC).
Report → scratchpad/retention-audit.md. Relevant to this lane: the 7-day soft-delete tail + the
detector-24h/matter-until-deletion retention classes + indefinite tombstone horizon.
