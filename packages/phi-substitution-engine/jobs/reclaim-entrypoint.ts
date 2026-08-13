import { Pool } from "pg";
import { AzureSpoolMaintenance } from "../src/tokens/durable/azure/azure-spool-maintenance";
import { PostgresControlPlane, runMigrations } from "../src/tokens/durable/azure/postgres-control-plane";
import {
  azureFilesBlobStoreFromEnvironment,
  postgresConfigFromEnvironment,
} from "../src/tokens/durable/azure/runtime-config";

const DEFAULT_HORIZON_MS = 86_400_000;
const DEFAULT_UPLOAD_HORIZON_MS = 172_800_000;
const DEFAULT_GRACE_MS = 86_400_000;
const DEFAULT_LIMIT = 1_000;

type ReclaimMode = "dry-run" | "quarantine" | "full";

function integerEnvironment(name: string, fallback: number, allowZero: boolean): number {
  const raw = process.env[name];
  const value = raw === undefined ? fallback : Number(raw);
  if (!Number.isSafeInteger(value) || value < (allowZero ? 0 : 1)) {
    throw new Error(`invalid_${name}`);
  }
  return value;
}

function modeFromEnvironment(): ReclaimMode {
  const mode = process.env.RECLAIM_MODE ?? "dry-run";
  if (mode !== "dry-run" && mode !== "quarantine" && mode !== "full") {
    throw new Error("invalid_RECLAIM_MODE");
  }
  return mode;
}

function errorDetail(error: unknown): string {
  const message = error instanceof Error ? error.message : String(error);
  return message.replace(/[\r\n]+/g, " ").slice(0, 300);
}

async function main(): Promise<void> {
  const startedAt = Date.now();
  let mode: ReclaimMode = "dry-run";
  let horizonMs = DEFAULT_HORIZON_MS;
  let pool: Pool | undefined;
  let outcome: { readonly scanned: number; readonly reclaimed: number; readonly skippedReferenced: number } | undefined;
  let failure: unknown;
  try {
    mode = modeFromEnvironment();
    horizonMs = integerEnvironment("RECLAIM_HORIZON_MS", DEFAULT_HORIZON_MS, true);
    const uploadHorizonMs = integerEnvironment(
      "RECLAIM_UPLOAD_HORIZON_MS",
      DEFAULT_UPLOAD_HORIZON_MS,
      true,
    );
    const graceMs = integerEnvironment("RECLAIM_GRACE_MS", DEFAULT_GRACE_MS, true);
    const limit = integerEnvironment("RECLAIM_LIMIT", DEFAULT_LIMIT, false);
    const nowEpochMs = Date.now();
    pool = new Pool(postgresConfigFromEnvironment());
    await runMigrations(pool);
    const controlPlane = new PostgresControlPlane(pool);

    outcome = mode === "dry-run"
      ? await controlPlane.previewReclamation({
        olderThanEpochMs: Math.max(0, nowEpochMs - horizonMs),
        uploadHorizonEpochMs: Math.max(0, nowEpochMs - uploadHorizonMs),
        quarantinedBeforeEpochMs: Math.max(0, nowEpochMs - graceMs),
        limit,
        includeHardDelete: true,
      })
      : await new AzureSpoolMaintenance({
        controlPlane,
        blobStore: azureFilesBlobStoreFromEnvironment(),
        uploadHorizonMs,
        graceMs,
        now: () => nowEpochMs,
        includeHardDelete: mode === "full",
      }).reclaimOrphanedPrepared({
        olderThanEpochMs: Math.max(0, nowEpochMs - horizonMs),
        limit,
      });

  } catch (error: unknown) {
    failure = error;
  } finally {
    if (pool !== undefined) {
      try {
        await pool.end();
      } catch (error: unknown) {
        failure ??= error;
      }
    }
  }

  if (failure !== undefined || outcome === undefined) {
    console.error(JSON.stringify({
      mode,
      scanned: 0,
      reclaimed: 0,
      skippedReferenced: 0,
      horizonMs,
      durationMs: Date.now() - startedAt,
      error: "reclamation_failed",
      detail: errorDetail(failure ?? "missing_reclamation_outcome"),
    }));
    process.exitCode = 1;
  } else {
    console.log(JSON.stringify({
      mode,
      scanned: outcome.scanned,
      reclaimed: outcome.reclaimed,
      skippedReferenced: outcome.skippedReferenced,
      horizonMs,
      durationMs: Date.now() - startedAt,
    }));
  }
}

void main();
