/**
 * Development Station Activity Monitor
 *
 * Collects development station activity (Claude Code sessions, Cursor, VS Code)
 * from local log files. Designed for graceful degradation - missing files return
 * empty data structures rather than errors.
 *
 * @file station-monitor.js
 * @module intelligence/station-monitor
 */

const fs = require('fs').promises;
const path = require('path');
const { safeExecute } = require('./utils');

// Default log directory for station activity
const DEFAULT_LOG_DIR = '/var/log/glass-box/station-activity';

/**
 * Sanitize terminal command - remove sensitive arguments
 * @param {string} command - Raw command string
 * @returns {string} - Sanitized command
 */
function sanitizeCommand(command) {
  if (!command) return '';

  // Remove any arguments containing secrets
  return command
    .replace(/--token[= ][\w-]+/gi, '--token=***')
    .replace(/--password[= ][\w-]+/gi, '--password=***')
    .replace(/--secret[= ][\w-]+/gi, '--secret=***')
    .replace(/--api-key[= ][\w-]+/gi, '--api-key=***')
    .replace(/Bearer [\w.-]+/gi, 'Bearer ***');
}

/**
 * Sanitize file path - remove sensitive paths
 * @param {string} filePath - Raw file path
 * @returns {string} - Sanitized path
 */
function sanitizePath(filePath) {
  if (!filePath) return '';

  // Redact paths containing secrets
  if (filePath.includes('/secrets/') || filePath.includes('/.env')) {
    return '[REDACTED]';
  }

  return filePath;
}

/**
 * Parse log file for specified date
 * @param {string} logDir - Log directory path
 * @param {Date} date - Date to collect activity for
 * @returns {Promise<Object|null>} - Parsed log data or null if missing
 */
async function parseLogFile(logDir, date) {
  const dateStr = date.toISOString().split('T')[0]; // YYYY-MM-DD
  const logPath = path.join(logDir, `${dateStr}.json`);

  try {
    const content = await fs.readFile(logPath, 'utf-8');
    const data = JSON.parse(content);
    return data;
  } catch (error) {
    if (error.code === 'ENOENT') {
      // File not found - return null (not an error)
      return null;
    }
    if (error instanceof SyntaxError) {
      // Malformed JSON - log warning and return null
      console.warn(`Malformed JSON in station log ${logPath}:`, error.message);
      return null;
    }
    // Other error - log but don't throw
    console.warn(`Failed to read station log ${logPath}:`, error.message);
    return null;
  }
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
      duration_minutes: durationMinutes,
      commands: session.commands || 0,
      files_edited: session.files_edited || 0
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
    by_tool: {}
  };

  // Calculate total active hours
  for (const session of sessions) {
    summary.active_hours += session.duration_minutes / 60;
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
 * Collect dev station activity for a specific date
 * @param {Date} date - Date to collect activity for
 * @param {Object} config - Intelligence configuration
 * @returns {Promise<Object>} - Station activity data
 */
async function collect(date, config) {
  // Use custom log directory if provided, otherwise default
  const logDir = config?.station?.log_dir || DEFAULT_LOG_DIR;

  console.log(`Collecting station activity for ${date.toISOString().split('T')[0]}`);

  // Try to read log file - returns null if missing
  const logData = await safeExecute(
    () => parseLogFile(logDir, date),
    null,
    'station-monitor/parse-log'
  );

  // If no log data, return empty structure
  if (!logData) {
    console.warn(`Station activity log not found for ${date.toISOString().split('T')[0]}`);
    return {
      date: date.toISOString().split('T')[0],
      sessions: [],
      summary: {
        total_sessions: 0,
        active_hours: 0,
        projects_touched: [],
        by_tool: {}
      },
      log_file_missing: true
    };
  }

  // Process sessions (sanitize, calculate durations)
  const sessions = processSessions(logData.sessions || []);

  // Calculate summary statistics
  const summary = calculateSummary(sessions);

  return {
    date: date.toISOString().split('T')[0],
    sessions,
    summary,
    log_file_missing: false
  };
}

module.exports = {
  collect,
  // Export for testing
  sanitizeCommand,
  sanitizePath,
  processSessions,
  calculateSummary
};
