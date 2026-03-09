// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// Validates confidence scoring logic for the invoice reconciliation matching algorithm.
// Tests that confidence values fall within expected ranges based on match quality:
//   - Exact description match:   confidence >= 0.95
//   - Partial keyword match:     confidence 0.50-0.94
//   - Fuzzy match:               confidence 0.20-0.49
//   - No match:                  confidence < 0.20
// Also validates that confidence is always bounded to [0.00, 1.00].

import type { ConfidenceTestCase, TestCaseResult } from "../types/index.js";

/**
 * Compute a confidence score between an invoice description and an entity title.
 * This is a reference implementation used for testing. The production reconciler
 * in gbs-operations-audit has its own implementation; this validates the approach.
 */
export function computeConfidence(
  invoiceDescription: string,
  entityTitle: string,
): number {
  if (!invoiceDescription || !entityTitle) {
    return 0;
  }

  const normInvoice = normalizeText(invoiceDescription);
  const normEntity = normalizeText(entityTitle);

  // Exact match after normalization
  if (normInvoice === normEntity) {
    return 1.0;
  }

  // Check if one contains the other fully
  if (normInvoice.includes(normEntity) || normEntity.includes(normInvoice)) {
    const shorter = Math.min(normInvoice.length, normEntity.length);
    const longer = Math.max(normInvoice.length, normEntity.length);
    const containmentRatio = shorter / longer;
    return Math.min(0.99, 0.85 + containmentRatio * 0.14);
  }

  // Keyword-based matching
  const invoiceTokens = tokenize(normInvoice);
  const entityTokens = tokenize(normEntity);

  if (invoiceTokens.length === 0 || entityTokens.length === 0) {
    return 0;
  }

  const commonTokens = invoiceTokens.filter((t) => entityTokens.includes(t));
  const jaccardSimilarity =
    commonTokens.length /
    new Set([...invoiceTokens, ...entityTokens]).size;

  // Weighted by how many invoice tokens were found
  const invoiceCoverage = commonTokens.length / invoiceTokens.length;

  // Combined score: jaccard + coverage, capped at 0.94 for non-exact matches
  const rawScore = jaccardSimilarity * 0.6 + invoiceCoverage * 0.4;

  // Apply Levenshtein boost for near-exact matches
  const levenshteinDistance = computeLevenshtein(normInvoice, normEntity);
  const maxLen = Math.max(normInvoice.length, normEntity.length);
  const levenshteinSimilarity = 1 - levenshteinDistance / maxLen;

  const finalScore = rawScore * 0.7 + levenshteinSimilarity * 0.3;

  return Math.min(0.94, Math.max(0, finalScore));
}

function normalizeText(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function tokenize(text: string): string[] {
  const stopWords = new Set([
    "the",
    "a",
    "an",
    "and",
    "or",
    "but",
    "in",
    "on",
    "at",
    "to",
    "for",
    "of",
    "with",
    "by",
    "from",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "have",
    "has",
    "had",
    "do",
    "does",
    "did",
    "will",
    "would",
    "could",
    "should",
    "may",
    "might",
    "shall",
    "can",
    "this",
    "that",
    "these",
    "those",
    "it",
    "its",
  ]);

  return text
    .split(/\s+/)
    .filter((t) => t.length > 1 && !stopWords.has(t));
}

function computeLevenshtein(a: string, b: string): number {
  const m = a.length;
  const n = b.length;
  const dp: number[][] = Array.from({ length: m + 1 }, () =>
    Array.from({ length: n + 1 }, () => 0),
  );

  for (let i = 0; i <= m; i++) dp[i][0] = i;
  for (let j = 0; j <= n; j++) dp[0][j] = j;

  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      if (a[i - 1] === b[j - 1]) {
        dp[i][j] = dp[i - 1][j - 1];
      } else {
        dp[i][j] = 1 + Math.min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1]);
      }
    }
  }

  return dp[m][n];
}

/**
 * Validate a single confidence test case. Returns a TestCaseResult indicating
 * whether the computed confidence falls within the expected range.
 */
export function validateConfidenceCase(
  testCase: ConfidenceTestCase,
): TestCaseResult {
  const start = performance.now();
  const confidence = computeConfidence(
    testCase.invoiceDescription,
    testCase.entityTitle,
  );
  const durationMs = Math.round(performance.now() - start);

  const inRange =
    confidence >= testCase.expectedMinConfidence &&
    confidence <= testCase.expectedMaxConfidence;
  const bounded = confidence >= 0 && confidence <= 1;

  const passed = inRange && bounded;
  const errors: string[] = [];

  if (!bounded) {
    errors.push(
      `Confidence ${confidence.toFixed(4)} is out of bounds [0.00, 1.00]`,
    );
  }
  if (!inRange) {
    errors.push(
      `Confidence ${confidence.toFixed(4)} outside expected range [${testCase.expectedMinConfidence.toFixed(2)}, ${testCase.expectedMaxConfidence.toFixed(2)}]`,
    );
  }

  return {
    testName: testCase.description,
    passed,
    expected: {
      min: testCase.expectedMinConfidence,
      max: testCase.expectedMaxConfidence,
    },
    actual: { confidence, bounded },
    errorMsg: errors.length > 0 ? errors.join("; ") : undefined,
    durationMs,
  };
}

/**
 * Run all confidence test cases and return results.
 */
export function validateAllConfidenceCases(
  cases: ConfidenceTestCase[],
): TestCaseResult[] {
  return cases.map(validateConfidenceCase);
}
