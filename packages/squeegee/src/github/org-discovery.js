/**
 * Squeegee Org Discovery
 *
 * Orchestrates the documentation curation pipeline across all repos
 * in the Glass-Box-Solutions-Inc GitHub org.
 *
 * NEW ARCHITECTURE (docsRepo mode):
 *   1. Clone adjudica-documentation (write target)
 *   2. Fetch all non-fork, non-archived repos from the org via GitHub API
 *   3. For each source repo:
 *      - Shallow clone (read-only)
 *      - Run pipeline (analyze + generate docs)
 *      - Write output to adjudica-documentation/projects/{repo}/
 *      - Clean up source repo clone
 *   4. Commit all changes to adjudica-documentation
 *   5. Push to main
 *   6. Clean up docs repo clone
 *
 * LEGACY MODE (docsRepo.enabled: false):
 *   Original behavior — clone each repo, run pipeline, commit back, open PR.
 *
 * Security: GITHUB_PAT is sourced exclusively from env — never logged.
 * Git clone uses stdio: 'pipe' to prevent PAT leaking to stdout/stderr.
 *
 * @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
 */

'use strict';

const { execSync, spawnSync } = require('child_process');
const fs = require('fs').promises;
const path = require('path');
const { runPipeline } = require('../pipeline/index');
const { setCurrentProject, setDocsRepoOutputPath } = require('../pipeline/config');

const ORG = process.env.GITHUB_ORG || 'Glass-Box-Solutions-Inc';
const MEMORY_LIMIT_MB = parseInt(process.env.MEMORY_LIMIT_MB || '2048', 10);
const MEMORY_THRESHOLD = 0.80;

// Secret is volume-mounted at /secrets/github-pat-glassbox (auto-refreshed by Cloud Run).
// Fall back to env var for local development.
function getPAT() {
  try {
    return require('fs').readFileSync('/secrets/github-pat-glassbox', 'utf-8').trim();
  } catch {
    return process.env.GITHUB_PAT || null;
  }
}

let pipelineRunning = false;

const WORKSPACE_BASE = '/tmp/squeegee-workspace';
const STATE_FILE = '/tmp/squeegee-state.json';
const MAX_HISTORY = 10;

// Default docs repo configuration
const DOCS_REPO_CONFIG = {
  repoName: 'adjudica-documentation',
  cloneUrl: 'https://github.com/Glass-Box-Solutions-Inc/adjudica-documentation.git',
  defaultBranch: 'main',
};

/**
 * Fetch all repos for the org with pagination.
 * Returns array of { name, clone_url, default_branch }.
 */
async function fetchOrgRepos() {
  const pat = getPAT();
  if (!pat) {
    throw new Error('GitHub PAT not available (checked /secrets/github-pat-glassbox and GITHUB_PAT env)');
  }

  const repos = [];
  let page = 1;
  const perPage = 100;

  while (true) {
    const url = `https://api.github.com/orgs/${ORG}/repos?per_page=${perPage}&page=${page}&type=all`;
    const response = await fetch(url, {
      headers: {
        Authorization: `Bearer ${pat}`,
        Accept: 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
      },
    });

    if (!response.ok) {
      throw new Error(`GitHub API error ${response.status}: ${await response.text()}`);
    }

    const batch = await response.json();
    repos.push(...batch);

    // Check Link header for next page
    const link = response.headers.get('link') || '';
    if (!link.includes('rel="next"') || batch.length < perPage) break;
    page++;
  }

  // Exclude forks, archived repos, and the docs repo itself (we write to it)
  return repos
    .filter(r => !r.fork && !r.archived && r.name !== DOCS_REPO_CONFIG.repoName)
    .map(r => ({
      name: r.name,
      cloneUrl: r.clone_url,
      defaultBranch: r.default_branch || 'main',
    }));
}

/**
 * Build a squeegee.config.json object targeting a cloned repo workspace.
 * In docsRepo mode, output is redirected to docs repo via config.docsRepo.outputPath.
 */
