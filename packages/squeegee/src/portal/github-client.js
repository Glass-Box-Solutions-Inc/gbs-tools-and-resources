/**
 * Portal GitHub Client
 *
 * Collects 365-day commit history, contributors, PRs, health scores,
 * and builds the developer heatmap for the portal.
 * Ported from glass-box-hub/squeegee/github_client.py (579 lines).
 *
 * Reuses the Octokit setup pattern from intelligence/github-collector.js.
 *
 * @file src/portal/github-client.js
 * @module portal/github-client
 */

'use strict';

const { Octokit } = require('@octokit/rest');
const { retry } = require('@octokit/plugin-retry');
const { throttling } = require('@octokit/plugin-throttling');
const {
  ProjectStatus,
  ProjectCategory,
  ExpertiseLevel,
  getExpertiseLevel,
  getColorIntensity,
  STATUS_MAP,
  CATEGORY_MAP,
} = require('./models');

const MyOctokit = Octokit.plugin(retry, throttling);
const GH_ORG = 'Glass-Box-Solutions-Inc';

/**
 * Create configured Octokit client with retry and throttling
 * @param {string} token - GitHub PAT
 * @returns {Octokit}
 */
function createOctokit(token) {
  return new MyOctokit({
    auth: token,
    throttle: {
      onRateLimit: (retryAfter, options, _octokit, retryCount) => {
        console.warn(`Portal: Rate limit hit for ${options.method} ${options.url}`);
        return retryCount < 3;
      },
      onSecondaryRateLimit: () => true,
    },
    retry: { doNotRetry: [400, 401, 403, 404, 422] },
  });
}

/**
 * Fetch commits for a repo over a date range
 * @param {Octokit} octokit
 * @param {string} repoName
 * @param {string} since - ISO 8601
 * @param {number} [maxCount=1000]
 * @returns {Promise<Array>}
 */
async function fetchCommits(octokit, repoName, since, maxCount = 1000) {
  try {
    const commits = await octokit.paginate(
      octokit.repos.listCommits,
      { owner: GH_ORG, repo: repoName, since, per_page: 100 },
      (response, done) => {
        const mapped = response.data.map((c) => ({
          sha: c.sha,
          message: (c.commit.message || '').split('\n')[0],
          author: c.commit.author?.name || 'Unknown',
          author_email: c.commit.author?.email || '',
          timestamp: c.commit.author?.date || '',
          repo_name: repoName,
          url: c.html_url || '',
        }));
        if (mapped.length >= maxCount) done();
        return mapped;
      }
    );
    return commits.slice(0, maxCount);
  } catch (err) {
    if (err.status === 409) return []; // empty repo
    console.error(`Portal: Failed to fetch commits for ${repoName}: ${err.message}`);
    return [];
  }
}

/**
 * Fetch contributors for a repo
 * @param {Octokit} octokit
 * @param {string} repoName
 * @returns {Promise<Array>}
 */
async function fetchContributors(octokit, repoName) {
  try {
    const { data } = await octokit.repos.listContributors({
      owner: GH_ORG,
      repo: repoName,
      per_page: 100,
    });
    return data.map((c) => ({
      login: c.login,
      contributions: c.contributions,
      avatar_url: c.avatar_url,
    }));
  } catch {
    return [];
  }
}

/**
 * Fetch open pull requests
 * @param {Octokit} octokit
 * @param {string} repoName
 * @returns {Promise<Array>}
 */
async function fetchOpenPRs(octokit, repoName) {
  try {
    const { data } = await octokit.pulls.list({
      owner: GH_ORG,
      repo: repoName,
      state: 'open',
      per_page: 30,
    });
    return data.map((pr) => ({
      number: pr.number,
      title: pr.title,
      author: pr.user?.login || 'unknown',
      created_at: pr.created_at,
      labels: pr.labels.map((l) => l.name),
    }));
  } catch {
    return [];
  }
}

/**
 * Fetch file content from a repo via GitHub Contents API
 * @param {Octokit} octokit
 * @param {string} repoName
 * @param {string} filePath
 * @returns {Promise<string|null>}
 */
async function fetchFileContent(octokit, repoName, filePath) {
  try {
    const { data } = await octokit.repos.getContent({
      owner: GH_ORG,
      repo: repoName,
      path: filePath,
    });
    if (data.content && data.encoding === 'base64') {
      return Buffer.from(data.content, 'base64').toString('utf-8');
    }
    return null;
  } catch {
    return null;
  }
}

