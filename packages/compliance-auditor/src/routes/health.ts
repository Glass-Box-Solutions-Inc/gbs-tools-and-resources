// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// Health check endpoint — no authentication required. Used by Cloud Run
// startup/liveness probes and the Dockerfile HEALTHCHECK instruction.

import type { FastifyInstance } from "fastify";

export async function healthRoutes(app: FastifyInstance): Promise<void> {
  app.get("/health", async (_request, reply) => {
    return reply.send({
      status: "ok",
      service: "compliance-auditor",
      version: "1.0.0",
    });
  });
}
