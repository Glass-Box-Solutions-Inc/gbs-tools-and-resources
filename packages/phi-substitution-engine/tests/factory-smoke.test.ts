// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
/**
 * GLY-336 M1 smoke + CAPABILITY-level boundary oracles (ADDED, not frozen — §10).
 *
 * After the GPT cross-family gate: name-pruning the barrel is not enough — the factories must hand
 * out UNFORGEABLE facades, and the policy must be GENUINELY immutable. These oracles prove the
 * capability boundary, not just the export names:
 *  - the returned provider/engine are frozen null-prototype facades (no recoverable constructor,
 *    no reachable concrete internals);
 *  - the boundary role policy cannot be mutated, even via `Set.prototype.add.call`;
 *  - the root barrel exports only the factories + error surface (createTokensModule is NOT public);
 *  - (regression) the concrete reversal store's raw map stays #private / non-enumerable.
 *
 * Test-internal DEEP imports (from ../src/...) are legitimate — the boundary under test is the
 * PUBLIC package root (../src/index), and a test is allowed to reach internals to probe them.
 */
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import {
  createProtectedAiProvider,
  createSubstitutionEngine,
  PhiEngineError,
  ReversalFailedError,
  REVERSAL_FAILED,
} from "../src/index";
import type { BoundaryGenerateOptions, TextSegment } from "../src/index";
// Deep imports (test-internal probes of internals — NOT the public boundary):
import { InMemoryReversalStore } from "../src/tokens/index";
import { BOUNDARY_TOKEN_GRAMMAR_POLICY } from "../src/core/orchestrator";

const DEV_NAME = "Jordan Testcase";

