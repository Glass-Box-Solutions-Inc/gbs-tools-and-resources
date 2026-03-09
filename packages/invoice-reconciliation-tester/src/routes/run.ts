// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// Test run trigger endpoint. Creates a new test run record, returns 202 Accepted,
// and executes the test suite orchestrator asynchronously via setImmediate().
// Protected by OIDC in production (Cloud Run handles auth).

import type { FastifyInstance } from "fastify";
import { db } from "../lib/db.js";
import { runAllSuites } from "../runner.js";

export async function runRoutes(app: FastifyInstance): Promise<void> {
  app.post("/api/run", async (request, reply) => {
    const body = (request.body as Record<string, unknown>) ?? {};

    // Create a new test run record
    const run = await db.testRun.create({
      data: {
        status: "running",
        config: body as object,
      },
    });

    app.log.info({ runId: run.id }, "Test run created, executing suites");

    // Fire and forget -- do not await so Cloud Run responds immediately
    setImmediate(() => {
      runAllSuites(run.id).catch((err) => {
        app.log.error(
          { runId: run.id, err: err instanceof Error ? err.message : String(err) },
          "Test run failed",
        );
      });
    });

    return reply.code(202).send({
      accepted: true,
      runId: run.id,
      message: "Test run queued for execution",
    });
  });
}
