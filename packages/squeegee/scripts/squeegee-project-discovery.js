/**
 * Squeegee Project Discovery & Onboarding
 *
 * Automatically detects new and undocumented projects in the workspace,
 * analyzes their tech stack, and generates documentation.
 *
 * Commands:
 *   node squeegee-project-discovery.js discover    - Scan for new projects
 *   node squeegee-project-discovery.js analyze     - Analyze detected projects
 *   node squeegee-project-discovery.js generate    - Generate missing docs
 *   node squeegee-project-discovery.js onboard     - Full onboarding pipeline
 *   node squeegee-project-discovery.js status      - Show project status
 *
 * @author GlassBox Solutions
 * @version 1.0.0
 */

const fs = require('fs').promises;
const path = require('path');
const { execSync } = require('child_process');
const crypto = require('crypto');

// Configuration
const WORKSPACE = process.env.WORKSPACE || '/home/vncuser/Desktop';
const HELPER_URL = 'http://localhost:5678';

// Project detection patterns
const PROJECT_INDICATORS = {
  // Files that indicate a project root
  root_indicators: [
    'package.json',
    'requirements.txt',
    'pyproject.toml',
    'Cargo.toml',
    'go.mod',
    'pom.xml',
    'build.gradle',
    'CLAUDE.md'
  ],

  // Directories to skip
  exclude_patterns: [
    'node_modules',
    '.git',
    '.venv',
    'venv',
    '__pycache__',
    'build',
    'dist',
    '.next',
    '.expo',
    'target',
    '.svelte-kit'
  ],

  // Framework detection
  frameworks: {
    'next.config.js': { framework: 'Next.js', type: 'web', language: 'typescript' },
    'next.config.mjs': { framework: 'Next.js', type: 'web', language: 'typescript' },
    'next.config.ts': { framework: 'Next.js', type: 'web', language: 'typescript' },
    'app.json': { framework: 'Expo', type: 'mobile', language: 'typescript' },
    'capacitor.config.ts': { framework: 'Capacitor', type: 'mobile', language: 'typescript' },
    'vite.config.ts': { framework: 'Vite', type: 'web', language: 'typescript' },
    'svelte.config.js': { framework: 'SvelteKit', type: 'web', language: 'javascript' },
    'docker-compose.yml': { framework: 'Docker', type: 'infrastructure', language: null },
    'main.py': { framework: 'Python', type: 'backend', language: 'python' },
    'manage.py': { framework: 'Django', type: 'backend', language: 'python' },
    'Cargo.toml': { framework: 'Rust', type: 'backend', language: 'rust' }
  }
};

// Documentation requirements by project type
const DOC_REQUIREMENTS = {
  web: {
    required: ['CLAUDE.md', 'README.md'],
    recommended: ['.planning/STATE.md', 'DEPLOYMENT.md'],
    guides: ['FRONTEND_GUIDE.md', 'API_INTEGRATION_GUIDE.md']
  },
  mobile: {
    required: ['CLAUDE.md', 'README.md'],
    recommended: ['.planning/STATE.md', 'BUILD_GUIDE.md'],
    guides: ['MOBILE_DEVELOPMENT_GUIDE.md', 'STORE_SUBMISSION_GUIDE.md']
  },
  backend: {
    required: ['CLAUDE.md', 'README.md'],
    recommended: ['.planning/STATE.md', 'API_DOCUMENTATION.md'],
    guides: ['BACKEND_GUIDE.md', 'DATABASE_GUIDE.md', 'SECURITY_GUIDE.md']
  },
  infrastructure: {
    required: ['CLAUDE.md', 'README.md'],
    recommended: ['.planning/STATE.md', 'DEPLOYMENT.md'],
    guides: ['DOCKER_GUIDE.md', 'INFRASTRUCTURE_GUIDE.md']
  },
  library: {
    required: ['CLAUDE.md', 'README.md'],
    recommended: ['CONTRIBUTING.md', 'CHANGELOG.md'],
    guides: ['API_REFERENCE.md']
  }
};

