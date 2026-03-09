// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// Fixture generation endpoint. Generates synthetic CSV, Linear, and GitHub
// fixtures without running the matching algorithm. Useful for debugging
// and manual inspection of generated test data.

import type { FastifyInstance } from "fastify";
import { generateCsvFixture, generateCsvWithMixedCaseHeaders, generateCsvWithSpecialAmounts } from "../generators/csv-fixture.generator.js";
import { generateLinearFixtureSet, resetIssueCounter } from "../generators/linear-fixture.generator.js";
import { generateGitHubFixtureSet, resetPrCounter } from "../generators/github-fixture.generator.js";
import type { CsvFixtureConfig } from "../types/index.js";

export async function generateRoutes(app: FastifyInstance): Promise<void> {
  app.post("/api/generate", async (request, reply) => {
    const body = (request.body as Partial<CsvFixtureConfig> & { variant?: string }) ?? {};

    // Reset counters for deterministic output
    resetIssueCounter();
    resetPrCounter();

    const config: CsvFixtureConfig = {
      rowCount: body.rowCount ?? 10,
      columnVariant: body.columnVariant ?? "standard",
      includeEdgeCases: body.includeEdgeCases ?? false,
      includeUnicode: body.includeUnicode ?? false,
      includeBom: body.includeBom ?? false,
    };

    // Handle special variants
    if (body.variant === "mixed-case") {
      const csvResult = generateCsvWithMixedCaseHeaders();
      const linearFixtures = generateLinearFixtureSet(csvResult.lineItems, 5);
      const githubFixtures = generateGitHubFixtureSet(csvResult.lineItems, 5);

      return reply.send({
        csv: csvResult.csv,
        lineItems: csvResult.lineItems,
        config: csvResult.config,
        linear: {
          matching: linearFixtures.matching,
          partial: linearFixtures.partial,
          nonMatching: linearFixtures.nonMatching,
          totalCount: linearFixtures.all.length,
        },
        github: {
          matching: githubFixtures.matching,
          partial: githubFixtures.partial,
          nonMatching: githubFixtures.nonMatching,
          totalCount: githubFixtures.all.length,
        },
      });
    }

    if (body.variant === "special-amounts") {
      const csvResult = generateCsvWithSpecialAmounts();
      const linearFixtures = generateLinearFixtureSet(csvResult.lineItems, 5);
      const githubFixtures = generateGitHubFixtureSet(csvResult.lineItems, 5);

      return reply.send({
        csv: csvResult.csv,
        lineItems: csvResult.lineItems,
        config: csvResult.config,
        linear: {
          matching: linearFixtures.matching,
          partial: linearFixtures.partial,
          nonMatching: linearFixtures.nonMatching,
          totalCount: linearFixtures.all.length,
        },
        github: {
          matching: githubFixtures.matching,
          partial: githubFixtures.partial,
          nonMatching: githubFixtures.nonMatching,
          totalCount: githubFixtures.all.length,
        },
      });
    }

    // Standard generation
    const csvResult = generateCsvFixture(config);
    const linearFixtures = generateLinearFixtureSet(csvResult.lineItems, 15);
    const githubFixtures = generateGitHubFixtureSet(csvResult.lineItems, 15);

    return reply.send({
      csv: csvResult.csv,
      lineItems: csvResult.lineItems,
      config: csvResult.config,
      linear: {
        matching: linearFixtures.matching,
        partial: linearFixtures.partial,
        nonMatching: linearFixtures.nonMatching,
        totalCount: linearFixtures.all.length,
      },
      github: {
        matching: githubFixtures.matching,
        partial: githubFixtures.partial,
        nonMatching: githubFixtures.nonMatching,
        totalCount: githubFixtures.all.length,
      },
    });
  });
}
