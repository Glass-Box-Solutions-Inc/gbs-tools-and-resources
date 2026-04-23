"use client";

/**
 * Batch Generation page.
 *
 * - Total count slider (1–500)
 * - Scenario distribution table (13 rows, weight per scenario, auto-normalizes)
 * - Submit → POST /api/v1/batch → navigate to /jobs/[id]
 *
 * @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
 */

import { useEffect, useState, useMemo } from "react";
import { useRouter } from "next/navigation";
import { Layers, Loader2, RefreshCw } from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Slider } from "@/components/ui/slider";
import { listScenarios, submitBatch } from "@/lib/api/client";
import type { ScenarioResponse } from "@/lib/api/types";
import { formatNumber } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function normalizeWeights(
  weights: Record<string, number>,
): Record<string, number> {
  const total = Object.values(weights).reduce((s, v) => s + Math.max(0, v), 0);
  if (total === 0) return weights;
  return Object.fromEntries(
    Object.entries(weights).map(([k, v]) => [k, Math.max(0, v) / total]),
  );
}

function buildJobs(
  scenarios: ScenarioResponse[],
  weights: Record<string, number>,
  total: number,
): Array<{ scenario: string; seed: number }> {
  const normalized = normalizeWeights(weights);
  const jobs: Array<{ scenario: string; seed: number }> = [];

  let assigned = 0;
  const counts: Array<{ slug: string; count: number }> = scenarios.map(
    (s, i) => {
      const count =
        i === scenarios.length - 1
          ? total - assigned
          : Math.round(total * (normalized[s.slug] ?? 0));
      assigned += count;
      return { slug: s.slug, count };
    },
  );

  let seed = 1;
  for (const { slug, count } of counts) {
    for (let i = 0; i < count; i++) {
      jobs.push({ scenario: slug, seed: seed++ });
    }
  }

  return jobs;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function BatchPage() {
  const router = useRouter();

  const [scenarios, setScenarios] = useState<ScenarioResponse[]>([]);
  const [loadingScenarios, setLoadingScenarios] = useState(true);
  const [total, setTotal] = useState(50);
  const [weights, setWeights] = useState<Record<string, number>>({});
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load scenarios and initialize equal weights
  useEffect(() => {
    listScenarios()
      .then((list) => {
        setScenarios(list);
        const equal = 1 / Math.max(list.length, 1);
        const initial: Record<string, number> = {};
        list.forEach((s) => {
          initial[s.slug] = equal;
        });
        setWeights(initial);
      })
      .catch(() => {/* backend may not be running */})
      .finally(() => setLoadingScenarios(false));
  }, []);

  // Derived: case counts per scenario
  const caseCounts = useMemo(() => {
    if (scenarios.length === 0) return {};
    const normalized = normalizeWeights(weights);
    let assigned = 0;
    const result: Record<string, number> = {};
    scenarios.forEach((s, i) => {
      if (i === scenarios.length - 1) {
        result[s.slug] = total - assigned;
      } else {
        const count = Math.round(total * (normalized[s.slug] ?? 0));
        result[s.slug] = count;
        assigned += count;
      }
    });
    return result;
  }, [scenarios, weights, total]);

  function setWeight(slug: string, value: number) {
    setWeights((prev) => ({ ...prev, [slug]: Math.max(0, value) }));
  }

  function resetEqual() {
    if (scenarios.length === 0) return;
    const equal = 1 / scenarios.length;
    const reset: Record<string, number> = {};
    scenarios.forEach((s) => { reset[s.slug] = equal; });
    setWeights(reset);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (scenarios.length === 0) {
      setError("No scenarios loaded. Is the backend running?");
      return;
    }
    try {
      setSubmitting(true);
      setError(null);

      const jobs = buildJobs(scenarios, weights, total);
      const result = await submitBatch({ jobs, generate_pdfs: true });
      router.push(`/jobs/${encodeURIComponent(result.job_id)}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Batch submission failed");
      setSubmitting(false);
    }
  }

  // Percentage display (0–100) for the weight input
  function weightPct(slug: string): string {
    const normalized = normalizeWeights(weights);
    return (((normalized[slug] ?? 0) * 100)).toFixed(1);
  }

  return (
    <form onSubmit={handleSubmit} className="mx-auto max-w-2xl space-y-6">
      {/* Total count */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Total Cases</CardTitle>
          <CardDescription>
            How many cases to generate across all scenarios (1–500).
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center gap-6">
            <Slider
              min={1}
              max={500}
              step={1}
              value={[total]}
              onValueChange={([v]) => setTotal(v)}
              className="flex-1"
            />
            <span className="w-16 text-right text-sm font-medium tabular-nums">
              {formatNumber(total)}
            </span>
          </div>
        </CardContent>
      </Card>

      {/* Scenario distribution */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-base">Scenario Distribution</CardTitle>
              <CardDescription>
                Set a relative weight for each scenario. Weights are
                auto-normalized to 100%.
              </CardDescription>
            </div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="gap-1.5"
              onClick={resetEqual}
            >
              <RefreshCw className="h-3.5 w-3.5" />
              Equal
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {loadingScenarios ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading scenarios…
            </div>
          ) : (
            <div className="overflow-hidden rounded-md border border-border">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-muted/50">
                    <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                      Scenario
                    </th>
                    <th className="px-4 py-2.5 text-right text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                      Weight
                    </th>
                    <th className="px-4 py-2.5 text-right text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                      %
                    </th>
                    <th className="px-4 py-2.5 text-right text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                      Cases
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {scenarios.map((s, i) => (
                    <tr
                      key={s.slug}
                      className={
                        i % 2 === 0 ? "bg-background" : "bg-muted/20"
                      }
                    >
                      <td className="px-4 py-2 font-medium">
                        {s.display_name}
                      </td>
                      <td className="px-4 py-2">
                        <div className="flex justify-end">
                          <Input
                            type="number"
                            min={0}
                            step={0.1}
                            value={
                              weights[s.slug] !== undefined
                                ? Number((weights[s.slug] * 100).toFixed(1))
                                : 0
                            }
                            onChange={(e) => {
                              const v = parseFloat(e.target.value);
                              setWeight(s.slug, isNaN(v) ? 0 : v / 100);
                            }}
                            className="h-8 w-24 text-right tabular-nums"
                          />
                        </div>
                      </td>
                      <td className="px-4 py-2 text-right text-muted-foreground tabular-nums">
                        {weightPct(s.slug)}%
                      </td>
                      <td className="px-4 py-2 text-right font-medium tabular-nums">
                        {caseCounts[s.slug] ?? 0}
                      </td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="border-t border-border bg-muted/50">
                    <td
                      colSpan={3}
                      className="px-4 py-2.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground"
                    >
                      Total
                    </td>
                    <td className="px-4 py-2.5 text-right font-bold tabular-nums">
                      {formatNumber(total)}
                    </td>
                  </tr>
                </tfoot>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Error */}
      {error && (
        <div className="rounded-md bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Submit */}
      <Button
        type="submit"
        size="lg"
        disabled={submitting || scenarios.length === 0}
        className="w-full gap-2 text-base"
      >
        {submitting ? (
          <Loader2 className="h-5 w-5 animate-spin" />
        ) : (
          <Layers className="h-5 w-5" />
        )}
        {submitting
          ? "Submitting Batch…"
          : `Generate ${formatNumber(total)} Cases`}
      </Button>
    </form>
  );
}
