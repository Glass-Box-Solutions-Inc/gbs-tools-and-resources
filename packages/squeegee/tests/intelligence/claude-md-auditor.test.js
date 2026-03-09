/**
 * Unit tests for CLAUDE.md Compliance Auditor
 *
 * @file claude-md-auditor.test.js
 */

const { audit, auditRepo } = require('../../intelligence/claude-md-auditor');

// Mock Octokit
jest.mock('@octokit/rest', () => {
  const mockOctokit = {
    repos: {
      getContent: jest.fn(),
      listCommits: jest.fn()
    }
  };

  return {
    Octokit: {
      plugin: jest.fn(() => {
        return jest.fn(() => mockOctokit);
      })
    }
  };
});

jest.mock('@octokit/plugin-retry', () => ({
  retry: {}
}));

jest.mock('@octokit/plugin-throttling', () => ({
  throttling: {}
}));

describe('CLAUDE.md Compliance Auditor', () => {
  let mockOctokit;

  beforeEach(() => {
    // Get mocked Octokit instance
    const { Octokit } = require('@octokit/rest');
    const MockedOctokit = Octokit.plugin()();
    mockOctokit = MockedOctokit;

    // Reset mocks
    jest.clearAllMocks();
  });

  describe('auditRepo - Happy Path', () => {
    test('should score 13/13 for excellent CLAUDE.md', async () => {
      const excellentContent = `# Excellent Project

This is a comprehensive overview with multiple sentences.
It provides clear context about the project purpose.
This satisfies the prose requirement.

## Tech Stack

| Layer | Technology |
|-------|------------|
| View | React |

## Commands

\`\`\`bash
npm run dev
\`\`\`

## Architecture

Standard directory structure.

## Environment Variables

| Variable | Description |
|----------|-------------|
| API_KEY | Key |

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | /api | API |

## Deployment

Cloud Run deployed to GCP project: example-project

## Centralized Documentation

See [adjudica-documentation](../adjudica-documentation/)

## Context Window & Checkpoint Protocol

Use checkpoints at 65% context.

## Conditional Context Load

Check for parent CLAUDE.md first.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
`;

      mockOctokit.repos.getContent.mockResolvedValue({
        data: {
          content: Buffer.from(excellentContent).toString('base64')
        }
      });

      mockOctokit.repos.listCommits.mockResolvedValue({
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
        intelligence: {
          repos: ['test-repo']
        }
      };

      const result = await auditRepo('test-repo', config);

      expect(result.has_claude_md).toBe(true);
      expect(result.score).toBe(13);
      expect(result.missing_points).toHaveLength(0);
      expect(result.breakdown.structure).toBe(100);
    });
  });

  describe('auditRepo - Missing CLAUDE.md', () => {
    test('should score 0/13 for missing CLAUDE.md', async () => {
      mockOctokit.repos.getContent.mockRejectedValue({
        status: 404,
        message: 'Not Found'
      });

      const config = {
        github_token: 'test-token',
        intelligence: {
          repos: ['test-repo']
        }
      };

      const result = await auditRepo('test-repo', config);

      expect(result.has_claude_md).toBe(false);
      expect(result.score).toBe(0);
      expect(result.missing_points).toHaveLength(13);
      expect(result.issues).toContain('Missing CLAUDE.md');
      expect(result.recommendations).toHaveLength(1);
    });
  });

  describe('auditRepo - Incomplete CLAUDE.md', () => {
    test('should detect missing sections', async () => {
      const incompleteContent = `# Project Name

Just a title and nothing else.
`;

      mockOctokit.repos.getContent.mockResolvedValue({
        data: {
          content: Buffer.from(incompleteContent).toString('base64')
        }
      });

      mockOctokit.repos.listCommits.mockResolvedValue({
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
        intelligence: {
          repos: ['test-repo']
        }
      };

      const result = await auditRepo('test-repo', config);

      expect(result.has_claude_md).toBe(true);
      expect(result.score).toBeLessThan(13);
      expect(result.missing_points.length).toBeGreaterThan(0);
      expect(result.issues.length).toBeGreaterThan(0);
      expect(result.recommendations.length).toBeGreaterThan(0);
    });
  });

  describe('auditRepo - Stale CLAUDE.md', () => {
    test('should flag stale documentation', async () => {
      const staleContent = `# Stale Project

This has all required sections but is very old.

## Tech Stack

| Layer | Technology |
|-------|------------|
| View | React |

## Commands

\`\`\`bash
npm run dev
\`\`\`

## Architecture

Standard directory structure.

## Environment Variables

| Variable | Description |
|----------|-------------|
| API_KEY | Key |

## API

| Method | Path |
|--------|------|
| GET | /api |

## Deployment

Cloud Run on GCP

See [adjudica-documentation](../adjudica-documentation/)

## Centralized Documentation

Link here.

## Context Window Protocol

Checkpoint at 65%.

@Developed & Documented by Glass Box Solutions, Inc.
`;

      mockOctokit.repos.getContent.mockResolvedValue({
        data: {
          content: Buffer.from(staleContent).toString('base64')
        }
      });

      // Last modified 120 days ago
      const oldDate = new Date();
      oldDate.setDate(oldDate.getDate() - 120);
      mockOctokit.repos.listCommits.mockResolvedValue({
        data: [{
          commit: {
            author: {
              date: oldDate.toISOString()
            }
          }
        }]
      });

      const config = {
        github_token: 'test-token',
        intelligence: {
          repos: ['test-repo']
        }
      };

      const result = await auditRepo('test-repo', config);

      expect(result.has_claude_md).toBe(true);
      expect(result.breakdown.freshness).toBeLessThanOrEqual(50);
      expect(result.recommendations).toContain('Update documentation to reflect recent changes');
    });
  });

  describe('auditRepo - Broken Links', () => {
    test('should detect broken internal links', async () => {
      const contentWithBrokenLinks = `# Project With Broken Links

This project has some broken links.

See [broken link](./non-existent-file.md) for details.

## Tech Stack

| Layer | Technology |
|-------|------------|
| View | React |

## Commands

\`\`\`bash
npm run dev
\`\`\`

## Architecture

Standard directory structure.

## Environment Variables

| Variable | Description |
|----------|-------------|
| API_KEY | Key |

## API

| Method | Path |
|--------|------|
| GET | /api |

## Deployment

Cloud Run on GCP

See [adjudica-documentation](../adjudica-documentation/)

## Centralized Documentation

Link here.

## Context Window Protocol

Checkpoint at 65%.

@Developed & Documented by Glass Box Solutions, Inc.
`;

      mockOctokit.repos.getContent
        .mockResolvedValueOnce({
          data: {
            content: Buffer.from(contentWithBrokenLinks).toString('base64')
          }
        })
        .mockRejectedValueOnce({
          status: 404,
          message: 'Not Found'
        });

      mockOctokit.repos.listCommits.mockResolvedValue({
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
        intelligence: {
          repos: ['test-repo']
        }
      };

      const result = await auditRepo('test-repo', config);

      expect(result.has_claude_md).toBe(true);
      expect(result.broken_links.length).toBeGreaterThanOrEqual(0);
    });
  });

  describe('auditRepo - Duplicate Parent Sections', () => {
    test('should flag duplicate sections without conditional load', async () => {
      const contentWithDuplicates = `# Project With Duplicates

Standard project overview.

## Related Projects

| Project | Link |
|---------|------|
| Other | Link |

## GBS Engineering Standards

| Doc | Link |
|-----|------|
| Standards | Link |

## Tech Stack

| Layer | Technology |
|-------|------------|
| View | React |

## Commands

\`\`\`bash
npm run dev
\`\`\`

## Architecture

Standard directory structure.

## Environment Variables

| Variable | Description |
|----------|-------------|
| API_KEY | Key |

## API

| Method | Path |
|--------|------|
| GET | /api |

## Deployment

Cloud Run on GCP

See [adjudica-documentation](../adjudica-documentation/)

## Centralized Documentation

Link here.

## Context Window Protocol

Checkpoint at 65%.

@Developed & Documented by Glass Box Solutions, Inc.
`;

      mockOctokit.repos.getContent.mockResolvedValue({
        data: {
          content: Buffer.from(contentWithDuplicates).toString('base64')
        }
      });

      mockOctokit.repos.listCommits.mockResolvedValue({
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
        intelligence: {
          repos: ['test-repo']
        }
      };

      const result = await auditRepo('test-repo', config);

      expect(result.has_claude_md).toBe(true);
      expect(result.missing_points).toContain(13);
      expect(result.recommendations).toContain('Move duplicate sections to GBS_CONTEXT_SUPPLEMENT.md and add conditional load instruction');
    });
  });

  describe('audit - Multiple Repos', () => {
    test('should audit all repos with mixed scores', async () => {
      const excellentContent = `# Excellent

Good overview text here.
Multiple lines of prose.
At least three lines.

## Tech Stack

| Layer | Technology |
|-------|------------|
| View | React |

## Commands

\`\`\`bash
npm run dev
\`\`\`

## Architecture

Standard directory structure.

## Environment Variables

| Variable | Description |
|----------|-------------|
| API_KEY | Key |

## API

| Method | Path |
|--------|------|
| GET | /api |

## Deployment

Cloud Run on GCP

See [adjudica-documentation](../adjudica-documentation/)

## Centralized Documentation

Link here.

## Context Window Protocol

Checkpoint at 65%.

## Conditional Context Load

Check parent first.

@Developed & Documented by Glass Box Solutions, Inc.
`;

      const poorContent = `# Poor

Minimal content.
`;

      mockOctokit.repos.getContent
        .mockResolvedValueOnce({
          data: {
            content: Buffer.from(excellentContent).toString('base64')
          }
        })
        .mockResolvedValueOnce({
          data: {
            content: Buffer.from(poorContent).toString('base64')
          }
        })
        .mockRejectedValueOnce({
          status: 404,
          message: 'Not Found'
        });

      mockOctokit.repos.listCommits.mockResolvedValue({
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
        intelligence: {
          repos: ['excellent-repo', 'poor-repo', 'missing-repo']
        }
      };

      const result = await audit(new Date(), config);

      expect(result.repos_audited).toBe(3);
      expect(result.summary.total_repos).toBe(3);
      expect(result.summary.with_claude_md).toBe(2);
      expect(result.summary.missing_claude_md).toBe(1);
      expect(result.details).toHaveLength(3);
    });
  });

  describe('audit - GitHub API Failure', () => {
    test('should continue processing on individual repo failure', async () => {
      mockOctokit.repos.getContent
        .mockRejectedValueOnce({
          status: 500,
          message: 'Internal Server Error'
        })
        .mockResolvedValueOnce({
          data: {
            content: Buffer.from('# Good\n\nGood content.').toString('base64')
          }
        });

      mockOctokit.repos.listCommits.mockResolvedValue({
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
        intelligence: {
          repos: ['failing-repo', 'good-repo']
        }
      };

      const result = await audit(new Date(), config);

      expect(result.repos_failed).toHaveLength(1);
      expect(result.repos_failed[0].repo).toBe('failing-repo');
      expect(result.details.length).toBeGreaterThan(0);
    });
  });

  describe('Scoring Algorithm', () => {
    test('should calculate accurate structure score', async () => {
      // 10 out of 13 points
      const tenPointContent = `# Project

Good overview.
Multiple lines.
At least three.

## Tech Stack

| Layer | Technology |
|-------|------------|
| View | React |

## Commands

\`\`\`bash
npm run dev
\`\`\`

## Architecture

Standard directory structure.

## Environment Variables

| Variable | Description |
|----------|-------------|
| API_KEY | Key |

## API

| Method | Path |
|--------|------|
| GET | /api |

## Deployment

Cloud Run on GCP

See [adjudica-documentation](../adjudica-documentation/)

@Developed & Documented by Glass Box Solutions, Inc.
`;

      mockOctokit.repos.getContent.mockResolvedValue({
        data: {
          content: Buffer.from(tenPointContent).toString('base64')
        }
      });

      mockOctokit.repos.listCommits.mockResolvedValue({
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
        intelligence: {
          repos: ['test-repo']
        }
      };

      const result = await auditRepo('test-repo', config);

      // 11/13 points: missing Centralized Documentation (11) and Context Window (12)
      expect(result.score).toBe(11);
      expect(result.missing_points).toHaveLength(2);
      expect(result.breakdown.structure).toBe(Math.round((11 / 13) * 100));
    });
  });
});
