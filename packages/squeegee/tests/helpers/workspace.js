/**
 * Test workspace helper
 *
 * Creates temporary workspaces with realistic project fixtures for e2e testing.
 * Each project is initialized as a git repo so stages that run git commands work.
 *
 * @file tests/helpers/workspace.js
 */

const fs = require('fs');
const fsp = require('fs').promises;
const path = require('path');
const os = require('os');
const { execSync } = require('child_process');

/**
 * Create a temporary test workspace with two mock projects.
 * Each project is a git repo with an initial commit.
 *
 * @returns {Promise<string>} Path to the temp workspace directory
 */
async function createTestWorkspace() {
  const tmpDir = await fsp.mkdtemp(path.join(os.tmpdir(), 'squeegee-test-'));

  // Copy mock-project-a (Node.js)
  const projectADest = path.join(tmpDir, 'project-a');
  const projectASrc = path.join(__dirname, '..', 'fixtures', 'mock-project-a');
  await copyDirRecursive(projectASrc, projectADest);

  // Copy mock-project-b (Python)
  const projectBDest = path.join(tmpDir, 'project-b');
  const projectBSrc = path.join(__dirname, '..', 'fixtures', 'mock-project-b');
  await copyDirRecursive(projectBSrc, projectBDest);

  // Initialize git repos for each project (stages 02, 05, 06, 10 need git)
  initGitRepo(projectADest);
  initGitRepo(projectBDest);

  // Also initialize the workspace root as a git repo
  // (some stages run git commands at the workspace level)
  initGitRepo(tmpDir);

  return tmpDir;
}

/**
 * Remove a test workspace directory.
 * @param {string} dir - Path to the workspace to clean up
 */
async function cleanupWorkspace(dir) {
  if (!dir || !dir.includes('squeegee-test-')) {
    throw new Error('Refusing to delete non-test directory: ' + dir);
  }
  await fsp.rm(dir, { recursive: true, force: true });
}

/**
 * Build a squeegee config object pointing at a test workspace.
 *
 * @param {string} workspaceDir - Path to the test workspace
 * @returns {object} Config compatible with runPipeline()
 */
function buildTestConfig(workspaceDir) {
  return {
    workspace: workspaceDir,
    version: '2.0.0',
    projects: [
      { name: 'project-a', path: 'project-a', stack: [] },
      { name: 'project-b', path: 'project-b', stack: [] },
    ],
    exclude: [
      '**/node_modules/**', '**/venv/**', '**/.venv/**', '**/.git/**',
      '**/dist/**', '**/build/**', '**/__pycache__/**', '**/coverage/**',
    ],
    include: [],
    docTypes: {
      'CLAUDE.md': {
        required: true,
        level: 1,
        minLines: 80,
        maxLines: 150,
        requiredSections: [
          'Project Overview', 'Commands', 'Tech Stack', 'Architecture',
          'Linked Resources Are Directives', 'GBS Core Principles',
          'Context Window & Checkpoint Protocol', 'Centralized Documentation & Planning',
          'Security & Secrets',
        ],
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

// ─── Internal helpers ─────────────────────────────────────────────────────

/**
 * Initialize a directory as a git repo with an initial commit.
 */
function initGitRepo(dir) {
  execSync('git init', { cwd: dir, stdio: 'pipe' });
  execSync('git config user.email "test@test.com"', { cwd: dir, stdio: 'pipe' });
  execSync('git config user.name "Test User"', { cwd: dir, stdio: 'pipe' });
  execSync('git add -A', { cwd: dir, stdio: 'pipe' });
  execSync('git commit -m "initial commit"', { cwd: dir, stdio: 'pipe' });
}

/**
 * Recursively copy a directory.
 */
async function copyDirRecursive(src, dest) {
  await fsp.mkdir(dest, { recursive: true });
  const entries = await fsp.readdir(src, { withFileTypes: true });
  for (const entry of entries) {
    const srcPath = path.join(src, entry.name);
    const destPath = path.join(dest, entry.name);
    if (entry.isDirectory()) {
      await copyDirRecursive(srcPath, destPath);
    } else {
      await fsp.copyFile(srcPath, destPath);
    }
  }
}

module.exports = {
  createTestWorkspace,
  cleanupWorkspace,
  buildTestConfig,
};
