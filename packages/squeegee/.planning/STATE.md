# Squeegee - Project State

**Last Updated:** 2026-03-09
**Status:** Active Development
**Current Phase:** Portal build-out + CI/CD hardening

---

## Current Focus

23-stage pipeline (stages 1-13 curation, 14-20 intelligence, 21-23 portal) fully scaffolded. Portal modules and templates complete. CI/CD pipeline hardened with test gates, health checks, rollback, and vulnerability scanning.

---

## Progress

### Completed
- 13-stage curation pipeline (stages 1-13)
- 7-stage intelligence pipeline (stages 14-20): GitHub/GCP/station collectors, Gemini synthesis, log writing, CLAUDE.md audit, Slack notifications
- Intelligence API endpoints (8 routes) with Fastify plugin pattern
- Portal pipeline (stages 21-23): collect, AI content generation, Nunjucks template rendering
- Portal modules (10): data-collector, ai-content-generator, template-renderer, gcs-uploader, config-loader, metadata-builder, nav-builder, search-indexer, sitemap-generator, asset-manager
- Portal templates (17 pages): index, project detail, changelog, health dashboard, practices, patterns, team, search, compare, timeline, about, 404, header/footer/base layouts
- Portal API routes and pipeline stage registration
- Config: `portal.config.json` (15 repos), `intelligence.config.json` (schedules)
- CI/CD hardening: test gate in deploy, post-deploy health check, automatic rollback, Trivy container scanning, production environment approval gate
- Fixed all 5 broken test suites (github-collector, gcp-collector, station-monitor, api/intelligence)
- Added missing `writeAll` to log-writer.js and `auditAll` to claude-md-auditor.js
- Added Dockerfile HEALTHCHECK
- Converted integration tests from vitest to Jest
- Added Jest coverage thresholds (50% branches, 60% functions/lines/statements)

### In Progress
- Portal end-to-end testing
- Deploy workflow validation (pending push to main)

### Blocked
*None*

---

## Blockers

*No current blockers.*

---

## Key Decisions

- **CommonJS throughout** — project uses `require`/`module.exports`, not ESM
- **Nunjucks for templates** — Jinja2-like syntax, familiar from Python ecosystem
- **Gemini for AI content** — `@google/generative-ai` with flash model
- **GCS for portal hosting** — static site upload to Cloud Storage bucket
- **Trivy for container scanning** — blocks deploy on CRITICAL/HIGH vulnerabilities
- **Two-job deploy pipeline** — separate `test` job gates the `deploy` job with `environment: production`

---

## Recent Activity

<!-- SQUEEGEE:AUTO:START recent-activity -->
- `2026-03-09` Merge pull request #24 from Glass-Box-Solutions-Inc/squeegee/auto-curate-20260309-000923
- `2026-03-09` **fix:** use revision status check instead of HTTP health check
- `2026-03-09` **fix:** use service account impersonation for health check token
- `2026-03-09` **fix:** upgrade Alpine packages to patch zlib CVE-2026-22184
- `2026-03-09` **chore:** auto-curate documentation
<!-- SQUEEGEE:AUTO:END recent-activity -->

---

## Architecture

```
Pipeline: 23 stages
  Curation (1-13):  scan -> analyze -> curate -> generate -> validate -> claudemd
  Intelligence (14-20): collect -> synthesize -> write -> audit-claude -> audit-quality -> research -> notify
  Portal (21-23): portal-collect -> portal-ai -> portal-render
```

---

## Quick Links

- [ROADMAP.md](ROADMAP.md) - Project roadmap
- [ISSUES.md](ISSUES.md) - Deferred work and issues
- [CLAUDE.md](../CLAUDE.md) - Project technical reference

---

*Managed by Squeegee Documentation System*
