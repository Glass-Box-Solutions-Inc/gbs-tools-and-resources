/**
 * Portal AI Cache
 *
 * Two-tier content-hash cache for AI-generated content (diagrams, explanations,
 * user journeys). Skips regeneration for unchanged projects.
 * Ported from glass-box-hub/squeegee/generator.py cache logic.
 *
 * @file src/portal/ai-cache.js
 * @module portal/ai-cache
 */

'use strict';

const fs = require('fs').promises;
const path = require('path');

const CACHE_FILE = path.join(process.cwd(), 'config', 'portal-ai-cache.json');

/**
 * @typedef {Object} CachedProject
 * @property {string} content_hash
 * @property {Object} diagram - { mermaid_code, explanation: { technical, non_technical } }
 * @property {Object} data_flow_diagram - { mermaid_code, explanation }
 * @property {Object} sequence_diagram - { mermaid_code, explanation }
 * @property {Object} explanation - { technical, non_technical }
 * @property {string} user_journey - HTML string
 */

/**
 * @typedef {Object} AICache
 * @property {number} version
 * @property {string} generated_at
 * @property {Object<string, CachedProject>} projects
 */

/**
 * Load the AI cache from disk
 * @returns {Promise<AICache>}
 */
async function loadCache() {
  try {
    const data = await fs.readFile(CACHE_FILE, 'utf-8');
    return JSON.parse(data);
  } catch {
    return { version: 1, generated_at: null, projects: {} };
  }
}

/**
 * Save the AI cache to disk
 * @param {AICache} cache
 * @returns {Promise<void>}
 */
async function saveCache(cache) {
  cache.generated_at = new Date().toISOString();
  const dir = path.dirname(CACHE_FILE);
  await fs.mkdir(dir, { recursive: true });
  await fs.writeFile(CACHE_FILE, JSON.stringify(cache, null, 2), 'utf-8');
}

/**
 * Get cached content for a project
 * @param {AICache} cache
 * @param {string} projectName
 * @returns {CachedProject|null}
 */
function getCachedProject(cache, projectName) {
  return cache.projects?.[projectName] || null;
}

/**
 * Check if a project's content has changed (needs regeneration)
 * @param {AICache} cache
 * @param {string} projectName
 * @param {string} contentHash
 * @returns {boolean} - true if content is different from cached
 */
function hasChanged(cache, projectName, contentHash) {
  const cached = cache.projects?.[projectName];
  if (!cached) return true;
  return cached.content_hash !== contentHash;
}

/**
 * Update cache entry for a project
 * @param {AICache} cache
 * @param {string} projectName
 * @param {string} contentHash
 * @param {Object} data - { diagram, data_flow_diagram, sequence_diagram, explanation, user_journey }
 */
function updateCacheEntry(cache, projectName, contentHash, data) {
  cache.projects[projectName] = {
    content_hash: contentHash,
    diagram: data.diagram || null,
    data_flow_diagram: data.data_flow_diagram || null,
    sequence_diagram: data.sequence_diagram || null,
    explanation: data.explanation || null,
    user_journey: data.user_journey || null,
  };
}

/**
 * Load diagrams, explanations, and user journeys from cache into portal data format
 * @param {AICache} cache
 * @returns {Object} - { diagrams, project_explanations, user_journeys }
 */
function loadContentFromCache(cache) {
  const diagrams = {};
  const projectExplanations = {};
  const userJourneys = {};

  for (const [name, entry] of Object.entries(cache.projects || {})) {
    // Build diagram entry
    if (entry.diagram) {
      diagrams[name] = {
        project_name: name,
        mermaid_code: entry.diagram.mermaid_code || '',
        explanation: entry.diagram.explanation || { technical: '', non_technical: '' },
        data_flow: entry.data_flow_diagram
          ? {
              mermaid_code: entry.data_flow_diagram.mermaid_code || '',
              explanation: entry.data_flow_diagram.explanation || { technical: '', non_technical: '' },
            }
          : null,
        sequence: entry.sequence_diagram
          ? {
              mermaid_code: entry.sequence_diagram.mermaid_code || '',
              explanation: entry.sequence_diagram.explanation || { technical: '', non_technical: '' },
            }
          : null,
      };
    }

    if (entry.explanation) {
      projectExplanations[name] = entry.explanation;
    }

    if (entry.user_journey) {
      userJourneys[name] = entry.user_journey;
    }
  }

  return { diagrams, project_explanations: projectExplanations, user_journeys: userJourneys };
}

module.exports = {
  CACHE_FILE,
  loadCache,
  saveCache,
  getCachedProject,
  hasChanged,
  updateCacheEntry,
  loadContentFromCache,
};
