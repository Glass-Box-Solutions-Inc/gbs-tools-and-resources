import type {
  ActorId,
  DictionaryVersion,
  EngineVersion,
  MatterId,
  OperationAttemptId,
  OperationId,
  TenantId,
} from "../../src/core/brands";
import type { AiOperation, IdentifierClass } from "../../src/core/contracts";
import type { AuditPrimaryStore, PhiAuditEvent, PhiAuditPreparedRecord } from "../../src/audit/ports";
import type { SpoolKeyProvider, SpoolVolume } from "../../src/audit/spool-ports";
import type { AttemptPrecondition } from "../../src/audit/coordinator";
import {
  Aes256GcmAuditSpool,
  DurablePhiAuditEmitter,
  ExactAllowListAuditSerializer,
  PhiAuditedAttemptCoordinator,
  isAuditError,
  preparedToTerminalEvent,
  toTotalIdentifierCounts,
} from "../../src/audit/index";
import type { ModuleHarness, OracleObservation } from "../harness-types";
import { SEEDED_CANARIES } from "../test-helpers";

/**
 * Real production adapter for the audit oracle (`tests/audit.test.ts`).
 *
 * This loader is a thin translation layer: every invariant it exercises is enforced by the
 * production code under `src/audit/**` (serializer allow-list, durable emitter, AES-256-GCM spool,
 * idempotent drain, one-terminal-event coordinator). The fakes here are only the injected
 * boundaries (primary store, durable volume, key provider) and never re-implement an invariant.
 */

const FIXED_CLOCK = (): string => "2026-01-01T00:00:00.000Z";

// Brands are compile-time only; the loader is a trusted adapter that constructs them for tests.
const opId = (s: string): OperationId => s as unknown as OperationId;
const attId = (s: string): OperationAttemptId => s as unknown as OperationAttemptId;
const tenId = (s: string): TenantId => s as unknown as TenantId;
const matId = (s: string): MatterId => s as unknown as MatterId;
const actId = (s: string): ActorId => s as unknown as ActorId;
const engId = (s: string): EngineVersion => s as unknown as EngineVersion;
const dictVer = (n: bigint): DictionaryVersion => n as unknown as DictionaryVersion;

function buildPrepared(opts: {
  readonly attemptId: string;
  readonly counts?: Partial<Record<IdentifierClass, number>>;
}): PhiAuditPreparedRecord {
  return {
    state: "PREPARED",
    attemptId: attId(opts.attemptId),
    operationId: opId("op-1"),
    tenantId: tenId("tenant-1"),
    matterId: matId("matter-1"),
    actorId: actId("actor-1"),
    operation: "generation" as AiOperation,
    dictionaryVersion: dictVer(7n),
    engineVersion: engId("engine-1"),
    counts: toTotalIdentifierCounts(opts.counts ?? {}),
    ambiguityCount: 0,
    detectorName: null,
    detectorVersion: null,
    latencyMs: { dictionary: 1, detector: 0, total: 2 },
    preparedAt: FIXED_CLOCK(),
  };
}

/** Injected durability boundary; never treats an outage as success (CONTRACT §5 N4). */
class FakePrimaryStore implements AuditPrimaryStore {
  public available = true;
  public prepareAttempts = 0;
  public readonly finalizedEvents: PhiAuditEvent[] = [];
  readonly #prepared = new Set<string>();

  /** Seeds an attempt already durably stored + finalized in primary (drain de-dup fixture). */
  public seedExisting(record: PhiAuditPreparedRecord): void {
    this.#prepared.add(record.attemptId as unknown as string);
    this.finalizedEvents.push(preparedToTerminalEvent(record, "completed", null, FIXED_CLOCK()));
  }

  public async prepare(
    record: PhiAuditPreparedRecord,
  ): Promise<
    | Readonly<{ status: "stored"; durableRecordId: string }>
    | Readonly<{ status: "already_exists"; durableRecordId: string }>
    | Readonly<{ status: "unavailable"; fixedFailureCode: string }>
  > {
    this.prepareAttempts += 1;
    const id = record.attemptId as unknown as string;
    if (!this.available) {
      return { status: "unavailable", fixedFailureCode: "AUDIT_PRIMARY_UNAVAILABLE" };
    }
    if (this.#prepared.has(id)) {
      return { status: "already_exists", durableRecordId: `primary:${id}` };
    }
    this.#prepared.add(id);
    return { status: "stored", durableRecordId: `primary:${id}` };
  }

  public async finalize(event: PhiAuditEvent): Promise<void> {
    this.finalizedEvents.push(event);
  }
}

/** Durable, append-oriented volume. Only ciphertext envelopes are ever written to it. */
class InMemorySpoolVolume implements SpoolVolume {
  public durable: boolean;
  readonly #store = new Map<string, Uint8Array>();

  public constructor(durable: boolean) {
    this.durable = durable;
  }

