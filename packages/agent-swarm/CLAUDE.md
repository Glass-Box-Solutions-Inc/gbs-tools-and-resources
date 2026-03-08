# Agent Swarm

**DAG-based multi-agent task orchestration — reference copy from Glassy PAI.**

---

## Project Overview

| Field | Value |
|-------|-------|
| Status | Reference Copy |
| Source | `glassy-app-production` → `backend/src/modules/agent-swarm/` |
| Stack | NestJS 11, TypeScript, Socket.io, Prisma |
| Auth | BetterAuth session tokens |

> **This is NOT a standalone deployable package.** It is a reference copy of the agent-swarm module from the Glassy PAI production monorepo, extracted here for discoverability and cross-team reference. The canonical source remains `glassy-app-production`.

---

## Architecture

```
SwarmController (/api/swarm)
├── TaskManagerService → Prisma (AgentTask, AgentExecution)
├── SwarmService
│   ├── TaskManagerService
│   ├── AgentCoordinatorService
│   └── SwarmGateway (Socket.io /swarm namespace)
└── AgentCoordinatorService
```

### Key Patterns
- **DAG execution**: Tasks have `blockedBy`/`blocks` relationships; DFS cycle detection
- **Greedy assignment**: IDLE agents claim available tasks in priority order
- **File scope isolation**: Each agent role has restricted file patterns
- **In-memory agent registry**: Fast state access, lost on restart

---

## Dependencies (NestJS)

```typescript
// Required NestJS modules
@nestjs/common, @nestjs/websockets, @nestjs/platform-socket.io
// Required Prisma models
AgentTask, AgentExecution, Session, User
// Required packages
class-validator, class-transformer, socket.io
```

### Prisma Models Required

```prisma
model AgentTask {
  id          String   @id @default(cuid())
  userId      String
  title       String
  description String
  status      String   // PENDING | IN_PROGRESS | COMPLETED | FAILED | BLOCKED
  assignee    String?
  priority    Int      @default(0)
  blockedBy   String[]
  blocks      String[]
  createdAt   DateTime @default(now())
  completedAt DateTime?
  executions  AgentExecution[]
}

model AgentExecution {
  id          String    @id @default(cuid())
  taskId      String?
  task        AgentTask? @relation(...)
  agentRole   String
  status      String    // RUNNING | SUCCESS | FAILED | TIMEOUT
  output      Json?
  error       String?
  startedAt   DateTime  @default(now())
  completedAt DateTime?
}
```

---

## File Map

| File | Purpose |
|------|---------|
| `src/agent-swarm.module.ts` | NestJS module definition |
| `src/agent-swarm.types.ts` | Shared enums (AgentRole, TaskStatus) and interfaces |
| `src/task-manager.service.ts` | Task CRUD, dependency management, DAG validation |
| `src/agent-coordinator.service.ts` | Agent spawning, assignment, file conflict detection |
| `src/swarm.service.ts` | High-level orchestration and progress |
| `src/swarm.controller.ts` | REST API endpoints under `/api/swarm` |
| `src/swarm.gateway.ts` | WebSocket gateway (namespace: `/swarm`) |
| `src/dto/swarm.dto.ts` | Request DTOs with class-validator |

---

## Agent Roles

| Role | File Scope | Purpose |
|------|-----------|---------|
| Frontend | `frontend/**` | UI components and pages |
| Backend | `backend/src/**` | API services and modules |
| Tests | `backend/test/**`, `frontend/e2e/**` | Test suites |
| Security | `docs/compliance/**`, `backend/src/common/guards/**` | Security audits |
| DevOps | `.github/**`, `infra/**` | CI/CD and infrastructure |
| Docs | `docs/**` | Documentation |
| Design | `frontend/app/components/**` | UI/UX design |
| Research | _(unrestricted)_ | Research and analysis |

---

## Known Limitations

1. **In-memory agent registry** — agents lost on server restart; no persistence layer
2. **No task pagination** — unbounded query on task lists
3. **Greedy assignment only** — no intelligent scheduling or load balancing
4. **File conflict detection is advisory** — warns but doesn't block
5. **swarmId ownership** — format validation only, no full user ownership check

---

## Related Documentation

- Source repo: `glassy-app-production` (`backend/src/modules/agent-swarm/`)
- Glassy PAI docs: `adjudica-documentation/projects/glassy-pai/features/agent-swarm.md`
- Glassy architecture: `adjudica-documentation/projects/glassy/ARCHITECTURE_OVERVIEW.md`

---

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
