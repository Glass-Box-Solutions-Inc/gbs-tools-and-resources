/**
 * Evidence-gated claims registry (invariant N6).
 *
 * Claims are limited to PASSING evidence. The registry holds a fixed allow-list
 * of copy; it emits only the subset whose evidence is satisfied and NEVER echoes
 * a caller-supplied string. The one eligible phase-1 text claim is exactly the
 * §2 sentence, and it asserts nothing about images — image egress is a
 * documented carve-out that lives OUTSIDE the claim. A phase-2 free-text claim
 * is eligible only when every detector class clears its own per-class gate (L7);
 * a single ineligible class blocks it.
 */
import { gateClasses, type ClassRecallEvidence } from "./eligibility";

/** The exact §2 phase-1 customer copy. The ONLY eligible phase-1 text claim. */
export const PHASE1_TEXT_CLAIM =
  "Client identifiers on file are replaced before AI processing.";

/**
 * The phase-2 free-text claim. Eligible ONLY when every detector class clears
 * its per-class recall gate. It is never emitted in phase 1.
 */
export const PHASE2_FREETEXT_CLAIM =
  "Free-text personal identifiers are detected and replaced before AI processing.";

export interface ClaimEvidence {
  /** 1 = trusted schema-tagged policy only; 2 = detector belt evidence present. */
  readonly phase: number;
  /** Per-class detector recall lower bounds backing a phase-2 free-text claim. */
  readonly detectorClasses: readonly ClassRecallEvidence[];
}

export interface ClaimDecision {
  /** The eligible copy, in registry order. Only registered, evidenced strings. */
  readonly outputs: readonly string[];
  /**
   * Whether any emitted claim asserts image-substitution coverage. Always false:
   * the phase-1 copy is text-only and images are an explicit carve-out (N6).
   */
  readonly imageCoverageClaimed: boolean;
  readonly diagnostics: readonly string[];
}

/**
 * Resolve the eligible copy for the given evidence. Nothing outside the registry
 * is ever emitted, regardless of what a caller requests.
 */
export function eligibleClaims(evidence: ClaimEvidence): ClaimDecision {
  const outputs: string[] = [];
  const diagnostics: string[] = [];

  // Phase-1 claim: eligible whenever the trusted schema-tagged policy is active.
  // It asserts substitution of on-file identifiers only — no free-text-detection
  // claim and no image claim.
  if (evidence.phase >= 1) {
    outputs.push(PHASE1_TEXT_CLAIM);
  }

  // Phase-2 free-text claim: gated on per-class detector eligibility (L7).
  if (evidence.phase >= 2 && evidence.detectorClasses.length > 0) {
    const gate = gateClasses(evidence.detectorClasses);
    if (gate.eligible) {
      outputs.push(PHASE2_FREETEXT_CLAIM);
    } else {
      // N6: a failed/ineligible class blocks the free-text claim entirely.
      diagnostics.push("CLAIM_BLOCKED:PHASE2_FREETEXT");
      for (const detail of gate.diagnostics) diagnostics.push(detail);
    }
  }

  // N6 image boundary: no eligible phase-1 claim implies image coverage.
  const imageCoverageClaimed = false;

  return { outputs, imageCoverageClaimed, diagnostics };
}

/**
 * Validate a caller-requested copy against the registry. The requested string is
 * used only to decide acceptance/rejection — it is NEVER added to the outputs.
 * An unproved request is rejected; the registry still returns the copy it can
 * actually stand behind.
 */
export function resolveRequestedClaim(
  requested: string | null,
  evidence: ClaimEvidence,
): ClaimDecision {
  const decision = eligibleClaims(evidence);
  if (requested === null || decision.outputs.includes(requested)) {
    return decision;
  }
  // N6: requested copy has no passing evidence in the registry — reject it and
  // emit only the eligible copy.
  return {
    outputs: decision.outputs,
    imageCoverageClaimed: decision.imageCoverageClaimed,
    diagnostics: [...decision.diagnostics, "CLAIM_REJECTED:UNPROVED_COPY"],
  };
}
