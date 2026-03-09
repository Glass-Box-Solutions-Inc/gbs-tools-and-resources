/**
 * Tests for morning-run.js pipeline orchestrator
 *
 * @file morning-run.test.js
 *
 * @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
 */

// Mock all collector modules before requiring morning-run
jest.mock('../../intelligence/github-collector', () => ({
  collect: jest.fn()
}));

jest.mock('../../intelligence/gcp-collector', () => ({
  collect: jest.fn()
}));

jest.mock('../../intelligence/station-collector', () => ({
  collect: jest.fn()
}));

jest.mock('../../intelligence/gemini-synthesizer', () => ({
  synthesize: jest.fn()
}));

jest.mock('../../intelligence/log-writer', () => ({
  write: jest.fn()
}));

jest.mock('../../intelligence/slack-notifier', () => ({
  notify: jest.fn()
}));

// Now require the module and mocks
const { run, runBatch, collectAll, writeAll, STAGES } = require('../../intelligence/morning-run');
const { collect: collectGitHub } = require('../../intelligence/github-collector');
const { collect: collectGCP } = require('../../intelligence/gcp-collector');
const { collect: collectStation } = require('../../intelligence/station-collector');
const { synthesize } = require('../../intelligence/gemini-synthesizer');
const { write: writeLog } = require('../../intelligence/log-writer');
const { notify: notifySlack } = require('../../intelligence/slack-notifier');

