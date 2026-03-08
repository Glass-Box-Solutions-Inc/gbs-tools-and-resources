// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology

// Prevent ESM import.meta issues in Jest
jest.mock('../../../generated/prisma/client', () => ({
  PrismaClient: jest.fn(),
}));

jest.mock('@prisma/adapter-pg', () => ({
  PrismaPg: jest.fn(),
}));

import { Test, TestingModule } from '@nestjs/testing';
import { SwarmService } from './swarm.service.js';
import { PrismaService } from '../prisma/prisma.service.js';
import { TaskManagerService } from './task-manager.service.js';
import { AgentCoordinatorService } from './agent-coordinator.service.js';
import { AgentRole } from './dto/swarm.dto.js';
import type { AgentInstance } from './agent-coordinator.service.js';

// ---------------------------------------------------------------------------
// Mock factories
// ---------------------------------------------------------------------------

const mockPrismaService = () => ({
  agentExecution: {
    findMany: jest.fn(),
  },
});

const mockTaskManagerService = () => ({
  validateDAG: jest.fn(),
  listTasks: jest.fn(),
  getAvailableTasks: jest.fn(),
  assignTask: jest.fn(),
  createTask: jest.fn(),
  getTask: jest.fn(),
  updateTask: jest.fn(),
});

const mockAgentCoordinatorService = () => ({
  spawnTeam: jest.fn(),
  assignTasks: jest.fn(),
  detectFileConflicts: jest.fn(),
  getActiveAgents: jest.fn(),
  completeTask: jest.fn(),
  failTask: jest.fn(),
});

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeAgentInstance(overrides: Partial<AgentInstance> = {}): AgentInstance {
  return {
    id: 'agent-1',
    role: AgentRole.BACKEND,
    status: 'IDLE',
    currentTaskId: null,
    assignedFiles: ['backend/src/**'],
    ...overrides,
  };
}

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

