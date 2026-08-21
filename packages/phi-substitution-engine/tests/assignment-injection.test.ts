import { describe, expect, it } from "vitest";
import {
  createProtectedAiProvider,
  createSubstitutionEngine,
  isPhiEngineError,
} from "../src/index";
import type {
  BoundaryGenerateOptions,
  CaseTruthReader,
  CreateSubstitutionEngineOptions,
  RawProviderPort,
  SubstitutionToken,
  TaggedValue,
  TextSegment,
  TokenAssignmentStore,
  TokenizedText,
} from "../src/index";

const CLAIMANT = "Avery Fixture";
const CANARY = "GLY372-PHI-CANARY";

function branded<T>(value: unknown): T {
  return value as T;
}

function tagged(subjectId: string, canonical = CLAIMANT): TaggedValue {
  return {
    field: {
      schemaPath: `claim.${subjectId}`,
      substitution: true,
      identifierClass: "PERSON_NAME",
      tokenRole: branded("Claimant"),
      expander: "person-name",
    },
    subjectId: branded(subjectId),
    canonicalDisplayValue: canonical,
    approvedAliases: [],
  };
}

function segments(text: string): readonly TextSegment[] {
  return [{ path: "messages[0].content[0].text", kind: "user", text }];
}

async function substitute(
  dev: ReturnType<typeof createSubstitutionEngine>,
  text: string,
): Promise<string> {
  const result = await dev.engine.substitute({
    context: dev.context,
    policy: dev.policy,
    segments: segments(text),
    purpose: "generation",
  });
  return String(result.segments[0]!.text);
}

function expectFixedFailure(error: unknown): void {
  expect(isPhiEngineError(error)).toBe(true);
  if (!isPhiEngineError(error))
    throw new Error("fixed failure assertion failed");
  expect(error.code).toBe("DICTIONARY_UNAVAILABLE");
  const exposed = [String(error), error.message, JSON.stringify(error)].join(
    "\n",
  );
  expect(exposed).not.toContain(CANARY);
}

type AssignmentInput = Parameters<TokenAssignmentStore["getOrAllocate"]>[0];

interface SharedAssignmentState {
  readonly assigned: Map<string, SubstitutionToken>;
  readonly nextOrdinalByRole: Map<string, number>;
  readonly retiredTokens: Set<string>;
  readonly acquisitionCalls: AssignmentInput[];
  readonly retirementCalls: AssignmentInput[];
}

function sharedState(): SharedAssignmentState {
  return {
    assigned: new Map(),
    nextOrdinalByRole: new Map(),
    retiredTokens: new Set(),
    acquisitionCalls: [],
    retirementCalls: [],
  };
}

class RecordingSharedAssignmentStore implements TokenAssignmentStore {
  public constructor(
    public readonly state: SharedAssignmentState = sharedState(),
  ) {}

  public restart(): RecordingSharedAssignmentStore {
    return new RecordingSharedAssignmentStore(this.state);
  }

  public getOrAllocate(input: AssignmentInput): Promise<SubstitutionToken> {
    this.state.acquisitionCalls.push({ ...input });
    const identity = [
      input.tenantId,
      input.matterId,
      input.subjectId,
      input.role,
    ].join("\0");
    const existing = this.state.assigned.get(identity);
    if (existing !== undefined) return Promise.resolve(existing);

    const roleKey = [input.tenantId, input.matterId, input.role].join("\0");
    let ordinal = this.state.nextOrdinalByRole.get(roleKey) ?? 1;
    let token =
      ordinal === 1 ? `[[${input.role}]]` : `[[${input.role}_${ordinal}]]`;
    while (this.state.retiredTokens.has(token)) {
      ordinal += 1;
      token = `[[${input.role}_${ordinal}]]`;
    }
    const brandedToken = branded<SubstitutionToken>(token);
    this.state.nextOrdinalByRole.set(roleKey, ordinal + 1);
    this.state.assigned.set(identity, brandedToken);
    return Promise.resolve(brandedToken);
  }

