/**
 * GLY-373 — namespaced substitution grammar oracles OR-GLY373-01/02/03/04/07/10/11/12/13.
 *
 * All fixtures are SYNTHETIC. Every "known answer" literal in OR-13 is FIXED BY THE SPEC and is
 * transcribed verbatim; it is deliberately NOT computed from the implementation, which would make
 * the test assert whatever the code happens to do. If the implementation disagrees with a literal
 * here, the implementation is wrong.
 */
import { describe, expect, it } from "vitest";
import { createSubstitutionEngine } from "../src/index";
import type {
  CreateSubstitutionEngineOptions,
  TaggedValue,
  TextSegment,
  SubstitutionToken,
  TokenizedText,
  TokenAssignmentStore,
} from "../src/index";
import { BracketTokenGrammar } from "../src/tokens/grammar";
import {
  BOUNDARY_TOKEN_GRAMMAR_POLICY,
  ComposedSubstitutionEngine,
} from "../src/core/orchestrator";
import { deriveDetectorNamespace } from "../src/tokens/namespace";
import { InMemoryReversalStore } from "../src/tokens/reversal";
import { SENTINEL_OPEN, SENTINEL_CLOSE } from "../src/tokens/escaper";
import { isPhiEngineError } from "../src/core/errors";
import { SYNTHETIC_DETECTOR_PREFIX } from "../src/core/orchestrator";
import type { TokenGrammarPolicy } from "../src/tokens/ports";

const NS = "3f9a1c7204b8e561";
const DETECTOR_TOKEN = /^\[\[D~[0-9a-f]{16}~[A-Za-z_]+(?:_\d+)?\]\]$/;

function branded<T>(value: unknown): T {
  return value as T;
}

const grammar = new BracketTokenGrammar();
const policy: TokenGrammarPolicy = BOUNDARY_TOKEN_GRAMMAR_POLICY;

function tagged(
  subjectId: string,
  canonical: string,
  role = "Claimant",
  identifierClass = "PERSON_NAME",
  expander = "person-name",
): TaggedValue {
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

function segments(...texts: readonly string[]): readonly TextSegment[] {
  return texts.map((text, index) => ({
    path: `messages[${index}].content[0].text`,
    kind: branded("user"),
    text,
  }));
}

function engineOf(
  options: CreateSubstitutionEngineOptions = {},
): ReturnType<typeof createSubstitutionEngine> {
  return createSubstitutionEngine({ taggedValues: [], ...options });
}

async function run(
  dev: ReturnType<typeof createSubstitutionEngine>,
  texts: readonly string[],
  detectorRequirement = "DETERMINISTIC_STRUCTURED_ONLY",
): Promise<{
  texts: string[];
  result: Awaited<ReturnType<typeof dev.engine.substitute>>;
}> {
  const result = await dev.engine.substitute({
    context: dev.context,
    policy: {
      ...dev.policy,
      detectorRequirement: branded(detectorRequirement),
    },
    segments: segments(...texts),
    purpose: branded("generation"),
  });
  return { texts: result.segments.map((s) => String(s.text)), result };
}

/** Every `[[...]]` token present in a piece of text, in order. */
function tokensIn(text: string): string[] {
  return [...text.matchAll(/\[\[[^\]]*\]\]/g)].map((m) => m[0]);
}

