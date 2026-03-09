/**
 * Stage 13: CLAUDE.md Curation
 *
 * Analyzes and maintains per-project CLAUDE.md files (Prong 2 of the 5-prong system).
 *
 * Checks:
 *   - Staleness: Is package.json newer than CLAUDE.md?
 *   - Completeness: Does it have required sections (Tech Stack, Commands, Architecture)?
 *   - Placeholder detection: Contains "*Not detected*", "[Define]", "TODO", etc.
 *   - Link health: Do internal links point to files that exist?
 *   - Stack accuracy: Does documented stack match package.json?
 *
 * Auto-fixes (within SQUEEGEE markers only):
 *   - Updates tech stack section from package.json dependencies
 *   - Updates commands section from package.json scripts
 *   - Adds missing section stubs with markers for future auto-update
 *
 * Reports suggestions for things it cannot auto-fix.
 *
 * @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
 */

const fs = require('fs').promises;
const path = require('path');
const { log, fileExists, readFileSafe, readJsonSafe, ensureDir } = require('../utils');
const { resolveProjectPath } = require('../config');
const { detectStack } = require('../analyzers/stack-detector');
const { updateSections, hasSection } = require('../formatters/sections');
const { timestamp, table, bulletList } = require('../formatters/markdown');

// ─── Required sections in a project CLAUDE.md ──────────────────────────────
const REQUIRED_SECTIONS = [
  'Tech Stack',
  'Commands',
  'Architecture',
  'Linked Resources Are Directives',
  'GBS Core Principles',
  'Context Window & Checkpoint Protocol',
  'Centralized Documentation & Planning',
  'Security & Secrets',
];

// ─── Placeholder patterns that signal incomplete documentation ──────────────
const PLACEHOLDER_PATTERNS = [
  '*Not detected*',
  '[Define]',
  '[To be documented]',
  '[Project description needed]',
  '[TODO]',
  'TODO:',
  'FIXME:',
  '*Add project-specific',
  '*No patterns detected*',
  '*Testing framework not detected*',
];

// ─── Known scripts and their human-readable descriptions ────────────────────
const SCRIPT_DESCRIPTIONS = {
  dev: 'Start development server',
  start: 'Start application',
  build: 'Build for production',
  test: 'Run tests',
  lint: 'Lint source code',
  format: 'Format source code',
  'type-check': 'Run type checking',
  typecheck: 'Run type checking',
  preview: 'Preview production build',
  'db:push': 'Push database schema',
  'db:migrate': 'Run database migrations',
  'db:seed': 'Seed database',
  'db:studio': 'Open Prisma Studio',
  clean: 'Clean build artifacts',
  deploy: 'Deploy application',
  'test:e2e': 'Run end-to-end tests',
  'test:unit': 'Run unit tests',
  generate: 'Run code generation',
};

// ─── Entry point ────────────────────────────────────────────────────────────

