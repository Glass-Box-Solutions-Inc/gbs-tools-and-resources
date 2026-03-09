/**
 * Squeegee Cloud Run Server
 *
 * Fastify entrypoint for the Squeegee documentation curation service.
 * Exposes HTTP endpoints for Cloud Scheduler, GitHub webhooks, and
 * manual triggers. The pipeline itself runs as a fire-and-forget
 * child process so Cloud Run can return 202 immediately.
 *
 * Env vars (set by Cloud Run / Secret Manager):
 *   PORT         — Cloud Run sets this automatically (default: 8080)
 *   GITHUB_PAT   — injected from Secret Manager (github-pat-glassbox)
 *   GITHUB_ORG   — GitHub org to curate (default: Glass-Box-Solutions-Inc)
 *
 * @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
 */

'use strict';

const Fastify = require('fastify');
const fs = require('fs').promises;
const path = require('path');
const { runOrgPipeline } = require('./github/org-discovery');

const PORT = parseInt(process.env.PORT || '8080', 10);
const STATE_FILE = '/tmp/squeegee-state.json';

const app = Fastify({ logger: true });

// ─── Health ──────────────────────────────────────────────────────────────────

app.get('/health', async (_req, reply) => {
  return reply.send({ status: 'ok', service: 'squeegee', version: '2.0.0' });
});

// ─── Status ──────────────────────────────────────────────────────────────────

app.get('/api/status', async (_req, reply) => {
  try {
    const raw = await fs.readFile(STATE_FILE, 'utf-8');
    return reply.send(JSON.parse(raw));
  } catch {
    return reply.send({ runs: [], message: 'No runs recorded yet' });
  }
});

// ─── Full org pipeline trigger ────────────────────────────────────────────────

app.post('/api/run', async (req, reply) => {
  const filterRepo = req.body?.repo || null;
  app.log.info({ filterRepo }, 'Triggering full org pipeline');

  // Fire and forget — do not await so Cloud Run responds immediately
  setImmediate(() => {
    runOrgPipeline({ filterRepo }).catch(err => {
      app.log.error({ err: err.message }, 'Org pipeline failed');
    });
  });

  return reply.code(202).send({
    accepted: true,
    message: filterRepo ? `Queued pipeline for repo: ${filterRepo}` : 'Queued full org pipeline',
  });
});

// ─── Single-stage trigger ─────────────────────────────────────────────────────

app.post('/api/run/:command', async (req, reply) => {
  const { command } = req.params;
  const filterRepo = req.body?.repo || null;

  const validCommands = new Set([
    'scan', 'analyze', 'variable', 'practices', 'plans', 'changelog',
    'patterns', 'report', 'health', 'projects', 'state', 'generate',
    'validate', 'claudemd', 'full',
    'portal', 'portal-collect', 'portal-ai', 'portal-render',
  ]);

  if (!validCommands.has(command)) {
    return reply.code(400).send({ error: `Unknown command: ${command}` });
  }

  app.log.info({ command, filterRepo }, 'Triggering single-stage pipeline');

  setImmediate(() => {
    runOrgPipeline({ command, filterRepo }).catch(err => {
      app.log.error({ err: err.message }, `Stage '${command}' failed`);
    });
  });

  return reply.code(202).send({
    accepted: true,
    message: `Queued stage '${command}'${filterRepo ? ` for repo: ${filterRepo}` : ''}`,
  });
});

// ─── Intelligence API routes ──────────────────────────────────────────────────

app.register(require('./api/intelligence'), { prefix: '/api/intelligence' });

// ─── Portal API routes ───────────────────────────────────────────────────────

app.register(require('./api/portal'), { prefix: '/api/portal' });

// ─── GitHub push webhook ──────────────────────────────────────────────────────

// Debounce map: repoName -> timeout ID (5-minute window)
const webhookDebounce = new Map();
const DEBOUNCE_MS = 5 * 60 * 1000; // 5 minutes

app.post('/api/webhook', async (req, reply) => {
  const event = req.headers['x-github-event'];

  // Only process push events
  if (event !== 'push') {
    return reply.code(200).send({ skipped: true, reason: `event '${event}' ignored` });
  }

  const repoName = req.body?.repository?.name;
  if (!repoName) {
    return reply.code(400).send({ error: 'Missing repository.name in payload' });
  }

  // Ignore pushes from Squeegee's own auto-curate branches to prevent loops
  const ref = req.body?.ref || '';
  if (ref.includes('squeegee/auto-curate')) {
    return reply.code(200).send({ skipped: true, reason: 'Squeegee auto-curate push ignored' });
  }

  // Ignore [squeegee-auto] commits
  const headCommit = req.body?.head_commit?.message || '';
  if (headCommit.includes('[squeegee-auto]')) {
    return reply.code(200).send({ skipped: true, reason: 'Squeegee auto-commit ignored' });
  }

  // Debounce: reset timer for this repo
  if (webhookDebounce.has(repoName)) {
    clearTimeout(webhookDebounce.get(repoName));
    app.log.info({ repoName }, 'Webhook debounced — resetting timer');
  }

  const timeoutId = setTimeout(() => {
    webhookDebounce.delete(repoName);

    app.log.info({ repoName, ref }, 'Webhook push — running curation + portal refresh');

    // Run curation pipeline, then portal refresh for this repo
    runOrgPipeline({ filterRepo: repoName })
      .then(() => {
        // Trigger portal refresh for this single repo after curation
        const portalRefresh = require('./api/portal');
        // Portal refresh is handled via the API route — we simulate an internal call
        app.inject({
          method: 'POST',
          url: `/api/portal/refresh/${repoName}`,
        }).catch(err => {
          app.log.error({ err: err.message }, `Portal refresh failed for ${repoName}`);
        });
      })
      .catch(err => {
        app.log.error({ err: err.message }, `Webhook pipeline failed for ${repoName}`);
      });
  }, DEBOUNCE_MS);

  webhookDebounce.set(repoName, timeoutId);

  return reply.code(202).send({ accepted: true, repo: repoName, debounced: true });
});

// ─── Start ────────────────────────────────────────────────────────────────────

async function start() {
  // Wait for all plugins/routes to register before binding the port.
  // Cloud Run's TCP startup probe only passes once the port is open,
  // so this guarantees no requests arrive before routes are ready.
  await app.ready();
  await app.listen({ port: PORT, host: '0.0.0.0' });
  app.log.info(`Squeegee listening on port ${PORT}`);
}

start().catch(err => {
  app.log.error(err);
  process.exit(1);
});

// ─── Graceful shutdown ───────────────────────────────────────────────────────
// Cloud Run sends SIGTERM with a 10s grace period before SIGKILL.

let shuttingDown = false;

async function shutdown(signal) {
  if (shuttingDown) return;
  shuttingDown = true;
  app.log.info(`${signal} received — shutting down gracefully`);

  // Stop accepting new connections
  try {
    await app.close();
    app.log.info('Server closed, no new requests accepted');
  } catch (err) {
    app.log.error({ err: err.message }, 'Error closing server');
  }

  // Give in-flight pipeline work a moment to reach a checkpoint
  // (Cloud Run allows ~10s total before SIGKILL)
  setTimeout(() => {
    console.error('Shutdown grace period expired — exiting');
    process.exit(0);
  }, 8000);
}

process.on('SIGTERM', () => shutdown('SIGTERM'));
process.on('SIGINT', () => shutdown('SIGINT'));
