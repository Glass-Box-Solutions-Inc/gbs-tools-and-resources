/**
 * Dev-composition factories (GLY-336 L1.b).
 *
 * These thin factories compose a WORKING dev engine / protected provider from the
 * already-frozen in-memory leaves + the phase-1 default policy, so a consumer can
 *
 *   import { createSubstitutionEngine } from "@glass-box-solutions-inc/phi-substitution-engine";
 *   const { engine, context, policy } = createSubstitutionEngine();
 *
 * and get a working instance without deep-importing internals. Every production seam
 * (`coordinator`, `truthReader`, `reversalStore`, the raw provider) is INJECTABLE, so
 * the same factory swaps the durable §6 store / real provider in for production without
 * re-typing core. The dev defaults are deliberately small and PHI-free.
 *
 * §7/N2 discipline: the factories return the composed engine / the single protected
 * provider binding — NEVER a raw reversal map, a raw provider, or any surface that would
 * let a consumer bypass the egress chokepoint. The dev raw provider is composed BEHIND the
 * wrapper and is never returned or exported.
 */
import type {
  ActorId,
  DictionaryVersion,
  DisplayText,
  EngineVersion,
  KnownLocale,
  MatterId,
  OperationAttemptId,
  OperationId,
  SchemaVersion,
  SubjectId,
  TenantId,
  TokenizedText,
  TokenRole,
} from "./core/brands";
import type {
  IdentifierClass,
  MatterAiContext,
  MatterAiContextAccessor,
  MatterAiPolicyAccessor,
  PhiSubstitutionEngine,
  ReversalHandle,
  ReversalWriteStore,
  ReverseStream,
  SubstitutionRequest,
  SubstitutionResult,
  TrustedMatterAiPolicy,
} from "./core/contracts";
import type { AiProvider, SafeAiTrace } from "./core/protected-ai-provider";
import type { CaseTruthReader, DictionaryVersionCoordinator, TaggedValue } from "./dictionary/contracts";
import type {
  AuditPrimaryStore,
  PhiAuditEvent,
  PhiAuditPreparedRecord,
} from "./audit/ports";
import type { SpoolKeyProvider, SpoolVolume } from "./audit/spool-ports";

import { ComposedSubstitutionEngine } from "./core/orchestrator";
import {
  ComposedProtectedAiProvider,
  type ProtectedStreamResult,
  type RawProviderPort,
} from "./core/wrapper";
import {
  StructuralOptionsProjector,
  type BoundaryGenerateOptions,
} from "./core/options-projector";
import { OriginalContentBaaRouter } from "./core/baa-router";
import { InMemoryReversalStore } from "./tokens/index";
import { InMemoryDictionaryVersionCoordinator } from "./dictionary/version-coordinator";
import { InMemoryCaseTruthReader } from "./dictionary/compiler";
import {
  Aes256GcmAuditSpool,
  DurablePhiAuditEmitter,
  ExactAllowListAuditSerializer,
} from "./audit/index";

// ---------------------------------------------------------------------------
// Dev defaults (deliberately small, PHI-free — a consumer overrides via options)
// ---------------------------------------------------------------------------

const DEV_TENANT = "dev-tenant";
const DEV_MATTER = "dev-matter";
const DEV_ACTOR = "dev-actor";
const DEV_OPERATION = "op-dev";
const DEV_ATTEMPT = "att-dev";
const DEV_REVISION = "dev-rev-1";
const DEV_ENGINE = "dev-engine-1";
const DEV_SCHEMA = "dev-schema-1";
const DEV_LOCALE = "en-US";
const DEV_VERSION = 1n;

const brand = <T>(value: unknown): T => value as unknown as T;

