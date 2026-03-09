// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// Status endpoint. Returns the last N test run summaries from the database.
// Protected by OIDC in production (Cloud Run handles auth).

import type { FastifyInstance } from "fastify";
import { db } from "../lib/db.js";

export async function statusRoutes(app: FastifyInstance): Promise<void> {
  app.get("/api/status", async (request, reply) => {
    const limit = Math.min(
      Math.max(1, Number((request.query as Record<string, string>).limit) || 10),
      100,
    );

    const runs = await db.testRun.findMany({
      orderBy: { startedAt: "desc" },
      take: limit,
      select: {
        id: true,
        startedAt: true,
        completedAt: true,
        status: true,
        summary: true,
        config: true,
      },
    });

    return reply.send({
      runs,
      total: runs.length,
      service: "invoice-reconciliation-tester",
    });
  });
}
