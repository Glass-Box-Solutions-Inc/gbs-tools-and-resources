/**
 * Tests for log-writer.js
 *
 * @file log-writer.test.js
 *
 * @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
 */

const {
  write,
  generateFrontmatter,
  formatCommitsLog,
  formatPRsLog,
  formatDeploymentsLog,
  formatAgentsLog,
  formatCheckpointsLog,
  formatAnalysisLog,
  getLogFilePath
} = require('../../intelligence/log-writer');

// Mock Octokit
const mockGetContent = jest.fn();
const mockCreateOrUpdateFileContents = jest.fn();

jest.mock('@octokit/rest', () => ({
  Octokit: {
    plugin: jest.fn(() => {
      return jest.fn().mockImplementation(() => ({
        repos: {
          getContent: mockGetContent,
          createOrUpdateFileContents: mockCreateOrUpdateFileContents
        }
      }));
    })
  }
}));

jest.mock('@octokit/plugin-retry', () => ({
  retry: {}
}));

jest.mock('@octokit/plugin-throttling', () => ({
  throttling: {}
}));

describe('log-writer', () => {
  let config;

  beforeEach(() => {
    jest.clearAllMocks();

    config = {
      github_token: 'test-token',
      intelligence: {
        docs_repo: 'Glass-Box-Solutions-Inc/adjudica-documentation'
      }
    };

    jest.spyOn(console, 'log').mockImplementation(() => {});
    jest.spyOn(console, 'warn').mockImplementation(() => {});
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  describe('generateFrontmatter()', () => {
    it('should generate YAML frontmatter with defaults', () => {
      const result = generateFrontmatter('2026-03-03', 'commits');

      expect(result).toContain('generated_by: squeegee');
      expect(result).toContain('date: 2026-03-03');
      expect(result).toContain('log_type: commits');
      expect(result).toContain('sources:');
      expect(result).toContain('- github');
    });

    it('should accept custom sources', () => {
      const result = generateFrontmatter('2026-03-03', 'analysis', ['gemini', 'custom']);

      expect(result).toContain('- gemini');
      expect(result).toContain('- custom');
    });
  });

  describe('formatCommitsLog()', () => {
    it('should format commits with summary and repo breakdown', () => {
      const data = {
        repos: {
          'repo-a': {
            commits: [
              { sha: 'abc123def456', message: 'feat: add feature', author: 'Alice' },
              { sha: 'def456abc123', message: 'fix: bug fix', author: 'Bob' }
            ],
            pull_requests: [],
            issues: [],
            ci_runs: []
          }
        },
        summary: { total_commits: 2, total_prs: 0, total_issues: 0, total_ci_runs: 0 }
      };

      const result = formatCommitsLog(data, '2026-03-03');

      expect(result).toContain('# GitHub Commit Activity - 2026-03-03');
      expect(result).toContain('**Total Commits**: 2');
      expect(result).toContain('### repo-a (2 commits)');
      expect(result).toContain('[`abc123d`]');
      expect(result).toContain('feat: add feature');
      expect(result).toContain('Alice');
    });

    it('should handle empty commits', () => {
      const data = {
        repos: {},
        summary: { total_commits: 0, total_prs: 0, total_issues: 0, total_ci_runs: 0 }
      };

      const result = formatCommitsLog(data, '2026-03-03');

      expect(result).toContain('*No commits on this date.*');
    });

    it('should identify top contributor', () => {
      const data = {
        repos: {
          'repo-a': {
            commits: [
              { sha: 'a', message: 'msg', author: 'Alice' },
              { sha: 'b', message: 'msg', author: 'Alice' },
              { sha: 'c', message: 'msg', author: 'Bob' }
            ],
            pull_requests: [],
            issues: [],
            ci_runs: []
          }
        },
        summary: { total_commits: 3, total_prs: 0, total_issues: 0, total_ci_runs: 0 }
      };

      const result = formatCommitsLog(data, '2026-03-03');

      expect(result).toContain('**Top Contributor**: Alice (2 commits)');
    });
  });

  describe('formatPRsLog()', () => {
    it('should format PRs with state breakdown', () => {
      const data = {
        repos: {
          'repo-a': {
            commits: [],
            pull_requests: [
              { number: 1, title: 'PR 1', author: 'Alice', state: 'merged', labels: ['feature'] },
              { number: 2, title: 'PR 2', author: 'Bob', state: 'open', labels: [] }
            ],
            issues: [],
            ci_runs: []
          }
        },
        summary: { total_commits: 0, total_prs: 2, total_issues: 0, total_ci_runs: 0 }
      };

      const result = formatPRsLog(data, '2026-03-03');

      expect(result).toContain('# GitHub Pull Request Activity - 2026-03-03');
      expect(result).toContain('**Total PRs**: 2');
      expect(result).toContain('**Merged**: 1');
      expect(result).toContain('**Opened**: 1');
      expect(result).toContain('✅ #1: PR 1 [feature]');
      expect(result).toContain('🟢 #2: PR 2');
    });

    it('should handle empty PRs', () => {
      const data = {
        repos: {},
        summary: { total_commits: 0, total_prs: 0, total_issues: 0, total_ci_runs: 0 }
      };

      const result = formatPRsLog(data, '2026-03-03');

      expect(result).toContain('*No pull request activity on this date.*');
    });
  });

  describe('formatDeploymentsLog()', () => {
    it('should format deployments by project', () => {
      const data = {
        deployments: [
          { project: 'proj-a', service: 'svc-1', revision: 'rev-001', status: 'success', timestamp: '2026-03-03T10:00:00Z' },
          { project: 'proj-a', service: 'svc-2', revision: 'rev-002', status: 'failed', timestamp: '2026-03-03T11:00:00Z' }
        ],
        errors: [],
        summary: { total_deployments: 2, total_errors: 0, projects_monitored: 1 }
      };

      const result = formatDeploymentsLog(data, '2026-03-03');

      expect(result).toContain('# GCP Cloud Run Deployments - 2026-03-03');
      expect(result).toContain('**Total Deployments**: 2');
      expect(result).toContain('**Successful**: 1');
      expect(result).toContain('**Failed**: 1');
      expect(result).toContain('### proj-a');
      expect(result).toContain('✅ **svc-1**');
      expect(result).toContain('❌ **svc-2**');
    });

    it('should handle empty deployments', () => {
      const data = {
        deployments: [],
        errors: [],
        summary: { total_deployments: 0, total_errors: 0, projects_monitored: 0 }
      };

      const result = formatDeploymentsLog(data, '2026-03-03');

      expect(result).toContain('*No deployments on this date.*');
    });
  });

  describe('formatAgentsLog()', () => {
    it('should format agent sessions', () => {
      const data = {
        claude_code_sessions: [
          { project_name: 'my-project', session_id: 's1', memory_files_count: 5, estimated_tokens: 12000 }
        ],
        cursor_active: true,
        squeegee_state: { last_run: '2026-03-03T07:00:00Z', repos_processed: 27 }
      };

      const result = formatAgentsLog(data, '2026-03-03');

      expect(result).toContain('# Development Agent Activity - 2026-03-03');
      expect(result).toContain('**Claude Code Sessions**: 1');
      expect(result).toContain('**Cursor Active**: Yes');
      expect(result).toContain('### my-project');
      expect(result).toContain('**Session ID**: s1');
      expect(result).toContain('**Memory Files**: 5');
      expect(result).toContain('**Estimated Tokens**: 12,000');
    });

    it('should handle no sessions', () => {
      const data = {
        claude_code_sessions: [],
        cursor_active: false,
        squeegee_state: {}
      };

      const result = formatAgentsLog(data, '2026-03-03');

      expect(result).toContain('*No Claude Code sessions detected.*');
      expect(result).toContain('**Cursor Active**: No');
    });
  });

  describe('formatCheckpointsLog()', () => {
    it('should format checkpoint events', () => {
      const checkpoints = [
        { repo: 'repo-a', user: 'alice', context_pct: 62, phase: 'Phase 1', timestamp: '2026-03-03T14:00:00Z' },
        { repo: 'repo-a', user: 'bob', context_pct: 75, phase: 'Phase 2', timestamp: '2026-03-03T15:00:00Z' }
      ];

      const result = formatCheckpointsLog(checkpoints, '2026-03-03');

      expect(result).toContain('# Context Checkpoint Events - 2026-03-03');
      expect(result).toContain('**Total Checkpoints**: 2');
      expect(result).toContain('### repo-a');
      expect(result).toContain('**Phase**: Phase 1');
      expect(result).toContain('**Context Window**: 62%');
    });

    it('should handle empty checkpoints', () => {
      const result = formatCheckpointsLog([], '2026-03-03');

      expect(result).toContain('*No checkpoint events on this date.*');
    });
  });

  describe('formatAnalysisLog()', () => {
    it('should format Gemini briefing', () => {
      const briefing = {
        executive_summary: ['Summary point 1', 'Summary point 2'],
        repository_activity: 'Repo activity details',
        deployment_events: 'Deployment details',
        development_activity: 'Dev activity',
        context_checkpoints: 'Checkpoint info',
        observations: 'Key observations',
        generated_at: '2026-03-03T12:00:00Z'
      };

      const result = formatAnalysisLog(briefing, '2026-03-03');

      expect(result).toContain('# Glass Box Intelligence Briefing - 2026-03-03');
      expect(result).toContain('## Executive Summary');
      expect(result).toContain('- Summary point 1');
      expect(result).toContain('## Repository Activity');
      expect(result).toContain('## Curator Observations & Recommendations');
    });

    it('should handle empty sections', () => {
      const briefing = {
        executive_summary: [],
        generated_at: '2026-03-03T12:00:00Z'
      };

      const result = formatAnalysisLog(briefing, '2026-03-03');

      expect(result).toContain('# Glass Box Intelligence Briefing - 2026-03-03');
      expect(result).not.toContain('## Executive Summary');
    });
  });

  describe('getLogFilePath()', () => {
    it('should return correct path for commits', () => {
      expect(getLogFilePath('commits', '2026-03-03')).toBe('logs/commits/2026/03/2026-03-03.md');
    });

    it('should return correct path for prs (using pull_requests directory)', () => {
      expect(getLogFilePath('prs', '2026-03-03')).toBe('logs/pull_requests/2026/03/2026-03-03.md');
    });

    it('should return correct path for analysis', () => {
      expect(getLogFilePath('analysis', '2026-12-25')).toBe('logs/analysis/2026/12/2026-12-25.md');
    });

    it('should handle unknown log types gracefully', () => {
      expect(getLogFilePath('custom', '2026-03-03')).toBe('logs/custom/2026/03/2026-03-03.md');
    });
  });

  describe('write()', () => {
    const sampleData = {
      repos: {
        'repo-a': {
          commits: [{ sha: 'abc123', message: 'test', author: 'Alice' }],
          pull_requests: [],
          issues: [],
          ci_runs: []
        }
      },
      summary: { total_commits: 1, total_prs: 0, total_issues: 0, total_ci_runs: 0 }
    };

    it('should write a new file when it does not exist', async () => {
      mockGetContent.mockRejectedValue({ status: 404 });
      mockCreateOrUpdateFileContents.mockResolvedValue({
        data: {
          commit: {
            sha: 'commit-sha-123',
            html_url: 'https://github.com/test/commit/123'
          }
        }
      });

      const result = await write(sampleData, 'commits', '2026-03-03', config);

      expect(result.success).toBe(true);
      expect(result.file_path).toBe('logs/commits/2026/03/2026-03-03.md');
      expect(result.commit_sha).toBe('commit-sha-123');
      expect(mockCreateOrUpdateFileContents).toHaveBeenCalledWith(
        expect.objectContaining({
          owner: 'Glass-Box-Solutions-Inc',
          repo: 'adjudica-documentation',
          path: 'logs/commits/2026/03/2026-03-03.md',
          message: 'chore: update commits log for 2026-03-03'
        })
      );
    });

    it('should update existing file with SHA', async () => {
      mockGetContent.mockResolvedValue({ data: { sha: 'existing-sha' } });
      mockCreateOrUpdateFileContents.mockResolvedValue({
        data: {
          commit: {
            sha: 'new-commit-sha',
            html_url: 'https://github.com/test/commit/456'
          }
        }
      });

      const result = await write(sampleData, 'commits', '2026-03-03', config);

      expect(result.success).toBe(true);
      expect(mockCreateOrUpdateFileContents).toHaveBeenCalledWith(
        expect.objectContaining({
          sha: 'existing-sha'
        })
      );
    });

    it('should throw error if GitHub token missing', async () => {
      const badConfig = { intelligence: { docs_repo: 'owner/repo' } };

      await expect(write(sampleData, 'commits', '2026-03-03', badConfig))
        .rejects.toThrow('GitHub token not configured');
    });

    it('should accept Date object', async () => {
      mockGetContent.mockRejectedValue({ status: 404 });
      mockCreateOrUpdateFileContents.mockResolvedValue({
        data: { commit: { sha: 'abc', html_url: 'url' } }
      });

      const result = await write(sampleData, 'commits', new Date('2026-03-03'), config);

      expect(result.success).toBe(true);
      expect(result.file_path).toContain('2026-03-03');
    });

    it('should throw error for unknown log type', async () => {
      await expect(write(sampleData, 'unknown', '2026-03-03', config))
        .rejects.toThrow('Unknown log type: unknown');
    });

    it('should write deployments log', async () => {
      const deploymentData = {
        deployments: [
          { project: 'proj', service: 'svc', revision: 'rev', status: 'success', timestamp: '2026-03-03T10:00:00Z' }
        ],
        errors: [],
        summary: { total_deployments: 1, total_errors: 0, projects_monitored: 1 }
      };

      mockGetContent.mockRejectedValue({ status: 404 });
      mockCreateOrUpdateFileContents.mockResolvedValue({
        data: { commit: { sha: 'abc', html_url: 'url' } }
      });

      const result = await write(deploymentData, 'deployments', '2026-03-03', config);

      expect(result.success).toBe(true);
      expect(result.file_path).toBe('logs/deployments/2026/03/2026-03-03.md');
    });

    it('should write analysis log', async () => {
      const analysisData = {
        executive_summary: ['Summary'],
        repository_activity: 'Activity',
        generated_at: '2026-03-03T12:00:00Z'
      };

      mockGetContent.mockRejectedValue({ status: 404 });
      mockCreateOrUpdateFileContents.mockResolvedValue({
        data: { commit: { sha: 'abc', html_url: 'url' } }
      });

      const result = await write(analysisData, 'analysis', '2026-03-03', config);

      expect(result.success).toBe(true);
      expect(result.file_path).toBe('logs/analysis/2026/03/2026-03-03.md');
    });
  });
});
