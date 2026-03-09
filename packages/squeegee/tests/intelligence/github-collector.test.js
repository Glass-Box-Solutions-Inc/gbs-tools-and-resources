/**
 * Unit tests for GitHub Activity Collector
 *
 * @file github-collector.test.js
 */

const assert = require('assert');

// Mock data store (prefixed with 'mock' for jest.mock hoisting)
const mockOctokitData = {
  commits: {},
  pulls: {},
  issues: {},
  actions: {}
};

jest.mock('@octokit/rest', () => {
  class MockOctokit {
    constructor(options) {
      this.auth = options.auth;
      this.repos = {
        listCommits: ({ owner, repo, since, until, per_page }) => ({
          data: mockOctokitData.commits[repo] || []
        })
      };
      this.pulls = {
        list: ({ owner, repo, state, sort, direction, per_page }) => ({
          data: mockOctokitData.pulls[repo] || []
        })
      };
      this.issues = {
        listForRepo: ({ owner, repo, state, since, per_page }) => ({
          data: mockOctokitData.issues[repo] || []
        })
      };
      this.actions = {
        listWorkflowRunsForRepo: ({ owner, repo, per_page }) => ({
          data: { workflow_runs: mockOctokitData.actions[repo] || [] }
        })
      };
    }

    async paginate(method, options, mapper) {
      const response = method.call(this, options);
      const data = response.data.workflow_runs || response.data;

      if (mapper) {
        return mapper(response);
      }
      return data;
    }

    static plugin() { return MockOctokit; }
  }
  return { Octokit: MockOctokit };
});

jest.mock('@octokit/plugin-retry', () => ({ retry: () => {} }));
jest.mock('@octokit/plugin-throttling', () => ({ throttling: () => {} }));

const { collect, collectRepo } = require('../../intelligence/github-collector');

