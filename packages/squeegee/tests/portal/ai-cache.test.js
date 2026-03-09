/**
 * Unit tests for Portal AI Cache
 */

const fs = require('fs').promises;
const path = require('path');
const {
  loadCache,
  saveCache,
  getCachedProject,
  hasChanged,
  updateCacheEntry,
  loadContentFromCache,
  CACHE_FILE,
} = require('../../src/portal/ai-cache');

// Use temp dir for test cache
const TEST_CACHE_FILE = '/tmp/test-portal-ai-cache.json';

// Override CACHE_FILE for tests
jest.mock('../../src/portal/ai-cache', () => {
  const original = jest.requireActual('../../src/portal/ai-cache');
  return {
    ...original,
    CACHE_FILE: '/tmp/test-portal-ai-cache.json',
  };
});

describe('Portal AI Cache', () => {
  beforeEach(async () => {
    try { await fs.unlink(TEST_CACHE_FILE); } catch {}
  });

  describe('hasChanged', () => {
    test('returns true for uncached project', () => {
      const cache = { version: 1, projects: {} };
      expect(hasChanged(cache, 'new-project', 'abc123')).toBe(true);
    });

    test('returns false for same hash', () => {
      const cache = {
        version: 1,
        projects: { 'test-project': { content_hash: 'abc123' } },
      };
      expect(hasChanged(cache, 'test-project', 'abc123')).toBe(false);
    });

    test('returns true for different hash', () => {
      const cache = {
        version: 1,
        projects: { 'test-project': { content_hash: 'abc123' } },
      };
      expect(hasChanged(cache, 'test-project', 'def456')).toBe(true);
    });
  });

  describe('getCachedProject', () => {
    test('returns null for missing project', () => {
      const cache = { version: 1, projects: {} };
      expect(getCachedProject(cache, 'missing')).toBeNull();
    });

    test('returns cached entry for existing project', () => {
      const entry = { content_hash: 'abc', diagram: { mermaid_code: 'graph TD' } };
      const cache = { version: 1, projects: { 'test': entry } };
      expect(getCachedProject(cache, 'test')).toEqual(entry);
    });
  });

  describe('updateCacheEntry', () => {
    test('adds new entry', () => {
      const cache = { version: 1, projects: {} };
      updateCacheEntry(cache, 'test', 'hash123', {
        diagram: { mermaid_code: 'graph TD', explanation: { technical: 'T', non_technical: 'NT' } },
        explanation: { technical: 'T2', non_technical: 'NT2' },
        user_journey: '<p>Step 1</p>',
      });

      expect(cache.projects.test).toBeDefined();
      expect(cache.projects.test.content_hash).toBe('hash123');
      expect(cache.projects.test.diagram.mermaid_code).toBe('graph TD');
      expect(cache.projects.test.explanation.technical).toBe('T2');
    });

    test('overwrites existing entry', () => {
      const cache = {
        version: 1,
        projects: { 'test': { content_hash: 'old', diagram: null } },
      };
      updateCacheEntry(cache, 'test', 'new', { diagram: { mermaid_code: 'flowchart LR' } });
      expect(cache.projects.test.content_hash).toBe('new');
    });
  });

  describe('loadContentFromCache', () => {
    test('extracts diagrams, explanations, and journeys', () => {
      const cache = {
        version: 1,
        projects: {
          'project-a': {
            diagram: {
              mermaid_code: 'graph TD',
              explanation: { technical: 'T', non_technical: 'NT' },
            },
            data_flow_diagram: {
              mermaid_code: 'flowchart LR',
              explanation: { technical: 'DF-T', non_technical: 'DF-NT' },
            },
            sequence_diagram: null,
            explanation: { technical: 'Proj-T', non_technical: 'Proj-NT' },
            user_journey: '<p>Step 1</p>',
          },
        },
      };

      const content = loadContentFromCache(cache);

      expect(content.diagrams['project-a']).toBeDefined();
      expect(content.diagrams['project-a'].mermaid_code).toBe('graph TD');
      expect(content.diagrams['project-a'].data_flow.mermaid_code).toBe('flowchart LR');
      expect(content.project_explanations['project-a'].technical).toBe('Proj-T');
      expect(content.user_journeys['project-a']).toBe('<p>Step 1</p>');
    });

    test('handles empty cache', () => {
      const content = loadContentFromCache({ version: 1, projects: {} });
      expect(content.diagrams).toEqual({});
      expect(content.project_explanations).toEqual({});
      expect(content.user_journeys).toEqual({});
    });
  });
});
