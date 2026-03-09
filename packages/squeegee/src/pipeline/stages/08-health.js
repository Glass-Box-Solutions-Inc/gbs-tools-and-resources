/**
 * Stage 08: Health Scoring
 *
 * Discriminating scores that produce meaningful spread (not all 70-74%).
 * Factors: section presence, git freshness, link validation, doc completeness.
 *
 * @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
 */

const fs = require('fs').promises;
const path = require('path');
const { log, fileExists, ensureDir, readFileSafe, readJsonSafe, writeJson } = require('../utils');
const { resolveProjectPath } = require('../config');
const { timestamp } = require('../formatters/markdown');

async function run(config, discovery) {
  log('Stage 8: Calculating health scores...', 'info');

  const projectScores = {};

  for (const project of config.projects) {
    const projectPath = resolveProjectPath(config, project.path);
    if (!(await fileExists(projectPath))) continue;

    const score = await scoreProject(projectPath, project, config, discovery);
    projectScores[project.name] = score;
  }

  // Load existing history for trend comparison
  const historyPath = path.join(config.workspace, 'docs-portal', 'health-history.json');
  const history = await readJsonSafe(historyPath, { runs: [] });

  await generateReport(projectScores, config, discovery, history);

  // Save scores to history after report generation
  await saveHealthHistory(projectScores, historyPath, history);

  const avgScore = Object.values(projectScores).reduce((s, p) => s + p.overall, 0) / Math.max(Object.keys(projectScores).length, 1);
  log(`Health scores calculated. Average: ${Math.round(avgScore)}%`, 'success');

  return projectScores;
}

async function scoreProject(projectPath, project, config, discovery) {
  const scores = {
    // Documentation presence (0-100): do the required files exist?
    presence: await scorePresence(projectPath),
    // Content quality (0-100): are sections populated, not just templates?
    quality: await scoreQuality(projectPath),
    // Git freshness (0-100): how recent is activity?
    freshness: await scoreFreshness(projectPath, config),
    // Structural completeness (0-100): headings, code blocks, links
    structure: await scoreStructure(projectPath, discovery),
    // Cross-references (0-100): does it link to other docs?
    crossRefs: await scoreCrossRefs(projectPath),
  };

  // Weighted overall score
  scores.overall = Math.round(
    scores.presence * 0.30 +
    scores.quality * 0.25 +
    scores.freshness * 0.20 +
    scores.structure * 0.15 +
    scores.crossRefs * 0.10
  );

  scores.grade = getGrade(scores.overall);

  return scores;
}

/**
 * Score based on which documentation files exist.
 * Maximum discrimination: 0 for empty projects, 100 for fully documented.
 */
async function scorePresence(projectPath) {
  const files = [
    { path: 'CLAUDE.md', weight: 30 },
    { path: '.planning/STATE.md', weight: 20 },
    { path: 'PLANS_APPROVED.md', weight: 10 },
    { path: 'PROGRAMMING_PRACTICES.md', weight: 10 },
    { path: 'README.md', weight: 10 },
    { path: 'CHANGELOG.md', weight: 5 },
    { path: '.planning/ROADMAP.md', weight: 5 },
    { path: '.planning/ISSUES.md', weight: 5 },
    { path: 'package.json', weight: 5 }, // Has project manifest
  ];

  let score = 0;
  for (const file of files) {
    if (await fileExists(path.join(projectPath, file.path))) {
      score += file.weight;
    }
  }

  return score;
}

/**
 * Score content quality — penalize template/placeholder content.
 */
