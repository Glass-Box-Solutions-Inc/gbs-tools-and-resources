/**
 * GLY-373 — OR-GLY373-14: historically aliased rows are unreachable through EVERY public entry
 * point, and the guard that makes that true leaks nothing through any of three layered controls.
 *
 * FILE PLACEMENT, FLAGGED: §6 names `tests/namespaced-grammar.test.ts` for OR-14. It lives here
 * instead purely for reviewability — OR-14 is three controls, a walker self-test, an AST check and
 * five entry-point row groups, and folding it into an already-900-line file would bury it. Every
 * spec-named oracle id is preserved verbatim in the test titles; no coverage differs.
 *
 * The three controls and what each does NOT cover (§3.2.4, stated rather than papered over):
 *   1. SHAPE (f) — the thrown object's own property graph, `stack` content, `safeDetails`
 *      mutability. Does NOT cover anything unreachable from the object.
 *   2. WALK (g) — nested/inherited values, `cause` chains, accessors, symbol keys. Does NOT cover
 *      opaque containers (`WeakMap`/`WeakRef`), method-mediated values, or `Proxy` traps.
 *   3. STATIC SOURCE (h) — module-level side channels no runtime inspection of the object can
 *      reach. Does NOT cover code above the engine boundary.
 * No single control is sufficient; control 3 exists precisely because 1 and 2 are object-level and
 * the `WeakMap` channel is not. MUT-29(a) is killed by (h) and by nothing else.
 */
import { describe, expect, it } from "vitest";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import ts from "typescript";
import { createSubstitutionEngine } from "../src/index";
import { isPhiEngineError } from "../src/core/errors";
import { InMemoryReversalStore } from "../src/tokens/reversal";
import {
  assertGuardErrorShape,
  assertWalkerSelfTest,
  walkForCanaries,
} from "./canary-walker";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = resolve(HERE, "../src");

const NUL = "\u0000";
const CANARY_CANONICAL = "GLY373-CANARY-SEEDED-CANONICAL";
/** A DISTINCT canary per id field, so a hit names the field that leaked. */
const CANARIES = {
  tenantId: "GLY373-CANARY-TENANT",
  matterId: "GLY373-CANARY-MATTER",
  operationId: "GLY373-CANARY-OP",
  attemptId: "GLY373-CANARY-ATTEMPT",
} as const;
const ALL_CANARIES = [...Object.values(CANARIES), CANARY_CANONICAL];

function branded<T>(value: unknown): T {
  return value as T;
}

/**
 * A FORGED STRUCTURAL handle — a plain object literal, NOT an engine-minted
 * `InProcessReversalHandle`. `ReversalHandle` is a structural interface, both reversal methods
 * accept it, and the sealed facade forwards it unvalidated, so nothing requires the handle to be
 * the one the engine minted. This is the exact reachability the revision-3 unreachability proof
 * wrongly claimed was impossible.
 */
function forgedHandle(
  overrides: Partial<Record<string, unknown>> = {},
): unknown {
  return {
    tenantId: `${CANARIES.tenantId}${NUL}x`,
    matterId: CANARIES.matterId,
    operationId: CANARIES.operationId,
    attemptId: CANARIES.attemptId,
    dictionaryVersion: 1n,
    toJSON: (): never => {
      throw new Error("handle_not_serializable");
    },
    ...overrides,
  };
}

function devEngine(
  overrides: Record<string, unknown> = {},
): ReturnType<typeof createSubstitutionEngine> {
  return createSubstitutionEngine(
    branded({
      taggedValues: [],
      reversalStore: new InMemoryReversalStore(),
      ...overrides,
    }),
  );
}