/**
 * Fetch README for a repo
 * @param {Octokit} octokit
 * @param {string} repoName
 * @param {number} [maxChars=15000]
 * @returns {Promise<string>}
 */
async function fetchReadme(octokit, repoName, maxChars = 15000) {
  try {
    const { data } = await octokit.repos.getReadme({
      owner: GH_ORG,
      repo: repoName,
    });
    if (data.content && data.encoding === 'base64') {
      const content = Buffer.from(data.content, 'base64').toString('utf-8');
      return content.slice(0, maxChars);
    }
    return '';
  } catch {
    return '';
  }
}

/**
 * Compute health score for a project (0-100)
 * @param {string} status
 * @param {number} priority
 * @param {boolean} hasUrl
 * @param {number} commits30d
 * @param {number} contributorCount
 * @returns {number}
 */
function computeHealthScore(status, priority, hasUrl, commits30d, contributorCount) {
  const statusScores = {
    deployed: 85,
    active: 70,
    maintenance: 50,
    planning: 40,
    deprecated: 20,
    archived: 10,
  };
  let score = statusScores[status] || 40;

  // Activity bonus
  if (commits30d > 50) score += 10;
  else if (commits30d > 20) score += 7;
  else if (commits30d > 5) score += 4;

  // Team bonus
  if (contributorCount >= 3) score += 5;
  else if (contributorCount >= 2) score += 3;

  // Production URL bonus
  if (hasUrl) score += 3;

  return Math.min(100, score);
}

/**
 * Build developer models from contribution data
 * @param {Object<string, Object<string, number>>} contributions - author -> { repo -> count }
 * @returns {Developer[]}
 */
function buildDevelopers(contributions) {
  const developers = [];

  for (const [author, repos] of Object.entries(contributions)) {
    const totalCommits = Object.values(repos).reduce((sum, n) => sum + n, 0);
    developers.push({
      name: author,
      expertise_areas: { ...repos },
      total_commits: totalCommits,
      active_projects: Object.keys(repos),
      contribution_counts: { ...repos },
    });
  }

  developers.sort((a, b) => b.total_commits - a.total_commits);
  return developers;
}

/**
 * Build heatmap cells from commit data
 * @param {Object<string, Object<string, number>>} allTime - author -> { repo -> count }
 * @param {Object<string, Object<string, number>>} recent30d - author -> { repo -> count }
 * @returns {HeatmapCell[]}
 */
function buildHeatmap(allTime, recent30d) {
  const cells = [];

  for (const [author, repos] of Object.entries(allTime)) {
    for (const [repo, count] of Object.entries(repos)) {
      const recentCount = recent30d[author]?.[repo] || 0;
      cells.push({
        developer_name: author,
        project_name: repo,
        commit_count: count,
        expertise_level: getExpertiseLevel(count),
        recent_commits: recentCount,
      });
    }
  }

  return cells;
}

/**
 * Collect all portal data from GitHub for configured repos
 * @param {Array<Object>} repoConfigs - Array of repo config objects from portal.config.json
 * @param {string} githubToken - GitHub PAT
 * @returns {Promise<Object>} - { projects, developers, recent_commits, heatmap, activity_feed, all_commits_365d }
 */