async function scoreQuality(projectPath) {
  let score = 0;
  let checks = 0;

  const claudeMd = await readFileSafe(path.join(projectPath, 'CLAUDE.md'));
  if (claudeMd) {
    checks++;
    const lines = claudeMd.split('\n').length;
    const hasRealContent = !claudeMd.includes('*Not detected*') && !claudeMd.includes('[Define]');
    const hasTechStack = /## (?:Tech Stack|Commands|Architecture)/i.test(claudeMd);
    const hasCommands = /```/.test(claudeMd);

    if (lines >= 80 && hasRealContent && hasTechStack && hasCommands) score += 100;
    else if (lines >= 40 && hasTechStack) score += 70;
    else if (lines >= 20) score += 40;
    else score += 20;
  }

  const stateMd = await readFileSafe(path.join(projectPath, '.planning', 'STATE.md'));
  if (stateMd) {
    checks++;
    const hasCurrentFocus = /## Current Focus/.test(stateMd) && !stateMd.includes('awaiting instructions');
    const hasProgress = /## Progress/.test(stateMd) && !stateMd.includes('*None*\n\n### In Progress\n*None*');
    const hasActivity = /## Recent Activity/.test(stateMd) && !stateMd.includes('GSD structure created by Squeegee\n');

    if (hasCurrentFocus && hasProgress && hasActivity) score += 100;
    else if (hasActivity) score += 60;
    else score += 30;
  }

  const practicesMd = await readFileSafe(path.join(projectPath, 'PROGRAMMING_PRACTICES.md'));
  if (practicesMd) {
    checks++;
    const hasStack = !practicesMd.includes('*Not detected*');
    const hasPatterns = !practicesMd.includes('*No patterns detected*');

    if (hasStack && hasPatterns) score += 100;
    else if (hasStack) score += 60;
    else score += 30;
  }

  return checks > 0 ? Math.round(score / checks) : 0;
}

/**
 * Score based on git commit freshness.
 */
async function scoreFreshness(projectPath, config) {
  try {
    const { execSync } = require('child_process');
    const lastCommitDate = execSync(
      `git log -1 --format=%aI`,
      { cwd: projectPath, encoding: 'utf-8', stdio: ['pipe', 'pipe', 'ignore'] }
    ).trim();

    if (!lastCommitDate) return 0;

    const daysSince = (Date.now() - new Date(lastCommitDate).getTime()) / (1000 * 60 * 60 * 24);

    if (daysSince < 7) return 100;
    if (daysSince < 14) return 90;
    if (daysSince < 30) return 75;
    if (daysSince < 60) return 50;
    if (daysSince < 90) return 30;
    if (daysSince < 180) return 15;
    return 5;
  } catch {
    return 0;
  }
}

/**
 * Score structural quality of markdown files.
 */
async function scoreStructure(projectPath, discovery) {
  const claudeMd = await readFileSafe(path.join(projectPath, 'CLAUDE.md'));
  if (!claudeMd) return 0;

  let score = 0;
  const lines = claudeMd.split('\n');
  const headings = lines.filter(l => /^#{1,6}\s/.test(l));
  const codeBlocks = claudeMd.match(/```[\s\S]*?```/g) || [];
  const tables = claudeMd.match(/^\|.+\|$/gm) || [];

  // Heading hierarchy
  if (headings.length >= 3 && headings.length <= 20) score += 30;
  else if (headings.length > 0) score += 15;

  // Has code examples
  if (codeBlocks.length >= 2) score += 25;
  else if (codeBlocks.length > 0) score += 15;

  // Has tables (structured info)
  if (tables.length > 0) score += 20;

  // Consistent formatting (no skipped heading levels)
  const levels = headings.map(h => h.match(/^#+/)[0].length);
  let skips = 0;
  for (let i = 1; i < levels.length; i++) {
    if (levels[i] - levels[i - 1] > 1) skips++;
  }
  if (skips === 0) score += 15;
  else if (skips <= 2) score += 5;

  // No bare URLs
  const bareUrls = claudeMd.match(/(?<![(\[])https?:\/\/[^\s)>\]]+/g) || [];
  if (bareUrls.length <= 2) score += 10;

  return Math.min(100, score);
}

/**
 * Score cross-references to other docs.
 */
async function scoreCrossRefs(projectPath) {
  const claudeMd = await readFileSafe(path.join(projectPath, 'CLAUDE.md'));
  if (!claudeMd) return 0;

  const links = claudeMd.match(/\[([^\]]+)\]\(([^)]+)\)/g) || [];
  const internalLinks = links.filter(l => !l.includes('http'));

  if (internalLinks.length >= 5) return 100;
  if (internalLinks.length >= 3) return 70;
  if (internalLinks.length >= 1) return 40;
  if (links.length > 0) return 20;
  return 0;
}

function getGrade(score) {
  if (score >= 90) return 'A';
  if (score >= 80) return 'B';
  if (score >= 70) return 'C';
  if (score >= 60) return 'D';
  return 'F';
}

/**
 * Save health scores to a JSON history file for trend tracking.
 * Keeps only the last 30 runs to prevent unbounded growth.
 */
async function saveHealthHistory(projectScores, historyPath, history) {
  const now = new Date();
  const run = {
    date: now.toISOString().slice(0, 10),
    timestamp: now.toISOString(),
    average: Math.round(
      Object.values(projectScores).reduce((s, p) => s + p.overall, 0) /
      Math.max(Object.keys(projectScores).length, 1)
    ),
    projects: {},
  };

  for (const [name, scores] of Object.entries(projectScores)) {
    run.projects[name] = { overall: scores.overall, grade: scores.grade };
  }

  history.runs.push(run);

  // Keep only the last 30 runs
  if (history.runs.length > 30) {
    history.runs = history.runs.slice(-30);
  }

  await writeJson(historyPath, history);
  log('Health history saved to docs-portal/health-history.json', 'success');
}

/**
 * Build the Trends section for the health report by comparing current scores
 * against the most recent previous run in history.
 */
function buildTrendsSection(projectScores, history) {
  // Need at least one previous run (before the current one is appended)
  if (!history.runs || history.runs.length === 0) {
    return `## Trends

*No previous runs available. Trends will appear after the next pipeline run.*

`;
  }

  const lastRun = history.runs[history.runs.length - 1];
  const currentAvg = Math.round(
    Object.values(projectScores).reduce((s, p) => s + p.overall, 0) /
    Math.max(Object.keys(projectScores).length, 1)
  );

  let section = `## Trends

**Compared to last run:** ${lastRun.date}

`;

  // Overall average trend
  const avgDiff = currentAvg - lastRun.average;
  const avgTrend = avgDiff > 0 ? `+${avgDiff}` : avgDiff < 0 ? `${avgDiff}` : 'unchanged';
  section += `**Overall Average:** ${currentAvg}% (${avgTrend})\n\n`;

  section += `| Project | Current | Previous | Change |\n`;
  section += `|---------|---------|----------|--------|\n`;

  // Collect all project names from both current and last run
  const allProjects = new Set([
    ...Object.keys(projectScores),
    ...Object.keys(lastRun.projects),
  ]);

  const sortedNames = [...allProjects].sort();

  for (const name of sortedNames) {
    const current = projectScores[name];
    const previous = lastRun.projects[name];

    if (current && previous) {
      const diff = current.overall - previous.overall;
      let change;
      if (diff > 0) change = `+${diff}`;
      else if (diff < 0) change = `${diff}`;
      else change = 'unchanged';
      section += `| ${name} | ${current.overall}% | ${previous.overall}% | ${change} |\n`;
    } else if (current && !previous) {
      section += `| ${name} | ${current.overall}% | — | new |\n`;
    } else if (!current && previous) {
      section += `| ${name} | — | ${previous.overall}% | removed |\n`;
    }
  }

  section += '\n';
  return section;
}

async function generateReport(projectScores, config, discovery, history) {
  const outputPath = path.join(config.workspace, 'docs-portal', 'HEALTH_REPORT.md');
  const date = timestamp();

  const sortedProjects = Object.entries(projectScores)
    .sort((a, b) => b[1].overall - a[1].overall);

  const avgScore = sortedProjects.reduce((s, [, p]) => s + p.overall, 0) / Math.max(sortedProjects.length, 1);
  const goodCount = sortedProjects.filter(([, p]) => p.overall >= 75).length;

  let report = `# Squeegee Documentation Health Report

**Generated:** ${date}
**System:** Squeegee v2.0
**Average Score:** ${Math.round(avgScore)}%
**Healthy Projects:** ${goodCount}/${sortedProjects.length}

---

## Project Scores

| Project | Overall | Presence | Quality | Freshness | Structure | Cross-Refs | Grade |
|---------|---------|----------|---------|-----------|-----------|------------|-------|
`;

  for (const [name, scores] of sortedProjects) {
    report += `| ${name} | ${scores.overall}% | ${scores.presence}% | ${scores.quality}% | ${scores.freshness}% | ${scores.structure}% | ${scores.crossRefs}% | ${scores.grade} |\n`;
  }

  report += `
---

## Score Distribution

`;

  const grades = { A: 0, B: 0, C: 0, D: 0, F: 0 };
  for (const [, scores] of sortedProjects) {
    grades[scores.grade]++;
  }

  for (const [grade, count] of Object.entries(grades)) {
    const bar = '█'.repeat(count) + '░'.repeat(Math.max(0, sortedProjects.length - count));
    report += `${grade}: ${bar} (${count})\n`;
  }

  report += `
---

`;

  // Add trends section from history comparison
  report += buildTrendsSection(projectScores, history);

  report += `---

## Recommendations

`;

  for (const [name, scores] of sortedProjects) {
    if (scores.overall >= 80) continue;

    report += `### ${name} (${scores.overall}%)\n`;
    if (scores.presence < 50) report += `- Missing key documentation files\n`;
    if (scores.quality < 50) report += `- Documentation has placeholder/template content — needs real content\n`;
    if (scores.freshness < 30) report += `- No recent git activity — may be stale or archived\n`;
    if (scores.structure < 50) report += `- CLAUDE.md needs better structure (headings, code examples, tables)\n`;
    if (scores.crossRefs < 40) report += `- Add cross-references to related documentation\n`;
    report += '\n';
  }

  report += `---

*Generated by Squeegee Documentation System*
`;

  await ensureDir(path.dirname(outputPath));
  await fs.writeFile(outputPath, report, 'utf-8');
  log(`Health report saved to docs-portal/HEALTH_REPORT.md`, 'success');

  // Console summary
  console.log('');
  console.log('  📊 HEALTH SCORES');
  console.log('  ─────────────────────────────────────');
  for (const [name, scores] of sortedProjects) {
    const icon = scores.overall >= 80 ? '✅' : scores.overall >= 60 ? '⚠️' : '❌';
    const bar = '█'.repeat(Math.round(scores.overall / 5)) + '░'.repeat(20 - Math.round(scores.overall / 5));
    console.log(`  ${icon} ${name.padEnd(30)} ${bar} ${scores.overall}% (${scores.grade})`);
  }
  console.log('');
}

module.exports = { run };