class ProjectDiscovery {
  constructor() {
    this.projects = [];
    this.stats = {
      discovered: 0,
      undocumented: 0,
      needs_update: 0
    };
  }

  /**
   * Scan workspace for projects
   */
  async discover() {
    console.log('\n=== Squeegee Project Discovery ===\n');
    console.log(`Scanning: ${WORKSPACE}\n`);

    // Known project directories to scan
    const projectDirs = [
      'projects',
      'glassy-web',
      'glassy-mobile',
      'glassy-infra'
    ];

    const projectPaths = [];

    // Scan known directories
    for (const dir of projectDirs) {
      const fullDir = path.join(WORKSPACE, dir);
      try {
        const stats = await fs.stat(fullDir);
        if (stats.isDirectory()) {
          // Check if this is a project itself (glassy-*)
          if (dir.startsWith('glassy-')) {
            const entries = await fs.readdir(fullDir, { withFileTypes: true });
            const fileNames = entries.filter(e => e.isFile()).map(e => e.name);
            if (PROJECT_INDICATORS.root_indicators.some(f => fileNames.includes(f))) {
              projectPaths.push(fullDir);
            }
          } else {
            // Scan subdirectories (projects/)
            const subDirs = await fs.readdir(fullDir, { withFileTypes: true });
            for (const subDir of subDirs) {
              if (subDir.isDirectory() && !subDir.name.startsWith('.')) {
                const subPath = path.join(fullDir, subDir.name);
                const subEntries = await fs.readdir(subPath, { withFileTypes: true });
                const subFileNames = subEntries.filter(e => e.isFile()).map(e => e.name);
                if (PROJECT_INDICATORS.root_indicators.some(f => subFileNames.includes(f))) {
                  projectPaths.push(subPath);
                }
              }
            }
          }
        }
      } catch (e) {
        // Directory doesn't exist, skip
      }
    }

    for (const projectPath of projectPaths) {
      const project = await this.analyzeProject(projectPath);
      if (project) {
        this.projects.push(project);
      }
    }

    this.stats.discovered = this.projects.length;
    this.stats.undocumented = this.projects.filter(p => !p.has_claude_md).length;
    this.stats.needs_update = this.projects.filter(p => p.documentation_score < 0.50).length;

    console.log('\n=== Discovery Results ===\n');
    console.log(`Total Projects: ${this.stats.discovered}`);
    console.log(`Undocumented:   ${this.stats.undocumented}`);
    console.log(`Needs Update:   ${this.stats.needs_update}`);
    console.log('');

    return this.projects;
  }

  /**
   * Recursively find project directories
   */
  async findProjects(dir, depth = 0) {
    const projects = [];

    // Limit depth to prevent deep recursion
    if (depth > 3) return projects;

    try {
      const entries = await fs.readdir(dir, { withFileTypes: true });

      // Check if this directory is a project root
      const isProject = await this.isProjectRoot(dir, entries);
      if (isProject) {
        projects.push(dir);
        // Don't recurse into project subdirectories
        return projects;
      }

      // Recurse into subdirectories
      for (const entry of entries) {
        if (!entry.isDirectory()) continue;

        // Skip excluded directories
        if (PROJECT_INDICATORS.exclude_patterns.includes(entry.name)) continue;
        if (entry.name.startsWith('.')) continue;

        const subDir = path.join(dir, entry.name);
        const subProjects = await this.findProjects(subDir, depth + 1);
        projects.push(...subProjects);
      }
    } catch (error) {
      // Ignore permission errors
    }

    return projects;
  }

  /**
   * Check if directory is a project root
   */
  async isProjectRoot(dir, entries) {
    const fileNames = entries.filter(e => e.isFile()).map(e => e.name);

    for (const indicator of PROJECT_INDICATORS.root_indicators) {
      if (fileNames.includes(indicator)) {
        return true;
      }
    }

    return false;
  }

