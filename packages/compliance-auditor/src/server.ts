// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// Fastify Cloud Run entrypoint for the compliance-auditor service. Registers
// all route modules and starts listening on 0.0.0.0 with the configured PORT.
// Follows the Squeegee Fastify server pattern with Pino logging.

import Fastify from "fastify";
import { env } from "./lib/env.js";
import { healthRoutes } from "./routes/health.js";
import { statusRoutes } from "./routes/status.js";
import { runRoutes } from "./routes/run.js";
import { reportRoutes } from "./routes/reports.js";

const app = Fastify({ logger: true });

// Register route modules
await app.register(healthRoutes);
await app.register(statusRoutes);
await app.register(runRoutes);
await app.register(reportRoutes);

// Start server
app.listen({ port: env.PORT, host: "0.0.0.0" }, (err) => {
  if (err) {
    app.log.error(err);
    process.exit(1);
  }
  app.log.info(`compliance-auditor listening on port ${env.PORT}`);
});
