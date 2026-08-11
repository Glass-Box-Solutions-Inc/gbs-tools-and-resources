/**
 * ADDITIVE integration hardening oracles (GLY-330). Each test reproduces a
 * cross-family-gate finding at the COMPOSED boundary — the per-module oracles are
 * green but the composition did not enforce the invariant. Every test was authored
 * red against the pre-fix production code and passes only after the production fix.
 *
 * These tests drive the frozen production classes directly (no invariant is
 * re-implemented here); they never edit any frozen oracle, loader, or harness type.
 */
import { describe, expect, it } from "vitest";

import { ComposedSubstitutionEngine, BOUNDARY_TOKEN_GRAMMAR_POLICY } from "../src/core/orchestrator";
import { ComposedProtectedAiProvider } from "../src/core/wrapper";
import { StructuralOptionsProjector } from "../src/core/options-projector";
import { OriginalContentBaaRouter } from "../src/core/baa-router";
import {
  AtomicTokenReverser,
  BracketTokenGrammar,
  HoldbackReverseStreamFactory,
  InMemoryReversalStore,
  InProcessReversalHandle,
  ReversalFailedError,
  reverseText,
  SENTINEL_OPEN,
} from "../src/tokens/index";
import {
  Aes256GcmAuditSpool,
  DurablePhiAuditEmitter,
  ExactAllowListAuditSerializer,
  isAuditError,
  PhiAuditedAttemptCoordinator,
  PhiAuditError,
  preparedToTerminalEvent,
} from "../src/audit/index";
import {
  decideEgress,
  DictionaryError,
  InMemoryCaseTruthReader,
  InMemoryDictionaryVersionCoordinator,
  isDictionaryError,
} from "../src/dictionary/index";
import { isPhiEngineError, PhiEngineError } from "../src/core/errors";

// ---------------------------------------------------------------------------
// Shared brand casters (runtime identity) + fixtures
// ---------------------------------------------------------------------------
const b = <T>(s: unknown): T => s as T;
const TENANT = b<any>("tenant-1");
const MATTER = b<any>("matter-1");
const LOCALE = "en-US";
const REVISION = "rev-1";
const VERSION_BIGINT = 7n;
const VERSION = b<any>(VERSION_BIGINT);
const ENGINE = b<any>("engine-1");
const SCHEMA = b<any>("schema-1");
const CLOCK = (): string => "2026-01-01T00:00:00.000Z";

function ctx(attemptId = "att-1", operationId = "op-1"): any {
  return {
    tenantId: TENANT,
    matterId: MATTER,
    actorId: b<any>("actor-1"),
    operationId: b<any>(operationId),
    attemptId: b<any>(attemptId),
  };
}

function policy(detectorRequirement: "DISABLED_PHASE_1" | "REQUIRED" = "DISABLED_PHASE_1"): any {
  return {
    mode: "REQUIRED",
    locale: b<any>(LOCALE),
    activeDictionaryVersion: VERSION,
    schemaVersion: SCHEMA,
    detectorRequirement,
    approvedOffDecisionId: null,
  };
}

function tagged(subjectId: string, identifierClass: string, value: string, tokenRole: string): any {
  return {
    field: {
      schemaPath: `case.${subjectId}`,
      substitution: true,
      identifierClass,
      tokenRole: b<any>(tokenRole),
      expander: "literal",
    },
    subjectId: b<any>(subjectId),
    canonicalDisplayValue: value,
    approvedAliases: [],
  };
}

const DEFAULT_TRUTH: any[] = [
  tagged("s-maria", "PERSON_NAME", "Maria García", "Claimant"),
  tagged("s-robert", "PERSON_NAME", "Robert O'Neil", "Claimant"),
  tagged("s-ssn", "SSN", "078-05-1120", "SSN"),
  tagged("s-mrn", "MRN", "MRN-A7719", "MRN"),
  tagged("s-addr", "ADDRESS", "412 May Street", "ADDRESS"),
];

function makeEngine(truth: any[] = DEFAULT_TRUTH, shared?: {
  reversalStore?: InMemoryReversalStore;
}): { engine: ComposedSubstitutionEngine; reversalStore: InMemoryReversalStore } {
  const reversalStore = shared?.reversalStore ?? new InMemoryReversalStore();
  const coordinator = new InMemoryDictionaryVersionCoordinator() as any;
  coordinator.noteReady({ tenantId: TENANT, matterId: MATTER }, VERSION_BIGINT);
  const truthReader = new InMemoryCaseTruthReader() as any;
  truthReader.set(
    { tenantId: TENANT, matterId: MATTER, dictionaryVersion: VERSION, sourceTruthRevision: REVISION },
    truth,
  );
  const engine = new ComposedSubstitutionEngine({
    coordinator,
    truthReader,
    sourceTruthRevision: REVISION,
    reversalStore,
    engineVersion: ENGINE,
  });
  return { engine, reversalStore };
}

// -- audit boundary fakes --------------------------------------------------
interface Gate {
  prepared: boolean;
}

