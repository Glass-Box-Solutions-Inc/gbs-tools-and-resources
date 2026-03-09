/**
 * Unit tests for Portal GitHub Client
 */

const {
  computeHealthScore,
  buildDevelopers,
  buildHeatmap,
} = require('../../src/portal/github-client');

describe('Portal GitHub Client', () => {
  describe('computeHealthScore', () => {
    test('deployed project gets base score of 85', () => {
      const score = computeHealthScore('deployed', 1, false, 0, 0);
      expect(score).toBe(85);
    });

    test('active project gets base score of 70', () => {
      const score = computeHealthScore('active', 2, false, 0, 0);
      expect(score).toBe(70);
    });

    test('activity bonus for 50+ commits', () => {
      const score = computeHealthScore('active', 2, false, 51, 0);
      expect(score).toBe(80); // 70 + 10
    });

    test('activity bonus for 20+ commits', () => {
      const score = computeHealthScore('active', 2, false, 25, 0);
      expect(score).toBe(77); // 70 + 7
    });

    test('team bonus for 3+ contributors', () => {
      const score = computeHealthScore('active', 2, false, 0, 3);
      expect(score).toBe(75); // 70 + 5
    });

    test('production URL bonus', () => {
      const score = computeHealthScore('active', 2, true, 0, 0);
      expect(score).toBe(73); // 70 + 3
    });

    test('max score is 100', () => {
      const score = computeHealthScore('deployed', 1, true, 100, 5);
      expect(score).toBe(100);
    });

    test('planning project gets low base score', () => {
      const score = computeHealthScore('planning', 4, false, 0, 0);
      expect(score).toBe(40);
    });
  });

  describe('buildDevelopers', () => {
    test('builds sorted developer list from contributions', () => {
      const contributions = {
        'Alice': { 'repo-a': 100, 'repo-b': 50 },
        'Bob': { 'repo-a': 200 },
        'Charlie': { 'repo-c': 10 },
      };

      const devs = buildDevelopers(contributions);
      expect(devs).toHaveLength(3);

      // Bob has most commits, should be first
      expect(devs[0].name).toBe('Bob');
      expect(devs[0].total_commits).toBe(200);
      expect(devs[0].active_projects).toEqual(['repo-a']);

      // Alice second
      expect(devs[1].name).toBe('Alice');
      expect(devs[1].total_commits).toBe(150);
      expect(devs[1].active_projects).toEqual(['repo-a', 'repo-b']);

      // Charlie last
      expect(devs[2].name).toBe('Charlie');
      expect(devs[2].total_commits).toBe(10);
    });

    test('returns empty array for empty input', () => {
      expect(buildDevelopers({})).toEqual([]);
    });
  });

  describe('buildHeatmap', () => {
    test('builds heatmap cells with expertise and recent activity', () => {
      const allTime = {
        'Alice': { 'repo-a': 250, 'repo-b': 30 },
      };
      const recent = {
        'Alice': { 'repo-a': 10 },
      };

      const cells = buildHeatmap(allTime, recent);
      expect(cells).toHaveLength(2);

      const repoA = cells.find(c => c.project_name === 'repo-a');
      expect(repoA.commit_count).toBe(250);
      expect(repoA.expertise_level).toBe('expert');
      expect(repoA.recent_commits).toBe(10);

      const repoB = cells.find(c => c.project_name === 'repo-b');
      expect(repoB.commit_count).toBe(30);
      expect(repoB.recent_commits).toBe(0);
    });
  });
});
