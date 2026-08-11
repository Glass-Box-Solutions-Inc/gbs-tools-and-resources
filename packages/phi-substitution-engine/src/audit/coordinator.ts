import type {
  AuditDurabilityLocation,
  AuditPreparationReceipt,
  PhiAuditEmitter,
  PhiAuditEvent,
  PhiAuditOutcome,
  PhiAuditPreparedRecord,
} from "./ports";
import { isAuditError } from "./errors";
import { isPhiEngineFailureCode, safeCodeString } from "../core/errors";
import { preparedToTerminalEvent, safeClockNow } from "./event-factory";

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

/** Reads an injected-emitter receipt's `location` ONCE, getter-throw-safe and allow-listed (§7/N2):
 *  a hostile `.location` getter can neither throw a raw PHI error nor smuggle an arbitrary string. */
function safeDurability(receipt: AuditPreparationReceipt): AuditDurabilityLocation | null {
  try {
    const loc = (receipt as { location?: unknown }).location;
    return loc === "PRIMARY_STORE" || loc === "ENCRYPTED_LOCAL_SPOOL" ? loc : null;
  } catch {
    return null;
  }
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
    // §7/N2: `plan.prepared` is an injected-plan getter — read it EXACTLY ONCE into a local. A getter
    // that returns a valid record for `prepare()` and then THROWS (or mutates) on the terminal-event
    // reads below would otherwise leak raw PHI out of `run()`. A throw on this single read fails
    // closed with a fixed code; nothing was prepared or egressed.
    let prepared: AttemptPlan["prepared"];
    try {
      prepared = plan.prepared;
    } catch {
      return {
        outcome: "failed_closed",
        errorCode: "AUDIT_PREPARE_FAILED",
        providerInvoked: false,
        durability: null,
      };
    }
    let receipt;
    try {
      receipt = await this.#emitter.prepare(prepared);
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
    // §7/N2: `receipt.location` is an injected-emitter result — read it ONCE, getter-throw-safe and
    // allow-listed, so a hostile `.location` getter can't throw a raw PHI error out of the (otherwise
    // fixed-code) AttemptResult, nor smuggle an arbitrary string into `durability`.
    const durability = safeDurability(receipt);

    // §7/N2: the precondition is UNTRUSTED input. BOTH `ok` and `failureCode` are read EXACTLY ONCE
    // behind a getter-throw guard — a hostile Proxy/getter on `.ok` (not just `.failureCode`) must
    // not throw a PHI canary out of `run()` uncaught. Any read failure, and any non-`true` `ok`, is
    // treated as a precondition failure and fails closed with a fixed code (stricter than `!ok`,
    // which a non-boolean truthy value would slip past into egress).
    let preconditionOk: boolean;
    let rawPreconditionCode: unknown;
    try {
      preconditionOk = plan.precondition.ok === true;
      rawPreconditionCode = preconditionOk
        ? undefined
        : (plan.precondition as { readonly failureCode?: unknown }).failureCode;
    } catch {
      preconditionOk = false;
      rawPreconditionCode = undefined;
    }
    if (!preconditionOk) {
      // Only a RECOGNIZED fixed failure code may be recorded; a caller-supplied code that is not a
      // known PhiEngineFailureCode (and could carry PHI) is replaced with the fixed fallback.
      const safeCode = isPhiEngineFailureCode(rawPreconditionCode) ? rawPreconditionCode : "PRECONDITION_FAILED";
      const event = preparedToTerminalEvent(prepared, "failed_closed", safeCode, safeClockNow(this.#clock));
      await this.#finalizeQuietly(receipt, event);
      return {
        outcome: "failed_closed",
        errorCode: safeCode,
        providerInvoked: false,
        durability,
      };
    }

    try {
      await plan.invokeProvider();
    } catch (error) {
      // N3: a provider rejection after send still finalizes exactly one terminal
      // (never a stuck PREPARED record). §7/N2: only a RECOGNIZED fixed failure code may be
      // recorded — an arbitrary upstream `.code` (which can carry PHI) is never copied. `.code` is
      // read EXACTLY ONCE behind a getter-throw guard, so a getter that validates on one read and
      // yields PHI on another, or throws PHI, cannot leak.
      const rawCode = safeCodeString(error);
      const failureCode =
        rawCode !== undefined && isPhiEngineFailureCode(rawCode) ? rawCode : "PROVIDER_INVOCATION_FAILED";
      const failedEvent = preparedToTerminalEvent(prepared, "unknown_after_send", failureCode, safeClockNow(this.#clock));
      await this.#finalizeQuietly(receipt, failedEvent);
      return {
        outcome: "unknown_after_send",
        errorCode: failureCode,
        providerInvoked: true,
        durability,
      };
    }
    const event = preparedToTerminalEvent(prepared, "completed", null, safeClockNow(this.#clock));
    await this.#finalizeQuietly(receipt, event);
    return { outcome: "completed", errorCode: null, providerInvoked: true, durability };
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
