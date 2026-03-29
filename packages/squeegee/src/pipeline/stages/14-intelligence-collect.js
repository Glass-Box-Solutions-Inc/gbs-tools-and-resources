/**
 * Stage 14: Intelligence Collection
 *
 * Collects daily intelligence data from GitHub, GCP, and dev station.
 * Runs in parallel for optimal performance.
 *
 * @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
 */

const githubCollector = require('../../../intelligence/github-collector');
const gcpCollector = require('../../../intelligence/gcp-collector');
const stationCollector = require('../../../intelligence/station-collector');
const { log } = require('../utils');

/**
 * Run intelligence collection stage
 * @param {Object} config - Pipeline configuration
 * @param {Object} context - Pipeline context (contains date)
 * @returns {Promise<Object>} - Stage result
 */
async function run(config, context = {}) {
  log('Stage 14: Collecting intelligence data...', 'info');

  const date = context.date || new Date();

  try {
    // Collect from all sources in parallel
    const [githubData, gcpData, stationData] = await Promise.all([
      githubCollector.collect(date, config),
      gcpCollector.collect(date, config),
      stationCollector.collect(date, config)
    ]);

    // Store in context for next stages
    context.intelligence = {
      github: githubData,
      gcp: gcpData,
      station: stationData
    };

    // Calculate summary metrics
    const metrics = {
      repos_active: Object.keys(githubData.repos || {}).length,
      total_commits: githubData.summary?.total_commits || 0,
      total_prs: githubData.summary?.total_prs || 0,
      deployments: gcpData.deployments?.length || 0,
      errors: gcpData.errors?.length || 0,
      sessions: stationData.summary?.total_sessions || 0
    };

    context.metrics = metrics;

    log(
      `Collected: ${metrics.repos_active} repos, ${metrics.total_commits} commits, ` +
      `${metrics.deployments} deployments, ${metrics.sessions} dev sessions`,
      'success'
    );

    return {
      status: 'success',
      summary: `Collected data from ${metrics.repos_active} repos, ${metrics.deployments} deployments, ${metrics.sessions} dev sessions`,
      metrics
    };
  } catch (error) {
    log(`Collection failed: ${error.message}`, 'error');
    return {
      status: 'failed',
      error: error.message,
      summary: 'Intelligence collection failed'
    };
  }
}

module.exports = { run };
