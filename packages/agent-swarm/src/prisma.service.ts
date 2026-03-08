// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology

import { Injectable, OnModuleInit, OnModuleDestroy } from '@nestjs/common';
import { PrismaClient } from '@prisma/client';

/**
 * Standalone PrismaService for agent-swarm.
 * Extends PrismaClient directly — no BetterAuth dependency.
 *
 * When used as a hosted module (via AgentSwarmModule.forRoot()),
 * the host app can provide its own PrismaService instead.
 */
@Injectable()
export class PrismaService extends PrismaClient implements OnModuleInit, OnModuleDestroy {
  async onModuleInit() {
    await this.$connect();
  }

  async onModuleDestroy() {
    await this.$disconnect();
  }
}
