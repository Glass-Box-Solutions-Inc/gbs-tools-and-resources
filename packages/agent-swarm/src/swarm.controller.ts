// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology

import { Controller, Post, Get, Patch, Delete, HttpCode, HttpStatus, Param, Body, Query } from '@nestjs/common';
import { TaskManagerService } from './task-manager.service.js';
import { SwarmService } from './swarm.service.js';
import { AgentCoordinatorService } from './agent-coordinator.service.js';
import { CreateTaskDto, UpdateTaskDto, SpawnSwarmDto, CompleteAgentTaskDto, FailAgentTaskDto } from './dto/swarm.dto.js';
import { CurrentUser } from './decorators/current-user.decorator.js';

@Controller('swarm')
export class SwarmController {
  constructor(
    private readonly taskManager: TaskManagerService,
    private readonly swarm: SwarmService,
    private readonly coordinator: AgentCoordinatorService,
  ) {}

  // ─── Task Endpoints ─────────────────────────────────────────────

  @Post('tasks')
  async createTask(
    @CurrentUser('id') userId: string,
    @Body() dto: CreateTaskDto,
  ) {
    return this.taskManager.createTask(userId, dto);
  }

  @Get('tasks')
  async listTasks(
    @CurrentUser('id') userId: string,
    @Query('status') status?: string,
    @Query('assignee') assignee?: string,
  ) {
    return this.taskManager.listTasks(userId, { status, assignee });
  }

  @Get('tasks/:id')
  async getTask(
    @Param('id') id: string,
    @CurrentUser('id') userId: string,
  ) {
    return this.taskManager.getTask(id, userId);
  }

  @Patch('tasks/:id')
  async updateTask(
    @Param('id') id: string,
    @Body() dto: UpdateTaskDto,
    @CurrentUser('id') userId: string,
  ) {
    return this.taskManager.updateTask(id, dto, userId);
  }

  @Delete('tasks/:id')
  @HttpCode(HttpStatus.NO_CONTENT)
  async deleteTask(
    @Param('id') id: string,
    @CurrentUser('id') userId: string,
  ) {
    await this.taskManager.deleteTask(id, userId);
  }

  @Get('tasks/available')
  async getAvailableTasks(@CurrentUser('id') userId: string) {
    return this.taskManager.getAvailableTasks(userId);
  }

  @Get('tasks/validate-dag')
  async validateDAG(@CurrentUser('id') userId: string) {
    return this.taskManager.validateDAG(userId);
  }

  // ─── Swarm Endpoints ────────────────────────────────────────────

  @Post('spawn')
  async spawnSwarm(
    @CurrentUser('id') userId: string,
    @Body() dto: SpawnSwarmDto,
  ) {
    return this.swarm.spawnSwarm(userId, dto.objective, dto.roles, dto.taskIds);
  }

  @Get('status')
  async getStatus(@CurrentUser('id') userId: string) {
    return this.swarm.getStatus(userId);
  }

  /**
   * Returns active in-process agent workers for the requesting user's session.
   * Agent coordinator state is global; filtering by userId prevents cross-user visibility.
   */
  @Get('agents')
  async getAgents(@CurrentUser('id') userId: string) {
    const all = this.coordinator.getActiveAgents();
    return all.filter((agent: any) => agent.userId === userId);
  }

  @Get('history')
  async getHistory(
    @CurrentUser('id') userId: string,
    @Query('limit') limit?: string,
  ) {
    return this.swarm.getExecutionHistory(userId, limit ? parseInt(limit, 10) : 50);
  }

  @Post('agents/:id/complete')
  async completeAgentTask(
    @Param('id') agentId: string,
    @Body() body: CompleteAgentTaskDto,
  ) {
    await this.coordinator.completeTask(agentId, body.output ?? {});
    return { success: true };
  }

  @Post('agents/:id/fail')
  async failAgentTask(
    @Param('id') agentId: string,
    @Body() body: FailAgentTaskDto,
  ) {
    await this.coordinator.failTask(agentId, body.error);
    return { success: true };
  }
}
