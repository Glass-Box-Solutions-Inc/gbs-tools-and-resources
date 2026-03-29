/**
 * Portal Pipeline E2E Tests (Stages 21-23)
 *
 * End-to-end tests for the portal pipeline with all external APIs mocked:
 * GitHub API, Linear API, Gemini API, and GCS.
 *
 * @file tests/e2e/portal-pipeline.test.js
 */

'use strict';

const fs   = require('fs').promises;
const path = require('path');

// ─── Jest module mocks (must be declared before require of the stages) ────────
//
// Several stages use destructured imports:
//   const { renderPortal } = require('../../portal/renderer')
//   const { uploadToGCS }  = require('../../portal/gcs-uploader')
//   const { fetchReadme, createOctokit } = require('../../portal/github-client')
//   const { saveProjectCache } = require('../../portal/project-cache')
//
// Monkey-patching module.exports after the fact cannot intercept those bindings.
// jest.mock() replaces the module in the require cache before any stage loads it,
// so all consumers — including the ones that destructure — get the mock.

jest.mock('../../src/portal/github-client', () => ({
  collectAll:        jest.fn(),
  collectSingleRepo: jest.fn(),
  createOctokit:     jest.fn(),
  fetchReadme:       jest.fn(),
  fetchCommits:      jest.fn(),
  fetchContributors: jest.fn(),
  fetchOpenPRs:      jest.fn(),
  computeHealthScore: jest.fn(),
  buildDevelopers:   jest.fn(),
  buildHeatmap:      jest.fn(),
}));

jest.mock('../../src/portal/linear-client', () => ({
  collectSprintData: jest.fn(),
}));

jest.mock('../../src/portal/project-cache', () => ({
  saveProjectCache: jest.fn(),
  loadProjectCache: jest.fn(),
}));

jest.mock('../../src/portal/ai-cache', () => ({
  loadCache:           jest.fn(),
  saveCache:           jest.fn(),
  hasChanged:          jest.fn(),
  updateCacheEntry:    jest.fn(),
  loadContentFromCache: jest.fn(),
  getCachedProject:    jest.fn(),
  CACHE_FILE:          '/tmp/test-portal-ai-cache.json',
}));

jest.mock('../../src/portal/diagram-generator', () => ({
  computeContentHash:     jest.fn(),
  generateAllDiagrams:    jest.fn(),
  fallbackArchitectureDiagram: jest.fn(),
  fallbackDataFlowDiagram: jest.fn(),
  fallbackSequenceDiagram: jest.fn(),
  cleanMermaidOutput:     jest.fn(),
  validateMermaid:        jest.fn(),
}));

jest.mock('../../src/portal/explanation-generator', () => ({
  generateDiagramExplanation: jest.fn(),
  generateProjectExplanation: jest.fn(),
  generateUserJourney:        jest.fn(),
}));

jest.mock('../../src/portal/renderer', () => ({
  renderPortal:    jest.fn(),
  buildContext:    jest.fn(),
  getNavSections:  jest.fn(),
  CATEGORY_DISPLAY: {},
  STATUS_DISPLAY:   {},
}));

jest.mock('../../src/portal/gcs-uploader', () => ({
  uploadToGCS: jest.fn(),
}));

// ─── Import mocked modules (references to jest.fn() instances) ───────────────

const githubClient   = require('../../src/portal/github-client');
const linearClient   = require('../../src/portal/linear-client');
const projectCache   = require('../../src/portal/project-cache');
const aiCache        = require('../../src/portal/ai-cache');
const diagramGen     = require('../../src/portal/diagram-generator');
const explanationGen = require('../../src/portal/explanation-generator');
const renderer       = require('../../src/portal/renderer');
const gcsUploader    = require('../../src/portal/gcs-uploader');

// ─── Pipeline stages (loaded after mocks are in place) ───────────────────────

const stage21 = require('../../src/pipeline/stages/21-portal-collect');
const stage22 = require('../../src/pipeline/stages/22-portal-ai');
const stage23 = require('../../src/pipeline/stages/23-portal-render');

// ─── Shared fixtures ─────────────────────────────────────────────────────────

