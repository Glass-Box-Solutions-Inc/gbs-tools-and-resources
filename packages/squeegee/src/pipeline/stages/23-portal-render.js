/**
 * Stage 23: Portal Render
 *
 * Renders HTML via Nunjucks, generates CSV exports, and uploads
 * to GCS bucket.
 *
 * @file src/pipeline/stages/23-portal-render.js
 * @module pipeline/stages/23-portal-render
 */

'use strict';

const fs = require('fs').promises;
const path = require('path');
const { log } = require('../utils');
const { renderPortal } = require('../../portal/renderer');
const { uploadToGCS } = require('../../portal/gcs-uploader');

const DEFAULT_OUTPUT_DIR = '/tmp/portal-output';

/**
 * Generate CSV exports from portal data
 * @param {Object} portalData
 * @param {string} outputDir
 */
async function generateExports(portalData, outputDir) {
  const exportsDir = path.join(outputDir, 'exports');
  await fs.mkdir(exportsDir, { recursive: true });

  // Heatmap CSV
  const heatmapRows = [['Developer', 'Project', 'Commit Count', 'Recent Commits (30d)', 'Expertise Level']];
  for (const cell of portalData.heatmap || []) {
    heatmapRows.push([
      cell.developer_name,
      cell.project_name,
      cell.commit_count,
      cell.recent_commits,
      cell.expertise_level,
    ]);
  }
  await writeCSV(path.join(exportsDir, 'heatmap.csv'), heatmapRows);

  // Projects CSV
  const projectRows = [['Project', 'Status', 'Category', 'Health Score', 'Commits (30d)', 'Contributors', 'Tech Stack', 'URL', 'Last Commit']];
  for (const p of portalData.projects || []) {
    projectRows.push([
      p.name,
      p.status,
      p.category,
      p.health_score,
      p.commit_count_30d,
      (p.contributors || []).length,
      (p.tech_stack || []).join('; '),
      p.production_url || '',
      p.last_commit_date || '',
    ]);
  }
  await writeCSV(path.join(exportsDir, 'projects.csv'), projectRows);

  // Developers CSV
  const devRows = [['Developer', 'Total Commits', 'Active Projects', 'Project List']];
  for (const d of portalData.developers || []) {
    devRows.push([
      d.name,
      d.total_commits,
      d.active_projects.length,
      d.active_projects.join('; '),
    ]);
  }
  await writeCSV(path.join(exportsDir, 'developers.csv'), devRows);

  log(`Generated 3 CSV exports to ${exportsDir}`, 'info');
}

/**
 * Write a CSV file
 * @param {string} filePath
 * @param {Array<Array>} rows
 */
async function writeCSV(filePath, rows) {
  const content = rows
    .map((row) =>
      row.map((cell) => {
        const str = String(cell ?? '');
        return str.includes(',') || str.includes('"') || str.includes('\n')
          ? `"${str.replace(/"/g, '""')}"`
          : str;
      }).join(',')
    )
    .join('\n');
  await fs.writeFile(filePath, content, 'utf-8');
}

/**
 * Run Stage 23: Render portal HTML and upload to GCS
 * @param {Object} config - Pipeline config
 * @param {Object} collectData - Data from stage 21
 * @param {Object} aiContent - Data from stage 22 (diagrams, explanations, user_journeys)
 * @returns {Promise<Object>} - Render results
 */
async function run(config, collectData, aiContent) {
  log('Stage 23: Portal render and upload', 'info');

  const portalConfig = collectData?.portal_config || {};
  const repoConfigs = collectData?.repo_configs || [];
  const outputDir = portalConfig.output_dir || DEFAULT_OUTPUT_DIR;

  // Build complete portal data
  const portalData = {
    projects: collectData?.projects || [],
    developers: collectData?.developers || [],
    recent_commits: collectData?.recent_commits || {},
    sprints: collectData?.sprints || {},
    heatmap: collectData?.heatmap || [],
    activity_feed: collectData?.activity_feed || [],
    generated_at: new Date().toISOString(),
    total_active_projects: (collectData?.projects || []).filter((p) => p.status === 'active').length,
    total_deployed_projects: (collectData?.projects || []).filter((p) => p.status === 'deployed').length,
    total_commits_today: 0,
    diagrams: aiContent?.diagrams || {},
    project_explanations: aiContent?.project_explanations || {},
    user_journeys: aiContent?.user_journeys || {},
    all_commits_365d: collectData?.all_commits_365d || [],
  };

  // Render HTML
  const renderResult = await renderPortal(portalData, repoConfigs, outputDir);

  // Generate CSV exports
  await generateExports(portalData, outputDir);

  // Upload to GCS if configured
  let uploadResult = null;
  const gcsBucket = portalConfig.gcs?.bucket;
  const gcsPrefix = portalConfig.gcs?.prefix || '';
  const dryRun = portalConfig.gcs?.dry_run !== false && !process.env.PORTAL_GCS_UPLOAD;

  if (gcsBucket) {
    uploadResult = await uploadToGCS(outputDir, gcsBucket, gcsPrefix, { dryRun });
  } else {
    log('No GCS bucket configured, skipping upload', 'info');
  }

  log(`Portal rendered: ${renderResult.pages_rendered} pages to ${outputDir}`, 'success');

  return {
    pages_rendered: renderResult.pages_rendered,
    output_dir: outputDir,
    upload: uploadResult,
  };
}

module.exports = { run };
