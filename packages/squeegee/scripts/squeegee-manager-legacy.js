#!/usr/bin/env node
/**
 * Squeegee Documentation Manager
 *
 * Multi-agent orchestration system for documentation curation.
 * Coordinates specialized agents for discovery, analysis, generation, and validation.
 *
 * Usage:
 *   node squeegee-manager.js scan          # Scan all projects
 *   node squeegee-manager.js analyze       # Analyze documentation quality
 *   node squeegee-manager.js generate      # Generate missing docs
 *   node squeegee-manager.js validate      # Validate all documentation
 *   node squeegee-manager.js report        # Generate health report
 *   node squeegee-manager.js full          # Run complete pipeline
 *
 * @author GlassBox Solutions
 * @version 1.0.0
 */

const fs = require('fs').promises;
const path = require('path');
const { execSync } = require('child_process');
const crypto = require('crypto');

// Configuration
const CONFIG = {
  workspace: process.env.WORKSPACE || process.cwd(),
  helperUrl: process.env.HELPER_URL || 'http://localhost:5678',
  supabaseUrl: process.env.SUPABASE_URL || '',
  supabaseKey: process.env.SUPABASE_KEY || '',
  projects: [
    'projects/ousd-campaign-platform',
    'projects/water-dragons-splash',
    'projects/wc-paralegal-agent',
    'projects/legal-research',
    'projects/legal-research-v2',
    'projects/legal-research-dashboard',
    'projects/glass-box-website',
    'projects/meruscase-medical-aggregator',
    'projects/adjudica-ai-website',
    'projects/adjudica-legal-docs',
    'projects/merus-expert',
    'projects/specticles',
    'projects/attorney-dashboard',
    'projects/glassy',
    'projects/glassy/web',
    'projects/glassy/mobile',
    'projects/glassy/infra',
    'projects/glassy/backend',
    'wc-paralegal-nestjs',
    'wc-paralegal-backend'
  ],
  docTypes: {
    'CLAUDE.md': { required: true, level: 1, minLines: 80, maxLines: 150 },
    'STATE.md': { required: true, level: 1, minLines: 30, maxLines: 200 },
    // 'VariableForClMD.md': DEPRECATED - Use .planning/STATE.md (GSD format)
    'PLANS_APPROVED.md': { required: false, level: 1, minLines: 10, maxLines: 500 },
    'README.md': { required: false, level: 1, minLines: 10 },
    'GUIDE': { required: false, level: 2, minLines: 50 }
  },
  plans: {
    maxRecentPlans: 20,
    archiveAfterDays: 90
  }
};

// Utility functions
const log = (msg, type = 'info') => {
  const colors = { info: '\x1b[36m', success: '\x1b[32m', warn: '\x1b[33m', error: '\x1b[31m' };
  const icons = { info: 'ℹ', success: '✓', warn: '⚠', error: '✗' };
  console.log(`${colors[type]}${icons[type]}\x1b[0m ${msg}`);
};

const hash = (content) => crypto.createHash('sha256').update(content).digest('hex').slice(0, 12);

// ============================================================================
// HISTORY MANAGER - Version control for documentation
// ============================================================================
class HistoryManager {
  constructor(workspace) {
    this.workspace = workspace;
    this.historyDir = path.join(workspace, 'docs-history');
  }

  /**
   * Archive a file before updating it
   * @param {string} filePath - Absolute path to the file
   * @param {string} reason - Why this version is being archived
   * @returns {object} Archive info with version path and metadata
   */
  async archive(filePath, reason = 'update') {
    try {
      const content = await fs.readFile(filePath, 'utf-8');
      const relativePath = path.relative(this.workspace, filePath);
      const fileName = path.basename(filePath);
      const dirPath = path.dirname(relativePath);

      // Create history structure: docs-history/[project]/[filename]/[date]-[hash].md
      const date = new Date().toISOString().split('T')[0];
      const time = new Date().toISOString().split('T')[1].slice(0, 5).replace(':', '');
      const contentHash = hash(content);
      const versionName = `${date}_${time}_${contentHash}.md`;

      const historyPath = path.join(this.historyDir, dirPath, fileName.replace('.md', ''));
      const versionPath = path.join(historyPath, versionName);

      // Check if this exact version already exists (same hash)
      try {
        const existing = await fs.readdir(historyPath);
        const sameHash = existing.find(f => f.includes(contentHash));
        if (sameHash) {
          return { skipped: true, reason: 'identical version exists', hash: contentHash };
        }
      } catch {}

      // Create directory and save version
      await fs.mkdir(historyPath, { recursive: true });

      // Add metadata header to archived version
      const metadata = `<!--
SQUEEGEE ARCHIVE
================
Archived: ${new Date().toISOString()}
Reason: ${reason}
Hash: ${contentHash}
Original: ${relativePath}
-->

${content}`;

      await fs.writeFile(versionPath, metadata, 'utf-8');

      // Update the changelog
      await this.updateChangelog(historyPath, {
        date: new Date().toISOString(),
        version: versionName,
        reason,
        hash: contentHash,
        lines: content.split('\n').length
      });

      return {
        archived: true,
        versionPath: path.relative(this.workspace, versionPath),
        hash: contentHash
      };

    } catch (e) {
      if (e.code === 'ENOENT') {
        return { skipped: true, reason: 'file does not exist yet' };
      }
      throw e;
    }
  }

  /**
   * Update the changelog for a document
   */
  async updateChangelog(historyPath, entry) {
    const changelogPath = path.join(historyPath, 'CHANGELOG.md');

    let changelog = '';
    try {
      changelog = await fs.readFile(changelogPath, 'utf-8');
    } catch {
      // Create new changelog
      const docName = path.basename(historyPath);
      changelog = `# ${docName} - Version History

This file tracks all versions of ${docName}.md managed by Squeegee.

---

## Versions

`;
    }

    // Add new entry at the top of versions section
    const newEntry = `### ${entry.date.split('T')[0]} - ${entry.hash}
- **Reason:** ${entry.reason}
- **Lines:** ${entry.lines}
- **File:** \`${entry.version}\`

`;

    // Insert after "## Versions" header
    const insertPoint = changelog.indexOf('## Versions') + '## Versions\n\n'.length;
    changelog = changelog.slice(0, insertPoint) + newEntry + changelog.slice(insertPoint);

    await fs.writeFile(changelogPath, changelog, 'utf-8');
  }

  /**
   * Get all versions of a document
   */
  async getVersions(filePath) {
    const relativePath = path.relative(this.workspace, filePath);
    const fileName = path.basename(filePath);
    const dirPath = path.dirname(relativePath);
    const historyPath = path.join(this.historyDir, dirPath, fileName.replace('.md', ''));

    try {
      const files = await fs.readdir(historyPath);
      const versions = files
        .filter(f => f.endsWith('.md') && f !== 'CHANGELOG.md')
        .map(f => {
          const [date, time, hashPart] = f.replace('.md', '').split('_');
          return { file: f, date, time, hash: hashPart };
        })
        .sort((a, b) => b.date.localeCompare(a.date) || b.time.localeCompare(a.time));

      return versions;
    } catch {
      return [];
    }
  }

  /**
   * Compare two versions and extract what changed
   */
  async compareVersions(filePath, oldVersion, newVersion) {
    const relativePath = path.relative(this.workspace, filePath);
    const fileName = path.basename(filePath);
    const dirPath = path.dirname(relativePath);
    const historyPath = path.join(this.historyDir, dirPath, fileName.replace('.md', ''));

    const oldContent = await fs.readFile(path.join(historyPath, oldVersion), 'utf-8');
    const newContent = await fs.readFile(path.join(historyPath, newVersion), 'utf-8');

    // Remove metadata headers for comparison
    const cleanOld = oldContent.replace(/<!--[\s\S]*?-->\n\n/, '');
    const cleanNew = newContent.replace(/<!--[\s\S]*?-->\n\n/, '');

    const oldLines = cleanOld.split('\n');
    const newLines = cleanNew.split('\n');

    // Simple diff: find added and removed lines
    const added = newLines.filter(l => !oldLines.includes(l) && l.trim());
    const removed = oldLines.filter(l => !newLines.includes(l) && l.trim());

    // Extract section changes
    const oldSections = this.extractSections(cleanOld);
    const newSections = this.extractSections(cleanNew);

    const sectionChanges = [];
    for (const [section, content] of Object.entries(newSections)) {
      if (!oldSections[section]) {
        sectionChanges.push({ section, change: 'added' });
      } else if (oldSections[section] !== content) {
        sectionChanges.push({ section, change: 'modified' });
      }
    }
    for (const section of Object.keys(oldSections)) {
      if (!newSections[section]) {
        sectionChanges.push({ section, change: 'removed' });
      }
    }

    return {
      linesAdded: added.length,
      linesRemoved: removed.length,
      sectionChanges,
      added: added.slice(0, 10),
      removed: removed.slice(0, 10)
    };
  }

  /**
   * Extract sections from markdown content
   */
  extractSections(content) {
    const sections = {};
    const lines = content.split('\n');
    let currentSection = 'header';
    let currentContent = [];

    for (const line of lines) {
      if (line.startsWith('## ')) {
        if (currentContent.length > 0) {
          sections[currentSection] = currentContent.join('\n');
        }
        currentSection = line.replace('## ', '').trim();
        currentContent = [];
      } else {
        currentContent.push(line);
      }
    }
    if (currentContent.length > 0) {
      sections[currentSection] = currentContent.join('\n');
    }

    return sections;
  }

  /**
   * Generate learnings from version history
   */
  async generateLearnings(filePath) {
    const versions = await this.getVersions(filePath);
    if (versions.length < 2) {
      return { message: 'Not enough versions to analyze' };
    }

    const learnings = {
      totalVersions: versions.length,
      dateRange: {
        oldest: versions[versions.length - 1].date,
        newest: versions[0].date
      },
      patterns: [],
      recommendations: []
    };

    // Analyze patterns across versions
    const changes = [];
    for (let i = 0; i < versions.length - 1; i++) {
      const diff = await this.compareVersions(filePath, versions[i + 1].file, versions[i].file);
      changes.push(diff);
    }

    // Extract patterns
    const totalAdded = changes.reduce((sum, c) => sum + c.linesAdded, 0);
    const totalRemoved = changes.reduce((sum, c) => sum + c.linesRemoved, 0);

    if (totalAdded > totalRemoved * 2) {
      learnings.patterns.push('Document is growing significantly - consider splitting');
    }
    if (totalRemoved > totalAdded) {
      learnings.patterns.push('Document is being simplified - good trend');
    }

    // Section change frequency
    const sectionFreq = {};
    for (const change of changes) {
      for (const sc of change.sectionChanges) {
        sectionFreq[sc.section] = (sectionFreq[sc.section] || 0) + 1;
      }
    }

    const frequentlyChanged = Object.entries(sectionFreq)
      .filter(([, count]) => count >= 3)
      .map(([section]) => section);

    if (frequentlyChanged.length > 0) {
      learnings.patterns.push(`Frequently updated sections: ${frequentlyChanged.join(', ')}`);
      learnings.recommendations.push('Consider if frequently changed sections need restructuring');
    }

    return learnings;
  }

  /**
   * Get history summary for all documents
   */
  async getSummary() {
    const summary = {
      totalDocuments: 0,
      totalVersions: 0,
      byProject: {}
    };

    try {
      const projects = await fs.readdir(this.historyDir);

      for (const project of projects) {
        const projectPath = path.join(this.historyDir, project);
        const stat = await fs.stat(projectPath);
        if (!stat.isDirectory()) continue;

        summary.byProject[project] = { documents: 0, versions: 0 };

        const docs = await fs.readdir(projectPath);
        for (const doc of docs) {
          const docPath = path.join(projectPath, doc);
          const docStat = await fs.stat(docPath);
          if (!docStat.isDirectory()) continue;

          const versions = await fs.readdir(docPath);
          const versionCount = versions.filter(f => f.endsWith('.md') && f !== 'CHANGELOG.md').length;

          summary.byProject[project].documents++;
          summary.byProject[project].versions += versionCount;
          summary.totalDocuments++;
          summary.totalVersions += versionCount;
        }
      }
    } catch {
      // History directory doesn't exist yet
    }

    return summary;
  }
}

// ============================================================================
// SCANNER - Discover all documentation files
// ============================================================================
class DocumentScanner {
  constructor(workspace) {
    this.workspace = workspace;
    this.results = { markdown: [], code: [], projects: {} };
  }

