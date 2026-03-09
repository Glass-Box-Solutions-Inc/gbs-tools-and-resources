/**
 * Unit tests for Portal Project Cache
 */

const { deserializeAll } = require('../../src/portal/project-cache');

describe('Portal Project Cache', () => {
  describe('deserializeAll', () => {
    test('extracts projects, commits, activity from cache', () => {
      const cache = {
        generated_at: '2026-03-08T00:00:00Z',
        projects: {
          'proj-a': {
            cached_at: '2026-03-08T00:00:00Z',
            project: { name: 'proj-a', status: 'active' },
            commits: [{ sha: 'abc', message: 'fix', repo_name: 'proj-a' }],
            commits_365d: [
              { sha: 'abc', message: 'fix', repo_name: 'proj-a' },
              { sha: 'def', message: 'feat', repo_name: 'proj-a' },
            ],
            activity: [{ event_type: 'commit', title: 'fix', repo_name: 'proj-a' }],
          },
          'proj-b': {
            cached_at: '2026-03-08T00:00:00Z',
            project: { name: 'proj-b', status: 'deployed' },
            commits: [],
            commits_365d: [{ sha: 'ghi', message: 'deploy', repo_name: 'proj-b' }],
            activity: [],
          },
        },
      };

      const result = deserializeAll(cache);
      expect(result.projects).toHaveLength(2);
      expect(result.recentCommits['proj-a']).toHaveLength(1);
      expect(result.recentCommits['proj-b']).toHaveLength(0);
      expect(result.allCommits365d).toHaveLength(3);
      expect(result.activity).toHaveLength(1);
    });

    test('handles empty cache', () => {
      const result = deserializeAll({ projects: {} });
      expect(result.projects).toEqual([]);
      expect(result.recentCommits).toEqual({});
      expect(result.allCommits365d).toEqual([]);
      expect(result.activity).toEqual([]);
    });

    test('handles cache with missing fields', () => {
      const cache = {
        projects: {
          'proj-a': {
            project: { name: 'proj-a' },
            // Missing commits, commits_365d, activity
          },
        },
      };

      const result = deserializeAll(cache);
      expect(result.projects).toHaveLength(1);
    });
  });
});
