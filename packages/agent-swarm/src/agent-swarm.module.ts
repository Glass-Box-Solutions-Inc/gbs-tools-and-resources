// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology

import { Module, DynamicModule } from '@nestjs/common';
import { SwarmController } from './swarm.controller.js';
import { TaskManagerService } from './task-manager.service.js';
import { AgentCoordinatorService } from './agent-coordinator.service.js';
import { SwarmService } from './swarm.service.js';
import { SwarmGateway } from './swarm.gateway.js';
import { PrismaService } from './prisma.service.js';

/**
 * AgentSwarmModule — DAG-based multi-agent task orchestration.
 *
 * Usage:
 *
 * **Standalone mode** (uses built-in PrismaService with agent-swarm schema):
 * ```typescript
 * @Module({ imports: [AgentSwarmModule] })
 * export class AppModule {}
 * ```
 *
 * **Hosted mode** (inject host app's PrismaService, e.g. from Glassy):
 * ```typescript
 * @Module({
 *   imports: [AgentSwarmModule.forRoot({ prismaService: GlassyPrismaService })],
 * })
 * export class AppModule {}
 * ```
 */
@Module({
  controllers: [SwarmController],
  providers: [
    PrismaService,
    TaskManagerService,
    AgentCoordinatorService,
    SwarmService,
    SwarmGateway,
  ],
  exports: [TaskManagerService, AgentCoordinatorService, SwarmService, SwarmGateway],
})
export class AgentSwarmModule {
  /**
   * Configure agent-swarm for hosted mode.
   * Pass `prismaService` to use the host app's Prisma instance instead of the standalone one.
   */
  static forRoot(options?: { prismaService?: any }): DynamicModule {
    const prismaProvider = options?.prismaService
      ? { provide: PrismaService, useExisting: options.prismaService }
      : PrismaService;

    return {
      module: AgentSwarmModule,
      controllers: [SwarmController],
      providers: [
        prismaProvider,
        TaskManagerService,
        AgentCoordinatorService,
        SwarmService,
        SwarmGateway,
      ],
      exports: [TaskManagerService, AgentCoordinatorService, SwarmService, SwarmGateway],
    };
  }
}
