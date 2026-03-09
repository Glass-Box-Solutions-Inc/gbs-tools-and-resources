/**
 * Tests for Documentation Quality Auditor Module
 *
 * @file doc-quality-auditor.test.js
 *
 * @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
 */

// Mock Octokit before requiring the module
const mockOctokitInstance = {
  repos: {
    get: jest.fn(),
    getContent: jest.fn(),
    listCommits: jest.fn()
  },
  git: {
    getTree: jest.fn()
  }
};

const MockOctokit = jest.fn(() => mockOctokitInstance);
MockOctokit.plugin = jest.fn(() => MockOctokit);

jest.mock('@octokit/rest', () => ({
  Octokit: MockOctokit
}));

jest.mock('@octokit/plugin-retry', () => ({
  retry: jest.fn()
}));

jest.mock('@octokit/plugin-throttling', () => ({
  throttling: jest.fn()
}));

const {
  audit,
  auditRepo,
  identifyKeyDocs,
  calculateCoverageScore,
  calculateOrganizationScore,
  isBackendRepo
} = require('../../intelligence/doc-quality-auditor');
const { Octokit } = require('@octokit/rest');

describe('Documentation Quality Auditor', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.spyOn(console, 'log').mockImplementation(() => {});
    jest.spyOn(console, 'warn').mockImplementation(() => {});
    jest.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  describe('identifyKeyDocs', () => {
    it('should identify README.md', () => {
      const mdFiles = [{ path: 'README.md' }];
      const result = identifyKeyDocs(mdFiles);
      expect(result.readme).toBe(true);
    });

    it('should identify CLAUDE.md', () => {
      const mdFiles = [{ path: 'CLAUDE.md' }];
      const result = identifyKeyDocs(mdFiles);
      expect(result.claude_md).toBe(true);
    });

    it('should identify CHANGELOG.md', () => {
      const mdFiles = [{ path: 'CHANGELOG.md' }];
      const result = identifyKeyDocs(mdFiles);
      expect(result.changelog).toBe(true);
    });

    it('should identify ARCHITECTURE.md', () => {
      const mdFiles = [{ path: 'ARCHITECTURE.md' }];
      const result = identifyKeyDocs(mdFiles);
      expect(result.architecture).toBe(true);
    });

    it('should identify architecture in docs folder', () => {
      const mdFiles = [{ path: 'docs/architecture/overview.md' }];
      const result = identifyKeyDocs(mdFiles);
      expect(result.architecture).toBe(true);
    });

    it('should identify TESTING.md', () => {
      const mdFiles = [{ path: 'TESTING.md' }];
      const result = identifyKeyDocs(mdFiles);
      expect(result.testing).toBe(true);
    });

    it('should identify DEPLOYMENT.md', () => {
      const mdFiles = [{ path: 'DEPLOYMENT.md' }];
      const result = identifyKeyDocs(mdFiles);
      expect(result.deployment).toBe(true);
    });

    it('should identify all docs in comprehensive repo', () => {
      const mdFiles = [
        { path: 'README.md' },
        { path: 'CLAUDE.md' },
        { path: 'CHANGELOG.md' },
        { path: 'ARCHITECTURE.md' },
        { path: 'TESTING.md' },
        { path: 'DEPLOYMENT.md' },
        { path: 'CONTRIBUTING.md' },
        { path: 'SECURITY.md' },
        { path: 'LICENSE' },
        { path: 'CODE_OF_CONDUCT.md' }
      ];
      const result = identifyKeyDocs(mdFiles);

      expect(result.readme).toBe(true);
      expect(result.claude_md).toBe(true);
      expect(result.changelog).toBe(true);
      expect(result.architecture).toBe(true);
      expect(result.testing).toBe(true);
      expect(result.deployment).toBe(true);
      expect(result.contributing).toBe(true);
      expect(result.security).toBe(true);
      expect(result.license).toBe(true);
      expect(result.code_of_conduct).toBe(true);
    });

    it('should return all false for empty repo', () => {
      const result = identifyKeyDocs([]);
      expect(result.readme).toBe(false);
      expect(result.claude_md).toBe(false);
      expect(result.changelog).toBe(false);
    });
  });

  describe('calculateCoverageScore', () => {
    it('should return 100 for fully documented frontend repo', () => {
      const docsFound = {
        readme: true,
        claude_md: true,
        changelog: true,
        testing: true
      };
      const score = calculateCoverageScore(docsFound, 'my-frontend-app');
      expect(score).toBe(100);
    });

    it('should return 100 for fully documented backend repo', () => {
      const docsFound = {
        readme: true,
        claude_md: true,
        changelog: true,
        architecture: true,
        testing: true,
        deployment: true
      };
      const score = calculateCoverageScore(docsFound, 'my-api-backend');
      expect(score).toBe(100);
    });

    it('should return 0 for completely undocumented repo', () => {
      const docsFound = {};
      const score = calculateCoverageScore(docsFound, 'my-frontend-app');
      expect(score).toBe(0);
    });

    it('should give bonus for optional docs', () => {
      // Use partial coverage so bonus points are visible (not capped at 100)
      const withOptional = {
        readme: true,
        claude_md: true,
        // missing changelog, testing - partial coverage
        contributing: true,
        security: true
      };
      const withoutOptional = {
        readme: true,
        claude_md: true
        // missing changelog, testing
      };
      const scoreWith = calculateCoverageScore(withOptional, 'my-app');
      const scoreWithout = calculateCoverageScore(withoutOptional, 'my-app');
      expect(scoreWith).toBeGreaterThan(scoreWithout);
    });

    it('should cap score at 100 with many bonus docs', () => {
      const docsFound = {
        readme: true,
        claude_md: true,
        changelog: true,
        testing: true,
        contributing: true,
        security: true,
        license: true,
        code_of_conduct: true
      };
      const score = calculateCoverageScore(docsFound, 'my-app');
      expect(score).toBeLessThanOrEqual(100);
    });
  });

  describe('calculateOrganizationScore', () => {
    it('should return 100 for well-organized docs', () => {
      const mdFiles = [
        { path: 'README.md' },
        { path: 'CLAUDE.md' },
        { path: 'docs/guide.md' }
      ];
      const score = calculateOrganizationScore(mdFiles);
      expect(score).toBe(100);
    });

    it('should penalize docs in non-standard locations', () => {
      const mdFiles = [
        { path: 'README.md' },
        { path: 'random/nested/deep/doc.md' },
        { path: 'another/random/location.md' }
      ];
      const score = calculateOrganizationScore(mdFiles);
      expect(score).toBeLessThan(100);
    });

    it('should handle empty file list', () => {
      const score = calculateOrganizationScore([]);
      expect(score).toBeGreaterThanOrEqual(0);
    });

    it('should penalize many docs without index', () => {
      const mdFiles = [
        { path: 'doc1.md' },
        { path: 'doc2.md' },
        { path: 'doc3.md' },
        { path: 'doc4.md' },
        { path: 'doc5.md' },
        { path: 'doc6.md' }
      ];
      const score = calculateOrganizationScore(mdFiles);
      expect(score).toBeLessThan(100);
    });

    it('should reward docs with index file', () => {
      const mdFiles = [
        { path: 'INDEX.md' },
        { path: 'doc1.md' },
        { path: 'doc2.md' },
        { path: 'doc3.md' },
        { path: 'doc4.md' },
        { path: 'doc5.md' },
        { path: 'doc6.md' }
      ];
      const scoreWithIndex = calculateOrganizationScore(mdFiles);

      const mdFilesNoIndex = [
        { path: 'doc1.md' },
        { path: 'doc2.md' },
        { path: 'doc3.md' },
        { path: 'doc4.md' },
        { path: 'doc5.md' },
        { path: 'doc6.md' }
      ];
      const scoreWithoutIndex = calculateOrganizationScore(mdFilesNoIndex);

      expect(scoreWithIndex).toBeGreaterThan(scoreWithoutIndex);
    });
  });

  describe('isBackendRepo', () => {
    it('should identify backend repos', () => {
      expect(isBackendRepo('my-api-server')).toBe(true);
      expect(isBackendRepo('user-service')).toBe(true);
      expect(isBackendRepo('knowledge-base')).toBe(true);
      expect(isBackendRepo('adjudica-ai-app')).toBe(true);
      expect(isBackendRepo('command-center')).toBe(true);
      expect(isBackendRepo('glassy-backend')).toBe(true);
    });

    it('should identify frontend repos', () => {
      expect(isBackendRepo('my-website')).toBe(false);
      expect(isBackendRepo('calculator')).toBe(false);
      expect(isBackendRepo('documentation')).toBe(false);
    });
  });

  describe('auditRepo - Happy Path', () => {
    it('should return high score for well-documented repo', async () => {
      // Mock repo data
      mockOctokitInstance.repos.get.mockResolvedValue({
        data: { default_branch: 'main' }
      });

      // Mock file tree with good docs
      mockOctokitInstance.git.getTree.mockResolvedValue({
        data: {
          tree: [
            { path: 'README.md', type: 'blob' },
            { path: 'CLAUDE.md', type: 'blob' },
            { path: 'CHANGELOG.md', type: 'blob' },
            { path: 'TESTING.md', type: 'blob' },
            { path: 'docs/guide.md', type: 'blob' }
          ]
        }
      });

      // Mock file content for quality check
      const goodReadme = `# My Project

This is a great project with good documentation.
It has multiple features.

## Installation

\`\`\`bash
npm install
\`\`\`

## Usage

See [docs](./docs/guide.md) for more.
`;

      mockOctokitInstance.repos.getContent.mockResolvedValue({
        data: {
          type: 'file',
          content: Buffer.from(goodReadme).toString('base64')
        }
      });

      // Mock commit history for freshness
      mockOctokitInstance.repos.listCommits.mockResolvedValue({
        data: [{
          commit: {
            author: {
              date: new Date().toISOString()
            }
          }
        }]
      });

      const config = {
        github_token: 'test-token',
        repos: ['test-repo']
      };

      const result = await auditRepo('test-repo', config);

      expect(result.repo).toBe('test-repo');
      expect(result.score).toBeGreaterThan(50);
      expect(result.breakdown).toBeDefined();
      expect(result.docs_found).toBeDefined();
      expect(result.issues).toBeDefined();
      expect(result.recommendations).toBeDefined();
    });
  });

  describe('auditRepo - Missing Docs', () => {
    it('should return low score for undocumented repo', async () => {
      mockOctokitInstance.repos.get.mockResolvedValue({
        data: { default_branch: 'main' }
      });

      // Empty repo - no docs
      mockOctokitInstance.git.getTree.mockResolvedValue({
        data: {
          tree: [
            { path: 'src/index.js', type: 'blob' }
          ]
        }
      });

      mockOctokitInstance.repos.getContent.mockRejectedValue({ status: 404 });
      mockOctokitInstance.repos.listCommits.mockResolvedValue({ data: [] });

      const config = {
        github_token: 'test-token'
      };

      const result = await auditRepo('undocumented-repo', config);

      expect(result.score).toBeLessThan(50);
      expect(result.issues.length).toBeGreaterThan(0);
      expect(result.recommendations.length).toBeGreaterThan(0);
      expect(result.issues).toContain('Missing README.md');
    });
  });

  describe('auditRepo - Error Handling', () => {
    it('should throw on missing GitHub token', async () => {
      const config = {};
      delete process.env.GITHUB_TOKEN;

      await expect(auditRepo('test-repo', config)).rejects.toThrow('GitHub token not configured');
    });

    it('should throw on 404 repo not found', async () => {
      mockOctokitInstance.repos.get.mockRejectedValue({ status: 404 });

      const config = {
        github_token: 'test-token'
      };

      await expect(auditRepo('nonexistent-repo', config)).rejects.toThrow('Repository not found');
    });
  });

  describe('audit - Multiple Repos', () => {
    it('should audit multiple repos and aggregate results', async () => {
      mockOctokitInstance.repos.get.mockResolvedValue({
        data: { default_branch: 'main' }
      });

      mockOctokitInstance.git.getTree.mockResolvedValue({
        data: {
          tree: [
            { path: 'README.md', type: 'blob' },
            { path: 'CLAUDE.md', type: 'blob' }
          ]
        }
      });

      mockOctokitInstance.repos.getContent.mockResolvedValue({
        data: {
          type: 'file',
          content: Buffer.from('# Test\n\n```code```\n[link](./)\n').toString('base64')
        }
      });

      mockOctokitInstance.repos.listCommits.mockResolvedValue({
        data: [{
          commit: { author: { date: new Date().toISOString() } }
        }]
      });

      const config = {
        github_token: 'test-token',
        repos: ['repo-a', 'repo-b', 'repo-c']
      };

      const result = await audit('2026-03-03', config);

      expect(result.repos_audited).toBe(3);
      expect(result.repos_failed).toHaveLength(0);
      expect(result.summary.total_repos).toBe(3);
      expect(result.summary.average_score).toBeGreaterThan(0);
      expect(result.details).toHaveLength(3);
    });

    it('should continue on individual repo failure', async () => {
      mockOctokitInstance.repos.get
        .mockRejectedValueOnce({ status: 404 }) // First repo fails
        .mockResolvedValue({ data: { default_branch: 'main' } }); // Others succeed

      mockOctokitInstance.git.getTree.mockResolvedValue({
        data: { tree: [{ path: 'README.md' }] }
      });

      mockOctokitInstance.repos.getContent.mockResolvedValue({
        data: {
          type: 'file',
          content: Buffer.from('# Test').toString('base64')
        }
      });

      mockOctokitInstance.repos.listCommits.mockResolvedValue({ data: [] });

      const config = {
        github_token: 'test-token',
        repos: ['failing-repo', 'good-repo']
      };

      const result = await audit('2026-03-03', config);

      expect(result.repos_failed).toHaveLength(1);
      expect(result.repos_failed[0].repo).toBe('failing-repo');
      expect(result.repos_audited).toBe(1);
    });
  });

  describe('audit - Summary Statistics', () => {
    it('should categorize repos by score', async () => {
      mockOctokitInstance.repos.get.mockResolvedValue({
        data: { default_branch: 'main' }
      });

      // Mock different documentation levels
      let callCount = 0;
      mockOctokitInstance.git.getTree.mockImplementation(() => {
        callCount++;
        if (callCount === 1) {
          // Excellent: full docs
          return {
            data: {
              tree: [
                { path: 'README.md' },
                { path: 'CLAUDE.md' },
                { path: 'CHANGELOG.md' },
                { path: 'TESTING.md' },
                { path: 'docs/guide.md' }
              ]
            }
          };
        } else {
          // Poor: minimal docs
          return {
            data: {
              tree: [{ path: 'README.md' }]
            }
          };
        }
      });

      mockOctokitInstance.repos.getContent.mockResolvedValue({
        data: {
          type: 'file',
          content: Buffer.from('# Test\n\n```bash\ntest\n```\n[link](./test)').toString('base64')
        }
      });

      mockOctokitInstance.repos.listCommits.mockResolvedValue({
        data: [{ commit: { author: { date: new Date().toISOString() } } }]
      });

      const config = {
        github_token: 'test-token',
        repos: ['excellent-repo', 'poor-repo']
      };

      const result = await audit('2026-03-03', config);

      expect(result.summary.average_score).toBeDefined();
      expect(result.summary.excellent + result.summary.good +
             result.summary.needs_work + result.summary.critical).toBe(2);
    });
  });
});
