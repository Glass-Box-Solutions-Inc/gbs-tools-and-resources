/**
 * L2.4 DurableReversalStore — store-level oracles (GLY-337), sol spec §C/§D as amended by the Opus
 * spec-check addendum (C1–C4). Named-mutation IDs are in the assertions so the GPT cross-family gate
 * can trace each oracle to the mutation it kills.
 *
 * Test-internal deep imports (../src/tokens/durable/*) are legitimate: these are NEW additive oracles
 * (not the frozen Sol harness), and a test may reach internals to probe them (factory-smoke precedent).
 */
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { ReversalFailedError } from "../src/tokens/index";
import { InMemoryReversalStore } from "../src/tokens/index";
import { buildReversalAad, DurableReversalStore, InMemoryKeyProvider, mappingKeyOf } from "../src/tokens/durable/index";
import type { DurableReversalRecordMeta, EncryptedReversalRecordBlob, ReversalAadFields, SpoolVolume } from "../src/tokens/durable/index";
import {
  brand,
  DEFAULT_MATTER,
  DEFAULT_TOKEN,
  DEFAULT_VERSION,
  DETECTOR_TTL_MS,
  keyFor,
  macrotask,
  makeClock,
  makeHarness,
  recordInput,
  resolveInput,
  T0,
  twoMounts,
} from "./durable-harness";
import type { SubstitutionToken, TenantId, MatterId, DictionaryVersion, OperationAttemptId } from "../src/core/brands";
import { expectNoCanary } from "./test-helpers";

const CLAIMANT = DEFAULT_TOKEN;
const WITNESS = brand<SubstitutionToken>("[[Witness]]");

describe("L2.4 DurableReversalStore — durability + envelope + idempotency (§6, L8, N5)", () => {
  it("record resolves only after durable flush (MUT-RETURN-BEFORE-FLUSH)", async () => {
    let release!: () => void;
    const gate = new Promise<void>((r) => {
      release = r;
    });
    const h = makeHarness({ faults: { flushGate: gate } });

    let resolved = false;
    const pending = h.store.record(recordInput()).then(() => {
      resolved = true;
    });
    await macrotask();
    // The promise is parked at flush — publish has happened but the write is not durable yet.
    expect(resolved).toBe(false);
    expect(h.spy.counts.published).toBe(1);
    expect(h.spy.counts.flush).toBe(1);

    release();
    await pending;
    expect(resolved).toBe(true);
  });

  it("record rejection has the fixed, safe surface — no cause / no canonical / no provider text (MUT-LEAK-UNDERLYING-ERROR)", async () => {
    const h = makeHarness({
      retention: async () => {
        throw new Error("primary db down: Maria García 078-05-1120 at /var/spool/reversal");
      },
    });
    let caught: unknown;
    try {
      await h.store.record(recordInput());
    } catch (error) {
      caught = error;
    }
    expect(caught).toBeInstanceOf(ReversalFailedError);
    const err = caught as ReversalFailedError & { cause?: unknown };
    expect(err.code).toBe("REVERSAL_FAILED");
    expect(err.message).toBe("reversal_failed");
    expect(err.cause).toBeUndefined();
    const surface = JSON.stringify({ name: err.name, message: err.message, code: err.code, ...err });
    expectNoCanary([surface, err.message, String(err), err.stack ?? ""]);
    expect(surface).not.toContain("db down");
    expect(surface).not.toContain("/var/spool");
  });

  it("acknowledged write survives replica loss (remount) (MUT-FLUSH-FILE-ONLY / MUT-CONTAINER-SCRATCH)", async () => {
    const h = makeHarness();
    await h.store.record(recordInput({ canonical: "Maria García" }));

    const replica = h.remount();
    const map = await replica.store.resolveEncounteredTokens(resolveInput());
    expect(map.get(CLAIMANT)).toBe("Maria García");
  });

  it("publication is atomic under a crash injected at every persistence phase (MUT-NONATOMIC-PUBLISH)", async () => {
    for (const phase of ["ensureDekGeneration", "reserveNonce", "prepare", "publish", "flush"] as const) {
      const h = makeHarness({ clock: () => T0, faults: { failAt: phase } });
      await expect(h.store.record(recordInput())).rejects.toBeInstanceOf(ReversalFailedError);

      // Fresh replica over the same durable backend: no partial readable state from the crashed write.
      const replica = h.remount();
      const afterCrash = await replica.store.resolveEncounteredTokens(resolveInput());
      expect(afterCrash.size, `phase=${phase}: no partial mapping visible`).toBe(0);

      // And the crash left no durable tombstone — a fresh, complete write of the same attempt succeeds.
      await replica.store.record(recordInput({ canonical: "Maria García" }));
      const afterRetry = await replica.store.resolveEncounteredTokens(resolveInput());
      expect(afterRetry.get(CLAIMANT), `phase=${phase}: retry resolves`).toBe("Maria García");
    }
  });

  it("record round-trips through encrypt → durable → decrypt (envelope sanity, §6 L8)", async () => {
    const h = makeHarness();
    await h.store.record(recordInput({ canonical: "Robert O'Neil" }));
    const map = await h.store.resolveEncounteredTokens(resolveInput());
    expect(map.get(CLAIMANT)).toBe("Robert O'Neil");
  });
});

