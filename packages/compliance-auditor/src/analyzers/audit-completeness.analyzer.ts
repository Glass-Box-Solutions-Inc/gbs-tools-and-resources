// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// Verifies that all CRUD operations are accompanied by audit log calls.
// SOC2 CC7.1 and CC7.2 require that data modification events are logged
// for monitoring and incident detection. This analyzer checks for Prisma
// operations (.create, .update, .delete, .upsert) and direct database
// mutation calls without accompanying audit trail entries nearby.

import { BaseAnalyzer } from "./base.analyzer.js";
import type {
  ScannedFile,
  ComplianceFindingInput,
  Framework,
} from "../types/index.js";

// Prisma mutation operations
const PRISMA_CREATE_PATTERN = /\.\s*create\s*\(\s*\{/;
const PRISMA_UPDATE_PATTERN = /\.\s*update\s*\(\s*\{/;
const PRISMA_DELETE_PATTERN = /\.\s*delete\s*\(\s*\{/;
const PRISMA_UPSERT_PATTERN = /\.\s*upsert\s*\(\s*\{/;
const PRISMA_UPDATE_MANY_PATTERN = /\.\s*updateMany\s*\(\s*\{/;
const PRISMA_DELETE_MANY_PATTERN = /\.\s*deleteMany\s*\(/;
const PRISMA_CREATE_MANY_PATTERN = /\.\s*createMany\s*\(\s*\{/;

// Audit trail indicators (things we expect to see near mutations)
const AUDIT_INDICATORS = [
  /audit/i,
  /\.log\s*\(/,
  /logger\.\w+\s*\(/,
  /createAuditEntry/i,
  /auditLog/i,
  /audit_log/i,
  /trackChange/i,
  /recordAction/i,
  /logActivity/i,
  /activityLog/i,
  /eventLog/i,
  /changelog/i,
];

const CODE_EXTENSIONS = [".ts", ".js", ".tsx", ".jsx"];

// Number of lines above and below a mutation to search for audit calls
const AUDIT_SEARCH_RADIUS = 15;

export class AuditCompletenessAnalyzer extends BaseAnalyzer {
  readonly analyzerName = "audit-completeness";
  readonly analyzerLabel = "CRUD Audit Trail Completeness";
  readonly framework: Framework = "soc2";

  async analyze(files: ScannedFile[]): Promise<ComplianceFindingInput[]> {
    const findings: ComplianceFindingInput[] = [];

    const mutationPatterns: Array<{
      pattern: RegExp;
      operation: string;
    }> = [
      { pattern: PRISMA_CREATE_PATTERN, operation: "create" },
      { pattern: PRISMA_UPDATE_PATTERN, operation: "update" },
      { pattern: PRISMA_DELETE_PATTERN, operation: "delete" },
      { pattern: PRISMA_UPSERT_PATTERN, operation: "upsert" },
      { pattern: PRISMA_UPDATE_MANY_PATTERN, operation: "updateMany" },
      { pattern: PRISMA_DELETE_MANY_PATTERN, operation: "deleteMany" },
      { pattern: PRISMA_CREATE_MANY_PATTERN, operation: "createMany" },
    ];

    // Filter to production source files, skip tests and migrations
    const productionFiles = files.filter(
      (f) =>
        CODE_EXTENSIONS.includes(f.extension) &&
        !f.filePath.includes("/test") &&
        !f.filePath.includes("/tests/") &&
        !f.filePath.includes("/__tests__/") &&
        !f.filePath.includes(".test.") &&
        !f.filePath.includes(".spec.") &&
        !f.filePath.includes("/migrations/") &&
        !f.filePath.includes("/seed"),
    );

    for (const file of productionFiles) {
      const lines = file.content.split("\n");
      for (let i = 0; i < lines.length; i++) {
        for (const { pattern, operation } of mutationPatterns) {
          const match = lines[i].match(pattern);
          if (!match) continue;

          // Search surrounding lines for audit trail indicators
          const searchStart = Math.max(0, i - AUDIT_SEARCH_RADIUS);
          const searchEnd = Math.min(
            lines.length,
            i + AUDIT_SEARCH_RADIUS,
          );
          const surroundingBlock = lines
            .slice(searchStart, searchEnd)
            .join("\n");

          const hasAuditTrail = AUDIT_INDICATORS.some((indicator) =>
            indicator.test(surroundingBlock),
          );

          if (!hasAuditTrail) {
            const snippetStart = Math.max(0, i - 2);
            const snippetEnd = Math.min(lines.length, i + 3);
            findings.push({
              analyzer: this.analyzerName,
              severity: "MEDIUM",
              framework: "soc2",
              repo: file.repo,
              filePath: file.filePath,
              lineNumber: i + 1,
              title: `Prisma .${operation}() without audit trail`,
              description: `A .${operation}() call in ${file.filePath} at line ${i + 1} does not have a corresponding audit log entry within ${AUDIT_SEARCH_RADIUS} lines. SOC2 CC7.1 requires that all data modification events are logged for accountability and incident investigation.`,
              snippet: lines.slice(snippetStart, snippetEnd).join("\n"),
              remediation: `Add an audit log entry after the .${operation}() call. Use a centralized audit service: await auditLog.record({ action: '${operation}', entity: '<model>', entityId: result.id, userId: ctx.userId, changes: { ... } }).`,
            });
          }
        }
      }
    }

    return findings;
  }
}
