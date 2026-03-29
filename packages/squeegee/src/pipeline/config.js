/**
 * Squeegee configuration loader
 *
 * Single source of truth: reads squeegee.config.json.
 * No hardcoded project lists — everything comes from config.
 *
 * docsRepo mode: When enabled, all documentation output is redirected
 * to adjudica-documentation/projects/{repo}/ instead of back to source repos.
 *
 * @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
 */

const path = require('path');
const { readJsonSafe } = require('./utils');

let _config = null;
let _workspace = null;

/** Default docsRepo configuration */
const DOCS_REPO_DEFAULTS = {
  enabled: false,
  repoName: 'adjudica-documentation',
  cloneUrl: 'https://github.com/Glass-Box-Solutions-Inc/adjudica-documentation.git',
  outputPath: null, // Set at runtime after cloning
  commitMessage: 'chore(squeegee): sync project documentation',
  autoPush: true,
};

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

    // Docs repo mode — write to adjudica-documentation instead of source repos
    docsRepo: {
      ...DOCS_REPO_DEFAULTS,
      ...(raw.docsRepo || {}),
    },

    // Current project name (set by org-discovery for each repo)
    currentProject: null,
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
 *
 * When docsRepo mode is enabled, redirects output to:
 *   adjudica-documentation/projects/{projectName}/
 *
 * This allows Squeegee to read from source repos but write to docs repo only.
 */
function resolveProjectPath(config, projectRelPath) {
  // docsRepo mode: redirect output to docs repo
  if (config.docsRepo && config.docsRepo.enabled && config.docsRepo.outputPath) {
    const projectName = config.currentProject || path.basename(projectRelPath) || 'unknown';
    return path.join(config.docsRepo.outputPath, 'projects', projectName);
  }

  // Default: write to source repo (original behavior)
  return path.join(config.workspace, projectRelPath);
}

/**
 * Set the current project name for docsRepo path resolution.
 * Called by org-discovery before running pipeline on each repo.
 */
function setCurrentProject(config, projectName) {
  config.currentProject = projectName;
}

/**
 * Set the docsRepo output path at runtime (after cloning docs repo).
 */
function setDocsRepoOutputPath(config, outputPath) {
  if (config.docsRepo) {
    config.docsRepo.outputPath = outputPath;
  }
}

/**
 * Resolve the SOURCE path for a project (always the workspace clone).
 * Use this for reading code, running git commands, detecting stack, etc.
 * Use resolveProjectPath() for writing output files.
 */
function resolveSourcePath(config, projectRelPath) {
  return path.join(config.workspace, projectRelPath);
}

module.exports = {
  loadConfig,
  getProjectPaths,
  resolveProjectPath,
  resolveSourcePath,
  setCurrentProject,
  setDocsRepoOutputPath,
};
