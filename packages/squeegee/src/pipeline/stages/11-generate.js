/**
 * Stage 11: Generate Missing Documentation
 *
 * Scans for projects missing 5-prong docs (CLAUDE.md, STATE.md,
 * PROGRAMMING_PRACTICES.md, PLANS_APPROVED.md) and generates them
 * with REAL content derived from package.json, directory structure,
 * git history, and stack detection — not placeholder stubs.
 *
 * Replaces DocumentGenerator.generateMissing() from the monolith.
 *
 * @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
 */

const fs = require('fs').promises;
const path = require('path');
const { execSync } = require('child_process');
const { log, fileExists, ensureDir, readJsonSafe, readFileSafe, listDirs } = require('../utils');
const { resolveProjectPath } = require('../config');
const { detectStack } = require('../analyzers/stack-detector');
const { heading, table, bulletList, codeBlock, divider, timestamp, bold, link } = require('../formatters/markdown');

/**
 * Run the generate stage.
 *
 * @param {object} config - Squeegee config from loadConfig()
 * @param {object} discovery - Results from stage 01 (optional, may be null)
 * @returns {{ created: string[], skipped: string[] }}
 */
async function run(config, discovery) {
  log('Stage 11: Generating missing documentation...', 'info');

  const results = { created: [], skipped: [] };

  for (const project of config.projects) {
    const projectPath = resolveProjectPath(config, project.path);

    if (!(await fileExists(projectPath))) {
      results.skipped.push(`${project.name} (path not found)`);
      continue;
    }

    const missing = await detectMissingDocs(projectPath);

    if (missing.length === 0) {
      results.skipped.push(project.name);
      continue;
    }

    // Gather project intelligence once for all generators
    const intel = await gatherProjectIntel(projectPath, project, config);

    for (const docType of missing) {
      // Skip CLAUDE.md generation in docsRepo mode — CLAUDE.md stays in source repos
      if (config.docsRepo?.enabled && docType === 'CLAUDE.md') {
        log(`Skipping CLAUDE.md for ${project.name} (docsRepo mode)`, 'info');
        continue;
      }

      try {
        await generateDoc(docType, projectPath, project, intel, config);
        results.created.push(`${project.name}/${docType}`);
      } catch (e) {
        log(`Failed to generate ${docType} for ${project.name}: ${e.message}`, 'warn');
      }
    }
  }

  log(`Generate — created: ${results.created.length}, skipped: ${results.skipped.length}`, 'success');
  return results;
}

// ---------------------------------------------------------------------------
// Detection
// ---------------------------------------------------------------------------

/**
 * Check which of the 4 key docs are missing for a project.
 * Returns array of missing doc type identifiers.
 */
async function detectMissingDocs(projectPath) {
  const checks = [
    { type: 'CLAUDE.md', path: path.join(projectPath, 'CLAUDE.md') },
    { type: 'STATE.md', path: path.join(projectPath, '.planning', 'STATE.md') },
    { type: 'PROGRAMMING_PRACTICES.md', path: path.join(projectPath, 'PROGRAMMING_PRACTICES.md') },
    { type: 'PLANS_APPROVED.md', path: path.join(projectPath, 'PLANS_APPROVED.md') },
  ];

  const missing = [];
  for (const check of checks) {
    if (!(await fileExists(check.path))) {
      missing.push(check.type);
    }
  }
  return missing;
}

// ---------------------------------------------------------------------------
// Project Intelligence Gathering
// ---------------------------------------------------------------------------

/**
 * Gather all useful data about a project to feed into templates.
 * Reads package.json, detects stack, scans directories, pulls git history.
 */
