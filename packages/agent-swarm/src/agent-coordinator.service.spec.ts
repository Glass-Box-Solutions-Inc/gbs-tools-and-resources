// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology

// Prevent ESM import.meta issues in Jest
jest.mock('../../../generated/prisma/client', () => ({
  PrismaClient: jest.fn(),
}));

jest.mock('@prisma/adapter-pg', () => ({
  PrismaPg: jest.fn(),
}));

import { Test, TestingModule } from '@nestjs/testing';
import { AgentCoordinatorService } from './agent-coordinator.service.js';
import { PrismaService } from '../prisma/prisma.service.js';
import { TaskManagerService } from './task-manager.service.js';
import { AgentRole } from './dto/swarm.dto.js';

// ---------------------------------------------------------------------------
// Mock factories
// ---------------------------------------------------------------------------

const mockPrismaService = () => ({
  agentExecution: {
    create: jest.fn(),
    update: jest.fn(),
  },
  agentTask: {
    update: jest.fn(),
    findMany: jest.fn(),
    findUnique: jest.fn(),
    create: jest.fn(),
  },
});

const mockTaskManagerService = () => ({
  getAvailableTasks: jest.fn(),
  assignTask: jest.fn(),
  updateTask: jest.fn(),
  createTask: jest.fn(),
  getTask: jest.fn(),
  listTasks: jest.fn(),
  validateDAG: jest.fn(),
});

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeExecution(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    id: 'exec-1',
    agentRole: 'Backend',
    status: 'RUNNING',
    output: {},
    error: null,
    startedAt: new Date('2025-01-01'),
    completedAt: null,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// AgentCoordinatorService tests
// ---------------------------------------------------------------------------

describe('AgentCoordinatorService', () => {
  let service: AgentCoordinatorService;
  let prisma: ReturnType<typeof mockPrismaService>;
  let taskManager: ReturnType<typeof mockTaskManagerService>;

  beforeEach(async () => {
    prisma = mockPrismaService();
    taskManager = mockTaskManagerService();

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        AgentCoordinatorService,
        { provide: PrismaService, useValue: prisma },
        { provide: TaskManagerService, useValue: taskManager },
      ],
    }).compile();

    service = module.get<AgentCoordinatorService>(AgentCoordinatorService);
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  // =========================================================================
  // spawnTeam
  // =========================================================================

  describe('spawnTeam', () => {
    it('should create one AgentExecution record per role', async () => {
      prisma.agentExecution.create
        .mockResolvedValueOnce(makeExecution({ id: 'exec-be' }))
        .mockResolvedValueOnce(makeExecution({ id: 'exec-ts' }));

      await service.spawnTeam('user-1', 'Build auth module', [
        AgentRole.BACKEND,
        AgentRole.TESTS,
      ]);

      expect(prisma.agentExecution.create).toHaveBeenCalledTimes(2);
    });

    it('should create AgentExecution with the correct role and RUNNING status', async () => {
      prisma.agentExecution.create.mockResolvedValue(makeExecution({ id: 'exec-fe', agentRole: 'Frontend' }));

      await service.spawnTeam('user-1', 'Build UI', [AgentRole.FRONTEND]);

      expect(prisma.agentExecution.create).toHaveBeenCalledWith(
        expect.objectContaining({
          data: expect.objectContaining({
            agentRole: AgentRole.FRONTEND,
            status: 'RUNNING',
          }),
        }),
      );
    });

    it('should embed the objective in the AgentExecution output', async () => {
      const objective = 'Refactor the billing service';
      prisma.agentExecution.create.mockResolvedValue(makeExecution({ id: 'exec-1' }));

      await service.spawnTeam('user-1', objective, [AgentRole.BACKEND]);

      expect(prisma.agentExecution.create).toHaveBeenCalledWith(
        expect.objectContaining({
          data: expect.objectContaining({
            output: expect.objectContaining({ objective }),
          }),
        }),
      );
    });

    it('should return an AgentInstance for each spawned role', async () => {
      prisma.agentExecution.create
        .mockResolvedValueOnce(makeExecution({ id: 'exec-be' }))
        .mockResolvedValueOnce(makeExecution({ id: 'exec-fe' }));

      const agents = await service.spawnTeam('user-1', 'Full stack', [
        AgentRole.BACKEND,
        AgentRole.FRONTEND,
      ]);

      expect(agents).toHaveLength(2);
    });

    it('should initialise each agent with status IDLE and no currentTaskId', async () => {
      prisma.agentExecution.create.mockResolvedValue(makeExecution({ id: 'exec-1' }));

      const agents = await service.spawnTeam('user-1', 'Task', [AgentRole.BACKEND]);

      expect(agents[0].status).toBe('IDLE');
      expect(agents[0].currentTaskId).toBeNull();
    });

    it('should assign default file scope to each agent based on role', async () => {
      prisma.agentExecution.create.mockResolvedValue(makeExecution({ id: 'exec-be' }));

      const agents = await service.spawnTeam('user-1', 'Task', [AgentRole.BACKEND]);

      expect(agents[0].assignedFiles).toContain('backend/src/**');
    });

    it('should assign correct file scope for FRONTEND role', async () => {
      prisma.agentExecution.create.mockResolvedValue(makeExecution({ id: 'exec-fe' }));

      const agents = await service.spawnTeam('user-1', 'Task', [AgentRole.FRONTEND]);

      expect(agents[0].assignedFiles).toContain('frontend/**');
    });

    it('should assign correct file scope for TESTS role', async () => {
      prisma.agentExecution.create.mockResolvedValue(makeExecution({ id: 'exec-ts' }));

      const agents = await service.spawnTeam('user-1', 'Task', [AgentRole.TESTS]);

      expect(agents[0].assignedFiles).toContain('backend/test/**');
    });

    it('should assign correct file scope for DEVOPS role', async () => {
      prisma.agentExecution.create.mockResolvedValue(makeExecution({ id: 'exec-do' }));

      const agents = await service.spawnTeam('user-1', 'Task', [AgentRole.DEVOPS]);

      expect(agents[0].assignedFiles).toContain('.github/**');
    });

    it('should assign empty file scope for RESEARCH role', async () => {
      prisma.agentExecution.create.mockResolvedValue(makeExecution({ id: 'exec-re' }));

      const agents = await service.spawnTeam('user-1', 'Task', [AgentRole.RESEARCH]);

      expect(agents[0].assignedFiles).toEqual([]);
    });

    it('should return an empty array when roles list is empty', async () => {
      const agents = await service.spawnTeam('user-1', 'Task', []);

      expect(agents).toHaveLength(0);
      expect(prisma.agentExecution.create).not.toHaveBeenCalled();
    });

    it('should register spawned agents in the internal activeAgents map', async () => {
      prisma.agentExecution.create.mockResolvedValue(makeExecution({ id: 'exec-1' }));

      await service.spawnTeam('user-1', 'Task', [AgentRole.BACKEND]);

      const activeAgents = service.getActiveAgents();
      expect(activeAgents).toHaveLength(1);
      expect(activeAgents[0].id).toBe('exec-1');
    });
  });

  // =========================================================================
  // getActiveAgents
  // =========================================================================

  describe('getActiveAgents', () => {
    it('should return an empty array when no agents have been spawned', () => {
      const agents = service.getActiveAgents();

      expect(agents).toEqual([]);
    });

    it('should return all spawned agents', async () => {
      prisma.agentExecution.create
        .mockResolvedValueOnce(makeExecution({ id: 'exec-1' }))
        .mockResolvedValueOnce(makeExecution({ id: 'exec-2' }));

      await service.spawnTeam('user-1', 'Multi-agent', [AgentRole.BACKEND, AgentRole.FRONTEND]);

      expect(service.getActiveAgents()).toHaveLength(2);
    });

    it('should reflect status updates after completeTask is called', async () => {
      prisma.agentExecution.create.mockResolvedValue(makeExecution({ id: 'exec-1' }));
      prisma.agentExecution.update.mockResolvedValue({});
      taskManager.updateTask.mockResolvedValue({});

      const agents = await service.spawnTeam('user-1', 'Task', [AgentRole.BACKEND]);
      // Manually put agent in WORKING state with a task assigned
      const agent = service.getActiveAgents()[0];
      agent.status = 'WORKING';
      agent.currentTaskId = 'task-1';

      await service.completeTask('exec-1', { result: 'done' });

      expect(service.getActiveAgents()[0].status).toBe('IDLE');
    });
  });

  // =========================================================================
  // assignTasks
  // =========================================================================

  describe('assignTasks', () => {
    it('should assign available tasks to IDLE agents', async () => {
      // First spawn an agent
      prisma.agentExecution.create.mockResolvedValue(makeExecution({ id: 'exec-1' }));
      await service.spawnTeam('user-1', 'Task', [AgentRole.BACKEND]);

      taskManager.getAvailableTasks.mockResolvedValue(['task-1', 'task-2']);
      taskManager.assignTask.mockResolvedValue({});

      const assignments = await service.assignTasks('user-1');

      expect(assignments).toHaveLength(1);
      expect(assignments[0]).toMatchObject({ agentId: 'exec-1', taskId: 'task-1' });
    });

    it('should not assign tasks to non-IDLE agents', async () => {
      prisma.agentExecution.create.mockResolvedValue(makeExecution({ id: 'exec-1' }));
      await service.spawnTeam('user-1', 'Task', [AgentRole.BACKEND]);

      // Put the agent in WORKING state
      service.getActiveAgents()[0].status = 'WORKING';

      taskManager.getAvailableTasks.mockResolvedValue(['task-1']);

      const assignments = await service.assignTasks('user-1');

      expect(assignments).toHaveLength(0);
      expect(taskManager.assignTask).not.toHaveBeenCalled();
    });

    it('should update agent status to WORKING after assignment', async () => {
      prisma.agentExecution.create.mockResolvedValue(makeExecution({ id: 'exec-1' }));
      await service.spawnTeam('user-1', 'Task', [AgentRole.BACKEND]);

      taskManager.getAvailableTasks.mockResolvedValue(['task-99']);
      taskManager.assignTask.mockResolvedValue({});

      await service.assignTasks('user-1');

      expect(service.getActiveAgents()[0].status).toBe('WORKING');
    });

    it('should set agent currentTaskId after assignment', async () => {
      prisma.agentExecution.create.mockResolvedValue(makeExecution({ id: 'exec-1' }));
      await service.spawnTeam('user-1', 'Task', [AgentRole.BACKEND]);

      taskManager.getAvailableTasks.mockResolvedValue(['task-42']);
      taskManager.assignTask.mockResolvedValue({});

      await service.assignTasks('user-1');

      expect(service.getActiveAgents()[0].currentTaskId).toBe('task-42');
    });

    it('should return empty assignments when no tasks are available', async () => {
      prisma.agentExecution.create.mockResolvedValue(makeExecution({ id: 'exec-1' }));
      await service.spawnTeam('user-1', 'Task', [AgentRole.BACKEND]);

      taskManager.getAvailableTasks.mockResolvedValue([]);

      const assignments = await service.assignTasks('user-1');

      expect(assignments).toHaveLength(0);
    });

    it('should return empty assignments when no agents are registered', async () => {
      taskManager.getAvailableTasks.mockResolvedValue(['task-1']);

      const assignments = await service.assignTasks('user-1');

      expect(assignments).toHaveLength(0);
    });

    it('should skip assignment and continue when taskManager.assignTask throws', async () => {
      prisma.agentExecution.create
        .mockResolvedValueOnce(makeExecution({ id: 'exec-1' }))
        .mockResolvedValueOnce(makeExecution({ id: 'exec-2' }));
      await service.spawnTeam('user-1', 'Task', [AgentRole.BACKEND, AgentRole.FRONTEND]);

      taskManager.getAvailableTasks.mockResolvedValue(['task-fail', 'task-ok']);
      taskManager.assignTask
        .mockRejectedValueOnce(new Error('Assignment failed'))
        .mockResolvedValueOnce({});

      // Should not throw — failed assignment is logged and skipped
      const assignments = await service.assignTasks('user-1');

      // The second agent should get the second task
      expect(assignments).toHaveLength(1);
    });
  });

  // =========================================================================
  // completeTask
  // =========================================================================

  describe('completeTask', () => {
    it('should mark the agent status as IDLE after completing a task', async () => {
      prisma.agentExecution.create.mockResolvedValue(makeExecution({ id: 'exec-1' }));
      await service.spawnTeam('user-1', 'Task', [AgentRole.BACKEND]);

      const agent = service.getActiveAgents()[0];
      agent.status = 'WORKING';
      agent.currentTaskId = 'task-1';

      taskManager.updateTask.mockResolvedValue({});
      prisma.agentExecution.update.mockResolvedValue({});

      await service.completeTask('exec-1', { result: 'success' });

      expect(agent.status).toBe('IDLE');
    });

    it('should clear currentTaskId on the agent after completion', async () => {
      prisma.agentExecution.create.mockResolvedValue(makeExecution({ id: 'exec-1' }));
      await service.spawnTeam('user-1', 'Task', [AgentRole.BACKEND]);

      const agent = service.getActiveAgents()[0];
      agent.status = 'WORKING';
      agent.currentTaskId = 'task-99';

      taskManager.updateTask.mockResolvedValue({});
      prisma.agentExecution.update.mockResolvedValue({});

      await service.completeTask('exec-1', {});

      expect(agent.currentTaskId).toBeNull();
    });

    it('should call taskManager.updateTask with COMPLETED status', async () => {
      prisma.agentExecution.create.mockResolvedValue(makeExecution({ id: 'exec-1' }));
      await service.spawnTeam('user-1', 'Task', [AgentRole.BACKEND]);

      const agent = service.getActiveAgents()[0];
      agent.status = 'WORKING';
      agent.currentTaskId = 'task-5';

      taskManager.updateTask.mockResolvedValue({});
      prisma.agentExecution.update.mockResolvedValue({});

      await service.completeTask('exec-1', { data: 'result' });

      expect(taskManager.updateTask).toHaveBeenCalledWith('task-5', { status: 'COMPLETED' });
    });

    it('should persist SUCCESS status to AgentExecution in the database', async () => {
      prisma.agentExecution.create.mockResolvedValue(makeExecution({ id: 'exec-1' }));
      await service.spawnTeam('user-1', 'Task', [AgentRole.BACKEND]);

      const agent = service.getActiveAgents()[0];
      agent.status = 'WORKING';
      agent.currentTaskId = 'task-5';

      taskManager.updateTask.mockResolvedValue({});
      prisma.agentExecution.update.mockResolvedValue({});

      await service.completeTask('exec-1', { summary: 'done' });

      expect(prisma.agentExecution.update).toHaveBeenCalledWith({
        where: { id: 'exec-1' },
        data: expect.objectContaining({
          status: 'SUCCESS',
          completedAt: expect.any(Date),
        }),
      });
    });

    it('should do nothing when agentId is not found', async () => {
      // No agents spawned — safe no-op
      await service.completeTask('nonexistent-agent', {});

      expect(taskManager.updateTask).not.toHaveBeenCalled();
      expect(prisma.agentExecution.update).not.toHaveBeenCalled();
    });

    it('should do nothing when agent has no currentTaskId', async () => {
      prisma.agentExecution.create.mockResolvedValue(makeExecution({ id: 'exec-1' }));
      await service.spawnTeam('user-1', 'Task', [AgentRole.BACKEND]);

      // Agent is IDLE with no currentTaskId — completeTask should be a no-op
      await service.completeTask('exec-1', {});

      expect(taskManager.updateTask).not.toHaveBeenCalled();
      expect(prisma.agentExecution.update).not.toHaveBeenCalled();
    });
  });

  // =========================================================================
  // failTask
  // =========================================================================

  describe('failTask', () => {
    it('should mark the agent status as FAILED', async () => {
      prisma.agentExecution.create.mockResolvedValue(makeExecution({ id: 'exec-1' }));
      await service.spawnTeam('user-1', 'Task', [AgentRole.BACKEND]);

      const agent = service.getActiveAgents()[0];
      agent.status = 'WORKING';
      agent.currentTaskId = 'task-1';

      taskManager.updateTask.mockResolvedValue({});
      prisma.agentExecution.update.mockResolvedValue({});

      await service.failTask('exec-1', 'Out of memory');

      expect(agent.status).toBe('FAILED');
    });

    it('should clear currentTaskId after failure', async () => {
      prisma.agentExecution.create.mockResolvedValue(makeExecution({ id: 'exec-1' }));
      await service.spawnTeam('user-1', 'Task', [AgentRole.BACKEND]);

      const agent = service.getActiveAgents()[0];
      agent.status = 'WORKING';
      agent.currentTaskId = 'task-7';

      taskManager.updateTask.mockResolvedValue({});
      prisma.agentExecution.update.mockResolvedValue({});

      await service.failTask('exec-1', 'error');

      expect(agent.currentTaskId).toBeNull();
    });

    it('should requeue the task back to PENDING so it can be retried', async () => {
      prisma.agentExecution.create.mockResolvedValue(makeExecution({ id: 'exec-1' }));
      await service.spawnTeam('user-1', 'Task', [AgentRole.BACKEND]);

      const agent = service.getActiveAgents()[0];
      agent.status = 'WORKING';
      agent.currentTaskId = 'task-requeue';

      taskManager.updateTask.mockResolvedValue({});
      prisma.agentExecution.update.mockResolvedValue({});

      await service.failTask('exec-1', 'timeout');

      expect(taskManager.updateTask).toHaveBeenCalledWith('task-requeue', { status: 'PENDING' });
    });

    it('should persist FAILED status and error to AgentExecution in the database', async () => {
      prisma.agentExecution.create.mockResolvedValue(makeExecution({ id: 'exec-1' }));
      await service.spawnTeam('user-1', 'Task', [AgentRole.BACKEND]);

      const agent = service.getActiveAgents()[0];
      agent.status = 'WORKING';
      agent.currentTaskId = 'task-3';

      taskManager.updateTask.mockResolvedValue({});
      prisma.agentExecution.update.mockResolvedValue({});

      await service.failTask('exec-1', 'Unhandled exception');

      expect(prisma.agentExecution.update).toHaveBeenCalledWith({
        where: { id: 'exec-1' },
        data: expect.objectContaining({
          status: 'FAILED',
          error: 'Unhandled exception',
          completedAt: expect.any(Date),
        }),
      });
    });

    it('should do nothing when agentId is not found', async () => {
      await service.failTask('nonexistent-agent', 'error');

      expect(taskManager.updateTask).not.toHaveBeenCalled();
      expect(prisma.agentExecution.update).not.toHaveBeenCalled();
    });

    it('should do nothing when agent has no currentTaskId', async () => {
      prisma.agentExecution.create.mockResolvedValue(makeExecution({ id: 'exec-1' }));
      await service.spawnTeam('user-1', 'Task', [AgentRole.BACKEND]);

      // Agent is IDLE — failTask should be a no-op
      await service.failTask('exec-1', 'spurious error');

      expect(taskManager.updateTask).not.toHaveBeenCalled();
      expect(prisma.agentExecution.update).not.toHaveBeenCalled();
    });
  });

  // =========================================================================
  // detectFileConflicts
  // =========================================================================

  describe('detectFileConflicts', () => {
    it('should return an empty array when no agents are active', () => {
      const conflicts = service.detectFileConflicts();

      expect(conflicts).toEqual([]);
    });

    it('should return an empty array when only one agent is WORKING', async () => {
      prisma.agentExecution.create.mockResolvedValue(makeExecution({ id: 'exec-1' }));
      await service.spawnTeam('user-1', 'Task', [AgentRole.BACKEND]);

      const agent = service.getActiveAgents()[0];
      agent.status = 'WORKING';

      const conflicts = service.detectFileConflicts();

      expect(conflicts).toEqual([]);
    });

    it('should detect a conflict when two WORKING agents share a file scope', async () => {
      prisma.agentExecution.create
        .mockResolvedValueOnce(makeExecution({ id: 'exec-1' }))
        .mockResolvedValueOnce(makeExecution({ id: 'exec-2' }));
      await service.spawnTeam('user-1', 'Task', [AgentRole.BACKEND, AgentRole.BACKEND]);

      // Both agents are WORKING with identical file scopes
      const agents = service.getActiveAgents();
      agents[0].status = 'WORKING';
      agents[1].status = 'WORKING';

      const conflicts = service.detectFileConflicts();

      expect(conflicts.length).toBeGreaterThanOrEqual(1);
      expect(conflicts[0].file).toBe('backend/src/**');
      expect(conflicts[0].agents).toContain('exec-1');
      expect(conflicts[0].agents).toContain('exec-2');
    });

    it('should not report conflicts for IDLE agents', async () => {
      prisma.agentExecution.create
        .mockResolvedValueOnce(makeExecution({ id: 'exec-1' }))
        .mockResolvedValueOnce(makeExecution({ id: 'exec-2' }));
      await service.spawnTeam('user-1', 'Task', [AgentRole.BACKEND, AgentRole.BACKEND]);

      // Both agents remain IDLE
      const conflicts = service.detectFileConflicts();

      expect(conflicts).toEqual([]);
    });

    it('should not report conflicts between agents with non-overlapping file scopes', async () => {
      prisma.agentExecution.create
        .mockResolvedValueOnce(makeExecution({ id: 'exec-fe' }))
        .mockResolvedValueOnce(makeExecution({ id: 'exec-be' }));
      await service.spawnTeam('user-1', 'Task', [AgentRole.FRONTEND, AgentRole.BACKEND]);

      const agents = service.getActiveAgents();
      agents.forEach((a) => (a.status = 'WORKING'));

      const conflicts = service.detectFileConflicts();

      // frontend/** and backend/src/** don't overlap
      expect(conflicts).toEqual([]);
    });
  });
});
