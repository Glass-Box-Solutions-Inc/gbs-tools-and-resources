/**
 * GLY-373 — detection-suppression oracles OR-GLY373-05 and OR-GLY373-06.
 *
 * The call-count seam is a MODULE-LEVEL spy over the `../collision/index` binding, per the ratified
 * AMB-GLY373-06 decision. There is deliberately NO production seam: an injected detector port would
 * be a real capability widening needing its own threat review, and it would breach the fenced root
 * surface OR-08 pins. The earlier "or an injected seam" alternative was withdrawn in revision 15.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

// THE SEAM IS `vi.spyOn` ON THE `../collision/index` BINDING, as AMB-GLY373-06 mandates, and there
// is deliberately NO production seam. The `vi.mock` factory below does NOT stub anything: it
// re-exports every real binding UNCHANGED. Its only job is to make the module namespace a plain,
// WRITABLE object, because a live ESM namespace is frozen and `vi.spyOn` cannot install on it. The
// spy therefore wraps the REAL `detectStructuredIdentifiers` — the same function the orchestrator
// imports at `orchestrator.ts:84` — and counts its real invocations.
//
// `{ spy: true }` was tried first and is WRONG here: it auto-spies every export including the
// classes, and a spied class constructor cannot be invoked with `new`, which breaks
// `dictionary/tokenize.ts:36` at import time.
vi.mock("../src/collision/index", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../src/collision/index")>()),
}));

const collision = await import("../src/collision/index");
const { createSubstitutionEngine } = await import("../src/index");
const { isPhiEngineError } = await import("../src/core/errors");
const { InMemoryReversalStore } = await import("../src/tokens/reversal");

const detectionSpy = vi.spyOn(collision, "detectStructuredIdentifiers");

/** Reads the live spy count; named so every row's assertion reads as the spec's "spy calls". */
const detectionCalls = {
  get count(): number {
    return detectionSpy.mock.calls.length;
  },
  set count(_value: number) {
    detectionSpy.mockClear();
  },
};

/**
 * Counts EVERY case-truth read. `MatterDictionaryCompiler` cannot compile without reading tagged
 * values (`dictionary/compiler.ts`), so a zero read count is direct evidence that "no dictionary
 * compile was attempted" — the spec's requirement for the invalid rows. Inferring it from the
 * absence of tokens would not distinguish "never compiled" from "compiled and then discarded".
 */
function countingTruthReader(counter: { reads: number }): unknown {
  return {
    readTaggedValues: (): Promise<readonly unknown[]> => {
      counter.reads += 1;
      return Promise.resolve([]);
    },
  };
}

/** Records every reversal write so detector rows can be counted DIRECTLY, not inferred. */
function recordingStore(rows: { token: string; canonical: string }[]): unknown {
  const inner = new InMemoryReversalStore();
  return new Proxy(inner, {
    get(target, property, receiver): unknown {
      const value = Reflect.get(target, property, receiver) as unknown;
      if (property === "record" && typeof value === "function") {
        return (input: { token: string; canonical: string }): unknown => {
          rows.push({ token: input.token, canonical: input.canonical });
          return (value as (i: unknown) => unknown).call(target, input);
        };
      }
      return typeof value === "function"
        ? (value as (...a: unknown[]) => unknown).bind(target)
        : value;
    },
  });
}

type Dev = ReturnType<typeof createSubstitutionEngine>;

const CANARY = "GLY373-PHI-CANARY";

function branded<T>(value: unknown): T {
  return value as T;
}

function tagged(
  subjectId: string,
  canonical: string,
  role: string,
  identifierClass: string,
  expander: string,
): unknown {
  return {
    field: {
      schemaPath: `claim.${subjectId}`,
      substitution: true,
      identifierClass: branded(identifierClass),
      tokenRole: branded(role),
      expander: branded(expander),
    },
    subjectId: branded(subjectId),
    canonicalDisplayValue: canonical,
    approvedAliases: [],
  };
}

/** THREE segments, so the per-segment call count is a meaningful number and not just 0-or-1. */
const SEGMENT_TEXTS = [
  "Reach alpha@example.com regarding the claim.",
  "SSN 123-45-6789 was verified.",
  "Injury date 3/4/2021, ref 987654321.",
] as const;

function segments(): unknown {
  return SEGMENT_TEXTS.map((text, index) => ({
    path: `messages[${index}].content[0].text`,
    kind: "user",
    text,
  }));
}

async function attempt(
  dev: Dev,
  detectorRequirement: unknown,
  policyOverride?: Record<string, unknown>,
): Promise<{ output?: unknown; error?: unknown }> {
  try {
    const output = await dev.engine.substitute(
      branded({
        context: dev.context,
        policy: policyOverride ?? {
          ...dev.policy,
          detectorRequirement,
        },
        segments: segments(),
        purpose: "generation",
      }),
    );
    return { output };
  } catch (error) {
    return { error };
  }
}

