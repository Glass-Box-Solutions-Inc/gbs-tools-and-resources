/**
 * Tests for Gemini Synthesizer Module
 *
 * @file gemini-synthesizer.test.js
 */

const {
  synthesize,
  formatPrompt,
  formatGitHubActivity,
  formatGCPActivity,
  formatStationActivity,
  formatCheckpoints,
  parseBriefing,
  generateFallbackBriefing
} = require('../../intelligence/gemini-synthesizer');

// Mock Google Generative AI
jest.mock('@google/generative-ai', () => ({
  GoogleGenerativeAI: jest.fn()
}));

const { GoogleGenerativeAI } = require('@google/generative-ai');

describe('Gemini Synthesizer - Formatting Functions', () => {
  describe('formatGitHubActivity', () => {
    it('should format GitHub activity with data', () => {
      const githubData = {
        repos: {
          'test-repo-1': {
            commits: [
              { sha: 'abc123def456', message: 'feat: add feature', author: 'Alice' },
              { sha: '123abc456def', message: 'fix: bug fix', author: 'Bob' }
            ],
            pull_requests: [
              { number: 42, title: 'Add tests', state: 'merged', author: 'Alice', labels: [] }
            ],
            issues: [],
            ci_runs: []
          },
          'test-repo-2': {
            commits: [],
            pull_requests: [],
            issues: [],
            ci_runs: []
          }
        },
        summary: {
          total_commits: 2,
          total_prs: 1,
          total_issues: 0,
          total_ci_runs: 0
        }
      };

      const result = formatGitHubActivity(githubData);

      expect(result).toContain('Total Commits: 2');
      expect(result).toContain('Total PRs: 1');
      expect(result).toContain('Active Repos: 2');
      expect(result).toContain('test-repo-1');
      expect(result).toContain('feat: add feature');
    });

    it('should handle empty GitHub activity', () => {
      const githubData = {
        repos: {},
        summary: {
          total_commits: 0,
          total_prs: 0,
          total_issues: 0,
          total_ci_runs: 0
        }
      };

      const result = formatGitHubActivity(githubData);

      expect(result).toContain('Total Commits: 0');
      expect(result).toContain('Active Repos: 0');
    });
  });

  describe('formatGCPActivity', () => {
    it('should format GCP activity with deployments and errors', () => {
      const gcpData = {
        deployments: [
          { project: 'test-project', service: 'test-service', status: 'success', revision: 'rev1', timestamp: '2026-03-03T10:00:00Z' },
          { project: 'test-project', service: 'test-service', status: 'failed', revision: 'rev2', timestamp: '2026-03-03T11:00:00Z' }
        ],
        errors: [
          { project: 'test-project', service: 'test-service', severity: 'ERROR', message: 'Test error', timestamp: '2026-03-03T12:00:00Z' }
        ],
        summary: {
          total_deployments: 2,
          total_errors: 1,
          projects_monitored: 1
        }
      };

      const result = formatGCPActivity(gcpData);

      expect(result).toContain('Total Deployments: 2');
      expect(result).toContain('Total Errors: 1');
      expect(result).toContain('Successful: 1');
      expect(result).toContain('Failed: 1');
      expect(result).toContain('ERROR: 1');
    });

    it('should handle empty GCP activity', () => {
      const gcpData = {
        deployments: [],
        errors: [],
        summary: {
          total_deployments: 0,
          total_errors: 0,
          projects_monitored: 0
        }
      };

      const result = formatGCPActivity(gcpData);

      expect(result).toContain('Total Deployments: 0');
      expect(result).toContain('Total Errors: 0');
    });
  });

  describe('formatStationActivity', () => {
    it('should format station activity with sessions', () => {
      const stationData = {
        claude_code_sessions: [
          { project_name: 'test-project', session_id: 'session-1', memory_files_count: 5, estimated_tokens: 20000 }
        ],
        cursor_active: true,
        squeegee_state: {
          last_run: '2026-03-03T07:00:00Z',
          repos_processed: 27
        }
      };

      const result = formatStationActivity(stationData);

      expect(result).toContain('Claude Code Sessions: 1');
      expect(result).toContain('Cursor Active: Yes');
      expect(result).toContain('test-project');
      expect(result).toContain('20,000 tokens');
    });

    it('should handle empty station activity', () => {
      const stationData = {
        claude_code_sessions: [],
        cursor_active: false,
        squeegee_state: {}
      };

      const result = formatStationActivity(stationData);

      expect(result).toContain('Claude Code Sessions: 0');
      expect(result).toContain('Cursor Active: No');
    });
  });

  describe('formatCheckpoints', () => {
    it('should format checkpoint events', () => {
      const checkpoints = [
        { repo: 'test-repo', user: 'alice', context_pct: 62, phase: 'Phase 1', timestamp: '2026-03-03T14:30:00Z' },
        { repo: 'test-repo', user: 'bob', context_pct: 75, phase: 'Phase 2', timestamp: '2026-03-03T15:00:00Z' }
      ];

      const result = formatCheckpoints(checkpoints);

      expect(result).toContain('**Total Events:** 2');
      expect(result).toContain('test-repo');
      expect(result).toContain('alice');
      expect(result).toContain('62%');
    });

    it('should handle empty checkpoints', () => {
      const result = formatCheckpoints([]);

      expect(result).toContain('No checkpoint events');
    });
  });

  describe('formatPrompt', () => {
    it('should build complete prompt with all sections', () => {
      const data = {
        date: '2026-03-03',
        github: {
          repos: { 'test-repo': { commits: [], pull_requests: [], issues: [], ci_runs: [] } },
          summary: { total_commits: 0, total_prs: 0, total_issues: 0, total_ci_runs: 0 }
        },
        gcp: {
          deployments: [],
          errors: [],
          summary: { total_deployments: 0, total_errors: 0, projects_monitored: 0 }
        },
        station: {
          claude_code_sessions: [],
          cursor_active: false,
          squeegee_state: {}
        },
        checkpoints: []
      };

      const result = formatPrompt(data);

      expect(result).toContain('Date:** 2026-03-03');
      expect(result).toContain('GitHub Activity');
      expect(result).toContain('GCP Activity');
      expect(result).toContain('Development Station Activity');
      expect(result).toContain('Context Checkpoints');
      expect(result).toContain('Executive Summary');
      expect(result).toContain('Generate the briefing now');
    });
  });
});

