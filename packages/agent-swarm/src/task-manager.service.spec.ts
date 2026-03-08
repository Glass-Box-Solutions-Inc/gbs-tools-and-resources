// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology

// Mock the Prisma client
jest.mock('@prisma/client', () => ({
  PrismaClient: jest.fn(),
}));

import { Test, TestingModule } from '@nestjs/testing';
import { NotFoundException, BadRequestException } from '@nestjs/common';
import { TaskManagerService } from './task-manager.service.js';
import { PrismaService } from './prisma.service.js';

// ---------------------------------------------------------------------------
// Mock PrismaService factory
// ---------------------------------------------------------------------------

const mockPrismaService = () => ({
  agentTask: {
    create: jest.fn(),
    findUnique: jest.fn(),
    findMany: jest.fn(),
    update: jest.fn(),
  },
});

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeTask(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    id: 'task-1',
    userId: 'user-1',
    title: 'Test Task',
    description: 'A test task',
    status: 'PENDING',
    priority: 0,
    blockedBy: [],
    blocks: [],
    assignee: null,
    createdAt: new Date('2025-01-01'),
    updatedAt: new Date('2025-01-01'),
    completedAt: null,
    ...overrides,
  };
}

describe('TaskManagerService', () => {
  let service: TaskManagerService;
  let prisma: ReturnType<typeof mockPrismaService>;

  beforeEach(async () => {
    prisma = mockPrismaService();

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        TaskManagerService,
        { provide: PrismaService, useValue: prisma },
      ],
    }).compile();

    service = module.get<TaskManagerService>(TaskManagerService);
  });

  // =========================================================================
  // createTask
  // =========================================================================

  describe('createTask', () => {
    it('should create a task with default PENDING status and priority 0', async () => {
      const created = makeTask();
      prisma.agentTask.create.mockResolvedValue(created);

      const result = await service.createTask('user-1', {
        title: 'Test Task',
        description: 'A test task',
      });

      expect(result).toEqual(created);
      expect(prisma.agentTask.create).toHaveBeenCalledWith({
        data: expect.objectContaining({
          userId: 'user-1',
          title: 'Test Task',
          description: 'A test task',
          status: 'PENDING',
          priority: 0,
          blockedBy: [],
          blocks: [],
        }),
      });
    });

    it('should create a task with explicit priority', async () => {
      const created = makeTask({ priority: 5 });
      prisma.agentTask.create.mockResolvedValue(created);

      const result = await service.createTask('user-1', {
        title: 'High Priority',
        description: 'Urgent task',
        priority: 5,
      });

      expect(result.priority).toBe(5);
      expect(prisma.agentTask.create).toHaveBeenCalledWith({
        data: expect.objectContaining({ priority: 5 }),
      });
    });

    it('should validate blockedBy tasks exist before creating', async () => {
      prisma.agentTask.findMany.mockResolvedValue([{ id: 'dep-1' }]);
      prisma.agentTask.create.mockResolvedValue(makeTask({ blockedBy: ['dep-1'] }));
      prisma.agentTask.findUnique.mockResolvedValue(makeTask({ id: 'dep-1', blocks: [] }));
      prisma.agentTask.update.mockResolvedValue({});

      await service.createTask('user-1', {
        title: 'Blocked Task',
        description: 'Blocked by dep-1',
        blockedBy: ['dep-1'],
      });

      expect(prisma.agentTask.findMany).toHaveBeenCalledWith({
        where: { id: { in: ['dep-1'] } },
        select: { id: true },
      });
    });

    it('should throw BadRequestException when blockedBy references missing tasks', async () => {
      prisma.agentTask.findMany.mockResolvedValue([]);

      await expect(
        service.createTask('user-1', {
          title: 'Bad Task',
          description: 'References missing task',
          blockedBy: ['nonexistent-task'],
        }),
      ).rejects.toThrow(BadRequestException);
    });

    it('should update blocks field on dependency tasks after creation', async () => {
      const depTask = makeTask({ id: 'dep-1', blocks: [] });
      prisma.agentTask.findMany.mockResolvedValue([{ id: 'dep-1' }]);
      prisma.agentTask.create.mockResolvedValue(makeTask({ id: 'new-task', blockedBy: ['dep-1'] }));
      prisma.agentTask.findUnique.mockResolvedValue(depTask);
      prisma.agentTask.update.mockResolvedValue({});

      await service.createTask('user-1', {
        title: 'New Task',
        description: 'Depends on dep-1',
        blockedBy: ['dep-1'],
      });

      expect(prisma.agentTask.update).toHaveBeenCalledWith({
        where: { id: 'dep-1' },
        data: { blocks: expect.arrayContaining(['new-task']) },
      });
    });
  });

  // =========================================================================
  // getTask
  // =========================================================================

  describe('getTask', () => {
    it('should return task when found', async () => {
      const task = makeTask();
      prisma.agentTask.findUnique.mockResolvedValue(task);

      const result = await service.getTask('task-1');

      expect(result).toEqual(task);
      expect(prisma.agentTask.findUnique).toHaveBeenCalledWith({ where: { id: 'task-1' } });
    });

    it('should throw NotFoundException when task does not exist', async () => {
      prisma.agentTask.findUnique.mockResolvedValue(null);

      await expect(service.getTask('nonexistent')).rejects.toThrow(NotFoundException);
    });
  });

  // =========================================================================
  // listTasks
  // =========================================================================

  describe('listTasks', () => {
    it('should list tasks for a user', async () => {
      const tasks = [makeTask(), makeTask({ id: 'task-2' })];
      prisma.agentTask.findMany.mockResolvedValue(tasks);

      const result = await service.listTasks('user-1');

      expect(result).toHaveLength(2);
      expect(prisma.agentTask.findMany).toHaveBeenCalledWith({
        where: { userId: 'user-1' },
        orderBy: [{ priority: 'desc' }, { createdAt: 'asc' }],
      });
    });

    it('should filter tasks by status', async () => {
      prisma.agentTask.findMany.mockResolvedValue([]);

      await service.listTasks('user-1', { status: 'IN_PROGRESS' });

      expect(prisma.agentTask.findMany).toHaveBeenCalledWith({
        where: { userId: 'user-1', status: 'IN_PROGRESS' },
        orderBy: [{ priority: 'desc' }, { createdAt: 'asc' }],
      });
    });

    it('should filter tasks by assignee', async () => {
      prisma.agentTask.findMany.mockResolvedValue([]);

      await service.listTasks('user-1', { assignee: 'agent-a' });

      expect(prisma.agentTask.findMany).toHaveBeenCalledWith({
        where: { userId: 'user-1', assignee: 'agent-a' },
        orderBy: [{ priority: 'desc' }, { createdAt: 'asc' }],
      });
    });

    it('should return empty array when no tasks match', async () => {
      prisma.agentTask.findMany.mockResolvedValue([]);

      const result = await service.listTasks('user-no-tasks');

      expect(result).toEqual([]);
    });
  });

  // =========================================================================
  // updateTask
  // =========================================================================

  describe('updateTask', () => {
    it('should update task title and description', async () => {
      const task = makeTask();
      prisma.agentTask.findUnique.mockResolvedValue(task);
      prisma.agentTask.update.mockResolvedValue({
        ...task,
        title: 'Updated Title',
        description: 'Updated Desc',
      });

      const result = await service.updateTask('task-1', {
        title: 'Updated Title',
        description: 'Updated Desc',
      });

      expect(result.title).toBe('Updated Title');
    });

    it('should set completedAt when status is changed to COMPLETED', async () => {
      const task = makeTask();
      prisma.agentTask.findUnique.mockResolvedValue(task);
      prisma.agentTask.update.mockResolvedValue({
        ...task,
        status: 'COMPLETED',
        completedAt: new Date(),
      });

      await service.updateTask('task-1', { status: 'COMPLETED' });

      expect(prisma.agentTask.update).toHaveBeenCalledWith({
        where: { id: 'task-1' },
        data: expect.objectContaining({
          status: 'COMPLETED',
          completedAt: expect.any(Date),
        }),
      });
    });

    it('should not set completedAt for non-COMPLETED status updates', async () => {
      const task = makeTask();
      prisma.agentTask.findUnique.mockResolvedValue(task);
      prisma.agentTask.update.mockResolvedValue({ ...task, status: 'IN_PROGRESS' });

      await service.updateTask('task-1', { status: 'IN_PROGRESS' });

      const updateCall = prisma.agentTask.update.mock.calls[0][0];
      expect(updateCall.data.completedAt).toBeUndefined();
    });

    it('should throw NotFoundException when updating a nonexistent task', async () => {
      prisma.agentTask.findUnique.mockResolvedValue(null);

      await expect(service.updateTask('nonexistent', { title: 'Nope' })).rejects.toThrow(
        NotFoundException,
      );
    });

    it('should update priority independently', async () => {
      const task = makeTask();
      prisma.agentTask.findUnique.mockResolvedValue(task);
      prisma.agentTask.update.mockResolvedValue({ ...task, priority: 10 });

      await service.updateTask('task-1', { priority: 10 });

      expect(prisma.agentTask.update).toHaveBeenCalledWith({
        where: { id: 'task-1' },
        data: { priority: 10 },
      });
    });
  });

  // =========================================================================
  // assignTask
  // =========================================================================

  describe('assignTask', () => {
    it('should assign task when all dependencies are complete', async () => {
      const task = makeTask({ blockedBy: ['dep-1'] });
      prisma.agentTask.findUnique.mockResolvedValue(task);
      prisma.agentTask.findMany.mockResolvedValue([{ id: 'dep-1', status: 'COMPLETED' }]);
      prisma.agentTask.update.mockResolvedValue({
        ...task,
        assignee: 'agent-a',
        status: 'IN_PROGRESS',
      });

      const result = await service.assignTask('task-1', 'agent-a');

      expect(result.assignee).toBe('agent-a');
      expect(result.status).toBe('IN_PROGRESS');
    });

    it('should throw BadRequestException when dependencies are incomplete', async () => {
      const task = makeTask({ blockedBy: ['dep-1'] });
      prisma.agentTask.findUnique.mockResolvedValue(task);
      prisma.agentTask.findMany.mockResolvedValue([{ id: 'dep-1', status: 'PENDING' }]);

      await expect(service.assignTask('task-1', 'agent-a')).rejects.toThrow(BadRequestException);
    });

    it('should assign task with no blockedBy dependencies immediately', async () => {
      const task = makeTask({ blockedBy: [] });
      prisma.agentTask.findUnique.mockResolvedValue(task);
      prisma.agentTask.update.mockResolvedValue({
        ...task,
        assignee: 'agent-a',
        status: 'IN_PROGRESS',
      });

      const result = await service.assignTask('task-1', 'agent-a');

      expect(result.status).toBe('IN_PROGRESS');
    });
  });

  // =========================================================================
  // getAvailableTasks
  // =========================================================================

  describe('getAvailableTasks', () => {
    it('should return tasks with no blockedBy dependencies', async () => {
      prisma.agentTask.findMany.mockResolvedValueOnce([
        makeTask({ id: 'task-1', blockedBy: [] }),
        makeTask({ id: 'task-2', blockedBy: [] }),
      ]);

      const result = await service.getAvailableTasks('user-1');

      expect(result).toEqual(['task-1', 'task-2']);
    });

    it('should return tasks whose dependencies are all COMPLETED', async () => {
      prisma.agentTask.findMany
        .mockResolvedValueOnce([makeTask({ id: 'task-1', blockedBy: ['dep-1'] })])
        .mockResolvedValueOnce([{ status: 'COMPLETED' }]);

      const result = await service.getAvailableTasks('user-1');

      expect(result).toEqual(['task-1']);
    });

    it('should exclude tasks with incomplete dependencies', async () => {
      prisma.agentTask.findMany
        .mockResolvedValueOnce([makeTask({ id: 'task-1', blockedBy: ['dep-1'] })])
        .mockResolvedValueOnce([{ status: 'PENDING' }]);

      const result = await service.getAvailableTasks('user-1');

      expect(result).toEqual([]);
    });

    it('should return empty array when no pending tasks exist', async () => {
      prisma.agentTask.findMany.mockResolvedValueOnce([]);

      const result = await service.getAvailableTasks('user-1');

      expect(result).toEqual([]);
    });
  });

  // =========================================================================
  // validateDAG (cycle detection)
  // =========================================================================

  describe('validateDAG', () => {
    it('should report valid DAG when no cycles exist', async () => {
      prisma.agentTask.findMany.mockResolvedValue([
        { id: 'A', blockedBy: [] },
        { id: 'B', blockedBy: ['A'] },
        { id: 'C', blockedBy: ['B'] },
      ]);

      const result = await service.validateDAG('user-1');

      expect(result.valid).toBe(true);
      expect(result.cycles).toHaveLength(0);
    });

    it('should detect a simple two-node cycle', async () => {
      prisma.agentTask.findMany.mockResolvedValue([
        { id: 'A', blockedBy: ['B'] },
        { id: 'B', blockedBy: ['A'] },
      ]);

      const result = await service.validateDAG('user-1');

      expect(result.valid).toBe(false);
      expect(result.cycles.length).toBeGreaterThanOrEqual(1);
    });

    it('should detect a three-node cycle (A->B->C->A)', async () => {
      prisma.agentTask.findMany.mockResolvedValue([
        { id: 'A', blockedBy: ['C'] },
        { id: 'B', blockedBy: ['A'] },
        { id: 'C', blockedBy: ['B'] },
      ]);

      const result = await service.validateDAG('user-1');

      expect(result.valid).toBe(false);
      expect(result.cycles.length).toBeGreaterThanOrEqual(1);
    });

    it('should report valid for a single task with no dependencies', async () => {
      prisma.agentTask.findMany.mockResolvedValue([{ id: 'A', blockedBy: [] }]);

      const result = await service.validateDAG('user-1');

      expect(result.valid).toBe(true);
      expect(result.cycles).toHaveLength(0);
    });

    it('should report valid for an empty task list', async () => {
      prisma.agentTask.findMany.mockResolvedValue([]);

      const result = await service.validateDAG('user-1');

      expect(result.valid).toBe(true);
      expect(result.cycles).toHaveLength(0);
    });

    it('should handle graphs with disconnected components correctly', async () => {
      prisma.agentTask.findMany.mockResolvedValue([
        { id: 'A', blockedBy: [] },
        { id: 'B', blockedBy: ['A'] },
        { id: 'C', blockedBy: [] },
        { id: 'D', blockedBy: ['C'] },
      ]);

      const result = await service.validateDAG('user-1');

      expect(result.valid).toBe(true);
      expect(result.cycles).toHaveLength(0);
    });

    it('should detect cycle in a graph where only one component has a cycle', async () => {
      prisma.agentTask.findMany.mockResolvedValue([
        { id: 'A', blockedBy: [] },
        { id: 'B', blockedBy: ['A'] },
        // Separate component with cycle
        { id: 'X', blockedBy: ['Y'] },
        { id: 'Y', blockedBy: ['X'] },
      ]);

      const result = await service.validateDAG('user-1');

      expect(result.valid).toBe(false);
      expect(result.cycles.length).toBeGreaterThanOrEqual(1);
    });
  });
});
