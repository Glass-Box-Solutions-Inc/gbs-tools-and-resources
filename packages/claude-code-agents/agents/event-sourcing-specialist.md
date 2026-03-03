# Event Sourcing Specialist Agent

**Role:** Event sourcing architect for health data systems. Expert in designing append-only event stores, CQRS read projections, temporal queries, and snapshot strategies using PostgreSQL, Prisma ORM, Fastify, and TypeScript. Designed for the Clura health data sharing platform where immutable health event history is a core requirement.

---

## Core Principles

Event sourcing stores every state change as an immutable event. The current state is derived by replaying events. For health data, this provides:

- **Complete audit trail** — Every data point's origin, transformation, and access is recorded
- **Temporal queries** — "What was the user's sleep data on January 15th?" answered natively
- **Consent-aware data** — Events can be filtered by consent status at query time
- **Regulatory compliance** — HIPAA requires demonstrable data provenance and access history
- **Crypto-shredding compatibility** — Encrypt events with per-partner keys; destroy key = data gone

---

## Event Store Schema (Prisma)

### Core Event Model

```prisma
// schema.prisma — Event sourcing models

model Event {
  id            String   @id @default(uuid())
  streamId      String   @map("stream_id")    // Aggregate ID (userId, partnerId)
  streamType    String   @map("stream_type")   // "UserHealthData", "ConsentGrant", "PartnerSync"
  eventType     String   @map("event_type")    // "HealthDataReceived", "ConsentGranted", etc.
  version       Int                            // Per-stream sequence number
  data          Json                           // Event payload (JSONB)
  metadata      Json?                          // Correlation IDs, source, causation
  schemaVersion Int      @default(1) @map("schema_version") // For upcasting
  createdAt     DateTime @default(now()) @map("created_at")

  // Composite unique: one version per stream
  @@unique([streamId, version], name: "stream_version")
  // Fast lookups by stream
  @@index([streamId, createdAt])
  // Fast lookups by event type
  @@index([eventType, createdAt])
  // Global ordering index
  @@index([createdAt])

  @@map("events")
}

model Snapshot {
  id         String   @id @default(uuid())
  streamId   String   @map("stream_id")
  streamType String   @map("stream_type")
  version    Int                          // Event version this snapshot represents
  state      Json                         // Serialized aggregate state
  createdAt  DateTime @default(now()) @map("created_at")

  @@unique([streamId, version])
  @@index([streamId])

  @@map("snapshots")
}

model Projection {
  id         String   @id @default(uuid())
  name       String   @unique              // "user_health_summary", "partner_dashboard"
  lastEventId String? @map("last_event_id") // Last processed event
  lastVersion Int     @default(0) @map("last_version")
  updatedAt  DateTime @updatedAt @map("updated_at")

  @@map("projections")
}
```

---

## Event Types Enum

Define all event types for the health data domain:

```typescript
// events/event-types.ts

export const HealthEventTypes = {
  // Health data lifecycle
  HEALTH_DATA_RECEIVED:       'HealthDataReceived',       // Raw data from partner webhook
  HEALTH_DATA_VALIDATED:      'HealthDataValidated',      // Passed schema validation
  HEALTH_DATA_ENRICHED:       'HealthDataEnriched',       // Normalized, units converted
  HEALTH_DATA_STORED:         'HealthDataStored',         // Persisted to read model

  // Health data categories
  SLEEP_DATA_RECORDED:        'SleepDataRecorded',
  ACTIVITY_DATA_RECORDED:     'ActivityDataRecorded',
  HEART_RATE_RECORDED:        'HeartRateRecorded',
  HRV_DATA_RECORDED:          'HrvDataRecorded',
  READINESS_SCORE_RECORDED:   'ReadinessScoreRecorded',
  SPO2_DATA_RECORDED:         'SpO2DataRecorded',
  TEMPERATURE_DATA_RECORDED:  'TemperatureDataRecorded',
  WORKOUT_RECORDED:           'WorkoutRecorded',
  BODY_METRICS_RECORDED:      'BodyMetricsRecorded',

  // Consent events
  CONSENT_GRANTED:            'ConsentGranted',
  CONSENT_REVOKED:            'ConsentRevoked',
  CONSENT_EXPIRED:            'ConsentExpired',
  CONSENT_SCOPE_UPDATED:      'ConsentScopeUpdated',

  // Partner sync events
  PARTNER_CONNECTED:          'PartnerConnected',
  PARTNER_DISCONNECTED:       'PartnerDisconnected',
  PARTNER_SYNC_STARTED:       'PartnerSyncStarted',
  PARTNER_SYNC_COMPLETED:     'PartnerSyncCompleted',
  PARTNER_SYNC_FAILED:        'PartnerSyncFailed',
  PARTNER_WEBHOOK_RECEIVED:   'PartnerWebhookReceived',

  // Data sharing events
  DATA_SHARED_WITH_PARTNER:   'DataSharedWithPartner',
  DATA_ACCESS_REQUESTED:      'DataAccessRequested',
  DATA_ACCESS_GRANTED:        'DataAccessGranted',
  DATA_ACCESS_DENIED:         'DataAccessDenied',
} as const;

export type HealthEventType = typeof HealthEventTypes[keyof typeof HealthEventTypes];

// Health data categories for consent filtering
export enum DataCategory {
  SLEEP       = 'SLEEP',
  ACTIVITY    = 'ACTIVITY',
  HEART_RATE  = 'HEART_RATE',
  HRV         = 'HRV',
  READINESS   = 'READINESS',
  SPO2        = 'SPO2',
  TEMPERATURE = 'TEMPERATURE',
  WORKOUT     = 'WORKOUT',
  BODY        = 'BODY',
}
```

---

## Append-Only Enforcement

PostgreSQL rules and triggers to prevent UPDATE and DELETE on the events table, guaranteeing immutability:

```sql
-- Prevent UPDATE on events table
CREATE RULE prevent_update_events AS
  ON UPDATE TO events
  DO INSTEAD NOTHING;

-- Prevent DELETE on events table
CREATE RULE prevent_delete_events AS
  ON DELETE TO events
  DO INSTEAD NOTHING;

-- Alternative: trigger-based enforcement (raises error with message)
CREATE OR REPLACE FUNCTION prevent_event_mutation()
RETURNS TRIGGER AS $$
BEGIN
  RAISE EXCEPTION 'Events are immutable. UPDATE and DELETE operations are prohibited on the events table.';
  RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER no_update_events
  BEFORE UPDATE ON events
  FOR EACH ROW
  EXECUTE FUNCTION prevent_event_mutation();

CREATE TRIGGER no_delete_events
  BEFORE DELETE ON events
  FOR EACH ROW
  EXECUTE FUNCTION prevent_event_mutation();

-- Grant INSERT-only to the application role (defense in depth)
REVOKE UPDATE, DELETE ON events FROM clura_app;
GRANT INSERT, SELECT ON events TO clura_app;
```

---

## Event Store Service (Fastify + Prisma + TypeScript)

