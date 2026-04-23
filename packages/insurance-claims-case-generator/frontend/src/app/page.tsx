"use client";

/**
 * Home / Scenario Selector — 13 scenario cards in a grid.
 * Each card shows name, flag badges, doc count range, and a Generate button.
 *
 * @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
 */

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Play, Loader2, AlertCircle, FileText } from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { listScenarios } from "@/lib/api/client";
import type { ScenarioResponse } from "@/lib/api/types";
import { scenarioFlags } from "@/lib/utils";

// Map flag label → badge variant
function flagVariant(
  flag: string,
): "litigated" | "ct" | "psych" | "ptd" | "denied" | "death" | "expedited" | "flag" {
  switch (flag) {
    case "Litigated":
      return "litigated";
    case "CT":
      return "ct";
    case "Psych":
      return "psych";
    case "PTD":
      return "ptd";
    case "Denied":
      return "denied";
    case "Death":
      return "death";
    case "Expedited":
      return "expedited";
    default:
      return "flag";
  }
}

function ScenarioCard({
  scenario,
  onGenerate,
}: {
  scenario: ScenarioResponse;
  onGenerate: (slug: string) => void;
}) {
  const flags = scenarioFlags(scenario);

  return (
    <Card className="flex flex-col">
      <CardHeader className="pb-3">
        <CardTitle className="text-base">{scenario.display_name}</CardTitle>
        <CardDescription className="line-clamp-2 text-xs">
          {scenario.description}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col justify-between gap-4">
        {/* Flag badges */}
        <div className="flex min-h-6 flex-wrap gap-1.5">
          {flags.length > 0 ? (
            flags.map((f) => (
              <Badge key={f} variant={flagVariant(f)}>
                {f}
              </Badge>
            ))
          ) : (
            <Badge variant="secondary">Standard</Badge>
          )}
        </div>

        {/* Doc count range */}
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <FileText className="h-3.5 w-3.5 shrink-0" />
          <span>
            {scenario.expected_doc_min}–{scenario.expected_doc_max} documents
          </span>
        </div>

        {/* Generate button */}
        <Button
          size="sm"
          className="w-full gap-2"
          onClick={() => onGenerate(scenario.slug)}
        >
          <Play className="h-3.5 w-3.5" />
          Generate
        </Button>
      </CardContent>
    </Card>
  );
}

export default function ScenariosPage() {
  const router = useRouter();
  const [scenarios, setScenarios] = useState<ScenarioResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listScenarios()
      .then(setScenarios)
      .catch((err: unknown) => {
        setError(
          err instanceof Error
            ? err.message
            : "Failed to load scenarios from backend",
        );
      })
      .finally(() => setLoading(false));
  }, []);

  function handleGenerate(slug: string) {
    router.push(`/generate?scenario=${encodeURIComponent(slug)}`);
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center gap-3 py-24 text-center">
        <AlertCircle className="h-8 w-8 text-destructive" />
        <p className="text-sm font-medium text-destructive">
          Backend unavailable
        </p>
        <p className="max-w-sm text-xs text-muted-foreground">{error}</p>
        <p className="text-xs text-muted-foreground">
          Start the FastAPI server at{" "}
          <code className="rounded bg-muted px-1 py-0.5">
            {process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8001"}
          </code>
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-sm font-semibold text-muted-foreground">
          {scenarios.length} scenarios available
        </h2>
        <p className="mt-1 text-xs text-muted-foreground">
          Select a scenario to pre-populate the generate form, or go to{" "}
          <button
            className="text-primary underline-offset-2 hover:underline"
            onClick={() => router.push("/generate")}
          >
            Generate
          </button>{" "}
          to choose manually.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {scenarios.map((s) => (
          <ScenarioCard key={s.slug} scenario={s} onGenerate={handleGenerate} />
        ))}
      </div>
    </div>
  );
}
