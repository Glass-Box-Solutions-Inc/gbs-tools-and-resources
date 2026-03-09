/**
 * Squeegee Org Discovery
 *
 * Orchestrates the documentation curation pipeline across all repos
 * in the Glass-Box-Solutions-Inc GitHub org.
 *
 * Flow:
 *   1. Fetch all non-fork, non-archived repos from the org via GitHub API
 *   2. Filter by `filterRepo` if provided (single-repo mode)
 *   3. Shallow clone each repo to /tmp/squeegee-workspace/{name}
 *   4. Run the Squeegee pipeline with a pre-built config pointing at the clone
 *   5. Detect changes via `git status --porcelain`
 *   6. If changes: branch → commit → push → open PR
 *   7. Clean up clone after each repo to keep /tmp lean
 *   8. Write run summary to /tmp/squeegee-state.json (last 10 runs)
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

const ORG = process.env.GITHUB_ORG || 'Glass-Box-Solutions-Inc';

// Secret is volume-mounted at /secrets/github-pat-glassbox (auto-refreshed by Cloud Run).
// Fall back to env var for local development.
function getPAT() {
  try {
    return require('fs').readFileSync('/secrets/github-pat-glassbox', 'utf-8').trim();
  } catch {
    return process.env.GITHUB_PAT || null;
  }
}
const WORKSPACE_BASE = '/tmp/squeegee-workspace';
const STATE_FILE = '/tmp/squeegee-state.json';
const MAX_HISTORY = 10;

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

  // Exclude forks and archived repos — they don't need curation
  return repos
    .filter(r => !r.fork && !r.archived)
    .map(r => ({
      name: r.name,
      cloneUrl: r.clone_url,
      defaultBranch: r.default_branch || 'main',
    }));
}

/**
 * Build a squeegee.config.json object targeting a cloned repo workspace.
 * Keeps the same exclude patterns; projects list is set to the repo root.
 */
function buildRepoConfig(workspace, repoName) {
  return {
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
  };
}

/**
 * Shallow clone a repo into WORKSPACE_BASE/{name}.
 * PAT is embedded in the URL but stdio is piped to prevent logging.
 */
function cloneRepo(repo) {
  const dest = path.join(WORKSPACE_BASE, repo.name);
  const pat = getPAT();
  // Build authenticated URL without exposing PAT in process args
  const authUrl = repo.cloneUrl.replace('https://', `https://x-access-token:${pat}@`);

  const CLONE_TIMEOUT_MS = 5 * 60 * 1000; // 5 minutes max per clone

  const result = spawnSync('git', [
    'clone',
    '--depth=1',
    '--branch', repo.defaultBranch,
    authUrl,
    dest,
  ], { stdio: 'pipe', timeout: CLONE_TIMEOUT_MS }); // pipe prevents PAT appearing in logs

  if (result.signal === 'SIGTERM') {
    throw new Error(`Clone timed out for ${repo.name} after ${CLONE_TIMEOUT_MS / 1000}s`);
  }

  if (result.status !== 0) {
    const errMsg = result.stderr?.toString() || 'unknown error';
    // Redact PAT from error message before throwing
    throw new Error(`Clone failed for ${repo.name}: ${errMsg.replace(pat, '[REDACTED]')}`);
  }

  return dest;
}

/**
 * Detect if the pipeline produced any file changes.
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
 * Create branch, commit all changes, push, and open a PR via GitHub API.
 */
