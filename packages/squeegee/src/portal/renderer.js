/**
 * Portal Renderer
 *
 * Nunjucks template rendering + custom filters for the HTML portal.
 * Ported from glass-box-hub/squeegee/renderer.py (552 lines).
 *
 * @file src/portal/renderer.js
 * @module portal/renderer
 */

'use strict';

const nunjucks = require('nunjucks');
const fs = require('fs').promises;
const fsSync = require('fs');
const path = require('path');

const TEMPLATES_DIR = path.join(__dirname, 'templates');
const STATIC_DIR = path.join(__dirname, 'static');
const DEFAULT_OUTPUT_DIR = '/tmp/portal-output';

// ─── Display Config ──────────────────────────────────────────────────────────

const CATEGORY_DISPLAY = {
  'adjudica-platform': { name: 'Adjudica Platform', color: '#3b82f6', icon: 'scales' },
  'meruscase-integration': { name: 'MerusCase Integration', color: '#8b5cf6', icon: 'link' },
  'legal-research': { name: 'Legal Research', color: '#06b6d4', icon: 'search' },
  'platform-services': { name: 'Platform Services', color: '#10b981', icon: 'server' },
  infrastructure: { name: 'Infrastructure', color: '#f59e0b', icon: 'cog' },
  'research-oss': { name: 'Research & OSS', color: '#ec4899', icon: 'flask' },
  'internal-tools': { name: 'Internal Tools', color: '#6366f1', icon: 'wrench' },
};

const STATUS_DISPLAY = {
  active: { label: 'Active', color: 'text-green-400', bg: 'bg-green-400/10', border: 'border-green-400/30' },
  deployed: { label: 'Deployed', color: 'text-cyan-400', bg: 'bg-cyan-400/10', border: 'border-cyan-400/30' },
  planning: { label: 'Planning', color: 'text-yellow-400', bg: 'bg-yellow-400/10', border: 'border-yellow-400/30' },
  maintenance: { label: 'Maintenance', color: 'text-orange-400', bg: 'bg-orange-400/10', border: 'border-orange-400/30' },
  deprecated: { label: 'Deprecated', color: 'text-red-400', bg: 'bg-red-400/10', border: 'border-red-400/30' },
  archived: { label: 'Archived', color: 'text-gray-400', bg: 'bg-gray-400/10', border: 'border-gray-400/30' },
};

// ─── Nunjucks Environment ────────────────────────────────────────────────────

let nunjucksEnv = null;

/**
 * Get or create the Nunjucks environment with custom filters
 * @returns {nunjucks.Environment}
 */
