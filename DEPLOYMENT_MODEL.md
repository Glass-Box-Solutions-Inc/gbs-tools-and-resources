# Deployment Model

> **This monorepo is the canonical source for all 4 agent packages.** Spectacles and merus-expert deploy to Cloud Run from this repo. Agent-swarm is an installable NestJS library. Agentic-debugger is adopted by copying its script and workflow into target repos.

---

## Per-Package Deployment

| Package | Deploy Method | Canonical Source |
|---------|--------------|------------------|
| **spectacles** | Cloud Build trigger → Cloud Run | This monorepo (`packages/spectacles/`) |
| **merus-expert** | Cloud Build trigger → Cloud Run | This monorepo (`packages/merus-expert/`) |
| **agent-swarm** | `npm install @gbs/agent-swarm` | This monorepo (`packages/agent-swarm/`) |
| **agentic-debugger** | Copy script + workflow + config into target repo | This monorepo (`packages/agentic-debugger/`) |
| **hindsight** | Docker / local | This monorepo (`packages/hindsight/`) |
| **mcp-servers** | Per-server (MCP protocol) | This monorepo (`packages/mcp-servers/`) |
| **phileas** | Maven JAR | This monorepo (`packages/phileas/`) |
| **yevrah_terminal** | pip install (CLI) | This monorepo (`packages/yevrah_terminal/`) |
| **merus-test-data-generator** | pip install (CLI) | This monorepo (`packages/merus-test-data-generator/`) |

---

## Cloud Run Services

### spectacles

- **Service:** `glassbox-spectacles`
- **Cloud Build trigger:** Points to `gbs-tools-and-resources` repo, `dir: packages/spectacles/`
- **Build:** `packages/spectacles/cloudbuild.yaml` (Docker → Artifact Registry → Cloud Run)
- **Secrets:** GCP Secret Manager (`spectacles-*` secrets)

### merus-expert

- **Service:** `merus-expert`
- **Cloud Build trigger:** Points to `gbs-tools-and-resources` repo, `dir: packages/merus-expert/`
- **Build:** `packages/merus-expert/cloudbuild.yaml` (Docker → Artifact Registry → Cloud Run)
- **Port:** 8000
- **Secrets:** GCP Secret Manager (`merus-expert-*` secrets)

---

## NestJS Library: agent-swarm

Agent-swarm is a standalone NestJS library module, not a deployed service. Host applications install it and import the module:

```typescript
// Standalone mode — uses built-in PrismaService
import { AgentSwarmModule } from '@gbs/agent-swarm';

// Hosted mode — inject host app's PrismaService
AgentSwarmModule.forRoot({ prismaService: HostPrismaService })
```

**Relationship to Glassy:** The agent-swarm module embedded in `glassy-app-production` remains canonical for Glassy PAI and continues to evolve independently. This standalone package is a separate GBS resource, forked from Glassy and decoupled from all Glassy dependencies (BetterAuth, Glassy Prisma schema, etc.).

---

## CI Debugging Agent: agentic-debugger

Agentic-debugger is adopted by copying files into the target repo:

```bash
cp packages/agentic-debugger/workflows/agentic-debugger.yml .github/workflows/
cp packages/agentic-debugger/scripts/debug-agent.mjs scripts/
cp packages/agentic-debugger/.agentic-debugger.json .
```

Configuration is project-specific via `.agentic-debugger.json`. A Glassy-specific workflow example is at `packages/agentic-debugger/workflows/examples/agentic-debugger.glassy.yml`.

**Relationship to Glassy:** The debug-agent script and workflow in `glassy-app-production` remain canonical for Glassy PAI. This standalone package is a generalized GBS resource for use in any repo.

---

## Scheduled Jobs / Cron

| Job | Package | Where Configured | Schedule |
|-----|---------|-----------------|----------|
| Daily curator run | spectacles | APScheduler in deployed app | Daily 7am UTC |
| CLAUDE.md audit | spectacles | APScheduler in deployed app | Weekly (Sunday 7am UTC) |
| Doc quality audit | spectacles | APScheduler in deployed app | Monthly (1st, 7am UTC) |
| CI failure debug | agentic-debugger | GitHub Actions in target repo | Event-driven |

---

## Secrets & Environment Variables

| Package | Secrets Location |
|---------|-----------------|
| **spectacles** | GCP Secret Manager (`glassbox-spectacles` project) |
| **merus-expert** | GCP Secret Manager (production) / `.env` (local, gitignored) |
| **agent-swarm** | Host app provides (standalone: own `.env`) |
| **agentic-debugger** | GitHub Secrets in target repo (`ANTHROPIC_API_KEY`, optionally `LINEAR_API_KEY`) |

Each package includes a `.env.example` file documenting required variables. Actual secrets are managed through:

- **GCP Secret Manager** — Production credentials for Cloud Run services
- **GitHub Secrets** — CI/CD workflow credentials
- **Local `.env` files** — Development credentials (gitignored, never committed)

**No secrets are committed to this monorepo.**

---

## GCP Infrastructure Notes

After the Phase 3 canonical transfer (2026-03-08):

1. **Spectacles Cloud Build trigger** → updated to point at `gbs-tools-and-resources` repo, `dir: packages/spectacles/`
2. **Merus-expert Cloud Build trigger** → created, pointing at `gbs-tools-and-resources` repo, `dir: packages/merus-expert/`
3. **Standalone repos** (`Glass-Box-Solutions-Inc/Spectacles`, `Glass-Box-Solutions-Inc/merus-expert`) → archived on GitHub

---

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