async function gatherProjectIntel(projectPath, project, config) {
  const intel = {
    name: project.name,
    description: '',
    commands: [],
    stack: await detectStack(projectPath),
    directories: [],
    envVars: [],
    recentCommits: [],
    structureTree: '',
  };

  // -- package.json analysis --
  const pkg = await readJsonSafe(path.join(projectPath, 'package.json'));
  if (pkg) {
    intel.description = pkg.description || '';

    // Extract commands from scripts with real descriptions
    if (pkg.scripts) {
      const scriptDescriptions = {
        dev: 'Start development server',
        start: 'Start production server',
        build: 'Build for production',
        test: 'Run test suite',
        lint: 'Lint source files',
        format: 'Format source files',
        preview: 'Preview production build',
        typecheck: 'Run TypeScript type checks',
        'type-check': 'Run TypeScript type checks',
        generate: 'Run code generation',
        migrate: 'Run database migrations',
        seed: 'Seed database',
        clean: 'Clean build artifacts',
        'test:e2e': 'Run end-to-end tests',
        'test:unit': 'Run unit tests',
        'test:cov': 'Run tests with coverage',
        'db:push': 'Push Prisma schema to DB',
        'db:generate': 'Generate Prisma client',
        'db:migrate': 'Run Prisma migrations',
        'db:studio': 'Open Prisma Studio',
      };

      for (const [script, command] of Object.entries(pkg.scripts)) {
        const desc = scriptDescriptions[script] || `Run \`${command}\``;
        const cmd = script.includes(':') ? `npm run ${script}` : `npm run ${script}`;
        intel.commands.push({ cmd, desc, raw: command });
      }
    }
  }

  // -- Python project analysis --
  const hasReqs = await fileExists(path.join(projectPath, 'requirements.txt'));
  if (hasReqs && intel.commands.length === 0) {
    intel.commands.push(
      { cmd: 'pip install -r requirements.txt', desc: 'Install dependencies', raw: '' },
      { cmd: 'python main.py', desc: 'Run application', raw: '' },
    );
  }

  // -- Directory structure --
  const dirPurposes = {
    'src': 'Source code',
    'app': 'Application routes and views',
    'components': 'React/UI components',
    'pages': 'Page components / routes',
    'api': 'API routes and endpoints',
    'lib': 'Utility libraries',
    'utils': 'Utility functions',
    'hooks': 'React hooks',
    'services': 'Service layer',
    'models': 'Data models',
    'tests': 'Test files',
    'test': 'Test files',
    '__tests__': 'Test files (Jest convention)',
    'docs': 'Documentation',
    'public': 'Static/public assets',
    'assets': 'Media assets',
    'styles': 'Stylesheets',
    'prisma': 'Prisma schema and migrations',
    'server': 'Server-side code',
    'shared': 'Shared code (client + server)',
    'scripts': 'Build/utility scripts',
    'packages': 'Monorepo packages',
    'config': 'Configuration files',
    'middleware': 'Middleware modules',
    'types': 'TypeScript type definitions',
    'stores': 'State management stores',
    'events': 'Event handlers / definitions',
    'forms': 'Form definitions / schemas',
  };

  const allDirs = await listDirs(projectPath);
  const visibleDirs = allDirs.filter(d => !d.startsWith('.') && d !== 'node_modules' && d !== 'dist' && d !== 'build' && d !== 'coverage');

  for (const dir of visibleDirs) {
    intel.directories.push({
      name: dir,
      purpose: dirPurposes[dir] || 'Project directory',
    });
  }

  intel.structureTree = visibleDirs.slice(0, 12).map(d => `├── ${d}/`).join('\n');

  // -- .env.example --
  const envExample = await readFileSafe(path.join(projectPath, '.env.example'));
  if (envExample) {
    intel.envVars = envExample.split('\n')
      .filter(l => l && !l.startsWith('#') && l.includes('='))
      .map(l => l.split('=')[0].trim())
      .filter(Boolean)
      .slice(0, 15);
  }

  // -- Git recent commits --
  intel.recentCommits = getRecentCommits(config.workspace, project.path, 10);

  // -- Defaults when nothing was detected --
  if (intel.commands.length === 0) {
    intel.commands = [
      { cmd: 'npm install', desc: 'Install dependencies', raw: '' },
      { cmd: 'npm run dev', desc: 'Start development', raw: '' },
    ];
  }

  if (intel.directories.length === 0) {
    intel.directories = [{ name: 'src', purpose: 'Source code' }];
  }

  return intel;
}

/**
 * Get recent git commits for a project path.
 * Returns array of { date, description } objects.
 */