// =============================================================================================
describe("GLY-373 OR-GLY373-14 — layered guard controls", () => {
  it("GLY373-OR-14(g) self-test: the canary walker detects every channel it claims to cover", () => {
    // MANDATORY, and it runs FIRST. Without it, a broken walker makes every downstream assertion
    // pass VACUOUSLY — "did not look" would read as "found nothing".
    assertWalkerSelfTest();
  });

  it("GLY373-OR-14(a): substitute rejects both members of the NUL aliasing pair at ingestion, before any store read", async () => {
    for (const [why, context] of [
      ["left", { tenantId: "a", matterId: `b${NUL}c` }],
      ["right", { tenantId: `a${NUL}b`, matterId: "c" }],
    ] as const) {
      let reads = 0;
      const store = new InMemoryReversalStore();
      const counting = {
        maximumEncounteredTokenBatch: 256,
        record: (input: unknown): void => {
          reads += 1;
          store.record(branded(input));
        },
        resolveEncounteredTokens: (input: unknown) => {
          reads += 1;
          return store.resolveEncounteredTokens(branded(input));
        },
      };
      const dev = devEngine({ ...context, reversalStore: counting });
      let caught: unknown;
      try {
        await dev.engine.substitute(
          branded({
            context: { ...dev.context, ...context },
            policy: {
              ...dev.policy,
              detectorRequirement: "DETERMINISTIC_STRUCTURED_ONLY",
            },
            segments: [{ path: "p", kind: "user", text: "SSN 123-45-6789." }],
            purpose: "generation",
          }),
        );
      } catch (error) {
        caught = error;
      }
      expect(isPhiEngineError(caught), why).toBe(true);
      expect((caught as { code: string }).code, why).toBe(
        "MISSING_TRUSTED_CONTEXT",
      );
      // BEFORE any store read — ordering is the whole guarantee (MUT-23).
      expect(reads, why).toBe(0);
    }
  });

  it("GLY373-OR-14(b): reverse() fails closed on a forged NUL-bearing handle and never queries the store", async () => {
    for (const [why, handle] of [
      ["NUL-bearing tenantId", forgedHandle()],
      // (c-wf) A LONE SURROGATE rather than a NUL. This row exists because NUL fixtures alone leave
      // a well-formedness-only mutant (MUT-34) alive on the reversal paths, and that mutant is
      // security-relevant: executed evidence shows `tenant\uD800` and `tenant�` produce
      // DISTINCT JavaScript mapping keys but IDENTICAL `b64url-v1:` durable keys — the exact
      // §3.2.1 aliasing, reachable through paths 2 and 3 while every other oracle passes.
      [
        "lone-surrogate tenantId",
        forgedHandle({ tenantId: `${CANARIES.tenantId}\uD800` }),
      ],
      // The SSN-SHAPED operationId row. The existing slug filter `SAFE_OPERATION_ID` ADMITS
      // `123-45-6789`, so a guard reusing that path's id handling would turn the fail-closed
      // branch itself into a PHI-egress route. MUT-27 is killed here.
      ["SSN-shaped operationId", forgedHandle({ operationId: "123-45-6789" })],
    ] as const) {
      let queried = 0;
      const store = new InMemoryReversalStore();
      // Seed the historically aliased row DIRECTLY, bypassing ingestion — which is the ONLY way
      // such a row can exist now that all three entry points reject its ids.
      store.record(
        branded({
          tenantId: "a",
          matterId: `b${NUL}c`,
          dictionaryVersion: 1n,
          token: "[[Claimant]]",
          canonical: CANARY_CANONICAL,
        }),
      );
      const dev = devEngine({
        reversalStore: {
          maximumEncounteredTokenBatch: 256,
          record: (input: unknown) => store.record(branded(input)),
          resolveEncounteredTokens: (input: unknown) => {
            queried += 1;
            return store.resolveEncounteredTokens(branded(input));
          },
        },
      });

      let caught: unknown;
      let result: unknown;
      try {
        result = await dev.engine.reverse(
          branded("[[Claimant]]"),
          branded(handle),
        );
      } catch (error) {
        caught = error;
      }
      expect(result, why).toBeUndefined();
      expect(isPhiEngineError(caught), why).toBe(true);
      // The store was NOT queried for that key.
      expect(queried, why).toBe(0);

      // Control 1 — SHAPE, on the value ACTUALLY CAUGHT.
      assertGuardErrorShape(caught, {
        code: "MISSING_TRUSTED_CONTEXT",
        operationId: "op-unbound",
        safeDetailKeys: [],
        canaries: [...ALL_CANARIES, "123-45-6789"],
      });
      // Control 2 — WALK, on the same object. Listing only `message`/`Object.keys`/
      // `getOwnPropertyNames`/`Reflect.ownKeys`/`JSON.stringify` would be INSUFFICIENT: a guard
      // attaching `cause: new Error("123-45-6789")` passes all five while echoing the value
      // verbatim, because `cause` is own NON-ENUMERABLE.
      expect(
        walkForCanaries(caught, [...ALL_CANARIES, "123-45-6789"]),
        why,
      ).toEqual([]);
    }
  });

  it("GLY373-OR-14(c): createReverseStream THROWS SYNCHRONOUSLY at construction on a forged handle", async () => {
    for (const [why, handle] of [
      ["NUL-bearing tenantId", forgedHandle()],
      // (c-wf) again, on path 3 — MUT-34's second application.
      [
        "lone-surrogate tenantId",
        forgedHandle({ tenantId: `${CANARIES.tenantId}\uD800` }),
      ],
      ["SSN-shaped operationId", forgedHandle({ operationId: "123-45-6789" })],
    ] as const) {
      let sinkCalls = 0;
      const sinkSeen: string[] = [];
      const dev = devEngine();

      let caught: unknown;
      let stream: unknown;
      try {
        stream = dev.engine.createReverseStream(branded(handle), (safe) => {
          sinkCalls += 1;
          sinkSeen.push(String(safe));
        });
      } catch (error) {
        caught = error;
      }

      // NO `ReverseStream` object is returned, and no `push`/`end` is ever called. Failing later at
      // `push` or `end` is NOT acceptable and MUST fail this oracle (MUT-25): by then the
      // `ReversalKeys` have been built from unvalidated input, and text containing no mapped tokens
      // can complete successfully over a garbage key.
      expect(stream, why).toBeUndefined();
      expect(sinkCalls, why).toBe(0);
      expect(sinkSeen, why).toEqual([]);
      assertGuardErrorShape(caught, {
        code: "MISSING_TRUSTED_CONTEXT",
        operationId: "op-unbound",
        safeDetailKeys: [],
        canaries: [...ALL_CANARIES, "123-45-6789"],
      });
      expect(
        walkForCanaries(caught, [...ALL_CANARIES, "123-45-6789"]),
        why,
      ).toEqual([]);
    }
  });

  it("GLY373-OR-14(c) regression: path 3 validates the RAW operationId and the version, and the rejected value never reaches a regex", () => {
    // THESE ROWS EXIST BECAUSE THEIR ABSENCE HID A REAL DEFECT, found by the cross-family gate.
    //
    // The earlier guard validated the SLUG-FILTERED operation id rather than the RAW one, which was
    // wrong twice over. First, `safeHandleOperationId` maps a non-slug value to the fixed
    // `op-unknown` placeholder, so a NUL-bearing or lone-surrogate operation id was silently
    // NORMALISED AND ACCEPTED instead of rejected — the guard's own output was what got validated.
    // Second, the slug filter is `SAFE_OPERATION_ID.test(rawId)`, so the REGEX RAN ON THE REJECTED
    // VALUE FIRST, parking the entire subject string in the legacy globals `RegExp.input` /
    // `RegExp.$_`. That is a process-global slot NO oracle on the thrown error can see, and it is
    // precisely the MUT-33(c) leak the own-property scan exists to avoid.
    //
    // Every fixture here carries a WELL-FORMED tenant and matter, so only the field under test can
    // cause the rejection. That is the mistake the original rows made: they defaulted to an
    // already-invalid tenant, so the tenant check short-circuited every row and the operation-id
    // and version paths were never actually exercised.
    const dev = devEngine();
    const wellFormedBase = {
      tenantId: "t-ok",
      matterId: "m-ok",
      dictionaryVersion: 1n,
      attemptId: "att-ok",
      toJSON: (): never => {
        throw new Error("handle_not_serializable");
      },
    };

    for (const [why, overrides] of [
      ["NUL-bearing operationId", { operationId: `op${NUL}x` }],
      ["lone-surrogate operationId", { operationId: "op\uD800" }],
      ["lone low-surrogate operationId", { operationId: "op\uDC00" }],
      ["non-string operationId", { operationId: 42 }],
      ["missing operationId", { operationId: undefined }],
      // `dictionaryVersion` is a branded BIGINT whose `toString` is invoked during key
      // derivation, so a non-bigint carrier is a raw-throw route. The baseline CAST it with no
      // validation at all, and so did the first version of this guard.
      ["undefined dictionaryVersion", { dictionaryVersion: undefined }],
      ["string dictionaryVersion", { dictionaryVersion: "1" }],
      [
        "object dictionaryVersion with a throwing toString",
        {
          dictionaryVersion: {
            toString: (): never => {
              throw new Error("GLY373-CANARY-VERSION");
            },
          },
        },
      ],
    ] as const) {
      let stream: unknown;
      let caught: unknown;
      try {
        stream = dev.engine.createReverseStream(
          branded({ ...wellFormedBase, ...overrides }),
          () => undefined,
        );
      } catch (error) {
        caught = error;
      }
      expect(stream, why).toBeUndefined();
      expect(isPhiEngineError(caught), why).toBe(true);
      expect((caught as { code: string }).code, why).toBe(
        "MISSING_TRUSTED_CONTEXT",
      );
    }

    // THE REGEX SIDE CHANNEL, asserted directly. An SSN-shaped operation id is admitted by
    // `SAFE_OPERATION_ID`, so if the slug filter runs BEFORE the scan, the whole subject is left in
    // `RegExp.input` where no error-object oracle can reach it. Clear the globals with a match on a
    // known-innocuous subject first, so the assertion cannot pass on a stale value.
    /GLY373-REGEXP-RESET/.test("GLY373-REGEXP-RESET");
    let rejected: unknown;
    try {
      dev.engine.createReverseStream(
        branded({
          ...wellFormedBase,
          tenantId: `t${NUL}bad`,
          operationId: "123-45-6789",
        }),
        () => undefined,
      );
    } catch (error) {
      rejected = error;
    }
    expect(isPhiEngineError(rejected)).toBe(true);
    const regexGlobals = RegExp as unknown as Record<string, unknown>;
    expect(String(regexGlobals["input"] ?? "")).not.toContain("123-45-6789");
    expect(String(regexGlobals["$_"] ?? "")).not.toContain("123-45-6789");
  });

  it("GLY373-OR-14(d): a genuine U+FFFD row IS reachable and DOES resolve — the boundary, not over-claimed", async () => {
    // The guarantee covers EXCESS-NUL rows only. A key derived from LEGITIMATE U+FFFD content is
    // reachable through its own well-formed context and resolves normally — which is exactly why
    // Query 2 is a NON-BLOCKING reporting obligation rather than a release gate, and why no row may
    // be deleted or rewritten on that evidence.
    const store = new InMemoryReversalStore();
    const dev = devEngine({
      tenantId: "t-fffd",
      matterId: "m�fffd",
      reversalStore: store,
    });
    const substituted = await dev.engine.substitute(
      branded({
        context: dev.context,
        policy: {
          ...dev.policy,
          detectorRequirement: "DETERMINISTIC_STRUCTURED_ONLY",
        },
        segments: [{ path: "p", kind: "user", text: "SSN 123-45-6789." }],
        purpose: "generation",
      }),
    );
    const text = String(substituted.segments[0]!.text);
    expect(text).not.toContain("123-45-6789");

    // Through `reverse()` ...
    expect(
      String(
        await dev.engine.reverse(branded(text), substituted.reversalHandle),
      ),
    ).toBe("SSN 123-45-6789.");

    // ... and through `createReverseStream()`.
    const chunks: string[] = [];
    const stream = dev.engine.createReverseStream(
      substituted.reversalHandle,
      (safe) => {
        chunks.push(String(safe));
      },
    );
    await stream.push(branded(text));
    await stream.end();
    expect(chunks.join("")).toBe("SSN 123-45-6789.");
  });

  it("GLY373-OR-14(i): each routing field is read EXACTLY ONCE, on success as well as on rejection", async () => {
    // A re-read on the HAPPY path is the same defect (MUT-30), and a validate-then-snapshot
    // ordering (MUT-31) lets read 2's value reach the key. If the count is 2 the oracle fails
    // REGARDLESS of the outcome: a passing result reached by reading twice is not evidence of
    // correctness, it is the defect with a lucky ordering.
    const countingHandle = (
      counts: Record<string, number>,
      values: Record<string, readonly unknown[]>,
    ): unknown => {
      const handle: Record<string, unknown> = {
        attemptId: CANARIES.attemptId,
        toJSON: (): never => {
          throw new Error("handle_not_serializable");
        },
      };
      // `dictionaryVersion` IS INSTRUMENTED TOO. It is a routing field that participates in the
      // mapping key, so leaving it as a plain data property put it outside the exact-once oracle
      // entirely — the same omission that let the `operationId` double-read hide.
      for (const field of [
        "tenantId",
        "matterId",
        "operationId",
        "dictionaryVersion",
      ] as const) {
        Object.defineProperty(handle, field, {
          enumerable: true,
          get(): unknown {
            counts[field] = (counts[field] ?? 0) + 1;
            const sequence = values[field] ?? [1n];
            return sequence[Math.min(counts[field]! - 1, sequence.length - 1)];
          },
        });
      }
      return handle;
    };

    // --- SUCCESS path, path 2: every field read exactly once ---
    {
      const store = new InMemoryReversalStore();
      const dev = devEngine({ reversalStore: store });
      store.record(
        branded({
          tenantId: "t-once",
          matterId: "m-once",
          dictionaryVersion: 1n,
          token: "[[Claimant]]",
          canonical: "Avery Alpha",
        }),
      );
      const counts: Record<string, number> = {};
      const handle = countingHandle(counts, {
        tenantId: ["t-once"],
        matterId: ["m-once"],
        operationId: ["op-once"],
      });
      const reversed = String(
        await dev.engine.reverse(branded("[[Claimant]]"), branded(handle)),
      );
      expect(reversed).toBe("Avery Alpha");
      expect(counts.tenantId).toBe(1);
      expect(counts.matterId).toBe(1);
      expect(counts.operationId).toBe(1);
    }

    // --- TOCTOU vector: well-formed on read 1, NUL-bearing on read 2 ---
    {
      const store = new InMemoryReversalStore();
      const dev = devEngine({ reversalStore: store });
      store.record(
        branded({
          tenantId: "t-toctou",
          matterId: "m-toctou",
          dictionaryVersion: 1n,
          token: "[[Claimant]]",
          canonical: "Avery Alpha",
        }),
      );
      const counts: Record<string, number> = {};
      const handle = countingHandle(counts, {
        // Read 1 is well-formed; every later read is NUL-bearing.
        tenantId: ["t-toctou", `t${NUL}toctou`],
        matterId: ["m-toctou"],
        operationId: ["op-toctou"],
      });
      // The call MUST SUCCEED USING READ 1'S VALUE, and the read count MUST stay 1.
      const reversed = String(
        await dev.engine.reverse(branded("[[Claimant]]"), branded(handle)),
      );
      expect(reversed).toBe("Avery Alpha");
      expect(counts.tenantId).toBe(1);
      // The derived key carried read 1's bytes, never read 2's — proven by the lookup HITTING the
      // row seeded under read 1's tenant.
    }

    // --- SUCCESS path, path 3 (createReverseStream) ---
    {
      const store = new InMemoryReversalStore();
      const dev = devEngine({ reversalStore: store });
      store.record(
        branded({
          tenantId: "t-stream",
          matterId: "m-stream",
          dictionaryVersion: 1n,
          token: "[[Claimant]]",
          canonical: "Avery Alpha",
        }),
      );
      const counts: Record<string, number> = {};
      const handle = countingHandle(counts, {
        tenantId: ["t-stream"],
        matterId: ["m-stream"],
        operationId: ["op-stream"],
      });
      const chunks: string[] = [];
      const stream = dev.engine.createReverseStream(branded(handle), (safe) => {
        chunks.push(String(safe));
      });
      await stream.push(branded("[[Claimant]]"));
      await stream.end();
      expect(chunks.join("")).toBe("Avery Alpha");
      expect(counts.tenantId).toBe(1);
      expect(counts.matterId).toBe(1);
      // `operationId` WAS MISSING FROM THIS LIST, and its absence hid a real defect. Path 3
      // validated a snapshot and then called `safeHandleOperationId(input.handle)`, which read the
      // property a SECOND time — so the exact-once oracle passed while the field was read twice.
      // A field omitted from an "exactly once" oracle is not covered by it.
      expect(counts.operationId).toBe(1);
      expect(counts.dictionaryVersion).toBe(1);
    }
  });

  // -------------------------------------------------------------------------------------------
  it("GLY373-OR-14(i) regression: a path-3 operationId getter cannot switch values between validation and use", async () => {
    // THIS ROW EXISTS BECAUSE ITS ABSENCE HID A REAL DEFECT, found by the cross-family gate.
    //
    // The TOCTOU shape the count alone does not express: read 1 returns a benign slug and passes
    // both the §3.2.2 scan and the slug regex; read 2 returns PHI and is what actually gets used —
    // and the slug regex, applied to it, parks the whole subject in `RegExp.input` / `RegExp.$_`.
    // Executed against the pre-fix code at the public boundary:
    // `{"operationIdReads":2,"regexpInput":"123-45-6789","regexpDollarUnderscore":"123-45-6789"}`.
    const dev = devEngine();
    let reads = 0;
    const handle = {
      tenantId: "t-toctou",
      matterId: "m-toctou",
      dictionaryVersion: 1n,
      attemptId: "att-toctou",
      get operationId(): string {
        reads += 1;
        return reads === 1 ? "op-benign" : "123-45-6789";
      },
      toJSON: (): never => {
        throw new Error("handle_not_serializable");
      },
    };
    // Clear the legacy globals on a known-innocuous subject so the assertion cannot pass stale.
    /GLY373-REGEXP-RESET/.test("GLY373-REGEXP-RESET");
    let caught: unknown;
    try {
      dev.engine.createReverseStream(branded(handle), () => undefined);
    } catch (error) {
      caught = error;
    }
    // Exactly ONE read, so the second value is never even produced — the strongest available form
    // of the guarantee, and stronger than merely asserting the second value was not USED.
    expect(reads).toBe(1);
    expect(caught).toBeUndefined();
    const regexGlobals = RegExp as unknown as Record<string, unknown>;
    expect(String(regexGlobals["input"] ?? "")).not.toContain("123-45-6789");
    expect(String(regexGlobals["$_"] ?? "")).not.toContain("123-45-6789");
  });

  // -------------------------------------------------------------------------------------------
  it("GLY373-OR-14(e): the per-symbol derivation-site pin matches the spec expectation exactly", () => {
    // EXACT COUNT AND EXACT FILE per symbol. Asserting only the SET OF FILES is insufficient and
    // fails this oracle: a second unvalidated `mappingKeyOf` call inside the SAME file leaves the
    // file set unchanged and MUT-26 would survive.
    //
    // THE COUNTS ARE A TRIPWIRE FOR THE THREE KNOWN ROUTES, NOT A PROOF OF COMPLETENESS, and the
    // spec says so: `tokens/reversal.ts` already derives and consumes mapping keys DIRECTLY through
    // its private `#key`, with no pinned symbol involved, so a new direct join or a renamed helper
    // is invisible to this count. The completeness obligation is discharged by INSPECTION and
    // recorded in the build ledger; this test is the mechanical half.
    const pins: readonly [string, number, readonly string[]][] = [
      ["idempotencyKeyOf", 1, ["src/tokens/durable/durable-reversal-store.ts"]],
      ["mappingKeyOf", 2, ["src/tokens/durable/durable-reversal-store.ts"]],
      ["resolveEncounteredTokens", 1, ["src/tokens/reversal.ts"]],
    ];

    const files = collectSourceFiles(SRC);
    for (const [symbol, expectedCount, expectedFiles] of pins) {
      const sites = callSitesOf(files, symbol);
      expect(sites.length, `${symbol} call-site count`).toBe(expectedCount);
      expect(
        [...new Set(sites.map((s) => s.file))].sort(),
        `${symbol} call-site files`,
      ).toEqual([...expectedFiles].sort());
    }
  });

  // -------------------------------------------------------------------------------------------
  it("GLY373-OR-14(h): the static guard-source oracle — data flow, token ban, and closure", () => {
    // CONTROL 3. Controls (f) and (g) inspect the thrown OBJECT; neither can see a module-level
    // side channel, because a `WeakMap` keyed by the error lives in the GUARD MODULE, not on the
    // error. This is the only thing that kills MUT-29(a), and the recursive analysis of the pinned
    // helper is the only thing that kills MUT-32.
    //
    // COMMENTS ARE NOT CODE and this check IGNORES THEM. That is why it is an AST check and not a
    // regex: the only occurrences of banned tokens in the pinned files are in PROSE COMMENTS
    // (`Proxy` at `core/errors.ts` and `core/orchestrator.ts`, `Symbol.toPrimitive` at
    // `core/orchestrator.ts`), and a regex implementation flags all of them and tempts an
    // implementer to DELETE ACCURATE SECURITY COMMENTARY to green a gate.
    const errorsPath = resolve(SRC, "core/errors.ts");
    const source = parse(errorsPath);

    // --- ZERO-OR-ONE pinned helper, named EXACTLY, in EXACTLY this module (allow-list item C) ---
    const helper = findFunction(source, "assertTrustedContextIdShape");
    expect(
      helper,
      "the pinned helper must be assertTrustedContextIdShape in core/errors.ts",
    ).toBeDefined();

    const valueParam = helper!.parameters[1]!.name.getText(source);
    expect(valueParam).toBe("value");

    // --- Assertion 2: TOKEN BAN inside the guard body (identifiers/property names only) ---
    const BANNED = [
      "WeakMap",
      "WeakRef",
      "WeakSet",
      "Proxy",
      "Reflect",
      "toJSON",
      "globalThis",
      "process",
      "console",
      "require",
    ];
    const identifiers = collectIdentifiers(helper!, source);
    for (const banned of BANNED) {
      expect(identifiers, `banned token ${banned} in guard body`).not.toContain(
        banned,
      );
    }
    expect(identifiers).not.toContain("toPrimitive");
    // No dynamic import.
    expect(
      hasNode(helper!, (node) => node.kind === ts.SyntaxKind.ImportKeyword),
      "dynamic import in guard body",
    ).toBe(false);

    // --- Assertion 1: DATA FLOW. The rejected value may be READ by own-property index/`length`
    //     and COMPARED against fixed literals (allow-list B) — and NOTHING ELSE. Specifically it
    //     is never an argument to any call, never a template-literal substitution, never a
    //     property write, and never inserted into a collection. MUT-33 reverts to a prototype
    //     method (`includes`/`isWellFormed`/`RegExp.test`) and is killed exactly here.
    const violations: string[] = [];
    const visit = (node: ts.Node): void => {
      if (ts.isCallExpression(node)) {
        for (const argument of node.arguments) {
          if (mentions(argument, valueParam, source)) {
            violations.push(
              `value passed as an argument: ${node.getText(source).slice(0, 80)}`,
            );
          }
        }
        // A METHOD CALL ON the value is equally forbidden: `RegExp.prototype.test` parks the whole
        // subject in the global `RegExp.input`/`RegExp.$_` slots, and every `String.prototype`
        // method is prototype-poisonable and can be made to retain a caller-controlled value —
        // executed: `LEAKED_BY_POISONED_PROTOTYPE=includes,indexOf,isWellFormed,charCodeAt,
        // codePointAt,RegExp.test`. Indexed reads and `.length` resolve as OWN properties of the
        // String exotic object and cannot be diverted, which is why they are the permitted form.
        if (
          ts.isPropertyAccessExpression(node.expression) &&
          mentions(node.expression.expression, valueParam, source)
        ) {
          violations.push(
            `prototype method invoked on the value: ${node.getText(source).slice(0, 80)}`,
          );
        }
      }
      if (ts.isTemplateExpression(node) && mentions(node, valueParam, source)) {
        violations.push("value interpolated into a template literal");
      }
      if (
        ts.isBinaryExpression(node) &&
        node.operatorToken.kind === ts.SyntaxKind.EqualsToken &&
        mentions(node.right, valueParam, source)
      ) {
        violations.push("value assigned to a property or variable");
      }
      ts.forEachChild(node, visit);
    };
    ts.forEachChild(helper!, visit);
    expect(violations).toEqual([]);

    // Only permitted property accesses on the value: the own `length`, and indexed element access.
    const accesses: string[] = [];
    ts.forEachChild(helper!, function scan(node: ts.Node): void {
      if (
        ts.isPropertyAccessExpression(node) &&
        node.expression.getText(source) === valueParam
      ) {
        accesses.push(node.name.getText(source));
      }
      ts.forEachChild(node, scan);
    });
    expect([...new Set(accesses)]).toEqual(["length"]);

    // --- Assertion 3: CLOSURE. The helper closes over nothing but fixed literals declared in this
    //     module, and stores nothing. Every free identifier it uses must resolve to a module-level
    //     `const` initialised with a literal, or to the pinned error factory.
    const ALLOWED_FREE = new Set([
      "NUL_UNIT",
      "HIGH_SURROGATE_FIRST",
      "HIGH_SURROGATE_LAST",
      "LOW_SURROGATE_FIRST",
      "LOW_SURROGATE_LAST",
      "missingTrustedContextError",
      "fieldName",
      "value",
      "length",
      "unit",
      "next",
      "i",
      "string",
      "void",
    ]);
    for (const identifier of identifiers) {
      expect(
        ALLOWED_FREE.has(identifier),
        `unexpected identifier in guard body: ${identifier}`,
      ).toBe(true);
    }

    // --- RECURSIVE ANALYSIS of the one permitted callee (allow-list item C). Its body may use only
    //     A and B, so it can neither store the value nor pass it on. MUT-32 gives it a module-level
    //     `WeakMap`/array that records what it was asked to validate; the token ban above and the
    //     data-flow rule here are what catch that. The recursion terminates at depth one BY THE
    //     A-B RESTRICTION, which is the whole reason to name the helper rather than allow any.
    const factory = findFunction(source, "missingTrustedContextError");
    expect(factory).toBeDefined();
    expect(factory!.parameters.length, "the factory takes NO arguments").toBe(
      0,
    );
    const factoryIdentifiers = collectIdentifiers(factory!, source);
    for (const banned of BANNED) {
      expect(
        factoryIdentifiers,
        `banned token ${banned} in the error factory`,
      ).not.toContain(banned);
    }

    // --- No SECOND validation helper exists. Zero-or-one, never more.
    const helperLike = source.statements.filter(
      (statement) =>
        ts.isFunctionDeclaration(statement) &&
        /assert.*ContextId|validate.*ContextId/i.test(
          statement.name?.getText(source) ?? "",
        ),
    );
    expect(helperLike).toHaveLength(1);

    // --- The pinned guard SITES pass the snapshot local ONLY to the pinned helper.
    for (const relative of [
      "core/orchestrator.ts",
      "tokens/reverse-stream.ts",
    ]) {
      const guardSource = parse(resolve(SRC, relative));
      const calls = collectIdentifiers(guardSource, guardSource);
      expect(
        calls.includes("assertTrustedContextIdShape"),
        `${relative} must use the pinned helper`,
      ).toBe(true);
    }

    // --- A FOURTH guard site would be a spec delta. Pin the set to exactly three modules.
    const guardModules = collectSourceFiles(SRC).filter((file) =>
      readFileSync(file, "utf8").includes("assertTrustedContextIdShape("),
    );
    expect(guardModules.map((f) => f.slice(SRC.length + 1)).sort()).toEqual(
      [
        "core/errors.ts",
        "core/orchestrator.ts",
        "tokens/reverse-stream.ts",
      ].sort(),
    );
  });
});

