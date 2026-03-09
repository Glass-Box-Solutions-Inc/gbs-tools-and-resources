/**
 * Tests for Intelligence Pipeline Stages (14-20)
 *
 * Tests the intelligence pipeline orchestration layer, including:
 * - Data collection (GitHub, GCP, Station)
 * - Briefing synthesis (Gemini)
 * - Log writing
 * - CLAUDE.md audits (weekly)
 * - Documentation quality audits (monthly)
 * - Research (quarterly)
 * - Slack notifications
 *
 * @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
 */

// Mock all intelligence modules before requiring stages
jest.mock('../../intelligence/github-collector');
jest.mock('../../intelligence/gcp-collector');
jest.mock('../../intelligence/station-monitor');
jest.mock('../../intelligence/gemini-synthesizer');
jest.mock('../../intelligence/log-writer');
jest.mock('../../intelligence/claude-md-auditor');
jest.mock('../../intelligence/slack-notifier');

const githubCollector = require('../../intelligence/github-collector');
const gcpCollector = require('../../intelligence/gcp-collector');
const stationMonitor = require('../../intelligence/station-monitor');
const geminiSynthesizer = require('../../intelligence/gemini-synthesizer');
const logWriter = require('../../intelligence/log-writer');
const claudeMdAuditor = require('../../intelligence/claude-md-auditor');
const slackNotifier = require('../../intelligence/slack-notifier');

const stage14 = require('../../src/pipeline/stages/14-intelligence-collect');
const stage15 = require('../../src/pipeline/stages/15-intelligence-synthesize');
const stage16 = require('../../src/pipeline/stages/16-intelligence-write');
const stage17 = require('../../src/pipeline/stages/17-intelligence-audit-claude');
const stage18 = require('../../src/pipeline/stages/18-intelligence-audit-quality');
const stage19 = require('../../src/pipeline/stages/19-intelligence-research');
const stage20 = require('../../src/pipeline/stages/20-intelligence-notify');