function getRecentCommits(workspace, projectRelPath, count) {
  try {
    const raw = execSync(
      `git log --format="%aI|%s" --max-count=${count} -- "${projectRelPath}"`,
      { cwd: workspace, encoding: 'utf-8', maxBuffer: 5 * 1024 * 1024, stdio: ['pipe', 'pipe', 'ignore'] }
    ).trim();

    if (!raw) return [];

    return raw.split('\n').filter(Boolean).map(line => {
      const sepIdx = line.indexOf('|');
      const date = line.slice(0, sepIdx).split('T')[0];
      const subject = line.slice(sepIdx + 1);

      // Parse conventional commit
      const ccMatch = subject.match(/^(\w+)(?:\(([^)]+)\))?:\s*(.+)/);
      return {
        date,
        type: ccMatch ? ccMatch[1] : null,
        description: ccMatch ? ccMatch[3] : subject,
      };
    });
  } catch {
    return [];
  }
}

// ---------------------------------------------------------------------------
// Document Generation Router
// ---------------------------------------------------------------------------

async function generateDoc(docType, projectPath, project, intel, config) {
  switch (docType) {
    case 'CLAUDE.md':
      return generateClaudeMd(projectPath, project, intel);
    case 'STATE.md':
      return generateStateMd(projectPath, project, intel);
    case 'PROGRAMMING_PRACTICES.md':
      return generatePracticesMd(projectPath, project, intel);
    case 'PLANS_APPROVED.md':
      return generatePlansMd(projectPath, project, intel);
    default:
      log(`Unknown doc type: ${docType}`, 'warn');
  }
}

// ---------------------------------------------------------------------------
// CLAUDE.md Generator
// ---------------------------------------------------------------------------

