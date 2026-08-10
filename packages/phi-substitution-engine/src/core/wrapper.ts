/**
 * The protected AI provider wrapper — the single application-facing binding for
 * `generateText`, `generateStream`, and `embedText` (CONTRACT-phase1 §3.1.4, §4,
 * invariants N1/N2/N3/N4/N5/L5/L11).
 *
 * It orchestrates the frozen composed pieces in the exact normative order:
 *
 *   1. require trusted tenant/matter/actor/operation/attempt context;
 *   2. load trusted matter policy;
 *   3. route on ORIGINAL content and PIN the raw provider decision, then enforce
 *      the conjunctive `isProductionSafe ∧ CLAUDE_BAA_ENABLED` gate (L11);
 *   4. project ALL text-bearing option fields, failing closed on an unclassified
 *      field before egress (L5);
 *   5-8. substitute every segment and build a non-serializable reversal handle;
 *   9. durably PREPARE exactly one metadata-only audit record BEFORE egress (N3);
 *   10. trace tokenized input (N2) and invoke the provider EXACTLY ONCE (N1);
 *   11. trace tokenized output (N2), then atomically reverse to current canonical
 *       values before display (N5) and finalize the audit event;
 *   12. on ANY precondition failure, invoke the provider ZERO times and surface a
 *       visible fixed-code fail-closed result (N4).
 *
 * The phase-1 detector belt is never invoked for a customer claim.
 */
import type { DisplayText, EngineVersion, TokenizedText } from "./brands";
import type {
  AiOperation,
  MatterAiContext,
  PhiEngineFailureCode,
  ReversalHandle,
  SubstitutionResult,
  TokenizedTextSegment,
  TrustedMatterAiPolicy,
} from "./contracts";
import type {
  AiProvider,
  ProtectedAiProviderDependencies,
} from "./protected-ai-provider";
import type { PhiAuditPreparedRecord, AuditPreparationReceipt } from "../audit/ports";
import { preparedToTerminalEvent } from "../audit/index";
import { PhiEngineError, toFailureCode } from "./errors";

/** The single private raw-provider port. It is never exported as an application binding. */
export interface RawProviderPort<GenerateOptions, EmbeddingKind = string> {
  generateText(options: GenerateOptions): Promise<TokenizedText>;
  generateStream(
    options: GenerateOptions,
    onChunk: (chunk: TokenizedText) => void | Promise<void>,
  ): Promise<void>;
  embedText(text: TokenizedText, kind: EmbeddingKind): Promise<readonly number[]>;
}

export interface ProtectedStreamResult {
  readonly displayChunks: readonly DisplayText[];
}

export interface ComposedProtectedAiProviderDeps<GenerateOptions, EmbeddingKind = string>
  extends ProtectedAiProviderDependencies<GenerateOptions, RawProviderPort<GenerateOptions, EmbeddingKind>> {
  readonly engineVersion: EngineVersion;
  readonly clock?: () => string;
  /** Wraps a bare embedding string into routable/traceable options (§4.3). */
  readonly embeddingOptionsFactory?: (text: string) => GenerateOptions;
}

