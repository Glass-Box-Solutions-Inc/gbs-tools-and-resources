# Agentic Debugger

**Automated CI test failure debugging agent — template for adoption.**

---

## Project Overview

| Field | Value |
|-------|-------|
| Status | Template for Adoption |
| Source | `glassy-app-production` → `scripts/debug-agent.mjs` + `.github/workflows/agentic-debugger.yml` |
| Stack | Claude Code CLI, GitHub Actions, TypeScript, Linear API |
| Model | Claude Opus 4.6 (via Claude Code) |

---

## Architecture

```
GitHub Actions Workflow
├── Setup: pnpm, Node 20, Prisma, Postgres 16+pgvector
├── Re-run tests → capture failure output
├── debug-agent.mjs
│   ├── Environmental failure detection (exit 2)
│   ├── Failing spec parsing (Jest regex)
│   ├── Claude Code CLI invocation
│   │   ├── Max 20 turns, 8-min timeout
│   │   ├── Allowed tools: Read, Edit, Bash(tsc only)
│   │   └── Reads CLAUDE.md for project conventions
│   └── TypeScript verification gate (tsc --noEmit)
├── Commit & push (if tsc passes)
└── Linear ticket update
```

---

## File Map

| File | Purpose |
|------|---------|
| `scripts/debug-agent.mjs` | Agent orchestrator — failure parsing, Claude CLI invocation, tsc gate |
| `workflows/agentic-debugger.yml` | GitHub Actions workflow — job runner, service setup, Linear integration |

---

## Key Dependencies

- `@anthropic-ai/claude-code` — Claude Code CLI (installed at runtime in workflow)
- GitHub Actions services: PostgreSQL 16 + pgvector
- Secrets: `ANTHROPIC_API_KEY`, `LINEAR_API_KEY`

---

## Exit Code Semantics

| Code | Meaning | Workflow Action |
|------|---------|-----------------|
| 0 | Success — agent ran, changes verified | Commit & push, update Linear |
| 1 | Agent failed — tsc gate failed or no patches | Skip commit, fail job |
| 2 | Environmental failure — missing keys, network | Skip agent, escalate to human |

---

## Safety Constraints

- **Tool-restricted Claude environment**: Read + Edit + tsc only
- **File scope**: Only `backend/src/` and `backend/test/`
- **No destructive edits**: Never truncate >15% of file, never delete functions
- **Forbidden**: schema.prisma, CI workflows, package.json, frontend code
- **TypeScript gate**: Must pass `tsc --noEmit` before any commit
- **Max 5 attempts** per Linear ticket

---

## Configuration

### Workflow Inputs (manual dispatch)
| Input | Description |
|-------|-------------|
| `linear_ticket_id` | Linear issue ID for tracking |
| `test_failure_log` | Failure excerpt (max 4000 chars) |
| `attempt_number` | 0-indexed counter (0-4) |
| `commit_sha` | The develop commit that failed |

### Environment Variables (set in workflow)
| Variable | Value |
|----------|-------|
| `DATABASE_URL` | PostgreSQL connection string |
| `NODE_ENV` | `test` |
| `BETTER_AUTH_SECRET` | Test-only secret |
| `PORT` | 3000 |

---

## Known Limitations

1. Manual trigger only — no auto-detection of CI failures
2. Glassy-specific regex and file scope patterns
3. Backend-only (no frontend/UI test support)
4. Linear-coupled (no standalone mode)
5. Single-repo (no cross-package monorepo awareness)

---

## Related Documentation

- Source: `glassy-app-production` (`scripts/` + `.github/workflows/`)
- Adoption guide: See `README.md` in this package

---

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