async function generateClaudeMd(projectPath, project, intel) {
  const date = timestamp();
  const { name, description, commands, stack, directories, envVars, structureTree } = intel;

  // Build tech stack section with real data
  const stackItems = [];
  if (stack.language) stackItems.push(`${bold('Language:')} ${stack.language}`);
  for (const fw of stack.frameworks) stackItems.push(`${bold('Framework:')} ${fw}`);
  for (const tool of stack.tools) stackItems.push(`${bold('Tool:')} ${tool}`);
  const stackSection = stackItems.length > 0
    ? stackItems.map(s => `- ${s}`).join('\n')
    : '- *Stack not auto-detected — update manually*';

  // Build commands table from real package.json scripts
  const cmdHeaders = ['Command', 'Description'];
  const cmdRows = commands.slice(0, 12).map(c => [`\`${c.cmd}\``, c.desc]);

  // Build directories table from real directory scan
  const dirHeaders = ['Directory', 'Purpose'];
  const dirRows = directories.slice(0, 10).map(d => [`\`${d.name}/\``, d.purpose]);

  // Build env vars section
  const envSection = envVars.length > 0
    ? codeBlock(envVars.map(e => `${e}=`).join('\n'), 'bash')
    : '```bash\n# No .env.example found — add environment variables here\n```';

  // Build architecture section
  const archSection = structureTree
    ? codeBlock(structureTree)
    : '```\n# Directory structure not detected\n```';

  const content = `# ${name} - Claude Code Configuration

${bold('Purpose:')} ${description || '[Project description — needs manual enrichment]'}
${bold('Status:')} Active
${bold('Last Updated:')} ${date}

---

## Quick Reference

${table(cmdHeaders, cmdRows)}

---

## Tech Stack

${stackSection}

---

## Architecture Overview

${archSection}

*Note: This is the detected directory layout. Add architectural notes manually for richer context.*

---

## Key Directories

${table(dirHeaders, dirRows)}

---

## Environment Setup

Required environment variables:
${envSection}

---

## Security & Secrets

<!-- SQUEEGEE:AUTO:START security-secrets -->
**All secrets are managed through GCP Secret Manager** (project: \`adjudica-internal\`).

**What qualifies as a secret:**
- API keys, tokens, and credentials (GitHub PAT, OAuth secrets, service account keys)
- Database connection strings with credentials
- Encryption keys and signing secrets
- Any value that grants access to a system or service

**Rules:**
- NEVER hardcode secrets in source code, config files, or documentation
- NEVER expose secrets in chat, logs, commit messages, or error output
- NEVER commit \`.env\` files — use \`.env.example\` with placeholder values only
- Access secrets via environment variables injected by Cloud Run or local \`.env\`
- For Cloud Run services: secrets are volume-mounted or set as env vars via Secret Manager
- Report any suspected secret exposure immediately
<!-- SQUEEGEE:AUTO:END security-secrets -->

---

## Linked Resources Are Directives

<!-- SQUEEGEE:AUTO:START linked-resources -->
**The following linked resources are not suggestions — they are authoritative directives.**

Every Claude agent working in this repo MUST read and follow:

1. **Parent CLAUDE.md** (\`~/Desktop/CLAUDE.md\`) — the master configuration for all GBS projects. Its instructions override any project-level defaults.
2. **Adjudica Documentation Hub** (\`~/Desktop/adjudica-documentation/CLAUDE.md\`) — centralized business, legal, marketing, and product documentation. Consult before making decisions that touch these domains.
3. **Engineering Standards** (\`PROGRAMMING_PRACTICES.md\`) — project-specific code conventions and stack decisions.

These are not "see also" links. Failure to consult linked resources before acting is a violation of GBS operating procedure. When in doubt, read the linked resource first.
<!-- SQUEEGEE:AUTO:END linked-resources -->

---

## GBS Core Principles

<!-- SQUEEGEE:AUTO:START gbs-core-principles -->
These principles are non-negotiable across all GBS projects:

- **Think before ALL actions** — not just big ones. Every file edit, every command, every commit deserves a moment of consideration.
- **Assess impact on other systems** — before changing code, consider what else depends on it. Check callers, consumers, and downstream effects.
- **Plan first, then execute** — never act without understanding the current state. Read before writing. Understand before modifying.
- **Root cause analysis is mandatory** — no quick fixes, no band-aids. If something is broken, find out WHY before applying a fix.
- **Use agents and tools** — never guess when you can verify. Use search, read files, check git history. Guessing leads to reckless behavior.
- **No reckless or destructive behavior** — measure twice, cut once. Prefer reversible actions. Ask before deleting, force-pushing, or overwriting.
- **Respect the codebase** — you are a guest in existing code. Match existing patterns, don't impose new ones without approval.
<!-- SQUEEGEE:AUTO:END gbs-core-principles -->

---

## Context Window & Checkpoint Protocol

<!-- SQUEEGEE:AUTO:START context-window -->
Agents MUST manage context window proactively:

**Checkpoint Format** (write to \`.planning/STATE.md\` or current task file):
\`\`\`
## Checkpoint [YYYY-MM-DD HH:MM]
**Task:** [current objective]
**Completed:** [what's done]
**In Progress:** [current work]
**Next Steps:** [what remains]
**Key Decisions:** [decisions made and why]
**Blockers:** [anything blocking progress]
\`\`\`

**When to Checkpoint:**
- Before any context-heavy operation (large file reads, multi-file refactors)
- After completing each logical unit of work
- Every 3 tool calls during complex tasks
- Before and after running tests or builds
- When switching between files or subsystems

**Handoff Protocol:**
- When approaching context limits, write a complete checkpoint BEFORE the window compresses
- Include enough detail that a fresh agent can continue without re-reading everything
- List exact file paths, line numbers, and remaining tasks
<!-- SQUEEGEE:AUTO:END context-window -->

---

## Centralized Documentation & Planning

<!-- SQUEEGEE:AUTO:START centralized-docs -->
GBS maintains centralized documentation that all agents must consult:

- **Adjudica Documentation Hub** — \`~/Desktop/adjudica-documentation/\`
  - Business strategy, legal documents, marketing materials, product specs
  - [Quick Index](\`~/Desktop/adjudica-documentation/ADJUDICA_INDEX.md\`)
- **Project Planning** — \`.planning/\` directory in each repo
  - \`STATE.md\` — current session context (GSD format)
  - \`ROADMAP.md\` — project vision and phases
  - \`ISSUES.md\` — deferred work and known issues
  - \`phases/\` — per-phase plans and summaries
- **Work Logs** — document decisions and progress in \`.planning/STATE.md\`
  - Every significant decision gets recorded with rationale
  - Session handoffs must update STATE.md before ending
<!-- SQUEEGEE:AUTO:END centralized-docs -->

---

## Related Documentation

- ${link('.planning/STATE.md', '.planning/STATE.md')} - Current session context (GSD format)
- ${link('PLANS_APPROVED.md', 'PLANS_APPROVED.md')} - Plan history and outcomes
- ${link('PROGRAMMING_PRACTICES.md', 'PROGRAMMING_PRACTICES.md')} - Code conventions and stack

---

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology

*Generated by Squeegee Documentation System*
`;

  const filePath = path.join(projectPath, 'CLAUDE.md');
  await fs.writeFile(filePath, content, 'utf-8');
  log(`Created CLAUDE.md for ${name}`, 'success');
}

