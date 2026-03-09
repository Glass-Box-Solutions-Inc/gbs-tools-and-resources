/**
 * Stage 07: Cross-Project Pattern Library
 *
 * Detects real implementation patterns (not just dependency frequency).
 * Analyzes state management, API patterns, auth, testing, and directory conventions.
 *
 * @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
 */

const fs = require('fs').promises;
const path = require('path');
const { log, fileExists, ensureDir, readFileSafe } = require('../utils');
const { resolveProjectPath } = require('../config');
const { detectStack } = require('../analyzers/stack-detector');
const { timestamp } = require('../formatters/markdown');

async function run(config, discovery) {
  log('Stage 7: Generating pattern library...', 'info');

  if (!config.patternLibrary.enabled) {
    log('Pattern library disabled in config', 'warn');
    return { patterns: 0 };
  }

  const projectAnalyses = {};

  for (const project of config.projects) {
    const projectPath = resolveProjectPath(config, project.path);
    if (!(await fileExists(projectPath))) continue;

    const stack = await detectStack(projectPath);
    const codePatterns = await detectCodePatterns(projectPath);

    projectAnalyses[project.name] = {
      stack,
      codePatterns,
      path: project.path,
    };
  }

  const patterns = findCrossProjectPatterns(projectAnalyses, config);
  await generatePatternLibrary(patterns, config);

  log(`Detected ${patterns.length} cross-project patterns`, 'success');
  return { patterns: patterns.length };
}

/**
 * Detect code-level patterns by scanning for common imports and patterns.
 */
