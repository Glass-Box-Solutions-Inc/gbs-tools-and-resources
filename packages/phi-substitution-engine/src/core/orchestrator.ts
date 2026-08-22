/**
 * Composed substitution orchestrator (CONTRACT-phase1 §4.1 steps 2/5/6/8/11,
 * invariants N4/N5/L1/L2/L3/L6/L8/L10).
 *
 * This is the `PhiSubstitutionEngine` the protected wrapper drives. It COMPOSES
 * the already-frozen leaves and never re-invents them:
 *   - `../dictionary` : the READY-version coordinator (L2/N4 readiness gate), the
 *                       tagged-truth reader, the matter-dictionary COMPILER
 *                       (variant expansion + subject-scoped tokens + Aho–Corasick,
 *                       L1/L3/L10), and `tokenize` (C1–C8 match-time resolution);
 *   - `../collision`  : deterministic structured-identifier detection + canonical
 *                       normalization;
 *   - `../tokens`     : the source-token escaper (L6), the SUBJECT-scoped token
 *                       assignment store (L1), the tenant-scoped reversal store
 *                       (L8/N5), the atomic reverser, and the M-1 holdback
 *                       reverse stream (L4).
 *
 * Matching + substitution (NEW-1): the orchestrator matches and substitutes using
 * the compiler's COMPILED, variant-expanded, Aho–Corasick output — so an approved
 * surface form such as `Smith, Alice` for canonical `Alice Smith` is substituted,
 * never egressed raw. Class-blind `runCollision` is no longer on the egress path.
 *
 * Token identity (L1, #6): the compiler assigns a stable SUBJECT-scoped token for
 * every tagged subject of EVERY class (person AND structured id) via the shared
 * token assignment store. Detector-only structured spans (no trusted subject) are
 * allocated tokens through the SAME store under an OPERATION-scoped SYNTHETIC
 * subject in a reserved namespace that can never collide with a real subject id,
 * so a real subject and a synthetic detector span never share a reversal key.
 *
 * TWO DIFFERENT THINGS ARE BOTH CALLED "THE DETECTOR" (GLY-373 §1 fact 3 — the previous
 * wording here was true of the belt and was read as covering both, which is how F-J1 hid):
 *   - the phase-1 detector BELT (`../detectors`) is the pluggable ML/service detector. It is
 *     DISABLED and is never called for a customer claim; a policy that REQUIRES it fails closed
 *     (N4). `detectorRequirement === "REQUIRED"` is the only value that reaches that fail.
 *   - the DETERMINISTIC STRUCTURED-IDENTIFIER detector (`../collision/detectors.ts`) is a
 *     separate, in-engine regex pass. At 0.2.0 it was UNCONDITIONAL. GLY-373 §4.2 makes it
 *     policy-governed and exhaustively fail-closed: it RUNS under
 *     `"DETERMINISTIC_STRUCTURED_ONLY"` and its deprecated alias `"DISABLED_PHASE_1"`, is NOT
 *     INVOKED AT ALL under `"STRUCTURED_DETECTION_OFF"` (suppression is non-invocation, never
 *     filtering — MUT-06), and any unrecognised value fails closed with `MISSING_TRUSTED_POLICY`
 *     before any dictionary work (MUT-07).
 *
 * Detector-only spans are substituted with NAMESPACED tokens (`[[D~<16 hex>~Role_N]]`, GLY-373
 * §3.1) in BOTH injected and default mode. The namespace makes a detector token structurally
 * incapable of equalling an authority token under the operation-blind reversal key, which is what
 * the 0.2.0 injected-mode fixed-fail existed to protect; that fixed-fail is therefore deleted and
 * replaced by this path, never merely removed (MUT-05).
 */
import type {
  DictionaryVersion,
  DisplayText,
  EngineVersion,
  SubstitutionToken,
  TokenizedText,
  TokenRole,
  TenantId,
  MatterId,
  OperationId,
  OperationAttemptId,
} from "./brands";
import type {
  IdentifierClass,
  PhiEngineFailureCode,
  PhiSubstitutionEngine,
  ReversalHandle,
  ReversalWriteStore,
  ReverseStream,
  SubstitutionRequest,
  SubstitutionResult,
  TextSegmentKind,
  TokenizedTextSegment,
} from "./contracts";
import type {
  CaseTruthReader,
  CompiledDictionaryCache,
  DictionaryVersionCoordinator,
} from "../dictionary/contracts";
import type {
  EscapedTokenLiteral,
  TokenAssignmentStore,
  TokenGrammarPolicy,
} from "../tokens/ports";
import { isDictionaryError } from "../dictionary/errors";
import { canonicalize, detectStructuredIdentifiers } from "../collision/index";
import { MatterDictionaryCompiler } from "../dictionary/compiler";
import {
  getOrCompile,
  tokenize,
  type DetectorSpanInput,
} from "../dictionary/tokenize";
import { InMemoryCompiledDictionaryCache } from "../dictionary/cache";
import { TokensLeafAssignmentPort } from "../dictionary/token-port";
import type { AhoCorasickCompiledDictionary } from "../dictionary/compiled-dictionary";
import {
  BracketTokenGrammar,
  frozenRoleSet,
  HoldbackReverseStreamFactory,
  InMemoryTokenAssignmentStore,
  InProcessReversalHandle,
  isInProcessReversalHandle,
  SentinelSourceTokenEscaper,
  SENTINEL_OPEN,
  SENTINEL_CLOSE,
  reverseText,
} from "../tokens/index";
import { toTotalIdentifierCounts } from "../audit/index";
import {
  PhiEngineError,
  safeCodeString,
  isPhiEngineError,
  assertTrustedContextIdShape,
  missingTrustedContextError,
} from "./errors";
import { deriveDetectorNamespace } from "../tokens/namespace";
import {
  REVERSAL_CANONICAL_CONFLICT,
  REVERSAL_CANONICAL_CONFLICT_DETAIL,
} from "../tokens/conflict-sentinel";
import { safeRead, safeString, intrinsicCopy } from "./boundary-snapshot";

