import { appendFileSync, readFileSync, writeFileSync } from "node:fs";
import { spawnSync } from "node:child_process";

const P = "src/tokens/durable/azure/postgres-control-plane.ts";
const D = "src/tokens/durable/dev/in-memory-control-plane.ts";
const S = "src/tokens/durable/dev/in-memory-spool-volume.ts";
const R = "src/tokens/durable/durable-reversal-store.ts";
const M = "src/tokens/durable/azure/azure-spool-maintenance.ts";
const V = "src/tokens/durable/azure/azure-files-spool-volume.ts";
const G = "migrations/0001_phi_reversal_control_plane.sql";
const td = "tests/durable-control-plane.test.ts";
const ts = "tests/durable-reversal-store.test.ts";
const tp = "tests/postgres-control-plane.test.ts";
const tm = "tests/azure-spool-maintenance.test.ts";
const tv = "tests/azure-files-spool-volume.test.ts";
const q = (name, file, from, to, testFile, test) => ({ name, file, edits: [{ from, to }], testFile, test });

const mutations = [
  q("MUT-RETENTION-BIND-PROCESS-MEMORY", D,
    "const existing = this.#operationRetention.get(operationKey);",
    "const existing = new Map().get(operationKey);", td, "keeps a durable operation binding"),
  q("MUT-RETENTION-BIND-TOKEN-SCOPED", S,
    "const key = `${blob.meta.tenantId as unknown as string}\\0${blob.meta.attemptId as unknown as string}`;",
    "const key = `${blob.meta.tenantId as unknown as string}\\0${blob.meta.attemptId as unknown as string}\\0${blob.meta.token as unknown as string}`;",
    ts, "rejects a sequential classifier flip"),
  q("MUT-RETENTION-BIND-MATTER-SCOPED", S,
    "const key = `${blob.meta.tenantId as unknown as string}\\0${blob.meta.attemptId as unknown as string}`;",
    "const key = `${blob.meta.tenantId as unknown as string}\\0${blob.meta.matterId as unknown as string}\\0${blob.meta.attemptId as unknown as string}`;",
    ts, "keys bindings by exact tenant"),
  q("MUT-RETENTION-BIND-LAST-WRITER-WINS", S,
    "throw new Error(\"operation_retention_binding_mismatch\");",
    "this.#operationRetention.set(key, blob.meta.retentionClass); return;", ts, "rejects a sequential classifier flip"),
  q("MUT-RETENTION-BIND-NONATOMIC-ANCHOR", D,
    "if (insertedBinding) this.#operationRetention.delete(operationKey);",
    "if (insertedBinding) { /* retain bare binding */ }", td, "rolls back both binding"),
  q("MUT-RETENTION-MISMATCH-ACCEPT", S,
    "throw new Error(\"operation_retention_binding_mismatch\");", "return;", ts, "rejects a sequential classifier flip"),
  q("MUT-RETENTION-BIND-DROP-ON-CRASH", S,
    "public crash(): void {\n    for (const [key, claim] of this.#claims) {",
    "public crash(): void {\n    this.#operationRetention.clear();\n    for (const [key, claim] of this.#claims) {",
    ts, "persists a committed anchor"),
  { name: "MUT-RETENTION-BIND-GC-AFTER-BLOB", file: D, edits: [{
    from: "delete row.quarantineBlob;\n      if (row.quarantineBlob === undefined) {\n        this.#prepared.delete(asString(row.preparedBlobId));",
    to: "delete row.quarantineBlob;\n      if (row.quarantineBlob === undefined) {\n        if (row.operationKey !== null) this.#operationRetention.delete(row.operationKey);\n        this.#prepared.delete(asString(row.preparedBlobId));",
  }], testFile: td, test: "keeps a durable operation binding" },
  q("MUT-RETENTION-MISMATCH-LEAK-DETAIL", R,
    "throw new ReversalFailedError();\n    }\n  }\n\n  /**\n   * Resolve encountered tokens",
    "throw new Error(\"primary db down: Maria García at /var/spool/reversal\");\n    }\n  }\n\n  /**\n   * Resolve encountered tokens",
    ts, "record rejection has the fixed"),
  q("MUT-RETENTION-BINDING-KEY-NONINJECTIVE", S,
    "const key = `${blob.meta.tenantId as unknown as string}\\0${blob.meta.attemptId as unknown as string}`;",
    "const key = `${blob.meta.tenantId as unknown as string}${blob.meta.attemptId as unknown as string}`;",
    ts, "keys bindings by exact tenant"),
  q("MUT-RETENTION-BIND-INBAND-OVERRIDE", S,
    "throw new Error(\"operation_retention_binding_mismatch\");",
    "this.#operationRetention.set(key, blob.meta.retentionClass); return;", ts, "has no in-band override"),
  q("MUT-ANCHOR-NON-READ-COMMITTED", P, "SET TRANSACTION ISOLATION LEVEL READ COMMITTED",
    "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ", tp, "keeps the READ COMMITTED"),
  q("MUT-ANCHOR-SELECT-THEN-INSERT", P, "INSERT INTO reversal_operation_retention (",
    "SELECT * FROM reversal_operation_retention /* select-then-insert */ (", tp, "keeps the READ COMMITTED"),
  q("MUT-SUPERSEDE-LEAVE-OLD-COMMITTED", D, "oldPrepared.state = \"superseded\";",
    "oldPrepared.state = \"committed\";", td, "advances current and atomically"),
  q("MUT-SUPERSEDE-LEAVE-CLAIM-REFERENCE", D, "oldClaim.preparedBlobId = null;",
    "oldClaim.preparedBlobId = oldPrepared.preparedBlobId;", td, "advances current and atomically"),
  q("MUT-SUPERSEDE-NONATOMIC-WITH-CAS", D,
    "for (const [key, value] of claims) {\n        this.#claims.set(key, value);\n        this.#claimsByCommit.set(asString(value.commitHandle), value);\n      }",
    "/* omit claim rollback */", td, "makes every intra-flush advance gate"),
  q("MUT-SUPERSEDE-BEFORE-CAS-WINS", D,
    "for (const [key, value] of current) this.#current.set(key, value);",
    "/* omit pointer rollback */", td, "makes every intra-flush advance gate"),
  q("MUT-CAS-LOSER-STAYS-COMMITTED", D,
    "this.#fault(\"flushAfterLoserClaim\");\n      row.state = \"superseded\";",
    "this.#fault(\"flushAfterLoserClaim\");\n      row.state = \"committed\";", td, "makes both losing-CAS gates"),
  q("MUT-SUPERSEDED-FLUSH-RESURRECTS", D, "if (claim.state === \"superseded\") return Promise.resolve();",
    "if (claim.state === \"superseded\") claim.state = \"pending\";", td, "advances current and atomically"),
  q("MUT-SUPERSEDED-FLUSH-FAILS-IDEMPOTENCY", D, "if (claim.state === \"superseded\") return Promise.resolve();",
    "if (claim.state === \"superseded\") return Promise.reject(new Error(\"mutant\"));", td, "advances current and atomically"),
  q("MUT-FLUSHED-NONCURRENT-NO-SELF-HEAL", D, "this.#selfHealIfStale(existing, nowEpochMilliseconds);",
    "/* skip self-heal */", td, "self-heals a stale non-current"),
  q("MUT-SUPERSEDE-RECLAIM-BEFORE-WINDOW", D,
    "return supersededAt + BigInt(Math.max(supersedeRetentionMs, readDrainMs));",
    "return supersededAt;", td, "computes matter and detector candidacy"),
  q("MUT-SUPERSEDE-CANDIDACY-OMITS-DRAIN-MAX", D, "return drain > policy ? drain : policy;",
    "return policy;", td, "keeps the drain MAX floor"),
  q("MUT-DETECTOR-SUPERSEDE-DROPS-EXPIRY-FLOOR", D,
    "const policy = row.retentionExpiresAtMs < window ? row.retentionExpiresAtMs : window;",
    "const policy = window;", td, "computes matter and detector candidacy"),
  q("MUT-SUPERSEDED-MATTER-NEVER", D,
    "return supersededAt + BigInt(Math.max(supersedeRetentionMs, readDrainMs));",
    "return undefined;", td, "computes matter and detector candidacy"),
  { name: "MUT-NONSUPERSEDED-MATTER-RECLAIMABLE", file: D, edits: [
    { from: "if (row.state !== \"superseded\" || row.supersededAtMs === undefined) return undefined;",
      to: "if ((row.state !== \"superseded\" && row.state !== \"committed\") || (row.state === \"superseded\" && row.supersededAtMs === undefined)) return undefined;" },
    { from: "(row.state === \"superseded\" &&\n          (this.#supersededCandidacy",
      to: "((row.state === \"superseded\" || row.state === \"committed\") &&\n          (this.#supersededCandidacy" },
    { from: "const supersededAt = BigInt(row.supersededAtMs);",
      to: "if (row.state === \"committed\") return BigInt(row.createdAtMs);\n    const supersededAt = BigInt(row.supersededAtMs);" },
  ], testFile: td, test: "computes matter and detector candidacy" },
  q("MUT-RETENTION-NUMERIC-TO-BIGINT", G, "retention_expires_at_ms NUMERIC(20,0)",
    "retention_expires_at_ms BIGINT", tp, "keeps the expand migration"),
  q("MUT-RETENTION-ORIGIN-TRUST-BACKFILLED-CREATED", D, "const supersededAt = BigInt(row.supersededAtMs);",
    "const supersededAt = BigInt(row.recordCreatedAtMs ?? row.supersededAtMs);", td, "keeps the drain MAX floor"),
  q("MUT-TX-NOW-REPLICA-CLOCK", P,
    "const current = currentResult.rows[0];\n        const clock = await client.query<DbNowRow>(\n          `SELECT (EXTRACT(EPOCH FROM clock_timestamp()) * 1000)::bigint::text AS db_now_ms`,",
    "const current = currentResult.rows[0];\n        const clock = await client.query<DbNowRow>(\n          `SELECT ${input.nowEpochMilliseconds}::bigint::text AS db_now_ms`,",
    tp, "contains fatal legacy class"),
  q("MUT-SUPERSEDE-SKIP-UNREFERENCED-GUARD", P,
    "AND NOT EXISTS (\n             SELECT 1 FROM reversal_claim c WHERE c.prepared_blob_id = p.prepared_blob_id\n           )\n           AND NOT EXISTS (\n             SELECT 1 FROM reversal_current c WHERE c.prepared_blob_id = p.prepared_blob_id\n           )",
    "/* omit reference guards */", tp, "filters Path-1 references before LIMIT"),
  q("MUT-SUPERSEDE-PRIVATE-BUDGET", M,
    "uploadHorizonEpochMs: Math.max(0, nowEpochMs - this.#uploadHorizonMs),\n        limit: remaining,",
    "uploadHorizonEpochMs: Math.max(0, nowEpochMs - this.#uploadHorizonMs),\n        limit: scrubbed.limit,",
    tm, "shares one global inspection budget"),
  q("MUT-SUPERSEDE-RECOVERY-SELECTOR-OMITTED", D, "row.state === \"reclaim_marked\" ||",
    "false ||", tm, "recovers a reclaim_marked row"),
  q("MUT-READ-OLD-POINTER-NO-QUARANTINE-FALLBACK", V,
    "for (const path of [pointer.blobPath, quarantine, pointer.blobPath]) {",
    "for (const path of [pointer.blobPath]) {", tv, "reads a snapshotted old pointer"),
  q("MUT-READ-INVENTS-UNENFORCEABLE-DEADLINE", V,
    "const quarantine = `reclaim-quarantine/${pointer.preparedBlobId as unknown as string}`;",
    "const quarantine = `reclaim-quarantine/${pointer.preparedBlobId as unknown as string}`;\n    if (this.#nowEpochMilliseconds() >= pointer.flushedAtEpochMs) throw new Error(\"mutant_reader_deadline\");",
    tv, "reads a snapshotted old pointer"),
  q("MUT-QUARANTINE-GRACE-SHORTER-THAN-DRAIN", M,
    "if (this.#supersedeRetentionMs < this.#graceMs || this.#graceMs < this.#readDrainMs) {",
    "if (this.#supersedeRetentionMs < this.#graceMs) {", tm, "ORACLE-MAINTENANCE-WINDOW-ORDER"),
  q("MUT-SUPERSEDE-WINDOW-SHORTER-THAN-GRACE", M,
    "if (this.#supersedeRetentionMs < this.#graceMs || this.#graceMs < this.#readDrainMs) {",
    "if (this.#graceMs < this.#readDrainMs) {", tm, "ORACLE-MAINTENANCE-WINDOW-ORDER"),
  q("MUT-SUPERSEDE-HARD-DELETE-DIRECT", M, "await this.#blobStore.rename(row.blobPath, destination);",
    "await this.#blobStore.remove(row.blobPath);", tm, "Path 1 quarantines old unreferenced"),
  q("MUT-SUPERSEDE-HARD-DELETE-OMITS-GRACE", M,
    "olderThanEpochMs: Math.max(0, nowEpochMs - this.#graceMs),",
    "olderThanEpochMs: nowEpochMs,", tm, "Path 3 keeps young quarantine"),
  q("MUT-QUARANTINE-MISSING-BOTH-AS-SUCCESS", M,
    "if (sourceHead === undefined) {\n      throw new Error(\"azure_spool_maintenance_quarantine_both_paths_absent\");\n    }",
    "if (sourceHead === undefined) {\n      return;\n    }", tm, "leaves reclaim_marked and fails when both"),
  q("MUT-MIGRATION-NONIDEMPOTENT", G, "ADD COLUMN IF NOT EXISTS operation_key TEXT",
    "ADD COLUMN operation_key TEXT", tp, "keeps the expand migration"),
  q("MUT-MIGRATION-DELETE-LEGACY-ROW", G,
    "-- GLY-345 v3 additive delta. runMigrations() already wraps this file in one transaction.",
    "-- GLY-345 v3 additive delta. runMigrations() already wraps this file in one transaction.\nDELETE FROM reversal_prepared;",
    tp, "keeps the expand migration"),
  q("MUT-MIGRATION-IGNORE-MIXED-LEGACY-CLASS", G, "HAVING count(DISTINCT CASE",
    "HAVING false AND count(DISTINCT CASE", tp, "contains fatal legacy class"),
  q("MUT-MIGRATION-SILENT-FINITE-MATTER-AS-DETECTOR", G,
    "c.expires_at_ms <> c.created_at_ms::numeric + 86400000::numeric",
    "false /* accept ambiguous finite expiry */", tp, "contains fatal legacy class"),
  q("MUT-MIGRATION-SKIP-ROW-COUNT-GUARD", G, "IF prepared_count > 100000 THEN",
    "IF false THEN", tp, "keeps the expand migration"),
  q("MUT-MIGRATION-VALIDATE-HOT-CONSTRAINTS", G,
    ") NOT VALID;\n\nALTER TABLE reversal_prepared\n  ADD CONSTRAINT reversal_prepared_gly345_blob_state_check",
    ");\n\nALTER TABLE reversal_prepared\n  ADD CONSTRAINT reversal_prepared_gly345_blob_state_check",
    tp, "keeps the expand migration"),
  q("MUT-MIGRATION-ADDS-REQUIRED-CHECK-DURING-EXPAND", G,
    "ALTER TABLE reversal_prepared ADD COLUMN IF NOT EXISTS reclaim_after_ms NUMERIC(20,0);",
    "ALTER TABLE reversal_prepared ADD COLUMN IF NOT EXISTS reclaim_after_ms NUMERIC(20,0);\nALTER TABLE reversal_prepared ADD CONSTRAINT reversal_prepared_gly345_required_check CHECK (operation_key IS NOT NULL);",
    tp, "keeps the expand migration"),
  q("MUT-MIGRATION-RETENTION-CHECK-REJECTS-NULL-METADATA", G,
    "operation_key IS NULL\n    OR record_created_at_ms IS NULL",
    "operation_key IS NOT NULL\n    AND record_created_at_ms IS NOT NULL", tp, "keeps the expand migration"),
  { name: "MUT-MIGRATION-ASSUME-CONSTRAINT-NAME", file: G, edits: Array.from({ length: 6 }, () => ({
    from: "pg_get_constraintdef(c.oid)", to: "'assumed_legacy_state_constraint'",
  })), testFile: tp, test: "discovers anonymous state checks" },
  q("MUT-MIGRATION-TRUST-LEGACY-FLUSHED-AT", G, "mc.db_now_ms AS migration_superseded_at_ms",
    "LEAST(cur.flushed_at_ms, mc.db_now_ms) AS migration_superseded_at_ms", tp, "discovers anonymous state checks"),
  q("MUT-SELF-HEAL-DROPS-F-A-ROW-LOCK", P,
    "FROM reversal_prepared\n       WHERE prepared_blob_id = $1\n       FOR UPDATE`,\n      [claim.prepared_blob_id],",
    "FROM reversal_prepared\n       WHERE prepared_blob_id = $1`,\n      [claim.prepared_blob_id],",
    tp, "contains fatal legacy class"),
];

