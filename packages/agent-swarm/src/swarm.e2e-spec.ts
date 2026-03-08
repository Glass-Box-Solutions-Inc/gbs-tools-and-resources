// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology

/**
 * Agent Swarm E2E Tests
 *
 * Covers the multi-agent task orchestration system:
 * - POST  /api/swarm/tasks         — create a task
 * - GET   /api/swarm/tasks         — list tasks (with optional filters)
 * - GET   /api/swarm/tasks/:id     — get a single task
 * - PATCH /api/swarm/tasks/:id     — update a task
 * - GET   /api/swarm/status        — get swarm status for the current user
 * - GET   /api/swarm/agents        — list active in-memory agents
 * - POST  /api/swarm/spawn         — spawn a multi-agent team
 * - GET   /api/swarm/history       — execution history
 * - Auth enforcement               — unauthenticated requests receive 401
 */

import { INestApplication } from '@nestjs/common';
import request from 'supertest';
import { TestSetup } from './setup';

describe('Agent Swarm E2E Tests', () => {
  let app: INestApplication;

  beforeAll(async () => {
    app = await TestSetup.createTestApp();
  });

  // Targeted teardown: remove swarm-related rows in FK-safe order.
  afterEach(async () => {
    const prisma = TestSetup.prisma;
    await prisma.$transaction([
      prisma.agentExecution.deleteMany(),
      prisma.agentTask.deleteMany(),
      prisma.session.deleteMany(),
      prisma.user.deleteMany(),
    ]);
  });

  afterAll(async () => {
    await TestSetup.closeApp();
  });

  // ==========================================================================
  // Helpers
  // ==========================================================================

  /** Minimal valid CreateTaskDto payload */
  const buildTaskPayload = (overrides: Record<string, unknown> = {}) => ({
    title: 'Implement user authentication',
    description: 'Add JWT-based auth to the API',
    ...overrides,
  });

  // ==========================================================================
  // POST /api/swarm/tasks — Create Task
  // ==========================================================================

  describe('POST /api/swarm/tasks', () => {
    it('should create a task with the default PENDING status', async () => {
      const { token } = await TestSetup.createAuthenticatedUser();

      const response = await request(app.getHttpServer())
        .post('/api/swarm/tasks')
        .set('Authorization', `Bearer ${token}`)
        .send(buildTaskPayload())
        .expect(201);

      expect(response.body).toHaveProperty('id');
      expect(response.body).toHaveProperty('title', 'Implement user authentication');
      expect(response.body).toHaveProperty('description', 'Add JWT-based auth to the API');
      expect(response.body).toHaveProperty('status', 'PENDING');
      expect(response.body).toHaveProperty('priority', 0);
      expect(response.body).toHaveProperty('createdAt');
    });

    it('should create a task with a custom priority', async () => {
      const { token } = await TestSetup.createAuthenticatedUser();

      const response = await request(app.getHttpServer())
        .post('/api/swarm/tasks')
        .set('Authorization', `Bearer ${token}`)
        .send(buildTaskPayload({ priority: 5 }))
        .expect(201);

      expect(response.body).toHaveProperty('priority', 5);
    });

    it('should create a task with blockedBy dependencies', async () => {
      const { user, token } = await TestSetup.createAuthenticatedUser();

      // Create a dependency task directly in the DB
      const depTask = await TestSetup.prisma.agentTask.create({
        data: {
          userId: user.id,
          title: 'Database schema migration',
          description: 'Must run before auth task',
          status: 'PENDING',
          blockedBy: [],
          blocks: [],
        },
      });

      const response = await request(app.getHttpServer())
        .post('/api/swarm/tasks')
        .set('Authorization', `Bearer ${token}`)
        .send(buildTaskPayload({ blockedBy: [depTask.id] }))
        .expect(201);

      expect(response.body).toHaveProperty('blockedBy');
      expect(response.body.blockedBy).toContain(depTask.id);
    });

    it('should return 400 when blockedBy references a non-existent task', async () => {
      const { token } = await TestSetup.createAuthenticatedUser();

      await request(app.getHttpServer())
        .post('/api/swarm/tasks')
        .set('Authorization', `Bearer ${token}`)
        .send(buildTaskPayload({ blockedBy: ['nonexistent-task-id'] }))
        .expect(400);
    });

    it('should return 400 when title is missing', async () => {
      const { token } = await TestSetup.createAuthenticatedUser();

      await request(app.getHttpServer())
        .post('/api/swarm/tasks')
        .set('Authorization', `Bearer ${token}`)
        .send({ description: 'No title provided' })
        .expect(400);
    });

    it('should return 400 when description is missing', async () => {
      const { token } = await TestSetup.createAuthenticatedUser();

      await request(app.getHttpServer())
        .post('/api/swarm/tasks')
        .set('Authorization', `Bearer ${token}`)
        .send({ title: 'No description' })
        .expect(400);
    });

    it('should return 401 when no token is provided', async () => {
      await request(app.getHttpServer())
        .post('/api/swarm/tasks')
        .send(buildTaskPayload())
        .expect(401);
    });
  });

  // ==========================================================================
  // GET /api/swarm/tasks — List Tasks
  // ==========================================================================

  describe('GET /api/swarm/tasks', () => {
    it('should return only the current user\'s tasks', async () => {
      const { user, token } = await TestSetup.createAuthenticatedUser();
      const { user: otherUser } = await TestSetup.createAuthenticatedUser();

      // Create tasks for both users
      await TestSetup.prisma.agentTask.createMany({
        data: [
          {
            userId: user.id,
            title: 'My Task A',
            description: 'User task',
            status: 'PENDING',
            blockedBy: [],
            blocks: [],
          },
          {
            userId: user.id,
            title: 'My Task B',
            description: 'User task 2',
            status: 'IN_PROGRESS',
            blockedBy: [],
            blocks: [],
          },
          {
            userId: otherUser.id,
            title: 'Other User Task',
            description: 'Should not appear',
            status: 'PENDING',
            blockedBy: [],
            blocks: [],
          },
        ],
      });

      const response = await request(app.getHttpServer())
        .get('/api/swarm/tasks')
        .set('Authorization', `Bearer ${token}`)
        .expect(200);

      expect(Array.isArray(response.body)).toBe(true);
      expect(response.body.length).toBe(2);
      response.body.forEach((task: Record<string, unknown>) => {
        expect(task).toHaveProperty('userId', user.id);
      });
    });

    it('should filter tasks by status', async () => {
      const { user, token } = await TestSetup.createAuthenticatedUser();

      await TestSetup.prisma.agentTask.createMany({
        data: [
          {
            userId: user.id,
            title: 'Pending Task',
            description: 'Still pending',
            status: 'PENDING',
            blockedBy: [],
            blocks: [],
          },
          {
            userId: user.id,
            title: 'Completed Task',
            description: 'Already done',
            status: 'COMPLETED',
            blockedBy: [],
            blocks: [],
          },
        ],
      });

      const response = await request(app.getHttpServer())
        .get('/api/swarm/tasks?status=PENDING')
        .set('Authorization', `Bearer ${token}`)
        .expect(200);

      expect(response.body.length).toBe(1);
      expect(response.body[0].status).toBe('PENDING');
    });

    it('should return an empty array when the user has no tasks', async () => {
      const { token } = await TestSetup.createAuthenticatedUser();

      const response = await request(app.getHttpServer())
        .get('/api/swarm/tasks')
        .set('Authorization', `Bearer ${token}`)
        .expect(200);

      expect(Array.isArray(response.body)).toBe(true);
      expect(response.body.length).toBe(0);
    });

    it('should return 401 when no token is provided', async () => {
      await request(app.getHttpServer()).get('/api/swarm/tasks').expect(401);
    });
  });

  // ==========================================================================
  // GET /api/swarm/tasks/:id — Get Single Task
  // ==========================================================================

  describe('GET /api/swarm/tasks/:id', () => {
    it('should return a task by ID', async () => {
      const { user, token } = await TestSetup.createAuthenticatedUser();

      const task = await TestSetup.prisma.agentTask.create({
        data: {
          userId: user.id,
          title: 'Specific Task',
          description: 'Return this one',
          status: 'PENDING',
          blockedBy: [],
          blocks: [],
        },
      });

      const response = await request(app.getHttpServer())
        .get(`/api/swarm/tasks/${task.id}`)
        .set('Authorization', `Bearer ${token}`)
        .expect(200);

      expect(response.body).toHaveProperty('id', task.id);
      expect(response.body).toHaveProperty('title', 'Specific Task');
    });

    it('should return 404 when the task does not exist', async () => {
      const { token } = await TestSetup.createAuthenticatedUser();

      await request(app.getHttpServer())
        .get('/api/swarm/tasks/nonexistent-task-id')
        .set('Authorization', `Bearer ${token}`)
        .expect(404);
    });

    it('should return 401 when no token is provided', async () => {
      await request(app.getHttpServer())
        .get('/api/swarm/tasks/some-id')
        .expect(401);
    });
  });

  // ==========================================================================
  // PATCH /api/swarm/tasks/:id — Update Task
  // ==========================================================================

  describe('PATCH /api/swarm/tasks/:id', () => {
    it('should update a task status', async () => {
      const { user, token } = await TestSetup.createAuthenticatedUser();

      const task = await TestSetup.prisma.agentTask.create({
        data: {
          userId: user.id,
          title: 'Task to update',
          description: 'Will be updated',
          status: 'PENDING',
          blockedBy: [],
          blocks: [],
        },
      });

      const response = await request(app.getHttpServer())
        .patch(`/api/swarm/tasks/${task.id}`)
        .set('Authorization', `Bearer ${token}`)
        .send({ status: 'IN_PROGRESS' })
        .expect(200);

      expect(response.body).toHaveProperty('status', 'IN_PROGRESS');
    });

    it('should set completedAt when status is updated to COMPLETED', async () => {
      const { user, token } = await TestSetup.createAuthenticatedUser();

      const task = await TestSetup.prisma.agentTask.create({
        data: {
          userId: user.id,
          title: 'Task to complete',
          description: 'Will be completed',
          status: 'IN_PROGRESS',
          blockedBy: [],
          blocks: [],
        },
      });

      const response = await request(app.getHttpServer())
        .patch(`/api/swarm/tasks/${task.id}`)
        .set('Authorization', `Bearer ${token}`)
        .send({ status: 'COMPLETED' })
        .expect(200);

      expect(response.body).toHaveProperty('status', 'COMPLETED');
      expect(response.body.completedAt).not.toBeNull();
    });

    it('should return 404 when updating a non-existent task', async () => {
      const { token } = await TestSetup.createAuthenticatedUser();

      await request(app.getHttpServer())
        .patch('/api/swarm/tasks/nonexistent-task-id')
        .set('Authorization', `Bearer ${token}`)
        .send({ status: 'COMPLETED' })
        .expect(404);
    });

    it('should return 401 when no token is provided', async () => {
      await request(app.getHttpServer())
        .patch('/api/swarm/tasks/some-id')
        .send({ status: 'COMPLETED' })
        .expect(401);
    });
  });

  // ==========================================================================
  // GET /api/swarm/status — Swarm Status
  // ==========================================================================

  describe('GET /api/swarm/status', () => {
    it('should return a status summary for the authenticated user', async () => {
      const { user, token } = await TestSetup.createAuthenticatedUser();

      // Seed a couple of tasks so the status is non-trivial
      await TestSetup.prisma.agentTask.createMany({
        data: [
          {
            userId: user.id,
            title: 'Task A',
            description: 'Pending',
            status: 'PENDING',
            blockedBy: [],
            blocks: [],
          },
          {
            userId: user.id,
            title: 'Task B',
            description: 'Completed',
            status: 'COMPLETED',
            blockedBy: [],
            blocks: [],
          },
        ],
      });

      const response = await request(app.getHttpServer())
        .get('/api/swarm/status')
        .set('Authorization', `Bearer ${token}`)
        .expect(200);

      expect(response.body).toHaveProperty('agents');
      expect(response.body).toHaveProperty('tasks');
      expect(response.body).toHaveProperty('progress');
      expect(response.body).toHaveProperty('conflicts');
      expect(response.body).toHaveProperty('agentsByStatus');
      // Progress should be 50% (1 of 2 tasks completed)
      expect(response.body.progress).toBe(50);
    });

    it('should return 0 progress when there are no tasks', async () => {
      const { token } = await TestSetup.createAuthenticatedUser();

      const response = await request(app.getHttpServer())
        .get('/api/swarm/status')
        .set('Authorization', `Bearer ${token}`)
        .expect(200);

      expect(response.body).toHaveProperty('progress', 0);
    });

    it('should return 401 when no token is provided', async () => {
      await request(app.getHttpServer()).get('/api/swarm/status').expect(401);
    });
  });

  // ==========================================================================
  // GET /api/swarm/agents — Active Agents
  // ==========================================================================

  describe('GET /api/swarm/agents', () => {
    it('should return an array of active agents (may be empty before any spawn)', async () => {
      const { token } = await TestSetup.createAuthenticatedUser();

      const response = await request(app.getHttpServer())
        .get('/api/swarm/agents')
        .set('Authorization', `Bearer ${token}`)
        .expect(200);

      expect(Array.isArray(response.body)).toBe(true);
    });

    it('should return 401 when no token is provided', async () => {
      await request(app.getHttpServer()).get('/api/swarm/agents').expect(401);
    });
  });

  // ==========================================================================
  // POST /api/swarm/spawn — Spawn Swarm Team
  // ==========================================================================

  describe('POST /api/swarm/spawn', () => {
    it('should spawn a swarm and return swarmId, agents, and assignments', async () => {
      const { token } = await TestSetup.createAuthenticatedUser();

      const response = await request(app.getHttpServer())
        .post('/api/swarm/spawn')
        .set('Authorization', `Bearer ${token}`)
        .send({
          objective: 'Build the user management feature end-to-end',
          roles: ['Frontend', 'Backend'],
        })
        .expect(201);

      expect(response.body).toHaveProperty('swarmId');
      expect(response.body.swarmId).toMatch(/^swarm-/);
      expect(response.body).toHaveProperty('objective', 'Build the user management feature end-to-end');
      expect(response.body).toHaveProperty('agents');
      expect(Array.isArray(response.body.agents)).toBe(true);
      expect(response.body.agents.length).toBe(2);
      expect(response.body).toHaveProperty('assignments');
      expect(response.body).toHaveProperty('conflicts');
    });

    it('should spawn agents with the correct roles', async () => {
      const { token } = await TestSetup.createAuthenticatedUser();

      const response = await request(app.getHttpServer())
        .post('/api/swarm/spawn')
        .set('Authorization', `Bearer ${token}`)
        .send({
          objective: 'Security audit and documentation',
          roles: ['Security', 'Docs'],
        })
        .expect(201);

      const roles = response.body.agents.map((a: { role: string }) => a.role);
      expect(roles).toContain('Security');
      expect(roles).toContain('Docs');
    });

    it('should return 400 when objective is missing', async () => {
      const { token } = await TestSetup.createAuthenticatedUser();

      await request(app.getHttpServer())
        .post('/api/swarm/spawn')
        .set('Authorization', `Bearer ${token}`)
        .send({ roles: ['Frontend'] })
        .expect(400);
    });

    it('should return 400 when roles array is empty', async () => {
      const { token } = await TestSetup.createAuthenticatedUser();

      await request(app.getHttpServer())
        .post('/api/swarm/spawn')
        .set('Authorization', `Bearer ${token}`)
        .send({ objective: 'some objective', roles: [] })
        .expect(400);
    });

    it('should return 400 when an invalid role is supplied', async () => {
      const { token } = await TestSetup.createAuthenticatedUser();

      await request(app.getHttpServer())
        .post('/api/swarm/spawn')
        .set('Authorization', `Bearer ${token}`)
        .send({ objective: 'some objective', roles: ['InvalidRole'] })
        .expect(400);
    });

    it('should return 401 when no token is provided', async () => {
      await request(app.getHttpServer())
        .post('/api/swarm/spawn')
        .send({ objective: 'test', roles: ['Frontend'] })
        .expect(401);
    });
  });

  // ==========================================================================
  // GET /api/swarm/history — Execution History
  // ==========================================================================

  describe('GET /api/swarm/history', () => {
    it('should return execution history (may be empty)', async () => {
      const { token } = await TestSetup.createAuthenticatedUser();

      const response = await request(app.getHttpServer())
        .get('/api/swarm/history')
        .set('Authorization', `Bearer ${token}`)
        .expect(200);

      expect(Array.isArray(response.body)).toBe(true);
    });

    it('should respect the limit query parameter', async () => {
      // Seed some agent executions
      await TestSetup.prisma.agentExecution.createMany({
        data: Array.from({ length: 5 }, (_, i) => ({
          agentRole: 'Frontend',
          status: 'SUCCESS',
          output: { iteration: i },
        })),
      });

      const { token } = await TestSetup.createAuthenticatedUser();

      const response = await request(app.getHttpServer())
        .get('/api/swarm/history?limit=3')
        .set('Authorization', `Bearer ${token}`)
        .expect(200);

      expect(response.body.length).toBeLessThanOrEqual(3);
    });

    it('should return 401 when no token is provided', async () => {
      await request(app.getHttpServer()).get('/api/swarm/history').expect(401);
    });
  });

  // ==========================================================================
  // Full Task Lifecycle Workflow
  // ==========================================================================

  describe('Full Task Lifecycle', () => {
    it('should complete create → list → update → verify workflow', async () => {
      const { token } = await TestSetup.createAuthenticatedUser();

      // 1. Create
      const createRes = await request(app.getHttpServer())
        .post('/api/swarm/tasks')
        .set('Authorization', `Bearer ${token}`)
        .send(buildTaskPayload({ title: 'Lifecycle Test Task', priority: 3 }))
        .expect(201);

      const taskId = createRes.body.id;
      expect(taskId).toBeDefined();

      // 2. List — verify it appears
      const listRes = await request(app.getHttpServer())
        .get('/api/swarm/tasks')
        .set('Authorization', `Bearer ${token}`)
        .expect(200);

      expect(listRes.body.some((t: { id: string }) => t.id === taskId)).toBe(true);

      // 3. Update status to IN_PROGRESS
      await request(app.getHttpServer())
        .patch(`/api/swarm/tasks/${taskId}`)
        .set('Authorization', `Bearer ${token}`)
        .send({ status: 'IN_PROGRESS', assignee: 'Frontend' })
        .expect(200);

      // 4. Verify the update via GET
      const getRes = await request(app.getHttpServer())
        .get(`/api/swarm/tasks/${taskId}`)
        .set('Authorization', `Bearer ${token}`)
        .expect(200);

      expect(getRes.body.status).toBe('IN_PROGRESS');
      expect(getRes.body.assignee).toBe('Frontend');
    });
  });
});
