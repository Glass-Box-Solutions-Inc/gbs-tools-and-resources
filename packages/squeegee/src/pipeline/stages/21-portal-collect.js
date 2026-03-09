/**
 * Stage 21: Portal Collect
 *
 * Fetches GitHub data (365d commits, contributors, PRs), Linear sprints,
 * and repo metadata for the HTML portal. Reuses data from stages 1-14
 * where available.
 *
 * @file src/pipeline/stages/21-portal-collect.js
 * @module pipeline/stages/21-portal-collect
 */

'use strict';

const fs = require('fs').promises;
const path = require('path');
const { log } = require('../utils');
const githubClient = require('../../portal/github-client');
const linearClient = require('../../portal/linear-client');
const { saveProjectCache } = require('../../portal/project-cache');

/**
 * Load portal configuration
 * @returns {Promise<Object>}
 */
async function loadPortalConfig() {
  const configPath = path.join(process.cwd(), 'config', 'portal.config.json');
  try {
    const data = await fs.readFile(configPath, 'utf-8');
    return JSON.parse(data);
  } catch (err) {
    throw new Error(`Portal config not found: ${err.message}`);
  }
}

/**
 * Resolve GitHub token from environment
 * @returns {string}
 */
function getGitHubToken() {
  // Try various env var names
  const token = process.env.GITHUB_PAT || process.env.GITHUB_TOKEN;
  if (token) {
    // Could be a path to a mounted secret or the token itself
    if (token.startsWith('/') && token.length < 200) {
      try {
        return require('fs').readFileSync(token, 'utf-8').trim();
      } catch {
        return token;
      }
    }
    return token;
  }
  throw new Error('GitHub token not configured (GITHUB_PAT or GITHUB_TOKEN)');
}

/**
 * Resolve Linear API key from environment
 * @returns {string|null}
 */
function getLinearApiKey() {
  const key = process.env.LINEAR_API_KEY;
  if (!key) return null;
  if (key.startsWith('/') && key.length < 200) {
    try {
      return require('fs').readFileSync(key, 'utf-8').trim();
    } catch {
      return key;
    }
  }
  return key;
}

/**
 * Run Stage 21: Portal data collection
 * @param {Object} config - Pipeline config
 * @param {Object} [prevData] - Data from previous stages
 * @returns {Promise<Object>} - Collected portal data
 */
async function run(config, prevData) {
  log('Stage 21: Portal data collection', 'info');

  const portalConfig = await loadPortalConfig();
  const repoConfigs = portalConfig.repos || [];
  const githubToken = getGitHubToken();
  const linearApiKey = getLinearApiKey();

  log(`Collecting data for ${repoConfigs.length} repositories`, 'info');

  // Collect GitHub data (365d commits, contributors, PRs)
  const githubData = await githubClient.collectAll(repoConfigs, githubToken);

  // Collect Linear sprint data
  const sprints = await linearClient.collectSprintData(linearApiKey);

  // Save to project cache for incremental updates
  const commitsByRepo = {};
  const activityByRepo = {};
  for (const event of githubData.activity_feed) {
    if (!activityByRepo[event.repo_name]) activityByRepo[event.repo_name] = [];
    activityByRepo[event.repo_name].push(event);
  }

  await saveProjectCache(
    githubData.projects,
    githubData.recent_commits,
    activityByRepo,
    githubData.all_commits_365d
  );

  const result = {
    ...githubData,
    sprints,
    repo_configs: repoConfigs,
    portal_config: portalConfig,
  };

  log(`Collected: ${githubData.projects.length} projects, ${githubData.all_commits_365d.length} commits (365d), ${Object.keys(sprints).length} sprints`, 'success');

  return result;
}

module.exports = { run };
