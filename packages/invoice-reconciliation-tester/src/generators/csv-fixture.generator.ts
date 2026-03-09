// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// Generates synthetic PioneerDev CSV invoices using @faker-js/faker.
// Supports multiple column header variants, edge cases (zero hours, negative
// amounts, unicode, BOM prefix, mixed-case columns), and returns both the raw
// CSV string and structured ParsedLineItem[] for ground truth comparison.

import { faker } from "@faker-js/faker";
import Papa from "papaparse";
import type {
  CsvFixtureConfig,
  CsvFixtureResult,
  ColumnHeaders,
  ParsedLineItem,
} from "../types/index.js";

const COLUMN_VARIANTS: Record<CsvFixtureConfig["columnVariant"], ColumnHeaders> = {
  standard: {
    description: "Description",
    hours: "Hours",
    rate: "Rate",
    amount: "Amount",
  },
  abbreviated: {
    description: "Desc",
    hours: "Qty",
    rate: "Price",
    amount: "Total",
  },
  custom: {
    description: "Work Description",
    hours: "Time",
    rate: "Hourly Rate",
    amount: "Cost",
  },
};

const WORK_TEMPLATES = [
  { template: "Implement {feature} feature", category: "development" },
  { template: "Develop {feature} module", category: "development" },
  { template: "Build {feature} integration", category: "development" },
  { template: "Fix {bug} bug in {component}", category: "bugfix" },
  { template: "Hotfix: {bug} crash on {component}", category: "bugfix" },
  { template: "Resolve {bug} issue in {component}", category: "bugfix" },
  { template: "Code review for {feature} PR", category: "review" },
  { template: "PR review: {feature} implementation", category: "review" },
  { template: "Review {feature} pull request", category: "review" },
  { template: "Sprint planning meeting", category: "meeting" },
  { template: "Weekly standup call", category: "meeting" },
  { template: "Design review meeting for {feature}", category: "meeting" },
  { template: "Client call: {feature} requirements", category: "meeting" },
  { template: "Deploy {feature} to staging", category: "devops" },
  { template: "CI pipeline fix for {component}", category: "devops" },
  { template: "Configure deployment pipeline", category: "devops" },
  { template: "Write E2E tests for {feature}", category: "testing" },
  { template: "QA testing: {feature} module", category: "testing" },
  { template: "Unit test coverage for {component}", category: "testing" },
  { template: "Design {feature} UI mockups in Figma", category: "design" },
  { template: "Update Figma designs for {component}", category: "design" },
];

const FEATURES = [
  "user authentication",
  "dashboard analytics",
  "payment processing",
  "notification system",
  "search functionality",
  "file upload",
  "report generation",
  "user onboarding",
  "API rate limiting",
  "webhook handler",
  "data export",
  "role-based access",
  "audit logging",
  "email templates",
  "caching layer",
];

const COMPONENTS = [
  "auth module",
  "API gateway",
  "database layer",
  "frontend router",
  "middleware stack",
  "queue processor",
  "file service",
  "notification engine",
  "billing module",
  "admin panel",
];

const BUGS = [
  "memory leak",
  "race condition",
  "null pointer",
  "timeout",
  "validation",
  "encoding",
  "pagination",
  "sorting",
  "caching",
  "authentication",
];

function fillTemplate(template: string): string {
  return template
    .replace("{feature}", faker.helpers.arrayElement(FEATURES))
    .replace("{component}", faker.helpers.arrayElement(COMPONENTS))
    .replace("{bug}", faker.helpers.arrayElement(BUGS));
}

function inferCategory(description: string): string | null {
  const lower = description.toLowerCase();
  if (lower.includes("meeting") || lower.includes("standup") || lower.includes("call")) {
    return "meeting";
  }
  if (lower.includes("design") || lower.includes("figma") || lower.includes("mockup")) {
    return "design";
  }
  if (lower.includes("review") || lower.includes("pr ") || lower.includes("code review")) {
    return "review";
  }
  if (lower.includes("test") || lower.includes("qa") || lower.includes("e2e")) {
    return "testing";
  }
  if (lower.includes("deploy") || lower.includes("ci") || lower.includes("pipeline")) {
    return "devops";
  }
  if (lower.includes("bug") || lower.includes("fix") || lower.includes("hotfix")) {
    return "bugfix";
  }
  if (
    lower.includes("feat") ||
    lower.includes("implement") ||
    lower.includes("develop") ||
    lower.includes("build")
  ) {
    return "development";
  }
  return null;
}

function generateStandardRow(): {
  description: string;
  hours: number;
  rate: number;
  amount: number;
} {
  const work = faker.helpers.arrayElement(WORK_TEMPLATES);
  const description = fillTemplate(work.template);
  const hours = faker.number.float({ min: 0.5, max: 40, fractionDigits: 1 });
  const rate = faker.helpers.arrayElement([75, 100, 125, 150, 175, 200]);
  const amount = Math.round(hours * rate * 100) / 100;
  return { description, hours, rate, amount };
}

function generateEdgeCaseRows(): Array<{
  description: string;
  hours: number;
  rate: number;
  amount: number;
}> {
  return [
    { description: "Zero hours admin task", hours: 0, rate: 150, amount: 0 },
    { description: "Credit adjustment for overbilling", hours: -2, rate: 150, amount: -300 },
    { description: "", hours: 1, rate: 100, amount: 100 },
    {
      description:
        "Very long description that exceeds the typical length limit for a line item and contains extensive details about the work performed including multiple sub-tasks, cross-references to other items, and detailed technical specifications that would normally be in a separate document but the contractor has chosen to include inline for completeness and to provide full context for the billing entry which makes reconciliation more challenging",
      hours: 8,
      rate: 175,
      amount: 1400,
    },
  ];
}