async function run(config, _discovery) {
  log('Stage 13: Curating project CLAUDE.md files...', 'info');

  const results = {
    analyzed: 0,
    updated: [],
    suggestions: {},
  };

  for (const project of config.projects) {
    const projectPath = resolveProjectPath(config, project.path);
    if (!(await fileExists(projectPath))) continue;

    results.analyzed++;

    const claudePath = path.join(projectPath, 'CLAUDE.md');
    const projectSuggestions = [];

    if (!(await fileExists(claudePath))) {
      projectSuggestions.push('Missing CLAUDE.md entirely (use generate command to scaffold)');
      results.suggestions[project.name] = projectSuggestions;
      continue;
    }

    try {
      const content = await readFileSafe(claudePath);
      const stack = await detectStack(projectPath);
      const pkg = await readJsonSafe(path.join(projectPath, 'package.json'));

      // ── Analysis checks ────────────────────────────────────────────────
      const stalenessHints = await checkStaleness(claudePath, projectPath);
      const completenessHints = checkCompleteness(content);
      const placeholderHints = checkPlaceholders(content);
      const linkHints = await checkLinks(content, projectPath);
      const accuracyHints = checkStackAccuracy(content, stack);

      projectSuggestions.push(
        ...stalenessHints,
        ...completenessHints,
        ...placeholderHints,
        ...linkHints,
        ...accuracyHints,
      );

      // ── Auto-fix within markers ────────────────────────────────────────
      let didUpdate = false;

      // Update tech-stack section
      const techContent = formatTechStackSection(stack);
      if (hasSection(content, 'tech-stack')) {
        const changed = await updateSections(claudePath, { 'tech-stack': techContent });
        if (changed) didUpdate = true;
      } else if (hasSectionHeading(content, 'Tech Stack')) {
        const injected = await injectMarkersAroundHeading(claudePath, 'Tech Stack', 'tech-stack', techContent);
        if (injected) didUpdate = true;
      }

      // Update commands section
      if (pkg && pkg.scripts) {
        const cmdContent = formatCommandsSection(pkg);
        if (hasSection(content, 'commands')) {
          const changed = await updateSections(claudePath, { commands: cmdContent });
          if (changed) didUpdate = true;
        } else if (hasSectionHeading(content, 'Commands') || hasSectionHeading(content, 'Quick Reference')) {
          const heading = hasSectionHeading(content, 'Commands') ? 'Commands' : 'Quick Reference';
          const injected = await injectMarkersAroundHeading(claudePath, heading, 'commands', cmdContent);
          if (injected) didUpdate = true;
        }
      }

      // Update GBS standards sections (static content)
      const gbsSections = [
        { tag: 'linked-resources', heading: 'Linked Resources Are Directives', formatter: formatLinkedResourcesSection },
        { tag: 'gbs-core-principles', heading: 'GBS Core Principles', formatter: formatGBSCorePrinciplesSection },
        { tag: 'context-window', heading: 'Context Window & Checkpoint Protocol', formatter: formatContextWindowSection },
        { tag: 'centralized-docs', heading: 'Centralized Documentation & Planning', formatter: formatCentralizedDocsSection },
        { tag: 'security-secrets', heading: 'Security & Secrets', formatter: formatSecuritySecretsSection },
      ];

      for (const { tag, heading, formatter } of gbsSections) {
        const sectionContent = formatter();
        if (hasSection(content, tag)) {
          const changed = await updateSections(claudePath, { [tag]: sectionContent });
          if (changed) didUpdate = true;
        } else if (hasSectionHeading(content, heading)) {
          const injected = await injectMarkersAroundHeading(claudePath, heading, tag, sectionContent);
          if (injected) didUpdate = true;
        }
      }

      // Add missing section stubs with markers (only if section heading is entirely absent)
      const refreshedContent = await readFileSafe(claudePath);
      const stubsAdded = await addMissingSectionStubs(claudePath, refreshedContent, stack, pkg);
      if (stubsAdded) didUpdate = true;

      if (didUpdate) {
        results.updated.push(project.name);
      }

      // Only record suggestions if there are any
      if (projectSuggestions.length > 0) {
        results.suggestions[project.name] = projectSuggestions;
      }
    } catch (err) {
      projectSuggestions.push(`Error analyzing: ${err.message}`);
      results.suggestions[project.name] = projectSuggestions;
    }
  }

  // ── Summary ──────────────────────────────────────────────────────────────
  printSummary(results);

  return results;
}

// ─── Staleness check ────────────────────────────────────────────────────────

async function checkStaleness(claudePath, projectPath) {
  const hints = [];

  // Compare package.json mtime vs CLAUDE.md mtime
  try {
    const pkgPath = path.join(projectPath, 'package.json');
    if (await fileExists(pkgPath)) {
      const pkgStat = await fs.stat(pkgPath);
      const claudeStat = await fs.stat(claudePath);
      if (pkgStat.mtime > claudeStat.mtime) {
        hints.push('package.json modified after CLAUDE.md - tech stack may need update');
      }
    }
  } catch { /* stat errors are non-fatal */ }

  // Check "Last Updated" date field
  try {
    const content = await readFileSafe(claudePath);
    const dateMatch = content.match(/Last Updated:\*?\*?\s*(\d{4}-\d{2}-\d{2})/);
    if (dateMatch) {
      const lastUpdated = new Date(dateMatch[1]);
      const daysSince = (Date.now() - lastUpdated.getTime()) / (1000 * 60 * 60 * 24);
      if (daysSince > 60) {
        hints.push(`Not updated in ${Math.floor(daysSince)} days - may be stale`);
      }
    }
  } catch { /* parse errors are non-fatal */ }

  return hints;
}

