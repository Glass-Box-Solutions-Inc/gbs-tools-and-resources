// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// Shared type definitions for the invoice reconciliation tester service.
// All interfaces used across generators, matchers, test suites, and routes.

export interface CsvFixtureConfig {
  rowCount: number;
  columnVariant: "standard" | "abbreviated" | "custom";
  includeEdgeCases: boolean;
  includeUnicode: boolean;
  includeBom: boolean;
}

export interface ParsedLineItem {
  lineNumber: number;
  description: string;
  hours: number | null;
  rate: number | null;
  amount: number;
  category: string | null;
}

export interface CsvFixtureResult {
  csv: string;
  lineItems: ParsedLineItem[];
  config: CsvFixtureConfig;
}

export interface LinearFixture {
  id: string;
  identifier: string;
  title: string;
  description: string;
  assignee: string;
  state: string;
  estimate: number | null;
  createdAt: string;
}

export interface GitHubFixture {
  number: number;
  title: string;
  body: string;
  user: string;
  merged: boolean;
  mergedAt: string | null;
  additions: number;
  deletions: number;
  changedFiles: number;
}

export interface MatchPair {
  invoiceLineNumber: number;
  invoiceDescription: string;
  matchedEntityType: "linear_issue" | "github_pr";
  matchedEntityId: string;
  expectedMatch: boolean;
  expectedConfidence: number;
}

export interface AccuracyMetrics {
  truePositives: number;
  falsePositives: number;
  trueNegatives: number;
  falseNegatives: number;
  precision: number;
  recall: number;
  f1Score: number;
}

export type VarianceType =
  | "hours_mismatch"
  | "rate_mismatch"
  | "unmatched_invoice"
  | "unmatched_work";

export interface VarianceTestCase {
  description: string;
  invoiceHours: number;
  trackedHours: number;
  invoiceRate: number;
  expectedVarianceType: VarianceType;
  expectedVarianceAmount: number;
}

export interface TestSuiteResult {
  suiteName: string;
  totalTests: number;
  passed: number;
  failed: number;
  metrics?: AccuracyMetrics;
  durationMs: number;
  details: TestCaseResult[];
}

export interface TestCaseResult {
  testName: string;
  passed: boolean;
  expected: unknown;
  actual: unknown;
  errorMsg?: string;
  durationMs: number;
}

export interface RunSummary {
  runId: string;
  status: string;
  startedAt: string;
  completedAt: string | null;
  totalSuites: number;
  totalTests: number;
  passedTests: number;
  failedTests: number;
  accuracy?: AccuracyMetrics;
}

export interface ConfidenceTestCase {
  description: string;
  invoiceDescription: string;
  entityTitle: string;
  entityType: "linear_issue" | "github_pr";
  expectedMinConfidence: number;
  expectedMaxConfidence: number;
}

export interface ColumnHeaders {
  description: string;
  hours: string;
  rate: string;
  amount: string;
}
