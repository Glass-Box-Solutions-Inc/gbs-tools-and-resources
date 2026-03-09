// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// Test suite orchestrator. Runs all test suites, collects results, and persists
// them to the database. Designed to be triggered via POST /api/run and executed
// asynchronously (fire-and-forget).

import { Prisma } from "@prisma/client";
import { db } from "./lib/db.js";
import { generateCsvFixture, generateCsvWithMixedCaseHeaders, generateCsvWithSpecialAmounts } from "./generators/csv-fixture.generator.js";
import { generateLinearFixtureSet, resetIssueCounter } from "./generators/linear-fixture.generator.js";
import { generateGitHubFixtureSet, resetPrCounter } from "./generators/github-fixture.generator.js";
import { computeAccuracy } from "./matchers/accuracy-scorer.js";
import { computeConfidence, validateAllConfidenceCases } from "./matchers/confidence-validator.js";
import { validateAllVarianceCases } from "./matchers/variance-classifier.js";
import { KNOWN_GOOD_MATCH_PAIRS, KNOWN_GOOD_CONFIDENCE_CASES } from "./test-suites/known-good-matches.js";
import { KNOWN_BAD_MATCH_PAIRS, KNOWN_BAD_CONFIDENCE_CASES } from "./test-suites/known-bad-matches.js";
import { EDGE_CASE_CSV_CONFIGS, EDGE_CASE_CONFIDENCE_CASES, EDGE_CASE_VARIANCE_CASES } from "./test-suites/edge-cases.js";
import type { AccuracyMetrics, TestSuiteResult, TestCaseResult, RunSummary } from "./types/index.js";

/**
 * Run all test suites, persist results, and update the run record.
 */
export async function runAllSuites(runId: string): Promise<void> {
  const suiteResults: TestSuiteResult[] = [];

  try {
    // Reset counters for deterministic fixture generation
    resetIssueCounter();
    resetPrCounter();

    // 1. CSV fixture generation suite
    suiteResults.push(await runCsvGenerationSuite());

    // 2. Known-good matches suite (confidence)
    suiteResults.push(await runKnownGoodMatchesSuite());

    // 3. Known-bad matches suite (confidence)
    suiteResults.push(await runKnownBadMatchesSuite());

    // 4. Edge cases confidence suite
    suiteResults.push(await runEdgeCasesConfidenceSuite());

    // 5. Variance classification suite
    suiteResults.push(await runVarianceClassificationSuite());

    // 6. Accuracy metrics validation suite
    suiteResults.push(await runAccuracyValidationSuite());

    // Compute aggregate accuracy across matching suites
    const aggregateAccuracy = computeAggregateAccuracy(suiteResults);

    // Persist all results to DB
    await persistResults(runId, suiteResults);

    // Build summary
    const totalTests = suiteResults.reduce((sum, s) => sum + s.totalTests, 0);
    const passedTests = suiteResults.reduce((sum, s) => sum + s.passed, 0);
    const failedTests = suiteResults.reduce((sum, s) => sum + s.failed, 0);

    const summary: RunSummary = {
      runId,
      status: failedTests > 0 ? "completed" : "completed",
      startedAt: new Date().toISOString(),
      completedAt: new Date().toISOString(),
      totalSuites: suiteResults.length,
      totalTests,
      passedTests,
      failedTests,
      accuracy: aggregateAccuracy,
    };

    // Update run record
    await db.testRun.update({
      where: { id: runId },
      data: {
        status: "completed",
        completedAt: new Date(),
        summary: summary as object,
      },
    });
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error);
    await db.testRun.update({
      where: { id: runId },
      data: {
        status: "failed",
        completedAt: new Date(),
        summary: { error: errorMsg },
      },
    });
    throw error;
  }
}

// ── Suite: CSV Fixture Generation ─────────────────────────────────────────────

