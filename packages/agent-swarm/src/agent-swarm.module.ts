// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology

import { Module } from '@nestjs/common';
import { SwarmController } from './swarm.controller.js';
import { TaskManagerService } from './task-manager.service.js';
import { AgentCoordinatorService } from './agent-coordinator.service.js';
import { SwarmService } from './swarm.service.js';
import { SwarmGateway } from './swarm.gateway.js';

@Module({
  controllers: [SwarmController],
  providers: [
    TaskManagerService,
    AgentCoordinatorService,
    SwarmService,
    SwarmGateway,
  ],
  exports: [TaskManagerService, AgentCoordinatorService, SwarmService, SwarmGateway],
})
export class AgentSwarmModule {}