  async scanMarkdown() {
    log('Scanning markdown files...', 'info');

    const markdownFiles = [];
    const excludeDirs = [
      'node_modules',
      '.git',
      '__pycache__',
      '.venv',
      'venv',
      'dist',
      'build',
      '.next',
      'coverage',
      '.svelte-kit',
      '.pytest_cache',
      'htmlcov',
      '.mypy_cache',
      '.tox',
      'eggs',
      '.cache',
      '.vercel',
      '.turbo',
      'vendor',
      '.nuxt',
      '.output',
      'out'
    ];

    for (const project of CONFIG.projects) {
      const projectPath = path.join(this.workspace, project);
      const files = await this.findFiles(projectPath, '.md', excludeDirs);

      for (const file of files) {
        const relativePath = path.relative(this.workspace, file).replace(/\\/g, '/');
        const content = await fs.readFile(file, 'utf-8');
        const lines = content.split('\n');

        // Determine doc type
        const filename = path.basename(file);
        let docType = 'OTHER';
        if (filename === 'CLAUDE.md') docType = 'CLAUDE.md';
        else if (filename === 'VariableForClMD.md') docType = 'VARIABLE';
        else if (filename === 'STATE.md') docType = 'STATE';
        else if (filename === 'README.md') docType = 'README';
        else if (filename.includes('GUIDE') || filename.includes('Guide')) docType = 'GUIDE';
        else if (filename.includes('DEPLOY')) docType = 'DEPLOYMENT';
        else if (filename.includes('SECURITY')) docType = 'SECURITY';
        else if (filename.includes('API')) docType = 'API';

        // Extract metadata
        const headings = lines.filter(l => l.startsWith('#')).length;
        const codeBlocks = (content.match(/```/g) || []).length / 2;
        const links = (content.match(/\[.*?\]\(.*?\)/g) || []).length;

        markdownFiles.push({
          path: relativePath,
          project: project.split('/').pop(),
          docType,
          lineCount: lines.length,
          wordCount: content.split(/\s+/).length,
          headingCount: headings,
          codeBlockCount: Math.floor(codeBlocks),
          linkCount: links,
          hash: hash(content),
          lastModified: (await fs.stat(file)).mtime.toISOString()
        });
      }
    }

    this.results.markdown = markdownFiles;
    log(`Found ${markdownFiles.length} markdown files`, 'success');
    return markdownFiles;
  }

  async scanCode() {
    log('Scanning code files...', 'info');

    const codeFiles = [];
    const extensions = ['.py', '.ts', '.tsx', '.js', '.jsx'];
    const excludeDirs = [
      'node_modules',
      '.git',
      '__pycache__',
      '.venv',
      'venv',
      'dist',
      'build',
      '.next',
      'coverage',
      '.svelte-kit',
      '.pytest_cache',
      'htmlcov',
      '.mypy_cache',
      '.tox',
      'eggs',
      '.cache',
      '.vercel',
      '.turbo',
      'vendor',
      '.nuxt',
      '.output',
      'out'
    ];

    for (const project of CONFIG.projects) {
      const projectPath = path.join(this.workspace, project);

      for (const ext of extensions) {
        const files = await this.findFiles(projectPath, ext, excludeDirs);

        for (const file of files) {
          const relativePath = path.relative(this.workspace, file).replace(/\\/g, '/');
          const content = await fs.readFile(file, 'utf-8');

          // Parse for functions/classes
          const stats = this.analyzeCode(content, ext);

          codeFiles.push({
            path: relativePath,
            project: project.split('/').pop(),
            type: ext.slice(1),
            lineCount: content.split('\n').length,
            ...stats
          });
        }
      }
    }

    this.results.code = codeFiles;
    log(`Found ${codeFiles.length} code files`, 'success');
    return codeFiles;
  }

  analyzeCode(content, ext) {
    const stats = {
      functionCount: 0,
      classCount: 0,
      documentedFunctions: 0,
      typedFunctions: 0
    };

    if (ext === '.py') {
      // Python analysis
      const funcMatches = content.match(/^(\s*)def\s+\w+\s*\(/gm) || [];
      const classMatches = content.match(/^class\s+\w+/gm) || [];
      const docstringAfterDef = content.match(/def\s+\w+[^:]+:\s*\n\s*"""/g) || [];
      const typeHints = content.match(/def\s+\w+\s*\([^)]*:\s*\w+[^)]*\)/g) || [];

      stats.functionCount = funcMatches.length;
      stats.classCount = classMatches.length;
      stats.documentedFunctions = docstringAfterDef.length;
      stats.typedFunctions = typeHints.length;
    } else if (['.ts', '.tsx', '.js', '.jsx'].includes(ext)) {
      // TypeScript/JavaScript analysis
      const funcMatches = content.match(/function\s+\w+|const\s+\w+\s*=\s*(?:async\s*)?\(/g) || [];
      const classMatches = content.match(/class\s+\w+/g) || [];
      const jsdocComments = content.match(/\/\*\*[\s\S]*?\*\/\s*(?:export\s+)?(?:async\s+)?(?:function|const|class)/g) || [];

      stats.functionCount = funcMatches.length;
      stats.classCount = classMatches.length;
      stats.documentedFunctions = jsdocComments.length;
      stats.typedFunctions = ext === '.ts' || ext === '.tsx' ? stats.functionCount : 0;
    }

    return stats;
  }

  async findFiles(dir, extension, excludeDirs = []) {
    const files = [];

    try {
      const entries = await fs.readdir(dir, { withFileTypes: true });

      for (const entry of entries) {
        const fullPath = path.join(dir, entry.name);

        if (entry.isDirectory()) {
          if (!excludeDirs.includes(entry.name)) {
            files.push(...await this.findFiles(fullPath, extension, excludeDirs));
          }
        } else if (entry.name.endsWith(extension)) {
          files.push(fullPath);
        }
      }
    } catch (e) {
      // Directory doesn't exist or isn't accessible
    }

    return files;
  }

  getProjectSummary() {
    const summary = {};

    for (const project of CONFIG.projects) {
      const projectName = project.split('/').pop();
      const mdFiles = this.results.markdown.filter(f => f.project === projectName);
      const codeFiles = this.results.code.filter(f => f.project === projectName);

      summary[projectName] = {
        markdownFiles: mdFiles.length,
        codeFiles: codeFiles.length,
        hasClaude: mdFiles.some(f => f.docType === 'CLAUDE.md'),
        hasState: mdFiles.some(f => f.docType === 'STATE'),
        hasVariable: mdFiles.some(f => f.docType === 'VARIABLE'),
        guideCount: mdFiles.filter(f => f.docType === 'GUIDE').length,
        totalFunctions: codeFiles.reduce((sum, f) => sum + f.functionCount, 0),
        documentedFunctions: codeFiles.reduce((sum, f) => sum + f.documentedFunctions, 0)
      };
    }

    return summary;
  }
}

// ============================================================================
// ANALYZER - Calculate quality scores
// ============================================================================
class QualityAnalyzer {
  constructor(scanResults) {
    this.scanResults = scanResults;
    this.scores = {};
  }

  analyzeAll() {
    log('Analyzing documentation quality...', 'info');

    for (const doc of this.scanResults.markdown) {
      this.scores[doc.path] = this.scoreDocument(doc);
    }

    log(`Analyzed ${Object.keys(this.scores).length} documents`, 'success');
    return this.scores;
  }

  scoreDocument(doc) {
    const scores = {
      completeness: this.scoreCompleteness(doc),
      structure: this.scoreStructure(doc),
      freshness: this.scoreFreshness(doc),
      consistency: this.scoreConsistency(doc),
      crossRefs: this.scoreCrossRefs(doc)
    };

    // Weighted average
    scores.overall = (
      scores.completeness * 0.30 +
      scores.structure * 0.25 +
      scores.freshness * 0.15 +
      scores.consistency * 0.15 +
      scores.crossRefs * 0.15
    );

    return scores;
  }

  scoreCompleteness(doc) {
    let score = 0.5; // Base score

    // Check line count against expectations
    const typeConfig = CONFIG.docTypes[doc.docType];
    if (typeConfig) {
      if (doc.lineCount >= (typeConfig.minLines || 0)) score += 0.2;
      if (typeConfig.maxLines && doc.lineCount <= typeConfig.maxLines) score += 0.1;
    }

    // Has code examples
    if (doc.codeBlockCount > 0) score += 0.1;

    // Has headings
    if (doc.headingCount >= 3) score += 0.1;

    return Math.min(1, score);
  }

  scoreStructure(doc) {
    let score = 0.4;

    // Has table of contents (for long docs)
    if (doc.lineCount > 100 && doc.linkCount > 5) score += 0.2;

    // Proper heading hierarchy
    if (doc.headingCount >= 3 && doc.headingCount <= 15) score += 0.2;

    // Has code blocks
    if (doc.codeBlockCount > 0) score += 0.2;

    return Math.min(1, score);
  }

  scoreFreshness(doc) {
    const daysSinceUpdate = (Date.now() - new Date(doc.lastModified).getTime()) / (1000 * 60 * 60 * 24);

    if (daysSinceUpdate < 7) return 1.0;
    if (daysSinceUpdate < 30) return 0.8;
    if (daysSinceUpdate < 90) return 0.6;
    if (daysSinceUpdate < 180) return 0.4;
    return 0.2;
  }

  scoreConsistency(doc) {
    // Real consistency scoring based on content analysis
    let score = 1.0;

    try {
      const content = require('fs').readFileSync(doc.path, 'utf-8');

      // 1. Check heading hierarchy (H1 should appear exactly once at top)
      const headings = content.match(/^(#{1,6})\s+.+$/gm) || [];
      const h1Count = headings.filter(h => h.startsWith('# ') && !h.startsWith('## ')).length;

      if (h1Count === 0) {
        score -= 0.15;
      } else if (h1Count > 1) {
        score -= 0.10;
      }

      // Check for skipped heading levels (e.g., H1 -> H3 without H2)
      const levels = headings.map(h => h.match(/^#+/)[0].length);
      for (let i = 1; i < levels.length; i++) {
        if (levels[i] - levels[i - 1] > 1) {
          score -= 0.05;
          break;
        }
      }

      // 2. Check code block language consistency
      const codeBlockFences = content.match(/^```[\w-]*$/gm) || [];
      const withLanguage = codeBlockFences.filter(f => f.length > 3).length;
      const totalBlocks = Math.floor(codeBlockFences.length / 2);
      const blocksWithoutLang = totalBlocks - withLanguage;

      if (totalBlocks > 0 && blocksWithoutLang > 0) {
        const ratio = blocksWithoutLang / totalBlocks;
        if (ratio > 0.5) {
          score -= 0.15;
        } else if (ratio > 0) {
          score -= 0.08;
        }
      }

      // 3. Check for bare URLs (not in markdown links)
      const bareUrls = content.match(/(?<![(\[])https?:\/\/[^\s)>\]]+/g) || [];
      if (bareUrls.length > 2) {
        score -= 0.10;
      }

      // 4. Check for consistent list formatting
      const bulletDash = (content.match(/^- /gm) || []).length;
      const bulletAsterisk = (content.match(/^\* /gm) || []).length;
      if (bulletDash > 0 && bulletAsterisk > 0) {
        score -= 0.05;
      }

    } catch (err) {
      return 0.6;
    }

    return Math.max(0, Math.min(1, score));
  }

  scoreCrossRefs(doc) {
    if (doc.linkCount === 0) return 0.3;
    if (doc.linkCount < 3) return 0.5;
    if (doc.linkCount < 10) return 0.8;
    return 1.0;
  }

  getProjectScores() {
    const projectScores = {};

    for (const project of CONFIG.projects) {
      const projectName = project.split('/').pop();
      const projectDocs = Object.entries(this.scores)
        .filter(([path]) => path.includes(projectName));

      if (projectDocs.length === 0) continue;

      const avgScore = projectDocs.reduce((sum, [, s]) => sum + s.overall, 0) / projectDocs.length;

      projectScores[projectName] = {
        documentCount: projectDocs.length,
        averageScore: Math.round(avgScore * 100) / 100,
        lowQualityDocs: projectDocs.filter(([, s]) => s.overall < 0.6).length
      };
    }

    return projectScores;
  }
}

// ============================================================================
// GENERATOR - Create missing documentation
// ============================================================================
class DocumentGenerator {
  constructor(workspace, scanResults) {
    this.workspace = workspace;
    this.scanResults = scanResults;
  }

  async generateMissing() {
    log('Checking for missing documentation...', 'info');

    const missing = this.findMissingDocs();

    for (const item of missing) {
      await this.generateDoc(item);
    }

    log(`Generated ${missing.length} missing documents`, 'success');
    return missing;
  }

  findMissingDocs() {
    const missing = [];

    for (const project of CONFIG.projects) {
      const projectName = project.split('/').pop();
      const projectDocs = this.scanResults.markdown.filter(f => f.project === projectName);

      // Check for CLAUDE.md
      if (!projectDocs.some(f => f.docType === 'CLAUDE.md')) {
        missing.push({ project, type: 'CLAUDE.md', path: `${project}/CLAUDE.md` });
      }

      // Check for STATE.md (GSD) - don't create VariableForClMD.md anymore
      const hasState = projectDocs.some(f => f.docType === 'STATE');
      const hasVariable = projectDocs.some(f => f.docType === 'VARIABLE');
      if (!hasState && !hasVariable) {
        missing.push({ project, type: 'STATE', path: `${project}/.planning/STATE.md` });
      }
    }

    return missing;
  }

  async generateDoc(item) {
    log(`Generating ${item.type} for ${item.project}...`, 'info');

    // Handle STATE type by creating full GSD structure
    if (item.type === 'STATE') {
      const projectPath = path.join(this.workspace, item.project);
      const stateCurator = new StateCurator(this.workspace);
      await stateCurator.createGsdState(projectPath, item.project);
      return;
    }

    const fullPath = path.join(this.workspace, item.path);
    let content;

    if (item.type === 'CLAUDE.md') {
      content = this.generateClaudeTemplate(item.project);
    }

    if (content) {
      await fs.mkdir(path.dirname(fullPath), { recursive: true });
      await fs.writeFile(fullPath, content, 'utf-8');
      log(`Created ${item.path}`, 'success');
    }
  }

  generateVariableTemplate(project) {
    const projectName = project.split('/').pop();
    const date = new Date().toISOString().split('T')[0];

    return `# ${projectName} - Session Context

**Last Updated:** ${date}
**Status:** Active Development

---

## Current Task

*No active task - awaiting instructions*

---

## Recent Changes

- Initial VariableForClMD.md created by Squeegee

---

## Session Notes

### Context
- Project documentation initialized
- Ready for development tasks

### Decisions Made
*None yet*

### Blockers
*None*

---

## Quick Links

- [CLAUDE.md](CLAUDE.md) - Project technical reference
- [README.md](README.md) - Project overview

---

*Generated by Squeegee Documentation System*
`;
  }

  generateClaudeTemplate(project) {
    const projectName = project.split('/').pop();
    const date = new Date().toISOString().split('T')[0];

    return `# ${projectName} - Claude Code Configuration

**Purpose:** [Project description needed]
**Status:** Active
**Last Updated:** ${date}

---

## Quick Reference

| Command | Description |
|---------|-------------|
| \`npm install\` | Install dependencies |
| \`npm run dev\` | Start development |
| \`npm run build\` | Build for production |
| \`npm test\` | Run tests |

---

## Tech Stack

- **Framework:** [To be documented]
- **Language:** [To be documented]
- **Database:** [To be documented]

---

## Architecture Overview

\`\`\`
[Architecture diagram needed]
\`\`\`

---

## Key Directories

| Directory | Purpose |
|-----------|---------|
| \`src/\` | Source code |
| \`tests/\` | Test files |
| \`docs/\` | Documentation |

---

## Environment Setup

Required environment variables:
\`\`\`bash
# Add environment variables here
\`\`\`

---

## Related Documentation

- [.planning/STATE.md](.planning/STATE.md) - Current session context (GSD format)

---

*Generated by Squeegee - needs manual completion*
`;
  }
}

// ============================================================================
// PLANS CURATOR - Manage and reconstruct PLANS_APPROVED.md files
// ============================================================================
class PlansCurator {
  constructor(workspace) {
    this.workspace = workspace;
    this.history = new HistoryManager(workspace);
  }

  async curateAll() {
    log('Curating plans across all projects...', 'info');

    const results = {
      created: [],
      updated: [],
      archived: []
    };

    for (const project of CONFIG.projects) {
      const projectPath = path.join(this.workspace, project);
      const plansPath = path.join(projectPath, 'PLANS_APPROVED.md');

      try {
        await fs.access(projectPath);
      } catch {
        continue; // Project doesn't exist
      }

      // Check if PLANS_APPROVED.md exists
      let exists = false;
      try {
        await fs.access(plansPath);
        exists = true;
      } catch {
        // File doesn't exist
      }

      if (!exists) {
        // Reconstruct from git history
        const plans = await this.reconstructFromGit(projectPath);
        await this.createPlansFile(plansPath, project, plans);
        results.created.push(project);
      } else {
        // Curate existing file
        const curated = await this.curateExisting(plansPath);
        if (curated.archived > 0) {
          results.archived.push({ project, count: curated.archived });
        }
        if (curated.updated) {
          results.updated.push(project);
        }
      }
    }

    log(`Created: ${results.created.length}, Updated: ${results.updated.length}, Archived: ${results.archived.length}`, 'success');
    return results;
  }

  async reconstructFromGit(projectPath) {
    const plans = [];

    try {
      // Get git log for this project directory
      const gitLog = execSync(
        `git log --oneline --since="2025-01-01" --all -- "${projectPath}"`,
        { cwd: this.workspace, encoding: 'utf-8', maxBuffer: 10 * 1024 * 1024, stdio: ['pipe', 'pipe', 'ignore'] }
      ).trim();

      if (!gitLog) return plans;

      const commits = gitLog.split('\n').filter(Boolean);

      // Group commits by date and look for significant changes
      const commitsByDate = {};
      for (const commit of commits) {
        const [hash, ...msgParts] = commit.split(' ');
        const msg = msgParts.join(' ');

        // Get commit date
        const dateStr = execSync(
          `git show -s --format=%ci ${hash}`,
          { cwd: this.workspace, encoding: 'utf-8', stdio: ['pipe', 'pipe', 'ignore'] }
        ).trim().split(' ')[0];

        if (!dateStr) continue;

        if (!commitsByDate[dateStr]) {
          commitsByDate[dateStr] = [];
        }
        commitsByDate[dateStr].push({ hash, msg });
      }

      // Convert significant commit groups to plans
      let planNum = 1;
      const sortedDates = Object.keys(commitsByDate).sort().reverse();

      for (const date of sortedDates) {
        const dayCommits = commitsByDate[date];

        // Look for feature/fix commits that represent plans
        const significantCommits = dayCommits.filter(c =>
          c.msg.match(/^(feat|fix|refactor|chore|docs)\(/i) ||
          c.msg.includes('implement') ||
          c.msg.includes('add') ||
          c.msg.includes('complete')
        );

        if (significantCommits.length > 0) {
          // Group into a plan
          const mainCommit = significantCommits[0];
          const planId = `PLAN-${date}-${String(planNum).padStart(2, '0')}`;

          // Extract title from commit message
          let title = mainCommit.msg;
          const typeMatch = title.match(/^(feat|fix|refactor|chore|docs)\(([^)]+)\):\s*(.+)/i);
          if (typeMatch) {
            title = typeMatch[3];
          }

          plans.push({
            id: planId,
            date: date,
            title: title.charAt(0).toUpperCase() + title.slice(1),
            status: 'Completed',
            commits: significantCommits.map(c => c.hash),
            summary: `Reconstructed from git: ${significantCommits.length} commit(s)`,
            decisions: significantCommits.map(c => `- ${c.msg}`).slice(0, 5)
          });

          planNum++;
        }
      }

      // Keep only recent plans
      return plans.slice(0, CONFIG.plans.maxRecentPlans);

    } catch (e) {
      log(`Git reconstruction failed for ${projectPath}: ${e.message}`, 'warn');
      return [];
    }
  }

  async createPlansFile(plansPath, project, plans) {
    const projectName = project.split('/').pop();
    const date = new Date().toISOString().split('T')[0];

    let content = `# ${projectName} - Plans Approved

**Last Updated:** ${date}
**Curated by:** Squeegee

---

## Recent Plans

`;

    if (plans.length === 0) {
      content += `*No plans recorded yet. Plans will be logged here when approved in Planning Mode.*

---

## Template

\`\`\`markdown
### [PLAN-YYYY-MM-DD-##] Title
**Approved:** YYYY-MM-DD
**Status:** Completed

#### Summary
Brief description.

#### Alternatives Considered
- Alternative 1: [Why not chosen]
- Alternative 2: [Why not chosen]

#### Decision Rationale
Why this approach was chosen over alternatives.

#### Constraints
- [Constraints that influenced the decision]

#### Key Decisions
- Decision 1

#### Success Metrics
- [ ] Metric 1: [How to measure success]

#### Result
Outcome of execution.

#### Learned Heuristics
- [Patterns or lessons for future reference]
\`\`\`

---

*Managed by Squeegee Documentation System*
`;
    } else {
      for (const plan of plans) {
        content += `### [${plan.id}] ${plan.title}
**Approved:** ${plan.date}
**Status:** ${plan.status}

#### Summary
${plan.summary}

#### Alternatives Considered
${plan.alternatives || '*Not recorded - reconstructed from git*'}

#### Decision Rationale
${plan.rationale || '*Not recorded - reconstructed from git*'}

#### Constraints
${plan.constraints || '*Not recorded*'}

#### Key Decisions
${plan.decisions.join('\n')}

#### Success Metrics
${plan.metrics || '*Not defined*'}

#### Result
${plan.commits ? `Commits: ${plan.commits.join(', ')}` : 'Completed successfully.'}

#### Learned Heuristics
${plan.heuristics || '*None captured yet*'}

---

`;
      }

      content += `
## Archive

*Older plans are archived automatically after ${CONFIG.plans.archiveAfterDays} days.*

---

*Managed by Squeegee Documentation System*
`;
    }

    await fs.mkdir(path.dirname(plansPath), { recursive: true });
    await fs.writeFile(plansPath, content, 'utf-8');
    log(`Created ${plansPath}`, 'success');
  }

  async curateExisting(plansPath) {
    const result = { archived: 0, updated: false };

    try {
      const content = await fs.readFile(plansPath, 'utf-8');
      const lines = content.split('\n');

      // Parse existing plans
      const planRegex = /^###\s*\[PLAN-(\d{4}-\d{2}-\d{2})-\d+\]/;
      const plans = [];
      let currentPlan = null;

      for (const line of lines) {
        const match = line.match(planRegex);
        if (match) {
          if (currentPlan) plans.push(currentPlan);
          currentPlan = { date: match[1], content: [line] };
        } else if (currentPlan) {
          currentPlan.content.push(line);
          if (line.startsWith('---')) {
            plans.push(currentPlan);
            currentPlan = null;
          }
        }
      }
      if (currentPlan) plans.push(currentPlan);

      // Check if any need archiving (older than archiveAfterDays)
      const cutoffDate = new Date();
      cutoffDate.setDate(cutoffDate.getDate() - CONFIG.plans.archiveAfterDays);

      const recentPlans = [];
      const archivedPlans = [];

      for (const plan of plans) {
        const planDate = new Date(plan.date);
        if (planDate < cutoffDate) {
          archivedPlans.push(plan);
        } else {
          recentPlans.push(plan);
        }
      }

      // Only keep maxRecentPlans
      if (recentPlans.length > CONFIG.plans.maxRecentPlans) {
        const toArchive = recentPlans.splice(CONFIG.plans.maxRecentPlans);
        archivedPlans.push(...toArchive);
      }

      result.archived = archivedPlans.length;

      // Update file if changes needed
      if (archivedPlans.length > 0) {
        result.updated = true;
        // Would rewrite file here - for now just log
        log(`Would archive ${archivedPlans.length} plans from ${plansPath}`, 'info');
      }

    } catch (e) {
      log(`Error curating ${plansPath}: ${e.message}`, 'warn');
    }

    return result;
  }
}

// ============================================================================
// CLAUDE.MD CURATOR - Update project CLAUDE.md files
// ============================================================================
class ClaudeMdCurator {
  constructor(workspace) {
    this.workspace = workspace;
    this.history = new HistoryManager(workspace);
  }

  async curateAll() {
    log('Curating project CLAUDE.md files...', 'info');

    const results = {
      created: [],
      updated: [],
      suggestions: []
    };

    for (const project of CONFIG.projects) {
      const projectPath = path.join(this.workspace, project);
      const claudePath = path.join(projectPath, 'CLAUDE.md');

      try {
        await fs.access(projectPath);
      } catch {
        continue;
      }

      let exists = false;
      try {
        await fs.access(claudePath);
        exists = true;
      } catch {}

      if (!exists) {
        // Generate new CLAUDE.md from project analysis
        await this.generateClaudeMd(claudePath, project);
        results.created.push(project);
      } else {
        // Analyze existing and suggest updates
        const suggestions = await this.analyzeAndSuggest(claudePath, projectPath, project);
        if (suggestions.length > 0) {
          results.suggestions.push({ project, suggestions });
        }
        results.updated.push(project);
      }
    }

    log(`Created: ${results.created.length}, Analyzed: ${results.updated.length}`, 'success');
    return results;
  }

  async generateClaudeMd(claudePath, project) {
    const projectPath = path.dirname(claudePath);
    const projectName = project.split('/').pop();
    const date = new Date().toISOString().split('T')[0];

    // Analyze project
    const analysis = await this.analyzeProject(projectPath);

    let content = `# ${projectName} - Claude Code Configuration

**Purpose:** ${analysis.description || '[Project description needed]'}
**Status:** Active
**Last Updated:** ${date}

---

## Quick Reference

| Command | Description |
|---------|-------------|
${analysis.commands.map(c => `| \`${c.cmd}\` | ${c.desc} |`).join('\n')}

---

## Tech Stack

${analysis.stack.map(s => `- **${s.name}:** ${s.version || 'latest'}`).join('\n')}

---

## Architecture Overview

\`\`\`
${analysis.structure}
\`\`\`

---

## Key Directories

| Directory | Purpose |
|-----------|---------|
${analysis.directories.map(d => `| \`${d.name}/\` | ${d.purpose} |`).join('\n')}

