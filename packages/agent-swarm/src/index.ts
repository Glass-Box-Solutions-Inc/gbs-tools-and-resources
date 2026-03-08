// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology

// Module
export { AgentSwarmModule } from './agent-swarm.module.js';

// Services
export { TaskManagerService } from './task-manager.service.js';
export { AgentCoordinatorService, AgentInstance } from './agent-coordinator.service.js';
export { SwarmService } from './swarm.service.js';

// Gateway
export { SwarmGateway } from './swarm.gateway.js';

// Controller
export { SwarmController } from './swarm.controller.js';

// DTOs
export {
  CreateTaskDto,
  UpdateTaskDto,
  SpawnSwarmDto,
  CompleteAgentTaskDto,
  FailAgentTaskDto,
  AgentRole,
  TaskStatus,
} from './dto/swarm.dto.js';

// Types
export * from './agent-swarm.types.js';

// Prisma (standalone mode)
export { PrismaService } from './prisma.service.js';

// Decorators
export { CurrentUser } from './decorators/current-user.decorator.js';