  /**
   * Analyze a single project
   */
  async analyzeProject(projectPath) {
    const relativePath = path.relative(WORKSPACE, projectPath).replace(/\\/g, '/');
    const projectName = path.basename(projectPath);

    console.log(`Analyzing: ${relativePath}`);

    try {
      const entries = await fs.readdir(projectPath, { withFileTypes: true });
      const fileNames = entries.filter(e => e.isFile()).map(e => e.name);
      const dirNames = entries.filter(e => e.isDirectory()).map(e => e.name);

      // Detect framework and type
      const detection = this.detectFramework(fileNames);

      // Count files
      const fileStats = await this.countFiles(projectPath);

      // Check documentation status
      const docStatus = await this.checkDocumentation(projectPath, fileNames, dirNames);

      // Calculate documentation score
      const docScore = this.calculateDocScore(docStatus);

      const project = {
        project_name: projectName,
        project_path: relativePath,
        project_type: detection.type || 'unknown',
        detected_languages: detection.languages,
        detected_frameworks: detection.frameworks,
        package_managers: this.detectPackageManagers(fileNames),

        // Documentation status
        has_claude_md: docStatus.has_claude_md,
        has_state_md: docStatus.has_state_md,
        has_readme: docStatus.has_readme,
        has_subsystem_guides: docStatus.has_guides,
        documentation_score: docScore,
        missing_docs: docStatus.missing,

        // File stats
        total_files: fileStats.total,
        total_code_files: fileStats.code,
        total_markdown_files: fileStats.markdown,

        // Onboarding
        onboarding_status: docStatus.has_claude_md ? 'complete' : 'discovered',
        needs_onboarding: !docStatus.has_claude_md || docScore < 0.50
      };

      return project;

    } catch (error) {
      console.error(`  Error: ${error.message}`);
      return null;
    }
  }

  /**
   * Detect framework from files
   */
  detectFramework(fileNames) {
    const result = {
      type: null,
      frameworks: [],
      languages: []
    };

    for (const [file, info] of Object.entries(PROJECT_INDICATORS.frameworks)) {
      if (fileNames.includes(file)) {
        result.frameworks.push(info.framework);
        if (info.type && !result.type) result.type = info.type;
        if (info.language && !result.languages.includes(info.language)) {
          result.languages.push(info.language);
        }
      }
    }

    // Detect languages from file extensions
    if (fileNames.some(f => f.endsWith('.py'))) result.languages.push('python');
    if (fileNames.some(f => f.endsWith('.ts') || f.endsWith('.tsx'))) result.languages.push('typescript');
    if (fileNames.some(f => f.endsWith('.js') || f.endsWith('.jsx'))) result.languages.push('javascript');

    // Remove duplicates
    result.languages = [...new Set(result.languages)];
    result.frameworks = [...new Set(result.frameworks)];

    return result;
  }

  /**
   * Detect package managers
   */
  detectPackageManagers(fileNames) {
    const managers = [];
    if (fileNames.includes('package.json')) managers.push('npm');
    if (fileNames.includes('yarn.lock')) managers.push('yarn');
    if (fileNames.includes('pnpm-lock.yaml')) managers.push('pnpm');
    if (fileNames.includes('requirements.txt')) managers.push('pip');
    if (fileNames.includes('pyproject.toml')) managers.push('poetry');
    if (fileNames.includes('Pipfile')) managers.push('pipenv');
    return managers;
  }

  /**
   * Count files in project
   */
  async countFiles(projectPath) {
    const stats = { total: 0, code: 0, markdown: 0 };

    try {
      const output = execSync(`git ls-files`, {
        cwd: projectPath,
        encoding: 'utf-8',
        stdio: ['pipe', 'pipe', 'pipe']
      });

      const files = output.split('\n').filter(f => f.trim());
      stats.total = files.length;

      for (const file of files) {
        if (file.endsWith('.md')) stats.markdown++;
        if (file.match(/\.(py|ts|tsx|js|jsx|rs|go|java|rb)$/)) stats.code++;
      }
    } catch {
      // Not a git repo or git not available
      stats.total = -1;
    }

    return stats;
  }

