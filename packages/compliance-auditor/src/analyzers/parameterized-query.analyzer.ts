// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// Detects raw SQL string concatenation patterns that bypass parameterized
// queries. Covers template literals with interpolation inside .query(),
// .execute(), and .raw() calls, as well as string concatenation with SQL
// keywords. These patterns expose the application to SQL injection attacks,
// violating both SOC2 (CC6.1 logical access) and HIPAA (technical safeguards).

import { BaseAnalyzer } from "./base.analyzer.js";
import type {
  ScannedFile,
  ComplianceFindingInput,
  Framework,
} from "../types/index.js";

const CODE_EXTENSIONS = [".ts", ".js", ".tsx", ".jsx"];

// Pattern: .query(`...${expr}...`)
const QUERY_TEMPLATE_PATTERN =
  /\.query\s*\(\s*`[^`]*\$\{/;

// Pattern: .execute(`...${expr}...`)
const EXECUTE_TEMPLATE_PATTERN =
  /\.execute\s*\(\s*`[^`]*\$\{/;

// Pattern: .raw(`...${expr}...`) or $queryRaw`...${expr}...`
const RAW_TEMPLATE_PATTERN =
  /(?:\.raw|queryRaw|executeRaw)\s*\(\s*`[^`]*\$\{/;

// Pattern: string concatenation with SQL keywords
const SQL_CONCAT_PATTERN =
  /(?:SELECT|INSERT|UPDATE|DELETE|DROP|ALTER|CREATE)\s+.*(?:\+\s*\w+|\$\{)/i;

// Pattern: .query("..." + variable + "...")
const QUERY_CONCAT_PATTERN =
  /\.query\s*\(\s*["'][^"']*["']\s*\+/;

// Pattern: .execute("..." + variable + "...")
const EXECUTE_CONCAT_PATTERN =
  /\.execute\s*\(\s*["'][^"']*["']\s*\+/;

export class ParameterizedQueryAnalyzer extends BaseAnalyzer {
  readonly analyzerName = "parameterized-query";
  readonly analyzerLabel = "Parameterized Query Enforcement";
  readonly framework: Framework = "both";

  async analyze(files: ScannedFile[]): Promise<ComplianceFindingInput[]> {
    const findings: ComplianceFindingInput[] = [];

    const patterns: Array<{
      pattern: RegExp;
      label: string;
    }> = [
      {
        pattern: QUERY_TEMPLATE_PATTERN,
        label: ".query() with template literal interpolation",
      },
      {
        pattern: EXECUTE_TEMPLATE_PATTERN,
        label: ".execute() with template literal interpolation",
      },
      {
        pattern: RAW_TEMPLATE_PATTERN,
        label: ".raw() / queryRaw with template literal interpolation",
      },
      {
        pattern: SQL_CONCAT_PATTERN,
        label: "SQL keyword with string concatenation or interpolation",
      },
      {
        pattern: QUERY_CONCAT_PATTERN,
        label: ".query() with string concatenation",
      },
      {
        pattern: EXECUTE_CONCAT_PATTERN,
        label: ".execute() with string concatenation",
      },
    ];

    for (const { pattern, label } of patterns) {
      findings.push(
        ...this.findPattern(files, pattern, {
          severity: "CRITICAL",
          framework: "both",
          title: "Raw SQL concatenation detected",
          descriptionFn: (_match, file) =>
            `${label} found in ${file.filePath}. Raw SQL string construction bypasses parameterized queries and exposes the application to SQL injection attacks.`,
          remediationFn: () =>
            "Use parameterized queries with placeholders ($1, $2) or an ORM's built-in query builder. For Prisma, use Prisma.sql tagged template or the query builder API instead of $queryRawUnsafe.",
          extensions: CODE_EXTENSIONS,
        }),
      );
    }

    return findings;
  }
}