// ─── Completeness check ─────────────────────────────────────────────────────

function checkCompleteness(content) {
  const hints = [];

  for (const section of REQUIRED_SECTIONS) {
    if (!hasSectionHeading(content, section)) {
      hints.push(`Missing required section: "${section}"`);
    }
  }

  return hints;
}

// ─── Placeholder detection ──────────────────────────────────────────────────

function checkPlaceholders(content) {
  const hints = [];
  const found = PLACEHOLDER_PATTERNS.filter(p => content.includes(p));

  if (found.length > 0) {
    hints.push('Contains placeholder text that needs completion');
  }

  return hints;
}

// ─── Link health check ─────────────────────────────────────────────────────

async function checkLinks(content, projectPath) {
  const hints = [];
  // Match markdown links: [text](path) — only relative paths (no http/https)
  const linkRegex = /\[([^\]]+)\]\(([^)]+)\)/g;
  let match;
  let brokenCount = 0;

  while ((match = linkRegex.exec(content)) !== null) {
    const linkTarget = match[2];

    // Skip external links, anchors, and protocol links
    if (linkTarget.startsWith('http') || linkTarget.startsWith('#') || linkTarget.startsWith('mailto:')) {
      continue;
    }

    // Strip anchor from path (e.g. "file.md#section" -> "file.md")
    const cleanTarget = linkTarget.split('#')[0];
    if (!cleanTarget) continue;

    const resolved = path.join(projectPath, cleanTarget);
    if (!(await fileExists(resolved))) {
      brokenCount++;
    }
  }

  if (brokenCount > 0) {
    hints.push(`${brokenCount} internal link(s) point to files that do not exist`);
  }

  return hints;
}

// ─── Stack accuracy check ───────────────────────────────────────────────────

function checkStackAccuracy(content, stack) {
  const hints = [];

  // Check if major frameworks detected in package.json are mentioned in CLAUDE.md
  const allDetected = [...stack.frameworks, ...stack.tools];
  const missing = allDetected.filter(item => !content.includes(item));

  if (missing.length > 0 && missing.length <= 5) {
    hints.push(`Stack items not documented: ${missing.join(', ')}`);
  } else if (missing.length > 5) {
    hints.push(`${missing.length} stack items not documented in CLAUDE.md`);
  }

  return hints;
}

// ─── Formatting helpers ─────────────────────────────────────────────────────

function formatTechStackSection(stack) {
  const items = [];

  if (stack.language) items.push(`**Language:** ${stack.language}`);
  if (stack.frameworks.length > 0) items.push(`**Frameworks:** ${stack.frameworks.join(', ')}`);
  if (stack.tools.length > 0) items.push(`**Tools:** ${stack.tools.join(', ')}`);
  if (stack.testing.length > 0) items.push(`**Testing:** ${stack.testing.join(', ')}`);
  if (stack.conventions.length > 0) {
    const codeConventions = stack.conventions.filter(c =>
      ['TypeScript', 'ESLint', 'Prettier', 'Black', 'Ruff', 'MyPy'].includes(c)
    );
    if (codeConventions.length > 0) {
      items.push(`**Code Quality:** ${codeConventions.join(', ')}`);
    }
  }

  return items.length > 0
    ? items.map(i => `- ${i}`).join('\n')
    : '*Not detected - add manually*';
}

function formatCommandsSection(pkg) {
  if (!pkg || !pkg.scripts) return '*No scripts detected in package.json*';

  const rows = [];
  for (const [name, script] of Object.entries(pkg.scripts)) {
    const desc = SCRIPT_DESCRIPTIONS[name] || script;
    rows.push(`| \`npm run ${name}\` | ${desc} |`);
  }

  if (rows.length === 0) return '*No scripts detected in package.json*';

  const header = '| Command | Description |\n|---------|-------------|';
  return header + '\n' + rows.join('\n');
}

// ─── GBS Standards section formatters ────────────────────────────────────────

