/**
 * Stage 12: Documentation Validation
 *
 * Comprehensive validation of all markdown documentation across projects.
 * Checks quality scores, broken internal links, placeholder content,
 * missing required sections, heading hierarchy, and staleness.
 *
 * Migrated from legacy squeegee-manager runValidate + QualityAnalyzer,
 * with improved scoring and richer diagnostics.
 *
 * @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
 */

const fs = require('fs').promises;
const path = require('path');
const { log, fileExists, readFileSafe, findFiles } = require('../utils');
const { resolveProjectPath } = require('../config');

// ---------------------------------------------------------------------------
// Placeholder / template patterns that indicate unfinished documentation
// ---------------------------------------------------------------------------
const PLACEHOLDER_PATTERNS = [
  { regex: /\*Not detected\*/g, label: 'placeholder "*Not detected*"' },
  { regex: /\[Define\]/g, label: 'placeholder "[Define]"' },
  { regex: /awaiting instructions/gi, label: 'placeholder "awaiting instructions"' },
  { regex: /TODO[:\s]/gi, label: 'TODO marker' },
  { regex: /FIXME[:\s]/gi, label: 'FIXME marker' },
  { regex: /\[INSERT .+?\]/gi, label: 'template insertion marker' },
  { regex: /\[TBD\]/gi, label: 'placeholder "[TBD]"' },
  { regex: /\[PLACEHOLDER\]/gi, label: 'placeholder "[PLACEHOLDER]"' },
  { regex: /Lorem ipsum/gi, label: 'Lorem ipsum filler text' },
  { regex: /\*No patterns detected\*/g, label: 'placeholder "*No patterns detected*"' },
];

// ---------------------------------------------------------------------------
// Required sections in CLAUDE.md files (sourced from config.docTypes)
// ---------------------------------------------------------------------------
const DEFAULT_CLAUDE_REQUIRED_SECTIONS = [
  'Tech Stack',
  'Commands',
  'Architecture',
];

// ---------------------------------------------------------------------------
// Main entry point
// ---------------------------------------------------------------------------
async function run(config, discovery) {
  log('Stage 12: Validating documentation...', 'info');

  const results = {
    errors: [],
    warnings: [],
    info: [],
    fileResults: [],
    totalFiles: 0,
  };

  // Use discovery data if available, otherwise scan from config
  const mdFiles = discovery && discovery.markdown
    ? discovery.markdown
    : await discoverMarkdownFiles(config);

  results.totalFiles = mdFiles.length;

  for (const doc of mdFiles) {
    const filePath = doc.absolutePath || path.join(config.workspace, doc.path);
    const content = await readFileSafe(filePath);
    if (!content) continue;

    const fileIssues = await validateFile(filePath, doc, content, config);
    results.fileResults.push(fileIssues);

    results.errors.push(...fileIssues.errors);
    results.warnings.push(...fileIssues.warnings);
    results.info.push(...fileIssues.info);
  }

  printReport(results);

  const passCount = results.fileResults.filter(f => f.score >= 60).length;
  const failCount = results.fileResults.filter(f => f.score < 60).length;

  log(
    `Validation complete. ${results.totalFiles} files scanned: ` +
    `${passCount} pass, ${failCount} below threshold. ` +
    `${results.errors.length} errors, ${results.warnings.length} warnings.`,
    results.errors.length > 0 ? 'warn' : 'success'
  );

  return {
    errors: results.errors,
    warnings: results.warnings,
    info: results.info,
    totalFiles: results.totalFiles,
  };
}

// ---------------------------------------------------------------------------
// Fallback discovery when no discovery object is passed
// ---------------------------------------------------------------------------
async function discoverMarkdownFiles(config) {
  const mdFiles = [];

  for (const project of config.projects) {
    const projectPath = resolveProjectPath(config, project.path);
    if (!(await fileExists(projectPath))) continue;

    const files = await findFiles(projectPath, '.md');
    for (const file of files) {
      const relativePath = path.relative(config.workspace, file).replace(/\\/g, '/');
      mdFiles.push({
        path: relativePath,
        absolutePath: file,
        docType: classifyDocType(path.basename(file)),
      });
    }
  }

  return mdFiles;
}