// ---------------------------------------------------------------------------
// STATE.md Generator (GSD format, compatible with 03-state-curate.js)
// ---------------------------------------------------------------------------

async function generateStateMd(projectPath, project, intel) {
  const date = timestamp();
  const { name, recentCommits } = intel;

  // Build recent activity from git history (like 03-state-curate.js does)
  let recentActivity = '- GSD structure created by Squeegee';
  if (recentCommits.length > 0) {
    recentActivity = recentCommits.slice(0, 8).map(c => {
      const typeTag = c.type ? `${bold(c.type + ':')} ` : '';
      return `- \`${c.date}\` ${typeTag}${c.description}`;
    }).join('\n');
  }

  const content = `# ${name} - Project State

${bold('Last Updated:')} ${date}
${bold('Status:')} Active Development
${bold('Current Phase:')} N/A (No phases defined yet)

---

## Current Focus

*No active task — awaiting instructions*

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

<!-- SQUEEGEE:AUTO:START recent-activity -->
${recentActivity}
<!-- SQUEEGEE:AUTO:END recent-activity -->

---

## Quick Links

- ${link('ROADMAP.md', 'ROADMAP.md')} - Project roadmap
- ${link('ISSUES.md', 'ISSUES.md')} - Deferred work and issues
- ${link('CLAUDE.md', '../CLAUDE.md')} - Project technical reference

---

*Managed by Squeegee Documentation System*
`;

  // Create the full .planning directory structure
  const planningDir = path.join(projectPath, '.planning');
  const phasesDir = path.join(planningDir, 'phases');
  await ensureDir(phasesDir);

  // Write STATE.md
  await fs.writeFile(path.join(planningDir, 'STATE.md'), content, 'utf-8');
  log(`Created .planning/STATE.md for ${name}`, 'success');

  // Also create ISSUES.md and ROADMAP.md if missing
  const issuesPath = path.join(planningDir, 'ISSUES.md');
  if (!(await fileExists(issuesPath))) {
    await fs.writeFile(issuesPath, generateIssuesContent(name, date), 'utf-8');
    log(`Created .planning/ISSUES.md for ${name}`, 'success');
  }

  const roadmapPath = path.join(planningDir, 'ROADMAP.md');
  if (!(await fileExists(roadmapPath))) {
    await fs.writeFile(roadmapPath, generateRoadmapContent(name, date), 'utf-8');
    log(`Created .planning/ROADMAP.md for ${name}`, 'success');
  }
}

function generateIssuesContent(projectName, date) {
  return `# ${projectName} - Issues & Deferred Work

${bold('Last Updated:')} ${date}
${bold('Managed by:')} Squeegee

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

*Managed by Squeegee Documentation System*
`;
}

function generateRoadmapContent(projectName, date) {
  return `# ${projectName} - Roadmap

${bold('Last Updated:')} ${date}
${bold('Status:')} Draft (needs completion)

---

## Vision

*Define the long-term vision for this project.*

---

## Phases

### Phase 1: [Name TBD]
${bold('Status:')} Not Started
${bold('Target:')} TBD

*Define phase objectives and success criteria.*

---

## Success Metrics

- [ ] Metric 1: [Define]
- [ ] Metric 2: [Define]

---

## Dependencies

*External dependencies and blockers:*

---

*Managed by Squeegee Documentation System*
`;
}

// ---------------------------------------------------------------------------
// PROGRAMMING_PRACTICES.md Generator
// ---------------------------------------------------------------------------