function getEnv() {
  if (nunjucksEnv) return nunjucksEnv;

  nunjucksEnv = new nunjucks.Environment(
    new nunjucks.FileSystemLoader(TEMPLATES_DIR, { noCache: true }),
    { autoescape: true }
  );

  // ─── Custom Filters ────────────────────────────────────────────────────

  nunjucksEnv.addFilter('timeago', (dt) => {
    if (!dt) return 'Never';
    const now = Date.now();
    const then = new Date(dt).getTime();
    const diffMs = now - then;
    const diffMin = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);
    const diffWeeks = Math.floor(diffDays / 7);
    const diffMonths = Math.floor(diffDays / 30);

    if (diffMin < 1) return 'Just now';
    if (diffMin < 60) return `${diffMin}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    if (diffWeeks < 5) return `${diffWeeks}w ago`;
    return `${diffMonths}mo ago`;
  });

  nunjucksEnv.addFilter('health_color', (score) => {
    if (score >= 85) return 'text-green-400';
    if (score >= 70) return 'text-cyan-400';
    if (score >= 50) return 'text-yellow-400';
    if (score >= 35) return 'text-orange-400';
    return 'text-red-400';
  });

  nunjucksEnv.addFilter('health_label', (score) => {
    if (score >= 85) return 'Deployed & Thriving';
    if (score >= 70) return 'Actively Developed';
    if (score >= 50) return 'Steady';
    if (score >= 35) return 'In Planning';
    return 'Needs Attention';
  });

  nunjucksEnv.addFilter('status_badge', (status) => {
    const display = STATUS_DISPLAY[status] || STATUS_DISPLAY.active;
    return new nunjucks.runtime.SafeString(
      `<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${display.bg} ${display.color} ${display.border} border">${display.label}</span>`
    );
  });

  nunjucksEnv.addFilter('category_color', (category) => {
    return CATEGORY_DISPLAY[category]?.color || '#6b7280';
  });

  nunjucksEnv.addFilter('category_name', (category) => {
    return CATEGORY_DISPLAY[category]?.name || category || 'Unknown';
  });

  nunjucksEnv.addFilter('expertise_color', (level) => {
    const colors = {
      none: 'bg-gray-700',
      familiar: 'bg-blue-900',
      proficient: 'bg-blue-700',
      expert: 'bg-blue-500',
      master: 'bg-blue-300',
    };
    return colors[level] || 'bg-gray-700';
  });

  nunjucksEnv.addFilter('heat_color_style', (count) => {
    if (!count || count <= 0) return 'background-color: rgba(255,255,255,0.03);';
    if (count <= 5) return 'background-color: rgba(0, 255, 135, 0.15);';
    if (count <= 15) return 'background-color: rgba(0, 255, 135, 0.30);';
    if (count <= 50) return 'background-color: rgba(0, 255, 135, 0.50);';
    if (count <= 100) return 'background-color: rgba(0, 255, 135, 0.70);';
    if (count <= 300) return 'background-color: rgba(0, 255, 135, 0.85);';
    return 'background-color: rgba(0, 255, 135, 1.0);';
  });

  nunjucksEnv.addFilter('truncate_message', (message, length) => {
    const maxLen = length || 60;
    if (!message) return '';
    return message.length > maxLen ? message.slice(0, maxLen) + '...' : message;
  });

  nunjucksEnv.addFilter('format_date', (dt, fmt) => {
    if (!dt) return 'N/A';
    const d = new Date(dt);
    if (isNaN(d.getTime())) return 'N/A';
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    return `${months[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}`;
  });

  nunjucksEnv.addFilter('priority_display', (priority) => {
    const colors = { 1: 'text-red-400', 2: 'text-orange-400', 3: 'text-yellow-400', 4: 'text-blue-400', 5: 'text-gray-400' };
    const labels = { 1: 'Critical', 2: 'High', 3: 'Medium', 4: 'Low', 5: 'Minimal' };
    const color = colors[priority] || 'text-gray-400';
    const label = labels[priority] || `P${priority}`;
    return new nunjucks.runtime.SafeString(`<span class="${color}">${label}</span>`);
  });

  // JSON filter for safe embedding in script tags
  nunjucksEnv.addFilter('tojson', (obj) => {
    return new nunjucks.runtime.SafeString(JSON.stringify(obj || {}));
  });

  // Safe HTML (no escaping)
  nunjucksEnv.addFilter('safe', (str) => {
    return new nunjucks.runtime.SafeString(str || '');
  });

  return nunjucksEnv;
}

/**
 * Build the full template context from portal data
 * @param {PortalData} portalData
 * @param {Array} repoConfigs
 * @returns {Object} - Template context
 */