---

## Environment Setup

Required environment variables:
\`\`\`bash
${analysis.envVars.map(e => `${e}=`).join('\n')}
\`\`\`

---

## Related Documentation

- [.planning/STATE.md](.planning/STATE.md) - Current session context (GSD format)
- [PLANS_APPROVED.md](PLANS_APPROVED.md) - Plan history
- [PROGRAMMING_PRACTICES.md](PROGRAMMING_PRACTICES.md) - Code conventions

---

*Generated by Squeegee Documentation System*
`;

    await fs.writeFile(claudePath, content, 'utf-8');
    log(`Created ${claudePath}`, 'success');
  }

  async analyzeProject(projectPath) {
    const analysis = {
      description: '',
      commands: [],
      stack: [],
      structure: '',
      directories: [],
      envVars: []
    };

    // Check package.json
    try {
      const pkg = JSON.parse(await fs.readFile(path.join(projectPath, 'package.json'), 'utf-8'));
      analysis.description = pkg.description || '';

      // Extract commands from scripts
      if (pkg.scripts) {
        const commonScripts = ['dev', 'start', 'build', 'test', 'lint'];
        for (const script of commonScripts) {
          if (pkg.scripts[script]) {
            analysis.commands.push({ cmd: `npm run ${script}`, desc: `Run ${script}` });
          }
        }
      }

      // Extract stack from dependencies
      const deps = { ...pkg.dependencies, ...pkg.devDependencies };
      if (deps.react) analysis.stack.push({ name: 'React', version: deps.react });
      if (deps.next) analysis.stack.push({ name: 'Next.js', version: deps.next });
      if (deps.express) analysis.stack.push({ name: 'Express', version: deps.express });
      if (deps.typescript) analysis.stack.push({ name: 'TypeScript', version: deps.typescript });

    } catch {}

    // Check requirements.txt for Python
    try {
      const reqs = await fs.readFile(path.join(projectPath, 'requirements.txt'), 'utf-8');
      if (reqs.includes('fastapi')) analysis.stack.push({ name: 'FastAPI' });
      if (reqs.includes('django')) analysis.stack.push({ name: 'Django' });
      if (reqs.includes('flask')) analysis.stack.push({ name: 'Flask' });

      analysis.commands.push({ cmd: 'pip install -r requirements.txt', desc: 'Install dependencies' });
      analysis.commands.push({ cmd: 'python main.py', desc: 'Run application' });
    } catch {}

    // Analyze directory structure
    try {
      const dirs = await fs.readdir(projectPath, { withFileTypes: true });
      const dirNames = dirs.filter(d => d.isDirectory() && !d.name.startsWith('.')).map(d => d.name);

      const dirPurposes = {
        'src': 'Source code',
        'components': 'React components',
        'pages': 'Page components',
        'api': 'API routes/endpoints',
        'lib': 'Utility libraries',
        'utils': 'Utility functions',
        'hooks': 'React hooks',
        'services': 'Service layer',
        'models': 'Data models',
        'tests': 'Test files',
        'docs': 'Documentation',
        'public': 'Static assets',
        'assets': 'Media assets'
      };

      for (const dir of dirNames) {
        if (dirPurposes[dir]) {
          analysis.directories.push({ name: dir, purpose: dirPurposes[dir] });
        }
      }

      analysis.structure = dirNames.slice(0, 8).map(d => `├── ${d}/`).join('\n');
    } catch {}

    // Check for .env.example
    try {
      const envExample = await fs.readFile(path.join(projectPath, '.env.example'), 'utf-8');
      analysis.envVars = envExample.split('\n')
        .filter(l => l && !l.startsWith('#') && l.includes('='))
        .map(l => l.split('=')[0])
        .slice(0, 10);
    } catch {}

    // Defaults
    if (analysis.commands.length === 0) {
      analysis.commands = [
        { cmd: 'npm install', desc: 'Install dependencies' },
        { cmd: 'npm run dev', desc: 'Start development' }
      ];
    }

    if (analysis.directories.length === 0) {
      analysis.directories = [{ name: 'src', purpose: 'Source code' }];
    }

    return analysis;
  }

  async analyzeAndSuggest(claudePath, projectPath, project) {
    const suggestions = [];

    try {
      const content = await fs.readFile(claudePath, 'utf-8');

      // Check for placeholder text
      if (content.includes('[To be documented]') || content.includes('[Project description needed]')) {
        suggestions.push('Contains placeholder text that needs completion');
      }

      // Check last updated date
      const dateMatch = content.match(/Last Updated:\*?\*?\s*(\d{4}-\d{2}-\d{2})/);
      if (dateMatch) {
        const lastUpdated = new Date(dateMatch[1]);
        const daysSince = (Date.now() - lastUpdated.getTime()) / (1000 * 60 * 60 * 24);
        if (daysSince > 30) {
          suggestions.push(`Not updated in ${Math.floor(daysSince)} days`);
        }
      }

      // Check if package.json changed since CLAUDE.md
      try {
        const pkgStat = await fs.stat(path.join(projectPath, 'package.json'));
        const claudeStat = await fs.stat(claudePath);
        if (pkgStat.mtime > claudeStat.mtime) {
          suggestions.push('package.json modified after CLAUDE.md - may need stack update');
        }
      } catch {}

    } catch (e) {
      suggestions.push(`Error analyzing: ${e.message}`);
    }

    return suggestions;
  }
}

// ============================================================================
// VARIABLE CURATOR - DEPRECATED (kept for backward compatibility)
// Use GSDStateCurator for .planning/STATE.md instead
// ============================================================================
class VariableCurator {
  constructor(workspace) {
    this.workspace = workspace;
    this.history = new HistoryManager(workspace);
  }

  async curateAll() {
    log('Curating VariableForClMD.md files...', 'info');

    const results = {
      created: [],
      updated: []
    };

    for (const project of CONFIG.projects) {
      const projectPath = path.join(this.workspace, project);
      const variablePath = path.join(projectPath, 'VariableForClMD.md');

      try {
        await fs.access(projectPath);
      } catch {
        continue;
      }

      let exists = false;
      try {
        await fs.access(variablePath);
        exists = true;
      } catch {}

      if (!exists) {
        await this.generateVariable(variablePath, project);
        results.created.push(project);
      } else {
        const updated = await this.updateVariable(variablePath, projectPath, project);
        if (updated) {
          results.updated.push(project);
        }
      }
    }

    log(`Created: ${results.created.length}, Updated: ${results.updated.length}`, 'success');
    return results;
  }

  async generateVariable(variablePath, project) {
    const projectName = project.split('/').pop();
    const date = new Date().toISOString().split('T')[0];
    const time = new Date().toTimeString().slice(0, 5);
    const recentChanges = await this.getRecentChanges(path.dirname(variablePath));

    const content = `# ${projectName} - Session Context

**Last Updated:** ${date}
**Session Started:** ${date} ${time}
**Status:** Active Development

---

## Current Task

*No active task - awaiting instructions*

---

## Session Timeline

### ${time} - Session initialized
- Documentation system ready
- Context loaded from CLAUDE.md

---

## Recent Changes

${recentChanges.length > 0 ? recentChanges.map(c => `- ${c}`).join('\n') : '- Initial setup'}

---

## Active Decisions

*Decisions made this session that affect future work:*

---

## Blockers

*None*

---

## Next Actions

*What to do next:*

---

## Quick Links

- [CLAUDE.md](CLAUDE.md) - Project technical reference
- [PLANS_APPROVED.md](PLANS_APPROVED.md) - Plan history
- [PROGRAMMING_PRACTICES.md](PROGRAMMING_PRACTICES.md) - Code conventions

---

*Generated by Squeegee Documentation System*
`;

    await fs.writeFile(variablePath, content, 'utf-8');
    log(`Created ${variablePath}`, 'success');
  }

  /**
   * Add a timeline entry to an existing VariableForClMD.md file
   * @param {string} projectPath - Path to the project
   * @param {object} entry - Entry with title and details array
   */
  async addTimelineEntry(projectPath, entry) {
    const variablePath = path.join(projectPath, 'VariableForClMD.md');

    try {
      const content = await fs.readFile(variablePath, 'utf-8');

      const time = new Date().toTimeString().slice(0, 5);
      const newEntry = `### ${time} - ${entry.title}\n${entry.details.map(d => `- ${d}`).join('\n')}\n\n`;

      // Insert after "## Session Timeline" header
      if (content.includes('## Session Timeline')) {
        const updated = content.replace(
          /## Session Timeline\n\n/,
          `## Session Timeline\n\n${newEntry}`
        );

        // Update last updated timestamp
        const date = new Date().toISOString().split('T')[0];
        const finalContent = updated.replace(
          /\*\*Last Updated:\*\*\s*\d{4}-\d{2}-\d{2}/,
          `**Last Updated:** ${date}`
        );

        await fs.writeFile(variablePath, finalContent, 'utf-8');
        return true;
      }
    } catch (e) {
      log(`Error adding timeline entry: ${e.message}`, 'warn');
    }

    return false;
  }

  /**
   * Calculate session duration from VariableForClMD.md
   */
  async getSessionDuration(variablePath) {
    try {
      const content = await fs.readFile(variablePath, 'utf-8');
      const startMatch = content.match(/\*\*Session Started:\*\*\s*(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})/);

      if (startMatch) {
        const startTime = new Date(`${startMatch[1]}T${startMatch[2]}:00`);
        const durationMs = Date.now() - startTime.getTime();
        const hours = Math.floor(durationMs / (1000 * 60 * 60));
        const minutes = Math.floor((durationMs % (1000 * 60 * 60)) / (1000 * 60));
        return `${hours}h ${minutes}m`;
      }
    } catch {}

    return 'Unknown';
  }

  async updateVariable(variablePath, projectPath, project) {
    try {
      const content = await fs.readFile(variablePath, 'utf-8');
      const recentChanges = await this.getRecentChanges(projectPath);

      // Check if "Recent Changes" section is stale
      const hasRecentSection = content.includes('## Recent Changes');
      if (!hasRecentSection || recentChanges.length === 0) {
        return false;
      }

      // Parse existing recent changes
      const existingChanges = content.match(/## Recent Changes\n\n([\s\S]*?)(?=\n---|\n##)/);
      if (existingChanges) {
        const existingList = existingChanges[1].trim();
        const newChangesList = recentChanges.map(c => `- ${c}`).join('\n');

        // Only update if changes are different
        if (existingList !== newChangesList) {
          // Archive current version before updating
          await this.history.archive(variablePath, 'recent changes update');

          const date = new Date().toISOString().split('T')[0];
          let newContent = content.replace(
            /\*\*Last Updated:\*\*\s*\d{4}-\d{2}-\d{2}/,
            `**Last Updated:** ${date}`
          );
          newContent = newContent.replace(
            /## Recent Changes\n\n[\s\S]*?(?=\n---|\n##)/,
            `## Recent Changes\n\n${newChangesList}\n\n`
          );

          await fs.writeFile(variablePath, newContent, 'utf-8');
          return true;
        }
      }

      return false;
    } catch (e) {
      log(`Error updating ${variablePath}: ${e.message}`, 'warn');
      return false;
    }
  }

  async getRecentChanges(projectPath) {
    const changes = [];

    try {
      const gitLog = execSync(
        `git log --oneline -10 -- "${projectPath}"`,
        { cwd: this.workspace, encoding: 'utf-8', stdio: ['pipe', 'pipe', 'ignore'] }
      ).trim();

      if (gitLog) {
        const commits = gitLog.split('\n').filter(Boolean);
        for (const commit of commits.slice(0, 5)) {
          const [hash, ...msgParts] = commit.split(' ');
          let msg = msgParts.join(' ');

          // Clean up conventional commit format
          msg = msg.replace(/^(feat|fix|chore|docs|refactor|test)\([^)]+\):\s*/, '');
          changes.push(msg.charAt(0).toUpperCase() + msg.slice(1));
        }
      }
    } catch {}

    return changes;
  }
}

// ============================================================================
// GSD STATE CURATOR - Unified management for VariableForClMD.md and GSD STATE.md
// ============================================================================
class StateCurator {
  constructor(workspace) {
    this.workspace = workspace;
    this.history = new HistoryManager(workspace);
    this.variableCurator = new VariableCurator(workspace);
  }

  async fileExists(filePath) {
    try {
      await fs.access(filePath);
      return true;
    } catch {
      return false;
    }
  }

  async curateAll() {
    log('Curating GSD session state files (.planning/STATE.md)...', 'info');

    const results = {
      created: [],
      updated: [],
      skipped: [],
      warnings: []
    };

    for (const project of CONFIG.projects) {
      const projectPath = path.join(this.workspace, project);

      try {
        await fs.access(projectPath);
      } catch {
        continue;
      }

      const gsdPath = path.join(projectPath, '.planning', 'STATE.md');
      const legacyPath = path.join(projectPath, 'VariableForClMD.md');

      const hasGsd = await this.fileExists(gsdPath);
      const hasLegacy = await this.fileExists(legacyPath);

      if (hasGsd) {
        // GSD mode: update STATE.md
        const updated = await this.updateState(gsdPath, projectPath, project);
        if (updated) results.updated.push(project);
      } else {
        // No STATE.md - create GSD structure
        if (hasLegacy) {
          results.warnings.push({
            project,
            message: 'Legacy VariableForClMD.md found but no STATE.md. Run "migrate-gsd" to migrate, or create .planning/STATE.md manually.'
          });
          results.skipped.push(project);
        } else {
          await this.createGsdState(projectPath, project);
          results.created.push(project);
        }
      }
    }

    log(`Created: ${results.created.length}, Updated: ${results.updated.length}`, 'success');
    if (results.warnings.length > 0) {
      log(`${results.warnings.length} projects need migration from legacy format`, 'warn');
    }
    if (results.skipped.length > 0) {
      log(`Skipped ${results.skipped.length} projects with legacy format only`, 'warn');
    }
    return results;
  }