// ============================================================================================
// Minimal AST helpers. `typescript` is already a devDependency, so no new tool is introduced.
// ============================================================================================

function parse(path: string): ts.SourceFile {
  return ts.createSourceFile(
    path,
    readFileSync(path, "utf8"),
    ts.ScriptTarget.ES2022,
    true,
  );
}

function collectSourceFiles(root: string): string[] {
  const out: string[] = [];
  const walk = (directory: string): void => {
    for (const entry of readdirSync(directory)) {
      const full = resolve(directory, entry);
      if (statSync(full).isDirectory()) walk(full);
      else if (full.endsWith(".ts")) out.push(full);
    }
  };
  walk(root);
  return out.sort();
}

function findFunction(
  source: ts.SourceFile,
  name: string,
): ts.FunctionDeclaration | undefined {
  return source.statements.find(
    (statement): statement is ts.FunctionDeclaration =>
      ts.isFunctionDeclaration(statement) &&
      statement.name?.getText(source) === name,
  );
}

function collectIdentifiers(node: ts.Node, source: ts.SourceFile): string[] {
  const names = new Set<string>();
  // A function declaration's OWN NAME is a child identifier; it is the declaration, not a free
  // reference, so counting it would make every named function fail its own closure assertion.
  const ownName =
    ts.isFunctionDeclaration(node) && node.name !== undefined
      ? node.name
      : undefined;
  const visit = (current: ts.Node): void => {
    if (ts.isIdentifier(current) && current !== ownName) {
      names.add(current.getText(source));
    }
    ts.forEachChild(current, visit);
  };
  ts.forEachChild(node, visit);
  return [...names];
}

