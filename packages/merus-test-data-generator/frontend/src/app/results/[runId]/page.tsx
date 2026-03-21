"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { Loader2, Upload, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { CaseTable } from "@/components/results/case-table";
import { DownloadPanel } from "@/components/results/download-panel";
import { getRunStatus, listCases } from "@/lib/api/client";
import type { RunStatus, CasePreview } from "@/lib/api/types";
import {
  capitalize,
  formatDate,
  formatNumber,
  statusColor,
  cn,
} from "@/lib/utils";

export default function RunResultsPage() {
  const params = useParams();
  const router = useRouter();
  const runId = Number(params.runId);

  const [run, setRun] = useState<RunStatus | null>(null);
  const [cases, setCases] = useState<CasePreview[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const [runData, casesData] = await Promise.all([
        getRunStatus(runId),
        listCases(runId),
      ]);
      setRun(runData);
      setCases(casesData);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load data");
    } finally {
      setLoading(false);
    }
  }, [runId]);

  useEffect(() => {
    if (!isNaN(runId)) {
      fetchData();
    }
  }, [runId, fetchData]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-md bg-red-50 px-4 py-3 text-sm text-red-700">
        {error}
      </div>
    );
  }

  if (!run) return null;

  return (
    <div className="space-y-6">
      {/* Run summary header */}
      <Card>
        <CardHeader className="flex-row items-start justify-between space-y-0">
          <div className="space-y-1">
            <div className="flex items-center gap-3">
              <CardTitle className="text-lg">Run #{run.run_id}</CardTitle>
              <Badge variant="secondary" className={statusColor(run.status)}>
                {capitalize(run.status)}
              </Badge>
            </div>
            <CardDescription>
              Started {formatDate(run.started_at)}
              {run.completed_at && ` -- Completed ${formatDate(run.completed_at)}`}
            </CardDescription>
          </div>
          <div className="flex gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={fetchData}
              disabled={loading}
            >
              <RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} />
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => router.push(`/upload/${run.run_id}`)}
              className="gap-2"
            >
              <Upload className="h-4 w-4" />
              Upload to MerusCase
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-5 gap-6">
            <div>
              <p className="text-xs text-muted-foreground">Total Cases</p>
              <p className="text-xl font-semibold tabular-nums">
                {formatNumber(run.total_cases)}
              </p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Total Documents</p>
              <p className="text-xl font-semibold tabular-nums">
                {formatNumber(run.total_docs)}
              </p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Data Generated</p>
              <p className="text-xl font-semibold tabular-nums">
                {formatNumber(run.cases_data_generated)}
              </p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">PDFs Generated</p>
              <p className="text-xl font-semibold tabular-nums">
                {formatNumber(run.docs_pdf_generated)}
              </p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Errors</p>
              <p
                className={cn(
                  "text-xl font-semibold tabular-nums",
                  run.errors > 0 ? "text-red-600" : "text-foreground",
                )}
              >
                {run.errors}
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Download */}
      <DownloadPanel
        runId={run.run_id}
        totalCases={run.total_cases}
        totalDocs={run.total_docs}
      />

      {/* Case table */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-foreground">
            Generated Cases
          </h2>
          <span className="text-sm text-muted-foreground">
            {cases.length} cases
          </span>
        </div>
        <CaseTable cases={cases} runId={runId} />
      </div>
    </div>
  );
}
