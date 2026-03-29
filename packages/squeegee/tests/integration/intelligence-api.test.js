/**
 * Intelligence API Integration Tests
 *
 * Tests REST API endpoints with real Fastify server bootstrap,
 * mocked intelligence modules, and fixture-based test data.
 *
 * @file tests/integration/intelligence-api.test.js
 */

const path = require('path');
const fsSync = require('fs');
const fs = require('fs').promises;
const Fastify = require('fastify');

// Mock intelligence modules before requiring them
jest.mock('../../intelligence/github-collector');
jest.mock('../../intelligence/gcp-collector');
jest.mock('../../intelligence/station-collector');
jest.mock('../../intelligence/log-writer');
jest.mock('../../intelligence/gemini-synthesizer');
jest.mock('../../intelligence/claude-md-auditor');
jest.mock('../../intelligence/slack-notifier');
jest.mock('../../intelligence/doc-quality-auditor');
jest.mock('../../intelligence/web-researcher');

const githubCollector = require('../../intelligence/github-collector');
const gcpCollector = require('../../intelligence/gcp-collector');
const stationCollector = require('../../intelligence/station-collector');
const logWriter = require('../../intelligence/log-writer');
const geminiSynthesizer = require('../../intelligence/gemini-synthesizer');
const claudeMdAuditor = require('../../intelligence/claude-md-auditor');
const slackNotifier = require('../../intelligence/slack-notifier');
const docQualityAuditor = require('../../intelligence/doc-quality-auditor');
const webResearcher = require('../../intelligence/web-researcher');

const intelligenceRoutes = require('../../src/api/intelligence');

// Load fixtures once
const fixturesPath = path.join(__dirname, '..', 'fixtures');
const fixtureGithub = JSON.parse(fsSync.readFileSync(path.join(fixturesPath, 'github-activity.json'), 'utf-8'));
const fixtureGcp = JSON.parse(fsSync.readFileSync(path.join(fixturesPath, 'gcp-logs.json'), 'utf-8'));
const fixtureStation = JSON.parse(fsSync.readFileSync(path.join(fixturesPath, 'station-activity.json'), 'utf-8'));
const fixtureBriefing = JSON.parse(fsSync.readFileSync(path.join(fixturesPath, 'gemini-briefing.json'), 'utf-8'));

// Mock fs.readFile for config loading
jest.spyOn(fs, 'readFile');

function setupConfigMock() {
  const mockConfig = {
    intelligence: {
      enabled: true,
      repos: ['test-repo-1', 'test-repo-2'],
      gcp_projects: ['test-project'],
      docs_repo: 'Test-Org/test-docs',
      gemini: {
        model: 'gemini-2.0-flash-exp',
        temperature: 0.3,
        max_output_tokens: 4096,
        apiKey: 'test-api-key'
      },
      claude_md_audit: {
        enabled: true,
        threshold: 10,
        reopen_delay_days: 30,
        auto_pr_enabled: true
      },
      doc_quality_audit: { enabled: true, threshold: 5, auto_pr_enabled: true },
      dry_run: false
    },
    notifications: {
      slack: { enabled: true, webhook_url: 'https://hooks.slack.com/test' },
      hub: { enabled: true, webhook_url: 'https://hub.test/api/webhooks' }
    },
    github_token: 'test-github-token'
  };

  fs.readFile.mockImplementation(async (filePath) => {
    if (filePath.includes('intelligence.config.json')) {
      return JSON.stringify(mockConfig);
    }
    if (filePath.includes('gemini-api-key')) return 'test-gemini-key';
    if (filePath.includes('github-pat')) return 'test-github-token';
    throw new Error('File not found');
  });
}

// Helper: create Fastify instance with auth hook
async function createTestApp() {
  const app = Fastify({ logger: false });

  // Mock auth — accept any Bearer token, reject missing
  app.addHook('onRequest', async (request, reply) => {
    const auth = request.headers.authorization;
    if (!auth || !auth.startsWith('Bearer ')) {
      reply.code(401).send({ error: 'Unauthorized' });
    }
  });

  await app.register(intelligenceRoutes, { prefix: '/api/intelligence' });
  return app;
}

