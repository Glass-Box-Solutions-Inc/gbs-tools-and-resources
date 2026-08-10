import type { AuditDurabilityLocation, PhiAuditEmitter, PhiAuditOutcome, PhiAuditPreparedRecord } from "./ports";
import { isAuditError } from "./errors";
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
      throw error;
    }

    if (!plan.precondition.ok) {
      const event = preparedToTerminalEvent(plan.prepared, "failed_closed", plan.precondition.failureCode, this.#clock());
      await this.#emitter.finalize(receipt, event);
      return {
        outcome: "failed_closed",
        errorCode: plan.precondition.failureCode,
        providerInvoked: false,
        durability: receipt.location,
      };
    }

    await plan.invokeProvider();
    const event = preparedToTerminalEvent(plan.prepared, "completed", null, this.#clock());
    await this.#emitter.finalize(receipt, event);
    return { outcome: "completed", errorCode: null, providerInvoked: true, durability: receipt.location };
  }
}