async function runCsvGenerationSuite(): Promise<TestSuiteResult> {
  const start = performance.now();
  const details: TestCaseResult[] = [];

  // Test each column variant
  for (const variant of ["standard", "abbreviated", "custom"] as const) {
    const caseStart = performance.now();
    try {
      const result = generateCsvFixture({
        rowCount: 10,
        columnVariant: variant,
        includeEdgeCases: false,
        includeUnicode: false,
        includeBom: false,
      });
      const hasContent = result.csv.length > 0;
      const hasLineItems = result.lineItems.length === 10;
      const passed = hasContent && hasLineItems;
      details.push({
        testName: `CSV generation with ${variant} columns`,
        passed,
        expected: { rowCount: 10, hasContent: true },
        actual: { csvLength: result.csv.length, lineItemCount: result.lineItems.length },
        errorMsg: passed ? undefined : `Expected 10 line items, got ${result.lineItems.length}`,
        durationMs: Math.round(performance.now() - caseStart),
      });
    } catch (err) {
      details.push({
        testName: `CSV generation with ${variant} columns`,
        passed: false,
        expected: { rowCount: 10 },
        actual: null,
        errorMsg: err instanceof Error ? err.message : String(err),
        durationMs: Math.round(performance.now() - caseStart),
      });
    }
  }

  // Test edge cases inclusion
  const edgeCaseStart = performance.now();
  try {
    const result = generateCsvFixture({
      rowCount: 10,
      columnVariant: "standard",
      includeEdgeCases: true,
      includeUnicode: false,
      includeBom: false,
    });
    const hasEdgeCases = result.lineItems.some(
      (item) => item.hours === 0 || item.amount < 0 || item.description === "",
    );
    details.push({
      testName: "CSV generation includes edge case rows",
      passed: hasEdgeCases,
      expected: { hasEdgeCases: true },
      actual: { hasEdgeCases, totalItems: result.lineItems.length },
      errorMsg: hasEdgeCases ? undefined : "Edge case rows not found in output",
      durationMs: Math.round(performance.now() - edgeCaseStart),
    });
  } catch (err) {
    details.push({
      testName: "CSV generation includes edge case rows",
      passed: false,
      expected: { hasEdgeCases: true },
      actual: null,
      errorMsg: err instanceof Error ? err.message : String(err),
      durationMs: Math.round(performance.now() - edgeCaseStart),
    });
  }

  // Test unicode inclusion
  const unicodeStart = performance.now();
  try {
    const result = generateCsvFixture({
      rowCount: 5,
      columnVariant: "standard",
      includeEdgeCases: false,
      includeUnicode: true,
      includeBom: false,
    });
    const hasUnicode = result.lineItems.some(
      (item) => /[^\x00-\x7F]/.test(item.description),
    );
    details.push({
      testName: "CSV generation includes unicode descriptions",
      passed: hasUnicode,
      expected: { hasUnicode: true },
      actual: { hasUnicode, totalItems: result.lineItems.length },
      errorMsg: hasUnicode ? undefined : "Unicode descriptions not found in output",
      durationMs: Math.round(performance.now() - unicodeStart),
    });
  } catch (err) {
    details.push({
      testName: "CSV generation includes unicode descriptions",
      passed: false,
      expected: { hasUnicode: true },
      actual: null,
      errorMsg: err instanceof Error ? err.message : String(err),
      durationMs: Math.round(performance.now() - unicodeStart),
    });
  }

  // Test BOM prefix
  const bomStart = performance.now();
  try {
    const result = generateCsvFixture({
      rowCount: 3,
      columnVariant: "standard",
      includeEdgeCases: false,
      includeUnicode: false,
      includeBom: true,
    });
    const hasBom = result.csv.charCodeAt(0) === 0xfeff;
    details.push({
      testName: "CSV generation includes BOM prefix",
      passed: hasBom,
      expected: { hasBom: true },
      actual: { hasBom, firstCharCode: result.csv.charCodeAt(0) },
      errorMsg: hasBom ? undefined : "BOM prefix not found at start of CSV",
      durationMs: Math.round(performance.now() - bomStart),
    });
  } catch (err) {
    details.push({
      testName: "CSV generation includes BOM prefix",
      passed: false,
      expected: { hasBom: true },
      actual: null,
      errorMsg: err instanceof Error ? err.message : String(err),
      durationMs: Math.round(performance.now() - bomStart),
    });
  }

  // Test mixed-case headers
  const mixedCaseStart = performance.now();
  try {
    const result = generateCsvWithMixedCaseHeaders();
    const hasMixedCase = result.csv.includes("dEsCrIpTiOn");
    details.push({
      testName: "CSV generation with mixed-case column headers",
      passed: hasMixedCase,
      expected: { hasMixedCase: true },
      actual: { hasMixedCase },
      errorMsg: hasMixedCase ? undefined : "Mixed-case headers not found",
      durationMs: Math.round(performance.now() - mixedCaseStart),
    });
  } catch (err) {
    details.push({
      testName: "CSV generation with mixed-case column headers",
      passed: false,
      expected: { hasMixedCase: true },
      actual: null,
      errorMsg: err instanceof Error ? err.message : String(err),
      durationMs: Math.round(performance.now() - mixedCaseStart),
    });
  }

  // Test special amount formatting
  const specialAmountStart = performance.now();
  try {
    const result = generateCsvWithSpecialAmounts();
    const hasSpecialAmounts = result.csv.includes("$1,200.00") || result.csv.includes("$437.50");
    details.push({
      testName: "CSV generation with special amount formatting ($, commas)",
      passed: hasSpecialAmounts,
      expected: { hasSpecialAmounts: true },
      actual: { hasSpecialAmounts },
      errorMsg: hasSpecialAmounts ? undefined : "Special amount formatting not found",
      durationMs: Math.round(performance.now() - specialAmountStart),
    });
  } catch (err) {
    details.push({
      testName: "CSV generation with special amount formatting ($, commas)",
      passed: false,
      expected: { hasSpecialAmounts: true },
      actual: null,
      errorMsg: err instanceof Error ? err.message : String(err),
      durationMs: Math.round(performance.now() - specialAmountStart),
    });
  }

  const totalDuration = Math.round(performance.now() - start);
  const passed = details.filter((d) => d.passed).length;

  return {
    suiteName: "csv-fixture-generation",
    totalTests: details.length,
    passed,
    failed: details.length - passed,
    durationMs: totalDuration,
    details,
  };
}