  async updateState(statePath, projectPath, project) {
    try {
      const content = await fs.readFile(statePath, 'utf-8');
      const recentChanges = await this.variableCurator.getRecentChanges(projectPath);
      const phaseStatus = await this.getPhaseStatus(projectPath);

      let updated = false;
      let newContent = content;

      // Update "Last Updated" timestamp
      const date = new Date().toISOString().split('T')[0];
      if (!content.includes(`**Last Updated:** ${date}`)) {
        newContent = newContent.replace(
          /\*\*Last Updated:\*\*\s*\d{4}-\d{2}-\d{2}/,
          `**Last Updated:** ${date}`
        );
        updated = true;
      }

      // Update phase progress if phases exist
      if (phaseStatus.currentPhase && !content.includes(`**Current Phase:** ${phaseStatus.currentPhase}`)) {
        newContent = newContent.replace(
          /\*\*Current Phase:\*\*\s*.*/,
          `**Current Phase:** ${phaseStatus.currentPhase}`
        );
        updated = true;
      }

      if (updated) {
        await this.history.archive(statePath, 'state update');
        await fs.writeFile(statePath, newContent, 'utf-8');
      }

      return updated;
    } catch (e) {
      log(`Error updating ${statePath}: ${e.message}`, 'warn');
      return false;
    }
  }

  async getPhaseStatus(projectPath) {
    const phasesDir = path.join(projectPath, '.planning', 'phases');
    const status = {
      currentPhase: null,
      phases: [],
      completedCount: 0,
      totalCount: 0
    };

    try {
      const entries = await fs.readdir(phasesDir, { withFileTypes: true });

      for (const entry of entries) {
        if (entry.isDirectory()) {
          const phasePath = path.join(phasesDir, entry.name);
          const hasPlan = await this.fileExists(path.join(phasePath, 'PLAN.md'));
          const hasSummary = await this.fileExists(path.join(phasePath, 'SUMMARY.md'));

          status.phases.push({
            name: entry.name,
            hasPlan,
            hasSummary,
            completed: hasSummary
          });

          status.totalCount++;
          if (hasSummary) status.completedCount++;

          // Current phase is the first one with PLAN but no SUMMARY
          if (!status.currentPhase && hasPlan && !hasSummary) {
            status.currentPhase = entry.name;
          }
        }
      }
    } catch {
      // No phases directory yet
    }

    return status;
  }

  async createGsdState(projectPath, project) {
    const projectName = project.split('/').pop();
    const date = new Date().toISOString().split('T')[0];

    // Create .planning directory structure
    const gsdDir = path.join(projectPath, '.planning');
    const phasesDir = path.join(gsdDir, 'phases');
    await fs.mkdir(phasesDir, { recursive: true });

    // Generate STATE.md
    const stateContent = this.generateStateTemplate(projectName, date);
    await fs.writeFile(path.join(gsdDir, 'STATE.md'), stateContent);

    // Generate ISSUES.md
    const issuesContent = this.generateIssuesTemplate(projectName, date);
    await fs.writeFile(path.join(gsdDir, 'ISSUES.md'), issuesContent);

    // Generate ROADMAP.md
    const roadmapContent = this.generateRoadmapTemplate(projectName, date);
    await fs.writeFile(path.join(gsdDir, 'ROADMAP.md'), roadmapContent);

    log(`Created GSD structure for ${project}`, 'success');
  }

  generateStateTemplate(projectName, date) {
    return `# ${projectName} - Project State

**Last Updated:** ${date}
**Status:** Active Development
**Current Phase:** N/A (No phases defined yet)

---

## Current Focus

*No active task - awaiting instructions*

---

## Progress

### Completed
- GSD structure initialized

### In Progress
*None*

### Blocked
*None*

---

## Blockers

*No current blockers.*

---

## Key Decisions

*Key project decisions will be tracked here.*

---

## Recent Activity

- GSD structure created by Squeegee

---

## Quick Links

- [ROADMAP.md](ROADMAP.md) - Project roadmap
- [ISSUES.md](ISSUES.md) - Deferred work and issues
- [CLAUDE.md](../CLAUDE.md) - Project technical reference

---

*Generated by Squeegee Documentation System*
`;
  }

  generateIssuesTemplate(projectName, date) {
    return `# ${projectName} - Issues & Deferred Work

**Last Updated:** ${date}
**Managed by:** Squeegee

---

## Deferred Items

*No deferred items.*

---

## Known Issues

*Issues discovered during development:*

---

## Future Enhancements

*None captured yet.*

---

*Generated by Squeegee Documentation System*
`;
  }

  generateRoadmapTemplate(projectName, date) {
    return `# ${projectName} - Roadmap

**Last Updated:** ${date}
**Status:** Draft (needs completion)

---

## Vision

*Define the long-term vision for this project.*

---

## Phases

### Phase 1: [Name TBD]
**Status:** Not Started
**Target:** TBD

*Define phase objectives and success criteria.*

---

## Success Metrics

- [ ] Metric 1: [Define]
- [ ] Metric 2: [Define]

---

## Dependencies

*External dependencies and blockers:*

---

*Generated by Squeegee Documentation System*
`;
  }
}

// ============================================================================
// GSD ANALYZER - Analyze GSD artifacts and plan quality
// ============================================================================
class GsdAnalyzer {
  constructor(workspace) {
    this.workspace = workspace;
  }

  async fileExists(filePath) {
    try {
      await fs.access(filePath);
      return true;
    } catch {
      return false;
    }
  }

  async analyzeAll() {
    log('Analyzing GSD artifacts...', 'info');
    const results = {};

    for (const project of CONFIG.projects) {
      const projectPath = path.join(this.workspace, project);
      const planningDir = path.join(projectPath, '.planning');

      try {
        await fs.access(planningDir);
      } catch {
        continue; // No GSD structure
      }

      results[project] = await this.analyzeProject(projectPath);
    }

    return results;
  }

  async analyzeProject(projectPath) {
    const planningDir = path.join(projectPath, '.planning');
    const phasesDir = path.join(planningDir, 'phases');

    const analysis = {
      hasState: await this.fileExists(path.join(planningDir, 'STATE.md')),
      hasRoadmap: await this.fileExists(path.join(planningDir, 'ROADMAP.md')),
      hasIssues: await this.fileExists(path.join(planningDir, 'ISSUES.md')),
      phaseCount: 0,
      completedPhases: 0,
      planQuality: null,
      learnings: []
    };

    try {
      const phases = await fs.readdir(phasesDir, { withFileTypes: true });

      for (const phase of phases) {
        if (!phase.isDirectory()) continue;

        analysis.phaseCount++;
        const phasePath = path.join(phasesDir, phase.name);

        // Check for SUMMARY.md (completed phase)
        if (await this.fileExists(path.join(phasePath, 'SUMMARY.md'))) {
          analysis.completedPhases++;

          // Extract learnings from SUMMARY.md
          const summaryContent = await fs.readFile(path.join(phasePath, 'SUMMARY.md'), 'utf-8');
          const phaseLearnings = this.extractLearnings(summaryContent, phase.name);
          analysis.learnings.push(...phaseLearnings);
        }

        // Analyze PLAN.md quality
        const planPath = path.join(phasePath, 'PLAN.md');
        if (await this.fileExists(planPath)) {
          const planContent = await fs.readFile(planPath, 'utf-8');
          const planQuality = this.calculatePlanQuality(planContent);
          if (!analysis.planQuality) {
            analysis.planQuality = planQuality;
          } else {
            // Average with existing
            for (const key of Object.keys(planQuality)) {
              analysis.planQuality[key] = (analysis.planQuality[key] + planQuality[key]) / 2;
            }
          }
        }
      }
    } catch {
      // No phases directory
    }

    return analysis;
  }

