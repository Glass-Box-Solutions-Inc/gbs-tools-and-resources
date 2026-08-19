import { describe, expect, it, vi } from "vitest";
import {
  createProductionProtectedAiProvider,
  isPhiEngineError,
} from "../src/index";
import type {
  AiProviderOptionProjector,
  AuditPrimaryStore,
  AuditPreparationReceipt,
  CreateProductionProtectedAiProviderOptions,
  DisplayText,
  EncryptedAuditSpool,
  EngineVersion,
  MatterAiContext,
  PhiAuditEvent,
  PhiAuditPreparedRecord,
  PhiSubstitutionEngine,
  ProductionRawProviderPort,
  ProductionRawResultTail,
  ProductionRawTextResult,
  ReversalHandle,
  ReverseStream,
  SubstitutionRequest,
  SubstitutionResult,
  TokenizedText,
  TrustedMatterAiPolicy,
} from "../src/index";

interface Options { readonly prompt: string }

const TOKEN = "[[Claimant]]";
const PHI = "Alice Example";
const ENGINE_POLICY = `sha256:${"a".repeat(64)}`;
let attemptCounter = 0;

function branded<T>(value: unknown): T {
  return value as T;
}

function context(): MatterAiContext {
  return {
    tenantId: branded("tenant-production"),
    matterId: branded("matter-production"),
    actorId: branded("actor-production"),
    operationId: branded("operation-production"),
    attemptId: branded(`attempt-${attemptCounter += 1}`),
  };
}

const policy: TrustedMatterAiPolicy = {
  mode: "REQUIRED",
  locale: branded("en-US"),
  activeDictionaryVersion: branded(1n),
  schemaVersion: branded("schema-1"),
  detectorRequirement: "DISABLED_PHASE_1",
  approvedOffDecisionId: null,
};

class TestEngine implements PhiSubstitutionEngine {
  public readonly reverseInputs: string[] = [];
  public substituteCalls = 0;
  public streamAborts = 0;
  public streamCreations = 0;
  public maliciousReversedChunk = false;
  public failToolReverse = false;
  public toolReverseGate: Promise<void> | undefined;

  public async substitute(request: SubstitutionRequest): Promise<SubstitutionResult> {
    this.substituteCalls += 1;
    return {
      segments: request.segments.map((segment) => ({
        ...segment,
        text: branded<TokenizedText>(segment.text.replaceAll(PHI, TOKEN)),
      })),
      dictionaryVersion: branded(1n),
      engineVersion: branded<EngineVersion>("engine-production-1"),
      counts: {
        PERSON_NAME: 1, DOB: 0, SSN: 0, MRN: 0, DEA: 0, EMAIL: 0,
        PHONE: 0, ADDRESS: 0, CLAIM_NUMBER: 0, POLICY_NUMBER: 0,
        ACCOUNT_NUMBER: 0, OTHER_TAGGED: 0,
      },
      ambiguityCount: 0,
      detector: null,
      latencyMs: { dictionary: 0, detector: 0, total: 0 },
      reversalHandle: branded<ReversalHandle>({}),
    };
  }

  public async reverse(text: TokenizedText, _handle: ReversalHandle): Promise<DisplayText> {
    this.reverseInputs.push(String(text));
    if (String(text).startsWith("{")) {
      await this.toolReverseGate;
      if (this.failToolReverse) throw new Error(`raw ${PHI}`);
    }
    return branded<DisplayText>(String(text).replaceAll(TOKEN, PHI));
  }

  public createReverseStream(
    _handle: ReversalHandle,
    sink: (safe: DisplayText) => void | Promise<void>,
  ): ReverseStream {
    this.streamCreations += 1;
    let aborted = false;
    return {
      push: async (chunk): Promise<void> => {
        if (aborted) return;
        if (this.maliciousReversedChunk) {
          await sink({ raw: PHI } as unknown as DisplayText);
          return;
        }
        await sink(branded<DisplayText>(String(chunk).replaceAll(TOKEN, PHI)));
      },
      end: async (): Promise<void> => undefined,
      abort: async (): Promise<void> => {
        aborted = true;
        this.streamAborts += 1;
      },
    };
  }
}