class RecordingPrimaryStore {
  public available = true;
  public prepareAttempts = 0;
  public readonly finalizedEvents: any[] = [];
  readonly #prepared = new Set<string>();
  public constructor(private readonly gate: Gate) {}
  public async prepare(record: any): Promise<any> {
    this.prepareAttempts += 1;
    if (!this.available) return { status: "unavailable", fixedFailureCode: "AUDIT_PRIMARY_UNAVAILABLE" };
    this.gate.prepared = true;
    const id = String(record.attemptId);
    if (this.#prepared.has(id)) return { status: "already_exists", durableRecordId: `primary:${id}` };
    this.#prepared.add(id);
    return { status: "stored", durableRecordId: `primary:${id}` };
  }
  public async finalize(event: any): Promise<void> {
    this.finalizedEvents.push(event);
  }
}

class InMemorySpoolVolume {
  public durable = true;
  readonly #store = new Map<string, Uint8Array>();
  public async putAtomic(recordId: string, bytes: Uint8Array): Promise<any> {
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

class FixedKeyProvider {
  public readonly keyVersion = "key-v1";
  readonly #key = new Uint8Array(32).fill(7);
  public dataKey(): Uint8Array {
    return Uint8Array.from(this.#key);
  }
}

class FakeSafeTrace {
  public readonly payloads: string[] = [];
  public async request(paths: readonly any[]): Promise<void> {
    for (const p of paths) this.payloads.push(String(p.text));
  }
  public async response(text: any): Promise<void> {
    this.payloads.push(String(text));
  }
  public async metadata(): Promise<void> {}
}

class FakeRawProvider {
  public calls = 0;
  public readonly payloads: string[] = [];
  public constructor(
    private readonly gate: Gate,
    private readonly opts: {
      responseText?: string;
      echoMessage?: boolean;
      rejects?: boolean;
      streamChunks?: readonly string[];
    } = {},
  ) {}
  public async generateText(options: any): Promise<any> {
    this.#guard();
    this.calls += 1;
    this.payloads.push(JSON.stringify(options));
    if (this.opts.rejects) throw new Error("provider rejected after send");
    if (this.opts.echoMessage) return options.messages[0].content[0].text;
    return this.opts.responseText ?? "[[Claimant]]";
  }
  public async generateStream(options: any, onChunk: (c: any) => Promise<void> | void): Promise<void> {
    this.#guard();
    this.calls += 1;
    this.payloads.push(JSON.stringify(options));
    for (const c of this.opts.streamChunks ?? ["[[Claimant]]"]) await onChunk(c);
  }
  public async embedText(text: any): Promise<readonly number[]> {
    this.#guard();
    this.calls += 1;
    this.payloads.push(String(text));
    return [0.1, 0.2, 0.3];
  }
  #guard(): void {
    if (!this.gate.prepared) throw new Error("N3: no provider egress before durable prepare");
  }
}

function makeAudit(gate: Gate): { primary: RecordingPrimaryStore; emitter: DurablePhiAuditEmitter } {
  const primary = new RecordingPrimaryStore(gate);
  const spool = new Aes256GcmAuditSpool(new InMemorySpoolVolume() as any, new FixedKeyProvider() as any, CLOCK);
  const emitter = new DurablePhiAuditEmitter(primary as any, spool, new ExactAllowListAuditSerializer(), CLOCK);
  return { primary, emitter };
}

function extractOriginalText(options: any): string {
  const parts: string[] = [];
  if (typeof options.system === "string") parts.push(options.system);
  for (const m of options.messages ?? []) for (const p of m.content) if (typeof p.text === "string") parts.push(p.text);
  for (const t of options.tools ?? []) parts.push(t.description);
  if (typeof options.embeddingText === "string") parts.push(options.embeddingText);
  return parts.join("\n");
}

interface RigOpts {
  truth?: any[];
  matterIsPhiTagged?: boolean;
  baaProvider?: FakeRawProvider;
  providerResponseText?: string;
  echoMessage?: boolean;
  providerRejects?: boolean;
  omitEmbeddingFactory?: boolean;
  detectorRequirement?: "DISABLED_PHASE_1" | "REQUIRED";
  attemptId?: string;
  engineWrap?: (engine: any) => any;
  sharedPrimary?: RecordingPrimaryStore;
  sharedGate?: Gate;
}

function makeWrapperRig(opts: RigOpts = {}): {
  wrapper: ComposedProtectedAiProvider<any, string>;
  provider: FakeRawProvider;
  primary: RecordingPrimaryStore;
  trace: FakeSafeTrace;
} {
  const gate: Gate = opts.sharedGate ?? { prepared: false };
  const { engine } = makeEngine(opts.truth ?? DEFAULT_TRUTH);
  const trace = new FakeSafeTrace();
  const provider = new FakeRawProvider(gate, {
    responseText: opts.providerResponseText,
    echoMessage: opts.echoMessage,
    rejects: opts.providerRejects,
  });

  let primary: RecordingPrimaryStore;
  let emitter: DurablePhiAuditEmitter;
  if (opts.sharedPrimary !== undefined) {
    primary = opts.sharedPrimary;
    const spool = new Aes256GcmAuditSpool(new InMemorySpoolVolume() as any, new FixedKeyProvider() as any, CLOCK);
    emitter = new DurablePhiAuditEmitter(primary as any, spool, new ExactAllowListAuditSerializer(), CLOCK);
  } else {
    const made = makeAudit(gate);
    primary = made.primary;
    emitter = made.emitter;
  }

  const router = new OriginalContentBaaRouter({
    extractOriginalText,
    rawProvider: provider,
    baaProviderId: "azure-openai-baa",
    nonBaaProviderId: "openai",
    claudeBaaEnabled: true,
    matterIsPhiTagged: opts.matterIsPhiTagged ?? true,
    ...(opts.baaProvider !== undefined ? { baaProvider: opts.baaProvider } : {}),
  } as any);

  const deps: any = {
    engine: opts.engineWrap ? opts.engineWrap(engine) : engine,
    context: { require: (): Promise<any> => Promise.resolve(ctx(opts.attemptId ?? "att-1")) },
    policy: { require: (): Promise<any> => Promise.resolve(policy(opts.detectorRequirement)) },
    options: new StructuralOptionsProjector(),
    router,
    safeTrace: trace,
    audit: emitter,
    invokeRaw: provider,
    engineVersion: ENGINE,
    clock: CLOCK,
  };
  if (!opts.omitEmbeddingFactory) {
    deps.embeddingOptionsFactory = (text: string): any => ({ embeddingText: text });
  }
  const wrapper = new ComposedProtectedAiProvider(deps);
  return { wrapper, provider, primary, trace };
}

function joined(payloads: readonly string[]): string {
  return payloads.join("\n");
}

// ===========================================================================
// Finding 1 — L11 provider pinning
// ===========================================================================
describe("GLY-330 finding 1 (L11): wrapper invokes the PINNED routed provider", () => {
  it("invokes the BAA provider the router selected, not the fixed invokeRaw adapter", async () => {
    const gate: Gate = { prepared: false };
    const baaProvider = new FakeRawProvider(gate, { responseText: "[[Claimant]]" });
    const rig = makeWrapperRig({ baaProvider, matterIsPhiTagged: true, sharedGate: gate });
    const options = {
      messages: [{ role: "user", content: [{ type: "text", text: "Maria García update." }] }],
    };
    await rig.wrapper.generateText(options);
    // The routed BAA provider is the one that ran; the fixed adapter must be untouched.
    expect(baaProvider.calls).toBe(1);
    expect(rig.provider.calls).toBe(0);
  });
});

// ===========================================================================
// Finding 2 — L11 embedding gate is not optional (fail closed without a factory)
// ===========================================================================
describe("GLY-330 finding 2 (L11): embedding without a routing factory fails closed", () => {
  it("performs zero egress when embeddingOptionsFactory is missing", async () => {
    const rig = makeWrapperRig({ omitEmbeddingFactory: true });
    let threw = false;
    try {
      await rig.wrapper.embedText("078-05-1120 is on file", "default");
    } catch {
      threw = true;
    }
    expect(threw).toBe(true);
    expect(rig.provider.calls).toBe(0);
  });
});

// ===========================================================================
// Finding 3 — N2: the router never exposes original content to observability
// ===========================================================================
describe("GLY-330 finding 3 (N2): router exposes no original content to an inspect hook", () => {
  it("never hands the original pre-substitution content to an observability callback", async () => {
    const received: string[] = [];
    const provider = new FakeRawProvider({ prepared: true });
    // `onInspect` is the removed observability hook. Passed via cast, it must NEVER be
    // invoked with the original PHI-bearing content.
    const router = new OriginalContentBaaRouter({
      extractOriginalText,
      rawProvider: provider,
      baaProviderId: "azure-openai-baa",
      nonBaaProviderId: "openai",
      claudeBaaEnabled: true,
      matterIsPhiTagged: true,
      onInspect: (t: string): void => {
        received.push(t);
      },
    } as any);
    const decision = await router.selectUsingOriginalContent({
      messages: [{ role: "user", content: [{ type: "text", text: "Claimant Maria García has MRN-A7719." }] }],
    } as any);
    // Routing still works on original content...
    expect(decision.providerId).toBe("azure-openai-baa");
    // ...but no observability sink ever received the canary.
    expect(joined(received)).not.toContain("Maria García");
    expect(received).toHaveLength(0);
  });
});

// ===========================================================================
// Finding 4 — L5/N2 projector exhaustive + fail-closed rebuild
// ===========================================================================
describe("GLY-330 finding 4 (L5): projector is exhaustive and rebuild is fail-closed", () => {
  it("tokenizes a non-\"text\" content part that carries text (tool_result)", async () => {
    const rig = makeWrapperRig({ providerResponseText: "[[Claimant]]" });
    const options = {
      messages: [
        { role: "user", content: [{ type: "tool_result", text: "Patient Maria García" }] },
      ],
    };
    await rig.wrapper.generateText(options);
    expect(rig.provider.calls).toBe(1);
    // The tool_result text must have been substituted, never egressed raw.
    expect(joined(rig.provider.payloads)).not.toContain("Maria García");
  });

  it("fails closed with zero egress when a classified path has no tokenized segment", async () => {
    // Decorate the engine so the tokenized `system` segment is dropped; rebuild must then
    // refuse to leave the raw original `system` value in place and fail closed.
    const rig = makeWrapperRig({
      engineWrap: (engine) => ({
        substitute: async (request: any) => {
          const r = await engine.substitute(request);
          return { ...r, segments: r.segments.filter((s: any) => s.path !== "system") };
        },
        reverse: (t: any, h: any) => engine.reverse(t, h),
        createReverseStream: (h: any, s: any) => engine.createReverseStream(h, s),
      }),
    });
    const options = {
      system: "Assist Maria García.",
      messages: [{ role: "user", content: [{ type: "text", text: "Contact Robert O'Neil." }] }],
    };
    let threw = false;
    try {
      await rig.wrapper.generateText(options);
    } catch {
      threw = true;
    }
    expect(threw).toBe(true);
    expect(rig.provider.calls).toBe(0);
  });
});

// ===========================================================================
// Finding 5 — N4 detectorRequirement REQUIRED fails closed (belt unavailable)
// ===========================================================================
describe("GLY-330 finding 5 (N4): a REQUIRED detector belt that is unavailable fails closed", () => {
  it("performs zero egress when policy REQUIRES the (unavailable) detection belt", async () => {
    const rig = makeWrapperRig({ detectorRequirement: "REQUIRED" });
    let code: string | null = null;
    try {
      await rig.wrapper.generateText({
        messages: [{ role: "user", content: [{ type: "text", text: "Unknown Person not on file." }] }],
      });
    } catch (error) {
      code = (error as any)?.code ?? "THREW";
    }
    expect(code).toBe("DETECTOR_UNAVAILABLE");
    expect(rig.provider.calls).toBe(0);
  });
});

// ===========================================================================
// Finding 6 — N5/L1: subject-scoped tokens; distinct subjects reverse to self
// ===========================================================================
describe("GLY-330 finding 6 (L1/N5): token identity is subject-scoped, never coalesced by class", () => {
  it("gives Alice and Bob distinct tokens that each reverse to their own value", async () => {
    const truth = [
      tagged("s-alice", "PERSON_NAME", "Alice", "Claimant"),
      tagged("s-bob", "PERSON_NAME", "Bob", "Claimant"),
    ];
    const { engine, reversalStore } = makeEngine(truth);
    const result = await engine.substitute({
      context: ctx(),
      policy: policy(),
      segments: [{ path: "messages[0].content[0].text", kind: "user", text: "Alice and Bob met." }],
      purpose: "generation",
    } as any);

    const tokenized = String(result.segments[0].text);
    // Two DISTINCT subject tokens, not one coalesced class token.
    expect(tokenized).toContain("[[Claimant]]");
    expect(tokenized).toContain("[[Claimant_2]]");

    // Reversing the tokenized echo restores each subject to its own value.
    const display = String(await engine.reverse(tokenized as any, result.reversalHandle));
    expect(display).toBe("Alice and Bob met.");

    // Bob's token must NOT reverse to Alice.
    const bobOnly = String(await engine.reverse("[[Claimant_2]]" as any, result.reversalHandle));
    expect(bobOnly).toBe("Bob");
    expect(bobOnly).not.toBe("Alice");

    // Cross-matter isolation (L8): the same token under another matter cannot resolve.
    const otherMatterHandle = new InProcessReversalHandle({
      tenantId: TENANT,
      matterId: b<any>("matter-OTHER"),
      dictionaryVersion: VERSION,
      operationId: b<any>("op-1"),
      attemptId: b<any>("att-1"),
    });
    await expect(engine.reverse("[[Claimant]]" as any, otherMatterHandle as any)).rejects.toBeTruthy();
    void reversalStore;
  });

  it("keeps detector-only tokens operation-scoped so two operations do not cross-contaminate", async () => {
    // Shared reversal + assignment state across two operations of one matter.
    const { engine } = makeEngine([]); // no tagged truth -> the SSNs are detector-only
    const opA = await engine.substitute({
      context: ctx("att-A", "op-A"),
      policy: policy(),
      segments: [{ path: "m", kind: "user", text: "SSN 111-11-1111 on file" }],
      purpose: "generation",
    } as any);
    const opB = await engine.substitute({
      context: ctx("att-B", "op-B"),
      policy: policy(),
      segments: [{ path: "m", kind: "user", text: "SSN 222-22-2222 on file" }],
      purpose: "generation",
    } as any);

    const tokA = String(opA.segments[0].text);
    const tokB = String(opB.segments[0].text);
    // Different operations receive distinct token strings for their detector spans.
    expect(tokA).not.toBe(tokB);

    // op-A reverses to op-A's value even after op-B ran (no shared-key overwrite).
    const displayA = String(await engine.reverse(tokA as any, opA.reversalHandle));
    expect(displayA).toContain("111-11-1111");
    const displayB = String(await engine.reverse(tokB as any, opB.reversalHandle));
    expect(displayB).toContain("222-22-2222");
    expect(displayA).not.toContain("222-22-2222");
  });
});

// ===========================================================================
// Finding 7 — L6 escaped literals restored on the reversed output
// ===========================================================================
describe("GLY-330 finding 7 (L6): source token literals round-trip on the reversed output", () => {
  it("restores a literal [[Claimant]] instead of leaking the escape sentinel", async () => {
    const rig = makeWrapperRig({ echoMessage: true });
    const display = String(
      await rig.wrapper.generateText({
        messages: [{ role: "user", content: [{ type: "text", text: "Repeat [[Claimant]] exactly." }] }],
      }),
    );
    expect(display).toBe("Repeat [[Claimant]] exactly.");
    // No private-use sentinel char leaked to the display surface.
    expect(display).not.toContain("");
    expect(display).not.toContain("");
  });
});

// ===========================================================================
// Finding 8 — L4 M-1 holdback + reversal-failure latch
// ===========================================================================
describe("GLY-330 finding 8 (L4): streaming holds back M-1 units and latches on failure", () => {
  const grammar = new BracketTokenGrammar();
  const factory = new HoldbackReverseStreamFactory();
  function handle(): any {
    return new InProcessReversalHandle({
      tenantId: TENANT,
      matterId: MATTER,
      dictionaryVersion: VERSION,
      operationId: b<any>("op-1"),
      attemptId: b<any>("att-1"),
    });
  }

  it("retains at least M-1 UTF-16 units at the tail (nothing emitted for 63 ordinary units)", async () => {
    const store = new InMemoryReversalStore();
    const emitted: string[] = [];
    const stream = factory.create({
      handle: handle(),
      store,
      grammar,
      policy: BOUNDARY_TOKEN_GRAMMAR_POLICY,
      sink: (safe: any) => {
        emitted.push(String(safe));
      },
    });
    await stream.push("a".repeat(63) as any); // M = 64 -> hold back >= 63.
    expect(emitted.join("")).toHaveLength(0);
  });

  it("latches after a reversal failure so a later push/end cannot resume", async () => {
    const store = new InMemoryReversalStore();
    store.record({
      tenantId: TENANT,
      matterId: MATTER,
      dictionaryVersion: VERSION,
      token: b<any>("[[Claimant]]"),
      canonical: "Alice",
    });
    const emitted: string[] = [];
    const stream = factory.create({
      handle: handle(),
      store,
      grammar,
      policy: BOUNDARY_TOKEN_GRAMMAR_POLICY,
      sink: (safe: any) => {
        emitted.push(String(safe));
      },
    });
    // Push an unknown token far enough from the tail that it lands in the settled prefix
    // and fails on push.
    let firstFailed = false;
    try {
      await stream.push(("[[Unknown_99]]" + "x".repeat(90)) as any);
    } catch {
      firstFailed = true;
    }
    expect(firstFailed).toBe(true);
    // A subsequent valid mapped token must NOT be emitted (the stream is latched).
    try {
      await stream.push(("[[Claimant]]" + "y".repeat(90)) as any);
    } catch {
      /* latched pushes may no-op */
    }
    try {
      await stream.end();
    } catch {
      /* latched end may no-op */
    }
    expect(emitted.join("")).not.toContain("Alice");
  });
});

// ===========================================================================
// Finding 9 — N3 terminal on every failure path
// ===========================================================================
describe("GLY-330 finding 9 (N3): a terminal audit event is finalized on failure paths", () => {
  it("finalizes exactly one terminal when the provider rejects after send", async () => {
    const rig = makeWrapperRig({ providerRejects: true });
    let threw = false;
    try {
      await rig.wrapper.generateText({
        messages: [{ role: "user", content: [{ type: "text", text: "Maria García update." }] }],
      });
    } catch {
      threw = true;
    }
    expect(threw).toBe(true);
    // Not stuck in PREPARED: exactly one terminal exists.
    expect(rig.primary.finalizedEvents).toHaveLength(1);
  });

  it("records a failed-closed terminal for an unclassified option (before prepare)", async () => {
    const rig = makeWrapperRig();
    let threw = false;
    try {
      await rig.wrapper.generateText({ futureProviderField: "Maria García" } as any);
    } catch {
      threw = true;
    }
    expect(threw).toBe(true);
    expect(rig.provider.calls).toBe(0);
    expect(rig.primary.finalizedEvents).toHaveLength(1);
    expect(JSON.stringify(rig.primary.finalizedEvents[0])).toContain("failed_closed");
  });
});

// ===========================================================================
// Finding 10 — N3 exactly-one terminal / idempotency by attempt id
// ===========================================================================
describe("GLY-330 finding 10 (N3): repeat attempt id yields one provider call + one terminal", () => {
  it("does not egress or finalize a second time for the same attempt id", async () => {
    const gate: Gate = { prepared: false };
    const primary = new RecordingPrimaryStore(gate);
    const rig = makeWrapperRig({ sharedGate: gate, sharedPrimary: primary, attemptId: "att-dup" });
    const options = {
      messages: [{ role: "user", content: [{ type: "text", text: "Maria García update." }] }],
    };
    await rig.wrapper.generateText(options);
    try {
      await rig.wrapper.generateText(options); // same attempt id
    } catch {
      /* the duplicate attempt is refused */
    }
    expect(rig.provider.calls).toBe(1);
    expect(primary.finalizedEvents).toHaveLength(1);
  });
});

// ===========================================================================
// Finding 11 — N3/N4 durable spool + crash-safe drain
// ===========================================================================
describe("GLY-330 finding 11 (N3/N4): spool is volume-durable and drain is crash-safe", () => {
  function preparedRecord(attemptId: string): any {
    return {
      state: "PREPARED",
      attemptId: b<any>(attemptId),
      operationId: b<any>("op-1"),
      tenantId: TENANT,
      matterId: MATTER,
      actorId: b<any>("actor-1"),
      operation: "generation",
      dictionaryVersion: VERSION,
      engineVersion: ENGINE,
      counts: {
        PERSON_NAME: 0, DOB: 0, SSN: 0, MRN: 0, DEA: 0, EMAIL: 0, PHONE: 0,
        ADDRESS: 0, CLAIM_NUMBER: 0, POLICY_NUMBER: 0, ACCOUNT_NUMBER: 0, OTHER_TAGGED: 0,
      },
      ambiguityCount: 0,
      detectorName: null,
      detectorVersion: null,
      latencyMs: { dictionary: 1, detector: 0, total: 2 },
      preparedAt: CLOCK(),
    };
  }
  function terminal(record: any): any {
    return {
      eventType: "AI_SUBSTITUTION_ATTEMPT",
      attemptId: record.attemptId,
      operationId: record.operationId,
      tenantId: record.tenantId,
      matterId: record.matterId,
      actorId: record.actorId,
      operation: record.operation,
      dictionaryVersion: String(VERSION_BIGINT),
      engineVersion: record.engineVersion,
      counts: record.counts,
      ambiguityCount: 0,
      detectorName: null,
      detectorVersion: null,
      latencyMs: record.latencyMs,
      outcome: "completed",
      failureCode: null,
      occurredAt: CLOCK(),
    };
  }

  it("rebuilds durable records from the volume after a restart so drain finds them", async () => {
    const volume = new InMemorySpoolVolume();
    const spool1 = new Aes256GcmAuditSpool(volume as any, new FixedKeyProvider() as any, CLOCK);
    const rec = preparedRecord("r1");
    const receipt = await spool1.appendPrepared(rec);
    await spool1.finalize(receipt, terminal(rec));

    // Simulated restart: a brand-new spool over the SAME durable volume (empty in-memory index).
    const spool2 = new Aes256GcmAuditSpool(volume as any, new FixedKeyProvider() as any, CLOCK);
    const gate: Gate = { prepared: false };
    const primary = new RecordingPrimaryStore(gate);
    const report = await spool2.drainTo(primary as any);
    expect(report.delivered).toBe(1);
    expect(primary.finalizedEvents.map((e) => String(e.attemptId))).toContain("r1");
  });

  it("does not lose the terminal when finalize fails then a retry succeeds", async () => {
    const volume = new InMemorySpoolVolume();
    const spool = new Aes256GcmAuditSpool(volume as any, new FixedKeyProvider() as any, CLOCK);
    const rec = preparedRecord("r2");
    const receipt = await spool.appendPrepared(rec);
    await spool.finalize(receipt, terminal(rec));

    // Primary: prepare succeeds; the FIRST finalize throws (partial), later ones succeed.
    const flaky = {
      prepared: new Set<string>(),
      finalizeCalls: 0,
      finalizedEvents: [] as any[],
      async prepare(record: any): Promise<any> {
        const id = String(record.attemptId);
        if (this.prepared.has(id)) return { status: "already_exists", durableRecordId: `p:${id}` };
        this.prepared.add(id);
        return { status: "stored", durableRecordId: `p:${id}` };
      },
      async finalize(event: any): Promise<void> {
        this.finalizeCalls += 1;
        if (this.finalizeCalls === 1) throw new Error("finalize transient outage");
        this.finalizedEvents.push(event);
      },
    };

    await spool.drainTo(flaky as any).catch(() => undefined); // partial: prepare ok, finalize failed
    await spool.drainTo(flaky as any); // retry must still deliver the terminal

    expect(flaky.finalizedEvents.map((e) => String(e.attemptId))).toContain("r2");
    // The delivered entry is discarded only after a successful finalize.
    expect(spool.recordIds()).toHaveLength(0);
  });
});

// ===========================================================================
// ROUND 2 — gate's EXACT reproduced scenarios (red-before / green-after)
// ===========================================================================

/** A tagged case-truth value with an explicit expander (variants use "person-name"). */
function taggedWith(
  subjectId: string,
  identifierClass: string,
  value: string,
  tokenRole: string,
  expander: string,
  approvedAliases: string[] = [],
): any {
  return {
    field: {
      schemaPath: `case.${subjectId}`,
      substitution: true,
      identifierClass,
      tokenRole: b<any>(tokenRole),
      expander,
    },
    subjectId: b<any>(subjectId),
    canonicalDisplayValue: value,
    approvedAliases,
  };
}

/** Manual wrapper builder allowing custom policy/router/trace/primary injection. */
function buildManualWrapper(
  gate: Gate,
  over: {
    truth?: any[];
    policyFn?: () => Promise<any>;
    router?: any;
    trace?: any;
    sharedPrimary?: RecordingPrimaryStore;
    engineWrap?: (e: any) => any;
    audit?: any;
    provider?: FakeRawProvider;
  } = {},
): { wrapper: ComposedProtectedAiProvider<any, string>; provider: FakeRawProvider; primary: RecordingPrimaryStore; trace: any } {
  const { engine } = makeEngine(over.truth ?? DEFAULT_TRUTH);
  const provider = over.provider ?? new FakeRawProvider(gate);
  const trace = over.trace ?? new FakeSafeTrace();
  const primary = over.sharedPrimary ?? new RecordingPrimaryStore(gate);
  const spool = new Aes256GcmAuditSpool(new InMemorySpoolVolume() as any, new FixedKeyProvider() as any, CLOCK);
  // A test may inject its own emitter (e.g. one whose finalize rejects, or a permissive emitter
  // with no idempotency short-circuit) to probe the wrapper's sanitize/no-double-prepare invariants.
  const emitter = over.audit ?? new DurablePhiAuditEmitter(primary as any, spool, new ExactAllowListAuditSerializer(), CLOCK);
  const router =
    over.router ??
    new OriginalContentBaaRouter({
      extractOriginalText,
      rawProvider: provider,
      baaProviderId: "azure-openai-baa",
      nonBaaProviderId: "openai",
      claudeBaaEnabled: true,
      matterIsPhiTagged: true,
    } as any);
  const deps: any = {
    engine: over.engineWrap ? over.engineWrap(engine) : engine,
    context: { require: (): Promise<any> => Promise.resolve(ctx()) },
    policy: { require: over.policyFn ?? ((): Promise<any> => Promise.resolve(policy())) },
    options: new StructuralOptionsProjector(),
    router,
    safeTrace: trace,
    audit: emitter,
    invokeRaw: provider,
    engineVersion: ENGINE,
    clock: CLOCK,
    embeddingOptionsFactory: (text: string): any => ({ embeddingText: text }),
  };
  const wrapper = new ComposedProtectedAiProvider(deps);
  return { wrapper, provider, primary, trace };
}

function spoolPrepared(attemptId: string): any {
  return {
    state: "PREPARED",
    attemptId: b<any>(attemptId),
    operationId: b<any>("op-1"),
    tenantId: TENANT,
    matterId: MATTER,
    actorId: b<any>("actor-1"),
    operation: "generation",
    dictionaryVersion: VERSION,
    engineVersion: ENGINE,
    counts: {
      PERSON_NAME: 0, DOB: 0, SSN: 0, MRN: 0, DEA: 0, EMAIL: 0, PHONE: 0,
      ADDRESS: 0, CLAIM_NUMBER: 0, POLICY_NUMBER: 0, ACCOUNT_NUMBER: 0, OTHER_TAGGED: 0,
    },
    ambiguityCount: 0,
    detectorName: null,
    detectorVersion: null,
    latencyMs: { dictionary: 1, detector: 0, total: 2 },
    preparedAt: CLOCK(),
  };
}

function spoolTerminal(record: any): any {
  return {
    eventType: "AI_SUBSTITUTION_ATTEMPT",
    attemptId: record.attemptId,
    operationId: record.operationId,
    tenantId: record.tenantId,
    matterId: record.matterId,
    actorId: record.actorId,
    operation: record.operation,
    dictionaryVersion: String(VERSION_BIGINT),
    engineVersion: record.engineVersion,
    counts: record.counts,
    ambiguityCount: 0,
    detectorName: null,
    detectorVersion: null,
    latencyMs: record.latencyMs,
    outcome: "completed",
    failureCode: null,
    occurredAt: CLOCK(),
  };
}

// ---------------------------------------------------------------------------
// ROOT / NEW-1 — orchestrator composes the compiler's variant-expanded matcher
// ---------------------------------------------------------------------------
describe("GLY-330 NEW-1 (L10/§4): orchestrator composes the compiler's variant-expanded Aho-Corasick output", () => {
  it("substitutes the approved person-name variant 'Smith, Alice' instead of leaking it raw", async () => {
    const truth = [taggedWith("s-alice", "PERSON_NAME", "Alice Smith", "Claimant", "person-name")];
    const { engine } = makeEngine(truth);
    const result = await engine.substitute({
      context: ctx(),
      policy: policy(),
      segments: [{ path: "m", kind: "user", text: "Please contact Smith, Alice today." }],
      purpose: "generation",
    } as any);
    const tokenized = String(result.segments[0].text);
    // The reordered variant must be substituted, never egressed raw.
    expect(tokenized).not.toContain("Smith");
    expect(tokenized).not.toContain("Alice");
    expect(tokenized).toContain("[[Claimant]]");
    // And it reverses to the CURRENT canonical value.
    const display = String(await engine.reverse(tokenized as any, result.reversalHandle));
    expect(display).toBe("Please contact Alice Smith today.");
  });
});

// ---------------------------------------------------------------------------
// #6 — subject-scoped tokens for ALL classes; synthetic vs real never collide
// ---------------------------------------------------------------------------
describe("GLY-330 finding 6 R2 (L1/N5): detector-only synthetic subjects never share a key with real subjects", () => {
  it("keeps a real SSN subject whose id equals the old synthetic shape distinct from a detector-only SSN", async () => {
    // A real tagged SSN subject whose subjectId is exactly the OLD synthetic shape `det:op-A:1`.
    const truth = [taggedWith("det:op-A:1", "SSN", "222-22-2222", "SSN", "literal")];
    const { engine } = makeEngine(truth);
    const result = await engine.substitute({
      context: ctx("att-A", "op-A"),
      policy: policy(),
      // detector-only 111-11-1111 first, then the real tagged 222-22-2222.
      segments: [{ path: "m", kind: "user", text: "SSN 111-11-1111 and 222-22-2222 on file." }],
      purpose: "generation",
    } as any);
    const tokenized = String(result.segments[0].text);
    const display = String(await engine.reverse(tokenized as any, result.reversalHandle));
    // Each SSN reverses to ITS OWN value; the real subject never overwrote the detector-only one.
    expect(display).toBe("SSN 111-11-1111 and 222-22-2222 on file.");
  });
});

// ---------------------------------------------------------------------------
// NEW-2 — the in-process handle exposes no raw literal data
// ---------------------------------------------------------------------------
describe("GLY-330 NEW-2 (§7): the reversal handle is an opaque capability (no raw literal via property/spread)", () => {
  it("does not expose EscapedTokenLiteral.originalLiteral through property access or object spread", async () => {
    const { engine } = makeEngine();
    const result = await engine.substitute({
      context: ctx(),
      policy: policy(),
      segments: [{ path: "m", kind: "user", text: "Echo [[Claimant]] please." }],
      purpose: "generation",
    } as any);
    const handle: any = result.reversalHandle;
    // Direct property access must not expose the raw token-shaped source literal.
    expect(handle.literals).toBeUndefined();
    // Object spread must not carry any raw literal data.
    const spread = JSON.stringify({ ...handle });
    expect(spread).not.toContain("[[Claimant]]");
    // toJSON still throws so it cannot be smuggled into a trace/job/cache payload.
    expect(() => JSON.stringify(handle)).toThrow();
  });
});

// ---------------------------------------------------------------------------
// #7 — streaming reversal restores escaped source literals (no sentinel leak)
// ---------------------------------------------------------------------------
describe("GLY-330 finding 7 R2 (L6): streaming reversal restores escaped literals, never leaking the sentinel", () => {
  it("emits the source literal [[Claimant]] on the streamed output, not the escape sentinel", async () => {
    const { engine } = makeEngine();
    const result = await engine.substitute({
      context: ctx(),
      policy: policy(),
      segments: [{ path: "m", kind: "user", text: "Echo [[Claimant]] please." }],
      purpose: "generation",
    } as any);
    const tokenized = String(result.segments[0].text); // contains the escape sentinel
    const emitted: string[] = [];
    const stream = engine.createReverseStream(result.reversalHandle, (safe) => {
      emitted.push(String(safe));
    });
    await stream.push(tokenized as any);
    await stream.end();
    const display = emitted.join("");
    expect(display).toBe("Echo [[Claimant]] please.");
    expect(display).not.toContain(SENTINEL_OPEN);
  });
});

// ---------------------------------------------------------------------------
// #8 — the M-1 holdback must never split a COMPLETE, valid token
// ---------------------------------------------------------------------------
describe("GLY-330 finding 8 R2 (L4): a complete token is never split by the M-1 holdback cut", () => {
  const grammar = new BracketTokenGrammar();
  const factory = new HoldbackReverseStreamFactory();
  function handle(): any {
    return new InProcessReversalHandle({
      tenantId: TENANT,
      matterId: MATTER,
      dictionaryVersion: VERSION,
      operationId: b<any>("op-1"),
      attemptId: b<any>("att-1"),
    });
  }

  it("reverses a complete token + 60 ordinary chars in one chunk without aborting (len 72, cut 9)", async () => {
    const store = new InMemoryReversalStore();
    store.record({
      tenantId: TENANT,
      matterId: MATTER,
      dictionaryVersion: VERSION,
      token: b<any>("[[Claimant]]"),
      canonical: "Alice",
    });
    const emitted: string[] = [];
    const stream = factory.create({
      handle: handle(),
      store,
      grammar,
      policy: BOUNDARY_TOKEN_GRAMMAR_POLICY,
      sink: (safe: any) => {
        emitted.push(String(safe));
      },
    });
    // One chunk: a COMPLETE token then 60 ordinary chars (len 72 -> M-1 cut 9, inside the token).
    await stream.push(("[[Claimant]]" + "x".repeat(60)) as any);
    await stream.end();
    expect(emitted.join("")).toBe("Alice" + "x".repeat(60));
  });
});

// ---------------------------------------------------------------------------
// #3 — router/callback errors are sanitized before caller and audit
// ---------------------------------------------------------------------------
describe("GLY-330 finding 3 R2 (N2/§7): unknown router/callback errors never leak text/code", () => {
  it("never surfaces a raw error message/code to the caller nor stores it as the audit failureCode", async () => {
    const gate: Gate = { prepared: false };
    const badError: any = new Error("Maria García");
    badError.code = "Maria García";
    const router = new OriginalContentBaaRouter({
      extractOriginalText: (): string => {
        throw badError;
      },
      rawProvider: new FakeRawProvider(gate),
      baaProviderId: "azure-openai-baa",
      nonBaaProviderId: "openai",
      claudeBaaEnabled: true,
      matterIsPhiTagged: true,
    } as any);
    const built = buildManualWrapper(gate, { router });
    let thrown: any;
    try {
      await built.wrapper.generateText({
        messages: [{ role: "user", content: [{ type: "text", text: "hi" }] }],
      });
    } catch (e) {
      thrown = e;
    }
    expect(thrown).toBeTruthy();
    // (a) No raw canary reaches the caller (message or code).
    expect(String(thrown?.message ?? "")).not.toContain("Maria García");
    expect(String(thrown?.code ?? "")).not.toContain("Maria García");
    // (b) No raw canary is stored as the audit failureCode.
    expect(JSON.stringify(built.primary.finalizedEvents)).not.toContain("Maria García");
    // A single terminal was still finalized (N3), and nothing egressed.
    expect(built.primary.finalizedEvents).toHaveLength(1);
    expect(built.provider.calls).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// #4 — projector validates provider-visible strings and preserves non-text knobs
// ---------------------------------------------------------------------------
describe("GLY-330 finding 4 R2 (L5): provider-visible strings validated + non-text knobs preserved", () => {
  it("fails closed when a tool name carries a PHI canary, never egressing it raw", async () => {
    const rig = makeWrapperRig({});
    let threw = false;
    try {
      await rig.wrapper.generateText({
        messages: [{ role: "user", content: [{ type: "text", text: "hello" }] }],
        tools: [{ name: "Maria García", description: "Look things up." }],
      } as any);
    } catch {
      threw = true;
    }
    expect(threw).toBe(true);
    expect(rig.provider.calls).toBe(0);
    expect(joined(rig.provider.payloads)).not.toContain("Maria García");
  });

  it("preserves non-text sampling knobs (model/temperature/maxTokens) unchanged to the provider", async () => {
    const rig = makeWrapperRig({ providerResponseText: "[[Claimant]]" });
    await rig.wrapper.generateText({
      model: "claude-x",
      temperature: 0.2,
      maxTokens: 512,
      messages: [{ role: "user", content: [{ type: "text", text: "Maria García update." }] }],
    } as any);
    expect(rig.provider.calls).toBe(1);
    const sent = JSON.parse(rig.provider.payloads[0] ?? "{}");
    expect(sent.model).toBe("claude-x");
    expect(sent.temperature).toBe(0.2);
    expect(sent.maxTokens).toBe(512);
  });
});

// ---------------------------------------------------------------------------
// #9 — exactly one terminal on EVERY failure path (no lost receipt, no double-prepare)
// ---------------------------------------------------------------------------
describe("GLY-330 finding 9 R2 (N3): exactly one terminal on every failure path", () => {
  it("finalizes exactly one terminal when policy load fails (context is known)", async () => {
    const gate: Gate = { prepared: false };
    const built = buildManualWrapper(gate, {
      policyFn: (): Promise<any> =>
        Promise.reject(new PhiEngineError("MISSING_TRUSTED_POLICY", b<any>("op-1"), {})),
    });
    let threw = false;
    try {
      await built.wrapper.generateText({
        messages: [{ role: "user", content: [{ type: "text", text: "Maria García update." }] }],
      });
    } catch {
      threw = true;
    }
    expect(threw).toBe(true);
    expect(built.provider.calls).toBe(0);
    expect(built.primary.finalizedEvents).toHaveLength(1);
  });

  it("finalizes exactly one terminal when createReverseStream throws after prepare (stream)", async () => {
    const gate: Gate = { prepared: false };
    const built = buildManualWrapper(gate, {
      engineWrap: (engine) => ({
        substitute: (r: any) => engine.substitute(r),
        reverse: (t: any, h: any) => engine.reverse(t, h),
        createReverseStream: (): never => {
          throw new Error("stream factory boom");
        },
      }),
    });
    let threw = false;
    try {
      await built.wrapper.generateStream({
        messages: [{ role: "user", content: [{ type: "text", text: "Maria García update." }] }],
      });
    } catch {
      threw = true;
    }
    expect(threw).toBe(true);
    expect(built.primary.finalizedEvents).toHaveLength(1);
  });

  it("finalizes exactly one terminal when response tracing throws after send (generation)", async () => {
    const gate: Gate = { prepared: false };
    const trace = {
      request: async (): Promise<void> => undefined,
      response: async (): Promise<void> => {
        throw new Error("response trace boom");
      },
      metadata: async (): Promise<void> => undefined,
    };
    const built = buildManualWrapper(gate, { trace });
    let threw = false;
    try {
      await built.wrapper.generateText({
        messages: [{ role: "user", content: [{ type: "text", text: "Maria García update." }] }],
      });
    } catch {
      threw = true;
    }
    expect(threw).toBe(true);
    expect(built.provider.calls).toBe(1);
    expect(built.primary.finalizedEvents).toHaveLength(1);
  });

  it("finalizes exactly one terminal (no double-prepare) when request tracing fails after prepare", async () => {
    const gate: Gate = { prepared: false };
    const primary = new RecordingPrimaryStore(gate);
    const trace = {
      request: async (): Promise<void> => {
        throw new Error("request trace boom");
      },
      response: async (): Promise<void> => undefined,
      metadata: async (): Promise<void> => undefined,
    };
    const built = buildManualWrapper(gate, { trace, sharedPrimary: primary });
    let threw = false;
    try {
      await built.wrapper.generateText({
        messages: [{ role: "user", content: [{ type: "text", text: "Maria García update." }] }],
      });
    } catch {
      threw = true;
    }
    expect(threw).toBe(true);
    expect(built.provider.calls).toBe(0);
    expect(primary.finalizedEvents).toHaveLength(1);
    expect(primary.prepareAttempts).toBe(1);
  });
});

// ---------------------------------------------------------------------------
// #10 — a finalized attempt can never egress again, even after restart
// ---------------------------------------------------------------------------
describe("GLY-330 finding 10 R2 (N3): durable idempotency survives restart", () => {
  it("refuses a fresh spool append for an attempt already finalized on the durable volume", async () => {
    const volume = new InMemorySpoolVolume();
    const spool1 = new Aes256GcmAuditSpool(volume as any, new FixedKeyProvider() as any, CLOCK);
    const rec = spoolPrepared("att-x");
    const receipt = await spool1.appendPrepared(rec);
    await spool1.finalize(receipt, spoolTerminal(rec));

    // Restart: a brand-new spool over the SAME durable volume.
    const spool2 = new Aes256GcmAuditSpool(volume as any, new FixedKeyProvider() as any, CLOCK);
    let refused = false;
    try {
      await spool2.appendPrepared(rec); // same attempt id, already finalized
    } catch {
      refused = true;
    }
    expect(refused).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// #11 — crash-safe drain (durable preparedInPrimary) + bigint dictionaryVersion
// ---------------------------------------------------------------------------
describe("GLY-330 finding 11 R2 (N3/N4): drain is crash-safe across restart and rehydrates the branded version", () => {
  it("still delivers the terminal after restart when a prior finalize failed", async () => {
    const volume = new InMemorySpoolVolume();
    const spool1 = new Aes256GcmAuditSpool(volume as any, new FixedKeyProvider() as any, CLOCK);
    const rec = spoolPrepared("att-r");
    const receipt = await spool1.appendPrepared(rec);
    await spool1.finalize(receipt, spoolTerminal(rec));

    // A primary whose FIRST finalize fails (transient), later ones succeed.
    const primary = {
      prepared: new Set<string>(),
      finalizeCalls: 0,
      finalizedEvents: [] as any[],
      async prepare(r: any): Promise<any> {
        const id = String(r.attemptId);
        if (this.prepared.has(id)) return { status: "already_exists", durableRecordId: `p:${id}` };
        this.prepared.add(id);
        return { status: "stored", durableRecordId: `p:${id}` };
      },
      async finalize(e: any): Promise<void> {
        this.finalizeCalls += 1;
        if (this.finalizeCalls === 1) throw new Error("finalize outage");
        this.finalizedEvents.push(e);
      },
    };

    // First drain: primary prepared ok, finalize failed -> entry kept.
    await spool1.drainTo(primary as any).catch(() => undefined);

    // RESTART: new spool over the same durable volume; primary already holds the PREPARED record.
    const spool2 = new Aes256GcmAuditSpool(volume as any, new FixedKeyProvider() as any, CLOCK);
    await spool2.drainTo(primary as any);

    expect(primary.finalizedEvents.map((e: any) => String(e.attemptId))).toContain("att-r");
    expect(spool2.recordIds()).toHaveLength(0);
  });

  it("rehydrates the rebuilt PREPARED record's dictionaryVersion to a branded bigint", async () => {
    const volume = new InMemorySpoolVolume();
    const spool1 = new Aes256GcmAuditSpool(volume as any, new FixedKeyProvider() as any, CLOCK);
    await spool1.appendPrepared(spoolPrepared("att-b")); // no finalize -> drain reconstructs

    const spool2 = new Aes256GcmAuditSpool(volume as any, new FixedKeyProvider() as any, CLOCK);
    const captured: any[] = [];
    const primary = {
      async prepare(r: any): Promise<any> {
        captured.push(r);
        return { status: "stored", durableRecordId: `p:${String(r.attemptId)}` };
      },
      async finalize(): Promise<void> {
        return undefined;
      },
    };
    await spool2.drainTo(primary as any);
    expect(captured).toHaveLength(1);
    expect(typeof captured[0].dictionaryVersion).toBe("bigint");
    expect(captured[0].dictionaryVersion).toBe(VERSION_BIGINT);
  });
});

// ---------------------------------------------------------------------------
// NEW-1 R3 — structured-id separator variants are composed, not just person-name
// ---------------------------------------------------------------------------
describe("GLY-330 NEW-1 R3 (N7/L10): structured-id separator variants are substituted through the composed engine", () => {
  function structuredIdTruth(): any[] {
    return [
      {
        field: {
          schemaPath: "case.s-claim",
          substitution: true,
          identifierClass: "MRN",
          tokenRole: b<any>("MRN"),
          expander: "structured-id",
          // permitted separators encoded as a scalar (field.options is frozen to scalars): "-" and " ".
          options: { permittedSeparators: "- ", requiredAlphaPrefix: "CLM" },
        },
        subjectId: b<any>("s-claim"),
        canonicalDisplayValue: "CLM-00421",
        approvedAliases: [],
      },
    ];
  }

  it("substitutes the space-separated variant of a tagged structured id, never egressing it raw", async () => {
    const { engine } = makeEngine(structuredIdTruth());
    const result = await engine.substitute({
      context: ctx(),
      policy: policy(),
      // The provider-bound text uses the SPACE variant of canonical `CLM-00421`.
      segments: [{ path: "m", kind: "user", text: "Claim CLM 00421 is pending." }],
      purpose: "generation",
    } as any);
    const tokenized = String(result.segments[0].text);
    expect(tokenized).not.toContain("CLM 00421");
    expect(tokenized).toContain("[[");
  });

  it("still substitutes the canonical hyphen form (canonical is never dropped by a partial policy)", async () => {
    const { engine } = makeEngine(structuredIdTruth());
    const result = await engine.substitute({
      context: ctx(),
      policy: policy(),
      segments: [{ path: "m", kind: "user", text: "Claim CLM-00421 is pending." }],
      purpose: "generation",
    } as any);
    const tokenized = String(result.segments[0].text);
    expect(tokenized).not.toContain("CLM-00421");
    expect(tokenized).toContain("[[");
  });
});

// ===========================================================================
// R5 — the round-5 gate found the round-4 fixes STILL-BROKEN on PARALLEL paths
// (the recurring failure mode). These lock every parallel path at the chokepoint
// level. Each was authored red against the pre-fix code (revert the cited line →
// the naming test goes red).
// ===========================================================================

// -- audit fakes for the R5 sanitize / no-double-prepare probes ---------------

/** PREPARE succeeds (arming the provider gate); FINALIZE rejects with a RAW, PHI-carrying error.
 *  Probes that no caller surfaces that raw message/code on a SUCCESS path (#3). */
class FinalizeRejectingAudit {
  public prepareCalls = 0;
  public finalizeCalls = 0;
  public constructor(private readonly gate: Gate) {}
  public async prepare(record: any): Promise<any> {
    this.prepareCalls += 1;
    this.gate.prepared = true;
    return { attemptId: record.attemptId, location: "PRIMARY_STORE", durableRecordId: "r-1" };
  }
  public async finalize(): Promise<void> {
    this.finalizeCalls += 1;
    const raw: any = new Error("RAW_FINALIZER_ALICE");
    raw.code = "RAW_FINALIZER_CODE";
    throw raw;
  }
}

/** Primary store whose PREPARE always throws a RAW (non-audit) error — probes that the emitter
 *  sanitizes it to a PhiAuditError so the wrapper never re-prepares (#9 no-double-prepare). */
class ThrowingPrimaryStore {
  public prepareCalls = 0;
  public async prepare(_record: any): Promise<any> {
    this.prepareCalls += 1;
    const raw: any = new Error("RAW_PREPARE_ALICE");
    raw.code = "RAW_PREPARE_CODE";
    throw raw;
  }
  public async finalize(): Promise<void> {
    /* not reached */
  }
}

/** Permissive emitter: stores every prepare and counts terminals, with NO N3 idempotency
 *  short-circuit — so a wrapper that STRUCTURALLY double-prepares is caught (a real emitter's
 *  short-circuit would otherwise mask it). */
class PermissiveAudit {
  public prepareCalls = 0;
  public finalizeCalls = 0;
  public constructor(private readonly gate: Gate) {}
  public async prepare(record: any): Promise<any> {
    this.prepareCalls += 1;
    this.gate.prepared = true;
    return { attemptId: record.attemptId, location: "PRIMARY_STORE", durableRecordId: `r-${this.prepareCalls}` };
  }
  public async finalize(): Promise<void> {
    this.finalizeCalls += 1;
  }
}

const rawFinalizeEmitter = (): any => ({
  async prepare(record: any): Promise<any> {
    return { attemptId: record.attemptId, location: "PRIMARY_STORE", durableRecordId: "r" };
  },
  async finalize(): Promise<void> {
    const raw: any = new Error("RAW_PHI_ALICE");
    raw.code = "RAW_PHI_CODE";
    throw raw;
  },
});

// ---------------------------------------------------------------------------
// #3 R5 — a rejecting finalizer never surfaces a raw message/code on ANY path
// (emitter root, wrapper SUCCESS paths, and the standalone coordinator).
// ---------------------------------------------------------------------------
describe("GLY-330 finding 3 R5 (§7/N2): a rejecting finalizer never leaks a raw message/code", () => {
  it("emitter.finalize sanitizes a RAW store rejection to a PhiAuditError (root chokepoint)", async () => {
    const rawPrimary = {
      async prepare(r: any): Promise<any> {
        return { status: "stored", durableRecordId: `p:${String(r.attemptId)}` };
      },
      async finalize(): Promise<void> {
        const raw: any = new Error("RAW_STORE_ALICE");
        raw.code = "RAW_STORE_CODE";
        throw raw;
      },
    };
    const spool = new Aes256GcmAuditSpool(new InMemorySpoolVolume() as any, new FixedKeyProvider() as any, CLOCK);
    const emitter = new DurablePhiAuditEmitter(rawPrimary as any, spool, new ExactAllowListAuditSerializer(), CLOCK);
    const rec = spoolPrepared("att-raw-fin");
    const receipt = await emitter.prepare(rec);
    let thrown: any;
    try {
      await emitter.finalize(receipt, spoolTerminal(rec));
    } catch (e) {
      thrown = e;
    }
    expect(thrown).toBeInstanceOf(PhiAuditError);
    expect(String(thrown?.message ?? "")).not.toContain("RAW_STORE_ALICE");
    expect(String(thrown?.code ?? "")).not.toContain("RAW_STORE_CODE");
  });

  it("generateText SUCCESS: a rejecting finalizer is sanitized to a PhiEngineError, never raw", async () => {
    const gate: Gate = { prepared: false };
    const audit = new FinalizeRejectingAudit(gate);
    const provider = new FakeRawProvider(gate, { responseText: "done" });
    const built = buildManualWrapper(gate, { audit, provider });
    let thrown: any;
    try {
      await built.wrapper.generateText({
        messages: [{ role: "user", content: [{ type: "text", text: "Maria García update." }] }],
      });
    } catch (e) {
      thrown = e;
    }
    expect(thrown).toBeInstanceOf(PhiEngineError);
    expect(String(thrown?.message ?? "")).not.toContain("RAW_FINALIZER_ALICE");
    expect(String(thrown?.code ?? "")).not.toContain("RAW_FINALIZER_CODE");
    expect(built.provider.calls).toBe(1); // egress happened; only the terminal write failed
    expect(audit.finalizeCalls).toBe(1);
  });

  it("generateStream SUCCESS: a rejecting finalizer is sanitized to a PhiEngineError, never raw", async () => {
    const gate: Gate = { prepared: false };
    const audit = new FinalizeRejectingAudit(gate);
    const provider = new FakeRawProvider(gate, { streamChunks: ["done"] });
    const built = buildManualWrapper(gate, { audit, provider });
    let thrown: any;
    try {
      await built.wrapper.generateStream({
        messages: [{ role: "user", content: [{ type: "text", text: "Maria García update." }] }],
      });
    } catch (e) {
      thrown = e;
    }
    expect(thrown).toBeInstanceOf(PhiEngineError);
    expect(String(thrown?.message ?? "")).not.toContain("RAW_FINALIZER_ALICE");
    expect(audit.finalizeCalls).toBe(1);
  });

  it("embedText SUCCESS: a rejecting finalizer is sanitized to a PhiEngineError, never raw", async () => {
    const gate: Gate = { prepared: false };
    const audit = new FinalizeRejectingAudit(gate);
    const provider = new FakeRawProvider(gate, {});
    const built = buildManualWrapper(gate, { audit, provider });
    let thrown: any;
    try {
      await built.wrapper.embedText("Maria García", "search" as any);
    } catch (e) {
      thrown = e;
    }
    expect(thrown).toBeInstanceOf(PhiEngineError);
    expect(String(thrown?.message ?? "")).not.toContain("RAW_FINALIZER_ALICE");
    expect(audit.finalizeCalls).toBe(1);
  });

  it("coordinator PRECONDITION path: a rejecting finalizer never surfaces raw", async () => {
    const coordinator = new PhiAuditedAttemptCoordinator(rawFinalizeEmitter(), CLOCK);
    let invoked = 0;
    const plan = {
      prepared: spoolPrepared("att-c1"),
      precondition: { ok: false, failureCode: "PRECONDITION_FAILED" },
      invokeProvider: async (): Promise<void> => {
        invoked += 1;
      },
    };
    let thrown: any;
    let result: any;
    try {
      result = await coordinator.run(plan as any);
    } catch (e) {
      thrown = e;
    }
    const surfaced = String(thrown?.message ?? "") + JSON.stringify(result ?? {});
    expect(surfaced).not.toContain("RAW_PHI_ALICE");
    expect(surfaced).not.toContain("RAW_PHI_CODE");
    expect(invoked).toBe(0);
  });

  it("coordinator PROVIDER-REJECTION path: a rejecting finalizer never surfaces raw", async () => {
    const coordinator = new PhiAuditedAttemptCoordinator(rawFinalizeEmitter(), CLOCK);
    const plan = {
      prepared: spoolPrepared("att-c2"),
      precondition: { ok: true },
      invokeProvider: async (): Promise<void> => {
        throw new Error("provider boom after send");
      },
    };
    let thrown: any;
    let result: any;
    try {
      result = await coordinator.run(plan as any);
    } catch (e) {
      thrown = e;
    }
    const surfaced = String(thrown?.message ?? "") + JSON.stringify(result ?? {});
    expect(surfaced).not.toContain("RAW_PHI_ALICE");
    expect(surfaced).not.toContain("RAW_PHI_CODE");
  });
});

// ---------------------------------------------------------------------------
// #9 R5 — no double-prepare, on the ordinary-prepare-rejection AND the
// request-trace-after-prepare parallel paths (probed with a permissive emitter).
// ---------------------------------------------------------------------------
describe("GLY-330 finding 9 R5 (N3): a failed attempt is prepared at most once (no double-prepare)", () => {
  it("an ordinary prepare rejection is sanitized to an audit error, so the wrapper never re-prepares", async () => {
    const gate: Gate = { prepared: false };
    const throwingPrimary = new ThrowingPrimaryStore();
    const spool = new Aes256GcmAuditSpool(new InMemorySpoolVolume() as any, new FixedKeyProvider() as any, CLOCK);
    const audit = new DurablePhiAuditEmitter(throwingPrimary as any, spool, new ExactAllowListAuditSerializer(), CLOCK);
    const built = buildManualWrapper(gate, { audit });
    let thrown: any;
    try {
      await built.wrapper.generateText({
        messages: [{ role: "user", content: [{ type: "text", text: "Maria García update." }] }],
      });
    } catch (e) {
      thrown = e;
    }
    expect(thrown).toBeTruthy();
    expect(built.provider.calls).toBe(0); // fail closed, no egress
    expect(throwingPrimary.prepareCalls).toBe(1); // NO second prepare
    expect(String(thrown?.message ?? "")).not.toContain("RAW_PREPARE_ALICE");
    expect(String(thrown?.code ?? "")).not.toContain("RAW_PREPARE_CODE");
  });

  it("a request-trace failure AFTER prepare finalizes exactly one terminal with no re-prepare (permissive emitter)", async () => {
    const gate: Gate = { prepared: false };
    const audit = new PermissiveAudit(gate);
    const trace = {
      request: async (): Promise<void> => {
        throw new Error("request trace boom");
      },
      response: async (): Promise<void> => undefined,
      metadata: async (): Promise<void> => undefined,
    };
    const built = buildManualWrapper(gate, { audit, trace });
    let threw = false;
    try {
      await built.wrapper.generateText({
        messages: [{ role: "user", content: [{ type: "text", text: "Maria García update." }] }],
      });
    } catch {
      threw = true;
    }
    expect(threw).toBe(true);
    expect(built.provider.calls).toBe(0);
    expect(audit.prepareCalls).toBe(1);
    expect(audit.finalizeCalls).toBe(1);
  });
});

// ---------------------------------------------------------------------------
// #4 R5 — tools[].name / tools[].description parallel carriers fail closed.
// ---------------------------------------------------------------------------
describe("GLY-330 finding 4 R5 (L5): tool name/description carriers fail closed on non-strings", () => {
  it("projector fails closed on a tool NAME object with a benign toString()", () => {
    const projector = new StructuralOptionsProjector();
    const maliciousName: any = { phi: "ALICE_CANARY" };
    maliciousName.toString = (): string => "safe_tool";
    expect(() =>
      projector.classify({ tools: [{ name: maliciousName, description: "ok" }] } as any),
    ).toThrow(PhiEngineError);
  });

  it("projector fails closed on a non-string tool DESCRIPTION", () => {
    const projector = new StructuralOptionsProjector();
    expect(() =>
      projector.classify({ tools: [{ name: "lookup", description: { phi: "BOB_CANARY" } }] } as any),
    ).toThrow(PhiEngineError);
  });

  it("end-to-end: a tool NAME object never egresses its canary to the provider", async () => {
    const rig = makeWrapperRig({});
    const maliciousName: any = { phi: "ALICE_CANARY" };
    maliciousName.toString = (): string => "safe_tool";
    let threw = false;
    try {
      await rig.wrapper.generateText({
        messages: [{ role: "user", content: [{ type: "text", text: "hello" }] }],
        tools: [{ name: maliciousName, description: "Look things up." }],
      } as any);
    } catch {
      threw = true;
    }
    expect(threw).toBe(true);
    expect(rig.provider.calls).toBe(0);
    expect(joined(rig.provider.payloads)).not.toContain("ALICE_CANARY");
  });
});

// ---------------------------------------------------------------------------
// #7 R5 — the low-level token reverser also fails closed on a residual sentinel.
// ---------------------------------------------------------------------------
describe("GLY-330 finding 7 R5 (L6): the low-level AtomicTokenReverser fails closed on a residual sentinel", () => {
  function handle(): any {
    return new InProcessReversalHandle({
      tenantId: TENANT,
      matterId: MATTER,
      dictionaryVersion: VERSION,
      operationId: b<any>("op-1"),
      attemptId: b<any>("att-1"),
    });
  }

  it("rejects a dangling escape sentinel instead of returning it as display text", async () => {
    const reverser = new AtomicTokenReverser(new InMemoryReversalStore(), new BracketTokenGrammar(), BOUNDARY_TOKEN_GRAMMAR_POLICY);
    const dangling = `Answer ${SENTINEL_OPEN} here` as any; // malformed sentinel, no matching close
    await expect(reverser.reverse(dangling, handle())).rejects.toThrow();
  });

  it("still reverses ordinary sentinel-free text unchanged", async () => {
    const reverser = new AtomicTokenReverser(new InMemoryReversalStore(), new BracketTokenGrammar(), BOUNDARY_TOKEN_GRAMMAR_POLICY);
    const out = await reverser.reverse("plain text no tokens" as any, handle());
    expect(String(out)).toBe("plain text no tokens");
  });
});

// ===========================================================================
// R6 — the round-6 gate found DEEPER adversarial-injection siblings behind the
// R5 chokepoint fixes: an arbitrary code smuggled inside a PhiAuditError /
// PhiEngineError instance, a getter that returns different values on successive
// reads (TOCTOU), a provider getter that throws after prepare, and a raw drain
// prepare error. These lock each. Each is mutation-proven.
// ===========================================================================

/** finalize() throws a PhiEngineError carrying an ARBITRARY (non-allow-listed) code — probes that a
 *  success-path finalizer's code is NOT trusted just for being a PhiEngineError (#3b). */
class PhiEngineFinalizeAudit {
  public constructor(private readonly gate: Gate) {}
  public async prepare(record: any): Promise<any> {
    this.gate.prepared = true;
    return { attemptId: record.attemptId, location: "PRIMARY_STORE", durableRecordId: "r-1" };
  }
  public async finalize(): Promise<void> {
    throw new PhiEngineError("RAW_FINALIZER_ALICE" as any);
  }
}

describe("GLY-330 finding 3 R6 (§7/N2): an arbitrary code inside an error instance is NOT trusted", () => {
  it("emitter.prepare re-wraps a PhiAuditError whose code is not an allow-listed AuditFailureCode", async () => {
    const roguePrimary = {
      async prepare(): Promise<any> {
        throw new PhiAuditError("RAW_STORE_ALICE" as any, null);
      },
      async finalize(): Promise<void> {},
    };
    const spool = new Aes256GcmAuditSpool(new InMemorySpoolVolume() as any, new FixedKeyProvider() as any, CLOCK);
    const emitter = new DurablePhiAuditEmitter(roguePrimary as any, spool, new ExactAllowListAuditSerializer(), CLOCK);
    let thrown: any;
    try {
      await emitter.prepare(spoolPrepared("att-rogue-p"));
    } catch (e) {
      thrown = e;
    }
    expect(thrown).toBeInstanceOf(PhiAuditError);
    expect(String(thrown?.code ?? "")).not.toContain("RAW_STORE_ALICE");
    expect(String(thrown?.message ?? "")).not.toContain("RAW_STORE_ALICE");
  });

  it("emitter.finalize re-wraps a PhiAuditError whose code is not an allow-listed AuditFailureCode", async () => {
    const roguePrimary = {
      async prepare(r: any): Promise<any> {
        return { status: "stored", durableRecordId: `p:${String(r.attemptId)}` };
      },
      async finalize(): Promise<void> {
        throw new PhiAuditError("RAW_STORE_ALICE" as any, null);
      },
    };
    const spool = new Aes256GcmAuditSpool(new InMemorySpoolVolume() as any, new FixedKeyProvider() as any, CLOCK);
    const emitter = new DurablePhiAuditEmitter(roguePrimary as any, spool, new ExactAllowListAuditSerializer(), CLOCK);
    const rec = spoolPrepared("att-rogue-f");
    const receipt = await emitter.prepare(rec);
    let thrown: any;
    try {
      await emitter.finalize(receipt, spoolTerminal(rec));
    } catch (e) {
      thrown = e;
    }
    expect(thrown).toBeInstanceOf(PhiAuditError);
    expect(String(thrown?.code ?? "")).not.toContain("RAW_STORE_ALICE");
    expect(String(thrown?.message ?? "")).not.toContain("RAW_STORE_ALICE");
  });

  it("generateText SUCCESS: a finalizer's arbitrary PhiEngineError.code is replaced by a fixed code", async () => {
    const gate: Gate = { prepared: false };
    const audit = new PhiEngineFinalizeAudit(gate);
    const provider = new FakeRawProvider(gate, { responseText: "done" });
    const built = buildManualWrapper(gate, { audit, provider });
    let thrown: any;
    try {
      await built.wrapper.generateText({
        messages: [{ role: "user", content: [{ type: "text", text: "Maria García update." }] }],
      });
    } catch (e) {
      thrown = e;
    }
    expect(thrown).toBeInstanceOf(PhiEngineError);
    expect(String(thrown?.code ?? "")).not.toContain("RAW_FINALIZER_ALICE");
    expect(String(thrown?.message ?? "")).not.toContain("RAW_FINALIZER_ALICE");
  });
});

// ---------------------------------------------------------------------------
// #9 R6 — a provider getter that throws AFTER routing must not double-prepare:
// every untrusted-getter deref precedes the durable prepare.
// ---------------------------------------------------------------------------
describe("GLY-330 finding 9 R6 (N3): an untrusted getter throwing after routing does not double-prepare", () => {
  it("dereferences decision.provider BEFORE prepare, so a throwing getter yields exactly one prepare", async () => {
    const gate: Gate = { prepared: false };
    const audit = new PermissiveAudit(gate);
    const decision: any = { isProductionSafe: true, baaSatisfied: true, providerId: "azure-openai-baa" };
    Object.defineProperty(decision, "provider", {
      get() {
        throw new Error("provider getter boom");
      },
      enumerable: true,
    });
    const router = { selectUsingOriginalContent: async (): Promise<any> => decision };
    const built = buildManualWrapper(gate, { audit, router });
    let threw = false;
    try {
      await built.wrapper.generateText({
        messages: [{ role: "user", content: [{ type: "text", text: "Maria García update." }] }],
      });
    } catch {
      threw = true;
    }
    expect(threw).toBe(true);
    expect(built.provider.calls).toBe(0);
    expect(audit.prepareCalls).toBe(1); // NO second prepare
  });
});

// ---------------------------------------------------------------------------
// #4 R6 — a getter that returns a benign value at validation and a PHI value at
// rebuild (TOCTOU) cannot smuggle raw PHI to the provider.
// ---------------------------------------------------------------------------
describe("GLY-330 finding 4 R6 (L5): a check-vs-use getter cannot smuggle PHI past the projector", () => {
  it("reads each provider-visible value once, so a mutating tool.name getter never egresses its canary", () => {
    const projector = new StructuralOptionsProjector();
    let reads = 0;
    const tool: any = { description: "ok" };
    Object.defineProperty(tool, "name", {
      get() {
        reads += 1;
        return reads === 1 ? "safe_tool" : { phi: "ALICE_CANARY" };
      },
      enumerable: true,
    });
    const classified = projector.classify({ tools: [tool] } as any);
    const rebuilt: any = classified.rebuild(
      classified.segments.map((s) => ({ path: s.path, text: s.text })) as any,
    );
    expect(rebuilt.tools[0].name).toBe("safe_tool");
    expect(JSON.stringify(rebuilt)).not.toContain("ALICE_CANARY");
  });
});

// ---------------------------------------------------------------------------
// NEW-R6-A — the background spool drain never surfaces a raw primary.prepare error.
// ---------------------------------------------------------------------------
describe("GLY-330 NEW-R6-A (§7/N2): spool.drainTo never surfaces a raw primary.prepare rejection", () => {
  it("keeps the entry and returns a report instead of rejecting with the raw message", async () => {
    const volume = new InMemorySpoolVolume();
    const spool = new Aes256GcmAuditSpool(volume as any, new FixedKeyProvider() as any, CLOCK);
    await spool.appendPrepared(spoolPrepared("att-drain-raw"));
    const rawPrimary = {
      async prepare(): Promise<any> {
        const raw: any = new Error("RAW_PRIMARY_ALICE");
        raw.code = "RAW_PRIMARY_CODE";
        throw raw;
      },
      async finalize(): Promise<void> {},
    };
    let thrown: any;
    let report: any;
    try {
      report = await spool.drainTo(rawPrimary as any);
    } catch (e) {
      thrown = e;
    }
    expect(thrown).toBeUndefined(); // no raw rejection escapes the drain
    expect(report.remaining).toBeGreaterThanOrEqual(1); // entry kept for a later drain
  });
});

// ---------------------------------------------------------------------------
// #3 R6 (pre-empt) — an injected component's PhiEngineError with an ARBITRARY code
// is never surfaced raw to the caller OR recorded in the durable audit terminal.
// Locks the whole class: the guarded passthrough, toFailureCode, and errorCodeString.
// ---------------------------------------------------------------------------
describe("GLY-330 finding 3 R6 (§7/N2): an arbitrary PhiEngineError.code is never surfaced (caller or audit)", () => {
  it("replaces a policy rejection's non-allow-listed code with a fixed code, everywhere", async () => {
    const gate: Gate = { prepared: false };
    const built = buildManualWrapper(gate, {
      policyFn: (): Promise<any> =>
        Promise.reject(new PhiEngineError("RAW_POLICY_ALICE" as any, b<any>("op-1"), {})),
    });
    let thrown: any;
    try {
      await built.wrapper.generateText({
        messages: [{ role: "user", content: [{ type: "text", text: "Maria García update." }] }],
      });
    } catch (e) {
      thrown = e;
    }
    expect(thrown).toBeInstanceOf(PhiEngineError);
    // (a) the caller never sees the raw code/message
    expect(String(thrown?.code ?? "")).not.toContain("RAW_POLICY_ALICE");
    expect(String(thrown?.message ?? "")).not.toContain("RAW_POLICY_ALICE");
    // (b) the durable audit terminal never records the raw code
    expect(JSON.stringify(built.primary.finalizedEvents)).not.toContain("RAW_POLICY_ALICE");
  });
});

// ===========================================================================
// R7 — the round-7 gate attacked with a fully-hostile input object: a `.code`
// getter that mutates between reads, an overridden array `.map`, and a throwing
// `.status` getter. Discipline: read every untrusted scalar ONCE into a local,
// never forward the mutable instance, use intrinsic array ops. Each is mutation-proven.
// ===========================================================================
describe("GLY-330 finding 3 R7 (§7/N2): a mutating error.code getter cannot smuggle PHI", () => {
  it("emitter.prepare reads a PhiAuditError code once and throws a fresh error", async () => {
    let reads = 0;
    const evil = new PhiAuditError("AUDIT_DURABILITY_UNAVAILABLE", null);
    Object.defineProperty(evil, "code", {
      get() {
        reads += 1;
        return reads <= 1 ? "AUDIT_DURABILITY_UNAVAILABLE" : "RAW_STORE_ALICE";
      },
      configurable: true,
    });
    const roguePrimary = {
      async prepare(): Promise<any> {
        throw evil;
      },
      async finalize(): Promise<void> {},
    };
    const spool = new Aes256GcmAuditSpool(new InMemorySpoolVolume() as any, new FixedKeyProvider() as any, CLOCK);
    const emitter = new DurablePhiAuditEmitter(roguePrimary as any, spool, new ExactAllowListAuditSerializer(), CLOCK);
    let thrown: any;
    try {
      await emitter.prepare(spoolPrepared("att-evil-p"));
    } catch (e) {
      thrown = e;
    }
    expect(String(thrown?.code ?? "")).not.toContain("RAW_STORE_ALICE");
    expect(String(thrown?.message ?? "")).not.toContain("RAW_STORE_ALICE");
  });

  it("emitter.finalize reads a PhiAuditError code once and throws a fresh error", async () => {
    let reads = 0;
    const evil = new PhiAuditError("AUDIT_SPOOL_FLUSH_FAILED", null);
    Object.defineProperty(evil, "code", {
      get() {
        reads += 1;
        return reads <= 1 ? "AUDIT_SPOOL_FLUSH_FAILED" : "RAW_STORE_ALICE";
      },
      configurable: true,
    });
    const roguePrimary = {
      async prepare(r: any): Promise<any> {
        return { status: "stored", durableRecordId: `p:${String(r.attemptId)}` };
      },
      async finalize(): Promise<void> {
        throw evil;
      },
    };
    const spool = new Aes256GcmAuditSpool(new InMemorySpoolVolume() as any, new FixedKeyProvider() as any, CLOCK);
    const emitter = new DurablePhiAuditEmitter(roguePrimary as any, spool, new ExactAllowListAuditSerializer(), CLOCK);
    const rec = spoolPrepared("att-evil-f");
    const receipt = await emitter.prepare(rec);
    let thrown: any;
    try {
      await emitter.finalize(receipt, spoolTerminal(rec));
    } catch (e) {
      thrown = e;
    }
    expect(String(thrown?.code ?? "")).not.toContain("RAW_STORE_ALICE");
  });

  it("coordinator reads a provider error's code once (mutating getter cannot leak)", async () => {
    let reads = 0;
    const evil: any = new Error("boom");
    Object.defineProperty(evil, "code", {
      get() {
        reads += 1;
        return reads <= 2 ? "REVERSAL_FAILED" : "RAW_PROVIDER_ALICE";
      },
      configurable: true,
    });
    const finalized: any[] = [];
    const okEmitter = {
      async prepare(r: any): Promise<any> {
        return { attemptId: r.attemptId, location: "PRIMARY_STORE", durableRecordId: "r" };
      },
      async finalize(_r: any, e: any): Promise<void> {
        finalized.push(e);
      },
    };
    const coordinator = new PhiAuditedAttemptCoordinator(okEmitter as any, CLOCK);
    const plan = {
      prepared: spoolPrepared("att-cc"),
      precondition: { ok: true },
      invokeProvider: async (): Promise<void> => {
        throw evil;
      },
    };
    const result: any = await coordinator.run(plan as any);
    const surfaced = JSON.stringify(result) + JSON.stringify(finalized);
    expect(surfaced).not.toContain("RAW_PROVIDER_ALICE");
  });

  it("wrapper never forwards the mutable error instance (fresh error, caller reads a data prop)", async () => {
    const gate: Gate = { prepared: false };
    let reads = 0;
    const evil = new PhiEngineError("MISSING_TRUSTED_POLICY", b<any>("op-1"), {});
    Object.defineProperty(evil, "code", {
      get() {
        reads += 1;
        return reads <= 2 ? "MISSING_TRUSTED_POLICY" : "RAW_POLICY_ALICE";
      },
      configurable: true,
    });
    const built = buildManualWrapper(gate, { policyFn: (): Promise<any> => Promise.reject(evil) });
    let thrown: any;
    try {
      await built.wrapper.generateText({
        messages: [{ role: "user", content: [{ type: "text", text: "Maria García update." }] }],
      });
    } catch (e) {
      thrown = e;
    }
    expect(String(thrown?.code ?? "")).not.toContain("RAW_POLICY_ALICE");
    expect(String(thrown?.message ?? "")).not.toContain("RAW_POLICY_ALICE");
    expect(JSON.stringify(built.primary.finalizedEvents)).not.toContain("RAW_POLICY_ALICE");
  });
});

describe("GLY-330 finding 4 R7 (L5): an overridden array .map cannot skip projector normalization", () => {
  it("uses intrinsic iteration, so a tools.map override cannot egress a mutating name", () => {
    const projector = new StructuralOptionsProjector();
    let reads = 0;
    const tool: any = { description: "ok" };
    Object.defineProperty(tool, "name", {
      get() {
        reads += 1;
        return reads <= 1 ? "safe_tool" : "ALICE_CANARY";
      },
      enumerable: true,
      configurable: true,
    });
    const tools: any = [tool];
    tools.map = (): any => tools; // adversarial: return the raw elements, skip the callback
    const classified = projector.classify({ tools } as any);
    const rebuilt: any = classified.rebuild(
      classified.segments.map((s) => ({ path: s.path, text: s.text })) as any,
    );
    expect(rebuilt.tools[0].name).toBe("safe_tool");
    expect(JSON.stringify(rebuilt)).not.toContain("ALICE_CANARY");
  });
});

describe("GLY-330 NEW-R6-A R7 (§7/N2): spool.drainTo tolerates a throwing status getter", () => {
  it("captures the prepare result's status inside the guarded region", async () => {
    const volume = new InMemorySpoolVolume();
    const spool = new Aes256GcmAuditSpool(volume as any, new FixedKeyProvider() as any, CLOCK);
    await spool.appendPrepared(spoolPrepared("att-status"));
    const rogue = {
      async prepare(): Promise<any> {
        const r: any = {};
        Object.defineProperty(r, "status", {
          get() {
            const e: any = new Error("RAW_PRIMARY_ALICE");
            e.code = "RAW_PRIMARY_CODE";
            throw e;
          },
        });
        return r;
      },
      async finalize(): Promise<void> {},
    };
    let thrown: any;
    let report: any;
    try {
      report = await spool.drainTo(rogue as any);
    } catch (e) {
      thrown = e;
    }
    expect(thrown).toBeUndefined();
    expect(report.remaining).toBeGreaterThanOrEqual(1);
  });

  it("tolerates a volume list() rejection carrying PHI during rebuild", async () => {
    const volume: any = {
      async list(): Promise<any> {
        throw new Error("ALICE_SMITH_DOB_1970");
      },
      async putAtomic(): Promise<any> {
        return { flushed: true };
      },
      async read(): Promise<any> {
        return null;
      },
      async remove(): Promise<void> {},
    };
    const spool = new Aes256GcmAuditSpool(volume as any, new FixedKeyProvider() as any, CLOCK);
    const primary = {
      async prepare(r: any): Promise<any> {
        return { status: "stored", durableRecordId: `p:${String(r.attemptId)}` };
      },
      async finalize(): Promise<void> {},
    };
    let thrown: any;
    try {
      await spool.drainTo(primary as any);
    } catch (e) {
      thrown = e;
    }
    expect(thrown).toBeUndefined();
  });
});

// ===========================================================================
// R8 — the round-8 gate found SIBLING paths: a THROWING .code getter, a non-array
// message.content whose own forEach/map run, and unguarded volume I/O in drainTo.
// Discipline: read untrusted members behind a getter-throw guard, fail closed on a
// non-array carrier, guard every drain I/O. Each is mutation-proven.
// ===========================================================================
describe("GLY-330 finding 3 R8 (§7/N2): a THROWING error.code getter cannot leak PHI", () => {
  it("never surfaces a throwing-getter PHI message to the caller or the audit terminal", async () => {
    const gate: Gate = { prepared: false };
    const evil: any = {};
    Object.defineProperty(evil, "code", {
      get() {
        throw new Error("ALICE_SMITH_DOB_1970");
      },
    });
    const built = buildManualWrapper(gate, { policyFn: (): Promise<any> => Promise.reject(evil) });
    let thrown: any;
    try {
      await built.wrapper.generateText({
        messages: [{ role: "user", content: [{ type: "text", text: "Maria García update." }] }],
      });
    } catch (e) {
      thrown = e;
    }
    expect(String(thrown?.message ?? "")).not.toContain("ALICE_SMITH_DOB_1970");
    expect(String(thrown?.code ?? "")).not.toContain("ALICE_SMITH_DOB_1970");
    expect(JSON.stringify(built.primary.finalizedEvents)).not.toContain("ALICE_SMITH_DOB_1970");
  });
});

describe("GLY-330 finding 4 R8 (L5): a non-array message.content fails closed", () => {
  it("rejects an object 'content' before its own forEach/map can run", () => {
    const projector = new StructuralOptionsProjector();
    const content: any = {
      forEach(): void {
        /* no-op: would skip classification */
      },
      map(): any {
        return [{ type: "text", text: "ALICE_CANARY" }]; // would egress raw via the clone
      },
    };
    expect(() =>
      projector.classify({ messages: [{ role: "user", content }] } as any),
    ).toThrow(PhiEngineError);
  });

  it("rejects a non-array 'messages' before its own forEach runs", () => {
    const projector = new StructuralOptionsProjector();
    const messages: any = {
      length: 1,
      0: { role: "user", content: [{ type: "text", text: "ALICE_CANARY" }] },
      forEach(): void {
        /* no-op: would skip all message classification */
      },
    };
    expect(() => projector.classify({ messages } as any)).toThrow(PhiEngineError);
  });

  it("rejects a non-array 'tools' before its own forEach runs", () => {
    const projector = new StructuralOptionsProjector();
    const tools: any = {
      length: 1,
      0: { name: "x", description: "ALICE_CANARY" },
      forEach(): void {
        /* no-op */
      },
    };
    expect(() => projector.classify({ tools } as any)).toThrow(PhiEngineError);
  });
});

describe("GLY-330 NEW-R6-A R8 (§7/N2): drainTo guards ALL volume/store I/O", () => {
  it("tolerates a volume putAtomic rejection carrying PHI on the primed-marker path", async () => {
    const base = new InMemorySpoolVolume();
    const volume: any = {
      async putAtomic(recordId: string, bytes: Uint8Array): Promise<any> {
        if (recordId.endsWith(".primed")) {
          throw new Error("ALICE_SMITH_DOB_1970"); // adversarial volume: PHI in the rejection
        }
        return base.putAtomic(recordId, bytes);
      },
      read: (id: string): Promise<any> => base.read(id),
      list: (): Promise<any> => base.list(),
      remove: (id: string): Promise<any> => base.remove(id),
    };
    const spool = new Aes256GcmAuditSpool(volume as any, new FixedKeyProvider() as any, CLOCK);
    await spool.appendPrepared(spoolPrepared("att-primed"));
    const primary = {
      async prepare(r: any): Promise<any> {
        return { status: "stored", durableRecordId: `p:${String(r.attemptId)}` };
      },
      async finalize(): Promise<void> {},
    };
    let thrown: any;
    let report: any;
    try {
      report = await spool.drainTo(primary as any);
    } catch (e) {
      thrown = e;
    }
    expect(thrown).toBeUndefined();
    expect(report.remaining).toBeGreaterThanOrEqual(1);
  });
});

// ---------------------------------------------------------------------------
// R9 (§7/N2): classifying a DELIBERATELY-HOSTILE thrown value can never itself
// surface PHI. A rejected value is untrusted: its `.code` may be a throwing
// getter, and its prototype access may be a throwing Proxy `getPrototypeOf` /
// `Symbol.hasInstance` trap. Both the `instanceof` test and the `.code` compare
// inside `isAuditError` / `isPhiEngineError` must swallow such a throw and fail
// closed, never re-raise the canary to the caller.
// ---------------------------------------------------------------------------
describe("GLY-330 R9 (§7/N2): hostile-object error classification cannot surface PHI", () => {
  it("coordinator: a prepare rejection whose .code getter THROWS PHI is sanitized to AUDIT_PREPARE_FAILED", async () => {
    // A real PhiAuditError (so `instanceof` passes) whose `.code` getter throws a canary on read.
    // The coordinator's `isAuditError(error, "AUDIT_DURABILITY_UNAVAILABLE")` must read that code
    // through the getter-throw guard, not by touching `.code` directly.
    const evil = new PhiAuditError("AUDIT_DURABILITY_UNAVAILABLE", b<any>("op-1"));
    Object.defineProperty(evil, "code", {
      configurable: true,
      get(): string {
        throw new Error("ALICE_SMITH_DOB_1970");
      },
    });
    const emitter = {
      prepare: async (): Promise<never> => {
        throw evil;
      },
      finalize: async (): Promise<void> => {},
      reconcileUnknownAfterSend: async (): Promise<void> => {},
    };
    const coordinator = new PhiAuditedAttemptCoordinator(emitter as any, CLOCK);
    const plan = {
      prepared: spoolPrepared("att-r9-code"),
      precondition: { ok: true },
      invokeProvider: async (): Promise<void> => {},
    };
    let thrown: any;
    let result: any;
    try {
      result = await coordinator.run(plan as any);
    } catch (e) {
      thrown = e;
    }
    const surfaced = String(thrown?.message ?? "") + JSON.stringify(result ?? {});
    expect(surfaced).not.toContain("ALICE_SMITH_DOB_1970");
    expect(result?.errorCode).toBe("AUDIT_PREPARE_FAILED");
    expect(result?.providerInvoked).toBe(false);
  });

  it("isAuditError / isPhiEngineError never throw on a hostile getPrototypeOf Proxy (fail closed to false)", () => {
    // `instanceof` walks the LHS prototype chain via [[GetPrototypeOf]]; a Proxy trap that throws
    // there would otherwise escape the classifier with a PHI canary.
    const evilAudit = new Proxy(new PhiAuditError("AUDIT_DURABILITY_UNAVAILABLE", b<any>("op-1")), {
      getPrototypeOf(): never {
        throw new Error("ALICE_SMITH_DOB_1970");
      },
    });
    const evilEngine = new Proxy(new PhiEngineError("REVERSAL_FAILED"), {
      getPrototypeOf(): never {
        throw new Error("ALICE_SMITH_DOB_1970");
      },
    });
    expect(() => isAuditError(evilAudit)).not.toThrow();
    expect(isAuditError(evilAudit)).toBe(false);
    expect(() => isPhiEngineError(evilEngine)).not.toThrow();
    expect(isPhiEngineError(evilEngine)).toBe(false);
  });

  it("emitter.prepare sanitizes a store rejection that is a hostile getPrototypeOf Proxy", async () => {
    const evil = new Proxy(new PhiAuditError("AUDIT_DURABILITY_UNAVAILABLE", b<any>("op-1")), {
      getPrototypeOf(): never {
        throw new Error("ALICE_SMITH_DOB_1970");
      },
    });
    const primary = {
      prepare: async (): Promise<never> => {
        throw evil;
      },
      finalize: async (): Promise<void> => {},
    };
    const spool = new Aes256GcmAuditSpool(new InMemorySpoolVolume() as any, new FixedKeyProvider() as any, CLOCK);
    const emitter = new DurablePhiAuditEmitter(primary as any, spool, new ExactAllowListAuditSerializer(), CLOCK);
    let thrown: any;
    try {
      await emitter.prepare(spoolPrepared("att-r9-proxy"));
    } catch (e) {
      thrown = e;
    }
    expect(thrown).toBeInstanceOf(PhiAuditError);
    expect(String(thrown?.message ?? "")).not.toContain("ALICE_SMITH_DOB_1970");
    expect(String(thrown?.code ?? "")).not.toContain("ALICE_SMITH_DOB_1970");
  });
});

// ---------------------------------------------------------------------------
// R10 (§7/N2): the SAME hostile-object leak classes, swept across the sibling
// modules the earlier rounds had not hardened — the dictionary orchestrator,
// the streaming reverser, the audit serializer, and two remaining scalar reads.
// A deliberately hostile thrown value / carrier must never surface PHI to a
// caller, a trace, an error, or a durable audit record.
// ---------------------------------------------------------------------------
describe("GLY-330 R10 (§7/N2): hostile-object leak class swept across sibling modules", () => {
  const CANARY = "ALICE_SMITH_DOB_1970";
  const substReq = (text: string): any => ({
    context: ctx(),
    policy: { locale: LOCALE, detectorRequirement: "OPTIONAL", schemaVersion: SCHEMA },
    segments: [{ text }],
  });

  // R10-A — a non-DictionaryError from the dictionary path is sanitized, never forwarded.
  it("orchestrator: a raw non-DictionaryError from requireActiveReady fails closed (never forwarded)", async () => {
    const coordinator: any = {
      requireActiveReady: async (): Promise<never> => {
        throw Object.assign(new Error(CANARY), { code: CANARY });
      },
    };
    const engine = new ComposedSubstitutionEngine({
      coordinator,
      truthReader: new InMemoryCaseTruthReader() as any,
      sourceTruthRevision: REVISION,
      reversalStore: new InMemoryReversalStore(),
      engineVersion: ENGINE,
    } as any);
    let thrown: any;
    try {
      await engine.substitute(substReq("Maria García"));
    } catch (e) {
      thrown = e;
    }
    expect(thrown).toBeInstanceOf(PhiEngineError);
    expect(String(thrown?.message ?? "")).not.toContain(CANARY);
    expect(String(thrown?.code ?? "")).not.toContain(CANARY);
  });

  // R10-G — a hostile getPrototypeOf Proxy cannot escape isDictionaryError's instanceof.
  it("isDictionaryError never throws on a hostile getPrototypeOf Proxy (fails closed to false)", () => {
    const evil = new Proxy(new DictionaryError("DICTIONARY_NOT_READY"), {
      getPrototypeOf(): never {
        throw new Error(CANARY);
      },
    });
    expect(() => isDictionaryError(evil)).not.toThrow();
    expect(isDictionaryError(evil)).toBe(false);
  });

  // R10-D — decideEgress copies no hostile `.code`; a throwing getter yields a fixed code.
  it("decideEgress: a DictionaryError with a THROWING .code getter yields a fixed code, no PHI", async () => {
    const evil = new DictionaryError("DICTIONARY_NOT_READY");
    Object.defineProperty(evil, "code", {
      configurable: true,
      get(): string {
        throw new Error(CANARY);
      },
    });
    const coordinator: any = {
      requireActiveReady: async (): Promise<never> => {
        throw evil;
      },
    };
    let decision: any;
    let thrown: any;
    try {
      decision = await decideEgress(
        {
          context: { tenantId: TENANT, matterId: MATTER } as any,
          dictionaryHealth: "available",
          text: "Maria García",
          policy: {} as any,
          engineVersion: ENGINE,
          sourceTruthRevision: REVISION,
        },
        { coordinator, cache: {} as any, compiler: {} as any },
      );
    } catch (e) {
      thrown = e;
    }
    const surfaced = JSON.stringify(decision ?? {}) + String(thrown?.message ?? "");
    expect(surfaced).not.toContain(CANARY);
    expect(decision?.kind).toBe("FAILED_CLOSED");
  });

  // R10-B — the streaming reverser sanitizes a store rejection, never forwards the instance.
  it("streaming reverser: a store rejection carrying PHI is sanitized to ReversalFailedError", async () => {
    const factory = new HoldbackReverseStreamFactory();
    const hostileStore: any = {
      maximumEncounteredTokenBatch: 8,
      resolveEncounteredTokens: async (): Promise<never> => {
        throw Object.assign(new Error(CANARY), { code: CANARY });
      },
    };
    const handle: any = {
      tenantId: TENANT,
      matterId: MATTER,
      dictionaryVersion: VERSION,
      operationId: b<any>("op-1"),
    };
    const stream = factory.create({
      handle,
      store: hostileStore,
      grammar: new BracketTokenGrammar(),
      policy: BOUNDARY_TOKEN_GRAMMAR_POLICY,
      sink: (): void => {},
    });
    let thrown: any;
    try {
      await stream.push(b<any>("[[Claimant]]"));
      await stream.end();
    } catch (e) {
      thrown = e;
    }
    expect(thrown).toBeInstanceOf(ReversalFailedError);
    expect(String(thrown?.message ?? "")).not.toContain(CANARY);
    expect(String(thrown?.code ?? "")).not.toContain(CANARY);
  });

  // R10-C — the serializer's failureCode is value-allow-listed: a canary is rejected pre-persist.
  it("serializer: a terminal event whose failureCode is an unrecognized (PHI) string is rejected", () => {
    const serializer = new ExactAllowListAuditSerializer();
    const event = preparedToTerminalEvent(spoolPrepared("att-r10c"), "failed_closed", CANARY, CLOCK());
    let thrown: any;
    try {
      serializer.serialize(event);
    } catch (e) {
      thrown = e;
    }
    expect(thrown).toBeInstanceOf(PhiAuditError);
    expect(String((thrown as any)?.code ?? "")).toBe("AUDIT_SCHEMA_REJECTED");
    expect(JSON.stringify({ m: thrown?.message, c: (thrown as any)?.code, d: (thrown as any)?.safeDetails })).not.toContain(CANARY);
    // A legitimate fixed code still serializes (guard against over-restriction).
    expect(() => serializer.serialize(preparedToTerminalEvent(spoolPrepared("att-r10c2"), "failed_closed", "PRECONDITION_FAILED", CLOCK()))).not.toThrow();
  });

  // R10-E — the coordinator reads precondition.ok behind a getter-throw guard.
  it("coordinator: a hostile precondition.ok getter trap fails closed, never surfaces PHI", async () => {
    const okThrows = new Proxy({}, {
      get(_t, key): unknown {
        if (key === "ok") throw new Error(CANARY);
        return undefined;
      },
    });
    const emitter = {
      prepare: async (): Promise<any> => ({ attemptId: b<any>("att-r10e"), location: "PRIMARY_STORE", durableRecordId: "d" }),
      finalize: async (): Promise<void> => {},
      reconcileUnknownAfterSend: async (): Promise<void> => {},
    };
    const coordinator = new PhiAuditedAttemptCoordinator(emitter as any, CLOCK);
    const plan = {
      prepared: spoolPrepared("att-r10e"),
      precondition: okThrows,
      invokeProvider: async (): Promise<void> => {},
    };
    let thrown: any;
    let result: any;
    try {
      result = await coordinator.run(plan as any);
    } catch (e) {
      thrown = e;
    }
    const surfaced = String(thrown?.message ?? "") + JSON.stringify(result ?? {});
    expect(surfaced).not.toContain(CANARY);
    expect(result?.outcome).toBe("failed_closed");
    expect(result?.providerInvoked).toBe(false);
  });

  // R10-F — a hostile Array.prototype.forEach override cannot make classification skip a carrier.
  it("projector: an overridden Array.prototype.forEach cannot skip classification (no raw egress)", () => {
    const projector = new StructuralOptionsProjector();
    const original = Array.prototype.forEach;
    let found = false;
    try {
      // eslint-disable-next-line no-extend-native
      (Array.prototype as any).forEach = function (): void {
        /* no-op: a `.forEach`-based classification pass would visit nothing */
      };
      const classified: any = projector.classify({
        messages: [{ role: "user", content: [{ type: "text", text: CANARY }] }],
      } as any);
      // Index-walk (not .some/.find — those are unaffected, but keep the assertion self-contained).
      for (let i = 0; i < classified.segments.length; i += 1) {
        if (String(classified.segments[i].text).includes(CANARY)) found = true;
      }
    } finally {
      (Array.prototype as any).forEach = original;
    }
    expect(found).toBe(true);
  });
});
