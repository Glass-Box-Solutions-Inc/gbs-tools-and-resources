import type { PoolConfig } from "pg";
import { AzureFilesBlobStore } from "./azure-files-blob-store";

export type RuntimeEnvironment = Readonly<Record<string, string | undefined>>;

function required(environment: RuntimeEnvironment, name: string): string {
  const value = environment[name];
  if (value === undefined || value.length === 0) {
    throw new Error(`missing_${name}`);
  }
  return value;
}

function port(environment: RuntimeEnvironment): number {
  const value = environment.PGPORT ?? "5432";
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed <= 0 || parsed > 65_535) {
    throw new Error("invalid_PGPORT");
  }
  return parsed;
}

/** Shared environment contract for the Q6 smoke and reclamation ACA Job. */
export function postgresConfigFromEnvironment(
  environment: RuntimeEnvironment = process.env,
): PoolConfig {
  return {
    host: required(environment, "PGHOST"),
    user: required(environment, "PGUSER"),
    password: required(environment, "PGPASSWORD"),
    database: required(environment, "PGDATABASE"),
    port: port(environment),
    ...(environment.PGSSLMODE === "require" ? { ssl: { rejectUnauthorized: false } } : {}),
  };
}

export function azureFilesBlobStoreFromEnvironment(
  environment: RuntimeEnvironment = process.env,
): AzureFilesBlobStore {
  return new AzureFilesBlobStore(
    required(environment, "PHI_SPOOL_ACCOUNT"),
    required(environment, "PHI_SPOOL_KEY"),
    required(environment, "PHI_SPOOL_SHARE"),
  );
}