/** Token role → identifier class, used to tally per-class counts from tokenized output. */
const ROLE_CLASS: Readonly<Record<string, IdentifierClass>> = {
  Claimant: "PERSON_NAME",
  Witness: "PERSON_NAME",
  Treating_Physician: "PERSON_NAME",
  Adjuster: "PERSON_NAME",
  Employer: "PERSON_NAME",
  Person: "PERSON_NAME",
  DOB: "DOB",
  SSN: "SSN",
  MRN: "MRN",
  DEA: "DEA",
  EMAIL: "EMAIL",
  PHONE: "PHONE",
  ADDRESS: "ADDRESS",
  Address: "ADDRESS",
  CLAIM: "CLAIM_NUMBER",
  POLICY: "POLICY_NUMBER",
  ACCOUNT: "ACCOUNT_NUMBER",
  OTHER: "OTHER_TAGGED",
};

/** Identifier class → token role for a detector-only structured span. */
const CLASS_ROLE: Readonly<Record<IdentifierClass, string>> = {
  PERSON_NAME: "Claimant",
  DOB: "DOB",
  SSN: "SSN",
  MRN: "MRN",
  DEA: "DEA",
  EMAIL: "EMAIL",
  PHONE: "PHONE",
  ADDRESS: "ADDRESS",
  CLAIM_NUMBER: "CLAIM",
  POLICY_NUMBER: "POLICY",
  ACCOUNT_NUMBER: "ACCOUNT",
  OTHER_TAGGED: "OTHER",
};

/**
 * Reserved, NUL-fenced namespace for detector-only synthetic subjects (#6). Real
 * subject ids come from tagged case truth and are never NUL-prefixed, so a synthetic
 * subject can never share an assignment key with a real one — even a real id that
 * happens to look like the old `det:op:ordinal` shape.
 *
 * GLY-373 §3.2.3 (ordinal source) REMOVED ITS LAST USE, and that is strictly stronger than the
 * fence it provided: detector ordinals now come from the per-operation counter and detector tokens
 * are formatted locally through `grammar.format(role, seq, policy, ns)`, so
 * `getOrAllocate`/`retire` are NEVER called for a synthetic subject on ANY store, injected or not
 * (GLY-372 §4.4 and OR-GLY372-09 remain literally true; OR-GLY373-04 asserts both counts are zero,
 * and MUT-11 restores the old allocation and must go RED). It is RETAINED as the record of that
 * fence — subject ids are deliberately out of scope for the §3.2.2 NUL check precisely because
 * this prefix is itself NUL-bearing by design (OR-GLY373-11(e)).
 */
export const SYNTHETIC_DETECTOR_PREFIX = "\u0000detector\u0000";

const role = (value: string): TokenRole => value as unknown as TokenRole;

/**
 * Grammar policy for the boundary. Roles are the trusted allow-list for both the
 * structured-id class tokens (`[[MRN]]`, `[[ADDRESS]]`, ...) and the person/role
 * tokens (`[[Claimant]]`, ...). Reversal validates every token-like sequence
 * against this policy; an off-registry shape fails visibly.
 */
// §7/N2 (GLY-336 gate, finding 2): DEEP-FROZEN. The allow-list is the fixed, PHI-free set of
// structural roles (person roles + structured-id classes). Freezing the policy object AND its role
// Set makes it immutable, so no in-process actor can add a PHI-bearing role that would let the
// grammar emit a raw value as a "token". The engine's token policy is not caller-overridable.
export const BOUNDARY_TOKEN_GRAMMAR_POLICY: TokenGrammarPolicy = Object.freeze({
  allowedRoles: frozenRoleSet(
    [
      "Claimant",
      "Witness",
      "Treating_Physician",
      "Adjuster",
      "Employer",
      "Person",
      "DOB",
      "SSN",
      "MRN",
      "DEA",
      "EMAIL",
      "PHONE",
      "ADDRESS",
      "Address",
      "CLAIM",
      "POLICY",
      "ACCOUNT",
      "OTHER",
    ].map(role),
  ),
  maximumTokenUtf16Length: 64,
  maximumRoleUtf16Length: 48,
  maximumSequence: 9999,
});

