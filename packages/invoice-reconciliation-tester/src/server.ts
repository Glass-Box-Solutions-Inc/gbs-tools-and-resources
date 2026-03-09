// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// Fastify entry point for the invoice reconciliation tester service.
// Registers all route plugins, loads validated environment config, and
// listens on 0.0.0.0 for Cloud Run compatibility.

import Fastify from "fastify";
import { env } from "./lib/env.js";
import { healthRoutes } from "./routes/health.js";
import { statusRoutes } from "./routes/status.js";
import { runRoutes } from "./routes/run.js";
import { resultsRoutes } from "./routes/results.js";
import { generateRoutes } from "./routes/generate.js";

const app = Fastify({ logger: true });

// ── Register route plugins ──────────────────────────────────────────────────

await app.register(healthRoutes);
await app.register(statusRoutes);
await app.register(runRoutes);
await app.register(resultsRoutes);
await app.register(generateRoutes);

// ── Start ───────────────────────────────────────────────────────────────────

app.listen({ port: env.PORT, host: "0.0.0.0" }, (err) => {
  if (err) {
    app.log.error(err);
    process.exit(1);
  }
  app.log.info(
    `invoice-reconciliation-tester listening on port ${env.PORT}`,
  );
});