  public async putAtomic(recordId: string, bytes: Uint8Array): Promise<Readonly<{ flushed: boolean }>> {
    this.#store.set(recordId, Uint8Array.from(bytes));
    return { flushed: true };
  }

  public async read(recordId: string): Promise<Uint8Array | null> {
    return this.#store.get(recordId) ?? null;
  }

  public async list(): Promise<readonly string[]> {
    return [...this.#store.keys()];
  }

  public async remove(recordId: string): Promise<void> {
    this.#store.delete(recordId);
  }
}

class FixedKeyProvider implements SpoolKeyProvider {
  public readonly keyVersion = "key-v1";
  readonly #key = new Uint8Array(32).fill(7);

  public dataKey(): Uint8Array {
    return Uint8Array.from(this.#key);
  }
}

function baseObservation(): OracleObservation {
  return {
    providerCalls: 0,
    providerPayloads: [],
    selectedProvider: null,
    routerInput: null,
    tracePayloads: [],
    displayText: null,
    displayChunks: [],
    errorCode: null,
    tokenizedText: null,
    reversedText: null,
    candidates: [],
    tokensBySubject: {},
    ambiguityCount: 0,
    dictionaryVersion: null,
    compileCount: 0,
    detectorCalls: 0,
    detectorName: null,
    detectorRequestBodiesLogged: 0,
    appliedSpanIds: [],
    reversalLookupCount: 0,
    reversalLookupTokens: [],
    latencyMs: 0,
    auditEvents: [],
    primaryAuditAttempts: 0,
    spoolRecords: [],
    drain: { delivered: 0, duplicates: 0, remaining: 0 },
    buildPassed: true,
    diagnostics: [],
    outputs: [],
    metrics: {},
  };
}

/**
 * Scans raw on-disk spool bytes for any plaintext leak. Correctly-encrypted envelopes carry only
 * base64 ciphertext + non-sensitive envelope metadata, so neither a seeded PHI canary nor a
 * cleartext audit-record body marker (`"state":"PREPARED"`, `"counts"`) can appear. Any hit means
 * the durability record was written unencrypted.
 */
function detectPlaintextOnDisk(raw: Uint8Array | null): string | null {
  if (raw === null) {
    return null;
  }
  const onDisk = new TextDecoder().decode(raw);
  const haystack = onDisk.normalize("NFKC").toLocaleLowerCase("en-US");
  for (const canary of SEEDED_CANARIES) {
    if (haystack.includes(canary.normalize("NFKC").toLocaleLowerCase("en-US"))) {
      return onDisk;
    }
  }
  if (onDisk.includes('"state":"PREPARED"') || onDisk.includes('"counts"')) {
    return onDisk;
  }
  return null;
}

async function collectSpoolRecords(
  spool: Aes256GcmAuditSpool,
  volume: InMemorySpoolVolume,
): Promise<OracleObservation["spoolRecords"][number][]> {
  const records: OracleObservation["spoolRecords"][number][] = [];
  for (const recordId of spool.recordIds()) {
    const envelope = await spool.inspectEnvelope(recordId);
    const rawPrepared = await volume.read(recordId);
    const rawEvent = await volume.read(`${recordId}.final`);
    const decrypted = await spool.decryptForAudit(recordId);
    records.push({
      attemptId: envelope.attemptId as unknown as string,
      plaintextOnDisk: detectPlaintextOnDisk(rawPrepared) ?? detectPlaintextOnDisk(rawEvent),
      ciphertextBytes: envelope.ciphertext.length,
      decrypted,
    });
  }
  return records;
}

/** SEC-N3-01: an audit event carrying any value/extra field is rejected before it is ever emitted. */
function runSchemaRejection(fixture: Readonly<Record<string, unknown>>): OracleObservation {
  const serializer = new ExactAllowListAuditSerializer();
  const validEvent = preparedToTerminalEvent(
    buildPrepared({ attemptId: "attempt-schema" }),
    "completed",
    null,
    FIXED_CLOCK(),
  );
  const extraKeys = (fixture["extraKeys"] as readonly string[] | undefined) ?? [];
  const tainted: Record<string, unknown> = { ...validEvent };
  for (const key of extraKeys) {
    tainted[key] = "SENSITIVE-VALUE";
  }

  const auditEvents: unknown[] = [];
  let errorCode: string | null = null;
  try {
    serializer.serialize(tainted as unknown as PhiAuditEvent);
    auditEvents.push(tainted); // reached only if the allow-list wrongly accepted the record
  } catch (error) {
    if (!isAuditError(error)) {
      throw error;
    }
    errorCode = error.code;
  }
  return { ...baseObservation(), auditEvents, errorCode };
}

/** SEC-N3-03: an audit event missing any required metadata field never serializes. */
function runOmitRequired(fixture: Readonly<Record<string, unknown>>): OracleObservation {
  const serializer = new ExactAllowListAuditSerializer();
  const validEvent = preparedToTerminalEvent(
    buildPrepared({ attemptId: "attempt-omit" }),
    "completed",
    null,
    FIXED_CLOCK(),
  );
  const omitEach = (fixture["omitEach"] as readonly string[] | undefined) ?? [];

  const diagnostics: string[] = [];
  let buildPassed = true;
  for (const field of omitEach) {
    const candidate: Record<string, unknown> = { ...validEvent };
    delete candidate[field];
    try {
      serializer.serialize(candidate as unknown as PhiAuditEvent);
      // A record missing a required field that still serialized means the build wrongly passed.
    } catch (error) {
      if (!isAuditError(error)) {
        throw error;
      }
      diagnostics.push(error.code);
      buildPassed = false;
    }
  }
  return { ...baseObservation(), buildPassed, diagnostics };
}

/** SEC-N3-05: draining the encrypted spool into primary is lossless and idempotent. */
async function runDrain(fixture: Readonly<Record<string, unknown>>): Promise<OracleObservation> {
  const volume = new InMemorySpoolVolume(true);
  const spool = new Aes256GcmAuditSpool(volume, new FixedKeyProvider(), FIXED_CLOCK);
  const primary = new FakePrimaryStore();

  const spooledAttemptIds = (fixture["spooledAttemptIds"] as readonly string[] | undefined) ?? [];
  for (const id of spooledAttemptIds) {
    const prepared = buildPrepared({ attemptId: id });
    const receipt = await spool.appendPrepared(prepared);
    await spool.finalize(receipt, preparedToTerminalEvent(prepared, "completed", null, FIXED_CLOCK()));
  }

  const existing = (fixture["existingPrimaryAttemptIds"] as readonly string[] | undefined) ?? [];
  for (const id of existing) {
    primary.seedExisting(buildPrepared({ attemptId: id }));
  }

  const report = await spool.drainTo(primary);
  if (fixture["drainTwice"] === true) {
    await spool.drainTo(primary); // must be a no-op: no re-delivery, no duplicate events
  }

  return {
    ...baseObservation(),
    drain: { delivered: report.delivered, duplicates: report.duplicates, remaining: report.remaining },
    auditEvents: [...primary.finalizedEvents],
  };
}

/**
 * The general attempted-AI-call lifecycle (SEC-N3-02/04, SEC-N4-04A/04B, SEC-N3-06/07). Runs the
 * real coordinator over the real durable emitter + AES-256-GCM spool. Durability is prepared before
 * the provider is ever invoked; a simultaneous primary+spool outage fails closed with zero egress.
 */
async function runAttempt(fixture: Readonly<Record<string, unknown>>): Promise<OracleObservation> {
  const attemptId = (fixture["attemptId"] as string | undefined) ?? "attempt-default";
  const primary = new FakePrimaryStore();
  primary.available = (fixture["primaryAvailable"] as boolean | undefined) ?? true;
  const volume = new InMemorySpoolVolume((fixture["spoolAvailable"] as boolean | undefined) ?? true);
  const spool = new Aes256GcmAuditSpool(volume, new FixedKeyProvider(), FIXED_CLOCK);
  const serializer = new ExactAllowListAuditSerializer();
  const emitter = new DurablePhiAuditEmitter(primary, spool, serializer, FIXED_CLOCK);
  const coordinator = new PhiAuditedAttemptCoordinator(emitter, FIXED_CLOCK);

  const prepared = buildPrepared({
    attemptId,
    counts: fixture["matchedClasses"] as Partial<Record<IdentifierClass, number>> | undefined,
  });

  const precondition: AttemptPrecondition =
    fixture["dictionaryHealth"] === "unavailable"
      ? { ok: false, failureCode: "DICTIONARY_UNAVAILABLE" }
      : { ok: true };

  const providerPayloads: string[] = [];
  const invokeProvider = async (): Promise<void> => {
    // Reached only after a durable PREPARED record exists; the payload is tokenized/metadata-safe.
    providerPayloads.push("[[SUBJECT_1]] tokenized-provider-request");
  };

  const result = await coordinator.run({ prepared, precondition, invokeProvider });

  return {
    ...baseObservation(),
    errorCode: result.errorCode,
    providerCalls: providerPayloads.length,
    providerPayloads,
    auditEvents: [...primary.finalizedEvents],
    primaryAuditAttempts: primary.prepareAttempts,
    spoolRecords: await collectSpoolRecords(spool, volume),
    metrics: { survivesReplicaRestart: spool.durabilityMetrics().survivesReplicaRestart },
  };
}

export function loadAuditHarness(): ModuleHarness {
  return {
    async run(_caseId: string, fixture: Readonly<Record<string, unknown>>): Promise<OracleObservation> {
      if (Array.isArray(fixture["extraKeys"])) {
        return runSchemaRejection(fixture);
      }
      if (Array.isArray(fixture["omitEach"])) {
        return runOmitRequired(fixture);
      }
      if (Array.isArray(fixture["spooledAttemptIds"])) {
        return runDrain(fixture);
      }
      return runAttempt(fixture);
    },
  };
}