export interface ComposedSubstitutionEngineDeps {
  /** Dictionary L2/N4 readiness gate. */
  readonly coordinator: DictionaryVersionCoordinator;
  /** Dictionary tagged-truth source (schema-tagged case truth). */
  readonly truthReader: CaseTruthReader;
  /** Constant per-matter truth revision the wrapper reads under. */
  readonly sourceTruthRevision: string;
  /**
   * Tenant-scoped reversal WRITE port (GLY-335 seam; roadmap defect A#3). The engine depends on
   * the `ReversalWriteStore` interface — record + encounter-bounded resolve — never a concrete
   * store class, so the durable §6 store swaps in without re-typing core. `InMemoryReversalStore`
   * is the in-process dev implementation and may be pre-seeded by callers.
   */
  readonly reversalStore: ReversalWriteStore;
  readonly engineVersion: EngineVersion;
  readonly grammar?: BracketTokenGrammar;
  readonly tokenPolicy?: TokenGrammarPolicy;
  readonly streamFactory?: HoldbackReverseStreamFactory;
  /**
   * Subject/operation-scoped token allocator (L1). Stable per tenant+matter+subject+role.
   * A persistent (restart-safe) store keeps ordinals monotonic across operations so two
   * operations' detector-only tokens never collide on the operation-blind reversal key.
   */
  readonly assignmentStore?: TokenAssignmentStore;
}

export class ComposedSubstitutionEngine implements PhiSubstitutionEngine {
  readonly #coordinator: DictionaryVersionCoordinator;
  readonly #truthReader: CaseTruthReader;
  readonly #sourceTruthRevision: string;
  readonly #reversalStore: ReversalWriteStore;
  readonly #engineVersion: EngineVersion;
  readonly #grammar: BracketTokenGrammar;
  readonly #policy: TokenGrammarPolicy;
  readonly #streamFactory: HoldbackReverseStreamFactory;
  readonly #escaper: SentinelSourceTokenEscaper;
  readonly #assignmentStore: TokenAssignmentStore;
  readonly #injectedAssignmentStore: boolean;
  readonly #compiler: MatterDictionaryCompiler;
  readonly #cache: CompiledDictionaryCache | null;

  public constructor(deps: ComposedSubstitutionEngineDeps) {
    this.#coordinator = deps.coordinator;
    this.#truthReader = deps.truthReader;
    this.#sourceTruthRevision = deps.sourceTruthRevision;
    this.#reversalStore = deps.reversalStore;
    this.#engineVersion = deps.engineVersion;
    this.#grammar = deps.grammar ?? new BracketTokenGrammar();
    this.#policy = deps.tokenPolicy ?? BOUNDARY_TOKEN_GRAMMAR_POLICY;
    this.#streamFactory =
      deps.streamFactory ?? new HoldbackReverseStreamFactory();
    this.#escaper = new SentinelSourceTokenEscaper(this.#grammar);
    this.#injectedAssignmentStore = deps.assignmentStore !== undefined;
    this.#assignmentStore = this.#injectedAssignmentStore
      ? deps.assignmentStore!
      : new InMemoryTokenAssignmentStore(this.#grammar, this.#policy);
    // The compiler allocates subject tokens through the SAME shared assignment store, so
    // dictionary and detector-only tokens share one monotonic ordinal space (L1/#6) and
    // handle EVERY identifier class (not just the five person roles).
    this.#compiler = new MatterDictionaryCompiler(
      this.#truthReader,
      () =>
        new TokensLeafAssignmentPort(
          this.#assignmentStore,
          this.#grammar,
          this.#policy,
        ),
    );
    // NEW-B/L1: the warm cache is INTERNAL and lifecycle-coupled to THIS engine's assignment
    // store. It is never injectable/shareable, so a compiled dictionary is never served against a
    // different (fresh) assignment namespace — which would let a detector-only token collide with a
    // cached real-subject token. Warm reuse still happens across requests on the same engine.
    this.#cache = this.#injectedAssignmentStore
      ? null
      : new InMemoryCompiledDictionaryCache();
  }

