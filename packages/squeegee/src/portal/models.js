/**
 * Portal Data Models
 *
 * JSDoc type definitions for the portal generation pipeline.
 * Ported from glass-box-hub/squeegee/models.py.
 *
 * @file src/portal/models.js
 * @module portal/models
 */

'use strict';

/** @enum {string} */
const ProjectStatus = {
  ACTIVE: 'active',
  DEPLOYED: 'deployed',
  PLANNING: 'planning',
  MAINTENANCE: 'maintenance',
  DEPRECATED: 'deprecated',
  ARCHIVED: 'archived',
};

/** @enum {string} */
const ProjectCategory = {
  ADJUDICA_PLATFORM: 'adjudica-platform',
  MERUSCASE_INTEGRATION: 'meruscase-integration',
  LEGAL_RESEARCH: 'legal-research',
  PLATFORM_SERVICES: 'platform-services',
  INFRASTRUCTURE: 'infrastructure',
  RESEARCH_OSS: 'research-oss',
  INTERNAL_TOOLS: 'internal-tools',
};

/** @enum {string} */
const ExpertiseLevel = {
  NONE: 'none',
  FAMILIAR: 'familiar',
  PROFICIENT: 'proficient',
  EXPERT: 'expert',
  MASTER: 'master',
};

/**
 * Map commit count to expertise level
 * @param {number} commitCount
 * @returns {string}
 */
function getExpertiseLevel(commitCount) {
  if (commitCount <= 0) return ExpertiseLevel.NONE;
  if (commitCount <= 50) return ExpertiseLevel.FAMILIAR;
  if (commitCount <= 200) return ExpertiseLevel.PROFICIENT;
  if (commitCount <= 500) return ExpertiseLevel.EXPERT;
  return ExpertiseLevel.MASTER;
}

/**
 * @typedef {Object} Project
 * @property {string} name
 * @property {string} repo_path - e.g. "Glass-Box-Solutions-Inc/adjudica-ai-app"
 * @property {string} status - ProjectStatus value
 * @property {string} category - ProjectCategory value
 * @property {string} description
 * @property {string[]} tech_stack
 * @property {string} [team_lead]
 * @property {string[]} contributors
 * @property {string} [production_url]
 * @property {string} [staging_url]
 * @property {string} [docs_url]
 * @property {number} commit_count_30d
 * @property {number} health_score
 * @property {string} [last_commit_date]
 */

/**
 * @typedef {Object} Developer
 * @property {string} name
 * @property {string} [email]
 * @property {string} [github_username]
 * @property {Object<string, number>} expertise_areas - repo_name -> commit_count
 * @property {number} total_commits
 * @property {string[]} active_projects
 * @property {Object<string, number>} contribution_counts - repo_name -> count
 */

/**
 * @typedef {Object} Commit
 * @property {string} sha
 * @property {string} message
 * @property {string} author
 * @property {string} [author_email]
 * @property {string} timestamp - ISO 8601
 * @property {string} repo_name
 * @property {string} [url]
 */

/**
 * @typedef {Object} Sprint
 * @property {string} id
 * @property {string} name
 * @property {string} [start_date]
 * @property {string} [end_date]
 * @property {number} velocity
 * @property {number} progress - 0-100
 * @property {Array} [burndown_data]
 */

/**
 * @typedef {Object} HeatmapCell
 * @property {string} developer_name
 * @property {string} project_name
 * @property {number} commit_count
 * @property {string} expertise_level
 * @property {number} recent_commits - last 30d
 */

/**
 * @typedef {Object} ActivityEvent
 * @property {string} event_type - "commit" | "pr" | "issue" | "deploy"
 * @property {string} title
 * @property {string} [description]
 * @property {string} author
 * @property {string} timestamp
 * @property {string} repo_name
 * @property {string} [url]
 */

/**
 * @typedef {Object} DualExplanation
 * @property {string} technical
 * @property {string} non_technical
 */

/**
 * @typedef {Object} DiagramEntry
 * @property {string} mermaid_code
 * @property {DualExplanation} explanation
 */

/**
 * @typedef {Object} ProjectDiagram
 * @property {string} project_name
 * @property {string} mermaid_code - Architecture diagram
 * @property {DualExplanation} explanation
 * @property {DiagramEntry} [data_flow]
 * @property {DiagramEntry} [sequence]
 */

/**
 * @typedef {Object} PortalData
 * @property {Project[]} projects
 * @property {Developer[]} developers
 * @property {Object<string, Commit[]>} recent_commits - repo_name -> commits (30d)
 * @property {Object<string, Sprint>} sprints - team_name -> sprint
 * @property {HeatmapCell[]} heatmap
 * @property {ActivityEvent[]} activity_feed
 * @property {string} generated_at - ISO 8601
 * @property {number} total_active_projects
 * @property {number} total_deployed_projects
 * @property {number} total_commits_today
 * @property {Object<string, ProjectDiagram>} diagrams - project_name -> diagram
 * @property {Object<string, DualExplanation>} project_explanations
 * @property {Object<string, string>} user_journeys - project_name -> HTML
 * @property {Commit[]} all_commits_365d
 */

/**
 * Compute color intensity for heatmap cells (0-4 scale)
 * @param {number} commitCount
 * @returns {number}
 */
function getColorIntensity(commitCount) {
  if (commitCount <= 0) return 0;
  if (commitCount <= 5) return 1;
  if (commitCount <= 15) return 2;
  if (commitCount <= 50) return 3;
  return 4;
}

/** Status string -> enum mapping */
const STATUS_MAP = {
  active: ProjectStatus.ACTIVE,
  deployed: ProjectStatus.DEPLOYED,
  planning: ProjectStatus.PLANNING,
  maintenance: ProjectStatus.MAINTENANCE,
  deprecated: ProjectStatus.DEPRECATED,
  archived: ProjectStatus.ARCHIVED,
};

/** Category string -> enum mapping */
const CATEGORY_MAP = {
  'adjudica-platform': ProjectCategory.ADJUDICA_PLATFORM,
  'meruscase-integration': ProjectCategory.MERUSCASE_INTEGRATION,
  'legal-research': ProjectCategory.LEGAL_RESEARCH,
  'platform-services': ProjectCategory.PLATFORM_SERVICES,
  infrastructure: ProjectCategory.INFRASTRUCTURE,
  'research-oss': ProjectCategory.RESEARCH_OSS,
  'internal-tools': ProjectCategory.INTERNAL_TOOLS,
};

module.exports = {
  ProjectStatus,
  ProjectCategory,
  ExpertiseLevel,
  getExpertiseLevel,
  getColorIntensity,
  STATUS_MAP,
  CATEGORY_MAP,
};
