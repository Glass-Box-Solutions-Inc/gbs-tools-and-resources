// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// Edge case test data for the invoice reconciliation tester.
// Covers: zero hours, negative amounts (credits), unicode descriptions,
// BOM-prefixed CSV, mixed-case column headers, empty descriptions,
// very long descriptions, special characters in amounts, and variance
// classification edge cases.

import type {
  CsvFixtureConfig,
  ConfidenceTestCase,
  VarianceTestCase,
} from "../types/index.js";

/**
 * CSV fixture configurations that exercise edge cases in the parser.
 */
export const EDGE_CASE_CSV_CONFIGS: CsvFixtureConfig[] = [
  {
    rowCount: 10,
    columnVariant: "standard",
    includeEdgeCases: true,
    includeUnicode: false,
    includeBom: false,
  },
  {
    rowCount: 5,
    columnVariant: "abbreviated",
    includeEdgeCases: false,
    includeUnicode: true,
    includeBom: false,
  },
  {
    rowCount: 8,
    columnVariant: "custom",
    includeEdgeCases: true,
    includeUnicode: true,
    includeBom: false,
  },
  {
    rowCount: 3,
    columnVariant: "standard",
    includeEdgeCases: false,
    includeUnicode: false,
    includeBom: true,
  },
  {
    rowCount: 6,
    columnVariant: "standard",
    includeEdgeCases: true,
    includeUnicode: true,
    includeBom: true,
  },
];

/**
 * Confidence test cases for edge case scenarios.
 */
export const EDGE_CASE_CONFIDENCE_CASES: ConfidenceTestCase[] = [
  {
    description: "Edge: empty invoice description",
    invoiceDescription: "",
    entityTitle: "Some Linear issue title",
    entityType: "linear_issue",
    expectedMinConfidence: 0.0,
    expectedMaxConfidence: 0.0,
  },
  {
    description: "Edge: empty entity title",
    invoiceDescription: "Implement feature X",
    entityTitle: "",
    entityType: "linear_issue",
    expectedMinConfidence: 0.0,
    expectedMaxConfidence: 0.0,
  },
  {
    description: "Edge: both empty",
    invoiceDescription: "",
    entityTitle: "",
    entityType: "linear_issue",
    expectedMinConfidence: 0.0,
    expectedMaxConfidence: 0.0,
  },
  {
    description: "Edge: very long invoice description vs short entity",
    invoiceDescription:
      "Very long description that exceeds the typical length limit for a line item and contains extensive details about the work performed including multiple sub-tasks cross-references to other items and detailed technical specifications that would normally be in a separate document but the contractor has chosen to include inline for completeness and to provide full context for the billing entry which makes reconciliation more challenging because the matching algorithm needs to handle such verbose input gracefully",
    entityTitle: "Verbose line item",
    entityType: "linear_issue",
    expectedMinConfidence: 0.0,
    expectedMaxConfidence: 0.30,
  },
  {
    description: "Edge: single word match",
    invoiceDescription: "Authentication",
    entityTitle: "Authentication",
    entityType: "linear_issue",
    expectedMinConfidence: 0.95,
    expectedMaxConfidence: 1.0,
  },
  {
    description: "Edge: unicode accented characters - French",
    invoiceDescription: "R\u00e9factoring du module d\u2019authentification",
    entityTitle: "R\u00e9factoring du module d\u2019authentification",
    entityType: "linear_issue",
    expectedMinConfidence: 0.95,
    expectedMaxConfidence: 1.0,
  },
  {
    description: "Edge: unicode accented characters - German",
    invoiceDescription: "Korrektur der Datenbankabfragen f\u00fcr B\u00f6rsen-API",
    entityTitle: "Korrektur der Datenbankabfragen f\u00fcr B\u00f6rsen-API",
    entityType: "linear_issue",
    expectedMinConfidence: 0.95,
    expectedMaxConfidence: 1.0,
  },
  {
    description: "Edge: case difference only",
    invoiceDescription: "IMPLEMENT USER AUTHENTICATION",
    entityTitle: "implement user authentication",
    entityType: "linear_issue",
    expectedMinConfidence: 0.95,
    expectedMaxConfidence: 1.0,
  },
  {
    description: "Edge: special characters in description",
    invoiceDescription: "Fix bug #1234 - API /users endpoint (v2)",
    entityTitle: "Fix bug #1234 - API /users endpoint (v2)",
    entityType: "linear_issue",
    expectedMinConfidence: 0.95,
    expectedMaxConfidence: 1.0,
  },
  {
    description: "Edge: numbers only difference",
    invoiceDescription: "Task 12345",
    entityTitle: "Task 67890",
    entityType: "linear_issue",
    expectedMinConfidence: 0.20,
    expectedMaxConfidence: 0.80,
  },
  {
    description: "Edge: completely numeric descriptions",
    invoiceDescription: "12345",
    entityTitle: "67890",
    entityType: "linear_issue",
    expectedMinConfidence: 0.0,
    expectedMaxConfidence: 0.30,
  },
  {
    description: "Edge: whitespace variations",
    invoiceDescription: "  Implement   user   authentication  ",
    entityTitle: "Implement user authentication",
    entityType: "linear_issue",
    expectedMinConfidence: 0.95,
    expectedMaxConfidence: 1.0,
  },
  {
    description: "Edge: punctuation only difference",
    invoiceDescription: "Implement user authentication.",
    entityTitle: "Implement user authentication!",
    entityType: "linear_issue",
    expectedMinConfidence: 0.95,
    expectedMaxConfidence: 1.0,
  },
  {
    description: "Edge: substring containment - invoice in entity",
    invoiceDescription: "user authentication",
    entityTitle: "Implement user authentication feature for dashboard",
    entityType: "linear_issue",
    expectedMinConfidence: 0.85,
    expectedMaxConfidence: 1.0,
  },
  {
    description: "Edge: substring containment - entity in invoice",
    invoiceDescription: "Implement user authentication feature for dashboard",
    entityTitle: "user authentication",
    entityType: "linear_issue",
    expectedMinConfidence: 0.85,
    expectedMaxConfidence: 1.0,
  },
];