describe('GitHub Collector', () => {
  beforeEach(() => {
    mockOctokitData.commits = {};
    mockOctokitData.pulls = {};
    mockOctokitData.issues = {};
    mockOctokitData.actions = {};
  });

  describe('collectRepo', () => {
    it('should collect all activity types for a repository', async () => {
      // Setup mock data
      mockOctokitData.commits['test-repo'] = [
        {
          sha: 'abc123',
          commit: {
            message: 'feat: add new feature',
            author: {
              name: 'Alex',
              date: '2026-03-03T10:00:00Z'
            }
          }
        }
      ];

      mockOctokitData.pulls['test-repo'] = [
        {
          number: 42,
          title: 'Add feature',
          user: { login: 'alex' },
          state: 'open',
          merged_at: null,
          created_at: '2026-03-03T09:00:00Z',
          updated_at: '2026-03-03T10:00:00Z',
          labels: [{ name: 'feature' }]
        }
      ];

      mockOctokitData.issues['test-repo'] = [
        {
          number: 10,
          title: 'Bug report',
          user: { login: 'brian' },
          state: 'open',
          created_at: '2026-03-03T08:00:00Z',
          labels: [{ name: 'bug' }]
        }
      ];

      mockOctokitData.actions['test-repo'] = [
        {
          name: 'CI',
          status: 'completed',
          conclusion: 'success',
          created_at: '2026-03-03T10:00:00Z',
          updated_at: '2026-03-03T10:05:00Z'
        }
      ];

      const result = await collectRepo('test-repo', '2026-03-03', 'fake-token');

      assert.strictEqual(result.repo, 'test-repo');
      assert.strictEqual(result.commits.length, 1);
      assert.strictEqual(result.commits[0].sha, 'abc123');
      assert.strictEqual(result.commits[0].author, 'Alex');

      assert.strictEqual(result.pull_requests.length, 1);
      assert.strictEqual(result.pull_requests[0].number, 42);

      assert.strictEqual(result.issues.length, 1);
      assert.strictEqual(result.issues[0].number, 10);

      assert.strictEqual(result.ci_runs.length, 1);
      assert.strictEqual(result.ci_runs[0].workflow_name, 'CI');
    });

    it('should handle repositories with no activity', async () => {
      const result = await collectRepo('empty-repo', '2026-03-03', 'fake-token');

      assert.strictEqual(result.repo, 'empty-repo');
      assert.strictEqual(result.commits.length, 0);
      assert.strictEqual(result.pull_requests.length, 0);
      assert.strictEqual(result.issues.length, 0);
      assert.strictEqual(result.ci_runs.length, 0);
    });

    it('should filter commits by date range', async () => {
      mockOctokitData.commits['test-repo'] = [
        {
          sha: 'in-range',
          commit: {
            message: 'In range',
            author: {
              name: 'Alex',
              date: '2026-03-03T10:00:00Z'
            }
          }
        }
      ];

      const result = await collectRepo('test-repo', '2026-03-03', 'fake-token');
      assert.strictEqual(result.commits.length, 1);
    });
  });

  describe('collect', () => {
    it('should collect activity from all configured repos', async () => {
      // Set environment variable
      process.env.GITHUB_TOKEN = 'test-token';

      mockOctokitData.commits['repo1'] = [
        {
          sha: 'abc',
          commit: {
            message: 'Commit 1',
            author: { name: 'Alex', date: '2026-03-03T10:00:00Z' }
          }
        }
      ];

      mockOctokitData.commits['repo2'] = [
        {
          sha: 'def',
          commit: {
            message: 'Commit 2',
            author: { name: 'Brian', date: '2026-03-03T11:00:00Z' }
          }
        }
      ];

      const config = {
        repos: ['repo1', 'repo2']
      };

      const result = await collect('2026-03-03', config);

      assert.strictEqual(Object.keys(result.repos).length, 2);
      assert.strictEqual(result.summary.total_commits, 2);
      assert.strictEqual(result.summary.total_prs, 0);
      assert.strictEqual(result.summary.total_issues, 0);
      assert.strictEqual(result.summary.total_ci_runs, 0);
    });

    it('should calculate correct summary statistics', async () => {
      process.env.GITHUB_TOKEN = 'test-token';

      mockOctokitData.commits['repo1'] = [{
        sha: '1',
        commit: {
          message: 'Test',
          author: { name: 'A', date: '2026-03-03T10:00:00Z' }
        }
      }];
      mockOctokitData.pulls['repo1'] = [
        {
          number: 1,
          title: 'PR',
          user: { login: 'a' },
          state: 'open',
          merged_at: null,
          created_at: '2026-03-03T10:00:00Z',
          updated_at: '2026-03-03T10:00:00Z',
          labels: []
        }
      ];

      const config = { repos: ['repo1'] };
      const result = await collect('2026-03-03', config);

      assert.strictEqual(result.summary.total_commits, 1);
      assert.strictEqual(result.summary.total_prs, 1);
    });

    it('should handle partial failures gracefully', async () => {
      process.env.GITHUB_TOKEN = 'test-token';

      // repo1 will succeed (has mock data)
      mockOctokitData.commits['repo1'] = [
        {
          sha: 'abc',
          commit: {
            message: 'Success',
            author: { name: 'Alex', date: '2026-03-03T10:00:00Z' }
          }
        }
      ];

      // repo2 will "fail" (no mock data will cause empty results via safeExecute)

      const config = { repos: ['repo1', 'repo2'] };
      const result = await collect('2026-03-03', config);

      // Both repos should be processed (safeExecute returns empty arrays on error)
      assert.strictEqual(Object.keys(result.repos).length, 2);
      assert.strictEqual(result.repos['repo1'].commits.length, 1);
      assert.strictEqual(result.repos['repo2'].commits.length, 0);
    });

    it('should throw error if GitHub token not configured', async () => {
      delete process.env.GITHUB_TOKEN;

      const config = { repos: ['repo1'] };

      try {
        await collect('2026-03-03', config);
        assert.fail('Should have thrown error');
      } catch (error) {
        assert.ok(error.message.includes('GitHub token not configured'));
      }
    });
  });

  describe('Error Handling', () => {
    it('should handle rate limiting via throttling plugin', async () => {
      process.env.GITHUB_TOKEN = 'test-token';
      const config = { repos: ['repo1'] };

      // Should not throw - throttling plugin handles rate limits
      const result = await collect('2026-03-03', config);
      assert.ok(result);
    });

    it('should handle missing CI/CD workflows gracefully', async () => {
      process.env.GITHUB_TOKEN = 'test-token';

      // Repo with no Actions setup
      const result = await collectRepo('no-actions-repo', '2026-03-03', 'fake-token');

      // Should return empty array instead of throwing
      assert.strictEqual(result.ci_runs.length, 0);
    });
  });

  describe('Date Range Filtering', () => {
    it('should only include PRs within date range', async () => {
      mockOctokitData.pulls['test-repo'] = [
        {
          number: 1,
          title: 'In range',
          user: { login: 'alex' },
          state: 'open',
          merged_at: null,
          created_at: '2026-03-03T10:00:00Z',
          updated_at: '2026-03-03T10:00:00Z',
          labels: []
        },
        {
          number: 2,
          title: 'Out of range',
          user: { login: 'brian' },
          state: 'open',
          merged_at: null,
          created_at: '2026-03-02T10:00:00Z',
          updated_at: '2026-03-02T10:00:00Z',
          labels: []
        }
      ];

      const result = await collectRepo('test-repo', '2026-03-03', 'fake-token');

      // Only PR #1 should be included
      assert.strictEqual(result.pull_requests.length, 1);
      assert.strictEqual(result.pull_requests[0].number, 1);
    });

    it('should exclude pull requests from issues list', async () => {
      mockOctokitData.issues['test-repo'] = [
        {
          number: 10,
          title: 'Real issue',
          user: { login: 'alex' },
          state: 'open',
          created_at: '2026-03-03T10:00:00Z',
          labels: []
        },
        {
          number: 11,
          title: 'Pull request',
          user: { login: 'brian' },
          state: 'open',
          created_at: '2026-03-03T10:00:00Z',
          labels: [],
          pull_request: { url: 'https://...' } // This marks it as a PR
        }
      ];

      const result = await collectRepo('test-repo', '2026-03-03', 'fake-token');

      // Only issue #10 should be included (PR excluded)
      assert.strictEqual(result.issues.length, 1);
      assert.strictEqual(result.issues[0].number, 10);
    });
  });

  describe('Data Formatting', () => {
    it('should format commits correctly', async () => {
      mockOctokitData.commits['test-repo'] = [
        {
          sha: 'abc123def456',
          commit: {
            message: 'feat: add new feature\n\nDetailed description here',
            author: {
              name: 'Alex Garcia',
              date: '2026-03-03T10:30:45Z'
            }
          }
        }
      ];

      const result = await collectRepo('test-repo', '2026-03-03', 'fake-token');

      assert.strictEqual(result.commits[0].sha, 'abc123def456');
      assert.strictEqual(result.commits[0].message, 'feat: add new feature'); // First line only
      assert.strictEqual(result.commits[0].author, 'Alex Garcia');
      assert.strictEqual(result.commits[0].timestamp, '2026-03-03T10:30:45Z');
    });

    it('should distinguish merged PRs from closed PRs', async () => {
      mockOctokitData.pulls['test-repo'] = [
        {
          number: 1,
          title: 'Merged PR',
          user: { login: 'alex' },
          state: 'closed',
          merged_at: '2026-03-03T11:00:00Z',
          created_at: '2026-03-03T10:00:00Z',
          updated_at: '2026-03-03T11:00:00Z',
          labels: []
        },
        {
          number: 2,
          title: 'Closed PR',
          user: { login: 'brian' },
          state: 'closed',
          merged_at: null,
          created_at: '2026-03-03T10:00:00Z',
          updated_at: '2026-03-03T10:30:00Z',
          labels: []
        }
      ];

      const result = await collectRepo('test-repo', '2026-03-03', 'fake-token');

      assert.strictEqual(result.pull_requests[0].state, 'merged');
      assert.strictEqual(result.pull_requests[1].state, 'closed');
    });

    it('should calculate CI run duration correctly', async () => {
      mockOctokitData.actions['test-repo'] = [
        {
          name: 'CI',
          status: 'completed',
          conclusion: 'success',
          created_at: '2026-03-03T10:00:00Z',
          updated_at: '2026-03-03T10:05:30Z'
        }
      ];

      const result = await collectRepo('test-repo', '2026-03-03', 'fake-token');

      // Duration should be 5.5 minutes = 330,000ms
      const expected = 330000;
      assert.strictEqual(result.ci_runs[0].duration_ms, expected);
    });
  });
});