function makeExecution(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    id: 'exec-1',
    agentRole: 'Backend',
    status: 'SUCCESS',
    output: {},
    error: null,
    startedAt: new Date('2025-01-01'),
    completedAt: new Date('2025-01-01'),
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// SwarmService tests
// ---------------------------------------------------------------------------

describe('SwarmService', () => {
  let service: SwarmService;
  let prisma: ReturnType<typeof mockPrismaService>;
  let taskManager: ReturnType<typeof mockTaskManagerService>;
  let coordinator: ReturnType<typeof mockAgentCoordinatorService>;

  beforeEach(async () => {
    prisma = mockPrismaService();
    taskManager = mockTaskManagerService();
    coordinator = mockAgentCoordinatorService();

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        SwarmService,
        { provide: PrismaService, useValue: prisma },
        { provide: TaskManagerService, useValue: taskManager },
        { provide: AgentCoordinatorService, useValue: coordinator },
      ],
    }).compile();

    service = module.get<SwarmService>(SwarmService);
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  // =========================================================================
  // spawnSwarm
  // =========================================================================

  describe('spawnSwarm', () => {
    const objective = 'Build the authentication module';
    const roles = [AgentRole.BACKEND, AgentRole.TESTS];

    beforeEach(() => {
      coordinator.spawnTeam.mockResolvedValue([
        makeAgentInstance({ id: 'agent-be', role: AgentRole.BACKEND }),
        makeAgentInstance({ id: 'agent-ts', role: AgentRole.TESTS, assignedFiles: ['backend/test/**'] }),
      ]);
      coordinator.assignTasks.mockResolvedValue([
        { agentId: 'agent-be', taskId: 'task-1' },
      ]);
      coordinator.detectFileConflicts.mockReturnValue([]);
    });

    it('should call coordinator.spawnTeam with userId, objective, and roles', async () => {
      await service.spawnSwarm('user-1', objective, roles);

      expect(coordinator.spawnTeam).toHaveBeenCalledWith('user-1', objective, roles);
    });

    it('should call coordinator.assignTasks after spawning agents', async () => {
      await service.spawnSwarm('user-1', objective, roles);

      expect(coordinator.assignTasks).toHaveBeenCalledWith('user-1');
    });

    it('should call coordinator.detectFileConflicts', async () => {
      await service.spawnSwarm('user-1', objective, roles);

      expect(coordinator.detectFileConflicts).toHaveBeenCalled();
    });

    it('should return a swarmId, objective, agents, assignments, and conflicts', async () => {
      const result = await service.spawnSwarm('user-1', objective, roles);

      expect(result).toHaveProperty('swarmId');
      expect(result.objective).toBe(objective);
      expect(result.agents).toHaveLength(2);
      expect(result.assignments).toEqual([{ agentId: 'agent-be', taskId: 'task-1' }]);
      expect(result.conflicts).toEqual([]);
    });

    it('should return agent summaries with id, role, and status fields', async () => {
      const result = await service.spawnSwarm('user-1', objective, roles);

      for (const agent of result.agents) {
        expect(agent).toHaveProperty('id');
        expect(agent).toHaveProperty('role');
        expect(agent).toHaveProperty('status');
        // assignedFiles should NOT be leaked into the summary
        expect(agent).not.toHaveProperty('assignedFiles');
      }
    });

    it('should generate a unique swarmId on each call', async () => {
      const result1 = await service.spawnSwarm('user-1', objective, roles);
      // Add a small delay to guarantee different Date.now() values
      await new Promise((resolve) => setTimeout(resolve, 2));
      const result2 = await service.spawnSwarm('user-1', objective, roles);

      expect(result1.swarmId).not.toBe(result2.swarmId);
    });

    it('should validate DAG when taskIds are provided', async () => {
      taskManager.validateDAG.mockResolvedValue({ valid: true, cycles: [] });

      await service.spawnSwarm('user-1', objective, roles, ['task-1', 'task-2']);

      expect(taskManager.validateDAG).toHaveBeenCalledWith('user-1');
    });

    it('should NOT validate DAG when no taskIds are provided', async () => {
      await service.spawnSwarm('user-1', objective, roles);

      expect(taskManager.validateDAG).not.toHaveBeenCalled();
    });

    it('should NOT validate DAG when taskIds is an empty array', async () => {
      await service.spawnSwarm('user-1', objective, roles, []);

      expect(taskManager.validateDAG).not.toHaveBeenCalled();
    });

    it('should still complete spawn even when DAG has cycles (logs warning only)', async () => {
      taskManager.validateDAG.mockResolvedValue({
        valid: false,
        cycles: [['task-1', 'task-2']],
      });

      // Should resolve without throwing
      const result = await service.spawnSwarm('user-1', objective, roles, ['task-1', 'task-2']);

      expect(result).toHaveProperty('swarmId');
    });

    it('should include file conflicts in the result when conflicts are detected', async () => {
      coordinator.detectFileConflicts.mockReturnValue([
        { file: 'backend/src/app.ts', agents: ['agent-1', 'agent-2'] },
      ]);

      const result = await service.spawnSwarm('user-1', objective, roles);

      expect(result.conflicts).toHaveLength(1);
      expect(result.conflicts[0].file).toBe('backend/src/app.ts');
    });

    it('should handle an empty roles array and return zero agents', async () => {
      coordinator.spawnTeam.mockResolvedValue([]);
      coordinator.assignTasks.mockResolvedValue([]);

      const result = await service.spawnSwarm('user-1', objective, []);

      expect(result.agents).toHaveLength(0);
    });
  });

  // =========================================================================
  // getStatus
  // =========================================================================

  describe('getStatus', () => {
    it('should call coordinator.getActiveAgents and taskManager.listTasks', async () => {
      coordinator.getActiveAgents.mockReturnValue([]);
      taskManager.listTasks.mockResolvedValue([]);
      coordinator.detectFileConflicts.mockReturnValue([]);

      await service.getStatus('user-1');

      expect(coordinator.getActiveAgents).toHaveBeenCalled();
      expect(taskManager.listTasks).toHaveBeenCalledWith('user-1');
    });

    it('should count active agents by status', async () => {
      coordinator.getActiveAgents.mockReturnValue([
        makeAgentInstance({ id: 'a1', status: 'IDLE' }),
        makeAgentInstance({ id: 'a2', status: 'WORKING' }),
        makeAgentInstance({ id: 'a3', status: 'WORKING' }),
        makeAgentInstance({ id: 'a4', status: 'BLOCKED' }),
        makeAgentInstance({ id: 'a5', status: 'COMPLETED' }),
        makeAgentInstance({ id: 'a6', status: 'FAILED' }),
      ]);
      taskManager.listTasks.mockResolvedValue([]);
      coordinator.detectFileConflicts.mockReturnValue([]);

      const result = await service.getStatus('user-1');

      expect(result.agentsByStatus.IDLE).toBe(1);
      expect(result.agentsByStatus.WORKING).toBe(2);
      expect(result.agentsByStatus.BLOCKED).toBe(1);
      expect(result.agentsByStatus.COMPLETED).toBe(1);
      expect(result.agentsByStatus.FAILED).toBe(1);
    });

    it('should count tasks by status', async () => {
      coordinator.getActiveAgents.mockReturnValue([]);
      taskManager.listTasks.mockResolvedValue([
        makeTask({ status: 'PENDING' }),
        makeTask({ id: 'task-2', status: 'PENDING' }),
        makeTask({ id: 'task-3', status: 'IN_PROGRESS' }),
        makeTask({ id: 'task-4', status: 'COMPLETED' }),
      ]);
      coordinator.detectFileConflicts.mockReturnValue([]);

      const result = await service.getStatus('user-1');

      expect(result.tasks.PENDING).toBe(2);
      expect(result.tasks.IN_PROGRESS).toBe(1);
      expect(result.tasks.COMPLETED).toBe(1);
    });

    it('should calculate progress as percentage of completed tasks', async () => {
      coordinator.getActiveAgents.mockReturnValue([]);
      taskManager.listTasks.mockResolvedValue([
        makeTask({ status: 'COMPLETED' }),
        makeTask({ id: 'task-2', status: 'COMPLETED' }),
        makeTask({ id: 'task-3', status: 'PENDING' }),
        makeTask({ id: 'task-4', status: 'PENDING' }),
      ]);
      coordinator.detectFileConflicts.mockReturnValue([]);

      const result = await service.getStatus('user-1');

      // 2 of 4 completed = 50%
      expect(result.progress).toBe(50);
    });

    it('should return 0 progress when there are no tasks', async () => {
      coordinator.getActiveAgents.mockReturnValue([]);
      taskManager.listTasks.mockResolvedValue([]);
      coordinator.detectFileConflicts.mockReturnValue([]);

      const result = await service.getStatus('user-1');

      expect(result.progress).toBe(0);
    });

    it('should return 100 progress when all tasks are completed', async () => {
      coordinator.getActiveAgents.mockReturnValue([]);
      taskManager.listTasks.mockResolvedValue([
        makeTask({ status: 'COMPLETED' }),
        makeTask({ id: 'task-2', status: 'COMPLETED' }),
      ]);
      coordinator.detectFileConflicts.mockReturnValue([]);

      const result = await service.getStatus('user-1');

      expect(result.progress).toBe(100);
    });

    it('should include agent details with id, role, status, and currentTaskId', async () => {
      const agent = makeAgentInstance({
        id: 'agent-working',
        status: 'WORKING',
        currentTaskId: 'task-99',
      });
      coordinator.getActiveAgents.mockReturnValue([agent]);
      taskManager.listTasks.mockResolvedValue([]);
      coordinator.detectFileConflicts.mockReturnValue([]);

      const result = await service.getStatus('user-1');

      expect(result.agents).toHaveLength(1);
      expect(result.agents[0]).toEqual({
        id: 'agent-working',
        role: AgentRole.BACKEND,
        status: 'WORKING',
        currentTaskId: 'task-99',
      });
    });

    it('should include conflicts from coordinator.detectFileConflicts', async () => {
      coordinator.getActiveAgents.mockReturnValue([]);
      taskManager.listTasks.mockResolvedValue([]);
      coordinator.detectFileConflicts.mockReturnValue([
        { file: 'backend/src/main.ts', agents: ['agent-1', 'agent-2'] },
      ]);

      const result = await service.getStatus('user-1');

      expect(result.conflicts).toHaveLength(1);
      expect(result.conflicts[0]).toMatchObject({
        file: 'backend/src/main.ts',
        agents: ['agent-1', 'agent-2'],
      });
    });
  });

  // =========================================================================
  // getExecutionHistory
  // =========================================================================

  describe('getExecutionHistory', () => {
    const TEST_USER_ID = 'user-1';

    it('should query agentExecution records scoped to userId, ordered by startedAt desc', async () => {
      const executions = [makeExecution(), makeExecution({ id: 'exec-2' })];
      prisma.agentExecution.findMany.mockResolvedValue(executions);

      const result = await service.getExecutionHistory(TEST_USER_ID, 50);

      expect(prisma.agentExecution.findMany).toHaveBeenCalledWith({
        where: { task: { userId: TEST_USER_ID } },
        orderBy: { startedAt: 'desc' },
        take: 50,
      });
      expect(result).toEqual(executions);
    });

    it('should use default limit of 50 when no limit argument is provided', async () => {
      prisma.agentExecution.findMany.mockResolvedValue([]);

      await service.getExecutionHistory(TEST_USER_ID);

      expect(prisma.agentExecution.findMany).toHaveBeenCalledWith({
        where: { task: { userId: TEST_USER_ID } },
        orderBy: { startedAt: 'desc' },
        take: 50,
      });
    });

    it('should respect a custom limit', async () => {
      prisma.agentExecution.findMany.mockResolvedValue([]);

      await service.getExecutionHistory(TEST_USER_ID, 10);

      expect(prisma.agentExecution.findMany).toHaveBeenCalledWith({
        where: { task: { userId: TEST_USER_ID } },
        orderBy: { startedAt: 'desc' },
        take: 10,
      });
    });

    it('should return an empty array when no executions exist', async () => {
      prisma.agentExecution.findMany.mockResolvedValue([]);

      const result = await service.getExecutionHistory(TEST_USER_ID);

      expect(result).toEqual([]);
    });
  });
});