function buildRepoConfig(workspace, repoName, docsRepoOutputPath = null) {
  const config = {
    workspace,
    version: '2.0.0',
    projects: [{ name: repoName, path: '.', stack: [] }],
    exclude: [
      '**/node_modules/**', '**/venv/**', '**/.venv/**', '**/.git/**',
      '**/dist/**', '**/build/**', '**/__pycache__/**', '**/coverage/**',
      '**/*.min.js', '**/vendor/**', '**/.next/**', '**/.svelte-kit/**',
      '**/.vercel/**', '**/.turbo/**', '**/.nuxt/**', '**/.output/**',
      '**/out/**', '**/.pytest_cache/**', '**/htmlcov/**',
    ],
    include: [],
    docTypes: {
      'CLAUDE.md': {
        required: true,
        level: 1,
        minLines: 80,
        maxLines: 150,
        requiredSections: ['Project Overview', 'Commands', 'Tech Stack', 'Architecture', 'Linked Resources Are Directives', 'GBS Core Principles', 'Context Window & Checkpoint Protocol', 'Centralized Documentation & Planning', 'Security & Secrets'],
      },
    },
    gsd: { enabled: true, planningDir: '.planning', phasesDir: '.planning/phases' },
    plans: { maxRecentPlans: 20, archiveAfterDays: 90 },
    quality: {
      thresholds: { minimum: 0.60, acceptable: 0.75, good: 0.85, excellent: 0.95 },
      weights: { completeness: 0.30, structure: 0.25, freshness: 0.15, consistency: 0.15, crossRefs: 0.15 },
      freshness: { excellent: 7, good: 30, fair: 90, poor: 180 },
    },
    triggerTables: { enabled: false },
    patternLibrary: { enabled: false },
    instructions: {},
    sectionMarkers: {
      start: (tag) => `<!-- SQUEEGEE:AUTO:START ${tag} -->`,
      end: (tag) => `<!-- SQUEEGEE:AUTO:END ${tag} -->`,
    },
    gitAnalysis: { maxCommits: 500, sinceDefault: '6 months ago' },
    changelog: { retentionDays: 90 },
    currentProject: repoName,
  };

  // Enable docsRepo mode if output path is provided
  if (docsRepoOutputPath) {
    config.docsRepo = {
      enabled: true,
      repoName: DOCS_REPO_CONFIG.repoName,
      outputPath: docsRepoOutputPath,
      autoPush: true,
    };
  }

  return config;
}

/**
 * Clone the docs repo (adjudica-documentation) as write target.
 * Returns the cloned directory path.
 */
function cloneDocsRepo() {
  const dest = path.join(WORKSPACE_BASE, DOCS_REPO_CONFIG.repoName);
  const pat = getPAT();
  const authUrl = DOCS_REPO_CONFIG.cloneUrl.replace('https://', `https://x-access-token:${pat}@`);

  const CLONE_TIMEOUT_MS = 5 * 60 * 1000;

  console.log(`📚 Cloning docs repo: ${DOCS_REPO_CONFIG.repoName}`);

  const result = spawnSync('git', [
    'clone',
    '--depth=1',
    '--branch', DOCS_REPO_CONFIG.defaultBranch,
    authUrl,
    dest,
  ], { stdio: 'pipe', timeout: CLONE_TIMEOUT_MS });

  if (result.signal === 'SIGTERM') {
    throw new Error(`Docs repo clone timed out after ${CLONE_TIMEOUT_MS / 1000}s`);
  }

  if (result.status !== 0) {
    const errMsg = result.stderr?.toString() || 'unknown error';
    throw new Error(`Docs repo clone failed: ${errMsg.replace(pat, '[REDACTED]')}`);
  }

  return dest;
}

/**
 * Shallow clone a source repo (read-only) into WORKSPACE_BASE/{name}.
 */
function cloneSourceRepo(repo) {
  const dest = path.join(WORKSPACE_BASE, repo.name);
  const pat = getPAT();
  const authUrl = repo.cloneUrl.replace('https://', `https://x-access-token:${pat}@`);

  const CLONE_TIMEOUT_MS = 5 * 60 * 1000;

  const result = spawnSync('git', [
    'clone',
    '--shallow-since=6 months ago',
    '--branch', repo.defaultBranch,
    authUrl,
    dest,
  ], { stdio: 'pipe', timeout: CLONE_TIMEOUT_MS });

  if (result.signal === 'SIGTERM') {
    throw new Error(`Clone timed out for ${repo.name} after ${CLONE_TIMEOUT_MS / 1000}s`);
  }

  if (result.status !== 0) {
    const errMsg = result.stderr?.toString() || 'unknown error';
    throw new Error(`Clone failed for ${repo.name}: ${errMsg.replace(pat, '[REDACTED]')}`);
  }

  return dest;
}

/**
 * Detect if the docs repo has any changes.
 */
function hasChanges(workdir) {
  try {
    const out = execSync('git status --porcelain', { cwd: workdir, encoding: 'utf-8', stdio: 'pipe' });
    return out.trim().length > 0;
  } catch {
    return false;
  }
}

/**
 * Commit all changes in the docs repo.
 */
