// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// Generates a structured JSON compliance report from scan results. Includes
// summary statistics with severity counts, per-repo breakdown, per-analyzer
// breakdown, and the full list of findings with metadata.

import type {
  ComplianceFindingInput,
  AnalyzerResult,
  ScanSummary,
  Severity,
} from "../types/index.js";

export interface JsonReport {
  meta: {
    generatedAt: string;
    scanId: string;
    framework: string;
  };
  summary: ScanSummary;
  analyzerResults: Array<{
    analyzerName: string;
    filesScanned: number;
    findingsCount: number;
    durationMs: number;
  }>;
  findingsByRepo: Record<string, ComplianceFindingInput[]>;
  findings: ComplianceFindingInput[];
}

/**
 * Generate a structured JSON report from scan results.
 */
export function generateJsonReport(opts: {
  scanId: string;
  framework: string;
  startedAt: string;
  completedAt: string | null;
  repos: string[];
  findings: ComplianceFindingInput[];
  analyzerResults: AnalyzerResult[];
  totalFilesScanned: number;
}): JsonReport {
  const {
    scanId,
    framework,
    startedAt,
    completedAt,
    repos,
    findings,
    analyzerResults,
    totalFilesScanned,
  } = opts;

  // Severity counts
  const bySeverity: Record<Severity, number> = {
    CRITICAL: 0,
    HIGH: 0,
    MEDIUM: 0,
    LOW: 0,
    INFO: 0,
  };
  for (const f of findings) {
    bySeverity[f.severity as Severity] =
      (bySeverity[f.severity as Severity] ?? 0) + 1;
  }

  // By analyzer
  const byAnalyzer: Record<string, number> = {};
  for (const f of findings) {
    byAnalyzer[f.analyzer] = (byAnalyzer[f.analyzer] ?? 0) + 1;
  }

  // By repo
  const byRepo: Record<string, number> = {};
  for (const f of findings) {
    byRepo[f.repo] = (byRepo[f.repo] ?? 0) + 1;
  }

  // Group findings by repo
  const findingsByRepo: Record<string, ComplianceFindingInput[]> = {};
  for (const f of findings) {
    if (!findingsByRepo[f.repo]) {
      findingsByRepo[f.repo] = [];
    }
    findingsByRepo[f.repo].push(f);
  }

  const summary: ScanSummary = {
    scanId,
    status: completedAt ? "completed" : "running",
    framework,
    startedAt,
    completedAt,
    reposScanned: repos.length,
    filesScanned: totalFilesScanned,
    totalFindings: findings.length,
    bySeverity,
    byAnalyzer,
    byRepo,
  };

  return {
    meta: {
      generatedAt: new Date().toISOString(),
      scanId,
      framework,
    },
    summary,
    analyzerResults: analyzerResults.map((ar) => ({
      analyzerName: ar.analyzerName,
      filesScanned: ar.filesScanned,
      findingsCount: ar.findings.length,
      durationMs: ar.durationMs,
    })),
    findingsByRepo,
    findings,
  };
}
