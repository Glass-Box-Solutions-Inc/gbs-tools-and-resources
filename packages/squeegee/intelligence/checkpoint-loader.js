/**
 * Checkpoint Queue Loader
 *
 * Loads context window checkpoint events written during development sessions.
 * Checkpoints follow the org's CONTEXT_WINDOW_CHECKPOINT_STANDARD format and
 * are found in `.planning/STATE.md` files across local repo clones, or in a
 * dedicated checkpoint queue directory.
 *
 * Checkpoint format (from CONTEXT_WINDOW_CHECKPOINT_STANDARD):
 *   ## Checkpoint [YYYY-MM-DD HH:MM]
 *   **Task:** ...
 *   **Completed:** ...
 *   **In Progress:** ...
 *   **Next Steps:** ...
 *   **Key Decisions:** ...
 *   **Blockers:** ...
 *
 * The loader scans a configurable directory for checkpoint files, parses them,
 * and returns an array of checkpoint event objects for the given date.
 *
 * Designed for graceful degradation — missing directories or unparseable files
 * return an empty array rather than throwing.
 *
 * @file checkpoint-loader.js
 * @module intelligence/checkpoint-loader
 *
 * @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
 */

'use strict';

const fs = require('fs').promises;
const path = require('path');
const { safeExecute } = require('./utils');

// Default checkpoint queue directory
// Agents drop checkpoint .md files here when triggered during sessions
const DEFAULT_CHECKPOINT_DIR = '/tmp/squeegee-checkpoints';

// Default repos workspace root — scan .planning/STATE.md in each subdirectory
const DEFAULT_WORKSPACE_DIR = '/home/vncuser';

/**
 * Parse a single checkpoint block from markdown text.
 * Extracts fields written per CONTEXT_WINDOW_CHECKPOINT_STANDARD.
 *
 * @param {string} block - Markdown block starting with "## Checkpoint [...]"
 * @param {string} repo - Repository name (from file path context)
 * @param {string} dateStr - Date filter (YYYY-MM-DD) — only include checkpoints from this date
 * @returns {Object|null} - Parsed checkpoint or null if date doesn't match / unparseable
 */
