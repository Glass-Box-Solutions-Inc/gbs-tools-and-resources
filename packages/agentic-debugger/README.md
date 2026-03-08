# Agentic Debugger

**Automated CI test failure debugging agent** — uses Claude Code to detect, diagnose, and fix test failures with type-check verification gates. Configuration-driven for any project.

> **Status:** Standalone Package (canonical for GBS) | **Package:** `@gbs/agentic-debugger`

This is a **standalone, configuration-driven CI debugging agent**, forked from Glassy PAI's debug-agent script and generalized for any project. It works with any test runner (Jest, Vitest, Playwright) and any TypeScript/JavaScript project. Linear integration is optional.

> **Relationship to Glassy:** The debug-agent script and workflow within `glassy-app-production` remain canonical for Glassy PAI and continue to be Glassy-specific. This standalone package is a separate GBS resource generalized for use in any repository.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Agent | Claude Code CLI (`@anthropic-ai/claude-code`) |
| Model | Claude Opus 4.6 (via Claude Code) |
| Workflow | GitHub Actions |
| Verification | Configurable type-check command (default: `tsc --noEmit`) |
| Integration | Linear API (optional — ticket tracking) |

---

## How It Works

```
CI Test Failure
         │
         ▼
Manual Workflow Dispatch (GitHub Actions UI)
  Input: failure log, attempt #, commit SHA, [Linear ticket]
         │
         ▼
Setup: Install deps → Run project setup
         │
         ▼
Re-run Tests → Capture Fresh Failure Output
         │
         ▼
debug-agent.mjs: Load .agentic-debugger.json → Parse Failures
         │
    ┌────┴────┬──────────────┐
    │         │              │
 (exit 2)  (continue)   (no failures)
 ENV ISSUE    │           SKIP
 ESCALATE     ▼
         Claude Code CLI
         (configurable turns/timeout)
         Allowed: Read, Edit, Bash(type-check)
              │
         Type-Check Gate
              │
         ┌────┴────┐
      (pass)     (fail)
         │       Exit 1
    Commit & Push
    Update Linear (if configured)
```

### Exit Codes

| Code | Meaning | Action |
|------|---------|--------|
| 0 | Success — changes verified | Commit, push, update ticket |
| 1 | Agent failed — type-check gate failed | Skip commit, fail job |
| 2 | Environmental failure | Skip agent, escalate to human |

---

## Configuration

Place `.agentic-debugger.json` in your repo root to customize behavior:

```json
{
  "testRunners": {
    "failurePatterns": ["^FAIL\\s+(.+\\.spec\\.ts)$"],
    "typeCheckCommand": "npx tsc --noEmit",
    "typeCheckTimeout": 90000
  },
  "fileScope": {
    "editable": ["src/**", "test/**"],
    "forbidden": ["*.lock", "package.json", "prisma/schema.prisma"]
  },
  "claudeCode": {
    "maxTurns": 20,
    "timeoutMinutes": 8,
    "allowedTools": ["Read", "Edit"]
  },
  "linear": {
    "enabled": false
  },
  "maxAttempts": 5,
  "branch": "develop"
}
```

All fields have sensible defaults. See `.agentic-debugger.json` in this package for the full default config.

---

## Adopting in Your Repo

### 1. Copy the workflow and script

```bash
# Copy workflow
cp workflows/agentic-debugger.yml .github/workflows/agentic-debugger.yml

# Copy debug agent script
mkdir -p scripts
cp scripts/debug-agent.mjs scripts/debug-agent.mjs
```

### 2. Configure (optional)

```bash
# Create project-specific config (or use defaults)
cp .agentic-debugger.json .agentic-debugger.json
# Edit to match your project structure
```

### 3. Add GitHub secrets

| Secret | Required | Purpose |
|--------|----------|---------|
| `ANTHROPIC_API_KEY` | Yes | Claude Code CLI authentication |
| `LINEAR_API_KEY` | No | Linear ticket updates (if enabled) |

### 4. Trigger

Go to GitHub Actions → "Agentic Debugger" → Run workflow.

---

## Safety Constraints

| Constraint | Detail |
|-----------|--------|
| Tool restrictions | Only `Read`, `Edit`, `Bash(type-check)` allowed |
| File scope | Configurable via `fileScope.editable` |
| No destructive edits | Never truncate >15% of file lines |
| No function deletion | Never delete entire functions, classes, or endpoints |
| Forbidden files | Configurable via `fileScope.forbidden` |
| Type-check gate | Must pass configured type-check before commit |
| Max attempts | Configurable (default: 5) |

---

## File Structure

```
packages/agentic-debugger/
├── package.json                  # @gbs/agentic-debugger
├── .env.example
├── .agentic-debugger.json        # Default config
├── scripts/
│   └── debug-agent.mjs           # Agent — config loader, failure parser, Claude CLI, type-check gate
├── workflows/
│   ├── agentic-debugger.yml      # Project-agnostic GitHub Actions template
│   └── examples/
│       └── agentic-debugger.glassy.yml  # Glassy PAI-specific variant (PostgreSQL, pnpm, Prisma)
├── README.md
└── CLAUDE.md
```

---

## Related Packages

- [agent-swarm](../agent-swarm/) — Multi-agent task orchestration (DAG-based)
- [spectacles](../spectacles/) — Browser automation (can verify UI after fixes)
- [merus-expert](../merus-expert/) — Domain agent pattern (tool-calling loop)

---

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
