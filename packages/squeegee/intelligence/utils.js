/**
 * Shared utilities and error classes for intelligence modules
 *
 * @file utils.js
 * @module intelligence/utils
 */

/**
 * GitHub API error - rate limiting, authentication, or API failures
 */
class GitHubAPIError extends Error {
  /**
   * @param {string} message - Error message
   * @param {number} statusCode - HTTP status code
   * @param {string} endpoint - API endpoint that failed
   */
  constructor(message, statusCode, endpoint) {
    super(message);
    this.name = 'GitHubAPIError';
    this.statusCode = statusCode;
    this.endpoint = endpoint;
    // Rate limit errors are recoverable via retry
    this.recoverable = statusCode === 429 || statusCode === 403;
  }
}

/**
 * GCP Cloud Logging error - permissions or quota issues
 */
class GCPLoggingError extends Error {
  /**
   * @param {string} message - Error message
   * @param {string} code - GCP error code
   */
  constructor(message, code) {
    super(message);
    this.name = 'GCPLoggingError';
    this.code = code;
    // Permission and quota errors are recoverable
    this.recoverable = code === 'PERMISSION_DENIED' || code === 'QUOTA_EXCEEDED';
  }
}

/**
 * GCS Storage error - permissions or not found
 */
class GCSStorageError extends Error {
  /**
   * @param {string} message - Error message
   * @param {number} code - HTTP status code
   * @param {string} bucket - Bucket name
   */
  constructor(message, code, bucket) {
    super(message);
    this.name = 'GCSStorageError';
    this.code = code;
    this.bucket = bucket;
    // 5xx and 429 are recoverable
    this.recoverable = code === 429 || code >= 500;
  }
}

/**
 * Gemini API error - API failures or quota issues
 */
class GeminiAPIError extends Error {
  /**
   * @param {string} message - Error message
   * @param {number} statusCode - HTTP status code
   */
  constructor(message, statusCode) {
    super(message);
    this.name = 'GeminiAPIError';
    this.statusCode = statusCode;
    // Rate limit and server errors are recoverable
    this.recoverable = statusCode === 429 || statusCode === 500;
  }
}

/**
 * Sleep for specified milliseconds
 * @param {number} ms - Milliseconds to sleep
 * @returns {Promise<void>}
 */
function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * Retry a function with exponential backoff
 * @param {Function} fn - Async function to retry
 * @param {number} maxRetries - Maximum retry attempts
 * @param {number} baseDelay - Base delay in ms (default: 1000)
 * @returns {Promise<any>} - Result of function
 */
async function retryWithBackoff(fn, maxRetries = 3, baseDelay = 1000) {
  for (let attempt = 0; attempt < maxRetries; attempt++) {
    try {
      return await fn();
    } catch (error) {
      // Check if error is recoverable
      const isRecoverable = error.recoverable !== false;
      const isLastAttempt = attempt === maxRetries - 1;

      if (isLastAttempt || !isRecoverable) {
        throw error;
      }

      // Exponential backoff: 1s, 2s, 4s, etc.
      const delay = baseDelay * Math.pow(2, attempt);
      console.warn(`Retry attempt ${attempt + 1}/${maxRetries} after ${delay}ms delay`, {
        error: error.message,
        recoverable: isRecoverable
      });
      await sleep(delay);
    }
  }
}

/**
 * Execute function with graceful error handling
 * Returns default value if function throws
 * @param {Function} fn - Async function to execute
 * @param {any} defaultValue - Value to return on error
 * @param {string} [context] - Context for logging
 * @returns {Promise<any>}
 */
async function safeExecute(fn, defaultValue, context = '') {
  try {
    return await fn();
  } catch (error) {
    console.warn(`Safe execute failed${context ? ` (${context})` : ''}:`, error.message);
    return defaultValue;
  }
}

/**
 * Format date as YYYY-MM-DD
 * @param {Date} date - Date object
 * @returns {string} - Formatted date string
 */
function formatDate(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

/**
 * Get yesterday's date as YYYY-MM-DD
 * @returns {string} - Yesterday's date
 */
function getYesterday() {
  const yesterday = new Date();
  yesterday.setDate(yesterday.getDate() - 1);
  return formatDate(yesterday);
}

/**
 * Parse YYYY-MM-DD date string to Date object
 * @param {string} dateStr - Date string
 * @returns {Date} - Date object
 */
function parseDate(dateStr) {
  const [year, month, day] = dateStr.split('-').map(Number);
  return new Date(year, month - 1, day);
}

/**
 * Get UTC start and end timestamps for a date
 * @param {string} dateStr - YYYY-MM-DD date string
 * @returns {{start: string, end: string}} - ISO 8601 timestamps
 */
function getDateRange(dateStr) {
  const [year, month, day] = dateStr.split('-').map(Number);
  const start = new Date(Date.UTC(year, month - 1, day, 0, 0, 0));
  const end = new Date(Date.UTC(year, month - 1, day, 23, 59, 59));

  return {
    start: start.toISOString(),
    end: end.toISOString()
  };
}

module.exports = {
  GitHubAPIError,
  GCPLoggingError,
  GCSStorageError,
  GeminiAPIError,
  sleep,
  retryWithBackoff,
  safeExecute,
  formatDate,
  getYesterday,
  parseDate,
  getDateRange
};
