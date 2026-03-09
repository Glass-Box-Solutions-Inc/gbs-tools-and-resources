/**
 * Morning Run - Daily Intelligence Pipeline Orchestrator
 *
 * Orchestrates the daily intelligence collection, synthesis, and publishing pipeline:
 * 1. Collect data from GitHub, GCP, and station activity
 * 2. Synthesize briefing using Gemini 2.5 Flash
 * 3. Write logs to adjudica-documentation repository
 * 4. Send notifications to Slack
 *
 * @file morning-run.js
 * @module intelligence/morning-run
 *
 * @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
 */

const { collect: collectGitHub } = require('./github-collector');
const { collect: collectGCP } = require('./gcp-collector');
const { collect: collectStation } = require('./station-collector');
const { synthesize } = require('./gemini-synthesizer');
const { write: writeLog } = require('./log-writer');
const { notify: notifySlack } = require('./slack-notifier');
const { getYesterday, safeExecute, formatDate } = require('./utils');

/**
 * Pipeline stage names
 */
const STAGES = {
  COLLECT_GITHUB: 'collect-github',
  COLLECT_GCP: 'collect-gcp',
  COLLECT_STATION: 'collect-station',
  SYNTHESIZE: 'synthesize',
  WRITE_COMMITS: 'write-commits',
  WRITE_PRS: 'write-prs',
  WRITE_DEPLOYMENTS: 'write-deployments',
  WRITE_ANALYSIS: 'write-analysis',
  NOTIFY: 'notify'
};

/**
 * Pipeline execution result
 * @typedef {Object} PipelineResult
 * @property {string} date - Date of the pipeline run
 * @property {boolean} success - Overall success status
 * @property {Object} stages - Stage-by-stage results
 * @property {Object} collected - Collected data summary
 * @property {Object} written - Written log summary
 * @property {number} duration_ms - Total execution time
 * @property {string[]} errors - Array of error messages
 */

/**
 * Collect data from all sources in parallel
 * @param {string} date - YYYY-MM-DD date string
 * @param {Object} config - Intelligence configuration
 * @returns {Promise<Object>} - Collected data from all sources
 */
async function collectAll(date, config) {
  console.log(`[morning-run] Collecting data for ${date}...`);
  const startTime = Date.now();

  // Collect from all sources in parallel
  const [github, gcp, station] = await Promise.all([
    safeExecute(
      () => collectGitHub(date, config),
      { repos: {}, summary: { total_commits: 0, total_prs: 0, total_issues: 0, total_ci_runs: 0 } },
      STAGES.COLLECT_GITHUB
    ),
    safeExecute(
      () => collectGCP(date, config),
      { deployments: [], errors: [], summary: { total_deployments: 0, total_errors: 0, projects_monitored: 0 } },
      STAGES.COLLECT_GCP
    ),
    safeExecute(
      () => collectStation(date, config),
      { date, sessions: [], summary: { total_sessions: 0, active_hours: 0, projects_touched: [], by_tool: {} } },
      STAGES.COLLECT_STATION
    )
  ]);

  const duration = Date.now() - startTime;
  console.log(`[morning-run] Collection complete in ${duration}ms`);

  return {
    github,
    gcp,
    station,
    checkpoints: [], // Reserved for future checkpoint integration
    collection_duration_ms: duration
  };
}

/**
 * Write all logs to adjudica-documentation
 * @param {Object} data - Collected data
 * @param {Object} briefing - Gemini briefing
 * @param {string} date - YYYY-MM-DD date string
 * @param {Object} config - Intelligence configuration
 * @returns {Promise<Object>} - Write results
 */
async function writeAll(data, briefing, date, config) {
  console.log(`[morning-run] Writing logs for ${date}...`);
  const startTime = Date.now();
  const results = {};
  const errors = [];

  // Write commits log
  const commitsResult = await safeExecute(
    () => writeLog(data.github, 'commits', date, config),
    { success: false, error: 'Failed to write commits log' },
    STAGES.WRITE_COMMITS
  );
  results.commits = commitsResult;
  if (!commitsResult.success) {
    errors.push(`commits: ${commitsResult.error || 'unknown error'}`);
  }

  // Write PRs log
  const prsResult = await safeExecute(
    () => writeLog(data.github, 'prs', date, config),
    { success: false, error: 'Failed to write PRs log' },
    STAGES.WRITE_PRS
  );
  results.prs = prsResult;
  if (!prsResult.success) {
    errors.push(`prs: ${prsResult.error || 'unknown error'}`);
  }

  // Write deployments log
  const deploymentsResult = await safeExecute(
    () => writeLog(data.gcp, 'deployments', date, config),
    { success: false, error: 'Failed to write deployments log' },
    STAGES.WRITE_DEPLOYMENTS
  );
  results.deployments = deploymentsResult;
  if (!deploymentsResult.success) {
    errors.push(`deployments: ${deploymentsResult.error || 'unknown error'}`);
  }

  // Write analysis/briefing log
  const analysisResult = await safeExecute(
    () => writeLog(briefing, 'analysis', date, config),
    { success: false, error: 'Failed to write analysis log' },
    STAGES.WRITE_ANALYSIS
  );
  results.analysis = analysisResult;
  if (!analysisResult.success) {
    errors.push(`analysis: ${analysisResult.error || 'unknown error'}`);
  }

  const duration = Date.now() - startTime;
  console.log(`[morning-run] Writing complete in ${duration}ms`);

  return {
    results,
    errors,
    write_duration_ms: duration
  };
}