  /**
   * §7/N2: read the request's caller-derived CONTEXT scalars EXACTLY ONCE, getter-throw-safe, into an
   * inert record. This runs BEFORE any error can be constructed, so a hostile `operationId` getter (or
   * any of the four) cannot re-throw a raw (PHI) message out of the fail-closed path — an invalid
   * envelope fails closed with a FIXED code and NO caller-supplied operation id.
   */
  #ingestContext(request: SubstitutionRequest): {
    tenantId: TenantId;
    matterId: MatterId;
    operationId: OperationId;
    attemptId: OperationAttemptId;
  } {
    const context = safeRead(request, "context");
    const tenantId = safeString(context, "tenantId");
    const matterId = safeString(context, "matterId");
    const operationId = safeString(context, "operationId");
    const attemptId = safeString(context, "attemptId");
    if (
      tenantId === undefined ||
      matterId === undefined ||
      operationId === undefined ||
      attemptId === undefined
    ) {
      throw new PhiEngineError("MISSING_TRUSTED_CONTEXT");
    }
    // GLY-373 §3.2.2 — ENTRY POINT 1 of 3. Reject NUL-bearing and ill-formed-UTF-16 routing ids
    // BEFORE the namespace derivation, the readiness gate, and any reversal write, on the
    // ALREADY-SNAPSHOTTED locals above (never by re-reading the request — that is the TOCTOU hole
    // MUT-30/MUT-31 exploit). Ordering is the whole guarantee: a late check still leaks the
    // derivation (MUT-23). This is the first code that actually establishes the injectivity the
    // NUL joins in `tokens/durable/keys.ts` and `tokens/reversal.ts` have always merely asserted.
    assertTrustedContextIdShape("tenantId", tenantId);
    assertTrustedContextIdShape("matterId", matterId);
    assertTrustedContextIdShape("operationId", operationId);
    assertTrustedContextIdShape("attemptId", attemptId);
    return {
      tenantId: tenantId as unknown as TenantId,
      matterId: matterId as unknown as MatterId,
      operationId: operationId as unknown as OperationId,
      attemptId: attemptId as unknown as OperationAttemptId,
    };
  }

  /**
   * §7/N2: copy the request's `segments` by OWN index/length and read each segment's `text`/`path`/
   * `kind` field EXACTLY ONCE, getter-throw-safe, into inert plain data. A NON-array carrier, an OWN
   * poisoned `Symbol.iterator`, a throwing/mutating field getter, or a non-string field fails closed
   * here rather than iterating live getters downstream (which could show one value to the matcher and
   * a raw PHI value to a later read, or throw raw out of this method).
   */
  #ingestSegments(
    request: SubstitutionRequest,
    operationId: OperationId,
  ): { text: string; path: string; kind: TextSegmentKind }[] {
    const rawSegments = intrinsicCopy<unknown>(safeRead(request, "segments"));
    if (rawSegments === null) {
      throw new PhiEngineError("MISSING_TRUSTED_CONTEXT", operationId);
    }
    const segments: { text: string; path: string; kind: TextSegmentKind }[] =
      [];
    for (let i = 0; i < rawSegments.length; i += 1) {
      const raw = rawSegments[i];
      const text = safeString(raw, "text");
      const path = safeString(raw, "path");
      const kind = safeString(raw, "kind");
      if (text === undefined || path === undefined || kind === undefined) {
        throw new PhiEngineError("MISSING_TRUSTED_CONTEXT", operationId);
      }
      segments[segments.length] = { text, path, kind: kind as TextSegmentKind };
    }
    return segments;
  }

  public async substitute(
    request: SubstitutionRequest,
  ): Promise<SubstitutionResult> {
    // §7/N2: snapshot the caller-derived context + segments ONCE at ingestion so nothing downstream
    // ever touches a live (possibly PHI-throwing / mutating) getter on the request envelope.
    const context = this.#ingestContext(request);
    const segments = this.#ingestSegments(request, context.operationId);
    // §7/N2: read the policy scalars the engine consumes OUTSIDE the compile guard ONCE, getter-throw-
    // safe. A throwing `policy.locale`/`detectorRequirement` getter (a hostile direct caller) must fail
    // closed with a FIXED code, never propagate raw. (The whole `request.policy` is still handed to
    // getOrCompile, but that runs inside the fixed-closed compile try/catch below.)
    const policy = safeRead(request, "policy");
    const locale = safeString(policy, "locale");
    const detectorRequirement = safeString(policy, "detectorRequirement");
    if (locale === undefined || detectorRequirement === undefined) {
      throw new PhiEngineError(
        "MISSING_TRUSTED_POLICY",
        context.operationId,
        {},
      );
    }
    // GLY-373 §4.2 — EXHAUSTIVE AND FAIL-CLOSED, validated at the same point the value is read
    // (§4.2(5): read exactly once, getter-throw-safe, via `safeString` above; no re-read anywhere,
    // MUT-15). Comparison is against four FIXED LITERALS — no `Array.prototype.includes`, no
    // `Set.prototype.has` — so a poisoned intrinsic cannot divert the decision. An unrecognised
    // string (hostile, or a future value on an older engine) reaches `MISSING_TRUSTED_POLICY`
    // HERE, before the readiness gate, so a bad policy costs no dictionary work and there is no
    // permissive default and no "treat unknown as off" (MUT-07).
    const runDeterministicDetection =
      detectorRequirement === "DETERMINISTIC_STRUCTURED_ONLY" ||
      // DEPRECATED ALIAS (AMB-GLY373-05): retained for pin compatibility, byte-identical
      // behaviour to the canonical name. Making it mean hard suppression is MUT-08.
      detectorRequirement === "DISABLED_PHASE_1";
    const suppressDeterministicDetection =
      detectorRequirement === "STRUCTURED_DETECTION_OFF";
    const requiresDetectorBelt = detectorRequirement === "REQUIRED";
    if (
      !runDeterministicDetection &&
      !suppressDeterministicDetection &&
      !requiresDetectorBelt
    ) {
      throw new PhiEngineError(
        "MISSING_TRUSTED_POLICY",
        context.operationId,
        {},
      );
    }

    // §4.1 step 2 / L2 / N4: require an active READY dictionary version.
    let dictionaryVersion: DictionaryVersion;
    try {
      dictionaryVersion = await this.#coordinator.requireActiveReady({
        tenantId: context.tenantId,
        matterId: context.matterId,
      });
    } catch (error) {
      if (isDictionaryError(error)) {
        // §7/N2: read the code getter-throw-safe; `mapDictionaryFailure` already collapses any
        // unrecognized value to a fixed code, so a hostile `.code` can never ride the failure.
        throw new PhiEngineError(
          mapDictionaryFailure(safeCodeString(error) ?? ""),
          context.operationId,
          {},
        );
      }
      // §7/N2: an unexpected non-DictionaryError (or a hostile Proxy `isDictionaryError` rejected)
      // must never surface a raw message/code — fail closed with a fixed code.
      throw new PhiEngineError(
        "DICTIONARY_UNAVAILABLE",
        context.operationId,
        {},
      );
    }
    // §7/N2: the injected coordinator's SUCCESS value is UNTRUSTED — a non-`bigint` (e.g. a PHI string)
    // must NOT be returned to the caller as SubstitutionResult.dictionaryVersion. Require a bigint.
    if (typeof (dictionaryVersion as unknown) !== "bigint") {
      throw new PhiEngineError(
        "DICTIONARY_UNAVAILABLE",
        context.operationId,
        {},
      );
    }

    // N4: phase-1 has no detection belt wired. A policy that REQUIRES it cannot be
    // satisfied, so we fail closed rather than brand untagged free text as safe.
    if (requiresDetectorBelt) {
      throw new PhiEngineError("DETECTOR_UNAVAILABLE", context.operationId, {});
    }

    // §4.1 steps 2/6 / L3/L10: compile the matter dictionary — variant-expanded surface
    // forms + subject-scoped tokens + the Aho–Corasick automaton. Subject tokens are
    // stable across compiles because the shared assignment store owns their identity.
    let compiled: AhoCorasickCompiledDictionary;
    try {
      // L9 / NEW-B: the WARM-CACHE serving path — a compiled dictionary for this
      // tenant+matter+version+engine+schema is reused instead of recompiled on every request.
      const compileInput = {
        tenantId: context.tenantId,
        matterId: context.matterId,
        policy: request.policy,
        dictionaryVersion,
        engineVersion: this.#engineVersion,
        schemaVersion: request.policy.schemaVersion,
        sourceTruthRevision: this.#sourceTruthRevision,
      };
      compiled =
        this.#cache === null
          ? ((await this.#compiler.compile(
              compileInput,
            )) as AhoCorasickCompiledDictionary)
          : await getOrCompile(this.#cache, this.#compiler, compileInput);
    } catch (error) {
      if (isDictionaryError(error)) {
        throw new PhiEngineError(
          mapDictionaryFailure(safeCodeString(error) ?? ""),
          context.operationId,
          {},
        );
      }
      // §7/N2: an unexpected non-DictionaryError must never surface a raw message/code — fail closed.
      throw new PhiEngineError(
        "DICTIONARY_UNAVAILABLE",
        context.operationId,
        {},
      );
    }

    const started = performance.now();
    const tokenizedSegments: TokenizedTextSegment[] = [];
    const counts: Partial<Record<IdentifierClass, number>> = {};
    const literals: EscapedTokenLiteral[] = [];
    // Operation-scoped and monotonic across ALL segments of this call so two detector
    // spans in one operation never mint the same token. Resetting this inside the segment loop
    // is MUT-12, which OR-GLY373-04's THREE-segment fixture exists to catch.
    let detectorOrdinal = 0;
    // GLY-373 §3.2.1: derived ONCE per `substitute()` call, before the segment loop, from exactly
    // five trusted context scalars over a length-prefixed (netstring) preimage. Derived in BOTH
    // injected and default mode (§4.2(4) / AMB-GLY373-01) — a mode-conditional namespace is
    // MUT-20 and leaves the default-mode shared-store collision open. `dictionaryVersion` is a
    // branded bigint here (a non-bigint fixed-failed above), so `toString()` is decimal digits.
    const detectorNamespace = deriveDetectorNamespace({
      tenantId: String(context.tenantId),
      matterId: String(context.matterId),
      operationId: String(context.operationId),
      attemptId: String(context.attemptId),
      dictionaryVersion: dictionaryVersion.toString(),
    });

    for (const segment of segments) {
      // §4.1 step 5 / L6: escape reserved token-shaped source text BEFORE matching, so a
      // caller cannot inject a `[[Role]]` shape and have it reversed to a value. Sentinel
      // indices are re-based to GLOBAL positions so a single restore pass on the reversed
      // output is unambiguous across segments.
      const escaped = this.#escaper.escape(segment.text, this.#policy);
      const base = literals.length;
      const sourceText = this.#rebaseSentinels(String(escaped.text), base);
      literals.push(...escaped.literals);

      // §4.1 step 7 / L1 / #6: allocate an OPERATION-scoped token (through the shared store,
      // under a reserved synthetic-subject namespace) for every deterministic structured-id
      // span, so a detector-only span never coalesces with a real subject.
      const detectorCanonicalByToken = new Map<string, string>();
      const detectorSpans: DetectorSpanInput[] = [];
      // GLY-373 §4.2(1): SUPPRESSION IS NON-INVOCATION, NOT FILTERING. Under
      // `STRUCTURED_DETECTION_OFF` this call MUST NOT EXECUTE — calling it and discarding the
      // spans is unnecessary work over PHI-bearing text AND makes the suppression untestable by
      // call count. OR-GLY373-05 asserts a spy call count of ZERO, so a filtering implementation
      // fails (MUT-06).
      //
      // GLY-373 §4.2(3): the 0.2.0 injected-mode fixed-fail that stood here is DELETED, and is
      // replaced by NOTHING EXCEPT the namespaced allocation below. Deleting it without shipping
      // the namespace is MUT-05 — the single most dangerous possible mis-implementation of this
      // ticket, since detector and authority tokens would then collide on one reversal key.
      const detectedSpans = runDeterministicDetection
        ? detectStructuredIdentifiers(sourceText)
        : [];
      for (const span of detectedSpans) {
        detectorOrdinal += 1;
        // GLY-373 §3.2.3 (ordinal source) + §5: the detector token is formatted LOCALLY, from the
        // per-operation ordinal and this call's namespace — NEVER through
        // `#assignmentStore.getOrAllocate`. That is what keeps GLY-372 §4.4 literally true (the
        // injected authority is never called for a synthetic subject) WHILE STILL SUBSTITUTING.
        // The namespace, not the store, is what makes the ordinals safe. MUT-11 restores the
        // allocation and must go RED on OR-GLY373-04's zero-authority-call assertions.
        //
        // The grammar is an injected dep, so its `format` is UNTRUSTED: a throw (whose message
        // could carry PHI) fails closed with the same FIXED code a failed allocation used.
        let token: unknown;
        try {
          token = this.#grammar.format(
            CLASS_ROLE[span.identifierClass] as unknown as TokenRole,
            detectorOrdinal === 1 ? null : detectorOrdinal,
            this.#policy,
            detectorNamespace,
          );
        } catch {
          throw new PhiEngineError(
            "DICTIONARY_UNAVAILABLE",
            context.operationId,
            {},
          );
        }
        // §7/N2 + GLY-373 §5: the formatter's SUCCESS return is UNTRUSTED and this guard is
        // RETAINED VERBATIM for the locally-formatted detector token — a token is spliced into
        // output ONLY after `grammar.parse(...).kind === "valid"`. A hostile internal formatter
        // returning a grammar-invalid string (`[[D~ZZZZ~SSN_2]]`) or a raw-PHI string would
        // otherwise reach `SubstitutionResult.segments[].text` and the reversal record. Dropping
        // this guard is MUT-13. Guarding only the REJECTION
        // (above) still lets a hostile allocation escape two ways: a non-string carrier whose
        // `Symbol.toPrimitive`/`toString` throws raw (PHI) out of `String(token)` below (sink c),
        // and a returned raw-PHI STRING that becomes the detector token spliced into the output
        // (SubstitutionResult.segments[].text, sink a) and enters compiled/scanned entries — both
        // SUCCESS paths, so the compile/tokenize catch blocks never contain them. Require a genuine,
        // GRAMMAR-VALID token (the real store returns `grammar.format()` output, always valid, so no
        // legitimate allocation is rejected); a bracketed token can only carry an allow-listed role +
        // numeric sequence, structurally incapable of holding raw PHI. Anything else fails closed with
        // the same fixed code as a rejection.
        //
        // GRAMMAR-VALIDITY ALONE IS NOT ENOUGH, and treating it as enough was a defect. A hostile
        // formatter can return a perfectly VALID AUTHORITY token — `[[SSN]]` — which passes
        // `kind === "valid"` and is then spliced into output and recorded, recreating the very
        // authority/detector collision under one reversal key that §3.2.3 exists to make
        // structurally impossible. The parsed namespace MUST therefore equal the namespace this
        // call derived: that is the property being relied on, so that is the property to assert.
        const parsedToken =
          typeof token === "string"
            ? this.#grammar.parse(token, this.#policy)
            : undefined;
        if (
          parsedToken === undefined ||
          parsedToken.kind !== "valid" ||
          parsedToken.namespace !== detectorNamespace
        ) {
          throw new PhiEngineError(
            "DICTIONARY_UNAVAILABLE",
            context.operationId,
            {},
          );
        }
        const start = span.startUtf16 as unknown as number;
        const end = span.endUtf16 as unknown as number;
        detectorCanonicalByToken.set(
          String(token),
          canonicalize(sourceText.slice(start, end)),
        );
        detectorSpans.push({
          startUtf16: start,
          endUtf16: end,
          identifierClass: span.identifierClass,
          confidence: span.confidence,
          token: String(token),
        });
      }

      // §4.1 steps 6/8 / L3/L12: the compiled matcher + C1–C8 resolver produce the
      // tokenized text (dictionary identity overrides overlapping detector spans).
      let tokenizedText: string;
      try {
        tokenizedText = tokenize(
          compiled,
          sourceText,
          locale,
          detectorSpans,
          this.#grammar,
          this.#policy,
        ).tokenizedText;
      } catch (error) {
        if (isDictionaryError(error)) {
          // C6 ambiguity → fail closed; a known value is never guessed.
          throw new PhiEngineError(
            "AMBIGUOUS_KNOWN_IDENTIFIER",
            context.operationId,
            {},
          );
        }
        // §7/N2: an unexpected non-DictionaryError must never surface a raw message/code — fail closed.
        throw new PhiEngineError(
          "DICTIONARY_UNAVAILABLE",
          context.operationId,
          {},
        );
      }

      // §4.1 step 8 / N5: record each output token → its CURRENT canonical value, and tally
      // per-class counts from the tokens actually present in the output.
      for (const span of this.#grammar.scan(tokenizedText, this.#policy)) {
        if (span.parsed.kind !== "valid") {
          continue;
        }
        const token: SubstitutionToken = span.parsed.token;
        const canonical =
          compiled.canonicalForToken(String(token)) ??
          detectorCanonicalByToken.get(String(token));
        if (canonical === undefined) {
          continue;
        }
        // §7/N2: the injected reversal store is UNTRUSTED — a `record()` throw OR promise rejection
        // (its message could carry PHI) must fail closed with a FIXED code, never propagate raw out of
        // substitute. §6: awaiting `record` makes the mapping DURABLE before this tokenized text is
        // returned for egress — a token is never egressed without exactly one durable reversible mapping.
        try {
          await this.#reversalStore.record({
            tenantId: context.tenantId,
            matterId: context.matterId,
            dictionaryVersion,
            token,
            canonical,
            // §6/§3.1.3 idempotency key: a replayed attempt is a no-op, never a duplicate/divergent mapping.
            attemptId: context.attemptId,
          });
        } catch (caught) {
          // GLY-373 §3.2.6 — PHI-SCRUB SEAM S2. Exactly ONE disposition passes through, and it
          // passes by IDENTITY against a module-private binding: not by `code`, `name`, `message`,
          // `instanceof`, or a duck-type check, any of which an untrusted injected store could
          // forge to ride its own error out (OR-16(b)'s forged rows exist for precisely that).
          // A FRESH frozen error is constructed here; the sentinel itself never reaches the caller
          // (OR-16(d)), `safeDetails`, a log, or the audit record — only the fixed literals do.
          if (caught === REVERSAL_CANONICAL_CONFLICT) {
            const conflict = new PhiEngineError(
              "AMBIGUOUS_KNOWN_IDENTIFIER",
              context.operationId,
              { conflict: REVERSAL_CANONICAL_CONFLICT_DETAIL },
            );
            Object.freeze(conflict.safeDetails);
            Object.freeze(conflict);
            throw conflict;
          }
          // On EVERY non-match the existing blanket scrub is UNCHANGED, VERBATIM: the caught value
          // is discarded — never inspected, read from, re-thrown, chained, or wrapped — and a
          // fresh fixed error is constructed exactly as before. Weakening this is MUT-37(b).
          throw new PhiEngineError("REVERSAL_FAILED", context.operationId, {});
        }
        const identifierClass =
          ROLE_CLASS[span.parsed.role as unknown as string];
        if (identifierClass !== undefined) {
          counts[identifierClass] = (counts[identifierClass] ?? 0) + 1;
        }
      }

      tokenizedSegments.push({
        path: segment.path,
        kind: segment.kind,
        text: tokenizedText as unknown as TokenizedText,
      });
    }

    const total = performance.now() - started;

    // §4.1 step 8: a non-serializable reversal capability, references only. It carries the
    // escaped source literals as a PRIVATE capability (§7/NEW-2) so the wrapper/stream can
    // restore them onto reversed output without ever exposing the raw literals.
    const reversalHandle: ReversalHandle = new InProcessReversalHandle({
      tenantId: context.tenantId,
      matterId: context.matterId,
      dictionaryVersion,
      operationId: context.operationId,
      attemptId: context.attemptId,
      literals,
    });

    return {
      segments: tokenizedSegments,
      dictionaryVersion,
      engineVersion: this.#engineVersion,
      counts: toTotalIdentifierCounts(counts),
      ambiguityCount: 0,
      detector: null,
      latencyMs: { dictionary: total, detector: 0, total },
      reversalHandle,
    };
  }

  public async reverse(
    text: TokenizedText,
    handle: ReversalHandle,
  ): Promise<DisplayText> {
    // §7/N2: `text` is a PUBLIC input — a NON-STRING carrier (e.g. { get length(){ throw PHI } }) would
    // leak raw through grammar scanning. Require a genuine string, fail closed otherwise.
    if (typeof (text as unknown) !== "string") {
      throw new Error("reversal_failed");
    }
    // §7/N2: read the handle's routing scalars ONCE, getter-throw-safe, AND validate their shapes — the
    // id fields as strings, `dictionaryVersion` as a bigint (a non-bigint whose `toString` throws PHI
    // would leak during a store lookup). A hostile handle getter or wrong-typed scalar fails closed
    // here. The BOUNDED `restoreEscapedLiterals` capability below stays on the live handle (it cannot be
    // snapshotted) and is already guarded by its own try/catch.
    const tenantId = safeString(handle, "tenantId");
    const matterId = safeString(handle, "matterId");
    const operationId = safeString(handle, "operationId");
    const dictionaryVersion = safeRead(handle, "dictionaryVersion");
    if (
      tenantId === undefined ||
      matterId === undefined ||
      operationId === undefined ||
      typeof dictionaryVersion !== "bigint"
    ) {
      throw new Error("reversal_failed");
    }
    // GLY-373 §3.2.2 — ENTRY POINT 2 of 3, and this is NEW BEHAVIOUR, not a restatement: the
    // baseline type-checks these scalars but performs no NUL or well-formedness check, so a FORGED
    // structural handle (`ReversalHandle` is a structural interface and the facade forwards it
    // unvalidated) could reach a historically aliased row through here. Runs on the snapshotted
    // locals above and BEFORE `reverseText` — hence before `mappingKeyOf` and any store read.
    // Dropping it is MUT-24; dropping only the well-formedness half is MUT-34.
    //
    // The guard throws the FIXED, PHI-FREE `MISSING_TRUSTED_CONTEXT` of §3.2.4, deliberately NOT
    // this path's legacy `reversal_failed`: `ReversalFailedError.operationId` is own-enumerable and
    // the slug filter `SAFE_OPERATION_ID` ADMITS SSN-shaped strings, so reusing that path's id
    // handling would turn a fail-closed branch into a fresh PHI-egress route (MUT-27). No handle
    // scalar is echoed anywhere reachable. Legitimate reversal failures keep their current class.
    assertTrustedContextIdShape("tenantId", tenantId);
    assertTrustedContextIdShape("matterId", matterId);
    assertTrustedContextIdShape("operationId", operationId);
    // §4.1 step 11 / N5: atomic reversal to CURRENT canonical values; an unknown
    // or malformed token fails the whole reversal with no partial display text.
    const reversed = await reverseText(
      text as unknown as string,
      {
        tenantId: tenantId as unknown as TenantId,
        matterId: matterId as unknown as MatterId,
        dictionaryVersion: dictionaryVersion as unknown as DictionaryVersion,
        operationId: operationId as unknown as OperationId,
      },
      this.#reversalStore,
      this.#grammar,
      this.#policy,
    );
    // L6/§7: restore any escaped source token literals onto the reversed output via the
    // handle's BOUNDED capability (never via raw literal data) so a source literal like
    // `[[Claimant]]` round-trips to itself, never a sentinel.
    let restored: string;
    try {
      const candidate = isInProcessReversalHandle(handle)
        ? handle.restoreEscapedLiterals(String(reversed))
        : String(reversed);
      // §7/N2: the catch wraps only the CALL. A hostile handle's `restoreEscapedLiterals` can
      // SUCCESSFULLY return a NON-STRING carrier whose `.includes` (the residual-sentinel check below)
      // throws a raw (PHI) message — require a genuine string so that check runs only on a string.
      if (typeof candidate !== "string") {
        throw new Error("reversal_restore_failed");
      }
      restored = candidate;
    } catch {
      // §7/N2: `restoreEscapedLiterals` is a BOUNDED capability but still injected — a throw from it
      // (even on a REAL handle whose method was replaced) must fail closed with a FIXED message, never
      // propagate a raw (PHI) message/code to the caller.
      throw new Error("reversal_restore_failed");
    }
    // L6/§7: a residual escape sentinel that never completed into a literal is internal machinery
    // and must NEVER reach the display. Fail closed (as the streaming path does) rather than leak a
    // provider-generated dangling sentinel through non-stream generation.
    if (restored.includes(SENTINEL_OPEN) || restored.includes(SENTINEL_CLOSE)) {
      throw new Error("residual_escape_sentinel_in_reversed_output");
    }
    return restored as unknown as DisplayText;
  }

  public createReverseStream(
    handle: ReversalHandle,
    sink: (safe: DisplayText) => void | Promise<void>,
  ): ReverseStream {
    // §4.2 / L4: M-1 UTF-16 holdback; raw chunks never reach the display sink. The factory
    // pulls the escaped-literal restore off the handle so streamed output round-trips too.
    // §7/N2: the stream factory is an INJECTED port — a SYNCHRONOUS throw from create() (its message
    // could carry PHI) must fail closed with a FIXED message, never propagate raw out of this public
    // API. The wrapper has its own catch, but a DIRECT engine caller of createReverseStream would
    // otherwise receive the raw throw.
    try {
      return this.#streamFactory.create({
        handle,
        store: this.#reversalStore,
        grammar: this.#grammar,
        policy: this.#policy,
        sink,
      });
    } catch (caught) {
      // GLY-373 §3.2.2 entry point 3. The §3.2.2 guard lives in the factory, so that the handle
      // routing fields are read EXACTLY ONCE (OR-14(i)); but this pre-existing catch would
      // otherwise convert its fixed failure into `reverse_stream_unavailable`, and §3.2.4 requires
      // the guard to throw the fixed frozen `MISSING_TRUSTED_CONTEXT` SYNCHRONOUSLY from
      // `createReverseStream` (OR-14(c); failing later at `push`/`end` is MUT-25 and is not
      // acceptable). This branch recognises that disposition and re-raises it.
      //
      // A FRESH, ENGINE-CONSTRUCTED error is raised on match — the caught value is NEVER
      // re-thrown, inspected beyond its fixed code, chained, or wrapped. That is what makes the
      // recognition safe despite being shape-based rather than identity-based: an injected stream
      // factory CAN forge a value that matches, and forging it buys nothing, because the value
      // that escapes carries only this engine's own fixed literals and none of the forgery's
      // content — not its `stack`, not its `safeDetails`, nothing.
      if (
        isPhiEngineError(caught) &&
        safeCodeString(caught) === "MISSING_TRUSTED_CONTEXT"
      ) {
        throw missingTrustedContextError();
      }
      // Every non-match keeps the existing blanket scrub, verbatim: an injected factory's
      // synchronous throw (whose message could carry PHI) never propagates raw out of this
      // public API.
      throw new Error("reverse_stream_unavailable");
    }
  }

  /** Rebases escaped-literal sentinel indices by `base` so global indices are unique. */
  #rebaseSentinels(text: string, base: number): string {
    if (base === 0) {
      return text;
    }
    const pattern = new RegExp(`${SENTINEL_OPEN}(\\d+)${SENTINEL_CLOSE}`, "g");
    return text.replace(
      pattern,
      (_match, digits: string) =>
        `${SENTINEL_OPEN}${base + Number(digits)}${SENTINEL_CLOSE}`,
    );
  }
}

function mapDictionaryFailure(code: string): PhiEngineFailureCode {
  if (code === "DICTIONARY_UNAVAILABLE") return "DICTIONARY_UNAVAILABLE";
  if (code === "MISSING_TRUSTED_CONTEXT") return "MISSING_TRUSTED_CONTEXT";
  return "DICTIONARY_NOT_READY";
}
