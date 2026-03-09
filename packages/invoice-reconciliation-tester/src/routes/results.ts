// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// Results endpoints. List test results and retrieve detailed results by run ID.
// Protected by OIDC in production (Cloud Run handles auth).

import type { FastifyInstance } from "fastify";
import { db } from "../lib/db.js";

export async function resultsRoutes(app: FastifyInstance): Promise<void> {
  // List recent test results (aggregated by run)
  app.get("/api/results", async (request, reply) => {
    const limit = Math.min(
      Math.max(1, Number((request.query as Record<string, string>).limit) || 20),
      100,
    );

    const runs = await db.testRun.findMany({
      orderBy: { startedAt: "desc" },
      take: limit,
      include: {
        results: {
          select: {
            id: true,
            suiteName: true,
            testName: true,
            passed: true,
            durationMs: true,
            errorMsg: true,
          },
        },
      },
    });

    const summaries = runs.map((run) => {
      const totalTests = run.results.length;
      const passedTests = run.results.filter((r) => r.passed).length;
      const failedTests = totalTests - passedTests;

      return {
        runId: run.id,
        status: run.status,
        startedAt: run.startedAt.toISOString(),
        completedAt: run.completedAt?.toISOString() ?? null,
        totalTests,
        passedTests,
        failedTests,
        summary: run.summary,
      };
    });

    return reply.send({ results: summaries, total: summaries.length });
  });

  // Get detailed results for a specific run
  app.get("/api/results/:id", async (request, reply) => {
    const { id } = request.params as { id: string };

    const run = await db.testRun.findUnique({
      where: { id },
      include: {
        results: {
          orderBy: { createdAt: "asc" },
        },
      },
    });

    if (!run) {
      return reply.code(404).send({ error: "Test run not found", runId: id });
    }

    // Group results by suite
    const suites: Record<
      string,
      { suiteName: string; tests: typeof run.results; passed: number; failed: number }
    > = {};

    for (const result of run.results) {
      if (!suites[result.suiteName]) {
        suites[result.suiteName] = {
          suiteName: result.suiteName,
          tests: [],
          passed: 0,
          failed: 0,
        };
      }
      suites[result.suiteName].tests.push(result);
      if (result.passed) {
        suites[result.suiteName].passed++;
      } else {
        suites[result.suiteName].failed++;
      }
    }

    return reply.send({
      runId: run.id,
      status: run.status,
      startedAt: run.startedAt.toISOString(),
      completedAt: run.completedAt?.toISOString() ?? null,
      config: run.config,
      summary: run.summary,
      suites: Object.values(suites),
    });
  });
}