/**
 * Run the daily intelligence pipeline
 * @param {Object} [options={}] - Pipeline options
 * @param {string} [options.date] - Date to run for (defaults to yesterday)
 * @param {Object} [options.config] - Override configuration
 * @param {boolean} [options.dryRun=false] - Skip writes and notifications
 * @param {string[]} [options.skipStages=[]] - Stages to skip
 * @returns {Promise<PipelineResult>} - Pipeline execution result
 */
async function run(options = {}) {
  const startTime = Date.now();
  const date = options.date || getYesterday();
  const config = options.config || require('../config/intelligence.config.json');
  const dryRun = options.dryRun || config.intelligence?.dry_run || false;
  const skipStages = options.skipStages || [];

  console.log(`[morning-run] Starting daily intelligence pipeline for ${date}`);
  console.log(`[morning-run] Dry run: ${dryRun}`);
  if (skipStages.length > 0) {
    console.log(`[morning-run] Skipping stages: ${skipStages.join(', ')}`);
  }

  const result = {
    date,
    success: true,
    stages: {},
    collected: null,
    briefing: null,
    written: null,
    notification: null,
    duration_ms: 0,
    errors: []
  };

  try {
    // Stage 1: Collect data from all sources
    if (!skipStages.includes('collect')) {
      const collectedData = await collectAll(date, config);
      result.collected = {
        github: {
          commits: collectedData.github.summary?.total_commits || 0,
          prs: collectedData.github.summary?.total_prs || 0,
          issues: collectedData.github.summary?.total_issues || 0,
          ci_runs: collectedData.github.summary?.total_ci_runs || 0,
          repos_processed: Object.keys(collectedData.github.repos || {}).length
        },
        gcp: {
          deployments: collectedData.gcp.summary?.total_deployments || 0,
          errors: collectedData.gcp.summary?.total_errors || 0,
          projects_monitored: collectedData.gcp.summary?.projects_monitored || 0
        },
        station: {
          sessions: collectedData.station.summary?.total_sessions || 0,
          active_hours: collectedData.station.summary?.active_hours || 0,
          projects_touched: collectedData.station.summary?.projects_touched?.length || 0
        },
        duration_ms: collectedData.collection_duration_ms
      };
      result.stages.collect = { success: true, duration_ms: collectedData.collection_duration_ms };

      // Stage 2: Synthesize briefing with Gemini
      if (!skipStages.includes('synthesize')) {
        console.log(`[morning-run] Synthesizing briefing...`);
        const synthesizeStart = Date.now();

        const briefing = await safeExecute(
          () => synthesize(date, collectedData, config),
          {
            date,
            executive_summary: ['Unable to generate briefing due to an error.'],
            fallback_used: true,
            error: 'Synthesis failed'
          },
          STAGES.SYNTHESIZE
        );

        const synthesizeDuration = Date.now() - synthesizeStart;
        result.briefing = {
          generated: !briefing.fallback_used,
          model_used: briefing.model_used || 'unknown',
          token_count: briefing.token_count || null,
          fallback_used: briefing.fallback_used || false,
          duration_ms: synthesizeDuration
        };
        result.stages.synthesize = { success: !briefing.fallback_used, duration_ms: synthesizeDuration };

        // Stage 3: Write logs (skip in dry run mode)
        if (!dryRun && !skipStages.includes('write')) {
          const writeResults = await writeAll(collectedData, briefing, date, config);
          result.written = {
            commits: writeResults.results.commits?.success || false,
            prs: writeResults.results.prs?.success || false,
            deployments: writeResults.results.deployments?.success || false,
            analysis: writeResults.results.analysis?.success || false,
            duration_ms: writeResults.write_duration_ms
          };
          result.stages.write = {
            success: writeResults.errors.length === 0,
            duration_ms: writeResults.write_duration_ms
          };
          if (writeResults.errors.length > 0) {
            result.errors.push(...writeResults.errors.map(e => `write: ${e}`));
          }

          // Stage 4: Notify Slack (skip in dry run mode)
          if (!skipStages.includes('notify')) {
            console.log(`[morning-run] Sending notifications...`);
            const notifyStart = Date.now();

            const notifyResult = await safeExecute(
              () => notifySlack(briefing, date, config),
              { success: false, error: 'Notification failed' },
              STAGES.NOTIFY
            );

            const notifyDuration = Date.now() - notifyStart;
            result.notification = {
              success: notifyResult.success,
              skipped: notifyResult.skipped || false,
              channel: notifyResult.channel,
              error: notifyResult.error,
              duration_ms: notifyDuration
            };
            result.stages.notify = { success: notifyResult.success, duration_ms: notifyDuration };

            if (!notifyResult.success && !notifyResult.skipped) {
              result.errors.push(`notify: ${notifyResult.error || 'unknown error'}`);
            }
          }
        } else if (dryRun) {
          console.log(`[morning-run] Dry run - skipping writes and notifications`);
          result.stages.write = { success: true, skipped: true };
          result.stages.notify = { success: true, skipped: true };
        }
      }
    }

    // Determine overall success
    result.success = result.errors.length === 0;

  } catch (error) {
    console.error(`[morning-run] Pipeline failed:`, error.message);
    result.success = false;
    result.errors.push(`pipeline: ${error.message}`);
  }

  result.duration_ms = Date.now() - startTime;

  // Log summary
  console.log(`[morning-run] Pipeline complete in ${result.duration_ms}ms`);
  console.log(`[morning-run] Success: ${result.success}`);
  if (result.errors.length > 0) {
    console.log(`[morning-run] Errors: ${result.errors.join('; ')}`);
  }

  return result;
}

