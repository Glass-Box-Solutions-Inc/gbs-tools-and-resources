// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// Status route. Returns per-system latest validation status from
// the in-memory store. Shows the most recent completed run and
// extracts each system's result from it.

import type { FastifyInstance } from "fastify";
import { getRuns } from "../lib/store.js";
import type { SystemName, SystemValidationResult } from "../types/index.js";

const ALL_SYSTEMS: SystemName[] = [
  "github",
  "linear",
  "n8n",
  "gcp",
  "stripe",
  "kb",
  "slack",
];

export async function statusRoute(app: FastifyInstance): Promise<void> {
  app.get("/api/status", async (_req, reply) => {
    const runs = getRuns();

    // Build a map of the latest validation result for each system
    const latestBySystem: Record<string, SystemValidationResult | null> =
      {};

    for (const system of ALL_SYSTEMS) {
      latestBySystem[system] = null;
    }

    // Walk runs from newest to oldest, filling in any systems we haven't seen yet
    for (const run of runs) {
      if (run.status !== "completed") continue;

      for (const result of run.systems) {
        if (latestBySystem[result.systemName] === null) {
          latestBySystem[result.systemName] = result;
        }
      }

      // Check if all systems are filled
      const allFilled = ALL_SYSTEMS.every(
        (s) => latestBySystem[s] !== null,
      );
      if (allFilled) break;
    }

    const systems = ALL_SYSTEMS.map((name) => {
      const result = latestBySystem[name];
      if (!result) {
        return {
          systemName: name,
          status: "no_data",
          message: "No validation data available yet",
        };
      }

      const allSchemasPassed =
        result.schema.length === 0 ||
        result.schema.every((s) => s.passed);
      const overallHealthy =
        result.connectivity.passed &&
        allSchemasPassed &&
        result.permissions.hasAccess;

      return {
        systemName: result.systemName,
        systemLabel: result.systemLabel,
        configured: result.configured,
        status: overallHealthy ? "healthy" : "degraded",
        connectivity: result.connectivity.passed,
        schemasValid: allSchemasPassed,
        hasAccess: result.permissions.hasAccess,
        latencyP50Ms: Math.round(result.latency.p50),
        lastChecked: result.timestamp,
      };
    });

    const lastRun = runs.find((r) => r.status === "completed");

    return reply.send({
      service: "gbs-integration-validator",
      lastRunId: lastRun?.runId ?? null,
      lastRunAt: lastRun?.completedAt ?? null,
      totalRuns: runs.length,
      systems,
    });
  });
}
