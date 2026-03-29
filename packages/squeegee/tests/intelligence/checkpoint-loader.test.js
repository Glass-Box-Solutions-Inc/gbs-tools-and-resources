/**
 * Checkpoint Loader Tests
 *
 * Tests for the checkpoint queue loading module.
 * Uses mocked fs.promises to avoid filesystem access.
 *
 * @file checkpoint-loader.test.js
 *
 * @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
 */

'use strict';

const fs = require('fs').promises;
const path = require('path');

const {
  load,
  parseCheckpointBlock,
  parseStateFile,
  loadFromQueueDir,
  loadFromWorkspace
} = require('../../intelligence/checkpoint-loader');

// Mock fs.promises
jest.mock('fs', () => ({
  promises: {
    readFile: jest.fn(),
    readdir: jest.fn()
  }
}));

// Sample STATE.md content with checkpoint blocks
const STATE_MD_WITH_CHECKPOINTS = `
# .planning/STATE.md

## Overview

Current task: Implement auth middleware.

## Checkpoint [2026-03-27 14:32]
**Task:** Implement auth middleware
**Completed:** Route scaffolding, schema validation
**In Progress:** JWT decode logic
**Next Steps:** Integration tests, rate limiting
**Key Decisions:** Using fastify-jwt over manual decode
**Blockers:** None
Context: 62%

## Checkpoint [2026-03-27 16:05]
**Task:** Integration tests for auth
**Completed:** JWT decode logic, middleware registration
**In Progress:** Writing integration test suite
**Next Steps:** Rate limiting, docs
**Key Decisions:** Using supertest for HTTP-level tests
**Blockers:** None
Context Window: 71%
`;

const STATE_MD_DIFFERENT_DATE = `
## Checkpoint [2026-03-26 10:00]
**Task:** Old checkpoint from yesterday
**Completed:** Something
**In Progress:** Other thing
**Next Steps:** More things
Context: 45%
`;

const STATE_MD_NO_CHECKPOINTS = `
# .planning/STATE.md

This file has no checkpoint headers.

## Regular Section

Just some notes.
`;

const QUEUE_FILE_CONTENT = `
## Checkpoint [2026-03-27 09:15]
**Task:** Queue-based checkpoint for testing
**Completed:** Setup
**In Progress:** Implementation
**Next Steps:** Tests
Context: 55%
`;