function classifyDocType(filename) {
  if (filename === 'CLAUDE.md') return 'CLAUDE.md';
  if (filename === 'STATE.md') return 'STATE.md';
  if (filename === 'PLANS_APPROVED.md') return 'PLANS_APPROVED.md';
  if (filename === 'PROGRAMMING_PRACTICES.md') return 'PROGRAMMING_PRACTICES.md';
  if (filename === 'README.md') return 'README.md';
  return 'OTHER';
}

// ---------------------------------------------------------------------------
// Per-file validation
// ---------------------------------------------------------------------------
async function validateFile(filePath, doc, content, config) {
  const relativePath = doc.path || path.relative(config.workspace, filePath).replace(/\\/g, '/');
  const result = {
    path: relativePath,
    docType: doc.docType || classifyDocType(path.basename(filePath)),
    score: 0,
    errors: [],
    warnings: [],
    info: [],
  };

  const lines = content.split('\n');
  const headings = lines.filter(l => /^#{1,6}\s/.test(l));
  const codeBlocks = content.match(/```[\s\S]*?```/g) || [];
  const links = content.match(/\[([^\]]+)\]\(([^)]+)\)/g) || [];

  // --- Quality score (0-100) ---
  result.score = computeQualityScore(content, lines, headings, codeBlocks, links, doc, config);

  const threshold = Math.round((config.quality?.thresholds?.minimum || 0.60) * 100);
  if (result.score < threshold) {
    result.errors.push(`[QUALITY] ${relativePath}: score ${result.score}/100 (below ${threshold} threshold)`);
  } else {
    result.info.push(`[QUALITY] ${relativePath}: score ${result.score}/100`);
  }

  // --- Heading hierarchy (no skipped levels) ---
  const headingIssues = checkHeadingHierarchy(headings);
  for (const issue of headingIssues) {
    result.warnings.push(`[HEADING] ${relativePath}: ${issue}`);
  }

  // --- Placeholder / template content ---
  const placeholderHits = detectPlaceholders(content);
  for (const hit of placeholderHits) {
    result.warnings.push(`[PLACEHOLDER] ${relativePath}: contains ${hit.label} (${hit.count} occurrence${hit.count > 1 ? 's' : ''})`);
  }

  // --- Broken internal links ---
  const brokenLinks = await checkInternalLinks(content, filePath, config);
  for (const broken of brokenLinks) {
    result.errors.push(`[BROKEN LINK] ${relativePath}: [${broken.text}](${broken.href}) target not found`);
  }

  // --- Missing required sections in CLAUDE.md ---
  if (result.docType === 'CLAUDE.md') {
    const requiredSections = (config.docTypes && config.docTypes['CLAUDE.md'] && config.docTypes['CLAUDE.md'].requiredSections)
      || DEFAULT_CLAUDE_REQUIRED_SECTIONS;
    const missingSections = checkRequiredSections(content, requiredSections);
    for (const section of missingSections) {
      result.warnings.push(`[MISSING SECTION] ${relativePath}: required section "${section}" not found`);
    }
  }

  // --- Staleness check ---
  const stalenessWarning = await checkStaleness(filePath, config);
  if (stalenessWarning) {
    result.warnings.push(`[STALE] ${relativePath}: ${stalenessWarning}`);
  }

  return result;
}