/** One tagged-truth entry, mirroring the frozen boundary loader's shape. */
function devTaggedValue(
  subjectId: string,
  identifierClass: IdentifierClass,
  canonicalDisplayValue: string,
  tokenRole: string,
  expander: TaggedValue["field"]["expander"],
): TaggedValue {
  return {
    field: {
      schemaPath: `case.${subjectId}`,
      substitution: true,
      identifierClass,
      tokenRole: brand<TokenRole>(tokenRole),
      expander,
    },
    subjectId: brand<SubjectId>(subjectId),
    canonicalDisplayValue,
    approvedAliases: [],
  };
}

/**
 * Sample dev case-truth (GLY-336 gate finding 6). SYNTHETIC, deliberately non-real identifiers
 * ONLY: clearly-fictional placeholder names and an SSN drawn from the SSA advertising-reserved
 * block `987-65-4320`–`987-65-4329`, which the SSA guarantees is never issued to a real person.
 * Never seed a real-person identifier here. Module-private — not part of the public root surface.
 */
const DEFAULT_DEV_TAGGED_VALUES: readonly TaggedValue[] = [
  devTaggedValue("dev-claimant", "PERSON_NAME", "Jordan Testcase", "Claimant", "person-name"),
  devTaggedValue("dev-physician", "PERSON_NAME", "Casey Fixture", "Treating_Physician", "person-name"),
  devTaggedValue("dev-mrn", "MRN", "MRN-TEST0000", "MRN", "literal"),
  devTaggedValue("dev-ssn", "SSN", "987-65-4320", "SSN", "literal"),
];

// ---------------------------------------------------------------------------
// createSubstitutionEngine (L1.b)
// ---------------------------------------------------------------------------

export interface CreateSubstitutionEngineOptions {
  readonly tenantId?: string;
  readonly matterId?: string;
  readonly actorId?: string;
  readonly operationId?: string;
  readonly attemptId?: string;
  readonly sourceTruthRevision?: string;
  readonly dictionaryVersion?: bigint;
  readonly engineVersion?: string;
  readonly schemaVersion?: string;
  readonly locale?: string;
  /** Dev case-truth to seed. Ignored when a custom `truthReader` is injected. */
  readonly taggedValues?: readonly TaggedValue[];
  /** Production injection seams — supply real adapters here; dev in-memory otherwise. */
  readonly coordinator?: DictionaryVersionCoordinator;
  readonly truthReader?: CaseTruthReader;
  readonly reversalStore?: ReversalWriteStore;
  // No caller-supplied token grammar policy (GLY-336 gate finding 2): the engine always uses the
  // frozen internal boundary policy, so a consumer can never register a PHI-bearing token role.
}

/**
 * A composed dev engine plus the matching dev context/policy.
 * `engine` is an UNFORGEABLE, null-prototype facade over the `PhiSubstitutionEngine` contract (see
 * {@link sealEngine}); `context`/`policy` are frozen and line up with the seeded defaults so a
 * caller can immediately `engine.substitute({ context, policy, ... })`. No concrete store,
 * coordinator, or truth reader is returned — those are injectable via options and otherwise stay
 * captured inside the engine (GLY-336 gate, capability-level).
 */
export interface DevSubstitutionEngine {
  readonly engine: PhiSubstitutionEngine;
  readonly context: MatterAiContext;
  readonly policy: TrustedMatterAiPolicy;
  readonly dictionaryVersion: DictionaryVersion;
  readonly sourceTruthRevision: string;
  readonly engineVersion: EngineVersion;
}

/** Internal parts; the CONCRETE engine here is only ever sealed, never returned to a consumer. */
interface DevEngineParts {
  readonly engine: ComposedSubstitutionEngine;
  readonly context: MatterAiContext;
  readonly policy: TrustedMatterAiPolicy;
  readonly dictionaryVersion: DictionaryVersion;
  readonly sourceTruthRevision: string;
  readonly brandedEngineVersion: EngineVersion;
}