  extractLearnings(content, phaseName) {
    const learnings = [];

    // Extract "What Worked" section
    const workedMatch = content.match(/##\s*What Worked[\s\S]*?(?=##|$)/i);
    if (workedMatch) {
      const items = workedMatch[0].match(/^[-*]\s+(.+)$/gm) || [];
      for (const item of items) {
        learnings.push({
          type: 'succeeded',
          text: item.replace(/^[-*]\s+/, ''),
          phase: phaseName
        });
      }
    }

    // Extract "What Didn't Work" section
    const failedMatch = content.match(/##\s*What Didn't(?:\s+Work)?[\s\S]*?(?=##|$)/i);
    if (failedMatch) {
      const items = failedMatch[0].match(/^[-*]\s+(.+)$/gm) || [];
      for (const item of items) {
        learnings.push({
          type: 'failed',
          text: item.replace(/^[-*]\s+/, ''),
          phase: phaseName
        });
      }
    }

    // Extract "Learned Heuristics" section
    const heuristicsMatch = content.match(/##\s*Learned Heuristics[\s\S]*?(?=##|$)/i);
    if (heuristicsMatch) {
      const items = heuristicsMatch[0].match(/^[-*]\s+(.+)$/gm) || [];
      for (const item of items) {
        learnings.push({
          type: 'heuristic',
          text: item.replace(/^[-*]\s+/, ''),
          phase: phaseName
        });
      }
    }

    return learnings;
  }

  calculatePlanQuality(planContent) {
    const quality = {
      taskClarity: 0,
      checkpointCoverage: 0,
      deviationFrequency: 1, // Start high (inverted metric)
      completionRate: 0,
      overall: 0
    };

    // Extract tasks (checkbox items)
    const tasks = planContent.match(/^[-*]\s*\[([ x])\]\s*(.+)$/gm) || [];
    const completedTasks = tasks.filter(t => t.includes('[x]'));

    // Extract checkpoints
    const checkpoints = planContent.match(/###\s*Checkpoint|checkpoint:/gi) || [];

    // Extract deviations
    const deviations = planContent.match(/DEVIATION:|deviated|changed approach/gi) || [];

    // Calculate metrics
    if (tasks.length > 0) {
      // Task clarity: based on task description length
      const avgTaskLength = tasks.reduce((sum, t) => sum + t.length, 0) / tasks.length;
      quality.taskClarity = Math.min(1, avgTaskLength / 80); // 80 chars = good clarity

      // Checkpoint coverage: 1 checkpoint per 3-4 tasks is ideal
      const idealRatio = 0.25;
      const actualRatio = checkpoints.length / tasks.length;
      quality.checkpointCoverage = Math.min(1, actualRatio / idealRatio);

      // Deviation frequency (inverted - fewer is better)
      const deviationRate = deviations.length / tasks.length;
      quality.deviationFrequency = Math.max(0, 1 - deviationRate);

      // Completion rate
      quality.completionRate = completedTasks.length / tasks.length;
    }

    // Overall weighted score
    quality.overall =
      quality.taskClarity * 0.25 +
      quality.checkpointCoverage * 0.20 +
      quality.deviationFrequency * 0.20 +
      quality.completionRate * 0.35;

    return quality;
  }

  async report() {
    const results = await this.analyzeAll();

    console.log('\n📋 GSD Analysis Summary:');
    console.log('───────────────────────────────────────');

    for (const [project, analysis] of Object.entries(results)) {
      console.log(`\n📁 ${project}:`);
      console.log(`   State: ${analysis.hasState ? '✅' : '❌'}`);
      console.log(`   Roadmap: ${analysis.hasRoadmap ? '✅' : '❌'}`);
      console.log(`   Phases: ${analysis.phaseCount} (${analysis.completedPhases} completed)`);

      if (analysis.planQuality) {
        console.log(`   Plan Quality: ${Math.round(analysis.planQuality.overall * 100)}%`);
        console.log(`     - Task Clarity: ${Math.round(analysis.planQuality.taskClarity * 100)}%`);
        console.log(`     - Checkpoint Coverage: ${Math.round(analysis.planQuality.checkpointCoverage * 100)}%`);
        console.log(`     - Completion Rate: ${Math.round(analysis.planQuality.completionRate * 100)}%`);
      }

      if (analysis.learnings.length > 0) {
        console.log(`   Learnings Extracted: ${analysis.learnings.length}`);
      }
    }

    console.log('');
  }
}

// ============================================================================
// GSD MIGRATOR - Migrate VariableForClMD.md to GSD STATE.md
// ============================================================================
class GsdMigrator {
  constructor(workspace) {
    this.workspace = workspace;
    this.history = new HistoryManager(workspace);
  }

  async fileExists(filePath) {
    try {
      await fs.access(filePath);
      return true;
    } catch {
      return false;
    }
  }

  async migrateAll() {
    log('Migrating VariableForClMD.md files to GSD STATE.md...', 'info');

    const results = {
      migrated: [],
      skipped: []
    };

    for (const project of CONFIG.projects) {
      const projectPath = path.join(this.workspace, project);
      const variablePath = path.join(projectPath, 'VariableForClMD.md');
      const gsdDir = path.join(projectPath, '.planning');
      const statePath = path.join(gsdDir, 'STATE.md');

      const hasVariable = await this.fileExists(variablePath);
      const hasState = await this.fileExists(statePath);

      if (hasState) {
        results.skipped.push({ project, reason: 'Already has STATE.md' });
        continue;
      }

      if (!hasVariable) {
        results.skipped.push({ project, reason: 'No VariableForClMD.md to migrate' });
        continue;
      }

      await this.migrateProject(projectPath, project);
      results.migrated.push(project);
    }

    // Report results
    console.log('\n📋 GSD Migration Summary:');
    console.log('───────────────────────────────────────');

    if (results.migrated.length > 0) {
      console.log('\n✅ Successfully migrated:');
      for (const project of results.migrated) {
        console.log(`   - ${project}`);
      }
    }

    if (results.skipped?.length > 0) {
      console.log('\n⏭️  Skipped:');
      for (const { project, reason } of results.skipped) {
        console.log(`   - ${project}: ${reason}`);
      }
    }

    console.log('');
    return results;
  }

  async migrateProject(projectPath, project) {
    const variablePath = path.join(projectPath, 'VariableForClMD.md');
    const variableContent = await fs.readFile(variablePath, 'utf-8');
    const projectName = project.split('/').pop();
    const date = new Date().toISOString().split('T')[0];

    // Parse existing content
    const parsed = this.parseVariableContent(variableContent);

    // Create GSD directory structure
    const gsdDir = path.join(projectPath, '.planning');
    const phasesDir = path.join(gsdDir, 'phases');
    await fs.mkdir(phasesDir, { recursive: true });

    // Generate STATE.md
    const stateContent = this.generateState(parsed, projectName, date);
    await fs.writeFile(path.join(gsdDir, 'STATE.md'), stateContent);

    // Generate ISSUES.md
    const issuesContent = this.generateIssues(parsed, projectName, date);
    await fs.writeFile(path.join(gsdDir, 'ISSUES.md'), issuesContent);

    // Generate stub ROADMAP.md
    const roadmapContent = this.generateRoadmap(projectName, date);
    await fs.writeFile(path.join(gsdDir, 'ROADMAP.md'), roadmapContent);

    // Archive original to history
    await this.history.archive(variablePath, 'migrated to GSD');

    // Delete or keep backup based on config
    const config = await this.loadConfig();
    if (config?.gsd?.deleteAfterMigration) {
      await fs.unlink(variablePath);
      log(`Deleted ${variablePath} after migration`, 'info');
    } else if (config?.gsd?.keepVariableAsBackup === false) {
      await fs.unlink(variablePath);
      log(`Deleted ${variablePath} (keepVariableAsBackup: false)`, 'info');
    } else {
      await fs.rename(variablePath, variablePath + '.migrated.bak');
      log(`Backed up ${variablePath} as .migrated.bak`, 'info');
    }

    log(`Migrated ${project} to GSD structure`, 'success');
  }

  async loadConfig() {
    try {
      const configPath = path.join(this.workspace, 'squeegee.config.json');
      const content = await fs.readFile(configPath, 'utf-8');
      return JSON.parse(content);
    } catch {
      return null;
    }
  }

  parseVariableContent(content) {
    const parsed = {
      lastUpdated: null,
      currentTask: null,
      recentChanges: [],
      activeDecisions: null,
      blockers: [],
      nextActions: []
    };

    // Extract Last Updated
    const dateMatch = content.match(/\*\*Last Updated:\*\*\s*(\d{4}-\d{2}-\d{2})/);
    if (dateMatch) parsed.lastUpdated = dateMatch[1];

    // Extract Current Task section
    const taskMatch = content.match(/## Current Task[\s\S]*?(?=\n## |$)/);
    if (taskMatch) {
      parsed.currentTask = taskMatch[0].replace(/## Current Task\s*\n/, '').trim();
    }

    // Extract Recent Changes section
    const changesMatch = content.match(/## Recent Changes[\s\S]*?(?=\n## |$)/);
    if (changesMatch) {
      const items = changesMatch[0].match(/^[-*]\s+(.+)$/gm) || [];
      parsed.recentChanges = items.map(i => i.replace(/^[-*]\s+/, ''));
    }

    // Extract Blockers
    const blockersMatch = content.match(/## Blockers[\s\S]*?(?=\n## |$)/i);
    if (blockersMatch) {
      const items = blockersMatch[0].match(/^[-*]\s+(.+)$/gm) || [];
      parsed.blockers = items.map(i => i.replace(/^[-*]\s+/, ''));
    }

    // Extract Active Decisions
    const decisionsMatch = content.match(/## (?:Active|Key) Decisions[\s\S]*?(?=\n## |$)/i);
    if (decisionsMatch) {
      parsed.activeDecisions = decisionsMatch[0].replace(/## (?:Active|Key) Decisions\s*\n/i, '').trim();
    }

    // Extract Next Actions
    const actionsMatch = content.match(/## Next Actions[\s\S]*?(?=\n## |$)/i);
    if (actionsMatch) {
      const items = actionsMatch[0].match(/^[-*\d.]\s+(.+)$/gm) || [];
      parsed.nextActions = items.map(i => i.replace(/^[-*\d.]\s+/, ''));
    }

    return parsed;
  }

  generateState(parsed, projectName, date) {
    return `# ${projectName} - Project State

**Last Updated:** ${date}
**Migrated From:** VariableForClMD.md
**Status:** Active Development
**Current Phase:** N/A (No phases defined yet)

---

## Current Focus

${parsed.currentTask || '*Migrated from VariableForClMD.md - update with current focus*'}

---

## Progress

### Completed
- Migrated from VariableForClMD.md to GSD structure

### In Progress
${parsed.nextActions.length > 0
  ? parsed.nextActions.slice(0, 5).map(a => `- ${a}`).join('\n')
  : '*Update with current work*'}

### Blocked
${parsed.blockers.length > 0 && !parsed.blockers[0].toLowerCase().includes('none')
  ? parsed.blockers.map(b => `- ${b}`).join('\n')
  : '*None*'}

---

## Blockers

${parsed.blockers.length > 0 && !parsed.blockers[0].toLowerCase().includes('none')
  ? parsed.blockers.map(b => `- ${b}`).join('\n')
  : '*No current blockers.*'}

---

## Key Decisions

${parsed.activeDecisions || '*Migrated - update with key project decisions*'}

---

## Recent Activity

${parsed.recentChanges.length > 0
  ? parsed.recentChanges.map(c => `- ${c}`).join('\n')
  : '- Migrated to GSD structure'}

---

## Quick Links

- [ROADMAP.md](ROADMAP.md) - Project roadmap
- [ISSUES.md](ISSUES.md) - Deferred work and issues
- [CLAUDE.md](../CLAUDE.md) - Project technical reference

---

*Migrated by Squeegee from VariableForClMD.md on ${date}*
`;
  }

  generateIssues(parsed, projectName, date) {
    return `# ${projectName} - Issues & Deferred Work

**Last Updated:** ${date}
**Managed by:** Squeegee

---

## Deferred Items

${parsed.blockers.length > 0 && !parsed.blockers[0].toLowerCase().includes('none')
  ? parsed.blockers.map(b => `- [ ] ${b}`).join('\n')
  : '*No deferred items.*'}

---

## Known Issues

*Issues discovered during development:*

---

## Future Enhancements

${parsed.nextActions.length > 5
  ? parsed.nextActions.slice(5).map(a => `- [ ] ${a}`).join('\n')
  : '*None captured yet.*'}

---

*Migrated by Squeegee from VariableForClMD.md on ${date}*
`;
  }

  generateRoadmap(projectName, date) {
    return `# ${projectName} - Roadmap

**Last Updated:** ${date}
**Status:** Draft (needs completion)

---

## Vision

*Define the long-term vision for this project.*

---

## Phases

### Phase 1: [Name TBD]
**Status:** Not Started
**Target:** TBD

*Define phase objectives and success criteria.*

---

## Success Metrics

- [ ] Metric 1: [Define]
- [ ] Metric 2: [Define]

---

## Dependencies

*External dependencies and blockers:*

---

*Created by Squeegee migration on ${date}*
`;
  }
}

// ============================================================================
// GSD ISSUE TRACKER - Analyze ISSUES.md across projects
// ============================================================================
class GsdIssueTracker {
  constructor(workspace) {
    this.workspace = workspace;
  }

  async fileExists(filePath) {
    try {
      await fs.access(filePath);
      return true;
    } catch {
      return false;
    }
  }

  async analyzeAll() {
    log('Analyzing GSD issues and deferred work...', 'info');
    const results = {};

    for (const project of CONFIG.projects) {
      const projectPath = path.join(this.workspace, project);
      const issuesPath = path.join(projectPath, '.planning', 'ISSUES.md');

      if (await this.fileExists(issuesPath)) {
        results[project] = await this.analyzeIssues(issuesPath);
      }
    }

    return results;
  }

  async analyzeIssues(issuesPath) {
    const content = await fs.readFile(issuesPath, 'utf-8');
    const stats = await fs.stat(issuesPath);
    const daysSinceUpdate = Math.floor((Date.now() - stats.mtime) / (1000 * 60 * 60 * 24));

    const analysis = {
      openCount: 0,
      staleCount: 0,
      fromPlans: 0,
      staleItems: []
    };

    // Count open items (unchecked checkboxes)
    const openItems = content.match(/^[-*]\s*\[ \]\s*(.+)$/gm) || [];
    analysis.openCount = openItems.length;

    // Check for stale items (file not updated in 30+ days)
    if (daysSinceUpdate > 30) {
      analysis.staleCount = analysis.openCount;
      for (const item of openItems) {
        analysis.staleItems.push({
          title: item.replace(/^[-*]\s*\[ \]\s*/, '').slice(0, 50),
          daysStale: daysSinceUpdate
        });
      }
    }

    // Count items from plan deviations
    const fromPlans = content.match(/\(from plan|deviation|deferred from/gi) || [];
    analysis.fromPlans = fromPlans.length;

    return analysis;
  }

  async report() {
    const results = await this.analyzeAll();

    console.log('\n📋 GSD Issues Summary:');
    console.log('───────────────────────────────────────');

    for (const [project, issues] of Object.entries(results)) {
      console.log(`\n📁 ${project}:`);
      console.log(`   Open Issues: ${issues.openCount}`);
      console.log(`   Stale Issues: ${issues.staleCount}`);
      console.log(`   From Plans: ${issues.fromPlans}`);

      if (issues.staleItems.length > 0) {
        console.log('   ⚠️  Stale items:');
        for (const item of issues.staleItems.slice(0, 3)) {
          console.log(`      - ${item.title}... (${item.daysStale} days)`);
        }
      }
    }

    console.log('');
  }
}

// ============================================================================
// PRACTICES CURATOR - Manage PROGRAMMING_PRACTICES.md files
// ============================================================================
class PracticesCurator {
  constructor(workspace) {
    this.workspace = workspace;
    this.history = new HistoryManager(workspace);
  }

  async curateAll() {
    log('Curating programming practices across all projects...', 'info');

    const results = {
      created: [],
      updated: []
    };

    for (const project of CONFIG.projects) {
      const projectPath = path.join(this.workspace, project);
      const practicesPath = path.join(projectPath, 'PROGRAMMING_PRACTICES.md');

      try {
        await fs.access(projectPath);
      } catch {
        continue; // Project doesn't exist
      }

      // Check if PROGRAMMING_PRACTICES.md exists
      let exists = false;
      try {
        await fs.access(practicesPath);
        exists = true;
      } catch {
        // File doesn't exist
      }

      if (!exists) {
        // Analyze project and create practices file
        const practices = await this.analyzeProject(projectPath, project);
        await this.createPracticesFile(practicesPath, project, practices);
        results.created.push(project);
      } else {
        // Could update existing - for now just report
        results.updated.push(project);
      }
    }

    log(`Created: ${results.created.length}, Existing: ${results.updated.length}`, 'success');
    return results;
  }

  async analyzeProject(projectPath, project) {
    const practices = {
      stack: [],
      patterns: [],
      conventions: [],
      dependencies: [],
      testing: []
    };

    try {
      // Detect tech stack from package.json
      const packageJsonPath = path.join(projectPath, 'package.json');
      try {
        const pkg = JSON.parse(await fs.readFile(packageJsonPath, 'utf-8'));
        practices.stack.push(`Node.js project: ${pkg.name || 'unnamed'}`);

        // Extract key dependencies
        const deps = { ...pkg.dependencies, ...pkg.devDependencies };
        if (deps.react) practices.stack.push('React');
        if (deps.next) practices.stack.push('Next.js');
        if (deps['react-native']) practices.stack.push('React Native');
        if (deps.expo) practices.stack.push('Expo');
        if (deps.express) practices.stack.push('Express');
        if (deps.fastify) practices.stack.push('Fastify');
        if (deps.typescript) practices.conventions.push('TypeScript enabled');
        if (deps.tailwindcss) practices.conventions.push('Tailwind CSS for styling');
        if (deps.jest) practices.testing.push('Jest for testing');
        if (deps.vitest) practices.testing.push('Vitest for testing');
        if (deps.eslint) practices.conventions.push('ESLint for linting');
        if (deps.prettier) practices.conventions.push('Prettier for formatting');

        // Store key dependencies
        const keyDeps = Object.keys(deps).filter(d =>
          !d.startsWith('@types/') && !d.startsWith('eslint')
        ).slice(0, 15);
        practices.dependencies = keyDeps;

      } catch {
        // No package.json
      }

      // Detect Python project from requirements.txt or pyproject.toml
      const requirementsPath = path.join(projectPath, 'requirements.txt');
      try {
        const reqs = await fs.readFile(requirementsPath, 'utf-8');
        practices.stack.push('Python project');

        if (reqs.includes('fastapi')) practices.stack.push('FastAPI');
        if (reqs.includes('django')) practices.stack.push('Django');
        if (reqs.includes('flask')) practices.stack.push('Flask');
        if (reqs.includes('pydantic')) practices.conventions.push('Pydantic for validation');
        if (reqs.includes('pytest')) practices.testing.push('pytest for testing');
        if (reqs.includes('black')) practices.conventions.push('Black for formatting');
        if (reqs.includes('ruff')) practices.conventions.push('Ruff for linting');

        practices.dependencies = reqs.split('\n')
          .filter(l => l && !l.startsWith('#'))
          .map(l => l.split('==')[0].split('>=')[0].trim())
          .slice(0, 15);

      } catch {
        // No requirements.txt
      }

      // Check for common patterns in code
      const codePatterns = await this.detectCodePatterns(projectPath);
      practices.patterns = codePatterns;

    } catch (e) {
      log(`Error analyzing ${project}: ${e.message}`, 'warn');
    }

    return practices;
  }

  async detectCodePatterns(projectPath) {
    const patterns = [];

    try {
      // Check for common directory structures
      const dirs = await fs.readdir(projectPath, { withFileTypes: true });
      const dirNames = dirs.filter(d => d.isDirectory()).map(d => d.name);

      if (dirNames.includes('src')) patterns.push('src/ directory for source code');
      if (dirNames.includes('components')) patterns.push('Component-based architecture');
      if (dirNames.includes('hooks')) patterns.push('Custom React hooks pattern');
      if (dirNames.includes('utils') || dirNames.includes('lib')) patterns.push('Utility modules in utils/ or lib/');
      if (dirNames.includes('api')) patterns.push('API layer separation');
      if (dirNames.includes('services')) patterns.push('Service layer pattern');
      if (dirNames.includes('stores')) patterns.push('State management with stores');
      if (dirNames.includes('types')) patterns.push('Centralized type definitions');
      if (dirNames.includes('tests') || dirNames.includes('__tests__')) patterns.push('Dedicated test directory');
      if (dirNames.includes('models')) patterns.push('Model layer for data structures');
      if (dirNames.includes('middleware')) patterns.push('Middleware pattern');
      if (dirNames.includes('repositories')) patterns.push('Repository pattern for data access');

    } catch {
      // Can't read directory
    }

    return patterns;
  }

  async createPracticesFile(practicesPath, project, practices) {
    const projectName = project.split('/').pop();
    const date = new Date().toISOString().split('T')[0];

    let content = `# ${projectName} - Programming Practices

**Last Updated:** ${date}
**Curated by:** Squeegee

---

## Tech Stack

${practices.stack.length > 0 ? practices.stack.map(s => `- ${s}`).join('\n') : '*Not detected*'}

---

## Architecture Patterns

${practices.patterns.length > 0 ? practices.patterns.map(p => `- ${p}`).join('\n') : '*No patterns detected*'}

---

## Code Conventions

${practices.conventions.length > 0 ? practices.conventions.map(c => `- ${c}`).join('\n') : `- Follow existing code style
- Use meaningful variable names
- Keep functions focused and small`}

---

## Key Dependencies

${practices.dependencies.length > 0 ? '```\n' + practices.dependencies.join('\n') + '\n```' : '*See package.json or requirements.txt*'}

---

## Testing Approach

${practices.testing.length > 0 ? practices.testing.map(t => `- ${t}`).join('\n') : '*Testing framework not detected*'}

---

## Project-Specific Notes

*Add project-specific programming practices here:*

-
-
-

---

## Best Practices Checklist

- [ ] Follow existing code patterns in the project
- [ ] Add types/type hints for new code
- [ ] Write tests for new functionality
- [ ] Update documentation when changing APIs
- [ ] Use existing utilities before creating new ones

---

*Managed by Squeegee Documentation System*
`;

    await fs.mkdir(path.dirname(practicesPath), { recursive: true });
    await fs.writeFile(practicesPath, content, 'utf-8');
    log(`Created ${practicesPath}`, 'success');
  }
}

// ============================================================================
// TRIGGER TABLE CURATOR - Generate keyword-to-resource mapping
// ============================================================================
class TriggerTableCurator {
  constructor(workspace) {
    this.workspace = workspace;
    this.configPath = path.join(workspace, 'squeegee.config.json');
  }

  async loadConfig() {
    try {
      const content = await fs.readFile(this.configPath, 'utf-8');
      return JSON.parse(content);
    } catch {
      return { triggerTables: { enabled: false } };
    }
  }

  async curateAll() {
    log('Generating trigger tables for all projects...', 'info');

    const config = await this.loadConfig();
    if (!config.triggerTables || !config.triggerTables.enabled) {
      log('Trigger tables disabled in config', 'warn');
      return { updated: [], skipped: [] };  // Consistent return shape
    }

    const results = { updated: [], skipped: [] };

    for (const project of CONFIG.projects) {
      const projectPath = path.join(this.workspace, project);
      const claudePath = path.join(projectPath, 'CLAUDE.md');

      try {
        await fs.access(claudePath);
      } catch {
        results.skipped.push(project);
        continue;
      }

      const updated = await this.addTriggerTable(claudePath, project, config);
      if (updated) {
        results.updated.push(project);
      }
    }

    log(`Updated: ${results.updated.length}, Skipped: ${results.skipped.length}`, 'success');
    return results;
  }

  async addTriggerTable(claudePath, project, config) {
    const content = await fs.readFile(claudePath, 'utf-8');
    const projectName = project.split('/').pop();

    // Check if trigger table already exists
    if (content.includes('## Trigger Table')) {
      return false; // Already has trigger table
    }

    // Build triggers for this project
    const triggers = await this.buildProjectTriggers(project, projectName, config);

    if (triggers.length === 0) {
      return false;
    }

    // Generate trigger table section
    const triggerSection = this.generateTriggerSection(triggers);

    // Find insertion point - before "## Related Documentation" or at end
    let insertPoint = content.indexOf('## Related Documentation');
    if (insertPoint === -1) {
      insertPoint = content.lastIndexOf('---');
    }
    if (insertPoint === -1) {
      insertPoint = content.length;
    }

    const newContent = content.slice(0, insertPoint) + triggerSection + '\n' + content.slice(insertPoint);

    await fs.writeFile(claudePath, newContent, 'utf-8');
    return true;
  }

  async buildProjectTriggers(project, projectName, config) {
    const triggers = [];
    const projectPath = path.join(this.workspace, project);

    // 1. Add global triggers relevant to this project's stack
    const globalTriggers = config.triggerTables.global || {};

    // Detect project stack
    const stack = await this.detectStack(projectPath);

    // Match global triggers to stack
    for (const [keyword, resources] of Object.entries(globalTriggers)) {
      const keywordLower = keyword.toLowerCase();
      const stackLower = stack.map(s => s.toLowerCase());

      if (stackLower.some(s => s.includes(keywordLower) || keywordLower.includes(s))) {
        triggers.push({
          keyword,
          resources: resources.slice(0, 2), // Limit to 2 resources
          context: 'Global'
        });
      }
    }

    // 2. Add project-specific triggers
    const projectTriggers = (config.triggerTables.projectSpecific && config.triggerTables.projectSpecific[projectName]) || {};
    for (const [keyword, resources] of Object.entries(projectTriggers)) {
      triggers.push({
        keyword,
        resources,
        context: 'Project'
      });
    }

    // 3. Auto-detect triggers from dependencies
    const autoTriggers = await this.detectAutoTriggers(projectPath);
    for (const trigger of autoTriggers) {
      if (!triggers.some(t => t.keyword === trigger.keyword)) {
        triggers.push(trigger);
      }
    }

    // Limit to maxKeywordsPerProject
    const maxKeywords = config.triggerTables.maxKeywordsPerProject || 10;
    return triggers.slice(0, maxKeywords);
  }

  async detectStack(projectPath) {
    const stack = [];

    try {
      const pkg = JSON.parse(await fs.readFile(path.join(projectPath, 'package.json'), 'utf-8'));
      const deps = { ...pkg.dependencies, ...pkg.devDependencies };

      if (deps.react) stack.push('React');
      if (deps.next) stack.push('Next.js');
      if (deps['react-native']) stack.push('React Native');
      if (deps.expo) stack.push('Expo');
      if (deps.typescript) stack.push('TypeScript');
      if (deps.tailwindcss) stack.push('Tailwind');
      if (deps['@tanstack/react-query']) stack.push('TanStack Query');
      if (deps.zustand) stack.push('Zustand');
      if (deps.supabase || deps['@supabase/supabase-js']) stack.push('Supabase');
    } catch {}

    try {
      const reqs = await fs.readFile(path.join(projectPath, 'requirements.txt'), 'utf-8');
      if (reqs.includes('fastapi')) stack.push('FastAPI');
      if (reqs.includes('django')) stack.push('Django');
      if (reqs.includes('flask')) stack.push('Flask');
      if (reqs.includes('google-cloud')) stack.push('Google Cloud');
      if (reqs.includes('playwright')) stack.push('Playwright');
      if (reqs.includes('pydantic')) stack.push('Pydantic');
    } catch {}

    return stack;
  }

  async detectAutoTriggers(projectPath) {
    const triggers = [];

    try {
      const pkg = JSON.parse(await fs.readFile(path.join(projectPath, 'package.json'), 'utf-8'));
      const deps = { ...pkg.dependencies, ...pkg.devDependencies };

      // Map common deps to trigger keywords
      const depTriggers = {
        'zustand': { keyword: 'state management', context: 'Uses Zustand' },
        '@tanstack/react-query': { keyword: 'data fetching', context: 'Uses TanStack Query' },
        'iron-session': { keyword: 'sessions', context: 'Uses iron-session' },
        'axios': { keyword: 'http client', context: 'Uses Axios' },
        'framer-motion': { keyword: 'animations', context: 'Uses Framer Motion' },
        'three': { keyword: '3d rendering', context: 'Uses Three.js' }
      };

      for (const [dep, trigger] of Object.entries(depTriggers)) {
        if (deps[dep]) {
          triggers.push({
            keyword: trigger.keyword,
            resources: ['See package.json'],
            context: trigger.context
          });
        }
      }
    } catch {}

    return triggers;
  }

  generateTriggerSection(triggers) {
    let section = `## Trigger Table

When working in this project, these keywords load additional context:

| Keyword | Resources | Context |
|---------|-----------|---------|
`;

    for (const trigger of triggers) {
      const resources = trigger.resources.map(r => `\`${r}\``).join(', ');
      section += `| \`${trigger.keyword}\` | ${resources} | ${trigger.context} |\n`;
    }

    section += `
*Auto-generated by Squeegee. Edit squeegee.config.json to customize.*

---

`;

    return section;
  }
}

// ============================================================================
// PATTERN LIBRARY CURATOR - Extract cross-project patterns
// ============================================================================
class PatternLibraryCurator {
  constructor(workspace) {
    this.workspace = workspace;
    this.configPath = path.join(workspace, 'squeegee.config.json');
  }

  async loadConfig() {
    try {
      const content = await fs.readFile(this.configPath, 'utf-8');
      return JSON.parse(content);
    } catch {
      return { patternLibrary: { enabled: false } };
    }
  }

  async curate() {
    log('Generating cross-project pattern library...', 'info');

    const config = await this.loadConfig();
    if (!config.patternLibrary || !config.patternLibrary.enabled) {
      log('Pattern library disabled in config', 'warn');
      return { patterns: 0 };
    }

    const patterns = await this.detectPatterns();
    await this.generatePatternLibrary(patterns, config);

    log(`Detected ${patterns.length} cross-project patterns`, 'success');
    return { patterns: patterns.length };
  }

  async detectPatterns() {
    const patterns = [];
    const projectData = {};

    // Analyze each project
    for (const project of CONFIG.projects) {
      const projectPath = path.join(this.workspace, project);
      const projectName = project.split('/').pop();

      projectData[projectName] = await this.analyzeProject(projectPath);
    }

    // Find patterns that appear in multiple projects
    const frameworkPatterns = this.findFrameworkPatterns(projectData);
    const architecturePatterns = this.findArchitecturePatterns(projectData);
    const toolingPatterns = this.findToolingPatterns(projectData);

    patterns.push(...frameworkPatterns, ...architecturePatterns, ...toolingPatterns);

    return patterns;
  }

  async analyzeProject(projectPath) {
    const analysis = {
      frameworks: [],
      architecture: [],
      tooling: [],
      dependencies: []
    };

    // Check package.json
    try {
      const pkg = JSON.parse(await fs.readFile(path.join(projectPath, 'package.json'), 'utf-8'));
      const deps = { ...pkg.dependencies, ...pkg.devDependencies };

      if (deps.react) analysis.frameworks.push('react');
      if (deps.next) analysis.frameworks.push('nextjs');
      if (deps['react-native']) analysis.frameworks.push('react-native');
      if (deps.expo) analysis.frameworks.push('expo');
      if (deps.zustand) analysis.tooling.push('zustand');
      if (deps['@tanstack/react-query']) analysis.tooling.push('tanstack-query');
      if (deps.typescript) analysis.tooling.push('typescript');
      if (deps.tailwindcss) analysis.tooling.push('tailwindcss');
      if (deps['iron-session']) analysis.tooling.push('iron-session');

      analysis.dependencies = Object.keys(deps);
    } catch {}

    // Check requirements.txt
    try {
      const reqs = await fs.readFile(path.join(projectPath, 'requirements.txt'), 'utf-8');
      if (reqs.includes('fastapi')) analysis.frameworks.push('fastapi');
      if (reqs.includes('pydantic')) analysis.tooling.push('pydantic');
      if (reqs.includes('pytest')) analysis.tooling.push('pytest');
    } catch {}

    // Check directory structure
    try {
      const dirs = await fs.readdir(projectPath, { withFileTypes: true });
      const dirNames = dirs.filter(d => d.isDirectory()).map(d => d.name);

      if (dirNames.includes('services')) analysis.architecture.push('service-layer');
      if (dirNames.includes('repositories')) analysis.architecture.push('repository-pattern');
      if (dirNames.includes('stores')) analysis.architecture.push('store-pattern');
      if (dirNames.includes('hooks')) analysis.architecture.push('custom-hooks');
      if (dirNames.includes('components')) analysis.architecture.push('component-based');
    } catch {}

    return analysis;
  }

  findFrameworkPatterns(projectData) {
    const patterns = [];
    const frameworkCounts = {};

    // Count framework occurrences
    for (const [project, data] of Object.entries(projectData)) {
      for (const fw of data.frameworks) {
        if (!frameworkCounts[fw]) frameworkCounts[fw] = [];
        frameworkCounts[fw].push(project);
      }
    }

    // Create patterns for frameworks used in 2+ projects
    for (const [fw, projects] of Object.entries(frameworkCounts)) {
      if (projects.length >= 2) {
        patterns.push({
          name: this.formatPatternName(fw),
          category: 'Framework',
          projects,
          description: `Used in ${projects.length} projects: ${projects.join(', ')}`
        });
      }
    }

    return patterns;
  }

  findArchitecturePatterns(projectData) {
    const patterns = [];
    const archCounts = {};

    for (const [project, data] of Object.entries(projectData)) {
      for (const arch of data.architecture) {
        if (!archCounts[arch]) archCounts[arch] = [];
        archCounts[arch].push(project);
      }
    }

    for (const [arch, projects] of Object.entries(archCounts)) {
      if (projects.length >= 2) {
        patterns.push({
          name: this.formatPatternName(arch),
          category: 'Architecture',
          projects,
          description: `Used in ${projects.length} projects: ${projects.join(', ')}`
        });
      }
    }

    return patterns;
  }

  findToolingPatterns(projectData) {
    const patterns = [];
    const toolCounts = {};

    for (const [project, data] of Object.entries(projectData)) {
      for (const tool of data.tooling) {
        if (!toolCounts[tool]) toolCounts[tool] = [];
        toolCounts[tool].push(project);
      }
    }

    // Check for interesting combinations
    const zustandProjects = toolCounts['zustand'] || [];
    const queryProjects = toolCounts['tanstack-query'] || [];
    const overlap = zustandProjects.filter(p => queryProjects.includes(p));

    if (overlap.length >= 2) {
      patterns.push({
        name: 'Zustand + TanStack Query State Management',
        category: 'State Management',
        projects: overlap,
        description: 'Hybrid approach: TanStack Query for server state, Zustand for client state'
      });
    }

    // Individual tool patterns
    for (const [tool, projects] of Object.entries(toolCounts)) {
      if (projects.length >= 2 && !['zustand', 'tanstack-query'].includes(tool)) {
        patterns.push({
          name: this.formatPatternName(tool),
          category: 'Tooling',
          projects,
          description: `Used in ${projects.length} projects: ${projects.join(', ')}`
        });
      }
    }

    return patterns;
  }

  formatPatternName(str) {
    return str
      .split('-')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ');
  }

  async generatePatternLibrary(patterns, config) {
    const outputPath = path.join(this.workspace, config.patternLibrary.outputPath);
    const date = new Date().toISOString().split('T')[0];

    let content = `# Cross-Project Pattern Library

**Last Updated:** ${date}
**Patterns Cataloged:** ${patterns.length}
**Generated by:** Squeegee

---

This document catalogs patterns and practices that appear across multiple projects in the workspace. Use this as a reference for consistency and to leverage proven approaches.

---

`;

    // Group patterns by category
    const byCategory = {};
    for (const pattern of patterns) {
      if (!byCategory[pattern.category]) byCategory[pattern.category] = [];
      byCategory[pattern.category].push(pattern);
    }

    for (const [category, categoryPatterns] of Object.entries(byCategory)) {
      content += `## ${category} Patterns\n\n`;

      for (const pattern of categoryPatterns) {
        content += `### ${pattern.name}\n`;
        content += `**Projects:** ${pattern.projects.join(', ')}\n\n`;
        content += `${pattern.description}\n\n`;
        content += `---\n\n`;
      }
    }

    content += `
## Usage

When starting a new project or feature:
1. Check this library for relevant patterns
2. Reference the listed projects for implementation examples
3. Maintain consistency with existing approaches when possible

---

*Auto-generated by Squeegee Pattern Library Curator*
`;

    await fs.mkdir(path.dirname(outputPath), { recursive: true });
    await fs.writeFile(outputPath, content, 'utf-8');
    log(`Pattern library saved to ${outputPath}`, 'success');
  }
}

// ============================================================================
// ROOT CLAUDE.MD CURATOR - Curate the workspace root CLAUDE.md
// ============================================================================
class RootClaudeMdCurator {
  constructor(workspace) {
    this.workspace = workspace;
    this.history = new HistoryManager(workspace);
    this.rootClaudePath = path.join(workspace, 'CLAUDE.md');
    this.config = null;
  }

  async loadConfig() {
    try {
      const configPath = path.join(this.workspace, 'squeegee.config.json');
      this.config = JSON.parse(await fs.readFile(configPath, 'utf-8'));
    } catch {
      this.config = { rootClaudeMd: { enabled: false } };
    }
    return this.config;
  }

  async curateAll() {
    await this.loadConfig();

    if (!this.config.rootClaudeMd?.enabled) {
      return { changes: [], warnings: [], suggestions: [] };
    }

    log('Curating root CLAUDE.md...', 'info');

    const results = {
      changes: [],
      warnings: [],
      suggestions: []
    };

    try {
      let content = await fs.readFile(this.rootClaudePath, 'utf-8');
      const originalContent = content;

      // 1. Discover projects and sync Projects Index
      if (this.config.rootClaudeMd.autoSync?.projectsIndex) {
        const syncResult = await this.syncProjectsIndex(content);
        content = syncResult.content;
        results.changes.push(...syncResult.changes);
        results.warnings.push(...syncResult.warnings);
      }

      // 2. Validate and fix cross-references
      if (this.config.rootClaudeMd.autoSync?.crossReferences) {
        const refResult = await this.validateAndFixCrossReferences(content);
        content = refResult.content;
        results.changes.push(...refResult.changes);
        results.warnings.push(...refResult.warnings);
      }

      // 3. Validate required sections
      const sectionResult = this.validateRequiredSections(content);
      results.warnings.push(...sectionResult.warnings);

      // 4. Detect missing documentation in projects
      const missingDocs = await this.detectMissingDocs();
      results.warnings.push(...missingDocs);

      // 5. Generate suggestions
      const suggestions = await this.generateSuggestions(content);
      results.suggestions.push(...suggestions);

      // Save if changed
      if (content !== originalContent) {
        await this.history.archive(this.rootClaudePath, 'root-curator-update');
        await fs.writeFile(this.rootClaudePath, content, 'utf-8');
        log(`Root CLAUDE.md updated with ${results.changes.length} changes`, 'success');
      }

    } catch (err) {
      results.warnings.push(`Error reading root CLAUDE.md: ${err.message}`);
    }

    return results;
  }

  async discoverProjects() {
    const discovered = {
      active: [],
      glassy: [],
      tools: [],
      archived: []
    };

    // Scan projects/ directory
    try {
      const projectsDir = path.join(this.workspace, 'projects');
      const entries = await fs.readdir(projectsDir, { withFileTypes: true });

      for (const entry of entries) {
        if (entry.isDirectory()) {
          const claudePath = path.join(projectsDir, entry.name, 'CLAUDE.md');
          try {
            await fs.access(claudePath);
            discovered.active.push({
              name: entry.name.split('-').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' '),
              path: `projects/${entry.name}/`,
              claudePath: `projects/${entry.name}/CLAUDE.md`
            });
          } catch {}
        }
      }
    } catch {}

    // Scan glassy-* directories
    try {
      const entries = await fs.readdir(this.workspace, { withFileTypes: true });

      for (const entry of entries) {
        if (entry.isDirectory() && entry.name.startsWith('glassy-')) {
          const claudePath = path.join(this.workspace, entry.name, 'CLAUDE.md');
          try {
            await fs.access(claudePath);
            const displayName = entry.name.split('-').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
            discovered.glassy.push({
              name: displayName,
              path: `${entry.name}/`,
              claudePath: `${entry.name}/CLAUDE.md`
            });
          } catch {}
        }
      }
    } catch {}

    return discovered;
  }

  parseProjectsTable(content, sectionHeader) {
    const projects = [];

    // Find the section - stop at next ### or horizontal rule followed by blank line
    const sectionRegex = new RegExp(`### ${sectionHeader}[\\s\\S]*?(?=\n### |\n---\n\n|$)`, 'i');
    const match = content.match(sectionRegex);

    if (!match) return projects;

    // Parse table rows with backtick-wrapped paths and CLAUDE.md links
    const tableContent = match[0];
    const rowRegex = /\|\s*([^|]+)\s*\|\s*`([^`]+)`\s*\|\s*\[CLAUDE\.md\]\(([^)]+)\)\s*\|/g;

    let row;
    while ((row = rowRegex.exec(tableContent)) !== null) {
      projects.push({
        name: row[1].trim(),
        path: row[2].trim(),
        claudePath: row[3].trim()
      });
    }

    return projects;
  }

  async syncProjectsIndex(content) {
    const changes = [];
    const warnings = [];

    const discovered = await this.discoverProjects();

    // Parse existing tables
    const existingActive = this.parseProjectsTable(content, 'Active Projects');
    const existingGlassy = this.parseProjectsTable(content, 'Glassy Platform');

    // Normalize path for comparison (remove trailing slash, lowercase)
    const normalizePath = (p) => p.replace(/\/+$/, '').toLowerCase().trim();

    // Find missing projects in Active Projects
    for (const project of discovered.active) {
      const normalizedDiscoveredPath = normalizePath(project.path);
      const exists = existingActive.some(p => normalizePath(p.path) === normalizedDiscoveredPath);
      if (!exists) {
        // Add to table
        const newRow = `| ${project.name} | \`${project.path}\` | [CLAUDE.md](${project.claudePath}) |`;

        // Find insertion point (before the empty line after the table)
        const tableEndRegex = /(### Active Projects[\s\S]*?\|[^|]+\|[^|]+\|[^|]+\|[\s\S]*?)(\n\n)/;
        const tableMatch = content.match(tableEndRegex);

        if (tableMatch) {
          // Find the last row of the table
          const lastRowMatch = tableMatch[1].match(/(\| [^|]+ \| `[^`]+` \| \[CLAUDE\.md\]\([^)]+\) \|)(?=\s*$)/);
          if (lastRowMatch) {
            content = content.replace(lastRowMatch[1], `${lastRowMatch[1]}\n${newRow}`);
            changes.push(`Added "${project.name}" to Active Projects`);
          }
        }
      }
    }

    // Find missing projects in Glassy Platform
    for (const project of discovered.glassy) {
      const normalizedDiscoveredPath = normalizePath(project.path);
      const exists = existingGlassy.some(p => normalizePath(p.path) === normalizedDiscoveredPath);
      if (!exists) {
        const newRow = `| ${project.name} | \`${project.path}\` | [CLAUDE.md](${project.claudePath}) |`;

        const tableEndRegex = /(### Glassy Platform[\s\S]*?\|[^|]+\|[^|]+\|[^|]+\|[\s\S]*?)(\n\n)/;
        const tableMatch = content.match(tableEndRegex);

        if (tableMatch) {
          const lastRowMatch = tableMatch[1].match(/(\| [^|]+ \| `[^`]+` \| \[CLAUDE\.md\]\([^)]+\) \|)(?=\s*$)/);
          if (lastRowMatch) {
            content = content.replace(lastRowMatch[1], `${lastRowMatch[1]}\n${newRow}`);
            changes.push(`Added "${project.name}" to Glassy Platform`);
          }
        }
      }
    }

    // Check for projects in table but not on filesystem
    for (const project of existingActive) {
      const normalizedExistingPath = normalizePath(project.path);
      const exists = discovered.active.some(p => normalizePath(p.path) === normalizedExistingPath);
      if (!exists) {
        warnings.push(`"${project.name}" in Active Projects but CLAUDE.md not found at ${project.claudePath}`);
      }
    }

    for (const project of existingGlassy) {
      const normalizedExistingPath = normalizePath(project.path);
      const exists = discovered.glassy.some(p => normalizePath(p.path) === normalizedExistingPath);
      if (!exists) {
        warnings.push(`"${project.name}" in Glassy Platform but CLAUDE.md not found at ${project.claudePath}`);
      }
    }

    return { content, changes, warnings };
  }

  async validateAndFixCrossReferences(content) {
    const changes = [];
    const warnings = [];

    // Extract all markdown links
    const linkRegex = /\[([^\]]+)\]\(([^)]+)\)/g;
    let match;

    while ((match = linkRegex.exec(content)) !== null) {
      const linkText = match[1];
      const linkPath = match[2];

      // Skip external links and anchors
      if (linkPath.startsWith('http') || linkPath.startsWith('#')) {
        continue;
      }

      // Check if file exists
      const fullPath = path.join(this.workspace, linkPath);
      try {
        await fs.access(fullPath);
      } catch {
        // Try to find the correct path
        const fileName = path.basename(linkPath);
        const searchResult = await this.findFile(fileName);

        if (searchResult) {
          const relativePath = path.relative(this.workspace, searchResult);
          content = content.replace(
            `[${linkText}](${linkPath})`,
            `[${linkText}](${relativePath})`
          );
          changes.push(`Fixed link: ${linkPath} → ${relativePath}`);
        } else {
          warnings.push(`Broken link: [${linkText}](${linkPath})`);
        }
      }
    }

    return { content, changes, warnings };
  }

  async findFile(fileName) {
    // Search in common locations
    const searchPaths = [
      '',
      'docs/',
      'docs-portal/',
      'scripts/'
    ];

    for (const searchPath of searchPaths) {
      const fullPath = path.join(this.workspace, searchPath, fileName);
      try {
        await fs.access(fullPath);
        return fullPath;
      } catch {}
    }

    // Search in project directories
    for (const project of CONFIG.projects) {
      const projectPath = path.join(this.workspace, project, fileName);
      try {
        await fs.access(projectPath);
        return projectPath;
      } catch {}
    }

    return null;
  }

  validateRequiredSections(content) {
    const warnings = [];
    const requiredSections = this.config.rootClaudeMd?.requiredSections || [];

    // Mapping from section names to module file patterns they can be satisfied by
    const sectionModuleMap = this.config.rootClaudeMd?.sectionModuleMap || {
      'Agents & Subagents': ['agents-subagents'],
      'Core Principles': ['core-principles'],
      'Projects Index': ['projects-index'],
      'Standard Tech Stack': ['tech-stack'],
      'Working Preferences': ['tech-stack'],
      'Tech Stack': ['tech-stack'],
    };

    for (const section of requiredSections) {
      // Check 1: Direct section header (## Section Name)
      const sectionRegex = new RegExp(`##.*${this.escapeRegex(section)}`, 'i');
      const hasDirectSection = sectionRegex.test(content);

      // Check 2: Module reference (@.claude/instructions/module-name.md)
      const modulePatterns = sectionModuleMap[section] || [];
      const hasModuleRef = modulePatterns.some(pattern => {
        // Match patterns like @.claude/instructions/agents-subagents.md or agents-subagents.md in links
        const moduleRegex = new RegExp(`@?\\.?claude/instructions/${pattern}\\.md|\\[.*${pattern}.*\\.md\\]`, 'i');
        return moduleRegex.test(content);
      });

      // Check 3: Reference in instruction modules table (keyword | @path | description format)
      const hasTableRef = modulePatterns.some(pattern => {
        const tableRefRegex = new RegExp(`\\|.*@\\.claude/instructions/${pattern}\\.md.*\\|`, 'i');
        return tableRefRegex.test(content);
      });

      if (!hasDirectSection && !hasModuleRef && !hasTableRef) {
        warnings.push(`Missing required section: "${section}"`);
      }
    }

    return { warnings };
  }

  // Helper to escape special regex characters
  escapeRegex(string) {
    return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }

  async detectMissingDocs() {
    const warnings = [];
    const requiredDocs = ['CLAUDE.md', '.planning/STATE.md'];

    for (const projectPath of CONFIG.projects) {
      const fullProjectPath = path.join(this.workspace, projectPath);

      try {
        await fs.access(fullProjectPath);
      } catch {
        continue;
      }

      for (const doc of requiredDocs) {
        const docPath = path.join(fullProjectPath, doc);
        try {
          await fs.access(docPath);
        } catch {
          warnings.push(`Project "${projectPath}" missing ${doc}`);
        }
      }
    }

    return warnings;
  }

  async generateSuggestions(content) {
    const suggestions = [];

    // Check freshness
    const lastUpdatedMatch = content.match(/Last Updated:\s*(\d{4}-\d{2}-\d{2})/);
    if (lastUpdatedMatch) {
      const lastUpdated = new Date(lastUpdatedMatch[1]);
      const daysSince = (Date.now() - lastUpdated.getTime()) / (1000 * 60 * 60 * 24);
      if (daysSince > 30) {
        suggestions.push(`Root CLAUDE.md not updated in ${Math.floor(daysSince)} days`);
      }
    }

    // Check for placeholder text
    if (content.includes('[To be documented]') || content.includes('TODO')) {
      suggestions.push('Contains placeholder text that needs completion');
    }

    // Check line count
    const lineCount = content.split('\n').length;
    if (lineCount > 300) {
      suggestions.push(`Root CLAUDE.md is ${lineCount} lines - consider condensing`);
    }

    return suggestions;
  }
}

// ============================================================================
// REPORT GENERATOR - Create health reports
// ============================================================================
class ReportGenerator {
  constructor(scanResults, qualityScores) {
    this.scanResults = scanResults;
    this.qualityScores = qualityScores;
  }

  generateConsoleReport() {
    console.log('\n');
    console.log('╔═══════════════════════════════════════════════════════════════╗');
    console.log('║              🧽 SQUEEGEE DOCUMENTATION REPORT                 ║');
    console.log('╚═══════════════════════════════════════════════════════════════╝');
    console.log('');

    // Summary stats
    const totalMd = this.scanResults.markdown.length;
    const totalCode = this.scanResults.code.length;
    const totalFunctions = this.scanResults.code.reduce((s, f) => s + f.functionCount, 0);
    const documentedFunctions = this.scanResults.code.reduce((s, f) => s + f.documentedFunctions, 0);

    console.log('  📊 OVERVIEW');
    console.log('  ───────────────────────────────────────');
    console.log(`  Markdown Files:     ${totalMd}`);
    console.log(`  Code Files:         ${totalCode}`);
    console.log(`  Total Functions:    ${totalFunctions}`);
    console.log(`  Documented:         ${documentedFunctions} (${Math.round(documentedFunctions/totalFunctions*100)}%)`);
    console.log('');

    // Project breakdown
    console.log('  📁 PROJECT BREAKDOWN');
    console.log('  ───────────────────────────────────────');

    const projectScores = this.qualityScores.getProjectScores();

    for (const [project, data] of Object.entries(projectScores)) {
      const scoreBar = this.makeBar(data.averageScore);
      const icon = data.averageScore >= 0.8 ? '✅' : data.averageScore >= 0.6 ? '⚠️' : '❌';
      console.log(`  ${icon} ${project.padEnd(25)} ${scoreBar} ${Math.round(data.averageScore * 100)}%`);
    }

    console.log('');

    // Missing docs
    const scanner = new DocumentScanner(CONFIG.workspace);
    scanner.results = this.scanResults;
    const summary = scanner.getProjectSummary();

    console.log('  ⚠️  MISSING DOCUMENTATION');
    console.log('  ───────────────────────────────────────');

    let missingCount = 0;
    for (const [project, data] of Object.entries(summary)) {
      if (!data.hasClaude) {
        console.log(`  ❌ ${project}: Missing CLAUDE.md`);
        missingCount++;
      }
      if (!data.hasState && !data.hasVariable) {
        console.log(`  ❌ ${project}: Missing .planning/STATE.md`);
        missingCount++;
      }
    }

    if (missingCount === 0) {
      console.log('  ✅ All required documentation present!');
    }

    console.log('');
    console.log('═══════════════════════════════════════════════════════════════');
    console.log('');
  }

  makeBar(score) {
    const filled = Math.round(score * 20);
    return '█'.repeat(filled) + '░'.repeat(20 - filled);
  }

  async generateMarkdownReport() {
    const date = new Date().toISOString().split('T')[0];
    const time = new Date().toISOString().split('T')[1].slice(0, 5);

    let report = `# Squeegee Documentation Health Report

**Generated:** ${date} ${time}
**System:** Squeegee v1.0.0

---

## Summary

| Metric | Value |
|--------|-------|
| Total Markdown Files | ${this.scanResults.markdown.length} |
| Total Code Files | ${this.scanResults.code.length} |
| Total Functions | ${this.scanResults.code.reduce((s, f) => s + f.functionCount, 0)} |
| Documented Functions | ${this.scanResults.code.reduce((s, f) => s + f.documentedFunctions, 0)} |

---

## Project Scores

| Project | Score | Docs | Status |
|---------|-------|------|--------|
`;

    const projectScores = this.qualityScores.getProjectScores();
    for (const [project, data] of Object.entries(projectScores)) {
      const status = data.averageScore >= 0.8 ? '✅ Good' : data.averageScore >= 0.6 ? '⚠️ Fair' : '❌ Poor';
      report += `| ${project} | ${Math.round(data.averageScore * 100)}% | ${data.documentCount} | ${status} |\n`;
    }

    report += `
---

## Recommendations

`;

    // Add recommendations based on scores
    for (const [project, data] of Object.entries(projectScores)) {
      if (data.averageScore < 0.8) {
        report += `### ${project}\n`;
        if (data.lowQualityDocs > 0) {
          report += `- ${data.lowQualityDocs} documents need improvement\n`;
        }
        report += '\n';
      }
    }

    report += `
---

*Generated by Squeegee Documentation System*
`;

    return report;
  }
}

// ============================================================================
// MAIN ORCHESTRATOR
// ============================================================================
class SqueegeeManager {
  constructor() {
    this.scanner = new DocumentScanner(CONFIG.workspace);
  }

  async run(command) {
    console.log('\n🧽 Squeegee Documentation Manager\n');

    switch (command) {
      case 'scan':
        await this.runScan();
        break;
      case 'analyze':
        await this.runAnalyze();
        break;
      case 'generate':
        await this.runGenerate();
        break;
      case 'validate':
        await this.runValidate();
        break;
      case 'report':
        await this.runReport();
        break;
      case 'plans':
        await this.runPlans();
        break;
      case 'practices':
        await this.runPractices();
        break;
      case 'claudemd':
        await this.runClaudeMd();
        break;
      case 'variable':
        await this.runVariable();
        break;
      case 'history':
        await this.runHistory();
        break;
      case 'learnings':
        await this.runLearnings();
        break;
      case 'triggers':
        await this.runTriggers();
        break;
      case 'patterns':
        await this.runPatterns();
        break;
      case 'root':
        await this.runRoot();
        break;
      case 'install-hook':
        await this.installPreCommitHook();
        break;
      case 'migrate-gsd':
        await this.runMigrateGsd();
        break;
      case 'gsd-analyze':
        await this.runGsdAnalyze();
        break;
      case 'gsd-issues':
        await this.runGsdIssues();
        break;
      case 'clean-legacy':
        await this.runCleanLegacy();
        break;
      case 'full':
        await this.runFull();
        break;
      default:
        this.showHelp();
    }
  }

  async runTriggers() {
    log('Running trigger table generation...', 'info');
    const curator = new TriggerTableCurator(CONFIG.workspace);
    const results = await curator.curateAll();

    console.log('\n📋 Trigger Table Summary:');
    console.log('───────────────────────────────────────');

    if (results.updated.length > 0) {
      console.log('\n✅ Added trigger tables to:');
      for (const project of results.updated) {
        console.log(`   - ${project}`);
      }
    }

    if (results.skipped?.length > 0) {
      console.log('\n⏭️  Skipped (already has triggers or no CLAUDE.md):');
      for (const project of results.skipped) {
        console.log(`   - ${project}`);
      }
    }

    console.log('');
  }

  async runPatterns() {
    log('Running pattern library generation...', 'info');
    const curator = new PatternLibraryCurator(CONFIG.workspace);
    const results = await curator.curate();

    console.log('\n📋 Pattern Library Summary:');
    console.log('───────────────────────────────────────');
    console.log(`\n✅ Detected ${results.patterns} cross-project patterns`);
    console.log('   Output: docs-portal/PATTERN_LIBRARY.md');
    console.log('');
  }

  async runRoot() {
    log('Running root CLAUDE.md curation...', 'info');
    const curator = new RootClaudeMdCurator(CONFIG.workspace);
    const results = await curator.curateAll();

    console.log('\n📋 Root CLAUDE.md Curation Summary:');
    console.log('───────────────────────────────────────');

    if (results.changes.length > 0) {
      console.log('\n✅ Auto-fixed:');
      for (const change of results.changes) {
        console.log(`   - ${change}`);
      }
    }

    if (results.warnings.length > 0) {
      console.log('\n⚠️  Warnings:');
      for (const warning of results.warnings) {
        console.log(`   - ${warning}`);
      }
    }

    if (results.suggestions.length > 0) {
      console.log('\n💡 Suggestions:');
      for (const suggestion of results.suggestions) {
        console.log(`   - ${suggestion}`);
      }
    }

    if (results.changes.length === 0 && results.warnings.length === 0 && results.suggestions.length === 0) {
      console.log('\n✅ Root CLAUDE.md is up to date!');
    }

    console.log('');
  }

  async installPreCommitHook() {
    log('Installing pre-commit hook...', 'info');

    const hookPath = path.join(CONFIG.workspace, '.git', 'hooks', 'pre-commit');
    const hookContent = `#!/bin/bash
# Squeegee Documentation Pre-commit Hook
# Auto-validates and fixes documentation before commits

node "\$(dirname "\$0")/../../scripts/squeegee-precommit.js"
`;

    try {
      await fs.writeFile(hookPath, hookContent, { mode: 0o755 });
      log(`Pre-commit hook installed at ${hookPath}`, 'success');

      console.log('\n📋 Pre-commit Hook Installation:');
      console.log('───────────────────────────────────────');
      console.log('\n✅ Hook installed successfully!');
      console.log('   Location: .git/hooks/pre-commit');
      console.log('   Script: scripts/squeegee-precommit.js');
      console.log('\n   The hook will run before each commit to:');
      console.log('   - Validate root CLAUDE.md structure');
      console.log('   - Sync Projects Index with filesystem');
      console.log('   - Fix broken cross-references');
      console.log('   - Report warnings and suggestions');
      console.log('');
    } catch (err) {
      log(`Failed to install hook: ${err.message}`, 'error');
    }
  }

  async runMigrateGsd() {
    log('Running GSD migration...', 'info');
    const migrator = new GsdMigrator(CONFIG.workspace);
    const results = await migrator.migrateAll();

    console.log('\n📋 GSD Migration Summary:');
    console.log('───────────────────────────────────────');

    if (results.migrated.length > 0) {
      console.log('\n✅ Migrated to GSD format:');
      for (const project of results.migrated) {
        console.log(`   - ${project}`);
      }
    }

    if (results.skipped?.length > 0) {
      console.log('\n⏭️  Skipped (already GSD or no VariableForClMD):');
      for (const item of results.skipped) {
        // Handle both object {project, reason} and string formats
        const projectName = typeof item === 'string' ? item : item.project;
        const reason = typeof item === 'object' && item.reason ? `: ${item.reason}` : '';
        console.log(`   - ${projectName}${reason}`);
      }
    }

    if (results.errors?.length > 0) {
      console.log('\n❌ Errors:');
      for (const error of results.errors) {
        console.log(`   - ${error}`);
      }
    }

    console.log('');
  }

  async runGsdAnalyze() {
    log('Running GSD artifact analysis...', 'info');
    const analyzer = new GsdAnalyzer(CONFIG.workspace);
    const rawResults = await analyzer.analyzeAll();

    console.log('\n📋 GSD Analysis Summary:');
    console.log('───────────────────────────────────────');

    const projectNames = Object.keys(rawResults);
    if (projectNames.length === 0) {
      console.log('\n⚠️  No GSD projects found. Use migrate-gsd to convert existing projects.');
      console.log('');
      return;
    }

    console.log(`\n📊 Analyzed ${projectNames.length} GSD projects:\n`);

    const allLearnings = [];

    for (const projectName of projectNames) {
      const project = rawResults[projectName];
      const quality = project.planQuality?.overall || 0;
      const qualityBar = '█'.repeat(Math.round(quality * 10)) +
                        '░'.repeat(10 - Math.round(quality * 10));

      console.log(`   ${projectName}:`);
      console.log(`      Plan Quality: [${qualityBar}] ${Math.round(quality * 100)}%`);
      console.log(`      Phases: ${project.phaseCount} total, ${project.completedPhases} completed`);
      console.log(`      GSD Files: STATE=${project.hasState ? '✓' : '✗'} ROADMAP=${project.hasRoadmap ? '✓' : '✗'} ISSUES=${project.hasIssues ? '✓' : '✗'}`);

      if (project.learnings?.length > 0) {
        console.log(`      Learnings: ${project.learnings.length} patterns extracted`);
        allLearnings.push(...project.learnings);
      }
      console.log('');
    }

    // Find cross-project learnings (appear in 2+ projects)
    const learningCounts = {};
    for (const learning of allLearnings) {
      const key = learning.pattern || learning;
      learningCounts[key] = (learningCounts[key] || 0) + 1;
    }

    const crossProjectLearnings = Object.entries(learningCounts)
      .filter(([, count]) => count >= 2)
      .map(([pattern]) => pattern);

    if (crossProjectLearnings.length > 0) {
      console.log('🎯 Cross-Project Learnings (appear in 2+ projects):');
      for (const learning of crossProjectLearnings) {
        console.log(`   - ${learning}`);
      }
      console.log('');
    }
  }

  async runGsdIssues() {
    log('Running GSD issues analysis...', 'info');
    const tracker = new GsdIssueTracker(CONFIG.workspace);
    const rawResults = await tracker.analyzeAll();

    console.log('\n📋 GSD Issues Summary:');
    console.log('───────────────────────────────────────');

    const projectNames = Object.keys(rawResults);
    if (projectNames.length === 0) {
      console.log('\n✅ No GSD projects with ISSUES.md found.');
      console.log('');
      return;
    }

    // Calculate totals from the object-keyed results
    let totalIssues = 0;
    let totalStale = 0;
    for (const projectName of projectNames) {
      const analysis = rawResults[projectName];
      totalIssues += analysis.openCount || 0;
      totalStale += analysis.staleCount || 0;
    }

    if (totalIssues === 0) {
      console.log('\n✅ No open issues found across projects.');
      console.log('');
      return;
    }

    console.log(`\n📊 Found ${totalIssues} issues across ${projectNames.length} projects:\n`);

    for (const projectName of projectNames) {
      const analysis = rawResults[projectName];
      if ((analysis.openCount || 0) === 0) continue;

      console.log(`   ${projectName}: ${analysis.openCount} issues`);

      // Show stale items if available
      if (analysis.staleItems?.length > 0) {
        for (const item of analysis.staleItems.slice(0, 5)) {
          const title = typeof item === 'string' ? item : (item.title || item);
          console.log(`      - ${title} ⚠️ STALE`);
        }
        if (analysis.staleItems.length > 5) {
          console.log(`      ... and ${analysis.staleItems.length - 5} more stale`);
        }
      }
      console.log('');
    }

    if (totalStale > 0) {
      console.log(`⚠️  ${totalStale} stale issues (>30 days old) need attention.`);
      console.log('');
    }
  }

  async runCleanLegacy() {
    log('Cleaning up legacy VariableForClMD.md files...', 'info');

    const results = { deleted: [], skipped: [] };
    const history = new HistoryManager(CONFIG.workspace);

    for (const project of CONFIG.projects) {
      const projectPath = path.join(CONFIG.workspace, project);
      const statePath = path.join(projectPath, '.planning', 'STATE.md');
      const variablePath = path.join(projectPath, 'VariableForClMD.md');
      const backupPath = variablePath + '.migrated.bak';

      // Check file existence
      let hasState = false;
      let hasVariable = false;
      let hasBackup = false;

      try { await fs.access(statePath); hasState = true; } catch {}
      try { await fs.access(variablePath); hasVariable = true; } catch {}
      try { await fs.access(backupPath); hasBackup = true; } catch {}

      // Only delete if STATE.md exists (migration complete)
      if (hasState && hasVariable) {
        await history.archive(variablePath, 'cleanup - STATE.md exists');
        await fs.unlink(variablePath);
        results.deleted.push({ project, file: 'VariableForClMD.md' });
      }

      if (hasState && hasBackup) {
        await fs.unlink(backupPath);
        results.deleted.push({ project, file: 'VariableForClMD.md.migrated.bak' });
      }

      if (!hasState && (hasVariable || hasBackup)) {
        results.skipped.push({ project, reason: 'No STATE.md - run migrate-gsd first' });
      }
    }

    console.log('\n📋 Legacy File Cleanup Summary:');
    console.log('───────────────────────────────────────');

    if (results.deleted.length > 0) {
      console.log('\n🗑️  Deleted:');
      for (const { project, file } of results.deleted) {
        console.log(`   - ${project}/${file}`);
      }
    }

    if (results.skipped.length > 0) {
      console.log('\n⏭️  Skipped:');
      for (const { project, reason } of results.skipped) {
        console.log(`   - ${project}: ${reason}`);
      }
    }

    if (results.deleted.length === 0 && results.skipped.length === 0) {
      console.log('\n✅ No legacy files found to clean up.');
    }

    console.log('');
  }

  async runScan() {
    await this.scanner.scanMarkdown();
    await this.scanner.scanCode();

    const summary = this.scanner.getProjectSummary();
    console.log('\nProject Summary:');
    console.log(JSON.stringify(summary, null, 2));
  }

  async runAnalyze() {
    await this.scanner.scanMarkdown();
    const analyzer = new QualityAnalyzer(this.scanner.results);
    analyzer.analyzeAll();

    console.log('\nProject Scores:');
    console.log(JSON.stringify(analyzer.getProjectScores(), null, 2));
  }

  async runGenerate() {
    await this.scanner.scanMarkdown();
    const generator = new DocumentGenerator(CONFIG.workspace, this.scanner.results);
    await generator.generateMissing();
  }

  async runValidate() {
    await this.scanner.scanMarkdown();
    const analyzer = new QualityAnalyzer(this.scanner.results);
    analyzer.analyzeAll();

    const lowQuality = Object.entries(analyzer.scores)
      .filter(([, s]) => s.overall < 0.6);

    if (lowQuality.length > 0) {
      console.log('\n⚠️  Low Quality Documents:');
      for (const [path, scores] of lowQuality) {
        console.log(`  - ${path}: ${Math.round(scores.overall * 100)}%`);
      }
    } else {
      console.log('\n✅ All documents pass quality threshold!');
    }
  }

  async runPlans() {
    log('Running plans curation...', 'info');
    const curator = new PlansCurator(CONFIG.workspace);
    const results = await curator.curateAll();

    console.log('\n📋 Plans Curation Summary:');
    console.log('───────────────────────────────────────');

    if (results.created.length > 0) {
      console.log('\n✅ Created PLANS_APPROVED.md for:');
      for (const project of results.created) {
        console.log(`   - ${project}`);
      }
    }

    if (results.updated.length > 0) {
      console.log('\n📝 Updated:');
      for (const project of results.updated) {
        console.log(`   - ${project}`);
      }
    }

    if (results.archived.length > 0) {
      console.log('\n📦 Archived old plans:');
      for (const item of results.archived) {
        console.log(`   - ${item.project}: ${item.count} plans`);
      }
    }

    if (results.created.length === 0 && results.updated.length === 0) {
      console.log('\n✅ All projects already have up-to-date PLANS_APPROVED.md files');
    }

    console.log('');
  }

  async runPractices() {
    log('Running programming practices curation...', 'info');
    const curator = new PracticesCurator(CONFIG.workspace);
    const results = await curator.curateAll();

    console.log('\n📋 Programming Practices Summary:');
    console.log('───────────────────────────────────────');

    if (results.created.length > 0) {
      console.log('\n✅ Created PROGRAMMING_PRACTICES.md for:');
      for (const project of results.created) {
        console.log(`   - ${project}`);
      }
    }

    if (results.updated.length > 0) {
      console.log('\n📝 Already exists:');
      for (const project of results.updated) {
        console.log(`   - ${project}`);
      }
    }

    console.log('');
  }

  async runClaudeMd() {
    log('Running CLAUDE.md curation...', 'info');
    const curator = new ClaudeMdCurator(CONFIG.workspace);
    const results = await curator.curateAll();

    console.log('\n📋 CLAUDE.md Curation Summary:');
    console.log('───────────────────────────────────────');

    if (results.created.length > 0) {
      console.log('\n✅ Created CLAUDE.md for:');
      for (const project of results.created) {
        console.log(`   - ${project}`);
      }
    }

    if (results.suggestions.length > 0) {
      console.log('\n⚠️  Suggestions:');
      for (const item of results.suggestions) {
        console.log(`   ${item.project}:`);
        for (const suggestion of item.suggestions) {
          console.log(`     - ${suggestion}`);
        }
      }
    }

    if (results.created.length === 0 && results.suggestions.length === 0) {
      console.log('\n✅ All project CLAUDE.md files are up to date');
    }

    console.log('');
  }

  async runVariable() {
    log('Running .planning/STATE.md curation (GSD format)...', 'info');
    const curator = new GSDStateCurator(CONFIG.workspace);
    const results = await curator.curateAll();

    console.log('\n📋 STATE.md Curation Summary:');
    console.log('───────────────────────────────────────');

    if (results.updated && results.updated.length > 0) {
      console.log('\n📝 Updated STATE.md for:');
      for (const project of results.updated) {
        console.log(`   - ${project}`);
      }
    }

    if (results.warnings && results.warnings.length > 0) {
      console.log('\n⚠️  Warnings:');
      for (const warning of results.warnings) {
        console.log(`   - ${warning.project}: ${warning.message}`);
      }
    }

    if (!results.updated?.length && !results.warnings?.length) {
      console.log('\n✅ All .planning/STATE.md files are current');
    }

    console.log('');
  }

  async runHistory() {
    log('Fetching documentation history...', 'info');
    const history = new HistoryManager(CONFIG.workspace);
    const summary = await history.getSummary();

    console.log('\n📚 Documentation History Summary:');
    console.log('───────────────────────────────────────');
    console.log(`  Total Documents Tracked: ${summary.totalDocuments}`);
    console.log(`  Total Versions Archived: ${summary.totalVersions}`);
    console.log('');

    if (Object.keys(summary.byProject).length > 0) {
      console.log('  By Project:');
      for (const [project, data] of Object.entries(summary.byProject)) {
        console.log(`    ${project}: ${data.documents} docs, ${data.versions} versions`);
      }
    } else {
      console.log('  No history yet. Run curation commands to start tracking.');
    }

    console.log('');
    console.log('  History stored in: docs-history/');
    console.log('');
  }

  async runLearnings() {
    log('Generating learnings from version history...', 'info');
    const history = new HistoryManager(CONFIG.workspace);

    console.log('\n🎓 Documentation Learnings:');
    console.log('───────────────────────────────────────');

    let hasLearnings = false;

    for (const project of CONFIG.projects) {
      const projectPath = path.join(CONFIG.workspace, project);

      for (const docType of ['CLAUDE.md', '.planning/STATE.md', 'PLANS_APPROVED.md', 'PROGRAMMING_PRACTICES.md']) {
        const docPath = path.join(projectPath, docType);
        const learnings = await history.generateLearnings(docPath);

        if (learnings.patterns && learnings.patterns.length > 0) {
          hasLearnings = true;
          console.log(`\n  📄 ${project}/${docType}:`);
          console.log(`     Versions: ${learnings.totalVersions} (${learnings.dateRange.oldest} → ${learnings.dateRange.newest})`);

          for (const pattern of learnings.patterns) {
            console.log(`     • ${pattern}`);
          }

          if (learnings.recommendations.length > 0) {
            console.log('     Recommendations:');
            for (const rec of learnings.recommendations) {
              console.log(`       → ${rec}`);
            }
          }
        }
      }
    }

    if (!hasLearnings) {
      console.log('\n  Not enough version history to generate learnings.');
      console.log('  Run curation commands multiple times over days/weeks to build history.');
    }

    console.log('');
  }

  async runReport() {
    await this.scanner.scanMarkdown();
    await this.scanner.scanCode();

    const analyzer = new QualityAnalyzer(this.scanner.results);
    analyzer.analyzeAll();

    const reporter = new ReportGenerator(this.scanner.results, analyzer);
    reporter.generateConsoleReport();

    // Save markdown report
    const report = await reporter.generateMarkdownReport();
    const reportPath = path.join(CONFIG.workspace, 'docs-portal', 'HEALTH_REPORT.md');
    await fs.mkdir(path.dirname(reportPath), { recursive: true });
    await fs.writeFile(reportPath, report, 'utf-8');
    log(`Report saved to ${reportPath}`, 'success');
  }

  async runFull() {
    log('Running full documentation pipeline...', 'info');
    console.log('');

    // Step 1: Scan
    log('Step 1/10: Scanning...', 'info');
    await this.scanner.scanMarkdown();
    await this.scanner.scanCode();

    // Step 2: Analyze
    log('Step 2/10: Analyzing...', 'info');
    const analyzer = new QualityAnalyzer(this.scanner.results);
    analyzer.analyzeAll();

    // Step 3: Generate missing base docs
    log('Step 3/10: Generating missing docs...', 'info');
    const generator = new DocumentGenerator(CONFIG.workspace, this.scanner.results);
    await generator.generateMissing();

    // Step 4: Curate CLAUDE.md (Prong 2)
    log('Step 4/10: Curating CLAUDE.md files...', 'info');
    const claudeCurator = new ClaudeMdCurator(CONFIG.workspace);
    await claudeCurator.curateAll();

    // Step 5: Curate root CLAUDE.md (Prong 1)
    log('Step 5/10: Curating root CLAUDE.md...', 'info');
    const rootCurator = new RootClaudeMdCurator(CONFIG.workspace);
    const rootResults = await rootCurator.curateAll();
    if (rootResults.changes.length > 0 || rootResults.warnings.length > 0) {
      log(`Changes: ${rootResults.changes.length}, Warnings: ${rootResults.warnings.length}`, 'success');
    }

    // Step 5.5: Migrate legacy VariableForClMD.md to GSD (if any remain)
    log('Step 5.5/10: Migrating legacy files to GSD...', 'info');
    const migrator = new GsdMigrator(CONFIG.workspace);
    await migrator.migrateAll();

    // Step 6: Curate GSD STATE.md (Prong 3 - session state)
    log('Step 6/10: Curating GSD STATE.md files...', 'info');
    const stateCurator = new StateCurator(CONFIG.workspace);
    await stateCurator.curateAll();

    // Step 7: Curate all 5-Prong docs
    log('Step 7/10: Curating Plans & Practices...', 'info');
    const plansCurator = new PlansCurator(CONFIG.workspace);
    await plansCurator.curateAll();
    const practicesCurator = new PracticesCurator(CONFIG.workspace);
    await practicesCurator.curateAll();

    // Step 8: Generate Trigger Tables
    log('Step 8/10: Generating trigger tables...', 'info');
    const triggerCurator = new TriggerTableCurator(CONFIG.workspace);
    await triggerCurator.curateAll();

    // Step 9: Generate Pattern Library
    log('Step 9/10: Generating pattern library...', 'info');
    const patternCurator = new PatternLibraryCurator(CONFIG.workspace);
    await patternCurator.curate();

    // Step 10: Report
    log('Step 10/10: Generating report...', 'info');
    const reporter = new ReportGenerator(this.scanner.results, analyzer);
    reporter.generateConsoleReport();

    const report = await reporter.generateMarkdownReport();
    const reportPath = path.join(CONFIG.workspace, 'docs-portal', 'HEALTH_REPORT.md');
    await fs.mkdir(path.dirname(reportPath), { recursive: true });
    await fs.writeFile(reportPath, report, 'utf-8');

    log('Pipeline complete!', 'success');
  }

  showHelp() {
    console.log('Usage: node squeegee-manager.js <command>');
    console.log('');
    console.log('Commands:');
    console.log('  scan      Scan all projects for documentation');
    console.log('  analyze   Analyze documentation quality');
    console.log('  generate  Generate missing documentation');
    console.log('  validate  Validate all documentation');
    console.log('  report    Generate health report');
    console.log('');
    console.log('5-Prong Curation:');
    console.log('  root      Curate root CLAUDE.md (Prong 1) - Projects Index, cross-refs');
    console.log('  claudemd  Curate project CLAUDE.md files (Prong 2)');
    console.log('  variable  Curate session state files (Prong 3) - GSD STATE.md (auto-migrates legacy)');
    console.log('  plans     Curate PLANS_APPROVED.md files (Prong 4)');
    console.log('  practices Curate PROGRAMMING_PRACTICES.md files (Prong 5)');
    console.log('');
    console.log('Context Engineering:');
    console.log('  triggers  Generate trigger tables in CLAUDE.md files');
    console.log('  patterns  Generate cross-project pattern library');
    console.log('');
    console.log('History & Learnings:');
    console.log('  history   View version history summary');
    console.log('  learnings Extract patterns from version changes');
    console.log('');
    console.log('GSD (Get Shit Done) Integration:');
    console.log('  migrate-gsd   Migrate legacy VariableForClMD.md to GSD STATE.md format');
    console.log('  clean-legacy  Delete legacy VariableForClMD.md files where STATE.md exists');
    console.log('  gsd-analyze   Analyze GSD artifacts and plan quality metrics');
    console.log('  gsd-issues    Review ISSUES.md and deferred work status');
    console.log('');
    console.log('Pre-commit Hook:');
    console.log('  install-hook  Install git pre-commit hook for auto-curation');
    console.log('');
    console.log('  full      Run complete pipeline (all curation)');
  }
}

// Run
const command = process.argv[2] || 'help';
const manager = new SqueegeeManager();
manager.run(command).catch(console.error);