describe("L2.4 DurableReversalStore — idempotency (§3.1.3, §6)", () => {
  it("same-attempt exact replay is a durable no-op — exactly one commit", async () => {
    const h = makeHarness();
    await h.store.record(recordInput({ attemptId: brand<OperationAttemptId>("att-x"), canonical: "Maria García" }));
    await h.store.record(recordInput({ attemptId: brand<OperationAttemptId>("att-x"), canonical: "Maria García" }));
    expect(h.spy.counts.published).toBe(1);
    expect(h.spy.counts.existing).toBe(1);
    const map = await h.store.resolveEncounteredTokens(resolveInput());
    expect(map.get(CLAIMANT)).toBe("Maria García");
  });

  it("same-attempt DIVERGENT replay keeps the FIRST canonical and creates no second commit (MUT-IDEMPOTENCY-INCLUDE-CANONICAL / MUT-OVERWRITE-SAME-ATTEMPT)", async () => {
    const h = makeHarness();
    await h.store.record(recordInput({ attemptId: brand<OperationAttemptId>("att-x"), canonical: "Maria García" }));
    await h.store.record(recordInput({ attemptId: brand<OperationAttemptId>("att-x"), canonical: "TOTALLY DIFFERENT" }));
    const map = await h.store.resolveEncounteredTokens(resolveInput());
    expect(map.get(CLAIMANT)).toBe("Maria García"); // first canonical stands
    expect(map.get(CLAIMANT)).not.toBe("TOTALLY DIFFERENT");
    expect(h.spy.counts.published).toBe(1); // no second commit
  });

  it("cross-scope replay (same tenant/attempt/token, different matter) rejects and creates no second mapping", async () => {
    const h = makeHarness();
    await h.store.record(
      recordInput({ attemptId: brand<OperationAttemptId>("att-cs"), matterId: brand<MatterId>("matter-1"), canonical: "Maria García" }),
    );
    await expect(
      h.store.record(
        recordInput({ attemptId: brand<OperationAttemptId>("att-cs"), matterId: brand<MatterId>("matter-2"), canonical: "Maria García" }),
      ),
    ).rejects.toBeInstanceOf(ReversalFailedError);
    // No mapping was created under matter-2; matter-1 is intact.
    const underM2 = await h.store.resolveEncounteredTokens(resolveInput({ matterId: brand<MatterId>("matter-2") }));
    expect(underM2.has(CLAIMANT)).toBe(false);
    const underM1 = await h.store.resolveEncounteredTokens(resolveInput({ matterId: brand<MatterId>("matter-1") }));
    expect(underM1.get(CLAIMANT)).toBe("Maria García");
  });

  it("different attempts advance the current canonical (atomic commit order wins)", async () => {
    const h = makeHarness();
    await h.store.record(recordInput({ attemptId: brand<OperationAttemptId>("att-1"), canonical: "First" }));
    await h.store.record(recordInput({ attemptId: brand<OperationAttemptId>("att-2"), canonical: "Second" }));
    const map = await h.store.resolveEncounteredTokens(resolveInput());
    expect(map.get(CLAIMANT)).toBe("Second");
    expect(h.spy.counts.published).toBe(2);
  });

  it("concurrent replay waits for the original durable flush — neither caller acks early (MUT-CONFLICT-ACK-WITHOUT-FLUSH)", async () => {
    let release!: () => void;
    const gate = new Promise<void>((r) => {
      release = r;
    });
    const h = makeHarness({ faults: { flushGate: gate } });

    let firstDone = false;
    let secondDone = false;
    const p1 = h.store.record(recordInput({ attemptId: brand<OperationAttemptId>("att-race"), canonical: "Maria García" })).then(() => {
      firstDone = true;
    });
    const p2 = h.store.record(recordInput({ attemptId: brand<OperationAttemptId>("att-race"), canonical: "Maria García" })).then(() => {
      secondDone = true;
    });
    await macrotask();
    // The conflict-path caller must not acknowledge before the shared commit is durably flushed.
    expect(firstDone).toBe(false);
    expect(secondDone).toBe(false);

    release();
    await Promise.all([p1, p2]);
    expect(firstDone).toBe(true);
    expect(secondDone).toBe(true);
    expect(h.spy.counts.published).toBe(1); // exactly one real commit for the shared attempt
  });
});

describe("L2.4 DurableReversalStore — cross-replica atomic publish (F1, two mounts on one backend)", () => {
  it("exact replay racing on two replicas commits exactly ONCE (MUT-NONATOMIC-PUBLISH)", async () => {
    const t = twoMounts();
    await Promise.all([
      t.a.store.record(recordInput({ attemptId: brand<OperationAttemptId>("att-r"), canonical: "Maria García" })),
      t.b.store.record(recordInput({ attemptId: brand<OperationAttemptId>("att-r"), canonical: "Maria García" })),
    ]);
    expect(t.publishedTotal()).toBe(1); // NOT two commits — the claim is cross-replica atomic
    const map = await t.a.store.resolveEncounteredTokens(resolveInput());
    expect(map.get(CLAIMANT)).toBe("Maria García");
  });

  it("divergent canonical under one attempt racing on two replicas — first wins, one commit, loser no-ops", async () => {
    const t = twoMounts();
    const settled = await Promise.allSettled([
      t.a.store.record(recordInput({ attemptId: brand<OperationAttemptId>("att-r"), canonical: "Maria García" })),
      t.b.store.record(recordInput({ attemptId: brand<OperationAttemptId>("att-r"), canonical: "TOTALLY DIFFERENT" })),
    ]);
    expect(settled.every((r) => r.status === "fulfilled")).toBe(true); // loser is an idempotent no-op
    expect(t.publishedTotal()).toBe(1);
    const map = await t.a.store.resolveEncounteredTokens(resolveInput());
    const winner = map.get(CLAIMANT);
    expect(["Maria García", "TOTALLY DIFFERENT"]).toContain(winner); // exactly ONE canonical won
    const again = await t.b.store.resolveEncounteredTokens(resolveInput());
    expect(again.get(CLAIMANT)).toBe(winner); // stable across replicas — the loser never overwrote
  });

  it("divergent matter under one attempt racing on two replicas — one rejects, one commit, no second mapping", async () => {
    const t = twoMounts();
    const settled = await Promise.allSettled([
      t.a.store.record(recordInput({ attemptId: brand<OperationAttemptId>("att-cs"), matterId: brand<MatterId>("matter-1"), canonical: "Maria García" })),
      t.b.store.record(recordInput({ attemptId: brand<OperationAttemptId>("att-cs"), matterId: brand<MatterId>("matter-2"), canonical: "Maria García" })),
    ]);
    const rejected = settled.filter((r) => r.status === "rejected") as PromiseRejectedResult[];
    expect(settled.filter((r) => r.status === "fulfilled")).toHaveLength(1);
    expect(rejected).toHaveLength(1);
    expect(rejected[0]!.reason).toBeInstanceOf(ReversalFailedError); // the cross-scope racer fails closed
    expect(t.publishedTotal()).toBe(1);
    const m1 = await t.a.store.resolveEncounteredTokens(resolveInput({ matterId: brand<MatterId>("matter-1") }));
    const m2 = await t.a.store.resolveEncounteredTokens(resolveInput({ matterId: brand<MatterId>("matter-2") }));
    expect(m1.has(CLAIMANT) !== m2.has(CLAIMANT)).toBe(true); // exactly one matter has the mapping
  });
});

