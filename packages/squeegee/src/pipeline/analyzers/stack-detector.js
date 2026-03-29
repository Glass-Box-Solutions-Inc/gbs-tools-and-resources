/**
 * Stack detector — single source of truth for tech stack detection.
 *
 * Replaces 3 duplicated detection routines in the old monolith.
 * Analyzes package.json, requirements.txt, pyproject.toml, and directory structure.
 *
 * @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
 */

const path = require('path');
const { readJsonSafe, readFileSafe, listDirs } = require('../utils');

/**
 * Detect full tech stack for a project path.
 * Returns structured object with frameworks, tools, conventions, testing, and deps.
 */
async function detectStack(projectPath) {
  const result = {
    frameworks: [],
    tools: [],
    conventions: [],
    testing: [],
    dependencies: [],
    language: null,
    directories: [],
  };

  await detectFromPackageJson(projectPath, result);
  await detectFromPython(projectPath, result);
  await detectFromDirectoryStructure(projectPath, result);

  return result;
}

// Known frameworks/tools for sorting dependencies by importance
const KNOWN_PACKAGES_JS = new Set([
  'react', 'react-dom', 'react-router', 'next', 'react-native', 'expo',
  'fastify', 'express', '@nestjs/core', 'zustand', '@tanstack/react-query',
  'prisma', '@prisma/client', 'better-auth', 'tailwindcss', 'zod',
  'react-hook-form', 'three', 'typescript', 'vitest', 'jest',
  '@playwright/test', 'vite', 'webpack', 'esbuild', 'socket.io',
  'graphql', 'apollo-server', 'mongoose', 'sequelize', 'knex',
]);

async function detectFromPackageJson(projectPath, result) {
  const pkg = await readJsonSafe(path.join(projectPath, 'package.json'));
  if (!pkg) return;

  result.language = result.language || 'JavaScript/TypeScript';

  const depNames = new Set([
    ...Object.keys(pkg.dependencies || {}),
    ...Object.keys(pkg.devDependencies || {}),
  ]);

  // Frameworks — exact key lookups
  if (depNames.has('react-router')) result.frameworks.push('React Router');
  else if (depNames.has('next')) result.frameworks.push('Next.js');
  if (depNames.has('react')) result.frameworks.push('React');
  if (depNames.has('react-native')) result.frameworks.push('React Native');
  if (depNames.has('expo')) result.frameworks.push('Expo');
  if (depNames.has('fastify')) result.frameworks.push('Fastify');
  if (depNames.has('express')) result.frameworks.push('Express');
  if (depNames.has('@nestjs/core')) result.frameworks.push('NestJS');

  // Tools / state management
  if (depNames.has('zustand')) result.tools.push('Zustand');
  if (depNames.has('@tanstack/react-query')) result.tools.push('TanStack Query');
  if (depNames.has('prisma') || depNames.has('@prisma/client')) result.tools.push('Prisma');
  if (depNames.has('better-auth')) result.tools.push('BetterAuth');
  if (depNames.has('tailwindcss')) result.tools.push('Tailwind CSS');
  if (depNames.has('zod')) result.tools.push('Zod');
  if (depNames.has('react-hook-form')) result.tools.push('React Hook Form');
  if (depNames.has('three')) result.tools.push('Three.js');

  // Conventions
  if (depNames.has('typescript')) result.conventions.push('TypeScript');
  if (depNames.has('eslint')) result.conventions.push('ESLint');
  if (depNames.has('prettier')) result.conventions.push('Prettier');

  // Testing
  if (depNames.has('vitest')) result.testing.push('Vitest');
  if (depNames.has('jest')) result.testing.push('Jest');
  if (depNames.has('@playwright/test')) result.testing.push('Playwright');

  // Key dependencies — exclude noise, sort by importance (known frameworks first, then alphabetical)
  const filtered = [...depNames]
    .filter(d => !d.startsWith('@types/') && !d.startsWith('eslint-'));
  filtered.sort((a, b) => {
    const aKnown = KNOWN_PACKAGES_JS.has(a);
    const bKnown = KNOWN_PACKAGES_JS.has(b);
    if (aKnown && !bKnown) return -1;
    if (!aKnown && bKnown) return 1;
    return a.localeCompare(b);
  });
  result.dependencies = filtered.slice(0, 20);
}

// Known Python packages for sorting dependencies by importance
const KNOWN_PACKAGES_PY = new Set([
  'fastapi', 'django', 'flask', 'pydantic', 'sqlalchemy', 'uvicorn',
  'gunicorn', 'celery', 'redis', 'httpx', 'requests', 'aiohttp',
  'pytest', 'black', 'ruff', 'mypy', 'alembic', 'boto3',
  'numpy', 'pandas', 'scipy', 'torch', 'tensorflow',
]);

