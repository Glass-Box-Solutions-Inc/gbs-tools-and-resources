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
import { Logger } from '@nestjs/common';
import { PrismaService } from '../prisma/prisma.service.js';

/**
 * Extract the better-auth session token from a raw Cookie header string.
 * Falls back to null if the cookie is absent.
 */
function parseSessionCookie(cookieHeader: string): string | null {
  const match = cookieHeader.match(/better-auth\.session_token=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : null;
}

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
 * - Auth accepts either `socket.handshake.auth.token` (E2E / server clients) or the
 *   `better-auth.session_token` cookie (browser clients using withCredentials: true).
 */
@WebSocketGateway({
  cors: { origin: CORS_ORIGINS, credentials: true },
  namespace: '/swarm',
})
export class SwarmGateway implements OnGatewayInit, OnGatewayConnection, OnGatewayDisconnect {
  @WebSocketServer()
  server!: Server;

  private readonly logger = new Logger(SwarmGateway.name);

  constructor(private readonly prisma: PrismaService) {}

  /**
   * Install per-connection middleware:
   * - Session authentication — requires a valid better-auth session.
   * - CORS origin restriction is enforced at the decorator level via CORS_ORIGINS (H-01).
   *
   * Runs before `handleConnection`, so rejected clients never reach the room logic.
   */
  afterInit(server: Server) {
    // Require a valid session — prefer auth.token (server clients), fallback to cookie (browsers)
    server.use(async (socket, next) => {
      const cookieHeader = socket.handshake.headers.cookie ?? '';
      const rawToken =
        (socket.handshake.auth?.token as string | undefined) ??
        parseSessionCookie(cookieHeader);
      // BetterAuth cookie format: "{tokenId}.{hmacSignature}" — only the tokenId is stored
      const token = rawToken ? rawToken.split('.')[0] : null;

      if (!token) {
        return next(new Error('UNAUTHENTICATED'));
      }

      const session = await this.prisma.session.findFirst({
        where: { token, expiresAt: { gt: new Date() } },
        include: { user: true },
      });

      if (!session) {
        return next(new Error('INVALID_TOKEN'));
      }

      socket.data.userId = session.userId;
      socket.data.user = session.user;
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
    // swarmIds are generated as 'swarm-{timestamp}' by SwarmService.spawnSwarm.
    // A full ownership check requires persisting swarmId→userId to the DB — tracked as a future
    // enhancement. This guard at minimum prevents null/empty room joins and validates format.
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
