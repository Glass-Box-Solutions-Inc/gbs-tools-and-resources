/**
 * Unit tests for Portal Renderer
 */

const {
  CATEGORY_DISPLAY,
  STATUS_DISPLAY,
  buildContext,
  getNavSections,
} = require('../../src/portal/renderer');

describe('Portal Renderer', () => {
  describe('CATEGORY_DISPLAY', () => {
    test('has entries for all categories', () => {
      expect(CATEGORY_DISPLAY['adjudica-platform']).toBeDefined();
      expect(CATEGORY_DISPLAY['infrastructure']).toBeDefined();
      expect(CATEGORY_DISPLAY['internal-tools']).toBeDefined();
      expect(CATEGORY_DISPLAY['research-oss']).toBeDefined();
    });

    test('each category has name, color, and icon', () => {
      for (const [key, value] of Object.entries(CATEGORY_DISPLAY)) {
        expect(value.name).toBeTruthy();
        expect(value.color).toMatch(/^#[a-f0-9]{6}$/);
        expect(value.icon).toBeTruthy();
      }
    });
  });

  describe('STATUS_DISPLAY', () => {
    test('has entries for all statuses', () => {
      expect(STATUS_DISPLAY.active).toBeDefined();
      expect(STATUS_DISPLAY.deployed).toBeDefined();
      expect(STATUS_DISPLAY.planning).toBeDefined();
      expect(STATUS_DISPLAY.archived).toBeDefined();
    });

    test('each status has label, color, bg, border', () => {
      for (const [key, value] of Object.entries(STATUS_DISPLAY)) {
        expect(value.label).toBeTruthy();
        expect(value.color).toContain('text-');
        expect(value.bg).toContain('bg-');
        expect(value.border).toContain('border-');
      }
    });
  });

  describe('buildContext', () => {
    const portalData = {
      projects: [
        { name: 'proj-a', status: 'active', category: 'infrastructure', health_score: 80, commit_count_30d: 50, contributors: ['alice', 'bob'], tech_stack: ['React'] },
        { name: 'proj-b', status: 'deployed', category: 'adjudica-platform', health_score: 90, commit_count_30d: 30, contributors: ['alice'], tech_stack: ['Node'] },
      ],
      developers: [{ name: 'alice', total_commits: 100, active_projects: ['proj-a', 'proj-b'] }],
      recent_commits: { 'proj-a': [{ sha: 'abc', message: 'test', author: 'alice', timestamp: new Date().toISOString(), repo_name: 'proj-a' }] },
      sprints: {},
      heatmap: [{ developer_name: 'alice', project_name: 'proj-a', commit_count: 80, expertise_level: 'proficient', recent_commits: 10 }],
      activity_feed: [],
      generated_at: new Date().toISOString(),
      diagrams: {},
      project_explanations: {},
      user_journeys: {},
      all_commits_365d: [{ sha: 'abc', message: 'test', author: 'alice', timestamp: new Date().toISOString(), repo_name: 'proj-a' }],
    };

    const repoConfigs = [
      { name: 'proj-a', category: 'infrastructure' },
      { name: 'proj-b', category: 'adjudica-platform' },
    ];

    test('computes total stats', () => {
      const ctx = buildContext(portalData, repoConfigs);
      expect(ctx.total_projects).toBe(2);
      expect(ctx.total_active).toBe(1);
      expect(ctx.total_deployed).toBe(1);
      expect(ctx.total_commits_30d).toBe(80);
      expect(ctx.total_contributors).toBe(2);
      expect(ctx.avg_health).toBe(85);
    });

    test('builds projects_by_category', () => {
      const ctx = buildContext(portalData, repoConfigs);
      expect(ctx.projects_by_category['infrastructure']).toHaveLength(1);
      expect(ctx.projects_by_category['adjudica-platform']).toHaveLength(1);
    });

    test('builds config_lookup', () => {
      const ctx = buildContext(portalData, repoConfigs);
      expect(ctx.config_lookup['proj-a']).toBeDefined();
      expect(ctx.config_lookup['proj-b']).toBeDefined();
    });

    test('builds commits_by_cell for heatmap drill-down', () => {
      const ctx = buildContext(portalData, repoConfigs);
      expect(ctx.commits_by_cell['alice::proj-a']).toBeDefined();
      expect(ctx.commits_by_cell['alice::proj-a']).toHaveLength(1);
    });

    test('includes nav_sections', () => {
      const ctx = buildContext(portalData, repoConfigs);
      expect(ctx.nav_sections).toBeDefined();
      expect(ctx.nav_sections.length).toBeGreaterThan(0);
    });
  });

  describe('getNavSections', () => {
    test('returns correct section structure', () => {
      const sections = getNavSections();
      expect(sections.length).toBe(7);

      const titles = sections.map(s => s.title);
      expect(titles).toContain('Overview');
      expect(titles).toContain('Projects');
      expect(titles).toContain('Team');
      expect(titles).toContain('Architecture');
      expect(titles).toContain('Intelligence');
      expect(titles).toContain('Docs');
      expect(titles).toContain('Admin');
    });

    test('each section has items with name and href', () => {
      const sections = getNavSections();
      for (const section of sections) {
        expect(section.items.length).toBeGreaterThan(0);
        for (const item of section.items) {
          expect(item.name).toBeTruthy();
          expect(item.href).toBeTruthy();
        }
      }
    });
  });
});
