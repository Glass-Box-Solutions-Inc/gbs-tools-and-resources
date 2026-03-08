// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology

import { Injectable, Logger } from '@nestjs/common';
import { PrismaService } from '../prisma/prisma.service.js';
import { TaskManagerService } from './task-manager.service.js';
import { AgentCoordinatorService } from './agent-coordinator.service.js';
import { AgentRole } from './dto/swarm.dto.js';

/**
 * Swarm Service — Orchestrates multi-agent workflows.
 * Monitors progress, handles timeouts, aggregates results.
 */
@Injectable()
export class SwarmService {
  private readonly logger = new Logger(SwarmService.name);

  constructor(
    private readonly prisma: PrismaService,
    private readonly taskManager: TaskManagerService,
    private readonly coordinator: AgentCoordinatorService,
  ) {}

  /**
   * Spawn a complete agent swarm for an objective.
   * Creates tasks from objective, spawns agents, assigns initial tasks.
   */
  async spawnSwarm(
    userId: string,
    objective: string,
    roles: AgentRole[],
    taskIds?: string[],
  ) {
    // Validate DAG if tasks provided
    if (taskIds?.length) {
      const dagCheck = await this.taskManager.validateDAG(userId);
      if (!dagCheck.valid) {
        this.logger.warn(`Circular dependencies detected: ${JSON.stringify(dagCheck.cycles)}`);
      }
    }

    // Spawn agent team
    const agents = await this.coordinator.spawnTeam(userId, objective, roles);

    // Assign available tasks to agents
    const assignments = await this.coordinator.assignTasks(userId);

    // Check for file conflicts
    const conflicts = this.coordinator.detectFileConflicts();
    if (conflicts.length > 0) {
      this.logger.warn(`File conflicts detected: ${JSON.stringify(conflicts)}`);
    }

    return {
      swarmId: `swarm-${Date.now()}`,
      objective,
      agents: agents.map((a) => ({ id: a.id, role: a.role, status: a.status })),
      assignments,
      conflicts,
    };
  }

  /**
   * Get comprehensive swarm status.
   */
  async getStatus(userId: string) {
    const agents = this.coordinator.getActiveAgents();
    const tasks = await this.taskManager.listTasks(userId);
    const conflicts = this.coordinator.detectFileConflicts();

    const tasksByStatus = {
      PENDING: tasks.filter((t) => t.status === 'PENDING').length,
      IN_PROGRESS: tasks.filter((t) => t.status === 'IN_PROGRESS').length,
      COMPLETED: tasks.filter((t) => t.status === 'COMPLETED').length,
    };

    const agentsByStatus = {
      IDLE: agents.filter((a) => a.status === 'IDLE').length,
      WORKING: agents.filter((a) => a.status === 'WORKING').length,
      BLOCKED: agents.filter((a) => a.status === 'BLOCKED').length,
      COMPLETED: agents.filter((a) => a.status === 'COMPLETED').length,
      FAILED: agents.filter((a) => a.status === 'FAILED').length,
    };

    const totalTasks = tasks.length;
    const progress = totalTasks > 0
      ? Math.round((tasksByStatus.COMPLETED / totalTasks) * 100)
      : 0;

    return {
      agents: agents.map((a) => ({
        id: a.id,
        role: a.role,
        status: a.status,
        currentTaskId: a.currentTaskId,
      })),
      tasks: tasksByStatus,
      progress,
      conflicts,
      agentsByStatus,
    };
  }

  /**
   * Get execution history scoped to the requesting user's swarm sessions.
   */
  async getExecutionHistory(userId: string, limit = 50) {
    return this.prisma.agentExecution.findMany({
      where: { task: { userId } },
      orderBy: { startedAt: 'desc' },
      take: limit,
    });
  }
}
