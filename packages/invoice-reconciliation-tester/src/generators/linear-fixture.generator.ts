// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// Generates synthetic Linear issues that correspond to invoice line items.
// Creates both known-good matches (titles matching invoice descriptions) and
// known-bad matches (intentional non-matches) to test reconciliation accuracy.

import { faker } from "@faker-js/faker";
import type { LinearFixture, ParsedLineItem } from "../types/index.js";

const STATES = ["Done", "In Progress", "Backlog", "Cancelled", "Triage"];
const ASSIGNEES = [
  "pioneer-dev-alex",
  "pioneer-dev-jordan",
  "pioneer-dev-casey",
  "pioneer-dev-taylor",
  "pioneer-dev-morgan",
];

const UNRELATED_TITLES = [
  "Refactor database connection pooling",
  "Update third-party dependencies to latest versions",
  "Migrate legacy API endpoints to v2",
  "Optimize image processing pipeline",
  "Integrate Sentry error tracking",
  "Set up staging environment infrastructure",
  "Write documentation for internal API",
  "Investigate memory leak in worker process",
  "Add rate limiting to public endpoints",
  "Create admin dashboard for analytics",
  "Implement SSO with Azure AD",
  "Design new onboarding flow wireframes",
  "Audit security headers configuration",
  "Set up automated database backups",
  "Performance optimization for search queries",
];

let issueCounter = 100;

function generateIssueId(): string {
  return faker.string.uuid();
}

function generateIdentifier(): string {
  issueCounter++;
  return `GBS-${issueCounter}`;
}

/**
 * Generate Linear issues that are known to match specific invoice line items.
 * The title will closely mirror the invoice description to create ground-truth matches.
 */
export function generateMatchingLinearIssues(
  lineItems: ParsedLineItem[],
): LinearFixture[] {
  return lineItems
    .filter((item) => item.description.length > 0)
    .map((item) => {
      const estimate = item.hours !== null ? Math.round(item.hours) : null;
      return {
        id: generateIssueId(),
        identifier: generateIdentifier(),
        title: item.description,
        description: `Work item corresponding to invoice line ${item.lineNumber}. ${faker.lorem.sentence()}`,
        assignee: faker.helpers.arrayElement(ASSIGNEES),
        state: "Done",
        estimate,
        createdAt: faker.date
          .recent({ days: 30 })
          .toISOString(),
      };
    });
}

/**
 * Generate Linear issues that are deliberately different from any invoice line items.
 * Used to test that the reconciliation algorithm correctly identifies non-matches.
 */
export function generateNonMatchingLinearIssues(count: number): LinearFixture[] {
  const issues: LinearFixture[] = [];

  for (let i = 0; i < count; i++) {
    const title =
      i < UNRELATED_TITLES.length
        ? UNRELATED_TITLES[i]
        : `${faker.hacker.verb()} ${faker.hacker.noun()} ${faker.hacker.ingverb()}`;

    issues.push({
      id: generateIssueId(),
      identifier: generateIdentifier(),
      title,
      description: faker.lorem.paragraph(),
      assignee: faker.helpers.arrayElement(ASSIGNEES),
      state: faker.helpers.arrayElement(STATES),
      estimate: faker.helpers.arrayElement([null, 1, 2, 3, 5, 8, 13]),
      createdAt: faker.date
        .recent({ days: 60 })
        .toISOString(),
    });
  }

  return issues;
}

/**
 * Generate Linear issues with partial keyword overlap to test fuzzy matching.
 * Titles share some keywords with typical invoice descriptions but are not exact matches.
 */
export function generatePartialMatchLinearIssues(): LinearFixture[] {
  const partialMatches = [
    "Authentication module improvements",
    "Dashboard component updates",
    "Payment flow bug investigation",
    "Notification service refactor",
    "Search index optimization",
    "File handling improvements",
    "Report template adjustments",
    "User onboarding flow fixes",
    "API endpoint rate limiter",
    "Webhook processing updates",
  ];

  return partialMatches.map((title) => ({
    id: generateIssueId(),
    identifier: generateIdentifier(),
    title,
    description: faker.lorem.paragraph(),
    assignee: faker.helpers.arrayElement(ASSIGNEES),
    state: "Done",
    estimate: faker.helpers.arrayElement([2, 4, 6, 8]),
    createdAt: faker.date
      .recent({ days: 14 })
      .toISOString(),
  }));
}

/**
 * Generate a complete Linear fixture set with a mix of matching, partial-matching,
 * and non-matching issues for comprehensive reconciliation testing.
 */
export function generateLinearFixtureSet(
  lineItems: ParsedLineItem[],
  nonMatchCount: number = 15,
): {
  matching: LinearFixture[];
  partial: LinearFixture[];
  nonMatching: LinearFixture[];
  all: LinearFixture[];
} {
  const matching = generateMatchingLinearIssues(lineItems);
  const partial = generatePartialMatchLinearIssues();
  const nonMatching = generateNonMatchingLinearIssues(nonMatchCount);
  const all = [...matching, ...partial, ...nonMatching];

  return { matching, partial, nonMatching, all };
}

export function resetIssueCounter(): void {
  issueCounter = 100;
}
