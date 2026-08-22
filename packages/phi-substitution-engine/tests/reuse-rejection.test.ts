/**
 * GLY-373 — reuse-rejection and scrub-seam oracles OR-GLY373-15 and OR-GLY373-16.
 *
 * §3.2.5 closes a cross-value PHI disclosure reachable with entirely well-formed input: the
 * namespace derives only from the five context fields while `detectorOrdinal` resets per call, so
 * two `substitute()` calls sharing a context tuple mint the SAME token for DIFFERENT values, and
 * the baseline's keep-first behaviour silently returned the FIRST canonical when the SECOND value
 * was reversed. §3.2.6 is what makes the resulting disposition observable at all.
 */
import { describe, expect, it } from "vitest";
import {
  brand,
  makeHarness,
  twoMounts,
  recordInput,
  resolveInput,
  DEFAULT_TOKEN,
} from "./durable-harness";
import type { OperationAttemptId, SubstitutionToken } from "../src/core/brands";
import { InMemoryReversalStore } from "../src/tokens/reversal";
import {
  REVERSAL_CANONICAL_CONFLICT,
  REVERSAL_CANONICAL_CONFLICT_DETAIL,
} from "../src/tokens/conflict-sentinel";
import { ReversalFailedError } from "../src/tokens/errors";
import { PhiEngineError, isPhiEngineError } from "../src/core/errors";
import { createSubstitutionEngine } from "../src/index";
import { DurableReversalStore } from "../src/tokens/durable/durable-reversal-store";
import {
  InMemoryKeyProvider,
  InMemoryReversalSpoolBackend,
} from "../src/tokens/durable/index";
import { walkForCanaries, assertGuardErrorShape } from "./canary-walker";

const FIRST = "GLY373-CANARY-FIRST-CANONICAL";
const SECOND = "GLY373-CANARY-SECOND-CANONICAL";

function branded<T>(value: unknown): T {
  return value as T;
}