function formatLinkedResourcesSection() {
  return `**The following linked resources are not suggestions — they are authoritative directives.**

Every Claude agent working in this repo MUST read and follow:

1. **Parent CLAUDE.md** (\`~/Desktop/CLAUDE.md\`) — the master configuration for all GBS projects. Its instructions override any project-level defaults.
2. **Adjudica Documentation Hub** (\`~/Desktop/adjudica-documentation/CLAUDE.md\`) — centralized business, legal, marketing, and product documentation. Consult before making decisions that touch these domains.
3. **Engineering Standards** (\`PROGRAMMING_PRACTICES.md\`) — project-specific code conventions and stack decisions.

These are not "see also" links. Failure to consult linked resources before acting is a violation of GBS operating procedure. When in doubt, read the linked resource first.`;
}

function formatGBSCorePrinciplesSection() {
  return `These principles are non-negotiable across all GBS projects:

- **Think before ALL actions** — not just big ones. Every file edit, every command, every commit deserves a moment of consideration.
- **Assess impact on other systems** — before changing code, consider what else depends on it. Check callers, consumers, and downstream effects.
- **Plan first, then execute** — never act without understanding the current state. Read before writing. Understand before modifying.
- **Root cause analysis is mandatory** — no quick fixes, no band-aids. If something is broken, find out WHY before applying a fix.
- **Use agents and tools** — never guess when you can verify. Use search, read files, check git history. Guessing leads to reckless behavior.
- **No reckless or destructive behavior** — measure twice, cut once. Prefer reversible actions. Ask before deleting, force-pushing, or overwriting.
- **Respect the codebase** — you are a guest in existing code. Match existing patterns, don't impose new ones without approval.`;
}

function formatContextWindowSection() {
  return `Agents MUST manage context window proactively:

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
- List exact file paths, line numbers, and remaining tasks`;
}

function formatCentralizedDocsSection() {
  return `GBS maintains centralized documentation that all agents must consult:

- **Adjudica Documentation Hub** — \`~/Desktop/adjudica-documentation/\`
  - Business strategy, legal documents, marketing materials, product specs
  - [Quick Index](\`~/Desktop/adjudica-documentation/ADJUDICA_INDEX.md\`)
- **Project Planning** — \`.planning/\` directory in each repo
  - \`STATE.md\` — current session context (GSD format)
  - \`ROADMAP.md\` — project vision and phases
  - \`ISSUES.md\` — deferred work and known issues
  - \`PLAN-*.md\` — approved plans (synced to docs hub)
  - \`GOAL-*.md\` — measurable goals (synced to docs hub)
- **Plan/Goal Sync (MANDATORY)** — every \`PLAN-*.md\` and \`GOAL-*.md\` must exist as exact copies in both \`.planning/\` and \`adjudica-documentation/projects/{repo}/planning/\` or \`goals/\`. See [Planning & Goals Standard](\`~/Desktop/adjudica-documentation/engineering/PLANNING_AND_GOALS_STANDARD.md\`).
- **Work Logs** — document decisions and progress in \`.planning/STATE.md\`
  - Every significant decision gets recorded with rationale
  - Session handoffs must update STATE.md before ending`;
}

function formatSecuritySecretsSection() {
  return `**All secrets are managed through GCP Secret Manager** (project: \`adjudica-internal\`).

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
- Report any suspected secret exposure immediately`;
}

// ─── Section helpers ────────────────────────────────────────────────────────

/**
 * Check if content has a markdown heading matching the given name (case-insensitive).
 */
function hasSectionHeading(content, heading) {
  const regex = new RegExp(`^##\\s+.*${escapeRegex(heading)}`, 'im');
  return regex.test(content);
}

