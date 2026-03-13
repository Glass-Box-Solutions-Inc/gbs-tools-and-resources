# Agentic Debugger

**Automated CI test failure debugging agent — standalone, configuration-driven.**

---

## ⚠️ CRITICAL GUARDRAILS (READ FIRST)

1. **NEVER push without permission** — Even small fixes require express user permission. No exceptions.
2. **NEVER expose secrets** — No API keys, tokens, credentials in git, logs, or conversation.
3. **NEVER force push or skip tests** — 100% passing tests required.
4. **ALWAYS read parent CLAUDE.md** — `~/CLAUDE.md` for org-wide standards.
5. **ALWAYS use Definition of Ready** — 100% clear requirements before implementation.

---

## Project Overview

| Field | Value |
|-------|-------|
| Status | Standalone Package (canonical for GBS) |
| Package | `@gbs/agentic-debugger` |
| Stack | Claude Code CLI, GitHub Actions, Node.js |
| Model | Claude Opus 4.6 (via Claude Code) |

---

## Architecture

```
GitHub Actions Workflow
├── Setup: Node.js, project dependencies
├── Re-run tests → capture failure output
├── debug-agent.mjs
│   ├── Load .agentic-debugger.json config
│   ├── Environmental failure detection (exit 2)
│   ├── Failing spec parsing (configurable patterns)
│   ├── Claude Code CLI invocation
│   │   ├── Configurable turns and timeout
│   │   ├── Allowed tools: Read, Edit, Bash(type-check)
│   │   └── Reads CLAUDE.md for project conventions
│   └── Type-check verification gate
├── Commit & push (if type-check passes)
└── Linear ticket update (if configured)
```

---

## File Map

| File | Purpose |
|------|---------|
| `scripts/debug-agent.mjs` | Agent orchestrator — config loader, failure parsing, Claude CLI, type-check gate |
| `workflows/agentic-debugger.yml` | Project-agnostic GitHub Actions workflow template |
| `workflows/examples/agentic-debugger.glassy.yml` | Glassy PAI-specific variant (PostgreSQL, pnpm, Prisma) |
| `.agentic-debugger.json` | Default configuration with sensible defaults |
| `package.json` | Package manifest with bin entry for debug-agent |
| `.env.example` | Environment variable template |

---

## Configuration

The agent reads `.agentic-debugger.json` from the target repo root. Key settings:

| Setting | Description | Default |
|---------|-------------|---------|
| `testRunners.failurePatterns` | Regex patterns to extract failing spec files | Jest/Vitest FAIL patterns |
| `testRunners.typeCheckCommand` | Command for type verification gate | `npx tsc --noEmit` |
| `fileScope.editable` | Glob patterns for files the agent can modify | `src/**`, `test/**` |
| `fileScope.forbidden` | Glob patterns for files the agent must not touch | `*.lock`, `package.json`, etc. |
| `claudeCode.maxTurns` | Maximum Claude Code turns per attempt | 20 |
| `claudeCode.timeoutMinutes` | Timeout for Claude Code invocation | 8 |
| `linear.enabled` | Whether to update Linear tickets | false |
| `maxAttempts` | Maximum debug attempts per issue | 5 |

---

## Exit Code Semantics

| Code | Meaning | Workflow Action |
|------|---------|-----------------|
| 0 | Success — agent ran, changes verified | Commit & push, update Linear |
| 1 | Agent failed — type-check gate failed or no patches | Skip commit, fail job |
| 2 | Environmental failure — missing keys, network | Skip agent, escalate to human |

---

## Safety Constraints

- **Tool-restricted Claude environment**: Read + Edit + type-check only
- **File scope**: Configurable via `.agentic-debugger.json`
- **No destructive edits**: Never truncate >15% of file, never delete functions
- **Type-check gate**: Must pass configured command before any commit
- **Max attempts**: Configurable (default 5)

---

## Key Dependencies

- `@anthropic-ai/claude-code` — Claude Code CLI (peer dependency, installed at runtime in workflow)
- Secrets: `ANTHROPIC_API_KEY` (required), `LINEAR_API_KEY` (optional)

---

## Root Standards Reference

For company-wide development standards, see the [Root CLAUDE.md](https://github.com/Glass-Box-Solutions-Inc/adjudica-documentation/blob/main/engineering/ROOT_CLAUDE.md).

For centralized business, legal, marketing, and product documentation, see the [Adjudica Documentation Hub](~/Desktop/adjudica-documentation/CLAUDE.md) and the [Quick Index](~/Desktop/adjudica-documentation/ADJUDICA_INDEX.md).

---

## ⚠️ GUARDRAILS REMINDER

Before ANY action, verify:

- [ ] **Push permission?** — Required for every push, no exceptions
- [ ] **Definition of Ready?** — Requirements 100% clear
- [ ] **Tests passing?** — 100% required
- [ ] **Root cause understood?** — For fixes, understand WHY first

---

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