function buildContext(portalData, repoConfigs) {
  // Build config lookup for template use
  const configLookup = {};
  for (const rc of repoConfigs) {
    configLookup[rc.name] = rc;
  }

  // Category stats
  const categoryStats = {};
  for (const project of portalData.projects || []) {
    const cat = project.category || 'research-oss';
    if (!categoryStats[cat]) categoryStats[cat] = { count: 0, deployed: 0, active: 0 };
    categoryStats[cat].count++;
    if (project.status === 'deployed') categoryStats[cat].deployed++;
    if (project.status === 'active') categoryStats[cat].active++;
  }

  // Build commits_by_cell for heatmap drill-down
  const commitsByCell = {};
  for (const commit of portalData.all_commits_365d || []) {
    const key = `${commit.author}::${commit.repo_name}`;
    if (!commitsByCell[key]) commitsByCell[key] = [];
    commitsByCell[key].push({
      sha: commit.sha?.slice(0, 7),
      message: commit.message,
      timestamp: commit.timestamp,
      url: commit.url,
    });
  }

  // Group projects by category
  const projectsByCategory = {};
  for (const project of portalData.projects || []) {
    const cat = project.category || 'research-oss';
    if (!projectsByCategory[cat]) projectsByCategory[cat] = [];
    projectsByCategory[cat].push(project);
  }

  // Unique developer names from heatmap for table header
  const projectNames = [...new Set((portalData.heatmap || []).map((c) => c.project_name))].sort();
  const developerNames = [...new Set((portalData.heatmap || []).map((c) => c.developer_name))].sort();

  // Heatmap lookup
  const heatmapLookup = {};
  for (const cell of portalData.heatmap || []) {
    const key = `${cell.developer_name}::${cell.project_name}`;
    heatmapLookup[key] = cell;
  }

  // Average health score
  const projects = portalData.projects || [];
  const avgHealth = projects.length > 0
    ? Math.round(projects.reduce((s, p) => s + (p.health_score || 0), 0) / projects.length)
    : 0;

  // Total unique contributors
  const allContributors = new Set();
  for (const project of projects) {
    for (const c of project.contributors || []) {
      allContributors.add(c);
    }
  }

  return {
    // Portal data
    projects,
    developers: portalData.developers || [],
    recent_commits: portalData.recent_commits || {},
    sprints: portalData.sprints || {},
    heatmap: portalData.heatmap || [],
    activity_feed: (portalData.activity_feed || []).slice(0, 50),
    diagrams: portalData.diagrams || {},
    project_explanations: portalData.project_explanations || {},
    user_journeys: portalData.user_journeys || {},
    all_commits_365d: portalData.all_commits_365d || [],

    // Computed data
    config_lookup: configLookup,
    category_stats: categoryStats,
    category_display: CATEGORY_DISPLAY,
    status_display: STATUS_DISPLAY,
    commits_by_cell: commitsByCell,
    projects_by_category: projectsByCategory,
    project_names: projectNames,
    developer_names: developerNames,
    heatmap_lookup: heatmapLookup,

    // Summary stats
    total_projects: projects.length,
    total_active: projects.filter((p) => p.status === 'active').length,
    total_deployed: projects.filter((p) => p.status === 'deployed').length,
    total_commits_30d: projects.reduce((s, p) => s + (p.commit_count_30d || 0), 0),
    total_contributors: allContributors.size,
    avg_health: avgHealth,
    generated_at: portalData.generated_at || new Date().toISOString(),

    // Navigation structure
    nav_sections: getNavSections(),
  };
}

/**
 * Get navigation sections for sidebar
 * @returns {Array}
 */
function getNavSections() {
  return [
    {
      title: 'Overview',
      items: [
        { name: 'Dashboard', href: 'index.html', icon: 'home' },
      ],
    },
    {
      title: 'Projects',
      items: [
        { name: 'All Projects', href: 'projects.html', icon: 'grid' },
        { name: 'Health Report', href: 'health.html', icon: 'activity' },
      ],
    },
    {
      title: 'Team',
      items: [
        { name: 'Heatmap', href: 'team.html', icon: 'users' },
        { name: 'Search', href: 'search.html', icon: 'search' },
        { name: 'Activity', href: 'activity.html', icon: 'clock' },
      ],
    },
    {
      title: 'Architecture',
      items: [
        { name: 'Diagrams', href: 'diagrams.html', icon: 'code' },
        { name: 'Dependencies', href: 'dependencies.html', icon: 'git-branch' },
        { name: 'Tech Stack', href: 'stack.html', icon: 'layers' },
      ],
    },
    {
      title: 'Intelligence',
      items: [
        { name: 'Daily Briefing', href: 'intelligence.html', icon: 'zap' },
        { name: 'Audit Reports', href: 'audits.html', icon: 'shield' },
        { name: 'Trends', href: 'trends.html', icon: 'trending-up' },
      ],
    },
    {
      title: 'Docs',
      items: [
        { name: 'Browser', href: 'docs.html', icon: 'book' },
        { name: 'Agents & Tools', href: 'agents.html', icon: 'cpu' },
      ],
    },
    {
      title: 'Admin',
      items: [
        { name: 'Settings', href: 'admin.html', icon: 'settings' },
      ],
    },
  ];
}