export class ComposedProtectedAiProvider<GenerateOptions, EmbeddingKind = string>
  implements
    AiProvider<
      GenerateOptions,
      Promise<DisplayText>,
      Promise<ProtectedStreamResult>,
      EmbeddingKind,
      Promise<readonly number[]>
    >
{
  readonly #deps: ComposedProtectedAiProviderDeps<GenerateOptions, EmbeddingKind>;
  readonly #clock: () => string;

  public constructor(deps: ComposedProtectedAiProviderDeps<GenerateOptions, EmbeddingKind>) {
    this.#deps = deps;
    this.#clock = deps.clock ?? ((): string => new Date().toISOString());
  }

  public async generateText(options: GenerateOptions): Promise<DisplayText> {
    const prepared = await this.#prepareForEgress(options, "generation");
    // §4.1 step 10 / N1: invoke the provider EXACTLY ONCE with tokenized options.
    const rawOutput = await this.#deps.invokeRaw.generateText(prepared.tokenizedOptions);
    // §4.1 step 11 / N2: trace tokenized output BEFORE reversal.
    await this.#deps.safeTrace.response(rawOutput);
    return this.#reverseAndFinalize(rawOutput, prepared);
  }

  public async generateStream(options: GenerateOptions): Promise<ProtectedStreamResult> {
    const prepared = await this.#prepareForEgress(options, "stream");
    const displayChunks: DisplayText[] = [];
    // §4.2 / L4: the reverse stream holds back M-1 units; raw chunks never reach display.
    const stream = this.#deps.engine.createReverseStream(prepared.substitutionHandle, (safe) => {
      displayChunks.push(safe);
    });
    // §4.1 step 10 / N1: exactly one provider call.
    await this.#deps.invokeRaw.generateStream(prepared.tokenizedOptions, async (chunk) => {
      // §4.2 / N2: trace tokenized chunk, then feed it to the reverse stream only.
      await this.#deps.safeTrace.response(chunk);
      await stream.push(chunk);
    });
    try {
      await stream.end();
    } catch (error) {
      await this.#finalize(prepared, "reversal_failed", "REVERSAL_FAILED");
      throw new PhiEngineError(
        toFailureCode(error, "REVERSAL_FAILED"),
        prepared.context.operationId,
        {},
      );
    }
    await this.#finalize(prepared, "completed", null);
    return { displayChunks };
  }

  public async embedText(text: string, kind: EmbeddingKind): Promise<readonly number[]> {
    const context = await this.#requireContext();
    const policy = await this.#deps.policy.require(context);

    // §4.3: provider choice + safety gate still use ORIGINAL content.
    const routingOptions =
      this.#deps.embeddingOptionsFactory !== undefined
        ? this.#deps.embeddingOptionsFactory(text)
        : (undefined as unknown as GenerateOptions);
    if (routingOptions !== undefined) {
      const decision = await this.#deps.router.selectUsingOriginalContent(routingOptions);
      this.#enforceSafetyGate(decision, context);
    }

    // §4.3: substitute the embedding text; tokenized-only, NO output reversal.
    const substitution = await this.#deps.engine.substitute({
      context,
      policy,
      segments: [{ path: "embedding", kind: "embedding", text }],
      purpose: "embedding",
    });
    const tokenizedText =
      substitution.segments[0]?.text ?? ("" as unknown as TokenizedText);

    const receipt = await this.#prepareAudit(context, policy, substitution, "embedding");

    // §4.3 / N2: only tokenized text is vectorized or traced.
    await this.#deps.safeTrace.request([{ path: "embedding", text: tokenizedText }]);
    const vector = await this.#deps.invokeRaw.embedText(tokenizedText, kind);

    const event = preparedToTerminalEvent(
      this.#preparedRecord(context, substitution, "embedding"),
      "completed",
      null,
      this.#clock(),
    );
    await this.#deps.audit.finalize(receipt, event);
    return vector;
  }

  /** Steps 1–9: everything that must succeed before the provider may be invoked. */
  async #prepareForEgress(
    options: GenerateOptions,
    purpose: Exclude<AiOperation, "graph_extraction">,
  ): Promise<PreparedEgress<GenerateOptions>> {
    // §4.1 step 1 / N4: require trusted context.
    const context = await this.#requireContext();
    // §4.1 step 2: load trusted matter policy.
    const policy = await this.#deps.policy.require(context);

    // §4.1 step 3 / L11: route on ORIGINAL content and pin the decision, then gate.
    const decision = await this.#deps.router.selectUsingOriginalContent(options);
    this.#enforceSafetyGate(decision, context);

    // §4.1 step 4 / L5: exhaustive, fail-closed projection of all text fields.
    const classified = this.#classify(options, context);

    // §4.1 steps 5–8: substitute + build the non-serializable reversal handle.
    const substitution = await this.#deps.engine.substitute({
      context,
      policy,
      segments: classified.segments,
      purpose,
    });
    const tokenizedOptions = classified.rebuild(substitution.segments);

    // §4.1 step 9 / N3: durably PREPARE the metadata-only record BEFORE egress.
    const receipt = await this.#prepareAudit(context, policy, substitution, purpose);

    // §4.1 step 10 / N2: trace tokenized input.
    await this.#deps.safeTrace.request(
      substitution.segments.map((segment: TokenizedTextSegment) => ({
        path: segment.path,
        text: segment.text,
      })),
    );

    return {
      context,
      purpose,
      substitution,
      substitutionHandle: substitution.reversalHandle,
      tokenizedOptions,
      receipt,
    };
  }

  #classify(options: GenerateOptions, context: MatterAiContext) {
    try {
      return this.#deps.options.classify(options);
    } catch (error) {
      // L5: a new/unclassified text-bearing field fails closed before egress.
      throw new PhiEngineError(
        toFailureCode(error, "UNCLASSIFIED_PROVIDER_FIELD"),
        context.operationId,
        {},
      );
    }
  }

  #enforceSafetyGate(
    decision: Readonly<{ isProductionSafe: boolean; baaSatisfied: boolean; providerId: string }>,
    context: MatterAiContext,
  ): void {
    // L11: the gate is conjunctive over the ORIGINAL-content decision. A successful
    // substitution ("it's tokenized now") never makes an unsafe provider safe.
    if (!decision.isProductionSafe || !decision.baaSatisfied) {
      throw new PhiEngineError("PROVIDER_SAFETY_GATE_FAILED", context.operationId, {
        providerId: decision.providerId,
      });
    }
  }

  async #requireContext(): Promise<MatterAiContext> {
    try {
      return await this.#deps.context.require();
    } catch (error) {
      throw error instanceof PhiEngineError
        ? error
        : new PhiEngineError("MISSING_TRUSTED_CONTEXT");
    }
  }

  async #prepareAudit(
    context: MatterAiContext,
    _policy: TrustedMatterAiPolicy,
    substitution: SubstitutionResult,
    purpose: AiOperation,
  ): Promise<AuditPreparationReceipt> {
    return this.#deps.audit.prepare(this.#preparedRecord(context, substitution, purpose));
  }

  #preparedRecord(
    context: MatterAiContext,
    substitution: SubstitutionResult,
    purpose: AiOperation,
  ): PhiAuditPreparedRecord {
    return {
      state: "PREPARED",
      attemptId: context.attemptId,
      operationId: context.operationId,
      tenantId: context.tenantId,
      matterId: context.matterId,
      actorId: context.actorId,
      operation: purpose,
      dictionaryVersion: substitution.dictionaryVersion,
      engineVersion: substitution.engineVersion,
      counts: substitution.counts,
      ambiguityCount: substitution.ambiguityCount,
      detectorName: substitution.detector?.name ?? null,
      detectorVersion: substitution.detector?.version ?? null,
      latencyMs: substitution.latencyMs,
      preparedAt: this.#clock(),
    };
  }

  async #reverseAndFinalize(
    rawOutput: TokenizedText,
    prepared: PreparedEgress<GenerateOptions>,
  ): Promise<DisplayText> {
    let display: DisplayText;
    try {
      // §4.1 step 11 / N5: reverse tokens to CURRENT canonical values before display.
      display = await this.#deps.engine.reverse(rawOutput, prepared.substitutionHandle);
    } catch (error) {
      await this.#finalize(prepared, "reversal_failed", "REVERSAL_FAILED");
      throw new PhiEngineError(
        toFailureCode(error, "REVERSAL_FAILED"),
        prepared.context.operationId,
        {},
      );
    }
    await this.#finalize(prepared, "completed", null);
    return display;
  }

  async #finalize(
    prepared: PreparedEgress<GenerateOptions>,
    outcome: "completed" | "reversal_failed",
    failureCode: PhiEngineFailureCode | null,
  ): Promise<void> {
    const event = preparedToTerminalEvent(
      this.#preparedRecord(prepared.context, prepared.substitution, prepared.purpose),
      outcome,
      failureCode,
      this.#clock(),
    );
    await this.#deps.audit.finalize(prepared.receipt, event);
  }
}

interface PreparedEgress<GenerateOptions> {
  readonly context: MatterAiContext;
  readonly purpose: AiOperation;
  readonly substitution: SubstitutionResult;
  readonly substitutionHandle: ReversalHandle;
  readonly tokenizedOptions: GenerateOptions;
  readonly receipt: AuditPreparationReceipt;
}
