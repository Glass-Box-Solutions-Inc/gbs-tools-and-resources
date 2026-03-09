/**
 * GCP Cloud Logging Collector
 *
 * Collects Cloud Run deployments and error logs from GCP Cloud Logging
 * for all configured GCP projects. Handles cross-project queries with
 * graceful degradation on permission errors.
 *
 * Required IAM permissions (per monitored project):
 * - logging.logEntries.list
 * - logging.logs.list
 *
 * Service account: squeegee-intelligence@glassbox-squeegee.iam.gserviceaccount.com
 *
 * @file gcp-collector.js
 * @module intelligence/gcp-collector
 */

const { Logging } = require('@google-cloud/logging');
const { GCPLoggingError, safeExecute, getDateRange } = require('./utils');

/**
 * Create configured Cloud Logging client
 * @param {string} projectId - GCP project ID
 * @returns {Logging} - Logging client instance
 */
function createLoggingClient(projectId) {
  // Credentials loaded from volume-mounted service account key
  // Path: /etc/secrets/gcp/sa-key.json (set via GOOGLE_APPLICATION_CREDENTIALS)
  return new Logging({
    projectId,
    // Application Default Credentials (ADC) used automatically
    // Local dev: use GOOGLE_APPLICATION_CREDENTIALS env var
    // Cloud Run: uses service account attached to container
  });
}

/**
 * Query Cloud Logging with filter
 * @param {Logging} logging - Logging client
 * @param {string} filter - Cloud Logging filter string
 * @param {string} projectId - GCP project ID
 * @returns {Promise<Array>} - Array of log entries
 */
async function queryLogs(logging, filter, projectId) {
  try {
    const [entries] = await logging.getEntries({
      filter,
      pageSize: 1000, // Max entries per page
      autoPaginate: true
    });

    return entries || [];
  } catch (error) {
    const code = error.code || 'UNKNOWN';
    throw new GCPLoggingError(
      `Failed to query logs for project ${projectId}: ${error.message}`,
      code
    );
  }
}

/**
 * Collect Cloud Run deployment events for a project
 * @param {Logging} logging - Logging client
 * @param {string} projectId - GCP project ID
 * @param {string} startTime - RFC3339 timestamp
 * @param {string} endTime - RFC3339 timestamp
 * @returns {Promise<Array>} - Array of deployment events
 */
async function collectDeployments(logging, projectId, startTime, endTime) {
  const filter = `
    resource.type="cloud_run_revision"
    AND (
      protoPayload.methodName="google.cloud.run.v2.Revisions.CreateRevision"
      OR protoPayload.methodName="google.cloud.run.v1.Revisions.CreateRevision"
    )
    AND timestamp>="${startTime}"
    AND timestamp<"${endTime}"
  `.trim();

  const entries = await queryLogs(logging, filter, projectId);

  return entries.map(entry => {
    const metadata = entry.metadata || {};
    const resource = metadata.resource || {};
    const labels = resource.labels || {};
    const protoPayload = entry.data || {};

    // Extract service name and revision from resource labels or request
    const serviceName = labels.service_name ||
                       labels.configuration_name ||
                       (protoPayload.resourceName || '').split('/').pop() ||
                       'unknown';

    const revision = labels.revision_name ||
                    (protoPayload.response?.name || '').split('/').pop() ||
                    'unknown';

    // Determine deployment status from response
    const status = protoPayload.response?.status?.conditions?.[0]?.status === 'True'
      ? 'success'
      : (protoPayload.status?.code === 0 ? 'success' : 'failed');

    return {
      project: projectId,
      service: serviceName,
      revision,
      status,
      timestamp: metadata.timestamp || entry.timestamp
    };
  });
}

/**
 * Collect error logs for a project
 * @param {Logging} logging - Logging client
 * @param {string} projectId - GCP project ID
 * @param {string} startTime - RFC3339 timestamp
 * @param {string} endTime - RFC3339 timestamp
 * @returns {Promise<Array>} - Array of error events
 */
