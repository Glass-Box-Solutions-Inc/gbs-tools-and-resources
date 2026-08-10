import type { ModuleHarness, OracleObservation } from "../harness-types";
import type {
  ActorId,
  DictionaryVersion,
  EngineVersion,
  MatterId,
  OperationAttemptId,
  OperationId,
  SchemaVersion,
  SubstitutionToken,
  TenantId,
  TokenizedText,
  TokenRole,
} from "../../src/core/brands";
import type {
  AiProviderOptionProjector,
  ClassifiedProviderOptions,
  OriginalContentProviderRouter,
  SafeAiTrace,
} from "../../src/core/protected-ai-provider";
import type {
  IdentifierClass,
  MatterAiContext,
  MatterAiContextAccessor,
  MatterAiPolicyAccessor,
  TrustedMatterAiPolicy,
} from "../../src/core/contracts";
import type { TaggedValue } from "../../src/dictionary/contracts";
import type {
  AuditPrimaryStore,
  PhiAuditEvent,
  PhiAuditPreparedRecord,
} from "../../src/audit/ports";
import type { SpoolKeyProvider, SpoolVolume } from "../../src/audit/spool-ports";

import {
  InMemoryCaseTruthReader,
  InMemoryDictionaryVersionCoordinator,
} from "../../src/dictionary/index";
import { InMemoryReversalStore } from "../../src/tokens/index";
import {
  Aes256GcmAuditSpool,
  DurablePhiAuditEmitter,
  ExactAllowListAuditSerializer,
} from "../../src/audit/index";

import { ComposedSubstitutionEngine } from "../../src/core/orchestrator";
import {
  ComposedProtectedAiProvider,
  type ProtectedStreamResult,
  type RawProviderPort,
} from "../../src/core/wrapper";
import {
  StructuralOptionsProjector,
  type BoundaryGenerateOptions,
} from "../../src/core/options-projector";
import {
  OriginalContentBaaRouter,
  type BaaRouterConfig,
  type ProviderRoutingDecision,
} from "../../src/core/baa-router";
import { PhiEngineError, toFailureCode } from "../../src/core/errors";

/**
 * Real adapter over the composed protected-provider boundary
 * (`tests/provider-boundary.test.ts`).
 *
 * This loader is the sole test-to-production wiring seam for the boundary. It
 * NEVER re-implements an invariant: every observable the oracle asserts is
 * produced by driving the frozen composed production code —
 * `ComposedProtectedAiProvider` (the §4 flow, N1/N2/N3/N4/L5/L11),
 * `ComposedSubstitutionEngine` (dictionary + collision + tokens + variants), the
 * `StructuralOptionsProjector` (L5), the `OriginalContentBaaRouter` (L11), the
 * real AES-256-GCM audit durability path, and the tokens reversal store. The
 * fakes here are only injected boundaries (context/policy, primary store, spool
 * volume, key provider, raw provider, safe trace).
 */

// -- branding helpers (test adapter side; brands are constructed by the harness) --
const tenant = (s: string): TenantId => s as unknown as TenantId;
const matter = (s: string): MatterId => s as unknown as MatterId;
const actor = (s: string): ActorId => s as unknown as ActorId;
const op = (s: string): OperationId => s as unknown as OperationId;
const attempt = (s: string): OperationAttemptId => s as unknown as OperationAttemptId;
const schema = (s: string): SchemaVersion => s as unknown as SchemaVersion;
const engine = (s: string): EngineVersion => s as unknown as EngineVersion;
const version = (n: bigint): DictionaryVersion => n as unknown as DictionaryVersion;
const role = (s: string): TokenRole => s as unknown as TokenRole;
const token = (s: string): SubstitutionToken => s as unknown as SubstitutionToken;
const locale = (s: string): TrustedMatterAiPolicy["locale"] =>
  s as unknown as TrustedMatterAiPolicy["locale"];

const TENANT = tenant("tenant-1");
const MATTER = matter("matter-1");
const LOCALE = "en-US";
const REVISION = "rev-1";
const VERSION_BIGINT = 7n;
const VERSION = version(VERSION_BIGINT);
const ENGINE = engine("engine-1");
const SCHEMA = schema("schema-1");
const CLOCK = (): string => "2026-01-01T00:00:00.000Z";

