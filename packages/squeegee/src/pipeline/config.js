/**
 * Squeegee configuration loader
 *
 * Single source of truth: reads squeegee.config.json.
 * No hardcoded project lists — everything comes from config.
 *
 * @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
 */

const path = require('path');
const { readJsonSafe } = require('./utils');

let _config = null;
let _workspace = null;

/**
 * Load config from squeegee.config.json.
 * Merges with runtime defaults (workspace path, etc.).
 */
async function loadConfig(workspace) {
  if (_config && _workspace === workspace) return _config;

  _workspace = workspace;
  const configPath = path.join(workspace, 'squeegee.config.json');
  const raw = await readJsonSafe(configPath, {});

  _config = {
    workspace,
    version: raw.version || '2.0.0',

    // Project list — single source of truth
    projects: (raw.projects || []).map(p => ({
      name: p.name,
      path: p.path,
      stack: p.stack || [],
    })),

    // File exclusion patterns
    exclude: raw.exclude || [],
    include: raw.include || [],

    // Document type requirements
    docTypes: raw.docTypes || {},

    // GSD config
    gsd: raw.gsd || { enabled: true, planningDir: '.planning', phasesDir: '.planning/phases' },

    // Plans management
    plans: {
      maxRecentPlans: 20,
      archiveAfterDays: 90,
      ...(raw.plans || {}),
    },

    // Quality scoring
    quality: raw.quality || {
      thresholds: { minimum: 0.60, acceptable: 0.75, good: 0.85, excellent: 0.95 },
      weights: { completeness: 0.30, structure: 0.25, freshness: 0.15, consistency: 0.15, crossRefs: 0.15 },
      freshness: { excellent: 7, good: 30, fair: 90, poor: 180 },
    },

    // Trigger tables
    triggerTables: raw.triggerTables || { enabled: false },

    // Pattern library
    patternLibrary: raw.patternLibrary || { enabled: true, outputPath: 'docs-portal/PATTERN_LIBRARY.md', minProjectsForPattern: 2 },

    // Instructions (projects-index markers, etc.)
    instructions: raw.instructions || {},

    // Section markers for auto-update regions
    sectionMarkers: {
      start: (tag) => `<!-- SQUEEGEE:AUTO:START ${tag} -->`,
      end: (tag) => `<!-- SQUEEGEE:AUTO:END ${tag} -->`,
    },

    // Git analysis settings
    gitAnalysis: {
      maxCommits: 500,
      sinceDefault: '6 months ago',
      ...(raw.gitAnalysis || {}),
    },

    // Changelog settings
    changelog: {
      retentionDays: 90,
      ...(raw.changelog || {}),
    },
  };

  return _config;
}

/**
 * Get project paths as simple string array (for backward compat).
 */
function getProjectPaths(config) {
  return config.projects.map(p => p.path);
}

/**
 * Resolve a project path to absolute.
 */
function resolveProjectPath(config, projectRelPath) {
  return path.join(config.workspace, projectRelPath);
}

module.exports = {
  loadConfig,
  getProjectPaths,
  resolveProjectPath,
};