  /**
   * Check documentation status
   */
  async checkDocumentation(projectPath, fileNames, dirNames) {
    // Check for .planning/STATE.md
    let hasStateMd = false;
    try {
      await fs.access(path.join(projectPath, '.planning', 'STATE.md'));
      hasStateMd = true;
    } catch {
      hasStateMd = false;
    }

    const status = {
      has_claude_md: fileNames.includes('CLAUDE.md'),
      has_state_md: hasStateMd,
      has_readme: fileNames.includes('README.md') || fileNames.includes('readme.md'),
      has_guides: dirNames.includes('docs') || fileNames.some(f => f.includes('GUIDE')),
      missing: []
    };

    if (!status.has_claude_md) status.missing.push('CLAUDE.md');
    if (!status.has_state_md) status.missing.push('.planning/STATE.md');
    if (!status.has_readme) status.missing.push('README.md');

    return status;
  }

  /**
   * Calculate documentation score
   */
  calculateDocScore(docStatus) {
    let score = 0;
    if (docStatus.has_claude_md) score += 0.40;
    if (docStatus.has_readme) score += 0.25;
    if (docStatus.has_state_md) score += 0.20;
    if (docStatus.has_guides) score += 0.15;
    return Math.round(score * 100) / 100;
  }

  /**
   * Generate documentation for undocumented projects
   */
  async generateDocumentation(project) {
    console.log(`\nGenerating documentation for: ${project.project_name}`);

    const generated = [];

    // Generate CLAUDE.md if missing
    if (!project.has_claude_md) {
      const claudeMd = await this.generateClaudeMd(project);
      if (claudeMd) {
        generated.push('CLAUDE.md');
        console.log('  [+] Generated CLAUDE.md');
      }
    }

    // Generate .planning/STATE.md if missing
    if (!project.has_state_md) {
      const stateMd = await this.generateStateMd(project);
      if (stateMd) {
        generated.push('.planning/STATE.md');
        console.log('  [+] Generated .planning/STATE.md');
      }
    }

    return generated;
  }

  /**
   * Generate CLAUDE.md content
   */
  async generateClaudeMd(project) {
    const techStack = project.detected_frameworks.join(', ') || 'Not detected';
    const languages = project.detected_languages.join(', ') || 'Not detected';

    const content = `# CLAUDE.md - ${project.project_name}

This file provides guidance to Claude Code when working on ${project.project_name}.

## Project Overview

${project.project_name} is a ${project.project_type} project.

**Tech Stack:** ${techStack}
**Languages:** ${languages}

## Commands

\`\`\`bash
# Development
${project.package_managers.includes('npm') ? 'npm install              # Install dependencies\nnpm run dev               # Start development server' : ''}
${project.package_managers.includes('pip') ? 'pip install -r requirements.txt  # Install dependencies\npython main.py                    # Run application' : ''}

# Testing
${project.package_managers.includes('npm') ? 'npm test                  # Run tests' : ''}
${project.package_managers.includes('pip') ? 'pytest                    # Run tests' : ''}
\`\`\`

## Directory Structure

\`\`\`
${project.project_path}/
├── src/                  # Source code
├── tests/                # Test files
└── docs/                 # Documentation
\`\`\`

## Architecture

> TODO: Add architecture description

## Critical Environment Variables

\`\`\`env
# TODO: Add required environment variables
\`\`\`

## Quick Troubleshooting

> TODO: Add common issues and solutions

---

*Generated by Squeegee Documentation System*
*Last updated: ${new Date().toISOString().split('T')[0]}*
`;

    try {
      const filePath = path.join(WORKSPACE, project.project_path, 'CLAUDE.md');
      await fs.writeFile(filePath, content, 'utf-8');
      return true;
    } catch (error) {
      console.error(`  Error writing CLAUDE.md: ${error.message}`);
      return false;
    }
  }