// ---------------------------------------------------------------------------
// Unforgeable facades (GLY-336 gate, capability-level: findings 2/3)
//
// A concrete class instance leaks its public constructor via the prototype chain
// (`Object.getPrototypeOf(x).constructor`), so a consumer could `new` it with a fake engine (relabel
// raw text as TokenizedText) or a malicious policy. Interface typing is COMPILE-TIME only and does
// not prevent this. Each factory therefore returns a FROZEN, NULL-PROTOTYPE object exposing ONLY the
// interface methods as closure-bound functions. There is no prototype → no recoverable constructor;
// no concrete field/internal is reachable; the real instance stays captured in the closure.
// ---------------------------------------------------------------------------

type DevBoundaryProvider = AiProvider<
  BoundaryGenerateOptions,
  Promise<DisplayText>,
  Promise<ProtectedStreamResult>,
  string,
  Promise<readonly number[]>
>;

function sealReverseStream(stream: ReverseStream): ReverseStream {
  const facade = Object.assign(Object.create(null) as object, {
    push: (chunk: TokenizedText): Promise<void> => stream.push(chunk),
    end: (): Promise<void> => stream.end(),
    abort: (reason: unknown): Promise<void> => stream.abort(reason),
  });
  return Object.freeze(facade) as ReverseStream;
}

function sealEngine(engine: PhiSubstitutionEngine): PhiSubstitutionEngine {
  const facade = Object.assign(Object.create(null) as object, {
    substitute: (request: SubstitutionRequest): Promise<SubstitutionResult> => engine.substitute(request),
    reverse: (text: TokenizedText, handle: ReversalHandle): Promise<DisplayText> =>
      engine.reverse(text, handle),
    createReverseStream: (
      handle: ReversalHandle,
      sink: (safe: DisplayText) => void | Promise<void>,
    ): ReverseStream => sealReverseStream(engine.createReverseStream(handle, sink)),
  });
  return Object.freeze(facade) as PhiSubstitutionEngine;
}

function sealProvider(provider: DevBoundaryProvider): DevBoundaryProvider {
  const facade = Object.assign(Object.create(null) as object, {
    generateText: (options: BoundaryGenerateOptions): Promise<DisplayText> =>
      provider.generateText(options),
    generateStream: (options: BoundaryGenerateOptions): Promise<ProtectedStreamResult> =>
      provider.generateStream(options),
    embedText: (text: string, kind: string): Promise<readonly number[]> =>
      provider.embedText(text, kind),
  });
  return Object.freeze(facade) as DevBoundaryProvider;
}

function buildDevEngineParts(options: CreateSubstitutionEngineOptions): DevEngineParts {
  const tenantId = brand<TenantId>(options.tenantId ?? DEV_TENANT);
  const matterId = brand<MatterId>(options.matterId ?? DEV_MATTER);
  const sourceTruthRevision = options.sourceTruthRevision ?? DEV_REVISION;
  const versionBigint = options.dictionaryVersion ?? DEV_VERSION;
  const dictionaryVersion = brand<DictionaryVersion>(versionBigint);
  const brandedEngineVersion = brand<EngineVersion>(options.engineVersion ?? DEV_ENGINE);
  const schemaVersion = brand<SchemaVersion>(options.schemaVersion ?? DEV_SCHEMA);

  let coordinator: DictionaryVersionCoordinator;
  if (options.coordinator !== undefined) {
    coordinator = options.coordinator;
  } else {
    const inMemory = new InMemoryDictionaryVersionCoordinator();
    inMemory.noteReady({ tenantId, matterId }, versionBigint);
    coordinator = inMemory;
  }

  let truthReader: CaseTruthReader;
  if (options.truthReader !== undefined) {
    truthReader = options.truthReader;
  } else {
    const inMemory = new InMemoryCaseTruthReader();
    inMemory.set(
      { tenantId, matterId, dictionaryVersion, sourceTruthRevision },
      options.taggedValues ?? DEFAULT_DEV_TAGGED_VALUES,
    );
    truthReader = inMemory;
  }

  const reversalStore: ReversalWriteStore = options.reversalStore ?? new InMemoryReversalStore();

  const engine = new ComposedSubstitutionEngine({
    coordinator,
    truthReader,
    sourceTruthRevision,
    reversalStore,
    engineVersion: brandedEngineVersion,
    // Token policy is intentionally NOT injectable from here — the engine defaults to the frozen
    // BOUNDARY_TOKEN_GRAMMAR_POLICY (GLY-336 gate finding 2).
  });

  const context: MatterAiContext = {
    tenantId,
    matterId,
    actorId: brand<ActorId>(options.actorId ?? DEV_ACTOR),
    operationId: brand<OperationId>(options.operationId ?? DEV_OPERATION),
    attemptId: brand<OperationAttemptId>(options.attemptId ?? DEV_ATTEMPT),
  };

  const policy: TrustedMatterAiPolicy = {
    mode: "REQUIRED",
    locale: brand<KnownLocale>(options.locale ?? DEV_LOCALE),
    activeDictionaryVersion: dictionaryVersion,
    schemaVersion,
    detectorRequirement: "DISABLED_PHASE_1",
    approvedOffDecisionId: null,
  };

  return {
    engine,
    context,
    policy,
    dictionaryVersion,
    sourceTruthRevision,
    brandedEngineVersion,
  };
}

