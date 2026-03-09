// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// Computes precision, recall, and F1 score from match results.
// Used to evaluate the accuracy of the invoice reconciliation matching algorithm
// against ground-truth test data.

import type { AccuracyMetrics } from "../types/index.js";

export interface PredictionResult {
  predicted: boolean;
  actual: boolean;
}

/**
 * Compute accuracy metrics (precision, recall, F1) from a set of prediction results.
 *
 * - Precision: Of all predicted matches, how many were correct?
 * - Recall: Of all actual matches, how many were found?
 * - F1 Score: Harmonic mean of precision and recall.
 */
export function computeAccuracy(results: PredictionResult[]): AccuracyMetrics {
  let tp = 0;
  let fp = 0;
  let tn = 0;
  let fn = 0;

  for (const r of results) {
    if (r.predicted && r.actual) tp++;
    else if (r.predicted && !r.actual) fp++;
    else if (!r.predicted && r.actual) fn++;
    else tn++;
  }

  const precision = tp + fp > 0 ? tp / (tp + fp) : 0;
  const recall = tp + fn > 0 ? tp / (tp + fn) : 0;
  const f1Score =
    precision + recall > 0
      ? (2 * (precision * recall)) / (precision + recall)
      : 0;

  return {
    truePositives: tp,
    falsePositives: fp,
    trueNegatives: tn,
    falseNegatives: fn,
    precision,
    recall,
    f1Score,
  };
}

/**
 * Check whether accuracy metrics meet minimum thresholds.
 * Returns a list of threshold violations, or an empty array if all pass.
 */
export function checkThresholds(
  metrics: AccuracyMetrics,
  minPrecision: number = 0.8,
  minRecall: number = 0.8,
  minF1: number = 0.8,
): string[] {
  const violations: string[] = [];

  if (metrics.precision < minPrecision) {
    violations.push(
      `Precision ${metrics.precision.toFixed(3)} below threshold ${minPrecision}`,
    );
  }
  if (metrics.recall < minRecall) {
    violations.push(
      `Recall ${metrics.recall.toFixed(3)} below threshold ${minRecall}`,
    );
  }
  if (metrics.f1Score < minF1) {
    violations.push(
      `F1 Score ${metrics.f1Score.toFixed(3)} below threshold ${minF1}`,
    );
  }

  return violations;
}
