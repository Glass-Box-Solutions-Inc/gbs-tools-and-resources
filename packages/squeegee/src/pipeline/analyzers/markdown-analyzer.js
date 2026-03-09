/**
 * Markdown analyzer — quality scoring and section parsing.
 *
 * Replaces the inline scoring logic from the old QualityAnalyzer class.
 *
 * @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
 */

const path = require('path');
const fs = require('fs').promises;
const { readFileSafe } = require('../utils');

/**
 * Analyze a markdown file and return metadata + quality scores.
 */
async function analyzeMarkdown(filePath, workspace) {
  const content = await readFileSafe(filePath);
  if (!content) return null;

  const lines = content.split('\n');
  const headings = lines.filter(l => /^#{1,6}\s/.test(l));
  const codeBlocks = content.match(/```[\s\S]*?```/g) || [];
  const links = content.match(/\[([^\]]+)\]\(([^)]+)\)/g) || [];
  const tables = content.match(/^\|.+\|$/gm) || [];

  // Extract sections by H2
  const sections = extractSections(content);

  // Get file modification time from git (more reliable than fs stat)
  let lastModified;
  try {
    const stat = await fs.stat(filePath);
    lastModified = stat.mtime;
  } catch {
    lastModified = new Date();
  }

  return {
    path: path.relative(workspace, filePath).replace(/\\/g, '/'),
    absolutePath: filePath,
    lineCount: lines.length,
    headingCount: headings.length,
    codeBlockCount: codeBlocks.length,
    linkCount: links.length,
    tableCount: tables.length,
    sections: Object.keys(sections),
    sectionContents: sections,
    lastModified,
    docType: classifyDocType(path.basename(filePath)),
  };
}

/**
 * Extract H2 sections from markdown.
 * Returns { sectionName: content } map.
 */
function extractSections(content) {
  const sections = {};
  const lines = content.split('\n');
  let currentSection = '_header';
  let currentContent = [];

  for (const line of lines) {
    if (line.startsWith('## ')) {
      if (currentContent.length > 0) {
        sections[currentSection] = currentContent.join('\n').trim();
      }
      currentSection = line.replace('## ', '').trim();
      currentContent = [];
    } else {
      currentContent.push(line);
    }
  }
  if (currentContent.length > 0) {
    sections[currentSection] = currentContent.join('\n').trim();
  }

  return sections;
}

function classifyDocType(filename) {
  if (filename === 'CLAUDE.md') return 'CLAUDE.md';
  if (filename === 'STATE.md') return 'STATE.md';
  if (filename === 'PLANS_APPROVED.md') return 'PLANS_APPROVED.md';
  if (filename === 'PROGRAMMING_PRACTICES.md') return 'PROGRAMMING_PRACTICES.md';
  if (filename === 'ROADMAP.md') return 'ROADMAP.md';
  if (filename === 'README.md') return 'README.md';
  if (filename === 'CHANGELOG.md') return 'CHANGELOG.md';
  if (filename === 'ISSUES.md') return 'ISSUES.md';
  if (filename.endsWith('PLAN.md')) return 'PLAN.md';
  if (filename.endsWith('SUMMARY.md')) return 'SUMMARY.md';
  return 'OTHER';
}

module.exports = { analyzeMarkdown, extractSections, classifyDocType };