  public retire(input: AssignmentInput): Promise<void> {
    this.state.retirementCalls.push({ ...input });
    const identity = [
      input.tenantId,
      input.matterId,
      input.subjectId,
      input.role,
    ].join("\0");
    const token = this.state.assigned.get(identity);
    if (token !== undefined) {
      this.state.retiredTokens.add(String(token));
      this.state.assigned.delete(identity);
    }
    return Promise.resolve();
  }
}

function fixedStore(token: unknown, onCall?: () => void): TokenAssignmentStore {
  return {
    getOrAllocate: () => {
      onCall?.();
      return Promise.resolve(token as SubstitutionToken);
    },
    retire: () => Promise.resolve(),
  };
}

function countingRawProvider(counter: {
  calls: number;
}): RawProviderPort<BoundaryGenerateOptions, string> {
  return {
    generateText: () => {
      counter.calls += 1;
      return Promise.resolve(branded<TokenizedText>("[[Claimant]]"));
    },
    generateStream: async (_options, onChunk): Promise<void> => {
      counter.calls += 1;
      await onChunk(branded<TokenizedText>("[[Claimant]]"));
    },
    embedText: () => {
      counter.calls += 1;
      return Promise.resolve([1]);
    },
  };
}

describe("GLY-372 assignment-authority injection seam", () => {
  it("GLY372-OR-01: package-root injection exclusively serves real tagged assignments", async () => {
    const calls: AssignmentInput[] = [];
    const store: TokenAssignmentStore = {
      getOrAllocate: (input) => {
        calls.push({ ...input });
        return Promise.resolve(branded("[[Claimant_41]]"));
      },
      retire: () => Promise.resolve(),
    };
    const dev = createSubstitutionEngine({
      tenantId: "tenant-01",
      matterId: "matter-01",
      dictionaryVersion: 7n,
      taggedValues: [tagged("subject-real-01")],
      assignmentStore: store,
    });

    const output = await substitute(dev, `Contact ${CLAIMANT}.`);
    expect(output).toBe("Contact [[Claimant_41]].");
    expect(output).not.toContain(CLAIMANT);
    expect(output).not.toContain("[[Claimant]].");
    expect(calls).toHaveLength(1);
    expect(calls[0]).toEqual({
      tenantId: "tenant-01",
      matterId: "matter-01",
      subjectId: "subject-real-01",
      role: "Claimant",
      dictionaryVersion: 7n,
    });
  });

  it("GLY372-OR-02: two engines share stable collision-free real assignments across order restart version and retirement", async () => {
    const first = new RecordingSharedAssignmentStore();
    const a = tagged("subject-a", "Avery Alpha");
    const b = tagged("subject-b", "Blake Beta");
    const common = {
      tenantId: "tenant-02",
      matterId: "matter-02",
      dictionaryVersion: 1n,
    };
    const engineOne = createSubstitutionEngine({
      ...common,
      taggedValues: [a, b],
      assignmentStore: first,
    });
    const engineTwo = createSubstitutionEngine({
      ...common,
      taggedValues: [b, a],
      assignmentStore: first.restart(),
    });

    const [outA, outB] = await Promise.all([
      substitute(engineOne, "Avery Alpha"),
      substitute(engineTwo, "Blake Beta"),
    ]);
    expect(outA).not.toBe(outB);
    expect(new Set([outA, outB]).size).toBe(2);
    expect(first.state.assigned.size).toBe(2);
    expect(new Set(first.state.assigned.values()).size).toBe(
      first.state.assigned.size,
    );
    expect(
      new Set(
        first.state.acquisitionCalls.map((call) => String(call.subjectId)),
      ),
    ).toEqual(new Set(["subject-a", "subject-b"]));

    const restartedA = createSubstitutionEngine({
      ...common,
      taggedValues: [b, a],
      assignmentStore: first.restart(),
    });
    const restartedB = createSubstitutionEngine({
      ...common,
      taggedValues: [a, b],
      assignmentStore: first.restart(),
    });
    expect(await substitute(restartedA, "Avery Alpha")).toBe(outA);
    expect(await substitute(restartedB, "Blake Beta")).toBe(outB);

    const versionTwo = createSubstitutionEngine({
      tenantId: common.tenantId,
      matterId: common.matterId,
      dictionaryVersion: 2n,
      taggedValues: [b],
      assignmentStore: first.restart(),
    });
    expect(await substitute(versionTwo, "Blake Beta")).toBe(outB);
    expect(
      first.state.acquisitionCalls.some(
        (call) => call.dictionaryVersion === 2n,
      ),
    ).toBe(true);

    await first.retire({
      tenantId: branded(common.tenantId),
      matterId: branded(common.matterId),
      subjectId: branded("subject-a"),
      role: branded("Claimant"),
      dictionaryVersion: branded(2n),
    });
    const c = tagged("subject-c", "Casey Gamma");
    const engineC = createSubstitutionEngine({
      ...common,
      taggedValues: [c],
      assignmentStore: first.restart(),
    });
    const outC = await substitute(engineC, "Casey Gamma");
    expect(outC).not.toBe(outA);
    expect(outC).not.toBe(outB);
    expect(first.state.retiredTokens.has(outA)).toBe(true);
    expect(first.state.nextOrdinalByRole.values().next().value).toBeGreaterThan(
      3,
    );
    expect(first.state.retirementCalls).toHaveLength(1);
  });

  it("GLY372-OR-03: injected authority throw or rejection fails closed without local fallback or provider call", async () => {
    let visited = 0;
    for (const factory of ["engine", "provider"] as const) {
      for (const mode of ["throw", "reject"] as const) {
        visited += 1;
        let calls = 0;
        const store: TokenAssignmentStore = {
          getOrAllocate: () => {
            calls += 1;
            const failure = { message: CANARY, code: CANARY, cause: CANARY };
            if (mode === "throw") throw failure;
            return Promise.reject(failure);
          },
          retire: () => Promise.resolve(),
        };
        const rawCounter = { calls: 0 };
        let result: unknown;
        let error: unknown;
        try {
          if (factory === "engine") {
            const dev = createSubstitutionEngine({
              taggedValues: [tagged("subject-fail")],
              assignmentStore: store,
            });
            result = await substitute(dev, CLAIMANT);
          } else {
            const dev = createProtectedAiProvider({
              taggedValues: [tagged("subject-fail")],
              assignmentStore: store,
              invokeRaw: countingRawProvider(rawCounter),
            });
            result = await dev.provider.generateText({
              messages: [
                { role: "user", content: [{ type: "text", text: CLAIMANT }] },
              ],
            });
          }
        } catch (caught) {
          error = caught;
        }
        expect(result).toBeUndefined();
        expectFixedFailure(error);
        expect(calls).toBe(1);
        expect(rawCounter.calls).toBe(0);
      }
    }
    expect(visited).toBe(4);
  });

  it("GLY372-OR-04: invalid or wrong-role authority successes fail closed before output", async () => {
    let coercions = 0;
    const throwingCoercion = {
      [Symbol.toPrimitive]: () => {
        coercions += 1;
        throw new Error(CANARY);
      },
      toString: () => {
        coercions += 1;
        throw new Error(CANARY);
      },
    };
    const matrix: readonly unknown[] = [
      CANARY,
      "[[Claimant_x]]",
      "[[Unknown_2]]",
      "[[Witness_8]]",
      new String("[[Claimant_9]]"),
      null,
      throwingCoercion,
    ];
    let visited = 0;
    for (const returned of matrix) {
      visited += 1;
      const rawCounter = { calls: 0 };
      const dev = createProtectedAiProvider({
        taggedValues: [tagged("subject-invalid")],
        assignmentStore: fixedStore(returned),
        invokeRaw: countingRawProvider(rawCounter),
      });
      let result: unknown;
      let error: unknown;
      try {
        result = await dev.provider.generateText({
          messages: [
            { role: "user", content: [{ type: "text", text: CLAIMANT }] },
          ],
        });
      } catch (caught) {
        error = caught;
      }
      expect(result).toBeUndefined();
      expectFixedFailure(error);
      expect(rawCounter.calls).toBe(0);
    }
    expect(visited).toBe(7);
    expect(coercions).toBe(0);
  });

  it("GLY372-OR-05: omitted assignment authority preserves the 0.1.0 process-local default", async () => {
    const engineA = createSubstitutionEngine({
      taggedValues: [tagged("default-a", "Avery Alpha")],
    });
    const engineB = createSubstitutionEngine({
      taggedValues: [tagged("default-b", "Blake Beta")],
    });
    expect(await substitute(engineA, "Avery Alpha")).toBe("[[Claimant]]");
    expect(await substitute(engineB, "Blake Beta")).toBe("[[Claimant]]");

    const first = await engineA.engine.substitute({
      context: engineA.context,
      policy: engineA.policy,
      segments: segments("Avery Alpha"),
      purpose: "generation",
    });
    const second = await engineA.engine.substitute({
      context: engineA.context,
      policy: engineA.policy,
      segments: segments("Avery Alpha"),
      purpose: "generation",
    });
    expect(String(second.segments[0]!.text)).toBe("[[Claimant]]");
    expect(
      String(
        await engineA.engine.reverse(
          first.segments[0]!.text,
          first.reversalHandle,
        ),
      ),
    ).toBe("Avery Alpha");

    const explicitUndefined = createSubstitutionEngine({
      taggedValues: [tagged("default-undefined", "Casey Gamma")],
      assignmentStore: undefined,
    });
    expect(await substitute(explicitUndefined, "Casey Gamma")).toBe(
      "[[Claimant]]",
    );

    const detectorDefault = createSubstitutionEngine({ taggedValues: [] });
    const detectorResult = await detectorDefault.engine.substitute({
      context: detectorDefault.context,
      policy: detectorDefault.policy,
      segments: segments("987-65-4321"),
      purpose: "generation",
    });
    const detectorOutput = String(detectorResult.segments[0]!.text);
    expect(detectorOutput).toMatch(/^\[\[SSN(?:_\d+)?\]\]$/);
    expect(
      String(
        await detectorDefault.engine.reverse(
          detectorResult.segments[0]!.text,
          detectorResult.reversalHandle,
        ),
      ),
    ).toBe("987-65-4321");

    let truthReads = 0;
    const truthReader: CaseTruthReader = {
      readTaggedValues: () => {
        truthReads += 1;
        return Promise.resolve([tagged("warm-default", "Drew Delta")]);
      },
    };
    const warmDefault = createSubstitutionEngine({ truthReader });
    await substitute(warmDefault, "Drew Delta");
    await substitute(warmDefault, "Drew Delta");
    expect(truthReads).toBe(1);
  });

  it("GLY372-OR-08A: malformed injected authorities fixed-fail construction and return no engine", () => {
    const throwing = new Proxy(
      {},
      {
        get: (_target, property) => {
          if (property === "getOrAllocate") throw new Error(CANARY);
          return undefined;
        },
      },
    );
    const rows: readonly unknown[] = [
      null,
      {},
      { getOrAllocate: 1 },
      { getOrAllocate: () => Promise.resolve(branded("[[Claimant]]")) },
      throwing,
      17,
    ];
    let visited = 0;
    let downstreamReads = 0;
    for (const assignmentStore of rows) {
      visited += 1;
      const options = {
        assignmentStore,
      } as unknown as CreateSubstitutionEngineOptions;
      Object.defineProperty(options, "taggedValues", {
        get: () => {
          downstreamReads += 1;
          return [tagged("must-not-read")];
        },
      });
      let returnedEngine: unknown;
      let error: unknown;
      try {
        returnedEngine = createSubstitutionEngine(options);
      } catch (caught) {
        error = caught;
      }
      expect(returnedEngine).toBeUndefined();
      expectFixedFailure(error);
    }
    expect(visited).toBe(6);
    expect(downstreamReads).toBe(0);
  });

  it("GLY372-OR-08B: assignmentStore options accessor is read once and acquisition uses the snapshot", async () => {
    let reads = 0;
    let callsA = 0;
    let callsB = 0;
    const authorityA = fixedStore("[[Claimant_41]]", () => {
      callsA += 1;
    });
    const authorityB = fixedStore("[[Claimant_42]]", () => {
      callsB += 1;
    });
    const options: Record<string, unknown> = {
      taggedValues: [tagged("snapshot-subject")],
    };
    Object.defineProperty(options, "assignmentStore", {
      enumerable: true,
      get: () => {
        reads += 1;
        return reads === 1 ? authorityA : authorityB;
      },
    });
    const dev = createSubstitutionEngine(
      options as unknown as CreateSubstitutionEngineOptions,
    );
    expect(await substitute(dev, CLAIMANT)).toBe("[[Claimant_41]]");
    expect(reads).toBe(1);
    expect(callsA).toBe(1);
    expect(callsB).toBe(0);
  });

  it("GLY372-OR-09: injected mode never persists synthetic detector subjects", async () => {
    const injected = new RecordingSharedAssignmentStore();
    const rawCounter = { calls: 0 };
    const dev = createProtectedAiProvider({
      taggedValues: [],
      assignmentStore: injected,
      invokeRaw: countingRawProvider(rawCounter),
    });
    let output: unknown;
    let error: unknown;
    try {
      output = await dev.provider.generateText({
        messages: [
          { role: "user", content: [{ type: "text", text: "987-65-4321" }] },
        ],
      });
    } catch (caught) {
      error = caught;
    }
    expect(output).toBeUndefined();
    expectFixedFailure(error);
    expect(injected.state.acquisitionCalls).toHaveLength(0);
    expect(injected.state.retirementCalls).toHaveLength(0);
    expect(injected.state.assigned.size).toBe(0);
    expect(rawCounter.calls).toBe(0);
  });

  it("GLY372-OR-10: injected mode reacquires on every substitute and observes peer retirement", async () => {
    let rowCount = 0;
    const state = sharedState();
    const authorityA = new RecordingSharedAssignmentStore(state);
    const authorityB = authorityA.restart();
    let visits = 0;
    const real = tagged("subject-live", "Robin Repeat");
    const reader: CaseTruthReader = {
      readTaggedValues: () => {
        visits += 1;
        return Promise.resolve([real]);
      },
    };
    const peer = createSubstitutionEngine({
      truthReader: reader,
      assignmentStore: authorityA,
    });
    const live = createSubstitutionEngine({
      truthReader: reader,
      assignmentStore: authorityB,
    });
    expect(peer.engine).not.toBe(live.engine);
    const first = await substitute(live, "Robin Repeat");
    const second = await substitute(live, "Robin Repeat");
    expect(second).toBe(first);
    expect(visits).toBe(2);
    expect(state.acquisitionCalls).toHaveLength(2);
    rowCount += 1;

    await authorityA.retire({
      tenantId: branded("dev-tenant"),
      matterId: branded("dev-matter"),
      subjectId: branded("subject-live"),
      role: branded("Claimant"),
      dictionaryVersion: branded(1n),
    });
    const afterRetirement = await substitute(live, "Robin Repeat");
    expect(afterRetirement).not.toBe(first);
    expect(afterRetirement).not.toContain(first);
    expect(state.acquisitionCalls).toHaveLength(3);
    expect(state.retiredTokens.has(first)).toBe(true);
    rowCount += 1;

    let defaultVisits = 0;
    const defaultReader: CaseTruthReader = {
      readTaggedValues: () => {
        defaultVisits += 1;
        return Promise.resolve([tagged("default-warm", "Taylor Control")]);
      },
    };
    const control = createSubstitutionEngine({ truthReader: defaultReader });
    await substitute(control, "Taylor Control");
    await substitute(control, "Taylor Control");
    expect(defaultVisits).toBe(1);
    expect(rowCount).toBe(2);
  });
});