/**
 * Compose a working dev {@link PhiSubstitutionEngine} from the in-memory leaves + the phase-1
 * default policy. Seeds a small dev dictionary (a person-name subject and a couple of literal
 * identifiers) unless a custom `truthReader`/`coordinator` is injected. The returned `context`
 * and `policy` line up with the seeded defaults, so a substitution works out of the box.
 */
export function createSubstitutionEngine(
  options: CreateSubstitutionEngineOptions = {},
): DevSubstitutionEngine {
  const parts = buildDevEngineParts(options);
  // Seal the engine into an unforgeable facade and freeze the bundle + its data records. The
  // concrete engine is captured only inside the facade's closure — never handed to the consumer.
  return Object.freeze({
    engine: sealEngine(parts.engine),
    context: Object.freeze({ ...parts.context }),
    policy: Object.freeze({ ...parts.policy }),
    dictionaryVersion: parts.dictionaryVersion,
    sourceTruthRevision: parts.sourceTruthRevision,
    engineVersion: parts.brandedEngineVersion,
  });
}

// ---------------------------------------------------------------------------
// createProtectedAiProvider (L1.b)
// ---------------------------------------------------------------------------

/** Reads the first tokenized text carrier out of the (already tokenized) provider options. */
function firstBoundaryText(options: BoundaryGenerateOptions): string {
  if (typeof options.system === "string") return options.system;
  for (const message of options.messages ?? []) {
    for (const part of message.content) {
      if (typeof part.text === "string") return part.text;
    }
  }
  for (const tool of options.tools ?? []) {
    if (typeof tool.description === "string") return tool.description;
  }
  if (typeof options.embeddingText === "string") return options.embeddingText;
  return "";
}

/** Concatenates every ORIGINAL text carrier for the router's L11 original-content inspection. */
function extractBoundaryText(options: BoundaryGenerateOptions): string {
  const parts: string[] = [];
  if (typeof options.system === "string") parts.push(options.system);
  for (const message of options.messages ?? []) {
    for (const part of message.content) {
      if (typeof part.text === "string") parts.push(part.text);
    }
  }
  for (const tool of options.tools ?? []) parts.push(tool.description);
  if (typeof options.embeddingText === "string") parts.push(options.embeddingText);
  return parts.join("\n");
}

/**
 * Dev raw provider (§4 boundary): it is composed BEHIND the wrapper and is never returned or
 * exported. It echoes the tokenized request back so the reverse path round-trips in dev; a
 * production caller injects a real `invokeRaw` binding. It never sees pre-substitution content.
 */
