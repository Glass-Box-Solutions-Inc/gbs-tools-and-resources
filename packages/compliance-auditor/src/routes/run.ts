// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// Run endpoint — triggers a compliance scan. Returns 202 Accepted immediately
// and runs the scan as a fire-and-forget background task using setImmediate().
// Follows the Squeegee pattern for Cloud Run services that need to respond
// quickly while performing long-running operations.

import type { FastifyInstance } from "fastify";
import { Octokit } from "@octokit/rest";
import { prisma } from "../lib/db.js";
import { env } from "../lib/env.js";
import { scanRepo } from "../scanners/codebase-scanner.js";
import { ParameterizedQueryAnalyzer } from "../analyzers/parameterized-query.analyzer.js";
import { PhiLeakageAnalyzer } from "../analyzers/phi-leakage.analyzer.js";
import { DebugLoggingAnalyzer } from "../analyzers/debug-logging.analyzer.js";
import { FieldEncryptionAnalyzer } from "../analyzers/field-encryption.analyzer.js";
import { ErrorSanitizationAnalyzer } from "../analyzers/error-sanitization.analyzer.js";
import { SslConnectionAnalyzer } from "../analyzers/ssl-connection.analyzer.js";
import { AuditCompletenessAnalyzer } from "../analyzers/audit-completeness.analyzer.js";
import { generateJsonReport } from "../reporters/json-reporter.js";
import type { BaseAnalyzer } from "../analyzers/base.analyzer.js";
import type {
  RunRequest,
  Framework,
  AnalyzerResult,
  ComplianceFindingInput,
} from "../types/index.js";

// Registry of all available analyzers
function getAllAnalyzers(): BaseAnalyzer[] {
  return [
    new ParameterizedQueryAnalyzer(),
    new PhiLeakageAnalyzer(),
    new DebugLoggingAnalyzer(),
    new FieldEncryptionAnalyzer(),
    new ErrorSanitizationAnalyzer(),
    new SslConnectionAnalyzer(),
    new AuditCompletenessAnalyzer(),
  ];
}

/**
 * Filter analyzers by name and framework.
 */
function filterAnalyzers(
  allAnalyzers: BaseAnalyzer[],
  analyzerNames?: string[],
  framework?: Framework,
): BaseAnalyzer[] {
  let filtered = allAnalyzers;

  if (analyzerNames && analyzerNames.length > 0) {
    const nameSet = new Set(analyzerNames);
    filtered = filtered.filter((a) => nameSet.has(a.analyzerName));
  }

  if (framework && framework !== "both") {
    filtered = filtered.filter(
      (a) => a.framework === framework || a.framework === "both",
    );
  }

  return filtered;
}

/**
 * Discover org repos via GitHub API if no specific repos are requested.
 */
async function discoverOrgRepos(): Promise<string[]> {
  const octokit = new Octokit({ auth: env.GITHUB_TOKEN });
  const repos: string[] = [];
  let page = 1;

  while (true) {
    const { data } = await octokit.repos.listForOrg({
      org: env.GITHUB_ORG,
      type: "all",
      per_page: 100,
      page,
    });

    if (data.length === 0) break;

    for (const repo of data) {
      // Skip archived and forked repos
      if (!repo.archived && !repo.fork) {
        repos.push(repo.name);
      }
    }

    if (data.length < 100) break;
    page++;
  }

  return repos;
}

export async function runRoutes(app: FastifyInstance): Promise<void> {
  app.post<{ Body: RunRequest }>("/api/run", async (request, reply) => {
    const body = (request.body ?? {}) as RunRequest;
    const framework: Framework = body.framework ?? "both";

    app.log.info(
      {
        repos: body.repos ?? "all",
        analyzers: body.analyzers ?? "all",
        framework,
      },
      "Compliance scan requested",
    );

    // Create the scan record immediately
    const scan = await prisma.complianceScan.create({
      data: {
        framework,
        repos: body.repos ?? [],
        status: "running",
      },
    });

    // Fire and forget — respond 202 immediately
    setImmediate(() => {
      runScanInBackground(app, scan.id, body).catch((err) => {
        app.log.error(
          { err: (err as Error).message, scanId: scan.id },
          "Background scan failed",
        );
      });
    });

    return reply.code(202).send({
      accepted: true,
      scanId: scan.id,
      message: body.repos
        ? `Queued compliance scan for ${body.repos.length} repo(s)`
        : "Queued compliance scan for all org repos",
    });
  });
}

