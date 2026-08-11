/**
 * Per-class detector eligibility (invariant L7).
 *
 * Detector eligibility is decided PER CLASS against a pinned recall floor. A
 * macro-average across classes is never consulted for the pass/fail decision:
 * a single failing class blocks the aggregate, even when the average is high.
 * Each failing class emits a `CLASS_GATE_FAILED:<CLASS>` diagnostic so the
 * blocked class is named in the release evidence, not silently averaged away.
 */

/**
 * Minimum acceptable per-class recall Wilson lower bound (95%).
 *
 * A class is eligible only when its Wilson lower bound is at or above this
 * floor; the point estimate is never used for the decision.
 */
export const MINIMUM_CLASS_RECALL_LOWER = 0.99;

export interface ClassRecallEvidence {
  /** Identifier class label, e.g. "SSN", "DEA", "PERSON_NAME". */
  readonly identifierClass: string;
  /** Pre-computed Wilson 95% lower bound of recall for this class. */
  readonly recallWilsonLower95: number;
}

export interface ClassGateResult {
  readonly identifierClass: string;
  readonly recallLower: number;
  readonly eligible: boolean;
}

export interface AggregateEligibility {
  /** True only when EVERY class clears its own gate. Never an average. */
  readonly eligible: boolean;
  readonly perClass: readonly ClassGateResult[];
  readonly failedClasses: readonly string[];
  /** `CLASS_GATE_FAILED:<CLASS>` for each class below the floor. */
  readonly diagnostics: readonly string[];
  /** Informational only. Deliberately NOT used to decide `eligible`. */
  readonly macroRecallLower: number;
}

function isClearing(lower: number, threshold: number): boolean {
  return Number.isFinite(lower) && lower >= threshold;
}

/**
 * Gate a set of per-class recall lower bounds. Eligibility is conjunctive over
 * classes — the macro-average is computed and reported but never decides.
 */
export function gateClasses(
  classes: readonly ClassRecallEvidence[],
  threshold: number = MINIMUM_CLASS_RECALL_LOWER,
): AggregateEligibility {
  const perClass: ClassGateResult[] = [];
  const failedClasses: string[] = [];
  const diagnostics: string[] = [];
  let lowerSum = 0;

  // §7/N2: `classes` is boundary evidence — index-iterate (a poisoned own `Symbol.iterator` can't
  // hide a class) and read each `identifierClass`/`recallWilsonLower95` EXACTLY ONCE, so a mutating
  // getter can't put a benign label in `perClass` and PHI in `failedClasses`/diagnostics.
  const classList = Array.isArray(classes) ? classes : [];
  for (let ci = 0; ci < (classList as { length: number }).length; ci += 1) {
    const evidence = classList[ci]!;
    const identifierClass = evidence.identifierClass;
    const recallLower = evidence.recallWilsonLower95;
    const eligible = isClearing(recallLower, threshold);
    perClass.push({ identifierClass, recallLower, eligible });
    lowerSum += Number.isFinite(recallLower) ? recallLower : 0;
    if (!eligible) {
      failedClasses.push(identifierClass);
      diagnostics.push(`CLASS_GATE_FAILED:${identifierClass}`);
    }
  }

  // L7 decision line: conjunctive over classes. A macro-average CANNOT hide a
  // weak class — one failing class forces the aggregate to false.
  const eligible = classes.length > 0 && failedClasses.length === 0;
  const macroRecallLower = classes.length > 0 ? lowerSum / classes.length : 0;

  return { eligible, perClass, failedClasses, diagnostics, macroRecallLower };
}