async function detectCodePatterns(projectPath) {
  const patterns = [];

  // Check for common patterns in code files
  const checks = [
    { file: 'app/root.tsx', pattern: /zustand|create\(/, name: 'Zustand store' },
    { file: 'app/root.tsx', pattern: /QueryClient|TanStack/, name: 'TanStack Query' },
    { file: 'server/index.ts', pattern: /fastify/i, name: 'Fastify server' },
    { file: 'server/index.ts', pattern: /express/i, name: 'Express server' },
  ];

  // Check for authentication patterns
  const authFiles = ['server/auth.ts', 'server/lib/auth.ts', 'app/lib/auth.ts', 'src/auth/auth.module.ts'];
  for (const authFile of authFiles) {
    const content = await readFileSafe(path.join(projectPath, authFile));
    if (content) {
      if (content.includes('betterAuth') || content.includes('better-auth')) patterns.push('BetterAuth');
      if (content.includes('iron-session')) patterns.push('Iron Session');
      if (content.includes('passport')) patterns.push('Passport.js');
      if (content.includes('jwt') || content.includes('jsonwebtoken')) patterns.push('JWT Auth');
    }
  }

  // Check for API patterns
  const apiDirs = ['app/routes/api', 'server/routes', 'src/controllers'];
  for (const apiDir of apiDirs) {
    if (await fileExists(path.join(projectPath, apiDir))) {
      patterns.push('REST API routes');
    }
  }

  // Check for database patterns
  const prismaSchema = await readFileSafe(path.join(projectPath, 'prisma/schema.prisma'));
  if (prismaSchema) {
    patterns.push('Prisma ORM');
    if (prismaSchema.includes('provider = "postgresql"')) patterns.push('PostgreSQL');
    if (prismaSchema.includes('provider = "sqlite"')) patterns.push('SQLite');
  }

  // Check for Zod validation
  const zodUsage = await findPatternInTree(projectPath, /from ['"]zod['"]/);
  if (zodUsage) patterns.push('Zod validation');

  return patterns;
}

/**
 * Quick check if a regex pattern exists anywhere in .ts/.tsx files.
 */
async function findPatternInTree(projectPath, pattern) {
  try {
    const { execSync } = require('child_process');
    // Use git grep for speed
    execSync(
      `git grep -l "${pattern.source}" -- "*.ts" "*.tsx"`,
      { cwd: projectPath, encoding: 'utf-8', stdio: ['pipe', 'pipe', 'ignore'] }
    );
    return true;
  } catch {
    return false;
  }
}

/**
 * Find patterns shared across 2+ projects.
 */
function findCrossProjectPatterns(projectAnalyses, config) {
  const minProjects = config.patternLibrary.minProjectsForPattern;
  const patterns = [];

  // Collect all pattern occurrences
  const patternProjects = {};

  for (const [projectName, analysis] of Object.entries(projectAnalyses)) {
    const allPatterns = [
      ...analysis.stack.frameworks.map(f => ({ name: f, category: 'Framework' })),
      ...analysis.stack.tools.map(t => ({ name: t, category: 'Tooling' })),
      ...analysis.codePatterns.map(p => ({ name: p, category: detectCategory(p) })),
    ];

    for (const p of allPatterns) {
      const key = p.name.toLowerCase();
      if (!patternProjects[key]) {
        patternProjects[key] = { name: p.name, category: p.category, projects: [] };
      }
      if (!patternProjects[key].projects.includes(projectName)) {
        patternProjects[key].projects.push(projectName);
      }
    }
  }

  // Detect interesting combinations
  const zustandProjects = (patternProjects['zustand'] || {}).projects || [];
  const tanstackProjects = (patternProjects['tanstack query'] || {}).projects || [];
  const overlap = zustandProjects.filter(p => tanstackProjects.includes(p));

  if (overlap.length >= minProjects) {
    patterns.push({
      name: 'Dual State Management (Zustand + TanStack Query)',
      category: 'State Management',
      projects: overlap,
      description: 'Zustand for UI state, TanStack Query for server state. Separation of concerns pattern.',
      references: overlap.map(p => `${projectAnalyses[p]?.path || p}/app/`),
    });
  }

  // Single patterns used across projects
  for (const [key, data] of Object.entries(patternProjects)) {
    if (data.projects.length >= minProjects) {
      // Skip if already captured in a combination pattern
      if (['zustand', 'tanstack query'].includes(key) && overlap.length >= minProjects) continue;

      patterns.push({
        name: data.name,
        category: data.category,
        projects: data.projects,
        description: `Used in ${data.projects.length} projects.`,
        references: data.projects.map(p => projectAnalyses[p]?.path || p),
      });
    }
  }

  return patterns.sort((a, b) => b.projects.length - a.projects.length);
}

function detectCategory(patternName) {
  const lower = patternName.toLowerCase();
  if (lower.includes('auth') || lower.includes('jwt') || lower.includes('session')) return 'Authentication';
  if (lower.includes('api') || lower.includes('rest') || lower.includes('route')) return 'API Design';
  if (lower.includes('prisma') || lower.includes('postgres') || lower.includes('sqlite') || lower.includes('database')) return 'Database';
  if (lower.includes('test') || lower.includes('vitest') || lower.includes('jest') || lower.includes('playwright')) return 'Testing';
  if (lower.includes('zod') || lower.includes('validation')) return 'Validation';
  if (lower.includes('zustand') || lower.includes('tanstack') || lower.includes('state')) return 'State Management';
  return 'Tooling';
}

async function generatePatternLibrary(patterns, config) {
  const outputPath = path.join(config.workspace, config.patternLibrary.outputPath);
  const date = timestamp();

  let content = `# Cross-Project Pattern Library

**Last Updated:** ${date}
**Patterns Cataloged:** ${patterns.length}
**Generated by:** Squeegee v2.0

---

This document catalogs patterns and practices used across multiple projects. Use it for consistency and to leverage proven approaches.

---

`;

  // Group by category
  const byCategory = {};
  for (const pattern of patterns) {
    if (!byCategory[pattern.category]) byCategory[pattern.category] = [];
    byCategory[pattern.category].push(pattern);
  }

  for (const [category, categoryPatterns] of Object.entries(byCategory)) {
    content += `## ${category}\n\n`;

    for (const pattern of categoryPatterns) {
      content += `### ${pattern.name}\n`;
      content += `**Projects (${pattern.projects.length}):** ${pattern.projects.join(', ')}\n\n`;
      content += `${pattern.description}\n\n`;

      if (pattern.references && pattern.references.length > 0) {
        content += `**References:**\n`;
        for (const ref of pattern.references) {
          content += `- \`${ref}\`\n`;
        }
        content += '\n';
      }

      content += `---\n\n`;
    }
  }

  content += `## Usage

When starting a new project or feature:
1. Check this library for relevant patterns
2. Reference the listed projects for implementation examples
3. Maintain consistency with existing approaches

---

*Auto-generated by Squeegee Documentation System*
`;

  await ensureDir(path.dirname(outputPath));
  await fs.writeFile(outputPath, content, 'utf-8');
  log(`Pattern library saved to ${config.patternLibrary.outputPath}`, 'success');
}

module.exports = { run };
