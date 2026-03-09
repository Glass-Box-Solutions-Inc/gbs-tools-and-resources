/**
 * Stage 16: Intelligence Log Writing
 *
 * Writes intelligence logs to adjudica-documentation via GitHub API.
 * Logs are organized by type: commits, prs, deployments, agents, analysis.
 *
 * @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
 */

const logWriter = require('../../../intelligence/log-writer');
const { log } = require('../utils');

/**
 * Run intelligence log writing stage
 * @param {Object} config - Pipeline configuration
 * @param {Object} context - Pipeline context (contains intelligence and briefing)
 * @returns {Promise<Object>} - Stage result
 */
async function run(config, context = {}) {
  log('Stage 16: Writing intelligence logs...', 'info');

  const { date = new Date(), intelligence, briefing } = context;

  if (!intelligence || !briefing) {
    log('Missing intelligence or briefing data - run collection and synthesis first', 'error');
    return {
      status: 'failed',
      error: 'Missing required data',
      summary: 'Cannot write logs without collection and synthesis data'
    };
  }

  try {
    // Write all log types in parallel
    const writePromises = [
      logWriter.write(intelligence.github, 'commits', date, config),
      logWriter.write(intelligence.github, 'prs', date, config),
      logWriter.write(intelligence.gcp, 'deployments', date, config),
      logWriter.write(intelligence.station, 'agents', date, config),
      logWriter.write(briefing, 'analysis', date, config)
    ];

    const results = await Promise.all(writePromises);
    const successful = results.filter(r => r.success);
    const failed = results.filter(r => !r.success);

    // Log detailed results
    if (successful.length > 0) {
      log(`Successfully wrote ${successful.length} log files:`, 'success');
      for (const result of successful) {
        console.log(`  ✓ ${result.file_path}`);
      }
    }

    if (failed.length > 0) {
      log(`Failed to write ${failed.length} log files:`, 'error');
      for (const result of failed) {
        console.log(`  ✗ ${result.file_path}: ${result.error}`);
      }
    }

    // Store results in context
    context.logsWritten = {
      successful: successful.map(r => r.file_path),
      failed: failed.map(r => ({ path: r.file_path, error: r.error }))
    };

    return {
      status: failed.length === 0 ? 'success' : 'partial',
      summary: `Wrote ${successful.length}/${results.length} log files`,
      logs_written: successful.length,
      logs_failed: failed.length,
      details: {
        successful: successful.map(r => r.file_path),
        failed: failed.map(r => r.file_path)
      }
    };
  } catch (error) {
    log(`Log writing failed: ${error.message}`, 'error');
    return {
      status: 'failed',
      error: error.message,
      summary: 'Intelligence log writing failed'
    };
  }
}

module.exports = { run };
