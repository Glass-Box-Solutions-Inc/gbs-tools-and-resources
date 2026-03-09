#!/usr/bin/env node
/**
 * Squeegee Pre-commit Hook
 *
 * Runs before git commit to validate and auto-fix documentation.
 * - Validates root CLAUDE.md structure
 * - Syncs Projects Index with filesystem
 * - Fixes broken cross-references
 * - Reports warnings and suggestions
 *
 * Configuration: squeegee.config.json → preCommitHook section
 *
 * @author GlassBox Solutions
 * @version 1.0.0
 */

const { execSync } = require('child_process');
const fs = require('fs').promises;
const path = require('path');

// Colors for console output
const colors = {
  reset: '\x1b[0m',
  green: '\x1b[32m',
  yellow: '\x1b[33m',
  blue: '\x1b[36m',
  red: '\x1b[31m',
  bold: '\x1b[1m'
};

/**
 * Check if a file matches any of the given glob patterns
 * Simple implementation for common patterns
 */
function matchesPattern(file, patterns) {
  for (const pattern of patterns) {
    // Convert glob to regex
    if (pattern === '**/*.md') {
      if (file.endsWith('.md')) return true;
    } else if (pattern === '**/CLAUDE.md') {
      if (file.endsWith('CLAUDE.md')) return true;
    } else if (pattern.includes('*')) {
      // Simple wildcard matching
      const regex = new RegExp('^' + pattern.replace(/\*\*/g, '.*').replace(/\*/g, '[^/]*') + '$');
      if (regex.test(file)) return true;
    } else {
      if (file === pattern || file.endsWith('/' + pattern)) return true;
    }
  }
  return false;
}

async function loadConfig() {
  try {
    const configPath = path.join(process.cwd(), 'squeegee.config.json');
    const content = await fs.readFile(configPath, 'utf-8');
    return JSON.parse(content);
  } catch {
    return { preCommitHook: { enabled: false } };
  }
}

async function getStagedFiles() {
  try {
    const output = execSync('git diff --cached --name-only', { encoding: 'utf-8' });
    return output.split('\n').filter(Boolean);
  } catch {
    return [];
  }
}

async function main() {
  const config = await loadConfig();
  const hookConfig = config.preCommitHook;

  // Check if hook is enabled
  if (!hookConfig?.enabled) {
    process.exit(0);
  }

  // Get staged files
  const stagedFiles = await getStagedFiles();

  if (stagedFiles.length === 0) {
    process.exit(0);
  }

  // Check trigger condition
  if (hookConfig.triggerOn === 'docs-only') {
    const docPatterns = hookConfig.docPatterns || ['**/*.md'];
    const hasDocChanges = stagedFiles.some(file => matchesPattern(file, docPatterns));

    if (!hasDocChanges) {
      console.log(`${colors.blue}📋 No doc changes, skipping Squeegee pre-commit${colors.reset}`);
      process.exit(0);
    }
  }

  console.log(`\n${colors.bold}🧽 Running Squeegee pre-commit validation...${colors.reset}\n`);

  // Dynamically import the RootClaudeMdCurator from squeegee-manager
  // We need to extract it since it's not exported
  const workspace = process.cwd();

  // Run root CLAUDE.md curation directly using the same logic
  const results = await runRootCuration(workspace, config);

  let hasOutput = false;

  // Report changes
  if (results.changes.length > 0) {
    hasOutput = true;
    console.log(`${colors.green}✅ Auto-fixed:${colors.reset}`);
    results.changes.forEach(c => console.log(`   - ${c}`));

    // Re-stage fixed files
    if (hookConfig.autoFix) {
      try {
        execSync('git add CLAUDE.md', { stdio: 'pipe' });
      } catch {
        // File might not be staged, that's ok
      }
    }
  }

  if (results.warnings.length > 0) {
    hasOutput = true;
    console.log(`\n${colors.yellow}⚠️  Warnings:${colors.reset}`);
    results.warnings.forEach(w => console.log(`   - ${w}`));
  }

  if (results.suggestions.length > 0) {
    hasOutput = true;
    console.log(`\n${colors.blue}💡 Suggestions:${colors.reset}`);
    results.suggestions.forEach(s => console.log(`   - ${s}`));
  }

  if (!hasOutput) {
    console.log(`${colors.green}✅ Documentation is up to date!${colors.reset}`);
  }

  console.log(`\n${colors.green}✨ Squeegee pre-commit complete${colors.reset}\n`);
  process.exit(0);
}

/**
 * Run root CLAUDE.md curation
 * Simplified version for pre-commit hook
 */