// ── Suite: Known-Good Matches ─────────────────────────────────────────────────

async function runKnownGoodMatchesSuite(): Promise<TestSuiteResult> {
  const start = performance.now();
  const details = validateAllConfidenceCases(KNOWN_GOOD_CONFIDENCE_CASES);
  const totalDuration = Math.round(performance.now() - start);
  const passed = details.filter((d) => d.passed).length;

  // Compute accuracy metrics: all pairs in known-good should be predicted as matches
  const predictionResults = KNOWN_GOOD_MATCH_PAIRS.map((pair) => ({
    predicted: true,
    actual: pair.expectedMatch,
  }));
  const metrics = computeAccuracy(predictionResults);

  return {
    suiteName: "known-good-matches",
    totalTests: details.length,
    passed,
    failed: details.length - passed,
    metrics,
    durationMs: totalDuration,
    details,
  };
}

// ── Suite: Known-Bad Matches ──────────────────────────────────────────────────

async function runKnownBadMatchesSuite(): Promise<TestSuiteResult> {
  const start = performance.now();
  const details = validateAllConfidenceCases(KNOWN_BAD_CONFIDENCE_CASES);
  const totalDuration = Math.round(performance.now() - start);
  const passed = details.filter((d) => d.passed).length;

  // Compute accuracy metrics: all pairs in known-bad should be predicted as non-matches
  const predictionResults = KNOWN_BAD_MATCH_PAIRS.map((pair) => ({
    predicted: false,
    actual: pair.expectedMatch,
  }));
  const metrics = computeAccuracy(predictionResults);

  return {
    suiteName: "known-bad-matches",
    totalTests: details.length,
    passed,
    failed: details.length - passed,
    metrics,
    durationMs: totalDuration,
    details,
  };
}

// ── Suite: Edge Cases Confidence ──────────────────────────────────────────────

