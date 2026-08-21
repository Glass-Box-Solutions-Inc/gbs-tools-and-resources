/**
 * L2.4 DurableReversalStore — orchestrator / reverser integration oracles (GLY-337).
 *
 * Proves the durable store is a behavior-preserving SWAP-IN for `InMemoryReversalStore` at the real
 * `ComposedSubstitutionEngine` boundary (via the injectable `reversalStore` seam on the composition
 * factory), and locates the addendum-C2 layering end-to-end:
 *   - the STORE returns a partial map (missing token absent);
 *   - the REVERSER (`reverseText`, driven by `engine.reverse`) enforces N5 all-or-nothing → the whole
 *     reversal fails REVERSAL_FAILED with no partial DisplayText.
 * Also proves durable-before-egress: a blocked/failed flush keeps `record()` from resolving, so a
 * provider spy sequenced after `substitute()` is never called (MUT-RETURN-BEFORE-FLUSH).
 */
import { describe, expect, it } from "vitest";
import {
  createSubstitutionEngine,
  PhiEngineError,
  ReversalFailedError,
} from "../src/index";
import type { TextSegment } from "../src/index";
import type { TokenizedText } from "../src/core/brands";
import {
  DurableReversalStore,
  InMemoryKeyProvider,
  InMemoryReversalSpoolBackend,
} from "../src/tokens/durable/index";
import { brand, makeHarness } from "./durable-harness";

const DEV_NAME = "Jordan Testcase"; // dev seed (Claimant) — synthetic, non-real (SSA-reserved block)

function userSegments(text: string): TextSegment[] {
  return [{ path: "messages[0].content[0].text", kind: "user", text }];
}

describe("L2.4 DurableReversalStore — orchestrator swap-in (real ComposedSubstitutionEngine)", () => {
  it("substitute → durable record → reverse round-trips through the durable store", async () => {
    const { store } = makeHarness({ retention: "matter" });
    const dev = createSubstitutionEngine({ reversalStore: store });

    const result = await dev.engine.substitute({
      context: dev.context,
      policy: dev.policy,
      segments: userSegments(
        `Please contact ${DEV_NAME} regarding the claim intake.`,
      ),
      purpose: "generation",
    });

    const tokenized = String(result.segments[0]!.text);
    expect(tokenized).toMatch(/\[\[Claimant/);
    expect(tokenized).not.toContain(DEV_NAME); // substituted, never egressed raw

    const display = await dev.engine.reverse(
      result.segments[0]!.text,
      result.reversalHandle,
    );
    expect(String(display)).toContain(DEV_NAME); // reversed from the durable, envelope-encrypted mapping
  });

  it("acknowledged durable mappings survive a replica remount and still reverse", async () => {
    const backend = new InMemoryReversalSpoolBackend();
    const keyProvider = new InMemoryKeyProvider();
    const clock = () => 1_700_000_000_000;
    const store = new DurableReversalStore({
      keyProvider,
      spoolVolume: backend.mount({}, clock),
      classifyRetention: async () => "matter",
      nowEpochMilliseconds: clock,
      maximumEncounteredTokenBatch: 256,
    });

    const dev = createSubstitutionEngine({ reversalStore: store });
    const result = await dev.engine.substitute({
      context: dev.context,
      policy: dev.policy,
      segments: userSegments(`Please contact ${DEV_NAME}.`),
      purpose: "generation",
    });

    // Fresh replica: a NEW store + NEW volume over the SAME durable backend + SAME KEK.
    const replicaStore = new DurableReversalStore({
      keyProvider,
      spoolVolume: backend.mount({}, clock),
      classifyRetention: async () => "matter",
      nowEpochMilliseconds: clock,
      maximumEncounteredTokenBatch: 256,
    });
    const replicaEngine = createSubstitutionEngine({
      reversalStore: replicaStore,
    });
    const display = await replicaEngine.engine.reverse(
      result.segments[0]!.text,
      result.reversalHandle,
    );
    expect(String(display)).toContain(DEV_NAME);
  });
});

describe("L2.4 DurableReversalStore — durable-before-egress (§6, N4)", () => {
  it("a failed durable flush rejects substitute as REVERSAL_FAILED and a sequenced provider spy stays uncalled (MUT-RETURN-BEFORE-FLUSH)", async () => {
    const backend = new InMemoryReversalSpoolBackend();
    const keyProvider = new InMemoryKeyProvider();
    const clock = () => 1_700_000_000_000;
    // flush throws → record() rejects → the orchestrator contains it as REVERSAL_FAILED before egress.
    const store = new DurableReversalStore({
      keyProvider,
      spoolVolume: backend.mount({ failAt: "flush" }, clock),
      classifyRetention: async () => "matter",
      nowEpochMilliseconds: clock,
      maximumEncounteredTokenBatch: 256,
    });
    const dev = createSubstitutionEngine({ reversalStore: store });

    let providerCalls = 0;
    const providerSpy = (): void => {
      providerCalls += 1;
    };

    let caught: unknown;
    try {
      const result = await dev.engine.substitute({
        context: dev.context,
        policy: dev.policy,
        segments: userSegments(`Please contact ${DEV_NAME}.`),
        purpose: "generation",
      });
      // This models the wrapper's next step (provider egress). It MUST NOT run when record() failed.
      providerSpy();
      void result;
    } catch (error) {
      caught = error;
    }

    expect(providerCalls).toBe(0); // durable-before-egress held — no provider call
    expect(caught).toBeInstanceOf(PhiEngineError);
    expect((caught as PhiEngineError).code).toBe("REVERSAL_FAILED");
  });
});

describe("L2.4 DurableReversalStore — N5 all-or-nothing lives at the reverser (addendum C2)", () => {
  it("an absent token fails the WHOLE reversal (REVERSAL_FAILED), never a partial DisplayText (MUT-PARTIAL-RESOLVE)", async () => {
    const { store } = makeHarness({ retention: "matter" });
    const dev = createSubstitutionEngine({ reversalStore: store });

    const result = await dev.engine.substitute({
      context: dev.context,
      policy: dev.policy,
      segments: userSegments(`Please contact ${DEV_NAME}.`),
      purpose: "generation",
    });

    // Append a grammar-valid but NEVER-recorded token. The store returns it ABSENT (partial map);
    // the reverser must fail the whole reversal rather than emit a partial display.
    const tampered =
      `${String(result.segments[0]!.text)} and also [[Witness]]` as unknown as TokenizedText;
    await expect(
      dev.engine.reverse(tampered, result.reversalHandle),
    ).rejects.toBeInstanceOf(ReversalFailedError);
  });
});

void brand;