function tokensIn(text: string): string[] {
  return [...text.matchAll(/\[\[[^\]]*\]\]/g)].map((m) => m[0]);
}

/** `JSON.stringify` throws on the bigint `dictionaryVersion`; canaries are strings either way. */
function safeJson(value: unknown): string {
  return JSON.stringify(value, (_k, v) =>
    typeof v === "bigint" ? v.toString() : v,
  );
}

function outputText(output: unknown): string {
  return (output as { segments: { text: unknown }[] }).segments
    .map((s) => String(s.text))
    .join("\n");
}

describe("GLY-373 detection suppression", () => {
  beforeEach(() => {
    detectionSpy.mockClear();
  });

  it("GLY373-OR-05: detectorRequirement governs whether deterministic detection executes", async () => {
    let rows = 0;
    const dev = createSubstitutionEngine({ taggedValues: [] });

    // --- RUN rows: the canonical name and its deprecated alias must be BYTE-IDENTICAL ---
    detectionCalls.count = 0;
    const canonical = await attempt(dev, "DETERMINISTIC_STRUCTURED_ONLY");
    rows += 1;
    expect(canonical.error).toBeUndefined();
    expect(detectionCalls.count).toBe(3);
    const canonicalText = outputText(canonical.output);
    expect(tokensIn(canonicalText).length).toBeGreaterThan(0);

    // A fresh engine so the alias row mints from the same starting state as the row above.
    const aliasDev = createSubstitutionEngine({ taggedValues: [] });
    detectionCalls.count = 0;
    const alias = await attempt(aliasDev, "DISABLED_PHASE_1");
    rows += 1;
    expect(alias.error).toBeUndefined();
    expect(detectionCalls.count).toBe(3);
    // MUT-08 makes the alias mean hard suppression and reds here.
    expect(outputText(alias.output)).toBe(canonicalText);

    // --- SUPPRESSION row: NON-INVOCATION, not filtering. MUT-06 calls and discards, and reds on
    //     the call count — which is exactly why the count, not the output, is the assertion.
    const offRows: { token: string; canonical: string }[] = [];
    const offDev = createSubstitutionEngine({
      taggedValues: [],
      reversalStore: branded(recordingStore(offRows)),
    });
    detectionCalls.count = 0;
    const off = await attempt(offDev, "STRUCTURED_DETECTION_OFF");
    rows += 1;
    expect(off.error).toBeUndefined();
    expect(detectionCalls.count).toBe(0);
    // ZERO DETECTOR REVERSAL ROWS, asserted DIRECTLY at the write seam rather than inferred from
    // the absence of tokens in the output. Those are different claims: a row could be written for a
    // token that never reached the text. There are no tagged values here, so the correct count is
    // zero rows of ANY kind, and in particular zero namespaced ones.
    expect(offRows).toHaveLength(0);
    expect(offRows.filter((r) => r.token.includes("~"))).toHaveLength(0);
    const offText = outputText(off.output);
    // The undetected identifiers pass through RAW — this is what ruling g8 rejected for both
    // consumers, and asserting it makes the safety cost of suppression explicit rather than
    // incidental. Zero detector reversal rows are written because zero detector tokens exist.
    expect(offText).toContain("alpha@example.com");
    expect(offText).toContain("123-45-6789");
    expect(tokensIn(offText)).toHaveLength(0);

    // --- REQUIRED row: the belt is not wired, so this fixed-fails, unchanged from 0.2.0 ---
    detectionCalls.count = 0;
    const required = await attempt(dev, "REQUIRED");
    rows += 1;
    expect(detectionCalls.count).toBe(0);
    expect(isPhiEngineError(required.error)).toBe(true);
    expect((required.error as { code: string }).code).toBe(
      "DETECTOR_UNAVAILABLE",
    );

    // --- INVALID rows: exhaustive and fail-closed. No permissive default, and never "treat
    //     unknown as off" (MUT-07). The failure lands BEFORE any dictionary work.
    const invalid: readonly [string, unknown][] = [
      ["NOT_A_VALUE", "NOT_A_VALUE"],
      ["empty string", ""],
      ["null", null],
      ["undefined", undefined],
      ["number", 7],
      ["object", { toString: () => "DETERMINISTIC_STRUCTURED_ONLY" }],
    ];
    for (const [why, value] of invalid) {
      rows += 1;
      // A FRESH engine per row over a COUNTING truth reader: the fail-closed branch must land
      // before ANY dictionary work, and `dev` above has already compiled, so reusing it would let
      // a cached dictionary hide a compile attempt.
      const truth = { reads: 0 };
      const invalidDev = createSubstitutionEngine({
        truthReader: branded(countingTruthReader(truth)),
      });
      detectionCalls.count = 0;
      const bad = await attempt(invalidDev, value);
      expect(detectionCalls.count, why).toBe(0);
      // "No dictionary compile attempted" — the spec's words, asserted rather than assumed.
      expect(truth.reads, why).toBe(0);
      expect(isPhiEngineError(bad.error), why).toBe(true);
      expect((bad.error as { code: string }).code, why).toBe(
        "MISSING_TRUSTED_POLICY",
      );
      const exposed = [
        String(bad.error),
        (bad.error as Error).message,
        JSON.stringify(bad.error),
      ].join("\n");
      expect(exposed, why).not.toContain(CANARY);
    }

    // A THROWING getter is read getter-throw-safely and lands on the same fixed failure.
    rows += 1;
    const throwingTruth = { reads: 0 };
    const throwingDev = createSubstitutionEngine({
      truthReader: branded(countingTruthReader(throwingTruth)),
    });
    detectionCalls.count = 0;
    const throwing = await attempt(throwingDev, undefined, {
      ...throwingDev.policy,
      get detectorRequirement(): string {
        throw new Error(CANARY);
      },
    });
    expect(detectionCalls.count).toBe(0);
    expect((throwing.error as { code: string }).code).toBe(
      "MISSING_TRUSTED_POLICY",
    );
    expect(JSON.stringify(throwing.error)).not.toContain(CANARY);
    expect(throwingTruth.reads).toBe(0);

    expect(rows).toBe(11);
  });

  it("GLY373-OR-05 single-read: detectorRequirement is read EXACTLY ONCE (snapshot, not re-read)", async () => {
    // This is the SNAPSHOT oracle and is distinct from the throwing-getter row above. MUT-15
    // re-reads the value at the detection site instead of using the `:334` snapshot; both variants
    // below catch it, from opposite directions.
    const variants: readonly [string, unknown][] = [
      // Variant A: throws a canary on read >= 2 — a re-reading implementation surfaces the canary
      // or a non-fixed error.
      ["throws on later reads", "THROW"],
      // Variant B: silently switches semantics on read >= 2 — a re-reading implementation
      // suppresses detection, so the call count drops below the segment count even though the
      // FIRST read said detection was on. This is the dangerous, quiet form.
      ["switches on later reads", "STRUCTURED_DETECTION_OFF"],
    ];

    for (const [why, later] of variants) {
      const dev = createSubstitutionEngine({ taggedValues: [] });
      let reads = 0;
      const policy = {
        ...dev.policy,
        get detectorRequirement(): string {
          reads += 1;
          if (reads === 1) return "DETERMINISTIC_STRUCTURED_ONLY";
          if (later === "THROW") throw new Error(CANARY);
          return later as string;
        },
      };
      detectionCalls.count = 0;
      const result = await attempt(dev, undefined, policy);

      expect(reads, why).toBe(1);
      expect(result.error, why).toBeUndefined();
      expect(detectionCalls.count, why).toBe(3);
      const exposed = [
        outputText(result.output),
        // The reversal handle deliberately THROWS from `toJSON` (§7/NEW-2), so it is excluded and
        // the scan targets the segments — which is where a canary could actually be spliced.
        safeJson(
          (result.output as { segments?: unknown } | undefined)?.segments ?? [],
        ),
      ].join("\n");
      expect(exposed, why).not.toContain(CANARY);
    }
  });

  it("GLY373-OR-06: STRUCTURED_DETECTION_OFF still substitutes every tagged subject", async () => {
    const dev = createSubstitutionEngine({
      taggedValues: branded([
        tagged(
          "s-claimant",
          "Avery Alpha",
          "Claimant",
          "PERSON_NAME",
          "person-name",
        ),
        tagged("s-ssn", "555-11-2222", "SSN", "SSN", "literal"),
      ]),
    });
    detectionCalls.count = 0;
    const result = await dev.engine.substitute(
      branded({
        context: dev.context,
        policy: {
          ...dev.policy,
          detectorRequirement: "STRUCTURED_DETECTION_OFF",
        },
        segments: [
          {
            path: "messages[0].content[0].text",
            kind: "user",
            // A TAGGED name, a TAGGED SSN, and an UNTAGGED free-text SSN + e-mail.
            text: "Avery Alpha, SSN 555-11-2222; also 123-45-6789 and alpha@example.com.",
          },
        ],
        purpose: "generation",
      }),
    );
    expect(detectionCalls.count).toBe(0);

    const text = String(result.segments[0]!.text);
    // Suppression does NOT weaken the dictionary path: every TAGGED subject is still tokenized
    // and still reversible. Both tokens are authority tokens, so both are bare.
    expect(text).toContain("[[Claimant]]");
    expect(text).toContain("[[SSN]]");
    expect(text).not.toContain("Avery Alpha");
    expect(text).not.toContain("555-11-2222");
    for (const token of tokensIn(text)) {
      expect(token).not.toContain("~");
    }
    // Only the UNTAGGED free-text identifiers pass through — the explicit, asserted safety cost.
    expect(text).toContain("123-45-6789");
    expect(text).toContain("alpha@example.com");

    const reversed = String(
      await dev.engine.reverse(branded(text), result.reversalHandle),
    );
    expect(reversed).toContain("Avery Alpha");
    expect(reversed).toContain("555-11-2222");
  });
});