class TestPrimary implements AuditPrimaryStore {
  public readonly prepared: PhiAuditPreparedRecord[] = [];
  public readonly finalized: PhiAuditEvent[] = [];
  public available = true;

  public async prepare(record: PhiAuditPreparedRecord) {
    this.prepared.push(record);
    return this.available
      ? { status: "stored" as const, durableRecordId: `primary:${record.attemptId}` }
      : { status: "unavailable" as const, fixedFailureCode: "PRIMARY_UNAVAILABLE" };
  }

  public async finalize(event: PhiAuditEvent): Promise<void> {
    this.finalized.push(event);
  }
}

class TestSpool implements EncryptedAuditSpool {
  public ready = false;
  public calls = 0;
  public readonly finalized: PhiAuditEvent[] = [];
  public appendPrepared(record: PhiAuditPreparedRecord): Promise<AuditPreparationReceipt> {
    this.calls += 1;
    if (!this.ready) return Promise.reject(new Error("unavailable"));
    return Promise.resolve({
      attemptId: record.attemptId,
      location: "ENCRYPTED_LOCAL_SPOOL",
      durableRecordId: `spool:${record.attemptId}`,
    });
  }
  public finalize(_receipt: AuditPreparationReceipt, event: PhiAuditEvent): Promise<void> {
    this.calls += 1;
    this.finalized.push(event);
    return Promise.resolve();
  }
  public drainTo(_primary: AuditPrimaryStore) {
    this.calls += 1;
    return Promise.resolve({ examined: 0, delivered: 0, duplicates: 0, remaining: 0 });
  }
  public inspectEnvelope(_recordId: string) {
    this.calls += 1;
    return Promise.reject(new Error("unused"));
  }
  public health(): Promise<"ready" | "unavailable"> {
    this.calls += 1;
    return Promise.resolve(this.ready ? "ready" : "unavailable");
  }
}

class TestProvider implements ProductionRawProviderPort<Options> {
  public textCalls = 0;
  public streamCalls = 0;
  public embedCalls = 0;
  public sawAbort = false;
  public waitForAbort = false;
  public maliciousRawChunk = false;
  public started: (() => void) | undefined;
  public streamFirstStarted: (() => void) | undefined;
  public streamSecondStarted: (() => void) | undefined;
  public streamAfterFirst: Promise<void> | undefined;
  public emitSecondChunk = false;
  public waitForStreamAbort = false;
  public sawStreamAbort = false;
  public streamSignal: AbortSignal | undefined;
  public lastTextPrompt: string | undefined;
  public lastStreamPrompt: string | undefined;
  public lastEmbeddingText: string | undefined;
  public textResult: ProductionRawTextResult | undefined;

  public async generateText(options: Options, signal: AbortSignal): Promise<ProductionRawTextResult> {
    this.textCalls += 1;
    this.lastTextPrompt = options.prompt;
    this.started?.();
    if (this.waitForAbort) {
      await new Promise<void>((resolve) => signal.addEventListener("abort", () => {
        this.sawAbort = true;
        resolve();
      }, { once: true }));
    }
    return this.textResult ?? ({
      text: branded<TokenizedText>(`Hello ${TOKEN}`),
      providerId: "raw-untrusted-provider",
      model: "model-1",
      usage: { inputTokens: 2, outputTokens: 3, totalTokens: 5 },
      toolCalls: [{
        id: "call-1",
        name: "lookup",
        arguments: branded<TokenizedText>(`{"name":"${TOKEN}"}`),
      }],
    } as unknown as ProductionRawTextResult);
  }

  public async generateStream(
    options: Options,
    onChunk: (chunk: TokenizedText) => void | Promise<void>,
    signal: AbortSignal,
  ): Promise<ProductionRawResultTail> {
    this.streamCalls += 1;
    this.streamSignal = signal;
    this.lastStreamPrompt = options.prompt;
    this.streamFirstStarted?.();
    await onChunk(this.maliciousRawChunk
      ? ({ raw: PHI } as unknown as TokenizedText)
      : branded<TokenizedText>(`Hello ${TOKEN}`));
    await this.streamAfterFirst;
    if (this.waitForStreamAbort) {
      if (signal.aborted) {
        this.sawStreamAbort = true;
      } else {
        await new Promise<void>((resolve) => signal.addEventListener("abort", () => {
          this.sawStreamAbort = true;
          resolve();
        }, { once: true }));
      }
    }
    if (this.emitSecondChunk) {
      this.streamSecondStarted?.();
      await onChunk(branded<TokenizedText>(`Again ${TOKEN}`));
    }
    return {
      providerId: "raw-untrusted-provider",
      model: "model-1",
      toolCalls: [{
        id: "call-1",
        name: "lookup",
        arguments: branded<TokenizedText>(`{"name":"${TOKEN}"}`),
      }],
    } as unknown as ProductionRawResultTail;
  }

