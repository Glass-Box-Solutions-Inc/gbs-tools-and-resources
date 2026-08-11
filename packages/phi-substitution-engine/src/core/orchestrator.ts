/**
 * Composed substitution orchestrator (CONTRACT-phase1 §4.1 steps 2/5/6/8/11,
 * invariants N4/N5/L1/L2/L3/L6/L8).
 *
 * This is the `PhiSubstitutionEngine` the protected wrapper drives. It COMPOSES
 * the already-frozen leaves and never re-invents them:
 *   - `../dictionary` : the READY-version coordinator (L2/N4 readiness gate) and
 *                       the tagged-truth reader (schema-tagged case truth);
 *   - `../collision`  : `runCollision` — NFKC normalization, C1–C8 resolution,
 *                       deterministic structured-identifier detection, and the
 *                       original-offset splice that produces the tokenized text;
 *   - `../tokens`     : the source-token escaper (L6), the SUBJECT-scoped token
 *                       assignment store (L1), the tenant-scoped reversal store
 *                       (L8/N5), the atomic reverser, and the M-1 holdback
 *                       reverse stream (L4);
 *   - `../variants`   : reached transitively through the tagged truth expanded
 *                       into `runCollision` known values (allow-listed only, L10).
 *
 * Token identity (L1): the class-level tokens `runCollision` splices in are
 * re-tokenized into SUBJECT-scoped tokens (`tenant+matter+subject+role → [[Role_N]]`)
 * via the assignment store, so two distinct subjects of one class receive distinct
 * tokens and each reverses to its OWN canonical value. Detector-only spans (no
 * trusted subject) are allocated OPERATION-scoped tokens so one operation's
 * `[[SSN]]` cannot surface in another.
 *
 * The phase-1 detector belt (`../detectors`) is DISABLED and is never called for
 * a customer claim. A policy that nonetheless REQUIRES the belt fails closed (N4),
 * because branding untagged text as safe and egressing it is exactly the leak the
 * requirement is meant to prevent.
 */
import type {
  DictionaryVersion,
  DisplayText,
  EngineVersion,
  SubjectId,
  SubstitutionToken,
  TokenizedText,
  TokenRole,
} from "./brands";
import type {
  IdentifierClass,
  MatterAiContext,
  PhiEngineFailureCode,
  PhiSubstitutionEngine,
  ReversalHandle,
  ReverseStream,
  SubstitutionRequest,
  SubstitutionResult,
  TokenizedTextSegment,
} from "./contracts";
import type { CaseTruthReader, DictionaryVersionCoordinator } from "../dictionary/contracts";
import type { EscapedTokenLiteral } from "../tokens/ports";
import { isDictionaryError } from "../dictionary/errors";
import { canonicalize, fold, runCollision, type KnownValue } from "../collision/index";
import {
  BracketTokenGrammar,
  HoldbackReverseStreamFactory,
  InMemoryReversalStore,
  InMemoryTokenAssignmentStore,
  InProcessReversalHandle,
  SentinelSourceTokenEscaper,
  SENTINEL_OPEN,
  SENTINEL_CLOSE,
  reverseText,
} from "../tokens/index";
import type { TokenGrammarPolicy } from "../tokens/ports";
import { toTotalIdentifierCounts } from "../audit/index";
import { PhiEngineError } from "./errors";

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

const role = (value: string): TokenRole => value as unknown as TokenRole;

/**
 * Grammar policy for the boundary. Roles are the trusted allow-list for both the
 * class tokens the collision leaf produces (`[[MRN]]`, `[[ADDRESS]]`, ...) and
 * the person/role tokens (`[[Claimant]]`, ...). Reversal validates every
 * token-like sequence against this policy; an off-registry shape fails visibly.
 */
