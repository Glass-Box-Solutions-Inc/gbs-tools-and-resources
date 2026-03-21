"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowRight, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import {
  ProgressTimeline,
  type Phase,
  type PhaseStatus,
} from "@/components/progress/progress-timeline";
import { LiveCaseFeed, type FeedItem } from "@/components/progress/live-case-feed";
import { StatsCards } from "@/components/progress/stats-cards";
import { connectSSE } from "@/lib/api/client";
import { capitalize } from "@/lib/utils";

export default function ProgressPage() {
  const params = useParams();
  const router = useRouter();
  const runId = Number(params.runId);

  const [phases, setPhases] = useState<Phase[]>([
    { id: "data_generation", label: "Data Generation", status: "pending" },
    { id: "pdf_generation", label: "PDF Generation", status: "pending" },
    { id: "complete", label: "Complete", status: "pending" },
  ]);

  const [feedItems, setFeedItems] = useState<FeedItem[]>([]);
  const [casesGenerated, setCasesGenerated] = useState(0);
  const [totalCases, setTotalCases] = useState(0);
  const [docsGenerated, setDocsGenerated] = useState(0);
  const [totalDocs, setTotalDocs] = useState(0);
  const [errors, setErrors] = useState(0);
  const [isComplete, setIsComplete] = useState(false);
  const [hasError, setHasError] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const feedIdRef = useRef(0);
  const esRef = useRef<EventSource | null>(null);

  const addFeedItem = useCallback(
    (type: FeedItem["type"], message: string, stage?: string) => {
      feedIdRef.current += 1;
      setFeedItems((prev) => [
        ...prev,
        {
          id: String(feedIdRef.current),
          type,
          message,
          stage,
          timestamp: new Date(),
        },
      ]);
    },
    [],
  );

  function updatePhase(phaseId: string, status: PhaseStatus) {
    setPhases((prev) =>
      prev.map((p) => (p.id === phaseId ? { ...p, status } : p)),
    );
  }

  useEffect(() => {
    if (isNaN(runId)) return;

    const es = connectSSE(`/api/generate?runId=${runId}`, {
      onPhase: (data) => {
        const phase = data.phase as string;
        const status = data.status as string;
        if (status === "started") {
          updatePhase(phase, "active");
          addFeedItem("phase", `${capitalize(phase)} started`);
          if (data.total_docs) {
            setTotalDocs(data.total_docs as number);
          }
        }
      },
      onCase: (data) => {
        setCasesGenerated((prev) => prev + 1);
        if (data.docs) {
          setTotalDocs((prev) => prev + (data.docs as number));
        }
        const name = data.applicant_name as string;
        const stage = data.stage as string;
        addFeedItem(
          "case",
          `Case generated: ${name} (${data.docs} docs)`,
          stage,
        );
      },
      onDoc: (data) => {
        setDocsGenerated((prev) => prev + 1);
        const filename = data.filename as string;
        addFeedItem("doc", `PDF: ${filename}`);
      },
      onComplete: (data) => {
        setIsComplete(true);
        setCasesGenerated(data.cases as number);
        setDocsGenerated(data.docs_generated as number);
        setErrors(data.errors as number);
        setTotalCases(data.cases as number);
        updatePhase("data_generation", "completed");
        updatePhase("pdf_generation", "completed");
        updatePhase("complete", "completed");
        addFeedItem("phase", "Generation complete");
      },
      onError: (data) => {
        setHasError(true);
        setErrorMessage((data.message as string) || "Unknown error");
        addFeedItem("error", `Error: ${data.message}`);
      },
    });

    esRef.current = es;

    return () => {
      es.close();
    };
  }, [runId, addFeedItem]);

  // Also set totalCases from the initial generate request
  useEffect(() => {
    async function fetchRunInfo() {
      try {
        const res = await fetch(`/api/runs/${runId}`);
        if (res.ok) {
          const data = await res.json();
          setTotalCases(data.total_cases || 0);
          setTotalDocs(data.total_docs || 0);
        }
      } catch {
        // ignore
      }
    }
    if (!isNaN(runId)) {
      fetchRunInfo();
    }
  }, [runId]);

  const progressPct =
    totalCases > 0
      ? Math.min(
          100,
          Math.round(
            ((casesGenerated + docsGenerated) /
              (totalCases + (totalDocs || totalCases * 30))) *
              100,
          ),
        )
      : 0;

  return (
    <div className="space-y-8">
      {/* Timeline */}
      <Card>
        <CardContent className="flex items-center justify-center py-8">
          <ProgressTimeline phases={phases} />
        </CardContent>
      </Card>

      {/* Overall progress bar */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base">Overall Progress</CardTitle>
            <span className="text-sm font-medium tabular-nums text-muted-foreground">
              {progressPct}%
            </span>
          </div>
        </CardHeader>
        <CardContent>
          <Progress value={isComplete ? 100 : progressPct} className="h-3" />
        </CardContent>
      </Card>

      {/* Stats */}
      <StatsCards
        casesGenerated={casesGenerated}
        totalCases={totalCases || casesGenerated}
        docsGenerated={docsGenerated}
        totalDocs={totalDocs || docsGenerated}
        errors={errors}
      />

      {/* Error banner */}
      {hasError && errorMessage && (
        <div className="rounded-md bg-red-50 px-4 py-3 text-sm text-red-700">
          Generation encountered an error: {errorMessage}
        </div>
      )}

      {/* Live feed */}
      <LiveCaseFeed items={feedItems} />

      {/* Navigation */}
      {isComplete && (
        <div className="flex items-center justify-center gap-4">
          <Button
            size="lg"
            onClick={() => router.push(`/results/${runId}`)}
            className="gap-2"
          >
            View Results
            <ArrowRight className="h-4 w-4" />
          </Button>
          <Button
            size="lg"
            variant="outline"
            onClick={() => router.push(`/upload/${runId}`)}
            className="gap-2"
          >
            Upload to MerusCase
            <ArrowRight className="h-4 w-4" />
          </Button>
        </div>
      )}

      {/* Still generating indicator */}
      {!isComplete && !hasError && (
        <div className="flex items-center justify-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Generation in progress...
        </div>
      )}
    </div>
  );
}
