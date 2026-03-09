// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// Results routes. GET /api/results lists all validation runs.
// GET /api/results/:id returns detailed results for a specific run.

import type { FastifyInstance } from "fastify";
import { getRuns, getRun } from "../lib/store.js";
import { aggregatePermissions } from "../checks/permission-checker.js";

export async function resultsRoute(app: FastifyInstance): Promise<void> {
  // -- List all runs --
  app.get("/api/results", async (req, reply) => {
    const runs = getRuns();
    const query = req.query as { limit?: string; status?: string };
    const limit = query.limit ? parseInt(query.limit, 10) : 50;
    const statusFilter = query.status;

    let filtered = runs;
    if (statusFilter) {
      filtered = filtered.filter((r) => r.status === statusFilter);
    }

    const page = filtered.slice(0, limit);

    return reply.send({
      total: filtered.length,
      returned: page.length,
      runs: page.map((run) => ({
        runId: run.runId,
        startedAt: run.startedAt,
        completedAt: run.completedAt,
        status: run.status,
        systemCount: run.systems.length,
        includeRateLimitTest: run.includeRateLimitTest,
        summary:
          run.status === "completed"
            ? {
                configured: run.systems.filter((s) => s.configured).length,
                connected: run.systems.filter(
                  (s) => s.connectivity.passed,
                ).length,
                schemasValid: run.systems.filter((s) =>
                  s.schema.every((c) => c.passed),
                ).length,
                fullyAuthorized: run.systems.filter(
                  (s) => s.permissions.hasAccess,
                ).length,
              }
            : null,
      })),
    });
  });

  // -- Get single run detail --
  app.get<{ Params: { id: string } }>(
    "/api/results/:id",
    async (req, reply) => {
      const { id } = req.params;
      const run = getRun(id);

      if (!run) {
        return reply.code(404).send({
          error: "Run not found",
          runId: id,
        });
      }

      // Build an aggregated permissions summary if the run is complete
      const permissionsSummary =
        run.status === "completed"
          ? aggregatePermissions(run.systems.map((s) => s.permissions))
          : null;

      return reply.send({
        ...run,
        permissionsSummary,
      });
    },
  );
}