const MOCK_REPO_CONFIGS = [
  {
    name: 'adjudica-ai-app',
    status: 'deployed',
    category: 'adjudica-platform',
    description: 'Core Adjudica platform',
    stack: ['React', 'Fastify', 'Prisma'],
    url: 'https://app.adjudica.ai',
    priority: 1,
  },
  {
    name: 'merus-expert',
    status: 'active',
    category: 'meruscase-integration',
    description: 'MerusCase domain agent',
    stack: ['Python', 'FastAPI'],
    priority: 2,
  },
];

const MOCK_GITHUB_DATA = {
  projects: [
    {
      name: 'adjudica-ai-app',
      repo_path: 'Glass-Box-Solutions-Inc/adjudica-ai-app',
      status: 'deployed',
      category: 'adjudica-platform',
      description: 'Core Adjudica platform',
      tech_stack: ['React', 'Fastify', 'Prisma'],
      contributors: ['alice', 'bob'],
      production_url: 'https://app.adjudica.ai',
      commit_count_30d: 42,
      health_score: 95,
      last_commit_date: '2026-03-26T10:00:00Z',
    },
    {
      name: 'merus-expert',
      repo_path: 'Glass-Box-Solutions-Inc/merus-expert',
      status: 'active',
      category: 'meruscase-integration',
      description: 'MerusCase domain agent',
      tech_stack: ['Python', 'FastAPI'],
      contributors: ['alice'],
      production_url: null,
      commit_count_30d: 12,
      health_score: 77,
      last_commit_date: '2026-03-25T14:00:00Z',
    },
  ],
  developers: [
    { name: 'alice', total_commits: 180, active_projects: ['adjudica-ai-app', 'merus-expert'] },
    { name: 'bob',   total_commits: 60,  active_projects: ['adjudica-ai-app'] },
  ],
  recent_commits: {
    'adjudica-ai-app': [
      { sha: 'abc1234', message: 'feat: add case timeline', author: 'alice', timestamp: '2026-03-26T10:00:00Z', repo_name: 'adjudica-ai-app', url: '' },
    ],
    'merus-expert': [
      { sha: 'def5678', message: 'fix: timeout handling', author: 'alice', timestamp: '2026-03-25T14:00:00Z', repo_name: 'merus-expert', url: '' },
    ],
  },
  heatmap: [
    { developer_name: 'alice', project_name: 'adjudica-ai-app', commit_count: 150, expertise_level: 'expert',    recent_commits: 30 },
    { developer_name: 'bob',   project_name: 'adjudica-ai-app', commit_count: 60,  expertise_level: 'proficient', recent_commits: 12 },
    { developer_name: 'alice', project_name: 'merus-expert',    commit_count: 30,  expertise_level: 'proficient', recent_commits: 12 },
  ],
  activity_feed: [
    { event_type: 'commit', title: 'feat: add case timeline', author: 'alice', timestamp: '2026-03-26T10:00:00Z', repo_name: 'adjudica-ai-app', url: '' },
  ],
  all_commits_365d: [
    { sha: 'abc1234', message: 'feat: add case timeline', author: 'alice', timestamp: '2026-03-26T10:00:00Z', repo_name: 'adjudica-ai-app' },
    { sha: 'def5678', message: 'fix: timeout handling',  author: 'alice', timestamp: '2026-03-25T14:00:00Z', repo_name: 'merus-expert' },
  ],
};

const MOCK_PORTAL_CONFIG = {
  repos: MOCK_REPO_CONFIGS,
  output_dir: '/tmp/portal-e2e-test-output',
  gcs: { bucket: 'gbs-portal', prefix: '', dry_run: true },
};

const MOCK_AI_CONTENT = {
  diagrams: {
    'adjudica-ai-app': {
      mermaid_code: 'graph TD\n    Client --> API --> DB',
      explanation:  { technical: 'Architecture overview', non_technical: 'How the app works' },
      data_flow: {
        mermaid_code: 'flowchart LR\n    Input --> Process --> Output',
        explanation:  { technical: 'Data flow', non_technical: 'Data movement' },
      },
      sequence: null,
    },
  },
  project_explanations: {
    'adjudica-ai-app': { technical: 'Fastify + React app', non_technical: 'Legal AI platform' },
  },
  user_journeys: {
    'adjudica-ai-app': '<p>Step 1: Login. Step 2: View case.</p>',
  },
};

