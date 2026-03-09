# Squeegee Architecture Report

**Comprehensive Technical Analysis — Synthesized from Parallel Codebase Exploration**

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [System Architecture Overview](#1-system-architecture-overview)
3. [Data Flow Diagram](#2-data-flow-diagram)
4. [Stage-by-Stage Reference](#3-stage-by-stage-reference)
5. [Subsystem Deep Dives](#4-subsystem-deep-dives)
6. [Design Strengths](#5-design-strengths)
7. [Technical Debt and Weaknesses](#6-technical-debt-and-weaknesses)
8. [Code Metrics](#7-code-metrics)
9. [Test Suite Analysis](#8-test-suite-analysis)
10. [Security Assessment](#9-security-assessment)
11. [Scalability Analysis](#10-scalability-analysis)
12. [Cross-Subsystem Redundancy](#11-cross-subsystem-redundancy)
13. [Missing Abstractions](#12-missing-abstractions)
14. [Recommendations](#13-recommendations-top-10)
15. [Dependency Map](#14-dependency-map)

---

## Executive Summary

Squeegee is a 23-stage documentation curation and intelligence pipeline that runs as a Cloud Run service for Glass-Box-Solutions-Inc. It automatically discovers, curates, audits, and publishes documentation across all repos in the GitHub org by cloning each repo, applying staged transformations, and opening PRs with the results.

**Scale:** ~19,400 lines of source code, ~10,200 lines of tests, 469 passing tests across 30 test files.

**Trigger mechanisms:** Cloud Scheduler (daily 6 AM UTC), GitHub push webhooks (5-minute debounce), or manual HTTP calls via OIDC-protected API.

**Three pipeline chains run in sequence or independently:**

- **Curation (stages 1-13, ~3,944 LOC):** Discovers projects, analyzes git history, curates `STATE.md`, `PROGRAMMING_PRACTICES.md`, `PLANS_APPROVED.md`, changelogs, pattern libraries, health reports, and `CLAUDE.md` files. Fully production-ready.
- **Intelligence (stages 14-20, ~5,899 LOC):** Collects GitHub/GCP/station data, synthesizes Gemini briefings, writes logs to `adjudica-documentation`, audits CLAUDE.md compliance (weekly), audits doc quality (monthly), conducts web research (quarterly), and sends Slack notifications. Stages 14-17 are production-ready; stages 18-20 are implemented as stubs.
- **Portal (stages 21-23, ~3,228 LOC):** Collects GitHub/Linear data, generates Mermaid diagrams and explanations via Gemini, renders 17 HTML pages via Nunjucks, and uploads to GCS. Fully production-ready.

**Critical gap:** `runFull()` in `src/pipeline/index.js` runs only stages 1-10. Stages 11-13 (generate, validate, claudemd) and all intelligence and portal stages are excluded from the default full run, making them accessible only by explicit command.

---

## 1. System Architecture Overview

### Infrastructure

Squeegee runs on Cloud Run in project `glassbox-squeegee`, region `us-central1`. Key infrastructure parameters:

| Parameter | Value |
|-----------|-------|
| Memory | 1 GiB |
| CPU | 1 vCPU |
| Min instances | 0 (scale to zero) |
| Max instances | 1 (no parallel runs) |
| Timeout | 900s (15 minutes) |
| Auth | OIDC (`--no-allow-unauthenticated`) |
| Scheduler | `squeegee-daily` — `0 6 * * *` UTC |
| State file | `/tmp/squeegee-state.json` (last 10 run summaries) |

### Server Layer

`src/server.js` (213 LOC) is the Fastify entrypoint. All pipeline work executes via `setImmediate()` (fire-and-forget), returning HTTP 202 immediately so Cloud Run does not terminate the request during a long run. The server registers:

- Core routes inline (health, status, `/api/run`, `/api/run/:command`, `/api/webhook`)
- Intelligence routes as a Fastify plugin (`src/api/intelligence.js`)
- Portal routes as a Fastify plugin (`src/api/portal.js`)

### Org Discovery Loop

`src/github/org-discovery.js` (374 LOC) is the primary orchestration engine. For each repo:

1. Fetches non-fork, non-archived repos from the GitHub API with pagination.
2. Shallow-clones the repo to `/tmp/squeegee-workspace/{name}` using `spawnSync` with `stdio: 'pipe'`.
3. Builds a disposable in-memory `squeegee.config.json` object via `buildRepoConfig()`.
4. Calls `runPipeline(command, workdir, prebuiltConfig)`.
5. Checks `git status --porcelain` for changes.
6. If changes exist: creates a branch, commits, pushes, opens a PR via GitHub REST API.
7. Cleans up the clone directory with `fs.rm({ recursive: true })`.
8. Appends a run record to `/tmp/squeegee-state.json`.

### Configuration Layer

Three configuration files, each serving a different subsystem:

```
squeegee.config.json        — Curation pipeline (projects list, docTypes, quality thresholds)
config/intelligence.config.json — Intelligence + Portal schedules, repos, GCP projects, Gemini settings
config/portal.config.json   — 15 repo definitions for portal generation
```

`src/pipeline/config.js` caches the loaded curation config in a module-level variable to avoid repeated disk reads within a single pipeline run.

### Subsystem LOC Breakdown

| Subsystem | Directory | LOC (approx) |
|-----------|-----------|--------------|
| Curation pipeline | `src/pipeline/stages/01-13` + analyzers + formatters | ~3,944 |
| Intelligence modules | `intelligence/` + `src/pipeline/stages/14-20` | ~5,899 |
| Portal modules | `src/portal/` + `src/pipeline/stages/21-23` | ~3,228 |
| Server + infrastructure | `src/server.js` + `src/github/` + `src/api/` | ~1,444 |
| Shared utilities | `src/pipeline/utils.js` + `src/pipeline/config.js` + formatters | ~716 |
| **Total source** | | **~19,400** |

---

## 2. Data Flow Diagram

### Trigger Sources

```
Cloud Scheduler (daily 6am UTC)
        |
        v
POST /api/run  ──────────────────────────────────────────────────┐
                                                                  |
GitHub push webhook ──> /api/webhook ──> (5-min debounce) ──────>│
                                                                  |
Manual HTTP call ──────────────────────────────────────────────> │
                                                                  v
                                               setImmediate() → runOrgPipeline()
```

### Org Discovery → Per-Repo Pipeline

```
GitHub API (org repos)
        |
        v
fetchOrgRepos() → filter (not fork, not archived)
        |
        v
for each repo:
  cloneRepo() → /tmp/squeegee-workspace/{name}/
        |
        v
  buildRepoConfig() → in-memory squeegee.config.json
        |
        v
  runPipeline(command, workdir, prebuiltConfig)
        |
        v
  hasChanges() → git status --porcelain
        |
  [changes] → publishChanges() → GitHub PR
  [no changes] → skip
        |
        v
  cleanupWorkspace() → rm -rf /tmp/squeegee-workspace/{name}
        |
        v
recordRun() → /tmp/squeegee-state.json
```

### Curation Chain (Stages 1-13)

```
Stage 1: Discover ──────────────────────────────────────────────────────────────┐
  Input: config.projects[], filesystem                                           |
  Output: { projects[], markdown[], code[] }                                     |
                                                                                 |
Stage 2: Git Analyze ────────────────────────────────────────────────────────── |
  Input: git log (execSync), filesystem                                          |
  Output: { commits[], authors[], dateRange }                                    |
                                                                                 |
Stage 3: State Curate ← disc, git ─────────────────────────────────────────────|
  Input: disc, git, .planning/STATE.md                                           |
  Output: updated STATE.md (within SQUEEGEE:AUTO markers)                        |
                                                                                 |
Stage 4: Practices ← disc ──────────────────────────────────────────────────────|
  Input: disc, PROGRAMMING_PRACTICES.md                                          |
  Output: updated PROGRAMMING_PRACTICES.md                                       |
                                                                                 |
Stage 5: Plans ← disc, git ────────────────────────────────────────────────────|
Stage 6: Changelog ← disc, git ─────────────────────────────────────────────── |
Stage 7: Patterns ← disc ────[disabled in org mode via patternLibrary.enabled]──|
Stage 8: Health ← disc ───────────────────────────────────────────────────────  |
  Output: health scores JSON + health-report.md                                  |
Stage 9: Projects Index ← disc                                                   |
Stage 10: Commit Summary ← git                                                   |
Stage 11: Generate (missing docs) ← disc ─────────────────────────────────────── |
Stage 12: Validate ← disc                                                         |
Stage 13: CLAUDE.md Curation ← disc ──────────────────────────────────────────── ┘
  Output: updated CLAUDE.md (tech-stack, commands sections auto-updated)
```

### Intelligence Chain (Stages 14-20)

```
GitHub API (commits, PRs, issues, CI runs)  ──────────────────┐
GCP Cloud Logging (deployment events, errors)  ────────────────┤
GCS (station activity data)  ──────────────────────────────────┤
                                                               v
                                             Stage 14: Collect ──────────────────┐
                                               Output: { github, gcp, station }   |
                                                               |                  |
                                             Stage 15: Synthesize ────────────────|
                                               Input: collected data              |
                                               Model: gemini-2.5-flash            |
                                               Output: { briefing, fallback_used }|
                                                               |                  |
                                             Stage 16: Write ────────────────────|
                                               GitHub API → adjudica-documentation|
                                               Writes: commits, prs, deployments, |
                                                 agents, checkpoints, analysis    |
                                                               |                  |
                                             Stage 17: Audit CLAUDE.md (Sundays)  |
                                               GitHub API → fetch CLAUDE.md files |
                                               Output: compliance scores, auto-PRs |
                                                               |                  |
                                             Stage 18: Audit Doc Quality (stub)    |
                                             Stage 19: Research (stub)             |
                                             Stage 20: Notify Slack (stub)  ───── ┘
```

### Portal Chain (Stages 21-23)

```
GitHub API (365d commits, contributors, PRs, health)  ────────┐
Linear API (sprints, issues)  ─────────────────────────────────┤
config/portal.config.json (15 repo configs)  ──────────────────┤
                                                               v
                                             Stage 21: Collect ──────────────────┐
                                               Output: { projects[], heatmap }    |
                                               Persists: project-cache.json       |
                                                               |                  |
                                             Stage 22: Portal AI ────────────────|
                                               Gemini: architecture diagrams      |
                                               Gemini: technical explanations     |
                                               Gemini: user journey pages         |
                                               Cache: config/portal-ai-cache.json |
                                               (skips unchanged projects)         |
                                                               |                  |
                                             Stage 23: Render ──────────────────  |
                                               Nunjucks: 17 HTML pages            |
                                               Output: /tmp/portal-output/        |
                                               GCS upload: portal bucket  ──────  ┘
```

---

## 3. Stage-by-Stage Reference

| # | Command | File | Purpose | External Deps | Status |
|---|---------|------|---------|---------------|--------|
| 1 | `scan` | `stages/01-discover.js` | Discover projects and scan docs/code | Filesystem | Production |
| 2 | `analyze` | `stages/02-git-analyze.js` | Analyze git history (commits, authors, dates) | `git log` (execSync) | Production |
| 3 | `variable` | `stages/03-state-curate.js` | Curate `.planning/STATE.md` within SQUEEGEE markers | Filesystem | Production |
| 4 | `practices` | `stages/04-practices.js` | Curate `PROGRAMMING_PRACTICES.md` | Filesystem | Production |
| 5 | `plans` | `stages/05-plans.js` | Curate `PLANS_APPROVED.md` | Filesystem | Production |
| 6 | `changelog` | `stages/06-changelog.js` | Generate per-project changelogs | `git log` | Production |
| 7 | `patterns` | `stages/07-patterns.js` | Cross-project pattern library | Filesystem | Disabled in org mode |
| 8 | `report` | `stages/08-health.js` | Calculate doc health scores | Filesystem | Production |
| 9 | `projects` | `stages/09-projects-index.js` | Update projects index | Filesystem | Production |
| 10 | `state` | `stages/10-commit-summary.js` | Save pipeline state | Filesystem | Production |
| 11 | `generate` | `stages/11-generate.js` | Generate missing documentation | `git log`, `package.json`, stack detection | Production (not in `runFull`) |
| 12 | `validate` | `stages/12-validate.js` | Validate documentation quality | Filesystem | Production (not in `runFull`) |
| 13 | `claudemd` | `stages/13-claudemd.js` | Curate `CLAUDE.md` files | `package.json`, stack-detector | Production (not in `runFull`) |
| 14 | `collect` | `stages/14-intelligence-collect.js` | Collect GitHub activity, GCP metrics, station data | GitHub API, GCP Logging, GCS | Production |
| 15 | `synthesize` | `stages/15-intelligence-synthesize.js` | Generate Gemini briefing | `@google/generative-ai` (gemini-2.5-flash) | Production |
| 16 | `write` | `stages/16-intelligence-write.js` | Write structured logs to adjudica-documentation | GitHub API (Octokit) | Production |
| 17 | `audit-claude` | `stages/17-intelligence-audit-claude.js` | CLAUDE.md compliance audit (Sundays) | GitHub API (Octokit) | Production |
| 18 | `audit-quality` | `stages/18-intelligence-audit-quality.js` | Doc quality audit (1st of month) | (none — stub) | Stub (TODO comment) |
| 19 | `research` | `stages/19-intelligence-research.js` | Quarterly best-practice web research | (none — stub) | Stub (TODO comment) |
| 20 | `notify` | `stages/20-intelligence-notify.js` | Send briefing to Slack | (none — stub) | Stub (TODO comment) |
| 21 | `portal-collect` | `stages/21-portal-collect.js` | Fetch GitHub + Linear data for portal | GitHub API, Linear API | Production |
| 22 | `portal-ai` | `stages/22-portal-ai.js` | Generate diagrams + explanations via Gemini | `@google/generative-ai`, GitHub API | Production |
| 23 | `portal-render` | `stages/23-portal-render.js` | Render HTML + upload to GCS | Nunjucks, `@google-cloud/storage` | Production |

### Stage Dependencies

Each stage that re-runs prior stages independently (no shared state between switch cases in `runPipeline()`):

```
variable  → runs discover + gitAnalyze inline
practices → runs discover inline
plans     → runs discover + gitAnalyze inline
changelog → runs discover + gitAnalyze inline
patterns  → runs discover inline
report    → runs discover inline
projects  → runs discover inline
state     → runs gitAnalyze inline
generate  → runs discover inline
validate  → runs discover inline
claudemd  → runs discover inline
```

This design means a `full` run of 10 stages calls `discover.run()` 10 separate times and `gitAnalyze.run()` 5 separate times. The `runFull()` function avoids this by sharing `disc` and `git` variables, but it only covers stages 1-10.

---

## 4. Subsystem Deep Dives

### 4.1 Curation Subsystem (Stages 1-13)

**Architecture:** Pure Node.js stdlib — no npm dependencies. Each stage is a focused module exporting a single `run(config, ...prevData)` function. The `SQUEEGEE:AUTO:START/END` marker system in `src/pipeline/formatters/sections.js` implements non-destructive file editing: only content inside markers is replaced; all other content is preserved.

**Key design patterns:**
- `updateSections(filePath, { tag: newContent })` — atomic marker-based update
- `detectStack(projectPath)` — infers tech stack from `package.json`, `requirements.txt`, `Gemfile`, etc.
- `analyzeMarkdown(filePath, workspace)` — extracts headings, links, and code blocks
- Stage isolation: each stage can run standalone by re-invoking prior stages

**Maturity: 4/5.** All 13 stages are individually callable and tested by the integration suite. The primary weakness is that `runFull()` (the default execution path) only covers stages 1-10, silently omitting stages 11-13. Stage 7 (pattern library) is explicitly disabled via `patternLibrary.enabled: false` in the org-mode config built by `buildRepoConfig()`.

**Strengths:** Idempotent, no external dependencies, fast execution (~5-15s per repo for stages 1-10).

**Weaknesses:** Stage 7 cannot aggregate cross-project patterns in org mode since each repo is cloned and processed in isolation. The `runFull()` omission of stages 11-13 is a silent correctness gap — the help text accurately lists them but the implementation does not run them.

---

### 4.2 Intelligence Subsystem (Stages 14-20)

**Architecture:** Orchestrated by `intelligence/morning-run.js` (the standalone runner) and `src/api/intelligence.js` (the HTTP API). Modules in `intelligence/` are self-contained with their own Octokit clients and error classes. Three custom error types (`GitHubAPIError`, `GCPLoggingError`, `GCSStorageError`) carry `.recoverable` flags — a clean pattern for distinguishing transient vs. permanent failures.

**Key modules:**
- `intelligence/github-collector.js` — Octokit with retry+throttling plugins, parallel collection (commits, PRs, issues, CI runs) via `Promise.all`
- `intelligence/gcp-collector.js` — GCP Cloud Logging client for deployment events and error rates
- `intelligence/station-collector.js` — GCS-backed dev station activity data
- `intelligence/gemini-synthesizer.js` — Gemini 2.5 Flash briefing generation with fallback to template-based output
- `intelligence/claude-md-auditor.js` — 13-point compliance rubric, creates auto-PRs for non-compliant repos
- `intelligence/log-writer.js` — writes 6 structured log files to `adjudica-documentation` via Octokit

**Maturity: 3/5.** Stages 14-17 are production-ready with comprehensive tests. Stages 18-20 are explicitly stubbed out with `TODO` comments pointing at modules that exist on disk (`doc-quality-auditor.js`, `web-researcher.js`, `slack-notifier.js`) but are commented out in both `src/api/intelligence.js` (lines 27-29) and the stage files. The `morning-run.js` orchestrator in `intelligence/` is a parallel implementation that calls `slack-notifier` directly — it is not wired into the HTTP API or the pipeline stage system.

**Strengths:** Structured error recovery, dry-run mode, per-module status reporting in `/api/intelligence/status`.

**Weaknesses:** 1,415 LOC of implemented modules (`doc-quality-auditor.js`, `web-researcher.js`, `slack-notifier.js`) are dormant. The `morning-run.js` and the stage 14-20 API represent two separate orchestration paths for the same work.

---

### 4.3 Portal Subsystem (Stages 21-23)

**Architecture:** Ported from a Python implementation (`glass-box-hub/squeegee/generator.py`). Uses Nunjucks templates (17 pages) for HTML rendering. A two-tier cache system (`config/portal-ai-cache.json`) skips Gemini regeneration for projects whose content hash has not changed, significantly reducing API costs on incremental runs.

**Key modules:**
- `src/portal/github-client.js` — 365-day commit history, contributors, PRs, developer heatmap
- `src/portal/linear-client.js` — Linear sprint and issue data
- `src/portal/diagram-generator.js` — Gemini-generated Mermaid architecture/data-flow/sequence diagrams
- `src/portal/explanation-generator.js` — Gemini-generated technical and non-technical project explanations
- `src/portal/renderer.js` — Nunjucks environment with custom filters, renders 17 HTML templates
- `src/portal/gcs-uploader.js` — uploads rendered HTML to GCS portal bucket
- `src/portal/project-cache.js` + `src/portal/ai-cache.js` — two-tier persistence

**Templates (17 pages):** `index`, `projects`, `project` (detail), `health`, `stack`, `trends`, `activity`, `diagrams`, `docs`, `intelligence`, `search`, `audits`, `dependencies`, `agents`, `team`, `admin`, `base` (layout).

**Maturity: 4/5.** All modules are fully implemented with tests. The cache system is well-designed. The primary concern is that `config/portal.config.json` (15 repos) and `config/intelligence.config.json` (27 repos) are maintained separately and have diverged.

**Strengths:** Content-hash caching, parallel Gemini calls per-project, incremental updates via single-repo webhook refresh.

**Weaknesses:** `portal.config.json` must be manually maintained in sync with the org's actual repo list. No auto-discovery of portal repos.

---

### 4.4 Infrastructure Subsystem

**Architecture:** `src/server.js` (Fastify), `src/github/org-discovery.js` (orchestration), `src/api/intelligence.js` and `src/api/portal.js` (route plugins).

**Maturity: 4/5.** Graceful shutdown (SIGTERM with 8s grace), webhook debounce, PAT redaction in error messages, loop prevention (auto-curate branch and `[squeegee-auto]` commit filtering), cold start safeguards.

**Weaknesses:** No webhook HMAC signature verification. State file at `/tmp/squeegee-state.json` is ephemeral — lost on cold starts. The `loadIntelligenceConfig()` function in `src/api/intelligence.js` reads `config/intelligence.config.json` from disk on every API call with no caching.

---

## 5. Design Strengths

### 5.1 Marker System (SQUEEGEE:AUTO:START/END)

Implemented in `src/pipeline/formatters/sections.js`, the marker system is the most consequential architectural decision in the codebase. It enables non-destructive, idempotent file editing by partitioning any markdown file into Squeegee-owned regions and human-owned regions.

```javascript
// From sections.js
const regex = /<!-- SQUEEGEE:AUTO:START (\S+) -->([\s\S]*?)<!-- SQUEEGEE:AUTO:END \1 -->/g;
```

This means Squeegee can update the `tech-stack` and `commands` sections of a `CLAUDE.md` without touching the project overview, architecture diagram, or any manually written content. The system is used across stages 3, 4, 5, 6, 9, and 13 and propagates into the org-wide self-curation of Squeegee's own `CLAUDE.md`.

**Evidence of correctness:** The markers appear in Squeegee's own `CLAUDE.md` (this file), demonstrating that the system is self-hosting and production-tested.

### 5.2 Fire-and-Forget Execution with Webhook Debouncing

`src/server.js` returns HTTP 202 immediately for all pipeline triggers using `setImmediate()`. This is essential for Cloud Run, which terminates connections after the timeout. The webhook handler in `src/server.js` (lines 107-167) implements a 5-minute debounce per repo name using a `Map` of `setTimeout` handles:

```javascript
const webhookDebounce = new Map();
const DEBOUNCE_MS = 5 * 60 * 1000;
```

This prevents thrashing when developers push multiple commits in rapid succession, and it filters Squeegee's own auto-curate commits to prevent infinite curation loops.

### 5.3 Per-Repo Isolation in Org Mode

`org-discovery.js` clones each repo to an isolated `/tmp/squeegee-workspace/{name}` directory, processes it completely, and then deletes it before moving to the next repo. This means:

- A failure in one repo does not contaminate another.
- Memory usage is bounded to one repo at a time.
- Each repo gets a fresh, disposable `prebuiltConfig` that eliminates `squeegee.config.json` file dependency in the cloned workspace.

The `try/catch/finally` in the main loop (lines 308-341) guarantees cleanup even on pipeline failure.

### 5.4 Structured Error Recovery with .recoverable Flags

`intelligence/utils.js` defines three custom error classes with a `.recoverable` boolean:

```javascript
class GitHubAPIError extends Error {
  constructor(message, statusCode, endpoint) {
    super(message);
    this.recoverable = statusCode === 429 || statusCode === 403;
  }
}
```

This pattern allows callers to distinguish between transient rate-limit errors (retryable) and permanent authentication failures (fail-fast). The `safeExecute()` helper uses this flag to decide whether to retry or return a default value.

### 5.5 Two-Tier AI Cache for Portal Content

`src/portal/ai-cache.js` implements content-hash-based caching for Gemini-generated content. Before calling Gemini for a project's diagrams or explanations, stage 22 computes a hash of the project's README and metadata, compares it to the stored hash in `config/portal-ai-cache.json`, and skips regeneration if nothing has changed.

```javascript
function hasChanged(cache, projectName, contentHash) {
  const cached = cache.projects?.[projectName];
  if (!cached) return true;
  return cached.content_hash !== contentHash;
}
```

At 15 repos with 3-5 Gemini calls each, this cache avoids 30-75 API calls per run when repos have not changed — a meaningful cost and latency reduction.

---

## 6. Technical Debt and Weaknesses

### 6.1 Stages 18-20: 1,415 LOC Dormant

Stages 18 (doc quality audit), 19 (web research), and 20 (Slack notification) all contain implemented modules in `intelligence/` but their stage files explicitly skip execution with TODO comments:

```javascript
// Stage 18: src/pipeline/stages/18-intelligence-audit-quality.js
// TODO: Implement when doc-quality-auditor.js is ready
// For now, return a placeholder result
log('Documentation quality auditor not yet implemented - skipping', 'warn');
```

The modules exist (`intelligence/doc-quality-auditor.js`, `intelligence/web-researcher.js`, `intelligence/slack-notifier.js`) and are imported in `intelligence/morning-run.js` — but are commented out in `src/api/intelligence.js` (lines 27-29). The API returns `501 Not Implemented` for `/audit-doc-quality`, `/research`, and `/notify`.

**Impact:** The daily intelligence pipeline is incomplete. Slack notifications, which are listed as a daily schedule item in `intelligence.config.json`, never fire.

### 6.2 Three Independent GitHub Client Implementations

Three separate modules create Octokit clients with identical configuration patterns:

| File | Octokit Setup |
|------|---------------|
| `intelligence/github-collector.js` | `Octokit.plugin(retry, throttling)` with rate-limit handlers |
| `intelligence/claude-md-auditor.js` | `Octokit.plugin(retry, throttling)` with rate-limit handlers |
| `intelligence/log-writer.js` | `Octokit.plugin(retry, throttling)` with rate-limit handlers |
| `src/portal/github-client.js` | `Octokit.plugin(retry, throttling)` with rate-limit handlers |

Each duplicates the same `createOctokit(token)` pattern. The `portal/github-client.js` file even contains a comment acknowledging this: "Reuses the Octokit setup pattern from `intelligence/github-collector.js`" — but it does not actually reuse it.

### 6.3 Two Incompatible Health Score Algorithms

Stage 8 (`src/pipeline/stages/08-health.js`) calculates health using a 5-factor weighted formula:

```
presence * 0.30 + quality * 0.25 + freshness * 0.20 + structure * 0.15 + crossRefs * 0.10
```

`src/portal/github-client.js` calculates a separate health score based on git activity (commit frequency, contributor count, PR merge rate). These two scores are not reconciled and are presented independently in the portal, creating potential for contradictory signals about the same repo.

### 6.4 runFull() Only Runs 10 of 13 Curation Stages

The `runFull()` function in `src/pipeline/index.js` declares `const totalStages = 10` and the help text reads `"Run complete pipeline (all 10 stages)"`. Stages 11 (generate), 12 (validate), and 13 (claudemd) are the most operationally valuable stages for the org-curation use case — they generate missing files and curate `CLAUDE.md` — but they are excluded from the default run.

The org-discovery flow calls `runPipeline('full', ...)` which invokes `runFull()`, meaning the daily scheduled run never executes stages 11-13 unless triggered by explicit command.

### 6.5 Config Fragmentation Across Three Files with Divergent Repo Lists

```
squeegee.config.json                → single self-entry (Squeegee repo only)
config/intelligence.config.json     → 27 repos
config/portal.config.json           → 15 repos
```

There is no single source of truth for the org's repo list. The three files must be manually kept in sync. The intelligence config and portal config have already diverged (27 vs. 15 repos).

### 6.6 Stage 7 (Pattern Library) Disabled in Primary Use Case

`org-discovery.js` builds `prebuiltConfig` with `patternLibrary: { enabled: false }` (line 125). Stage 7 exits immediately when this flag is false. The pattern library was designed as a cross-project analysis, but the per-repo isolation model of org discovery makes cross-project pattern detection architecturally impossible without a post-processing aggregation step.

### 6.7 No Webhook HMAC Signature Verification

`src/server.js` processes GitHub push events without verifying the `X-Hub-Signature-256` header. Any request to `/api/webhook` that includes a `x-github-event: push` header and a valid JSON body with a `repository.name` field will trigger a pipeline run. OIDC protection on the endpoint mitigates this but does not eliminate the risk from misconfigured clients or internal services.

### 6.8 PAT Visible in /proc/PID/cmdline During Clone

`org-discovery.js` uses `spawnSync('git', ['clone', ..., authUrl, dest])` with `stdio: 'pipe'` to prevent PAT from appearing in log streams. However, the authenticated URL (`https://x-access-token:{PAT}@github.com/...`) is passed as a command argument. On Linux, process arguments are readable via `/proc/{PID}/cmdline` for the duration of the clone, which may be up to 5 minutes per the configured timeout.

The comment acknowledges piped stdio but does not address the `/proc` exposure.

### 6.9 State File Lost on Cold Starts

`/tmp/squeegee-state.json` stores the last 10 run summaries for the `/api/status` endpoint. Cloud Run scales to zero between runs and `/tmp` is not persistent. After a cold start, the status endpoint returns `{ runs: [], message: 'No runs recorded yet' }` even if dozens of successful runs occurred previously. There is no GCS backup of run history.

### 6.10 Three Different PAT Retrieval Patterns

```javascript
// Pattern 1: org-discovery.js — volume-mounted secret with env fallback
function getPAT() {
  try { return fs.readFileSync('/secrets/github-pat-glassbox', 'utf-8').trim(); }
  catch { return process.env.GITHUB_PAT || null; }
}

// Pattern 2: portal/21-portal-collect.js — env var, may be file path
const token = process.env.GITHUB_PAT || process.env.GITHUB_TOKEN;
if (token.startsWith('/') && token.length < 200) { /* read file */ }

// Pattern 3: intelligence/github-collector.js — env var only
const githubToken = process.env.GITHUB_TOKEN || config.github_token;
```

The three patterns have different fallback chains, different env var names (`GITHUB_PAT` vs. `GITHUB_TOKEN`), and different secret-as-file detection logic. In production, only Pattern 1 (volume-mounted secret) is reliably populated by Cloud Run.

---

## 7. Code Metrics

### LOC by Subsystem

| Category | LOC (approx) | % of Total |
|----------|-------------|------------|
| Intelligence modules (`intelligence/`) | ~4,200 | 21.6% |
| Portal modules (`src/portal/`) | ~2,800 | 14.4% |
| Curation stages 1-13 (`src/pipeline/stages/`) | ~2,900 | 14.9% |
| Intelligence stages 14-20 (`src/pipeline/stages/14-20`) | ~700 | 3.6% |
| Portal stages 21-23 (`src/pipeline/stages/21-23`) | ~420 | 2.2% |
| Pipeline infrastructure (`src/pipeline/analyzers`, formatters) | ~1,044 | 5.4% |
| Server + API (`src/server.js`, `src/api/`, `src/github/`) | ~1,444 | 7.4% |
| Shared utilities | ~716 | 3.7% |
| Templates (`src/portal/templates/`) | ~3,400 | 17.5% |
| Scripts | ~310 | 1.6% |
| Config files | ~200 | 1.0% |
| Static JS assets (`src/portal/static/js/`) | ~1,270 | 6.5% |
| **Total** | **~19,400** | **100%** |

### Complexity Concentration

The five largest files account for approximately 21% of all JavaScript source:

| File | LOC (approx) | Role |
|------|-------------|------|
| `src/api/intelligence.js` | ~648 | Intelligence HTTP API routes |
| `src/github/org-discovery.js` | ~374 | Org pipeline orchestration |
| `intelligence/github-collector.js` | ~344 | GitHub activity collection |
| `intelligence/gemini-synthesizer.js` | ~340 | Gemini briefing generation |
| `src/portal/github-client.js` | ~320 | Portal GitHub data collection |

### Test-to-Code Ratio

| Subsystem | Source LOC | Test LOC | Ratio |
|-----------|-----------|----------|-------|
| Intelligence modules | ~4,200 | ~2,800 | 0.67:1 |
| Portal modules | ~2,800 | ~730 | 0.26:1 |
| Curation stages | ~2,900 | ~280 | 0.10:1 |
| Server + API | ~1,444 | ~450 | 0.31:1 |
| **Overall** | **~19,400** | **~10,200** | **0.53:1** |

The intelligence subsystem has the highest test coverage by ratio. The curation pipeline (stages 1-13) has the lowest — most curation testing is exercised through integration and e2e tests rather than unit tests.

---

## 8. Test Suite Analysis

### Overview

| Metric | Value |
|--------|-------|
| Test files | 30 |
| Total tests | 469 |
| Test LOC | ~10,200 |
| Execution time | ~26 seconds |
| Failing tests | 0 |
| Skipped tests | 0 |

### File Distribution by Category

| Category | Files | Tests (approx) |
|----------|-------|----------------|
| Intelligence unit tests (`tests/intelligence/`) | 10 | ~230 |
| Portal unit tests (`tests/portal/`) | 7 | ~140 |
| API tests (`tests/api/`, `tests/integration/`) | 3 | ~50 |
| Stage-level tests (`tests/stages/`) | 1 | ~25 |
| End-to-end tests (`tests/e2e/`) | 3 | ~24 |
| Helpers and fixtures | 2 | — |

### Mock Infrastructure

The test suite uses 45 `jest.mock()` declarations across 7 service categories:

| Service Category | Mocked In |
|-----------------|-----------|
| `@octokit/rest` + plugins | intelligence tests, portal tests |
| `@google/generative-ai` | gemini-synthesizer, diagram-generator, explanation-generator tests |
| `@google-cloud/logging` | gcp-collector tests |
| `@google-cloud/storage` | station-collector tests |
| `fs` (promises) | multiple modules |
| `node-fetch` / `fetch` | org-discovery, webhook tests |
| Internal modules | cross-module boundary isolation |

### Coverage Gaps

- **Portal templates:** The 17 Nunjucks HTML templates have no dedicated rendering tests. The `renderer.test.js` tests the renderer module but not individual template output.
- **Curation stage unit tests:** Stages 1-13 are tested through integration tests (`tests/e2e/pipeline-full.test.js`) rather than isolated unit tests. A failure in stage 3 requires running stages 1-2 first to reproduce.
- **Load testing:** No tests validate behavior under concurrent API calls or with the maximum expected number of repos (15+).
- **Webhook signature path:** The HMAC verification gap (see Section 6.7) has no corresponding test for rejection of unsigned requests.

---

## 9. Security Assessment

### Strengths

| Control | Implementation |
|---------|---------------|
| PAT from Secret Manager | Volume-mounted at `/secrets/github-pat-glassbox`, auto-refreshed by Cloud Run |
| Piped stdio on clone/push | `spawnSync('git', [...], { stdio: 'pipe' })` prevents PAT in log streams |
| PAT redaction in error messages | `errMsg.replace(pat, '[REDACTED]')` before throwing |
| Non-root container | Dockerfile uses Alpine with a non-root user |
| Container scanning | Trivy scanning in `deploy.yml` workflow |
| OIDC authentication | All endpoints except `/health` require Cloud Run OIDC tokens |
| Loop prevention | Auto-curate branches and `[squeegee-auto]` commits filtered at webhook handler |
| Graceful shutdown | SIGTERM handler ensures 8-second grace period before process exit |

### Concerns

| Concern | Severity | Location |
|---------|----------|----------|
| No webhook HMAC verification | Medium | `src/server.js` line 110 |
| PAT in `/proc/PID/cmdline` during clone | Low-Medium | `org-discovery.js` line 149 |
| No per-endpoint authorization | Low | All OIDC endpoints share same auth level |
| Inconsistent PAT retrieval | Low | 3 different patterns across codebase |
| `/tmp` state file ephemeral | Low | Run history lost on cold start |
| `intelligence.config.json` loaded on every API call | Low | `loadIntelligenceConfig()` no caching |

The HMAC verification gap is the most actionable — GitHub provides the `X-Hub-Signature-256` header on all webhook payloads, and verifying it takes approximately 10 lines of Node.js crypto code. The PAT-in-cmdline risk is mitigated by the short clone window and Cloud Run's isolated container execution environment, but it should be addressed using a git credential helper or `GIT_ASKPASS` instead of URL embedding.

---

## 10. Scalability Analysis

### Current Scale (15 repos, tested)

A full org run at 15 repos takes approximately 30 minutes end-to-end on Cloud Run (900s timeout allows this). Each repo requires:
- Clone: 10-30 seconds
- Pipeline stages 1-10: 5-15 seconds
- PR creation (if changes): 5-10 seconds
- Cleanup: 1-2 seconds

This is comfortably within the 900s timeout at 15 repos.

### At 100 Repos (projected bottleneck)

| Bottleneck | Estimate | Mitigation Required |
|-----------|----------|---------------------|
| Cloud Run timeout | ~500-700 min required vs. 15 min allowed | Fan-out with parallel workers or queue |
| Sequential repo processing | No parallelism in main loop | Parallelism with concurrency limit |
| GitHub REST rate limits | 100 repos × clone + API calls = approaching 5000/hr | Octokit throttling helps; may need delay |
| `/tmp` disk space | 100 shallow clones × ~50MB = 5GB peak | Sequential cleanup as currently done helps |

### At 500 Repos (would require re-architecture)

At 500 repos, Squeegee requires a fundamentally different execution model:

1. **Fan-out:** Distribute repos across multiple Cloud Run job instances rather than one service instance.
2. **Config auto-discovery:** Eliminate manually maintained `portal.config.json` and `intelligence.config.json` repo lists; fetch them from the GitHub API at runtime.
3. **Auto-merge PRs:** At 500 repos, human review of Squeegee PRs is impractical. Auto-merge with branch protection rules would be required.
4. **Persistent state:** Move run history from `/tmp/squeegee-state.json` to Firestore or GCS for durability across cold starts.
5. **GitHub App:** Replace PAT with a GitHub App installation token for higher rate limits (5,000/hr per installation vs. 5,000/hr per user).

---

## 11. Cross-Subsystem Redundancy

The following implementations are duplicated across subsystems:

### GitHub API Client

Three files each implement `createOctokit(token)` with identical plugin configuration:

- `intelligence/github-collector.js` (lines 17-49)
- `intelligence/claude-md-auditor.js` (lines 16-30)
- `intelligence/log-writer.js` (lines 27-52)
- `src/portal/github-client.js` (lines 29-48)

### Health Score Calculation

- `src/pipeline/stages/08-health.js` — 5-factor doc-quality score (presence, content quality, freshness, structure, cross-references)
- `src/portal/github-client.js` — git activity score (commit frequency, contributor count, PR merge rate)

### Date Formatting

- `intelligence/utils.js` — `formatDate(date)` returning `YYYY-MM-DD`
- `src/pipeline/formatters/markdown.js` — `timestamp()` returning locale string
- `src/portal/renderer.js` — inline date formatting with `toLocaleDateString()`

### Config Loading

- `src/pipeline/config.js` — `loadConfig(workspace)` with module-level cache
- `src/api/intelligence.js` — `loadIntelligenceConfig()` reading from disk on every call (no cache)
- `src/pipeline/stages/21-portal-collect.js` — `loadPortalConfig()` reading from disk
- `src/api/portal.js` — `loadPortalConfig()` reading from disk (duplicate of stage 21's version)

### Safe File Read

- `src/pipeline/utils.js` — `readFileSafe(filePath, fallback)` and `readJsonSafe(filePath, fallback)`
- `src/portal/ai-cache.js` — inline try/catch on `fs.readFile` returning `{}` on failure
- `src/portal/project-cache.js` — inline try/catch on `fs.readFile`

---

## 12. Missing Abstractions

The following abstractions would reduce duplication and improve maintainability:

| Missing Abstraction | What It Would Replace | Estimated Effort |
|--------------------|----------------------|-----------------|
| **Unified GitHub service** (`src/lib/github.js`) | 4 independent Octokit client implementations | 2 days |
| **Stage result type** (`{ status, summary, data, error }`) | Ad-hoc return objects from each stage | 1 day |
| **Pipeline runner class** | `runFull()` + `runPortal()` + `runStage()` in `intelligence.js` | 2 days |
| **Config registry** (single repo source of truth) | 3 config files with divergent repo lists | 2 days |
| **Health score interface** | 2 incompatible scoring algorithms | 1 day |
| **Persistent state layer** (GCS-backed) | Ephemeral `/tmp/*.json` state files | 3 days |
| **Secret resolver** (`resolveSecret(envVar)`) | 3 PAT retrieval patterns | 0.5 days |

---

## 13. Recommendations (Top 10)

Ordered by effort-to-value ratio (highest value first within comparable effort):

### Priority 1: Wire Stages 18-20 (1 day, high value)

The modules exist and are tested. The only work required is removing the `TODO` stubs and uncommenting three `require()` calls in `src/api/intelligence.js` (lines 27-29). This completes the daily intelligence pipeline and enables Slack notifications as scheduled in `intelligence.config.json`.

**Files:** `src/pipeline/stages/18-intelligence-audit-quality.js`, `stages/19-intelligence-research.js`, `stages/20-intelligence-notify.js`, `src/api/intelligence.js`

### Priority 2: Fix runFull() to Include Stages 11-13 (0.5 day, high value)

Add stages 11-13 to `runFull()` in `src/pipeline/index.js`. Update `totalStages` from 10 to 13. Update the help text. This makes the daily org curation run complete — generating missing docs, validating quality, and curating `CLAUDE.md` files.

**File:** `src/pipeline/index.js` (lines 150-298)

### Priority 3: Add Webhook HMAC Verification (0.5 day, high value, low effort)

Add X-Hub-Signature-256 verification to `/api/webhook` using Node.js `crypto.timingSafeEqual`. The webhook secret should be stored in Secret Manager and volume-mounted similarly to the GitHub PAT.

**File:** `src/server.js` (lines 110-167)

### Priority 4: Extract Shared GitHub Service (2 days, high value)

Create `src/lib/github.js` that exports `createOctokit(token)` with shared retry/throttling configuration. Update the four files that currently duplicate this setup.

**Files to update:** `intelligence/github-collector.js`, `intelligence/claude-md-auditor.js`, `intelligence/log-writer.js`, `src/portal/github-client.js`

### Priority 5: Extract Secret Resolver (0.5 day, medium value)

Create `src/lib/secrets.js` that implements the volume-mount-with-env-fallback pattern once. Standardize all three PAT retrieval patterns to use it.

**Files to update:** `src/github/org-discovery.js`, `src/pipeline/stages/21-portal-collect.js`, `intelligence/github-collector.js`

### Priority 6: Unify Health Scoring (1 day, medium value)

Define a common `HealthScore` interface. Have stage 8 write its scores to a shared location (e.g., GCS or a run artifact). Have `portal/github-client.js` incorporate stage 8's scores rather than computing a parallel score.

**Files:** `src/pipeline/stages/08-health.js`, `src/portal/github-client.js`

### Priority 7: Memoize Intelligence Config Loading (0.5 day, medium value)

Add a module-level cache to `loadIntelligenceConfig()` in `src/api/intelligence.js`, matching the pattern already used by `src/pipeline/config.js`. This prevents redundant disk reads on every API call.

**File:** `src/api/intelligence.js` (lines 39-87)

### Priority 8: Consolidate Config with Single Repo Registry (2 days, medium value)

Create a unified `config/repos.yaml` that is the single source of truth for all repos in the org. Generate `intelligence.config.json` and `portal.config.json` from it, or load from it directly. Eliminates the 27 vs. 15 repo divergence.

**Files:** All three config files + their loaders

### Priority 9: Solve Stage 7 via Post-Processing Aggregation (2 days, medium value)

Stage 7 needs cross-project data that is architecturally unavailable in per-repo isolation mode. Solution: run stages 1-6 across all repos (current behavior), then run a separate aggregation step that reads all generated outputs and produces the pattern library. This aggregation could run as a new stage 7 in a second pass after all repos are processed.

**Files:** `src/pipeline/stages/07-patterns.js`, `src/github/org-discovery.js`

### Priority 10: Add Structured Observability (3 days, medium value)

Add Cloud Logging structured log entries at key pipeline events (repo start/end, stage transitions, PR creation). Currently all logging is `console.log/error` which goes to Cloud Logging as unstructured text. Structured logs would enable Cloud Monitoring dashboards and alerting on pipeline health.

**Files:** `src/pipeline/utils.js` (log function), `src/github/org-discovery.js`

---

## 14. Dependency Map

### Production Dependencies

| Package | Version | Used By |
|---------|---------|---------|
| `fastify` | ^5.7.4 | `src/server.js` — HTTP server |
| `@octokit/rest` | ^20.0.0 | intelligence/github-collector, claude-md-auditor, log-writer, portal/github-client |
| `@octokit/plugin-retry` | ^6.0.0 | Same four Octokit clients |
| `@octokit/plugin-throttling` | ^8.0.0 | Same four Octokit clients |
| `@google-cloud/logging` | ^11.0.0 | `intelligence/gcp-collector.js` |
| `@google-cloud/storage` | ^7.0.0 | `intelligence/station-collector.js`, `src/portal/gcs-uploader.js` |
| `@google/generative-ai` | ^0.21.0 | `intelligence/gemini-synthesizer.js`, `src/portal/diagram-generator.js`, `src/portal/explanation-generator.js` |
| `nunjucks` | ^3.2.4 | `src/portal/renderer.js` |
| `js-yaml` | ^4.1.0 | `src/portal/metadata-reader.js` |

### Development Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `jest` | ^29.7.0 | Test runner for all 469 tests |

### Runtime Requirements

| Requirement | Value | Source |
|-------------|-------|--------|
| Node.js | >=20 | `package.json` engines field |
| Git | Any recent | `spawnSync('git', ...)` in org-discovery |
| Platform | Linux (Cloud Run) | `/tmp` paths, `/proc`, `/secrets` mounts |

### External Service Dependencies

| Service | Used By | Auth Method |
|---------|---------|-------------|
| GitHub REST API v3 | github-collector, claude-md-auditor, log-writer, portal/github-client, org-discovery | PAT from Secret Manager |
| GCP Cloud Logging | gcp-collector | Service account (GOOGLE_APPLICATION_CREDENTIALS) |
| GCP Cloud Storage | station-collector, gcs-uploader | Service account |
| Gemini API (Google AI) | gemini-synthesizer, diagram-generator, explanation-generator | API key from Secret Manager |
| Linear API | portal/linear-client | Linear API key (env var) |
| Slack Webhooks | slack-notifier (stub) | Webhook URL from Secret Manager |
| GCP Secret Manager | Cloud Run volume mounts | Service account (`squeegee-runner@glassbox-squeegee`) |

---

*Generated by Squeegee Architecture Analysis — 2026-03-09*
