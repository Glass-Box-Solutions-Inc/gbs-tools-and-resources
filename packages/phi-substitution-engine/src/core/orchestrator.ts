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
 * The phase-1 detector belt (`../detectors`) is DISABLED and is never called for
 * a customer claim. A policy that nonetheless REQUIRES the belt fails closed (N4).
 */
import type {
  DictionaryVersion,
  DisplayText,
  EngineVersion,
  SubjectId,
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
import type { CaseTruthReader, CompiledDictionaryCache, DictionaryVersionCoordinator } from "../dictionary/contracts";
import type { EscapedTokenLiteral, TokenGrammarPolicy } from "../tokens/ports";
import { isDictionaryError } from "../dictionary/errors";
import { canonicalize, detectStructuredIdentifiers } from "../collision/index";
import { MatterDictionaryCompiler } from "../dictionary/compiler";
import { getOrCompile, tokenize, type DetectorSpanInput } from "../dictionary/tokenize";
import { InMemoryCompiledDictionaryCache } from "../dictionary/cache";
import { TokensLeafAssignmentPort } from "../dictionary/token-port";
import type { AhoCorasickCompiledDictionary } from "../dictionary/compiled-dictionary";
import {
  BracketTokenGrammar,
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
import { PhiEngineError, safeCodeString } from "./errors";
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
 */
const SYNTHETIC_DETECTOR_PREFIX = "\u0000detector\u0000";

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
  allowedRoles: Object.freeze(
    new Set<TokenRole>(
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
  ) as ReadonlySet<TokenRole>,
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
  readonly assignmentStore?: InMemoryTokenAssignmentStore;
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
  readonly #assignmentStore: InMemoryTokenAssignmentStore;
  readonly #compiler: MatterDictionaryCompiler;
  readonly #cache: CompiledDictionaryCache;

  public constructor(deps: ComposedSubstitutionEngineDeps) {
    this.#coordinator = deps.coordinator;
    this.#truthReader = deps.truthReader;
    this.#sourceTruthRevision = deps.sourceTruthRevision;
    this.#reversalStore = deps.reversalStore;
    this.#engineVersion = deps.engineVersion;
    this.#grammar = deps.grammar ?? new BracketTokenGrammar();
    this.#policy = deps.tokenPolicy ?? BOUNDARY_TOKEN_GRAMMAR_POLICY;
    this.#streamFactory = deps.streamFactory ?? new HoldbackReverseStreamFactory();
    this.#escaper = new SentinelSourceTokenEscaper(this.#grammar);
    this.#assignmentStore =
      deps.assignmentStore ?? new InMemoryTokenAssignmentStore(this.#grammar, this.#policy);
    // The compiler allocates subject tokens through the SAME shared assignment store, so
    // dictionary and detector-only tokens share one monotonic ordinal space (L1/#6) and
    // handle EVERY identifier class (not just the five person roles).
    this.#compiler = new MatterDictionaryCompiler(
      this.#truthReader,
      () => new TokensLeafAssignmentPort(this.#assignmentStore),
    );
    // NEW-B/L1: the warm cache is INTERNAL and lifecycle-coupled to THIS engine's assignment
    // store. It is never injectable/shareable, so a compiled dictionary is never served against a
    // different (fresh) assignment namespace — which would let a detector-only token collide with a
    // cached real-subject token. Warm reuse still happens across requests on the same engine.
    this.#cache = new InMemoryCompiledDictionaryCache();
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
      tenantId === undefined || matterId === undefined ||
      operationId === undefined || attemptId === undefined
    ) {
      throw new PhiEngineError("MISSING_TRUSTED_CONTEXT");
    }
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
    const segments: { text: string; path: string; kind: TextSegmentKind }[] = [];
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

  public async substitute(request: SubstitutionRequest): Promise<SubstitutionResult> {
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
      throw new PhiEngineError("MISSING_TRUSTED_POLICY", context.operationId, {});
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
        throw new PhiEngineError(mapDictionaryFailure(safeCodeString(error) ?? ""), context.operationId, {});
      }
      // §7/N2: an unexpected non-DictionaryError (or a hostile Proxy `isDictionaryError` rejected)
      // must never surface a raw message/code — fail closed with a fixed code.
      throw new PhiEngineError("DICTIONARY_UNAVAILABLE", context.operationId, {});
    }
    // §7/N2: the injected coordinator's SUCCESS value is UNTRUSTED — a non-`bigint` (e.g. a PHI string)
    // must NOT be returned to the caller as SubstitutionResult.dictionaryVersion. Require a bigint.
    if (typeof (dictionaryVersion as unknown) !== "bigint") {
      throw new PhiEngineError("DICTIONARY_UNAVAILABLE", context.operationId, {});
    }

    // N4: phase-1 has no detection belt wired. A policy that REQUIRES it cannot be
    // satisfied, so we fail closed rather than brand untagged free text as safe.
    if (detectorRequirement === "REQUIRED") {
      throw new PhiEngineError("DETECTOR_UNAVAILABLE", context.operationId, {});
    }

    // §4.1 steps 2/6 / L3/L10: compile the matter dictionary — variant-expanded surface
    // forms + subject-scoped tokens + the Aho–Corasick automaton. Subject tokens are
    // stable across compiles because the shared assignment store owns their identity.
    let compiled: AhoCorasickCompiledDictionary;
    try {
      // L9 / NEW-B: the WARM-CACHE serving path — a compiled dictionary for this
      // tenant+matter+version+engine+schema is reused instead of recompiled on every request.
      compiled = await getOrCompile(this.#cache, this.#compiler, {
        tenantId: context.tenantId,
        matterId: context.matterId,
        policy: request.policy,
        dictionaryVersion,
        engineVersion: this.#engineVersion,
        schemaVersion: request.policy.schemaVersion,
        sourceTruthRevision: this.#sourceTruthRevision,
      });
    } catch (error) {
      if (isDictionaryError(error)) {
        throw new PhiEngineError(mapDictionaryFailure(safeCodeString(error) ?? ""), context.operationId, {});
      }
      // §7/N2: an unexpected non-DictionaryError must never surface a raw message/code — fail closed.
      throw new PhiEngineError("DICTIONARY_UNAVAILABLE", context.operationId, {});
    }

    const started = performance.now();
    const tokenizedSegments: TokenizedTextSegment[] = [];
    const counts: Partial<Record<IdentifierClass, number>> = {};
    const literals: EscapedTokenLiteral[] = [];
    // Operation-scoped and monotonic across ALL segments of this call so two detector
    // spans in one operation never share a synthetic subject.
    let detectorOrdinal = 0;

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
      for (const span of detectStructuredIdentifiers(sourceText)) {
        detectorOrdinal += 1;
        const syntheticSubject = `${SYNTHETIC_DETECTOR_PREFIX}${String(context.operationId)}\u0000${detectorOrdinal}`;
        // §7/N2: the injected assignment store is UNTRUSTED — a `getOrAllocate` REJECTION (its message
        // could carry PHI) must fail closed with a FIXED code, never propagate raw out of substitute
        // (this call sits outside the compile guard). A failed allocation means the detector span could
        // not be tokenized, so failing closed prevents the identifier egressing raw.
        let token: unknown;
        try {
          token = await this.#assignmentStore.getOrAllocate({
            tenantId: context.tenantId,
            matterId: context.matterId,
            subjectId: syntheticSubject as unknown as SubjectId,
            role: CLASS_ROLE[span.identifierClass] as unknown as TokenRole,
            dictionaryVersion,
          });
        } catch {
          throw new PhiEngineError("DICTIONARY_UNAVAILABLE", context.operationId, {});
        }
        // §7/N2: the injected store's SUCCESS return is UNTRUSTED. Guarding only the REJECTION
        // (above) still lets a hostile allocation escape two ways: a non-string carrier whose
        // `Symbol.toPrimitive`/`toString` throws raw (PHI) out of `String(token)` below (sink c),
        // and a returned raw-PHI STRING that becomes the detector token spliced into the output
        // (SubstitutionResult.segments[].text, sink a) and enters compiled/scanned entries — both
        // SUCCESS paths, so the compile/tokenize catch blocks never contain them. Require a genuine,
        // GRAMMAR-VALID token (the real store returns `grammar.format()` output, always valid, so no
        // legitimate allocation is rejected); a bracketed token can only carry an allow-listed role +
        // numeric sequence, structurally incapable of holding raw PHI. Anything else fails closed with
        // the same fixed code as a rejection.
        if (typeof token !== "string" || this.#grammar.parse(token, this.#policy).kind !== "valid") {
          throw new PhiEngineError("DICTIONARY_UNAVAILABLE", context.operationId, {});
        }
        const start = span.startUtf16 as unknown as number;
        const end = span.endUtf16 as unknown as number;
        detectorCanonicalByToken.set(String(token), canonicalize(sourceText.slice(start, end)));
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
        tokenizedText = tokenize(compiled, sourceText, locale, detectorSpans, this.#grammar, this.#policy).tokenizedText;
      } catch (error) {
        if (isDictionaryError(error)) {
          // C6 ambiguity → fail closed; a known value is never guessed.
          throw new PhiEngineError("AMBIGUOUS_KNOWN_IDENTIFIER", context.operationId, {});
        }
        // §7/N2: an unexpected non-DictionaryError must never surface a raw message/code — fail closed.
        throw new PhiEngineError("DICTIONARY_UNAVAILABLE", context.operationId, {});
      }

      // §4.1 step 8 / N5: record each output token → its CURRENT canonical value, and tally
      // per-class counts from the tokens actually present in the output.
      for (const span of this.#grammar.scan(tokenizedText, this.#policy)) {
        if (span.parsed.kind !== "valid") {
          continue;
        }
        const token: SubstitutionToken = span.parsed.token;
        const canonical =
          compiled.canonicalForToken(String(token)) ?? detectorCanonicalByToken.get(String(token));
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
        } catch {
          throw new PhiEngineError("REVERSAL_FAILED", context.operationId, {});
        }
        const identifierClass = ROLE_CLASS[span.parsed.role as unknown as string];
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

  public async reverse(text: TokenizedText, handle: ReversalHandle): Promise<DisplayText> {
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
      tenantId === undefined || matterId === undefined || operationId === undefined ||
      typeof dictionaryVersion !== "bigint"
    ) {
      throw new Error("reversal_failed");
    }
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
      const candidate =
        isInProcessReversalHandle(handle)
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
    } catch {
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
      (_match, digits: string) => `${SENTINEL_OPEN}${base + Number(digits)}${SENTINEL_CLOSE}`,
    );
  }
}

function mapDictionaryFailure(code: string): PhiEngineFailureCode {
  if (code === "DICTIONARY_UNAVAILABLE") return "DICTIONARY_UNAVAILABLE";
  if (code === "MISSING_TRUSTED_CONTEXT") return "MISSING_TRUSTED_CONTEXT";
  return "DICTIONARY_NOT_READY";
}