async function runRootCuration(workspace, config) {
  const results = {
    changes: [],
    warnings: [],
    suggestions: []
  };

  const rootClaudePath = path.join(workspace, 'CLAUDE.md');

  try {
    let content = await fs.readFile(rootClaudePath, 'utf-8');
    const originalContent = content;

    // 1. Discover and sync projects
    if (config.rootClaudeMd?.autoSync?.projectsIndex) {
      const discovered = await discoverProjects(workspace);
      const syncResult = await syncProjectsIndex(content, discovered);
      content = syncResult.content;
      results.changes.push(...syncResult.changes);
      results.warnings.push(...syncResult.warnings);
    }

    // 2. Validate cross-references
    if (config.rootClaudeMd?.autoSync?.crossReferences) {
      const refResult = await validateCrossReferences(content, workspace);
      content = refResult.content;
      results.changes.push(...refResult.changes);
      results.warnings.push(...refResult.warnings);
    }

    // 3. Validate required sections
    const requiredSections = config.rootClaudeMd?.requiredSections || [];
    for (const section of requiredSections) {
      const sectionRegex = new RegExp(`##.*${section}`, 'i');
      if (!sectionRegex.test(content)) {
        results.warnings.push(`Missing required section: "${section}"`);
      }
    }

    // 4. Detect missing docs in projects
    const projects = config.projects || [];
    for (const project of projects) {
      const projectPath = path.join(workspace, project.path || project);
      try {
        await fs.access(projectPath);
        const claudePath = path.join(projectPath, 'CLAUDE.md');
        try {
          await fs.access(claudePath);
        } catch {
          results.warnings.push(`Project "${project.name || project}" missing CLAUDE.md`);
        }
      } catch {
        // Project doesn't exist, skip
      }
    }

    // 5. Save if changed
    if (content !== originalContent) {
      await fs.writeFile(rootClaudePath, content, 'utf-8');
    }

  } catch (err) {
    results.warnings.push(`Error processing root CLAUDE.md: ${err.message}`);
  }

  return results;
}

async function discoverProjects(workspace) {
  const discovered = { active: [], glassy: [] };

  // Scan projects/ directory
  try {
    const projectsDir = path.join(workspace, 'projects');
    const entries = await fs.readdir(projectsDir, { withFileTypes: true });

    for (const entry of entries) {
      if (entry.isDirectory()) {
        const claudePath = path.join(projectsDir, entry.name, 'CLAUDE.md');
        try {
          await fs.access(claudePath);
          discovered.active.push({
            name: entry.name.split('-').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' '),
            path: `projects/${entry.name}/`,
            claudePath: `projects/${entry.name}/CLAUDE.md`
          });
        } catch {}
      }
    }
  } catch {}

  // Scan glassy-* directories
  try {
    const entries = await fs.readdir(workspace, { withFileTypes: true });

    for (const entry of entries) {
      if (entry.isDirectory() && entry.name.startsWith('glassy-')) {
        const claudePath = path.join(workspace, entry.name, 'CLAUDE.md');
        try {
          await fs.access(claudePath);
          const displayName = entry.name.split('-').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
          discovered.glassy.push({
            name: displayName,
            path: `${entry.name}/`,
            claudePath: `${entry.name}/CLAUDE.md`
          });
        } catch {}
      }
    }
  } catch {}

  return discovered;
}

