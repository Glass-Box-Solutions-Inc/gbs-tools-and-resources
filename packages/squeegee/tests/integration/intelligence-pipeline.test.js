/**
 * Intelligence Pipeline Integration Tests
 *
 * End-to-end tests for Squeegee's intelligence system (stages 14-20).
 * Tests full pipeline data flow, scheduling logic, error handling, and API integration.
 *
 * @file tests/integration/intelligence-pipeline.test.js
 * @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
 */

const assert = require('assert');
const path = require('path');
const fs = require('fs').promises;

// Import pipeline stages
const stage14 = require('../../src/pipeline/stages/14-intelligence-collect');
const stage15 = require('../../src/pipeline/stages/15-intelligence-synthesize');
const stage16 = require('../../src/pipeline/stages/16-intelligence-write');
const stage17 = require('../../src/pipeline/stages/17-intelligence-audit-claude');
const stage18 = require('../../src/pipeline/stages/18-intelligence-audit-quality');
const stage19 = require('../../src/pipeline/stages/19-intelligence-research');

// Import intelligence modules
const githubCollector = require('../../intelligence/github-collector');
const gcpCollector = require('../../intelligence/gcp-collector');
const stationCollector = require('../../intelligence/station-collector');
const geminiSynthesizer = require('../../intelligence/gemini-synthesizer');
const logWriter = require('../../intelligence/log-writer');
const claudeMdAuditor = require('../../intelligence/claude-md-auditor');
const docQualityAuditor = require('../../intelligence/doc-quality-auditor');
const webResearcher = require('../../intelligence/web-researcher');

// ─── Load Test Fixtures ────────────────────────────────────────────────────

let fixtureGithub, fixtureGcp, fixtureStation, fixtureBriefing, fixtureClaudeMdAudit;

async function loadFixtures() {
  const fixturesPath = path.join(__dirname, '..', 'fixtures');
  fixtureGithub = JSON.parse(await fs.readFile(path.join(fixturesPath, 'github-activity.json'), 'utf-8'));
  fixtureGcp = JSON.parse(await fs.readFile(path.join(fixturesPath, 'gcp-logs.json'), 'utf-8'));
  fixtureStation = JSON.parse(await fs.readFile(path.join(fixturesPath, 'station-activity.json'), 'utf-8'));
  fixtureBriefing = JSON.parse(await fs.readFile(path.join(fixturesPath, 'gemini-briefing.json'), 'utf-8'));
  fixtureClaudeMdAudit = JSON.parse(await fs.readFile(path.join(fixturesPath, 'claude-md-audit-report.json'), 'utf-8'));
}

// ─── Mock Configuration ────────────────────────────────────────────────────

const mockConfig = {
  intelligence: {
    enabled: true,
    repos: [
      'adjudica-ai-app',
      'glassy-personal-ai',
      'command-center',
      'knowledge-base',
      'Squeegee'
    ],
    gcp_projects: [
      'glassbox-squeegee',
      'glassy-personal-ai',
      'command-center-gbs'
    ],
    docs_repo: 'Glass-Box-Solutions-Inc/adjudica-documentation',
    gemini: {
      model: 'gemini-2.0-flash-exp',
      temperature: 0.3,
      max_output_tokens: 4096,
      apiKey: 'test-gemini-key'
    },
    claude_md_audit: {
      enabled: true,
      threshold: 10,
      auto_pr_enabled: true
    },
    dry_run: false
  },
  github_token: 'test-github-token'
};

// ─── Mock Helpers ──────────────────────────────────────────────────────────

// Store original functions
const originalFunctions = {
  githubCollect: githubCollector.collect,
  gcpCollect: gcpCollector.collect,
  stationCollect: stationCollector.collect,
  geminiSynthesize: geminiSynthesizer.synthesize,
  logWrite: logWriter.write,
  claudeMdAudit: claudeMdAuditor.audit,
  docQualityAudit: docQualityAuditor.audit,
  webResearch: webResearcher.research
};

function mockGithubCollector(returnValue) {
  githubCollector.collect = jest.fn().mockResolvedValue(returnValue);
}

function mockGcpCollector(returnValue) {
  gcpCollector.collect = jest.fn().mockResolvedValue(returnValue);
}

function mockStationMonitor(returnValue) {
  stationCollector.collect = jest.fn().mockResolvedValue(returnValue);
}

function mockGeminiSynthesizer(returnValue) {
  geminiSynthesizer.synthesize = jest.fn().mockResolvedValue(returnValue);
}

