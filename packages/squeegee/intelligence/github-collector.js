/**
 * GitHub Activity Collector
 *
 * Collects GitHub activity (commits, PRs, issues, CI runs) for all GBS repos
 * via GitHub REST API with rate limiting, pagination, and error handling.
 *
 * @file github-collector.js
 * @module intelligence/github-collector
 */

const { Octokit } = require('@octokit/rest');
const { retry } = require('@octokit/plugin-retry');
const { throttling } = require('@octokit/plugin-throttling');
const { GitHubAPIError, retryWithBackoff, safeExecute, getDateRange } = require('./utils');

// Create Octokit with retry and throttling plugins
const MyOctokit = Octokit.plugin(retry, throttling);

// GitHub organization constant
const GH_ORG = 'Glass-Box-Solutions-Inc';

/**
 * Create configured Octokit client
 * @param {string} token - GitHub PAT
 * @returns {Octokit} - Configured Octokit instance
 */
function createOctokit(token) {
  return new MyOctokit({
    auth: token,
    throttle: {
      onRateLimit: (retryAfter, options, octokit, retryCount) => {
        console.warn(`Rate limit hit for ${options.method} ${options.url}`);
        console.warn(`Retry after ${retryAfter}s (attempt ${retryCount})`);

        // Retry first 3 times
        if (retryCount < 3) {
          return true;
        }
      },
      onSecondaryRateLimit: (retryAfter, options, octokit, retryCount) => {
        console.warn(`Secondary rate limit hit for ${options.method} ${options.url}`);
        // Always retry secondary rate limits
        return true;
      }
    },
    retry: {
      doNotRetry: [400, 401, 403, 404, 422]
    }
  });
}

/**
 * Collect commits for a repository within date range
 * @param {Octokit} octokit - GitHub API client
 * @param {string} repo - Repository name
 * @param {string} since - ISO 8601 start timestamp
 * @param {string} until - ISO 8601 end timestamp
 * @returns {Promise<Array>} - Array of commit data
 */
async function collectCommits(octokit, repo, since, until) {
  try {
    const commits = await octokit.paginate(
      octokit.repos.listCommits,
      {
        owner: GH_ORG,
        repo,
        since,
        until,
        per_page: 100
      },
      (response) => response.data.map(commit => ({
        sha: commit.sha,
        message: commit.commit.message.split('\n')[0], // First line only
        author: commit.commit.author.name,
        timestamp: commit.commit.author.date
      }))
    );

    return commits;
  } catch (error) {
    throw new GitHubAPIError(
      `Failed to collect commits for ${repo}: ${error.message}`,
      error.status || 500,
      `GET /repos/${GH_ORG}/${repo}/commits`
    );
  }
}

/**
 * Collect pull requests for a repository within date range
 * @param {Octokit} octokit - GitHub API client
 * @param {string} repo - Repository name
 * @param {string} since - ISO 8601 start timestamp
 * @param {string} until - ISO 8601 end timestamp
 * @returns {Promise<Array>} - Array of PR data
 */
async function collectPRs(octokit, repo, since, until) {
  try {
    // GitHub API doesn't support time-based filtering for PRs directly
    // We'll fetch all PRs and filter client-side
    const sinceDate = new Date(since);
    const untilDate = new Date(until);

    const allPRs = await octokit.paginate(
      octokit.pulls.list,
      {
        owner: GH_ORG,
        repo,
        state: 'all',
        sort: 'updated',
        direction: 'desc',
        per_page: 100
      }
    );

    // Filter PRs created or updated within date range
    const filteredPRs = allPRs
      .filter(pr => {
        const createdAt = new Date(pr.created_at);
        const updatedAt = new Date(pr.updated_at);
        return (createdAt >= sinceDate && createdAt <= untilDate) ||
               (updatedAt >= sinceDate && updatedAt <= untilDate);
      })
      .map(pr => ({
        number: pr.number,
        title: pr.title,
        author: pr.user.login,
        state: pr.merged_at ? 'merged' : pr.state,
        created_at: pr.created_at,
        merged_at: pr.merged_at || undefined,
        labels: pr.labels.map(l => l.name)
      }));

    return filteredPRs;
  } catch (error) {
    throw new GitHubAPIError(
      `Failed to collect PRs for ${repo}: ${error.message}`,
      error.status || 500,
      `GET /repos/${GH_ORG}/${repo}/pulls`
    );
  }
}

/**
 * Collect issues for a repository within date range
 * @param {Octokit} octokit - GitHub API client
 * @param {string} repo - Repository name
 * @param {string} since - ISO 8601 start timestamp
 * @param {string} until - ISO 8601 end timestamp
 * @returns {Promise<Array>} - Array of issue data
 */