  /**
   * Generate .planning/STATE.md content (GSD format)
   */
  async generateStateMd(project) {
    const content = `# ${project.project_name} - Session State

## Current Focus

Initial project setup and documentation.

## Session

| Field | Value |
|-------|-------|
| Started | ${new Date().toISOString()} |
| Phase | Setup |
| Status | In Progress |

## Active Tasks

- [ ] Complete project documentation
- [ ] Set up development environment
- [ ] Define project architecture

## Context

This STATE.md file was auto-generated by Squeegee.
Update with current work focus when starting a session.

## Blockers

None currently.

---

*Generated by Squeegee Documentation System*
`;

    try {
      // Create .planning directory if it doesn't exist
      const planningDir = path.join(WORKSPACE, project.project_path, '.planning');
      await fs.mkdir(planningDir, { recursive: true });

      const filePath = path.join(planningDir, 'STATE.md');
      await fs.writeFile(filePath, content, 'utf-8');
      return true;
    } catch (error) {
      console.error(`  Error writing .planning/STATE.md: ${error.message}`);
      return false;
    }
  }

  /**
   * Show project status
   */
  showStatus() {
    console.log('\n=== Project Documentation Status ===\n');
    console.log('Project'.padEnd(35) + 'Type'.padEnd(15) + 'Score'.padEnd(8) + 'Status');
    console.log('-'.repeat(70));

    for (const project of this.projects.sort((a, b) => a.documentation_score - b.documentation_score)) {
      const status = project.has_claude_md ? '[OK]' : '[MISSING]';
      const score = (project.documentation_score * 100).toFixed(0) + '%';
      console.log(
        project.project_name.substring(0, 33).padEnd(35) +
        (project.project_type || 'unknown').padEnd(15) +
        score.padEnd(8) +
        status
      );

      if (project.missing_docs.length > 0) {
        console.log(`  Missing: ${project.missing_docs.join(', ')}`);
      }
    }

    console.log('');
  }

  /**
   * Full onboarding pipeline
   */
  async onboard() {
    console.log('\n=== Squeegee Project Onboarding ===\n');

    // Step 1: Discover projects
    await this.discover();

    // Step 2: Find undocumented projects
    const undocumented = this.projects.filter(p => p.needs_onboarding);

    if (undocumented.length === 0) {
      console.log('\nAll projects are documented!');
      return;
    }

    console.log(`\nFound ${undocumented.length} projects needing documentation:\n`);

    for (const project of undocumented) {
      console.log(`  - ${project.project_name} (${project.project_type})`);
    }

    // Step 3: Generate documentation
    console.log('\n--- Generating Documentation ---\n');

    let generated = 0;
    for (const project of undocumented) {
      const files = await this.generateDocumentation(project);
      generated += files.length;
    }

    console.log(`\n=== Onboarding Complete ===`);
    console.log(`Generated ${generated} documentation files`);
    console.log('');
  }
}

// CLI interface
async function main() {
  const command = process.argv[2] || 'status';
  const discovery = new ProjectDiscovery();

  switch (command) {
    case 'discover':
      await discovery.discover();
      discovery.showStatus();
      break;

    case 'analyze':
      await discovery.discover();
      console.log('\n=== Detailed Analysis ===\n');
      console.log(JSON.stringify(discovery.projects, null, 2));
      break;

    case 'generate':
      await discovery.discover();
      const undoc = discovery.projects.filter(p => p.needs_onboarding);
      for (const project of undoc) {
        await discovery.generateDocumentation(project);
      }
      break;

    case 'onboard':
      await discovery.onboard();
      break;

    case 'status':
    default:
      await discovery.discover();
      discovery.showStatus();
      break;
  }
}

main().catch(console.error);