async function runEdgeCasesConfidenceSuite(): Promise<TestSuiteResult> {
  const start = performance.now();
  const details = validateAllConfidenceCases(EDGE_CASE_CONFIDENCE_CASES);
  const totalDuration = Math.round(performance.now() - start);
  const passed = details.filter((d) => d.passed).length;

  return {
    suiteName: "edge-cases-confidence",
    totalTests: details.length,
    passed,
    failed: details.length - passed,
    durationMs: totalDuration,
    details,
  };
}

// ── Suite: Variance Classification ────────────────────────────────────────────

async function runVarianceClassificationSuite(): Promise<TestSuiteResult> {
  const start = performance.now();
  const details = validateAllVarianceCases(EDGE_CASE_VARIANCE_CASES);
  const totalDuration = Math.round(performance.now() - start);
  const passed = details.filter((d) => d.passed).length;

  return {
    suiteName: "variance-classification",
    totalTests: details.length,
    passed,
    failed: details.length - passed,
    durationMs: totalDuration,
    details,
  };
}

// ── Suite: Accuracy Metrics Validation ────────────────────────────────────────

async function runAccuracyValidationSuite(): Promise<TestSuiteResult> {
  const start = performance.now();
  const details: TestCaseResult[] = [];

  // Test 1: Perfect accuracy (all correct)
  const perfectStart = performance.now();
  const perfectResults = [
    { predicted: true, actual: true },
    { predicted: true, actual: true },
    { predicted: false, actual: false },
    { predicted: false, actual: false },
  ];
  const perfectMetrics = computeAccuracy(perfectResults);
  details.push({
    testName: "Perfect accuracy: precision=1, recall=1, F1=1",
    passed:
      perfectMetrics.precision === 1 &&
      perfectMetrics.recall === 1 &&
      perfectMetrics.f1Score === 1,
    expected: { precision: 1, recall: 1, f1Score: 1 },
    actual: perfectMetrics,
    durationMs: Math.round(performance.now() - perfectStart),
  });

  // Test 2: All false positives
  const fpStart = performance.now();
  const fpResults = [
    { predicted: true, actual: false },
    { predicted: true, actual: false },
    { predicted: true, actual: false },
  ];
  const fpMetrics = computeAccuracy(fpResults);
  details.push({
    testName: "All false positives: precision=0, recall=0",
    passed: fpMetrics.precision === 0 && fpMetrics.recall === 0 && fpMetrics.f1Score === 0,
    expected: { precision: 0, recall: 0, f1Score: 0 },
    actual: fpMetrics,
    durationMs: Math.round(performance.now() - fpStart),
  });

  // Test 3: All false negatives
  const fnStart = performance.now();
  const fnResults = [
    { predicted: false, actual: true },
    { predicted: false, actual: true },
    { predicted: false, actual: true },
  ];
  const fnMetrics = computeAccuracy(fnResults);
  details.push({
    testName: "All false negatives: precision=0, recall=0",
    passed: fnMetrics.precision === 0 && fnMetrics.recall === 0 && fnMetrics.f1Score === 0,
    expected: { precision: 0, recall: 0, f1Score: 0 },
    actual: fnMetrics,
    durationMs: Math.round(performance.now() - fnStart),
  });

  // Test 4: Mixed results (known precision/recall)
  const mixedStart = performance.now();
  const mixedResults = [
    { predicted: true, actual: true },   // TP
    { predicted: true, actual: true },   // TP
    { predicted: true, actual: false },  // FP
    { predicted: false, actual: true },  // FN
    { predicted: false, actual: false }, // TN
  ];
  const mixedMetrics = computeAccuracy(mixedResults);
  const expectedPrecision = 2 / 3;
  const expectedRecall = 2 / 3;
  const expectedF1 = 2 * (expectedPrecision * expectedRecall) / (expectedPrecision + expectedRecall);
  const precisionMatch = Math.abs(mixedMetrics.precision - expectedPrecision) < 0.001;
  const recallMatch = Math.abs(mixedMetrics.recall - expectedRecall) < 0.001;
  const f1Match = Math.abs(mixedMetrics.f1Score - expectedF1) < 0.001;
  details.push({
    testName: "Mixed results: precision=0.667, recall=0.667, F1=0.667",
    passed: precisionMatch && recallMatch && f1Match,
    expected: { precision: expectedPrecision, recall: expectedRecall, f1Score: expectedF1 },
    actual: mixedMetrics,
    errorMsg:
      precisionMatch && recallMatch && f1Match
        ? undefined
        : `Precision: ${mixedMetrics.precision.toFixed(3)}, Recall: ${mixedMetrics.recall.toFixed(3)}, F1: ${mixedMetrics.f1Score.toFixed(3)}`,
    durationMs: Math.round(performance.now() - mixedStart),
  });

  // Test 5: Empty results
  const emptyStart = performance.now();
  const emptyMetrics = computeAccuracy([]);
  details.push({
    testName: "Empty results: all metrics zero",
    passed:
      emptyMetrics.precision === 0 &&
      emptyMetrics.recall === 0 &&
      emptyMetrics.f1Score === 0,
    expected: { precision: 0, recall: 0, f1Score: 0 },
    actual: emptyMetrics,
    durationMs: Math.round(performance.now() - emptyStart),
  });

  // Test 6: High precision, low recall
  const hpStart = performance.now();
  const hpResults = [
    { predicted: true, actual: true },   // TP
    { predicted: false, actual: true },  // FN
    { predicted: false, actual: true },  // FN
    { predicted: false, actual: true },  // FN
    { predicted: false, actual: false }, // TN
  ];
  const hpMetrics = computeAccuracy(hpResults);
  details.push({
    testName: "High precision (1.0), low recall (0.25)",
    passed: hpMetrics.precision === 1 && Math.abs(hpMetrics.recall - 0.25) < 0.001,
    expected: { precision: 1.0, recall: 0.25 },
    actual: { precision: hpMetrics.precision, recall: hpMetrics.recall },
    durationMs: Math.round(performance.now() - hpStart),
  });

  // Test 7: Low precision, high recall
  const lpStart = performance.now();
  const lpResults = [
    { predicted: true, actual: true },   // TP
    { predicted: true, actual: false },  // FP
    { predicted: true, actual: false },  // FP
    { predicted: true, actual: false },  // FP
  ];
  const lpMetrics = computeAccuracy(lpResults);
  details.push({
    testName: "Low precision (0.25), high recall (1.0)",
    passed: Math.abs(lpMetrics.precision - 0.25) < 0.001 && lpMetrics.recall === 1,
    expected: { precision: 0.25, recall: 1.0 },
    actual: { precision: lpMetrics.precision, recall: lpMetrics.recall },
    durationMs: Math.round(performance.now() - lpStart),
  });

  // Test 8: Generate fixtures and validate matching structure
  const fixtureStart = performance.now();
  const csvFixture = generateCsvFixture({
    rowCount: 5,
    columnVariant: "standard",
    includeEdgeCases: false,
    includeUnicode: false,
    includeBom: false,
  });
  const linearFixtures = generateLinearFixtureSet(csvFixture.lineItems, 5);
  const githubFixtures = generateGitHubFixtureSet(csvFixture.lineItems, 5);

  const hasMatchingLinear = linearFixtures.matching.length > 0;
  const hasNonMatchingLinear = linearFixtures.nonMatching.length === 5;
  const hasMatchingGitHub = githubFixtures.matching.length > 0;
  const hasNonMatchingGitHub = githubFixtures.nonMatching.length === 5;
  const fixturesPassed = hasMatchingLinear && hasNonMatchingLinear && hasMatchingGitHub && hasNonMatchingGitHub;
  details.push({
    testName: "Fixture generation produces matching and non-matching sets",
    passed: fixturesPassed,
    expected: {
      matchingLinear: ">0",
      nonMatchingLinear: 5,
      matchingGitHub: ">0",
      nonMatchingGitHub: 5,
    },
    actual: {
      matchingLinear: linearFixtures.matching.length,
      nonMatchingLinear: linearFixtures.nonMatching.length,
      matchingGitHub: githubFixtures.matching.length,
      nonMatchingGitHub: githubFixtures.nonMatching.length,
    },
    durationMs: Math.round(performance.now() - fixtureStart),
  });

  // Test 9: Matching Linear issue titles match invoice descriptions
  const matchStart = performance.now();
  const matchingTitlesCorrect = linearFixtures.matching.every((issue) =>
    csvFixture.lineItems.some((item) => item.description === issue.title),
  );
  details.push({
    testName: "Matching Linear issue titles correspond to invoice descriptions",
    passed: matchingTitlesCorrect,
    expected: { allTitlesMatch: true },
    actual: { allTitlesMatch: matchingTitlesCorrect },
    durationMs: Math.round(performance.now() - matchStart),
  });

  // Test 10: Confidence scoring for matching fixtures
  const confStart = performance.now();
  const confidenceScores = linearFixtures.matching.map((issue) => {
    const matchedItem = csvFixture.lineItems.find(
      (item) => item.description === issue.title,
    );
    if (!matchedItem) return 0;
    return computeConfidence(matchedItem.description, issue.title);
  });
  const allHighConfidence = confidenceScores.every((score) => score >= 0.95);
  details.push({
    testName: "Exact matching fixtures produce confidence >= 0.95",
    passed: allHighConfidence,
    expected: { allAbove095: true },
    actual: {
      allAbove095: allHighConfidence,
      scores: confidenceScores.map((s) => s.toFixed(3)),
    },
    durationMs: Math.round(performance.now() - confStart),
  });

  const totalDuration = Math.round(performance.now() - start);
  const passed = details.filter((d) => d.passed).length;

  return {
    suiteName: "accuracy-metrics-validation",
    totalTests: details.length,
    passed,
    failed: details.length - passed,
    durationMs: totalDuration,
    details,
  };
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function computeAggregateAccuracy(
  suiteResults: TestSuiteResult[],
): AccuracyMetrics {
  const suitesWithMetrics = suiteResults.filter((s) => s.metrics);
  if (suitesWithMetrics.length === 0) {
    return {
      truePositives: 0,
      falsePositives: 0,
      trueNegatives: 0,
      falseNegatives: 0,
      precision: 0,
      recall: 0,
      f1Score: 0,
    };
  }

  let totalTp = 0;
  let totalFp = 0;
  let totalTn = 0;
  let totalFn = 0;

  for (const suite of suitesWithMetrics) {
    totalTp += suite.metrics!.truePositives;
    totalFp += suite.metrics!.falsePositives;
    totalTn += suite.metrics!.trueNegatives;
    totalFn += suite.metrics!.falseNegatives;
  }

  const precision = totalTp + totalFp > 0 ? totalTp / (totalTp + totalFp) : 0;
  const recall = totalTp + totalFn > 0 ? totalTp / (totalTp + totalFn) : 0;
  const f1Score =
    precision + recall > 0
      ? (2 * (precision * recall)) / (precision + recall)
      : 0;

  return {
    truePositives: totalTp,
    falsePositives: totalFp,
    trueNegatives: totalTn,
    falseNegatives: totalFn,
    precision,
    recall,
    f1Score,
  };
}

async function persistResults(
  runId: string,
  suiteResults: TestSuiteResult[],
): Promise<void> {
  const testResults = suiteResults.flatMap((suite) =>
    suite.details.map((detail) => ({
      runId,
      suiteName: suite.suiteName,
      testName: detail.testName,
      passed: detail.passed,
      expected: detail.expected as object,
      actual: detail.actual as object,
      metrics: suite.metrics
        ? (JSON.parse(JSON.stringify(suite.metrics)) as Prisma.InputJsonValue)
        : Prisma.JsonNull,
      errorMsg: detail.errorMsg ?? null,
      durationMs: detail.durationMs,
    })),
  );

  // Batch insert in chunks to avoid overwhelming the DB
  const chunkSize = 50;
  for (let i = 0; i < testResults.length; i += chunkSize) {
    const chunk = testResults.slice(i, i + chunkSize);
    await db.testResult.createMany({ data: chunk });
  }
}
