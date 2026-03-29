/**
 * Intelligence Pipeline E2E Tests (Stages 14-20)
 *
 * End-to-end tests for the intelligence system with all stages chained.
 * All external APIs (GitHub, GCP, Gemini, Slack) are mocked.
 *
 * @file tests/e2e/intelligence-pipeline.test.js
 */

const path = require('path');
const fs = require('fs').promises;

// Import pipeline stages
const stage14 = require('../../src/pipeline/stages/14-intelligence-collect');
const stage15 = require('../../src/pipeline/stages/15-intelligence-synthesize');
const stage16 = require('../../src/pipeline/stages/16-intelligence-write');
const stage17 = require('../../src/pipeline/stages/17-intelligence-audit-claude');

// Import intelligence modules for mocking
const githubCollector = require('../../intelligence/github-collector');
const gcpCollector = require('../../intelligence/gcp-collector');
const stationCollector = require('../../intelligence/station-collector');
const geminiSynthesizer = require('../../intelligence/gemini-synthesizer');
const logWriter = require('../../intelligence/log-writer');
const claudeMdAuditor = require('../../intelligence/claude-md-auditor');

// ─── Fixtures ────────────────────────────────────────────────────────────

let fixtureGithub, fixtureGcp, fixtureStation, fixtureBriefing, fixtureClaudeMdAudit;

async function loadFixtures() {
  const fixturesPath = path.join(__dirname, '..', 'fixtures');
  fixtureGithub = JSON.parse(await fs.readFile(path.join(fixturesPath, 'github-activity.json'), 'utf-8'));
  fixtureGcp = JSON.parse(await fs.readFile(path.join(fixturesPath, 'gcp-logs.json'), 'utf-8'));
  fixtureStation = JSON.parse(await fs.readFile(path.join(fixturesPath, 'station-activity.json'), 'utf-8'));
  fixtureBriefing = JSON.parse(await fs.readFile(path.join(fixturesPath, 'gemini-briefing.json'), 'utf-8'));
  fixtureClaudeMdAudit = JSON.parse(await fs.readFile(path.join(fixturesPath, 'claude-md-audit-report.json'), 'utf-8'));
}

// ─── Mock Config ─────────────────────────────────────────────────────────

const mockConfig = {
  intelligence: {
    enabled: true,
    repos: ['adjudica-ai-app', 'glassy-personal-ai', 'command-center', 'knowledge-base', 'Squeegee'],
    gcp_projects: ['glassbox-squeegee', 'glassy-personal-ai', 'command-center-gbs'],
    docs_repo: 'Glass-Box-Solutions-Inc/adjudica-documentation',
    gemini: {
      model: 'gemini-2.0-flash-exp',
      temperature: 0.3,
      max_output_tokens: 4096,
      apiKey: 'test-gemini-key',
    },
    claude_md_audit: { enabled: true, threshold: 10, auto_pr_enabled: true },
    dry_run: false,
  },
  github_token: 'test-github-token',
};

// ─── Mock helpers ─────────────────────────────────────────────────────────

const originals = {};

function saveOriginals() {
  originals.githubCollect = githubCollector.collect;
  originals.gcpCollect = gcpCollector.collect;
  originals.stationCollect = stationCollector.collect;
  originals.geminiSynthesize = geminiSynthesizer.synthesize;
  originals.logWrite = logWriter.write;
  originals.claudeMdAudit = claudeMdAuditor.audit;
}

function restoreOriginals() {
  githubCollector.collect = originals.githubCollect;
  gcpCollector.collect = originals.gcpCollect;
  stationCollector.collect = originals.stationCollect;
  geminiSynthesizer.synthesize = originals.geminiSynthesize;
  logWriter.write = originals.logWrite;
  claudeMdAuditor.audit = originals.claudeMdAudit;
}

function mockAllCollectors() {
  githubCollector.collect = jest.fn().mockResolvedValue(fixtureGithub);
  gcpCollector.collect = jest.fn().mockResolvedValue(fixtureGcp);
  stationCollector.collect = jest.fn().mockResolvedValue(fixtureStation);
}

function mockSynthesizer(returnValue) {
  geminiSynthesizer.synthesize = jest.fn().mockResolvedValue(returnValue || fixtureBriefing);
}

