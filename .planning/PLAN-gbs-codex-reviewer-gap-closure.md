# PLAN — Glass Box Codex Code Reviewer — gap closure

**Created:** 2026-05-01  
**Status:** Executed (2026-05-01)  
**Artifact:** [.claude/agents/gbs-codex-code-reviewer.md](../.claude/agents/gbs-codex-code-reviewer.md)

---

## Goal

Close evaluation gaps so the agent is **clear to operators**, **consistent under Claude/Cursor/Codex**, **audit-friendly**, and **aligned with Glass Box merge gates**—without turning it into an overlapping duplicate of domain specialists (HIPAA/OAuth/etc.).

## Definition of Done (program-wide)

- Agent markdown documents **invocation**, **Status/Risk reconciliation**, **optional metadata**, **large-diff behavior**, **internal policy pointers**, and **non-goals**.
- At least one **smoke verification** documented (CLI or manual checklist) after edits.
- Optional follow-up: **`/codex-code-review` skill** prepends Glass Box output block when team agrees (may live outside this repo).

---

## Gap inventory → planned work

### G1 — Naming vs behavior (“Codex-centric” vs host-agnostic)

**Issue:** Title/description imply Codex-only; instructions work on any host model.

**Plan:**

- Add an **Invocation & hosts** subsection stating: primary artifact is **review instructions**; Codex MCP/CLI, Claude (`--append-system-prompt-file`), and Cursor (`@` file) are supported hosts.
- Optionally rename heading from “Codex Code Reviewer” to **“Glass Box Code Reviewer (Codex-capable)”** *or* keep filename and add one clarifying sentence under Description—**pick one** during execution to avoid churn across docs.

**Acceptance:** A new reader understands Codex is optional, not mandatory.

---

### G2 — Status vs Risk Level ambiguity

**Issue:** `APPROVE WITH CHANGES` + `Risk Level: CRITICAL` can confuse reviewers.

**Plan:**

- Add **Reconciliation rules**, for example:
  - **Risk Level** = severity of worst **unresolved** finding after proposed fixes (or current state if no fix proposed).
  - **Status** = merge recommendation **assuming listed fixes land** before merge (except BLOCK when CRITICAL remains).
  - Explicit rule: **BLOCK** if any finding remains CRITICAL without mitigation path; **APPROVE WITH CHANGES** if CRITICAL mitigations are specified and verifiable.

**Acceptance:** Two reviewers interpreting the same output assign the same merge stance after reading rules.

---

### G3 — Audit metadata missing from template

**Issue:** No PR/repo/base/head/ticket fields for audit trail.

**Plan:**

- Extend **Required Output Format** with optional lines (omit when unknown):

  ```
  Repo: <owner/repo or path>
  Scope: <branch vs main | PR #N | commit SHA>
  Ticket: <Linear ID if any>
  ```

**Acceptance:** Paste into Linear/GitHub comment without editing structure.

---

### G4 — Evidence quality (line anchors)

**Issue:** Evidence is stronger with line ranges.

**Plan:**

- Under Evidence rule: prefer **`path:line` or `path:start-end`** when sourced from diff or file read.

**Acceptance:** Example finding in tests shows line anchors.

---

### G5 — Large diffs / patch size

**Issue:** Agent silent on chunking; skill `codex-code-review` handles size thresholds.

**Plan:**

- Add **Large change sets** bullets: follow repo/org convention—if patch exceeds internal threshold (~250 KB per existing skill), supply **changed-file list** and instruct reviewer to open files or split review by area; never omit Evidence by guessing.

**Acceptance:** Agent text references one canonical threshold or says “follow local codex-code-review skill / team SOP.”

---

### G6 — Merge gates (LVR, wave propagation)

**Issue:** Agent does not mention when human co-signature or branch sync applies.

**Plan:**

- Add **Glass Box merge gates (pointer)** subsection: if changed paths touch **Agent-Signed LVR** categories or PR workflow uses **wave propagation**, reviewers must follow internal docs—link [AGENT_HITL_PATTERNS_STANDARD.md](https://github.com/Glass-Box-Solutions-Inc/adjudica-documentation/blob/main/engineering/AGENT_HITL_PATTERNS_STANDARD.md) and [THREE_BRANCH_CI_STANDARD.md](https://github.com/Glass-Box-Solutions-Inc/adjudica-documentation/blob/main/engineering/THREE_BRANCH_CI_STANDARD.md) (paths only; no secrets).

**Acceptance:** Agent flags “high-risk path category → verify LVR/wave policy” without duplicating full policy text.

---

### G7 — Operational: Claude Code `--agent` slug mismatch

**Issue:** `--agent gbs-codex-code-reviewer` did not inject markdown body on tested version.

**Plan:**

- Document **preferred invocation** at top of agent file:

  - `claude -p --append-system-prompt-file .claude/agents/gbs-codex-code-reviewer.md "..."`

  - Cursor: `@gbs-codex-code-reviewer.md` + “follow Required Output Format.”

- Add note: **`--agent <slug>`** is version-dependent; re-verify after Claude Code upgrades.

**Acceptance:** [CODEX_REVIEWER_AGENT_TEST_RESULTS.md](CODEX_REVIEWER_AGENT_TEST_RESULTS.md) updated or superseded by short “Invocation” checklist after execution.

---

### G8 — Compliance boundaries for juniors / AI routing

**Issue:** No explicit “don’t paste prod PHI into chat” or “external API = org policy.”

**Plan:**

- Add **Non-goals** + **Input hygiene**: not legal/compliance sign-off; not a penetration test; do not paste secrets or prod PHI—use IDs/redacted snippets only; external model routing subject to **BAA/org AI policy**.

**Acceptance:** Guardrails section references input hygiene without repeating PHI examples verbatim.

---

### G9 — Skill parity (`/codex-code-review`)

**Issue:** Skill uses generic priorities; agent mandates Glass Box banner.

**Plan (optional phase):**

- Edit [`~/.claude/skills/codex-code-review/SKILL.md`](/home/vncuser/.claude/skills/codex-code-review/SKILL.md) Phase 4 prompt to **prepend** Glass Box principles + Required Output Format from this agent (or symlink excerpt maintained in single source).

**Acceptance:** One Codex MCP run emits `GLASS BOX CODE REVIEW` banner with Model line.

**Dependency:** Codex MCP available + stable skill distribution policy (personal vs org repo).

---

### G10 — Versioning / changelog

**Issue:** Single “Last Updated” line only.

**Plan:**

- Add **Revision** subsection or footer `CHANGELOG:` one-line bullets when agent changes.

**Acceptance:** Future edits bump date + bullet.

---

## Execution order (recommended)

| Phase | Items | Notes |
|-------|--------|--------|
| P0 | G1, G2, G3, G4, G8 | Agent body only; highest reviewer clarity |
| P1 | G5, G6, G7 | Ops + policy pointers |
| P2 | G10 | Lightweight hygiene |
| P3 | G9 | Optional; coordinate with skill ownership |

---

## Risks

- **Scope creep:** Avoid duplicating HIPAA/OAuth specialist checklists—keep pointers.
- **Doc drift:** Links to `adjudica-documentation` must stay stable URLs (repo moves break links).
- **Skill location:** `~/.claude/skills/` may be user-local; org may prefer copying skill into `gbs-tools-and-resources` package later.

---

## Out of scope (this plan)

- Replacing human review or LVR co-signature.
- Auto-posting to GitHub without human approval.
- Pinning model versions organization-wide (remains env/host responsibility).

---

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
