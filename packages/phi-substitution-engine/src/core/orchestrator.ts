/**
 * Composed substitution orchestrator (CONTRACT-phase1 §4.1 steps 2/5/6/8/11,
 * invariants N4/N5/L2/L3/L6).
 *
 * This is the `PhiSubstitutionEngine` the protected wrapper drives. It COMPOSES
 * the already-frozen leaves and never re-invents them:
 *   - `../dictionary` : the READY-version coordinator (L2/N4 readiness gate) and
 *                       the tagged-truth reader (schema-tagged case truth);
 *   - `../collision`  : `runCollision` — NFKC normalization, C1–C8 resolution,
 *                       deterministic structured-identifier detection, and the
 *                       original-offset splice that produces the tokenized text
 *                       and its reversal;
 *   - `../tokens`     : the source-token escaper (L6), the tenant-scoped reversal
 *                       store (L8/N5), the atomic reverser, and the M-1 holdback
 *                       reverse stream (L4);
 *   - `../variants`   : reached transitively through the tagged truth expanded
 *                       into `runCollision` known values (allow-listed only, L10).
 *
 * The phase-1 detector belt (`../detectors`) is DISABLED and is never called for
 * a customer claim: substitution is sourced only from on-file tagged truth plus
 * the deterministic structured-identifier detector that the collision leaf owns.
 */
import type {
  DictionaryVersion,
  DisplayText,
  EngineVersion,
  MatterId,
  SubstitutionToken,
  TenantId,
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
import { isDictionaryError } from "../dictionary/errors";
import {
  canonicalize,
  detectStructuredIdentifiers,
  fold,
  runCollision,
  type KnownValue,
} from "../collision/index";
import {
  BracketTokenGrammar,
  HoldbackReverseStreamFactory,
  InMemoryReversalStore,
  InProcessReversalHandle,
  SentinelSourceTokenEscaper,
  reverseText,
} from "../tokens/index";
import type { TokenGrammarPolicy } from "../tokens/ports";
import { toTotalIdentifierCounts } from "../audit/index";
import { PhiEngineError } from "./errors";

/** Class → token role, matching the collision leaf's `tokenFor` mapping. */
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

const asToken = (value: string): SubstitutionToken => value as unknown as SubstitutionToken;

function tokenForClass(identifierClass: IdentifierClass): SubstitutionToken {
  return asToken(`[[${CLASS_ROLE[identifierClass]}]]`);
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

    const knownValues = await this.#loadKnownValues(context, dictionaryVersion);

    const started = performance.now();
    const tokenizedSegments: TokenizedTextSegment[] = [];
    const counts: Partial<Record<IdentifierClass, number>> = {};

    for (const segment of request.segments) {
      // §4.1 step 5 / L6: escape reserved token-shaped source text BEFORE matching,
      // so a caller cannot inject a `[[Role]]` shape and have it reversed to a value.
      // For token-free source this is an identity transform; the fenced sentinels
      // are private-use and non-reversible, so they never reach reversal.
      const sourceText = this.#escaper.escape(segment.text, this.#policy).text as unknown as string;

      // §4.1 steps 6/8 / L3: match tagged truth + C1–C8 resolution + splice.
      const collision = runCollision({ originalText: sourceText, locale, knownValues });
      if (collision.errorCode !== null || collision.tokenizedText === null) {
        // C6 ambiguity → fail closed; a known value is never guessed.
        throw new PhiEngineError("AMBIGUOUS_KNOWN_IDENTIFIER", context.operationId, {
          ambiguityCount: collision.ambiguityCount,
        });
      }

      // §4.1 step 8 / N5: record token → CURRENT canonical for output reversal.
      this.#recordCanonicals(context, dictionaryVersion, sourceText, locale, knownValues);

      // Tally per-class counts from the tokens that were actually substituted.
      for (const [identifierClass, count] of this.#countTokens(collision.tokenizedText)) {
        counts[identifierClass] = (counts[identifierClass] ?? 0) + count;
      }

      tokenizedSegments.push({
        path: segment.path,
        kind: segment.kind,
        text: collision.tokenizedText as unknown as TokenizedText,
      });
    }

    const total = performance.now() - started;

    // §4.1 step 8: a non-serializable reversal capability, references only.
    const reversalHandle: ReversalHandle = new InProcessReversalHandle({
      tenantId: context.tenantId,
      matterId: context.matterId,
      dictionaryVersion,
      operationId: context.operationId,
      attemptId: context.attemptId,
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
    return reversed as unknown as DisplayText;
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

  /** Reads schema-tagged case truth and expands it into collision known values. */
  async #loadKnownValues(
    context: MatterAiContext,
    dictionaryVersion: DictionaryVersion,
  ): Promise<readonly KnownValue[]> {
    const tagged = await this.#truthReader.readTaggedValues({
      tenantId: context.tenantId,
      matterId: context.matterId,
      dictionaryVersion,
      sourceTruthRevision: this.#sourceTruthRevision,
    });
    const known: KnownValue[] = [];
    for (const value of tagged) {
      const identifierClass = value.field.identifierClass;
      const subjectId = value.subjectId as unknown as string;
      known.push({
        literal: value.canonicalDisplayValue,
        identifierClass,
        subjectId,
        canonicalDisplayValue: value.canonicalDisplayValue,
      });
      for (const alias of value.approvedAliases) {
        known.push({
          literal: alias,
          identifierClass,
          subjectId,
          canonicalDisplayValue: value.canonicalDisplayValue,
        });
      }
    }
    return known;
  }

  /** Records token → current canonical for known values present in the text + structured spans. */
  #recordCanonicals(
    context: MatterAiContext,
    dictionaryVersion: DictionaryVersion,
    text: string,
    locale: string,
    knownValues: readonly KnownValue[],
  ): void {
    const foldedText = fold(text, locale);
    const tenantId: TenantId = context.tenantId;
    const matterId: MatterId = context.matterId;

    for (const known of knownValues) {
      const literal = known.literal ?? known.normalizedForm;
      if (literal === undefined) continue;
      if (!foldedText.includes(fold(literal, locale))) continue;
      this.#reversalStore.record({
        tenantId,
        matterId,
        dictionaryVersion,
        token: tokenForClass(known.identifierClass),
        canonical: known.canonicalDisplayValue ?? canonicalize(literal),
      });
    }

    for (const span of detectStructuredIdentifiers(text)) {
      const start = span.startUtf16 as unknown as number;
      const end = span.endUtf16 as unknown as number;
      const matchText = text.slice(start, end);
      this.#reversalStore.record({
        tenantId,
        matterId,
        dictionaryVersion,
        token: tokenForClass(span.identifierClass),
        canonical: canonicalize(matchText),
      });
    }
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

function mapDictionaryFailure(code: string): PhiEngineFailureCode {
  if (code === "DICTIONARY_UNAVAILABLE") return "DICTIONARY_UNAVAILABLE";
  if (code === "MISSING_TRUSTED_CONTEXT") return "MISSING_TRUSTED_CONTEXT";
  return "DICTIONARY_NOT_READY";
}