const CONTEXT: MatterAiContext = {
  tenantId: TENANT,
  matterId: MATTER,
  actorId: actor("actor-1"),
  operationId: op("op-1"),
  attemptId: attempt("att-1"),
};

const POLICY: TrustedMatterAiPolicy = {
  mode: "REQUIRED",
  locale: locale(LOCALE),
  activeDictionaryVersion: VERSION,
  schemaVersion: SCHEMA,
  detectorRequirement: "DISABLED_PHASE_1",
  approvedOffDecisionId: null,
};

const CONTEXT_ACCESSOR: MatterAiContextAccessor = {
  require: (): Promise<MatterAiContext> => Promise.resolve(CONTEXT),
};
const POLICY_ACCESSOR: MatterAiPolicyAccessor = {
  require: (): Promise<TrustedMatterAiPolicy> => Promise.resolve(POLICY),
};

function taggedValue(
  subjectId: string,
  identifierClass: IdentifierClass,
  value: string,
  tokenRole: string,
  expander: TaggedValue["field"]["expander"],
): TaggedValue {
  return {
    field: {
      schemaPath: `case.${subjectId}`,
      substitution: true,
      identifierClass,
      tokenRole: role(tokenRole),
      expander,
    },
    subjectId: subjectId as unknown as TaggedValue["subjectId"],
    canonicalDisplayValue: value,
    approvedAliases: [],
  };
}

/** On-file, schema-tagged case truth covering every seeded canary. */
const DEFAULT_KNOWN_VALUES: readonly TaggedValue[] = [
  taggedValue("s-maria", "PERSON_NAME", "Maria García", "Claimant", "person-name"),
  taggedValue("s-robert", "PERSON_NAME", "Robert O'Neil", "Claimant", "person-name"),
  taggedValue("s-ssn", "SSN", "078-05-1120", "SSN", "literal"),
  taggedValue("s-mrn", "MRN", "MRN-A7719", "MRN", "literal"),
  taggedValue("s-dea", "DEA", "DEA-AB1234567", "DEA", "literal"),
  taggedValue("s-email", "EMAIL", "maria@example.test", "EMAIL", "literal"),
  taggedValue("s-phone", "PHONE", "+1 (415) 555-0199", "PHONE", "literal"),
  taggedValue("s-addr", "ADDRESS", "412 May Street", "ADDRESS", "literal"),
  taggedValue("s-claim", "CLAIM_NUMBER", "CLM-00421", "CLAIM", "literal"),
  taggedValue("s-policy", "POLICY_NUMBER", "POL-7788", "POLICY", "literal"),
  taggedValue("s-acct", "ACCOUNT_NUMBER", "ACCT-91234", "ACCOUNT", "literal"),
];

// ---------------------------------------------------------------------------
// Injected boundary fakes
// ---------------------------------------------------------------------------

interface AuditGate {
  prepared: boolean;
}

/** N3 boundary model: the raw provider is reachable only after a durable PREPARE. */
class FakeRawProvider implements RawProviderPort<BoundaryGenerateOptions, string> {
  public calls = 0;
  public readonly payloads: string[] = [];

  public constructor(
    private readonly gate: AuditGate,
    private readonly responseText: string,
    private readonly streamChunks: readonly string[],
  ) {}

  public generateText(options: BoundaryGenerateOptions): Promise<TokenizedText> {
    this.#guard();
    this.calls += 1;
    this.payloads.push(JSON.stringify(options));
    return Promise.resolve(this.responseText as unknown as TokenizedText);
  }

  public async generateStream(
    options: BoundaryGenerateOptions,
    onChunk: (chunk: TokenizedText) => void | Promise<void>,
  ): Promise<void> {
    this.#guard();
    this.calls += 1;
    this.payloads.push(JSON.stringify(options));
    for (const chunk of this.streamChunks) {
      await onChunk(chunk as unknown as TokenizedText);
    }
  }

