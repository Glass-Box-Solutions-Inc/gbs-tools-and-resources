# Deployment Model

> **This monorepo is a discoverability and reference hub, not a deployment source.** Each deployable package continues to deploy from its original standalone repository.

---

## Why This Matters

When packages were consolidated into `gbs-tools-and-resources`, deploy files (Dockerfiles, `cloudbuild.yaml`, `docker-compose.yml`, workflow YAML) were copied faithfully to preserve context. However, **no Cloud Build triggers, GitHub Actions, or CI/CD pipelines point at this monorepo**. The deploy files here are inert snapshots — they document how each service is built and deployed, but deployment is triggered from the canonical source repos listed below.

---

## Per-Package Deployment Sources

| Package | Deploys From | Deploy Method | Deploy Files in Monorepo |
|---------|-------------|---------------|--------------------------|
| **spectacles** | [`Glass-Box-Solutions-Inc/Spectacles`](https://github.com/Glass-Box-Solutions-Inc/Spectacles) (standalone repo) | Cloud Build trigger → Cloud Run | Dockerfile, cloudbuild.yaml, .env.example, .dockerignore |
| **merus-expert** | [`Glass-Box-Solutions-Inc/merus-expert`](https://github.com/Glass-Box-Solutions-Inc/merus-expert) (standalone repo) | Manual `docker build` + `gcloud run deploy` | Dockerfile, docker-compose.yml, .env.example |
| **agent-swarm** | [`glassy-app-production`](https://github.com/Glass-Box-Solutions-Inc/glassy) (`backend/src/modules/agent-swarm/`) | Part of Glassy NestJS build | Source code only (no deploy files) |
| **agentic-debugger** | [`glassy-app-production`](https://github.com/Glass-Box-Solutions-Inc/glassy) (`.github/workflows/`) | GitHub Actions (triggered by CI failure) | debug-agent.mjs + workflow YAML |
| **hindsight** | This monorepo (canonical) | Local / Docker | Dockerfile, docker-compose.yml |
| **mcp-servers** | This monorepo (canonical) | Per-server (see individual READMEs) | Varies by server |
| **phileas** | This monorepo (canonical) | Maven (library JAR) | pom.xml |
| **yevrah_terminal** | This monorepo (canonical) | pip install (CLI tool) | pyproject.toml |
| **merus-test-data-generator** | This monorepo (canonical) | pip install (CLI tool) | pyproject.toml |

**Note:** The Phase 1 utility packages (hindsight, mcp-servers, phileas, yevrah_terminal, merus-test-data-generator) were fully migrated — their standalone repos are archived and this monorepo is their canonical source. The Phase 2 agent packages (spectacles, merus-expert, agent-swarm, agentic-debugger) maintain their standalone repos as the deployment source.

---

## Scheduled Jobs / Cron

| Job | Package | Where It's Configured | Schedule |
|-----|---------|----------------------|----------|
| Daily curator run | spectacles | APScheduler inside the Spectacles app code | Daily 7am UTC |
| CLAUDE.md audit | spectacles | APScheduler inside the app code | Weekly (Sunday 7am UTC) |
| Doc quality audit | spectacles | APScheduler inside the app code | Monthly (1st, 7am UTC) |
| CI failure debug | agentic-debugger | GitHub Actions in `glassy-app-production` | Event-driven (on CI failure) |

The scheduler code (APScheduler) was copied into this monorepo as part of the Spectacles source. However, **the running instance** uses the code deployed from the standalone Spectacles repo. Changes to scheduler config here will NOT affect production until the standalone repo is updated.

---

## Secrets & Environment Variables

| Package | Secrets Location | Affected by Monorepo Copy? |
|---------|-----------------|---------------------------|
| **spectacles** | GCP Secret Manager (`glassbox-spectacles` project) | No — secrets are in GCP, not in repo |
| **merus-expert** | `.env` file (local) / GCP Secret Manager (prod) | No — `.env` is gitignored, never copied |
| **agent-swarm** | Inherits from Glassy's env | N/A — reference copy |
| **agentic-debugger** | GitHub Secrets in Glassy repo | N/A — template copy |

Each package includes a `.env.example` file documenting required variables. Actual secrets are managed through:

- **GCP Secret Manager** — Production credentials for Cloud Run services
- **GitHub Secrets** — CI/CD workflow credentials
- **Local `.env` files** — Development credentials (gitignored, never committed)

**No secrets were copied into this monorepo.** The `.env.example` files are safe to commit — they contain placeholder values only.

---

## Deploying from This Monorepo (Future Consideration)

If the decision is made to deploy agent packages from this monorepo instead of standalone repos:

1. **Cloud Build triggers** would need to be created pointing at `packages/spectacles/` and `packages/merus-expert/` paths in this repo
2. **Build context** paths in `cloudbuild.yaml` would need updating to account for monorepo nesting
3. **The standalone repos** would become read-only archives (like the Phase 1 utility repos)
4. **GitHub Actions** for agentic-debugger would need to reference this repo's workflow path
5. **Spectacles' APScheduler** config would be live from this repo's copy

This is not currently planned. The standalone repos remain the deployment sources.

---

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