function commitToDocsRepo(docsRepoPath, repoCount) {
  const timestamp = new Date().toISOString().slice(0, 19).replace('T', ' ');

  execSync('git config user.email "squeegee-bot@glassboxsolutions.com"', { cwd: docsRepoPath, stdio: 'pipe' });
  execSync('git config user.name "Squeegee Bot"', { cwd: docsRepoPath, stdio: 'pipe' });

  execSync('git add -A', { cwd: docsRepoPath, stdio: 'pipe' });

  const message = `chore(squeegee): sync project documentation [squeegee-auto]

Automated documentation sync for ${repoCount} repositories.
Generated: ${timestamp}`;

  spawnSync('git', ['commit', '-m', message], { cwd: docsRepoPath, stdio: 'pipe' });

  console.log(`✅ Committed changes to docs repo`);
}

/**
 * Push the docs repo to main.
 */
function pushDocsRepo(docsRepoPath) {
  const pat = getPAT();
  const authUrl = `https://x-access-token:${pat}@github.com/${ORG}/${DOCS_REPO_CONFIG.repoName}.git`;

  console.log(`🚀 Pushing to ${DOCS_REPO_CONFIG.repoName} main...`);

  const pushResult = spawnSync('git', ['push', authUrl, DOCS_REPO_CONFIG.defaultBranch], {
    cwd: docsRepoPath,
    stdio: 'pipe',
  });

  if (pushResult.status !== 0) {
    const errMsg = pushResult.stderr?.toString() || 'unknown';
    throw new Error(`Push to docs repo failed: ${errMsg.replace(pat, '[REDACTED]')}`);
  }

  console.log(`✅ Pushed to ${DOCS_REPO_CONFIG.repoName} main`);
}

/**
 * Clean up a cloned workspace directory.
 */
async function cleanupWorkspace(workdir) {
  try {
    await fs.rm(workdir, { recursive: true, force: true });
  } catch {
    // Non-fatal — /tmp will be cleaned by the OS eventually
  }
}

/**
 * Append a run record to the state file.
 */
async function recordRun(record) {
  let state = { runs: [] };
  try {
    const raw = await fs.readFile(STATE_FILE, 'utf-8');
    state = JSON.parse(raw);
  } catch {
    // First run
  }

  state.runs.unshift(record);
  state.runs = state.runs.slice(0, MAX_HISTORY);
  state.lastRun = record.startedAt;

  await fs.writeFile(STATE_FILE, JSON.stringify(state, null, 2), 'utf-8');
}

/**
 * Main entrypoint — runs the org pipeline in docsRepo mode.
 *
 * NEW FLOW:
 *   1. Clone docs repo (adjudica-documentation)
 *   2. For each source repo: clone → pipeline → cleanup
 *   3. Commit all changes to docs repo
 *   4. Push to main
 *
 * @param {object} options
 * @param {string|null} options.filterRepo  - If set, only curate this repo name
 * @param {string}      options.command     - Pipeline command (default: 'full')
 */
