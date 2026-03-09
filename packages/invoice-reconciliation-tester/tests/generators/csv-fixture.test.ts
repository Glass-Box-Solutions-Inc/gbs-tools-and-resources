// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// Unit tests for the CSV fixture generator. Validates that generated CSV
// content and structured line items match expectations for all column
// variants, edge cases, unicode, BOM, mixed-case headers, and special
// amount formatting.

import { describe, it, expect } from "vitest";
import {
  generateCsvFixture,
  generateCsvWithMixedCaseHeaders,
  generateCsvWithSpecialAmounts,
} from "../../src/generators/csv-fixture.generator.js";
import type { CsvFixtureConfig } from "../../src/types/index.js";

describe("CSV Fixture Generator", () => {
  describe("generateCsvFixture", () => {
    it("generates CSV with standard column headers", () => {
      const config: CsvFixtureConfig = {
        rowCount: 5,
        columnVariant: "standard",
        includeEdgeCases: false,
        includeUnicode: false,
        includeBom: false,
      };

      const result = generateCsvFixture(config);

      expect(result.csv).toContain("Description");
      expect(result.csv).toContain("Hours");
      expect(result.csv).toContain("Rate");
      expect(result.csv).toContain("Amount");
      expect(result.lineItems).toHaveLength(5);
    });

    it("generates CSV with abbreviated column headers", () => {
      const config: CsvFixtureConfig = {
        rowCount: 3,
        columnVariant: "abbreviated",
        includeEdgeCases: false,
        includeUnicode: false,
        includeBom: false,
      };

      const result = generateCsvFixture(config);

      expect(result.csv).toContain("Desc");
      expect(result.csv).toContain("Qty");
      expect(result.csv).toContain("Price");
      expect(result.csv).toContain("Total");
      expect(result.lineItems).toHaveLength(3);
    });

    it("generates CSV with custom column headers", () => {
      const config: CsvFixtureConfig = {
        rowCount: 4,
        columnVariant: "custom",
        includeEdgeCases: false,
        includeUnicode: false,
        includeBom: false,
      };

      const result = generateCsvFixture(config);

      expect(result.csv).toContain("Work Description");
      expect(result.csv).toContain("Time");
      expect(result.csv).toContain("Hourly Rate");
      expect(result.csv).toContain("Cost");
      expect(result.lineItems).toHaveLength(4);
    });

    it("includes edge case rows when configured", () => {
      const config: CsvFixtureConfig = {
        rowCount: 10,
        columnVariant: "standard",
        includeEdgeCases: true,
        includeUnicode: false,
        includeBom: false,
      };

      const result = generateCsvFixture(config);

      // Edge cases add 4 rows: zero hours, negative amount, empty description, long description
      const hasZeroHours = result.lineItems.some((item) => item.hours === 0);
      const hasNegativeAmount = result.lineItems.some((item) => item.amount < 0);
      const hasEmptyDescription = result.lineItems.some((item) => item.description === "");

      expect(hasZeroHours).toBe(true);
      expect(hasNegativeAmount).toBe(true);
      expect(hasEmptyDescription).toBe(true);
    });

    it("includes unicode descriptions when configured", () => {
      const config: CsvFixtureConfig = {
        rowCount: 5,
        columnVariant: "standard",
        includeEdgeCases: false,
        includeUnicode: true,
        includeBom: false,
      };

      const result = generateCsvFixture(config);

      const hasUnicode = result.lineItems.some((item) =>
        /[^\x00-\x7F]/.test(item.description),
      );
      expect(hasUnicode).toBe(true);
    });

    it("prepends BOM when configured", () => {
      const config: CsvFixtureConfig = {
        rowCount: 3,
        columnVariant: "standard",
        includeEdgeCases: false,
        includeUnicode: false,
        includeBom: true,
      };

      const result = generateCsvFixture(config);

      expect(result.csv.charCodeAt(0)).toBe(0xfeff);
    });

    it("does not prepend BOM when not configured", () => {
      const config: CsvFixtureConfig = {
        rowCount: 3,
        columnVariant: "standard",
        includeEdgeCases: false,
        includeUnicode: false,
        includeBom: false,
      };

      const result = generateCsvFixture(config);

      expect(result.csv.charCodeAt(0)).not.toBe(0xfeff);
    });

    it("assigns sequential line numbers starting from 1", () => {
      const config: CsvFixtureConfig = {
        rowCount: 5,
        columnVariant: "standard",
        includeEdgeCases: false,
        includeUnicode: false,
        includeBom: false,
      };

      const result = generateCsvFixture(config);

      result.lineItems.forEach((item, index) => {
        expect(item.lineNumber).toBe(index + 1);
      });
    });

    it("computes amount as hours * rate", () => {
      const config: CsvFixtureConfig = {
        rowCount: 10,
        columnVariant: "standard",
        includeEdgeCases: false,
        includeUnicode: false,
        includeBom: false,
      };

      const result = generateCsvFixture(config);

      for (const item of result.lineItems) {
        if (item.hours !== null && item.rate !== null) {
          const expectedAmount = Math.round(item.hours * item.rate * 100) / 100;
          expect(item.amount).toBeCloseTo(expectedAmount, 2);
        }
      }
    });

    it("infers categories from descriptions", () => {
      const config: CsvFixtureConfig = {
        rowCount: 20,
        columnVariant: "standard",
        includeEdgeCases: false,
        includeUnicode: false,
        includeBom: false,
      };

      const result = generateCsvFixture(config);

      const validCategories = new Set([
        "development",
        "bugfix",
        "review",
        "meeting",
        "devops",
        "testing",
        "design",
        null,
      ]);

      for (const item of result.lineItems) {
        expect(validCategories.has(item.category)).toBe(true);
      }
    });

    it("returns matching config in result", () => {
      const config: CsvFixtureConfig = {
        rowCount: 7,
        columnVariant: "abbreviated",
        includeEdgeCases: true,
        includeUnicode: false,
        includeBom: false,
      };

      const result = generateCsvFixture(config);

      expect(result.config).toEqual(config);
    });
  });

  describe("generateCsvWithMixedCaseHeaders", () => {
    it("generates CSV with mixed-case column headers", () => {
      const result = generateCsvWithMixedCaseHeaders();

      expect(result.csv).toContain("dEsCrIpTiOn");
      expect(result.csv).toContain("HOURS");
      expect(result.lineItems).toHaveLength(5);
    });

    it("still produces valid line items", () => {
      const result = generateCsvWithMixedCaseHeaders();

      for (const item of result.lineItems) {
        expect(item.description).toBeTruthy();
        expect(item.lineNumber).toBeGreaterThan(0);
        expect(typeof item.amount).toBe("number");
      }
    });
  });

  describe("generateCsvWithSpecialAmounts", () => {
    it("generates CSV with dollar signs and commas in amounts", () => {
      const result = generateCsvWithSpecialAmounts();

      expect(result.csv).toContain("$1,200.00");
      expect(result.csv).toContain("$437.50");
      expect(result.lineItems).toHaveLength(4);
    });

    it("provides correctly parsed numeric line items", () => {
      const result = generateCsvWithSpecialAmounts();

      expect(result.lineItems[0].amount).toBe(1200);
      expect(result.lineItems[1].amount).toBe(437.5);
      expect(result.lineItems[2].amount).toBe(350);
      expect(result.lineItems[3].amount).toBe(1000);
    });

    it("assigns correct categories", () => {
      const result = generateCsvWithSpecialAmounts();

      expect(result.lineItems[0].category).toBe("development");
      expect(result.lineItems[1].category).toBe("bugfix");
      expect(result.lineItems[2].category).toBe("review");
      expect(result.lineItems[3].category).toBe("devops");
    });
  });
});