class DevEchoRawProvider implements RawProviderPort<BoundaryGenerateOptions, string> {
  public generateText(options: BoundaryGenerateOptions): Promise<TokenizedText> {
    return Promise.resolve(brand<TokenizedText>(firstBoundaryText(options)));
  }

  public async generateStream(
    options: BoundaryGenerateOptions,
    onChunk: (chunk: TokenizedText) => void | Promise<void>,
  ): Promise<void> {
    await onChunk(brand<TokenizedText>(firstBoundaryText(options)));
  }

  public embedText(_text: TokenizedText, _kind: string): Promise<readonly number[]> {
    return Promise.resolve([0.1, 0.2, 0.3]);
  }
}

/** N2 dev sink: only branded tokenized text ever reaches it (the wrapper enforces this). */
class DevCollectingSafeTrace implements SafeAiTrace {
  public readonly payloads: string[] = [];

  public request(paths: readonly Readonly<{ path: string; text: TokenizedText }>[]): Promise<void> {
    for (const entry of paths) this.payloads.push(String(entry.text));
    return Promise.resolve();
  }

  public response(text: TokenizedText): Promise<void> {
    this.payloads.push(String(text));
    return Promise.resolve();
  }

  public metadata(_values: Readonly<Record<string, string | number | boolean | null>>): Promise<void> {
    return Promise.resolve();
  }
}

/** Always-available in-memory primary audit store (dev durability). */
class DevInMemoryAuditPrimaryStore implements AuditPrimaryStore {
  public readonly finalized: PhiAuditEvent[] = [];
  readonly #prepared = new Set<string>();

  public prepare(record: PhiAuditPreparedRecord): Promise<
    | Readonly<{ status: "stored"; durableRecordId: string }>
    | Readonly<{ status: "already_exists"; durableRecordId: string }>
    | Readonly<{ status: "unavailable"; fixedFailureCode: string }>
  > {
    const id = record.attemptId as unknown as string;
    if (this.#prepared.has(id)) {
      return Promise.resolve({ status: "already_exists", durableRecordId: `primary:${id}` });
    }
    this.#prepared.add(id);
    return Promise.resolve({ status: "stored", durableRecordId: `primary:${id}` });
  }

  public finalize(event: PhiAuditEvent): Promise<void> {
    this.finalized.push(event);
    return Promise.resolve();
  }
}

/** In-memory durable spool volume (dev). */
class DevInMemorySpoolVolume implements SpoolVolume {
  public readonly durable = true;
  readonly #store = new Map<string, Uint8Array>();

