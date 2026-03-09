/**
 * GCS Station Activity Collector
 *
 * Collects development station activity (Claude Code sessions, Cursor, VS Code)
 * from GCS bucket. Reads JSON log files stored daily by workstation monitors.
 * Designed for graceful degradation - missing files return empty data structures.
 *
 * GCS Bucket: configured via config.storage.gcs_bucket
 * File Pattern: {prefix}YYYY-MM-DD.json
 *
 * Required IAM:
 *   - roles/storage.objectViewer on the bucket
 *
 * @file station-collector.js
 * @module intelligence/station-collector
 *
 * @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
 */

const { Storage } = require('@google-cloud/storage');
const path = require('path');
const { safeExecute, formatDate, GCSStorageError } = require('./utils');

/**
 * Sanitize terminal command - remove sensitive arguments
 * @param {string} command - Raw command string
 * @returns {string} - Sanitized command
 */
function sanitizeCommand(command) {
  if (!command) return '';

  return command
    .replace(/--token[= ][\w-]+/gi, '--token=***')
    .replace(/--password[= ][\w-]+/gi, '--password=***')
    .replace(/--secret[= ][\w-]+/gi, '--secret=***')
    .replace(/--api-key[= ][\w-]+/gi, '--api-key=***')
    .replace(/Bearer [\w.-]+/gi, 'Bearer ***')
    .replace(/ghp_[\w]+/gi, 'ghp_***')
    .replace(/gcloud.*--access-token[= ][\w-]+/gi, 'gcloud ... --access-token=***');
}

/**
 * Sanitize file path - remove sensitive paths
 * @param {string} filePath - Raw file path
 * @returns {string} - Sanitized path
 */
function sanitizePath(filePath) {
  if (!filePath) return '';

  // Redact paths containing secrets
  if (filePath.includes('/secrets/') ||
      filePath.includes('/.env') ||
      filePath.includes('/credentials/') ||
      filePath.includes('/service-account')) {
    return '[REDACTED]';
  }

  return filePath;
}

/**
 * Process session data - sanitize and calculate durations
 * @param {Array} sessions - Raw session data
 * @returns {Array} - Processed sessions
 */
function processSessions(sessions) {
  if (!Array.isArray(sessions)) return [];

  return sessions.map(session => {
    const start = new Date(session.start);
    const end = session.end ? new Date(session.end) : new Date();
    const durationMinutes = Math.round((end - start) / (1000 * 60));

    return {
      type: session.type || 'unknown',
      project: sanitizePath(session.project || ''),
      start: session.start,
      end: session.end || null,
      duration_minutes: Math.max(0, durationMinutes), // Guard against negative
      commands: session.commands || 0,
      files_edited: session.files_edited || 0,
      // Include agent info if available
      ...(session.agent && { agent: session.agent }),
      ...(session.model && { model: session.model })
    };
  });
}

/**
 * Calculate summary statistics from sessions
 * @param {Array} sessions - Processed session data
 * @returns {Object} - Summary statistics
 */
function calculateSummary(sessions) {
  const summary = {
    total_sessions: sessions.length,
    active_hours: 0,
    projects_touched: [],
    by_tool: {},
    total_commands: 0,
    total_files_edited: 0
  };

  // Calculate totals
  for (const session of sessions) {
    summary.active_hours += session.duration_minutes / 60;
    summary.total_commands += session.commands || 0;
    summary.total_files_edited += session.files_edited || 0;
  }

  // Round to 1 decimal place
  summary.active_hours = Math.round(summary.active_hours * 10) / 10;

  // Extract unique projects (filter out redacted paths)
  const projectSet = new Set();
  for (const session of sessions) {
    if (session.project && session.project !== '[REDACTED]') {
      // Extract project name from path
      const projectName = path.basename(session.project);
      if (projectName) {
        projectSet.add(projectName);
      }
    }
  }
  summary.projects_touched = Array.from(projectSet).sort();

  // Count sessions by tool type
  for (const session of sessions) {
    const tool = session.type;
    summary.by_tool[tool] = (summary.by_tool[tool] || 0) + 1;
  }

  return summary;
}

/**
 * Download and parse JSON file from GCS
 * @param {Storage} storage - GCS Storage client
 * @param {string} bucketName - Bucket name
 * @param {string} filePath - File path in bucket
 * @returns {Promise<Object|null>} - Parsed JSON or null if not found
 */
async function downloadAndParse(storage, bucketName, filePath) {
  try {
    const bucket = storage.bucket(bucketName);
    const file = bucket.file(filePath);

    // Check if file exists
    const [exists] = await file.exists();
    if (!exists) {
      return null;
    }

    // Download file contents
    const [contents] = await file.download();
    const data = JSON.parse(contents.toString('utf-8'));
    return data;
  } catch (error) {
    // Handle specific GCS errors
    if (error.code === 404) {
      return null;
    }
    if (error.code === 403) {
      throw new GCSStorageError(
        `Permission denied accessing ${bucketName}/${filePath}`,
        403,
        bucketName
      );
    }
    if (error instanceof SyntaxError) {
      console.warn(`Malformed JSON in GCS file ${bucketName}/${filePath}:`, error.message);
      return null;
    }
    // Re-throw other errors
    throw new GCSStorageError(
      `Failed to download ${bucketName}/${filePath}: ${error.message}`,
      error.code || 500,
      bucketName
    );
  }
}