function parseCheckpointBlock(block, repo, dateStr) {
  // Extract timestamp from "## Checkpoint [YYYY-MM-DD HH:MM]"
  const timestampMatch = block.match(/##\s+Checkpoint\s+\[(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})\]/i);
  if (!timestampMatch) {
    return null;
  }

  const checkpointDate = timestampMatch[1]; // YYYY-MM-DD
  const checkpointTime = timestampMatch[2]; // HH:MM

  // Only include checkpoints for the requested date
  if (dateStr && checkpointDate !== dateStr) {
    return null;
  }

  const timestamp = new Date(`${checkpointDate}T${checkpointTime}:00`).toISOString();

  // Extract named fields — each is "**Field:** value" on its own line
  function extractField(fieldName) {
    const regex = new RegExp(`\\*\\*${fieldName}:\\*\\*\\s*(.+)`, 'i');
    const match = block.match(regex);
    return match ? match[1].trim() : null;
  }

  const task = extractField('Task');
  const completed = extractField('Completed');
  const inProgress = extractField('In Progress');
  const nextSteps = extractField('Next Steps');
  const blockers = extractField('Blockers');

  // Extract context percentage if present ("Context: 65%" or "**Context Window:** 65%")
  const contextMatch = block.match(/(?:Context(?:\s+Window)?[:\s]+)(\d+)%/i);
  const contextPct = contextMatch ? parseInt(contextMatch[1], 10) : null;

  return {
    repo,
    user: 'agent', // Checkpoints are written by agents; user field for display
    timestamp,
    context_pct: contextPct,
    phase: task || null,
    completed: completed || inProgress || null,
    next: nextSteps || null,
    blockers: blockers || null,
    source: 'state_md'
  };
}

/**
 * Parse all checkpoint blocks from a STATE.md file.
 *
 * @param {string} content - File content
 * @param {string} repo - Repository name
 * @param {string} dateStr - Date filter (YYYY-MM-DD)
 * @returns {Array<Object>} - Array of checkpoint events
 */
function parseStateFile(content, repo, dateStr) {
  const checkpoints = [];

  // Split on "## Checkpoint [" headers — each block ends at the next "## " header or EOF
  const sections = content.split(/(?=##\s+Checkpoint\s+\[)/i);

  for (const section of sections) {
    if (!section.match(/^##\s+Checkpoint\s+\[/i)) {
      continue;
    }
    const checkpoint = parseCheckpointBlock(section, repo, dateStr);
    if (checkpoint) {
      checkpoints.push(checkpoint);
    }
  }

  return checkpoints;
}

/**
 * Load checkpoint events from a dedicated checkpoint queue directory.
 * Agents drop .md files here (filename: repo-name_YYYY-MM-DDTHH-MM.md).
 *
 * @param {string} queueDir - Path to checkpoint queue directory
 * @param {string} dateStr - Date filter (YYYY-MM-DD)
 * @returns {Promise<Array<Object>>} - Array of checkpoint events
 */
async function loadFromQueueDir(queueDir, dateStr) {
  const checkpoints = [];

  let entries;
  try {
    entries = await fs.readdir(queueDir);
  } catch (error) {
    if (error.code === 'ENOENT') {
      // Directory doesn't exist — no checkpoints, not an error
      return [];
    }
    throw error;
  }

  const mdFiles = entries.filter(f => f.endsWith('.md'));

  for (const filename of mdFiles) {
    const filePath = path.join(queueDir, filename);

    const content = await safeExecute(
      () => fs.readFile(filePath, 'utf-8'),
      null,
      `checkpoint-loader/read-queue-file/${filename}`
    );

    if (!content) continue;

    // Derive repo name from filename: "repo-name_2026-03-27T14-30.md" → "repo-name"
    // Or fall back to filename without extension
    const repoMatch = filename.match(/^(.+?)_\d{4}-\d{2}-\d{2}/);
    const repo = repoMatch ? repoMatch[1] : path.basename(filename, '.md');

    const parsed = parseStateFile(content, repo, dateStr);
    checkpoints.push(...parsed);
  }

  return checkpoints;
}

/**
 * Load checkpoint events from .planning/STATE.md files in workspace repos.
 * Scans immediate subdirectories of workspaceDir for .planning/STATE.md.
 *
 * @param {string} workspaceDir - Root workspace directory
 * @param {string} dateStr - Date filter (YYYY-MM-DD)
 * @returns {Promise<Array<Object>>} - Array of checkpoint events
 */
async function loadFromWorkspace(workspaceDir, dateStr) {
  const checkpoints = [];

  let entries;
  try {
    entries = await fs.readdir(workspaceDir, { withFileTypes: true });
  } catch (error) {
    if (error.code === 'ENOENT') {
      return [];
    }
    throw error;
  }

  const subdirs = entries
    .filter(e => e.isDirectory())
    .map(e => e.name)
    // Skip hidden directories and known non-repo dirs
    .filter(name => !name.startsWith('.') && name !== 'node_modules');

  for (const dirName of subdirs) {
    const statePath = path.join(workspaceDir, dirName, '.planning', 'STATE.md');

    const content = await safeExecute(
      () => fs.readFile(statePath, 'utf-8'),
      null,
      `checkpoint-loader/read-state-md/${dirName}`
    );

    if (!content) continue;

    const parsed = parseStateFile(content, dirName, dateStr);
    if (parsed.length > 0) {
      checkpoints.push(...parsed);
    }
  }

  return checkpoints;
}

/**
 * Load all checkpoint events for a given date.
 *
 * Checks two sources in order:
 *   1. Dedicated checkpoint queue directory (config.checkpoints.queue_dir or DEFAULT_CHECKPOINT_DIR)
 *   2. Workspace .planning/STATE.md files (config.checkpoints.workspace_dir or DEFAULT_WORKSPACE_DIR)
 *
 * Both sources are checked — results are merged and deduped by timestamp+repo.
 * All errors are handled gracefully; missing directories return empty arrays.
 *
 * @param {string} dateStr - Date to load checkpoints for (YYYY-MM-DD)
 * @param {Object} config - Intelligence configuration
 * @returns {Promise<Array<Object>>} - Array of checkpoint event objects
 */
async function load(dateStr, config) {
  const checkpointConfig = config?.intelligence?.checkpoints || {};
  const queueDir = checkpointConfig.queue_dir || DEFAULT_CHECKPOINT_DIR;
  const workspaceDir = checkpointConfig.workspace_dir || DEFAULT_WORKSPACE_DIR;
  const enabled = checkpointConfig.enabled !== false; // Default: enabled

  if (!enabled) {
    console.log('Checkpoint loading disabled in configuration');
    return [];
  }

  console.log(`Loading checkpoints for ${dateStr} from queue: ${queueDir}, workspace: ${workspaceDir}`);

  // Load from both sources, gracefully degrading on any error
  const [queueCheckpoints, workspaceCheckpoints] = await Promise.all([
    safeExecute(
      () => loadFromQueueDir(queueDir, dateStr),
      [],
      'checkpoint-loader/queue-dir'
    ),
    safeExecute(
      () => loadFromWorkspace(workspaceDir, dateStr),
      [],
      'checkpoint-loader/workspace'
    )
  ]);

  const allCheckpoints = [...queueCheckpoints, ...workspaceCheckpoints];

  // Deduplicate by repo+timestamp (same checkpoint may appear in both sources)
  const seen = new Set();
  const unique = allCheckpoints.filter(cp => {
    const key = `${cp.repo}:${cp.timestamp}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });

  // Sort chronologically
  unique.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));

  console.log(`Loaded ${unique.length} checkpoint(s) for ${dateStr}`);

  return unique;
}

module.exports = {
  load,
  // Export internals for testing
  parseCheckpointBlock,
  parseStateFile,
  loadFromQueueDir,
  loadFromWorkspace
};
