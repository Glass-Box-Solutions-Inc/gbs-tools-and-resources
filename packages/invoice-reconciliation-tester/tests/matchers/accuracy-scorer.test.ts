// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// Unit tests for the accuracy scorer. Validates precision, recall, and F1
// computation with known inputs covering perfect accuracy, all-wrong,
// mixed results, and edge cases (empty input, single item).

import { describe, it, expect } from "vitest";
import {
  computeAccuracy,
  checkThresholds,
} from "../../src/matchers/accuracy-scorer.js";
import type { PredictionResult } from "../../src/matchers/accuracy-scorer.js";

describe("Accuracy Scorer", () => {
  describe("computeAccuracy", () => {
    it("computes perfect accuracy (all correct predictions)", () => {
      const results: PredictionResult[] = [
        { predicted: true, actual: true },
        { predicted: true, actual: true },
        { predicted: false, actual: false },
        { predicted: false, actual: false },
      ];

      const metrics = computeAccuracy(results);

      expect(metrics.truePositives).toBe(2);
      expect(metrics.falsePositives).toBe(0);
      expect(metrics.trueNegatives).toBe(2);
      expect(metrics.falseNegatives).toBe(0);
      expect(metrics.precision).toBe(1);
      expect(metrics.recall).toBe(1);
      expect(metrics.f1Score).toBe(1);
    });

    it("computes zero accuracy (all false positives)", () => {
      const results: PredictionResult[] = [
        { predicted: true, actual: false },
        { predicted: true, actual: false },
        { predicted: true, actual: false },
      ];

      const metrics = computeAccuracy(results);

      expect(metrics.truePositives).toBe(0);
      expect(metrics.falsePositives).toBe(3);
      expect(metrics.precision).toBe(0);
      expect(metrics.recall).toBe(0);
      expect(metrics.f1Score).toBe(0);
    });

    it("computes zero recall (all false negatives)", () => {
      const results: PredictionResult[] = [
        { predicted: false, actual: true },
        { predicted: false, actual: true },
        { predicted: false, actual: true },
      ];

      const metrics = computeAccuracy(results);

      expect(metrics.truePositives).toBe(0);
      expect(metrics.falseNegatives).toBe(3);
      expect(metrics.precision).toBe(0);
      expect(metrics.recall).toBe(0);
      expect(metrics.f1Score).toBe(0);
    });

    it("computes mixed results correctly", () => {
      const results: PredictionResult[] = [
        { predicted: true, actual: true },   // TP
        { predicted: true, actual: true },   // TP
        { predicted: true, actual: false },  // FP
        { predicted: false, actual: true },  // FN
        { predicted: false, actual: false }, // TN
      ];

      const metrics = computeAccuracy(results);

      expect(metrics.truePositives).toBe(2);
      expect(metrics.falsePositives).toBe(1);
      expect(metrics.trueNegatives).toBe(1);
      expect(metrics.falseNegatives).toBe(1);
      expect(metrics.precision).toBeCloseTo(2 / 3, 5);
      expect(metrics.recall).toBeCloseTo(2 / 3, 5);
      expect(metrics.f1Score).toBeCloseTo(2 / 3, 5);
    });

    it("handles empty input", () => {
      const metrics = computeAccuracy([]);

      expect(metrics.truePositives).toBe(0);
      expect(metrics.falsePositives).toBe(0);
      expect(metrics.trueNegatives).toBe(0);
      expect(metrics.falseNegatives).toBe(0);
      expect(metrics.precision).toBe(0);
      expect(metrics.recall).toBe(0);
      expect(metrics.f1Score).toBe(0);
    });

    it("handles single true positive", () => {
      const metrics = computeAccuracy([{ predicted: true, actual: true }]);

      expect(metrics.precision).toBe(1);
      expect(metrics.recall).toBe(1);
      expect(metrics.f1Score).toBe(1);
    });

    it("handles single false positive", () => {
      const metrics = computeAccuracy([{ predicted: true, actual: false }]);

      expect(metrics.precision).toBe(0);
      expect(metrics.recall).toBe(0);
      expect(metrics.f1Score).toBe(0);
    });

    it("handles single true negative", () => {
      const metrics = computeAccuracy([{ predicted: false, actual: false }]);

      expect(metrics.trueNegatives).toBe(1);
      expect(metrics.precision).toBe(0);
      expect(metrics.recall).toBe(0);
      expect(metrics.f1Score).toBe(0);
    });

    it("computes high precision, low recall correctly", () => {
      const results: PredictionResult[] = [
        { predicted: true, actual: true },   // TP
        { predicted: false, actual: true },  // FN
        { predicted: false, actual: true },  // FN
        { predicted: false, actual: true },  // FN
        { predicted: false, actual: false }, // TN
      ];

      const metrics = computeAccuracy(results);

      expect(metrics.precision).toBe(1);
      expect(metrics.recall).toBeCloseTo(0.25, 5);
    });

    it("computes low precision, high recall correctly", () => {
      const results: PredictionResult[] = [
        { predicted: true, actual: true },   // TP
        { predicted: true, actual: false },  // FP
        { predicted: true, actual: false },  // FP
        { predicted: true, actual: false },  // FP
      ];

      const metrics = computeAccuracy(results);

      expect(metrics.precision).toBeCloseTo(0.25, 5);
      expect(metrics.recall).toBe(1);
    });

    it("handles large dataset", () => {
      const results: PredictionResult[] = [];
      for (let i = 0; i < 100; i++) {
        results.push({ predicted: true, actual: true });
      }
      for (let i = 0; i < 10; i++) {
        results.push({ predicted: true, actual: false });
      }
      for (let i = 0; i < 5; i++) {
        results.push({ predicted: false, actual: true });
      }
      for (let i = 0; i < 50; i++) {
        results.push({ predicted: false, actual: false });
      }

      const metrics = computeAccuracy(results);

      expect(metrics.truePositives).toBe(100);
      expect(metrics.falsePositives).toBe(10);
      expect(metrics.falseNegatives).toBe(5);
      expect(metrics.trueNegatives).toBe(50);
      expect(metrics.precision).toBeCloseTo(100 / 110, 5);
      expect(metrics.recall).toBeCloseTo(100 / 105, 5);
    });

    it("F1 is harmonic mean of precision and recall", () => {
      const results: PredictionResult[] = [
        { predicted: true, actual: true },
        { predicted: true, actual: true },
        { predicted: true, actual: true },
        { predicted: true, actual: false },
        { predicted: false, actual: true },
        { predicted: false, actual: true },
      ];

      const metrics = computeAccuracy(results);

      const expectedPrecision = 3 / 4;
      const expectedRecall = 3 / 5;
      const expectedF1 =
        (2 * expectedPrecision * expectedRecall) /
        (expectedPrecision + expectedRecall);

      expect(metrics.precision).toBeCloseTo(expectedPrecision, 5);
      expect(metrics.recall).toBeCloseTo(expectedRecall, 5);
      expect(metrics.f1Score).toBeCloseTo(expectedF1, 5);
    });
  });

  describe("checkThresholds", () => {
    it("returns no violations when all thresholds met", () => {
      const metrics = computeAccuracy([
        { predicted: true, actual: true },
        { predicted: true, actual: true },
        { predicted: false, actual: false },
      ]);

      const violations = checkThresholds(metrics, 0.8, 0.8, 0.8);

      expect(violations).toHaveLength(0);
    });

    it("reports precision violation", () => {
      const metrics = computeAccuracy([
        { predicted: true, actual: true },
        { predicted: true, actual: false },
        { predicted: true, actual: false },
        { predicted: true, actual: false },
      ]);

      const violations = checkThresholds(metrics, 0.8, 0.0, 0.0);

      expect(violations.length).toBeGreaterThan(0);
      expect(violations[0]).toContain("Precision");
    });

    it("reports recall violation", () => {
      const metrics = computeAccuracy([
        { predicted: true, actual: true },
        { predicted: false, actual: true },
        { predicted: false, actual: true },
        { predicted: false, actual: true },
      ]);

      const violations = checkThresholds(metrics, 0.0, 0.8, 0.0);

      expect(violations.length).toBeGreaterThan(0);
      expect(violations[0]).toContain("Recall");
    });

    it("reports F1 violation", () => {
      const metrics = computeAccuracy([
        { predicted: true, actual: true },
        { predicted: true, actual: false },
        { predicted: true, actual: false },
        { predicted: false, actual: true },
        { predicted: false, actual: true },
      ]);

      const violations = checkThresholds(metrics, 0.0, 0.0, 0.9);

      expect(violations.some((v) => v.includes("F1 Score"))).toBe(true);
    });

    it("uses default thresholds of 0.8", () => {
      const metrics = {
        truePositives: 1,
        falsePositives: 1,
        trueNegatives: 1,
        falseNegatives: 1,
        precision: 0.5,
        recall: 0.5,
        f1Score: 0.5,
      };

      const violations = checkThresholds(metrics);

      expect(violations).toHaveLength(3);
    });
  });
});
