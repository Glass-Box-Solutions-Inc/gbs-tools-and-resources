/**
 * Intelligence API Routes
 *
 * REST API endpoints for Squeegee's intelligence system (stages 14-20).
 * Provides manual triggers for intelligence collection, synthesis, audits,
 * research, and notifications.
 *
 * All endpoints require bearer token authentication (Cloud Run OIDC).
 *
 * @file src/api/intelligence.js
 * @module api/intelligence
 * @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
 */

'use strict';

const path = require('path');
const fs = require('fs').promises;

// Import intelligence modules
const githubCollector = require('../../intelligence/github-collector');
const gcpCollector = require('../../intelligence/gcp-collector');
const stationMonitor = require('../../intelligence/station-monitor');
const logWriter = require('../../intelligence/log-writer');
const geminiSynthesizer = require('../../intelligence/gemini-synthesizer');
const claudeMdAuditor = require('../../intelligence/claude-md-auditor');
// const docQualityAuditor = require('../../intelligence/doc-quality-auditor'); // TODO: Implement
// const webResearcher = require('../../intelligence/web-researcher'); // TODO: Implement
const slackNotifier = require('../../intelligence/slack-notifier');

// Import utilities
const { formatDate } = require('../../intelligence/utils');

/**
 * Load intelligence configuration
 * Reads from config/intelligence.config.json and merges with env overrides
 * @returns {Promise<Object>} - Complete intelligence configuration
 */
async function loadIntelligenceConfig() {
  const configPath = path.join(process.cwd(), 'config', 'intelligence.config.json');

  try {
    const configData = await fs.readFile(configPath, 'utf-8');
    const config = JSON.parse(configData);

    // Apply environment variable overrides
    if (process.env.INTELLIGENCE_ENABLED !== undefined) {
      config.intelligence.enabled = process.env.INTELLIGENCE_ENABLED === 'true';
    }

    if (process.env.INTELLIGENCE_DRY_RUN !== undefined) {
      config.intelligence.dry_run = process.env.INTELLIGENCE_DRY_RUN === 'true';
    }

    if (process.env.GEMINI_MODEL) {
      config.intelligence.gemini.model = process.env.GEMINI_MODEL;
    }

    if (process.env.GEMINI_TEMPERATURE) {
      config.intelligence.gemini.temperature = parseFloat(process.env.GEMINI_TEMPERATURE);
    }

    // Load API keys from environment (volume-mounted secrets)
    if (process.env.GOOGLE_AI_API_KEY) {
      const keyPath = process.env.GOOGLE_AI_API_KEY;
      try {
        config.intelligence.gemini.apiKey = (await fs.readFile(keyPath, 'utf-8')).trim();
      } catch (error) {
        console.warn(`Failed to load Gemini API key from ${keyPath}:`, error.message);
      }
    }

    if (process.env.GITHUB_TOKEN) {
      const tokenPath = process.env.GITHUB_TOKEN;
      try {
        config.github_token = (await fs.readFile(tokenPath, 'utf-8')).trim();
      } catch (error) {
        console.warn(`Failed to load GitHub token from ${tokenPath}:`, error.message);
      }
    }

    // Load Slack webhook URL from environment or volume-mounted secret
    if (process.env.SLACK_WEBHOOK_URL) {
      const slackPath = process.env.SLACK_WEBHOOK_URL;
      try {
        const url = (await fs.readFile(slackPath, 'utf-8')).trim();
        if (config.notifications?.slack) {
          config.notifications.slack.webhook_url = url;
        }
      } catch {
        // Not a file path — treat as raw URL
        if (slackPath.startsWith('https://')) {
          if (config.notifications?.slack) {
            config.notifications.slack.webhook_url = slackPath;
          }
        } else {
          console.warn(`Failed to load Slack webhook URL from ${slackPath}`);
        }
      }
    }

    return config;
  } catch (error) {
    console.error('Failed to load intelligence config:', error.message);
    throw new Error(`Intelligence configuration not available: ${error.message}`);
  }
}

/**
 * Helper to format date parameter
 * @param {string|undefined} dateParam - Date string (YYYY-MM-DD) or undefined
 * @returns {Date} - Parsed date or yesterday
 */
