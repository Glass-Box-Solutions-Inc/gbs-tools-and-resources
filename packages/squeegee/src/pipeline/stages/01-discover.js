/**
 * Stage 01: Project Discovery
 *
 * Scans the workspace for projects and their documentation files.
 * Replaces DocumentScanner from the monolith.
 *
 * @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
 */

const path = require('path');
const { log, fileExists, findFiles, readFileSafe } = require('../utils');
const { getProjectPaths, resolveProjectPath } = require('../config');
const { analyzeMarkdown } = require('../analyzers/markdown-analyzer');

async function run(config) {
  log('Stage 1: Discovering projects and documentation...', 'info');

  const results = {
    projects: [],
    markdown: [],
  };

  for (const project of config.projects) {
    const projectPath = resolveProjectPath(config, project.path);

    if (!(await fileExists(projectPath))) {
      continue;
    }

    const projectInfo = {
      name: project.name,
      path: project.path,
      absolutePath: projectPath,
      hasClaude: await fileExists(path.join(projectPath, 'CLAUDE.md')),
      hasState: await fileExists(path.join(projectPath, '.planning', 'STATE.md')),
      hasPlans: await fileExists(path.join(projectPath, 'PLANS_APPROVED.md')),
      hasPractices: await fileExists(path.join(projectPath, 'PROGRAMMING_PRACTICES.md')),
      hasReadme: await fileExists(path.join(projectPath, 'README.md')),
      hasChangelog: await fileExists(path.join(projectPath, 'CHANGELOG.md')),
    };

    results.projects.push(projectInfo);

    // Scan markdown files
    const mdFiles = await findFiles(projectPath, '.md');
    for (const file of mdFiles) {
      const analysis = await analyzeMarkdown(file, config.workspace);
      if (analysis) {
        results.markdown.push(analysis);
      }
    }

  }

  log(`Discovered ${results.projects.length} projects, ${results.markdown.length} docs`, 'success');

  return results;
}

module.exports = { run };