describe("GLY-336 M1: capability-tight composition from the published root", () => {
  it("GLY372-OR-06: assignment injection adds types only and leaks no authority capability", async () => {
    const mod = (await import("../src/index")) as Record<string, unknown>;
    expect(mod["TokenAssignmentStore"]).toBeUndefined();
    expect(mod["assignmentStore"]).toBeUndefined();

    const engineBundle = createSubstitutionEngine() as unknown as Record<
      string,
      unknown
    >;
    const providerBundle = createProtectedAiProvider() as unknown as Record<
      string,
      unknown
    >;
    expect(engineBundle["assignmentStore"]).toBeUndefined();
    expect(providerBundle["assignmentStore"]).toBeUndefined();
    expect(
      (engineBundle["engine"] as Record<string, unknown>)["assignmentStore"],
    ).toBeUndefined();
    expect(
      (providerBundle["provider"] as Record<string, unknown>)[
        "assignmentStore"
      ],
    ).toBeUndefined();
  });

  it("root exports ONLY the factories + error surface (createTokensModule is not public)", async () => {
    const mod = (await import("../src/index")) as Record<string, unknown>;
    for (const name of [
      "createSubstitutionEngine",
      "createProtectedAiProvider",
      "createProductionProtectedAiProvider",
      "PhiEngineError",
      "isPhiEngineError",
      "isPhiEngineFailureCode",
      "ReversalFailedError",
      "REVERSAL_FAILED",
    ]) {
      expect(
        typeof mod[name] !== "undefined",
        `${name} MUST be a root export`,
      ).toBe(true);
    }
    for (const name of [
      "createTokensModule", // finding 4 — dropped from the public root
      "ComposedSubstitutionEngine",
      "ComposedProtectedAiProvider",
      "InMemoryReversalStore",
      "InProcessReversalHandle",
      "isInProcessReversalHandle",
      "reverseText",
      "AtomicTokenReverser",
      "HoldbackReverseStreamFactory",
      "BracketTokenGrammar",
      "InMemoryTokenAssignmentStore",
      "SentinelSourceTokenEscaper",
      "InMemoryCaseTruthReader",
      "InMemoryDictionaryVersionCoordinator",
      "BOUNDARY_TOKEN_GRAMMAR_POLICY",
      "DEFAULT_TOKEN_GRAMMAR_POLICY",
      "DEFAULT_DEV_TAGGED_VALUES",
      "frozenRoleSet",
      "SENTINEL_OPEN",
      "SENTINEL_CLOSE",
      // L2.4 durable concrete surface — MUST stay behind the factory wiring / port types, never at the
      // runtime root (a value export here would leak a reversal or decryption capability past the barrel).
      "DurableReversalStore",
      "InMemoryKeyProvider",
      "InMemoryReversalSpoolBackend",
      "InMemoryReversalSpoolVolume",
      "gcmEncrypt",
      "gcmDecrypt",
      "buildReversalAad",
      "mappingKeyOf",
    ]) {
      expect(mod[name], `${name} MUST NOT be a root export`).toBeUndefined();
    }
    expect(REVERSAL_FAILED).toBe("REVERSAL_FAILED");
    expect(new ReversalFailedError()).toBeInstanceOf(Error);
    expect(new PhiEngineError("REVERSAL_FAILED").code).toBe("REVERSAL_FAILED");
  });

  it("package.json `exports` fences the deep barrels — no subpath re-exposes the concrete store / crypto / key material", () => {
    // The runtime-root guard above proves the concrete durable surface is not re-exported from src/index.
    // But the deep barrels (src/tokens/index, src/tokens/durable/index) DO export DurableReversalStore /
    // gcmDecrypt / InMemoryKeyProvider; today they are unreachable to an external consumer ONLY because
    // the package `exports` map has no subpath for them. A wildcard ("./*") or an added deep subpath would
    // silently re-open that capability boundary — this locks the allowlist against that regression.
    const pkg = JSON.parse(
      readFileSync(new URL("../package.json", import.meta.url), "utf8"),
    ) as {
      exports?: Record<string, unknown>;
    };
    const keys = Object.keys(pkg.exports ?? {}).sort();
    expect(keys).toEqual([".", "./package.json"]);
    for (const key of keys) {
      expect(
        key,
        "no wildcard subpath may be added to `exports`",
      ).not.toContain("*");
    }
  });

  it("the provider facade is unforgeable (null prototype, no recoverable constructor, no leaked internals)", () => {
    const { provider } = createProtectedAiProvider();
    // No prototype → no recoverable public constructor to `new` with a fake engine (finding 3).
    expect(Object.getPrototypeOf(provider)).toBeNull();
    expect(
      (provider as Record<string, unknown>)["constructor"],
    ).toBeUndefined();
    expect(Object.isFrozen(provider)).toBe(true);
    // Exposes ONLY the AiProvider interface methods.
    expect(Object.getOwnPropertyNames(provider).sort()).toEqual([
      "embedText",
      "generateStream",
      "generateText",
    ]);
    for (const leak of [
      "engine",
      "reversalStore",
      "reverser",
      "streamFactory",
      "policy",
      "options",
      "router",
      "audit",
      "invokeRaw",
      "safeTrace",
      "deps",
    ]) {
      expect(
        (provider as Record<string, unknown>)[leak],
        `facade must not leak ${leak}`,
      ).toBeUndefined();
    }
  });

  it("the engine facade is unforgeable (null prototype, only interface methods)", () => {
    const { engine } = createSubstitutionEngine();
    expect(Object.getPrototypeOf(engine)).toBeNull();
    expect((engine as Record<string, unknown>)["constructor"]).toBeUndefined();
    expect(Object.isFrozen(engine)).toBe(true);
    expect(Object.getOwnPropertyNames(engine).sort()).toEqual([
      "createReverseStream",
      "reverse",
      "substitute",
    ]);
    for (const leak of [
      "reversalStore",
      "reverser",
      "streamFactory",
      "assignmentStore",
      "coordinator",
      "truthReader",
      "policy",
      "grammar",
      "compiler",
      "cache",
      "escaper",
    ]) {
      expect(
        (engine as Record<string, unknown>)[leak],
        `facade must not leak ${leak}`,
      ).toBeUndefined();
    }
  });

  it("the boundary role policy is GENUINELY immutable (no mutators, no Set.prototype bypass)", () => {
    const roles = BOUNDARY_TOKEN_GRAMMAR_POLICY.allowedRoles as unknown as {
      has: (v: string) => boolean;
    } & Record<string, unknown>;
    expect(roles.has("Claimant")).toBe(true);
    expect(roles.has("Jordan Smith PHI role")).toBe(false);
    // No mutator method is exposed on the membership oracle.
    for (const mutator of ["add", "delete", "clear"]) {
      expect(
        roles[mutator],
        `role set must not expose ${mutator}`,
      ).toBeUndefined();
    }
    // And a stolen `Set.prototype.add` cannot operate on it — the oracle has no [[SetData]] slot.
    expect(() =>
      (Set.prototype.add as (this: unknown, v: unknown) => unknown).call(
        roles,
        "Jordan Smith PHI role",
      ),
    ).toThrow();
    expect(roles.has("Jordan Smith PHI role")).toBe(false);
    expect(Object.isFrozen(roles)).toBe(true);
  });

  it("the role allow-list is READ-poison-resistant (a replaced Set.prototype.has cannot admit a role)", () => {
    // GLY-336 R4 (killed-gate finding): R3 sealed the WRITE path (Set.prototype.add can't mutate the
    // frozen policy) but the security-critical membership READ must ALSO not route through the
    // globally-replaceable `Set.prototype.has`. A consumer that replaces it — even before this module
    // is imported — must not be able to make an unauthorized (PHI-bearing) role pass the allow-list and
    // be emitted as a token label. Membership is a null-prototype record read directly, so the poison
    // is inert. Mutation-proof: back `frozenRoleSet.has` with a live Set again and this test goes red.
    const roles = BOUNDARY_TOKEN_GRAMMAR_POLICY.allowedRoles as unknown as {
      has: (v: string) => boolean;
    };
    const originalHas = Set.prototype.has;
    try {
      // Most aggressive poison: every Set membership check answers true.
      (
        Set.prototype as unknown as {
          has: (this: unknown, v: unknown) => boolean;
        }
      ).has = function (): boolean {
        return true;
      };
      // Sanity: the poison is genuinely live on a real Set.
      expect(new Set<string>().has("anything")).toBe(true);
      // The allow-list is unmoved: unauthorized role still rejected, authorized role still admitted.
      expect(roles.has("Jordan Smith PHI role")).toBe(false);
      expect(roles.has("Claimant")).toBe(true);
    } finally {
      (Set.prototype as unknown as { has: unknown }).has = originalHas;
    }
    // Poison fully restored — a real Set behaves normally again.
    expect(new Set<string>(["x"]).has("y")).toBe(false);
  });

  it("regression (#private): the concrete reversal store's raw map is NOT reflectively enumerable", async () => {
    const store = new InMemoryReversalStore() as unknown as {
      record: (input: unknown) => void;
      resolveEncounteredTokens: (
        input: unknown,
      ) => Promise<ReadonlyMap<string, string>>;
    };
    const CANARY = "Jordan Testcase — 987-65-4320";
    store.record({
      tenantId: "t-1",
      matterId: "m-1",
      dictionaryVersion: 1n,
      token: "[[Claimant]]",
      canonical: CANARY,
      attemptId: "a-1",
    });
    const resolved = await store.resolveEncounteredTokens({
      tenantId: "t-1",
      matterId: "m-1",
      dictionaryVersion: 1n,
      tokens: ["[[Claimant]]"],
    });
    expect(resolved.get("[[Claimant]]")).toBe(CANARY); // value IS stored (bounded read works)...

    const ownNames = Object.getOwnPropertyNames(store);
    const reflectKeys = Reflect.ownKeys(store).map((k) => String(k));
    for (const forbidden of ["canonicalByKey", "recordedAttempts"]) {
      expect(ownNames).not.toContain(forbidden);
      expect(reflectKeys).not.toContain(forbidden);
      expect(Object.keys(store)).not.toContain(forbidden);
    }
    expect(JSON.stringify(store) ?? "").not.toContain("Jordan Testcase"); // ...but never reflectable
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
    expect(tokenized).toMatch(/\[\[Claimant/);
    expect(tokenized).not.toContain(DEV_NAME);

    expect(() => result.reversalHandle.toJSON()).toThrow(); // non-serializable capability

    const display = await dev.engine.reverse(
      result.segments[0]!.text,
      result.reversalHandle,
    );
    expect(String(display)).toContain(DEV_NAME);
  });

  it("createProtectedAiProvider() round-trips generateText through the protected binding", async () => {
    const dev = createProtectedAiProvider();
    const options: BoundaryGenerateOptions = {
      messages: [
        {
          role: "user",
          content: [{ type: "text", text: `Please contact ${DEV_NAME}.` }],
        },
      ],
    };
    const display = await dev.provider.generateText(options);
    expect(String(display)).toContain(DEV_NAME);
    expect(String(display)).not.toContain("[[Claimant");
  });
});