describe("L2.4 DurableReversalStore — detector TTL (§6, roadmap D5)", () => {
  it("expired detector mapping is absent at now === expiresAt, without decrypt (MUT-SKIP-READ-TTL)", async () => {
    const clock = makeClock(T0);
    const h = makeHarness({ retention: "detector-only", clock: clock.now });
    await h.store.record(recordInput({ attemptId: brand<OperationAttemptId>("att-d"), canonical: "Maria García" }));

    clock.set(T0 + DETECTOR_TTL_MS - 1);
    const before = await h.store.resolveEncounteredTokens(resolveInput());
    expect(before.get(CLAIMANT)).toBe("Maria García");

    clock.set(T0 + DETECTOR_TTL_MS); // exact expiry instant
    const at = await h.store.resolveEncounteredTokens(resolveInput());
    expect(at.has(CLAIMANT)).toBe(false); // ABSENT (partial map), not a throw
  });

  it("expired detector attempt is non-retryable — replay rejects and opens no fresh 24h window (MUT-REFRESH-EXPIRED-REPLAY)", async () => {
    const clock = makeClock(T0);
    const h = makeHarness({ retention: "detector-only", clock: clock.now });
    await h.store.record(recordInput({ attemptId: brand<OperationAttemptId>("att-d"), canonical: "Maria García" }));

    clock.set(T0 + DETECTOR_TTL_MS + 10);
    await expect(
      h.store.record(recordInput({ attemptId: brand<OperationAttemptId>("att-d"), canonical: "Maria García" })),
    ).rejects.toBeInstanceOf(ReversalFailedError);

    // No new window — still absent well past the original expiry.
    clock.set(T0 + DETECTOR_TTL_MS + 20);
    const after = await h.store.resolveEncounteredTokens(resolveInput());
    expect(after.has(CLAIMANT)).toBe(false);
  });

  it("matter mapping has no store-level 24h expiry", async () => {
    const clock = makeClock(T0);
    const h = makeHarness({ retention: "matter", clock: clock.now });
    await h.store.record(recordInput({ canonical: "Maria García" }));

    clock.set(T0 + DETECTOR_TTL_MS * 30);
    const map = await h.store.resolveEncounteredTokens(resolveInput());
    expect(map.get(CLAIMANT)).toBe("Maria García");
  });

  it("retention classification fails closed on an unknown class", async () => {
    const h = makeHarness({ retention: (() => "surprise") as never });
    await expect(h.store.record(recordInput())).rejects.toBeInstanceOf(ReversalFailedError);
  });
});