async function collectIssues(octokit, repo, since, until) {
  try {
    const sinceDate = new Date(since);
    const untilDate = new Date(until);

    // List issues (this includes PRs, we'll filter them out)
    const allIssues = await octokit.paginate(
      octokit.issues.listForRepo,
      {
        owner: GH_ORG,
        repo,
        state: 'all',
        since, // GitHub supports 'since' for issues
        per_page: 100
      }
    );

    // Filter issues within date range and exclude pull requests
    const filteredIssues = allIssues
      .filter(issue => {
        const createdAt = new Date(issue.created_at);
        // Exclude pull requests (they have pull_request field)
        return !issue.pull_request && createdAt >= sinceDate && createdAt <= untilDate;
      })
      .map(issue => ({
        number: issue.number,
        title: issue.title,
        author: issue.user.login,
        state: issue.state,
        labels: issue.labels.map(l => l.name),
        created_at: issue.created_at
      }));

    return filteredIssues;
  } catch (error) {
    throw new GitHubAPIError(
      `Failed to collect issues for ${repo}: ${error.message}`,
      error.status || 500,
      `GET /repos/${GH_ORG}/${repo}/issues`
    );
  }
}

/**
 * Collect CI/CD workflow runs for a repository within date range
 * @param {Octokit} octokit - GitHub API client
 * @param {string} repo - Repository name
 * @param {string} since - ISO 8601 start timestamp
 * @param {string} until - ISO 8601 end timestamp
 * @returns {Promise<Array>} - Array of CI run data
 */
async function collectCIRuns(octokit, repo, since, until) {
  try {
    const sinceDate = new Date(since);
    const untilDate = new Date(until);

    const runs = await octokit.paginate(
      octokit.actions.listWorkflowRunsForRepo,
      {
        owner: GH_ORG,
        repo,
        per_page: 100
      }
    );

    // Filter runs within date range
    const filteredRuns = runs
      .filter(run => {
        const createdAt = new Date(run.created_at);
        return createdAt >= sinceDate && createdAt <= untilDate;
      })
      .map(run => ({
        workflow_name: run.name,
        status: run.status,
        conclusion: run.conclusion || 'in_progress',
        duration_ms: run.updated_at && run.created_at
          ? new Date(run.updated_at) - new Date(run.created_at)
          : 0,
        created_at: run.created_at
      }));

    return filteredRuns;
  } catch (error) {
    // Some repos may not have Actions enabled - this is not an error
    if (error.status === 404) {
      return [];
    }
    throw new GitHubAPIError(
      `Failed to collect CI runs for ${repo}: ${error.message}`,
      error.status || 500,
      `GET /repos/${GH_ORG}/${repo}/actions/runs`
    );
  }
}

/**
 * Collect all activity for a single repository
 * @param {string} repo - Repository name
 * @param {string} date - YYYY-MM-DD date string
 * @param {string} githubToken - GitHub PAT
 * @returns {Promise<Object>} - Repository activity data
 */
async function collectRepo(repo, date, githubToken) {
  const octokit = createOctokit(githubToken);
  const { start, end } = getDateRange(date);

  console.log(`Collecting activity for ${repo} on ${date}`);

  // Collect all activity types in parallel
  const [commits, pull_requests, issues, ci_runs] = await Promise.all([
    safeExecute(() => collectCommits(octokit, repo, start, end), [], `${repo}/commits`),
    safeExecute(() => collectPRs(octokit, repo, start, end), [], `${repo}/prs`),
    safeExecute(() => collectIssues(octokit, repo, start, end), [], `${repo}/issues`),
    safeExecute(() => collectCIRuns(octokit, repo, start, end), [], `${repo}/ci`)
  ]);

  return {
    repo,
    commits,
    pull_requests,
    issues,
    ci_runs
  };
}

/**
 * Collect GitHub activity for all configured repositories
 * @param {string} date - YYYY-MM-DD date string
 * @param {Object} config - Intelligence configuration
 * @returns {Promise<Object>} - GitHub activity data
 */
async function collect(date, config) {
  const githubToken = process.env.GITHUB_TOKEN || config.github_token;

  if (!githubToken) {
    throw new Error('GitHub token not configured (GITHUB_TOKEN env var or config.github_token)');
  }

  console.log(`Starting GitHub collection for ${date} across ${config.repos.length} repos`);

  const startTime = Date.now();
  const repos = {};
  const failedRepos = [];

  // Collect activity for each repository
  // Use sequential processing to respect rate limits better
  for (const repo of config.repos) {
    try {
      const activity = await collectRepo(repo, date, githubToken);
      repos[repo] = activity;
    } catch (error) {
      console.error(`Failed to collect activity for ${repo}:`, error.message);
      failedRepos.push(repo);
    }
  }

  // Calculate summary statistics
  const summary = {
    total_commits: 0,
    total_prs: 0,
    total_issues: 0,
    total_ci_runs: 0
  };

  for (const repoData of Object.values(repos)) {
    summary.total_commits += repoData.commits.length;
    summary.total_prs += repoData.pull_requests.length;
    summary.total_issues += repoData.issues.length;
    summary.total_ci_runs += repoData.ci_runs.length;
  }

  const duration = Date.now() - startTime;
  console.log(`GitHub collection complete in ${duration}ms`, {
    repos_processed: Object.keys(repos).length,
    repos_failed: failedRepos.length,
    total_commits: summary.total_commits,
    total_prs: summary.total_prs,
    total_issues: summary.total_issues,
    total_ci_runs: summary.total_ci_runs
  });

  return {
    repos,
    summary,
    ...(failedRepos.length > 0 ? { repos_failed: failedRepos } : {})
  };
}

module.exports = {
  collect,
  collectRepo
};
