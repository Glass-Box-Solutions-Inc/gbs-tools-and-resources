// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
/**
 * GLY-336 M1 smoke + boundary oracles (ADDED, not frozen — §10).
 *
 * Two jobs:
 *  1. Prove the tightened root barrel is EXERCISED, not merely declared: import the composition
 *     factories from the published root (`../src/index`, i.e. `dist/index.js`) and drive a real
 *     substitute+reverse round-trip and a protected-provider round-trip.
 *  2. Reflection-oriented §7/N2 oracles (GPT cross-family gate): prove (i) the concrete reversal
 *     store's raw backing map is NOT reflectively enumerable (#private holds under ES2022), and
 *     (ii) the public root does NOT export the concrete stores/handle/reverser/live policy.
 *
 * The dev seed is deliberately fictional: `Jordan Testcase` (never a real person) and the SSA
 * advertising-reserved SSN block.
 */
import { describe, expect, it } from "vitest";
import {
  createProtectedAiProvider,
  createSubstitutionEngine,
  createTokensModule,
  PhiEngineError,
  ReversalFailedError,
  REVERSAL_FAILED,
} from "../src/index";
import type { BoundaryGenerateOptions, TextSegment } from "../src/index";

const DEV_NAME = "Jordan Testcase";

describe("GLY-336 M1: composable from a TIGHT published root", () => {
  it("root exports the factories + error surface — and nothing else runtime", async () => {
    const mod = (await import("../src/index")) as Record<string, unknown>;

    // (3) allowed runtime root exports
    for (const name of [
      "createSubstitutionEngine",
      "createProtectedAiProvider",
      "createTokensModule",
      "PhiEngineError",
      "isPhiEngineError",
      "isPhiEngineFailureCode",
      "ReversalFailedError",
      "REVERSAL_FAILED",
    ]) {
      expect(typeof mod[name] !== "undefined", `${name} MUST be a root export`).toBe(true);
    }

    // Boundary oracle (ii): no concrete internal class / live policy / dev seed at the root.
    for (const name of [
      "InMemoryReversalStore",
      "InProcessReversalHandle",
      "isInProcessReversalHandle",
      "reverseText",
      "AtomicTokenReverser",
      "HoldbackReverseStreamFactory",
      "ComposedSubstitutionEngine",
      "ComposedProtectedAiProvider",
      "BracketTokenGrammar",
      "InMemoryTokenAssignmentStore",
      "SentinelSourceTokenEscaper",
      "InMemoryCaseTruthReader",
      "InMemoryDictionaryVersionCoordinator",
      "BOUNDARY_TOKEN_GRAMMAR_POLICY",
      "DEFAULT_TOKEN_GRAMMAR_POLICY",
      "DEFAULT_DEV_TAGGED_VALUES",
      "SENTINEL_OPEN",
      "SENTINEL_CLOSE",
    ]) {
      expect(mod[name], `${name} MUST NOT be a root export`).toBeUndefined();
    }

    expect(REVERSAL_FAILED).toBe("REVERSAL_FAILED");
    expect(new ReversalFailedError()).toBeInstanceOf(Error);
    expect(new PhiEngineError("REVERSAL_FAILED").code).toBe("REVERSAL_FAILED");
  });

  it("boundary oracle (i): the concrete reversal store's raw map is NOT reflectively enumerable", async () => {
    // createTokensModule returns the store typed as the bounded interface; the runtime object is
    // the concrete InMemoryReversalStore, so this exercises the real #private backing.
    const store = createTokensModule().reversalStore as unknown as {
      record: (input: unknown) => void;
      resolveEncounteredTokens: (input: unknown) => Promise<ReadonlyMap<string, string>>;
    };
    const CANARY = "Jordan Testcase — 987-65-4320"; // a raw value the store now holds

    store.record({
      tenantId: "t-1",
      matterId: "m-1",
      dictionaryVersion: 1n,
      token: "[[Claimant]]",
      canonical: CANARY,
      attemptId: "a-1",
    });

    // The value IS stored — the bounded read returns it...
    const resolved = await store.resolveEncounteredTokens({
      tenantId: "t-1",
      matterId: "m-1",
      dictionaryVersion: 1n,
      tokens: ["[[Claimant]]"],
    });
    expect(resolved.get("[[Claimant]]")).toBe(CANARY);

    // ...but it is NOT reachable by any reflective/enumerable path.
    const ownNames = Object.getOwnPropertyNames(store);
    const reflectKeys = Reflect.ownKeys(store).map((k) => String(k));
    const enumKeys = Object.keys(store);
    for (const forbidden of ["canonicalByKey", "recordedAttempts"]) {
      expect(ownNames, `getOwnPropertyNames must not expose ${forbidden}`).not.toContain(forbidden);
      expect(reflectKeys, `Reflect.ownKeys must not expose ${forbidden}`).not.toContain(forbidden);
      expect(enumKeys, `Object.keys must not expose ${forbidden}`).not.toContain(forbidden);
    }
    // No enumerable own value (nor a whole-object serialization) reveals the raw canonical.
    expect(JSON.stringify(store) ?? "").not.toContain("Jordan Testcase");
    for (const name of ownNames) {
      const value = (store as unknown as Record<string, unknown>)[name];
      expect(JSON.stringify(value ?? null)).not.toContain("Jordan Testcase");
    }
  });

  it("boundary oracle (finding 2): the grammar policy handed out is deep-frozen", () => {
    const tokens = createTokensModule();
    expect(Object.isFrozen(tokens.policy)).toBe(true);
    expect(Object.isFrozen(tokens.policy.allowedRoles)).toBe(true);
  });

  it("createSubstitutionEngine() composes and performs a basic substitution + reversal", async () => {
    const dev = createSubstitutionEngine();
    expect(typeof dev.engine.substitute).toBe("function");

    const raw = `Please contact ${DEV_NAME} regarding the claim intake.`;
    const segments: TextSegment[] = [
      { path: "messages[0].content[0].text", kind: "user", text: raw },
    ];

    const result = await dev.engine.substitute({
      context: dev.context,
      policy: dev.policy,
      segments,
      purpose: "generation",
    });

    const tokenized = String(result.segments[0]!.text);
    expect(tokenized).toMatch(/\[\[Claimant/); // trusted name replaced with a role token
    expect(tokenized).not.toContain(DEV_NAME); // raw value never survives into egress text

    // §7/N2: the reversal handle is a non-serializable capability, never a map.
    expect(() => result.reversalHandle.toJSON()).toThrow();

    const display = await dev.engine.reverse(result.segments[0]!.text, result.reversalHandle);
    expect(String(display)).toContain(DEV_NAME); // reversed server-side for display
  });

  it("createProtectedAiProvider() round-trips generateText through the protected binding", async () => {
    const dev = createProtectedAiProvider();
    const options: BoundaryGenerateOptions = {
      messages: [{ role: "user", content: [{ type: "text", text: `Please contact ${DEV_NAME}.` }] }],
    };
    const display = await dev.provider.generateText(options);
    // The dev raw provider only ever saw tokenized text; the wrapper reversed it for display.
    expect(String(display)).toContain(DEV_NAME);
    expect(String(display)).not.toContain("[[Claimant");
  });
});