describe('Intelligence Pipeline Stages', () => {
  let mockConfig;
  let mockDate;

  beforeEach(() => {
    jest.clearAllMocks();

    mockConfig = {
      workspace: '/test/workspace',
      projects: [],
      intelligence: {
        slack: {
          enabled: false
        }
      }
    };

    // Use a fixed date for consistent testing
    mockDate = new Date('2026-03-03T10:00:00Z');
  });

  // ========================================================================
  // Stage 14: Intelligence Collection
  // ========================================================================

  describe('Stage 14: Intelligence Collection', () => {
    const mockGitHubData = {
      repos: { 'test-repo': { commits: [], pull_requests: [] } },
      summary: { total_commits: 5, total_prs: 2, total_issues: 1, total_ci_runs: 3 }
    };

    const mockGCPData = {
      deployments: [{ project: 'test-project', status: 'success' }],
      errors: [],
      summary: { total_deployments: 1, total_errors: 0, projects_monitored: 1 }
    };

    const mockStationData = {
      summary: { total_sessions: 3, total_checkpoints: 5 }
    };

    beforeEach(() => {
      githubCollector.collect.mockResolvedValue(mockGitHubData);
      gcpCollector.collect.mockResolvedValue(mockGCPData);
      stationMonitor.collect.mockResolvedValue(mockStationData);
    });

    test('should collect data from all sources in parallel', async () => {
      const context = { date: mockDate };
      const result = await stage14.run(mockConfig, context);

      expect(result.status).toBe('success');
      expect(githubCollector.collect).toHaveBeenCalledWith(mockDate, mockConfig);
      expect(gcpCollector.collect).toHaveBeenCalledWith(mockDate, mockConfig);
      expect(stationMonitor.collect).toHaveBeenCalledWith(mockDate, mockConfig);
    });

    test('should store collected data in context', async () => {
      const context = { date: mockDate };
      await stage14.run(mockConfig, context);

      expect(context.intelligence).toBeDefined();
      expect(context.intelligence.github).toEqual(mockGitHubData);
      expect(context.intelligence.gcp).toEqual(mockGCPData);
      expect(context.intelligence.station).toEqual(mockStationData);
    });

    test('should calculate summary metrics', async () => {
      const context = { date: mockDate };
      const result = await stage14.run(mockConfig, context);

      expect(context.metrics).toBeDefined();
      expect(context.metrics.repos_active).toBe(1);
      expect(context.metrics.total_commits).toBe(5);
      expect(context.metrics.deployments).toBe(1);
      expect(context.metrics.sessions).toBe(3);
    });

    test('should handle collection errors gracefully', async () => {
      githubCollector.collect.mockRejectedValue(new Error('GitHub API error'));

      const context = { date: mockDate };
      const result = await stage14.run(mockConfig, context);

      expect(result.status).toBe('failed');
      expect(result.error).toContain('GitHub API error');
    });

    test('should use current date if not provided in context', async () => {
      const context = {};
      await stage14.run(mockConfig, context);

      expect(githubCollector.collect).toHaveBeenCalledWith(expect.any(Date), mockConfig);
    });
  });

  // ========================================================================
  // Stage 15: Intelligence Synthesis
  // ========================================================================

  describe('Stage 15: Intelligence Synthesis', () => {
    const mockIntelligence = {
      github: { repos: {}, summary: {} },
      gcp: { deployments: [], errors: [], summary: {} },
      station: { summary: {} }
    };

    const mockBriefing = {
      content: 'Daily briefing content',
      model_used: 'gemini-2.0-flash',
      fallback_used: false,
      token_count: 1500
    };

    beforeEach(() => {
      geminiSynthesizer.synthesize.mockResolvedValue(mockBriefing);
    });

    test('should synthesize briefing from intelligence data', async () => {
      const context = { date: mockDate, intelligence: mockIntelligence };
      const result = await stage15.run(mockConfig, context);

      expect(result.status).toBe('success');
      expect(geminiSynthesizer.synthesize).toHaveBeenCalledWith(
        mockDate,
        mockIntelligence,
        mockConfig
      );
    });

    test('should store briefing in context', async () => {
      const context = { date: mockDate, intelligence: mockIntelligence };
      await stage15.run(mockConfig, context);

      expect(context.briefing).toEqual(mockBriefing);
    });

    test('should handle missing intelligence data', async () => {
      const context = { date: mockDate };
      const result = await stage15.run(mockConfig, context);

      expect(result.status).toBe('failed');
      expect(result.error).toContain('Missing intelligence data');
      expect(geminiSynthesizer.synthesize).not.toHaveBeenCalled();
    });

    test('should handle fallback briefings', async () => {
      const fallbackBriefing = { ...mockBriefing, fallback_used: true };
      geminiSynthesizer.synthesize.mockResolvedValue(fallbackBriefing);

      const context = { date: mockDate, intelligence: mockIntelligence };
      const result = await stage15.run(mockConfig, context);

      expect(result.status).toBe('partial');
      expect(result.fallback_used).toBe(true);
    });

    test('should handle synthesis errors', async () => {
      geminiSynthesizer.synthesize.mockRejectedValue(new Error('Gemini API error'));

      const context = { date: mockDate, intelligence: mockIntelligence };
      const result = await stage15.run(mockConfig, context);

      expect(result.status).toBe('failed');
      expect(result.error).toContain('Gemini API error');
    });
  });

  // ========================================================================
  // Stage 16: Intelligence Log Writing
  // ========================================================================

  describe('Stage 16: Intelligence Log Writing', () => {
    const mockIntelligence = {
      github: { repos: {}, summary: {} },
      gcp: { deployments: [], errors: [], summary: {} },
      station: { summary: {} }
    };

    const mockBriefing = { content: 'Briefing' };

    beforeEach(() => {
      logWriter.write.mockResolvedValue({
        success: true,
        file_path: 'logs/test/file.md'
      });
    });

    test('should write all log types', async () => {
      const context = {
        date: mockDate,
        intelligence: mockIntelligence,
        briefing: mockBriefing
      };

      const result = await stage16.run(mockConfig, context);

      expect(result.status).toBe('success');
      expect(logWriter.write).toHaveBeenCalledTimes(5);
      expect(logWriter.write).toHaveBeenCalledWith(
        mockIntelligence.github,
        'commits',
        mockDate,
        mockConfig
      );
      expect(logWriter.write).toHaveBeenCalledWith(
        mockIntelligence.github,
        'prs',
        mockDate,
        mockConfig
      );
      expect(logWriter.write).toHaveBeenCalledWith(
        mockIntelligence.gcp,
        'deployments',
        mockDate,
        mockConfig
      );
      expect(logWriter.write).toHaveBeenCalledWith(
        mockIntelligence.station,
        'agents',
        mockDate,
        mockConfig
      );
      expect(logWriter.write).toHaveBeenCalledWith(
        mockBriefing,
        'analysis',
        mockDate,
        mockConfig
      );
    });

    test('should handle partial failures', async () => {
      logWriter.write
        .mockResolvedValueOnce({ success: true, file_path: 'logs/commits.md' })
        .mockResolvedValueOnce({ success: false, file_path: 'logs/prs.md', error: 'Write error' })
        .mockResolvedValueOnce({ success: true, file_path: 'logs/deployments.md' })
        .mockResolvedValueOnce({ success: true, file_path: 'logs/agents.md' })
        .mockResolvedValueOnce({ success: true, file_path: 'logs/analysis.md' });

      const context = {
        date: mockDate,
        intelligence: mockIntelligence,
        briefing: mockBriefing
      };

      const result = await stage16.run(mockConfig, context);

      expect(result.status).toBe('partial');
      expect(result.logs_written).toBe(4);
      expect(result.logs_failed).toBe(1);
    });

    test('should handle missing data', async () => {
      const context = { date: mockDate };
      const result = await stage16.run(mockConfig, context);

      expect(result.status).toBe('failed');
      expect(result.error).toContain('Missing required data');
      expect(logWriter.write).not.toHaveBeenCalled();
    });

    test('should store write results in context', async () => {
      const context = {
        date: mockDate,
        intelligence: mockIntelligence,
        briefing: mockBriefing
      };

      await stage16.run(mockConfig, context);

      expect(context.logsWritten).toBeDefined();
      expect(context.logsWritten.successful).toHaveLength(5);
      expect(context.logsWritten.failed).toHaveLength(0);
    });
  });

  // ========================================================================
  // Stage 17: CLAUDE.md Audit (Weekly - Sundays)
  // ========================================================================

  describe('Stage 17: CLAUDE.md Audit', () => {
    const mockAuditReport = {
      repos_audited: 10,
      summary: {
        average_score: 85.5,
        needs_work: 2,
        critical: 1
      }
    };

    beforeEach(() => {
      claudeMdAuditor.audit.mockResolvedValue(mockAuditReport);
      logWriter.write.mockResolvedValue({ success: true, file_path: 'logs/audit.md' });
    });

    test('should run on Sundays', async () => {
      const sunday = new Date('2026-03-01T10:00:00Z'); // This is a Sunday
      const context = { date: sunday };

      const result = await stage17.run(mockConfig, context);

      expect(result.status).toBe('success');
      expect(claudeMdAuditor.audit).toHaveBeenCalledWith(sunday, mockConfig);
    });

    test('should skip on non-Sundays', async () => {
      const monday = new Date('2026-03-02T10:00:00Z'); // This is a Monday
      const context = { date: monday };

      const result = await stage17.run(mockConfig, context);

      expect(result.status).toBe('skipped');
      expect(claudeMdAuditor.audit).not.toHaveBeenCalled();
      expect(result.next_run).toBeDefined();
    });

    test('should run when explicitly forced', async () => {
      const monday = new Date('2026-03-02T10:00:00Z');
      const context = { date: monday, forceClaudeMdAudit: true };

      const result = await stage17.run(mockConfig, context);

      expect(result.status).toBe('success');
      expect(claudeMdAuditor.audit).toHaveBeenCalled();
    });

    test('should store audit report in context', async () => {
      const sunday = new Date('2026-03-01T10:00:00Z');
      const context = { date: sunday };

      await stage17.run(mockConfig, context);

      expect(context.claudeMdAudit).toEqual(mockAuditReport);
    });

    test('should write audit report to logs', async () => {
      const sunday = new Date('2026-03-01T10:00:00Z');
      const context = { date: sunday };

      await stage17.run(mockConfig, context);

      expect(logWriter.write).toHaveBeenCalledWith(
        mockAuditReport,
        'claude-md-audit',
        sunday,
        mockConfig
      );
    });

    test('should handle audit errors', async () => {
      claudeMdAuditor.audit.mockRejectedValue(new Error('Audit failed'));

      const sunday = new Date('2026-03-01T10:00:00Z');
      const context = { date: sunday };

      const result = await stage17.run(mockConfig, context);

      expect(result.status).toBe('failed');
      expect(result.error).toContain('Audit failed');
    });
  });

  // ========================================================================
  // Stage 18: Documentation Quality Audit (Monthly - 1st of month)
  // ========================================================================

  describe('Stage 18: Documentation Quality Audit', () => {
    test('should skip on non-1st days of month', async () => {
      const notFirst = new Date('2026-03-15T10:00:00Z');
      const context = { date: notFirst };

      const result = await stage18.run(mockConfig, context);

      expect(result.status).toBe('skipped');
      expect(result.next_run).toBeDefined();
    });

    test('should skip on 1st of month (not yet implemented)', async () => {
      const firstOfMonth = new Date('2026-03-01T10:00:00Z');
      const context = { date: firstOfMonth };

      const result = await stage18.run(mockConfig, context);

      // Currently returns skipped because module not implemented
      expect(result.status).toBe('skipped');
      expect(result.summary).toContain('not yet implemented');
    });

    test('should skip when explicitly forced (not yet implemented)', async () => {
      const notFirst = new Date('2026-03-15T10:00:00Z');
      const context = { date: notFirst, forceDocQualityAudit: true };

      const result = await stage18.run(mockConfig, context);

      // Currently returns skipped because module not implemented
      expect(result.status).toBe('skipped');
      expect(result.summary).toContain('not yet implemented');
    });

    test('should calculate next run date correctly', async () => {
      const midMonth = new Date('2026-03-15T10:00:00Z');
      const context = { date: midMonth };

      const result = await stage18.run(mockConfig, context);

      expect(result.next_run).toBe('2026-04-01');
    });
  });

  // ========================================================================
  // Stage 19: Intelligence Research (Quarterly)
  // ========================================================================

  describe('Stage 19: Intelligence Research', () => {
    test('should skip on non-quarter-start dates', async () => {
      const notQuarterStart = new Date('2026-03-15T10:00:00Z');
      const context = { date: notQuarterStart };

      const result = await stage19.run(mockConfig, context);

      expect(result.status).toBe('skipped');
      expect(result.next_run).toBeDefined();
    });

    test('should skip on quarter start (not yet implemented)', async () => {
      const quarterStart = new Date('2026-04-01T10:00:00Z'); // Apr 1
      const context = { date: quarterStart };

      const result = await stage19.run(mockConfig, context);

      // Currently returns skipped because module not implemented
      expect(result.status).toBe('skipped');
      expect(result.summary).toContain('not yet implemented');
    });

    test('should skip when explicitly forced (not yet implemented)', async () => {
      const notQuarterStart = new Date('2026-03-15T10:00:00Z');
      const context = { date: notQuarterStart, forceResearch: true };

      const result = await stage19.run(mockConfig, context);

      // Currently returns skipped because module not implemented
      expect(result.status).toBe('skipped');
      expect(result.summary).toContain('not yet implemented');
    });

    test('should calculate next quarter correctly', async () => {
      const march = new Date('2026-03-15T10:00:00Z');
      const context = { date: march };

      const result = await stage19.run(mockConfig, context);

      expect(result.next_run).toBe('2026-04-01');
    });

    test('should roll over to next year for Q1', async () => {
      const november = new Date('2026-11-15T10:00:00Z');
      const context = { date: november };

      const result = await stage19.run(mockConfig, context);

      expect(result.next_run).toBe('2027-01-01');
    });
  });

  // ========================================================================
  // Stage 20: Slack Notification
  // ========================================================================

  describe('Stage 20: Slack Notification', () => {
    const mockBriefing = { content: 'Daily briefing' };

    test('should skip when Slack is disabled', async () => {
      const context = { date: mockDate, briefing: mockBriefing };

      const result = await stage20.run(mockConfig, context);

      expect(result.status).toBe('skipped');
      expect(result.summary).toContain('disabled in config');
    });

    test('should send notification when enabled with briefing', async () => {
      slackNotifier.notify.mockResolvedValue({
        success: true,
        channel: '#main',
        message_ts: '1234567890.123456',
        error: null
      });

      const configWithSlack = {
        ...mockConfig,
        notifications: { slack: { enabled: true, webhook_url: 'https://hooks.slack.com/test' } }
      };

      const context = { date: mockDate, briefing: mockBriefing };

      const result = await stage20.run(configWithSlack, context);

      expect(result.status).toBe('success');
      expect(result.channel).toBe('#main');
      expect(slackNotifier.notify).toHaveBeenCalledWith(mockBriefing, mockDate, configWithSlack);
    });

    test('should fail when briefing is missing', async () => {
      const configWithSlack = {
        ...mockConfig,
        notifications: { slack: { enabled: true, webhook_url: 'https://hooks.slack.com/test' } }
      };

      const context = { date: mockDate };

      const result = await stage20.run(configWithSlack, context);

      expect(result.status).toBe('failed');
      expect(result.error).toContain('Missing briefing data');
    });
  });

  // ========================================================================
  // Context Flow Between Stages
  // ========================================================================

  describe('Context Flow', () => {
    test('should flow data through stages 14->15->16', async () => {
      const mockGitHubData = {
        repos: { 'test-repo': { commits: [], pull_requests: [] } },
        summary: { total_commits: 5, total_prs: 2 }
      };

      const mockGCPData = {
        deployments: [],
        errors: [],
        summary: { total_deployments: 0 }
      };

      const mockStationData = {
        summary: { total_sessions: 3 }
      };

      const mockBriefing = {
        content: 'Briefing',
        model_used: 'gemini-2.0-flash',
        fallback_used: false
      };

      githubCollector.collect.mockResolvedValue(mockGitHubData);
      gcpCollector.collect.mockResolvedValue(mockGCPData);
      stationMonitor.collect.mockResolvedValue(mockStationData);
      geminiSynthesizer.synthesize.mockResolvedValue(mockBriefing);
      logWriter.write.mockResolvedValue({ success: true, file_path: 'logs/test.md' });

      const context = { date: mockDate };

      // Stage 14: Collect
      const result14 = await stage14.run(mockConfig, context);
      expect(result14.status).toBe('success');
      expect(context.intelligence).toBeDefined();

      // Stage 15: Synthesize (uses intelligence from stage 14)
      const result15 = await stage15.run(mockConfig, context);
      expect(result15.status).toBe('success');
      expect(context.briefing).toBeDefined();

      // Stage 16: Write (uses intelligence and briefing from stages 14 & 15)
      const result16 = await stage16.run(mockConfig, context);
      expect(result16.status).toBe('success');
      expect(context.logsWritten).toBeDefined();
    });
  });
});