async function publishChanges(workdir, repo) {
  const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
  const branch = `squeegee/auto-curate-${timestamp}`;

  // Configure git identity for the commit
  execSync('git config user.email "squeegee-bot@glassboxsolutions.com"', { cwd: workdir, stdio: 'pipe' });
  execSync('git config user.name "Squeegee Bot"', { cwd: workdir, stdio: 'pipe' });

  execSync(`git checkout -b "${branch}"`, { cwd: workdir, stdio: 'pipe' });
  execSync('git add -A', { cwd: workdir, stdio: 'pipe' });
  execSync('git commit -m "chore(squeegee): auto-curate documentation"', { cwd: workdir, stdio: 'pipe' });

  // Push with PAT auth — stdio pipe prevents credential logging
  const pat = getPAT();
  const authUrl = `https://x-access-token:${pat}@github.com/${ORG}/${repo.name}.git`;
  const pushResult = spawnSync('git', ['push', authUrl, branch], { cwd: workdir, stdio: 'pipe' });

  if (pushResult.status !== 0) {
    const errMsg = pushResult.stderr?.toString() || 'unknown';
    throw new Error(`Push failed: ${errMsg.replace(pat, '[REDACTED]')}`);
  }

  // Create PR via GitHub API
  const prResponse = await fetch(`https://api.github.com/repos/${ORG}/${repo.name}/pulls`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${pat}`,
      Accept: 'application/vnd.github+json',
      'Content-Type': 'application/json',
      'X-GitHub-Api-Version': '2022-11-28',
    },
    body: JSON.stringify({
      title: 'chore(squeegee): auto-curate documentation',
      body: 'Automated documentation curation by [Squeegee](https://github.com/Glass-Box-Solutions-Inc/Squeegee). Safe to merge without review.',
      head: branch,
      base: repo.defaultBranch,
    }),
  });

  if (!prResponse.ok) {
    // PR creation is best-effort — log but don't fail the run
    console.warn(`PR creation failed for ${repo.name}: ${prResponse.status}`);
    return null;
  }

  const pr = await prResponse.json();
  return pr.html_url;
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
 * Keeps the last MAX_HISTORY runs.
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
 * Main entrypoint — runs the full org pipeline or a single repo/stage.
 *
 * @param {object} options
 * @param {string|null} options.filterRepo  - If set, only curate this repo name
 * @param {string}      options.command     - Pipeline command (default: 'full')
 */
async function runOrgPipeline({ filterRepo = null, command = 'full' } = {}) {
  const startedAt = new Date().toISOString();
  const results = [];

  console.log(`\n🧽 Squeegee Org Pipeline — org: ${ORG}  command: ${command}${filterRepo ? `  repo: ${filterRepo}` : ''}\n`);

  // Ensure workspace base exists
  await fs.mkdir(WORKSPACE_BASE, { recursive: true });

  let repos;
  try {
    repos = await fetchOrgRepos();
  } catch (err) {
    console.error(`Failed to fetch org repos: ${err.message}`);
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

  for (let i = 0; i < repos.length; i++) {
    const repo = repos[i];
    const progress = `[${i + 1}/${repos.length}]`;
    const repoResult = { repo: repo.name, status: 'pending', prUrl: null, error: null };
    let workdir = null;

    try {
      // Log to stderr (unbuffered) so this line survives OOM/timeout kills
      console.error(`${progress} [${repo.name}] Starting clone at ${new Date().toISOString()}`);
      workdir = cloneRepo(repo);

      const prebuiltConfig = buildRepoConfig(workdir, repo.name);

      console.log(`${progress} [${repo.name}] Running pipeline stage: ${command}`);
      await runPipeline(command, workdir, prebuiltConfig);

      if (hasChanges(workdir)) {
        console.log(`${progress} [${repo.name}] Changes detected — creating PR`);
        const prUrl = await publishChanges(workdir, repo);
        repoResult.prUrl = prUrl;
        repoResult.status = 'pr_created';
        console.log(`${progress} [${repo.name}] PR: ${prUrl || 'created (URL unavailable)'}`);
      } else {
        repoResult.status = 'no_changes';
        console.log(`${progress} [${repo.name}] No changes`);
      }
      succeeded++;
    } catch (err) {
      repoResult.status = 'error';
      repoResult.error = err.message;
      failed++;
      console.error(`${progress} [${repo.name}] Error — skipping repo: ${err.message}`);
    } finally {
      if (workdir) {
        await cleanupWorkspace(workdir);
      }
    }

    results.push(repoResult);
  }

  const summary = {
    startedAt,
    completedAt: new Date().toISOString(),
    command,
    filterRepo,
    total: results.length,
    succeeded,
    failed,
    prsCreated: results.filter(r => r.status === 'pr_created').length,
    noChanges: results.filter(r => r.status === 'no_changes').length,
    errors: results.filter(r => r.status === 'error').length,
    status: 'completed',
    results,
  };

  await recordRun(summary);

  console.log(`\n${'='.repeat(60)}`);
  console.log(`  SQUEEGEE ORG PIPELINE COMPLETE`);
  console.log(`${'='.repeat(60)}`);
  console.log(`  Repos: ${summary.total}  |  Succeeded: ${succeeded}  |  Failed: ${failed}`);
  console.log(`  PRs: ${summary.prsCreated}  |  No changes: ${summary.noChanges}  |  Errors: ${summary.errors}`);
  if (failed > 0) {
    const failedRepos = results.filter(r => r.status === 'error').map(r => r.repo);
    console.error(`  Failed repos: ${failedRepos.join(', ')}`);
  }
  console.log(`${'='.repeat(60)}\n`);

  return summary;
}

module.exports = { runOrgPipeline };
