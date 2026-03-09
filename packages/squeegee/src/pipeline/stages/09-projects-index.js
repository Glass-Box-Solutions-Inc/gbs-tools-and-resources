/**
 * Stage 09: Projects Index Auto-Update
 *
 * Updates the projects-index.md file between SQUEEGEE:AUTO-UPDATE markers.
 * Config has the markers and paths; this stage implements the actual update.
 *
 * @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
 */

const fs = require('fs').promises;
const path = require('path');
const { log, fileExists } = require('../utils');
const { resolveProjectPath } = require('../config');

async function run(config, discovery) {
  log('Stage 9: Updating projects index...', 'info');

  const indexConfig = config.instructions?.projectsIndex;
  if (!indexConfig) {
    log('No projects index config found, skipping', 'warn');
    return { updated: false };
  }

  const indexPath = path.join(config.workspace, indexConfig.path);
  if (!(await fileExists(indexPath))) {
    log(`Projects index file not found at ${indexConfig.path}`, 'warn');
    return { updated: false };
  }

  const content = await fs.readFile(indexPath, 'utf-8');

  const startMarker = indexConfig.markers?.start || '<!-- SQUEEGEE:AUTO-UPDATE:START -->';
  const endMarker = indexConfig.markers?.end || '<!-- SQUEEGEE:AUTO-UPDATE:END -->';

  const startIdx = content.indexOf(startMarker);
  const endIdx = content.indexOf(endMarker);

  if (startIdx === -1 || endIdx === -1) {
    log('Projects index markers not found', 'warn');
    return { updated: false };
  }

  // Generate new content between markers
  const newSection = await generateProjectTables(config, discovery);

  const before = content.slice(0, startIdx + startMarker.length);
  const after = content.slice(endIdx);
  const newContent = before + '\n\n' + newSection + '\n\n' + after;

  if (newContent === content) {
    log('Projects index already up to date', 'info');
    return { updated: false };
  }

  await fs.writeFile(indexPath, newContent, 'utf-8');
  log('Updated projects index', 'success');
  return { updated: true };
}

async function generateProjectTables(config, discovery) {
  const lines = [];

  // Active projects (in Sandbox)
  const activeProjects = [];
  const externalProjects = [];

  for (const project of config.projects) {
    const projectPath = resolveProjectPath(config, project.path);
    const isExternal = isExternalRepo(project);

    if (isExternal) {
      externalProjects.push(project);
    } else if (await fileExists(projectPath)) {
      activeProjects.push(project);
    }
  }

  // Active projects table
  lines.push('## Active Projects (in Sandbox)');
  lines.push('');
  lines.push('| Project | Path | CLAUDE.md |');
  lines.push('|---------|------|-----------|');

  for (const project of activeProjects) {
    const claudeRelPath = project.path + '/CLAUDE.md'; // Use forward slashes for markdown
    const hasClaudeMd = await fileExists(path.join(config.workspace, project.path, 'CLAUDE.md'));
    const claudeLink = hasClaudeMd ? `[CLAUDE.md](${claudeRelPath})` : '*Missing*';
    const displayName = formatProjectName(project.name);
    lines.push(`| ${displayName} | \`${project.path}/\` | ${claudeLink} |`);
  }

  // External repos section (if any discovered)
  if (externalProjects.length > 0) {
    lines.push('');
    lines.push('## External Repositories');
    lines.push('');
    lines.push('| Project | Path | Notes |');
    lines.push('|---------|------|-------|');

    for (const project of externalProjects) {
      const displayName = formatProjectName(project.name);
      lines.push(`| ${displayName} | \`${project.path}/\` | External repo pointer |`);
    }
  }

  // Internal tools
  lines.push('');
  lines.push('## Internal Tools');
  lines.push('');
  lines.push('| Tool | Path | Reference |');
  lines.push('|------|------|-----------|');
  lines.push('| Squeegee | `scripts/squeegee/` | [squeegee.config.json](squeegee.config.json) |');
  lines.push('| Docs Portal | `docs-portal/` | [PATTERN_LIBRARY.md](docs-portal/PATTERN_LIBRARY.md) |');

  return lines.join('\n');
}

function isExternalRepo(project) {
  // External repos are monorepo pointers — paths starting with projects/ that
  // reference repos living outside the monorepo. Standalone repos (Desktop-level)
  // never match this pattern since their paths are bare directory names.
  const externalPaths = [
    'projects/spectacles',
    'projects/attorney-dashboard',
    'projects/wc-knowledge-base',
    'projects/pd-calculator',
    'projects/adjudica-documentation',
    'projects/adjudica-production',
    'projects/wc-paralegal-backend',
    'projects/wc-paralegal-nestjs',
  ];
  return externalPaths.some(ep => project.path.startsWith(ep));
}

function formatProjectName(name) {
  return name
    .split('-')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

module.exports = { run };