describe("L2.4 DurableReversalStore — AAD authenticates every field (§B.6, tamper → fail closed)", () => {
  it("cross-tenant record relocation rejects (MUT-AAD-DROP-TENANT)", async () => {
    const h = makeHarness();
    await h.store.record(recordInput({ tenantId: brand<TenantId>("tenant-a"), canonical: "Maria García" }));
    const from = keyFor({ tenantId: brand<TenantId>("tenant-a") });
    const to = keyFor({ tenantId: brand<TenantId>("tenant-b") });
    h.backend.debugRelocate(from, to);
    await expect(
      h.store.resolveEncounteredTokens(resolveInput({ tenantId: brand<TenantId>("tenant-b") })),
    ).rejects.toBeInstanceOf(ReversalFailedError);
  });

  it("cross-matter relocation rejects (MUT-AAD-DROP-MATTER)", async () => {
    const h = makeHarness();
    await h.store.record(recordInput({ matterId: brand<MatterId>("matter-1"), canonical: "Maria García" }));
    h.backend.debugRelocate(keyFor({ matterId: brand<MatterId>("matter-1") }), keyFor({ matterId: brand<MatterId>("matter-2") }));
    await expect(
      h.store.resolveEncounteredTokens(resolveInput({ matterId: brand<MatterId>("matter-2") })),
    ).rejects.toBeInstanceOf(ReversalFailedError);
  });

  it("cross-version relocation rejects (MUT-AAD-DROP-VERSION)", async () => {
    const h = makeHarness();
    await h.store.record(recordInput({ dictionaryVersion: brand<DictionaryVersion>(1n), canonical: "Maria García" }));
    h.backend.debugRelocate(keyFor({ dictionaryVersion: brand<DictionaryVersion>(1n) }), keyFor({ dictionaryVersion: brand<DictionaryVersion>(2n) }));
    await expect(
      h.store.resolveEncounteredTokens(resolveInput({ dictionaryVersion: brand<DictionaryVersion>(2n) })),
    ).rejects.toBeInstanceOf(ReversalFailedError);
  });

  it("token-slot substitution rejects (MUT-AAD-DROP-TOKEN)", async () => {
    const h = makeHarness();
    await h.store.record(recordInput({ token: CLAIMANT, canonical: "Maria García" }));
    h.backend.debugRelocate(keyFor({ token: CLAIMANT }), keyFor({ token: WITNESS }));
    await expect(h.store.resolveEncounteredTokens(resolveInput({ tokens: [WITNESS] }))).rejects.toBeInstanceOf(ReversalFailedError);
  });

  it("persisted-metadata tampering rejects for attempt / retention / timestamps / dekGen / kekVersion (MUT-AAD-DROP-ATTEMPT / -TTL, key-metadata substitution)", async () => {
    const metaTampers: ReadonlyArray<readonly [string, Partial<DurableReversalRecordMeta>]> = [
      ["attemptId", { attemptId: brand<OperationAttemptId>("att-forged") }],
      ["retentionClass", { retentionClass: "detector-only" }],
      ["createdAtEpochMs", { createdAtEpochMs: 42 }],
      ["expiresAtEpochMs", { expiresAtEpochMs: 999_999_999_999_999n }],
    ];
    for (const [label, patch] of metaTampers) {
      const h = makeHarness({ retention: "matter" });
      await h.store.record(recordInput({ canonical: "Maria García" }));
      h.backend.debugMutateMeta(keyFor(), patch);
      // Read via a fresh replica so the read hits the tampered durable record, not a clean pending copy.
      const replica = h.remount();
      await expect(replica.store.resolveEncounteredTokens(resolveInput()), `meta tamper: ${label}`).rejects.toBeInstanceOf(ReversalFailedError);
    }

    const blobTampers: ReadonlyArray<readonly [string, Partial<EncryptedReversalRecordBlob>]> = [
      ["dekGenerationId", { dekGenerationId: brand("gen-forged") }], // authenticated by AAD field 9
      ["wrappingKeyVersion", { wrappingKeyVersion: brand("v-forged") }], // authenticated by AAD field 10
      ["wrappedDek", { wrappedDek: brand(new Uint8Array(60)) }], // NOT in AAD — fails closed via unwrap/GCM (F4)
      ["wrappingKeyId", { wrappingKeyId: brand("kek-forged") }], // NOT in AAD — fails closed via binding digest (F4)
    ];
    for (const [label, patch] of blobTampers) {
      const h = makeHarness({ retention: "matter" });
      await h.store.record(recordInput({ canonical: "Maria García" }));
      h.backend.debugPatchBlob(keyFor(), patch);
      const replica = h.remount();
      await expect(replica.store.resolveEncounteredTokens(resolveInput()), `blob tamper: ${label}`).rejects.toBeInstanceOf(ReversalFailedError);
    }
  });

  it("extending a detector expiry via metadata tamper is rejected (MUT-AAD-DROP-TTL)", async () => {
    const clock = makeClock(T0);
    const h = makeHarness({ retention: "detector-only", clock: clock.now });
    await h.store.record(recordInput({ canonical: "Maria García" }));
    // Attacker extends expiry to resurrect an about-to-expire detector record.
    h.backend.debugMutateMeta(keyFor(), { expiresAtEpochMs: BigInt(T0) + BigInt(DETECTOR_TTL_MS) * 100n });
    clock.set(T0 + DETECTOR_TTL_MS + 5);
    const replica = h.remount();
    await expect(replica.store.resolveEncounteredTokens(resolveInput())).rejects.toBeInstanceOf(ReversalFailedError);
  });

  it("ciphertext bit-flip fails closed — never returns plaintext (MUT-IGNORE-GCM-TAG)", async () => {
    const h = makeHarness();
    await h.store.record(recordInput({ canonical: "Maria García" }));
    h.backend.debugCorruptCiphertext(keyFor());
    const replica = h.remount();
    await expect(replica.store.resolveEncounteredTokens(resolveInput())).rejects.toBeInstanceOf(ReversalFailedError);
  });
});

describe("L2.4 DurableReversalStore — tenant isolation + nonce uniqueness (L8, §6)", () => {
  it("a colliding token never crosses tenants (MUT-FALLBACK-TENANTLESS-LOOKUP)", async () => {
    const h = makeHarness();
    await h.store.record(recordInput({ tenantId: brand<TenantId>("tenant-a"), canonical: "Value-A" }));
    await h.store.record(recordInput({ tenantId: brand<TenantId>("tenant-b"), canonical: "Value-B" }));

    const a = await h.store.resolveEncounteredTokens(resolveInput({ tenantId: brand<TenantId>("tenant-a") }));
    const b = await h.store.resolveEncounteredTokens(resolveInput({ tenantId: brand<TenantId>("tenant-b") }));
    expect(a.get(CLAIMANT)).toBe("Value-A");
    expect(b.get(CLAIMANT)).toBe("Value-B");

    // Tenant C never recorded this token — absent, never A's or B's canonical.
    const c = await h.store.resolveEncounteredTokens(resolveInput({ tenantId: brand<TenantId>("tenant-c") }));
    expect(c.has(CLAIMANT)).toBe(false);
  });

  it("nonce reservation is unique across concurrency and remount (MUT-REUSE-GCM-NONCE)", async () => {
    const backend = new (await import("../src/tokens/durable/index")).InMemoryReversalSpoolBackend();
    const volumeA = backend.mount();
    const dekGenerationId = brand<import("../src/tokens/durable/index").DekGenerationId>("gen-1");
    const scoped = { tenantId: brand<TenantId>("tenant-a"), matterId: DEFAULT_MATTER, dekGenerationId };

    const first = await Promise.all(Array.from({ length: 8 }, () => volumeA.reserveNonce(scoped)));
    // Remount: a fresh replica over the same durable backend must NOT restart the counter.
    const volumeB = backend.mount();
    const second = await Promise.all(Array.from({ length: 8 }, () => volumeB.reserveNonce(scoped)));

    const hex = [...first, ...second].map((n) => Buffer.from(n).toString("hex"));
    expect(new Set(hex).size).toBe(hex.length); // all 16 distinct across concurrency + remount
  });
});

