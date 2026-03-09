/**
 * Stage 02: Git Analysis Engine
 *
 * The core of the rebuilt pipeline. Extracts commits, diffs, and dependency
 * changes per project since the last Squeegee run.
 *
 * @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
 */

const { execSync } = require('child_process');
const path = require('path');
const { log, readJsonSafe } = require('../utils');
const { resolveProjectPath } = require('../config');

/**
 * Run git analysis for all projects.
 *
 * Reads .squeegee-state.json for the last run hash/timestamp.
 * Extracts commits, file changes, and dependency diffs since then.
 */
async function run(config, _discovery) {
  log('Stage 2: Analyzing git history...', 'info');

  const statePath = path.join(config.workspace, '.squeegee-state.json');
  const state = await readJsonSafe(statePath, { lastRun: null, lastHash: null, projects: {} });

  const sinceArg = state.lastRun
    ? `--since="${state.lastRun}"`
    : `--since="${config.gitAnalysis.sinceDefault}"`;

  const results = {
    global: getGlobalGitInfo(config),
    projects: {},
  };

  for (const project of config.projects) {
    const projectPath = project.path;
    const absPath = resolveProjectPath(config, projectPath);

    try {
      const commits = getCommits(config.workspace, projectPath, sinceArg, config.gitAnalysis.maxCommits);
      const fileChanges = state.lastHash
        ? getFileChanges(config.workspace, projectPath, state.lastHash)
        : [];

      results.projects[project.name] = {
        path: projectPath,
        commits,
        fileChanges,
        commitCount: commits.length,
        filesChanged: fileChanges.length,
        hasActivity: commits.length > 0,
      };
    } catch (e) {
      results.projects[project.name] = {
        path: projectPath,
        commits: [],
        fileChanges: [],
        commitCount: 0,
        filesChanged: 0,
        hasActivity: false,
        error: e.message,
      };
    }
  }

  const activeCount = Object.values(results.projects).filter(p => p.hasActivity).length;
  log(`Git analysis complete: ${activeCount} active projects`, 'success');

  return results;
}

function getGlobalGitInfo(config) {
  try {
    const headHash = execSync('git rev-parse HEAD', {
      cwd: config.workspace,
      encoding: 'utf-8',
      stdio: ['pipe', 'pipe', 'ignore'],
    }).trim();

    const branch = execSync('git rev-parse --abbrev-ref HEAD', {
      cwd: config.workspace,
      encoding: 'utf-8',
      stdio: ['pipe', 'pipe', 'ignore'],
    }).trim();

    return { headHash, branch };
  } catch {
    return { headHash: null, branch: null };
  }
}

/**
 * Get commits for a project path.
 * Returns array of { hash, date, author, subject, type, scope }.
 */
function getCommits(workspace, projectPath, sinceArg, maxCommits) {
  try {
    const raw = execSync(
      `git log --format="%H|%aI|%an|%s" ${sinceArg} --max-count=${maxCommits}`,
      { cwd: path.join(workspace, projectPath), encoding: 'utf-8', maxBuffer: 10 * 1024 * 1024, stdio: ['pipe', 'pipe', 'ignore'] }
    ).trim();

    if (!raw) return [];

    return raw.split('\n').filter(Boolean).map(line => {
      const [hash, date, author, ...subjectParts] = line.split('|');
      const subject = subjectParts.join('|');

      // Parse conventional commit format
      const ccMatch = subject.match(/^(\w+)(?:\(([^)]+)\))?:\s*(.+)/);
      return {
        hash,
        date,
        author,
        subject,
        type: ccMatch ? ccMatch[1] : null,
        scope: ccMatch ? ccMatch[2] : null,
        description: ccMatch ? ccMatch[3] : subject,
      };
    });
  } catch {
    return [];
  }
}

/**
 * Get files changed since a specific commit hash.
 * Returns array of { status, file }.
 */
function getFileChanges(workspace, projectPath, sinceHash) {
  try {
    const raw = execSync(
      `git diff --name-status ${sinceHash}..HEAD`,
      { cwd: path.join(workspace, projectPath), encoding: 'utf-8', maxBuffer: 10 * 1024 * 1024, stdio: ['pipe', 'pipe', 'ignore'] }
    ).trim();

    if (!raw) return [];

    return raw.split('\n').filter(Boolean).map(line => {
      const [status, ...fileParts] = line.split('\t');
      return { status, file: fileParts.join('\t') };
    });
  } catch {
    return [];
  }
}

module.exports = { run };
