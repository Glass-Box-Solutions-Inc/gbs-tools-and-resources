import { Pool } from "pg";
import { AzureSpoolMaintenance } from "../src/tokens/durable/azure/azure-spool-maintenance";
import { PostgresControlPlane } from "../src/tokens/durable/azure/postgres-control-plane";
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

async function main(): Promise<void> {
  const startedAt = Date.now();
  let mode: ReclaimMode = "dry-run";
  let horizonMs = DEFAULT_HORIZON_MS;
  let pool: Pool | undefined;
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
    const controlPlane = new PostgresControlPlane(pool);

    const outcome = mode === "dry-run"
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

    console.log(JSON.stringify({
      mode,
      scanned: outcome.scanned,
      reclaimed: outcome.reclaimed,
      skippedReferenced: outcome.skippedReferenced,
      horizonMs,
      durationMs: Date.now() - startedAt,
    }));
  } catch {
    console.error(JSON.stringify({
      mode,
      scanned: 0,
      reclaimed: 0,
      skippedReferenced: 0,
      horizonMs,
      durationMs: Date.now() - startedAt,
      error: "reclamation_failed",
    }));
    process.exitCode = 1;
  } finally {
    await pool?.end().catch(() => undefined);
  }
}

void main();