const ledger = ".planning/GLY-345/mutation-evidence.log";
writeFileSync(ledger, `GLY-345 mutation evidence\nSTART=${new Date().toISOString()}\n`);
const originals = new Map(mutations.map(({ file }) => [file, readFileSync(file, "utf8")]));
let failures = 0;
for (const [index, mutant] of mutations.entries()) {
  const original = originals.get(mutant.file);
  let changed = original;
  const anchors = [];
  try {
    for (const edit of mutant.edits) {
      const count = changed.split(edit.from).length - 1;
      if (count < 1) throw new Error(`missing anchor: ${edit.from.slice(0, 100)}`);
      anchors.push(`${mutant.file}:${count}x:${edit.from.slice(0, 80).replaceAll("\n", "\\n")}`);
      changed = changed.replace(edit.from, edit.to);
    }
    writeFileSync(mutant.file, changed);
    const applied = changed !== original && readFileSync(mutant.file, "utf8") === changed;
    const red = spawnSync("npx", ["vitest", "run", mutant.testFile, "-t", mutant.test, "--reporter=dot"], {
      encoding: "utf8",
    });
    writeFileSync(mutant.file, original);
    const restored = readFileSync(mutant.file, "utf8") === original;
    const green = spawnSync("npx", ["vitest", "run", mutant.testFile, "-t", mutant.test, "--reporter=dot"], {
      encoding: "utf8",
    });
    const passed = applied && red.status !== 0 && restored && green.status === 0;
    if (!passed) failures += 1;
    appendFileSync(ledger,
      `\n[${index + 1}/${mutations.length}] ${mutant.name}\n` +
      `ANCHOR=${anchors.join(" | ")}\nVERIFIED_APPLIED=${applied}\n` +
      `RED_TEST=${mutant.testFile} :: ${mutant.test}\nRED_EXIT=${red.status}\n${red.stdout}${red.stderr}` +
      `RESTORED=${restored}\nGREEN_EXIT=${green.status}\n${green.stdout}${green.stderr}RESULT=${passed ? "PASS" : "FAIL"}\n`);
    process.stdout.write(`${mutant.name}: applied=${applied} red=${red.status} restored=${restored} green=${green.status}\n`);
  } catch (error) {
    writeFileSync(mutant.file, original);
    failures += 1;
    appendFileSync(ledger, `\n${mutant.name}\nHARNESS_ERROR=${error.stack ?? error}\nRESULT=FAIL\n`);
    process.stdout.write(`${mutant.name}: HARNESS_ERROR=${error.message}\n`);
  }
}
for (const [file, original] of originals) writeFileSync(file, original);
appendFileSync(ledger, `\nEND=${new Date().toISOString()}\nTOTAL=${mutations.length}\nFAILURES=${failures}\n`);
process.stdout.write(`TOTAL=${mutations.length} FAILURES=${failures}\n`);
process.exitCode = failures === 0 ? 0 : 1;
