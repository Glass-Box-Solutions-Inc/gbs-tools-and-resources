// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// Fastify entrypoint for the GBS Integration Validator service.
// Exposes HTTP endpoints for health checks, status queries, manual
// validation triggers, and results retrieval. Stateless Cloud Run
// service with in-memory + /tmp state persistence.
//
// Env vars (set by Cloud Run / Secret Manager):
//   PORT — Cloud Run sets this automatically (default: 5510)
//   See .env.example for full list of API credentials.

import Fastify from "fastify";
import { env } from "./lib/env.js";
import { loadState } from "./lib/store.js";
import { loadLatencyState } from "./checks/latency-recorder.js";
import { healthRoute } from "./routes/health.js";
import { statusRoute } from "./routes/status.js";
import { runRoute } from "./routes/run.js";
import { resultsRoute } from "./routes/results.js";

const app = Fastify({ logger: true });

// -- Register routes ----------------------------------------------------------

await app.register(healthRoute);
await app.register(statusRoute);
await app.register(runRoute);
await app.register(resultsRoute);

// -- Load persisted state from /tmp -------------------------------------------

await loadState();
await loadLatencyState();
app.log.info("Loaded persisted state from /tmp");

// -- Start server -------------------------------------------------------------

try {
  await app.listen({ port: env.PORT, host: "0.0.0.0" });
  app.log.info(`gbs-integration-validator listening on port ${env.PORT}`);
} catch (err) {
  app.log.error(err);
  process.exit(1);
}