function parseProjectsTable(content, sectionHeader) {
  const projects = [];

  // Find the section - stop at next ### or horizontal rule followed by blank line
  const sectionRegex = new RegExp(`### ${sectionHeader}[\\s\\S]*?(?=\n### |\n---\n\n|$)`, 'i');
  const match = content.match(sectionRegex);

  if (!match) return projects;

  // Parse table rows with backtick-wrapped paths and CLAUDE.md links
  const tableContent = match[0];
  const rowRegex = /\|\s*([^|]+)\s*\|\s*`([^`]+)`\s*\|\s*\[CLAUDE\.md\]\(([^)]+)\)\s*\|/g;

  let row;
  while ((row = rowRegex.exec(tableContent)) !== null) {
    projects.push({
      name: row[1].trim(),
      path: row[2].trim(),
      claudePath: row[3].trim()
    });
  }

  return projects;
}

async function syncProjectsIndex(content, discovered) {
  const changes = [];
  const warnings = [];

  const existingActive = parseProjectsTable(content, 'Active Projects');
  const existingGlassy = parseProjectsTable(content, 'Glassy Platform');

  // Normalize path for comparison (remove trailing slash, lowercase)
  const normalizePath = (p) => p.replace(/\/+$/, '').toLowerCase().trim();

  // Find missing projects in Active
  for (const project of discovered.active) {
    const normalizedDiscoveredPath = normalizePath(project.path);
    const exists = existingActive.some(p => normalizePath(p.path) === normalizedDiscoveredPath);
    if (!exists) {
      const newRow = `| ${project.name} | \`${project.path}\` | [CLAUDE.md](${project.claudePath}) |`;
      const tableEndRegex = /(### Active Projects[\s\S]*?\|[^|]+\|[^|]+\|[^|]+\|[\s\S]*?)(\n\n)/;
      const tableMatch = content.match(tableEndRegex);

      if (tableMatch) {
        const lastRowMatch = tableMatch[1].match(/(\| [^|]+ \| `[^`]+` \| \[CLAUDE\.md\]\([^)]+\) \|)(?=\s*$)/);
        if (lastRowMatch) {
          content = content.replace(lastRowMatch[1], `${lastRowMatch[1]}\n${newRow}`);
          changes.push(`Added "${project.name}" to Active Projects`);
        }
      }
    }
  }

  // Find missing projects in Glassy
  for (const project of discovered.glassy) {
    const normalizedDiscoveredPath = normalizePath(project.path);
    const exists = existingGlassy.some(p => normalizePath(p.path) === normalizedDiscoveredPath);
    if (!exists) {
      const newRow = `| ${project.name} | \`${project.path}\` | [CLAUDE.md](${project.claudePath}) |`;
      const tableEndRegex = /(### Glassy Platform[\s\S]*?\|[^|]+\|[^|]+\|[^|]+\|[\s\S]*?)(\n\n)/;
      const tableMatch = content.match(tableEndRegex);

      if (tableMatch) {
        const lastRowMatch = tableMatch[1].match(/(\| [^|]+ \| `[^`]+` \| \[CLAUDE\.md\]\([^)]+\) \|)(?=\s*$)/);
        if (lastRowMatch) {
          content = content.replace(lastRowMatch[1], `${lastRowMatch[1]}\n${newRow}`);
          changes.push(`Added "${project.name}" to Glassy Platform`);
        }
      }
    }
  }

  // Check for stale entries
  for (const project of existingActive) {
    const normalizedExistingPath = normalizePath(project.path);
    const exists = discovered.active.some(p => normalizePath(p.path) === normalizedExistingPath);
    if (!exists) {
      warnings.push(`"${project.name}" in Active Projects but CLAUDE.md not found`);
    }
  }

  for (const project of existingGlassy) {
    const normalizedExistingPath = normalizePath(project.path);
    const exists = discovered.glassy.some(p => normalizePath(p.path) === normalizedExistingPath);
    if (!exists) {
      warnings.push(`"${project.name}" in Glassy Platform but CLAUDE.md not found`);
    }
  }

  return { content, changes, warnings };
}

async function validateCrossReferences(content, workspace) {
  const changes = [];
  const warnings = [];

  const linkRegex = /\[([^\]]+)\]\(([^)]+)\)/g;
  let match;
  const linksToCheck = [];

  while ((match = linkRegex.exec(content)) !== null) {
    const linkText = match[1];
    const linkPath = match[2];

    if (!linkPath.startsWith('http') && !linkPath.startsWith('#')) {
      linksToCheck.push({ text: linkText, path: linkPath, fullMatch: match[0] });
    }
  }

  for (const link of linksToCheck) {
    const fullPath = path.join(workspace, link.path);
    try {
      await fs.access(fullPath);
    } catch {
      // Try to find the correct path
      const fileName = path.basename(link.path);
      const searchResult = await findFile(workspace, fileName);

      if (searchResult) {
        const relativePath = path.relative(workspace, searchResult);
        content = content.replace(
          link.fullMatch,
          `[${link.text}](${relativePath})`
        );
        changes.push(`Fixed link: ${link.path} → ${relativePath}`);
      } else {
        warnings.push(`Broken link: [${link.text}](${link.path})`);
      }
    }
  }

  return { content, changes, warnings };
}

async function findFile(workspace, fileName) {
  const searchPaths = ['', 'docs/', 'docs-portal/', 'scripts/'];

  for (const searchPath of searchPaths) {
    const fullPath = path.join(workspace, searchPath, fileName);
    try {
      await fs.access(fullPath);
      return fullPath;
    } catch {}
  }

  // Search in projects
  try {
    const projectsDir = path.join(workspace, 'projects');
    const entries = await fs.readdir(projectsDir, { withFileTypes: true });

    for (const entry of entries) {
      if (entry.isDirectory()) {
        const filePath = path.join(projectsDir, entry.name, fileName);
        try {
          await fs.access(filePath);
          return filePath;
        } catch {}
      }
    }
  } catch {}

  return null;
}

// Run the pre-commit hook
main().catch(err => {
  console.error(`${colors.red}❌ Squeegee pre-commit error: ${err.message}${colors.reset}`);
  // Don't block commit on error
  process.exit(0);
});
