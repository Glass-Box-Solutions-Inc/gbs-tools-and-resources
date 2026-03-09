// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// Report endpoints — list scans, get scan detail, and generate Markdown
// reports from completed scan data.

import type { FastifyInstance } from "fastify";
import { prisma } from "../lib/db.js";
import { generateJsonReport } from "../reporters/json-reporter.js";
import { generateMarkdownReport } from "../reporters/markdown-reporter.js";
import type { AnalyzerResult, ComplianceFindingInput } from "../types/index.js";

export async function reportRoutes(app: FastifyInstance): Promise<void> {
  /**
   * GET /api/reports — List all completed scans with summaries.
   */
  app.get("/api/reports", async (_request, reply) => {
    const scans = await prisma.complianceScan.findMany({
      orderBy: { startedAt: "desc" },
      select: {
        id: true,
        startedAt: true,
        completedAt: true,
        status: true,
        framework: true,
        repos: true,
        summary: true,
        _count: { select: { findings: true } },
      },
      take: 50,
    });

    const reports = scans.map((scan) => ({
      id: scan.id,
      startedAt: scan.startedAt.toISOString(),
      completedAt: scan.completedAt?.toISOString() ?? null,
      status: scan.status,
      framework: scan.framework,
      reposScanned: (scan.repos as string[]).length,
      totalFindings: scan._count.findings,
      summary: scan.summary,
    }));

    return reply.send({ reports });
  });

  /**
   * GET /api/reports/:id — Full scan detail with all findings.
   */
  app.get<{ Params: { id: string } }>(
    "/api/reports/:id",
    async (request, reply) => {
      const { id } = request.params;

      const scan = await prisma.complianceScan.findUnique({
        where: { id },
        include: { findings: true },
      });

      if (!scan) {
        return reply.code(404).send({ error: "Scan not found" });
      }

      // Rebuild the JSON report from persisted data
      const findings: ComplianceFindingInput[] = scan.findings.map((f) => ({
        analyzer: f.analyzer,
        severity: f.severity as ComplianceFindingInput["severity"],
        framework: f.framework as ComplianceFindingInput["framework"],
        repo: f.repo,
        filePath: f.filePath,
        lineNumber: f.lineNumber ?? undefined,
        title: f.title,
        description: f.description,
        snippet: f.snippet ?? undefined,
        remediation: f.remediation ?? undefined,
      }));

      // Build analyzer result summaries from findings
      const analyzerMap = new Map<string, number>();
      for (const f of findings) {
        analyzerMap.set(f.analyzer, (analyzerMap.get(f.analyzer) ?? 0) + 1);
      }
      const analyzerResults: AnalyzerResult[] = Array.from(
        analyzerMap.entries(),
      ).map(([name, count]) => ({
        analyzerName: name,
        findings: findings.filter((f) => f.analyzer === name),
        filesScanned: 0,
        durationMs: 0,
      }));

      const report = generateJsonReport({
        scanId: scan.id,
        framework: scan.framework,
        startedAt: scan.startedAt.toISOString(),
        completedAt: scan.completedAt?.toISOString() ?? null,
        repos: scan.repos as string[],
        findings,
        analyzerResults,
        totalFilesScanned:
          (scan.summary as Record<string, unknown>)?.filesScanned as number ?? 0,
      });

      return reply.send(report);
    },
  );

  /**
   * GET /api/reports/:id/markdown — Markdown-formatted report for human review.
   */
  app.get<{ Params: { id: string } }>(
    "/api/reports/:id/markdown",
    async (request, reply) => {
      const { id } = request.params;

      const scan = await prisma.complianceScan.findUnique({
        where: { id },
        include: { findings: true },
      });

      if (!scan) {
        return reply.code(404).send({ error: "Scan not found" });
      }

      const findings: ComplianceFindingInput[] = scan.findings.map((f) => ({
        analyzer: f.analyzer,
        severity: f.severity as ComplianceFindingInput["severity"],
        framework: f.framework as ComplianceFindingInput["framework"],
        repo: f.repo,
        filePath: f.filePath,
        lineNumber: f.lineNumber ?? undefined,
        title: f.title,
        description: f.description,
        snippet: f.snippet ?? undefined,
        remediation: f.remediation ?? undefined,
      }));

      const analyzerMap = new Map<string, number>();
      for (const f of findings) {
        analyzerMap.set(f.analyzer, (analyzerMap.get(f.analyzer) ?? 0) + 1);
      }
      const analyzerResults: AnalyzerResult[] = Array.from(
        analyzerMap.entries(),
      ).map(([name]) => ({
        analyzerName: name,
        findings: findings.filter((f) => f.analyzer === name),
        filesScanned: 0,
        durationMs: 0,
      }));

      const markdown = generateMarkdownReport({
        scanId: scan.id,
        framework: scan.framework,
        startedAt: scan.startedAt.toISOString(),
        completedAt: scan.completedAt?.toISOString() ?? null,
        repos: scan.repos as string[],
        findings,
        analyzerResults,
        totalFilesScanned:
          (scan.summary as Record<string, unknown>)?.filesScanned as number ?? 0,
      });

      return reply.header("Content-Type", "text/markdown; charset=utf-8").send(markdown);
    },
  );
}
