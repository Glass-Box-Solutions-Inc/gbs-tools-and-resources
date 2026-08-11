import type { IdentifierClass, IdentifierCounts } from "../core/contracts";
import { safeRead } from "../core/boundary-snapshot";

/**
 * The canonical, ordered list of every identifier class. An audit `counts` record is a
 * TOTAL count record: every class is always present, including explicit zeroes, so the
 * absence of a class can never be confused with a class that was simply not observed
 * (CONTRACT §5 N3 / SEC-N3-07).
 */
export const IDENTIFIER_CLASSES: readonly IdentifierClass[] = [
  "PERSON_NAME",
  "DOB",
  "SSN",
  "MRN",
  "DEA",
  "EMAIL",
  "PHONE",
  "ADDRESS",
  "CLAIM_NUMBER",
  "POLICY_NUMBER",
  "ACCOUNT_NUMBER",
  "OTHER_TAGGED",
];

/**
 * Projects a partial per-class tally into a total count record. Every identifier class is
 * emitted with an explicit integer, defaulting unobserved classes to zero. Negative or
 * non-integer inputs are clamped to a safe non-negative integer so a corrupt tally can never
 * smuggle a fractional or negative signal into the audit event.
 */
export function toTotalIdentifierCounts(
  partial: Readonly<Partial<Record<IdentifierClass, number>>>,
): IdentifierCounts {
  const result: Record<IdentifierClass, number> = {
    PERSON_NAME: 0,
    DOB: 0,
    SSN: 0,
    MRN: 0,
    DEA: 0,
    EMAIL: 0,
    PHONE: 0,
    ADDRESS: 0,
    CLAIM_NUMBER: 0,
    POLICY_NUMBER: 0,
    ACCOUNT_NUMBER: 0,
    OTHER_TAGGED: 0,
  };
  // §7/N2: `partial` is boundary data — read each FIXED, known class key getter-throw-safe (a hostile
  // `get SSN(){ throw PHI }` must not propagate raw out of this exported projector). Only the fixed
  // IDENTIFIER_CLASSES keys are ever read, so no attacker-chosen property name is touched or echoed.
  for (const identifierClass of IDENTIFIER_CLASSES) {
    const raw = safeRead(partial, identifierClass);
    if (typeof raw === "number" && Number.isFinite(raw)) {
      result[identifierClass] = Math.max(0, Math.trunc(raw));
    }
  }
  return result;
}
