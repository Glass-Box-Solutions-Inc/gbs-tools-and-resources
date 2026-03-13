/**
 * Org Discovery E2E Tests
 *
 * Tests the GitHub org pipeline flow: repo fetching, config building,
 * clone → pipeline → write to docs repo (docsRepo mode).
 *
 * All external calls (GitHub API, git clone/push) are mocked.
 *
 * @file tests/e2e/org-discovery.test.js
 */

const path = require('path');
const childProcess = require('child_process');
const fs = require('fs').promises;

// We need to mock child_process and fetch before requiring the module
jest.mock('child_process');

// Mock the pipeline runner to avoid actually running stages
jest.mock('../../src/pipeline/index', () => ({
  runPipeline: jest.fn().mockResolvedValue(null),
}));

const { runPipeline } = require('../../src/pipeline/index');

// ─── Mock GitHub API responses ──────────────────────────────────────────

function createMockRepo(name, overrides = {}) {
  return {
    name,
    clone_url: `https://github.com/Glass-Box-Solutions-Inc/${name}.git`,
    default_branch: 'main',
    fork: false,
    archived: false,
    ...overrides,
  };
}

const MOCK_REPOS_PAGE1 = [
  createMockRepo('repo-alpha'),
  createMockRepo('repo-beta'),
  createMockRepo('repo-fork', { fork: true }),
  createMockRepo('repo-archived', { archived: true }),
];

const MOCK_REPOS_PAGE2 = [
  createMockRepo('repo-gamma'),
];

// ─── Test suite ──────────────────────────────────────────────────────────