describe("L2.4 DurableReversalStore — warm DEK cache fails closed on key-material tamper (F2)", () => {
  it("a post-warm wrappedDek swap misses the cache and fails closed — never decrypts under the cached DEK (F2)", async () => {
    const h = makeHarness();
    await h.store.record(recordInput({ tenantId: brand<TenantId>("tenant-a"), canonical: "Maria García" })); // warms #dekCache for tenant-a
    await h.store.record(recordInput({ tenantId: brand<TenantId>("tenant-b"), canonical: "Robert O'Neil" })); // a different scope → a different valid wrapped DEK

    // Warm path works before tamper.
    const warm = await h.store.resolveEncounteredTokens(resolveInput({ tenantId: brand<TenantId>("tenant-a") }));
    expect(warm.get(CLAIMANT)).toBe("Maria García");

    // Attacker swaps in a VALID-but-wrong wrapped DEK (not covered by the AAD). The warm store must
    // NOT reuse the cached original DEK.
    const otherWrapped = h.backend.debugReadBlob(keyFor({ tenantId: brand<TenantId>("tenant-b") })).wrappedDek;
    h.backend.debugPatchBlob(keyFor({ tenantId: brand<TenantId>("tenant-a") }), { wrappedDek: otherWrapped });
    await expect(
      h.store.resolveEncounteredTokens(resolveInput({ tenantId: brand<TenantId>("tenant-a") })),
    ).rejects.toBeInstanceOf(ReversalFailedError);
  });

  it("a post-warm wrappingKeyId swap misses the cache and fails closed (F2)", async () => {
    const h = makeHarness();
    await h.store.record(recordInput({ canonical: "Maria García" })); // warms #dekCache
    const warm = await h.store.resolveEncounteredTokens(resolveInput());
    expect(warm.get(CLAIMANT)).toBe("Maria García");

    h.backend.debugPatchBlob(keyFor(), { wrappingKeyId: brand("kek-forged") });
    await expect(h.store.resolveEncounteredTokens(resolveInput())).rejects.toBeInstanceOf(ReversalFailedError);
  });
});

describe("L2.4 DurableReversalStore — resolve semantics (addendum C2/C4, §7/N2)", () => {
  it("returns a PARTIAL map (missing token absent) with behavioral parity to InMemoryReversalStore", async () => {
    const durable = makeHarness();
    await durable.store.record(recordInput({ token: CLAIMANT, canonical: "Maria García" }));

    const inMemory = new InMemoryReversalStore();
    inMemory.record({
      tenantId: recordInput().tenantId,
      matterId: recordInput().matterId,
      dictionaryVersion: recordInput().dictionaryVersion,
      token: CLAIMANT,
      canonical: "Maria García",
      attemptId: recordInput().attemptId,
    });

    const query = resolveInput({ tokens: [CLAIMANT, WITNESS] }); // one known, one never-recorded
    const durableMap = await durable.store.resolveEncounteredTokens(query);
    const inMemoryMap = await inMemory.resolveEncounteredTokens(query);

    expect(durableMap.get(CLAIMANT)).toBe("Maria García");
    expect(durableMap.has(WITNESS)).toBe(false); // absent, NOT a throw (MUT-PARTIAL-RESOLVE is at the reverser)
    expect(durableMap.size).toBe(1);
    // Behavioral parity: same keys and values as the frozen dev store (swap-in invariant).
    expect([...durableMap.entries()].sort()).toEqual([...inMemoryMap.entries()].sort());
  });

  it("resolve reads ONLY the exact tenant-scoped keys requested (bounded, no list-all)", async () => {
    const h = makeHarness();
    await h.store.record(recordInput({ token: CLAIMANT, canonical: "Maria García" }));
    await h.store.record(recordInput({ token: WITNESS, canonical: "Robert O'Neil", attemptId: brand<OperationAttemptId>("att-w") }));

    await h.store.resolveEncounteredTokens(resolveInput({ tokens: [CLAIMANT] }));
    const requested = h.spy.lastReadRequests.map((r) => String(r.mappingKey));
    expect(requested).toEqual([String(keyFor({ token: CLAIMANT }))]);
    expect(requested).toHaveLength(1);
  });

  it("dedupes tokens and never over-reads", async () => {
    const h = makeHarness();
    await h.store.record(recordInput({ token: CLAIMANT, canonical: "Maria García" }));
    const map = await h.store.resolveEncounteredTokens(resolveInput({ tokens: [CLAIMANT, CLAIMANT, CLAIMANT] }));
    expect(map.size).toBe(1);
    expect(h.spy.lastReadRequests).toHaveLength(1);
  });

  it("rejects an over-sized batch BEFORE any I/O", async () => {
    const h = makeHarness({ maximumEncounteredTokenBatch: 2 });
    const tokens = [CLAIMANT, WITNESS, brand<SubstitutionToken>("[[Adjuster]]")];
    await expect(h.store.resolveEncounteredTokens(resolveInput({ tokens }))).rejects.toBeInstanceOf(ReversalFailedError);
    expect(h.spy.counts.readCurrent).toBe(0); // no I/O occurred
  });

  it("an empty batch resolves to an empty map without I/O", async () => {
    const h = makeHarness();
    const map = await h.store.resolveEncounteredTokens(resolveInput({ tokens: [] }));
    expect(map.size).toBe(0);
    expect(h.spy.counts.readCurrent).toBe(0);
  });
});