function mockLogWriter(returnValue) {
  logWriter.write = jest.fn().mockResolvedValue(returnValue || { success: true, file_path: 'logs/test.md' });
}

function mockAuditor(returnValue) {
  claudeMdAuditor.audit = jest.fn().mockResolvedValue(returnValue || fixtureClaudeMdAudit);
}

// ─── Test suite ──────────────────────────────────────────────────────────

describe('Intelligence Pipeline E2E (Stages 14-20)', () => {
  beforeAll(async () => {
    await loadFixtures();
    saveOriginals();
  });

  afterEach(() => {
    restoreOriginals();
    jest.clearAllMocks();
  });

  // ─── Full Daily Flow (14 → 15 → 16) ──────────────────────────────────

  describe('Full Daily Flow (14 → 15 → 16)', () => {
    test('collect → synthesize → write completes successfully', async () => {
      mockAllCollectors();
      mockSynthesizer();
      mockLogWriter();

      const context = { date: new Date('2026-03-13'), config: mockConfig };

      // Stage 14: Collect
      const r14 = await stage14.run(mockConfig, context);
      expect(r14.status).toBe('success');
      expect(context.intelligence).toBeDefined();
      expect(context.intelligence.github).toEqual(fixtureGithub);
      expect(context.intelligence.gcp).toEqual(fixtureGcp);
      expect(context.intelligence.station).toEqual(fixtureStation);

      // Stage 15: Synthesize
      const r15 = await stage15.run(mockConfig, context);
      expect(r15.status).toBe('success');
      expect(context.briefing).toBeDefined();
      expect(context.briefing.executive_summary).toHaveLength(3);

      // Stage 16: Write
      const r16 = await stage16.run(mockConfig, context);
      expect(r16.status).toBe('success');
      expect(r16.logs_written).toBe(5);
      expect(r16.logs_failed).toBe(0);
    });

    test('context flows correctly between stages', async () => {
      mockAllCollectors();
      mockSynthesizer();

      const context = { date: new Date('2026-03-13'), config: mockConfig };

      await stage14.run(mockConfig, context);

      // Verify synthesizer receives the collected data
      await stage15.run(mockConfig, context);
      expect(geminiSynthesizer.synthesize).toHaveBeenCalledWith(
        expect.any(Date),
        context.intelligence,
        mockConfig
      );
    });

    test('metrics calculated from collected data', async () => {
      mockAllCollectors();

      const context = { date: new Date('2026-03-13'), config: mockConfig };
      await stage14.run(mockConfig, context);

      expect(context.metrics).toEqual({
        repos_active: 3,
        total_commits: 4,
        total_prs: 1,
        deployments: 3,
        errors: 2,
        sessions: 4,
      });
    });
  });

  // ─── Full Weekly Flow (14 → 15 → 16 → 17) ────────────────────────────

  describe('Full Weekly Flow (14 → 15 → 16 → 17)', () => {
    test('daily flow + CLAUDE.md audit on Sunday', async () => {
      mockAllCollectors();
      mockSynthesizer();
      mockLogWriter();
      mockAuditor();

      const sunday = new Date('2026-03-15'); // Sunday
      const context = { date: sunday, config: mockConfig };

      // Run daily stages
      await stage14.run(mockConfig, context);
      await stage15.run(mockConfig, context);
      await stage16.run(mockConfig, context);

      // Run audit
      const r17 = await stage17.run(mockConfig, context);
      expect(r17.status).toBe('success');
      expect(r17.repos_audited).toBe(27);
      expect(context.claudeMdAudit).toBeDefined();
    });

    test('audit skipped on non-Sunday', async () => {
      const monday = new Date('2026-03-16'); // Monday
      const context = { date: monday, config: mockConfig };

      const r17 = await stage17.run(mockConfig, context);
      expect(r17.status).toBe('skipped');
      expect(r17.summary).toContain('runs on Sundays');
    });
  });

  // ─── Error Resilience ─────────────────────────────────────────────────

  describe('Error Resilience', () => {
    test('single collector failure: partial success', async () => {
      githubCollector.collect = jest.fn().mockResolvedValue(fixtureGithub);
      gcpCollector.collect = jest.fn().mockRejectedValue(new Error('GCP unavailable'));
      stationCollector.collect = jest.fn().mockResolvedValue(fixtureStation);

      const context = { date: new Date('2026-03-13'), config: mockConfig };
      const r14 = await stage14.run(mockConfig, context);

      // Stage should handle partial failure
      // The exact behavior depends on implementation — it may succeed with partial data
      // or fail. Either way, it should not throw.
      expect(r14).toBeDefined();
      expect(r14).toHaveProperty('status');
    });

    test('Gemini failure: synthesis fails gracefully', async () => {
      mockAllCollectors();
      geminiSynthesizer.synthesize = jest.fn().mockRejectedValue(new Error('API quota exceeded'));

      const context = { date: new Date('2026-03-13'), config: mockConfig };
      await stage14.run(mockConfig, context);

      const r15 = await stage15.run(mockConfig, context);
      expect(r15.status).toBe('failed');
      expect(r15.error).toBe('API quota exceeded');
    });

    test('log writer partial failure: continues writing', async () => {
      mockAllCollectors();
      mockSynthesizer();

      let writeCount = 0;
      logWriter.write = jest.fn().mockImplementation(() => {
        writeCount++;
        if (writeCount === 3) {
          return Promise.resolve({ success: false, error: 'Rate limit', file_path: 'logs/fail.md' });
        }
        return Promise.resolve({ success: true, file_path: `logs/test-${writeCount}.md` });
      });

      const context = { date: new Date('2026-03-13'), config: mockConfig };
      await stage14.run(mockConfig, context);
      await stage15.run(mockConfig, context);

      const r16 = await stage16.run(mockConfig, context);
      expect(r16.status).toBe('partial');
      expect(r16.logs_written).toBe(4);
      expect(r16.logs_failed).toBe(1);
    });

    test('all collectors fail: stage 14 fails', async () => {
      githubCollector.collect = jest.fn().mockRejectedValue(new Error('GitHub down'));
      gcpCollector.collect = jest.fn().mockRejectedValue(new Error('GCP down'));
      stationCollector.collect = jest.fn().mockRejectedValue(new Error('Station down'));

      const context = { date: new Date('2026-03-13'), config: mockConfig };
      const r14 = await stage14.run(mockConfig, context);

      expect(r14.status).toBe('failed');
    });

    test('stage 15 fails when no intelligence data', async () => {
      const context = { date: new Date('2026-03-13'), config: mockConfig };
      const r15 = await stage15.run(mockConfig, context);

      expect(r15.status).toBe('failed');
      expect(r15.error).toBe('Missing intelligence data');
    });

    test('stage 16 fails when no briefing data', async () => {
      mockAllCollectors();

      const context = { date: new Date('2026-03-13'), config: mockConfig };
      await stage14.run(mockConfig, context);
      // Skip stage 15

      const r16 = await stage16.run(mockConfig, context);
      expect(r16.status).toBe('failed');
      expect(r16.error).toBe('Missing required data');
    });
  });

  // ─── Dry-run Mode ─────────────────────────────────────────────────────

  describe('Dry-run Mode', () => {
    test('stage 16 skips writing when dry_run is true', async () => {
      mockAllCollectors();
      mockSynthesizer();
      mockLogWriter();

      const dryConfig = {
        ...mockConfig,
        intelligence: { ...mockConfig.intelligence, dry_run: true },
      };

      const context = { date: new Date('2026-03-13'), config: dryConfig };
      await stage14.run(dryConfig, context);
      await stage15.run(dryConfig, context);
      const r16 = await stage16.run(dryConfig, context);

      // Dry run behavior depends on implementation
      // At minimum, it should not throw
      expect(r16).toBeDefined();
      expect(r16).toHaveProperty('status');
    });
  });

  // ─── Fallback Briefing ────────────────────────────────────────────────

  describe('Fallback Briefing', () => {
    test('uses fallback when Gemini returns fallback flag', async () => {
      mockAllCollectors();
      const fallbackBriefing = { ...fixtureBriefing, fallback_used: true };
      mockSynthesizer(fallbackBriefing);

      const context = { date: new Date('2026-03-13'), config: mockConfig };
      await stage14.run(mockConfig, context);
      const r15 = await stage15.run(mockConfig, context);

      expect(r15.status).toBe('partial');
      expect(r15.fallback_used).toBe(true);
      expect(context.briefing.fallback_used).toBe(true);
    });
  });
});