  public putAtomic(recordId: string, bytes: Uint8Array): Promise<Readonly<{ flushed: boolean }>> {
    this.#store.set(recordId, Uint8Array.from(bytes));
    return Promise.resolve({ flushed: true });
  }
  public read(recordId: string): Promise<Uint8Array | null> {
    return Promise.resolve(this.#store.get(recordId) ?? null);
  }
  public list(): Promise<readonly string[]> {
    return Promise.resolve([...this.#store.keys()]);
  }
  public remove(recordId: string): Promise<void> {
    this.#store.delete(recordId);
    return Promise.resolve();
  }
}

/** Fixed 32-byte dev spool key. Not for production — inject a real key reference there. */
class DevFixedSpoolKeyProvider implements SpoolKeyProvider {
  public readonly keyVersion = "dev-key-v1";
  readonly #key = new Uint8Array(32).fill(7);
  public dataKey(): Uint8Array {
    return Uint8Array.from(this.#key);
  }
}

export interface CreateProtectedAiProviderOptions extends CreateSubstitutionEngineOptions {
  /**
   * Production raw-provider binding — the single private port (§3.1.4 / N1). The dev default echoes
   * the tokenized request BEHIND the wrapper. There is deliberately NO caller-controlled PHI-tag or
   * safety knob (GLY-336 gate findings 4/5): the dev route always treats the matter as PHI-tagged
   * and production-safe (BAA route), so a caller can never assert `phi:false` to loosen the gate.
   */
  readonly invokeRaw?: RawProviderPort<BoundaryGenerateOptions, string>;
}

/** A composed dev protected provider — the single application-facing binding — plus its context. */
export interface DevProtectedAiProvider {
  /**
   * The single application-facing binding, returned as an UNFORGEABLE, null-prototype facade over the
   * `AiProvider` interface (GLY-336 gate, capability-level: finding 3). No recoverable constructor,
   * so a consumer cannot forge a wrapper around a fake engine that relabels raw text as
   * `TokenizedText`.
   */
  readonly provider: DevBoundaryProvider;
  /** Unforgeable facade over the underlying `PhiSubstitutionEngine`. */
  readonly engine: PhiSubstitutionEngine;
  readonly context: MatterAiContext;
  readonly policy: TrustedMatterAiPolicy;
}

/**
 * Compose a working dev {@link ComposedProtectedAiProvider} — the single §3.1.4 application binding —
 * over a dev engine, the exhaustive options projector (L5), the original-content BAA router (L11), and
 * a real AES-256-GCM audit durability path with an in-memory primary/spool. The raw provider is
 * composed BEHIND the wrapper (dev echo unless `invokeRaw` is injected) and never exposed.
 */
export function createProtectedAiProvider(
  options: CreateProtectedAiProviderOptions = {},
): DevProtectedAiProvider {
  const parts = buildDevEngineParts(options);
  const clock = (): string => new Date().toISOString();

  const rawProvider: RawProviderPort<BoundaryGenerateOptions, string> =
    options.invokeRaw ?? new DevEchoRawProvider();

  // GLY-336 gate findings 4/5: the dev route is FIXED to a PHI-tagged, production-safe BAA path.
  // No caller input can set `matterIsPhiTagged:false` or otherwise loosen the conjunctive safety
  // gate. A real deployment derives PHI-tagging from the trusted matter policy in its own router.
  const router = new OriginalContentBaaRouter<
    BoundaryGenerateOptions,
    RawProviderPort<BoundaryGenerateOptions, string>
  >({
    extractOriginalText: extractBoundaryText,
    rawProvider,
    baaProviderId: "dev-baa-provider",
    nonBaaProviderId: "dev-provider",
    claudeBaaEnabled: true,
    matterIsPhiTagged: true,
  });

  const primary = new DevInMemoryAuditPrimaryStore();
  const spool = new Aes256GcmAuditSpool(new DevInMemorySpoolVolume(), new DevFixedSpoolKeyProvider(), clock);
  const audit = new DurablePhiAuditEmitter(primary, spool, new ExactAllowListAuditSerializer(), clock);

  const contextAccessor: MatterAiContextAccessor = {
    require: (): Promise<MatterAiContext> => Promise.resolve(parts.context),
  };
  const policyAccessor: MatterAiPolicyAccessor = {
    require: (): Promise<TrustedMatterAiPolicy> => Promise.resolve(parts.policy),
  };

  const provider = new ComposedProtectedAiProvider<BoundaryGenerateOptions, string>({
    engine: parts.engine,
    context: contextAccessor,
    policy: policyAccessor,
    options: new StructuralOptionsProjector(),
    router,
    safeTrace: new DevCollectingSafeTrace(),
    audit,
    invokeRaw: rawProvider,
    engineVersion: parts.brandedEngineVersion,
    clock,
    embeddingOptionsFactory: (text: string): BoundaryGenerateOptions => ({ embeddingText: text }),
  });

  // Seal the provider AND the engine into unforgeable facades; freeze the bundle + its data records.
  // The concrete wrapper/engine are captured only inside the facades' closures — never returned.
  return Object.freeze({
    provider: sealProvider(provider),
    engine: sealEngine(parts.engine),
    context: Object.freeze({ ...parts.context }),
    policy: Object.freeze({ ...parts.policy }),
  });
}