// ---------------------------------------------------------------------------
// Quality scoring (0-100)
// ---------------------------------------------------------------------------
function computeQualityScore(content, lines, headings, codeBlocks, links, doc, config) {
  let score = 0;

  // --- Content length (0-20) ---
  const lineCount = lines.length;
  if (lineCount >= 80) score += 20;
  else if (lineCount >= 40) score += 14;
  else if (lineCount >= 20) score += 8;
  else if (lineCount >= 5) score += 3;

  // --- Heading structure (0-20) ---
  if (headings.length >= 3 && headings.length <= 25) score += 12;
  else if (headings.length > 0) score += 6;

  // Check for single H1
  const h1s = headings.filter(h => /^#\s/.test(h) && !/^##/.test(h));
  if (h1s.length === 1) score += 5;
  else if (h1s.length === 0) score += 0;
  else score += 2; // Multiple H1s is suboptimal

  // No skipped heading levels bonus
  const levels = headings.map(h => h.match(/^#+/)[0].length);
  let skips = 0;
  for (let i = 1; i < levels.length; i++) {
    if (levels[i] - levels[i - 1] > 1) skips++;
  }
  if (skips === 0 && headings.length > 0) score += 3;

  // --- Code blocks (0-15) ---
  if (codeBlocks.length >= 3) score += 15;
  else if (codeBlocks.length >= 1) score += 8;

  // --- Links and cross-references (0-15) ---
  const internalLinks = links.filter(l => !l.includes('http'));
  if (internalLinks.length >= 5) score += 15;
  else if (internalLinks.length >= 2) score += 10;
  else if (links.length >= 3) score += 6;
  else if (links.length > 0) score += 3;

  // --- Tables (0-10) ---
  const tables = content.match(/^\|.+\|$/gm) || [];
  if (tables.length >= 4) score += 10;
  else if (tables.length > 0) score += 5;

  // --- No placeholders bonus (0-10) ---
  const placeholders = detectPlaceholders(content);
  if (placeholders.length === 0) score += 10;
  else if (placeholders.length <= 2) score += 4;

  // --- Consistency (0-10) ---
  let consistency = 10;

  // Mixed bullet styles penalty
  const bulletDash = (content.match(/^- /gm) || []).length;
  const bulletAsterisk = (content.match(/^\* /gm) || []).length;
  if (bulletDash > 0 && bulletAsterisk > 0) consistency -= 3;

  // Bare URLs penalty
  const bareUrls = content.match(/(?<![(\[])https?:\/\/[^\s)>\]]+/g) || [];
  if (bareUrls.length > 3) consistency -= 4;
  else if (bareUrls.length > 0) consistency -= 1;

  // Code blocks without language tag
  const codeBlockFences = content.match(/^```[\w-]*$/gm) || [];
  const withLanguage = codeBlockFences.filter(f => f.length > 3).length;
  const totalBlocks = Math.floor(codeBlockFences.length / 2);
  if (totalBlocks > 0 && withLanguage < totalBlocks) {
    const ratio = (totalBlocks - withLanguage) / totalBlocks;
    if (ratio > 0.5) consistency -= 3;
  }

  score += Math.max(0, consistency);

  return Math.min(100, Math.max(0, score));
}

// ---------------------------------------------------------------------------
// Heading hierarchy check
// ---------------------------------------------------------------------------
function checkHeadingHierarchy(headings) {
  const issues = [];
  if (headings.length === 0) return issues;

  const levels = headings.map(h => h.match(/^#+/)[0].length);

  for (let i = 1; i < levels.length; i++) {
    if (levels[i] - levels[i - 1] > 1) {
      const fromHeading = headings[i - 1].trim().slice(0, 60);
      const toHeading = headings[i].trim().slice(0, 60);
      issues.push(
        `skipped heading level H${levels[i - 1]} -> H${levels[i]} ` +
        `("${fromHeading}" -> "${toHeading}")`
      );
    }
  }

  // Check for multiple H1s
  const h1Count = levels.filter(l => l === 1).length;
  if (h1Count > 1) {
    issues.push(`multiple H1 headings found (${h1Count}); expected at most 1`);
  }

  return issues;
}

// ---------------------------------------------------------------------------
// Placeholder / template content detection
// ---------------------------------------------------------------------------
function detectPlaceholders(content) {
  const hits = [];

  for (const pattern of PLACEHOLDER_PATTERNS) {
    const matches = content.match(pattern.regex);
    if (matches && matches.length > 0) {
      hits.push({ label: pattern.label, count: matches.length });
    }
  }

  return hits;
}

// ---------------------------------------------------------------------------
// Broken internal link checking
// ---------------------------------------------------------------------------
async function checkInternalLinks(content, filePath, config) {
  const broken = [];
  const linkRegex = /\[([^\]]+)\]\(([^)]+)\)/g;
  let match;

  while ((match = linkRegex.exec(content)) !== null) {
    const linkText = match[1];
    const href = match[2];

    // Skip external links, anchors, and mailto
    if (href.startsWith('http') || href.startsWith('#') || href.startsWith('mailto:')) {
      continue;
    }

    // Strip fragment identifier for file-existence check
    const hrefNoFragment = href.split('#')[0];
    if (!hrefNoFragment) continue; // Pure anchor like #heading

    // Resolve relative to the file's directory
    const fileDir = path.dirname(filePath);
    let targetPath;

    // Handle workspace-root-relative links (starting with no ./ or ../)
    if (!hrefNoFragment.startsWith('.') && !path.isAbsolute(hrefNoFragment)) {
      // Try relative to file first
      targetPath = path.resolve(fileDir, hrefNoFragment);
      if (!(await fileExists(targetPath))) {
        // Try relative to workspace root
        targetPath = path.resolve(config.workspace, hrefNoFragment);
      }
    } else {
      targetPath = path.resolve(fileDir, hrefNoFragment);
    }

    if (!(await fileExists(targetPath))) {
      broken.push({ text: linkText, href });
    }
  }

  return broken;
}

// ---------------------------------------------------------------------------
// Required section checking for CLAUDE.md
// ---------------------------------------------------------------------------
function checkRequiredSections(content, requiredSections) {
  const missing = [];

  for (const section of requiredSections) {
    // Match ## heading or ### heading containing the section name (case-insensitive)
    const sectionRegex = new RegExp(`^##+ .*${escapeRegex(section)}`, 'im');
    if (!sectionRegex.test(content)) {
      missing.push(section);
    }
  }

  return missing;
}

function escapeRegex(str) {
  return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

// ---------------------------------------------------------------------------
// Staleness detection: file modified date vs. config freshness thresholds
// ---------------------------------------------------------------------------
async function checkStaleness(filePath, config) {
  try {
    const stat = await fs.stat(filePath);
    const daysSince = (Date.now() - stat.mtime.getTime()) / (1000 * 60 * 60 * 24);

    const poorThreshold = config.quality?.freshness?.poor || 180;

    if (daysSince > poorThreshold) {
      return `last modified ${Math.round(daysSince)} days ago (>${poorThreshold} day threshold)`;
    }
  } catch {
    // Can't stat — skip
  }

  return null;
}

// ---------------------------------------------------------------------------
// Console report
// ---------------------------------------------------------------------------
function printReport(results) {
  console.log('');
  console.log('  VALIDATION REPORT');
  console.log('  ─────────────────────────────────────────');
  console.log(`  Files scanned:  ${results.totalFiles}`);
  console.log(`  Errors:         ${results.errors.length}`);
  console.log(`  Warnings:       ${results.warnings.length}`);
  console.log(`  Info:           ${results.info.length}`);
  console.log('');

  // Group by severity
  if (results.errors.length > 0) {
    console.log('  ERRORS');
    console.log('  .......................................');
    for (const err of results.errors) {
      console.log(`    ${err}`);
    }
    console.log('');
  }

  if (results.warnings.length > 0) {
    console.log('  WARNINGS');
    console.log('  .......................................');
    for (const warn of results.warnings) {
      console.log(`    ${warn}`);
    }
    console.log('');
  }

  // Score summary table
  const scored = results.fileResults
    .filter(f => f.score !== undefined)
    .sort((a, b) => a.score - b.score);

  if (scored.length > 0) {
    console.log('  SCORE SUMMARY');
    console.log('  .......................................');
    for (const f of scored) {
      const barFilled = Math.round(f.score / 5);
      const bar = '\u2588'.repeat(barFilled) + '\u2591'.repeat(20 - barFilled);
      const icon = f.score >= 80 ? 'OK' : f.score >= 60 ? '--' : 'XX';
      const shortPath = f.path.length > 50 ? '...' + f.path.slice(-47) : f.path;
      console.log(`    [${icon}] ${shortPath.padEnd(50)} ${bar} ${f.score}%`);
    }
    console.log('');
  }
}

module.exports = { run };