describe('Gemini Synthesizer - Parsing', () => {
  describe('parseBriefing', () => {
    it('should parse Gemini response into sections', () => {
      const responseText = `## Executive Summary

- Key activity point 1
- Key activity point 2

## Development Highlights

Major feature work completed.

## Pull Request Activity

5 PRs merged today.

## Infrastructure & Operations

3 successful deployments.

## Team Activity

Active collaboration detected.

## Recommendations

Follow up on failed CI runs.`;

      const result = parseBriefing(responseText);

      expect(result.executive_summary).toEqual(['Key activity point 1', 'Key activity point 2']);
      expect(result.repository_activity).toContain('Major feature work');
      expect(result.deployment_events).toContain('3 successful deployments');
      expect(result.observations).toContain('Follow up on failed CI runs');
    });

    it('should handle missing sections gracefully', () => {
      const responseText = `Some unstructured text without proper headers.`;

      const result = parseBriefing(responseText);

      expect(result.executive_summary).toEqual(['Daily development activity captured and analyzed.']);
    });
  });
});

describe('Gemini Synthesizer - Fallback Briefing', () => {
  describe('generateFallbackBriefing', () => {
    it('should generate template-based briefing', () => {
      const data = {
        date: '2026-03-03',
        github: {
          repos: {
            'test-repo': {
              commits: [{ sha: 'abc123', message: 'Test commit', author: 'Alice' }],
              pull_requests: [],
              issues: [],
              ci_runs: []
            }
          },
          summary: { total_commits: 1, total_prs: 0, total_issues: 0, total_ci_runs: 0 }
        },
        gcp: {
          deployments: [],
          errors: [],
          summary: { total_deployments: 0, total_errors: 0, projects_monitored: 0 }
        },
        station: {
          claude_code_sessions: [],
          cursor_active: false,
          squeegee_state: {}
        },
        checkpoints: []
      };

      const result = generateFallbackBriefing(data);

      expect(result.date).toBe('2026-03-03');
      expect(result.fallback_used).toBe(true);
      expect(result.model_used).toBe('fallback-template');
      expect(result.executive_summary).toEqual(expect.arrayContaining([
        expect.stringContaining('1 commits')
      ]));
      expect(result.observations).toContain('fallback template');
    });

    it('should include deployment data in fallback', () => {
      const data = {
        date: '2026-03-03',
        github: { repos: {}, summary: { total_commits: 0, total_prs: 0, total_issues: 0, total_ci_runs: 0 } },
        gcp: {
          deployments: [
            { project: 'test-project', service: 'test-service', status: 'success', revision: 'rev1', timestamp: '2026-03-03T10:00:00Z' }
          ],
          errors: [],
          summary: { total_deployments: 1, total_errors: 0, projects_monitored: 1 }
        },
        station: { claude_code_sessions: [], cursor_active: false, squeegee_state: {} },
        checkpoints: []
      };

      const result = generateFallbackBriefing(data);

      expect(result.deployment_events).toContain('test-project');
      expect(result.deployment_events).toContain('1 deployments');
    });
  });
});