const EMPTY_AI_CACHE = { version: 1, projects: {} };

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** Write portal.config.json into a temp directory that stage 21 will read */
async function writePortalConfig(dir, config = MOCK_PORTAL_CONFIG) {
  const configDir = path.join(dir, 'config');
  await fs.mkdir(configDir, { recursive: true });
  await fs.writeFile(
    path.join(configDir, 'portal.config.json'),
    JSON.stringify(config),
    'utf-8'
  );
}

/** Apply the standard set of mock return values for a typical happy-path run */
function setupHappyPathMocks() {
  githubClient.collectAll.mockResolvedValue(MOCK_GITHUB_DATA);
  linearClient.collectSprintData.mockResolvedValue({});
  projectCache.saveProjectCache.mockResolvedValue(undefined);

  aiCache.loadCache.mockResolvedValue({ ...EMPTY_AI_CACHE, projects: {} });
  aiCache.saveCache.mockResolvedValue(undefined);
  aiCache.hasChanged.mockReturnValue(true);
  aiCache.updateCacheEntry.mockImplementation(() => {});
  aiCache.loadContentFromCache.mockReturnValue(MOCK_AI_CONTENT);

  diagramGen.computeContentHash.mockReturnValue('hash-abc123');
  diagramGen.generateAllDiagrams.mockResolvedValue({
    architecture: 'graph TD\n    A --> B',
    data_flow:    'flowchart LR\n    X --> Y',
    sequence:     'sequenceDiagram\n    A->>B: request',
  });

  githubClient.createOctokit.mockReturnValue({});
  githubClient.fetchReadme.mockResolvedValue('# README content');

  explanationGen.generateDiagramExplanation.mockResolvedValue({
    technical: 'Technical explanation', non_technical: 'Plain explanation',
  });
  explanationGen.generateProjectExplanation.mockResolvedValue({
    technical: 'Project tech detail', non_technical: 'Project plain detail',
  });
  explanationGen.generateUserJourney.mockResolvedValue('<p>User journey HTML</p>');

  renderer.renderPortal.mockResolvedValue({
    pages_rendered: 15,
    output_dir: '/tmp/portal-e2e-test-output',
  });
  gcsUploader.uploadToGCS.mockResolvedValue({ files_uploaded: 20, bytes_uploaded: 1024000 });
}

// ─── Test Suite ───────────────────────────────────────────────────────────────

