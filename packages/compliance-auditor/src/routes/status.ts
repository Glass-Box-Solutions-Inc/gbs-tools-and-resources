// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// Status endpoint — returns the most recent scan summary from the database.
// Protected by OIDC in production (Cloud Run handles this at the infra level).

import type { FastifyInstance } from "fastify";
import { prisma } from "../lib/db.js";
import type { ScanSummary, Severity } from "../types/index.js";

export async function statusRoutes(app: FastifyInstance): Promise<void> {
  app.get("/api/status", async (_request, reply) => {
    const latestScan = await prisma.complianceScan.findFirst({
      orderBy: { startedAt: "desc" },
      include: {
        findings: true,
      },
    });

    if (!latestScan) {
      return reply.send({
        message: "No scans recorded yet",
        lastScan: null,
      });
    }

    // Build severity counts
    const bySeverity: Record<Severity, number> = {
      CRITICAL: 0,
      HIGH: 0,
      MEDIUM: 0,
      LOW: 0,
      INFO: 0,
    };
    const byAnalyzer: Record<string, number> = {};
    const byRepo: Record<string, number> = {};

    for (const f of latestScan.findings) {
      bySeverity[f.severity as Severity] =
        (bySeverity[f.severity as Severity] ?? 0) + 1;
      byAnalyzer[f.analyzer] = (byAnalyzer[f.analyzer] ?? 0) + 1;
      byRepo[f.repo] = (byRepo[f.repo] ?? 0) + 1;
    }

    const summary: ScanSummary = {
      scanId: latestScan.id,
      status: latestScan.status,
      framework: latestScan.framework,
      startedAt: latestScan.startedAt.toISOString(),
      completedAt: latestScan.completedAt?.toISOString() ?? null,
      reposScanned: (latestScan.repos as string[]).length,
      filesScanned:
        (latestScan.summary as Record<string, unknown>)?.filesScanned as number ?? 0,
      totalFindings: latestScan.findings.length,
      bySeverity,
      byAnalyzer,
      byRepo,
    };

    return reply.send({ lastScan: summary });
  });
}
