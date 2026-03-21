"use client";

import { useState, useMemo } from "react";
import { useRouter } from "next/navigation";
import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import {
  Play,
  Loader2,
  Sparkles,
  FileText,
  FolderOpen,
  Hash,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { CaseCountSlider } from "@/components/generate/case-count-slider";
import { StageDistribution } from "@/components/generate/stage-distribution";
import { ConstraintsPanel } from "@/components/generate/constraints-panel";
import { PresetButtons } from "@/components/generate/preset-buttons";
import { generateCases } from "@/lib/api/client";
import {
  STAGE_PRESETS,
  ALL_STAGES,
  type CaseConstraints,
} from "@/lib/api/types";
import { capitalize, formatNumber, cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Form schema
// ---------------------------------------------------------------------------

const generateSchema = z.object({
  count: z.number().min(1).max(500),
  seed: z.number().nullable().optional(),
  stage_distribution: z.record(z.string(), z.number()).nullable().optional(),
  constraints: z
    .object({
      min_surgery_cases: z.number().min(0).optional(),
      min_psych_cases: z.number().min(0).optional(),
      min_lien_cases: z.number().min(0).optional(),
      min_ur_dispute_cases: z.number().min(0).optional(),
      attorney_rate: z.number().min(0).max(1).optional(),
      surgery_rate: z.number().min(0).max(1).optional(),
      psych_rate: z.number().min(0).max(1).optional(),
      ur_dispute_rate: z.number().min(0).max(1).optional(),
      lien_rate: z.number().min(0).max(1).optional(),
      imr_rate: z.number().min(0).max(1).optional(),
    })
    .nullable()
    .optional(),
});

type GenerateForm = z.infer<typeof generateSchema>;

// ---------------------------------------------------------------------------
// Estimation logic
// ---------------------------------------------------------------------------

const STAGE_DOC_RANGES: Record<string, [number, number]> = {
  intake: [18, 28],
  active_treatment: [25, 45],
  discovery: [30, 55],
  medical_legal: [30, 55],
  settlement: [35, 65],
  resolved: [45, 75],
};

function estimateDocs(
  count: number,
  distribution: Record<string, number>,
): { totalDocsLow: number; totalDocsHigh: number; avgDocs: number; stageBreakdown: Record<string, number> } {
  const total = Object.values(distribution).reduce((s, v) => s + v, 0) || 1;
  const normalized = Object.fromEntries(
    Object.entries(distribution).map(([k, v]) => [k, v / total]),
  );

  let totalDocsLow = 0;
  let totalDocsHigh = 0;
  const stageBreakdown: Record<string, number> = {};

  for (const stage of ALL_STAGES) {
    const stageCases = Math.round(count * (normalized[stage] || 0));
    stageBreakdown[stage] = stageCases;
    const [low, high] = STAGE_DOC_RANGES[stage] || [20, 40];
    totalDocsLow += stageCases * low;
    totalDocsHigh += stageCases * high;
  }

  const avgDocs = Math.round((totalDocsLow + totalDocsHigh) / 2);

  return { totalDocsLow, totalDocsHigh, avgDocs, stageBreakdown };
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function GeneratePage() {
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [activePreset, setActivePreset] = useState<string | null>("balanced");

  const { control, handleSubmit, watch, setValue } = useForm<GenerateForm>({
    resolver: zodResolver(generateSchema),
    defaultValues: {
      count: 20,
      seed: null,
      stage_distribution: { ...STAGE_PRESETS.balanced },
      constraints: {
        attorney_rate: 0.7,
        surgery_rate: 0.25,
        psych_rate: 0.15,
        ur_dispute_rate: 0.4,
        lien_rate: 0.3,
        imr_rate: 0.2,
        min_surgery_cases: 0,
        min_psych_cases: 0,
        min_lien_cases: 0,
        min_ur_dispute_cases: 0,
      },
    },
  });

  const watchedCount = watch("count");
  const watchedDistribution = watch("stage_distribution");

  const estimates = useMemo(
    () =>
      estimateDocs(watchedCount, watchedDistribution || STAGE_PRESETS.balanced),
    [watchedCount, watchedDistribution],
  );

  async function onSubmit(data: GenerateForm) {
    try {
      setSubmitting(true);
      setSubmitError(null);
      const result = await generateCases({
        count: data.count,
        seed: data.seed ?? undefined,
        stage_distribution: data.stage_distribution,
        constraints: data.constraints,
      });
      router.push(`/progress/${result.run_id}`);
    } catch (err) {
      setSubmitError(
        err instanceof Error ? err.message : "Generation failed",
      );
      setSubmitting(false);
    }
  }

  function handlePresetSelect(name: string, dist: Record<string, number>) {
    setActivePreset(name);
    setValue("stage_distribution", { ...dist });
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)}>
      <div className="grid grid-cols-3 gap-8">
        {/* Left panel: Configuration */}
        <div className="col-span-2 space-y-6">
          {/* Case count */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Case Count</CardTitle>
              <CardDescription>
                How many Workers' Compensation test cases to generate.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Controller
                control={control}
                name="count"
                render={({ field }) => (
                  <CaseCountSlider
                    value={field.value}
                    onChange={field.onChange}
                  />
                )}
              />
            </CardContent>
          </Card>

          {/* Presets */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Stage Distribution</CardTitle>
              <CardDescription>
                Control how cases are distributed across litigation stages.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <PresetButtons
                activePreset={activePreset}
                onSelect={handlePresetSelect}
              />
              <Controller
                control={control}
                name="stage_distribution"
                render={({ field }) => (
                  <StageDistribution
                    distribution={field.value || STAGE_PRESETS.balanced}
                    onChange={(dist) => {
                      setActivePreset(null);
                      field.onChange(dist);
                    }}
                  />
                )}
              />
            </CardContent>
          </Card>

          {/* Advanced constraints */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Constraints</CardTitle>
              <CardDescription>
                Fine-tune rate targets and minimum counts for specific case
                features.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <Controller
                control={control}
                name="constraints"
                render={({ field }) => (
                  <ConstraintsPanel
                    constraints={field.value || {}}
                    onChange={field.onChange}
                  />
                )}
              />

              {/* Seed */}
              <div className="space-y-2">
                <label className="text-sm font-medium text-foreground">
                  Random Seed (optional)
                </label>
                <p className="text-xs text-muted-foreground">
                  Set a seed for reproducible generation. Leave empty for random.
                </p>
                <Controller
                  control={control}
                  name="seed"
                  render={({ field }) => (
                    <Input
                      type="number"
                      placeholder="e.g. 42"
                      value={field.value ?? ""}
                      onChange={(e) => {
                        const val = e.target.value;
                        field.onChange(val === "" ? null : parseInt(val, 10));
                      }}
                      className="w-40"
                    />
                  )}
                />
              </div>
            </CardContent>
          </Card>

          {/* Submit error */}
          {submitError && (
            <div className="rounded-md bg-red-50 px-4 py-3 text-sm text-red-700">
              {submitError}
            </div>
          )}

          {/* Generate button */}
          <Button
            type="submit"
            size="lg"
            disabled={submitting}
            className="w-full gap-2 text-base"
          >
            {submitting ? (
              <Loader2 className="h-5 w-5 animate-spin" />
            ) : (
              <Play className="h-5 w-5" />
            )}
            {submitting
              ? "Starting Generation..."
              : `Generate ${formatNumber(watchedCount)} Cases`}
          </Button>
        </div>

        {/* Right panel: Estimated stats */}
        <div className="space-y-6">
          <Card className="sticky top-8">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Sparkles className="h-4 w-4 text-primary" />
                Estimated Output
              </CardTitle>
              <CardDescription>
                Preview of what will be generated based on your settings.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">
              {/* Case count */}
              <div className="flex items-center gap-3 rounded-lg bg-muted/50 px-4 py-3">
                <FolderOpen className="h-5 w-5 text-blue-600" />
                <div>
                  <p className="text-sm font-medium">
                    {formatNumber(watchedCount)} Cases
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Test cases to generate
                  </p>
                </div>
              </div>

              {/* Doc estimate */}
              <div className="flex items-center gap-3 rounded-lg bg-muted/50 px-4 py-3">
                <FileText className="h-5 w-5 text-violet-600" />
                <div>
                  <p className="text-sm font-medium">
                    ~{formatNumber(estimates.avgDocs)} Documents
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Range: {formatNumber(estimates.totalDocsLow)} -{" "}
                    {formatNumber(estimates.totalDocsHigh)}
                  </p>
                </div>
              </div>

              {/* Seed */}
              <div className="flex items-center gap-3 rounded-lg bg-muted/50 px-4 py-3">
                <Hash className="h-5 w-5 text-amber-600" />
                <div>
                  <p className="text-sm font-medium">
                    Seed: {watch("seed") ?? "Random"}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {watch("seed") ? "Reproducible" : "Non-deterministic"}
                  </p>
                </div>
              </div>

              {/* Stage breakdown */}
              <div className="space-y-2">
                <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Cases per Stage
                </p>
                {ALL_STAGES.map((stage) => (
                  <div
                    key={stage}
                    className="flex items-center justify-between text-sm"
                  >
                    <span className="text-muted-foreground">
                      {capitalize(stage)}
                    </span>
                    <span className="font-medium tabular-nums">
                      {estimates.stageBreakdown[stage] ?? 0}
                    </span>
                  </div>
                ))}
              </div>

              {/* Preset label */}
              {activePreset && (
                <div className="rounded-md bg-primary/5 px-3 py-2 text-center text-xs font-medium text-primary">
                  Using {capitalize(activePreset)} preset
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </form>
  );
}