async function collectAll(repoConfigs, githubToken) {
  const octokit = createOctokit(githubToken);
  const since365d = new Date();
  since365d.setDate(since365d.getDate() - 365);
  const sinceISO = since365d.toISOString();

  const since30d = new Date();
  since30d.setDate(since30d.getDate() - 30);

  const projects = [];
  const recentCommits = {};
  const allCommits365d = [];
  const activityFeed = [];
  const contributionsAllTime = {};
  const contributionsRecent = {};

  for (const repoConfig of repoConfigs) {
    const repoName = repoConfig.name;
    if (repoConfig.hidden) continue;

    console.log(`Portal: Collecting data for ${repoName}`);

    // Fetch commits (365d), contributors, and PRs in parallel
    const [commits, contributors, openPRs] = await Promise.all([
      fetchCommits(octokit, repoName, sinceISO),
      fetchContributors(octokit, repoName),
      fetchOpenPRs(octokit, repoName),
    ]);

    // Split commits into 30d and 365d buckets
    const commits30d = commits.filter((c) => new Date(c.timestamp) >= since30d);
    const lastCommitDate = commits.length > 0 ? commits[0].timestamp : null;

    // Build project
    const status = repoConfig.status || 'active';
    const project = {
      name: repoName,
      repo_path: `${GH_ORG}/${repoName}`,
      status,
      category: repoConfig.category || 'research-oss',
      description: repoConfig.description || '',
      tech_stack: repoConfig.stack || [],
      team_lead: repoConfig.team_lead,
      contributors: contributors.map((c) => c.login),
      production_url: repoConfig.url,
      commit_count_30d: commits30d.length,
      health_score: computeHealthScore(
        status,
        repoConfig.priority || 3,
        !!repoConfig.url,
        commits30d.length,
        contributors.length
      ),
      last_commit_date: lastCommitDate,
    };

    projects.push(project);
    recentCommits[repoName] = commits30d;
    allCommits365d.push(...commits);

    // Build activity feed from recent commits and PRs
    for (const commit of commits30d.slice(0, 5)) {
      activityFeed.push({
        event_type: 'commit',
        title: commit.message,
        author: commit.author,
        timestamp: commit.timestamp,
        repo_name: repoName,
        url: commit.url,
      });
    }

    for (const pr of openPRs) {
      activityFeed.push({
        event_type: 'pr',
        title: pr.title,
        author: pr.author,
        timestamp: pr.created_at,
        repo_name: repoName,
      });
    }

    // Track contributions for heatmap
    for (const c of commits) {
      if (!contributionsAllTime[c.author]) contributionsAllTime[c.author] = {};
      contributionsAllTime[c.author][repoName] =
        (contributionsAllTime[c.author][repoName] || 0) + 1;
    }

    for (const c of commits30d) {
      if (!contributionsRecent[c.author]) contributionsRecent[c.author] = {};
      contributionsRecent[c.author][repoName] =
        (contributionsRecent[c.author][repoName] || 0) + 1;
    }
  }

  // Sort activity feed by recency
  activityFeed.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));

  return {
    projects,
    developers: buildDevelopers(contributionsAllTime),
    recent_commits: recentCommits,
    heatmap: buildHeatmap(contributionsAllTime, contributionsRecent),
    activity_feed: activityFeed.slice(0, 100),
    all_commits_365d: allCommits365d,
  };
}

/**
 * Collect data for a single repo (for webhook refresh)
 * @param {string} repoName
 * @param {Object} repoConfig
 * @param {string} githubToken
 * @returns {Promise<Object>} - { project, commits, commits_365d, activity, readme, claudemd }
 */
async function collectSingleRepo(repoName, repoConfig, githubToken) {
  const octokit = createOctokit(githubToken);
  const since365d = new Date();
  since365d.setDate(since365d.getDate() - 365);

  const since30d = new Date();
  since30d.setDate(since30d.getDate() - 30);

  const [commits, contributors, openPRs, readme, claudemd] = await Promise.all([
    fetchCommits(octokit, repoName, since365d.toISOString()),
    fetchContributors(octokit, repoName),
    fetchOpenPRs(octokit, repoName),
    fetchReadme(octokit, repoName),
    fetchFileContent(octokit, repoName, 'CLAUDE.md'),
  ]);

  const commits30d = commits.filter((c) => new Date(c.timestamp) >= since30d);
  const lastCommitDate = commits.length > 0 ? commits[0].timestamp : null;
  const status = repoConfig.status || 'active';

  const project = {
    name: repoName,
    repo_path: `${GH_ORG}/${repoName}`,
    status,
    category: repoConfig.category || 'research-oss',
    description: repoConfig.description || '',
    tech_stack: repoConfig.stack || [],
    contributors: contributors.map((c) => c.login),
    production_url: repoConfig.url,
    commit_count_30d: commits30d.length,
    health_score: computeHealthScore(
      status,
      repoConfig.priority || 3,
      !!repoConfig.url,
      commits30d.length,
      contributors.length
    ),
    last_commit_date: lastCommitDate,
  };

  const activity = [];
  for (const c of commits30d.slice(0, 10)) {
    activity.push({
      event_type: 'commit',
      title: c.message,
      author: c.author,
      timestamp: c.timestamp,
      repo_name: repoName,
      url: c.url,
    });
  }

  return { project, commits: commits30d, commits_365d: commits, activity, readme, claudemd };
}

module.exports = {
  createOctokit,
  fetchCommits,
  fetchContributors,
  fetchOpenPRs,
  fetchFileContent,
  fetchReadme,
  computeHealthScore,
  buildDevelopers,
  buildHeatmap,
  collectAll,
  collectSingleRepo,
};
