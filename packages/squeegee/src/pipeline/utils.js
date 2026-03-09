/**
 * Squeegee shared utilities
 *
 * Single source of truth for common functions used across all stages.
 *
 * @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
 */

const fs = require('fs').promises;
const crypto = require('crypto');

const log = (msg, type = 'info') => {
  const colors = { info: '\x1b[36m', success: '\x1b[32m', warn: '\x1b[33m', error: '\x1b[31m' };
  const icons = { info: 'ℹ', success: '✓', warn: '⚠', error: '✗' };
  console.log(`${colors[type] || ''}${icons[type] || 'ℹ'}\x1b[0m ${msg}`);
};

const hash = (content) => crypto.createHash('sha256').update(content).digest('hex').slice(0, 12);

async function fileExists(filePath) {
  try {
    await fs.access(filePath);
    return true;
  } catch {
    return false;
  }
}

async function readJsonSafe(filePath, fallback = null) {
  try {
    const content = await fs.readFile(filePath, 'utf-8');
    return JSON.parse(content);
  } catch {
    return fallback;
  }
}

async function writeJson(filePath, data) {
  await fs.mkdir(require('path').dirname(filePath), { recursive: true });
  await fs.writeFile(filePath, JSON.stringify(data, null, 2) + '\n', 'utf-8');
}

async function readFileSafe(filePath, fallback = '') {
  try {
    return await fs.readFile(filePath, 'utf-8');
  } catch {
    return fallback;
  }
}

async function ensureDir(dirPath) {
  await fs.mkdir(dirPath, { recursive: true });
}

/**
 * List directories (not files) in a given path.
 */
async function listDirs(dirPath) {
  try {
    const entries = await fs.readdir(dirPath, { withFileTypes: true });
    return entries.filter(e => e.isDirectory()).map(e => e.name);
  } catch {
    return [];
  }
}

/**
 * Recursively find files matching an extension, excluding common noise directories.
 */
async function findFiles(dirPath, extension, excludeDirs = []) {
  const defaultExclude = [
    'node_modules', '.git', '__pycache__', '.venv', 'venv', 'dist', 'build',
    '.next', 'coverage', '.svelte-kit', '.pytest_cache', 'htmlcov', '.mypy_cache',
    '.tox', 'eggs', '.cache', '.vercel', '.turbo', 'vendor', '.nuxt', '.output', 'out'
  ];
  const excluded = new Set([...defaultExclude, ...excludeDirs]);
  const results = [];

  async function walk(dir) {
    try {
      const entries = await fs.readdir(dir, { withFileTypes: true });
      for (const entry of entries) {
        if (excluded.has(entry.name)) continue;
        const fullPath = require('path').join(dir, entry.name);
        if (entry.isDirectory()) {
          await walk(fullPath);
        } else if (entry.name.endsWith(extension)) {
          results.push(fullPath);
        }
      }
    } catch {
      // Permission denied or deleted mid-scan
    }
  }

  await walk(dirPath);
  return results;
}

module.exports = {
  log,
  hash,
  fileExists,
  readJsonSafe,
  writeJson,
  readFileSafe,
  ensureDir,
  listDirs,
  findFiles,
};
