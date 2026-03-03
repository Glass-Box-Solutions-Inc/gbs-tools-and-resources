# Claude Code Specialized Agents

> **Curated collection of specialized Claude Code agent definitions** — domain-specific AI teammates for health tech, legaltech, infrastructure, and billing systems.

These agents are designed for use with [Claude Code](https://docs.anthropic.com/en/docs/claude-code) as specialized subagents. Each agent file contains deep domain knowledge, code patterns, anti-patterns, and configuration templates that enable Claude to act as a domain expert for specific tasks.

---

## Agent Catalog

| Agent | File | Domain | Primary Use Case |
|-------|------|--------|-----------------|
| **Event Sourcing Specialist** | [`event-sourcing-specialist.md`](agents/event-sourcing-specialist.md) | Health Data / CQRS | Append-only event stores, temporal queries, snapshot strategies with PostgreSQL/Prisma |
| **Health Platform Specialist** | [`health-platform-specialist.md`](agents/health-platform-specialist.md) | Wearable Integrations | OAuth 2.0 flows, webhook ingestion, and data normalization for Oura, Fitbit, Whoop, Withings |
| **Health Visualization Specialist** | [`health-viz-specialist.md`](agents/health-viz-specialist.md) | Dashboard UI | React + TypeScript chart components for sleep, HR, HRV, recovery, and comparative health views |
| **HIPAA GCP Specialist** | [`hipaa-gcp-specialist.md`](agents/hipaa-gcp-specialist.md) | Cloud Infrastructure | HIPAA-compliant architecture on GCP — CMEK, pgAudit, VPC Service Controls, Cloud Armor |
| **Legaltech Web Design Specialist** | [`legaltech-web-design-specialist.md`](agents/legaltech-web-design-specialist.md) | Legaltech UX/UI | B2B web design for CA Workers' Compensation — brand alignment, evidence-first layouts, compliance messaging |
| **Notification Specialist** | [`notification-specialist.md`](agents/notification-specialist.md) | Multi-Channel Messaging | Telegram, SendGrid, Twilio notification pipelines with HIPAA-safe PHI handling via GCP Pub/Sub |
| **Stripe Billing Specialist** | [`stripe-specialist.md`](agents/stripe-specialist.md) | SaaS Billing | Stripe subscription lifecycle, webhook processing, tier enforcement, founding user programs |

---

## How to Use

### 1. Copy to your project's `.claude/agents/` directory

```bash
# Copy a specific agent
cp packages/claude-code-agents/agents/hipaa-gcp-specialist.md /path/to/your/project/.claude/agents/

# Copy all agents
cp packages/claude-code-agents/agents/*.md /path/to/your/project/.claude/agents/
```

### 2. Reference in Claude Code

Claude Code automatically discovers agents in `.claude/agents/`. Once copied, you can reference them in conversations:

- **Direct invocation:** "Use the HIPAA GCP Specialist to review our Cloud SQL configuration"
- **Plan mode:** During planning, Claude will discover available agents and assign them to tasks
- **Subagent spawning:** Agents can be spawned as specialized teammates in Agent Teams

### 3. Register in SUBAGENT_GUIDE.md (recommended)

For discoverability, add each agent to your project's `SUBAGENT_GUIDE.md`:

```markdown
| Agent | File | When to Use |
|-------|------|-------------|
| HIPAA GCP Specialist | `hipaa-gcp-specialist.md` | GCP infrastructure involving PHI |
```

---

## Agent Structure

Each agent file follows a consistent structure:

1. **Role** — One-paragraph description of the agent's expertise
2. **Core Principles / Domain Understanding** — Key concepts the agent internalizes
3. **Detailed Guides** — Code examples, schemas, configuration templates
4. **Anti-Patterns** — Common mistakes to avoid
5. **Operating Rules** — How the agent should behave when invoked
6. **Example Tasks** — Sample prompts that demonstrate good usage

---

## Agent Categories

### Health & Wellness Platform
- **Event Sourcing Specialist** — Data architecture (append-only stores, CQRS)
- **Health Platform Specialist** — External API integrations (OAuth, webhooks)
- **Health Visualization Specialist** — Frontend chart components
- **Notification Specialist** — Alert delivery across channels

### Infrastructure & Compliance
- **HIPAA GCP Specialist** — Cloud security and PHI handling
- **Stripe Billing Specialist** — SaaS monetization

### Legaltech
- **Legaltech Web Design Specialist** — Marketing and product web surfaces for CA Workers' Compensation

---

## Tech Stack Coverage

| Technology | Agents That Cover It |
|-----------|---------------------|
| **Fastify + TypeScript** | Event Sourcing, Health Platform, Notification, Stripe |
| **Prisma + PostgreSQL** | Event Sourcing, HIPAA GCP |
| **React + TypeScript** | Health Visualization, Legaltech Web Design |
| **GCP (Cloud SQL, KMS, Pub/Sub)** | HIPAA GCP, Notification |
| **Stripe API** | Stripe Billing |
| **OAuth 2.0** | Health Platform |
| **Next.js / Tailwind CSS** | Legaltech Web Design |

---

## Contributing

To add a new agent:

1. Create a `.md` file in `agents/` following the structure above
2. Add an entry to the catalog table in this README
3. Test the agent by copying it to a project's `.claude/agents/` and invoking it on a relevant task

---

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
