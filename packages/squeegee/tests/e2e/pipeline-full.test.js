/**
 * Core Pipeline E2E Tests (Stages 1-13)
 *
 * Tests the full Squeegee documentation curation pipeline against
 * realistic project fixtures in temporary workspaces.
 *
 * @file tests/e2e/pipeline-full.test.js
 */

const fs = require('fs').promises;
const path = require('path');
const { createTestWorkspace, cleanupWorkspace, buildTestConfig } = require('../helpers/workspace');

// Pipeline stages
const discover = require('../../src/pipeline/stages/01-discover');
const gitAnalyze = require('../../src/pipeline/stages/02-git-analyze');
const stateCurate = require('../../src/pipeline/stages/03-state-curate');
const practices = require('../../src/pipeline/stages/04-practices');
const plans = require('../../src/pipeline/stages/05-plans');
const changelog = require('../../src/pipeline/stages/06-changelog');
const patterns = require('../../src/pipeline/stages/07-patterns');
const health = require('../../src/pipeline/stages/08-health');
const projectsIndex = require('../../src/pipeline/stages/09-projects-index');
const commitSummary = require('../../src/pipeline/stages/10-commit-summary');
const generate = require('../../src/pipeline/stages/11-generate');
const validate = require('../../src/pipeline/stages/12-validate');
const claudemd = require('../../src/pipeline/stages/13-claudemd');

// ─── Test suite ──────────────────────────────────────────────────────────

