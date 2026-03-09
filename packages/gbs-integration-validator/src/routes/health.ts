// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// Health route. No auth required. Returns service name and status.

import type { FastifyInstance } from "fastify";

export async function healthRoute(app: FastifyInstance): Promise<void> {
  app.get("/health", async (_req, reply) => {
    return reply.send({
      status: "ok",
      service: "gbs-integration-validator",
    });
  });
}