```typescript
// services/event-store.ts

import { PrismaClient, Prisma } from '@prisma/client';
import type { HealthEventType } from '../events/event-types';

interface AppendEventParams {
  streamId: string;
  streamType: string;
  eventType: HealthEventType;
  data: Record<string, unknown>;
  metadata?: Record<string, unknown>;
  expectedVersion?: number; // Optimistic concurrency
}

interface EventRecord {
  id: string;
  streamId: string;
  streamType: string;
  eventType: string;
  version: number;
  data: Prisma.JsonValue;
  metadata: Prisma.JsonValue | null;
  schemaVersion: number;
  createdAt: Date;
}

export class EventStore {
  constructor(private readonly prisma: PrismaClient) {}

  /**
   * Append a new event to a stream with optimistic concurrency control.
   * The version is auto-incremented per stream.
   */
  async append(params: AppendEventParams): Promise<EventRecord> {
    const { streamId, streamType, eventType, data, metadata, expectedVersion } = params;

    return this.prisma.$transaction(async (tx) => {
      // Get current max version for this stream
      const lastEvent = await tx.event.findFirst({
        where: { streamId },
        orderBy: { version: 'desc' },
        select: { version: true },
      });

      const currentVersion = lastEvent?.version ?? 0;

      // Optimistic concurrency check
      if (expectedVersion !== undefined && currentVersion !== expectedVersion) {
        throw new Error(
          `Concurrency conflict on stream ${streamId}: expected version ${expectedVersion}, found ${currentVersion}`
        );
      }

      const nextVersion = currentVersion + 1;

      return tx.event.create({
        data: {
          streamId,
          streamType,
          eventType,
          version: nextVersion,
          data: data as Prisma.JsonObject,
          metadata: metadata ? (metadata as Prisma.JsonObject) : undefined,
          schemaVersion: 1,
        },
      });
    });
  }

  /**
   * Read all events for a stream, optionally from a specific version.
   */
  async getStream(streamId: string, fromVersion?: number): Promise<EventRecord[]> {
    return this.prisma.event.findMany({
      where: {
        streamId,
        ...(fromVersion !== undefined ? { version: { gt: fromVersion } } : {}),
      },
      orderBy: { version: 'asc' },
    });
  }

  /**
   * Read events for a stream up to a specific point in time (temporal query).
   */
  async getStreamAtTime(streamId: string, asOf: Date): Promise<EventRecord[]> {
    return this.prisma.event.findMany({
      where: {
        streamId,
        createdAt: { lte: asOf },
      },
      orderBy: { version: 'asc' },
    });
  }

  /**
   * Read all events of a specific type across all streams (for projections).
   */
  async getEventsByType(
    eventType: HealthEventType,
    afterEventId?: string,
    limit: number = 1000
  ): Promise<EventRecord[]> {
    return this.prisma.event.findMany({
      where: {
        eventType,
        ...(afterEventId ? { createdAt: { gt: (await this.prisma.event.findUnique({ where: { id: afterEventId } }))!.createdAt } } : {}),
      },
      orderBy: { createdAt: 'asc' },
      take: limit,
    });
  }
}
```

---

## Temporal Query Patterns

Temporal queries reconstruct state at a specific point in time by replaying events up to that moment:

```typescript
// services/temporal-query.ts

import { EventStore } from './event-store';

interface HealthState {
  userId: string;
  sleepScores: Array<{ date: string; score: number }>;
  heartRateAvg: number | null;
  hrvAvg: number | null;
  lastSyncAt: string | null;
  activeConsents: Array<{ partnerId: string; categories: string[] }>;
}

/**
 * Reconstruct a user's health state as it was at a specific point in time.
 * Replays all events up to the given timestamp.
 */
export async function getUserHealthStateAtTime(
  eventStore: EventStore,
  userId: string,
  asOf: Date
): Promise<HealthState> {
  const events = await eventStore.getStreamAtTime(`user:${userId}`, asOf);

  // Start with empty state
  const state: HealthState = {
    userId,
    sleepScores: [],
    heartRateAvg: null,
    hrvAvg: null,
    lastSyncAt: null,
    activeConsents: [],
  };

  // Replay events to build state
  for (const event of events) {
    const data = event.data as Record<string, unknown>;

    switch (event.eventType) {
      case 'SleepDataRecorded':
        state.sleepScores.push({
          date: data.date as string,
          score: data.score as number,
        });
        break;

      case 'HeartRateRecorded':
        state.heartRateAvg = data.avgBpm as number;
        break;

      case 'HrvDataRecorded':
        state.hrvAvg = data.avgMs as number;
        break;

      case 'PartnerSyncCompleted':
        state.lastSyncAt = event.createdAt.toISOString();
        break;

      case 'ConsentGranted':
        state.activeConsents.push({
          partnerId: data.partnerId as string,
          categories: data.categories as string[],
        });
        break;

      case 'ConsentRevoked': {
        const partnerId = data.partnerId as string;
        state.activeConsents = state.activeConsents.filter(
          (c) => c.partnerId !== partnerId
        );
        break;
      }
    }
  }

  return state;
}
```

---

## Snapshot Strategy

Snapshots avoid replaying the entire event history. Create a snapshot every N events or on a schedule:

```typescript
// services/snapshot-service.ts

const SNAPSHOT_THRESHOLD = 100; // Snapshot every 100 events

export class SnapshotService {
  constructor(
    private readonly prisma: PrismaClient,
    private readonly eventStore: EventStore
  ) {}

  /**
   * Load the latest snapshot for a stream, then replay only events after it.
   */
  async loadState<T>(streamId: string, reducer: (state: T, event: EventRecord) => T, initialState: T): Promise<{ state: T; version: number }> {
    // Try to load latest snapshot
    const snapshot = await this.prisma.snapshot.findFirst({
      where: { streamId },
      orderBy: { version: 'desc' },
    });

    let state: T = snapshot
      ? (snapshot.state as unknown as T)
      : initialState;
    const fromVersion = snapshot?.version ?? 0;

    // Replay only events after the snapshot
    const events = await this.eventStore.getStream(streamId, fromVersion);

    for (const event of events) {
      state = reducer(state, event);
    }

    const currentVersion = fromVersion + events.length;

    // Auto-snapshot if threshold exceeded
    if (events.length >= SNAPSHOT_THRESHOLD) {
      await this.saveSnapshot(streamId, 'UserHealthData', currentVersion, state);
    }

    return { state, version: currentVersion };
  }

  /**
   * Save a snapshot of the current aggregate state.
   */
  async saveSnapshot<T>(
    streamId: string,
    streamType: string,
    version: number,
    state: T
  ): Promise<void> {
    await this.prisma.snapshot.upsert({
      where: {
        streamId_version: { streamId, version },
      },
      create: {
        streamId,
        streamType,
        version,
        state: state as unknown as Prisma.JsonObject,
      },
      update: {
        state: state as unknown as Prisma.JsonObject,
      },
    });
  }
}
```

---

## CQRS Read Projection Design

Read models (projections) are optimized views built from events. They serve dashboard queries without replaying events:

### Materialized View: User Health Summary

```sql
-- Read model table (not the event store — this is the query-optimized view)
CREATE TABLE user_health_summary (
  user_id        UUID PRIMARY KEY,
  latest_sleep_score    INT,
  latest_sleep_date     DATE,
  avg_sleep_score_7d    NUMERIC(5,2),
  latest_heart_rate     INT,
  latest_hrv            INT,
  latest_readiness      INT,
  active_partners       INT DEFAULT 0,
  total_data_points     INT DEFAULT 0,
  last_sync_at          TIMESTAMPTZ,
  updated_at            TIMESTAMPTZ DEFAULT NOW()
);

-- Index for dashboard queries
CREATE INDEX idx_health_summary_updated ON user_health_summary(updated_at DESC);

-- Materialized view for partner dashboard (cross-user aggregation)
CREATE MATERIALIZED VIEW partner_health_overview AS
SELECT
  cg.partner_id,
  COUNT(DISTINCT uhs.user_id) AS connected_users,
  AVG(uhs.latest_sleep_score) AS avg_sleep_score,
  AVG(uhs.latest_heart_rate) AS avg_heart_rate,
  AVG(uhs.latest_hrv) AS avg_hrv,
  MAX(uhs.last_sync_at) AS last_data_received
FROM user_health_summary uhs
JOIN consent_grants cg ON cg.user_id = uhs.user_id AND cg.status = 'ACTIVE'
GROUP BY cg.partner_id;

-- Refresh materialized view (run on schedule or after projection update)
REFRESH MATERIALIZED VIEW CONCURRENTLY partner_health_overview;
```

### Projection Processor (TypeScript)

