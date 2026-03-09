// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// Tests variance type classification for the invoice reconciliation process.
// Classifies discrepancies between invoice line items and tracked work into:
//   - hours_mismatch:    invoice hours != tracked hours
//   - rate_mismatch:     invoice rate != expected rate
//   - unmatched_invoice: invoice line with no matching work
//   - unmatched_work:    tracked work with no invoice line

import type {
  VarianceType,
  VarianceTestCase,
  TestCaseResult,
} from "../types/index.js";

export interface VarianceInput {
  invoiceHours: number | null;
  trackedHours: number | null;
  invoiceRate: number | null;
  expectedRate: number | null;
  hasMatchedWork: boolean;
  hasMatchedInvoice: boolean;
}

export interface ClassifiedVariance {
  type: VarianceType;
  amount: number;
  description: string;
}

/**
 * Classify the variance between an invoice line item and its matched work item.
 * Returns the variance type and the monetary amount of the discrepancy.
 */
export function classifyVariance(input: VarianceInput): ClassifiedVariance {
  // Unmatched invoice line -- no corresponding work found
  if (!input.hasMatchedWork) {
    const amount =
      (input.invoiceHours ?? 0) * (input.invoiceRate ?? 0);
    return {
      type: "unmatched_invoice",
      amount,
      description: "Invoice line item has no matching tracked work",
    };
  }

  // Unmatched work -- tracked work with no invoice line
  if (!input.hasMatchedInvoice) {
    const amount =
      (input.trackedHours ?? 0) * (input.expectedRate ?? 0);
    return {
      type: "unmatched_work",
      amount,
      description: "Tracked work has no corresponding invoice line",
    };
  }

  // Rate mismatch -- compare invoice rate to expected rate
  if (
    input.invoiceRate !== null &&
    input.expectedRate !== null &&
    Math.abs(input.invoiceRate - input.expectedRate) > 0.01
  ) {
    const hoursBasis = input.invoiceHours ?? input.trackedHours ?? 0;
    const amount = Math.abs(input.invoiceRate - input.expectedRate) * hoursBasis;
    return {
      type: "rate_mismatch",
      amount,
      description: `Rate difference: invoiced $${input.invoiceRate}/hr vs expected $${input.expectedRate}/hr`,
    };
  }

  // Hours mismatch -- compare invoice hours to tracked hours
  if (
    input.invoiceHours !== null &&
    input.trackedHours !== null &&
    Math.abs(input.invoiceHours - input.trackedHours) > 0.01
  ) {
    const rate = input.invoiceRate ?? input.expectedRate ?? 0;
    const amount = Math.abs(input.invoiceHours - input.trackedHours) * rate;
    return {
      type: "hours_mismatch",
      amount,
      description: `Hours difference: invoiced ${input.invoiceHours}h vs tracked ${input.trackedHours}h`,
    };
  }

  // No variance detected -- return hours_mismatch with zero amount as a fallback
  return {
    type: "hours_mismatch",
    amount: 0,
    description: "No variance detected",
  };
}

/**
 * Validate a single variance test case. Returns a TestCaseResult indicating
 * whether the classification matches expectations.
 */
export function validateVarianceCase(
  testCase: VarianceTestCase,
): TestCaseResult {
  const start = performance.now();

  const input: VarianceInput = buildVarianceInput(testCase);
  const result = classifyVariance(input);
  const durationMs = Math.round(performance.now() - start);

  const typeMatch = result.type === testCase.expectedVarianceType;
  const amountMatch =
    Math.abs(result.amount - testCase.expectedVarianceAmount) < 0.01;
  const passed = typeMatch && amountMatch;

  const errors: string[] = [];
  if (!typeMatch) {
    errors.push(
      `Expected type "${testCase.expectedVarianceType}", got "${result.type}"`,
    );
  }
  if (!amountMatch) {
    errors.push(
      `Expected amount ${testCase.expectedVarianceAmount.toFixed(2)}, got ${result.amount.toFixed(2)}`,
    );
  }

  return {
    testName: testCase.description,
    passed,
    expected: {
      type: testCase.expectedVarianceType,
      amount: testCase.expectedVarianceAmount,
    },
    actual: {
      type: result.type,
      amount: result.amount,
      description: result.description,
    },
    errorMsg: errors.length > 0 ? errors.join("; ") : undefined,
    durationMs,
  };
}

function buildVarianceInput(testCase: VarianceTestCase): VarianceInput {
  switch (testCase.expectedVarianceType) {
    case "unmatched_invoice":
      return {
        invoiceHours: testCase.invoiceHours,
        trackedHours: null,
        invoiceRate: testCase.invoiceRate,
        expectedRate: null,
        hasMatchedWork: false,
        hasMatchedInvoice: true,
      };
    case "unmatched_work":
      return {
        invoiceHours: null,
        trackedHours: testCase.trackedHours,
        invoiceRate: null,
        expectedRate: testCase.invoiceRate,
        hasMatchedWork: true,
        hasMatchedInvoice: false,
      };
    case "rate_mismatch":
      return {
        invoiceHours: testCase.invoiceHours,
        trackedHours: testCase.trackedHours,
        invoiceRate: testCase.invoiceRate,
        expectedRate: testCase.invoiceRate - testCase.expectedVarianceAmount / testCase.invoiceHours,
        hasMatchedWork: true,
        hasMatchedInvoice: true,
      };
    case "hours_mismatch":
      return {
        invoiceHours: testCase.invoiceHours,
        trackedHours: testCase.trackedHours,
        invoiceRate: testCase.invoiceRate,
        expectedRate: testCase.invoiceRate,
        hasMatchedWork: true,
        hasMatchedInvoice: true,
      };
    default:
      return {
        invoiceHours: testCase.invoiceHours,
        trackedHours: testCase.trackedHours,
        invoiceRate: testCase.invoiceRate,
        expectedRate: testCase.invoiceRate,
        hasMatchedWork: true,
        hasMatchedInvoice: true,
      };
  }
}

/**
 * Run all variance test cases and return results.
 */
export function validateAllVarianceCases(
  cases: VarianceTestCase[],
): TestCaseResult[] {
  return cases.map(validateVarianceCase);
}
