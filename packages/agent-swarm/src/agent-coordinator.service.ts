// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology

import { Injectable, Logger } from '@nestjs/common';
import { PrismaService } from './prisma.service.js';
import { TaskManagerService } from './task-manager.service.js';
import { AgentRole } from './dto/swarm.dto.js';

/**
 * Agent Coordinator Service — Spawn agents, assign tasks, coordinate parallel execution.
 * Agents are logical execution units (not separate processes) that represent
 * AI-driven workers performing specific roles.
 */

export interface AgentInstance {
  id: string;
  role: AgentRole;
  status: 'IDLE' | 'WORKING' | 'BLOCKED' | 'COMPLETED' | 'FAILED';
  currentTaskId: string | null;
  assignedFiles: string[];
}

@Injectable()
export class AgentCoordinatorService {
  private readonly logger = new Logger(AgentCoordinatorService.name);
  private readonly activeAgents = new Map<string, AgentInstance>();

  constructor(
    private readonly prisma: PrismaService,
    private readonly taskManager: TaskManagerService,
  ) {}

  /**
   * Spawn a team of agents with specified roles.
   */
  async spawnTeam(
    userId: string,
    objective: string,
    roles: AgentRole[],
  ): Promise<AgentInstance[]> {
    const agents: AgentInstance[] = [];

    for (const role of roles) {
      const execution = await this.prisma.agentExecution.create({
        data: {
          agentRole: role,
          status: 'RUNNING',
          output: { objective, spawnedAt: new Date().toISOString() },
        },
      });

      const agent: AgentInstance = {
        id: execution.id,
        role,
        status: 'IDLE',
        currentTaskId: null,
        assignedFiles: this.getDefaultFileScope(role),
      };

      this.activeAgents.set(agent.id, agent);
      agents.push(agent);

      this.logger.log(`Spawned agent ${agent.id} with role: ${role}`);
    }

    return agents;
  }

  /**
   * Assign available tasks to idle agents, respecting file scope boundaries.
   */
  async assignTasks(userId: string): Promise<Array<{ agentId: string; taskId: string }>> {
    const assignments: Array<{ agentId: string; taskId: string }> = [];
    const availableTaskIds = await this.taskManager.getAvailableTasks(userId);

    for (const [agentId, agent] of this.activeAgents) {
      if (agent.status !== 'IDLE') continue;
      if (availableTaskIds.length === 0) break;

      const taskId = availableTaskIds.shift()!;
      try {
        await this.taskManager.assignTask(taskId, agent.role);
        agent.status = 'WORKING';
        agent.currentTaskId = taskId;

        assignments.push({ agentId, taskId });
        this.logger.log(`Assigned task ${taskId} to agent ${agentId} (${agent.role})`);
      } catch (error) {
        this.logger.warn(`Failed to assign task ${taskId} to agent ${agentId}: ${error}`);
      }
    }

    return assignments;
  }

  /**
   * Complete a task for an agent and make agent available for next task.
   */
  async completeTask(
    agentId: string,
    output: Record<string, unknown>,
  ): Promise<void> {
    const agent = this.activeAgents.get(agentId);
    if (!agent || !agent.currentTaskId) return;

    await this.taskManager.updateTask(agent.currentTaskId, { status: 'COMPLETED' });
    await this.prisma.agentExecution.update({
      where: { id: agentId },
      data: {
        status: 'SUCCESS',
        output: output as object,
        completedAt: new Date(),
      },
    });

    agent.status = 'IDLE';
    agent.currentTaskId = null;
    this.logger.log(`Agent ${agentId} completed task, now IDLE`);
  }

  /**
   * Report agent failure.
   */
  async failTask(agentId: string, error: string): Promise<void> {
    const agent = this.activeAgents.get(agentId);
    if (!agent || !agent.currentTaskId) return;

    await this.taskManager.updateTask(agent.currentTaskId, { status: 'PENDING' });
    await this.prisma.agentExecution.update({
      where: { id: agentId },
      data: {
        status: 'FAILED',
        error,
        completedAt: new Date(),
      },
    });

    agent.status = 'FAILED';
    agent.currentTaskId = null;
    this.logger.warn(`Agent ${agentId} failed: ${error}`);
  }

  /**
   * Get status of all active agents.
   */
  getActiveAgents(): AgentInstance[] {
    return Array.from(this.activeAgents.values());
  }

  /**
   * Check for file scope conflicts between agents.
   */
  detectFileConflicts(): Array<{ file: string; agents: string[] }> {
    const fileMap = new Map<string, string[]>();

    for (const [agentId, agent] of this.activeAgents) {
      if (agent.status !== 'WORKING') continue;
      for (const file of agent.assignedFiles) {
        const existing = fileMap.get(file) ?? [];
        existing.push(agentId);
        fileMap.set(file, existing);
      }
    }

    return Array.from(fileMap.entries())
      .filter(([, agents]) => agents.length > 1)
      .map(([file, agents]) => ({ file, agents }));
  }

  /**
   * Default file scope per agent role to prevent conflicts.
   */
  private getDefaultFileScope(role: AgentRole): string[] {
    switch (role) {
      case AgentRole.FRONTEND:
        return ['frontend/**'];
      case AgentRole.BACKEND:
        return ['backend/src/**'];
      case AgentRole.TESTS:
        return ['backend/test/**', 'frontend/e2e/**'];
      case AgentRole.SECURITY:
        return ['docs/compliance/**', 'backend/src/common/guards/**'];
      case AgentRole.DEVOPS:
        return ['.github/**', 'infra/**'];
      case AgentRole.DOCS:
        return ['docs/**'];
      case AgentRole.DESIGN:
        return ['frontend/app/components/**'];
      case AgentRole.RESEARCH:
        return [];
      default:
        return [];
    }
  }
}