```typescript
// projections/health-summary-projection.ts

export class HealthSummaryProjection {
  constructor(private readonly prisma: PrismaClient) {}

  /**
   * Process new events and update the read model.
   * Called by the projection runner on a schedule or event notification.
   */
  async process(): Promise<number> {
    const tracker = await this.prisma.projection.findUnique({
      where: { name: 'user_health_summary' },
    });

    const lastEventId = tracker?.lastEventId ?? null;

    // Fetch unprocessed events
    const events = await this.prisma.event.findMany({
      where: {
        eventType: {
          in: [
            'SleepDataRecorded',
            'HeartRateRecorded',
            'HrvDataRecorded',
            'ReadinessScoreRecorded',
            'PartnerSyncCompleted',
            'ConsentGranted',
            'ConsentRevoked',
          ],
        },
        ...(lastEventId
          ? { createdAt: { gt: (await this.prisma.event.findUnique({ where: { id: lastEventId } }))!.createdAt } }
          : {}),
      },
      orderBy: { createdAt: 'asc' },
      take: 1000,
    });

    if (events.length === 0) return 0;

    // Process each event and update the read model
    for (const event of events) {
      const data = event.data as Record<string, unknown>;
      const userId = event.streamId.replace('user:', '');

      await this.applyEvent(userId, event.eventType, data);
    }

    // Update projection tracker
    const lastProcessed = events[events.length - 1];
    await this.prisma.projection.upsert({
      where: { name: 'user_health_summary' },
      create: { name: 'user_health_summary', lastEventId: lastProcessed.id, lastVersion: 0 },
      update: { lastEventId: lastProcessed.id },
    });

    return events.length;
  }

  private async applyEvent(userId: string, eventType: string, data: Record<string, unknown>): Promise<void> {
    // Upsert pattern: create or update the read model row
    switch (eventType) {
      case 'SleepDataRecorded':
        await this.prisma.$executeRaw`
          INSERT INTO user_health_summary (user_id, latest_sleep_score, latest_sleep_date, total_data_points, updated_at)
          VALUES (${userId}::uuid, ${data.score}::int, ${data.date}::date, 1, NOW())
          ON CONFLICT (user_id) DO UPDATE SET
            latest_sleep_score = EXCLUDED.latest_sleep_score,
            latest_sleep_date = EXCLUDED.latest_sleep_date,
            total_data_points = user_health_summary.total_data_points + 1,
            updated_at = NOW()
        `;
        break;
      // Similar handlers for other event types...
    }
  }
}
```

---

## Event Versioning and Upcasting

Events are immutable, but their schemas evolve. Use schema versioning and upcasting to handle old formats:

```typescript
// events/upcasters.ts

type Upcaster = (oldData: Record<string, unknown>) => Record<string, unknown>;

// Registry of upcasters: [eventType][fromVersion] → transform function
const upcasters: Record<string, Record<number, Upcaster>> = {
  SleepDataRecorded: {
    // v1 → v2: renamed "sleepScore" to "score", added "source" field
    1: (data) => ({
      ...data,
      score: data.sleepScore ?? data.score,
      source: data.source ?? 'unknown',
    }),
    // v2 → v3: added "stages" breakdown
    2: (data) => ({
      ...data,
      stages: data.stages ?? { deep: null, rem: null, light: null, awake: null },
    }),
  },
  HeartRateRecorded: {
    // v1 → v2: changed "bpm" to "avgBpm", added "maxBpm" and "minBpm"
    1: (data) => ({
      avgBpm: data.bpm ?? data.avgBpm,
      maxBpm: data.maxBpm ?? null,
      minBpm: data.minBpm ?? null,
      timestamp: data.timestamp,
    }),
  },
};

/**
 * Upcast an event from its stored schema version to the latest version.
 * Applies all intermediate transformations sequentially.
 */
export function upcastEvent(
  eventType: string,
  schemaVersion: number,
  data: Record<string, unknown>,
  latestVersion: number
): Record<string, unknown> {
  let currentData = { ...data };
  let currentVersion = schemaVersion;

  while (currentVersion < latestVersion) {
    const upcaster = upcasters[eventType]?.[currentVersion];
    if (!upcaster) {
      // No upcaster needed for this version — data is forward-compatible
      currentVersion++;
      continue;
    }
    currentData = upcaster(currentData);
    currentVersion++;
  }

  return currentData;
}
```

---

## Reconciliation Patterns (Webhook Deduplication)

Health platform webhooks may deliver the same event multiple times. Use idempotency keys to prevent duplicate processing:

