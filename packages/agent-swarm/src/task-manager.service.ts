// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology

import { Injectable, Logger, NotFoundException, BadRequestException, ForbiddenException } from '@nestjs/common';
import { PrismaService } from './prisma.service.js';

/**
 * Task Manager Service — CRUD operations for agent tasks with dependency management.
 * Implements DAG validation to prevent circular dependencies.
 */
@Injectable()
export class TaskManagerService {
  private readonly logger = new Logger(TaskManagerService.name);

  constructor(private readonly prisma: PrismaService) {}

  async createTask(
    userId: string,
    data: {
      title: string;
      description: string;
      priority?: number;
      blockedBy?: string[];
    },
  ) {
    // Validate blockedBy tasks exist
    if (data.blockedBy?.length) {
      const existingTasks = await this.prisma.agentTask.findMany({
        where: { id: { in: data.blockedBy } },
        select: { id: true },
      });
      const existingIds = new Set(existingTasks.map((t) => t.id));
      const missing = data.blockedBy.filter((id) => !existingIds.has(id));
      if (missing.length > 0) {
        throw new BadRequestException(`Blocked-by tasks not found: ${missing.join(', ')}`);
      }
    }

    const task = await this.prisma.agentTask.create({
      data: {
        userId,
        title: data.title,
        description: data.description,
        status: 'PENDING',
        priority: data.priority ?? 0,
        blockedBy: data.blockedBy ?? [],
        blocks: [],
      },
    });

    // Update the "blocks" field on each dependency
    if (data.blockedBy?.length) {
      for (const depId of data.blockedBy) {
        const dep = await this.prisma.agentTask.findUnique({ where: { id: depId } });
        if (dep) {
          const currentBlocks = (dep.blocks as string[]) ?? [];
          await this.prisma.agentTask.update({
            where: { id: depId },
            data: { blocks: [...currentBlocks, task.id] },
          });
        }
      }
    }

    this.logger.log(`Created task ${task.id}: "${task.title}"`);
    return task;
  }

  async getTask(id: string, userId?: string) {
    const task = await this.prisma.agentTask.findUnique({ where: { id } });
    if (!task) throw new NotFoundException(`Task ${id} not found`);
    // Ownership check — internal callers (coordinator, swarm service) pass no userId (HIGH-02)
    if (userId && task.userId !== userId) {
      throw new ForbiddenException('Access denied');
    }
    return task;
  }

  async listTasks(userId: string, filters?: { status?: string; assignee?: string }) {
    const where: Record<string, unknown> = { userId };
    if (filters?.status) where.status = filters.status;
    if (filters?.assignee) where.assignee = filters.assignee;

    return this.prisma.agentTask.findMany({
      where,
      orderBy: [{ priority: 'desc' }, { createdAt: 'asc' }],
    });
  }

  async updateTask(
    id: string,
    data: {
      title?: string;
      description?: string;
      status?: string;
      assignee?: string;
      priority?: number;
    },
    userId?: string,
  ) {
    // Ownership check — internal callers (coordinator) pass no userId (HIGH-02)
    const task = await this.getTask(id, userId);

    const updateData: Record<string, unknown> = {};
    if (data.title !== undefined) updateData.title = data.title;
    if (data.description !== undefined) updateData.description = data.description;
    if (data.status !== undefined) updateData.status = data.status;
    if (data.assignee !== undefined) updateData.assignee = data.assignee;
    if (data.priority !== undefined) updateData.priority = data.priority;

    if (data.status === 'COMPLETED') {
      updateData.completedAt = new Date();
    }

    const updated = await this.prisma.agentTask.update({
      where: { id },
      data: updateData,
    });

    this.logger.log(`Updated task ${id}: status=${updated.status}`);
    return updated;
  }

  async assignTask(taskId: string, agentRole: string) {
    // Check dependencies are met
    const task = await this.getTask(taskId);
    const blockedBy = (task.blockedBy as string[]) ?? [];

    if (blockedBy.length > 0) {
      const deps = await this.prisma.agentTask.findMany({
        where: { id: { in: blockedBy } },
        select: { id: true, status: true },
      });
      const incomplete = deps.filter((d) => d.status !== 'COMPLETED');
      if (incomplete.length > 0) {
        throw new BadRequestException(
          `Task ${taskId} is blocked by incomplete tasks: ${incomplete.map((d) => d.id).join(', ')}`,
        );
      }
    }

    return this.updateTask(taskId, { assignee: agentRole, status: 'IN_PROGRESS' });
  }

  async getAvailableTasks(userId: string): Promise<string[]> {
    const pendingTasks = await this.prisma.agentTask.findMany({
      where: { userId, status: 'PENDING' },
    });

    const available: string[] = [];
    for (const task of pendingTasks) {
      const blockedBy = (task.blockedBy as string[]) ?? [];
      if (blockedBy.length === 0) {
        available.push(task.id);
        continue;
      }

      const deps = await this.prisma.agentTask.findMany({
        where: { id: { in: blockedBy } },
        select: { status: true },
      });
      if (deps.every((d) => d.status === 'COMPLETED')) {
        available.push(task.id);
      }
    }

    return available;
  }

  /**
   * Validate no circular dependencies exist in the task graph.
   */
  async validateDAG(userId: string): Promise<{ valid: boolean; cycles: string[][] }> {
    const tasks = await this.prisma.agentTask.findMany({
      where: { userId },
      select: { id: true, blockedBy: true },
    });

    const graph = new Map<string, string[]>();
    for (const task of tasks) {
      graph.set(task.id, (task.blockedBy as string[]) ?? []);
    }

    const cycles: string[][] = [];
    const visited = new Set<string>();
    const inStack = new Set<string>();

    const dfs = (node: string, path: string[]) => {
      if (inStack.has(node)) {
        const cycleStart = path.indexOf(node);
        cycles.push(path.slice(cycleStart));
        return;
      }
      if (visited.has(node)) return;

      visited.add(node);
      inStack.add(node);
      path.push(node);

      const deps = graph.get(node) ?? [];
      for (const dep of deps) {
        dfs(dep, [...path]);
      }

      inStack.delete(node);
    };

    for (const [id] of graph) {
      if (!visited.has(id)) {
        dfs(id, []);
      }
    }

    return { valid: cycles.length === 0, cycles };
  }

  async deleteTask(taskId: string, userId: string): Promise<void> {
    const task = await this.getTask(taskId, userId);
    // Cascade: remove this task from the "blocks" array of its dependencies
    const blockedBy = (task.blockedBy as string[]) ?? [];
    for (const depId of blockedBy) {
      const dep = await this.prisma.agentTask.findUnique({ where: { id: depId } });
      if (dep) {
        const updatedBlocks = ((dep.blocks as string[]) ?? []).filter((id) => id !== taskId);
        await this.prisma.agentTask.update({ where: { id: depId }, data: { blocks: updatedBlocks } });
      }
    }
    await this.prisma.agentExecution.deleteMany({ where: { taskId } });
    await this.prisma.agentTask.delete({ where: { id: taskId } });
    this.logger.log(`Deleted task ${taskId}`);
  }
}