function parseDateParam(dateParam) {
  if (dateParam) {
    const parsed = new Date(dateParam);
    if (isNaN(parsed.getTime())) {
      throw new Error('Invalid date format. Use YYYY-MM-DD');
    }
    return parsed;
  }

  // Default to yesterday
  const yesterday = new Date();
  yesterday.setDate(yesterday.getDate() - 1);
  yesterday.setHours(0, 0, 0, 0);
  return yesterday;
}

/**
 * Check if today is Sunday
 * @returns {boolean}
 */
function isSunday() {
  return new Date().getDay() === 0;
}

/**
 * Check if today is the first day of the month
 * @returns {boolean}
 */
function isFirstOfMonth() {
  return new Date().getDate() === 1;
}

/**
 * Check if today is the first day of the quarter
 * @returns {boolean}
 */
function isFirstOfQuarter() {
  const today = new Date();
  const month = today.getMonth() + 1; // 1-12
  const day = today.getDate();
  return day === 1 && [1, 4, 7, 10].includes(month);
}

/**
 * Register intelligence routes
 * @param {FastifyInstance} fastify - Fastify instance
 * @param {Object} options - Route options
 */
async function routes(fastify, options) {

  // ─── POST /api/intelligence/run ────────────────────────────────────────────

  /**
   * Trigger full intelligence run (stages 14-20)
   *
   * Example:
   *   curl -X POST https://squeegee.run.app/api/intelligence/run \
   *     -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
   *     -H "Content-Type: application/json" \
   *     -d '{"date": "2026-03-13", "force": {"claudeMdAudit": true}}'
   */
  fastify.post('/run', {
    schema: {
      body: {
        type: 'object',
        properties: {
          date: { type: 'string', pattern: '^\\d{4}-\\d{2}-\\d{2}$' },
          force: {
            type: 'object',
            properties: {
              claudeMdAudit: { type: 'boolean' },
              docQualityAudit: { type: 'boolean' },
              research: { type: 'boolean' }
            }
          }
        }
      }
    }
  }, async (request, reply) => {
    const startTime = Date.now();

    try {
      const config = await loadIntelligenceConfig();

      if (!config.intelligence.enabled) {
        return reply.code(503).send({
          status: 'disabled',
          message: 'Intelligence system is disabled in configuration'
        });
      }

      const date = parseDateParam(request.body?.date);
      const dateStr = formatDate(date);

      const context = {
        date,
        dateStr,
        config,
        forceClaudeMdAudit: request.body?.force?.claudeMdAudit || false,
        forceDocQualityAudit: request.body?.force?.docQualityAudit || false,
        forceResearch: request.body?.force?.research || false
      };

      const stages = [];

      // Stage 14: Collect
      stages.push(await runStage('14-intelligence-collect', async () => {
        const github = await githubCollector.collect(dateStr, config);
        const gcp = await gcpCollector.collect(dateStr, config);
        const station = await stationMonitor.collect(config);
        const checkpoints = []; // TODO: Load from checkpoint queue

        context.intelligence = { github, gcp, station, checkpoints };

        return {
          status: 'success',
          summary: `Collected data: ${github.summary.total_commits} commits, ${gcp.summary.total_deployments} deployments`
        };
      }));

      // Stage 15: Synthesize
      stages.push(await runStage('15-intelligence-synthesize', async () => {
        const briefing = await geminiSynthesizer.synthesize(
          date,
          context.intelligence,
          config
        );

        context.briefing = briefing;

        return {
          status: 'success',
          summary: `Generated briefing (${briefing.fallback_used ? 'fallback' : 'Gemini'})`
        };
      }));

      // Stage 16: Write
      if (!config.intelligence.dry_run) {
        stages.push(await runStage('16-intelligence-write', async () => {
          await logWriter.writeAll(
            context.intelligence,
            context.briefing,
            dateStr,
            config
          );

          return {
            status: 'success',
            summary: 'Wrote 6 log files to adjudica-documentation'
          };
        }));
      } else {
        stages.push({
          stage: 16,
          name: 'intelligence-write',
          status: 'skipped',
          summary: 'Dry run mode enabled'
        });
      }

      // Stage 17: CLAUDE.md Audit (Sunday or forced)
      if (isSunday() || context.forceClaudeMdAudit) {
        stages.push(await runStage('17-intelligence-audit-claude', async () => {
          const results = await claudeMdAuditor.auditAll(config);
          const needsPR = results.filter(r => r.needs_pr).length;

          return {
            status: 'success',
            summary: `Audited ${results.length} repos, ${needsPR} need PRs`
          };
        }));
      } else {
        stages.push({
          stage: 17,
          name: 'intelligence-audit-claude',
          status: 'skipped',
          summary: 'Not Sunday (weekly audit)'
        });
      }

      // Stage 18: Doc Quality Audit (1st of month or forced)
      if (isFirstOfMonth() || context.forceDocQualityAudit) {
        stages.push({
          stage: 18,
          name: 'intelligence-audit-quality',
          status: 'skipped',
          summary: 'Not implemented yet'
        });
      } else {
        stages.push({
          stage: 18,
          name: 'intelligence-audit-quality',
          status: 'skipped',
          summary: 'Not 1st of month (monthly audit)'
        });
      }

      // Stage 19: Web Research (quarterly or forced)
      if (isFirstOfQuarter() || context.forceResearch) {
        stages.push({
          stage: 19,
          name: 'intelligence-research',
          status: 'skipped',
          summary: 'Not implemented yet'
        });
      } else {
        stages.push({
          stage: 19,
          name: 'intelligence-research',
          status: 'skipped',
          summary: 'Not 1st of quarter (quarterly research)'
        });
      }

      // Stage 20: Notify
      stages.push(await runStage('20-intelligence-notify', async () => {
        const result = await slackNotifier.notify(context.briefing, date, config);

        if (result.skipped) {
          return { status: 'skipped', summary: 'Slack notifications disabled or no webhook configured' };
        }
        if (result.success) {
          return { status: 'success', summary: `Sent briefing to ${result.channel}` };
        }
        return { status: 'failed', summary: result.error || 'Notification failed' };
      }));

      const duration = Date.now() - startTime;
      const overallStatus = stages.every(s => s.status === 'success' || s.status === 'skipped') ? 'success' : 'partial';

      return reply.send({
        status: overallStatus,
        date: dateStr,
        stages,
        duration_ms: duration
      });

    } catch (error) {
      fastify.log.error({ error: error.message }, 'Intelligence run failed');
      return reply.code(500).send({
        status: 'failed',
        error: error.message
      });
    }
  });

  // ─── POST /api/intelligence/collect ───────────────────────────────────────

  /**
   * Run only data collection (stage 14)
   *
   * Example:
   *   curl -X POST https://squeegee.run.app/api/intelligence/collect \
   *     -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
   *     -d '{"date": "2026-03-13"}'
   */
  fastify.post('/collect', async (request, reply) => {
    try {
      const config = await loadIntelligenceConfig();
      const date = parseDateParam(request.body?.date);
      const dateStr = formatDate(date);

      const github = await githubCollector.collect(dateStr, config);
      const gcp = await gcpCollector.collect(dateStr, config);
      const station = await stationMonitor.collect(config);
      const checkpoints = []; // TODO: Load from checkpoint queue

      const metrics = {
        repos_active: Object.keys(github.repos).length,
        total_commits: github.summary.total_commits,
        total_prs: github.summary.total_prs,
        deployments: gcp.summary.total_deployments,
        errors: gcp.summary.total_errors,
        sessions: station.claude_code_sessions?.length || 0
      };

      return reply.send({
        status: 'success',
        date: dateStr,
        data: { github, gcp, station, checkpoints },
        metrics
      });

    } catch (error) {
      fastify.log.error({ error: error.message }, 'Collection failed');
      return reply.code(500).send({
        status: 'failed',
        error: error.message
      });
    }
  });

  // ─── POST /api/intelligence/synthesize ────────────────────────────────────

  /**
   * Generate briefing from collected data
   *
   * Example:
   *   curl -X POST https://squeegee.run.app/api/intelligence/synthesize \
   *     -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
   *     -d @collected-data.json
   */
  fastify.post('/synthesize', {
    schema: {
      body: {
        type: 'object',
        required: ['date', 'data'],
        properties: {
          date: { type: 'string', pattern: '^\\d{4}-\\d{2}-\\d{2}$' },
          data: { type: 'object' }
        }
      }
    }
  }, async (request, reply) => {
    try {
      const config = await loadIntelligenceConfig();
      const { date, data } = request.body;

      const parsedDate = new Date(date);
      const briefing = await geminiSynthesizer.synthesize(parsedDate, data, config);

      return reply.send({
        status: 'success',
        briefing
      });

    } catch (error) {
      fastify.log.error({ error: error.message }, 'Synthesis failed');
      return reply.code(500).send({
        status: 'failed',
        error: error.message
      });
    }
  });

  // ─── POST /api/intelligence/audit-claude-md ───────────────────────────────

  /**
   * Run CLAUDE.md compliance audit
   *
   * Example:
   *   curl -X POST https://squeegee.run.app/api/intelligence/audit-claude-md \
   *     -H "Authorization: Bearer $(gcloud auth print-identity-token)"
   */
  fastify.post('/audit-claude-md', async (request, reply) => {
    try {
      const config = await loadIntelligenceConfig();
      const date = formatDate(new Date());

      const results = await claudeMdAuditor.auditAll(config);

      const summary = {
        average_score: results.reduce((sum, r) => sum + r.score, 0) / results.length,
        excellent: results.filter(r => r.score >= 13).length,
        good: results.filter(r => r.score >= 10 && r.score < 13).length,
        needs_work: results.filter(r => r.score >= 7 && r.score < 10).length,
        critical: results.filter(r => r.score < 7).length
      };

      return reply.send({
        status: 'success',
        report: {
          date,
          repos_audited: results.length,
          summary,
          details: results
        }
      });

    } catch (error) {
      fastify.log.error({ error: error.message }, 'CLAUDE.md audit failed');
      return reply.code(500).send({
        status: 'failed',
        error: error.message
      });
    }
  });

  // ─── POST /api/intelligence/audit-doc-quality ─────────────────────────────

  /**
   * Run documentation quality audit (10-point rubric)
   *
   * Example:
   *   curl -X POST https://squeegee.run.app/api/intelligence/audit-doc-quality \
   *     -H "Authorization: Bearer $(gcloud auth print-identity-token)"
   */
  fastify.post('/audit-doc-quality', async (request, reply) => {
    return reply.code(501).send({
      status: 'not_implemented',
      message: 'Doc quality auditor not yet implemented'
    });
  });

  // ─── POST /api/intelligence/research ──────────────────────────────────────

  /**
   * Run web research on a documentation topic
   *
   * Example:
   *   curl -X POST https://squeegee.run.app/api/intelligence/research \
   *     -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
   *     -d '{"topic": "documentation-standards"}'
   */
  fastify.post('/research', {
    schema: {
      body: {
        type: 'object',
        required: ['topic'],
        properties: {
          topic: { type: 'string' },
          date: { type: 'string', pattern: '^\\d{4}-\\d{2}-\\d{2}$' }
        }
      }
    }
  }, async (request, reply) => {
    return reply.code(501).send({
      status: 'not_implemented',
      message: 'Web researcher not yet implemented'
    });
  });

  // ─── POST /api/intelligence/notify ────────────────────────────────────────

  /**
   * Send briefing to Slack (manual trigger)
   *
   * Example:
   *   curl -X POST https://squeegee.run.app/api/intelligence/notify \
   *     -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
   *     -d @briefing.json
   */
  fastify.post('/notify', {
    schema: {
      body: {
        type: 'object',
        required: ['briefing', 'date'],
        properties: {
          briefing: { type: 'object' },
          date: { type: 'string', pattern: '^\\d{4}-\\d{2}-\\d{2}$' }
        }
      }
    }
  }, async (request, reply) => {
    try {
      const config = await loadIntelligenceConfig();
      const { briefing, date } = request.body;

      const result = await slackNotifier.notify(briefing, date, config);

      if (result.skipped) {
        return reply.send({
          status: 'skipped',
          channel: result.channel,
          message: 'Slack notifications disabled or no webhook configured'
        });
      }

      if (result.success) {
        return reply.send({
          status: 'success',
          channel: result.channel,
          message_ts: result.message_ts
        });
      }

      return reply.code(502).send({
        status: 'failed',
        error: result.error
      });
    } catch (error) {
      fastify.log.error({ error: error.message }, 'Slack notification failed');
      return reply.code(500).send({
        status: 'failed',
        error: error.message
      });
    }
  });

  // ─── GET /api/intelligence/status ─────────────────────────────────────────

  /**
   * Get intelligence system status
   *
   * Example:
   *   curl https://squeegee.run.app/api/intelligence/status \
   *     -H "Authorization: Bearer $(gcloud auth print-identity-token)"
   */
  fastify.get('/status', async (request, reply) => {
    try {
      const config = await loadIntelligenceConfig();

      // Check module health
      const modules = {
        'github-collector': 'ok',
        'gcp-collector': 'ok',
        'station-monitor': 'ok',
        'log-writer': 'ok',
        'gemini-synthesizer': config.intelligence.gemini?.apiKey ? 'ok' : 'missing_api_key',
        'claude-md-auditor': 'ok',
        'doc-quality-auditor': 'not_implemented',
        'web-researcher': 'not_implemented',
        'slack-notifier': 'ok'
      };

      // Try to read last run summary
      let lastRun = null;
      const stateFile = '/tmp/squeegee-intelligence-state.json';
      try {
        const stateData = await fs.readFile(stateFile, 'utf-8');
        const state = JSON.parse(stateData);
        lastRun = state.last_run;
      } catch {
        // No state file yet
      }

      // Calculate next scheduled runs
      const now = new Date();
      const tomorrow = new Date(now);
      tomorrow.setDate(tomorrow.getDate() + 1);
      tomorrow.setHours(7, 0, 0, 0);

      const nextSunday = new Date(now);
      nextSunday.setDate(nextSunday.getDate() + ((7 - nextSunday.getDay()) % 7 || 7));
      nextSunday.setHours(7, 0, 0, 0);

      const nextMonth = new Date(now.getFullYear(), now.getMonth() + 1, 1, 7, 0, 0, 0);

      const currentMonth = now.getMonth();
      const nextQuarterMonth = [1, 4, 7, 10].find(m => m > currentMonth + 1) || 1;
      const nextQuarterYear = nextQuarterMonth === 1 ? now.getFullYear() + 1 : now.getFullYear();
      const nextQuarter = new Date(nextQuarterYear, nextQuarterMonth - 1, 1, 7, 0, 0, 0);

      return reply.send({
        status: 'healthy',
        enabled: config.intelligence.enabled,
        dry_run: config.intelligence.dry_run,
        modules,
        last_run: lastRun,
        next_scheduled: {
          daily: tomorrow.toISOString(),
          weekly_audit: nextSunday.toISOString(),
          monthly_audit: nextMonth.toISOString(),
          quarterly_research: nextQuarter.toISOString()
        }
      });

    } catch (error) {
      fastify.log.error({ error: error.message }, 'Status check failed');
      return reply.code(500).send({
        status: 'error',
        error: error.message
      });
    }
  });
}

// ─── Helper Functions ──────────────────────────────────────────────────────

/**
 * Run a stage with error handling
 * @param {string} name - Stage name
 * @param {Function} fn - Stage function
 * @returns {Promise<Object>} - Stage result
 */
async function runStage(name, fn) {
  const stageNumber = parseInt(name.split('-')[0]);
  const stageName = name.substring(3); // Remove "14-" prefix

  try {
    const result = await fn();
    return {
      stage: stageNumber,
      name: stageName,
      ...result
    };
  } catch (error) {
    console.error(`Stage ${name} failed:`, error.message);
    return {
      stage: stageNumber,
      name: stageName,
      status: 'failed',
      error: error.message
    };
  }
}

module.exports = routes;