/**
 * Render a single page
 * @param {string} template - Template filename
 * @param {Object} context - Template context
 * @param {string} outputPath - Full output file path
 */
async function renderPage(template, context, outputPath) {
  const env = getEnv();
  try {
    const html = env.render(template, context);
    await fs.mkdir(path.dirname(outputPath), { recursive: true });
    await fs.writeFile(outputPath, html, 'utf-8');
  } catch (err) {
    console.error(`Portal: Failed to render ${template}: ${err.message}`);
  }
}

/**
 * Render the full portal
 * @param {PortalData} portalData
 * @param {Array} repoConfigs
 * @param {string} [outputDir] - Output directory
 * @returns {Promise<Object>} - { pages_rendered, output_dir }
 */
async function renderPortal(portalData, repoConfigs, outputDir) {
  const outDir = outputDir || DEFAULT_OUTPUT_DIR;
  const context = buildContext(portalData, repoConfigs);
  let pagesRendered = 0;

  // Aggregate pages
  const aggregatePages = [
    'index.html',
    'projects.html',
    'health.html',
    'team.html',
    'search.html',
    'activity.html',
    'diagrams.html',
    'dependencies.html',
    'stack.html',
    'intelligence.html',
    'audits.html',
    'trends.html',
    'docs.html',
    'agents.html',
    'admin.html',
  ];

  for (const page of aggregatePages) {
    const templatePath = path.join(TEMPLATES_DIR, page);
    if (fsSync.existsSync(templatePath)) {
      await renderPage(page, { ...context, current_page: page }, path.join(outDir, page));
      pagesRendered++;
    }
  }

  // Per-project pages
  for (const project of portalData.projects || []) {
    const projectContext = {
      ...context,
      project,
      current_page: `project/${project.name}.html`,
      breadcrumbs: [
        { name: 'Dashboard', href: '../index.html' },
        { name: 'Projects', href: '../projects.html' },
        { name: project.name, href: null },
      ],
      project_commits: context.recent_commits[project.name] || [],
      project_diagram: context.diagrams[project.name] || null,
      project_explanation: context.project_explanations[project.name] || null,
      user_journey: context.user_journeys[project.name] || null,
    };

    await renderPage(
      'project.html',
      projectContext,
      path.join(outDir, 'project', `${project.name}.html`)
    );
    pagesRendered++;
  }

  // Copy static assets
  await copyStaticAssets(outDir);

  console.log(`Portal: Rendered ${pagesRendered} pages to ${outDir}`);
  return { pages_rendered: pagesRendered, output_dir: outDir };
}

/**
 * Copy static assets (CSS, JS) to output
 * @param {string} outputDir
 */
async function copyStaticAssets(outputDir) {
  const destStatic = path.join(outputDir, 'static');
  await fs.mkdir(destStatic, { recursive: true });

  // Recursively copy static directory
  await copyDir(STATIC_DIR, destStatic);
}

/**
 * Recursively copy a directory
 * @param {string} src
 * @param {string} dest
 */
async function copyDir(src, dest) {
  if (!fsSync.existsSync(src)) return;

  await fs.mkdir(dest, { recursive: true });
  const entries = await fs.readdir(src, { withFileTypes: true });

  for (const entry of entries) {
    const srcPath = path.join(src, entry.name);
    const destPath = path.join(dest, entry.name);

    if (entry.isDirectory()) {
      await copyDir(srcPath, destPath);
    } else {
      await fs.copyFile(srcPath, destPath);
    }
  }
}

module.exports = {
  CATEGORY_DISPLAY,
  STATUS_DISPLAY,
  getEnv,
  buildContext,
  getNavSections,
  renderPage,
  renderPortal,
  copyStaticAssets,
};
