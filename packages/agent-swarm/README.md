# Agent Swarm

**DAG-based multi-agent task orchestration system** — spawns teams of specialized AI agents that execute interdependent tasks in parallel with file scope isolation and real-time WebSocket status updates.

> **Status:** Standalone Package (canonical for GBS) | **Install:** `npm install @gbs/agent-swarm`

This is a **standalone NestJS library module**, forked from Glassy PAI's embedded agent-swarm module and decoupled from all Glassy dependencies. It can be used independently with its own Prisma schema or hosted inside any NestJS application via `AgentSwarmModule.forRoot()`.

> **Relationship to Glassy:** The agent-swarm module within `glassy-app-production` remains canonical for Glassy PAI and continues to evolve independently within that codebase. This standalone package is a separate resource maintained by GBS for use outside of Glassy.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Runtime | NestJS 11 + TypeScript |
| Real-time | Socket.io (WebSocket gateway) |
| Database | Prisma ORM (PostgreSQL) |
| Auth | Pluggable — standalone token or host-provided auth |
| Validation | class-validator + class-transformer |

---

## Installation

### Standalone Mode

```bash
npm install @gbs/agent-swarm
cp .env.example .env  # Configure DATABASE_URL
npx prisma generate
npx prisma migrate dev
```

### Hosted Mode (e.g. inside Glassy)

```typescript
import { AgentSwarmModule } from '@gbs/agent-swarm';
import { GlassyPrismaService } from './prisma/prisma.service.js';

@Module({
  imports: [AgentSwarmModule.forRoot({ prismaService: GlassyPrismaService })],
})
export class AppModule {}
```

---

## Architecture

```
SwarmController (/api/swarm)
├── TaskManagerService ───────→ Prisma (AgentTask, AgentExecution)
├── SwarmService
│   ├── TaskManagerService     (DAG validation, task queries)
│   ├── AgentCoordinatorService (team spawning, assignment)
│   └── SwarmGateway           (real-time broadcasts)
└── AgentCoordinatorService
```

### DAG Task Model

Tasks are organized as a Directed Acyclic Graph with `blockedBy`/`blocks` relationships. Cycle detection runs via DFS before execution. Tasks progress: `PENDING` → `IN_PROGRESS` → `COMPLETED` or `FAILED`.

```
[Parse Requirements] ──→ [Implement Backend] ──→ [Write Tests]
                     ──→ [Implement Frontend] ──→ [Write Tests]
```

### Agent Roles (8 Specializations)

| Role | File Scope |
|------|-----------|
| Frontend | `frontend/**` |
| Backend | `backend/src/**` |
| Tests | `backend/test/**`, `frontend/e2e/**` |
| Security | `docs/compliance/**`, `backend/src/common/guards/**` |
| DevOps | `.github/**`, `infra/**` |
| Docs | `docs/**` |
| Design | `frontend/app/components/**` |
| Research | Unrestricted |

---

## Core Services

### TaskManagerService
CRUD operations, dependency management, DAG validation. Key methods:
- `createTask()` — Create task with optional `blockedBy` dependencies
- `assignTask()` — Assign to agent; validates all dependencies are COMPLETED
- `getAvailableTasks()` — Returns PENDING tasks with satisfied dependencies
- `validateDAG()` — DFS cycle detection; returns `{ valid, cycles }`

### AgentCoordinatorService
Agent spawning, task assignment, file conflict detection:
- `spawnTeam()` — Creates agent instances for specified roles
- `assignTasks()` — Greedy assignment of available tasks to IDLE agents
- `detectFileConflicts()` — Returns files assigned to multiple WORKING agents

### SwarmService
High-level orchestration and progress aggregation:
- `spawnSwarm()` — Validates DAG → spawns team → assigns tasks → detects conflicts
- `getStatus()` — Aggregated health: agent/task counts, progress %, active conflicts
- `getExecutionHistory()` — User-scoped execution records

---

## API Reference

### Task Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/swarm/tasks` | Create task with dependencies |
| GET | `/api/swarm/tasks` | List tasks (`?status=X&assignee=Y`) |
| GET | `/api/swarm/tasks/:id` | Get single task |
| PATCH | `/api/swarm/tasks/:id` | Update task |
| DELETE | `/api/swarm/tasks/:id` | Delete task (cascades) |
| GET | `/api/swarm/tasks/available` | List ready-to-execute tasks |
| GET | `/api/swarm/tasks/validate-dag` | Validate DAG for cycles |

### Swarm Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/swarm/spawn` | Spawn multi-agent team |
| GET | `/api/swarm/status` | Real-time swarm health |
| GET | `/api/swarm/agents` | List active agents |
| GET | `/api/swarm/history` | Execution history (`?limit=50`) |
| POST | `/api/swarm/agents/:id/complete` | Mark agent task complete |
| POST | `/api/swarm/agents/:id/fail` | Report agent failure |

### WebSocket Events (Namespace: `/swarm`)

**Client → Server:**
- `joinSwarm({ swarmId })` — Subscribe to swarm updates
- `leaveSwarm({ swarmId })` — Unsubscribe

**Server → Client:**
- `taskUpdate({ id, status, assignee? })` — Task state change
- `agentStatus({ id, role, status, currentTaskId })` — Agent state change
- `progress({ completed, total, percentage })` — Progress update
- `conflict({ file, agents[] })` — File conflict detected

---

## File Structure

```
packages/agent-swarm/
├── package.json                             # @gbs/agent-swarm
├── tsconfig.json
├── .env.example
├── prisma/
│   └── schema.prisma                        # Standalone schema (AgentTask + AgentExecution)
├── src/
│   ├── index.ts                             # Barrel export
│   ├── prisma.service.ts                    # Standalone PrismaService
│   ├── agent-swarm.module.ts                # NestJS module (with forRoot())
│   ├── agent-swarm.types.ts                 # Shared type definitions
│   ├── agent-coordinator.service.ts         # Agent spawning & assignment
│   ├── task-manager.service.ts              # Task CRUD & DAG validation
│   ├── swarm.service.ts                     # Orchestration & progress
│   ├── swarm.controller.ts                  # REST API endpoints
│   ├── swarm.gateway.ts                     # WebSocket gateway (pluggable auth)
│   ├── swarm.e2e-spec.ts                    # E2E integration tests
│   ├── agent-coordinator.service.spec.ts
│   ├── swarm.service.spec.ts
│   ├── task-manager.service.spec.ts
│   ├── decorators/
│   │   └── current-user.decorator.ts        # Local @CurrentUser() decorator
│   └── dto/
│       └── swarm.dto.ts                     # Request validation DTOs
├── README.md
└── CLAUDE.md
```

---

## Related Packages

- [spectacles](../spectacles/) — Browser automation platform (uses agent orchestration patterns)
- [merus-expert](../merus-expert/) — MerusCase domain agent (single-agent, tool-calling pattern)
- [agentic-debugger](../agentic-debugger/) — CI debugging agent (Claude Code-based)

---

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
