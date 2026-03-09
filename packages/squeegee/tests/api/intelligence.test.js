/**
 * Tests for Intelligence API Endpoints
 *
 * @file tests/api/intelligence.test.js
 */

const fastify = require('fastify');
const fs = require('fs').promises;
const path = require('path');

// Mock intelligence modules
jest.mock('../../intelligence/github-collector');
jest.mock('../../intelligence/gcp-collector');
jest.mock('../../intelligence/station-monitor');
jest.mock('../../intelligence/log-writer');
jest.mock('../../intelligence/gemini-synthesizer');
jest.mock('../../intelligence/claude-md-auditor');
jest.mock('../../intelligence/slack-notifier');

const githubCollector = require('../../intelligence/github-collector');
const gcpCollector = require('../../intelligence/gcp-collector');
const stationMonitor = require('../../intelligence/station-monitor');
const logWriter = require('../../intelligence/log-writer');
const geminiSynthesizer = require('../../intelligence/gemini-synthesizer');
const claudeMdAuditor = require('../../intelligence/claude-md-auditor');
const slackNotifier = require('../../intelligence/slack-notifier');

const intelligenceRoutes = require('../../src/api/intelligence');

// Mock configuration factory — returns a fresh deep copy each time
function createMockConfig() {
  return {
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
      doc_quality_audit: {
        enabled: true,
        threshold: 5,
        auto_pr_enabled: true
      },
      dry_run: false
    },
    notifications: {
      slack: { enabled: true, webhook_url: 'https://hooks.slack.com/test' },
      hub: { enabled: true, webhook_url: 'https://hub.test/api/webhooks' }
    },
    github_token: 'test-github-token'
  };
}

// Helper to set up default fs.readFile mock
function setupFsReadFileMock(configOverride) {
  const config = configOverride || createMockConfig();
  fs.readFile.mockImplementation(async (filePath) => {
    if (filePath.includes('intelligence.config.json')) {
      return JSON.stringify(config);
    }
    if (filePath.includes('gemini-api-key')) {
      return 'test-gemini-key';
    }
    if (filePath.includes('github-pat')) {
      return 'test-github-token';
    }
    throw new Error('File not found');
  });
}

// Initial mock setup
jest.spyOn(fs, 'readFile');
setupFsReadFileMock();

