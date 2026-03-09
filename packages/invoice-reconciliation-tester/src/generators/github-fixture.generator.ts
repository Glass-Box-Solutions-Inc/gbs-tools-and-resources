// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// Generates synthetic GitHub PRs that correspond to invoice line items.
// Creates both known-good matches (titles matching invoice descriptions) and
// known-bad matches (intentional non-matches) to test reconciliation accuracy.

import { faker } from "@faker-js/faker";
import type { GitHubFixture, ParsedLineItem } from "../types/index.js";

const PR_AUTHORS = [
  "pioneer-dev-alex",
  "pioneer-dev-jordan",
  "pioneer-dev-casey",
  "pioneer-dev-taylor",
  "pioneer-dev-morgan",
];

const UNRELATED_PR_TITLES = [
  "chore: bump dependencies to latest",
  "ci: fix GitHub Actions workflow",
  "docs: update API reference",
  "refactor: extract shared utilities",
  "chore: configure ESLint flat config",
  "perf: optimize database queries for reports",
  "style: apply Prettier formatting",
  "build: switch to pnpm workspace",
  "chore: update Docker base image",
  "refactor: migrate to Fastify 5",
  "ci: add automated security scanning",
  "docs: add architecture decision records",
  "chore: clean up unused imports",
  "perf: implement Redis caching layer",
  "build: optimize production bundle size",
];

let prCounter = 200;

/**
 * Generate GitHub PRs that are known to match specific invoice line items.
 * The title will closely mirror the invoice description to create ground-truth matches.
 */
export function generateMatchingGitHubPRs(
  lineItems: ParsedLineItem[],
): GitHubFixture[] {
  return lineItems
    .filter((item) => item.description.length > 0)
    .map((item) => {
      prCounter++;
      const additions = faker.number.int({ min: 10, max: 500 });
      const deletions = faker.number.int({ min: 0, max: 200 });

      return {
        number: prCounter,
        title: `feat: ${item.description.toLowerCase()}`,
        body: `## Summary\n\n${item.description}\n\n${faker.lorem.paragraph()}\n\n## Related\n\nInvoice line ${item.lineNumber}`,
        user: faker.helpers.arrayElement(PR_AUTHORS),
        merged: true,
        mergedAt: faker.date.recent({ days: 30 }).toISOString(),
        additions,
        deletions,
        changedFiles: faker.number.int({ min: 1, max: 25 }),
      };
    });
}

/**
 * Generate GitHub PRs that are deliberately different from any invoice line items.
 * Used to test that the reconciliation algorithm correctly identifies non-matches.
 */
export function generateNonMatchingGitHubPRs(count: number): GitHubFixture[] {
  const prs: GitHubFixture[] = [];

  for (let i = 0; i < count; i++) {
    prCounter++;
    const title =
      i < UNRELATED_PR_TITLES.length
        ? UNRELATED_PR_TITLES[i]
        : `${faker.helpers.arrayElement(["feat", "fix", "chore", "refactor"])}: ${faker.hacker.phrase()}`;

    prs.push({
      number: prCounter,
      title,
      body: faker.lorem.paragraphs(2),
      user: faker.helpers.arrayElement(PR_AUTHORS),
      merged: faker.datatype.boolean({ probability: 0.7 }),
      mergedAt: faker.datatype.boolean({ probability: 0.7 })
        ? faker.date.recent({ days: 60 }).toISOString()
        : null,
      additions: faker.number.int({ min: 1, max: 1000 }),
      deletions: faker.number.int({ min: 0, max: 500 }),
      changedFiles: faker.number.int({ min: 1, max: 50 }),
    });
  }

  return prs;
}

/**
 * Generate GitHub PRs with partial keyword overlap to test fuzzy matching.
 * Titles share some keywords with typical invoice descriptions but are not exact matches.
 */
export function generatePartialMatchGitHubPRs(): GitHubFixture[] {
  const partialMatches = [
    "feat: update authentication flow",
    "fix: dashboard rendering performance",
    "feat: payment gateway error handling",
    "fix: notification delivery timing",
    "feat: search results pagination",
    "fix: file upload size validation",
    "feat: report export functionality",
    "fix: user registration edge case",
    "feat: API versioning support",
    "fix: webhook retry logic",
  ];

  return partialMatches.map((title) => {
    prCounter++;
    return {
      number: prCounter,
      title,
      body: faker.lorem.paragraphs(2),
      user: faker.helpers.arrayElement(PR_AUTHORS),
      merged: true,
      mergedAt: faker.date.recent({ days: 14 }).toISOString(),
      additions: faker.number.int({ min: 20, max: 300 }),
      deletions: faker.number.int({ min: 5, max: 150 }),
      changedFiles: faker.number.int({ min: 2, max: 15 }),
    };
  });
}

/**
 * Generate a complete GitHub fixture set with a mix of matching, partial-matching,
 * and non-matching PRs for comprehensive reconciliation testing.
 */
export function generateGitHubFixtureSet(
  lineItems: ParsedLineItem[],
  nonMatchCount: number = 15,
): {
  matching: GitHubFixture[];
  partial: GitHubFixture[];
  nonMatching: GitHubFixture[];
  all: GitHubFixture[];
} {
  const matching = generateMatchingGitHubPRs(lineItems);
  const partial = generatePartialMatchGitHubPRs();
  const nonMatching = generateNonMatchingGitHubPRs(nonMatchCount);
  const all = [...matching, ...partial, ...nonMatching];

  return { matching, partial, nonMatching, all };
}

export function resetPrCounter(): void {
  prCounter = 200;
}
