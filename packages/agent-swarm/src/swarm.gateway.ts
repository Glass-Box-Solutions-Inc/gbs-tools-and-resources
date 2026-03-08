// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology

import {
  WebSocketGateway,
  WebSocketServer,
  SubscribeMessage,
  OnGatewayConnection,
  OnGatewayDisconnect,
  OnGatewayInit,
  ConnectedSocket,
  MessageBody,
} from '@nestjs/websockets';
import { Server, Socket } from 'socket.io';
import { Logger, Optional, Inject } from '@nestjs/common';

/**
 * Token for injecting a custom auth handler into the SwarmGateway.
 *
 * Hosted mode (e.g. Glassy): provide an AUTH_HANDLER that validates BetterAuth sessions.
 * Standalone mode: accepts `socket.handshake.auth.token` as the userId directly.
 */
export const SWARM_AUTH_HANDLER = 'SWARM_AUTH_HANDLER';

export type SwarmAuthHandler = (socket: Socket) => Promise<{ userId: string } | null>;

// H-01: Restrict WebSocket origins to configured allow-list (not wildcard)
const CORS_ORIGINS = (process.env.CORS_ORIGINS ?? 'http://localhost:5173')
  .split(',')
  .map((o) => o.trim());

/**
 * Swarm Gateway — WebSocket for real-time task updates and agent status broadcasts.
 *
 * Security:
 * - afterInit() installs session auth middleware.
 * - CORS is enforced at the decorator level via CORS_ORIGINS env var (H-01).
 * - Standalone mode: accepts `socket.handshake.auth.token` as userId directly.
 * - Hosted mode: inject SWARM_AUTH_HANDLER to validate sessions (e.g. BetterAuth).
 */
@WebSocketGateway({
  cors: { origin: CORS_ORIGINS, credentials: true },
  namespace: '/swarm',
})
export class SwarmGateway implements OnGatewayInit, OnGatewayConnection, OnGatewayDisconnect {
  @WebSocketServer()
  server!: Server;

  private readonly logger = new Logger(SwarmGateway.name);

  constructor(
    @Optional() @Inject(SWARM_AUTH_HANDLER) private readonly authHandler?: SwarmAuthHandler,
  ) {}

  /**
   * Install per-connection middleware:
   * - Hosted mode: delegates to injected auth handler (e.g. BetterAuth session lookup).
   * - Standalone mode: accepts `socket.handshake.auth.token` as userId directly.
   */
  afterInit(server: Server) {
    server.use(async (socket, next) => {
      if (this.authHandler) {
        // Hosted mode — delegate to injected auth handler
        const result = await this.authHandler(socket);
        if (!result) {
          return next(new Error('UNAUTHENTICATED'));
        }
        socket.data.userId = result.userId;
        return next();
      }

      // Standalone mode — accept auth.token as userId directly
      const token = socket.handshake.auth?.token as string | undefined;
      if (!token) {
        return next(new Error('UNAUTHENTICATED'));
      }

      socket.data.userId = token;
      next();
    });
  }

  handleConnection(client: Socket) {
    this.logger.log(`Swarm client connected: ${client.id} userId=${client.data.userId}`);
  }

  handleDisconnect(client: Socket) {
    this.logger.log(`Swarm client disconnected: ${client.id}`);
  }

  @SubscribeMessage('joinSwarm')
  handleJoinSwarm(
    @ConnectedSocket() client: Socket,
    @MessageBody() data: { swarmId: string },
  ) {
    // H-02: Validate swarmId is non-empty with expected format before joining the room.
    if (!data?.swarmId || !data.swarmId.startsWith('swarm-')) {
      client.emit('error', { message: 'Invalid or missing swarmId' });
      return;
    }

    client.join(`swarm:${data.swarmId}`);
    return { event: 'joinedSwarm', data: { swarmId: data.swarmId } };
  }

  @SubscribeMessage('leaveSwarm')
  handleLeaveSwarm(
    @ConnectedSocket() client: Socket,
    @MessageBody() data: { swarmId: string },
  ) {
    client.leave(`swarm:${data.swarmId}`);
  }

  // ─── Broadcast methods called by SwarmService / AgentCoordinator ────────────

  emitTaskUpdate(swarmId: string, task: { id: string; status: string; assignee?: string }) {
    this.server.to(`swarm:${swarmId}`).emit('taskUpdate', task);
  }

  emitAgentStatus(
    swarmId: string,
    agent: { id: string; role: string; status: string; currentTaskId: string | null },
  ) {
    this.server.to(`swarm:${swarmId}`).emit('agentStatus', agent);
  }

  emitProgress(
    swarmId: string,
    progress: { completed: number; total: number; percentage: number },
  ) {
    this.server.to(`swarm:${swarmId}`).emit('progress', progress);
  }

  emitConflict(swarmId: string, conflict: { file: string; agents: string[] }) {
    this.server.to(`swarm:${swarmId}`).emit('conflict', conflict);
  }
}
