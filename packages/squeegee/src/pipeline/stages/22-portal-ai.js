/**
 * Stage 22: Portal AI Content
 *
 * Generates Mermaid diagrams and explanations via Gemini 3.1.
 * Skips unchanged projects using content-hash cache.
 *
 * @file src/pipeline/stages/22-portal-ai.js
 * @module pipeline/stages/22-portal-ai
 */

'use strict';

const fs = require('fs').promises;
const path = require('path');
const { log } = require('../utils');
const diagramGenerator = require('../../portal/diagram-generator');
const explanationGenerator = require('../../portal/explanation-generator');
const aiCache = require('../../portal/ai-cache');
const { fetchReadme, createOctokit } = require('../../portal/github-client');

/**
 * Resolve Gemini API key from environment
 * @returns {string}
 */
function getGeminiApiKey() {
  const key = process.env.GOOGLE_AI_API_KEY;
  if (!key) throw new Error('Gemini API key not configured (GOOGLE_AI_API_KEY)');
  if (key.startsWith('/') && key.length < 200) {
    try {
      return require('fs').readFileSync(key, 'utf-8').trim();
    } catch {
      return key;
    }
  }
  return key;
}

/**
 * Run Stage 22: Generate AI content for portal
 * @param {Object} config - Pipeline config
 * @param {Object} collectData - Data from stage 21
 * @returns {Promise<Object>} - AI content (diagrams, explanations, user_journeys)
 */
async function run(config, collectData) {
  log('Stage 22: Portal AI content generation', 'info');

  const apiKey = getGeminiApiKey();
  const cache = await aiCache.loadCache();
  const projects = collectData?.projects || [];
  const githubToken = process.env.GITHUB_PAT || process.env.GITHUB_TOKEN || '';

  let generated = 0;
  let skipped = 0;
  let failed = 0;

  for (const project of projects) {
    const contentHash = diagramGenerator.computeContentHash(project);

    // Skip if content hasn't changed
    if (!aiCache.hasChanged(cache, project.name, contentHash)) {
      skipped++;
      continue;
    }

    log(`Generating AI content for ${project.name}`, 'info');

    try {
      // Fetch README for context
      let readme = '';
      if (githubToken) {
        const octokit = createOctokit(githubToken);
        readme = await fetchReadme(octokit, project.name);
      }

      // Generate all three diagram types in parallel
      const diagrams = await diagramGenerator.generateAllDiagrams(project, readme, apiKey);

      // Generate explanations in parallel
      const [archExplanation, dfExplanation, seqExplanation, projectExplanation, userJourney] =
        await Promise.all([
          explanationGenerator.generateDiagramExplanation(project, diagrams.architecture, 'architecture', readme, apiKey),
          explanationGenerator.generateDiagramExplanation(project, diagrams.data_flow, 'data_flow', readme, apiKey),
          explanationGenerator.generateDiagramExplanation(project, diagrams.sequence, 'sequence', readme, apiKey),
          explanationGenerator.generateProjectExplanation(project, readme, apiKey),
          explanationGenerator.generateUserJourney(project, readme, apiKey),
        ]);

      // Update cache
      aiCache.updateCacheEntry(cache, project.name, contentHash, {
        diagram: { mermaid_code: diagrams.architecture, explanation: archExplanation },
        data_flow_diagram: { mermaid_code: diagrams.data_flow, explanation: dfExplanation },
        sequence_diagram: { mermaid_code: diagrams.sequence, explanation: seqExplanation },
        explanation: projectExplanation,
        user_journey: userJourney,
      });

      generated++;
    } catch (err) {
      log(`Failed to generate AI content for ${project.name}: ${err.message}`, 'error');
      failed++;
    }
  }

  // Save cache
  await aiCache.saveCache(cache);

  // Load all content from cache into portal format
  const content = aiCache.loadContentFromCache(cache);

  log(`AI content: ${generated} generated, ${skipped} cached, ${failed} failed`, 'success');

  return content;
}

module.exports = { run };
