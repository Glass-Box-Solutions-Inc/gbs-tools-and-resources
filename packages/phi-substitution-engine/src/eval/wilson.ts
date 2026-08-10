/**
 * Wilson score interval lower bound for a binomial proportion.
 *
 * A per-class detector gate (invariant L7) must not pass on a lucky point
 * estimate drawn from a small corpus. The Wilson lower bound pulls the accepted
 * recall down toward 0 as the sample shrinks, so a class only clears the gate
 * when the evidence is both high AND sufficiently sampled. The evaluation
 * harness computes this once per class and stores it as
 * `PerClassEvaluation.recallWilsonLower95`; the claims layer gates on that value.
 */

/** Standard-normal quantile for a two-sided 95% interval (z_{0.975}). */
export const Z_95 = 1.959963984540054;

/**
 * Lower bound of the Wilson score interval at confidence implied by `z`.
 *
 * Degenerate inputs (non-finite, zero/negative trials) return 0 — an unmeasured
 * class can never clear a positive gate. `successes` is clamped into `[0, trials]`.
 */
export function wilsonLowerBound(
  successes: number,
  trials: number,
  z: number = Z_95,
): number {
  if (!Number.isFinite(successes) || !Number.isFinite(trials) || trials <= 0) {
    return 0;
  }
  const boundedSuccesses = Math.max(0, Math.min(successes, trials));
  const pHat = boundedSuccesses / trials;
  const z2 = z * z;
  const denominator = 1 + z2 / trials;
  const centre = pHat + z2 / (2 * trials);
  const margin = z * Math.sqrt((pHat * (1 - pHat) + z2 / (4 * trials)) / trials);
  const lower = (centre - margin) / denominator;
  if (lower < 0) return 0;
  if (lower > 1) return 1;
  return lower;
}
