# Agentic Debugger

**Automated CI test failure debugging agent** — uses Claude Code to detect, diagnose, and fix test failures on the `develop` branch with TypeScript verification gates.

> **Status:** Template for Adoption | **Source:** `glassy-app-production` (`scripts/debug-agent.mjs` + `.github/workflows/agentic-debugger.yml`)

This is a **reference copy** from the Glassy PAI production monorepo, packaged here as an adoption template for other GBS repositories.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Agent | Claude Code CLI (`@anthropic-ai/claude-code`) |
| Model | Claude Opus 4.6 (via Claude Code) |
| Workflow | GitHub Actions |
| Verification | TypeScript (`tsc --noEmit`) |
| Integration | Linear API (ticket tracking) |
| Services | PostgreSQL 16 + pgvector |

---

## How It Works

```
CI Test Failure on develop
         │
         ▼
Manual Workflow Dispatch (GitHub Actions UI)
  Input: Linear ticket ID, failure log, attempt #, commit SHA
         │
         ▼
Setup: Install deps → Prisma generate → Prisma migrate
         │
         ▼
Re-run Tests → Capture Fresh Failure Output
         │
         ▼
debug-agent.mjs: Parse Failures
         │
    ┌────┴────┬──────────────┐
    │         │              │
 (exit 2)  (continue)   (no failures)
 ENV ISSUE    │           SKIP
 ESCALATE     ▼
         Claude Code CLI
         (20 turns max, 8 min timeout)
         Allowed: Read, Edit, Bash(tsc only)
              │
         TypeScript Gate (tsc --noEmit)
              │
         ┌────┴────┐
      (pass)     (fail)
         │       Exit 1
    Commit & Push
    Update Linear Ticket
```

### Exit Codes

| Code | Meaning | Action |
|------|---------|--------|
| 0 | Success — changes verified | Commit, push, update ticket |
| 1 | Agent failed — tsc gate failed | Skip commit, fail job |
| 2 | Environmental failure | Skip agent, escalate to human |

### Environmental Failure Detection

The agent detects non-fixable issues before invoking Claude:
- Missing API keys (GEMINI_API_KEY, ANTHROPIC_API_KEY, etc.)
- Network errors (ECONNREFUSED, ECONNRESET, ENOTFOUND)
- Missing node_modules
- Connection timeouts

---

## Safety Constraints

| Constraint | Detail |
|-----------|--------|
| Tool restrictions | Only `Read`, `Edit`, `Bash(tsc verification)` allowed |
| File scope | Only `backend/src/` and `backend/test/` editable |
| No destructive edits | Never truncate >15% of file lines |
| No function deletion | Never delete entire functions, classes, or endpoints |
| Forbidden files | `prisma/schema.prisma`, CI workflows, `package.json`, frontend |
| Import style | Must use `import type { ... }` (isolatedModules: true) |
| TypeScript gate | Must pass `tsc --noEmit` before commit is allowed |
| Max attempts | 5 total per ticket |

---

## Adopting in Your Repo

### 1. Copy the workflow

```bash
cp workflows/agentic-debugger.yml .github/workflows/agentic-debugger.yml
```

### 2. Copy the debug agent script

```bash
cp scripts/debug-agent.mjs scripts/debug-agent.mjs
```

### 3. Configure GitHub secrets

| Secret | Required | Purpose |
|--------|----------|---------|
| `ANTHROPIC_API_KEY` | Yes | Claude Code CLI authentication |
| `LINEAR_API_KEY` | Yes | Linear ticket updates |

### 4. Customize for your project

Edit `debug-agent.mjs`:
- Update the FAIL line regex for your test runner output format
- Adjust allowed file scope paths
- Modify the tsc verification command for your project
- Update environment variables in the workflow

### 5. Trigger manually

Go to GitHub Actions → "Agentic Debugger" → Run workflow, providing:
- Linear ticket ID
- Test failure excerpt (max 4000 chars)
- Attempt number (0-indexed)
- Commit SHA

---

## File Structure

```
packages/agentic-debugger/
├── scripts/
│   └── debug-agent.mjs     # Main agent — failure parsing, Claude CLI, tsc gate
├── workflows/
│   └── agentic-debugger.yml # GitHub Actions workflow definition
├── README.md
└── CLAUDE.md
```

---

## Known Limitations

1. **Manual trigger only** — not yet automated on CI failure detection
2. **Glassy-specific** — regex patterns and file scopes target Glassy's monorepo structure
3. **Backend-only** — only fixes `backend/src/` and `backend/test/` files
4. **No frontend support** — cannot fix React/UI test failures
5. **Single-repo** — doesn't handle cross-package failures in monorepos
6. **Linear-coupled** — requires Linear for ticket tracking (no standalone mode)

## Improvement Roadmap

- [ ] Auto-trigger from CI failure webhook (eliminate manual dispatch)
- [ ] Generalize file scope detection from project structure
- [ ] Frontend test failure support
- [ ] Multi-package monorepo awareness
- [ ] Standalone mode without Linear dependency
- [ ] Configurable test runner integration (Jest, Vitest, Playwright)
- [ ] Success rate tracking and metrics dashboard

---

## Related Packages

- [agent-swarm](../agent-swarm/) — Multi-agent task orchestration (DAG-based)
- [spectacles](../spectacles/) — Browser automation (can verify UI after fixes)
- [merus-expert](../merus-expert/) — Domain agent pattern (tool-calling loop)

---

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