describe('Gemini Synthesizer - Main Function', () => {
  let mockGenerateContent;
  let mockGetGenerativeModel;
  let mockGenAI;

  beforeEach(() => {
    // Reset mocks
    jest.clearAllMocks();

    // Setup mock chain
    mockGenerateContent = jest.fn();
    mockGetGenerativeModel = jest.fn(() => ({
      generateContent: mockGenerateContent
    }));
    mockGenAI = {
      getGenerativeModel: mockGetGenerativeModel
    };

    GoogleGenerativeAI.mockImplementation(() => mockGenAI);
  });

  describe('synthesize', () => {
    const config = {
      intelligence: {
        gemini: {
          apiKey: 'test-api-key',
          model: 'gemini-2.0-flash-exp',
          temperature: 0.3,
          max_output_tokens: 4096
        }
      }
    };

    const collectedData = {
      github: {
        repos: {},
        summary: { total_commits: 0, total_prs: 0, total_issues: 0, total_ci_runs: 0 }
      },
      gcp: {
        deployments: [],
        errors: [],
        summary: { total_deployments: 0, total_errors: 0, projects_monitored: 0 }
      },
      station: {
        claude_code_sessions: [],
        cursor_active: false,
        squeegee_state: {}
      },
      checkpoints: []
    };

    it('should generate briefing with Gemini API (happy path)', async () => {
      const mockResponse = {
        response: {
          text: () => `## Executive Summary

- Test activity summary

## Development Highlights

Test highlights

## Pull Request Activity

Test PR activity

## Infrastructure & Operations

Test infrastructure

## Team Activity

Test team activity

## Recommendations

Test recommendations`
        }
      };

      mockGenerateContent.mockResolvedValue(mockResponse);

      const result = await synthesize('2026-03-03', collectedData, config);

      expect(result.date).toBe('2026-03-03');
      expect(result.fallback_used).toBe(false);
      expect(result.model_used).toBe('gemini-2.0-flash-exp');
      expect(result.executive_summary).toContain('Test activity summary');
      expect(result.token_count.input).toBeGreaterThan(0);
      expect(result.token_count.output).toBeGreaterThan(0);
      expect(GoogleGenerativeAI).toHaveBeenCalledWith('test-api-key');
      expect(mockGetGenerativeModel).toHaveBeenCalledWith({
        model: 'gemini-2.0-flash-exp'
      });
    });

    it('should accept Date object as first parameter', async () => {
      const mockResponse = {
        response: {
          text: () => `## Executive Summary\n\n- Test\n\n## Recommendations\n\nNone`
        }
      };

      mockGenerateContent.mockResolvedValue(mockResponse);

      const date = new Date('2026-03-03');
      const result = await synthesize(date, collectedData, config);

      expect(result.date).toBe('2026-03-03');
    });

    it('should use fallback briefing when API key missing', async () => {
      const configNoKey = {
        intelligence: {
          gemini: {
            model: 'gemini-2.0-flash-exp',
            temperature: 0.3
          }
        }
      };

      // Unset environment variable
      delete process.env.GOOGLE_AI_API_KEY;

      const result = await synthesize('2026-03-03', collectedData, configNoKey);

      expect(result.fallback_used).toBe(true);
      expect(result.model_used).toBe('fallback-template');
      expect(GoogleGenerativeAI).not.toHaveBeenCalled();
    });

    it('should handle Gemini API failure and use fallback', async () => {
      mockGenerateContent.mockRejectedValue(new Error('API quota exceeded'));

      const result = await synthesize('2026-03-03', collectedData, config);

      expect(result.fallback_used).toBe(true);
      expect(result.error).toContain('API quota exceeded');
      expect(result.observations).toContain('fallback template');
    });

    it('should handle empty Gemini response', async () => {
      const mockResponse = {
        response: {
          text: () => ''
        }
      };

      mockGenerateContent.mockResolvedValue(mockResponse);

      const result = await synthesize('2026-03-03', collectedData, config);

      expect(result.fallback_used).toBe(true);
      expect(result.error).toContain('empty response');
    });

    it('should retry on transient failures', async () => {
      // First call fails, second succeeds
      mockGenerateContent
        .mockRejectedValueOnce(new Error('Transient error'))
        .mockResolvedValueOnce({
          response: {
            text: () => `## Executive Summary\n\n- Success after retry\n\n## Recommendations\n\nNone`
          }
        });

      const result = await synthesize('2026-03-03', collectedData, config);

      expect(result.fallback_used).toBe(false);
      expect(mockGenerateContent).toHaveBeenCalledTimes(2);
    });

    it('should handle partial data gracefully', async () => {
      const mockResponse = {
        response: {
          text: () => `## Executive Summary\n\n- Partial data processed\n\n## Recommendations\n\nNone`
        }
      };

      mockGenerateContent.mockResolvedValue(mockResponse);

      const partialData = {
        github: {
          repos: {},
          summary: { total_commits: 0, total_prs: 0, total_issues: 0, total_ci_runs: 0 }
        }
        // Missing gcp, station, checkpoints
      };

      const result = await synthesize('2026-03-03', partialData, config);

      expect(result.date).toBe('2026-03-03');
      expect(result.fallback_used).toBe(false);
    });

    it('should estimate token counts', async () => {
      const longResponse = '## Executive Summary\n\n' + 'x'.repeat(2000) + '\n\n## Recommendations\n\nNone';
      const mockResponse = {
        response: {
          text: () => longResponse
        }
      };

      mockGenerateContent.mockResolvedValue(mockResponse);

      const result = await synthesize('2026-03-03', collectedData, config);

      expect(result.token_count.input).toBeGreaterThan(0);
      expect(result.token_count.output).toBeGreaterThan(400); // ~2000 chars / 4
    });
  });
});