describe("L2.4 DurableReversalStore — contaminated dependency errors never ride out (F3, C1)", () => {
  const MARKER = "CONTAMINANT-Maria García-078-05-1120";
  function contaminate(): never {
    const error = new ReversalFailedError();
    (error as unknown as { cause: unknown }).cause = MARKER; // an injected dep smuggles PHI on a `cause`
    (error as unknown as { smuggled: unknown }).smuggled = MARKER;
    throw error;
  }
  function assertCleanEscape(caught: unknown): void {
    expect(caught).toBeInstanceOf(ReversalFailedError);
    const err = caught as ReversalFailedError & { cause?: unknown; smuggled?: unknown };
    expect(err.cause).toBeUndefined();
    expect(err.smuggled).toBeUndefined();
    const serialized = `${JSON.stringify({ message: err.message, code: err.code, ...err })}${String(err)}${err.stack ?? ""}`;
    expect(serialized).not.toContain("CONTAMINANT");
    expectNoCanary([serialized]);
  }

  it("record(): a contaminated classifier error escapes as a FRESH, cause-free REVERSAL_FAILED", async () => {
    const h = makeHarness({ retention: () => contaminate() });
    let caught: unknown;
    try {
      await h.store.record(recordInput());
    } catch (error) {
      caught = error;
    }
    assertCleanEscape(caught);
  });

  it("resolveEncounteredTokens(): a contaminated spool error escapes as a FRESH, cause-free REVERSAL_FAILED", async () => {
    const throwingSpool = {
      readCurrent: () => contaminate(),
      ensureDekGeneration: () => contaminate(),
      reserveNonce: () => contaminate(),
      prepare: () => contaminate(),
      publish: () => contaminate(),
      flush: () => contaminate(),
    } as unknown as SpoolVolume;
    const store = new DurableReversalStore({
      keyProvider: new InMemoryKeyProvider(),
      spoolVolume: throwingSpool,
      classifyRetention: async () => "matter",
      nowEpochMilliseconds: () => T0,
      maximumEncounteredTokenBatch: 256,
    });
    let caught: unknown;
    try {
      await store.resolveEncounteredTokens(resolveInput());
    } catch (error) {
      caught = error;
    }
    assertCleanEscape(caught);
  });
});