  public embedText(text: TokenizedText, _kind: string): Promise<readonly number[]> {
    this.embedCalls += 1;
    this.lastEmbeddingText = String(text);
    return Promise.resolve([1, 2, 3]);
  }
}

function makeRig() {
  const engine = new TestEngine();
  const primary = new TestPrimary();
  const spool = new TestSpool();
  const selected = new TestProvider();
  const unselected = new TestProvider();
  const traceRequests: string[] = [];
  const traceResponses: string[] = [];
  const routedOriginal: string[] = [];
  let contextCalls = 0;
  let policyCalls = 0;
  let routeCalls = 0;
  let projectorCalls = 0;
  let traceMetadataCalls = 0;
  let clockCalls = 0;

  const projector: AiProviderOptionProjector<Options> = {
    classify: (options) => {
      projectorCalls += 1;
      return ({
      segments: [{ path: "prompt", kind: "user", text: options.prompt }],
      rebuild: (segments) => ({ prompt: String(segments[0]!.text) }),
      });
    },
  };

  const dependencies = {
    engine,
    engineVersion: branded("engine-production-1"),
    enginePolicyVersion: ENGINE_POLICY,
    context: { require: async () => { contextCalls += 1; return context(); } },
    policy: { require: async () => { policyCalls += 1; return policy; } },
    projector,
    router: {
      selectUsingOriginalContent: async (options) => {
        routeCalls += 1;
        routedOriginal.push(options.prompt);
        return {
          provider: selected,
          providerId: "azure-baa",
          isProductionSafe: true,
          baaSatisfied: true,
        };
      },
    },
    safeTrace: {
      request: async (paths) => { traceRequests.push(...paths.map((entry) => String(entry.text))); },
      response: async (text) => { traceResponses.push(String(text)); },
      metadata: async () => { traceMetadataCalls += 1; },
    },
    auditPrimary: primary,
    auditSpool: spool,
    embeddingOptionsFactory: (text) => ({ prompt: text }),
    clock: () => { clockCalls += 1; return "2026-08-18T00:00:00.000Z"; },
  } satisfies CreateProductionProtectedAiProviderOptions<Options>;
  const provider = createProductionProtectedAiProvider<Options>(dependencies);

  return {
    engine, primary, spool, selected, unselected, provider, dependencies,
    traceRequests, traceResponses, routedOriginal,
    counts: () => ({
      contextCalls,
      policyCalls,
      routeCalls,
      projectorCalls,
      traceMetadataCalls,
      clockCalls,
    }),
  };
}