function generateUnicodeRows(): Array<{
  description: string;
  hours: number;
  rate: number;
  amount: number;
}> {
  return [
    {
      description: "R\u00e9factoring du module d\u2019authentification",
      hours: 4,
      rate: 150,
      amount: 600,
    },
    {
      description: "Korrektur der Datenbankabfragen f\u00fcr B\u00f6rsen-API",
      hours: 3,
      rate: 125,
      amount: 375,
    },
    {
      description: "\u30C7\u30FC\u30BF\u30D9\u30FC\u30B9\u6700\u9069\u5316 - UI navigation menu update",
      hours: 6,
      rate: 175,
      amount: 1050,
    },
  ];
}

export function generateCsvFixture(config: CsvFixtureConfig): CsvFixtureResult {
  const headers = COLUMN_VARIANTS[config.columnVariant];
  const rows: Array<Record<string, string | number>> = [];
  const lineItems: ParsedLineItem[] = [];

  let lineNumber = 1;

  // Generate standard rows
  const standardCount = config.includeEdgeCases
    ? Math.max(1, config.rowCount - 7)
    : config.rowCount;

  for (let i = 0; i < standardCount; i++) {
    const row = generateStandardRow();
    rows.push({
      [headers.description]: row.description,
      [headers.hours]: row.hours,
      [headers.rate]: row.rate,
      [headers.amount]: row.amount,
    });
    lineItems.push({
      lineNumber,
      description: row.description.trim(),
      hours: row.hours,
      rate: row.rate,
      amount: row.amount,
      category: inferCategory(row.description),
    });
    lineNumber++;
  }

  // Add edge case rows
  if (config.includeEdgeCases) {
    for (const row of generateEdgeCaseRows()) {
      rows.push({
        [headers.description]: row.description,
        [headers.hours]: row.hours,
        [headers.rate]: row.rate,
        [headers.amount]: row.amount,
      });
      lineItems.push({
        lineNumber,
        description: row.description.trim(),
        hours: row.hours !== 0 ? row.hours : 0,
        rate: row.rate,
        amount: row.amount,
        category: inferCategory(row.description),
      });
      lineNumber++;
    }
  }

  // Add unicode rows
  if (config.includeUnicode) {
    for (const row of generateUnicodeRows()) {
      rows.push({
        [headers.description]: row.description,
        [headers.hours]: row.hours,
        [headers.rate]: row.rate,
        [headers.amount]: row.amount,
      });
      lineItems.push({
        lineNumber,
        description: row.description.trim(),
        hours: row.hours,
        rate: row.rate,
        amount: row.amount,
        category: inferCategory(row.description),
      });
      lineNumber++;
    }
  }

  let csv = Papa.unparse(rows);

  // Add BOM prefix if configured
  if (config.includeBom) {
    csv = "\uFEFF" + csv;
  }

  return { csv, lineItems, config };
}

export function generateCsvWithMixedCaseHeaders(): CsvFixtureResult {
  const config: CsvFixtureConfig = {
    rowCount: 5,
    columnVariant: "standard",
    includeEdgeCases: false,
    includeUnicode: false,
    includeBom: false,
  };

  const rows: Array<Record<string, string | number>> = [];
  const lineItems: ParsedLineItem[] = [];

  const mixedHeaders = {
    description: "dEsCrIpTiOn",
    hours: "HOURS",
    rate: "rate",
    amount: "Amount",
  };

  for (let i = 0; i < 5; i++) {
    const row = generateStandardRow();
    rows.push({
      [mixedHeaders.description]: row.description,
      [mixedHeaders.hours]: row.hours,
      [mixedHeaders.rate]: row.rate,
      [mixedHeaders.amount]: row.amount,
    });
    lineItems.push({
      lineNumber: i + 1,
      description: row.description.trim(),
      hours: row.hours,
      rate: row.rate,
      amount: row.amount,
      category: inferCategory(row.description),
    });
  }

  const csv = Papa.unparse(rows);
  return { csv, lineItems, config };
}

export function generateCsvWithSpecialAmounts(): CsvFixtureResult {
  const config: CsvFixtureConfig = {
    rowCount: 4,
    columnVariant: "standard",
    includeEdgeCases: false,
    includeUnicode: false,
    includeBom: false,
  };

  const specialRows = [
    {
      description: "Feature development - auth module",
      hours: "8",
      rate: "150",
      amount: "$1,200.00",
    },
    {
      description: "Bug fix - payment processing",
      hours: "3.5",
      rate: "$125.00",
      amount: "$437.50",
    },
    {
      description: "Code review - API endpoints",
      hours: "2",
      rate: "175",
      amount: "350.00",
    },
    {
      description: "DevOps - CI pipeline setup",
      hours: "5",
      rate: "$200.00",
      amount: "$1,000.00",
    },
  ];

  const csvLines = [
    "Description,Hours,Rate,Amount",
    ...specialRows.map(
      (r) => `"${r.description}",${r.hours},${r.rate},${r.amount}`,
    ),
  ];

  const lineItems: ParsedLineItem[] = [
    {
      lineNumber: 1,
      description: "Feature development - auth module",
      hours: 8,
      rate: 150,
      amount: 1200,
      category: "development",
    },
    {
      lineNumber: 2,
      description: "Bug fix - payment processing",
      hours: 3.5,
      rate: 125,
      amount: 437.5,
      category: "bugfix",
    },
    {
      lineNumber: 3,
      description: "Code review - API endpoints",
      hours: 2,
      rate: 175,
      amount: 350,
      category: "review",
    },
    {
      lineNumber: 4,
      description: "DevOps - CI pipeline setup",
      hours: 5,
      rate: 200,
      amount: 1000,
      category: "devops",
    },
  ];

  return { csv: csvLines.join("\n"), lineItems, config };
}