describe('Portal Pipeline E2E (Stages 21-23)', () => {
  const testOutputDir = '/tmp/portal-e2e-test-output';
  const originalCwd   = process.cwd();

  beforeAll(async () => {
    await fs.mkdir(testOutputDir, { recursive: true });
    await writePortalConfig(testOutputDir);
    // Stage 21 resolves portal.config.json relative to process.cwd()
    process.chdir(testOutputDir);
    process.env.GITHUB_PAT        = 'test-github-pat';
    process.env.GOOGLE_AI_API_KEY = 'test-gemini-key';
  });

  afterAll(async () => {
    process.chdir(originalCwd);
    delete process.env.GITHUB_PAT;
    delete process.env.GOOGLE_AI_API_KEY;
    try { await fs.rm(testOutputDir, { recursive: true, force: true }); } catch {}
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  // ─── Test 1: Stages 21-23 run in sequence without errors ─────────────────

  describe('Full Portal Pipeline (21 → 22 → 23)', () => {
    test('all three stages complete successfully with mocked external APIs', async () => {
      setupHappyPathMocks();

      // Stage 21: Portal collect
      const r21 = await stage21.run({}, {});
      expect(r21).toBeDefined();
      expect(r21.projects).toBeDefined();
      expect(r21.sprints).toBeDefined();
      expect(r21.repo_configs).toBeDefined();
      expect(r21.portal_config).toBeDefined();

      // Stage 22: AI content generation
      const r22 = await stage22.run({}, r21);
      expect(r22).toBeDefined();
      expect(r22).toHaveProperty('diagrams');
      expect(r22).toHaveProperty('project_explanations');
      expect(r22).toHaveProperty('user_journeys');

      // Stage 23: Render and upload
      const r23 = await stage23.run({}, r21, r22);
      expect(r23).toBeDefined();
      expect(r23).toHaveProperty('pages_rendered');
      expect(r23).toHaveProperty('output_dir');
    });

    test('data produced by stage 21 flows correctly into stage 22 and 23', async () => {
      setupHappyPathMocks();

      const r21 = await stage21.run({}, {});

      // Stage 22 receives the project list from stage 21
      await stage22.run({}, r21);
      expect(diagramGen.computeContentHash).toHaveBeenCalledWith(
        expect.objectContaining({ name: expect.any(String) })
      );

      // Stage 23 passes merged portal data to renderPortal
      await stage23.run({}, r21, MOCK_AI_CONTENT);
      expect(renderer.renderPortal).toHaveBeenCalledWith(
        expect.objectContaining({
          projects:             r21.projects,
          sprints:              r21.sprints,
          diagrams:             MOCK_AI_CONTENT.diagrams,
          project_explanations: MOCK_AI_CONTENT.project_explanations,
          user_journeys:        MOCK_AI_CONTENT.user_journeys,
        }),
        r21.repo_configs,
        expect.any(String)
      );
    });
  });

  // ─── Test 2: Stage 21 data structure ─────────────────────────────────────

  describe('Stage 21 — Portal Data Collection', () => {
    test('result contains all required top-level fields', async () => {
      setupHappyPathMocks();

      const result = await stage21.run({}, {});

      expect(result).toHaveProperty('projects');
      expect(result).toHaveProperty('developers');
      expect(result).toHaveProperty('recent_commits');
      expect(result).toHaveProperty('heatmap');
      expect(result).toHaveProperty('activity_feed');
      expect(result).toHaveProperty('all_commits_365d');
      expect(result).toHaveProperty('sprints');
      expect(result).toHaveProperty('repo_configs');
      expect(result).toHaveProperty('portal_config');
    });

    test('projects array contains objects with expected shape', async () => {
      setupHappyPathMocks();

      const result = await stage21.run({}, {});

      expect(result.projects).toHaveLength(2);
      for (const project of result.projects) {
        expect(project).toHaveProperty('name');
        expect(project).toHaveProperty('status');
        expect(project).toHaveProperty('category');
        expect(project).toHaveProperty('health_score');
        expect(project).toHaveProperty('commit_count_30d');
        expect(project).toHaveProperty('contributors');
        expect(typeof project.health_score).toBe('number');
        expect(project.health_score).toBeGreaterThanOrEqual(0);
        expect(project.health_score).toBeLessThanOrEqual(100);
      }
    });

    test('repo_configs matches repos from portal.config.json', async () => {
      setupHappyPathMocks();

      const result = await stage21.run({}, {});

      expect(result.repo_configs).toHaveLength(MOCK_REPO_CONFIGS.length);
      const names = result.repo_configs.map((r) => r.name);
      expect(names).toContain('adjudica-ai-app');
      expect(names).toContain('merus-expert');
    });

    test('calls githubClient.collectAll with repo configs and token', async () => {
      setupHappyPathMocks();

      await stage21.run({}, {});

      expect(githubClient.collectAll).toHaveBeenCalledTimes(1);
      expect(githubClient.collectAll).toHaveBeenCalledWith(
        expect.arrayContaining([
          expect.objectContaining({ name: 'adjudica-ai-app' }),
        ]),
        expect.any(String)
      );
    });

    test('calls linearClient.collectSprintData', async () => {
      setupHappyPathMocks();

      await stage21.run({}, {});

      expect(linearClient.collectSprintData).toHaveBeenCalledTimes(1);
    });

    test('calls saveProjectCache with collected data', async () => {
      setupHappyPathMocks();

      await stage21.run({}, {});

      expect(projectCache.saveProjectCache).toHaveBeenCalledTimes(1);
      expect(projectCache.saveProjectCache).toHaveBeenCalledWith(
        MOCK_GITHUB_DATA.projects,
        MOCK_GITHUB_DATA.recent_commits,
        expect.any(Object), // activityByRepo — keyed by repo name
        MOCK_GITHUB_DATA.all_commits_365d
      );
    });

    test('sprints defaults to empty object when Linear returns no data', async () => {
      setupHappyPathMocks();
      linearClient.collectSprintData.mockResolvedValue({});

      const result = await stage21.run({}, {});

      expect(result.sprints).toEqual({});
    });
  });

  // ─── Test 3: Stage 22 handles missing/partial data gracefully ────────────

  describe('Stage 22 — AI Content Generation (partial/missing data)', () => {
    test('returns empty content structure when collectData has no projects', async () => {
      setupHappyPathMocks();
      aiCache.loadContentFromCache.mockReturnValue({
        diagrams: {},
        project_explanations: {},
        user_journeys: {},
      });

      const result = await stage22.run({}, { projects: [] });

      expect(result).toHaveProperty('diagrams');
      expect(result).toHaveProperty('project_explanations');
      expect(result).toHaveProperty('user_journeys');
      // No diagrams generated when there are no projects
      expect(diagramGen.generateAllDiagrams).not.toHaveBeenCalled();
    });

    test('returns empty content structure when collectData is undefined', async () => {
      setupHappyPathMocks();
      aiCache.loadContentFromCache.mockReturnValue({
        diagrams: {},
        project_explanations: {},
        user_journeys: {},
      });

      const result = await stage22.run({}, undefined);

      expect(result).toBeDefined();
      expect(result.diagrams).toEqual({});
      expect(diagramGen.generateAllDiagrams).not.toHaveBeenCalled();
    });

    test('skips AI generation for unchanged projects (cache hit)', async () => {
      setupHappyPathMocks();
      aiCache.hasChanged.mockReturnValue(false);

      await stage22.run({}, { projects: MOCK_GITHUB_DATA.projects });

      expect(diagramGen.generateAllDiagrams).not.toHaveBeenCalled();
      expect(explanationGen.generateProjectExplanation).not.toHaveBeenCalled();
    });

    test('generates AI content for each changed project', async () => {
      setupHappyPathMocks();
      aiCache.hasChanged.mockReturnValue(true);

      await stage22.run({}, { projects: MOCK_GITHUB_DATA.projects });

      // One call per project (2 projects in fixture)
      expect(diagramGen.generateAllDiagrams).toHaveBeenCalledTimes(2);
      expect(explanationGen.generateProjectExplanation).toHaveBeenCalledTimes(2);
      expect(explanationGen.generateUserJourney).toHaveBeenCalledTimes(2);
    });

    test('continues processing remaining projects when one diagram generation fails', async () => {
      setupHappyPathMocks();
      aiCache.hasChanged.mockReturnValue(true);

      let callCount = 0;
      diagramGen.generateAllDiagrams.mockImplementation(() => {
        callCount++;
        if (callCount === 1) {
          return Promise.reject(new Error('Gemini quota exceeded'));
        }
        return Promise.resolve({
          architecture: 'graph TD\n    A --> B',
          data_flow:    'flowchart LR\n    X --> Y',
          sequence:     'sequenceDiagram\n    A->>B: ok',
        });
      });

      // Should not throw — failures are caught per-project
      const result = await stage22.run({}, { projects: MOCK_GITHUB_DATA.projects });

      expect(result).toBeDefined();
      // Both projects attempted regardless of first failure
      expect(diagramGen.generateAllDiagrams).toHaveBeenCalledTimes(2);
    });

    test('saves updated cache after generation', async () => {
      setupHappyPathMocks();
      aiCache.hasChanged.mockReturnValue(true);

      await stage22.run({}, { projects: MOCK_GITHUB_DATA.projects });

      expect(aiCache.saveCache).toHaveBeenCalledTimes(1);
    });

    test('loads final content from cache after generation', async () => {
      setupHappyPathMocks();

      await stage22.run({}, { projects: MOCK_GITHUB_DATA.projects });

      expect(aiCache.loadContentFromCache).toHaveBeenCalledTimes(1);
    });
  });

  // ─── Test 4: Stage 23 produces valid HTML output ─────────────────────────

  describe('Stage 23 — Portal Render', () => {
    test('calls renderPortal with correctly assembled portal data', async () => {
      setupHappyPathMocks();

      const collectData = {
        ...MOCK_GITHUB_DATA,
        sprints:       {},
        repo_configs:  MOCK_REPO_CONFIGS,
        portal_config: MOCK_PORTAL_CONFIG,
      };

      await stage23.run({}, collectData, MOCK_AI_CONTENT);

      expect(renderer.renderPortal).toHaveBeenCalledTimes(1);
      const [portalData, repoConfigs, outputDir] = renderer.renderPortal.mock.calls[0];

      expect(portalData.projects).toEqual(MOCK_GITHUB_DATA.projects);
      expect(portalData.developers).toEqual(MOCK_GITHUB_DATA.developers);
      expect(portalData.heatmap).toEqual(MOCK_GITHUB_DATA.heatmap);
      expect(portalData.diagrams).toEqual(MOCK_AI_CONTENT.diagrams);
      expect(portalData.project_explanations).toEqual(MOCK_AI_CONTENT.project_explanations);
      expect(portalData.user_journeys).toEqual(MOCK_AI_CONTENT.user_journeys);
      expect(typeof portalData.generated_at).toBe('string');
      expect(repoConfigs).toEqual(MOCK_REPO_CONFIGS);
      expect(typeof outputDir).toBe('string');
    });

    test('returns result with pages_rendered and output_dir', async () => {
      setupHappyPathMocks();
      renderer.renderPortal.mockResolvedValue({
        pages_rendered: 17,
        output_dir: '/tmp/portal-e2e-test-output',
      });

      const collectData = {
        ...MOCK_GITHUB_DATA,
        sprints:       {},
        repo_configs:  MOCK_REPO_CONFIGS,
        portal_config: MOCK_PORTAL_CONFIG,
      };

      const result = await stage23.run({}, collectData, MOCK_AI_CONTENT);

      expect(result.pages_rendered).toBe(17);
      expect(result.output_dir).toBe('/tmp/portal-e2e-test-output');
    });

    test('computes correct derived counts (total_active, total_deployed)', async () => {
      setupHappyPathMocks();

      const collectData = {
        ...MOCK_GITHUB_DATA,
        sprints:       {},
        repo_configs:  MOCK_REPO_CONFIGS,
        portal_config: MOCK_PORTAL_CONFIG,
      };

      await stage23.run({}, collectData, MOCK_AI_CONTENT);

      const [portalData] = renderer.renderPortal.mock.calls[0];
      // MOCK_GITHUB_DATA: 1 deployed (adjudica-ai-app) + 1 active (merus-expert)
      expect(portalData.total_active_projects).toBe(1);
      expect(portalData.total_deployed_projects).toBe(1);
    });

    test('handles completely empty collectData without throwing', async () => {
      setupHappyPathMocks();

      const result = await stage23.run({}, {}, {});

      expect(result).toBeDefined();
      expect(renderer.renderPortal).toHaveBeenCalledTimes(1);

      const [portalData] = renderer.renderPortal.mock.calls[0];
      expect(portalData.projects).toEqual([]);
      expect(portalData.heatmap).toEqual([]);
      expect(portalData.total_active_projects).toBe(0);
      expect(portalData.total_deployed_projects).toBe(0);
    });

    test('handles missing aiContent without throwing', async () => {
      setupHappyPathMocks();

      const collectData = {
        ...MOCK_GITHUB_DATA,
        sprints:       {},
        repo_configs:  MOCK_REPO_CONFIGS,
        portal_config: MOCK_PORTAL_CONFIG,
      };

      const result = await stage23.run({}, collectData, undefined);

      expect(result).toBeDefined();
      const [portalData] = renderer.renderPortal.mock.calls[0];
      expect(portalData.diagrams).toEqual({});
      expect(portalData.project_explanations).toEqual({});
      expect(portalData.user_journeys).toEqual({});
    });

    test('skips GCS upload when no bucket is configured', async () => {
      setupHappyPathMocks();

      const collectData = {
        ...MOCK_GITHUB_DATA,
        sprints:       {},
        repo_configs:  MOCK_REPO_CONFIGS,
        portal_config: { ...MOCK_PORTAL_CONFIG, gcs: undefined }, // no bucket
      };

      const result = await stage23.run({}, collectData, MOCK_AI_CONTENT);

      expect(gcsUploader.uploadToGCS).not.toHaveBeenCalled();
      expect(result.upload).toBeNull();
    });

    test('calls uploadToGCS when bucket is configured and upload is enabled', async () => {
      setupHappyPathMocks();
      // PORTAL_GCS_UPLOAD=1 disables dry-run guard
      const originalEnv = process.env.PORTAL_GCS_UPLOAD;
      process.env.PORTAL_GCS_UPLOAD = '1';

      const collectData = {
        ...MOCK_GITHUB_DATA,
        sprints:       {},
        repo_configs:  MOCK_REPO_CONFIGS,
        portal_config: MOCK_PORTAL_CONFIG, // has gcs.bucket = 'gbs-portal'
      };

      const result = await stage23.run({}, collectData, MOCK_AI_CONTENT);

      expect(gcsUploader.uploadToGCS).toHaveBeenCalledTimes(1);
      expect(gcsUploader.uploadToGCS).toHaveBeenCalledWith(
        expect.any(String),   // outputDir
        'gbs-portal',         // bucket from MOCK_PORTAL_CONFIG
        expect.any(String),   // prefix
        expect.objectContaining({ dryRun: expect.any(Boolean) })
      );
      expect(result.upload).toBeDefined();

      if (originalEnv === undefined) {
        delete process.env.PORTAL_GCS_UPLOAD;
      } else {
        process.env.PORTAL_GCS_UPLOAD = originalEnv;
      }
    });

    test('CSV exports are written to the output directory', async () => {
      setupHappyPathMocks();

      // Use a real output directory so we can inspect the CSV files.
      // renderPortal is still mocked — CSV writing happens in stage 23's own
      // generateExports() helper, which uses real fs.
      const csvOutputDir = '/tmp/portal-e2e-csv-test';
      renderer.renderPortal.mockResolvedValue({
        pages_rendered: 1,
        output_dir: csvOutputDir,
      });

      const collectData = {
        ...MOCK_GITHUB_DATA,
        sprints:       {},
        repo_configs:  MOCK_REPO_CONFIGS,
        portal_config: { ...MOCK_PORTAL_CONFIG, output_dir: csvOutputDir },
      };

      await stage23.run({}, collectData, MOCK_AI_CONTENT);

      // Verify all three CSV files exist
      const heatmapExists  = await fs.access(path.join(csvOutputDir, 'exports', 'heatmap.csv')).then(() => true).catch(() => false);
      const projectsExists = await fs.access(path.join(csvOutputDir, 'exports', 'projects.csv')).then(() => true).catch(() => false);
      const devsExists     = await fs.access(path.join(csvOutputDir, 'exports', 'developers.csv')).then(() => true).catch(() => false);

      expect(heatmapExists).toBe(true);
      expect(projectsExists).toBe(true);
      expect(devsExists).toBe(true);

      // Verify heatmap CSV has header and data rows
      const heatmapContent = await fs.readFile(path.join(csvOutputDir, 'exports', 'heatmap.csv'), 'utf-8');
      expect(heatmapContent).toContain('Developer');
      expect(heatmapContent).toContain('Project');
      expect(heatmapContent).toContain('alice');
      expect(heatmapContent).toContain('adjudica-ai-app');

      // Verify projects CSV has header and data rows
      const projectsContent = await fs.readFile(path.join(csvOutputDir, 'exports', 'projects.csv'), 'utf-8');
      expect(projectsContent).toContain('Project');
      expect(projectsContent).toContain('Health Score');
      expect(projectsContent).toContain('adjudica-ai-app');

      // Verify developers CSV has header and data rows
      const devsContent = await fs.readFile(path.join(csvOutputDir, 'exports', 'developers.csv'), 'utf-8');
      expect(devsContent).toContain('Developer');
      expect(devsContent).toContain('Total Commits');
      expect(devsContent).toContain('alice');

      await fs.rm(csvOutputDir, { recursive: true, force: true });
    });
  });
});
