# Agent Swarm

**DAG-based multi-agent task orchestration — standalone NestJS library module.**

---

## Project Overview

| Field | Value |
|-------|-------|
| Status | Standalone Package (canonical for GBS) |
| Package | `@gbs/agent-swarm` |
| Stack | NestJS 11, TypeScript, Socket.io, Prisma |
| Auth | Pluggable — standalone token or host-provided (e.g. BetterAuth) |

> This is a **standalone installable NestJS library module**, forked from Glassy PAI and decoupled from all Glassy dependencies. It includes its own Prisma schema, PrismaService, and auth decorator. Host applications can inject their own PrismaService via `AgentSwarmModule.forRoot({ prismaService })`.
>
> **Note:** The agent-swarm module within `glassy-app-production` remains canonical for Glassy PAI. This standalone package is a separate GBS resource.

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
- **Pluggable auth**: Standalone mode uses token-as-userId; hosted mode injects custom auth handler

---

## Dependencies

```typescript
// Peer dependencies (host app provides)
@nestjs/common, @nestjs/websockets, @nestjs/platform-socket.io
// Bundled dependencies
@prisma/client, class-validator, class-transformer, socket.io
```

### Prisma Models (standalone schema)

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
| `src/index.ts` | Barrel export for all public APIs |
| `src/prisma.service.ts` | Standalone PrismaService (extends PrismaClient) |
| `src/agent-swarm.module.ts` | NestJS module with `forRoot()` for hosted mode |
| `src/agent-swarm.types.ts` | Shared enums (AgentRole, TaskStatus) and interfaces |
| `src/task-manager.service.ts` | Task CRUD, dependency management, DAG validation |
| `src/agent-coordinator.service.ts` | Agent spawning, assignment, file conflict detection |
| `src/swarm.service.ts` | High-level orchestration and progress |
| `src/swarm.controller.ts` | REST API endpoints under `/api/swarm` |
| `src/swarm.gateway.ts` | WebSocket gateway with pluggable auth |
| `src/dto/swarm.dto.ts` | Request DTOs with class-validator |
| `src/decorators/current-user.decorator.ts` | Local `@CurrentUser()` param decorator |
| `prisma/schema.prisma` | Standalone Prisma schema (AgentTask + AgentExecution) |

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

- Glassy PAI docs: `adjudica-documentation/projects/glassy-pai/features/agent-swarm.md`
- Glassy architecture: `adjudica-documentation/projects/glassy/ARCHITECTURE_OVERVIEW.md`

---

## Root Standards Reference

For company-wide development standards, see the main CLAUDE.md at `~/Desktop/CLAUDE.md`.

For centralized business, legal, marketing, and product documentation, see the [Adjudica Documentation Hub](~/Desktop/adjudica-documentation/CLAUDE.md) and the [Quick Index](~/Desktop/adjudica-documentation/ADJUDICA_INDEX.md).

---

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