/**
 * Collect station activity from GCS for a specific date
 * @param {Date|string} date - Date to collect activity for (Date object or YYYY-MM-DD string)
 * @param {Object} config - Intelligence configuration
 * @returns {Promise<Object>} - Station activity data
 */
async function collect(date, config) {
  // Normalize date to string
  const dateStr = date instanceof Date ? formatDate(date) : date;

  // Get GCS configuration
  const bucketName = config?.storage?.gcs_bucket || 'glassbox-dev-activity';
  const prefix = config?.storage?.gcs_prefix || 'station/';
  const filePath = `${prefix}${dateStr}.json`;

  console.log(`Collecting station activity from GCS: gs://${bucketName}/${filePath}`);

  // Create GCS client (uses ADC in production)
  const storage = new Storage();

  // Try to download and parse the log file
  const logData = await safeExecute(
    () => downloadAndParse(storage, bucketName, filePath),
    null,
    `station-collector/gcs-download`
  );

  // If no log data, return empty structure
  if (!logData) {
    console.warn(`Station activity log not found: gs://${bucketName}/${filePath}`);
    return {
      date: dateStr,
      sessions: [],
      summary: {
        total_sessions: 0,
        active_hours: 0,
        projects_touched: [],
        by_tool: {},
        total_commands: 0,
        total_files_edited: 0
      },
      source: {
        type: 'gcs',
        bucket: bucketName,
        path: filePath,
        found: false
      }
    };
  }

  // Process sessions (sanitize, calculate durations)
  const sessions = processSessions(logData.sessions || []);

  // Calculate summary statistics
  const summary = calculateSummary(sessions);

  console.log(`Station activity collected: ${sessions.length} sessions, ${summary.active_hours}h active`);

  return {
    date: dateStr,
    sessions,
    summary,
    source: {
      type: 'gcs',
      bucket: bucketName,
      path: filePath,
      found: true
    }
  };
}

/**
 * List available station activity dates in GCS
 * Useful for backfill or finding gaps in data
 * @param {Object} config - Intelligence configuration
 * @param {Object} [options] - List options
 * @param {string} [options.startDate] - YYYY-MM-DD start date filter
 * @param {string} [options.endDate] - YYYY-MM-DD end date filter
 * @param {number} [options.limit] - Maximum files to return
 * @returns {Promise<Array<string>>} - Array of available dates (YYYY-MM-DD)
 */
async function listAvailableDates(config, options = {}) {
  const bucketName = config?.storage?.gcs_bucket || 'glassbox-dev-activity';
  const prefix = config?.storage?.gcs_prefix || 'station/';

  const storage = new Storage();
  const bucket = storage.bucket(bucketName);

  try {
    const [files] = await bucket.getFiles({
      prefix,
      maxResults: options.limit || 365
    });

    // Extract dates from filenames - only match files directly named YYYY-MM-DD.json
    const dates = files
      .map(file => {
        // Match only files like station/2026-03-01.json (not backup-2026-03-01.json)
        const match = file.name.match(/\/(\d{4}-\d{2}-\d{2})\.json$/);
        return match ? match[1] : null;
      })
      .filter(date => date !== null)
      .filter(date => {
        // Apply date filters if specified
        if (options.startDate && date < options.startDate) return false;
        if (options.endDate && date > options.endDate) return false;
        return true;
      })
      .sort()
      .reverse(); // Most recent first

    return dates;
  } catch (error) {
    console.error(`Failed to list station activity files: ${error.message}`);
    return [];
  }
}

/**
 * Collect station activity for multiple dates (batch operation)
 * @param {Array<string>} dates - Array of YYYY-MM-DD date strings
 * @param {Object} config - Intelligence configuration
 * @returns {Promise<Object>} - Aggregated station activity data
 */
async function collectBatch(dates, config) {
  const results = {
    dates_requested: dates.length,
    dates_found: 0,
    dates_missing: [],
    sessions: [],
    summary: {
      total_sessions: 0,
      active_hours: 0,
      projects_touched: [],
      by_tool: {},
      total_commands: 0,
      total_files_edited: 0
    },
    by_date: {}
  };

  // Collect sequentially to avoid overwhelming GCS
  for (const date of dates) {
    const data = await collect(date, config);

    if (data.source.found) {
      results.dates_found++;
      results.sessions.push(...data.sessions);
      results.by_date[date] = {
        sessions: data.sessions.length,
        active_hours: data.summary.active_hours
      };
    } else {
      results.dates_missing.push(date);
    }
  }

  // Recalculate aggregate summary
  results.summary = calculateSummary(results.sessions);

  return results;
}

module.exports = {
  collect,
  listAvailableDates,
  collectBatch,
  // Export for testing
  GCSStorageError,
  sanitizeCommand,
  sanitizePath,
  processSessions,
  calculateSummary,
  downloadAndParse
};
