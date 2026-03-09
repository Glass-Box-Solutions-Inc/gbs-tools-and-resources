// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// Run route. POST /api/run triggers a validation run. Creates a unique
// runId, fires off validation via setImmediate() (fire-and-forget for
// Cloud Run compatibility), and returns 202 Accepted immediately.

import { randomUUID } from "node:crypto";
import type { FastifyInstance } from "fastify";
import { addRun, updateRun, saveState } from "../lib/store.js";
import {
  recordSamples,
  saveLatencyState,
} from "../checks/latency-recorder.js";
import { GitHubValidator } from "../validators/github.validator.js";
import { LinearValidator } from "../validators/linear.validator.js";
import { N8nValidator } from "../validators/n8n.validator.js";
import { GcpValidator } from "../validators/gcp.validator.js";
import { StripeValidator } from "../validators/stripe.validator.js";
import { KbValidator } from "../validators/kb.validator.js";
import { SlackValidator } from "../validators/slack.validator.js";
import type { BaseValidator } from "../validators/base.validator.js";
import type {
  SystemName,
  ValidationRun,
  SystemValidationResult,
} from "../types/index.js";

const ALL_SYSTEM_NAMES: SystemName[] = [
  "github",
  "linear",
  "n8n",
  "gcp",
  "stripe",
  "kb",
  "slack",
];

function createValidator(systemName: SystemName): BaseValidator {
  switch (systemName) {
    case "github":
      return new GitHubValidator();
    case "linear":
      return new LinearValidator();
    case "n8n":
      return new N8nValidator();
    case "gcp":
      return new GcpValidator();
    case "stripe":
      return new StripeValidator();
    case "kb":
      return new KbValidator();
    case "slack":
      return new SlackValidator();
  }
}

export async function runRoute(app: FastifyInstance): Promise<void> {
  app.post<{
    Body?: {
      systems?: SystemName[];
      includeRateLimitTest?: boolean;
    };
  }>("/api/run", async (req, reply) => {
    const body = req.body ?? {};
    const requestedSystems = body.systems ?? ALL_SYSTEM_NAMES;
    const includeRateLimitTest = body.includeRateLimitTest ?? false;

    // Validate requested system names
    const invalidSystems = requestedSystems.filter(
      (s) => !ALL_SYSTEM_NAMES.includes(s),
    );
    if (invalidSystems.length > 0) {
      return reply.code(400).send({
        error: `Invalid system names: ${invalidSystems.join(", ")}`,
        validSystems: ALL_SYSTEM_NAMES,
      });
    }

    const runId = randomUUID();
    const run: ValidationRun = {
      runId,
      startedAt: new Date().toISOString(),
      completedAt: null,
      status: "running",
      systems: [],
      includeRateLimitTest,
    };

    addRun(run);

    // Fire and forget — do not await so Cloud Run responds immediately
    setImmediate(() => {
      executeValidation(app, runId, requestedSystems, includeRateLimitTest).catch(
        (err) => {
          app.log.error(
            { err: err instanceof Error ? err.message : String(err), runId },
            "Validation run failed",
          );
          updateRun(runId, {
            status: "failed",
            completedAt: new Date().toISOString(),
          });
          saveState().catch(() => {});
        },
      );
    });

    return reply.code(202).send({
      accepted: true,
      runId,
      message: `Validation run started for ${requestedSystems.length} system(s)`,
      systems: requestedSystems,
      includeRateLimitTest,
    });
  });
}

async function executeValidation(
  app: FastifyInstance,
  runId: string,
  systems: SystemName[],
  _includeRateLimitTest: boolean,
): Promise<void> {
  app.log.info({ runId, systems }, "Starting validation run");
  const results: SystemValidationResult[] = [];

  for (const systemName of systems) {
    app.log.info({ runId, system: systemName }, "Validating system");
    const validator = createValidator(systemName);

    try {
      const result = await validator.validate();
      results.push(result);

      // Record latency samples for historical tracking
      if (result.latency.samples.length > 0) {
        recordSamples(systemName, result.latency.samples);
      }

      app.log.info(
        {
          runId,
          system: systemName,
          configured: result.configured,
          connectivity: result.connectivity.passed,
          schemaChecks: result.schema.length,
          schemasPassed: result.schema.filter((s) => s.passed).length,
          hasAccess: result.permissions.hasAccess,
          latencyP50: Math.round(result.latency.p50),
        },
        "System validation complete",
      );
    } catch (error) {
      app.log.error(
        {
          runId,
          system: systemName,
          err: error instanceof Error ? error.message : String(error),
        },
        "System validation threw unexpected error",
      );

      results.push({
        systemName,
        systemLabel: systemName,
        configured: validator.isConfigured(),
        connectivity: {
          name: "connectivity",
          passed: false,
          message: `Unexpected error: ${error instanceof Error ? error.message : String(error)}`,
          durationMs: 0,
        },
        schema: [],
        permissions: {
          systemName,
          hasAccess: false,
          scopes: [],
          missingScopes: [],
        },
        latency: { p50: 0, p95: 0, p99: 0, samples: [] },
        timestamp: new Date().toISOString(),
      });
    }
  }

  updateRun(runId, {
    status: "completed",
    completedAt: new Date().toISOString(),
    systems: results,
  });

  await saveState();
  await saveLatencyState();

  app.log.info(
    {
      runId,
      totalSystems: results.length,
      configured: results.filter((r) => r.configured).length,
      connected: results.filter((r) => r.connectivity.passed).length,
    },
    "Validation run completed",
  );
}
