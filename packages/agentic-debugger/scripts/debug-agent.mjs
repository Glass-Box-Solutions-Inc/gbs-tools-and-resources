#!/usr/bin/env node
// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// GBS Agentic Debugger v2.0
// Called by .github/workflows/agentic-debugger.yml
//
// v1: Single-shot Anthropic Messages API call → <file> patch blocks written to disk.
//     Problem: no tsc verification, no project context, destructive full-file rewrites.
//
// v2: Orchestrates Claude Code CLI as a tool-enabled agentic loop.
//     Claude Code can read files, make targeted edits, and run tsc to self-verify.
//     CLAUDE.md in repo root is loaded automatically (project conventions, import type rules, etc).
//
// Exit codes:
//   0 — Agent ran, changes may have been made (tsc verified)
//   1 — Agent failed (API error, no patches, tsc gate failed) — do NOT commit
//   2 — Environmental failure (missing API key, network, no live service) — escalate immediately

import { readFileSync, writeFileSync, existsSync } from 'fs';
import { spawnSync } from 'child_process';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const REPO_ROOT = resolve(__dirname, '..');

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
// These patterns indicate failures the agent cannot fix (missing live services,
// network issues, missing secrets). Skip the agent and escalate to human.

const ENVIRONMENTAL_PATTERNS = [
  /GEMINI_API_KEY/,
  /ANTHROPIC_API_KEY.*not set/i,
  /OPENAI_API_KEY/,
  /connect ECONNREFUSED/,
  /network timeout/i,
  /ENOTFOUND/,
  /Cannot find module.*node_modules\/(?!.*\.spec)/,  // library import errors, not spec files
  /ECONNRESET/,
  /getaddrinfo ENOTFOUND/,
];

function detectEnvironmentalFailure(log) {
  for (const pattern of ENVIRONMENTAL_PATTERNS) {
    if (pattern.test(log)) return pattern.toString();
  }
  return null;
}

// ─── Parse failing spec paths from FAIL lines ─────────────────────────────────

function parseFailingSpecs(log) {
  const specs = new Set();
  // Jest: "FAIL backend/src/.../foo.spec.ts" or "FAIL src/.../foo.spec.ts"
  const failLineRegex = /^FAIL\s+(?:backend\/)?(src\/\S+\.spec\.ts)/gm;
  for (const m of log.matchAll(failLineRegex)) {
    specs.add(`backend/${m[1]}`);
  }
  return [...specs];
}

// ─── Build the Claude Code prompt ─────────────────────────────────────────────

function buildPrompt(failures, failingSpecs) {
  const specList = failingSpecs.length > 0
    ? failingSpecs.map(s => `- \`${s}\``).join('\n')
    : '_No FAIL lines detected — use stack traces in the output above to identify files._';

  return `## GBS Agentic Debugger — Attempt ${ATTEMPT_NUMBER + 1}/5

CI tests are failing on the \`develop\` branch. Your job is to make targeted, minimal fixes.

### Failing Test Output
\`\`\`
${failures.slice(-8000)}
\`\`\`

### Failing Spec Files
${specList}

---

### Instructions

1. **Read \`CLAUDE.md\`** — understand project conventions before touching anything.

2. **Read \`backend/tsconfig.json\`** — critical. The project uses \`"isolatedModules": true\`.
   - All type-only imports MUST use \`import type { ... }\` syntax.
   - \`import { Prisma }\` is only valid after \`prisma generate\` — use types from the service layer instead.

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
   - Only edit files under \`backend/src/\` or \`backend/test/\`. Nothing else.
   - Do not modify \`prisma/schema.prisma\`, CI workflows, or \`package.json\` files.

7. **After editing, run \`pnpm --filter backend tsc --noEmit\`** to verify no TypeScript errors.
   - If tsc reports errors, read the output and fix them before stopping.
   - Do not stop until tsc is clean.

8. **Stop** when tsc is clean. Do not run the full test suite — it takes too long in this budget.

The CI workflow will commit and push whatever you changed.`;
}

// ─── Run Claude Code CLI ───────────────────────────────────────────────────────

function runClaudeCode(prompt) {
  // Verify claude CLI is available
  const which = spawnSync('which', ['claude'], { encoding: 'utf8' });
  if (which.status !== 0) {
    console.error('Claude Code CLI not found. Install with: npm install -g @anthropic-ai/claude-code');
    process.exit(1);
  }

  // Write prompt to a temp file to avoid shell quoting issues with long strings
  const promptFile = '/tmp/gbs-debug-agent-prompt.txt';
  writeFileSync(promptFile, prompt, 'utf8');

  // Tools allowed:
  //   Read  — read any file (needs full repo access to understand context)
  //   Edit  — edit existing files (NOT Write — prevents creating files at wrong paths)
  //   Bash  — only tsc verification
  // No Write, no Task, no browser, no WebSearch.
  const allowedTools = [
    'Read',
    'Edit',
    'Bash(pnpm --filter backend tsc --noEmit)',
  ].join(',');

  console.log('Invoking Claude Code CLI...');
  console.log(`Allowed tools: ${allowedTools}`);
  console.log(`Max turns: 20`);

  const result = spawnSync(
    'claude',
    [
      '--print',
      '--output-format', 'text',
      '--dangerously-skip-permissions', // CI sandbox — no interactive user to approve tool calls
      '--allowedTools', allowedTools,
      '--max-turns', '20',
      prompt,
    ],
    {
      cwd: REPO_ROOT,
      env: { ...process.env, ANTHROPIC_API_KEY },
      stdio: 'inherit',
      timeout: 8 * 60 * 1000, // 8 minute timeout — generous for up to 20 turns
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

// ─── Post-edit TypeScript gate ────────────────────────────────────────────────
// Hard verification before the CI workflow is allowed to commit.
// Claude Code already runs tsc internally, but this is a final catch.

function runTscGate() {
  console.log('\n=== Post-edit TypeScript gate ===');
  const result = spawnSync(
    'pnpm',
    ['--filter', 'backend', 'tsc', '--noEmit'],
    {
      cwd: REPO_ROOT,
      stdio: 'inherit',
      timeout: 90 * 1000,
    },
  );

  if (result.status !== 0) {
    console.error('\n[ABORT] TypeScript check failed after agent edits.');
    console.error('The agent introduced type errors. Refusing to commit broken code.');
    console.error('Manual fix required.');
    process.exit(1);
  }

  console.log('TypeScript gate passed.');
}

// ─── Main ─────────────────────────────────────────────────────────────────────

async function main() {
  console.log(`\n=== GBS Agentic Debugger v2.0 — attempt ${ATTEMPT_NUMBER + 1}/5 ===\n`);

  if (!FAILURES.trim()) {
    console.error('No failure log provided. Cannot proceed.');
    process.exit(1);
  }

  // Environmental failure check — skip the agent entirely and signal the
  // workflow to escalate the ticket to human-required immediately.
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
  runTscGate();

  console.log('\n=== Debug agent completed successfully ===');
}

main().catch((err) => {
  console.error('Debug agent failed with unexpected error:', err);
  process.exit(1);
});