describe('Intelligence API - POST /api/intelligence/run', () => {
  let app;

  beforeEach(async () => {
    app = fastify({ logger: false });
    await app.register(intelligenceRoutes, { prefix: '/api/intelligence' });

    // Reset mocks and re-setup fs.readFile (clearAllMocks wipes implementations)
    jest.clearAllMocks();
    setupFsReadFileMock();

    // Setup default mock responses
    githubCollector.collect.mockResolvedValue({
      repos: {
        'test-repo-1': {
          commits: [{ sha: 'abc123', message: 'test commit', author: 'Alice' }],
          pull_requests: [],
          issues: [],
          ci_runs: []
        }
      },
      summary: {
        total_commits: 1,
        total_prs: 0,
        total_issues: 0,
        total_ci_runs: 0
      }
    });

    gcpCollector.collect.mockResolvedValue({
      deployments: [],
      errors: [],
      summary: {
        total_deployments: 0,
        total_errors: 0,
        projects_monitored: 1
      }
    });

    stationMonitor.collect.mockResolvedValue({
      claude_code_sessions: [],
      cursor_active: false,
      squeegee_state: {}
    });

    geminiSynthesizer.synthesize.mockResolvedValue({
      date: '2026-03-13',
      executive_summary: ['Test briefing'],
      repository_activity: 'Test activity',
      deployment_events: 'No deployments',
      development_activity: 'No sessions',
      context_checkpoints: 'No checkpoints',
      observations: 'All quiet',
      generated_at: '2026-03-13T10:00:00Z',
      model_used: 'gemini-2.0-flash-exp',
      token_count: { input: 1000, output: 500 },
      fallback_used: false,
      error: null
    });

    logWriter.writeAll.mockResolvedValue();

    claudeMdAuditor.auditAll.mockResolvedValue([
      { repo: 'test-repo-1', score: 13, missing_points: [], needs_pr: false },
      { repo: 'test-repo-2', score: 9, missing_points: [11, 12], needs_pr: true }
    ]);

    slackNotifier.notify.mockResolvedValue({
      success: true,
      skipped: false,
      channel: '#main',
      timestamp: '2026-03-13T10:00:00Z',
      message_ts: '1234567890.123456',
      error: null
    });
  });

  afterEach(async () => {
    await app.close();
  });

  it('should run full intelligence pipeline with default date', async () => {
    const response = await app.inject({
      method: 'POST',
      url: '/api/intelligence/run',
      payload: {}
    });

    expect(response.statusCode).toBe(200);
    const body = JSON.parse(response.body);

    expect(body.status).toBe('success');
    expect(body.date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(body.stages).toHaveLength(7);
    expect(body.duration_ms).toBeGreaterThan(0);

    // Verify stage results
    const collectStage = body.stages.find(s => s.name === 'intelligence-collect');
    expect(collectStage.status).toBe('success');

    const synthesizeStage = body.stages.find(s => s.name === 'intelligence-synthesize');
    expect(synthesizeStage.status).toBe('success');

    const writeStage = body.stages.find(s => s.name === 'intelligence-write');
    expect(writeStage.status).toBe('success');

    // Verify collectors were called
    expect(githubCollector.collect).toHaveBeenCalled();
    expect(gcpCollector.collect).toHaveBeenCalled();
    expect(stationMonitor.collect).toHaveBeenCalled();
    expect(geminiSynthesizer.synthesize).toHaveBeenCalled();
    expect(logWriter.writeAll).toHaveBeenCalled();
  });

  it('should accept custom date parameter', async () => {
    const response = await app.inject({
      method: 'POST',
      url: '/api/intelligence/run',
      payload: { date: '2026-03-13' }
    });

    expect(response.statusCode).toBe(200);
    const body = JSON.parse(response.body);

    expect(body.date).toBe('2026-03-13');

    // Verify collectors called with correct date
    expect(githubCollector.collect).toHaveBeenCalledWith('2026-03-13', expect.any(Object));
  });

  it('should reject invalid date format', async () => {
    // Use a value that passes Fastify schema (YYYY-MM-DD pattern) but fails Date parsing
    const response = await app.inject({
      method: 'POST',
      url: '/api/intelligence/run',
      payload: { date: '2026-13-01' }
    });

    expect(response.statusCode).toBe(500);
    const body = JSON.parse(response.body);
    expect(body.status).toBe('failed');
    expect(body.error).toContain('Invalid date');
  });

  it('should skip write stage in dry-run mode', async () => {
    // Override config to enable dry-run
    const dryRunConfig = createMockConfig();
    dryRunConfig.intelligence.dry_run = true;
    setupFsReadFileMock(dryRunConfig);

    const response = await app.inject({
      method: 'POST',
      url: '/api/intelligence/run',
      payload: {}
    });

    expect(response.statusCode).toBe(200);
    const body = JSON.parse(response.body);

    const writeStage = body.stages.find(s => s.name === 'intelligence-write');
    expect(writeStage.status).toBe('skipped');
    expect(writeStage.summary).toContain('Dry run');
    expect(logWriter.writeAll).not.toHaveBeenCalled();
  });

  it('should run CLAUDE.md audit on Sunday', async () => {
    // Mock Date to return Sunday — return clones so parseDateParam mutations don't affect future calls
    const realDate = Date;
    const mockTime = new Date('2026-03-15T10:00:00Z').getTime(); // Sunday
    global.Date = class extends realDate {
      constructor(...args) {
        if (args.length === 0) {
          return new realDate(mockTime);
        }
        return new realDate(...args);
      }
      static now() {
        return mockTime;
      }
    };

    const response = await app.inject({
      method: 'POST',
      url: '/api/intelligence/run',
      payload: {}
    });

    expect(response.statusCode).toBe(200);
    const body = JSON.parse(response.body);

    const auditStage = body.stages.find(s => s.name === 'intelligence-audit-claude');
    expect(auditStage.status).toBe('success');
    expect(claudeMdAuditor.auditAll).toHaveBeenCalled();

    global.Date = realDate;
  });

  it('should skip CLAUDE.md audit on weekday', async () => {
    // Mock Date to return Monday — return clones so parseDateParam mutations don't affect future calls
    const realDate = Date;
    const mockTime = new Date('2026-03-16T10:00:00Z').getTime(); // Monday
    global.Date = class extends realDate {
      constructor(...args) {
        if (args.length === 0) {
          return new realDate(mockTime);
        }
        return new realDate(...args);
      }
      static now() {
        return mockTime;
      }
    };

    const response = await app.inject({
      method: 'POST',
      url: '/api/intelligence/run',
      payload: {}
    });

    expect(response.statusCode).toBe(200);
    const body = JSON.parse(response.body);

    const auditStage = body.stages.find(s => s.name === 'intelligence-audit-claude');
    expect(auditStage.status).toBe('skipped');
    expect(auditStage.summary).toContain('Not Sunday');
    expect(claudeMdAuditor.auditAll).not.toHaveBeenCalled();

    global.Date = realDate;
  });

  it('should force CLAUDE.md audit when requested', async () => {
    const response = await app.inject({
      method: 'POST',
      url: '/api/intelligence/run',
      payload: {
        force: {
          claudeMdAudit: true
        }
      }
    });

    expect(response.statusCode).toBe(200);
    const body = JSON.parse(response.body);

    const auditStage = body.stages.find(s => s.name === 'intelligence-audit-claude');
    expect(auditStage.status).toBe('success');
    expect(claudeMdAuditor.auditAll).toHaveBeenCalled();
  });

  it('should return 503 when intelligence is disabled', async () => {
    // Override config to disable intelligence
    const disabledConfig = createMockConfig();
    disabledConfig.intelligence.enabled = false;
    setupFsReadFileMock(disabledConfig);

    const response = await app.inject({
      method: 'POST',
      url: '/api/intelligence/run',
      payload: {}
    });

    expect(response.statusCode).toBe(503);
    const body = JSON.parse(response.body);
    expect(body.status).toBe('disabled');
  });

  it('should handle stage failures gracefully', async () => {
    githubCollector.collect.mockRejectedValue(new Error('GitHub API error'));

    const response = await app.inject({
      method: 'POST',
      url: '/api/intelligence/run',
      payload: {}
    });

    expect(response.statusCode).toBe(200);
    const body = JSON.parse(response.body);

    expect(body.status).toBe('partial');
    const collectStage = body.stages.find(s => s.name === 'intelligence-collect');
    expect(collectStage.status).toBe('failed');
    expect(collectStage.error).toContain('GitHub API error');
  });
});

describe('Intelligence API - POST /api/intelligence/collect', () => {
  let app;

  beforeEach(async () => {
    app = fastify({ logger: false });
    await app.register(intelligenceRoutes, { prefix: '/api/intelligence' });

    jest.clearAllMocks();
    setupFsReadFileMock();

    githubCollector.collect.mockResolvedValue({
      repos: {
        'test-repo-1': {
          commits: [{ sha: 'abc123', message: 'test', author: 'Alice' }],
          pull_requests: [{ number: 1, title: 'Test PR', state: 'open', author: 'Bob', labels: [] }],
          issues: [],
          ci_runs: []
        }
      },
      summary: { total_commits: 1, total_prs: 1, total_issues: 0, total_ci_runs: 0 }
    });

    gcpCollector.collect.mockResolvedValue({
      deployments: [{ project: 'test', service: 'test-service', status: 'success', revision: 'rev1', timestamp: '2026-03-13T10:00:00Z' }],
      errors: [],
      summary: { total_deployments: 1, total_errors: 0, projects_monitored: 1 }
    });

    stationMonitor.collect.mockResolvedValue({
      claude_code_sessions: [{ project_name: 'test-project', memory_files_count: 5, estimated_tokens: 20000 }],
      cursor_active: true,
      squeegee_state: { last_run: '2026-03-13T06:00:00Z', repos_processed: 27 }
    });
  });

  afterEach(async () => {
    await app.close();
  });

  it('should collect intelligence data successfully', async () => {
    const response = await app.inject({
      method: 'POST',
      url: '/api/intelligence/collect',
      payload: { date: '2026-03-13' }
    });

    expect(response.statusCode).toBe(200);
    const body = JSON.parse(response.body);

    expect(body.status).toBe('success');
    expect(body.date).toBe('2026-03-13');
    expect(body.data).toHaveProperty('github');
    expect(body.data).toHaveProperty('gcp');
    expect(body.data).toHaveProperty('station');
    expect(body.data).toHaveProperty('checkpoints');

    expect(body.metrics).toEqual({
      repos_active: 1,
      total_commits: 1,
      total_prs: 1,
      deployments: 1,
      errors: 0,
      sessions: 1
    });
  });

  it('should use yesterday as default date', async () => {
    const response = await app.inject({
      method: 'POST',
      url: '/api/intelligence/collect',
      payload: {}
    });

    expect(response.statusCode).toBe(200);
    const body = JSON.parse(response.body);

    expect(body.date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(githubCollector.collect).toHaveBeenCalled();
  });

  it('should handle collection errors', async () => {
    gcpCollector.collect.mockRejectedValue(new Error('Permission denied'));

    const response = await app.inject({
      method: 'POST',
      url: '/api/intelligence/collect',
      payload: {}
    });

    expect(response.statusCode).toBe(500);
    const body = JSON.parse(response.body);
    expect(body.status).toBe('failed');
    expect(body.error).toContain('Permission denied');
  });
});

describe('Intelligence API - POST /api/intelligence/synthesize', () => {
  let app;

  beforeEach(async () => {
    app = fastify({ logger: false });
    await app.register(intelligenceRoutes, { prefix: '/api/intelligence' });

    jest.clearAllMocks();
    setupFsReadFileMock();

    geminiSynthesizer.synthesize.mockResolvedValue({
      date: '2026-03-13',
      executive_summary: ['Test summary'],
      repository_activity: 'Test activity',
      deployment_events: 'Test deployments',
      development_activity: 'Test dev activity',
      context_checkpoints: 'Test checkpoints',
      observations: 'Test observations',
      generated_at: '2026-03-13T10:00:00Z',
      model_used: 'gemini-2.0-flash-exp',
      token_count: { input: 2000, output: 1000 },
      fallback_used: false,
      error: null
    });
  });

  afterEach(async () => {
    await app.close();
  });

  it('should synthesize briefing from collected data', async () => {
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

    const response = await app.inject({
      method: 'POST',
      url: '/api/intelligence/synthesize',
      payload: {
        date: '2026-03-13',
        data: collectedData
      }
    });

    expect(response.statusCode).toBe(200);
    const body = JSON.parse(response.body);

    expect(body.status).toBe('success');
    expect(body.briefing).toHaveProperty('executive_summary');
    expect(body.briefing).toHaveProperty('repository_activity');
    expect(body.briefing.date).toBe('2026-03-13');
    expect(geminiSynthesizer.synthesize).toHaveBeenCalled();
  });

  it('should reject missing required fields', async () => {
    const response = await app.inject({
      method: 'POST',
      url: '/api/intelligence/synthesize',
      payload: {
        date: '2026-03-13'
        // Missing 'data' field
      }
    });

    expect(response.statusCode).toBe(400);
  });
});

describe('Intelligence API - POST /api/intelligence/audit-claude-md', () => {
  let app;

  beforeEach(async () => {
    app = fastify({ logger: false });
    await app.register(intelligenceRoutes, { prefix: '/api/intelligence' });

    jest.clearAllMocks();
    setupFsReadFileMock();

    claudeMdAuditor.auditAll.mockResolvedValue([
      { repo: 'repo-1', score: 13, missing_points: [], needs_pr: false },
      { repo: 'repo-2', score: 11, missing_points: [13], needs_pr: false },
      { repo: 'repo-3', score: 9, missing_points: [11, 12, 13], needs_pr: true },
      { repo: 'repo-4', score: 6, missing_points: [9, 10, 11, 12, 13], needs_pr: true }
    ]);
  });

  afterEach(async () => {
    await app.close();
  });

  it('should run CLAUDE.md audit and return summary', async () => {
    const response = await app.inject({
      method: 'POST',
      url: '/api/intelligence/audit-claude-md'
    });

    expect(response.statusCode).toBe(200);
    const body = JSON.parse(response.body);

    expect(body.status).toBe('success');
    expect(body.report.repos_audited).toBe(4);
    expect(body.report.summary.excellent).toBe(1);
    expect(body.report.summary.good).toBe(1);
    expect(body.report.summary.needs_work).toBe(1);
    expect(body.report.summary.critical).toBe(1);
    expect(body.report.details).toHaveLength(4);
  });
});

describe('Intelligence API - GET /api/intelligence/status', () => {
  let app;

  beforeEach(async () => {
    app = fastify({ logger: false });
    await app.register(intelligenceRoutes, { prefix: '/api/intelligence' });

    jest.clearAllMocks();
    setupFsReadFileMock();
  });

  afterEach(async () => {
    await app.close();
  });

  it('should return system status', async () => {
    const response = await app.inject({
      method: 'GET',
      url: '/api/intelligence/status'
    });

    expect(response.statusCode).toBe(200);
    const body = JSON.parse(response.body);

    expect(body.status).toBe('healthy');
    expect(body.enabled).toBe(true);
    expect(body.dry_run).toBe(false);
    expect(body.modules).toHaveProperty('github-collector');
    expect(body.modules).toHaveProperty('gemini-synthesizer');
    expect(body.next_scheduled).toHaveProperty('daily');
    expect(body.next_scheduled).toHaveProperty('weekly_audit');
    expect(body.next_scheduled).toHaveProperty('monthly_audit');
    expect(body.next_scheduled).toHaveProperty('quarterly_research');
  });

  it('should indicate missing Gemini API key', async () => {
    // Override config to have no API key
    const noKeyConfig = createMockConfig();
    delete noKeyConfig.intelligence.gemini.apiKey;
    setupFsReadFileMock(noKeyConfig);

    const response = await app.inject({
      method: 'GET',
      url: '/api/intelligence/status'
    });

    expect(response.statusCode).toBe(200);
    const body = JSON.parse(response.body);

    expect(body.modules['gemini-synthesizer']).toBe('missing_api_key');
  });
});

describe('Intelligence API - Unimplemented Endpoints', () => {
  let app;

  beforeEach(async () => {
    app = fastify({ logger: false });
    await app.register(intelligenceRoutes, { prefix: '/api/intelligence' });
  });

  afterEach(async () => {
    await app.close();
  });

  it('should return 501 for doc quality audit', async () => {
    const response = await app.inject({
      method: 'POST',
      url: '/api/intelligence/audit-doc-quality'
    });

    expect(response.statusCode).toBe(501);
    const body = JSON.parse(response.body);
    expect(body.status).toBe('not_implemented');
  });

  it('should return 501 for research', async () => {
    const response = await app.inject({
      method: 'POST',
      url: '/api/intelligence/research',
      payload: { topic: 'test-topic' }
    });

    expect(response.statusCode).toBe(501);
    const body = JSON.parse(response.body);
    expect(body.status).toBe('not_implemented');
  });

  it('should send Slack notification via notify endpoint', async () => {
    const response = await app.inject({
      method: 'POST',
      url: '/api/intelligence/notify',
      payload: {
        briefing: { executive_summary: ['Test'] },
        date: '2026-03-13'
      }
    });

    expect(response.statusCode).toBe(200);
    const body = JSON.parse(response.body);
    expect(body.status).toBe('success');
    expect(body.channel).toBe('#main');
    expect(slackNotifier.notify).toHaveBeenCalled();
  });
});
