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

async function detectFromPackageJson(projectPath, result) {
  const pkg = await readJsonSafe(path.join(projectPath, 'package.json'));
  if (!pkg) return;

  result.language = result.language || 'JavaScript/TypeScript';

  const deps = { ...(pkg.dependencies || {}), ...(pkg.devDependencies || {}) };

  // Frameworks
  if (deps['react-router']) result.frameworks.push('React Router');
  else if (deps.next) result.frameworks.push('Next.js');
  if (deps.react) result.frameworks.push('React');
  if (deps['react-native']) result.frameworks.push('React Native');
  if (deps.expo) result.frameworks.push('Expo');
  if (deps.fastify) result.frameworks.push('Fastify');
  if (deps.express) result.frameworks.push('Express');
  if (deps['@nestjs/core']) result.frameworks.push('NestJS');

  // Tools / state management
  if (deps.zustand) result.tools.push('Zustand');
  if (deps['@tanstack/react-query']) result.tools.push('TanStack Query');
  if (deps.prisma || deps['@prisma/client']) result.tools.push('Prisma');
  if (deps['better-auth']) result.tools.push('BetterAuth');
  if (deps.tailwindcss) result.tools.push('Tailwind CSS');
  if (deps.zod) result.tools.push('Zod');
  if (deps['react-hook-form']) result.tools.push('React Hook Form');
  if (deps.three) result.tools.push('Three.js');

  // Conventions
  if (deps.typescript) result.conventions.push('TypeScript');
  if (deps.eslint) result.conventions.push('ESLint');
  if (deps.prettier) result.conventions.push('Prettier');

  // Testing
  if (deps.vitest) result.testing.push('Vitest');
  if (deps.jest) result.testing.push('Jest');
  if (deps['@playwright/test']) result.testing.push('Playwright');

  // Key dependencies (exclude noise)
  result.dependencies = Object.keys(deps)
    .filter(d => !d.startsWith('@types/') && !d.startsWith('eslint-'))
    .slice(0, 20);
}

async function detectFromPython(projectPath, result) {
  const reqs = await readFileSafe(path.join(projectPath, 'requirements.txt'));
  const pyproject = await readFileSafe(path.join(projectPath, 'pyproject.toml'));
  const source = reqs || pyproject;

  if (!source) return;

  result.language = result.language || 'Python';

  if (source.includes('fastapi')) result.frameworks.push('FastAPI');
  if (source.includes('django')) result.frameworks.push('Django');
  if (source.includes('flask')) result.frameworks.push('Flask');
  if (source.includes('pydantic')) result.tools.push('Pydantic');
  if (source.includes('sqlalchemy')) result.tools.push('SQLAlchemy');

  if (source.includes('black')) result.conventions.push('Black');
  if (source.includes('ruff')) result.conventions.push('Ruff');
  if (source.includes('mypy')) result.conventions.push('MyPy');

  if (source.includes('pytest')) result.testing.push('pytest');

  // Extract dependency names from requirements.txt
  if (reqs) {
    result.dependencies = reqs.split('\n')
      .filter(l => l && !l.startsWith('#') && !l.startsWith('-'))
      .map(l => l.split('==')[0].split('>=')[0].split('~=')[0].trim())
      .filter(Boolean)
      .slice(0, 20);
  }
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