function escapeRegex(str) {
  return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/**
 * Inject SQUEEGEE markers around an existing heading's content.
 * Finds the heading, locates the content between it and the next heading/divider,
 * and wraps the auto-generated portion with markers.
 */
async function injectMarkersAroundHeading(filePath, heading, tag, newContent) {
  let content = await readFileSafe(filePath);
  const headerRegex = new RegExp(`^(##\\s+.*${escapeRegex(heading)}.*)$`, 'im');
  const match = content.match(headerRegex);
  if (!match) return false;

  const headerIdx = match.index;
  const afterHeader = headerIdx + match[0].length;

  // Find the next ## heading or --- divider
  const rest = content.slice(afterHeader);
  const nextSection = rest.search(/^(?:## |---)/m);
  const endIdx = nextSection > -1 ? afterHeader + nextSection : content.length;

  const before = content.slice(0, afterHeader);
  const after = content.slice(endIdx);

  const startMarker = `<!-- SQUEEGEE:AUTO:START ${tag} -->`;
  const endMarker = `<!-- SQUEEGEE:AUTO:END ${tag} -->`;

  const updated = before + '\n\n' + startMarker + '\n' + newContent + '\n' + endMarker + '\n\n' + after;

  if (updated !== content) {
    await fs.writeFile(filePath, updated, 'utf-8');
    return true;
  }

  return false;
}

/**
 * Add stub sections with markers for any required sections that are completely absent.
 * Returns true if the file was modified.
 */
async function addMissingSectionStubs(filePath, content, stack, pkg) {
  let modified = false;

  const stubs = [
    {
      heading: 'Tech Stack',
      tag: 'tech-stack',
      generator: () => formatTechStackSection(stack),
    },
    {
      heading: 'Commands',
      tag: 'commands',
      generator: () => pkg ? formatCommandsSection(pkg) : '*No package.json found*',
    },
    {
      heading: 'Architecture',
      tag: 'architecture',
      generator: () => {
        if (stack.directories.length > 0) {
          const visible = stack.directories
            .filter(d => !d.startsWith('.') && d !== 'node_modules')
            .slice(0, 10);
          return '```\n' + visible.map(d => `├── ${d}/`).join('\n') + '\n```';
        }
        return '*Architecture overview needed - describe key directories and data flow*';
      },
    },
    {
      heading: 'Linked Resources Are Directives',
      tag: 'linked-resources',
      generator: formatLinkedResourcesSection,
    },
    {
      heading: 'GBS Core Principles',
      tag: 'gbs-core-principles',
      generator: formatGBSCorePrinciplesSection,
    },
    {
      heading: 'Context Window & Checkpoint Protocol',
      tag: 'context-window',
      generator: formatContextWindowSection,
    },
    {
      heading: 'Centralized Documentation & Planning',
      tag: 'centralized-docs',
      generator: formatCentralizedDocsSection,
    },
    {
      heading: 'Security & Secrets',
      tag: 'security-secrets',
      generator: formatSecuritySecretsSection,
    },
  ];

  for (const stub of stubs) {
    // Skip if section heading or markers already exist
    if (hasSectionHeading(content, stub.heading) || hasSection(content, stub.tag)) {
      continue;
    }

    // Append stub section before the footer or at end of file
    const startMarker = `<!-- SQUEEGEE:AUTO:START ${stub.tag} -->`;
    const endMarker = `<!-- SQUEEGEE:AUTO:END ${stub.tag} -->`;
    const block = [
      '',
      '---',
      '',
      `## ${stub.heading}`,
      '',
      startMarker,
      stub.generator(),
      endMarker,
      '',
    ].join('\n');

    const footerIdx = content.lastIndexOf('*Generated by Squeegee');
    const managedIdx = content.lastIndexOf('*Managed by Squeegee');
    const insertBefore = Math.max(footerIdx, managedIdx);

    if (insertBefore > -1) {
      const lineStart = content.lastIndexOf('\n', insertBefore);
      content = content.slice(0, lineStart) + block + content.slice(lineStart);
    } else {
      content += block;
    }

    modified = true;
  }

  if (modified) {
    await fs.writeFile(filePath, content, 'utf-8');
  }

  return modified;
}

// ─── Summary printer ────────────────────────────────────────────────────────

function printSummary(results) {
  const suggestionCount = Object.values(results.suggestions)
    .reduce((sum, arr) => sum + arr.length, 0);
  const projectsWithSuggestions = Object.keys(results.suggestions).length;

  log(
    `CLAUDE.md — analyzed: ${results.analyzed}, updated: ${results.updated.length}, ` +
    `projects with suggestions: ${projectsWithSuggestions}`,
    'success'
  );

  if (results.updated.length > 0) {
    log('Updated:', 'info');
    for (const name of results.updated) {
      console.log(`   - ${name}`);
    }
  }

  if (projectsWithSuggestions > 0) {
    log('Suggestions:', 'warn');
    for (const [project, suggestions] of Object.entries(results.suggestions)) {
      console.log(`   ${project}:`);
      for (const s of suggestions) {
        console.log(`     - ${s}`);
      }
    }
  }

  if (results.updated.length === 0 && projectsWithSuggestions === 0) {
    log('All project CLAUDE.md files are up to date', 'success');
  }
}

module.exports = { run };