function mockLogWriter(returnValue) {
  logWriter.write = jest.fn().mockResolvedValue(returnValue);
}

function mockClaudeMdAuditor(returnValue) {
  claudeMdAuditor.audit = jest.fn().mockResolvedValue(returnValue);
}

function mockDocQualityAuditor(returnValue) {
  docQualityAuditor.audit = jest.fn().mockResolvedValue(returnValue);
}

function mockWebResearcher(returnValue) {
  webResearcher.research = jest.fn().mockResolvedValue(returnValue);
}

function restoreMocks() {
  githubCollector.collect = originalFunctions.githubCollect;
  gcpCollector.collect = originalFunctions.gcpCollect;
  stationCollector.collect = originalFunctions.stationCollect;
  geminiSynthesizer.synthesize = originalFunctions.geminiSynthesize;
  logWriter.write = originalFunctions.logWrite;
  claudeMdAuditor.audit = originalFunctions.claudeMdAudit;
  docQualityAuditor.audit = originalFunctions.docQualityAudit;
  webResearcher.research = originalFunctions.webResearch;
}

// ─── Test Suites ───────────────────────────────────────────────────────────

describe('Intelligence Pipeline Integration Tests', () => {

  beforeAll(async () => {
    await loadFixtures();
  });

  afterEach(() => {
    restoreMocks();
    jest.clearAllMocks();
  });

  // ─── Full Daily Pipeline Tests (Stages 14→15→16) ─────────────────────────

  describe('Full Daily Run (Stages 14-16)', () => {

    test('should complete full daily pipeline successfully', async () => {
      mockGithubCollector(fixtureGithub);
      mockGcpCollector(fixtureGcp);
      mockStationMonitor(fixtureStation);
      mockGeminiSynthesizer(fixtureBriefing);
      mockLogWriter({ success: true, file_path: 'logs/test.md' });

      const context = {
        date: new Date('2026-03-13'),
        config: mockConfig
      };

      // Stage 14: Collect
      const result14 = await stage14.run(mockConfig, context);
      assert.strictEqual(result14.status, 'success');
      assert.ok(context.intelligence);
      assert.deepStrictEqual(context.intelligence.github, fixtureGithub);
      assert.deepStrictEqual(context.intelligence.gcp, fixtureGcp);
      assert.deepStrictEqual(context.intelligence.station, fixtureStation);
      assert.strictEqual(context.metrics.total_commits, 4);
      assert.strictEqual(context.metrics.repos_active, 3);

      // Stage 15: Synthesize
      const result15 = await stage15.run(mockConfig, context);
      assert.strictEqual(result15.status, 'success');
      assert.ok(context.briefing);
      assert.strictEqual(context.briefing.executive_summary.length, 3);
      assert.strictEqual(context.briefing.model_used, 'gemini-2.0-flash-exp');
      assert.strictEqual(context.briefing.fallback_used, false);

      // Stage 16: Write
      const result16 = await stage16.run(mockConfig, context);
      assert.strictEqual(result16.status, 'success');
      assert.strictEqual(logWriter.write.mock.calls.length, 5);
      assert.strictEqual(result16.logs_written, 5);
      assert.strictEqual(result16.logs_failed, 0);
    });

    test('should collect data from all sources in parallel', async () => {
      const collectStart = Date.now();

      mockGithubCollector(
        new Promise(resolve => setTimeout(() => resolve(fixtureGithub), 100))
      );
      mockGcpCollector(
        new Promise(resolve => setTimeout(() => resolve(fixtureGcp), 100))
      );
      mockStationMonitor(
        new Promise(resolve => setTimeout(() => resolve(fixtureStation), 100))
      );

      const context = { date: new Date('2026-03-13'), config: mockConfig };
      await stage14.run(mockConfig, context);

      const duration = Date.now() - collectStart;

      // Should complete in ~100ms (parallel), not ~300ms (sequential)
      assert.ok(duration < 200, `Expected parallel execution <200ms, got ${duration}ms`);
      assert.ok(context.intelligence.github);
      assert.ok(context.intelligence.gcp);
      assert.ok(context.intelligence.station);
    });

    test('should validate context data flow between stages', async () => {
      mockGithubCollector(fixtureGithub);
      mockGcpCollector(fixtureGcp);
      mockStationMonitor(fixtureStation);
      mockGeminiSynthesizer(fixtureBriefing);

      const context = { date: new Date('2026-03-13'), config: mockConfig };

      // Run stages in sequence
      await stage14.run(mockConfig, context);

      // Verify context has intelligence data
      assert.ok(context.intelligence);
      assert.ok(context.metrics);

      await stage15.run(mockConfig, context);

      // Verify synthesize received intelligence data
      assert.strictEqual(geminiSynthesizer.synthesize.mock.calls.length, 1);
      const [callDate, callIntel, callConfig] = geminiSynthesizer.synthesize.mock.calls[0];
      assert.ok(callDate instanceof Date);
      assert.deepStrictEqual(callIntel, context.intelligence);
      assert.ok(context.briefing);
    });

    test('should calculate metrics correctly from collected data', async () => {
      mockGithubCollector(fixtureGithub);
      mockGcpCollector(fixtureGcp);
      mockStationMonitor(fixtureStation);

      const context = { date: new Date('2026-03-13'), config: mockConfig };
      await stage14.run(mockConfig, context);

      assert.deepStrictEqual(context.metrics, {
        repos_active: 3,
        total_commits: 4,
        total_prs: 1,
        deployments: 3,
        errors: 2,
        sessions: 4
      });
    });

    test('should fail stage 15 when intelligence data is missing', async () => {
      const context = { date: new Date('2026-03-13'), config: mockConfig };

      // Skip stage 14 - no intelligence data
      const result15 = await stage15.run(mockConfig, context);

      assert.strictEqual(result15.status, 'failed');
      assert.strictEqual(result15.error, 'Missing intelligence data');
      assert.ok(result15.summary.includes('Cannot synthesize'));
    });

    test('should fail stage 16 when briefing is missing', async () => {
      mockGithubCollector(fixtureGithub);
      mockGcpCollector(fixtureGcp);
      mockStationMonitor(fixtureStation);

      const context = { date: new Date('2026-03-13'), config: mockConfig };

      // Run stage 14 but skip stage 15
      await stage14.run(mockConfig, context);
      const result16 = await stage16.run(mockConfig, context);

      assert.strictEqual(result16.status, 'failed');
      assert.strictEqual(result16.error, 'Missing required data');
      assert.ok(result16.summary.includes('Cannot write logs'));
    });
  });

  // ─── Weekly CLAUDE.md Audit Tests (Stage 17) ────────────────────────────

  describe('Weekly CLAUDE.md Audit (Stage 17)', () => {

    test('should run audit on Sunday', async () => {
      mockClaudeMdAuditor(fixtureClaudeMdAudit);
      mockLogWriter({ success: true, file_path: 'logs/audit.md' });

      const sunday = new Date('2026-03-15'); // Sunday
      const context = { date: sunday, config: mockConfig };

      const result = await stage17.run(mockConfig, context);

      assert.strictEqual(result.status, 'success');
      assert.ok(context.claudeMdAudit);
      assert.strictEqual(context.claudeMdAudit.repos_audited, 27);
      assert.strictEqual(result.average_score, 11.2);
      assert.strictEqual(result.needs_work, 4); // 3 needs_work + 1 critical
      assert.strictEqual(claudeMdAuditor.audit.mock.calls.length, 1);
    });

    test('should skip audit on Monday', async () => {
      const monday = new Date('2026-03-16'); // Monday
      const context = { date: monday, config: mockConfig };

      const result = await stage17.run(mockConfig, context);

      assert.strictEqual(result.status, 'skipped');
      assert.ok(result.summary.includes('runs on Sundays'));
      assert.strictEqual(result.next_run, '2026-03-22'); // Next Sunday
    });

    test('should run audit when forced on weekday', async () => {
      mockClaudeMdAuditor(fixtureClaudeMdAudit);
      mockLogWriter({ success: true, file_path: 'logs/audit.md' });

      const monday = new Date('2026-03-16'); // Monday
      const context = {
        date: monday,
        config: mockConfig,
        forceClaudeMdAudit: true
      };

      const result = await stage17.run(mockConfig, context);

      assert.strictEqual(result.status, 'success');
      assert.strictEqual(context.claudeMdAudit.repos_audited, 27);
      assert.strictEqual(claudeMdAuditor.audit.mock.calls.length, 1);
    });

    test('should handle audit failure gracefully', async () => {
      claudeMdAuditor.audit = jest.fn().mockRejectedValue(new Error('GitHub API rate limit'));

      const sunday = new Date('2026-03-15'); // Sunday
      const context = { date: sunday, config: mockConfig };

      const result = await stage17.run(mockConfig, context);

      assert.strictEqual(result.status, 'failed');
      assert.strictEqual(result.error, 'GitHub API rate limit');
      assert.ok(result.summary.includes('audit failed'));
    });
  });

  // ─── Monthly Doc Quality Audit Tests (Stage 18) ─────────────────────────

  describe('Monthly Doc Quality Audit (Stage 18)', () => {

    const mockDocQualityReport = {
      repos_audited: 10,
      summary: {
        average_score: 82.5,
        needs_work: 2,
        critical: 1
      }
    };

    test('should run audit on 1st of month', async () => {
      mockDocQualityAuditor(mockDocQualityReport);
      mockLogWriter({ success: true, file_path: 'logs/doc-quality-audit.md' });

      const firstOfMonth = new Date('2026-03-01');
      const context = { date: firstOfMonth, config: mockConfig };

      const result = await stage18.run(mockConfig, context);

      assert.strictEqual(result.status, 'success');
      assert.strictEqual(result.repos_audited, 10);
      assert.strictEqual(result.average_score, 82.5);
      assert.strictEqual(docQualityAuditor.audit.mock.calls.length, 1);
    });

    test('should skip audit on 2nd of month', async () => {
      const secondOfMonth = new Date('2026-03-02');
      const context = { date: secondOfMonth, config: mockConfig };

      const result = await stage18.run(mockConfig, context);

      assert.strictEqual(result.status, 'skipped');
      assert.ok(result.summary.includes('runs on 1st of month'));
      assert.strictEqual(result.next_run, '2026-04-01'); // Next month
    });

    test('should run audit when forced on non-1st day', async () => {
      mockDocQualityAuditor(mockDocQualityReport);
      mockLogWriter({ success: true, file_path: 'logs/doc-quality-audit.md' });

      const fifteenth = new Date('2026-03-15');
      const context = {
        date: fifteenth,
        config: mockConfig,
        forceDocQualityAudit: true
      };

      const result = await stage18.run(mockConfig, context);

      assert.strictEqual(result.status, 'success');
      assert.strictEqual(docQualityAuditor.audit.mock.calls.length, 1);
    });

    test('should calculate correct next run across year boundary', async () => {
      const december = new Date('2025-12-15');
      const context = { date: december, config: mockConfig };

      const result = await stage18.run(mockConfig, context);

      assert.strictEqual(result.status, 'skipped');
      assert.strictEqual(result.next_run, '2026-01-01'); // Next year
    });
  });

  // ─── Quarterly Research Tests (Stage 19) ────────────────────────────────

  describe('Quarterly Research (Stage 19)', () => {

    const mockResearchReport = {
      topic: 'documentation-standards',
      findings: ['Finding 1', 'Finding 2'],
      recommendations: ['Rec 1']
    };

    test('should run research on Jan 1', async () => {
      mockWebResearcher(mockResearchReport);
      mockLogWriter({ success: true, file_path: 'logs/research.md' });

      const jan1 = new Date('2026-01-01');
      const context = { date: jan1, config: mockConfig };

      const result = await stage19.run(mockConfig, context);

      assert.strictEqual(result.status, 'success');
      assert.strictEqual(result.reports_generated, 4);
      assert.ok(webResearcher.research.mock.calls.length >= 4);
    });

    test('should skip research on Feb 1', async () => {
      const feb1 = new Date('2026-02-01');
      const context = { date: feb1, config: mockConfig };

      const result = await stage19.run(mockConfig, context);

      assert.strictEqual(result.status, 'skipped');
      assert.ok(result.summary.includes('runs quarterly'));
      assert.strictEqual(result.next_run, '2026-04-01'); // Next quarter
    });

    test('should run research when forced', async () => {
      mockWebResearcher(mockResearchReport);
      mockLogWriter({ success: true, file_path: 'logs/research.md' });

      const mar15 = new Date('2026-03-15');
      const context = {
        date: mar15,
        config: mockConfig,
        forceResearch: true
      };

      const result = await stage19.run(mockConfig, context);

      assert.strictEqual(result.status, 'success');
      assert.ok(webResearcher.research.mock.calls.length >= 4);
    });

    test('should handle year rollover correctly (Dec → Jan)', async () => {
      const dec15 = new Date('2025-12-15');
      const context = { date: dec15, config: mockConfig };

      const result = await stage19.run(mockConfig, context);

      assert.strictEqual(result.status, 'skipped');
      assert.strictEqual(result.next_run, '2026-01-01'); // Next year Q1
    });
  });

  // ─── Error Handling & Partial Failures ──────────────────────────────────

  describe('Error Handling & Partial Failures', () => {

    test('should use fallback briefing when Gemini unavailable', async () => {
      mockGithubCollector(fixtureGithub);
      mockGcpCollector(fixtureGcp);
      mockStationMonitor(fixtureStation);

      const fallbackBriefing = { ...fixtureBriefing, fallback_used: true };
      mockGeminiSynthesizer(fallbackBriefing);

      const context = { date: new Date('2026-03-13'), config: mockConfig };

      await stage14.run(mockConfig, context);
      const result15 = await stage15.run(mockConfig, context);

      assert.strictEqual(result15.status, 'partial');
      assert.strictEqual(result15.fallback_used, true);
      assert.strictEqual(context.briefing.fallback_used, true);
      assert.ok(context.briefing.executive_summary);
    });

    test('should continue when some log writes fail', async () => {
      mockGithubCollector(fixtureGithub);
      mockGcpCollector(fixtureGcp);
      mockStationMonitor(fixtureStation);
      mockGeminiSynthesizer(fixtureBriefing);

      // Mock log writer to fail on 3rd write
      let writeCount = 0;
      logWriter.write = jest.fn().mockImplementation(() => {
        writeCount++;
        if (writeCount === 3) {
          return Promise.resolve({ success: false, error: 'Rate limit exceeded', file_path: 'logs/fail.md' });
        }
        return Promise.resolve({ success: true, file_path: `logs/test-${writeCount}.md` });
      });

      const context = { date: new Date('2026-03-13'), config: mockConfig };

      await stage14.run(mockConfig, context);
      await stage15.run(mockConfig, context);
      const result16 = await stage16.run(mockConfig, context);

      assert.strictEqual(result16.status, 'partial');
      assert.strictEqual(result16.logs_written, 4); // 4 succeeded
      assert.strictEqual(result16.logs_failed, 1); // 1 failed
      assert.strictEqual(context.logsWritten.successful.length, 4);
      assert.strictEqual(context.logsWritten.failed.length, 1);
    });

    test('should fail stage 14 when all collectors fail', async () => {
      githubCollector.collect = jest.fn().mockRejectedValue(new Error('GitHub API unavailable'));
      gcpCollector.collect = jest.fn().mockRejectedValue(new Error('GCP logging unavailable'));
      stationCollector.collect = jest.fn().mockRejectedValue(new Error('Station data unavailable'));

      const context = { date: new Date('2026-03-13'), config: mockConfig };
      const result = await stage14.run(mockConfig, context);

      assert.strictEqual(result.status, 'failed');
      assert.ok(result.error);
    });

    test('should handle Gemini synthesis complete failure', async () => {
      mockGithubCollector(fixtureGithub);
      mockGcpCollector(fixtureGcp);
      mockStationMonitor(fixtureStation);
      geminiSynthesizer.synthesize = jest.fn().mockRejectedValue(new Error('API quota exceeded'));

      const context = { date: new Date('2026-03-13'), config: mockConfig };

      await stage14.run(mockConfig, context);
      const result15 = await stage15.run(mockConfig, context);

      assert.strictEqual(result15.status, 'failed');
      assert.strictEqual(result15.error, 'API quota exceeded');
    });
  });

  // ─── Configuration Validation ───────────────────────────────────────────

  describe('Configuration Validation', () => {

    test('should validate all required config fields are present', () => {
      assert.strictEqual(mockConfig.intelligence.repos.length, 5);
      assert.strictEqual(mockConfig.intelligence.gcp_projects.length, 3);
      assert.strictEqual(mockConfig.intelligence.gemini.model, 'gemini-2.0-flash-exp');
      assert.strictEqual(mockConfig.intelligence.gemini.apiKey, 'test-gemini-key');
      assert.strictEqual(mockConfig.intelligence.docs_repo, 'Glass-Box-Solutions-Inc/adjudica-documentation');
    });

    test('should have correct schedule configuration', () => {
      // Load actual config
      const actualConfig = require('../../config/intelligence.config.json');

      assert.ok(actualConfig.intelligence.schedules.daily.stages.includes('14-collect'));
      assert.strictEqual(actualConfig.intelligence.schedules.weekly.day, 'sunday');
      assert.strictEqual(actualConfig.intelligence.schedules.monthly.day, 1);
      assert.deepStrictEqual(actualConfig.intelligence.schedules.quarterly.months, [1, 4, 7, 10]);
    });
  });
});

/**
 * @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
 */
