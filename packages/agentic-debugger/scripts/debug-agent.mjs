#!/usr/bin/env node
// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// GBS Agentic Debugger v2.1 — Configuration-driven standalone CI debugging agent
// Called by .github/workflows/agentic-debugger.yml (or any CI workflow)
//
// v1: Single-shot Anthropic Messages API call → file patch blocks written to disk.
// v2: Orchestrates Claude Code CLI as a tool-enabled agentic loop.
// v2.1: Configuration-driven — reads .agentic-debugger.json from repo root.
//       Supports any test runner, configurable file scope, optional Linear integration.
//
// Exit codes:
//   0 — Agent ran, changes may have been made (type-check verified)
//   1 — Agent failed (API error, no patches, type-check gate failed) — do NOT commit
//   2 — Environmental failure (missing API key, network, no live service) — escalate immediately

import { readFileSync, writeFileSync, existsSync } from 'fs';
import { spawnSync } from 'child_process';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const REPO_ROOT = resolve(__dirname, '..');

// ─── Configuration loader ───────────────────────────────────────────────────

const DEFAULT_CONFIG = {
  testRunners: {
    failurePatterns: [
      String.raw`^FAIL\s+(?:.*/)?(src/\S+\.(?:spec|test)\.(?:ts|tsx|js|jsx))$`,
      String.raw`^\s*FAIL\s+(\S+\.(?:spec|test)\.(?:ts|tsx|js|jsx))$`,
    ],
    typeCheckCommand: 'npx tsc --noEmit',
    typeCheckTimeout: 90000,
  },
  fileScope: {
    editable: ['src/**', 'test/**', 'tests/**'],
    forbidden: ['*.lock', 'package.json', 'package-lock.json', 'pnpm-lock.yaml', '*.yml', '*.yaml', 'prisma/schema.prisma'],
  },
  claudeCode: {
    maxTurns: 20,
    timeoutMinutes: 8,
    allowedTools: ['Read', 'Edit'],
  },
  linear: {
    enabled: false,
  },
  maxAttempts: 5,
  branch: 'develop',
};

function loadConfig() {
  const configPath = resolve(REPO_ROOT, '.agentic-debugger.json');
  if (existsSync(configPath)) {
    try {
      const userConfig = JSON.parse(readFileSync(configPath, 'utf8'));
      // Deep merge (one level)
      return {
        testRunners: { ...DEFAULT_CONFIG.testRunners, ...userConfig.testRunners },
        fileScope: { ...DEFAULT_CONFIG.fileScope, ...userConfig.fileScope },
        claudeCode: { ...DEFAULT_CONFIG.claudeCode, ...userConfig.claudeCode },
        linear: { ...DEFAULT_CONFIG.linear, ...userConfig.linear },
        maxAttempts: userConfig.maxAttempts ?? DEFAULT_CONFIG.maxAttempts,
        branch: userConfig.branch ?? DEFAULT_CONFIG.branch,
      };
    } catch (err) {
      console.warn(`Warning: Failed to parse .agentic-debugger.json: ${err.message}`);
      console.warn('Falling back to default configuration.');
    }
  }
  return DEFAULT_CONFIG;
}

const CONFIG = loadConfig();

// ─── Environment ────────────────────────────────────────────────────────────

const ANTHROPIC_API_KEY = process.env.ANTHROPIC_API_KEY;
const ATTEMPT_NUMBER = parseInt(process.env.ATTEMPT_NUMBER || '0', 10);

function loadFailures() {
  const filePath = process.env.CURRENT_FAILURES_FILE;
  if (filePath) {
    try { return readFileSync(filePath, 'utf8'); } catch { /* fall through */ }
  }
  return process.env.CURRENT_FAILURES || process.env.TEST_FAILURE_LOG || '';
}

const FAILURES = loadFailures();

if (!ANTHROPIC_API_KEY) {
  console.error('ANTHROPIC_API_KEY is required');
  process.exit(1);
}

// ─── Environmental failure classifier ────────────────────────────────────────

const ENVIRONMENTAL_PATTERNS = [
  /GEMINI_API_KEY/,
  /ANTHROPIC_API_KEY.*not set/i,
  /OPENAI_API_KEY/,
  /connect ECONNREFUSED/,
  /network timeout/i,
  /ENOTFOUND/,
  /Cannot find module.*node_modules\/(?!.*\.spec)/,
  /ECONNRESET/,
  /getaddrinfo ENOTFOUND/,
];

function detectEnvironmentalFailure(log) {
  for (const pattern of ENVIRONMENTAL_PATTERNS) {
    if (pattern.test(log)) return pattern.toString();
  }
  return null;
}

// ─── Parse failing spec paths ────────────────────────────────────────────────

function parseFailingSpecs(log) {
  const specs = new Set();
  for (const patternStr of CONFIG.testRunners.failurePatterns) {
    const regex = new RegExp(patternStr, 'gm');
    for (const m of log.matchAll(regex)) {
      if (m[1]) specs.add(m[1]);
    }
  }
  return [...specs];
}

// ─── Build the Claude Code prompt ────────────────────────────────────────────