/**
 * Execute the full compliance scan in the background.
 */
async function runScanInBackground(
  app: FastifyInstance,
  scanId: string,
  request: RunRequest,
): Promise<void> {
  const startTime = performance.now();

  try {
    // Determine repos to scan
    let repos: string[];
    if (request.repos && request.repos.length > 0) {
      repos = request.repos;
    } else {
      app.log.info("Discovering org repos via GitHub API...");
      repos = await discoverOrgRepos();
      app.log.info({ count: repos.length }, "Discovered org repos");
    }

    // Update scan with actual repo list
    await prisma.complianceScan.update({
      where: { id: scanId },
      data: { repos },
    });

    // Prepare analyzers
    const allAnalyzers = getAllAnalyzers();
    const analyzers = filterAnalyzers(
      allAnalyzers,
      request.analyzers,
      request.framework,
    );

    app.log.info(
      {
        repos: repos.length,
        analyzers: analyzers.map((a) => a.analyzerName),
      },
      "Starting compliance scan",
    );

    // Scan each repo sequentially (to avoid overwhelming GitHub API / disk)
    const allFindings: ComplianceFindingInput[] = [];
    const allAnalyzerResults: AnalyzerResult[] = [];
    let totalFilesScanned = 0;

    for (const repo of repos) {
      app.log.info({ repo }, "Scanning repository");
      try {
        const result = await scanRepo(repo, analyzers);
        allFindings.push(...result.findings);
        allAnalyzerResults.push(...result.analyzerResults);
        totalFilesScanned += result.filesScanned;
        app.log.info(
          {
            repo,
            findings: result.findings.length,
            files: result.filesScanned,
          },
          "Repository scan complete",
        );
      } catch (err) {
        app.log.error(
          { repo, err: (err as Error).message },
          "Failed to scan repository",
        );
      }
    }

    // Persist findings to database
    if (allFindings.length > 0) {
      await prisma.complianceFinding.createMany({
        data: allFindings.map((f) => ({
          scanId,
          analyzer: f.analyzer,
          severity: f.severity,
          framework: f.framework,
          repo: f.repo,
          filePath: f.filePath,
          lineNumber: f.lineNumber ?? null,
          title: f.title,
          description: f.description,
          snippet: f.snippet ?? null,
          remediation: f.remediation ?? null,
        })),
      });
    }

    // Generate summary
    const completedAt = new Date().toISOString();
    const scan = await prisma.complianceScan.findUniqueOrThrow({
      where: { id: scanId },
    });

    const jsonReport = generateJsonReport({
      scanId,
      framework: scan.framework,
      startedAt: scan.startedAt.toISOString(),
      completedAt,
      repos,
      findings: allFindings,
      analyzerResults: allAnalyzerResults,
      totalFilesScanned,
    });

    // Update scan as completed
    await prisma.complianceScan.update({
      where: { id: scanId },
      data: {
        status: "completed",
        completedAt: new Date(completedAt),
        summary: JSON.parse(JSON.stringify(jsonReport.summary)),
      },
    });

    const durationMs = Math.round(performance.now() - startTime);
    app.log.info(
      {
        scanId,
        repos: repos.length,
        findings: allFindings.length,
        durationMs,
      },
      "Compliance scan completed",
    );
  } catch (err) {
    app.log.error(
      { scanId, err: (err as Error).message },
      "Compliance scan failed",
    );
    await prisma.complianceScan.update({
      where: { id: scanId },
      data: {
        status: "failed",
        completedAt: new Date(),
        summary: { error: (err as Error).message },
      },
    });
  }
}