// ==============================================================================================
describe("GLY-373 §3.2.5 reuse rejection (OR-GLY373-15)", () => {
  it("GLY373-OR-15: repeated substitute() on one context tuple rejects a conflicting canonical without disclosing the first", async () => {
    // DRIVEN AT THE PUBLIC BOUNDARY. An earlier revision of this row called `store.record()`
    // directly, which is the wrong seam for this oracle twice over: it asserted the raw sentinel
    // instead of the CONSUMER-VISIBLE `AMBIGUOUS_KNOWN_IDENTIFIER` + `conflict` disposition, and it
    // never exercised the orchestrator path where the ordinal reset actually causes the collision.
    // §10.2's disclosure is reached through `substitute()`, so `substitute()` is what this row
    // must drive.
    //
    // (e) BOTH STORES — a divergence between them is a defect in itself, since consumers select a
    // store by deployment shape and would otherwise get different safety. Every row below runs
    // against both and the outcomes must be identical.
    for (const kind of ["durable", "in-memory"] as const) {
      const published: { token: string; canonical: string }[] = [];
      const inner =
        kind === "durable" ? makeHarness().store : new InMemoryReversalStore();
      // Records what the failed call actually published, so requirement 1 is asserted against
      // observed state rather than assumed token spellings.
      const store = new Proxy(inner as object, {
        get(target, property, receiver): unknown {
          const value = Reflect.get(target, property, receiver) as unknown;
          if (typeof value !== "function") return value;
          if (property === "record") {
            return (input: { token: string; canonical: string }): unknown => {
              published.push({
                token: input.token,
                canonical: input.canonical,
              });
              return (value as (i: unknown) => unknown).call(target, input);
            };
          }
          return (value as (...a: unknown[]) => unknown).bind(target);
        },
      });

      // The IDENTICAL context tuple for both calls — same tenant, matter, operation AND attempt.
      const shape = {
        // A tagged subject whose canonical appears ONLY in the second call's text. It therefore
        // mints an AUTHORITY token — which does NOT consume a detector ordinal — and is published
        // for the FIRST time inside the failing call. A detector identifier could not play this
        // role: the detector ordinal is a single per-call counter, so an extra identifier ahead of
        // the SSN shifts it from `SSN` to `SSN_2`, changing the key and dissolving the very
        // conflict this row exists to provoke (executed: `[[D~…~EMAIL]]` + `[[D~…~SSN_2]]`).
        taggedValues: branded([
          {
            field: {
              schemaPath: "claim.s-witness",
              substitution: true,
              identifierClass: branded("PERSON_NAME"),
              tokenRole: branded("Witness"),
              expander: branded("person-name"),
            },
            subjectId: branded("s-witness"),
            canonicalDisplayValue: "Wilma Witness",
            approvedAliases: [],
          },
        ]),
        reversalStore: branded(store),
        tenantId: "t-conflict",
        matterId: "m-conflict",
        operationId: "op-conflict",
        attemptId: "att-conflict",
      } as const;
      const call = async (
        engine: ReturnType<typeof createSubstitutionEngine>,
        text: string,
      ): Promise<unknown> =>
        engine.engine.substitute(
          branded({
            context: engine.context,
            policy: {
              ...engine.policy,
              detectorRequirement: "DETERMINISTIC_STRUCTURED_ONLY",
            },
            segments: [{ path: "p", kind: "user", text }],
            purpose: "generation",
          }),
        );

      // (a) FIRST call succeeds and mints the detector token for the first SSN.
      const one = createSubstitutionEngine(branded(shape));
      const first = (await call(one, `SSN 123-45-6789 for ${FIRST}.`)) as {
        segments: { text: string }[];
        reversalHandle: unknown;
      };
      const firstText = String(first.segments[0]!.text);
      expect(firstText, kind).not.toContain("123-45-6789");
      expect(firstText, kind).toMatch(/\[\[D~[0-9a-f]{16}~/);

      // (b) SECOND call, IDENTICAL context tuple — hence the same attemptId — with a DIFFERENT
      // first SSN. The detector ordinal resets per invocation, so the SAME token is minted for a
      // DIFFERENT canonical. It must fail closed with no result returned.
      // `Wilma Witness` appears ONLY here, so its mapping is genuinely published EARLIER IN THE
      // FAILING CALL — that is what requirement 1's per-mapping atomicity is about, and reusing an
      // identifier from call (a) would have made the row an idempotent replay instead.
      const two = createSubstitutionEngine(branded(shape));
      let caught: unknown;
      let returned: unknown = "NOT-SET";
      try {
        returned = await call(
          two,
          `Wilma Witness reports. SSN 987-65-4321 for ${SECOND}.`,
        );
      } catch (error) {
        caught = error;
      }
      expect(returned, kind).toBe("NOT-SET");
      expect(isPhiEngineError(caught), kind).toBe(true);
      expect((caught as PhiEngineError).code, kind).toBe(
        "AMBIGUOUS_KNOWN_IDENTIFIER",
      );
      expect((caught as PhiEngineError).safeDetails.conflict, kind).toBe(
        REVERSAL_CANONICAL_CONFLICT_DETAIL,
      );

      // (c) READ-AFTER-FAIL, through BOTH public reversal APIs. MUT-36 rejects only AFTER
      // persisting; the call still throws, so (b) alone stays green and ONLY this row catches it.
      const viaReverse = String(
        await one.engine.reverse(branded(firstText), first.reversalHandle),
      );
      expect(viaReverse, kind).toContain("123-45-6789");
      expect(viaReverse, kind).not.toContain("987-65-4321");

      let streamed = "";
      const stream = one.engine.createReverseStream(
        branded(first.reversalHandle),
        (chunk: unknown) => {
          streamed += String(chunk);
        },
      );
      await stream.push(branded(firstText));
      await stream.end();
      expect(streamed, kind).toContain("123-45-6789");
      expect(streamed, kind).not.toContain("987-65-4321");

      // Requirement 1, asserted POSITIVELY and BY READING THE STORE: the mapping published for a
      // different token earlier in the failed call is still present and still reverses to its own
      // canonical. "Permitted to persist" is not assertable — it also passes an implementation that
      // rolled the mapping back.
      const witness = published.find((r) => r.canonical === "Wilma Witness");
      expect(witness, kind).toBeDefined();
      const state = await (
        inner as unknown as {
          resolveEncounteredTokens: (
            i: unknown,
          ) => Promise<Map<string, string>>;
        }
      ).resolveEncounteredTokens(
        resolveInput({
          // The keys of THIS call, not the harness defaults — a defaulted lookup would miss the
          // row and report a false "rolled back".
          tenantId: brand(one.context.tenantId),
          matterId: brand(one.context.matterId),
          dictionaryVersion: one.dictionaryVersion,
          tokens: [brand<SubstitutionToken>(witness!.token)],
        }),
      );
      expect(state.get(witness!.token), kind).toBe("Wilma Witness");

      // (f) A NON-CONFLICTING replay — same tuple, SAME canonical — still succeeds idempotently,
      // so the fix is not over-broad.
      const three = createSubstitutionEngine(branded(shape));
      await expect(
        call(three, `SSN 123-45-6789 for ${FIRST}.`),
        kind,
      ).resolves.toBeDefined();

      // (h) CROSS-ATTEMPT UPDATE still works — the row that keeps the rule from being over-broad.
      // A FRESH attemptId with a different canonical MUST succeed and update the current mapping
      // (`contracts.ts:176-195`). If this row fails, the fix has broken legitimate authority-token
      // updates and MUST NOT SHIP.
      const fresh = createSubstitutionEngine(
        branded({ ...shape, attemptId: "att-fresh" }),
      );
      const updated = (await call(fresh, `SSN 987-65-4321 for ${SECOND}.`)) as {
        segments: { text: string }[];
        reversalHandle: unknown;
      };
      expect(
        String(
          await fresh.engine.reverse(
            branded(String(updated.segments[0]!.text)),
            updated.reversalHandle,
          ),
        ),
        kind,
      ).toContain("987-65-4321");
    }
  });

  it("GLY373-OR-15(d): the conflict error carries no canonical, value, or excerpt", async () => {
    // Driven end-to-end so the assertions run on the value ACTUALLY CAUGHT at the public call
    // site — never on a locally constructed instance, which would prove nothing about what the
    // engine threw.
    const store = new InMemoryReversalStore();
    const shape = {
      taggedValues: [],
      reversalStore: store,
      tenantId: "t-conflict",
      matterId: "m-conflict",
      operationId: "op-conflict",
      attemptId: "att-conflict",
    } as const;

    const one = createSubstitutionEngine(branded(shape));
    await one.engine.substitute(
      branded({
        context: one.context,
        policy: {
          ...one.policy,
          detectorRequirement: "DETERMINISTIC_STRUCTURED_ONLY",
        },
        segments: [
          { path: "p", kind: "user", text: `SSN 123-45-6789 for ${FIRST}.` },
        ],
        purpose: "generation",
      }),
    );

    // A SECOND call under the IDENTICAL context tuple with a DIFFERENT identifier value. The
    // ordinal resets per invocation, so the same token is minted for a different canonical.
    const two = createSubstitutionEngine(branded(shape));
    let caught: unknown;
    try {
      await two.engine.substitute(
        branded({
          context: two.context,
          policy: {
            ...two.policy,
            detectorRequirement: "DETERMINISTIC_STRUCTURED_ONLY",
          },
          segments: [
            { path: "p", kind: "user", text: `SSN 987-65-4321 for ${SECOND}.` },
          ],
          purpose: "generation",
        }),
      );
    } catch (error) {
      caught = error;
    }

    // Both PHI-scrub seams passed exactly this disposition through and converted nothing else.
    expect(isPhiEngineError(caught)).toBe(true);
    const err = caught as PhiEngineError;
    expect(err.code).toBe("AMBIGUOUS_KNOWN_IDENTIFIER");
    expect(err.safeDetails.conflict).toBe(REVERSAL_CANONICAL_CONFLICT_DETAIL);

    // OR-14(f) PARAMETERISED per §3.2.5 requirement 3: the same structural rows, but with this
    // path's code, the call's REAL operationId, and a `safeDetails` whose ONLY key is `conflict`.
    // Applying (f) unparameterised here would be an impossible assertion.
    assertGuardErrorShape(err, {
      code: "AMBIGUOUS_KNOWN_IDENTIFIER",
      operationId: "op-conflict",
      safeDetailKeys: ["conflict"],
      canaries: [FIRST, SECOND, "123-45-6789", "987-65-4321"],
    });
    // OR-14(g) recursive walk over the SAME caught object.
    expect(
      walkForCanaries(err, [FIRST, SECOND, "123-45-6789", "987-65-4321"]),
    ).toEqual([]);
  });

  it("GLY373-OR-15(g): two concurrent divergent writers — exactly one succeeds, the other is rejected", async () => {
    // The §10.3 row-4 concurrency oracle, and the WHOLE of the §3.2.5 atomicity requirement.
    // Transaction PLACEMENT is deliberately NOT asserted: the publish seam exposes neither the
    // existing canonical nor a comparator, so placement is unobservable, and the spec may only
    // claim what an oracle can observe. Run repeatedly to reduce interleaving luck.
    for (let round = 0; round < 3; round += 1) {
      const mounts = twoMounts();
      const attemptId = brand<OperationAttemptId>("att-race");
      const settled = await Promise.allSettled([
        mounts.a.store.record(recordInput({ attemptId, canonical: FIRST })),
        mounts.b.store.record(recordInput({ attemptId, canonical: SECOND })),
      ]);
      // A run where BOTH settle `fulfilled` is a FAILURE — that is the executed check-then-set
      // defect this row exists to catch (`{"statuses":["fulfilled","fulfilled"]}`).
      expect(settled.filter((r) => r.status === "fulfilled")).toHaveLength(1);
      const rejectedResults = settled.filter((r) => r.status === "rejected");
      expect(rejectedResults).toHaveLength(1);
      expect((rejectedResults[0] as PromiseRejectedResult).reason).toBe(
        REVERSAL_CANONICAL_CONFLICT,
      );
      // The surviving canonical is the one the SUCCESSFUL call wrote.
      const winner = settled[0]!.status === "fulfilled" ? FIRST : SECOND;
      const map = await mounts.a.store.resolveEncounteredTokens(resolveInput());
      expect(map.get(DEFAULT_TOKEN)).toBe(winner);
    }
  });

  it("GLY373-OR-15(i)/OR-16(f): the durable audit record distinguishes this failure from dictionary ambiguity", async () => {
    // The discriminator must reach the DURABLE record, not merely the thrown error — the record is
    // precisely where an operator looks weeks later. `audit/serializer.ts` serialized only
    // `failureCode`, and an executed `git grep safeDetails` found NO audit projection of engine
    // `safeDetails`, so without this the disambiguation would exist on the error and vanish.
    const { ExactAllowListAuditSerializer } =
      await import("../src/audit/index");
    const { preparedToTerminalEvent } =
      await import("../src/audit/event-factory");
    const prepared = branded<Parameters<typeof preparedToTerminalEvent>[0]>({
      state: "PREPARED",
      attemptId: "att-conflict",
      operationId: "op-conflict",
      tenantId: "t-conflict",
      matterId: "m-conflict",
      actorId: "actor-1",
      operation: "generation",
      dictionaryVersion: 1n,
      engineVersion: "engine-1",
      counts: {
        PERSON_NAME: 0,
        DOB: 0,
        SSN: 0,
        MRN: 0,
        DEA: 0,
        EMAIL: 0,
        PHONE: 0,
        ADDRESS: 0,
        CLAIM_NUMBER: 0,
        POLICY_NUMBER: 0,
        ACCOUNT_NUMBER: 0,
        OTHER_TAGGED: 0,
      },
      ambiguityCount: 0,
      detectorName: null,
      detectorVersion: null,
      latencyMs: { dictionary: 0, detector: 0, total: 0 },
    });

    const event = preparedToTerminalEvent(
      prepared,
      branded("failed_closed"),
      "AMBIGUOUS_KNOWN_IDENTIFIER",
      "2026-08-22T00:00:00.000Z",
      REVERSAL_CANONICAL_CONFLICT_DETAIL,
    );
    const encoded = new TextDecoder().decode(
      new ExactAllowListAuditSerializer().serialize(event),
    );
    // A record carrying ONLY `failureCode` is a failure of this row.
    expect(encoded).toContain('"failureCode":"AMBIGUOUS_KNOWN_IDENTIFIER"');
    expect(encoded).toContain(
      `"failureDetail":"${REVERSAL_CANONICAL_CONFLICT_DETAIL}"`,
    );

    // The serializer's exact value allow-list is a second, independent gate: an arbitrary
    // (possibly PHI-laden) discriminator can never be persisted.
    expect(() =>
      new ExactAllowListAuditSerializer().serialize(
        branded({ ...event, failureDetail: "GLY373-PHI-CANARY" }),
      ),
    ).toThrow();
  });
});

// ==============================================================================================
describe("GLY-373 §3.2.6 scrub-seam propagation (OR-GLY373-16)", () => {
  /** The table of values an untrusted dependency might throw. NONE may ride out except the sentinel. */
  function hostileThrows(): readonly [string, unknown][] {
    return [
      ["ReversalFailedError", new ReversalFailedError()],
      ["plain Error with a canary", new Error("GLY373-PHI-CANARY")],
      [
        "object literal DUCK-TYPING the conflict",
        {
          code: "AMBIGUOUS_KNOWN_IDENTIFIER",
          safeDetails: { conflict: REVERSAL_CANONICAL_CONFLICT_DETAIL },
        },
      ],
      [
        "PhiEngineError constructed BY the untrusted dependency",
        new PhiEngineError(
          "AMBIGUOUS_KNOWN_IDENTIFIER",
          branded("op-forged"),
          branded({ conflict: REVERSAL_CANONICAL_CONFLICT_DETAIL }),
        ),
      ],
      ["a thrown string", "GLY373-PHI-CANARY"],
      // A REJECTED PROMISE, not a synchronous throw. Included in the SHARED table so BOTH seams
      // receive it: an earlier revision added it only to the S2 row, which left the S1 boundary
      // untested for the async-rejection shape.
      ["a rejected promise carrying a canary", REJECTED_PROMISE_MARKER],
    ];
  }

  /**
   * Marker for the async row. A live rejected `Promise` cannot sit in a module-level table without
   * triggering an unhandled-rejection warning before the row runs, so each seam materialises it at
   * use time.
   */
  const REJECTED_PROMISE_MARKER = Symbol("gly373-rejected-promise-row");

  it("GLY373-OR-16(b2) S1: the durable store rethrows ONLY the sentinel, by identity, at its own boundary", async () => {
    // MUT-37(a) is killed ONLY here. Executed evidence: the literal (b) row CANNOT kill it
    // (`MUT37_at_S1_killed_by_literal_OR16b:false`) because an injected reversal store bypasses S1
    // entirely, and a CORRECT S2 scrubs both the correct S1 output and S1's raw-error mutant into
    // observably identical `REVERSAL_FAILED` errors end-to-end
    // (`MUT37_at_S1_killed_end_to_end_through_correct_S2:false`). Asserting at
    // `DurableReversalStore.record()` kills all of them.
    for (const [why, thrown] of hostileThrows()) {
      // CONSTRUCTED DIRECTLY over a faulted spool, per OR-16(b2). NOTE: `makeHarness` has NO
      // `wrapSpool` option — passing one is silently ignored, which would have made this entire
      // row VACUOUS while appearing to pass. The store is therefore built here explicitly.
      //
      // A PROXY, not an object spread: the spool is a class instance whose methods rely on private
      // state and `this` binding, so a spread would hand the store a broken collaborator and the
      // row would prove nothing about the seam.
      const backend = new InMemoryReversalSpoolBackend();
      const rawSpool = backend.mount({}, () => Date.now());
      const store = new DurableReversalStore({
        keyProvider: new InMemoryKeyProvider(),
        spoolVolume: branded(
          new Proxy(rawSpool, {
            get: (target, property, receiver) => {
              if (
                property === "prepare" ||
                property === "publish" ||
                property === "flush"
              ) {
                // The async row is materialised HERE rather than held in the shared table, so no
                // rejected promise exists before the row that consumes it.
                if (thrown === REJECTED_PROMISE_MARKER) {
                  return (): Promise<never> =>
                    Promise.reject(new Error("GLY373-PHI-CANARY"));
                }
                return (): never => {
                  throw thrown;
                };
              }
              const value = Reflect.get(target, property, receiver);
              return typeof value === "function" ? value.bind(target) : value;
            },
          }),
        ),
        classifyRetention: () => Promise.resolve(branded("matter")),
        nowEpochMilliseconds: () => Date.now(),
        maximumEncounteredTokenBatch: 256,
      });
      let caught: unknown;
      try {
        await store.record(recordInput({ canonical: FIRST }));
      } catch (error) {
        caught = error;
      }
      // Every NON-sentinel value surfaces as a FRESH `ReversalFailedError`; the caught value is
      // discarded, never inspected, preserved, or re-thrown — not even a `ReversalFailedError`,
      // since an injected dependency can throw one carrying a `cause` or provider text.
      expect(caught, why).not.toBe(thrown);
      expect(caught instanceof ReversalFailedError, why).toBe(true);
      expect(walkForCanaries(caught, ["GLY373-PHI-CANARY"]), why).toEqual([]);
      // The forged rows prove the seam compares by IDENTITY against a module-private binding, not
      // by `code`, `name`, `message`, `instanceof`, or duck-typing.
      expect(caught, why).not.toBe(REVERSAL_CANONICAL_CONFLICT);
    }

    // And the SENTINEL itself passes through UNCHANGED, by identity.
    const conflict = makeHarness();
    const attemptId = brand<OperationAttemptId>("att-s1");
    await conflict.store.record(recordInput({ attemptId, canonical: FIRST }));
    await expect(
      conflict.store.record(recordInput({ attemptId, canonical: SECOND })),
    ).rejects.toBe(REVERSAL_CANONICAL_CONFLICT);
  });

  it("GLY373-OR-16(a)/(b) S2: exactly one disposition survives the orchestrator seam and nothing else does", async () => {
    const shape = (store: unknown) => ({
      taggedValues: [],
      reversalStore: store,
      tenantId: "t-s2",
      matterId: "m-s2",
      operationId: "op-s2",
      attemptId: "att-s2",
    });
    const call = async (store: unknown): Promise<unknown> => {
      const dev = createSubstitutionEngine(branded(shape(store)));
      try {
        await dev.engine.substitute(
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
        return undefined;
      } catch (error) {
        return error;
      }
    };

    // (a) PASS-THROUGH. Without this row, ruling C (§10.2) is unverifiable.
    const sentinelStore = {
      maximumEncounteredTokenBatch: 256,
      record: (): never => {
        throw REVERSAL_CANONICAL_CONFLICT;
      },
      resolveEncounteredTokens: () => Promise.resolve(new Map()),
    };
    const passed = await call(sentinelStore);
    expect(isPhiEngineError(passed)).toBe(true);
    expect((passed as PhiEngineError).code).toBe("AMBIGUOUS_KNOWN_IDENTIFIER");
    expect((passed as PhiEngineError).safeDetails.conflict).toBe(
      REVERSAL_CANONICAL_CONFLICT_DETAIL,
    );

    // (b) EVERYTHING ELSE IS STILL SCRUBBED — the load-bearing negative row. A `code`-based seam
    // passes (a) and FAILS here, which is exactly the point.
    // The full table, INCLUDING the rejected-promise row, is now shared with the S1 boundary.
    const rows = hostileThrows();
    for (const [why, thrown] of rows) {
      const store = {
        maximumEncounteredTokenBatch: 256,
        record: (): unknown => {
          if (thrown === REJECTED_PROMISE_MARKER) {
            return Promise.reject(new Error("GLY373-PHI-CANARY"));
          }
          throw thrown;
        },
        resolveEncounteredTokens: () => Promise.resolve(new Map()),
      };
      const error = await call(store);
      expect(isPhiEngineError(error), why).toBe(true);
      expect((error as PhiEngineError).code, why).toBe("REVERSAL_FAILED");
      expect((error as PhiEngineError).safeDetails, why).toEqual({});
      expect(walkForCanaries(error, ["GLY373-PHI-CANARY"]), why).toEqual([]);
    }

    // (d) The sentinel itself NEVER escapes to the caller and is not a root export.
    expect(passed).not.toBe(REVERSAL_CANONICAL_CONFLICT);
    const root = (await import("../src/index")) as Record<string, unknown>;
    for (const key of Object.keys(root)) {
      expect(root[key]).not.toBe(REVERSAL_CANONICAL_CONFLICT);
    }
    expect(Object.getOwnPropertyNames(REVERSAL_CANONICAL_CONFLICT)).toEqual([]);
    expect(Object.isFrozen(REVERSAL_CANONICAL_CONFLICT)).toBe(true);
  });
});
