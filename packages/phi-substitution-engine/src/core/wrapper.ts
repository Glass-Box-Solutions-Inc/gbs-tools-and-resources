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
 *   10. trace tokenized input (N2) and invoke the PINNED provider EXACTLY ONCE (N1);
 *   11. trace tokenized output (N2), then atomically reverse to current canonical
 *       values before display (N5) and finalize the audit event;
 *   12. on ANY precondition or post-send failure, invoke the provider ZERO extra
 *       times and finalize EXACTLY ONE terminal audit event (N3/N4).
 *
 * The phase-1 detector belt is never invoked for a customer claim.
 */
import type {
  DisplayText,
  EngineVersion,
  OperationId,
  TokenizedText,
} from "./brands";
import type {
  AiOperation,
  MatterAiContext,
  PhiEngineFailureCode,
  PhiSubstitutionEngine,
  ReversalHandle,
  SubstitutionResult,
  TokenizedTextSegment,
  TrustedMatterAiPolicy,
} from "./contracts";
import type {
  AiProvider,
  ProductionRawProviderPort,
  ProductionRawResultTail,
  ProductionRawTextResult,
  ProductionRawToolCall,
  ProtectedAiResultTail,
  ProtectedAiTextResult,
  ProtectedAiToolCall,
  ProtectedAiUsage,
  ProtectedAiProviderDependencies,
} from "./protected-ai-provider";
import type {
  AuditPreparationReceipt,
  PhiAuditEvent,
  PhiAuditOutcome,
  PhiAuditPreparedRecord,
} from "../audit/ports";
import {
  isAuditError,
  preparedToTerminalEvent,
  safeClockNow,
  toTotalIdentifierCounts,
} from "../audit/index";
import {
  isPhiEngineFailureCode,
  PhiEngineError,
  safeCodeString,
  toFailureCode,
} from "./errors";
import {
  safeOwnKeys,
  safeRead,
  safeString,
  intrinsicCopy,
} from "./boundary-snapshot";
import { REVERSAL_CANONICAL_CONFLICT_DETAIL } from "../tokens/conflict-sentinel";

/** The single private raw-provider port. It is never exported as an application binding. */
export interface RawProviderPort<GenerateOptions, EmbeddingKind = string> {
  generateText(options: GenerateOptions): Promise<TokenizedText>;
  generateStream(
    options: GenerateOptions,
    onChunk: (chunk: TokenizedText) => void | Promise<void>,
  ): Promise<void>;
  embedText(
    text: TokenizedText,
    kind: EmbeddingKind,
  ): Promise<readonly number[]>;
}

export interface ProtectedStreamResult {
  readonly displayChunks: readonly DisplayText[];
}

export interface ComposedProtectedAiProviderDeps<
  GenerateOptions,
  EmbeddingKind = string,
> extends ProtectedAiProviderDependencies<
  GenerateOptions,
  RawProviderPort<GenerateOptions, EmbeddingKind>
> {
  readonly engineVersion: EngineVersion;
  readonly clock?: () => string;
  /** Wraps a bare embedding string into routable/traceable options (§4.3). */
  readonly embeddingOptionsFactory?: (text: string) => GenerateOptions;
}

export interface ComposedProductionProtectedAiProviderDeps<
  GenerateOptions,
  EmbeddingKind = string,
> extends ProtectedAiProviderDependencies<
  GenerateOptions,
  ProductionRawProviderPort<GenerateOptions, EmbeddingKind>
> {
  readonly production: true;
  readonly engineVersion: EngineVersion;
  readonly clock?: () => string;
  readonly embeddingOptionsFactory: (text: string) => GenerateOptions;
}

type AnyRawProvider<GenerateOptions, EmbeddingKind> =
  | RawProviderPort<GenerateOptions, EmbeddingKind>
  | ProductionRawProviderPort<GenerateOptions, EmbeddingKind>;

type AnyComposedDeps<GenerateOptions, EmbeddingKind> =
  | ComposedProtectedAiProviderDeps<GenerateOptions, EmbeddingKind>
  | ComposedProductionProtectedAiProviderDeps<GenerateOptions, EmbeddingKind>;

const SAFE_RESULT_IDENTIFIER = /^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$/;
const INTERRUPTED = Symbol("GLY-353-interrupted");

type ProductionFailureOutcome =
  | "failed_closed"
  | "reversal_failed"
  | "unknown_after_send";

class ProductionCallFailure {
  public constructor(
    public readonly code: PhiEngineFailureCode,
    public readonly outcome: ProductionFailureOutcome,
  ) {}
}

type ControlledResult<T> =
  | Readonly<{ kind: "value"; value: T }>
  | Readonly<{ kind: "error"; error: unknown }>
  | Readonly<{ kind: "interrupted" }>;

/** Request-local first-terminal latch plus a private transport signal. */
class ProductionCallControl {
  readonly #controller = new AbortController();
  readonly #callerSignal: AbortSignal | undefined;
  readonly #onAbort: () => void;
  readonly #abortResult: Promise<Readonly<{ kind: "interrupted" }>>;
  #resolveAbort!: (value: Readonly<{ kind: "interrupted" }>) => void;
  #terminal: "interrupted" | "failure" | "completed" | null = null;
  #listening = false;