describe("L2.4 DurableReversalStore — capability boundary (§7/N2, req 18/19)", () => {
  it("the public surface is frozen: exactly record + resolveEncounteredTokens + maximumEncounteredTokenBatch (MUT-WIDEN-LISTALL)", () => {
    const h = makeHarness();
    const proto = Object.getPrototypeOf(h.store);
    const methods = Object.getOwnPropertyNames(proto)
      .filter((n) => n !== "constructor")
      .sort();
    expect(methods).toEqual(["record", "resolveEncounteredTokens"]);
    expect(Object.getOwnPropertyNames(h.store).sort()).toEqual(["maximumEncounteredTokenBatch"]);
    for (const forbidden of ["listAll", "snapshot", "export", "entriesForMatter", "delete", "diagnostics", "dump", "all", "keys", "entries", "values"]) {
      expect((h.store as unknown as Record<string, unknown>)[forbidden]).toBeUndefined();
    }
  });

  it("store reflection exposes no DEK cache / canonical / wrapped-key after a write+read (MUT-TS-PRIVATE-DEK-CACHE)", async () => {
    const h = makeHarness();
    await h.store.record(recordInput({ canonical: "Maria García 078-05-1120" }));
    await h.store.resolveEncounteredTokens(resolveInput()); // populates the #dekCache

    const reflect = Reflect.ownKeys(h.store).map(String);
    expect(reflect).toEqual(["maximumEncounteredTokenBatch"]); // ONLY the required public number
    for (const forbidden of ["dekCache", "keyProvider", "spool", "classifyRetention", "nowEpochMilliseconds"]) {
      expect(reflect).not.toContain(forbidden);
      expect(Object.getOwnPropertyNames(h.store)).not.toContain(forbidden);
      expect(Object.keys(h.store)).not.toContain(forbidden);
    }
    const serialized = JSON.stringify(h.store) ?? "";
    expect(serialized).not.toContain("Maria García");
    expectNoCanary([serialized]);
  });

  it("sensitive fields use native #private identifiers in source (MUT-TS-PRIVATE-DEK-CACHE, AST)", () => {
    const src = readFileSync(new URL("../src/tokens/durable/durable-reversal-store.ts", import.meta.url), "utf8");
    expect(src).toMatch(/#dekCache\b/); // native private field
    expect(src).not.toMatch(/\bprivate\s+dekCache\b/); // NOT TS-private (runtime-enumerable)
    for (const field of ["#keyProvider", "#spool", "#classifyRetention", "#nowEpochMilliseconds", "#dekCache"]) {
      expect(src, `${field} must be a native #private field`).toContain(field);
    }
  });

  it("the returned map is a working ReadonlyMap view (behavioral parity, addendum C4)", async () => {
    const h = makeHarness();
    await h.store.record(recordInput({ canonical: "Maria García" }));
    const map = await h.store.resolveEncounteredTokens(resolveInput());
    expect(map.get(CLAIMANT)).toBe("Maria García");
    expect([...map.keys()]).toEqual([CLAIMANT]);
    // The AAD builder is a pure, tested primitive (referenced so a tree-shake never drops it).
    expect(buildReversalAad).toBeTypeOf("function");
    expect(mappingKeyOf).toBeTypeOf("function");
  });
});

describe("L2.4 AAD — injective over every one of the 10 authenticated fields (§B.6)", () => {
  // A DIRECT injectivity oracle isolating each AAD field from the DEK-wrap bindingDigest layer.
  // The relocation oracles above are backstopped by the KeyProvider bindingDigest (which itself binds
  // tenant+matter+purpose+keyId+keyVersion), so a cross-tenant/cross-matter relocation is rejected at
  // the unwrap even if the record AAD dropped that field — MUT-AAD-DROP-TENANT / -MATTER SURVIVE those
  // oracles. This pins every field's binding at the AAD itself: two inputs one field apart must yield
  // different bytes, so dropping any field (`field(k, "")`) collapses that pair and fails HERE — no DEK
  // involved. Kills all ten MUT-AAD-DROP-* directly (see [[guard moves when the code moves]]).
  const base: ReversalAadFields = {
    tenantId: "tenant-a",
    matterId: "matter-1",
    dictionaryVersion: "1",
    token: "[[Claimant]]",
    attemptId: "attempt-1",
    retentionClass: "detector-only",
    createdAtEpochMs: 1_700_000_000_000,
    expiresAtEpochMs: 1_700_000_086_400_000n,
    dekGenerationId: "gen-a",
    wrappingKeyVersion: "kek-v1",
  };
  const variants: ReadonlyArray<readonly [string, Partial<ReversalAadFields>]> = [
    ["field(1) tenantId (MUT-AAD-DROP-TENANT)", { tenantId: "tenant-b" }],
    ["field(2) matterId (MUT-AAD-DROP-MATTER)", { matterId: "matter-2" }],
    ["field(3) dictionaryVersion (MUT-AAD-DROP-VERSION)", { dictionaryVersion: "2" }],
    ["field(4) token (MUT-AAD-DROP-TOKEN)", { token: "[[Witness]]" }],
    ["field(5) attemptId (MUT-AAD-DROP-ATTEMPT)", { attemptId: "attempt-2" }],
    ["field(6) retentionClass (MUT-AAD-DROP-RETENTION)", { retentionClass: "matter" }],
    ["field(7) createdAtEpochMs (MUT-AAD-DROP-CREATED)", { createdAtEpochMs: 1_700_000_000_001 }],
    ["field(8) expiresAtEpochMs (MUT-AAD-DROP-TTL)", { expiresAtEpochMs: 1_700_000_086_400_001n }],
    ["field(9) dekGenerationId (MUT-AAD-DROP-DEKGEN)", { dekGenerationId: "gen-b" }],
    ["field(10) wrappingKeyVersion (MUT-AAD-DROP-KEKVER)", { wrappingKeyVersion: "kek-v2" }],
  ];
  const baseHex = Buffer.from(buildReversalAad(base)).toString("hex");
  for (const [label, patch] of variants) {
    it(`changing ${label} changes the AAD bytes`, () => {
      const variantHex = Buffer.from(buildReversalAad({ ...base, ...patch })).toString("hex");
      expect(variantHex, "an AAD field must be injective — dropping it collapses this pair").not.toBe(baseHex);
    });
  }
});

describe("L2.4 durable current mapping survives a concurrent different-attempt publisher (§6/N4)", () => {
  it("an acknowledged commit stays resolvable after a later same-mappingKey attempt publishes, fails to flush, then the replica crashes (MUT-DURABLE-MAPPING-STEAL)", async () => {
    // Two operations of ONE matter tokenize the same canonical → SAME mappingKey, DIFFERENT attemptId.
    const hA = makeHarness({ retention: "matter" });
    // Second live replica over the SAME durable backend + KEK; its flush always fails (publishes, never
    // durably flushes), so it steals the PROVISIONAL current pointer without establishing a durable one.
    const hB = makeHarness({
      retention: "matter",
      backend: hA.backend,
      keyProvider: hA.keyProvider,
      faults: { failAt: "flush" },
    });
    const CANON = "Maria García";
    // Attempt A fully records (publish + durable flush) → acknowledged; durable pointer = A.
    await hA.store.record(recordInput({ attemptId: brand<OperationAttemptId>("att-A"), canonical: CANON }));
    // Attempt B (same mappingKey, different attempt) publishes on replica B, then fails to flush.
    await expect(
      hB.store.record(recordInput({ attemptId: brand<OperationAttemptId>("att-B"), canonical: CANON })),
    ).rejects.toBeInstanceOf(ReversalFailedError);
    // Replica loss: every published-but-unflushed claim/mapping is discarded.
    hA.backend.crash();
    // A's acknowledgment MUST hold: the token is still resolvable via the surviving durable pointer.
    const resolved = await hA.store.resolveEncounteredTokens(resolveInput());
    expect(resolved.get(CLAIMANT)).toBe(CANON);
  });

  it("an old-attempt idempotent replay does NOT roll the durable current canonical back (MUT-DURABLE-ROLLBACK)", async () => {
    const h = makeHarness();
    await h.store.record(recordInput({ attemptId: brand<OperationAttemptId>("att-1"), canonical: "First" }));
    await h.store.record(recordInput({ attemptId: brand<OperationAttemptId>("att-2"), canonical: "Second" }));
    // Replaying the OLDER attempt is a no-op that flushes its ORIGINAL (lower-ordinal) commit again.
    await h.store.record(recordInput({ attemptId: brand<OperationAttemptId>("att-1"), canonical: "First" }));
    const map = await h.store.resolveEncounteredTokens(resolveInput());
    expect(map.get(CLAIMANT)).toBe("Second"); // atomic publication order wins — NOT rolled back to "First"
  });

  it("a late flush of an earlier publication does not override a newer commit's durable current (MUT-DURABLE-ROLLBACK)", async () => {
    let releaseA!: () => void;
    const gateA = new Promise<void>((r) => {
      releaseA = r;
    });
    const hA = makeHarness({ faults: { flushGate: gateA } });
    const hB = makeHarness({ backend: hA.backend, keyProvider: hA.keyProvider });
    // A publishes FIRST (lower ordinal) but its flush is held pending.
    const pA = hA.store.record(recordInput({ attemptId: brand<OperationAttemptId>("att-A"), canonical: "First" }));
    await macrotask();
    // B publishes SECOND (higher ordinal) and flushes → durable current = B.
    await hB.store.record(recordInput({ attemptId: brand<OperationAttemptId>("att-B"), canonical: "Second" }));
    // A's flush now completes LAST; flush-completion order must NOT override publication order.
    releaseA();
    await pA;
    const map = await hA.store.resolveEncounteredTokens(resolveInput());
    expect(map.get(CLAIMANT)).toBe("Second");
  });

  it("a gated peer of a crashed idempotency claim fails closed — cannot ack a vanished commit (MUT-FLUSH-LOST-COMMIT)", async () => {
    let releaseA!: () => void;
    let releaseB!: () => void;
    const gateA = new Promise<void>((r) => {
      releaseA = r;
    });
    const gateB = new Promise<void>((r) => {
      releaseB = r;
    });
    const hA = makeHarness({ faults: { flushGate: gateA } });
    const hB = makeHarness({ backend: hA.backend, keyProvider: hA.keyProvider, faults: { flushGate: gateB } });
    // A publishes its idempotency claim, then blocks in flush (claim is published-but-unflushed).
    const pA = hA.store.record(recordInput({ attemptId: brand<OperationAttemptId>("att-A"), canonical: "X" }));
    await macrotask();
    // B (SAME attempt) observes the existing unflushed claim and enters a gated flush of that SAME commit.
    const pB = hB.store.record(recordInput({ attemptId: brand<OperationAttemptId>("att-A"), canonical: "X" }));
    await macrotask();
    // Replica loss erases the unflushed claim and its commit-index entry.
    hA.backend.crash();
    // Both gated callers resume; neither may acknowledge a vanished commit.
    releaseA();
    releaseB();
    await expect(pA).rejects.toBeInstanceOf(ReversalFailedError);
    await expect(pB).rejects.toBeInstanceOf(ReversalFailedError);
    const map = await hA.store.resolveEncounteredTokens(resolveInput());
    expect(map.has(CLAIMANT)).toBe(false);
  });
});

describe("L2.4 retention is operation-scoped — classifier sees identifiers only, identically per operation (C3)", () => {
  it("both record()s of one operation pass ONLY {tenantId,matterId,attemptId} — never a token/canonical — and the same values (MUT-CLASSIFY-PER-TOKEN)", async () => {
    const calls: Array<Record<string, unknown>> = [];
    const h = makeHarness({
      retention: (input) => {
        calls.push({ ...(input as unknown as Record<string, unknown>) });
        return "matter";
      },
    });
    const att = brand<OperationAttemptId>("att-op1");
    // Two DIFFERENT tokens under ONE operation (same tenant/matter/attempt).
    await h.store.record(recordInput({ attemptId: att, token: CLAIMANT, canonical: "Maria García" }));
    await h.store.record(recordInput({ attemptId: att, token: WITNESS, canonical: "Bob Jones" }));
    expect(calls.length).toBe(2);
    for (const c of calls) {
      // The classifier is operation-scoped: it receives EXACTLY the operation identifiers, never a token
      // or canonical — so retention can never be inferred per-token. Passing the token is MUT-CLASSIFY-PER-TOKEN.
      expect(Object.keys(c).sort()).toEqual(["attemptId", "matterId", "tenantId"]);
      expect("token" in c).toBe(false);
      expect("canonical" in c).toBe(false);
    }
    // Same operation → identical classifier input both times → a deterministic classifier yields ONE class.
    expect(calls[0]).toEqual(calls[1]);
  });
});

describe("L2.4 boundary input is read INSIDE the scrub try — a throwing getter/iterator fails closed (F3-boundary, C1)", () => {
  const MARKER = "CONTAMINANT-Maria García-078-05-1120";
  function poison(): never {
    // A hostile passed-in field access smuggles PHI on the thrown error's cause (NOT intrinsic poisoning).
    throw Object.assign(new ReversalFailedError(), { cause: MARKER, smuggled: MARKER });
  }
  function assertCleanEscape(caught: unknown): void {
    expect(caught).toBeInstanceOf(ReversalFailedError);
    const err = caught as ReversalFailedError & { cause?: unknown; smuggled?: unknown };
    expect(err.cause).toBeUndefined();
    expect(err.smuggled).toBeUndefined();
    const dump = `${JSON.stringify({ message: err.message, ...err })}${String(err)}${err.stack ?? ""}`;
    expect(dump).not.toContain("CONTAMINANT");
    expectNoCanary([dump]);
  }

  it("record(): a throwing `canonical` getter rejects with a FRESH, cause-free REVERSAL_FAILED (MUT-INPUT-OUTSIDE-SCRUB)", async () => {
    const h = makeHarness();
    const hostile = { ...recordInput() } as Record<string, unknown>;
    Object.defineProperty(hostile, "canonical", { get: poison, enumerable: true, configurable: true });
    let caught: unknown;
    try {
      await h.store.record(hostile as unknown as Parameters<DurableReversalStore["record"]>[0]);
    } catch (e) {
      caught = e;
    }
    assertCleanEscape(caught);
  });

  it("resolveEncounteredTokens(): a throwing `tokens` iterator rejects with a FRESH, cause-free REVERSAL_FAILED (MUT-INPUT-OUTSIDE-SCRUB)", async () => {
    const h = makeHarness();
    const hostile = {
      ...resolveInput(),
      tokens: {
        get length() {
          return 1;
        },
        [Symbol.iterator]() {
          poison();
        },
      },
    };
    let caught: unknown;
    try {
      await h.store.resolveEncounteredTokens(hostile as unknown as Parameters<DurableReversalStore["resolveEncounteredTokens"]>[0]);
    } catch (e) {
      caught = e;
    }
    assertCleanEscape(caught);
  });
});

describe("L2.4 resolve snapshots its scope inputs — no TOCTOU between mapping-key and AAD scope (Silas F1)", () => {
  it("a flipping `dictionaryVersion` getter is read once, so a v1 record resolves consistently (MUT-RESOLVE-SCOPE-TOCTOU)", async () => {
    const h = makeHarness();
    await h.store.record(recordInput({ dictionaryVersion: brand<DictionaryVersion>(1n), canonical: "Maria García" }));
    let reads = 0;
    // The scope field flips AFTER its first read. A single snapshot pins the whole resolution to v1
    // (mapping key AND AAD reconstruction); re-reading `input.dictionaryVersion` per use would build the
    // mapping key under v1 but reconstruct the AAD under v2 → byte-mismatch → spurious REVERSAL_FAILED.
    const hostile = {
      ...resolveInput({ dictionaryVersion: brand<DictionaryVersion>(1n) }),
      get dictionaryVersion(): DictionaryVersion {
        reads += 1;
        return brand<DictionaryVersion>(reads === 1 ? 1n : 2n);
      },
    };
    const resolved = await h.store.resolveEncounteredTokens(
      hostile as unknown as Parameters<DurableReversalStore["resolveEncounteredTokens"]>[0],
    );
    expect(resolved.get(CLAIMANT)).toBe("Maria García");
  });
});

// Silence unused-import lint in transpile-only test runs while keeping the symbols available.
void DEFAULT_MATTER;
void DEFAULT_VERSION;