describe('morning-run', () => {
  let config;

  // Sample data
  const sampleGitHubData = {
    repos: {
      'repo-a': {
        commits: [{ sha: 'abc123', message: 'test', author: 'Alice' }],
        pull_requests: [{ number: 1, title: 'PR 1', author: 'Bob', state: 'merged' }],
        issues: [],
        ci_runs: []
      }
    },
    summary: { total_commits: 1, total_prs: 1, total_issues: 0, total_ci_runs: 0 }
  };

  const sampleGCPData = {
    deployments: [
      { project: 'proj-a', service: 'svc', revision: 'rev-1', status: 'success', timestamp: '2026-03-03T10:00:00Z' }
    ],
    errors: [],
    summary: { total_deployments: 1, total_errors: 0, projects_monitored: 1 }
  };

  const sampleStationData = {
    date: '2026-03-03',
    sessions: [
      { type: 'claude-code', project: 'my-project', duration_minutes: 60 }
    ],
    summary: { total_sessions: 1, active_hours: 1.0, projects_touched: ['my-project'], by_tool: { 'claude-code': 1 } }
  };

  const sampleBriefing = {
    date: '2026-03-03',
    executive_summary: ['Test briefing summary'],
    repository_activity: 'Test repo activity',
    deployment_events: 'Test deployments',
    development_activity: 'Test dev activity',
    observations: 'Test observations',
    generated_at: '2026-03-03T12:00:00.000Z',
    model_used: 'gemini-2.5-flash',
    token_count: { input: 1000, output: 500 },
    fallback_used: false
  };

  beforeEach(() => {
    jest.clearAllMocks();

    config = {
      repos: ['repo-a', 'repo-b'],
      gcp_projects: ['proj-a'],
      github_token: 'test-token',
      intelligence: {
        docs_repo: 'Glass-Box-Solutions-Inc/adjudica-documentation',
        gemini: { model: 'gemini-2.5-flash' },
        dry_run: false
      },
      notifications: {
        slack: { enabled: true, webhook_url: 'https://hooks.slack.com/test', channel: '#main' }
      },
      storage: { gcs_bucket: 'glassbox-dev-activity', gcs_prefix: 'station/' }
    };

    jest.spyOn(console, 'log').mockImplementation(() => {});
    jest.spyOn(console, 'warn').mockImplementation(() => {});
    jest.spyOn(console, 'error').mockImplementation(() => {});

    // Set up default mock implementations
    collectGitHub.mockResolvedValue(sampleGitHubData);
    collectGCP.mockResolvedValue(sampleGCPData);
    collectStation.mockResolvedValue(sampleStationData);
    synthesize.mockResolvedValue(sampleBriefing);
    writeLog.mockResolvedValue({ success: true, file_path: 'logs/test.md', commit_sha: 'abc123' });
    notifySlack.mockResolvedValue({ success: true, channel: '#main' });
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  describe('STAGES constant', () => {
    it('should define all pipeline stages', () => {
      expect(STAGES.COLLECT_GITHUB).toBe('collect-github');
      expect(STAGES.COLLECT_GCP).toBe('collect-gcp');
      expect(STAGES.COLLECT_STATION).toBe('collect-station');
      expect(STAGES.SYNTHESIZE).toBe('synthesize');
      expect(STAGES.WRITE_COMMITS).toBe('write-commits');
      expect(STAGES.WRITE_PRS).toBe('write-prs');
      expect(STAGES.WRITE_DEPLOYMENTS).toBe('write-deployments');
      expect(STAGES.WRITE_ANALYSIS).toBe('write-analysis');
      expect(STAGES.NOTIFY).toBe('notify');
    });
  });

  describe('collectAll()', () => {
    it('should collect from all sources in parallel', async () => {
      const result = await collectAll('2026-03-03', config);

      expect(collectGitHub).toHaveBeenCalledWith('2026-03-03', config);
      expect(collectGCP).toHaveBeenCalledWith('2026-03-03', config);
      expect(collectStation).toHaveBeenCalledWith('2026-03-03', config);
      expect(result.github).toEqual(sampleGitHubData);
      expect(result.gcp).toEqual(sampleGCPData);
      expect(result.station).toEqual(sampleStationData);
      expect(result.checkpoints).toEqual([]);
      expect(result.collection_duration_ms).toBeGreaterThanOrEqual(0);
    });

    it('should return empty data if GitHub collector fails', async () => {
      collectGitHub.mockRejectedValue(new Error('GitHub API error'));

      const result = await collectAll('2026-03-03', config);

      expect(result.github.repos).toEqual({});
      expect(result.github.summary.total_commits).toBe(0);
      expect(result.gcp).toEqual(sampleGCPData);
      expect(result.station).toEqual(sampleStationData);
    });

    it('should return empty data if GCP collector fails', async () => {
      collectGCP.mockRejectedValue(new Error('GCP API error'));

      const result = await collectAll('2026-03-03', config);

      expect(result.github).toEqual(sampleGitHubData);
      expect(result.gcp.deployments).toEqual([]);
      expect(result.gcp.summary.total_deployments).toBe(0);
      expect(result.station).toEqual(sampleStationData);
    });

    it('should return empty data if station collector fails', async () => {
      collectStation.mockRejectedValue(new Error('GCS error'));

      const result = await collectAll('2026-03-03', config);

      expect(result.github).toEqual(sampleGitHubData);
      expect(result.gcp).toEqual(sampleGCPData);
      expect(result.station.sessions).toEqual([]);
      expect(result.station.summary.total_sessions).toBe(0);
    });
  });

  describe('writeAll()', () => {
    it('should write all log types', async () => {
      const data = { github: sampleGitHubData, gcp: sampleGCPData };

      const result = await writeAll(data, sampleBriefing, '2026-03-03', config);

      expect(writeLog).toHaveBeenCalledTimes(4);
      expect(writeLog).toHaveBeenCalledWith(sampleGitHubData, 'commits', '2026-03-03', config);
      expect(writeLog).toHaveBeenCalledWith(sampleGitHubData, 'prs', '2026-03-03', config);
      expect(writeLog).toHaveBeenCalledWith(sampleGCPData, 'deployments', '2026-03-03', config);
      expect(writeLog).toHaveBeenCalledWith(sampleBriefing, 'analysis', '2026-03-03', config);
      expect(result.errors).toEqual([]);
    });

    it('should collect errors from failed writes', async () => {
      writeLog
        .mockResolvedValueOnce({ success: true }) // commits
        .mockResolvedValueOnce({ success: false, error: 'PR write failed' }) // prs
        .mockResolvedValueOnce({ success: true }) // deployments
        .mockResolvedValueOnce({ success: true }); // analysis

      const data = { github: sampleGitHubData, gcp: sampleGCPData };
      const result = await writeAll(data, sampleBriefing, '2026-03-03', config);

      expect(result.errors).toContain('prs: PR write failed');
    });
  });

  describe('run()', () => {
    it('should run full pipeline successfully', async () => {
      const result = await run({ date: '2026-03-03', config });

      expect(result.success).toBe(true);
      expect(result.date).toBe('2026-03-03');
      expect(result.collected.github.commits).toBe(1);
      expect(result.collected.gcp.deployments).toBe(1);
      expect(result.collected.station.sessions).toBe(1);
      expect(result.briefing.generated).toBe(true);
      expect(result.briefing.model_used).toBe('gemini-2.5-flash');
      expect(result.written.commits).toBe(true);
      expect(result.written.analysis).toBe(true);
      expect(result.notification.success).toBe(true);
      expect(result.errors).toEqual([]);
      expect(result.duration_ms).toBeGreaterThanOrEqual(0);
    });

    it('should default to yesterday if no date provided', async () => {
      await run({ config });

      // Verify collectors were called (date will be yesterday)
      expect(collectGitHub).toHaveBeenCalled();
      const callDate = collectGitHub.mock.calls[0][0];
      expect(callDate).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    });

    it('should skip writes and notifications in dry run mode', async () => {
      const result = await run({ date: '2026-03-03', config, dryRun: true });

      expect(result.success).toBe(true);
      expect(collectGitHub).toHaveBeenCalled();
      expect(synthesize).toHaveBeenCalled();
      expect(writeLog).not.toHaveBeenCalled();
      expect(notifySlack).not.toHaveBeenCalled();
      expect(result.stages.write.skipped).toBe(true);
      expect(result.stages.notify.skipped).toBe(true);
    });

    it('should respect config dry_run setting', async () => {
      config.intelligence.dry_run = true;

      const result = await run({ date: '2026-03-03', config });

      expect(writeLog).not.toHaveBeenCalled();
      expect(notifySlack).not.toHaveBeenCalled();
    });

    it('should skip stages when specified', async () => {
      const result = await run({ date: '2026-03-03', config, skipStages: ['collect'] });

      expect(collectGitHub).not.toHaveBeenCalled();
      expect(collectGCP).not.toHaveBeenCalled();
      expect(collectStation).not.toHaveBeenCalled();
      expect(result.collected).toBe(null);
    });

    it('should skip notify stage when specified', async () => {
      const result = await run({ date: '2026-03-03', config, skipStages: ['notify'] });

      expect(notifySlack).not.toHaveBeenCalled();
      expect(result.notification).toBe(null);
    });

    it('should handle synthesize failure gracefully', async () => {
      synthesize.mockRejectedValue(new Error('Gemini API error'));

      const result = await run({ date: '2026-03-03', config });

      expect(result.briefing.fallback_used).toBe(true);
      expect(result.stages.synthesize.success).toBe(false);
    });

    it('should collect errors from write failures', async () => {
      writeLog.mockResolvedValue({ success: false, error: 'Write failed' });

      const result = await run({ date: '2026-03-03', config });

      expect(result.success).toBe(false);
      expect(result.errors.length).toBeGreaterThan(0);
      expect(result.errors.some(e => e.includes('write:'))).toBe(true);
    });

    it('should collect errors from notification failures', async () => {
      notifySlack.mockResolvedValue({ success: false, error: 'Webhook failed' });

      const result = await run({ date: '2026-03-03', config });

      expect(result.success).toBe(false);
      expect(result.errors.some(e => e.includes('notify:'))).toBe(true);
    });

    it('should not record error for skipped notifications', async () => {
      notifySlack.mockResolvedValue({ success: true, skipped: true, channel: '#main' });

      const result = await run({ date: '2026-03-03', config });

      expect(result.success).toBe(true);
      expect(result.notification.skipped).toBe(true);
      expect(result.errors).toEqual([]);
    });

    it('should track stage durations', async () => {
      const result = await run({ date: '2026-03-03', config });

      expect(result.stages.collect.duration_ms).toBeGreaterThanOrEqual(0);
      expect(result.stages.synthesize.duration_ms).toBeGreaterThanOrEqual(0);
      expect(result.stages.write.duration_ms).toBeGreaterThanOrEqual(0);
      expect(result.stages.notify.duration_ms).toBeGreaterThanOrEqual(0);
    });

    it('should handle unexpected errors', async () => {
      collectGitHub.mockImplementation(() => {
        throw new Error('Unexpected error');
      });

      // This should not throw, but return error in result
      const result = await run({ date: '2026-03-03', config });

      // The safeExecute should catch the error and return default data
      expect(result.collected.github.commits).toBe(0);
    });
  });

  describe('runBatch()', () => {
    it('should process multiple dates', async () => {
      const dates = ['2026-03-01', '2026-03-02', '2026-03-03'];

      const result = await runBatch(dates, { config, dryRun: true });

      expect(result.dates_processed).toBe(3);
      expect(result.dates_succeeded).toBe(3);
      expect(result.dates_failed).toBe(0);
      expect(Object.keys(result.by_date)).toEqual(dates);
      expect(result.errors).toEqual([]);
    });

    it('should continue processing after date failure', async () => {
      collectGitHub
        .mockResolvedValueOnce(sampleGitHubData)
        .mockRejectedValueOnce(new Error('GitHub error'))
        .mockResolvedValueOnce(sampleGitHubData);

      const dates = ['2026-03-01', '2026-03-02', '2026-03-03'];
      const result = await runBatch(dates, { config, dryRun: true });

      expect(result.dates_processed).toBe(3);
      expect(result.dates_succeeded).toBe(3); // All succeed because safeExecute handles errors
      expect(result.by_date['2026-03-01'].success).toBe(true);
      expect(result.by_date['2026-03-02'].success).toBe(true);
      expect(result.by_date['2026-03-03'].success).toBe(true);
    });

    it('should aggregate errors from all dates', async () => {
      writeLog.mockResolvedValue({ success: false, error: 'Write failed' });

      const dates = ['2026-03-01', '2026-03-02'];
      const result = await runBatch(dates, { config });

      expect(result.dates_failed).toBe(2);
      expect(result.errors.length).toBeGreaterThan(0);
    });

    it('should track total duration', async () => {
      const dates = ['2026-03-01', '2026-03-02'];
      const result = await runBatch(dates, { config, dryRun: true });

      expect(result.duration_ms).toBeGreaterThanOrEqual(0);
    });
  });

  describe('integration behavior', () => {
    it('should pass collected data to synthesizer', async () => {
      await run({ date: '2026-03-03', config });

      expect(synthesize).toHaveBeenCalledWith(
        '2026-03-03',
        expect.objectContaining({
          github: sampleGitHubData,
          gcp: sampleGCPData,
          station: sampleStationData,
          checkpoints: []
        }),
        config
      );
    });

    it('should pass briefing to log writer', async () => {
      await run({ date: '2026-03-03', config });

      expect(writeLog).toHaveBeenCalledWith(
        sampleBriefing,
        'analysis',
        '2026-03-03',
        config
      );
    });

    it('should pass briefing to Slack notifier', async () => {
      await run({ date: '2026-03-03', config });

      expect(notifySlack).toHaveBeenCalledWith(
        sampleBriefing,
        '2026-03-03',
        config
      );
    });
  });
});