  public constructor(callerSignal?: AbortSignal) {
    this.#callerSignal = callerSignal;
    this.#abortResult = new Promise((resolve) => {
      this.#resolveAbort = resolve;
    });
    this.#onAbort = (): void => this.#interrupt();
    if (callerSignal !== undefined) {
      if (callerSignal.aborted) {
        this.#interrupt();
      } else {
        callerSignal.addEventListener("abort", this.#onAbort, { once: true });
        this.#listening = true;
      }
    }
  }

  public get signal(): AbortSignal {
    return this.#controller.signal;
  }

  public get interrupted(): boolean {
    return this.#terminal === "interrupted";
  }

  public latchFailure(): "failure" | "interrupted" | "completed" {
    if (this.#terminal === null) this.#terminal = "failure";
    return this.#terminal;
  }

  public latchCompleted(): boolean {
    if (this.#terminal !== null) return false;
    this.#terminal = "completed";
    return true;
  }

  public throwIfInterrupted(): void {
    if (this.interrupted) throw INTERRUPTED;
  }

  public async race<T>(work: Promise<T>): Promise<ControlledResult<T>> {
    const settled: Promise<ControlledResult<T>> = Promise.resolve(work).then(
      (value): ControlledResult<T> => ({ kind: "value", value }),
      (error: unknown): ControlledResult<T> => ({ kind: "error", error }),
    );
    return Promise.race([settled, this.#abortResult]);
  }

  public dispose(): void {
    if (this.#listening && this.#callerSignal !== undefined) {
      try {
        this.#callerSignal.removeEventListener("abort", this.#onAbort);
      } catch {
        // Listener cleanup is best-effort and must never surface a caller-controlled throw.
      }
      this.#listening = false;
    }
  }

  #interrupt(): void {
    if (this.#terminal !== null) return;
    this.#terminal = "interrupted";
    try {
      this.#controller.abort();
    } catch {
      // Transport cancellation is best-effort; the local interruption latch is authoritative.
    }
    this.#resolveAbort({ kind: "interrupted" });
  }
}

interface SnapshotProductionTail {
  readonly model: string | undefined;
  readonly usage: ProtectedAiUsage | undefined;
  readonly toolCalls: readonly ProductionRawToolCall[] | undefined;
}

interface SnapshotProductionText {
  readonly text: TokenizedText;
  readonly tail: SnapshotProductionTail;
}

function ownKey(keys: readonly string[], expected: string): boolean {
  for (let i = 0; i < keys.length; i += 1) {
    if (keys[i] === expected) return true;
  }
  return false;
}

/**
 * Extracts a safe fixed error-code string for a terminal audit event's failureCode. A `code` is
 * honored ONLY if it is a recognized `PhiEngineFailureCode` — a `PhiEngineError` instance's `.code`
 * is not trusted just for being an instance (an injected component could cast a raw value to a
 * code), so nothing PHI-laden can land in the durable audit trail (§7/N2).
 */
function errorCodeString(error: unknown): string {
  const code = safeCodeString(error);
  return code !== undefined &&
    code !== "CALL_INTERRUPTED" &&
    isPhiEngineFailureCode(code)
    ? code
    : "FAILED_CLOSED";
}

/**
 * GLY-373 §3.2.5 — projects the engine's fixed `safeDetails.conflict` discriminator into the
 * durable audit record, so a reversal-key canonical conflict is distinguishable from dictionary
 * ambiguity long after the call (both surface as `AMBIGUOUS_KNOWN_IDENTIFIER`, and the ruling
 * forbids widening the published failure-code union).
 *
 * §7/N2 discipline is unchanged: the value is read ONCE behind a getter-throw guard and is
 * returned ONLY when it is EXACTLY the one fixed literal. Anything else — a hostile string, a
 * non-string, a throwing getter — yields `null`, so nothing PHI-laden can reach the record. The
 * serializer's `TERMINAL_FAILURE_DETAILS` allow-list is a second, independent gate.
 */
function errorFailureDetail(error: unknown): string | null {
  try {
    if (error === null || typeof error !== "object") {
      return null;
    }
    const details = (error as { safeDetails?: unknown }).safeDetails;
    if (details === null || typeof details !== "object") {
      return null;
    }
    const conflict = (details as { conflict?: unknown }).conflict;
    return conflict === REVERSAL_CANONICAL_CONFLICT_DETAIL ? conflict : null;
  } catch {
    return null;
  }
}

export class ComposedProtectedAiProvider<
  GenerateOptions,
  EmbeddingKind = string,
> implements AiProvider<
  GenerateOptions,
  Promise<DisplayText>,
  Promise<ProtectedStreamResult>,
  EmbeddingKind,
  Promise<readonly number[]>
> {
  readonly #deps: AnyComposedDeps<GenerateOptions, EmbeddingKind>;
  readonly #clock: () => string;

  public constructor(deps: AnyComposedDeps<GenerateOptions, EmbeddingKind>) {
    this.#deps = deps;
    // §7/N2: `deps.clock` is the ONE dependency read EAGERLY at construction; a throwing `clock` getter
    // must not propagate a raw (PHI) throw out of the public constructor. Read it getter-throw-safe and
    // fall back to the default clock. (Every OTHER dependency is read lazily inside a guarded request
    // path, so a throwing getter there is already sanitized to a fixed code.)
    let injectedClock: unknown;
    try {
      injectedClock = deps.clock;
    } catch {
      injectedClock = undefined;
    }
    this.#clock =
      typeof injectedClock === "function"
        ? (injectedClock as () => string)
        : (): string => new Date().toISOString();
  }

  public async generateText(options: GenerateOptions): Promise<DisplayText> {
    const context = await this.#requireContext();

    let prepared: PreparedEgress<GenerateOptions, EmbeddingKind>;
    try {
      // §4.1 step 2 / N3: policy load is INSIDE the protected region — a policy rejection
      // after context is known finalizes exactly one terminal.
      const policy = await this.#deps.policy.require(context);
      prepared = await this.#prepareForEgress(
        options,
        "generation",
        context,
        policy,
      );
    } catch (error) {
      // §4.1 step 12 / N3: any pre-egress failure finalizes exactly one terminal.
      await this.#recordPreEgressFailure(context, "generation", error);
      // §7: never surface a raw upstream message/code to the caller.
      throw new PhiEngineError(
        toFailureCode(error, "PROVIDER_SAFETY_GATE_FAILED"),
        context.operationId,
        {},
      );
    }

    // §4.1 step 10 / N2/N3: trace the tokenized input AFTER prepare; a failure here finalizes
    // exactly one terminal against the receipt and never re-prepares.
    await this.#traceTokenizedRequest(prepared);

    let rawOutput: TokenizedText;
    try {
      // §4.1 step 10 / N1: invoke the PINNED provider EXACTLY ONCE with tokenized options.
      rawOutput = await (
        prepared.provider as RawProviderPort<GenerateOptions, EmbeddingKind>
      ).generateText(prepared.tokenizedOptions);
    } catch (error) {
      // N3: a provider rejection after send still finalizes exactly one terminal.
      await this.#finalizeQuietly(
        prepared,
        "unknown_after_send",
        errorCodeString(error),
      );
      throw new PhiEngineError(
        toFailureCode(error, "REVERSAL_FAILED"),
        prepared.context.operationId,
        {},
      );
    }
    // §7/N2: the provider result is an INJECTED-port return. A NON-STRING carrier (e.g. an object with a
    // PHI-producing `toJSON`) must NOT be forwarded to the trace or reversal — require a genuine string
    // (the tokenized output) and fail closed otherwise, so nothing but a tokenized string reaches a sink.
    if (typeof (rawOutput as unknown) !== "string") {
      await this.#finalizeQuietly(
        prepared,
        "unknown_after_send",
        "PROVIDER_SAFETY_GATE_FAILED",
      );
      throw new PhiEngineError(
        "PROVIDER_SAFETY_GATE_FAILED",
        prepared.context.operationId,
        {},
      );
    }
    // §4.1 step 11 / N2/N3: tracing the tokenized output is AFTER the single provider call, so a
    // trace failure here still finalizes exactly one terminal (provider already invoked once).
    try {
      await this.#deps.safeTrace.response(rawOutput);
    } catch (error) {
      await this.#finalizeQuietly(
        prepared,
        "unknown_after_send",
        errorCodeString(error),
      );
      throw new PhiEngineError(
        toFailureCode(error, "REVERSAL_FAILED"),
        prepared.context.operationId,
        {},
      );
    }
    return this.#reverseAndFinalize(rawOutput, prepared);
  }

  public async generateStream(
    options: GenerateOptions,
  ): Promise<ProtectedStreamResult> {
    const context = await this.#requireContext();

    let prepared: PreparedEgress<GenerateOptions, EmbeddingKind>;
    try {
      const policy = await this.#deps.policy.require(context);
      prepared = await this.#prepareForEgress(
        options,
        "stream",
        context,
        policy,
      );
    } catch (error) {
      await this.#recordPreEgressFailure(context, "stream", error);
      throw new PhiEngineError(
        toFailureCode(error, "PROVIDER_SAFETY_GATE_FAILED"),
        context.operationId,
        {},
      );
    }

    // §4.2 / N2/N3: trace the tokenized input AFTER prepare; a failure finalizes exactly one
    // terminal against the receipt and never re-prepares.
    await this.#traceTokenizedRequest(prepared);

    const displayChunks: DisplayText[] = [];
    let stream: ReturnType<PhiSubstitutionEngine["createReverseStream"]>;
    try {
      // §4.2 / N3: the reverse-stream factory runs BEFORE egress; a factory throw finalizes a
      // fail-closed terminal with zero provider calls.
      stream = this.#deps.engine.createReverseStream(
        prepared.substitutionHandle,
        (safe) => {
          // §7/N2: the injected engine drives this sink — a NON-STRING carrier must NOT be placed in the
          // caller-visible displayChunks. Drop anything that is not a genuine string (fail closed).
          if (typeof (safe as unknown) === "string") {
            displayChunks.push(safe);
          }
        },
      );
    } catch (error) {
      await this.#finalizeQuietly(
        prepared,
        "failed_closed",
        errorCodeString(error),
      );
      throw new PhiEngineError(
        toFailureCode(error, "PROVIDER_SAFETY_GATE_FAILED"),
        prepared.context.operationId,
        {},
      );
    }
    try {
      // §4.1 step 10 / N1: exactly one PINNED provider call.
      await (
        prepared.provider as RawProviderPort<GenerateOptions, EmbeddingKind>
      ).generateStream(prepared.tokenizedOptions, async (chunk) => {
        // §7/N2: each streamed chunk is an INJECTED-port return — a NON-STRING carrier must NOT be
        // traced or pushed to reversal. Fail closed BEFORE either sink (the catch below latches the
        // stream and surfaces a fixed code).
        if (typeof (chunk as unknown) !== "string") {
          throw new PhiEngineError(
            "PROVIDER_SAFETY_GATE_FAILED",
            prepared.context.operationId,
            {},
          );
        }
        // §4.2 / N2: trace tokenized chunk, then feed it to the reverse stream only.
        await this.#deps.safeTrace.response(chunk);
        await stream.push(chunk);
      });
      await stream.end();
    } catch (error) {
      // L4: latch the reverse stream so no later chunk can resume/complete. §7/N2: `abort()` is an
      // injected-stream capability — its OWN rejection could carry PHI, so it is swallowed here and
      // the caller sees only the fixed-code error below, never the raw abort rejection.
      try {
        await stream.abort(error);
      } catch {
        /* best-effort latch; a hostile abort rejection must not escape */
      }
      const code = toFailureCode(error, "REVERSAL_FAILED");
      const outcome: PhiAuditOutcome =
        code === "REVERSAL_FAILED" ? "reversal_failed" : "unknown_after_send";
      // N3: a push/end failure after send still finalizes exactly one terminal.
      await this.#finalizeQuietly(prepared, outcome, code);
      throw new PhiEngineError(code, prepared.context.operationId, {});
    }
    await this.#finalizeStrict(prepared, "completed", null);
    return { displayChunks };
  }

  /** GLY-353 production text path. Only the production factory exposes this method. */
  public async generateProductionText(
    options: GenerateOptions,
    callerSignal?: AbortSignal,
  ): Promise<ProtectedAiTextResult> {
    const context = await this.#requireContext();
    let control: ProductionCallControl;
    try {
      control = new ProductionCallControl(callerSignal);
    } catch {
      await this.#recordFailedClosedTerminal(
        context,
        "generation",
        "PROVIDER_SAFETY_GATE_FAILED",
      );
      throw new PhiEngineError(
        "PROVIDER_SAFETY_GATE_FAILED",
        context.operationId,
        {},
      );
    }

    let prepared: PreparedEgress<GenerateOptions, EmbeddingKind> | undefined;
    try {
      if (control.interrupted) {
        await this.#recordInterruptedTerminal(context, "generation");
        throw INTERRUPTED;
      }

      try {
        const policy = await this.#deps.policy.require(context);
        control.throwIfInterrupted();
        prepared = await this.#prepareForEgress(
          options,
          "generation",
          context,
          policy,
        );
      } catch (error) {
        if (control.interrupted || error === INTERRUPTED) {
          if (!isAuditError(error))
            await this.#recordInterruptedTerminal(context, "generation");
          throw INTERRUPTED;
        }
        control.latchFailure();
        await this.#recordPreEgressFailure(context, "generation", error);
        throw new ProductionCallFailure(
          this.#safeProductionCode(error, "PROVIDER_SAFETY_GATE_FAILED"),
          "failed_closed",
        );
      }

      if (control.interrupted) throw INTERRUPTED;
      await this.#traceProductionRequest(prepared, control);

      const provider = prepared.provider as ProductionRawProviderPort<
        GenerateOptions,
        EmbeddingKind
      >;
      const raw = await this.#awaitControlled(
        control,
        provider.generateText(prepared.tokenizedOptions, control.signal),
        (error) =>
          new ProductionCallFailure(
            this.#safeProductionCode(error, "REVERSAL_FAILED"),
            "unknown_after_send",
          ),
      );
      const snapshot = this.#snapshotProductionTextResult(raw);
      await this.#traceProductionResponse(snapshot.text, control);
      const display = await this.#reverseProductionValue(
        snapshot.text,
        prepared,
        control,
      );
      const toolCalls = await this.#reverseProductionTools(
        snapshot.tail.toolCalls,
        prepared,
        control,
      );
      const result = this.#freezeProductionTextResult(
        display,
        prepared.providerId,
        snapshot.tail.model,
        snapshot.tail.usage,
        toolCalls,
      );

      if (!control.latchCompleted()) throw INTERRUPTED;
      await this.#finalizeStrict(prepared, "completed", null);
      return result;
    } catch (error) {
      if (prepared !== undefined) {
        if (control.interrupted || error === INTERRUPTED) {
          await this.#finalizeQuietly(prepared, "interrupted", null);
        } else if (error instanceof ProductionCallFailure) {
          await this.#finalizeQuietly(prepared, error.outcome, error.code);
        }
      }
      if (control.interrupted || error === INTERRUPTED) {
        throw new PhiEngineError("CALL_INTERRUPTED", context.operationId, {});
      }
      if (error instanceof PhiEngineError) throw error;
      if (error instanceof ProductionCallFailure) {
        throw new PhiEngineError(error.code, context.operationId, {});
      }
      throw new PhiEngineError(
        "PROVIDER_SAFETY_GATE_FAILED",
        context.operationId,
        {},
      );
    } finally {
      control.dispose();
    }
  }

  /** GLY-353 production live-stream path. Only reversed strings reach `sink`. */
  public async streamProductionText(
    options: GenerateOptions,
    sink: (chunk: DisplayText) => void | Promise<void>,
    callerSignal?: AbortSignal,
  ): Promise<ProtectedAiResultTail> {
    const context = await this.#requireContext();
    let control: ProductionCallControl;
    try {
      control = new ProductionCallControl(callerSignal);
    } catch {
      await this.#recordFailedClosedTerminal(
        context,
        "stream",
        "PROVIDER_SAFETY_GATE_FAILED",
      );
      throw new PhiEngineError(
        "PROVIDER_SAFETY_GATE_FAILED",
        context.operationId,
        {},
      );
    }

    let prepared: PreparedEgress<GenerateOptions, EmbeddingKind> | undefined;
    let stream:
      | ReturnType<PhiSubstitutionEngine["createReverseStream"]>
      | undefined;
    try {
      if (control.interrupted) {
        await this.#recordInterruptedTerminal(context, "stream");
        throw INTERRUPTED;
      }
      try {
        const policy = await this.#deps.policy.require(context);
        control.throwIfInterrupted();
        prepared = await this.#prepareForEgress(
          options,
          "stream",
          context,
          policy,
        );
      } catch (error) {
        if (control.interrupted || error === INTERRUPTED) {
          if (!isAuditError(error))
            await this.#recordInterruptedTerminal(context, "stream");
          throw INTERRUPTED;
        }
        control.latchFailure();
        await this.#recordPreEgressFailure(context, "stream", error);
        throw new ProductionCallFailure(
          this.#safeProductionCode(error, "PROVIDER_SAFETY_GATE_FAILED"),
          "failed_closed",
        );
      }

      control.throwIfInterrupted();
      await this.#traceProductionRequest(prepared, control);
      try {
        stream = this.#deps.engine.createReverseStream(
          prepared.substitutionHandle,
          async (safe) => {
            control.throwIfInterrupted();
            if (typeof (safe as unknown) !== "string") {
              control.latchFailure();
              throw new ProductionCallFailure(
                "PROVIDER_SAFETY_GATE_FAILED",
                "reversal_failed",
              );
            }
            await this.#awaitControlled(
              control,
              Promise.resolve().then(() => sink(safe)),
              () =>
                new ProductionCallFailure(
                  "PROVIDER_SAFETY_GATE_FAILED",
                  "unknown_after_send",
                ),
            );
          },
        );
      } catch (error) {
        if (control.interrupted || error === INTERRUPTED) throw INTERRUPTED;
        control.latchFailure();
        throw error instanceof ProductionCallFailure
          ? error
          : new ProductionCallFailure(
              "PROVIDER_SAFETY_GATE_FAILED",
              "failed_closed",
            );
      }

      const provider = prepared.provider as ProductionRawProviderPort<
        GenerateOptions,
        EmbeddingKind
      >;
      const rawTail = await this.#awaitControlled(
        control,
        provider.generateStream(
          prepared.tokenizedOptions,
          async (chunk) => {
            control.throwIfInterrupted();
            if (typeof (chunk as unknown) !== "string") {
              control.latchFailure();
              throw new ProductionCallFailure(
                "PROVIDER_SAFETY_GATE_FAILED",
                "unknown_after_send",
              );
            }
            await this.#traceProductionResponse(chunk, control);
            await this.#awaitControlled(
              control,
              stream!.push(chunk),
              (error) =>
                error instanceof ProductionCallFailure
                  ? error
                  : new ProductionCallFailure(
                      "REVERSAL_FAILED",
                      "reversal_failed",
                    ),
            );
          },
          control.signal,
        ),
        (error) =>
          error instanceof ProductionCallFailure
            ? error
            : new ProductionCallFailure(
                this.#safeProductionCode(error, "REVERSAL_FAILED"),
                "unknown_after_send",
              ),
      );

      await this.#awaitControlled(control, stream.end(), (error) =>
        error instanceof ProductionCallFailure
          ? error
          : new ProductionCallFailure("REVERSAL_FAILED", "reversal_failed"),
      );
      const snapshot = this.#snapshotProductionTail(rawTail);
      const toolCalls = await this.#reverseProductionTools(
        snapshot.toolCalls,
        prepared,
        control,
      );
      const tail = this.#freezeProductionTail(
        prepared.providerId,
        snapshot.model,
        snapshot.usage,
        toolCalls,
      );
      if (!control.latchCompleted()) throw INTERRUPTED;
      await this.#finalizeStrict(prepared, "completed", null);
      return tail;
    } catch (error) {
      if (stream !== undefined) {
        try {
          await stream.abort(undefined);
        } catch {
          // Reverse-stream cancellation is best-effort and never escapes raw.
        }
      }
      if (prepared !== undefined) {
        if (control.interrupted || error === INTERRUPTED) {
          await this.#finalizeQuietly(prepared, "interrupted", null);
        } else if (error instanceof ProductionCallFailure) {
          await this.#finalizeQuietly(prepared, error.outcome, error.code);
        }
      }
      if (control.interrupted || error === INTERRUPTED) {
        throw new PhiEngineError("CALL_INTERRUPTED", context.operationId, {});
      }
      if (error instanceof PhiEngineError) throw error;
      if (error instanceof ProductionCallFailure) {
        throw new PhiEngineError(error.code, context.operationId, {});
      }
      throw new PhiEngineError(
        "PROVIDER_SAFETY_GATE_FAILED",
        context.operationId,
        {},
      );
    } finally {
      control.dispose();
    }
  }

  async #awaitControlled<T>(
    control: ProductionCallControl,
    work: Promise<T>,
    failure: (error: unknown) => ProductionCallFailure,
  ): Promise<T> {
    const result = await control.race(work);
    if (result.kind === "interrupted") throw INTERRUPTED;
    if (result.kind === "error") {
      const winner = control.latchFailure();
      if (winner === "interrupted") throw INTERRUPTED;
      if (result.error instanceof ProductionCallFailure) throw result.error;
      throw failure(result.error);
    }
    control.throwIfInterrupted();
    return result.value;
  }

  #safeProductionCode(
    error: unknown,
    fallback: PhiEngineFailureCode,
  ): PhiEngineFailureCode {
    const code = safeCodeString(error);
    return code !== undefined &&
      code !== "CALL_INTERRUPTED" &&
      isPhiEngineFailureCode(code)
      ? code
      : fallback;
  }

  async #traceProductionRequest(
    prepared: PreparedEgress<GenerateOptions, EmbeddingKind>,
    control: ProductionCallControl,
  ): Promise<void> {
    const traced: { path: string; text: TokenizedText }[] = [];
    for (let i = 0; i < prepared.tracedSegments.length; i += 1) {
      const segment = prepared.tracedSegments[i]!;
      traced[traced.length] = { path: segment.path, text: segment.text };
    }
    await this.#awaitControlled(
      control,
      this.#deps.safeTrace.request(traced),
      (error) =>
        new ProductionCallFailure(
          this.#safeProductionCode(error, "PROVIDER_SAFETY_GATE_FAILED"),
          "failed_closed",
        ),
    );
  }

  async #traceProductionResponse(
    text: TokenizedText,
    control: ProductionCallControl,
  ): Promise<void> {
    await this.#awaitControlled(
      control,
      this.#deps.safeTrace.response(text),
      (error) =>
        new ProductionCallFailure(
          this.#safeProductionCode(error, "PROVIDER_SAFETY_GATE_FAILED"),
          "unknown_after_send",
        ),
    );
  }

  #snapshotProductionTextResult(
    raw: ProductionRawTextResult,
  ): SnapshotProductionText {
    const text = safeString(raw, "text");
    if (text === undefined) {
      throw new ProductionCallFailure(
        "PROVIDER_SAFETY_GATE_FAILED",
        "unknown_after_send",
      );
    }
    return {
      text: text as TokenizedText,
      tail: this.#snapshotProductionTail(raw),
    };
  }

  #snapshotProductionTail(
    raw: ProductionRawResultTail,
  ): SnapshotProductionTail {
    if (raw === null || typeof raw !== "object" || Array.isArray(raw)) {
      throw new ProductionCallFailure(
        "PROVIDER_SAFETY_GATE_FAILED",
        "unknown_after_send",
      );
    }
    const keys = safeOwnKeys(raw);
    let model: string | undefined;
    if (ownKey(keys, "model")) {
      model = safeString(raw, "model");
      if (model === undefined || !SAFE_RESULT_IDENTIFIER.test(model)) {
        throw new ProductionCallFailure(
          "PROVIDER_SAFETY_GATE_FAILED",
          "unknown_after_send",
        );
      }
    }

    let usage: ProtectedAiUsage | undefined;
    if (ownKey(keys, "usage")) {
      const liveUsage = safeRead(raw, "usage");
      if (
        liveUsage === null ||
        typeof liveUsage !== "object" ||
        Array.isArray(liveUsage)
      ) {
        throw new ProductionCallFailure(
          "PROVIDER_SAFETY_GATE_FAILED",
          "unknown_after_send",
        );
      }
      const usageKeys = safeOwnKeys(liveUsage);
      const copied: {
        inputTokens?: number;
        outputTokens?: number;
        totalTokens?: number;
      } = {};
      for (const key of [
        "inputTokens",
        "outputTokens",
        "totalTokens",
      ] as const) {
        if (!ownKey(usageKeys, key)) continue;
        const value = safeRead(liveUsage, key);
        if (
          typeof value !== "number" ||
          !Number.isSafeInteger(value) ||
          value < 0
        ) {
          throw new ProductionCallFailure(
            "PROVIDER_SAFETY_GATE_FAILED",
            "unknown_after_send",
          );
        }
        copied[key] = value;
      }
      usage = Object.freeze(copied);
    }

    let toolCalls: readonly ProductionRawToolCall[] | undefined;
    if (ownKey(keys, "toolCalls")) {
      const liveTools = intrinsicCopy<unknown>(safeRead(raw, "toolCalls"));
      if (liveTools === null) {
        throw new ProductionCallFailure(
          "PROVIDER_SAFETY_GATE_FAILED",
          "unknown_after_send",
        );
      }
      const copied: ProductionRawToolCall[] = [];
      for (let i = 0; i < liveTools.length; i += 1) {
        const tool = liveTools[i];
        const id = safeString(tool, "id");
        const name = safeString(tool, "name");
        const argument = safeString(tool, "arguments");
        if (
          id === undefined ||
          name === undefined ||
          argument === undefined ||
          !SAFE_RESULT_IDENTIFIER.test(id) ||
          !SAFE_RESULT_IDENTIFIER.test(name)
        ) {
          throw new ProductionCallFailure(
            "PROVIDER_SAFETY_GATE_FAILED",
            "unknown_after_send",
          );
        }
        copied[copied.length] = Object.freeze({
          id,
          name,
          arguments: argument as TokenizedText,
        });
      }
      toolCalls = Object.freeze(copied);
    }
    return { model, usage, toolCalls };
  }

  async #reverseProductionValue(
    text: TokenizedText,
    prepared: PreparedEgress<GenerateOptions, EmbeddingKind>,
    control: ProductionCallControl,
  ): Promise<DisplayText> {
    const display = await this.#awaitControlled(
      control,
      this.#deps.engine.reverse(text, prepared.substitutionHandle),
      () => new ProductionCallFailure("REVERSAL_FAILED", "reversal_failed"),
    );
    if (typeof (display as unknown) !== "string") {
      control.latchFailure();
      throw new ProductionCallFailure("REVERSAL_FAILED", "reversal_failed");
    }
    return display;
  }

  async #reverseProductionTools(
    tools: readonly ProductionRawToolCall[] | undefined,
    prepared: PreparedEgress<GenerateOptions, EmbeddingKind>,
    control: ProductionCallControl,
  ): Promise<readonly ProtectedAiToolCall[] | undefined> {
    if (tools === undefined) return undefined;
    const safe: ProtectedAiToolCall[] = [];
    for (let i = 0; i < tools.length; i += 1) {
      control.throwIfInterrupted();
      const tool = tools[i]!;
      const displayArguments = await this.#reverseProductionValue(
        tool.arguments,
        prepared,
        control,
      );
      safe[safe.length] = Object.freeze({
        id: tool.id,
        name: tool.name,
        arguments: displayArguments,
      });
    }
    return Object.freeze(safe);
  }

  #freezeProductionTail(
    providerId: string,
    model: string | undefined,
    usage: ProtectedAiUsage | undefined,
    toolCalls: readonly ProtectedAiToolCall[] | undefined,
  ): ProtectedAiResultTail {
    const tail: {
      providerId: string;
      model?: string;
      usage?: ProtectedAiUsage;
      toolCalls?: readonly ProtectedAiToolCall[];
    } = { providerId };
    if (model !== undefined) tail.model = model;
    if (usage !== undefined) tail.usage = usage;
    if (toolCalls !== undefined) tail.toolCalls = toolCalls;
    return Object.freeze(tail);
  }

  #freezeProductionTextResult(
    display: DisplayText,
    providerId: string,
    model: string | undefined,
    usage: ProtectedAiUsage | undefined,
    toolCalls: readonly ProtectedAiToolCall[] | undefined,
  ): ProtectedAiTextResult {
    return Object.freeze({
      display,
      ...this.#freezeProductionTail(providerId, model, usage, toolCalls),
    });
  }

  /** Best-effort zero-egress interruption record. Durability failure never overrides CALL_INTERRUPTED. */
  async #recordInterruptedTerminal(
    context: MatterAiContext,
    purpose: AiOperation,
  ): Promise<void> {
    const record = this.#minimalPreparedRecord(context, purpose);
    try {
      const receipt = await this.#deps.audit.prepare(record);
      await this.#finalizeAt(receipt, record, "interrupted", null);
    } catch {
      // GLY-353 R3: interruption remains the caller-visible outcome when PREPARE is unavailable.
    }
  }

  public async embedText(
    text: string,
    kind: EmbeddingKind,
  ): Promise<readonly number[]> {
    const context = await this.#requireContext();

    // §4.3 / L11: embedding MUST route on ORIGINAL content and enforce the conjunctive
    // safety/BAA gate. Without a factory we cannot inspect original content, so we FAIL
    // CLOSED with zero egress rather than skipping routing.
    if (this.#deps.embeddingOptionsFactory === undefined) {
      await this.#recordFailedClosedTerminal(
        context,
        "embedding",
        "PROVIDER_SAFETY_GATE_FAILED",
      );
      throw new PhiEngineError(
        "PROVIDER_SAFETY_GATE_FAILED",
        context.operationId,
        {},
      );
    }

    let providerBinding: AnyRawProvider<GenerateOptions, EmbeddingKind>;
    let substitution: SubstitutionResult;
    let receipt: AuditPreparationReceipt;
    let tokenizedText: TokenizedText;
    try {
      // §4.3 step 2 / N3: policy load, routing/gate, substitution, and the durable PREPARE
      // are ALL inside the protected region — any failure after context finalizes exactly one
      // terminal (N3) and NEVER surfaces a raw upstream message/code to the caller (§7).
      const policy = await this.#deps.policy.require(context);
      const routingOptions = this.#deps.embeddingOptionsFactory(text);
      const decision =
        await this.#deps.router.selectUsingOriginalContent(routingOptions);
      this.#enforceSafetyGate(decision, context);
      providerBinding = decision.provider;
      // §4.3: substitute the embedding text; tokenized-only, NO output reversal.
      substitution = this.#snapshotSubstitution(
        await this.#deps.engine.substitute({
          context,
          policy,
          segments: [{ path: "embedding", kind: "embedding", text }],
          purpose: "embedding",
        }),
      );
      tokenizedText =
        substitution.segments[0]?.text ?? ("" as unknown as TokenizedText);
      receipt = await this.#prepareAudit(
        context,
        policy,
        substitution,
        "embedding",
      );
    } catch (error) {
      await this.#recordPreEgressFailure(context, "embedding", error);
      throw new PhiEngineError(
        toFailureCode(error, "PROVIDER_SAFETY_GATE_FAILED"),
        context.operationId,
        {},
      );
    }

    // §4.3 step 10 / N2/N3: tracing the tokenized input runs AFTER the durable prepare, so a
    // failure here finalizes against THIS receipt (exactly one terminal, no second prepare) and
    // surfaces only a fixed code.
    try {
      await this.#deps.safeTrace.request([
        { path: "embedding", text: tokenizedText },
      ]);
    } catch (error) {
      await this.#finalizeAtQuietly(
        receipt,
        this.#preparedRecord(context, substitution, "embedding"),
        "failed_closed",
        errorCodeString(error),
      );
      throw new PhiEngineError(
        toFailureCode(error, "PROVIDER_SAFETY_GATE_FAILED"),
        context.operationId,
        {},
      );
    }

    let vector: readonly number[];
    try {
      vector = await providerBinding.embedText(tokenizedText, kind);
    } catch (error) {
      await this.#finalizeAtQuietly(
        receipt,
        this.#preparedRecord(context, substitution, "embedding"),
        "unknown_after_send",
        errorCodeString(error),
      );
      throw new PhiEngineError(
        toFailureCode(error, "REVERSAL_FAILED"),
        context.operationId,
        {},
      );
    }

    // §7/N2: the raw provider's embedding is a boundary result. Validate it is a genuine array of
    // FINITE numbers and copy it by OWN index/length into a fresh array — a NON-array carrier, a
    // throwing/mutating index getter, or a non-numeric element must fail closed, never reach the
    // caller as an object that could carry PHI (e.g. a PHI-throwing `get 0()`), and never egress raw.
    // `intrinsicCopy` reads `.length` AND every element INSIDE its own try (Array.isArray sees through
    // a Proxy to an array target, so a Proxy `get length`/`get 0` trap that throws must not escape the
    // guard) — a non-array carrier or any throwing read yields null → fail closed.
    const rawVector = intrinsicCopy<unknown>(vector);
    const safeVector: number[] = [];
    let vectorOk = rawVector !== null;
    if (rawVector !== null) {
      for (let i = 0; i < rawVector.length; i += 1) {
        const element = rawVector[i];
        if (typeof element !== "number" || !Number.isFinite(element)) {
          vectorOk = false;
          break;
        }
        safeVector[safeVector.length] = element;
      }
    }
    if (!vectorOk) {
      await this.#finalizeAtQuietly(
        receipt,
        this.#preparedRecord(context, substitution, "embedding"),
        "unknown_after_send",
        "PROVIDER_SAFETY_GATE_FAILED",
      );
      throw new PhiEngineError(
        "PROVIDER_SAFETY_GATE_FAILED",
        context.operationId,
        {},
      );
    }

    await this.#finalizeAtStrict(
      receipt,
      this.#preparedRecord(context, substitution, "embedding"),
      "completed",
      null,
      context.operationId,
    );
    return safeVector;
  }

  /** Steps 3–9: everything that must succeed before the provider may be invoked. */
  async #prepareForEgress(
    options: GenerateOptions,
    purpose: Exclude<AiOperation, "graph_extraction">,
    context: MatterAiContext,
    policy: TrustedMatterAiPolicy,
  ): Promise<PreparedEgress<GenerateOptions, EmbeddingKind>> {
    // §4.1 step 3 / L11: route on ORIGINAL content and PIN the decision, then gate.
    const liveDecision =
      await this.#deps.router.selectUsingOriginalContent(options);
    const provider = safeRead(liveDecision, "provider") as
      | AnyRawProvider<GenerateOptions, EmbeddingKind>
      | undefined;
    const providerId = safeString(liveDecision, "providerId");
    const decision = {
      provider,
      providerId,
      isProductionSafe: safeRead(liveDecision, "isProductionSafe") === true,
      baaSatisfied: safeRead(liveDecision, "baaSatisfied") === true,
    };
    if (
      provider === undefined ||
      providerId === undefined ||
      !SAFE_RESULT_IDENTIFIER.test(providerId)
    ) {
      throw new PhiEngineError(
        "PROVIDER_SAFETY_GATE_FAILED",
        context.operationId,
        {},
      );
    }
    this.#enforceSafetyGate(
      {
        providerId,
        isProductionSafe: decision.isProductionSafe,
        baaSatisfied: decision.baaSatisfied,
      },
      context,
    );

    // §4.1 step 4 / L5: exhaustive, fail-closed projection of all text fields.
    const classified = this.#classify(options, context);

    // §4.1 steps 5–8: substitute + build the non-serializable reversal handle. The injected engine's
    // result is snapshotted read-once (§7/N2) so no later prepared-record build re-reads a hostile
    // metadata getter.
    const substitution = this.#snapshotSubstitution(
      await this.#deps.engine.substitute({
        context,
        policy,
        segments: classified.segments,
        purpose,
      }),
    );
    // §7/N2: snapshot the injected engine's segments ONCE (path/text read a single time, by index)
    // so rebuild and the later trace see identical values — a mutating own getter cannot show a
    // tokenized value to rebuild and raw PHI to the trace, and a poisoned own iterator cannot slip a
    // raw value past rebuild's classification.
    const tracedSegments = snapshotSegments(substitution.segments);
    // §4.1 step 4 / L5: rebuild asserts a 1:1 path↔tokenized-segment mapping; a missing
    // or unexpected path fails closed here, before egress.
    const tokenizedOptions = classified.rebuild(
      tracedSegments as unknown as readonly TokenizedTextSegment[],
    );

    // N3: read every value the prepared record needs — including the PINNED provider and the
    // reversal handle, which may be adversarial getters — BEFORE the durable PREPARE. Nothing may
    // be dereferenced AFTER prepare, or a throw there would re-enter the pre-egress handler and
    // prepare a SECOND durable record (no double-prepare). Prepare is therefore the LAST step.
    const substitutionHandle = substitution.reversalHandle;
    // L11: the read-once pinned provider for the routed+gated decision.

    // §4.1 step 9 / N3: durably PREPARE the metadata-only record BEFORE egress (and last here).
    const receipt = await this.#prepareAudit(
      context,
      policy,
      substitution,
      purpose,
    );

    const prepared: PreparedEgress<GenerateOptions, EmbeddingKind> = {
      context,
      purpose,
      substitution,
      substitutionHandle,
      tokenizedOptions,
      receipt,
      provider,
      providerId,
      tracedSegments,
    };

    // §4.1 step 10 tracing of the tokenized input happens in the CALLER (after this returns), not
    // here: a post-prepare failure must be finalized against THIS receipt WITHOUT ever reaching the
    // pre-egress handler, which would otherwise prepare a SECOND durable record (no double-prepare).
    return prepared;
  }

  /**
   * §4.1 step 10 / N2/N3: trace the TOKENIZED request input AFTER the durable prepare. A trace
   * failure finalizes against THIS receipt (exactly one terminal, no second prepare) and surfaces
   * only a fixed, PHI-free code. Deliberately called by the egress methods rather than inside
   * `#prepareForEgress`, so its failure propagates straight to the caller and never re-enters
   * `#recordPreEgressFailure` (which would prepare again).
   */
  async #traceTokenizedRequest(
    prepared: PreparedEgress<GenerateOptions, EmbeddingKind>,
  ): Promise<void> {
    try {
      // Trace the INERT read-once snapshot (built by #prepareForEgress from the injected engine's
      // segments), NEVER the live substitution object — so a mutating getter or a poisoned own
      // `map`/iterator cannot swap the TOKENIZED value shown to rebuild for raw PHI at the trace sink
      // (§7/N2 / N2-observability).
      const segments = prepared.tracedSegments;
      const traced: { path: string; text: TokenizedText }[] = [];
      for (let i = 0; i < (segments as { length: number }).length; i += 1) {
        const segment = segments[i]!;
        traced[traced.length] = { path: segment.path, text: segment.text };
      }
      await this.#deps.safeTrace.request(traced);
    } catch (error) {
      await this.#finalizeQuietly(
        prepared,
        "failed_closed",
        errorCodeString(error),
      );
      throw new PhiEngineError(
        toFailureCode(error, "PROVIDER_SAFETY_GATE_FAILED"),
        prepared.context.operationId,
        {},
      );
    }
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
    decision: Readonly<{
      isProductionSafe: boolean;
      baaSatisfied: boolean;
      providerId: string;
    }>,
    context: MatterAiContext,
  ): void {
    // L11: the gate is conjunctive over the ORIGINAL-content decision. A successful
    // substitution ("it's tokenized now") never makes an unsafe provider safe.
    if (!decision.isProductionSafe || !decision.baaSatisfied) {
      throw new PhiEngineError(
        "PROVIDER_SAFETY_GATE_FAILED",
        context.operationId,
        {
          providerId: decision.providerId,
        },
      );
    }
  }

  async #requireContext(): Promise<MatterAiContext> {
    let raw: MatterAiContext;
    try {
      raw = await this.#deps.context.require();
    } catch {
      throw new PhiEngineError("MISSING_TRUSTED_CONTEXT");
    }
    // §7/N2: the injected context port's result is UNTRUSTED. Read every scalar EXACTLY ONCE into an
    // inert snapshot AND validate it is a genuine string — downstream code reads these fields many
    // times (prepared records, fixed-code error ids, finalize), so a throwing/mutating getter, OR a
    // non-string carrier (e.g. `operationId:{toString(){throw PHI}}` that later gets coerced onto an
    // error), would otherwise leak raw PHI at any of those LATER reads, several of which sit outside a
    // guard. A throw or a non-string field fails closed here with MISSING_TRUSTED_CONTEXT.
    const tenantId = safeString(raw, "tenantId");
    const matterId = safeString(raw, "matterId");
    const actorId = safeString(raw, "actorId");
    const operationId = safeString(raw, "operationId");
    const attemptId = safeString(raw, "attemptId");
    if (
      tenantId === undefined ||
      matterId === undefined ||
      actorId === undefined ||
      operationId === undefined ||
      attemptId === undefined
    ) {
      throw new PhiEngineError("MISSING_TRUSTED_CONTEXT");
    }
    return {
      tenantId: tenantId as MatterAiContext["tenantId"],
      matterId: matterId as MatterAiContext["matterId"],
      actorId: actorId as MatterAiContext["actorId"],
      operationId: operationId as MatterAiContext["operationId"],
      attemptId: attemptId as MatterAiContext["attemptId"],
    };
  }

  async #prepareAudit(
    context: MatterAiContext,
    _policy: TrustedMatterAiPolicy,
    substitution: SubstitutionResult,
    purpose: AiOperation,
  ): Promise<AuditPreparationReceipt> {
    return this.#deps.audit.prepare(
      this.#preparedRecord(context, substitution, purpose),
    );
  }

  /**
   * §7/N2: the injected engine's `SubstitutionResult` is UNTRUSTED. Read its METADATA fields EXACTLY
   * ONCE into inert values here, so the (repeated) prepared-record construction — on the durable
   * PREPARE and on EVERY finalize path, several outside a guard — never re-reads a getter that is
   * valid for PREPARED and throws PHI after provider invocation. `segments` and `reversalHandle` flow
   * on to their own hardened consumers (segment snapshot / guarded reversal).
   */
  #snapshotSubstitution(s: SubstitutionResult): SubstitutionResult {
    const detector = safeRead(s, "detector") as SubstitutionResult["detector"];
    const detectorSnapshot =
      detector == null
        ? null
        : {
            name: safeString(detector, "name") ?? "",
            version: safeString(detector, "version") ?? "",
          };
    const latency = safeRead(s, "latencyMs");
    const ambiguityCount = safeRead(s, "ambiguityCount");
    // §7/N2: the injected engine's `segments` are UNTRUSTED. Deep-copy by own index and require each
    // path/kind/text to be a genuine STRING — a non-string `text` carrier (e.g. { toJSON: () => PHI })
    // would otherwise reach safeTrace.request (via rebuild) and the caller. Fail closed on any
    // non-string, non-array carrier, or throwing own-index getter.
    const rawSegments = intrinsicCopy<TokenizedTextSegment>(
      safeRead(s, "segments"),
    );
    if (rawSegments === null) {
      throw new PhiEngineError("PROVIDER_SAFETY_GATE_FAILED");
    }
    const segments: TokenizedTextSegment[] = [];
    for (let i = 0; i < rawSegments.length; i += 1) {
      const seg = rawSegments[i];
      const path = safeString(seg, "path");
      const kind = safeString(seg, "kind");
      const textValue = safeString(seg, "text");
      if (path === undefined || kind === undefined || textValue === undefined) {
        throw new PhiEngineError("PROVIDER_SAFETY_GATE_FAILED");
      }
      segments[segments.length] = {
        path,
        kind: kind as TokenizedTextSegment["kind"],
        text: textValue as unknown as TokenizedText,
      };
    }
    return {
      segments,
      dictionaryVersion: safeRead(
        s,
        "dictionaryVersion",
      ) as SubstitutionResult["dictionaryVersion"],
      engineVersion: safeRead(
        s,
        "engineVersion",
      ) as SubstitutionResult["engineVersion"],
      counts: safeRead(s, "counts") as SubstitutionResult["counts"],
      ambiguityCount: typeof ambiguityCount === "number" ? ambiguityCount : 0,
      detector: detectorSnapshot,
      latencyMs: {
        dictionary: Number(safeRead(latency, "dictionary")) || 0,
        detector: Number(safeRead(latency, "detector")) || 0,
        total: Number(safeRead(latency, "total")) || 0,
      },
      reversalHandle: safeRead(
        s,
        "reversalHandle",
      ) as SubstitutionResult["reversalHandle"],
    };
  }

  /**
   * §7/N2: the injected clock is UNTRUSTED — a throwing clock must never propagate a raw (PHI) throw
   * out of a record/event build (which runs OUTSIDE the fail-closed try/catch of the recording paths).
   * Delegates to the shared getter-throw-safe clock accessor (single chokepoint with the audit layer).
   */
  #safeNow(): string {
    return safeClockNow(this.#clock);
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
      preparedAt: this.#safeNow(),
    };
  }

  /** A metadata-only PREPARED record for a fail-closed terminal recorded before substitution. */
  #minimalPreparedRecord(
    context: MatterAiContext,
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
      dictionaryVersion: null,
      engineVersion: this.#deps.engineVersion,
      counts: toTotalIdentifierCounts({}),
      ambiguityCount: 0,
      detectorName: null,
      detectorVersion: null,
      latencyMs: { dictionary: 0, detector: 0, total: 0 },
      preparedAt: this.#safeNow(),
    };
  }

  /**
   * Finalizes exactly one terminal for a pre-egress failure. An idempotency signal
   * (the attempt already has its single terminal) records nothing further.
   */
  async #recordPreEgressFailure(
    context: MatterAiContext,
    purpose: AiOperation,
    error: unknown,
  ): Promise<void> {
    // ANY audit-layer error means the durable record path itself is what failed (already finalized,
    // durability unavailable, or the PREPARE rejected). Preparing a FRESH terminal here would
    // DOUBLE-PREPARE (or just hit the same failure), so fail closed with no second prepare — nothing
    // egressed, and N4 permits no terminal when durability is unavailable. A NON-audit pre-egress
    // failure (policy/routing/substitution) still records exactly one fail-closed terminal.
    if (isAuditError(error)) {
      return;
    }
    await this.#recordFailedClosedTerminal(
      context,
      purpose,
      errorCodeString(error),
      // GLY-373 §3.2.5: a reversal-key canonical conflict fails during `substitute()`, i.e. on this
      // PRE-EGRESS path, so this is where the triage discriminator has to be threaded for it to
      // reach the durable record at all. `null` on every other failure.
      errorFailureDetail(error),
    );
  }

  /** Prepares + finalizes a single failed-closed terminal; never egresses (N3/N4). */
  async #recordFailedClosedTerminal(
    context: MatterAiContext,
    purpose: AiOperation,
    failureCode: string,
    failureDetail: string | null = null,
  ): Promise<void> {
    const record = this.#minimalPreparedRecord(context, purpose);
    try {
      const receipt = await this.#deps.audit.prepare(record);
      await this.#finalizeAt(
        receipt,
        record,
        "failed_closed",
        failureCode,
        failureDetail,
      );
    } catch {
      // Durability unavailable (or terminal already exists): the fail-closed outcome is
      // still surfaced via the thrown original error, and nothing egressed.
    }
  }

  async #reverseAndFinalize(
    rawOutput: TokenizedText,
    prepared: PreparedEgress<GenerateOptions, EmbeddingKind>,
  ): Promise<DisplayText> {
    let display: DisplayText;
    try {
      // §4.1 step 11 / N5: reverse tokens to CURRENT canonical values before display.
      display = await this.#deps.engine.reverse(
        rawOutput,
        prepared.substitutionHandle,
      );
    } catch (error) {
      await this.#finalizeQuietly(
        prepared,
        "reversal_failed",
        "REVERSAL_FAILED",
      );
      throw new PhiEngineError(
        toFailureCode(error, "REVERSAL_FAILED"),
        prepared.context.operationId,
        {},
      );
    }
    // §7/N2: the injected engine's reverse() result is UNTRUSTED — a NON-STRING carrier (e.g. an object
    // whose toString/toJSON yields PHI) must NOT be returned to the caller. Require a genuine string.
    if (typeof (display as unknown) !== "string") {
      await this.#finalizeQuietly(
        prepared,
        "reversal_failed",
        "REVERSAL_FAILED",
      );
      throw new PhiEngineError(
        "REVERSAL_FAILED",
        prepared.context.operationId,
        {},
      );
    }
    await this.#finalizeStrict(prepared, "completed", null);
    return display;
  }

  async #finalize(
    prepared: PreparedEgress<GenerateOptions, EmbeddingKind>,
    outcome: PhiAuditOutcome,
    failureCode: PhiEngineFailureCode | string | null,
  ): Promise<void> {
    await this.#finalizeAt(
      prepared.receipt,
      this.#preparedRecord(
        prepared.context,
        prepared.substitution,
        prepared.purpose,
      ),
      outcome,
      failureCode,
    );
  }

  async #finalizeAt(
    receipt: AuditPreparationReceipt,
    record: PhiAuditPreparedRecord,
    outcome: PhiAuditOutcome,
    failureCode: string | null,
    /** GLY-373 §3.2.5 triage discriminator; `null` on every path that does not carry one. */
    failureDetail: string | null = null,
  ): Promise<void> {
    const event: PhiAuditEvent = preparedToTerminalEvent(
      record,
      outcome,
      failureCode,
      this.#safeNow(),
      failureDetail,
    );
    await this.#deps.audit.finalize(receipt, event);
  }

  /**
   * Best-effort terminal on a FAILURE path (§7/N2). A rejecting finalizer must NEVER override the
   * fixed, sanitized error being surfaced to the caller — its raw message/code could carry PHI. A
   * lost terminal under total durability failure is acceptable (N4 fail-closed); the caller still
   * receives the sanitized fixed-code error.
   */
  async #finalizeQuietly(
    prepared: PreparedEgress<GenerateOptions, EmbeddingKind>,
    outcome: PhiAuditOutcome,
    failureCode: PhiEngineFailureCode | string | null,
  ): Promise<void> {
    try {
      await this.#finalize(prepared, outcome, failureCode);
    } catch {
      /* durability failure on a failure path; the sanitized error is still thrown by the caller. */
    }
  }

  async #finalizeAtQuietly(
    receipt: AuditPreparationReceipt,
    record: PhiAuditPreparedRecord,
    outcome: PhiAuditOutcome,
    failureCode: string | null,
  ): Promise<void> {
    try {
      await this.#finalizeAt(receipt, record, outcome, failureCode);
    } catch {
      /* durability failure on a failure path; the sanitized error is still thrown by the caller. */
    }
  }

  /**
   * Finalize the SUCCESS ("completed") terminal, failing closed with a fixed, PHI-free code if the
   * terminal write rejects. A rejecting finalizer must NEVER surface a raw message/code to the
   * caller (§7/N2) — its rejection could carry PHI — and a completed egress whose durable terminal
   * could not be written fails closed (N3/N4) rather than returning an unaudited result.
   */
  async #finalizeStrict(
    prepared: PreparedEgress<GenerateOptions, EmbeddingKind>,
    outcome: PhiAuditOutcome,
    failureCode: PhiEngineFailureCode | string | null,
  ): Promise<void> {
    try {
      await this.#finalize(prepared, outcome, failureCode);
    } catch {
      // §7/N2: the rejected error's message/code is NEVER surfaced — even a `PhiEngineError.code`
      // is untrusted here (it could be a raw value cast to a code by an injected finalizer). Fail
      // closed with a FIXED code.
      throw new PhiEngineError(
        "AUDIT_DURABILITY_UNAVAILABLE",
        prepared.context.operationId,
        {},
      );
    }
  }

  /** As {@link #finalizeStrict}, for the receipt-scoped success terminal (embedding). */
  async #finalizeAtStrict(
    receipt: AuditPreparationReceipt,
    record: PhiAuditPreparedRecord,
    outcome: PhiAuditOutcome,
    failureCode: string | null,
    operationId: OperationId,
  ): Promise<void> {
    try {
      await this.#finalizeAt(receipt, record, outcome, failureCode);
    } catch {
      // §7/N2: never surface the rejected error's message/code (a fixed code only, see above).
      throw new PhiEngineError("AUDIT_DURABILITY_UNAVAILABLE", operationId, {});
    }
  }
}