/**
 * Extract package names from requirements.txt lines.
 * Handles version specifiers: ==, >=, <=, ~=, !=, >, <, [extras]
 */
function parseRequirementsTxt(content) {
  return content.split('\n')
    .map(l => l.trim())
    .filter(l => l && !l.startsWith('#') && !l.startsWith('-'))
    .map(l => l.split(/[=><~!;\[]/)[0].trim().toLowerCase())
    .filter(Boolean);
}

/**
 * Extract dependency names from pyproject.toml content.
 * Handles both `dependencies = [...]` lists and `name = "..."` under [project].
 */
function parsePyprojectDeps(content) {
  const deps = [];
  const lines = content.split('\n');
  let inDeps = false;

  for (const line of lines) {
    const trimmed = line.trim();

    // Detect start of a dependencies list
    if (/^dependencies\s*=\s*\[/.test(trimmed) || /^requires\s*=\s*\[/.test(trimmed)) {
      inDeps = true;
      // Handle inline entries on the same line as the opening bracket
      const inline = trimmed.replace(/^[^[]*\[/, '').replace(/].*$/, '');
      if (inline) {
        for (const item of inline.split(',')) {
          const name = item.replace(/["']/g, '').split(/[=><~!;\[]/)[0].trim().toLowerCase();
          if (name) deps.push(name);
        }
      }
      if (trimmed.includes(']')) inDeps = false;
      continue;
    }

    if (inDeps) {
      if (trimmed.startsWith(']')) {
        inDeps = false;
        continue;
      }
      const name = trimmed.replace(/["',]/g, '').split(/[=><~!;\[]/)[0].trim().toLowerCase();
      if (name && !name.startsWith('#')) deps.push(name);
    }
  }

  return deps;
}

async function detectFromPython(projectPath, result) {
  const reqs = await readFileSafe(path.join(projectPath, 'requirements.txt'));
  const pyproject = await readFileSafe(path.join(projectPath, 'pyproject.toml'));

  if (!reqs && !pyproject) return;

  result.language = result.language || 'Python';

  // Build a set of exact package names from both sources
  const pkgNames = new Set();

  if (reqs) {
    for (const name of parseRequirementsTxt(reqs)) {
      pkgNames.add(name);
    }
  }

  if (pyproject) {
    for (const name of parsePyprojectDeps(pyproject)) {
      pkgNames.add(name);
    }
  }

  // Frameworks — exact match
  if (pkgNames.has('fastapi')) result.frameworks.push('FastAPI');
  if (pkgNames.has('django')) result.frameworks.push('Django');
  if (pkgNames.has('flask')) result.frameworks.push('Flask');
  if (pkgNames.has('pydantic')) result.tools.push('Pydantic');
  if (pkgNames.has('sqlalchemy')) result.tools.push('SQLAlchemy');

  if (pkgNames.has('black')) result.conventions.push('Black');
  if (pkgNames.has('ruff')) result.conventions.push('Ruff');
  if (pkgNames.has('mypy')) result.conventions.push('MyPy');

  if (pkgNames.has('pytest')) result.testing.push('pytest');

  // Dependencies list — sort by importance (known packages first, then alphabetical)
  const allDeps = [...pkgNames];
  allDeps.sort((a, b) => {
    const aKnown = KNOWN_PACKAGES_PY.has(a);
    const bKnown = KNOWN_PACKAGES_PY.has(b);
    if (aKnown && !bKnown) return -1;
    if (!aKnown && bKnown) return 1;
    return a.localeCompare(b);
  });
  result.dependencies = allDeps.slice(0, 20);
}

async function detectFromDirectoryStructure(projectPath, result) {
  const dirs = await listDirs(projectPath);
  result.directories = dirs;

  // Detect architectural patterns from directory names
  const patterns = {
    'src': 'src/ source layout',
    'app': 'app/ directory (framework convention)',
    'components': 'Component-based architecture',
    'hooks': 'Custom React hooks',
    'stores': 'Store-based state management',
    'services': 'Service layer',
    'repositories': 'Repository pattern',
    'middleware': 'Middleware pattern',
    'models': 'Model layer',
    'types': 'Centralized type definitions',
    'utils': 'Utility modules',
    'lib': 'Library modules',
    'api': 'API layer separation',
    'tests': 'Dedicated test directory',
    '__tests__': 'Jest test convention',
    'prisma': 'Prisma ORM',
    'server': 'Server-side code separation',
  };

  for (const dir of dirs) {
    if (patterns[dir]) {
      result.conventions.push(patterns[dir]);
    }
  }
}

module.exports = { detectStack };
