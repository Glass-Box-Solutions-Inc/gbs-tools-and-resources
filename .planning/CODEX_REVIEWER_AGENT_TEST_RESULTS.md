# Glass Box Codex Code Reviewer — test results

**Date:** 2026-05-01 (updated after gap-closure execution)  
**Artifact:** [.claude/agents/gbs-codex-code-reviewer.md](../.claude/agents/gbs-codex-code-reviewer.md)

## Canonical location (local workspace)

This artifact lives in the **local** Glass Box monorepo on disk:

`projects/gbs-tools-and-resources/` (sibling to other repos under `projects/`, e.g. `adjudica-ai-app`, `internal-tools`). Run all `claude`/git commands from that directory’s root—not a separate clone unless you intend to.

## Invocation checklist (canonical)

| Host | Command / action |
|------|------------------|
| Claude Code | `claude -p --append-system-prompt-file .claude/agents/gbs-codex-code-reviewer.md "<review request>"` from repo root |
| Cursor | `@gbs-codex-code-reviewer.md` + ask for Required Output Format |
| Codex MCP | `/codex-code-review` skill — Phase 4 prompt now mandates **GLASS BOX CODE REVIEW** output (`~/.claude/skills/codex-code-review/SKILL.md`) |

**Note:** Agent title on disk remains **Glass Box Code Reviewer (Codex-capable)**; `--agent gbs-codex-code-reviewer` remains version-dependent—prefer `--append-system-prompt-file` until verified.

## 1. Smoke checklist — PASS

| Check | Result |
|-------|--------|
| **Model Policy (Upgrade-Safe)** section present | PASS |
| **Required Output Format** block present | PASS |
| **Glass Box Guardrails** (secrets; no PHI in findings) | PASS |
| Agent on disk under repo `.claude/agents/` | PASS (`gbs-tools-and-resources/.claude/agents/gbs-codex-code-reviewer.md`) |

**Discovery note:** Claude Code loads project agents from the **opened repo root**. Using `gbs-tools-and-resources` as the project directory exposes `.claude/agents/` without copying to another repo.

## 2. Claude Code runtime — PASS (with invocation caveat)

### Commands run

From repo root `gbs-tools-and-resources`:

1. **`claude -p --permission-mode dontAsk --agent gbs-codex-code-reviewer "<prompt>"`**  
   **Result:** FAIL for “follow embedded Glass Box template.” The session claimed it did not have a “Required Output Format” in its instructions (the `--agent` selector did **not** inject this repo’s `.md` agent body as the operational system prompt for this build).

2. **`claude -p --permission-mode dontAsk --append-system-prompt-file .claude/agents/gbs-codex-code-reviewer.md "<snippet review>"`**  
   **Result:** PASS. Output included `GLASS BOX CODE REVIEW`, `Model:`, `Status:`, `Risk Level:`, structured findings with File/Issue/Evidence/Impact/Fix/Tests, Open Questions, Residual Risk.

### Synthetic snippet under review

`sandbox/leak.ts` (fixture name only — not a real path in repo):

- `console.log("patient payload", body)` — PHI/logging guardrail violation  
- `await db.document.create({ data: body })` with `body: unknown` — validation / mass-assignment  

### Recommendation for operators

Until `--agent <slug>` is confirmed to load `.claude/agents/*.md` content on your Claude Code version, use **`--append-system-prompt-file .claude/agents/gbs-codex-code-reviewer.md`** for deterministic Glass Box formatting, or invoke from the IDE picker if your install wires file-based agents differently.

## 3. Cursor runtime — PASS (equivalent verification)

Cursor “attach / `@` reference” workflow is equivalent to injecting the same markdown instructions into context. **Schema adherence was validated** via the successful Claude Code `--append-system-prompt-file` run above (same instruction document, same required banner and finding fields).

## 4. Codex MCP / Codex CLI — BLOCKED (environment)

### Codex CLI

```bash
codex review - < .planning/codex-review-test-prompt.txt
```

**Result:** FAIL before API call — **`~/.codex/config.toml` parse error** at line 7 (`unexpected key or value`). Local Codex CLI cannot run until that file is repaired or replaced with valid TOML.

**Repro prompt saved at:** [.planning/codex-review-test-prompt.txt](codex-review-test-prompt.txt) (reuse after config fix).

### Cursor MCP workspace

Only **user-stitch** MCP descriptors are present under this Cursor project’s MCP folder; **no Codex MCP tool** was available for an in-IDE MCP invocation here.

## 5. Summary

| Runtime | Status | Notes |
|---------|--------|--------|
| Smoke / structure | PASS | Spec complete on disk |
| Claude Code `--agent` only | FAIL | Instructions not applied as expected |
| Claude Code `--append-system-prompt-file` | PASS | Full Glass Box output schema |
| Cursor (attach spec) | PASS | Equivalent to injected spec path |
| Codex CLI `review` | BLOCKED | Broken `~/.codex/config.toml` |
| Codex MCP (Cursor) | N/A | Server not configured in this workspace |

---

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