interface PreparedEgress<GenerateOptions, EmbeddingKind> {
  readonly context: MatterAiContext;
  readonly purpose: AiOperation;
  readonly substitution: SubstitutionResult;
  readonly substitutionHandle: ReversalHandle;
  readonly tokenizedOptions: GenerateOptions;
  readonly receipt: AuditPreparationReceipt;
  readonly provider: AnyRawProvider<GenerateOptions, EmbeddingKind>;
  readonly providerId: string;
  /** §7/N2: an INERT read-once snapshot of the substitution segments (path/text read exactly once
   *  from the injected engine's result), used by BOTH rebuild and the trace so a mutating getter
   *  cannot show a tokenized value to rebuild and raw PHI to the trace. */
  readonly tracedSegments: readonly {
    readonly path: string;
    readonly text: TokenizedText;
  }[];
}

/**
 * Read-once, index-iterated snapshot of the injected engine's substitution segments (§7/N2). `path`
 * and `text` are each read a SINGLE time (a mutating getter cannot differ between rebuild and trace),
 * via own-index access (a poisoned own `Symbol.iterator` cannot yield different values than the
 * indexed segments). A throwing getter propagates to the pre-egress handler, which fails closed.
 */
function snapshotSegments(
  segments: readonly TokenizedTextSegment[],
): { path: string; kind: TokenizedTextSegment["kind"]; text: TokenizedText }[] {
  const out: {
    path: string;
    kind: TokenizedTextSegment["kind"];
    text: TokenizedText;
  }[] = [];
  const len = (segments as { length: number }).length;
  for (let i = 0; i < len; i += 1) {
    const seg = segments[i] as TokenizedTextSegment;
    out[out.length] = { path: seg.path, kind: seg.kind, text: seg.text };
  }
  return out;
}
