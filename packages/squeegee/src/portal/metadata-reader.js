/**
 * Portal Metadata Reader
 *
 * Reads .glassbox-meta.yaml from repos via GitHub API and enriches
 * project data with display names, descriptions, URLs, and team info.
 * Ported from glass-box-hub/squeegee/metadata_reader.py.
 *
 * @file src/portal/metadata-reader.js
 * @module portal/metadata-reader
 */

'use strict';

const yaml = require('js-yaml');
const { fetchFileContent } = require('./github-client');

/**
 * Read .glassbox-meta.yaml from a repo
 * @param {Octokit} octokit - Configured Octokit
 * @param {string} repoName
 * @param {string} [subPath] - Optional sub-directory path
 * @returns {Promise<Object|null>}
 */
async function readMetadata(octokit, repoName, subPath) {
  // Try sub-path first, then root
  const paths = [];
  if (subPath) paths.push(`${subPath}/.glassbox-meta.yaml`);
  paths.push('.glassbox-meta.yaml');

  for (const filePath of paths) {
    const content = await fetchFileContent(octokit, repoName, filePath);
    if (content) {
      try {
        return yaml.load(content);
      } catch (err) {
        console.warn(`Portal: Failed to parse ${repoName}/${filePath}: ${err.message}`);
      }
    }
  }

  return null;
}

/**
 * Read metadata for all configured repos
 * @param {Octokit} octokit
 * @param {Array<Object>} repoConfigs
 * @returns {Promise<Object<string, Object>>} - repoName -> metadata
 */
async function readAllMetadata(octokit, repoConfigs) {
  const metadata = {};

  for (const config of repoConfigs) {
    const meta = await readMetadata(octokit, config.name, config.sub_path);
    if (meta) {
      metadata[config.name] = meta;
    }
  }

  return metadata;
}

/**
 * Enrich a project with metadata fields
 * @param {Project} project
 * @param {Object} metadata - Parsed .glassbox-meta.yaml
 * @returns {Project} - Enriched project (mutated)
 */
function enrichProject(project, metadata) {
  if (!metadata) return project;

  if (metadata.display_name) project.display_name = metadata.display_name;
  if (metadata.description?.short) project.description = metadata.description.short;
  if (metadata.description?.long) project.long_description = metadata.description.long;
  if (metadata.status) project.status = metadata.status;
  if (metadata.priority) project.priority = metadata.priority;

  if (metadata.tech_detail) {
    project.tech_stack = Array.isArray(metadata.tech_detail)
      ? metadata.tech_detail
      : project.tech_stack;
  }

  if (metadata.urls) {
    if (metadata.urls.production) project.production_url = metadata.urls.production;
    if (metadata.urls.staging) project.staging_url = metadata.urls.staging;
    if (metadata.urls.docs) project.docs_url = metadata.urls.docs;
  }

  if (metadata.team) {
    if (metadata.team.lead) project.team_lead = metadata.team.lead;
  }

  if (metadata.dependencies) project.dependencies = metadata.dependencies;
  if (metadata.dependents) project.dependents = metadata.dependents;

  return project;
}

module.exports = {
  readMetadata,
  readAllMetadata,
  enrichProject,
};