/**
 * Run pipeline for multiple dates (backfill)
 * @param {string[]} dates - Array of YYYY-MM-DD date strings
 * @param {Object} [options={}] - Pipeline options
 * @returns {Promise<Object>} - Aggregated results
 */
async function runBatch(dates, options = {}) {
  console.log(`[morning-run] Starting batch pipeline for ${dates.length} dates`);
  const startTime = Date.now();

  const results = {
    dates_processed: 0,
    dates_succeeded: 0,
    dates_failed: 0,
    by_date: {},
    errors: [],
    duration_ms: 0
  };

  // Process dates sequentially to avoid overwhelming APIs
  for (const date of dates) {
    try {
      const dateResult = await run({ ...options, date });
      results.by_date[date] = dateResult;
      results.dates_processed++;

      if (dateResult.success) {
        results.dates_succeeded++;
      } else {
        results.dates_failed++;
        results.errors.push(...dateResult.errors.map(e => `${date}: ${e}`));
      }
    } catch (error) {
      console.error(`[morning-run] Failed to process ${date}:`, error.message);
      results.dates_processed++;
      results.dates_failed++;
      results.errors.push(`${date}: ${error.message}`);
      results.by_date[date] = { success: false, error: error.message };
    }
  }

  results.duration_ms = Date.now() - startTime;
  console.log(`[morning-run] Batch complete: ${results.dates_succeeded}/${dates.length} succeeded in ${results.duration_ms}ms`);

  return results;
}

/**
 * CLI entry point
 * Parses command line arguments and runs pipeline
 */
async function main() {
  const args = process.argv.slice(2);
  const options = {};

  // Parse arguments
  for (let i = 0; i < args.length; i++) {
    const arg = args[i];

    if (arg === '--date' && args[i + 1]) {
      options.date = args[++i];
    } else if (arg === '--dry-run') {
      options.dryRun = true;
    } else if (arg === '--skip' && args[i + 1]) {
      options.skipStages = args[++i].split(',');
    } else if (arg === '--help' || arg === '-h') {
      console.log(`
Squeegee Intelligence Pipeline

Usage: node morning-run.js [options]

Options:
  --date YYYY-MM-DD   Date to run pipeline for (default: yesterday)
  --dry-run           Skip writes and notifications
  --skip STAGES       Comma-separated stages to skip (collect,synthesize,write,notify)
  --help, -h          Show this help message

Examples:
  node morning-run.js                           # Run for yesterday
  node morning-run.js --date 2026-03-01         # Run for specific date
  node morning-run.js --dry-run                 # Test without writing
  node morning-run.js --skip notify             # Skip Slack notification
      `.trim());
      process.exit(0);
    }
  }

  try {
    const result = await run(options);
    console.log(JSON.stringify(result, null, 2));
    process.exit(result.success ? 0 : 1);
  } catch (error) {
    console.error('Pipeline failed:', error.message);
    process.exit(1);
  }
}

// Export for module usage
module.exports = {
  run,
  runBatch,
  collectAll,
  writeAll,
  STAGES
};

// Run if executed directly
if (require.main === module) {
  main();
}