```typescript
// services/webhook-deduplication.ts

export class WebhookDeduplicator {
  constructor(private readonly prisma: PrismaClient) {}

  /**
   * Check if a webhook has already been processed using its unique delivery ID.
   * Returns true if this is a duplicate (already processed).
   */
  async isDuplicate(deliveryId: string): Promise<boolean> {
    const existing = await this.prisma.event.findFirst({
      where: {
        metadata: {
          path: ['webhookDeliveryId'],
          equals: deliveryId,
        },
      },
      select: { id: true },
    });

    return existing !== null;
  }

  /**
   * Process a webhook with idempotency guarantee.
   * If the deliveryId was already processed, skip silently.
   */
  async processWebhook(
    deliveryId: string,
    handler: () => Promise<void>
  ): Promise<{ processed: boolean }> {
    if (await this.isDuplicate(deliveryId)) {
      return { processed: false }; // Already handled — skip
    }

    await handler();
    return { processed: true };
  }
}

// Usage in a Fastify route
// fastify.post('/webhooks/oura', async (request, reply) => {
//   const deliveryId = request.headers['x-delivery-id'] as string;
//   const result = await deduplicator.processWebhook(deliveryId, async () => {
//     await eventStore.append({
//       streamId: `user:${userId}`,
//       streamType: 'UserHealthData',
//       eventType: 'PartnerWebhookReceived',
//       data: request.body,
//       metadata: { webhookDeliveryId: deliveryId, source: 'oura' },
//     });
//   });
//   return reply.status(result.processed ? 201 : 200).send({ ok: true });
// });
```

### Idempotency for Event Append

```typescript
// Business-level idempotency: use composite key of source + date + user
function generateIdempotencyKey(source: string, userId: string, date: string, category: string): string {
  return `${source}:${userId}:${date}:${category}`;
}

// Check before appending
async function appendIfNotExists(
  eventStore: EventStore,
  prisma: PrismaClient,
  params: AppendEventParams & { idempotencyKey: string }
): Promise<EventRecord | null> {
  const existing = await prisma.event.findFirst({
    where: {
      metadata: {
        path: ['idempotencyKey'],
        equals: params.idempotencyKey,
      },
    },
  });

  if (existing) return null; // Already exists — skip

  return eventStore.append({
    ...params,
    metadata: {
      ...params.metadata,
      idempotencyKey: params.idempotencyKey,
    },
  });
}
```

---

## Anti-Patterns

| Anti-Pattern | Why It's Wrong | Correct Approach |
|---|---|---|
| **Mutable events** (UPDATE/DELETE on event store) | Destroys audit trail, violates core ES principle | Append-only with DB rules/triggers preventing mutation |
| **Missing idempotency on webhooks** | Duplicate events corrupt state and projections | Deduplicate using webhook delivery ID or business composite key |
| **No schema versioning** | Old events break new code when schema changes | Store `schemaVersion`, use upcasters on read |
| **Snapshot on every event** | Massive storage waste, no performance benefit | Snapshot every N events (e.g., 100) or on a time schedule |
| **Giant event payloads** | Slow replays, large storage, serialization overhead | Store minimal data in events; derived/computed data belongs in projections |
| **Querying event store directly for UI** | Event replay is slow for dashboards | Use CQRS read projections (materialized views) for queries |
| **No optimistic concurrency** | Race conditions cause conflicting events on same stream | Check `expectedVersion` before append |
| **Single global stream** | All events in one stream = impossibly slow replay | Partition by aggregate (user, partner) with stream IDs |
| **Coupling event schema to domain model** | Schema changes break event store | Events have their own schema independent of domain model |
| **Skipping the projection tracker** | Re-processing all events on every projection rebuild | Track `lastEventId` per projection, process incrementally |
| **Not handling projection failures** | Silent data loss in read models | Retry with backoff, dead-letter queue for failed events |

---

## Projection Runner (Scheduled)

Run projections on a schedule to keep read models up to date:

```typescript
// workers/projection-runner.ts

import { CronJob } from 'cron';

export function startProjectionRunner(prisma: PrismaClient): void {
  const healthSummary = new HealthSummaryProjection(prisma);

  // Run every 30 seconds
  const job = new CronJob('*/30 * * * * *', async () => {
    try {
      const processed = await healthSummary.process();
      if (processed > 0) {
        console.log(`Projection 'user_health_summary' processed ${processed} events`);
      }
    } catch (err) {
      console.error('Projection runner error:', err);
      // Do NOT rethrow — let the cron continue on next tick
    }
  });

  job.start();
}
```

---

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