async function collectErrors(logging, projectId, startTime, endTime) {
  const filter = `
    resource.type="cloud_run_revision"
    AND severity>="ERROR"
    AND timestamp>="${startTime}"
    AND timestamp<"${endTime}"
  `.trim();

  const entries = await queryLogs(logging, filter, projectId);

  return entries.map(entry => {
    const metadata = entry.metadata || {};
    const resource = metadata.resource || {};
    const labels = resource.labels || {};

    const serviceName = labels.service_name ||
                       labels.configuration_name ||
                       'unknown';

    return {
      project: projectId,
      service: serviceName,
      severity: metadata.severity || 'ERROR',
      message: typeof entry.data === 'string'
        ? entry.data
        : (entry.data?.message || JSON.stringify(entry.data).substring(0, 200)),
      timestamp: metadata.timestamp || entry.timestamp
    };
  });
}

/**
 * Collect all logs for a single GCP project
 * @param {string} projectId - GCP project ID
 * @param {string} startTime - RFC3339 timestamp
 * @param {string} endTime - RFC3339 timestamp
 * @returns {Promise<Object>} - { deployments: [], errors: [] }
 */
async function collectProject(projectId, startTime, endTime) {
  console.log(`Collecting GCP logs for project: ${projectId}`);

  const logging = createLoggingClient(projectId);

  // Collect deployments and errors in parallel
  const [deployments, errors] = await Promise.all([
    safeExecute(
      () => collectDeployments(logging, projectId, startTime, endTime),
      [],
      `${projectId}/deployments`
    ),
    safeExecute(
      () => collectErrors(logging, projectId, startTime, endTime),
      [],
      `${projectId}/errors`
    )
  ]);

  return { deployments, errors };
}

/**
 * Collect GCP Cloud Logging activity for all configured projects
 *
 * @param {Date|string} date - Date to collect logs for (Date object or YYYY-MM-DD string)
 * @param {Object} config - Intelligence configuration
 * @param {string[]} config.gcp_projects - Array of GCP project IDs to monitor
 * @returns {Promise<Object>} - GCP activity data
 *
 * @example
 * const data = await collect(new Date('2026-03-03'), config);
 * // Returns:
 * // {
 * //   deployments: [...],
 * //   errors: [...],
 * //   summary: { total_deployments: 5, total_errors: 2, projects_monitored: 6 },
 * //   projects_failed: [{ project: 'proj-id', error: 'PERMISSION_DENIED' }]
 * // }
 */
async function collect(date, config) {
  // Convert date to string if Date object
  const dateStr = date instanceof Date
    ? `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
    : date;

  const { start, end } = getDateRange(dateStr);

  console.log(`Starting GCP collection for ${dateStr} across ${config.gcp_projects.length} projects`);

  const startCollectionTime = Date.now();
  const allDeployments = [];
  const allErrors = [];
  const projectsFailed = [];

  // Collect from each project sequentially (avoid overwhelming API)
  for (const projectId of config.gcp_projects) {
    try {
      const { deployments, errors } = await collectProject(projectId, start, end);
      allDeployments.push(...deployments);
      allErrors.push(...errors);
    } catch (error) {
      console.error(`Failed to collect logs for project ${projectId}:`, error.message);
      projectsFailed.push({
        project: projectId,
        error: error.code || error.message
      });
      // Continue with other projects
    }
  }

  // Calculate summary
  const summary = {
    total_deployments: allDeployments.length,
    total_errors: allErrors.length,
    projects_monitored: config.gcp_projects.length - projectsFailed.length
  };

  const duration = Date.now() - startCollectionTime;
  console.log(`GCP collection complete in ${duration}ms`, {
    projects_succeeded: summary.projects_monitored,
    projects_failed: projectsFailed.length,
    total_deployments: summary.total_deployments,
    total_errors: summary.total_errors
  });

  return {
    deployments: allDeployments,
    errors: allErrors,
    summary,
    ...(projectsFailed.length > 0 ? { projects_failed: projectsFailed } : {})
  };
}

module.exports = {
  collect
};