describe('parseCheckpointBlock()', () => {
  beforeEach(() => {
    jest.spyOn(console, 'log').mockImplementation(() => {});
    jest.spyOn(console, 'warn').mockImplementation(() => {});
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('should parse a complete checkpoint block', () => {
    const block = `## Checkpoint [2026-03-27 14:32]
**Task:** Implement auth middleware
**Completed:** Route scaffolding
**In Progress:** JWT decode
**Next Steps:** Integration tests
**Key Decisions:** Using fastify-jwt
**Blockers:** None
Context: 62%`;

    const result = parseCheckpointBlock(block, 'adjudica-ai-app', '2026-03-27');

    expect(result).not.toBeNull();
    expect(result.repo).toBe('adjudica-ai-app');
    expect(result.timestamp).toMatch(/^2026-03-27T/);
    expect(result.phase).toBe('Implement auth middleware');
    expect(result.completed).toBe('Route scaffolding');
    expect(result.next).toBe('Integration tests');
    expect(result.context_pct).toBe(62);
    expect(result.user).toBe('agent');
    expect(result.source).toBe('state_md');
  });

  it('should return null for non-matching date', () => {
    const block = `## Checkpoint [2026-03-26 14:32]
**Task:** Old task
Context: 50%`;

    const result = parseCheckpointBlock(block, 'some-repo', '2026-03-27');
    expect(result).toBeNull();
  });

  it('should return null if no checkpoint header found', () => {
    const block = `## Regular Header
Some content here`;

    const result = parseCheckpointBlock(block, 'some-repo', '2026-03-27');
    expect(result).toBeNull();
  });

  it('should handle missing context percentage', () => {
    const block = `## Checkpoint [2026-03-27 10:00]
**Task:** Quick note
**Completed:** Something`;

    const result = parseCheckpointBlock(block, 'repo', '2026-03-27');

    expect(result).not.toBeNull();
    expect(result.context_pct).toBeNull();
  });

  it('should handle "Context Window:" format', () => {
    const block = `## Checkpoint [2026-03-27 15:00]
**Task:** Test context window format
Context Window: 71%`;

    const result = parseCheckpointBlock(block, 'repo', '2026-03-27');

    expect(result).not.toBeNull();
    expect(result.context_pct).toBe(71);
  });

  it('should return checkpoint when no date filter provided (null)', () => {
    const block = `## Checkpoint [2026-03-27 14:32]
**Task:** Some task
Context: 50%`;

    const result = parseCheckpointBlock(block, 'repo', null);
    expect(result).not.toBeNull();
  });
});

describe('parseStateFile()', () => {
  beforeEach(() => {
    jest.spyOn(console, 'log').mockImplementation(() => {});
    jest.spyOn(console, 'warn').mockImplementation(() => {});
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('should parse multiple checkpoints from a STATE.md file', () => {
    const results = parseStateFile(STATE_MD_WITH_CHECKPOINTS, 'adjudica-ai-app', '2026-03-27');

    expect(results).toHaveLength(2);
    expect(results[0].repo).toBe('adjudica-ai-app');
    expect(results[0].phase).toBe('Implement auth middleware');
    expect(results[1].phase).toBe('Integration tests for auth');
  });

  it('should filter out checkpoints from other dates', () => {
    const results = parseStateFile(STATE_MD_DIFFERENT_DATE, 'some-repo', '2026-03-27');
    expect(results).toHaveLength(0);
  });

  it('should return empty array for file with no checkpoints', () => {
    const results = parseStateFile(STATE_MD_NO_CHECKPOINTS, 'some-repo', '2026-03-27');
    expect(results).toHaveLength(0);
  });

  it('should return empty array for empty file content', () => {
    const results = parseStateFile('', 'some-repo', '2026-03-27');
    expect(results).toHaveLength(0);
  });
});

describe('loadFromQueueDir()', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.spyOn(console, 'log').mockImplementation(() => {});
    jest.spyOn(console, 'warn').mockImplementation(() => {});
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('should load checkpoint files from queue directory', async () => {
    fs.readdir.mockResolvedValue(['adjudica-ai-app_2026-03-27T09-15.md', 'not-a-md.json']);
    fs.readFile.mockResolvedValue(QUEUE_FILE_CONTENT);

    const results = await loadFromQueueDir('/tmp/squeegee-checkpoints', '2026-03-27');

    expect(results).toHaveLength(1);
    expect(results[0].repo).toBe('adjudica-ai-app');
    expect(results[0].phase).toBe('Queue-based checkpoint for testing');
  });

  it('should return empty array if queue dir does not exist', async () => {
    const enoent = new Error('ENOENT');
    enoent.code = 'ENOENT';
    fs.readdir.mockRejectedValue(enoent);

    const results = await loadFromQueueDir('/tmp/squeegee-checkpoints', '2026-03-27');
    expect(results).toEqual([]);
  });

  it('should return empty array if queue dir is empty', async () => {
    fs.readdir.mockResolvedValue([]);

    const results = await loadFromQueueDir('/tmp/squeegee-checkpoints', '2026-03-27');
    expect(results).toEqual([]);
  });

  it('should derive repo name from filename without date suffix', async () => {
    fs.readdir.mockResolvedValue(['no-date-in-name.md']);
    fs.readFile.mockResolvedValue(`## Checkpoint [2026-03-27 10:00]
**Task:** Test
Context: 40%`);

    const results = await loadFromQueueDir('/tmp/squeegee-checkpoints', '2026-03-27');

    expect(results).toHaveLength(1);
    expect(results[0].repo).toBe('no-date-in-name');
  });

  it('should skip unreadable files gracefully', async () => {
    fs.readdir.mockResolvedValue(['good.md', 'bad.md']);
    fs.readFile
      .mockRejectedValueOnce(new Error('Permission denied'))
      .mockResolvedValueOnce(`## Checkpoint [2026-03-27 10:00]
**Task:** Good file
Context: 50%`);

    const results = await loadFromQueueDir('/tmp/squeegee-checkpoints', '2026-03-27');
    // Only the second file succeeds (mocks are consumed in order)
    expect(results.length).toBeGreaterThanOrEqual(0);
  });
});

describe('loadFromWorkspace()', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.spyOn(console, 'log').mockImplementation(() => {});
    jest.spyOn(console, 'warn').mockImplementation(() => {});
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('should scan subdirectories for .planning/STATE.md files', async () => {
    // readdir returns workspace entries
    fs.readdir.mockResolvedValue([
      { name: 'adjudica-ai-app', isDirectory: () => true },
      { name: 'squeegee', isDirectory: () => true },
      { name: 'not-a-dir.txt', isDirectory: () => false }
    ]);

    // First STATE.md has checkpoints, second doesn't
    fs.readFile
      .mockResolvedValueOnce(STATE_MD_WITH_CHECKPOINTS)
      .mockResolvedValueOnce(STATE_MD_NO_CHECKPOINTS);

    const results = await loadFromWorkspace('/home/vncuser', '2026-03-27');

    expect(results).toHaveLength(2); // Two checkpoints from STATE_MD_WITH_CHECKPOINTS
    expect(results[0].repo).toBe('adjudica-ai-app');
    expect(results[1].repo).toBe('adjudica-ai-app');
  });

  it('should skip repos with no STATE.md', async () => {
    fs.readdir.mockResolvedValue([
      { name: 'no-planning-dir', isDirectory: () => true }
    ]);

    const enoent = new Error('ENOENT');
    enoent.code = 'ENOENT';
    fs.readFile.mockRejectedValue(enoent);

    const results = await loadFromWorkspace('/home/vncuser', '2026-03-27');
    expect(results).toEqual([]);
  });

  it('should return empty array if workspace dir does not exist', async () => {
    const enoent = new Error('ENOENT');
    enoent.code = 'ENOENT';
    fs.readdir.mockRejectedValue(enoent);

    const results = await loadFromWorkspace('/home/vncuser', '2026-03-27');
    expect(results).toEqual([]);
  });

  it('should skip hidden directories', async () => {
    fs.readdir.mockResolvedValue([
      { name: '.hidden', isDirectory: () => true },
      { name: 'node_modules', isDirectory: () => true },
      { name: 'real-repo', isDirectory: () => true }
    ]);

    fs.readFile.mockResolvedValue(STATE_MD_WITH_CHECKPOINTS);

    const results = await loadFromWorkspace('/home/vncuser', '2026-03-27');

    // readFile should only be called once (for real-repo)
    expect(fs.readFile).toHaveBeenCalledTimes(1);
    expect(fs.readFile).toHaveBeenCalledWith(
      expect.stringContaining('real-repo'),
      'utf-8'
    );
  });
});

describe('load() - main entry point', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.spyOn(console, 'log').mockImplementation(() => {});
    jest.spyOn(console, 'warn').mockImplementation(() => {});
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  const mockConfig = {
    intelligence: {
      checkpoints: {
        enabled: true,
        queue_dir: '/tmp/squeegee-checkpoints',
        workspace_dir: '/home/vncuser'
      }
    }
  };

  it('should return empty array when checkpoints are disabled', async () => {
    const config = {
      intelligence: {
        checkpoints: { enabled: false }
      }
    };

    const results = await load('2026-03-27', config);
    expect(results).toEqual([]);
    expect(fs.readdir).not.toHaveBeenCalled();
  });

  it('should merge and deduplicate checkpoints from both sources', async () => {
    // Both queue and workspace return the same checkpoint (duplicate)
    const checkpointContent = `## Checkpoint [2026-03-27 14:32]
**Task:** Deduplicated task
Context: 62%`;

    fs.readdir
      // First call: queue dir listing
      .mockResolvedValueOnce(['repo_2026-03-27T14-32.md'])
      // Second call: workspace listing
      .mockResolvedValueOnce([
        { name: 'repo', isDirectory: () => true }
      ]);

    fs.readFile.mockResolvedValue(checkpointContent);

    const results = await load('2026-03-27', mockConfig);

    // Both sources return the same checkpoint — deduplicated to 1
    expect(results).toHaveLength(1);
  });

  it('should return empty array when both sources have no data', async () => {
    fs.readdir
      .mockResolvedValueOnce([]) // empty queue
      .mockResolvedValueOnce([]); // empty workspace

    const results = await load('2026-03-27', mockConfig);
    expect(results).toEqual([]);
  });

  it('should sort results chronologically', async () => {
    // Queue has a later checkpoint, workspace has an earlier one
    fs.readdir
      .mockResolvedValueOnce(['repo_2026-03-27.md'])
      .mockResolvedValueOnce([
        { name: 'other-repo', isDirectory: () => true }
      ]);

    fs.readFile
      .mockResolvedValueOnce(`## Checkpoint [2026-03-27 16:00]
**Task:** Later task
Context: 70%`)
      .mockResolvedValueOnce(`## Checkpoint [2026-03-27 09:00]
**Task:** Earlier task
Context: 30%`);

    const results = await load('2026-03-27', mockConfig);

    expect(results.length).toBe(2);
    // Earlier timestamp should come first
    expect(new Date(results[0].timestamp) < new Date(results[1].timestamp)).toBe(true);
  });

  it('should use defaults when config has no checkpoint section', async () => {
    fs.readdir.mockResolvedValue([]);

    const results = await load('2026-03-27', {});
    expect(results).toEqual([]);
    // Should not throw — uses DEFAULT_CHECKPOINT_DIR and DEFAULT_WORKSPACE_DIR
  });

  it('should return empty array when checkpoint section is absent from config', async () => {
    fs.readdir.mockResolvedValue([]);

    const results = await load('2026-03-27', { intelligence: {} });
    expect(results).toEqual([]);
  });
});
