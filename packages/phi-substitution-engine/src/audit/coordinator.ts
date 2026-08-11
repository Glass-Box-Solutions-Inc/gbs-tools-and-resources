import type {
  AuditDurabilityLocation,
  AuditPreparationReceipt,
  PhiAuditEmitter,
  PhiAuditEvent,
  PhiAuditOutcome,
  PhiAuditPreparedRecord,
} from "./ports";
import { isAuditError } from "./errors";
import { isPhiEngineFailureCode } from "../core/errors";
import { preparedToTerminalEvent } from "./event-factory";

/** Performs the single provider egress for an attempt. Called at most once, only after durability. */
export type ProviderInvoker = () => Promise<void>;

export type AttemptPrecondition =
  | { readonly ok: true }
  | { readonly ok: false; readonly failureCode: string };

export interface AttemptPlan {
  readonly prepared: PhiAuditPreparedRecord;
  readonly precondition: AttemptPrecondition;
  readonly invokeProvider: ProviderInvoker;
}

export interface AttemptResult {
  readonly outcome: PhiAuditOutcome;
  readonly errorCode: string | null;
  readonly providerInvoked: boolean;
  readonly durability: AuditDurabilityLocation | null;
}

/**
 * Wraps a single attempted AI call in the audit lifecycle (CONTRACT §4.1 / §5 N3-N4):
 *
 *  1. Durably PREPARE one metadata-only record before any provider egress.
 *  2. If durability is unavailable everywhere, fail closed and invoke the provider zero times.
 *  3. If a precondition failed, audit exactly one `failed_closed` terminal event, no egress.
 *  4. Otherwise invoke the provider exactly once and finalize exactly one terminal event.
 *
 * Exactly one terminal audit event is produced per attempt, and the provider is never reached
 * before a durable PREPARED record exists.
 */
export class PhiAuditedAttemptCoordinator {
  readonly #emitter: PhiAuditEmitter;
  readonly #clock: () => string;

  public constructor(emitter: PhiAuditEmitter, clock: () => string = (): string => new Date().toISOString()) {
    this.#emitter = emitter;
    this.#clock = clock;
  }

  public async run(plan: AttemptPlan): Promise<AttemptResult> {
    let receipt;
    try {
      receipt = await this.#emitter.prepare(plan.prepared);
    } catch (error) {
      if (isAuditError(error, "AUDIT_DURABILITY_UNAVAILABLE")) {
        return {
          outcome: "failed_closed",
          errorCode: "AUDIT_DURABILITY_UNAVAILABLE",
          providerInvoked: false,
          durability: null,
        };
      }
      // §7/N2: an unexpected prepare failure must NEVER surface a raw upstream message/code.
      // The provider was never invoked; fail closed with a FIXED code.
      return {
        outcome: "failed_closed",
        errorCode: "AUDIT_PREPARE_FAILED",
        providerInvoked: false,
        durability: null,
      };
    }

    if (!plan.precondition.ok) {
      // §7/N2: only a RECOGNIZED fixed failure code may be recorded; a caller-supplied precondition
      // code that is not a known PhiEngineFailureCode (and could carry PHI) is replaced.
      const safeCode = isPhiEngineFailureCode(plan.precondition.failureCode)
        ? plan.precondition.failureCode
        : "PRECONDITION_FAILED";
      const event = preparedToTerminalEvent(plan.prepared, "failed_closed", safeCode, this.#clock());
      await this.#finalizeQuietly(receipt, event);
      return {
        outcome: "failed_closed",
        errorCode: safeCode,
        providerInvoked: false,
        durability: receipt.location,
      };
    }

    try {
      await plan.invokeProvider();
    } catch (error) {
      // N3: a provider rejection after send still finalizes exactly one terminal
      // (never a stuck PREPARED record). §7/N2: only a RECOGNIZED fixed failure code may be
      // recorded — an arbitrary upstream `.code` (which can carry PHI) is never copied.
      const failureCode =
        error !== null &&
        typeof error === "object" &&
        "code" in error &&
        typeof (error as { code?: unknown }).code === "string" &&
        isPhiEngineFailureCode((error as { code: string }).code)
          ? (error as { code: string }).code
          : "PROVIDER_INVOCATION_FAILED";
      const failedEvent = preparedToTerminalEvent(plan.prepared, "unknown_after_send", failureCode, this.#clock());
      await this.#finalizeQuietly(receipt, failedEvent);
      return {
        outcome: "unknown_after_send",
        errorCode: failureCode,
        providerInvoked: true,
        durability: receipt.location,
      };
    }
    const event = preparedToTerminalEvent(plan.prepared, "completed", null, this.#clock());
    await this.#finalizeQuietly(receipt, event);
    return { outcome: "completed", errorCode: null, providerInvoked: true, durability: receipt.location };
  }

  /**
   * §7/N2: a rejecting emitter `finalize` must NEVER surface a raw upstream message/code to the
   * caller — a rejecting finalizer could carry PHI. A lost terminal under total durability failure
   * is N4-acceptable (a later drain/reconcile can still deliver it); the fixed-code `AttemptResult`
   * is still returned, and nothing raw escapes.
   */
  async #finalizeQuietly(receipt: AuditPreparationReceipt, event: PhiAuditEvent): Promise<void> {
    try {
      await this.#emitter.finalize(receipt, event);
    } catch {
      /* durability failure on the terminal write; the fixed-code result is still returned. */
    }
  }
}