  public embedText(text: TokenizedText, _kind: string): Promise<readonly number[]> {
    this.#guard();
    this.calls += 1;
    this.payloads.push(String(text));
    return Promise.resolve([0.11, 0.22, 0.33]);
  }

  #guard(): void {
    // N3/N4: no provider egress before a durable PREPARED record exists.
    if (!this.gate.prepared) {
      throw new PhiEngineError("AUDIT_DURABILITY_UNAVAILABLE", CONTEXT.operationId, {});
    }
  }
}

/** N2 sink: only branded tokenized text ever reaches a content trace. */
class FakeSafeTrace implements SafeAiTrace {
  public readonly payloads: string[] = [];

  public request(paths: readonly Readonly<{ path: string; text: TokenizedText }>[]): Promise<void> {
    for (const entry of paths) {
      this.payloads.push(String(entry.text));
    }
    return Promise.resolve();
  }

  public response(text: TokenizedText): Promise<void> {
    this.payloads.push(String(text));
    return Promise.resolve();
  }

  public metadata(_values: Readonly<Record<string, string | number | boolean | null>>): Promise<void> {
    // Metadata is counts/IDs only; it never carries content.
    return Promise.resolve();
  }
}

/** Durable primary store; an outage is never treated as success (N4). */
class FakePrimaryStore implements AuditPrimaryStore {
  public available = true;
  public prepareAttempts = 0;
  public readonly finalized: PhiAuditEvent[] = [];
  readonly #prepared = new Set<string>();

  public constructor(private readonly gate: AuditGate) {}

