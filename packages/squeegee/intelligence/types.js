/**
 * Shared type definitions for Squeegee intelligence modules
 *
 * This file contains TypeScript-style JSDoc type definitions for the intelligence
 * collection, synthesis, and curation pipeline.
 *
 * @file types.js
 * @module intelligence/types
 */

/**
 * @typedef {Object} IntelligenceConfig
 * @property {boolean} enabled - Whether intelligence collection is enabled
 * @property {string[]} repos - Array of repo names to monitor
 * @property {string[]} gcp_projects - GCP projects to query Cloud Logging
 * @property {string} docs_repo - Target documentation repository
 * @property {Object} gemini - Gemini API configuration
 * @property {string} gemini.model - Model name (e.g., "gemini-2.0-flash-exp")
 * @property {number} gemini.temperature - Temperature for generation
 * @property {string} [gemini.apiKey] - API key (loaded from Secret Manager)
 * @property {Object} claude_md_audit - CLAUDE.md audit configuration
 * @property {number} claude_md_audit.threshold - Min score to pass
 * @property {number} claude_md_audit.reopen_delay_days - Days before reopening rejected PR
 * @property {boolean} dry_run - If true, collect but don't write
 */

/**
 * @typedef {Object} GitHubActivity
 * @property {Record<string, RepoActivity>} repos - Activity by repository
 * @property {Object} summary - Aggregated summary statistics
 * @property {number} summary.total_commits - Total commits across all repos
 * @property {number} summary.total_prs - Total pull requests
 * @property {number} summary.total_issues - Total issues
 * @property {number} summary.total_ci_runs - Total CI runs
 * @property {string[]} [repos_failed] - Repos that failed to collect
 */

/**
 * @typedef {Object} RepoActivity
 * @property {string} repo - Repository name
 * @property {CommitData[]} commits - Commit activity
 * @property {PullRequestData[]} pull_requests - Pull request activity
 * @property {IssueData[]} issues - Issue activity
 * @property {CIRunData[]} ci_runs - CI run activity
 */

/**
 * @typedef {Object} CommitData
 * @property {string} sha - Commit SHA
 * @property {string} message - Commit message
 * @property {string} author - Author name
 * @property {string} timestamp - ISO 8601 timestamp
 */

/**
 * @typedef {Object} PullRequestData
 * @property {number} number - PR number
 * @property {string} title - PR title
 * @property {string} author - Author username
 * @property {'open'|'closed'|'merged'} state - PR state
 * @property {string} created_at - ISO 8601 timestamp
 * @property {string} [merged_at] - ISO 8601 timestamp (if merged)
 * @property {string[]} labels - Array of label names
 */

/**
 * @typedef {Object} IssueData
 * @property {number} number - Issue number
 * @property {string} title - Issue title
 * @property {string} author - Author username
 * @property {'open'|'closed'} state - Issue state
 * @property {string[]} labels - Array of label names
 * @property {string} created_at - ISO 8601 timestamp
 */

/**
 * @typedef {Object} CIRunData
 * @property {string} workflow_name - Workflow name
 * @property {string} status - Run status
 * @property {string} conclusion - Run conclusion
 * @property {number} duration_ms - Duration in milliseconds
 * @property {string} created_at - ISO 8601 timestamp
 */

/**
 * @typedef {Object} CollectedData
 * @property {string} date - YYYY-MM-DD
 * @property {GitHubActivity} github - GitHub activity data
 * @property {Object} gcp - GCP activity data
 * @property {Object} station - Station activity data
 * @property {Array} checkpoints - Checkpoint events
 */

module.exports = {
  // Export empty object - types are for documentation only
};