describe("GLY-353 production factory runtime", () => {
  it("ORACLE-PROD-CONSTRUCTION-PURE/FACADE: construction invokes no port and returns a tight facade", () => {
    const rig = makeRig();
    expect(rig.counts()).toEqual({
      contextCalls: 0,
      policyCalls: 0,
      routeCalls: 0,
      projectorCalls: 0,
      traceMetadataCalls: 0,
      clockCalls: 0,
    });
    expect(rig.engine.substituteCalls).toBe(0);
    expect(rig.engine.reverseInputs).toHaveLength(0);
    expect(rig.engine.streamCreations).toBe(0);
    expect(rig.primary.prepared).toHaveLength(0);
    expect(rig.spool.calls).toBe(0);
    expect(rig.selected.textCalls).toBe(0);
    expect(rig.selected.streamCalls).toBe(0);
    expect(rig.selected.embedCalls).toBe(0);
    expect(Object.getPrototypeOf(rig.provider)).toBeNull();
    expect(Object.isFrozen(rig.provider)).toBe(true);
    expect(Object.getOwnPropertyNames(rig.provider).sort()).toEqual(["embedText", "generateText", "streamText"]);
  });

  it("ORACLE-PROD-TEXT/TOOL/ROUTE-PIN: envelope and tool arguments reverse through the selected provider", async () => {
    const rig = makeRig();
    rig.selected.started = () => {
      expect(rig.primary.prepared).toHaveLength(1);
    };
    const result = await rig.provider.generateText({ prompt: `Ask about ${PHI}` });

    expect(rig.routedOriginal).toEqual([`Ask about ${PHI}`]);
    expect(rig.traceRequests.join(" ")).not.toContain(PHI);
    expect(rig.traceResponses.join(" ")).not.toContain(PHI);
    expect(rig.selected.textCalls).toBe(1);
    expect(rig.unselected.textCalls).toBe(0);
    expect(rig.selected.lastTextPrompt).toBe(`Ask about ${TOKEN}`);
    expect(rig.counts()).toMatchObject({
      contextCalls: 1,
      policyCalls: 1,
      routeCalls: 1,
      projectorCalls: 1,
    });
    expect(result).toEqual({
      display: `Hello ${PHI}`,
      providerId: "azure-baa",
      model: "model-1",
      usage: { inputTokens: 2, outputTokens: 3, totalTokens: 5 },
      toolCalls: [{ id: "call-1", name: "lookup", arguments: `{"name":"${PHI}"}` }],
    });
    expect(rig.engine.reverseInputs).toEqual([`Hello ${TOKEN}`, `{"name":"${TOKEN}"}`]);
    expect(Object.isFrozen(result)).toBe(true);
    expect(Object.isFrozen(result.toolCalls)).toBe(true);
    expect(Object.isFrozen(result.toolCalls?.[0])).toBe(true);
    expect(rig.primary.finalized.map((event) => event.outcome)).toEqual(["completed"]);
  });

  it("ORACLE-PROD-SINGLETON/SNAPSHOT: every path uses captured caller ports, never live dependency properties", async () => {
    const rig = makeRig();
    const replacement = new TestProvider();
    const mutable = rig.dependencies as unknown as Record<string, unknown>;
    mutable.engine = new TestEngine();
    mutable.router = {
      selectUsingOriginalContent: async () => ({
        provider: replacement,
        providerId: "replacement",
        isProductionSafe: true,
        baaSatisfied: true,
      }),
    };

    await rig.provider.generateText({ prompt: PHI });
    await rig.provider.streamText({ prompt: PHI }, () => undefined);
    await expect(rig.provider.embedText(PHI, "search")).resolves.toEqual([1, 2, 3]);

    expect(rig.engine.substituteCalls).toBe(3);
    expect(rig.engine.streamCreations).toBe(1);
    expect(rig.selected.textCalls).toBe(1);
    expect(rig.selected.streamCalls).toBe(1);
    expect(rig.selected.embedCalls).toBe(1);
    expect(replacement.textCalls + replacement.streamCalls + replacement.embedCalls).toBe(0);
  });

  it("ORACLE-PROD-NO-DEFAULTS: every required dependency fails closed without invoking a port", () => {
    const rig = makeRig();
    const required = [
      "engine", "engineVersion", "enginePolicyVersion", "context", "policy", "projector",
      "router", "safeTrace", "auditPrimary", "auditSpool", "embeddingOptionsFactory",
    ] as const;
    for (const key of required) {
      const candidate = { ...rig.dependencies, [key]: undefined };
      expect(() => createProductionProtectedAiProvider(candidate as never), key).toThrowError(
        expect.objectContaining({ code: "PROVIDER_SAFETY_GATE_FAILED" }),
      );
    }
    const throwing = { ...rig.dependencies } as Record<string, unknown>;
    Object.defineProperty(throwing, "router", { get: () => { throw new Error(PHI); } });
    expect(() => createProductionProtectedAiProvider(throwing as never)).toThrowError(
      expect.objectContaining({ code: "PROVIDER_SAFETY_GATE_FAILED" }),
    );
    expect(rig.counts()).toEqual({
      contextCalls: 0,
      policyCalls: 0,
      routeCalls: 0,
      projectorCalls: 0,
      traceMetadataCalls: 0,
      clockCalls: 0,
    });
    expect(rig.selected.textCalls + rig.selected.streamCalls + rig.selected.embedCalls).toBe(0);
  });

  it("ORACLE-PROD-TOOL-FAIL-CLOSED/METADATA-VALIDATION: no partial envelope escapes", async () => {
    const rig = makeRig();
    rig.engine.failToolReverse = true;
    await expect(rig.provider.generateText({ prompt: PHI })).rejects.toMatchObject({
      name: "PhiEngineError",
      code: "REVERSAL_FAILED",
    });
    expect(rig.primary.finalized).toHaveLength(1);
    expect(rig.primary.finalized[0]?.outcome).toBe("reversal_failed");

    const invalid = makeRig();
    invalid.selected.textResult = {
      text: branded<TokenizedText>(TOKEN),
      model: PHI,
    };
    await expect(invalid.provider.generateText({ prompt: PHI })).rejects.toMatchObject({
      name: "PhiEngineError",
      code: "PROVIDER_SAFETY_GATE_FAILED",
    });
    expect(JSON.stringify(invalid.primary.finalized)).not.toContain(PHI);
  });

  it("ORACLE-PROD-AUDIT-SPOOL: fallback permits one egress and total outage permits zero", async () => {
    const fallback = makeRig();
    fallback.primary.available = false;
    fallback.spool.ready = true;
    await fallback.provider.generateText({ prompt: PHI });
    expect(fallback.selected.textCalls).toBe(1);
    expect(fallback.spool.finalized.map((event) => event.outcome)).toEqual(["completed"]);

    const outage = makeRig();
    outage.primary.available = false;
    outage.spool.ready = false;
    await expect(outage.provider.generateText({ prompt: PHI })).rejects.toMatchObject({
      name: "PhiEngineError",
      code: "AUDIT_DURABILITY_UNAVAILABLE",
    });
    expect(outage.selected.textCalls).toBe(0);
  });

  it("ORACLE-PROD-EMBED: original routing precedes tokenized selected-provider egress", async () => {
    const rig = makeRig();
    await expect(rig.provider.embedText(PHI, "search")).resolves.toEqual([1, 2, 3]);
    expect(rig.routedOriginal).toEqual([PHI]);
    expect(rig.selected.lastEmbeddingText).toBe(TOKEN);
    expect(rig.traceRequests).toEqual([TOKEN]);
    expect(rig.selected.embedCalls).toBe(1);
    expect(rig.unselected.embedCalls).toBe(0);
    expect(rig.primary.prepared).toHaveLength(1);
    expect(rig.primary.finalized.map((event) => event.outcome)).toEqual(["completed"]);
  });

  it("ORACLE-PROD-STREAM-TAIL: only reversed chunks and tool arguments cross the streaming seam", async () => {
    const rig = makeRig();
    const chunks: string[] = [];
    const tail = await rig.provider.streamText(
      { prompt: `Ask about ${PHI}` },
      async (chunk) => { chunks.push(String(chunk)); },
    );
    expect(chunks).toEqual([`Hello ${PHI}`]);
    expect(tail.providerId).toBe("azure-baa");
    expect(tail.toolCalls?.[0]?.arguments).toBe(`{"name":"${PHI}"}`);
    expect(rig.selected.streamCalls).toBe(1);
    expect(rig.primary.finalized.map((event) => event.outcome)).toEqual(["completed"]);
  });

  it("ORACLE-PROD-STREAM-LIVE/BACKPRESSURE: chunk one is live and its sink gates chunk two", async () => {
    const rig = makeRig();
    rig.selected.emitSecondChunk = true;
    let releaseSink!: () => void;
    const sinkGate = new Promise<void>((resolve) => { releaseSink = resolve; });
    let firstSink!: () => void;
    const firstObserved = new Promise<void>((resolve) => { firstSink = resolve; });
    let secondStarted = false;
    rig.selected.streamSecondStarted = () => { secondStarted = true; };
    const chunks: string[] = [];
    const call = rig.provider.streamText({ prompt: PHI }, async (chunk) => {
      chunks.push(String(chunk));
      if (chunks.length === 1) {
        firstSink();
        await sinkGate;
      }
    });
    await firstObserved;
    expect(chunks).toEqual([`Hello ${PHI}`]);
    expect(secondStarted).toBe(false);
    expect(rig.primary.finalized).toHaveLength(0);
    releaseSink();
    await call;
    expect(secondStarted).toBe(true);
    expect(chunks).toEqual([`Hello ${PHI}`, `Again ${PHI}`]);
  });

  it("ORACLE-PROD-STREAM-LIVE: completion buffering cannot delay the first safe chunk", async () => {
    const rig = makeRig();
    let releaseProvider!: () => void;
    rig.selected.streamAfterFirst = new Promise<void>((resolve) => { releaseProvider = resolve; });
    let observed!: () => void;
    const firstObserved = new Promise<void>((resolve) => { observed = resolve; });
    const chunks: string[] = [];
    const call = rig.provider.streamText({ prompt: PHI }, (chunk) => {
      chunks.push(String(chunk));
      observed();
    });
    await firstObserved;
    expect(chunks).toEqual([`Hello ${PHI}`]);
    expect(rig.primary.finalized).toHaveLength(0);
    releaseProvider();
    await call;
  });

  it("ORACLE-PROD-STREAM-TOOL-ARGUMENT-REVERSAL: completion waits for in-package tool reversal", async () => {
    const rig = makeRig();
    let releaseTool!: () => void;
    rig.engine.toolReverseGate = new Promise<void>((resolve) => { releaseTool = resolve; });
    let settled = false;
    const call = rig.provider.streamText({ prompt: PHI }, () => undefined).then((tail) => {
      settled = true;
      return tail;
    });
    await vi.waitFor(() => expect(rig.engine.reverseInputs).toContain(`{"name":"${TOKEN}"}`));
    expect(settled).toBe(false);
    expect(rig.primary.finalized).toHaveLength(0);
    releaseTool();
    const tail = await call;
    expect(tail.toolCalls?.[0]?.arguments).toBe(`{"name":"${PHI}"}`);
    expect(rig.primary.finalized.map((event) => event.outcome)).toEqual(["completed"]);
  });

  it("ORACLE-PROD-STREAM-NONSTRING-REVERSED: malicious reversed carriers fail closed before sink", async () => {
    const rig = makeRig();
    rig.engine.maliciousReversedChunk = true;
    const sink = vi.fn();
    await expect(rig.provider.streamText({ prompt: PHI }, sink)).rejects.toMatchObject({
      name: "PhiEngineError",
      code: "PROVIDER_SAFETY_GATE_FAILED",
    });
    expect(sink).not.toHaveBeenCalled();
    expect(rig.engine.streamAborts).toBe(1);
    expect(rig.primary.finalized).toHaveLength(1);
  });

  it("ORACLE-PROD-STREAM-NONSTRING-RAW: malicious provider chunks fail before trace, reversal, or sink", async () => {
    const rig = makeRig();
    rig.selected.maliciousRawChunk = true;
    const sink = vi.fn();
    await expect(rig.provider.streamText({ prompt: PHI }, sink)).rejects.toMatchObject({
      name: "PhiEngineError",
      code: "PROVIDER_SAFETY_GATE_FAILED",
    });
    expect(sink).not.toHaveBeenCalled();
    expect(rig.traceResponses).toHaveLength(0);
    expect(rig.engine.streamAborts).toBe(1);
  });

  it("ORACLE-PROD-STREAM-SINK-FAILURE: sink rejection remains a failure, never interruption", async () => {
    const rig = makeRig();
    await expect(rig.provider.streamText(
      { prompt: PHI },
      async () => { throw new Error(`sink ${PHI}`); },
    )).rejects.toMatchObject({
      name: "PhiEngineError",
      code: "PROVIDER_SAFETY_GATE_FAILED",
    });
    expect(rig.selected.streamCalls).toBe(1);
    expect(rig.primary.finalized).toHaveLength(1);
    expect(rig.primary.finalized[0]?.outcome).not.toBe("interrupted");
    expect(JSON.stringify(rig.primary.finalized)).not.toContain(PHI);
  });

  it("ORACLE-PROD-ABORT-IN-FLIGHT: abort propagates privately and finalizes interrupted once", async () => {
    const rig = makeRig();
    rig.selected.waitForAbort = true;
    let started!: () => void;
    const providerStarted = new Promise<void>((resolve) => { started = resolve; });
    rig.selected.started = started;
    const controller = new AbortController();
    const remove = vi.spyOn(controller.signal, "removeEventListener");
    const call = rig.provider.generateText({ prompt: PHI }, controller.signal);
    await providerStarted;
    controller.abort("caller secret reason");

    await expect(call).rejects.toMatchObject({ name: "PhiEngineError", code: "CALL_INTERRUPTED" });
    expect(rig.selected.sawAbort).toBe(true);
    expect(rig.selected.textCalls).toBe(1);
    expect(rig.primary.finalized).toHaveLength(1);
    expect(rig.primary.finalized[0]).toMatchObject({ outcome: "interrupted", failureCode: null });
    expect(JSON.stringify(rig.primary.finalized)).not.toContain("caller secret reason");
    expect(remove).toHaveBeenCalledTimes(1);
  });

  it("ORACLE-PROD-ABORT-IN-FLIGHT-STREAM/SINK-RACE: abort wins once and suppresses later display", async () => {
    const rig = makeRig();
    rig.selected.waitForStreamAbort = true;
    let first!: () => void;
    const firstObserved = new Promise<void>((resolve) => { first = resolve; });
    const chunks: string[] = [];
    const controller = new AbortController();
    const call = rig.provider.streamText({ prompt: PHI }, (chunk) => {
      chunks.push(String(chunk));
      first();
    }, controller.signal);
    await firstObserved;
    controller.abort(`raw ${PHI}`);
    await expect(call).rejects.toMatchObject({ name: "PhiEngineError", code: "CALL_INTERRUPTED" });
    expect(rig.selected.streamSignal?.aborted).toBe(true);
    expect(rig.selected.streamCalls).toBe(1);
    expect(chunks).toEqual([`Hello ${PHI}`]);
    expect(rig.engine.streamAborts).toBe(1);
    expect(rig.primary.finalized).toHaveLength(1);
    expect(rig.primary.finalized[0]).toMatchObject({ outcome: "interrupted", failureCode: null });
    expect(JSON.stringify(rig.primary.finalized)).not.toContain(PHI);
  });

  it("ORACLE-PROD-ABORT-SINK-RACE: interruption latched inside the sink beats its rejection", async () => {
    const rig = makeRig();
    const controller = new AbortController();
    const call = rig.provider.streamText({ prompt: PHI }, () => {
      controller.abort(`raw ${PHI}`);
      throw new Error(`raw ${PHI}`);
    }, controller.signal);
    await expect(call).rejects.toMatchObject({ name: "PhiEngineError", code: "CALL_INTERRUPTED" });
    expect(rig.primary.finalized).toHaveLength(1);
    expect(rig.primary.finalized[0]).toMatchObject({ outcome: "interrupted", failureCode: null });
    expect(JSON.stringify(rig.primary.finalized)).not.toContain(PHI);
  });

  it("ORACLE-PROD-LATE-ABORT: completed calls remove the listener and ignore later abort", async () => {
    const rig = makeRig();
    const controller = new AbortController();
    const remove = vi.spyOn(controller.signal, "removeEventListener");
    await rig.provider.generateText({ prompt: PHI }, controller.signal);
    expect(remove).toHaveBeenCalledTimes(1);
    controller.abort();
    expect(rig.primary.finalized).toHaveLength(1);
    expect(rig.primary.finalized[0]?.outcome).toBe("completed");
  });

  it("ORACLE-PROD-ABORT-BEFORE-EGRESS-R3: unavailable PREPARE cannot override CALL_INTERRUPTED", async () => {
    const rig = makeRig();
    rig.primary.available = false;
    rig.spool.ready = false;
    const controller = new AbortController();
    controller.abort();

    let thrown: unknown;
    try {
      await rig.provider.generateText({ prompt: PHI }, controller.signal);
    } catch (error) {
      thrown = error;
    }
    expect(isPhiEngineError(thrown)).toBe(true);
    expect((thrown as { code: string }).code).toBe("CALL_INTERRUPTED");
    expect(rig.counts().routeCalls).toBe(0);
    expect(rig.selected.textCalls).toBe(0);
    expect(rig.primary.prepared).toHaveLength(1);
    expect(rig.primary.finalized).toHaveLength(0);
  });
});