// ===========================================================================================
describe("GLY-373 namespaced grammar", () => {
  it("GLY373-OR-01: the detector namespace round-trips and every malformed namespace is rejected", () => {
    let rows = 0;

    // --- format -> parse round trip, including the byte-identical authority rows ---
    const accept: readonly [
      string,
      number | null,
      string | undefined,
      string,
    ][] = [
      ["Claimant", null, undefined, "[[Claimant]]"],
      ["SSN", 2, undefined, "[[SSN_2]]"],
      ["SSN", 2, NS, `[[D~${NS}~SSN_2]]`],
      ["SSN", null, NS, `[[D~${NS}~SSN]]`],
      // The tested WORST CASE, included as an exact literal rather than reasoned about:
      // 2 + 2 + 16 + 1 + 18 + 5 + 2 = 46 UTF-16 units, inside the bound of 64 with 18 spare.
      ["Treating_Physician", 9999, NS, `[[D~${NS}~Treating_Physician_9999]]`],
    ];
    for (const [role, sequence, namespace, expected] of accept) {
      rows += 1;
      const token =
        namespace === undefined
          ? grammar.format(branded(role), sequence, policy)
          : grammar.format(branded(role), sequence, policy, namespace);
      expect(String(token)).toBe(expected);
      expect(String(token).length).toBeLessThanOrEqual(
        policy.maximumTokenUtf16Length,
      );
      const parsed = grammar.parse(String(token), policy);
      expect(parsed.kind).toBe("valid");
      if (parsed.kind !== "valid") throw new Error("unreachable");
      expect(parsed.role as unknown as string).toBe(role);
      expect(parsed.sequence).toBe(sequence === 1 ? null : sequence);
      expect(parsed.namespace).toBe(namespace ?? null);
      expect(String(parsed.token)).toBe(expected);
    }
    expect(
      String(grammar.format(branded("Treating_Physician"), 9999, policy, NS))
        .length,
    ).toBe(46);

    // --- BAD_NAMESPACE rejections. The REASON STRING is the assertion, never merely "malformed":
    //     a distinct reason is what proves the namespace was VALIDATED rather than incidentally
    //     rejected by the role or delimiter rules (MUT-03).
    const badNamespace: readonly [string, string][] = [
      [`[[D~3f9a1c7204b8e56~SSN_2]]`, "15 hex"],
      [`[[D~3f9a1c7204b8e5611~SSN_2]]`, "17 hex"],
      [`[[D~3F9A1C7204B8E561~SSN_2]]`, "uppercase hex"],
      [`[[D~3f9a1c7204b8g561~SSN_2]]`, "non-hex"],
      [`[[D~~SSN_2]]`, "empty ns"],
      // PARSE-ORDER ROWS (F-GLY373-G-02). These are exactly the two vectors a delegate-first
      // implementation gets wrong: traced at 8105730, `"SSN~X"` reaches the role branch and yields
      // UNKNOWN_ROLE, and `""` reaches the empty branch and yields BAD_DELIMITER. Both are
      // rejections, so a row asserting only "is malformed" passes against the defect and proves
      // nothing. MUT-38 is killed here and by nothing else.
      [`[[D~${NS}~SSN~X]]`, "third ~ (delegate-first would say UNKNOWN_ROLE)"],
      [
        `[[D~${NS}~]]`,
        "empty remainder (delegate-first would say BAD_DELIMITER)",
      ],
      [`[[D~SSN_2]]`, "no second ~"],
    ];
    for (const [candidate, why] of badNamespace) {
      rows += 1;
      const parsed = grammar.parse(candidate, policy);
      expect(parsed.kind, why).toBe("malformed");
      if (parsed.kind !== "malformed") throw new Error("unreachable");
      expect(parsed.reason, why).toBe("BAD_NAMESPACE");
    }

    // --- the ordering must NOT swallow legitimate delegation: steps 3-5 pass, step 6 decides.
    //     An over-eager namespace layer returning BAD_NAMESPACE for every non-valid inner fails here.
    const delegated: readonly [string, string][] = [
      [`[[D~${NS}~NotARole]]`, "UNKNOWN_ROLE"],
      [`[[D~${NS}~SSN_1]]`, "BAD_SEQUENCE"],
      [`[[D~${NS}~SSN_02]]`, "BAD_SEQUENCE"],
    ];
    for (const [candidate, reason] of delegated) {
      rows += 1;
      const parsed = grammar.parse(candidate, policy);
      expect(parsed.kind, candidate).toBe("malformed");
      if (parsed.kind !== "malformed") throw new Error("unreachable");
      expect(parsed.reason, candidate).toBe(reason);
    }

    // --- format never emits an UNVALIDATED namespace ---
    for (const bad of [
      "3f9a1c7204b8e56",
      "3F9A1C7204B8E561",
      "",
      "zzzz",
      NS + "0",
    ]) {
      rows += 1;
      expect(() => grammar.format(branded("SSN"), 2, policy, bad)).toThrow(
        "token_grammar_bad_namespace",
      );
    }

    expect(rows).toBe(
      accept.length + badNamespace.length + delegated.length + 5,
    );
  });

  // =========================================================================================
  it("GLY373-OR-02: authority-minted tokens are unchanged by the namespace release", async () => {
    const dev = engineOf({
      taggedValues: [
        tagged("s-claimant", "Avery Alpha", "Claimant"),
        tagged("s-ssn", "987-65-4320", "SSN", "SSN", "literal"),
        tagged("s-doc", "Blake Beta", "Treating_Physician"),
      ],
    });
    const { texts, result } = await run(dev, [
      "Avery Alpha saw Blake Beta; SSN 987-65-4320.",
    ]);
    const out = texts[0]!;
    // Byte-identical to 0.2.0 — this is the no-regression oracle for every existing reversal row,
    // embedding, and consumer assertion. MUT-10 namespaces the authority path and reds here.
    expect(out).toContain("[[Claimant]]");
    expect(out).toContain("[[SSN]]");
    expect(out).toContain("[[Treating_Physician]]");
    expect(out).not.toContain("~");
    for (const token of tokensIn(out)) {
      expect(token).not.toContain("~");
    }
    const reversed = String(
      await dev.engine.reverse(
        branded<TokenizedText>(out),
        result.reversalHandle,
      ),
    );
    expect(reversed).toBe("Avery Alpha saw Blake Beta; SSN 987-65-4320.");
  });

  // =========================================================================================
  it("GLY373-OR-03: no detector token can equal an authority token under one reversal key", async () => {
    const shared = new InMemoryReversalStore();
    const sharedAuthority = new InMemoryTokenAssignmentSpy();

    // Engine A — the AUTHORITY path, serving a real tagged SSN subject.
    const a = engineOf({
      operationId: "op-a",
      attemptId: "att-a",
      reversalStore: shared,
      assignmentStore: sharedAuthority,
      taggedValues: [tagged("s-ssn", "987-65-4320", "SSN", "SSN", "literal")],
    });
    const aRun = await run(a, ["SSN 987-65-4320 on file."]);
    const aToken = tokensIn(aRun.texts[0]!)[0]!;

    // Engine B — the DETECTOR path, under a DIFFERENT operationId, over free text.
    const b = engineOf({
      operationId: "op-b",
      attemptId: "att-b",
      reversalStore: shared,
      assignmentStore: sharedAuthority,
      taggedValues: [],
    });
    const bRun = await run(b, ["Contact 987-65-4320 today."]);
    const bToken = tokensIn(bRun.texts[0]!)[0]!;

    expect(aToken).not.toContain("~");
    expect(bToken).toMatch(/^\[\[D~[0-9a-f]{16}~SSN(_\d+)?\]\]$/);
    // The whole point of ruling g6: the two token SPACES are disjoint as STRINGS, therefore
    // disjoint as reversal keys under `tenant ∥ matter ∥ version ∥ token`, with NO key change.
    // MUT-01 (namespace dropped) and MUT-05 (fixed-fail deleted without namespacing) both red here.
    expect(bToken).not.toBe(aToken);

    // Both rows exist under DISTINCT keys and each reverses to its OWN canonical, never the other's.
    expect(
      String(
        await a.engine.reverse(
          branded<TokenizedText>(aToken),
          aRun.result.reversalHandle,
        ),
      ),
    ).toBe("987-65-4320");
    expect(
      String(
        await b.engine.reverse(
          branded<TokenizedText>(bToken),
          bRun.result.reversalHandle,
        ),
      ),
    ).toBe("987-65-4320");

    // Replay B's operation under a THIRD operationId — a third, distinct token. A process-random
    // namespace (MUT-04) is CONSTANT within a process, so it would repeat across these distinct
    // operationIds; the label must vary with operation context.
    const c = engineOf({
      operationId: "op-c",
      attemptId: "att-c",
      reversalStore: shared,
      assignmentStore: sharedAuthority,
      taggedValues: [],
    });
    const cRun = await run(c, ["Contact 987-65-4320 today."]);
    const cToken = tokensIn(cRun.texts[0]!)[0]!;
    expect(cToken).toMatch(/^\[\[D~[0-9a-f]{16}~SSN(_\d+)?\]\]$/);
    expect(cToken).not.toBe(bToken);
    expect(cToken).not.toBe(aToken);
  });

  // =========================================================================================
  it("GLY373-OR-04: injected authority is never called for a synthetic detector subject and detection no longer fixed-fails", async () => {
    const authority = new InMemoryTokenAssignmentSpy();
    const dev = engineOf({ taggedValues: [], assignmentStore: authority });
    // THREE segments, with detectable identifiers distributed across them. The cross-segment pair
    // (segment 1's e-mail vs segment 3's e-mail — same role, different segments) is what proves the
    // ordinal counter is OPERATION-scoped rather than segment-scoped; a single-segment fixture
    // cannot kill MUT-12.
    const { texts, result } = await run(dev, [
      "Write to alpha@example.com about the 3/4/2021 injury.",
      "SSN 123-45-6789 is on file.",
      "Also 987654321 and beta@example.com.",
    ]);

    // (1) SUBSTITUTION SUCCEEDS — this is the F-J1 regression assertion.
    expect(result.segments).toHaveLength(3);

    const all = texts.flatMap(tokensIn);
    expect(all).toHaveLength(5);
    for (const token of all) {
      expect(token).toMatch(DETECTOR_TOKEN);
    }
    // (2) CARDINALITY 5 — every token distinct, explicitly including the cross-segment e-mail pair.
    expect(new Set(all).size).toBe(5);
    const emails = [tokensIn(texts[0]!)[0]!, tokensIn(texts[2]!)[1]!];
    expect(emails[0]).not.toBe(emails[1]);

    // (3) All five share ONE identical namespace label.
    const labels = new Set(
      all.map((t) => /\[\[D~([0-9a-f]{16})~/.exec(t)![1]!),
    );
    expect(labels.size).toBe(1);

    // (4) The injected authority is NEVER touched — GLY-372 §4.4 remains literally true. MUT-11.
    expect(authority.acquisitions).toHaveLength(0);
    expect(authority.retirements).toHaveLength(0);
    expect(JSON.stringify(authority.assigned)).not.toContain("detector");

    // (5) Every detector token reverses to its OWN canonical; the raw identifiers are gone.
    const joined = texts.join("\n");
    for (const raw of [
      "alpha@example.com",
      "3/4/2021",
      "123-45-6789",
      "987654321",
      "beta@example.com",
    ]) {
      expect(joined).not.toContain(raw);
    }
    // EVERY detector token reverses to ITS OWN canonical — all five, not a representative one.
    // Reversing only one segment would leave four of the five mappings unasserted.
    const originals = [
      "Write to alpha@example.com about the 3/4/2021 injury.",
      "SSN 123-45-6789 is on file.",
      "Also 987654321 and beta@example.com.",
    ];
    for (let i = 0; i < texts.length; i += 1) {
      expect(
        String(
          await dev.engine.reverse(
            branded<TokenizedText>(texts[i]!),
            result.reversalHandle,
          ),
        ),
      ).toBe(originals[i]);
    }
  });

  // =========================================================================================
  it("GLY373-OR-04 regression: a hostile formatter returning a VALID AUTHORITY token fails closed", async () => {
    // THIS ROW EXISTS BECAUSE ITS ABSENCE HID A REAL DEFECT, found by the cross-family gate.
    //
    // The success guard checked only `grammar.parse(token).kind === "valid"`. That is NOT enough:
    // a hostile injected formatter can return a perfectly VALID AUTHORITY token — `[[SSN]]` — which
    // passes the validity check and was then spliced into output and RECORDED as a detector
    // mapping, recreating the exact authority/detector collision under one reversal key that the
    // namespace exists to make structurally impossible. The pre-existing hostile-formatter rows
    // covered grammar-INVALID strings and raw PHI, so none of them caught a grammar-VALID token
    // from the WRONG NAMESPACE.
    //
    // The guard now asserts the parsed namespace EQUALS the namespace this call derived, because
    // that is the property §3.2.3's non-collision argument actually relies on.
    const real = new BracketTokenGrammar();
    for (const [why, forged] of [
      ["a valid AUTHORITY token (no namespace)", "[[SSN]]"],
      ["a valid AUTHORITY token with a sequence", "[[SSN_2]]"],
      // A well-formed namespace that is simply NOT this call's — a different operation's label.
      [
        "a valid token under a DIFFERENT namespace",
        `[[D~00000000000000ff~SSN]]`,
      ],
    ] as const) {
      const hostileGrammar = {
        parse: (candidate: string, p: TokenGrammarPolicy) =>
          real.parse(candidate, p),
        scan: (text: string, p: TokenGrammarPolicy) => real.scan(text, p),
        format: () => forged,
      };
      const store = new InMemoryReversalStore();
      // Constructed DIRECTLY: `createSubstitutionEngine` deliberately does NOT expose a `grammar`
      // option (the engine always uses the frozen internal boundary policy and grammar), so passing
      // one through the dev factory is silently ignored and the row would be VACUOUS.
      const engine = new ComposedSubstitutionEngine(
        branded({
          coordinator: {
            requireActiveReady: async () => 1n,
          },
          truthReader: { readTaggedValues: async () => [] },
          sourceTruthRevision: "rev-1",
          reversalStore: store,
          engineVersion: "engine-1",
          grammar: hostileGrammar,
        }),
      );
      let caught: unknown;
      let output: unknown;
      try {
        output = await engine.substitute(
          branded({
            context: {
              tenantId: "t-forge",
              matterId: "m-forge",
              actorId: "a-forge",
              operationId: "op-forge",
              attemptId: "att-forge",
            },
            policy: {
              mode: "REQUIRED",
              locale: "en-US",
              activeDictionaryVersion: 1n,
              schemaVersion: "schema-1",
              detectorRequirement: "DETERMINISTIC_STRUCTURED_ONLY",
              approvedOffDecisionId: null,
            },
            segments: segments("SSN 123-45-6789."),
            purpose: "generation",
          }),
        );
      } catch (error) {
        caught = error;
      }
      expect(output, why).toBeUndefined();
      expect((caught as { code?: string } | undefined)?.code, why).toBe(
        "DICTIONARY_UNAVAILABLE",
      );
      // And NOTHING was recorded — the forged token never became a reversible mapping.
      const map = await store.resolveEncounteredTokens({
        tenantId: branded("t-forge"),
        matterId: branded("m-forge"),
        dictionaryVersion: branded(1n),
        tokens: [branded<SubstitutionToken>(forged)],
      });
      expect(map.size, why).toBe(0);
    }
  });

  // =========================================================================================
  it("GLY373-OR-07: source-literal namespaced tokens are escaped and hostile namespaced tokens fail reversal", async () => {
    const dev = engineOf({ taggedValues: [] });

    // (a) A source document LITERALLY containing a namespaced token round-trips to ITSELF and is
    //     NOT reversible to any canonical. The escaper is grammar-driven, so this works by the
    //     grammar change alone; special-casing the escaper is MUT-14.
    const literal = `Report says [[D~${NS}~SSN_2]] verbatim.`;
    const { texts, result } = await run(dev, [literal]);
    const reversed = String(
      await dev.engine.reverse(
        branded<TokenizedText>(texts[0]!),
        result.reversalHandle,
      ),
    );
    expect(reversed).toBe(literal);

    // (b) Reversing an UNRECORDED namespaced token fails atomically, with no partial DisplayText.
    await expect(
      dev.engine.reverse(
        branded<TokenizedText>(`[[D~${NS}~SSN_7]]`),
        result.reversalHandle,
      ),
    ).rejects.toThrow();

    // (c) A malformed namespace fails CLOSED at reversal — the grammar's BAD_NAMESPACE is inherited
    //     by `reverseText` for free, which is why §3.3 needs no reversal key change.
    await expect(
      dev.engine.reverse(
        branded<TokenizedText>("[[D~ZZZZ~SSN_2]]"),
        result.reversalHandle,
      ),
    ).rejects.toThrow();

    // (d) No residual escape sentinel reaches output. Asserted against the REAL exported constants:
    // an earlier draft hard-coded a raw control character and used the SAME one for both ends, so
    // the close-sentinel assertion was silently checking the open sentinel. Lint caught it as an
    // unused import, which is exactly the kind of quiet oracle weakness that is worth catching.
    // Scoped to the REVERSED (display) output, and deliberately NOT to the tokenized text: the
    // escaper's sentinels are the MECHANISM by which a source literal survives matching, so the
    // tokenized text legitimately carries them until `restoreEscapedLiterals` runs. Asserting on
    // the tokenized text would be asserting against the design; asserting on the display output is
    // the actual invariant — a residual sentinel that never completed into a literal is internal
    // machinery and must never reach a reader.
    expect(reversed).not.toContain(SENTINEL_OPEN);
    expect(reversed).not.toContain(SENTINEL_CLOSE);
  });

  // =========================================================================================
  it("GLY373-OR-10: the namespace digest preimage is injective across field-boundary shifts", () => {
    const NUL = "\u0000";
    const base = {
      tenantId: "t",
      matterId: "m",
      operationId: "o",
      attemptId: "a",
      dictionaryVersion: "1",
    };
    const fields = (f: Record<string, string>): string[] => [
      f.tenantId as string,
      f.matterId as string,
      f.operationId as string,
      f.attemptId as string,
      f.dictionaryVersion as string,
    ];
    /** The BARE-NUL join — the encoding §1 fact 8 proved non-injective for NUL-bearing fields. */
    const nulJoin = (f: Record<string, string>): string => fields(f).join(NUL);
    /** The separatorless concatenation — non-injective for ANY field-boundary shift. */
    const concatJoin = (f: Record<string, string>): string =>
      fields(f).join("");

    // Each pair names the join it actually COLLIDES under, and that join is asserted EQUAL as a
    // positive control, so this test DOCUMENTS the defect it prevents rather than merely passing.
    // Using one join for every row would be wrong: a boundary shift with no NUL involved does not
    // collide under a NUL join, and a NUL-shift does not collide under concatenation. Length
    // prefixing defeats BOTH families, which is the property being asserted. MUT-18 replaces the
    // preimage with a bare join of either kind and reds on the `not.toBe` line.
    const pairs: readonly [
      Record<string, string>,
      Record<string, string>,
      "nul" | "concat",
      string,
    ][] = [
      [
        { ...base, tenantId: "a", matterId: `b${NUL}c` },
        { ...base, tenantId: `a${NUL}b`, matterId: "c" },
        "nul",
        "tenant/matter with an embedded NUL — the §1 fact 8 counterexample, EXECUTED",
      ],
      [
        { ...base, tenantId: "ab", matterId: "c" },
        { ...base, tenantId: "a", matterId: "bc" },
        "concat",
        "tenant/matter boundary shift",
      ],
      [
        { ...base, tenantId: "", matterId: "ab" },
        { ...base, tenantId: "ab", matterId: "" },
        "concat",
        "empty-field boundary shift",
      ],
      [
        { ...base, operationId: `o${NUL}p`, attemptId: "a" },
        { ...base, operationId: "o", attemptId: `p${NUL}a` },
        "nul",
        "operation/attempt NUL shift",
      ],
      [
        { ...base, operationId: "op", attemptId: "1" },
        { ...base, operationId: "o", attemptId: "p1" },
        "concat",
        "operation/attempt boundary shift",
      ],
      [
        { ...base, attemptId: `a${NUL}1`, dictionaryVersion: "2" },
        { ...base, attemptId: "a", dictionaryVersion: `1${NUL}2` },
        "nul",
        "attempt/version NUL shift",
      ],
      [
        { ...base, attemptId: "a1", dictionaryVersion: "2" },
        { ...base, attemptId: "a", dictionaryVersion: "12" },
        "concat",
        "attempt/version boundary shift",
      ],
    ];

    let ran = 0;
    for (const [left, right, control, why] of pairs) {
      ran += 1;
      const join = control === "nul" ? nulJoin : concatJoin;
      expect(join(left), `positive control (${control}): ${why}`).toBe(
        join(right),
      );
      expect(deriveDetectorNamespace(branded(left)), why).not.toBe(
        deriveDetectorNamespace(branded(right)),
      );
    }
    expect(ran).toBe(pairs.length);
    expect(pairs.filter(([, , c]) => c === "nul")).toHaveLength(3);
    expect(pairs.filter(([, , c]) => c === "concat")).toHaveLength(4);
  });

  it("GLY373-OR-13: the namespace label is a known-answer function of exactly the five context fields", () => {
    // (a) KNOWN ANSWER — NORMATIVE LITERALS, transcribed verbatim from the spec, never computed
    //     from the implementation. Preimage `4:t-ka4:m-ka5:op-ka1:11:1` (25 bytes). Independently
    //     reproducible with:
    //       printf '4:t-ka4:m-ka5:op-ka1:11:1' | openssl dgst -sha256 -r | cut -c1-16
    const KAT = {
      tenantId: "t-ka",
      matterId: "m-ka",
      operationId: "op-ka",
      attemptId: "1",
      // `DictionaryVersion` is a branded BIGINT and a non-bigint fixed-fails upstream, so
      // `toString()` is decimal digits only — a literal like "v1" is UNREACHABLE at runtime and
      // must never appear in a KAT vector.
      dictionaryVersion: "1",
    };
    expect(deriveDetectorNamespace(KAT)).toBe("f21ee3934e128fe4");

    // (b) PER-FIELD VARIATION. Each row asserts the EXACT expected label, not merely "differs" —
    //     a derivation that DROPPED a field would still produce *some* differing value for the
    //     other four rows, so "differs" would not prove participation. MUT-21 drops one field per
    //     application and each of the five applications must be killed individually.
    const variations: readonly [string, Record<string, string>, string][] = [
      ["tenantId", { ...KAT, tenantId: "t-ka2" }, "adbd70ff36f2af35"],
      ["matterId", { ...KAT, matterId: "m-ka2" }, "8688108d817dfe8b"],
      ["operationId", { ...KAT, operationId: "op-ka2" }, "69b484d62ae44568"],
      ["attemptId", { ...KAT, attemptId: "2" }, "59c1bac59818c32b"],
      [
        "dictionaryVersion",
        { ...KAT, dictionaryVersion: "2" },
        "bb5a9517d1a905c2",
      ],
    ];
    let ran = 0;
    for (const [field, input, expected] of variations) {
      ran += 1;
      expect(deriveDetectorNamespace(branded(input)), field).toBe(expected);
      expect(deriveDetectorNamespace(branded(input)), field).not.toBe(
        "f21ee3934e128fe4",
      );
    }
    expect(ran).toBe(5);
  });

  it("GLY373-OR-13c: two independently constructed engines derive identical labels and tokens", async () => {
    const shape = {
      tenantId: "t-det",
      matterId: "m-det",
      operationId: "op-det",
      attemptId: "att-det",
      taggedValues: [],
    } as const;
    const one = engineOf({
      ...shape,
      reversalStore: new InMemoryReversalStore(),
    });
    const two = engineOf({
      ...shape,
      reversalStore: new InMemoryReversalStore(),
    });
    const a = await run(one, ["SSN 123-45-6789."]);
    const b = await run(two, ["SSN 123-45-6789."]);
    // Byte-identical detector tokens. Replica identity is irrelevant because the label is derived
    // from the OPERATION, not the process; restart is irrelevant for the same reason. This is the
    // direction of the non-collision argument that MUT-04 (process-random label) breaks.
    expect(tokensIn(a.texts[0]!)).toEqual(tokensIn(b.texts[0]!));
  });

  // =========================================================================================
  it("GLY373-OR-12: detector tokens are namespaced with no authority injected", async () => {
    for (const omitted of [true, false]) {
      const shared = new InMemoryReversalStore();
      const options: CreateSubstitutionEngineOptions = {
        operationId: "op-default-1",
        attemptId: "att-default-1",
        reversalStore: shared,
        taggedValues: [tagged("s-claimant", "Avery Alpha", "Claimant")],
        // Omitted vs EXPLICITLY `undefined` — both must take the default path.
        ...(omitted ? {} : { assignmentStore: undefined }),
      };
      const dev = engineOf(options);
      const { texts } = await run(dev, [
        "Avery Alpha, SSN 123-45-6789, alpha@example.com.",
      ]);
      const tokens = tokensIn(texts[0]!);
      const detector = tokens.filter((t) => t.includes("~"));
      const authority = tokens.filter((t) => !t.includes("~"));
      expect(detector).toHaveLength(2);
      for (const token of detector) {
        expect(token).toMatch(/^\[\[D~[0-9a-f]{16}~(SSN|EMAIL)(_\d+)?\]\]$/);
      }
      // Tagged-subject tokens in the SAME request stay BARE — the namespace applies to the
      // detector space only, in both modes. MUT-10 reds here, MUT-20 reds on the line above.
      expect(authority).toEqual(["[[Claimant]]"]);

      // A SECOND engine over the SHARED reversal store, under a DIFFERENT operationId, mints
      // DIFFERENT detector tokens and does not overwrite the first engine's rows. This is the
      // default-mode collision MUT-20 would leave open and that OR-03/04 (injected-only) miss.
      const peer = engineOf({
        ...options,
        operationId: "op-default-2",
        attemptId: "att-default-2",
      });
      const peerRun = await run(peer, [
        "Avery Alpha, SSN 987-65-4321, alpha@example.com.",
      ]);
      const peerDetector = tokensIn(peerRun.texts[0]!).filter((t) =>
        t.includes("~"),
      );
      expect(peerDetector).toHaveLength(2);
      for (const token of peerDetector) {
        expect(detector).not.toContain(token);
      }
      // The first engine's rows still reverse to THEIR canonicals.
      const map = await shared.resolveEncounteredTokens({
        tenantId: branded(dev.context.tenantId),
        matterId: branded(dev.context.matterId),
        dictionaryVersion: dev.dictionaryVersion,
        tokens: [...detector, ...peerDetector].map((t) =>
          branded<SubstitutionToken>(t),
        ),
      });
      expect(map.size).toBe(4);
    }
  });
});

/** A recording authority that fails the test loudly if it is ever asked for a synthetic subject. */
class InMemoryTokenAssignmentSpy implements TokenAssignmentStore {
  public readonly acquisitions: unknown[] = [];
  public readonly retirements: unknown[] = [];
  public readonly assigned = new Map<string, string>();

  public getOrAllocate(
    input: Parameters<TokenAssignmentStore["getOrAllocate"]>[0],
  ): Promise<SubstitutionToken> {
    this.acquisitions.push({ ...input });
    const identity = [
      input.tenantId,
      input.matterId,
      input.subjectId,
      input.role,
    ].join("\u0000");
    const existing = this.assigned.get(identity);
    if (existing !== undefined) return Promise.resolve(branded(existing));
    const roleKey = `${String(input.tenantId)}\u0000${String(input.matterId)}\u0000${String(input.role)}`;
    const used = [...this.assigned.values()].filter((t) =>
      t.startsWith(`[[${String(input.role)}`),
    ).length;
    void roleKey;
    const ordinal = used + 1;
    const token =
      ordinal === 1
        ? `[[${String(input.role)}]]`
        : `[[${String(input.role)}_${ordinal}]]`;
    this.assigned.set(identity, token);
    return Promise.resolve(branded(token));
  }

  public retire(
    input: Parameters<TokenAssignmentStore["retire"]>[0],
  ): Promise<void> {
    this.retirements.push({ ...input });
    return Promise.resolve();
  }
}

// ===========================================================================================
// OR-GLY373-11 — §3.2.2 ingestion validation, closing BOTH aliasing families.
// ===========================================================================================

const NUL = "\u0000";
const ID_FIELDS = ["tenantId", "matterId", "operationId", "attemptId"] as const;

/** Counts every side effect that MUST NOT happen when ingestion rejects. */
interface SideEffectSpies {
  readonly options: CreateSubstitutionEngineOptions;
  readonly counts: {
    compiles: number;
    records: number;
    acquisitions: number;
  };
}

function spies(taggedValues: readonly TaggedValue[] = []): SideEffectSpies {
  const counts = { compiles: 0, records: 0, acquisitions: 0 };
  const authority = new InMemoryTokenAssignmentSpy();
  const store = new InMemoryReversalStore();
  const wrappedStore = {
    maximumEncounteredTokenBatch: store.maximumEncounteredTokenBatch,
    record: (input: unknown): void => {
      counts.records += 1;
      store.record(branded(input));
    },
    resolveEncounteredTokens: (input: unknown) =>
      store.resolveEncounteredTokens(branded(input)),
  };
  return {
    counts,
    options: {
      taggedValues,
      reversalStore: branded(wrappedStore),
      assignmentStore: branded({
        getOrAllocate: (input: unknown) => {
          counts.acquisitions += 1;
          return authority.getOrAllocate(branded(input));
        },
        retire: (input: unknown) => authority.retire(branded(input)),
      }),
      truthReader: {
        readTaggedValues: (): Promise<readonly TaggedValue[]> => {
          // The truth read is the first thing a dictionary COMPILE does, so a non-zero count here
          // means ingestion let the request reach the compile path.
          counts.compiles += 1;
          return Promise.resolve(taggedValues);
        },
      },
    },
  };
}

/** Drives one `substitute()` and returns the thrown value, never letting it escape the row. */
async function reject(
  options: CreateSubstitutionEngineOptions,
  overrides: Partial<Record<(typeof ID_FIELDS)[number], string>>,
  text = "SSN 123-45-6789.",
): Promise<unknown> {
  const dev = engineOf({ ...options, ...overrides });
  try {
    await dev.engine.substitute({
      context: { ...dev.context, ...overrides },
      policy: {
        ...dev.policy,
        detectorRequirement: branded("DETERMINISTIC_STRUCTURED_ONLY"),
      },
      segments: segments(text),
      purpose: branded("generation"),
    });
    return undefined;
  } catch (error) {
    return error;
  }
}

function expectFixedContextFailure(error: unknown, why: string): void {
  expect(isPhiEngineError(error), why).toBe(true);
  const err = error as {
    code: string;
    name: string;
    operationId: string;
    safeDetails: Record<string, unknown>;
    message: string;
    stack?: string;
  };
  expect(err.code, why).toBe("MISSING_TRUSTED_CONTEXT");
  expect(err.name, why).toBe("PhiEngineError");
  // The FIXED placeholder — never the rejected value's own operation id (MUT-27).
  expect(err.operationId, why).toBe("op-unbound");
  expect(Object.keys(err.safeDetails), why).toEqual([]);
  expect(Object.isFrozen(err), why).toBe(true);
  expect(Object.isFrozen(err.safeDetails), why).toBe(true);
  expect("cause" in (err as object), why).toBe(false);
}

describe("GLY-373 §3.2.2 ingestion validation (OR-GLY373-11)", () => {
  it("GLY373-OR-11: NUL-bearing and ill-formed trusted context is rejected before any key or namespace is derived", async () => {
    // ---------- (a) NUL table: 4 fields x 3 positions = 12 rows ----------
    let nulRows = 0;
    for (const field of ID_FIELDS) {
      for (const [position, value] of [
        ["leading", `${NUL}canary`],
        ["embedded", `can${NUL}ary`],
        ["trailing", `canary${NUL}`],
      ] as const) {
        nulRows += 1;
        const why = `${field} ${position}`;
        const s = spies();
        const error = await reject(s.options, { [field]: value });
        expectFixedContextFailure(error, why);
        // ORDERING IS THE WHOLE GUARANTEE. A check that rejects LATE still leaks the derivation,
        // so these zero counts are the assertion MUT-23 reds on.
        expect(s.counts.compiles, why).toBe(0);
        expect(s.counts.records, why).toBe(0);
        expect(s.counts.acquisitions, why).toBe(0);
      }
    }
    expect(nulRows).toBe(12);

    // ---------- (b) The NUL aliasing counterexample, END TO END ----------
    // These two operations are the §1 fact 8 pair: under the bare-NUL reversal-key join they
    // produce the IDENTICAL key, i.e. two distinct tenants aliasing onto one reversal row. BOTH
    // are now rejected at ingestion, so that row can no longer be created. MUT-19 accepts them.
    const left = await reject(spies().options, {
      tenantId: "a",
      matterId: `b${NUL}c`,
    });
    const right = await reject(spies().options, {
      tenantId: `a${NUL}b`,
      matterId: "c",
    });
    expectFixedContextFailure(left, "alias pair left");
    expectFixedContextFailure(right, "alias pair right");

    // The well-formed control pair SUCCEEDS and produces TWO DISTINCT reversal keys — so the
    // guard rejects ill-formedness, not the shape of the pair.
    const shared = new InMemoryReversalStore();
    const controlA = engineOf({
      tenantId: "a",
      matterId: "bc",
      reversalStore: shared,
    });
    const controlB = engineOf({
      tenantId: "ab",
      matterId: "c",
      reversalStore: shared,
    });
    const runA = await run(controlA, ["SSN 123-45-6789."]);
    const runB = await run(controlB, ["SSN 123-45-6789."]);
    expect(
      String(
        await controlA.engine.reverse(
          branded<TokenizedText>(runA.texts[0]!),
          runA.result.reversalHandle,
        ),
      ),
    ).toBe("SSN 123-45-6789.");
    expect(
      String(
        await controlB.engine.reverse(
          branded<TokenizedText>(runB.texts[0]!),
          runB.result.reversalHandle,
        ),
      ),
    ).toBe("SSN 123-45-6789.");

    // ---------- (c) Lone-surrogate table: 4 fields x 4 vectors = 16 rows, + 4 astral controls ----
    let surrogateRows = 0;
    for (const field of ID_FIELDS) {
      for (const [why, value] of [
        ["leading high surrogate", "\uD800op"],
        ["embedded high surrogate", "op\uD800x"],
        ["trailing high surrogate", "op\uD800"],
        ["lone low surrogate", "op\uDC00"],
      ] as const) {
        surrogateRows += 1;
        const label = `${field} ${why}`;
        const s = spies();
        const error = await reject(s.options, { [field]: value });
        expectFixedContextFailure(error, label);
        expect(s.counts.compiles, label).toBe(0);
        expect(s.counts.records, label).toBe(0);
        expect(s.counts.acquisitions, label).toBe(0);
      }
      // A well-formed ASTRAL-PLANE control (a COMPLETE surrogate pair) MUST SUCCEED: the check
      // rejects ill-formedness, NOT non-BMP characters.
      surrogateRows += 1;
      const ok = await reject(spies().options, { [field]: "op\u{1F600}" });
      expect(ok, `${field} astral control`).toBeUndefined();
    }
    expect(surrogateRows).toBe(20);

    // ---------- (d) The lone-surrogate aliasing counterexample, the exact §3.2.1 vector ----------
    const rejected = await reject(spies().options, { operationId: "op\uD800" });
    expectFixedContextFailure(rejected, "lone-surrogate operationId");
    const accepted = await reject(spies().options, { operationId: "op�" });
    expect(
      accepted,
      "U+FFFD operationId is well-formed and succeeds",
    ).toBeUndefined();

    // DOCUMENTING POSITIVE CONTROL: had BOTH been admitted they would have derived the IDENTICAL
    // label, because `Buffer.from(s,"utf8")` substitutes U+FFFD for a lone surrogate BEFORE the
    // length is taken — so length prefixing cannot rescue it and the well-formedness check is
    // LOAD-BEARING FOR THE INJECTIVITY CLAIM ITSELF, not defence in depth. MUT-22 deletes it.
    const kat = (operationId: string): string =>
      deriveDetectorNamespace({
        tenantId: "t-ka",
        matterId: "m-ka",
        operationId,
        attemptId: "1",
        dictionaryVersion: "1",
      });
    expect(kat("op\uD800")).toBe("74b2c51a28c355a5");
    expect(kat("op�")).toBe("74b2c51a28c355a5");
    expect(kat("op\uD800")).toBe(kat("op�"));

    // ---------- (e) No silent scope creep: SUBJECT ids are deliberately OUT of scope ----------
    // §3.2.2's final paragraph puts subject ids out of scope for the CONTEXT-id guard: they are not
    // part of the namespace preimage or the reversal key, and the reserved detector-subject fence
    // is itself NUL-bearing BY DESIGN, so extending the guard to them would break that fence.
    //
    // SPEC-LETTER DEVIATION, FLAGGED. §3.2.2(e) says a real subject id containing U+0000 "still
    // works". That is FALSE against baseline 8105730 and independent of GLY-373: the COMPILER has
    // rejected NUL-bearing real subject ids since GLY-330 (`dictionary/compiler.ts:228-236`, #6/L1),
    // for the adjacent reason that such an id could share a token-assignment key with a synthetic
    // subject. The row is therefore implemented as what it EXISTS to prove — that the new guard did
    // not creep into subject ids — which is STRONGER than the literal wording: the rejection must
    // come from the PRE-EXISTING compiler rule and must NOT be the new context guard's
    // MISSING_TRUSTED_CONTEXT. Asserting the literal wording would have required weakening a
    // pre-existing security rule, which is never the right trade.
    const subjectSpies = spies([
      tagged(`s${NUL}nul`, "Avery Alpha", "Claimant"),
    ]);
    const subjectError = await reject(
      subjectSpies.options,
      {},
      "Avery Alpha filed.",
    );
    expect(isPhiEngineError(subjectError)).toBe(true);
    // The PRE-EXISTING compiler rule, NOT the new §3.2.2 context guard.
    expect((subjectError as { code: string }).code).not.toBe(
      "MISSING_TRUSTED_CONTEXT",
    );
    expect((subjectError as { code: string }).code).toBe(
      "DICTIONARY_UNAVAILABLE",
    );
    // It reached the COMPILE path — i.e. ingestion accepted the (well-formed) CONTEXT and the
    // subject id was judged by its own rule downstream. A context guard that had crept into
    // subject ids would have rejected at ingestion with zero compiles.
    expect(subjectSpies.counts.compiles).toBeGreaterThan(0);

    // A NUL-FREE subject id still works, so the rule above is about the NUL and nothing else.
    const okSubject = engineOf({
      taggedValues: [tagged("s-ok", "Avery Alpha", "Claimant")],
    });
    const okRun = await run(okSubject, ["Avery Alpha filed."]);
    expect(okRun.texts[0]!).toContain("[[Claimant]]");

    // The reserved synthetic-detector fence is NUL-bearing BY DESIGN and is untouched.
    expect(SYNTHETIC_DETECTOR_PREFIX).toContain(NUL);
  });
});