  public prepare(
    record: PhiAuditPreparedRecord,
  ): Promise<
    | Readonly<{ status: "stored"; durableRecordId: string }>
    | Readonly<{ status: "already_exists"; durableRecordId: string }>
    | Readonly<{ status: "unavailable"; fixedFailureCode: string }>
  > {
    this.prepareAttempts += 1;
    if (!this.available) {
      return Promise.resolve({ status: "unavailable", fixedFailureCode: "AUDIT_PRIMARY_UNAVAILABLE" });
    }
    this.gate.prepared = true;
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

class InMemorySpoolVolume implements SpoolVolume {
  public durable = true;
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

class FixedKeyProvider implements SpoolKeyProvider {
  public readonly keyVersion = "key-v1";
  readonly #key = new Uint8Array(32).fill(7);
  public dataKey(): Uint8Array {
    return Uint8Array.from(this.#key);
  }
}

/** Records the classified path count so L5 exhaustiveness is observable. */
class RecordingProjector implements AiProviderOptionProjector<BoundaryGenerateOptions> {
  public classifiedPathCount = 0;
  public constructor(private readonly inner: StructuralOptionsProjector) {}
  public classify(options: BoundaryGenerateOptions): ClassifiedProviderOptions<BoundaryGenerateOptions> {
    const classified = this.inner.classify(options);
    this.classifiedPathCount = classified.segments.length;
    return classified;
  }
}

/** Records the routed provider id so L11 selection is observable. */
class RecordingRouter
  implements OriginalContentProviderRouter<BoundaryGenerateOptions, RawProviderPort<BoundaryGenerateOptions, string>>
{
  public selectedProvider: string | null = null;
  public constructor(
    private readonly inner: OriginalContentBaaRouter<
      BoundaryGenerateOptions,
      RawProviderPort<BoundaryGenerateOptions, string>
    >,
  ) {}
  public async selectUsingOriginalContent(
    options: BoundaryGenerateOptions,
  ): Promise<ProviderRoutingDecision<RawProviderPort<BoundaryGenerateOptions, string>>> {
    const decision = await this.inner.selectUsingOriginalContent(options);
    this.selectedProvider = decision.providerId;
    return decision;
  }
}

function extractOriginalText(options: BoundaryGenerateOptions): string {
  const parts: string[] = [];
  if (typeof options.system === "string") parts.push(options.system);
  for (const message of options.messages ?? []) {
    for (const part of message.content) {
      if (part.type === "text") parts.push(part.text);
    }
  }
  for (const tool of options.tools ?? []) parts.push(tool.description);
  if (typeof options.embeddingText === "string") parts.push(options.embeddingText);
  return parts.join("\n");
}

function countExpectedTextPaths(options: BoundaryGenerateOptions): number {
  let count = 0;
  if (typeof options.system === "string") count += 1;
  for (const message of options.messages ?? []) {
    for (const part of message.content) {
      if (part.type === "text") count += 1;
    }
  }
  count += (options.tools ?? []).length;
  if (typeof options.embeddingText === "string") count += 1;
  return count;
}

// ---------------------------------------------------------------------------
// Rig assembly
// ---------------------------------------------------------------------------

interface RigOptions {
  readonly knownValues?: readonly TaggedValue[];
  readonly matterIsPhiTagged?: boolean;
  readonly forcedProviderId?: string;
  readonly forcedProviderBaaCovered?: boolean;
  readonly claudeBaaEnabled?: boolean;
  readonly forcedProductionSafe?: boolean;
  readonly providerResponseText?: string;
  readonly providerStreamChunks?: readonly string[];
  readonly seedReversal?: (store: InMemoryReversalStore) => void;
}

interface Rig {
  readonly wrapper: ComposedProtectedAiProvider<BoundaryGenerateOptions, string>;
  readonly provider: FakeRawProvider;
  readonly trace: FakeSafeTrace;
  readonly router: RecordingRouter;
  readonly projector: RecordingProjector;
  readonly routerInputHolder: { value: string | null };
}

function makeRig(opts: RigOptions): Rig {
  const gate: AuditGate = { prepared: false };
  const reversalStore = new InMemoryReversalStore();

  const coordinator = new InMemoryDictionaryVersionCoordinator();
  coordinator.noteReady({ tenantId: TENANT, matterId: MATTER }, VERSION_BIGINT);

  const truthReader = new InMemoryCaseTruthReader();
  truthReader.set(
    { tenantId: TENANT, matterId: MATTER, dictionaryVersion: VERSION, sourceTruthRevision: REVISION },
    opts.knownValues ?? DEFAULT_KNOWN_VALUES,
  );

  if (opts.seedReversal !== undefined) {
    opts.seedReversal(reversalStore);
  }

  const engineInstance = new ComposedSubstitutionEngine({
    coordinator,
    truthReader,
    sourceTruthRevision: REVISION,
    reversalStore,
    engineVersion: ENGINE,
  });

  const projector = new RecordingProjector(new StructuralOptionsProjector());
  const trace = new FakeSafeTrace();
  const provider = new FakeRawProvider(
    gate,
    opts.providerResponseText ?? "[[Claimant]]",
    opts.providerStreamChunks ?? ["[[Claimant]]"],
  );

  const primary = new FakePrimaryStore(gate);
  const spool = new Aes256GcmAuditSpool(new InMemorySpoolVolume(), new FixedKeyProvider(), CLOCK);
  const emitter = new DurablePhiAuditEmitter(primary, spool, new ExactAllowListAuditSerializer(), CLOCK);

  const routerInputHolder: { value: string | null } = { value: null };

  const routerConfig: BaaRouterConfig<
    BoundaryGenerateOptions,
    RawProviderPort<BoundaryGenerateOptions, string>
  > = {
    extractOriginalText,
    rawProvider: provider,
    baaProviderId: "azure-openai-baa",
    nonBaaProviderId: "openai",
    claudeBaaEnabled: opts.claudeBaaEnabled ?? true,
    matterIsPhiTagged: opts.matterIsPhiTagged ?? true,
    onInspect: (text): void => {
      routerInputHolder.value = text;
    },
    ...(opts.forcedProviderId !== undefined ? { forcedProviderId: opts.forcedProviderId } : {}),
    ...(opts.forcedProviderBaaCovered !== undefined
      ? { forcedProviderBaaCovered: opts.forcedProviderBaaCovered }
      : {}),
    ...(opts.forcedProductionSafe !== undefined
      ? { forcedProductionSafe: opts.forcedProductionSafe }
      : {}),
  };

  const router = new RecordingRouter(new OriginalContentBaaRouter(routerConfig));

  const wrapper = new ComposedProtectedAiProvider<BoundaryGenerateOptions, string>({
    engine: engineInstance,
    context: CONTEXT_ACCESSOR,
    policy: POLICY_ACCESSOR,
    options: projector,
    router,
    safeTrace: trace,
    audit: emitter,
    invokeRaw: provider,
    engineVersion: ENGINE,
    clock: CLOCK,
    embeddingOptionsFactory: (text: string): BoundaryGenerateOptions => ({ embeddingText: text }),
  });

  return { wrapper, provider, trace, router, projector, routerInputHolder };
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

function observeRig(rig: Rig): Partial<OracleObservation> {
  return {
    providerCalls: rig.provider.calls,
    providerPayloads: [...rig.provider.payloads],
    tracePayloads: [...rig.trace.payloads],
    selectedProvider: rig.router.selectedProvider,
    routerInput: rig.routerInputHolder.value,
  };
}

function asString(value: unknown, fallback: string): string {
  return typeof value === "string" ? value : fallback;
}

function asBool(value: unknown, fallback: boolean): boolean {
  return typeof value === "boolean" ? value : fallback;
}

// ---------------------------------------------------------------------------
// Case dispatch
// ---------------------------------------------------------------------------

async function runCase(
  caseId: string,
  fixture: Readonly<Record<string, unknown>>,
): Promise<OracleObservation> {
  switch (caseId) {
    // ---- N1: all generation crosses the wrapper exactly once, tokenized ----
    case "M-N1-DIRECT-GENERATE": {
      const rig = makeRig({ providerResponseText: "[[Claimant]]" });
      const options: BoundaryGenerateOptions = {
        system: "Assist Maria García.",
        messages: [{ role: "user", content: [{ type: "text", text: "Contact Robert O'Neil." }] }],
        tools: [{ name: "lookup", description: "Look up MRN-A7719 details." }],
      };
      const display = await rig.wrapper.generateText(options);
      return { ...baseObservation(), ...observeRig(rig), displayText: String(display) };
    }

    // ---- N1: streaming egress is tokenized before the provider ----
    case "M-N1-DIRECT-STREAM": {
      const input = asString(fixture["input"], "Maria García MRN-A7719");
      const rig = makeRig({ providerStreamChunks: ["[[Claimant]] ", "[[MRN]]"] });
      const options: BoundaryGenerateOptions = {
        messages: [{ role: "user", content: [{ type: "text", text: input }] }],
      };
      const result: ProtectedStreamResult = await rig.wrapper.generateStream(options);
      return {
        ...baseObservation(),
        ...observeRig(rig),
        displayChunks: result.displayChunks.map((chunk) => String(chunk)),
      };
    }

    // ---- N1: embeddings cross the wrapper (tokenized, not reversed) ----
    case "M-N1-DIRECT-EMBED": {
      const input = asString(fixture["input"], "078-05-1120 MRN-A7719");
      const rig = makeRig({});
      const vector = await rig.wrapper.embedText(input, "default");
      return {
        ...baseObservation(),
        ...observeRig(rig),
        metrics: { embeddingDimensions: vector.length },
      };
    }

    // ---- N2: request traces accept safe (post-substitution) text only ----
    case "M-N2-TRACE-BEFORE-SUBSTITUTE": {
      const input = asString(fixture["input"], "Maria García at 412 May Street");
      const rig = makeRig({ providerResponseText: "[[Claimant]]" });
      const options: BoundaryGenerateOptions = {
        messages: [{ role: "user", content: [{ type: "text", text: input }] }],
      };
      const display = await rig.wrapper.generateText(options);
      return { ...baseObservation(), ...observeRig(rig), displayText: String(display) };
    }

    // ---- N2: output traces remain tokenized; display is reversed ----
    case "M-N2-TRACE-AFTER-REVERSE": {
      const providerOutput = asString(fixture["providerOutput"], "[[Claimant]] lives at [[Address]].");
      const rig = makeRig({
        providerResponseText: providerOutput,
        seedReversal: (store): void => {
          store.record({
            tenantId: TENANT,
            matterId: MATTER,
            dictionaryVersion: VERSION,
            token: token("[[Claimant]]"),
            canonical: "Maria García",
          });
          store.record({
            tenantId: TENANT,
            matterId: MATTER,
            dictionaryVersion: VERSION,
            token: token("[[Address]]"),
            canonical: "412 May Street",
          });
        },
      });
      const options: BoundaryGenerateOptions = {
        messages: [{ role: "user", content: [{ type: "text", text: "Summarize the record." }] }],
      };
      const display = await rig.wrapper.generateText(options);
      return { ...baseObservation(), ...observeRig(rig), displayText: String(display) };
    }

    // ---- L5: every known text option path is projected (exhaustive) ----
    case "M-L5-SKIP-SYSTEM-PROMPT": {
      const rig = makeRig({ providerResponseText: "[[Claimant]]" });
      const options: BoundaryGenerateOptions = {
        system: "Assist Maria García.",
        messages: [
          { role: "user", content: [{ type: "text", text: "Contact Robert O'Neil." }] },
          { role: "user", content: [{ type: "text", text: "SSN 078-05-1120 on file." }] },
        ],
        tools: [{ name: "lookup", description: "Look up MRN-A7719 details." }],
      };
      const display = await rig.wrapper.generateText(options);
      return {
        ...baseObservation(),
        ...observeRig(rig),
        displayText: String(display),
        metrics: {
          classifiedPathCount: rig.projector.classifiedPathCount,
          expectedTextPathCount: countExpectedTextPaths(options),
        },
      };
    }

    // ---- L5: a new/unknown text field fails closed before egress ----
    case "M-L5-ALLOW-UNKNOWN-TEXT-FIELD": {
      const rawOptions =
        (fixture["options"] as Record<string, unknown> | undefined) ?? {
          futureProviderField: "Maria García",
        };
      const rig = makeRig({});
      try {
        await rig.wrapper.generateText(rawOptions as unknown as BoundaryGenerateOptions);
        return { ...baseObservation(), ...observeRig(rig) };
      } catch (error) {
        return {
          ...baseObservation(),
          ...observeRig(rig),
          errorCode: toFailureCode(error, "UNCLASSIFIED_PROVIDER_FIELD"),
        };
      }
    }

    // ---- L11: safety gates remain conjunctive (tokenized != production-safe) ----
    case "M-L11-TOKENIZED-MEANS-PRODUCTION-SAFE": {
      const rig = makeRig({
        forcedProviderId: asString(fixture["selectedProvider"], "anthropic"),
        forcedProviderBaaCovered: false,
        claudeBaaEnabled: asBool(fixture["claudeBaaEnabled"], false),
        forcedProductionSafe: asBool(fixture["isProductionSafe"], false),
      });
      const options: BoundaryGenerateOptions = {
        messages: [{ role: "user", content: [{ type: "text", text: "Maria García update." }] }],
      };
      try {
        await rig.wrapper.generateText(options);
        return { ...baseObservation(), ...observeRig(rig) };
      } catch (error) {
        return {
          ...baseObservation(),
          ...observeRig(rig),
          errorCode: toFailureCode(error, "PROVIDER_SAFETY_GATE_FAILED"),
        };
      }
    }

    // ---- L11: BAA routing inspects ORIGINAL content, not the substituted text ----
    case "M-L11-ROUTE-AFTER-SUBSTITUTE": {
      const original = asString(fixture["original"], "Claimant Maria García has MRN-A7719.");
      const phiTagged = asBool(fixture["phiTaggedMatter"], true);
      const rig = makeRig({ matterIsPhiTagged: phiTagged, providerResponseText: "[[Claimant]]" });
      const options: BoundaryGenerateOptions = {
        messages: [{ role: "user", content: [{ type: "text", text: original }] }],
      };
      const display = await rig.wrapper.generateText(options);
      return { ...baseObservation(), ...observeRig(rig), displayText: String(display) };
    }

    default:
      throw new Error(`provider-boundary.loader: unknown case ${caseId}`);
  }
}

export function loadProviderBoundaryHarness(): ModuleHarness {
  return {
    run(caseId: string, fixture: Readonly<Record<string, unknown>>): Promise<OracleObservation> {
      return runCase(caseId, fixture);
    },
  };
}