function buildPrompt(failures, failingSpecs) {
  const specList = failingSpecs.length > 0
    ? failingSpecs.map(s => `- \`${s}\``).join('\n')
    : '_No FAIL lines detected — use stack traces in the output above to identify files._';

  const editableScope = CONFIG.fileScope.editable.map(p => `\`${p}\``).join(', ');
  const forbiddenFiles = CONFIG.fileScope.forbidden.map(p => `\`${p}\``).join(', ');
  const typeCheckCmd = CONFIG.claudeCode.allowedTools.includes('Bash')
    ? CONFIG.testRunners.typeCheckCommand
    : CONFIG.testRunners.typeCheckCommand;

  return `## GBS Agentic Debugger — Attempt ${ATTEMPT_NUMBER + 1}/${CONFIG.maxAttempts}

CI tests are failing on the \`${CONFIG.branch}\` branch. Your job is to make targeted, minimal fixes.

### Failing Test Output
\`\`\`
${failures.slice(-8000)}
\`\`\`

### Failing Spec Files
${specList}

---

### Instructions

1. **Read \`CLAUDE.md\`** if it exists — understand project conventions before touching anything.

2. **Read \`tsconfig.json\`** (or equivalent config) to understand the project's TypeScript settings.

3. **Read each failing spec file** to understand exactly what the tests expect.

4. **Read the corresponding implementation file(s)** to understand the current behavior.

5. **Make the smallest possible edit** to fix the failures:
   - Fix shape mismatches, missing fields, wrong status codes, wrong response structures.
   - Do NOT refactor, rename, or clean up code unrelated to the failures.
   - Do NOT add new imports unless absolutely required by the fix.
   - Do NOT rewrite entire files — edit only the specific functions/lines that are wrong.

6. **Hard limits — violations will be reverted:**
   - Never truncate a file. If a file has N lines, your edit must leave at least 0.85*N lines.
   - Never delete an entire function, class, or endpoint — only fix its internals.
   - Only edit files matching: ${editableScope}
   - Do not modify: ${forbiddenFiles}

7. **After editing, run \`${typeCheckCmd}\`** to verify no type errors.
   - If it reports errors, read the output and fix them before stopping.
   - Do not stop until the type check is clean.

8. **Stop** when type check is clean. Do not run the full test suite — it takes too long in this budget.

The CI workflow will commit and push whatever you changed.`;
}

// ─── Run Claude Code CLI ─────────────────────────────────────────────────────

function runClaudeCode(prompt) {
  const which = spawnSync('which', ['claude'], { encoding: 'utf8' });
  if (which.status !== 0) {
    console.error('Claude Code CLI not found. Install with: npm install -g @anthropic-ai/claude-code');
    process.exit(1);
  }

  // Build allowed tools list from config + type-check command
  const allowedTools = [
    ...CONFIG.claudeCode.allowedTools,
    `Bash(${CONFIG.testRunners.typeCheckCommand})`,
  ].join(',');

  console.log('Invoking Claude Code CLI...');
  console.log(`Allowed tools: ${allowedTools}`);
  console.log(`Max turns: ${CONFIG.claudeCode.maxTurns}`);

  const result = spawnSync(
    'claude',
    [
      '--print',
      '--output-format', 'text',
      '--dangerously-skip-permissions',
      '--allowedTools', allowedTools,
      '--max-turns', String(CONFIG.claudeCode.maxTurns),
      prompt,
    ],
    {
      cwd: REPO_ROOT,
      env: { ...process.env, ANTHROPIC_API_KEY },
      stdio: 'inherit',
      timeout: CONFIG.claudeCode.timeoutMinutes * 60 * 1000,
    },
  );

  if (result.error) {
    console.error('Failed to spawn claude:', result.error.message);
    process.exit(1);
  }

  if (result.status !== 0) {
    console.error(`Claude Code exited with non-zero status: ${result.status}`);
    process.exit(1);
  }

  console.log('\nClaude Code finished.');
}

// ─── Post-edit type-check gate ───────────────────────────────────────────────

function runTypeCheckGate() {
  console.log('\n=== Post-edit type-check gate ===');
  const [cmd, ...args] = CONFIG.testRunners.typeCheckCommand.split(/\s+/);
  const result = spawnSync(cmd, args, {
    cwd: REPO_ROOT,
    stdio: 'inherit',
    timeout: CONFIG.testRunners.typeCheckTimeout,
    shell: true,
  });

  if (result.status !== 0) {
    console.error('\n[ABORT] Type check failed after agent edits.');
    console.error('The agent introduced type errors. Refusing to commit broken code.');
    console.error('Manual fix required.');
    process.exit(1);
  }

  console.log('Type-check gate passed.');
}

// ─── Main ────────────────────────────────────────────────────────────────────

async function main() {
  console.log(`\n=== GBS Agentic Debugger v2.1 — attempt ${ATTEMPT_NUMBER + 1}/${CONFIG.maxAttempts} ===\n`);
  console.log(`Config: ${existsSync(resolve(REPO_ROOT, '.agentic-debugger.json')) ? '.agentic-debugger.json loaded' : 'using defaults'}`);

  if (!FAILURES.trim()) {
    console.error('No failure log provided. Cannot proceed.');
    process.exit(1);
  }

  const envPattern = detectEnvironmentalFailure(FAILURES);
  if (envPattern) {
    console.log(`\n[SKIP] Environmental failure detected: ${envPattern}`);
    console.log('These failures require human intervention (missing API keys, network issues, live services).');
    console.log('Signalling workflow to escalate ticket rather than waste an attempt.');
    process.exit(2);
  }

  const failingSpecs = parseFailingSpecs(FAILURES);
  if (failingSpecs.length > 0) {
    console.log(`Failing specs detected:\n  ${failingSpecs.join('\n  ')}`);
  } else {
    console.log('No FAIL lines detected — Claude will use stack traces to identify files.');
  }

  const prompt = buildPrompt(FAILURES, failingSpecs);

  runClaudeCode(prompt);
  runTypeCheckGate();

  console.log('\n=== Debug agent completed successfully ===');
}

main().catch((err) => {
  console.error('Debug agent failed with unexpected error:', err);
  process.exit(1);
});