function hasNode(
  node: ts.Node,
  predicate: (node: ts.Node) => boolean,
): boolean {
  let found = false;
  const visit = (current: ts.Node): void => {
    if (found) return;
    if (predicate(current)) {
      found = true;
      return;
    }
    ts.forEachChild(current, visit);
  };
  ts.forEachChild(node, visit);
  return found;
}

function mentions(
  node: ts.Node,
  identifier: string,
  source: ts.SourceFile,
): boolean {
  if (ts.isIdentifier(node)) return node.getText(source) === identifier;
  return hasNode(
    node,
    (current) =>
      ts.isIdentifier(current) && current.getText(source) === identifier,
  );
}

interface CallSite {
  readonly file: string;
  readonly line: number;
}

/** Call EXPRESSIONS only — interface/implementation declarations are not derivations. */
function callSitesOf(files: readonly string[], symbol: string): CallSite[] {
  const sites: CallSite[] = [];
  for (const file of files) {
    const source = parse(file);
    const visit = (node: ts.Node): void => {
      if (ts.isCallExpression(node)) {
        const callee = node.expression;
        const name = ts.isPropertyAccessExpression(callee)
          ? callee.name.getText(source)
          : callee.getText(source);
        if (name === symbol) {
          sites.push({
            file: file.slice(SRC.length - 3),
            line:
              source.getLineAndCharacterOfPosition(node.getStart(source)).line +
              1,
          });
        }
      }
      ts.forEachChild(node, visit);
    };
    ts.forEachChild(source, visit);
  }
  return sites;
}