describe('Gemini Synthesizer - Integration Tests', () => {
  it('should handle large dataset without errors', async () => {
    const largeData = {
      date: '2026-03-03',
      github: {
        repos: {},
        summary: { total_commits: 0, total_prs: 0, total_issues: 0, total_ci_runs: 0 }
      },
      gcp: { deployments: [], errors: [], summary: { total_deployments: 0, total_errors: 0, projects_monitored: 0 } },
      station: { claude_code_sessions: [], cursor_active: false, squeegee_state: {} },
      checkpoints: []
    };

    // Add 50 repos with activity
    for (let i = 0; i < 50; i++) {
      largeData.github.repos[`repo-${i}`] = {
        commits: Array(10).fill(null).map((_, j) => ({
          sha: `commit-${i}-${j}`,
          message: `Commit ${j} in repo ${i}`,
          author: 'test-user'
        })),
        pull_requests: [],
        issues: [],
        ci_runs: []
      };
      largeData.github.summary.total_commits += 10;
    }

    const prompt = formatPrompt(largeData);

    expect(prompt.length).toBeGreaterThan(1000);
    expect(prompt).toContain('repo-0');
    // Note: Only top 10 repos are included in the prompt to avoid token bloat
    expect(prompt).toContain('Top Active Repos');
  });

  it('should generate valid fallback briefing for all data types', () => {
    const completeData = {
      date: '2026-03-03',
      github: {
        repos: {
          'repo-1': {
            commits: [{ sha: 'abc123', message: 'Test', author: 'Alice' }],
            pull_requests: [{ number: 1, title: 'PR', state: 'merged', author: 'Bob', labels: [] }],
            issues: [{ number: 2, title: 'Issue', state: 'open', author: 'Charlie', labels: [] }],
            ci_runs: []
          }
        },
        summary: { total_commits: 1, total_prs: 1, total_issues: 1, total_ci_runs: 0 }
      },
      gcp: {
        deployments: [{ project: 'test', service: 'svc', status: 'success', revision: 'rev1', timestamp: '2026-03-03T10:00:00Z' }],
        errors: [{ project: 'test', service: 'svc', severity: 'ERROR', message: 'Error', timestamp: '2026-03-03T11:00:00Z' }],
        summary: { total_deployments: 1, total_errors: 1, projects_monitored: 1 }
      },
      station: {
        claude_code_sessions: [{ project_name: 'test', session_id: 's1', memory_files_count: 3, estimated_tokens: 12000 }],
        cursor_active: true,
        squeegee_state: { last_run: '2026-03-03T07:00:00Z', repos_processed: 27 }
      },
      checkpoints: [
        { repo: 'repo-1', user: 'alice', context_pct: 50, phase: 'Phase 1', timestamp: '2026-03-03T14:00:00Z' }
      ]
    };

    const result = generateFallbackBriefing(completeData);

    expect(result.date).toBe('2026-03-03');
    expect(result.repository_activity).toContain('repo-1');
    expect(result.deployment_events).toContain('test');
    expect(result.development_activity).toContain('test');
    expect(result.context_checkpoints).toContain('repo-1');
  });
});
