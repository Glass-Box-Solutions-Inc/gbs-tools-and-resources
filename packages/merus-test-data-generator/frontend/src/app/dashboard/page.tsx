"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import {
  Play,
  FolderOpen,
  FileText,
  Clock,
  AlertTriangle,
  RefreshCw,
  Loader2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { generateCases, listRuns } from "@/lib/api/client";
import type { RunStatus } from "@/lib/api/types";
import { capitalize, formatDate, formatNumber, statusColor, cn } from "@/lib/utils";

export default function DashboardPage() {
  const router = useRouter();
  const [runs, setRuns] = useState<RunStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [quickGenerating, setQuickGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchRuns = useCallback(async () => {
    try {
      setLoading(true);
      const data = await listRuns();
      setRuns(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch runs");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchRuns();
  }, [fetchRuns]);

  async function handleQuickGenerate() {
    try {
      setQuickGenerating(true);
      const result = await generateCases({ count: 20 });
      router.push(`/progress/${result.run_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Generation failed");
      setQuickGenerating(false);
    }
  }

  const totalCases = runs.reduce((sum, r) => sum + r.total_cases, 0);
  const totalDocs = runs.reduce((sum, r) => sum + r.total_docs, 0);

  return (
    <div className="space-y-8">
      {/* Stats row */}
      <div className="grid grid-cols-4 gap-4">
        <Card>
          <CardContent className="p-5">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-50">
                <FolderOpen className="h-5 w-5 text-blue-600" />
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Total Runs</p>
                <p className="text-2xl font-semibold tabular-nums">
                  {runs.length}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-5">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-violet-50">
                <FileText className="h-5 w-5 text-violet-600" />
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Total Cases</p>
                <p className="text-2xl font-semibold tabular-nums">
                  {formatNumber(totalCases)}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-5">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-emerald-50">
                <FileText className="h-5 w-5 text-emerald-600" />
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Total Documents</p>
                <p className="text-2xl font-semibold tabular-nums">
                  {formatNumber(totalDocs)}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-5">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-amber-50">
                <AlertTriangle className="h-5 w-5 text-amber-600" />
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Total Errors</p>
                <p className="text-2xl font-semibold tabular-nums">
                  {runs.reduce((sum, r) => sum + r.errors, 0)}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Quick generate + advanced CTA */}
      <div className="grid grid-cols-2 gap-6">
        <Card className="border-primary/20 bg-gradient-to-br from-primary/5 to-transparent">
          <CardHeader>
            <CardTitle className="text-lg">Quick Generate</CardTitle>
            <CardDescription>
              Generate 20 balanced WC test cases with default settings. Uses the
              balanced preset with a random seed.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button
              size="lg"
              onClick={handleQuickGenerate}
              disabled={quickGenerating}
              className="gap-2"
            >
              {quickGenerating ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Play className="h-4 w-4" />
              )}
              {quickGenerating ? "Starting..." : "Generate 20 Cases"}
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Advanced Generation</CardTitle>
            <CardDescription>
              Customize case count, stage distribution, constraints, and seed
              for reproducible test data.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button
              size="lg"
              variant="outline"
              onClick={() => router.push("/generate")}
              className="gap-2"
            >
              <Play className="h-4 w-4" />
              Configure and Generate
            </Button>
          </CardContent>
        </Card>
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-md bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Recent runs */}
      <Card>
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <div>
            <CardTitle className="text-lg">Recent Runs</CardTitle>
            <CardDescription>
              Previously generated test data runs.
            </CardDescription>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={fetchRuns}
            disabled={loading}
          >
            <RefreshCw
              className={cn("h-4 w-4", loading && "animate-spin")}
            />
          </Button>
        </CardHeader>
        <CardContent>
          {loading && runs.length === 0 ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : runs.length === 0 ? (
            <div className="py-12 text-center">
              <Clock className="mx-auto h-8 w-8 text-muted-foreground" />
              <p className="mt-2 text-sm text-muted-foreground">
                No runs yet. Generate your first batch of test cases.
              </p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Run ID</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Cases</TableHead>
                  <TableHead>Documents</TableHead>
                  <TableHead>Started</TableHead>
                  <TableHead>Errors</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {runs.map((run) => (
                  <TableRow key={run.run_id}>
                    <TableCell className="font-mono text-sm">
                      #{run.run_id}
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant="secondary"
                        className={statusColor(run.status)}
                      >
                        {capitalize(run.status)}
                      </Badge>
                    </TableCell>
                    <TableCell className="tabular-nums">
                      {run.cases_data_generated} / {run.total_cases}
                    </TableCell>
                    <TableCell className="tabular-nums">
                      {run.docs_pdf_generated} / {run.total_docs}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {formatDate(run.started_at)}
                    </TableCell>
                    <TableCell>
                      {run.errors > 0 ? (
                        <span className="font-medium text-red-600">
                          {run.errors}
                        </span>
                      ) : (
                        <span className="text-muted-foreground">0</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => router.push(`/results/${run.run_id}`)}
                      >
                        View
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