/**
 * Variance classification test cases covering edge scenarios.
 */
export const EDGE_CASE_VARIANCE_CASES: VarianceTestCase[] = [
  {
    description: "Hours mismatch: invoice 8h, tracked 6h at $150/hr",
    invoiceHours: 8,
    trackedHours: 6,
    invoiceRate: 150,
    expectedVarianceType: "hours_mismatch",
    expectedVarianceAmount: 300,
  },
  {
    description: "Hours mismatch: invoice 2h, tracked 5h at $125/hr",
    invoiceHours: 2,
    trackedHours: 5,
    invoiceRate: 125,
    expectedVarianceType: "hours_mismatch",
    expectedVarianceAmount: 375,
  },
  {
    description: "Rate mismatch: invoice $200/hr vs expected $150/hr for 8h",
    invoiceHours: 8,
    trackedHours: 8,
    invoiceRate: 200,
    expectedVarianceType: "rate_mismatch",
    expectedVarianceAmount: 400,
  },
  {
    description: "Rate mismatch: invoice $100/hr vs expected $175/hr for 4h",
    invoiceHours: 4,
    trackedHours: 4,
    invoiceRate: 100,
    expectedVarianceType: "rate_mismatch",
    expectedVarianceAmount: 300,
  },
  {
    description: "Unmatched invoice: 10h at $150/hr with no tracked work",
    invoiceHours: 10,
    trackedHours: 0,
    invoiceRate: 150,
    expectedVarianceType: "unmatched_invoice",
    expectedVarianceAmount: 1500,
  },
  {
    description: "Unmatched work: 6h tracked at $125/hr with no invoice",
    invoiceHours: 0,
    trackedHours: 6,
    invoiceRate: 125,
    expectedVarianceType: "unmatched_work",
    expectedVarianceAmount: 750,
  },
  {
    description: "Zero hours mismatch: invoice 0h, tracked 4h at $100/hr",
    invoiceHours: 0,
    trackedHours: 4,
    invoiceRate: 100,
    expectedVarianceType: "hours_mismatch",
    expectedVarianceAmount: 400,
  },
  {
    description: "Large hours mismatch: invoice 40h, tracked 20h at $175/hr",
    invoiceHours: 40,
    trackedHours: 20,
    invoiceRate: 175,
    expectedVarianceType: "hours_mismatch",
    expectedVarianceAmount: 3500,
  },
  {
    description: "Fractional hours mismatch: invoice 3.5h, tracked 2.75h at $150/hr",
    invoiceHours: 3.5,
    trackedHours: 2.75,
    invoiceRate: 150,
    expectedVarianceType: "hours_mismatch",
    expectedVarianceAmount: 112.5,
  },
  {
    description: "Unmatched invoice: 0.5h at $200/hr with no tracked work",
    invoiceHours: 0.5,
    trackedHours: 0,
    invoiceRate: 200,
    expectedVarianceType: "unmatched_invoice",
    expectedVarianceAmount: 100,
  },
];
