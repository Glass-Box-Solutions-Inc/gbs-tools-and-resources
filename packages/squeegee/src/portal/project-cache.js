/**
 * Portal Project Cache
 *
 * Per-project data cache for single-repo webhook refresh. Stores project
 * data, commits, and activity so we only need to fetch the changed repo.
 * Ported from glass-box-hub/squeegee/project_cache.py.
 *
 * @file src/portal/project-cache.js
 * @module portal/project-cache
 */

'use strict';

const fs = require('fs').promises;
const path = require('path');

const CACHE_DIR = '/tmp/portal-output';
const CACHE_FILE = path.join(CACHE_DIR, '.project-data-cache.json');

/**
 * @typedef {Object} ProjectCacheEntry
 * @property {string} cached_at
 * @property {Object} project
 * @property {Array} commits - 30d commits
 * @property {Array} commits_365d
 * @property {Array} activity
 */

/**
 * Load the project data cache
 * @returns {Promise<Object>} - { generated_at, projects: { [name]: ProjectCacheEntry } }
 */
async function loadProjectCache() {
  try {
    const data = await fs.readFile(CACHE_FILE, 'utf-8');
    return JSON.parse(data);
  } catch {
    return { generated_at: null, projects: {} };
  }
}

/**
 * Save the full project data cache
 * @param {Object} projects - { [name]: Project }
 * @param {Object} commits - { [name]: Commit[] } (30d)
 * @param {Object} activity - { [name]: ActivityEvent[] }
 * @param {Array} commits365d - All commits
 * @returns {Promise<void>}
 */
async function saveProjectCache(projects, commits, activity, commits365d) {
  const cache = {
    generated_at: new Date().toISOString(),
    projects: {},
  };

  // Group 365d commits by repo
  const commitsByRepo = {};
  for (const c of commits365d) {
    if (!commitsByRepo[c.repo_name]) commitsByRepo[c.repo_name] = [];
    commitsByRepo[c.repo_name].push(c);
  }

  for (const project of Array.isArray(projects) ? projects : Object.values(projects)) {
    const name = project.name;
    cache.projects[name] = {
      cached_at: new Date().toISOString(),
      project,
      commits: commits[name] || [],
      commits_365d: commitsByRepo[name] || [],
      activity: activity[name] || [],
    };
  }

  await fs.mkdir(CACHE_DIR, { recursive: true });
  await fs.writeFile(CACHE_FILE, JSON.stringify(cache), 'utf-8');
}

/**
 * Update a single project entry in the cache
 * @param {string} repoName
 * @param {Object} project
 * @param {Array} commits - 30d
 * @param {Array} activity
 * @param {Array} commits365d
 * @returns {Promise<void>}
 */
async function updateProjectCacheEntry(repoName, project, commits, activity, commits365d) {
  const cache = await loadProjectCache();

  cache.projects[repoName] = {
    cached_at: new Date().toISOString(),
    project,
    commits,
    commits_365d: commits365d,
    activity,
  };

  cache.generated_at = new Date().toISOString();
  await fs.mkdir(CACHE_DIR, { recursive: true });
  await fs.writeFile(CACHE_FILE, JSON.stringify(cache), 'utf-8');
}

/**
 * Deserialize all cached project data into portal format
 * @param {Object} cache - Loaded cache object
 * @returns {Object} - { projects, recentCommits, activity, allCommits365d }
 */
function deserializeAll(cache) {
  const projects = [];
  const recentCommits = {};
  const activity = [];
  const allCommits365d = [];

  for (const [name, entry] of Object.entries(cache.projects || {})) {
    if (entry.project) projects.push(entry.project);
    if (entry.commits) recentCommits[name] = entry.commits;
    if (entry.activity) activity.push(...entry.activity);
    if (entry.commits_365d) allCommits365d.push(...entry.commits_365d);
  }

  return { projects, recentCommits, activity, allCommits365d };
}

module.exports = {
  CACHE_FILE,
  loadProjectCache,
  saveProjectCache,
  updateProjectCacheEntry,
  deserializeAll,
};