describe('Intelligence API Integration', () => {
  let app;

  beforeEach(async () => {
    jest.clearAllMocks();
    setupConfigMock();
    app = await createTestApp();
  });

  afterEach(async () => {
    await app.close();
  });

  describe('POST /api/intelligence/run', () => {
    beforeEach(() => {
      githubCollector.collect.mockResolvedValue(fixtureGithub);
      gcpCollector.collect.mockResolvedValue(fixtureGcp);
      stationCollector.collect.mockResolvedValue(fixtureStation);
      geminiSynthesizer.synthesize.mockResolvedValue(fixtureBriefing);
      logWriter.writeAll.mockResolvedValue();
      claudeMdAuditor.auditAll.mockResolvedValue([
        { repo: 'test-repo-1', score: 13, needs_pr: false },
        { repo: 'test-repo-2', score: 9, needs_pr: true }
      ]);
      slackNotifier.notify.mockResolvedValue({
        success: true,
        channel: '#main',
        message_ts: '1234567890.123456',
        error: null
      });
    });

    it('should run full pipeline successfully', async () => {
      const response = await app.inject({
        method: 'POST',
        url: '/api/intelligence/run',
        headers: { authorization: 'Bearer test-token' },
        payload: { date: '2026-03-13' }
      });

      expect(response.statusCode).toBe(200);
      const body = JSON.parse(response.body);

      expect(body.status).toBe('success');
      expect(body.date).toBe('2026-03-13');
      expect(body.stages.length).toBeGreaterThan(0);

      const collectStage = body.stages.find(s => s.name === 'intelligence-collect');
      expect(collectStage.status).toBe('success');

      const synthesizeStage = body.stages.find(s => s.name === 'intelligence-synthesize');
      expect(synthesizeStage.status).toBe('success');

      const writeStage = body.stages.find(s => s.name === 'intelligence-write');
      expect(writeStage.status).toBe('success');
    });

    it('should reject request without authorization', async () => {
      const response = await app.inject({
        method: 'POST',
        url: '/api/intelligence/run',
        payload: { date: '2026-03-13' }
      });

      expect(response.statusCode).toBe(401);
      const body = JSON.parse(response.body);
      expect(body.error).toBe('Unauthorized');
    });

    it('should reject invalid date format', async () => {
      const response = await app.inject({
        method: 'POST',
        url: '/api/intelligence/run',
        headers: { authorization: 'Bearer test-token' },
        payload: { date: 'invalid-date' }
      });

      expect(response.statusCode).toBe(400);
    });

    it('should use yesterday as default date', async () => {
      const response = await app.inject({
        method: 'POST',
        url: '/api/intelligence/run',
        headers: { authorization: 'Bearer test-token' },
        payload: {}
      });

      expect(response.statusCode).toBe(200);
      const body = JSON.parse(response.body);

      expect(body.status).toBe('success');
      expect(body.date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    });

    it('should force CLAUDE.md audit when requested', async () => {
      claudeMdAuditor.auditAll.mockResolvedValue([
        { repo: 'test', score: 12, needs_pr: false }
      ]);

      const response = await app.inject({
        method: 'POST',
        url: '/api/intelligence/run',
        headers: { authorization: 'Bearer test-token' },
        payload: {
          date: '2026-03-10',
          force: { claudeMdAudit: true }
        }
      });

      expect(response.statusCode).toBe(200);
      const body = JSON.parse(response.body);

      const auditStage = body.stages.find(s => s.name === 'intelligence-audit-claude');
      expect(auditStage.status).toBe('success');
      expect(claudeMdAuditor.auditAll).toHaveBeenCalled();
    });
  });

  describe('POST /api/intelligence/collect', () => {
    beforeEach(() => {
      githubCollector.collect.mockResolvedValue(fixtureGithub);
      gcpCollector.collect.mockResolvedValue(fixtureGcp);
      stationCollector.collect.mockResolvedValue(fixtureStation);
    });

    it('should collect data from all sources', async () => {
      const response = await app.inject({
        method: 'POST',
        url: '/api/intelligence/collect',
        headers: { authorization: 'Bearer test-token' },
        payload: { date: '2026-03-13' }
      });

      expect(response.statusCode).toBe(200);
      const body = JSON.parse(response.body);

      expect(body.status).toBe('success');
      expect(body.date).toBe('2026-03-13');
      expect(body.data.github).toEqual(fixtureGithub);
      expect(body.data.gcp).toEqual(fixtureGcp);
      expect(body.data.station).toEqual(fixtureStation);
      expect(body.metrics.total_commits).toBe(4);
      expect(body.metrics.repos_active).toBe(3);
    });

    it('should return error when collection fails', async () => {
      githubCollector.collect.mockRejectedValue(new Error('GitHub API unavailable'));

      const response = await app.inject({
        method: 'POST',
        url: '/api/intelligence/collect',
        headers: { authorization: 'Bearer test-token' },
        payload: { date: '2026-03-13' }
      });

      expect(response.statusCode).toBe(500);
      const body = JSON.parse(response.body);
      expect(body.status).toBe('failed');
      expect(body.error).toContain('GitHub API unavailable');
    });
  });

  describe('POST /api/intelligence/synthesize', () => {
    it('should generate briefing from collected data', async () => {
      geminiSynthesizer.synthesize.mockResolvedValue(fixtureBriefing);

      const response = await app.inject({
        method: 'POST',
        url: '/api/intelligence/synthesize',
        headers: { authorization: 'Bearer test-token' },
        payload: {
          date: '2026-03-13',
          data: {
            github: fixtureGithub,
            gcp: fixtureGcp,
            station: fixtureStation
          }
        }
      });

      expect(response.statusCode).toBe(200);
      const body = JSON.parse(response.body);
      expect(body.status).toBe('success');
      expect(body.briefing).toBeDefined();
      expect(geminiSynthesizer.synthesize).toHaveBeenCalled();
    });

    it('should reject request without required fields', async () => {
      const response = await app.inject({
        method: 'POST',
        url: '/api/intelligence/synthesize',
        headers: { authorization: 'Bearer test-token' },
        payload: { date: '2026-03-13' }
      });

      expect(response.statusCode).toBe(400);
    });
  });

  describe('POST /api/intelligence/audit-claude-md', () => {
    it('should run CLAUDE.md compliance audit', async () => {
      claudeMdAuditor.auditAll.mockResolvedValue([
        { repo: 'adjudica-ai-app', score: 14, needs_pr: false },
        { repo: 'glassy-personal-ai', score: 12, needs_pr: false },
        { repo: 'command-center', score: 11, needs_pr: false },
        { repo: 'legacy-repo', score: 5, needs_pr: true }
      ]);

      const response = await app.inject({
        method: 'POST',
        url: '/api/intelligence/audit-claude-md',
        headers: { authorization: 'Bearer test-token' }
      });

      expect(response.statusCode).toBe(200);
      const body = JSON.parse(response.body);

      expect(body.status).toBe('success');
      expect(body.report.repos_audited).toBe(4);
      expect(body.report.summary.excellent).toBe(1);
      expect(body.report.summary.good).toBe(2);
      expect(body.report.summary.critical).toBe(1);
    });
  });

  describe('Doc quality audit & research endpoints', () => {
    it('should return 200 with audit results for doc quality audit', async () => {
      docQualityAuditor.audit.mockResolvedValue({
        repos_audited: 10,
        summary: {
          average_score: 82.5,
          needs_work: 2,
          critical: 1
        }
      });

      const response = await app.inject({
        method: 'POST',
        url: '/api/intelligence/audit-doc-quality',
        headers: { authorization: 'Bearer test-token' }
      });

      expect(response.statusCode).toBe(200);
      const body = JSON.parse(response.body);
      expect(body.status).toBe('success');
      expect(body.report).toBeDefined();
      expect(docQualityAuditor.audit).toHaveBeenCalled();
    });

    it('should return 200 with research results', async () => {
      webResearcher.research.mockResolvedValue({
        topic: 'test-topic',
        findings: ['Finding 1'],
        recommendations: ['Rec 1']
      });

      const response = await app.inject({
        method: 'POST',
        url: '/api/intelligence/research',
        headers: { authorization: 'Bearer test-token' },
        payload: { topic: 'test-topic' }
      });

      expect(response.statusCode).toBe(200);
      const body = JSON.parse(response.body);
      expect(body.status).toBe('success');
      expect(body.report).toBeDefined();
      expect(webResearcher.research).toHaveBeenCalled();
    });

    it('should send Slack notification via notify endpoint', async () => {
      slackNotifier.notify.mockResolvedValue({
        success: true,
        channel: '#main',
        message_ts: '1234567890.123456',
        error: null
      });

      const response = await app.inject({
        method: 'POST',
        url: '/api/intelligence/notify',
        headers: { authorization: 'Bearer test-token' },
        payload: { briefing: { executive_summary: ['Test'] }, date: '2026-03-13' }
      });

      expect(response.statusCode).toBe(200);
      const body = JSON.parse(response.body);
      expect(body.status).toBe('success');
      expect(body.channel).toBe('#main');
    });
  });

  describe('GET /api/intelligence/status', () => {
    it('should return system health status', async () => {
      const response = await app.inject({
        method: 'GET',
        url: '/api/intelligence/status',
        headers: { authorization: 'Bearer test-token' }
      });

      expect(response.statusCode).toBe(200);
      const body = JSON.parse(response.body);

      expect(body.status).toBe('healthy');
      expect(body.enabled).toBe(true);
      expect(body.modules['github-collector']).toBe('ok');
      expect(body.next_scheduled).toHaveProperty('daily');
      expect(body.next_scheduled).toHaveProperty('weekly_audit');
    });

    it('should reject request without authorization', async () => {
      const response = await app.inject({
        method: 'GET',
        url: '/api/intelligence/status'
      });

      expect(response.statusCode).toBe(401);
    });
  });
});