export const BOUNDARY_TOKEN_GRAMMAR_POLICY: TokenGrammarPolicy = {
  allowedRoles: new Set<TokenRole>(
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
};

/** Trusted subject/role info recovered by folded match text during re-tokenization. */
interface SubjectInfo {
  readonly subjectId: string;
  readonly role: string;
  readonly canonical: string;
}

export interface ComposedSubstitutionEngineDeps {
  /** Dictionary L2/N4 readiness gate. */
  readonly coordinator: DictionaryVersionCoordinator;
  /** Dictionary tagged-truth source (schema-tagged case truth). */
  readonly truthReader: CaseTruthReader;
  /** Constant per-matter truth revision the wrapper reads under. */
  readonly sourceTruthRevision: string;
  /** Tenant-scoped reversal store (tokens leaf); may be pre-seeded by callers. */
  readonly reversalStore: InMemoryReversalStore;
  readonly engineVersion: EngineVersion;
  readonly grammar?: BracketTokenGrammar;
  readonly tokenPolicy?: TokenGrammarPolicy;
  readonly streamFactory?: HoldbackReverseStreamFactory;
  /** Subject/operation-scoped token allocator (L1). Stable per tenant+matter+subject+role. */
  readonly assignmentStore?: InMemoryTokenAssignmentStore;
}

export class ComposedSubstitutionEngine implements PhiSubstitutionEngine {
  readonly #coordinator: DictionaryVersionCoordinator;
  readonly #truthReader: CaseTruthReader;
  readonly #sourceTruthRevision: string;
  readonly #reversalStore: InMemoryReversalStore;
  readonly #engineVersion: EngineVersion;
  readonly #grammar: BracketTokenGrammar;
  readonly #policy: TokenGrammarPolicy;
  readonly #streamFactory: HoldbackReverseStreamFactory;
  readonly #escaper: SentinelSourceTokenEscaper;
  readonly #assignmentStore: InMemoryTokenAssignmentStore;

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
  }

  public async substitute(request: SubstitutionRequest): Promise<SubstitutionResult> {
    const context = request.context;
    const locale = request.policy.locale as unknown as string;

    // §4.1 step 2 / L2 / N4: require an active READY dictionary version.
    let dictionaryVersion: DictionaryVersion;
    try {
      dictionaryVersion = await this.#coordinator.requireActiveReady({
        tenantId: context.tenantId,
        matterId: context.matterId,
      });
    } catch (error) {
      if (isDictionaryError(error)) {
        throw new PhiEngineError(mapDictionaryFailure(error.code), context.operationId, {});
      }
      throw error;
    }

    // N4: phase-1 has no detection belt wired. A policy that REQUIRES it cannot be
    // satisfied, so we fail closed rather than brand untagged free text as safe.
    if (request.policy.detectorRequirement === "REQUIRED") {
      throw new PhiEngineError("DETECTOR_UNAVAILABLE", context.operationId, {});
    }

    const truth = await this.#loadTruth(context, dictionaryVersion, locale);

    const started = performance.now();
    const tokenizedSegments: TokenizedTextSegment[] = [];
    const counts: Partial<Record<IdentifierClass, number>> = {};
    const literals: EscapedTokenLiteral[] = [];

    for (const segment of request.segments) {
      // §4.1 step 5 / L6: escape reserved token-shaped source text BEFORE matching,
      // so a caller cannot inject a `[[Role]]` shape and have it reversed to a value.
      // Sentinel indices are re-based to GLOBAL positions so a single restore pass on
      // the reversed output is unambiguous across segments.
      const escaped = this.#escaper.escape(segment.text, this.#policy);
      const base = literals.length;
      const sourceText = this.#rebaseSentinels(String(escaped.text), base);
      literals.push(...escaped.literals);

      // §4.1 steps 6/8 / L3: match tagged truth + C1–C8 resolution + splice.
      const collision = runCollision({ originalText: sourceText, locale, knownValues: truth.knownValues });
      if (collision.errorCode !== null || collision.tokenizedText === null) {
        // C6 ambiguity → fail closed; a known value is never guessed.
        throw new PhiEngineError("AMBIGUOUS_KNOWN_IDENTIFIER", context.operationId, {
          ambiguityCount: collision.ambiguityCount,
        });
      }

      // §4.1 step 8 / L1 / N5: re-tokenize the class tokens into subject/operation
      // scoped tokens and record each token → its CURRENT canonical for reversal.
      const rebuilt = await this.#assignScopedTokens(
        context,
        dictionaryVersion,
        locale,
        collision.tokenizedText,
        collision.candidates,
        truth.byFold,
      );

      // Tally per-class counts from the tokens that were actually substituted.
      for (const [identifierClass, count] of this.#countTokens(rebuilt)) {
        counts[identifierClass] = (counts[identifierClass] ?? 0) + count;
      }

      tokenizedSegments.push({
        path: segment.path,
        kind: segment.kind,
        text: rebuilt as unknown as TokenizedText,
      });
    }

    const total = performance.now() - started;

    // §4.1 step 8: a non-serializable reversal capability, references only. It carries
    // the escaped source literals so the wrapper can restore them onto reversed output.
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
    // §4.1 step 11 / N5: atomic reversal to CURRENT canonical values; an unknown
    // or malformed token fails the whole reversal with no partial display text.
    const reversed = await reverseText(
      text as unknown as string,
      {
        tenantId: handle.tenantId,
        matterId: handle.matterId,
        dictionaryVersion: handle.dictionaryVersion,
        operationId: handle.operationId,
      },
      this.#reversalStore,
      this.#grammar,
      this.#policy,
    );
    // L6: restore any escaped source token literals onto the reversed output so a
    // source literal like `[[Claimant]]` round-trips to itself, never a sentinel.
    const restored = this.#escaper.restoreLiterals(
      reversed as unknown as TokenizedText,
      handleLiterals(handle),
    );
    return restored as unknown as DisplayText;
  }

  public createReverseStream(
    handle: ReversalHandle,
    sink: (safe: DisplayText) => void | Promise<void>,
  ): ReverseStream {
    // §4.2 / L4: M-1 UTF-16 holdback; raw chunks never reach the display sink.
    return this.#streamFactory.create({
      handle,
      store: this.#reversalStore,
      grammar: this.#grammar,
      policy: this.#policy,
      sink,
    });
  }

  /** Reads schema-tagged case truth into collision known values + a folded subject lookup. */
  async #loadTruth(
    context: MatterAiContext,
    dictionaryVersion: DictionaryVersion,
    locale: string,
  ): Promise<{ knownValues: readonly KnownValue[]; byFold: ReadonlyMap<string, SubjectInfo> }> {
    const tagged = await this.#truthReader.readTaggedValues({
      tenantId: context.tenantId,
      matterId: context.matterId,
      dictionaryVersion,
      sourceTruthRevision: this.#sourceTruthRevision,
    });
    const knownValues: KnownValue[] = [];
    const byFold = new Map<string, SubjectInfo>();
    for (const value of tagged) {
      const identifierClass = value.field.identifierClass;
      const subjectId = value.subjectId as unknown as string;
      const tokenRole = value.field.tokenRole as unknown as string;
      const canonical = value.canonicalDisplayValue;
      const info: SubjectInfo = { subjectId, role: tokenRole, canonical };
      knownValues.push({
        literal: value.canonicalDisplayValue,
        identifierClass,
        subjectId,
        canonicalDisplayValue: canonical,
      });
      byFold.set(fold(value.canonicalDisplayValue, locale), info);
      for (const alias of value.approvedAliases) {
        knownValues.push({
          literal: alias,
          identifierClass,
          subjectId,
          canonicalDisplayValue: canonical,
        });
        byFold.set(fold(alias, locale), info);
      }
    }
    return { knownValues, byFold };
  }

  /**
   * Re-tokenizes the class-level tokens `runCollision` spliced in (one per resolved
   * span, in ascending original offset order matching `candidates`) into distinct
   * subject-scoped (or operation-scoped) tokens, recording each token → canonical.
   */
  async #assignScopedTokens(
    context: MatterAiContext,
    dictionaryVersion: DictionaryVersion,
    locale: string,
    tokenizedText: string,
    candidates: readonly string[],
    byFold: ReadonlyMap<string, SubjectInfo>,
  ): Promise<string> {
    const spans = this.#grammar.scan(tokenizedText, this.#policy);
    let out = "";
    let cursor = 0;
    let candidateIndex = 0;
    let detectorOrdinal = 0;
    for (const span of spans) {
      if (span.parsed.kind !== "valid") {
        continue;
      }
      const matchText = candidates[candidateIndex] ?? "";
      candidateIndex += 1;
      const known = byFold.get(fold(matchText, locale));

      let token: SubstitutionToken;
      let canonical: string;
      if (known !== undefined) {
        // L1: stable token by tenant+matter+subject+role, distinct per subject.
        token = await this.#assignmentStore.getOrAllocate({
          tenantId: context.tenantId,
          matterId: context.matterId,
          subjectId: known.subjectId as unknown as SubjectId,
          role: known.role as unknown as TokenRole,
          dictionaryVersion,
        });
        canonical = known.canonical;
      } else {
        // Detector-only span: allocate an OPERATION-scoped token so one operation's
        // detector token cannot surface as another operation's.
        detectorOrdinal += 1;
        const syntheticSubject = `det:${String(context.operationId)}:${detectorOrdinal}`;
        token = await this.#assignmentStore.getOrAllocate({
          tenantId: context.tenantId,
          matterId: context.matterId,
          subjectId: syntheticSubject as unknown as SubjectId,
          role: (span.parsed.role as unknown as string) as unknown as TokenRole,
          dictionaryVersion,
        });
        canonical = canonicalize(matchText);
      }

      this.#reversalStore.record({
        tenantId: context.tenantId,
        matterId: context.matterId,
        dictionaryVersion,
        token,
        canonical,
      });

      out += tokenizedText.slice(cursor, span.startUtf16) + String(token);
      cursor = span.endUtf16;
    }
    out += tokenizedText.slice(cursor);
    return out;
  }

  /** Rebases escaped-literal sentinel indices by `base` so global indices are unique. */
  #rebaseSentinels(text: string, base: number): string {
    if (base === 0) {
      return text;
    }
    const pattern = new RegExp(`${SENTINEL_OPEN}(\\d+)${SENTINEL_CLOSE}`, "g");
    return text.replace(pattern, (_match, digits: string) => `${SENTINEL_OPEN}${base + Number(digits)}${SENTINEL_CLOSE}`);
  }

  /** Tallies substituted identifier classes from the token shapes in the output. */
  #countTokens(tokenizedText: string): ReadonlyArray<readonly [IdentifierClass, number]> {
    const tally = new Map<IdentifierClass, number>();
    for (const span of this.#grammar.scan(tokenizedText, this.#policy)) {
      if (span.parsed.kind !== "valid") continue;
      const roleName = span.parsed.role as unknown as string;
      const identifierClass = ROLE_CLASS[roleName];
      if (identifierClass === undefined) continue;
      tally.set(identifierClass, (tally.get(identifierClass) ?? 0) + 1);
    }
    return [...tally.entries()];
  }
}

/** Reads escaped literals off a concrete in-process handle; empty for any other handle. */
function handleLiterals(handle: ReversalHandle): readonly EscapedTokenLiteral[] {
  if (handle instanceof InProcessReversalHandle) {
    return handle.literals;
  }
  return [];
}

function mapDictionaryFailure(code: string): PhiEngineFailureCode {
  if (code === "DICTIONARY_UNAVAILABLE") return "DICTIONARY_UNAVAILABLE";
  if (code === "MISSING_TRUSTED_CONTEXT") return "MISSING_TRUSTED_CONTEXT";
  return "DICTIONARY_NOT_READY";
}