async function runOrgPipeline({ filterRepo = null, command = 'full' } = {}) {
  if (pipelineRunning) {
    console.warn('⚠️  Pipeline run already in progress — skipping concurrent invocation');
    return { status: 'skipped', reason: 'Another pipeline run is in progress' };
  }

  pipelineRunning = true;
  try {
  const startedAt = new Date().toISOString();
  const results = [];

  console.log(`\n🧽 Squeegee Org Pipeline (docsRepo mode)`);
  console.log(`   org: ${ORG}  command: ${command}${filterRepo ? `  repo: ${filterRepo}` : ''}\n`);

  // Ensure workspace base exists
  await fs.mkdir(WORKSPACE_BASE, { recursive: true });

  // Step 1: Clone docs repo
  let docsRepoPath;
  try {
    docsRepoPath = cloneDocsRepo();
  } catch (err) {
    console.error(`Failed to clone docs repo: ${err.message}`);
    await recordRun({ startedAt, status: 'error', error: err.message, results: [] });
    throw err;
  }

  // Step 2: Fetch all source repos
  let repos;
  try {
    repos = await fetchOrgRepos();
  } catch (err) {
    console.error(`Failed to fetch org repos: ${err.message}`);
    await cleanupWorkspace(docsRepoPath);
    await recordRun({ startedAt, status: 'error', error: err.message, results: [] });
    throw err;
  }

  if (filterRepo) {
    repos = repos.filter(r => r.name === filterRepo);
    if (repos.length === 0) {
      console.warn(`Repo '${filterRepo}' not found in org (or is forked/archived)`);
    }
  }

  console.log(`Processing ${repos.length} repo(s)...\n`);

  let succeeded = 0;
  let failed = 0;

  // Step 3: Process each source repo (read-only)
  for (let i = 0; i < repos.length; i++) {
    const repo = repos[i];
    const progress = `[${i + 1}/${repos.length}]`;
    const repoResult = { repo: repo.name, status: 'pending', error: null };
    let sourceWorkdir = null;

    // Memory observability — log heap and RSS before each repo
    const mem = process.memoryUsage();
    const heapMiB = (mem.heapUsed / 1024 / 1024).toFixed(0);
    const rssMiB = (mem.rss / 1024 / 1024).toFixed(0);
    console.log(`${progress} [${repo.name}] Memory: heap=${heapMiB}MiB rss=${rssMiB}MiB limit=${MEMORY_LIMIT_MB}MiB`);

    // Memory threshold check — skip repo if RSS > 80% of limit to avoid OOM kill
    const rssLimitMiB = MEMORY_LIMIT_MB * MEMORY_THRESHOLD;
    if (mem.rss / 1024 / 1024 > rssLimitMiB) {
      const msg = `RSS ${rssMiB}MiB exceeds ${Math.round(MEMORY_THRESHOLD * 100)}% of ${MEMORY_LIMIT_MB}MiB limit — skipping to avoid OOM`;
      console.error(`${progress} [${repo.name}] ${msg}`);
      repoResult.status = 'skipped';
      repoResult.error = msg;
      failed++;
      results.push(repoResult);
      continue;
    }

    try {
      console.error(`${progress} [${repo.name}] Starting clone at ${new Date().toISOString()}`);
      sourceWorkdir = cloneSourceRepo(repo);

      // Build config with docsRepo output path
      const prebuiltConfig = buildRepoConfig(sourceWorkdir, repo.name, docsRepoPath);

      console.log(`${progress} [${repo.name}] Running pipeline stage: ${command}`);
      await runPipeline(command, sourceWorkdir, prebuiltConfig);

      repoResult.status = 'processed';
      console.log(`${progress} [${repo.name}] ✓ Documentation generated`);
      succeeded++;
    } catch (err) {
      repoResult.status = 'error';
      repoResult.error = err.message;
      failed++;
      console.error(`${progress} [${repo.name}] Error — skipping: ${err.message}`);
    } finally {
      // Clean up source repo clone immediately (read-only, no longer needed)
      if (sourceWorkdir) {
        await cleanupWorkspace(sourceWorkdir);
      }
      // Release pipeline object references to help GC reclaim memory
      sourceWorkdir = null;

      // Best-effort GC between repos (requires --expose-gc flag)
      if (typeof global.gc === 'function') {
        global.gc();
      }
    }

    results.push(repoResult);
  }

  // Step 4: Commit and push docs repo if there are changes
  let pushed = false;
  try {
    if (hasChanges(docsRepoPath)) {
      console.log(`\n📝 Committing changes to docs repo...`);
      commitToDocsRepo(docsRepoPath, succeeded);
      pushDocsRepo(docsRepoPath);
      pushed = true;
    } else {
      console.log(`\n📭 No changes to commit to docs repo`);
    }
  } catch (err) {
    console.error(`Failed to commit/push docs repo: ${err.message}`);
    // Record the error but don't fail the whole run
  }

  // Step 5: Clean up docs repo
  await cleanupWorkspace(docsRepoPath);

  const summary = {
    startedAt,
    completedAt: new Date().toISOString(),
    command,
    filterRepo,
    mode: 'docsRepo',
    total: results.length,
    succeeded,
    failed,
    pushed,
    errors: results.filter(r => r.status === 'error').length,
    status: 'completed',
    results,
  };

  await recordRun(summary);

  console.log(`\n${'='.repeat(60)}`);
  console.log(`  SQUEEGEE ORG PIPELINE COMPLETE (docsRepo mode)`);
  console.log(`${'='.repeat(60)}`);
  console.log(`  Repos: ${summary.total}  |  Succeeded: ${succeeded}  |  Failed: ${failed}`);
  console.log(`  Pushed to ${DOCS_REPO_CONFIG.repoName}: ${pushed ? 'Yes' : 'No'}`);
  if (failed > 0) {
    const failedRepos = results.filter(r => r.status === 'error').map(r => r.repo);
    console.error(`  Failed repos: ${failedRepos.join(', ')}`);
  }
  console.log(`${'='.repeat(60)}\n`);

  return summary;
  } finally {
    pipelineRunning = false;
  }
}

module.exports = { runOrgPipeline };
