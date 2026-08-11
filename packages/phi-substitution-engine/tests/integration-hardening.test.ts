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
  BracketTokenGrammar,
  HoldbackReverseStreamFactory,
  InMemoryReversalStore,
  InProcessReversalHandle,
  reverseText,
  SENTINEL_OPEN,
} from "../src/tokens/index";
import {
  Aes256GcmAuditSpool,
  DurablePhiAuditEmitter,
  ExactAllowListAuditSerializer,
} from "../src/audit/index";
import {
  InMemoryCaseTruthReader,
  InMemoryDictionaryVersionCoordinator,
} from "../src/dictionary/index";
import { PhiEngineError } from "../src/core/errors";

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
  } = {},
): { wrapper: ComposedProtectedAiProvider<any, string>; provider: FakeRawProvider; primary: RecordingPrimaryStore; trace: any } {
  const { engine } = makeEngine(over.truth ?? DEFAULT_TRUTH);
  const provider = new FakeRawProvider(gate);
  const trace = over.trace ?? new FakeSafeTrace();
  const primary = over.sharedPrimary ?? new RecordingPrimaryStore(gate);
  const spool = new Aes256GcmAuditSpool(new InMemorySpoolVolume() as any, new FixedKeyProvider() as any, CLOCK);
  const emitter = new DurablePhiAuditEmitter(primary as any, spool, new ExactAllowListAuditSerializer(), CLOCK);
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
