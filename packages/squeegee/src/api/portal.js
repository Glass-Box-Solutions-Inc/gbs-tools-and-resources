/**
 * Portal API Routes
 *
 * REST API endpoints for portal generation (stages 21-23).
 * Provides manual triggers for portal generation, single-repo refresh,
 * and generation status.
 *
 * @file src/api/portal.js
 * @module api/portal
 */

'use strict';

const fs = require('fs').promises;
const path = require('path');

// Import portal pipeline stages
const portalCollect = require('../pipeline/stages/21-portal-collect');
const portalAI = require('../pipeline/stages/22-portal-ai');
const portalRender = require('../pipeline/stages/23-portal-render');

// Import portal modules for single-repo refresh
const githubClient = require('../portal/github-client');
const { loadCache, saveCache, hasChanged, updateCacheEntry, loadContentFromCache } = require('../portal/ai-cache');
const { loadProjectCache, updateProjectCacheEntry, deserializeAll } = require('../portal/project-cache');
const diagramGenerator = require('../portal/diagram-generator');
const explanationGenerator = require('../portal/explanation-generator');
const { renderPortal } = require('../portal/renderer');

// State tracking
const PORTAL_STATE_FILE = '/tmp/portal-generation-state.json';

/**
 * Load portal config
 */
async function loadPortalConfig() {
  const configPath = path.join(process.cwd(), 'config', 'portal.config.json');
  const data = await fs.readFile(configPath, 'utf-8');
  return JSON.parse(data);
}

/**
 * Save generation state
 */
async function saveState(state) {
  await fs.writeFile(PORTAL_STATE_FILE, JSON.stringify(state, null, 2), 'utf-8');
}

/**
 * Register portal routes
 * @param {FastifyInstance} fastify
 * @param {Object} options
 */
async function routes(fastify, options) {

  // ─── POST /api/portal/generate ──────────────────────────────────────────────

  fastify.post('/generate', async (request, reply) => {
    const startTime = Date.now();

    try {
      await saveState({ status: 'running', started_at: new Date().toISOString() });

      fastify.log.info('Portal generation triggered');

      // Run all three stages sequentially
      const collectData = await portalCollect.run({});
      const aiContent = await portalAI.run({}, collectData);
      const renderResult = await portalRender.run({}, collectData, aiContent);

      const duration = Date.now() - startTime;

      await saveState({
        status: 'completed',
        started_at: new Date(startTime).toISOString(),
        completed_at: new Date().toISOString(),
        duration_ms: duration,
        pages_rendered: renderResult.pages_rendered,
      });

      return reply.send({
        status: 'success',
        pages_rendered: renderResult.pages_rendered,
        output_dir: renderResult.output_dir,
        duration_ms: duration,
      });

    } catch (error) {
      await saveState({
        status: 'failed',
        error: error.message,
        failed_at: new Date().toISOString(),
      });
      fastify.log.error({ error: error.message }, 'Portal generation failed');
      return reply.code(500).send({ status: 'failed', error: error.message });
    }
  });

  // ─── POST /api/portal/refresh/:repo ─────────────────────────────────────────

  fastify.post('/refresh/:repo', async (request, reply) => {
    const { repo } = request.params;
    const startTime = Date.now();

    try {
      const portalConfig = await loadPortalConfig();
      const repoConfig = (portalConfig.repos || []).find(r => r.name === repo);

      if (!repoConfig) {
        return reply.code(404).send({ error: `Repo '${repo}' not in portal config` });
      }

      const githubToken = process.env.GITHUB_PAT || process.env.GITHUB_TOKEN;
      if (!githubToken) {
        return reply.code(500).send({ error: 'GitHub token not configured' });
      }

      fastify.log.info({ repo }, 'Single-repo portal refresh');

      // Fetch data for this one repo
      const repoData = await githubClient.collectSingleRepo(repo, repoConfig, githubToken);

      // Update project cache
      await updateProjectCacheEntry(
        repo,
        repoData.project,
        repoData.commits,
        repoData.activity,
        repoData.commits_365d
      );

      // Check if AI content needs regeneration
      const cache = await loadCache();
      const contentHash = diagramGenerator.computeContentHash(repoData.project);

      if (hasChanged(cache, repo, contentHash)) {
        const apiKey = process.env.GOOGLE_AI_API_KEY;
        if (apiKey) {
          fastify.log.info({ repo }, 'Content changed, regenerating AI content');

          const diagrams = await diagramGenerator.generateAllDiagrams(repoData.project, repoData.readme || '', apiKey);
          const [archExp, dfExp, seqExp, projExp, journey] = await Promise.all([
            explanationGenerator.generateDiagramExplanation(repoData.project, diagrams.architecture, 'architecture', repoData.readme || '', apiKey),
            explanationGenerator.generateDiagramExplanation(repoData.project, diagrams.data_flow, 'data_flow', repoData.readme || '', apiKey),
            explanationGenerator.generateDiagramExplanation(repoData.project, diagrams.sequence, 'sequence', repoData.readme || '', apiKey),
            explanationGenerator.generateProjectExplanation(repoData.project, repoData.readme || '', apiKey),
            explanationGenerator.generateUserJourney(repoData.project, repoData.readme || '', apiKey),
          ]);

          updateCacheEntry(cache, repo, contentHash, {
            diagram: { mermaid_code: diagrams.architecture, explanation: archExp },
            data_flow_diagram: { mermaid_code: diagrams.data_flow, explanation: dfExp },
            sequence_diagram: { mermaid_code: diagrams.sequence, explanation: seqExp },
            explanation: projExp,
            user_journey: journey,
          });

          await saveCache(cache);
        }
      }

      // Load full project cache + AI cache and re-render
      const projectCache = await loadProjectCache();
      const fullData = deserializeAll(projectCache);
      const aiContent = loadContentFromCache(cache);

      const portalData = {
        projects: fullData.projects,
        developers: [],
        recent_commits: fullData.recentCommits,
        sprints: {},
        heatmap: [],
        activity_feed: fullData.activity.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp)).slice(0, 100),
        generated_at: new Date().toISOString(),
        total_active_projects: fullData.projects.filter(p => p.status === 'active').length,
        total_deployed_projects: fullData.projects.filter(p => p.status === 'deployed').length,
        total_commits_today: 0,
        diagrams: aiContent.diagrams,
        project_explanations: aiContent.project_explanations,
        user_journeys: aiContent.user_journeys,
        all_commits_365d: fullData.allCommits365d,
      };

      const renderResult = await renderPortal(portalData, portalConfig.repos || []);

      return reply.send({
        status: 'success',
        repo,
        pages_rendered: renderResult.pages_rendered,
        duration_ms: Date.now() - startTime,
      });

    } catch (error) {
      fastify.log.error({ error: error.message, repo }, 'Single-repo refresh failed');
      return reply.code(500).send({ status: 'failed', error: error.message });
    }
  });

  // ─── GET /api/portal/status ─────────────────────────────────────────────────

  fastify.get('/status', async (request, reply) => {
    try {
      const stateData = await fs.readFile(PORTAL_STATE_FILE, 'utf-8');
      return reply.send(JSON.parse(stateData));
    } catch {
      return reply.send({ status: 'idle', message: 'No portal generation has run yet' });
    }
  });
}

module.exports = routes;
