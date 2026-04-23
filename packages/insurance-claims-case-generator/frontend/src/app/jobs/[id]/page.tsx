"use client";

/**
 * Job Status Poller — polls GET /api/v1/jobs/{id} every 2s.
 *
 * Also handles the sync=1 case from the generate endpoint, which is
 * synchronous (no real job to poll) — shows instant "done" result.
 *
 * @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
 */

import { useEffect, useRef, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import {
  CheckCircle2,
  Download,
  Loader2,
  AlertCircle,
  FileText,
} from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { getJobStatus, exportUrl } from "@/lib/api/client";
import type { JobStatusResponse } from "@/lib/api/types";
import { statusColor } from "@/lib/utils";

const POLL_INTERVAL_MS = 2000;

export default function JobStatusPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const router = useRouter();

  const jobId = params.id as string;

  // Sync case (from single-case /generate) — no real job ID to poll
  const isSync = searchParams.get("sync") === "1";
  const syncDocs = searchParams.get("docs");
  const syncZip = searchParams.get("zip");
  const syncScenario = searchParams.get("scenario");

  const [status, setStatus] = useState<JobStatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // For sync single-case results — fake a completed job display
  if (isSync) {
    return (
      <div className="mx-auto max-w-xl space-y-6">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <CheckCircle2 className="h-5 w-5 text-emerald-600" />
              Case Generated
            </CardTitle>
            <CardDescription>
              Single-case generation completed synchronously.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Case ID</span>
                <span className="font-mono text-xs">{jobId}</span>
              </div>
              {syncScenario && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Scenario</span>
                  <span>{syncScenario}</span>
                </div>
              )}
              {syncDocs && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Documents</span>
                  <span className="font-medium">{syncDocs}</span>
                </div>
              )}
              {syncZip && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground">ZIP size</span>
                  <span>
                    {(parseInt(syncZip, 10) / 1024).toFixed(1)} KB
                  </span>
                </div>
              )}
            </div>

            <div className="flex gap-3 pt-2">
              <Button
                className="flex-1 gap-2"
                onClick={() => router.push("/")}
              >
                Back to Scenarios
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  // Async batch job — poll for status
  // eslint-disable-next-line react-hooks/rules-of-hooks
  useEffect(() => {
    async function poll() {
      try {
        const s = await getJobStatus(jobId);
        setStatus(s);

        if (s.status === "done" || s.status === "failed") {
          if (intervalRef.current) {
            clearInterval(intervalRef.current);
            intervalRef.current = null;
          }
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to fetch job status");
        if (intervalRef.current) {
          clearInterval(intervalRef.current);
          intervalRef.current = null;
        }
      }
    }

    poll();
    intervalRef.current = setInterval(poll, POLL_INTERVAL_MS);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);

  if (error) {
    return (
      <div className="mx-auto max-w-xl">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base text-destructive">
              <AlertCircle className="h-5 w-5" />
              Error
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-muted-foreground">{error}</p>
            <Button variant="outline" onClick={() => router.push("/batch")}>
              Back to Batch
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (!status) {
    return (
      <div className="flex items-center justify-center py-24">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  const isDone = status.status === "done";
  const isFailed = status.status === "failed";
  const isRunning = status.status === "running" || status.status === "pending";

  return (
    <div className="mx-auto max-w-xl space-y-6">
      {/* Status header */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-base">Job {jobId.slice(0, 8)}…</CardTitle>
            <span
              className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${statusColor(status.status)}`}
            >
              {status.status.toUpperCase()}
            </span>
          </div>
          <CardDescription>
            {isDone
              ? "Generation complete. Download your ZIP below."
              : isFailed
              ? "Generation failed."
              : "Generating cases — polling every 2s…"}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Progress bar */}
          <div className="space-y-1.5">
            <div className="flex justify-between text-xs text-muted-foreground">
              <span>
                {status.completed} / {status.total} cases
              </span>
              <span>{status.progress}%</span>
            </div>
            <Progress value={isDone ? 100 : status.progress} className="h-3" />
          </div>

          {/* Running indicator */}
          {isRunning && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              Processing…
            </div>
          )}

          {/* Success indicator + doc count */}
          {isDone && (
            <div className="flex items-center gap-2 text-sm text-emerald-700">
              <CheckCircle2 className="h-4 w-4" />
              {status.total} case
              {status.total !== 1 ? "s" : ""} generated successfully
            </div>
          )}

          {/* Doc count summary */}
          {isDone && (
            <div className="flex items-center gap-2 rounded-md bg-muted/50 px-4 py-3 text-sm">
              <FileText className="h-4 w-4 text-violet-600" />
              <span className="text-muted-foreground">
                Total cases: <span className="font-medium text-foreground">{status.total}</span>
              </span>
            </div>
          )}

          {/* Error */}
          {isFailed && status.error && (
            <div className="rounded-md bg-red-50 px-4 py-3 text-sm text-red-700">
              {status.error}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Actions */}
      <div className="flex gap-3">
        {isDone && (
          <a
            href={exportUrl(jobId)}
            download={`batch_${jobId.slice(0, 8)}.zip`}
            className="flex-1"
          >
            <Button className="w-full gap-2">
              <Download className="h-4 w-4" />
              Download ZIP
            </Button>
          </a>
        )}
        <Button
          variant="outline"
          className={isDone ? "" : "flex-1"}
          onClick={() => router.push("/batch")}
        >
          Back to Batch
        </Button>
      </div>
    </div>
  );
}
