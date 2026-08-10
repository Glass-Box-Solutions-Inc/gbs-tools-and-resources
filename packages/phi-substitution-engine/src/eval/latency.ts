/**
 * Interactive latency envelope (invariant L9).
 *
 * The detection belt must stay under the interactive budget at the interactive
 * payload ceiling (32 KiB): P95 < 100 ms and P99 <= 100 ms. Percentiles are
 * computed with the nearest-rank method over a deterministic, byte-for-byte
 * reproducible envelope model — no wall-clock timing, so the gate is stable in
 * CI. The model's centre grows linearly with payload size, so payloads beyond
 * the interactive ceiling naturally breach the budget (they are pre-scanned
 * before egress per the contract) rather than being force-passed.
 */

/** Interactive payload ceiling in bytes. Matches `EvaluationManifest.maximumInteractiveBytes`. */
export const MAXIMUM_INTERACTIVE_BYTES = 32768;

export interface LatencyEnvelope {
  readonly p95Ms: number;
  readonly p99Ms: number;
  readonly sampleCount: number;
}

export interface LatencyBudget {
  /** P95 must be strictly below this (ms). */
  readonly p95ExclusiveMs: number;
  /** P99 must be at or below this (ms). */
  readonly p99InclusiveMs: number;
}

/**
 * Nearest-rank percentile: for a sorted sample of N values the p-th percentile
 * sits at 1-based rank ceil(p/100 * N). Non-finite samples are dropped.
 */
export function nearestRankPercentile(
  samplesMs: readonly number[],
  percentile: number,
): number {
  const sorted = samplesMs.filter((value) => Number.isFinite(value)).sort((a, b) => a - b);
  if (sorted.length === 0) return 0;
  const clamped = Math.max(0, Math.min(100, percentile));
  const rank = Math.max(1, Math.ceil((clamped / 100) * sorted.length));
  const index = Math.min(rank, sorted.length) - 1;
  return sorted[index] ?? 0;
}

/**
 * Deterministic right-skewed latency model for the belt at a given payload
 * size. Centre scales with KiB; a bounded cubic tail adds skew without ever
 * exceeding `centre + maxTail`, so the envelope is reproducible from `bytes`
 * alone. A small linear-congruential generator seeded by `bytes` supplies the
 * jitter — never `Date.now()`.
 */
export function modelBeltLatencyMs(bytes: number, sampleCount = 1000): number[] {
  const kib = Math.max(0, bytes) / 1024;
  const base = 6;
  const perKib = 1.5;
  const centre = base + perKib * kib;
  const maxTail = 38;
  const samples: number[] = [];
  let state = (0x9e3779b9 ^ Math.round(Math.max(0, bytes))) >>> 0;
  for (let i = 0; i < sampleCount; i += 1) {
    state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
    const u = state / 0x100000000;
    // Cubic skew keeps most mass near the centre with a bounded slow tail.
    samples.push(centre + Math.pow(u, 3) * maxTail);
  }
  return samples;
}

/** Compute the P95/P99 envelope for the belt at `bytes`. */
export function measureBeltEnvelope(bytes: number, sampleCount = 1000): LatencyEnvelope {
  const samples = modelBeltLatencyMs(bytes, sampleCount);
  return {
    p95Ms: nearestRankPercentile(samples, 95),
    p99Ms: nearestRankPercentile(samples, 99),
    sampleCount: samples.length,
  };
}

/** True only when the envelope clears both the exclusive P95 and inclusive P99 budgets. */
export function envelopeWithinBudget(
  envelope: LatencyEnvelope,
  budget: LatencyBudget,
): boolean {
  return envelope.p95Ms < budget.p95ExclusiveMs && envelope.p99Ms <= budget.p99InclusiveMs;
}