async function generatePracticesMd(projectPath, project, intel) {
  const date = timestamp();
  const { name, stack } = intel;

  // Build tech stack list
  const techItems = [];
  if (stack.language) techItems.push(stack.language);
  techItems.push(...stack.frameworks);
  techItems.push(...stack.tools);
  techItems.push(...stack.conventions.filter(c =>
    ['TypeScript', 'ESLint', 'Prettier', 'Black', 'Ruff', 'MyPy'].includes(c)
  ));
  const techContent = techItems.length > 0
    ? techItems.map(s => `- ${s}`).join('\n')
    : '*Not detected — add manually*';

  // Build dependencies list
  const depsContent = stack.dependencies.length > 0
    ? '```\n' + stack.dependencies.join('\n') + '\n```'
    : '*See package.json or requirements.txt*';

  // Build testing section
  const testContent = stack.testing.length > 0
    ? stack.testing.map(t => `- ${t}`).join('\n')
    : '*Testing framework not detected*';

  // Build architecture patterns
  const archPatterns = stack.conventions
    .filter(c => !['TypeScript', 'ESLint', 'Prettier', 'Black', 'Ruff', 'MyPy'].includes(c));
  const archContent = archPatterns.length > 0
    ? archPatterns.map(p => `- ${p}`).join('\n')
    : '*No patterns detected*';

  const content = `# ${name} - Programming Practices

${bold('Last Updated:')} ${date}
${bold('Curated by:')} Squeegee

---

## Tech Stack

<!-- SQUEEGEE:AUTO:START tech-stack -->
${techContent}
<!-- SQUEEGEE:AUTO:END tech-stack -->

---

## Architecture Patterns

${archContent}

---

## Code Conventions

- Follow existing code style
- Use meaningful variable names
- Keep functions focused and small

---

## Key Dependencies

<!-- SQUEEGEE:AUTO:START dependencies -->
${depsContent}
<!-- SQUEEGEE:AUTO:END dependencies -->

---

## Testing Approach

<!-- SQUEEGEE:AUTO:START testing -->
${testContent}
<!-- SQUEEGEE:AUTO:END testing -->

---

## Project-Specific Notes

*Add project-specific programming practices here.*

---

*Managed by Squeegee Documentation System*
`;

  const filePath = path.join(projectPath, 'PROGRAMMING_PRACTICES.md');
  await ensureDir(path.dirname(filePath));
  await fs.writeFile(filePath, content, 'utf-8');
  log(`Created PROGRAMMING_PRACTICES.md for ${name}`, 'success');
}

// ---------------------------------------------------------------------------
// PLANS_APPROVED.md Generator
// ---------------------------------------------------------------------------

async function generatePlansMd(projectPath, project, intel) {
  const date = timestamp();
  const { name, recentCommits } = intel;

  // If there is git history, create a "reconstructed" entry summarizing recent work
  let plansSection = '*No plans recorded yet.*';
  if (recentCommits.length > 0) {
    // Group commits by date for a rough summary
    const byDate = {};
    for (const c of recentCommits) {
      if (!byDate[c.date]) byDate[c.date] = [];
      byDate[c.date].push(c);
    }

    const entries = [];
    const sortedDates = Object.keys(byDate).sort().reverse();
    let planNum = 1;

    for (const d of sortedDates.slice(0, 5)) {
      const commits = byDate[d];
      const summary = commits.map(c => {
        const typeTag = c.type ? `(${c.type}) ` : '';
        return `  - ${typeTag}${c.description}`;
      }).join('\n');

      entries.push(`### [PLAN-${d}-${String(planNum).padStart(2, '0')}] Activity on ${d}

${bold('Status:')} Reconstructed from git
${bold('Date:')} ${d}

${summary}
`);
      planNum++;
    }

    plansSection = entries.join('\n---\n\n');
  }

  const content = `# ${name} - Plans Approved

${bold('Last Updated:')} ${date}
${bold('Curated by:')} Squeegee

---

## Recent Plans

${plansSection}

---

## Archive

*Plans older than ${90} days are archived here.*

---

*Managed by Squeegee Documentation System*
`;

  const filePath = path.join(projectPath, 'PLANS_APPROVED.md');
  await fs.writeFile(filePath, content, 'utf-8');
  log(`Created PLANS_APPROVED.md for ${name}`, 'success');
}

module.exports = { run };