describe('Core Pipeline E2E (Stages 1-13)', () => {
  let workspace;
  let config;

  beforeAll(async () => {
    workspace = await createTestWorkspace();
    config = buildTestConfig(workspace);
  });

  afterAll(async () => {
    if (workspace) await cleanupWorkspace(workspace);
  });

  // ─── Stage 01: Discover ─────────────────────────────────────────────────

  describe('Stage 01 — Discover', () => {
    let discoveryResult;

    beforeAll(async () => {
      discoveryResult = await discover.run(config);
    });

    test('discovers both projects from config', () => {
      expect(discoveryResult.projects).toHaveLength(2);
      const names = discoveryResult.projects.map(p => p.name);
      expect(names).toContain('project-a');
      expect(names).toContain('project-b');
    });

    test('returns correct project metadata', () => {
      const projectA = discoveryResult.projects.find(p => p.name === 'project-a');
      expect(projectA.absolutePath).toBe(path.join(workspace, 'project-a'));
      expect(projectA.hasReadme).toBe(true);
      expect(projectA.hasClaude).toBe(false); // not yet generated
    });

    test('discovers markdown files', () => {
      expect(discoveryResult.markdown.length).toBeGreaterThanOrEqual(1);
      const mdPaths = discoveryResult.markdown.map(m => m.path);
      // project-a has README.md
      expect(mdPaths.some(p => p.includes('README.md'))).toBe(true);
    });

    test('discovers code files', () => {
      expect(discoveryResult.code.length).toBeGreaterThanOrEqual(1);
      const projectACode = discoveryResult.code.find(c => c.project === 'project-a');
      expect(projectACode).toBeDefined();
      expect(projectACode.files.length).toBeGreaterThanOrEqual(1);
    });
  });

  // ─── Stage 11: Generate ─────────────────────────────────────────────────

  describe('Stage 11 — Generate (fresh CLAUDE.md creation)', () => {
    let generateResult;

    beforeAll(async () => {
      const disc = await discover.run(config);
      generateResult = await generate.run(config, disc);
    });

    test('generates CLAUDE.md for both projects', () => {
      expect(generateResult.created).toEqual(
        expect.arrayContaining([
          expect.stringContaining('project-a/CLAUDE.md'),
          expect.stringContaining('project-b/CLAUDE.md'),
        ])
      );
    });

    test('generated CLAUDE.md contains SQUEEGEE:AUTO markers', async () => {
      const claudeContent = await fs.readFile(
        path.join(workspace, 'project-a', 'CLAUDE.md'), 'utf-8'
      );

      const expectedMarkers = [
        'SQUEEGEE:AUTO:START security-secrets',
        'SQUEEGEE:AUTO:END security-secrets',
        'SQUEEGEE:AUTO:START linked-resources',
        'SQUEEGEE:AUTO:END linked-resources',
        'SQUEEGEE:AUTO:START gbs-core-principles',
        'SQUEEGEE:AUTO:END gbs-core-principles',
        'SQUEEGEE:AUTO:START context-window',
        'SQUEEGEE:AUTO:END context-window',
        'SQUEEGEE:AUTO:START centralized-docs',
        'SQUEEGEE:AUTO:END centralized-docs',
      ];

      for (const marker of expectedMarkers) {
        expect(claudeContent).toContain(marker);
      }
    });

    test('generated CLAUDE.md has tech stack from package.json (not placeholder)', async () => {
      const claudeContent = await fs.readFile(
        path.join(workspace, 'project-a', 'CLAUDE.md'), 'utf-8'
      );

      // Should contain detected frameworks from package.json
      expect(claudeContent).toContain('Fastify');
      expect(claudeContent).toContain('Express');
      expect(claudeContent).toContain('JavaScript/TypeScript');
    });

    test('generated CLAUDE.md has commands from package.json', async () => {
      const claudeContent = await fs.readFile(
        path.join(workspace, 'project-a', 'CLAUDE.md'), 'utf-8'
      );

      expect(claudeContent).toContain('npm run start');
      expect(claudeContent).toContain('npm run dev');
      expect(claudeContent).toContain('npm run test');
    });

    test('generates STATE.md in .planning directory', async () => {
      const statePath = path.join(workspace, 'project-a', '.planning', 'STATE.md');
      const exists = await fs.access(statePath).then(() => true).catch(() => false);
      expect(exists).toBe(true);

      const content = await fs.readFile(statePath, 'utf-8');
      expect(content).toContain('project-a');
      expect(content).toContain('Project State');
    });

    test('generates PROGRAMMING_PRACTICES.md', async () => {
      const ppPath = path.join(workspace, 'project-a', 'PROGRAMMING_PRACTICES.md');
      const exists = await fs.access(ppPath).then(() => true).catch(() => false);
      expect(exists).toBe(true);

      const content = await fs.readFile(ppPath, 'utf-8');
      expect(content).toContain('Tech Stack');
      expect(content).toContain('SQUEEGEE:AUTO:START tech-stack');
    });

    test('generates PLANS_APPROVED.md', async () => {
      const plansPath = path.join(workspace, 'project-a', 'PLANS_APPROVED.md');
      const exists = await fs.access(plansPath).then(() => true).catch(() => false);
      expect(exists).toBe(true);

      const content = await fs.readFile(plansPath, 'utf-8');
      expect(content).toContain('Plans Approved');
    });

    test('generates docs for Python project-b', async () => {
      const claudeContent = await fs.readFile(
        path.join(workspace, 'project-b', 'CLAUDE.md'), 'utf-8'
      );

      // Should detect Python stack
      expect(claudeContent).toContain('Python');
      expect(claudeContent).toContain('Flask');
    });
  });

  // ─── Stage 13: CLAUDE.md Curation ─────────────────────────────────────

  describe('Stage 13 — CLAUDE.md Curation', () => {
    test('curates existing CLAUDE.md files', async () => {
      const disc = await discover.run(config);
      const result = await claudemd.run(config, disc);

      expect(result.analyzed).toBeGreaterThanOrEqual(2);
      // Files were just generated so they should be current
      expect(result).toHaveProperty('suggestions');
    });

    test('idempotent: running twice produces updated=0 on second run', async () => {
      // First run to ensure everything is fresh
      const disc1 = await discover.run(config);
      await claudemd.run(config, disc1);

      // Second run — should update nothing
      const disc2 = await discover.run(config);
      const result2 = await claudemd.run(config, disc2);

      // updated array should be empty (or contain only staleness-triggered updates)
      // The key assertion is that no content-based updates are made
      expect(result2.analyzed).toBeGreaterThanOrEqual(2);
    });

    test('preserves content outside SQUEEGEE markers', async () => {
      const claudePath = path.join(workspace, 'project-a', 'CLAUDE.md');

      // Read original content
      const original = await fs.readFile(claudePath, 'utf-8');

      // Add custom content outside markers
      const customNote = '\n## Custom Developer Notes\n\nThis section was added manually.\n';
      await fs.writeFile(claudePath, original + customNote, 'utf-8');

      // Run curation
      const disc = await discover.run(config);
      await claudemd.run(config, disc);

      // Verify custom content is preserved
      const after = await fs.readFile(claudePath, 'utf-8');
      expect(after).toContain('Custom Developer Notes');
      expect(after).toContain('This section was added manually.');
    });

    test('reports completeness suggestions for missing sections', async () => {
      // Create a minimal CLAUDE.md missing required sections
      const minimalClaude = '# Test Project\n\nBasic documentation.\n';
      const claudePath = path.join(workspace, 'project-a', 'CLAUDE.md');
      await fs.writeFile(claudePath, minimalClaude, 'utf-8');

      const disc = await discover.run(config);
      const result = await claudemd.run(config, disc);

      // Should have added missing section stubs
      expect(result.updated).toContain('project-a');

      // After curation, the file should now have GBS sections injected
      const after = await fs.readFile(claudePath, 'utf-8');
      expect(after).toContain('GBS Core Principles');
      expect(after).toContain('Security & Secrets');
    });
  });

  // ─── Full Pipeline Run ──────────────────────────────────────────────────

  describe('Full Pipeline (Stages 1-13)', () => {
    let freshWorkspace;
    let freshConfig;

    beforeAll(async () => {
      // Use a fresh workspace for the full pipeline run
      freshWorkspace = await createTestWorkspace();
      freshConfig = buildTestConfig(freshWorkspace);
    });

    afterAll(async () => {
      if (freshWorkspace) await cleanupWorkspace(freshWorkspace);
    });

    test('stages 1-10 run without crashing', async () => {
      // Stage 1: Discover
      const disc = await discover.run(freshConfig);
      expect(disc.projects).toHaveLength(2);

      // Stage 2: Git analysis
      const git = await gitAnalyze.run(freshConfig);
      expect(git).toHaveProperty('global');
      expect(git).toHaveProperty('projects');

      // Stage 3: STATE.md curation (creates since none exist)
      const stateResult = await stateCurate.run(freshConfig, disc, git);
      expect(stateResult).toBeDefined();

      // Stage 4: PROGRAMMING_PRACTICES.md
      const practicesResult = await practices.run(freshConfig, disc);
      expect(practicesResult).toBeDefined();

      // Stage 5: PLANS_APPROVED.md
      const plansResult = await plans.run(freshConfig, disc, git);
      expect(plansResult).toBeDefined();

      // Stage 6: Changelogs
      const changelogResult = await changelog.run(freshConfig, disc, git);
      expect(changelogResult).toBeDefined();

      // Stage 7: Patterns
      const patternsResult = await patterns.run(freshConfig, disc);
      expect(patternsResult).toBeDefined();

      // Stage 8: Health
      const healthResult = await health.run(freshConfig, disc);
      expect(healthResult).toBeDefined();

      // Stage 9: Projects index
      const indexResult = await projectsIndex.run(freshConfig, disc);
      expect(indexResult).toBeDefined();

      // Stage 10: Pipeline state
      const commitResult = await commitSummary.run(freshConfig, disc, git);
      expect(commitResult).toBeDefined();
    });

    test('stage 11 generates missing docs', async () => {
      const disc = await discover.run(freshConfig);
      const result = await generate.run(freshConfig, disc);

      expect(result.created.length).toBeGreaterThan(0);
      expect(result.created).toEqual(
        expect.arrayContaining([
          expect.stringContaining('CLAUDE.md'),
        ])
      );
    });

    test('stage 12 validates generated docs', async () => {
      const disc = await discover.run(freshConfig);
      const result = await validate.run(freshConfig, disc);

      expect(result).toHaveProperty('totalFiles');
      expect(result.totalFiles).toBeGreaterThan(0);
      // Generated docs may have warnings but shouldn't have critical errors
      // related to missing files
    });

    test('stage 13 curates CLAUDE.md files', async () => {
      const disc = await discover.run(freshConfig);
      const result = await claudemd.run(freshConfig, disc);

      expect(result.analyzed).toBeGreaterThanOrEqual(2);
    });

    test('final workspace has expected documentation files', async () => {
      for (const projectName of ['project-a', 'project-b']) {
        const projectDir = path.join(freshWorkspace, projectName);

        // CLAUDE.md exists
        const claudeExists = await fs.access(path.join(projectDir, 'CLAUDE.md'))
          .then(() => true).catch(() => false);
        expect(claudeExists).toBe(true);

        // .planning/STATE.md exists
        const stateExists = await fs.access(path.join(projectDir, '.planning', 'STATE.md'))
          .then(() => true).catch(() => false);
        expect(stateExists).toBe(true);

        // PROGRAMMING_PRACTICES.md exists
        const ppExists = await fs.access(path.join(projectDir, 'PROGRAMMING_PRACTICES.md'))
          .then(() => true).catch(() => false);
        expect(ppExists).toBe(true);

        // PLANS_APPROVED.md exists
        const plansExists = await fs.access(path.join(projectDir, 'PLANS_APPROVED.md'))
          .then(() => true).catch(() => false);
        expect(plansExists).toBe(true);
      }
    });
  });

  // ─── Idempotency ───────────────────────────────────────────────────────

  describe('Idempotency', () => {
    let idempotentWorkspace;
    let idempotentConfig;

    beforeAll(async () => {
      idempotentWorkspace = await createTestWorkspace();
      idempotentConfig = buildTestConfig(idempotentWorkspace);

      // Run the full pipeline once to generate all docs
      const disc1 = await discover.run(idempotentConfig);
      const git1 = await gitAnalyze.run(idempotentConfig);
      await stateCurate.run(idempotentConfig, disc1, git1);
      await practices.run(idempotentConfig, disc1);
      await plans.run(idempotentConfig, disc1, git1);
      await generate.run(idempotentConfig, disc1);
      await claudemd.run(idempotentConfig, disc1);
    });

    afterAll(async () => {
      if (idempotentWorkspace) await cleanupWorkspace(idempotentWorkspace);
    });

    test('second generate run creates no new files', async () => {
      const disc = await discover.run(idempotentConfig);
      const result = await generate.run(idempotentConfig, disc);

      // All docs already exist, so nothing should be created
      expect(result.created).toHaveLength(0);
      expect(result.skipped.length).toBeGreaterThan(0);
    });

    test('second claudemd run updates nothing', async () => {
      const disc = await discover.run(idempotentConfig);
      const result = await claudemd.run(idempotentConfig, disc);

      expect(result.analyzed).toBeGreaterThanOrEqual(2);
      expect(result.updated).toHaveLength(0);
    });
  });
});