describe('Org Discovery E2E', () => {
  let orgDiscovery;
  let originalFetch;
  let originalEnv;

  beforeAll(() => {
    // Store original env
    originalEnv = { ...process.env };
    // Set test PAT
    process.env.GITHUB_PAT = 'ghp_test_token_12345';
    process.env.GITHUB_ORG = 'Glass-Box-Solutions-Inc';
  });

  afterAll(() => {
    // Restore env
    process.env = originalEnv;
  });

  beforeEach(() => {
    jest.clearAllMocks();

    // Mock global.fetch for GitHub API
    originalFetch = global.fetch;
    global.fetch = jest.fn();

    // Reset module cache to get fresh require with mocks
    jest.isolateModules(() => {
      orgDiscovery = require('../../src/github/org-discovery');
    });
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  // ─── Repo Fetching ───────────────────────────────────────────────────

  describe('Repo Fetching', () => {
    test('fetches repos from GitHub API', async () => {
      global.fetch = jest.fn().mockResolvedValueOnce({
        ok: true,
        json: async () => MOCK_REPOS_PAGE1,
        headers: { get: () => '' }, // no Link header = single page
      });

      // Re-require with mocked fetch
      let orgMod;
      jest.isolateModules(() => {
        orgMod = require('../../src/github/org-discovery');
      });

      // Set up mock for cloneRepo (spawnSync) and hasChanges (execSync)
      childProcess.spawnSync.mockReturnValue({ status: 0, stderr: Buffer.from('') });
      childProcess.execSync.mockImplementation((cmd) => {
        if (cmd.includes('git status --porcelain')) return '';
        if (cmd.includes('git config')) return '';
        return '';
      });

      // Mock PR creation fetch to not be called (no changes)
      const result = await orgMod.runOrgPipeline({ command: 'full' });

      // Should have called GitHub API
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('api.github.com/orgs/Glass-Box-Solutions-Inc/repos'),
        expect.objectContaining({
          headers: expect.objectContaining({
            Authorization: expect.stringContaining('Bearer'),
          }),
        })
      );

      // Should filter out forks and archived repos
      expect(result.total).toBe(2); // repo-alpha and repo-beta only
    });

    test('filters out forks and archived repos', async () => {
      global.fetch = jest.fn().mockResolvedValueOnce({
        ok: true,
        json: async () => MOCK_REPOS_PAGE1,
        headers: { get: () => '' },
      });

      childProcess.spawnSync.mockReturnValue({ status: 0, stderr: Buffer.from('') });
      childProcess.execSync.mockImplementation((cmd) => {
        if (cmd.includes('git status --porcelain')) return '';
        if (cmd.includes('git config')) return '';
        return '';
      });

      let orgMod;
      jest.isolateModules(() => {
        orgMod = require('../../src/github/org-discovery');
      });

      const result = await orgMod.runOrgPipeline({ command: 'full' });

      const repoNames = result.results.map(r => r.repo);
      expect(repoNames).not.toContain('repo-fork');
      expect(repoNames).not.toContain('repo-archived');
      expect(repoNames).toContain('repo-alpha');
      expect(repoNames).toContain('repo-beta');
    });

    test('handles pagination', async () => {
      // First page with Link header indicating more pages
      global.fetch = jest.fn()
        .mockResolvedValueOnce({
          ok: true,
          json: async () => {
            // Return 100 repos to simulate "full page"
            const repos = [];
            for (let i = 0; i < 100; i++) {
              repos.push(createMockRepo(`repo-page1-${i}`));
            }
            return repos;
          },
          headers: {
            get: (name) => {
              if (name === 'link') return '<https://api.github.com/next>; rel="next"';
              return '';
            },
          },
        })
        .mockResolvedValueOnce({
          ok: true,
          json: async () => [createMockRepo('repo-page2-final')],
          headers: { get: () => '' },
        });

      childProcess.spawnSync.mockReturnValue({ status: 0, stderr: Buffer.from('') });
      childProcess.execSync.mockImplementation((cmd) => {
        if (cmd.includes('git status --porcelain')) return '';
        if (cmd.includes('git config')) return '';
        return '';
      });

      let orgMod;
      jest.isolateModules(() => {
        orgMod = require('../../src/github/org-discovery');
      });

      const result = await orgMod.runOrgPipeline({ command: 'full' });

      // Should have fetched 2 pages
      expect(global.fetch).toHaveBeenCalledTimes(2);
      // 100 from page 1 + 1 from page 2
      expect(result.total).toBe(101);
    });
  });

  // ─── Config Building ─────────────────────────────────────────────────

  describe('Config Building', () => {
    test('buildRepoConfig returns correct structure', () => {
      // Access the module-level function by re-requiring the source
      // Since buildRepoConfig is not exported, we test it indirectly
      // through the pipeline call
      global.fetch = jest.fn().mockResolvedValueOnce({
        ok: true,
        json: async () => [createMockRepo('test-repo')],
        headers: { get: () => '' },
      });

      childProcess.spawnSync.mockReturnValue({ status: 0, stderr: Buffer.from('') });
      childProcess.execSync.mockImplementation((cmd) => {
        if (cmd.includes('git status --porcelain')) return '';
        if (cmd.includes('git config')) return '';
        return '';
      });

      let orgMod;
      jest.isolateModules(() => {
        orgMod = require('../../src/github/org-discovery');
      });

      return orgMod.runOrgPipeline({ command: 'full' }).then(() => {
        // Verify runPipeline was called with a config containing required structure
        expect(runPipeline).toHaveBeenCalledWith(
          'full',
          expect.stringContaining('test-repo'),
          expect.objectContaining({
            workspace: expect.any(String),
            version: '2.0.0',
            projects: expect.arrayContaining([
              expect.objectContaining({
                name: 'test-repo',
                path: '.',
              }),
            ]),
            exclude: expect.arrayContaining(['**/node_modules/**']),
            docTypes: expect.objectContaining({
              'CLAUDE.md': expect.objectContaining({
                requiredSections: expect.arrayContaining([
                  'Project Overview',
                  'Commands',
                  'Tech Stack',
                  'Architecture',
                  'Linked Resources Are Directives',
                  'GBS Core Principles',
                  'Context Window & Checkpoint Protocol',
                  'Centralized Documentation & Planning',
                  'Security & Secrets',
                ]),
              }),
            }),
          })
        );
      });
    });
  });

  // ─── Full Org Flow (docsRepo mode) ────────────────────────────────────

  describe('Full Org Flow', () => {
    test('clones docs repo, processes source repos, commits and pushes', async () => {
      global.fetch = jest.fn()
        // First call: fetch repos
        .mockResolvedValueOnce({
          ok: true,
          json: async () => [createMockRepo('changed-repo')],
          headers: { get: () => '' },
        });

      // Mock clone success (docs repo first, then source repo)
      childProcess.spawnSync.mockReturnValue({ status: 0, stderr: Buffer.from('') });

      // Mock: git status shows changes in docs repo, git config/add/commit succeed
      childProcess.execSync.mockImplementation((cmd) => {
        if (cmd.includes('git status --porcelain')) return 'M projects/changed-repo/STATE.md\n';
        return '';
      });

      let orgMod;
      jest.isolateModules(() => {
        orgMod = require('../../src/github/org-discovery');
      });

      const result = await orgMod.runOrgPipeline({ command: 'full' });

      expect(result.pushed).toBe(true);
      expect(result.succeeded).toBe(1);
      expect(result.results[0].status).toBe('processed');
      expect(result.mode).toBe('docsRepo');
    });

    test('no-changes scenario: skips push to docs repo', async () => {
      global.fetch = jest.fn().mockResolvedValueOnce({
        ok: true,
        json: async () => [createMockRepo('unchanged-repo')],
        headers: { get: () => '' },
      });

      childProcess.spawnSync.mockReturnValue({ status: 0, stderr: Buffer.from('') });
      childProcess.execSync.mockImplementation((cmd) => {
        if (cmd.includes('git status --porcelain')) return ''; // no changes in docs repo
        return '';
      });

      let orgMod;
      jest.isolateModules(() => {
        orgMod = require('../../src/github/org-discovery');
      });

      const result = await orgMod.runOrgPipeline({ command: 'full' });

      expect(result.pushed).toBe(false);
      expect(result.succeeded).toBe(1);
      expect(result.results[0].status).toBe('processed');
    });

    test('source repo clone failure does not crash the run', async () => {
      global.fetch = jest.fn().mockResolvedValueOnce({
        ok: true,
        json: async () => [
          createMockRepo('fail-repo'),
          createMockRepo('ok-repo'),
        ],
        headers: { get: () => '' },
      });

      let cloneCount = 0;
      childProcess.spawnSync.mockImplementation((cmd, args) => {
        cloneCount++;
        // First clone is docs repo (succeeds)
        if (cloneCount === 1) {
          return { status: 0, stderr: Buffer.from('') };
        }
        // Second clone is fail-repo (fails)
        if (cloneCount === 2) {
          return { status: 1, stderr: Buffer.from('fatal: repository not found') };
        }
        // Third clone is ok-repo (succeeds), fourth is push (succeeds)
        return { status: 0, stderr: Buffer.from('') };
      });

      childProcess.execSync.mockImplementation((cmd) => {
        if (cmd.includes('git status --porcelain')) return '';
        return '';
      });

      let orgMod;
      jest.isolateModules(() => {
        orgMod = require('../../src/github/org-discovery');
      });

      const result = await orgMod.runOrgPipeline({ command: 'full' });

      expect(result.errors).toBe(1);
      expect(result.total).toBe(2);
      expect(result.succeeded).toBe(1);
      expect(result.failed).toBe(1);
      // First repo errored, second should have processed
      expect(result.results[0].status).toBe('error');
      expect(result.results[1].status).toBe('processed');
    });

    test('records run summary to state file', async () => {
      global.fetch = jest.fn().mockResolvedValueOnce({
        ok: true,
        json: async () => [createMockRepo('summary-repo')],
        headers: { get: () => '' },
      });

      childProcess.spawnSync.mockReturnValue({ status: 0, stderr: Buffer.from('') });
      childProcess.execSync.mockImplementation((cmd) => {
        if (cmd.includes('git status --porcelain')) return '';
        return '';
      });

      let orgMod;
      jest.isolateModules(() => {
        orgMod = require('../../src/github/org-discovery');
      });

      const result = await orgMod.runOrgPipeline({ command: 'full' });

      expect(result).toHaveProperty('startedAt');
      expect(result).toHaveProperty('completedAt');
      expect(result).toHaveProperty('command', 'full');
      expect(result).toHaveProperty('status', 'completed');
      expect(result).toHaveProperty('results');
    });
  });

  // ─── Security ─────────────────────────────────────────────────────────

  describe('Security', () => {
    test('PAT is not exposed in error messages (redacted)', async () => {
      const pat = process.env.GITHUB_PAT;

      global.fetch = jest.fn().mockResolvedValueOnce({
        ok: true,
        json: async () => [createMockRepo('sec-repo')],
        headers: { get: () => '' },
      });

      let cloneCount = 0;
      childProcess.spawnSync.mockImplementation((cmd, args) => {
        cloneCount++;
        // First clone is docs repo (succeeds)
        if (cloneCount === 1) {
          return { status: 0, stderr: Buffer.from('') };
        }
        // Second clone is source repo (fails with PAT in error message)
        return {
          status: 1,
          stderr: Buffer.from(`fatal: could not read from https://x-access-token:${pat}@github.com/org/repo.git`),
        };
      });

      childProcess.execSync.mockImplementation((cmd) => {
        if (cmd.includes('git status --porcelain')) return '';
        return '';
      });

      let orgMod;
      jest.isolateModules(() => {
        orgMod = require('../../src/github/org-discovery');
      });

      const result = await orgMod.runOrgPipeline({ command: 'full' });

      // The error should be recorded but PAT should be redacted
      expect(result.results[0].status).toBe('error');
      expect(result.results[0].error).not.toContain(pat);
      expect(result.results[0].error).toContain('[REDACTED]');
    });
  });
});
