"use client";

import { Slider } from "@/components/ui/slider";
import { ALL_STAGES, type Stage } from "@/lib/api/types";
import { capitalize, cn } from "@/lib/utils";

interface StageDistributionProps {
  distribution: Record<string, number>;
  onChange: (distribution: Record<string, number>) => void;
}

const stageBarColors: Record<string, string> = {
  intake: "bg-sky-500",
  active_treatment: "bg-teal-500",
  discovery: "bg-violet-500",
  medical_legal: "bg-amber-500",
  settlement: "bg-orange-500",
  resolved: "bg-emerald-500",
};

export function StageDistribution({
  distribution,
  onChange,
}: StageDistributionProps) {
  const total = Object.values(distribution).reduce((s, v) => s + v, 0);

  function handleSliderChange(stage: Stage, newVal: number) {
    const updated = { ...distribution, [stage]: newVal / 100 };
    onChange(updated);
  }

  return (
    <div className="space-y-4">
      <label className="text-sm font-medium text-foreground">
        Stage Distribution
      </label>

      {/* Visual bar */}
      <div className="flex h-3 w-full overflow-hidden rounded-full bg-secondary">
        {ALL_STAGES.map((stage) => {
          const pct = total > 0 ? ((distribution[stage] || 0) / total) * 100 : 0;
          return (
            <div
              key={stage}
              className={cn("transition-all", stageBarColors[stage])}
              style={{ width: `${pct}%` }}
              title={`${capitalize(stage)}: ${pct.toFixed(0)}%`}
            />
          );
        })}
      </div>

      {/* Individual sliders */}
      <div className="space-y-3">
        {ALL_STAGES.map((stage) => {
          const pct = Math.round((distribution[stage] || 0) * 100);
          return (
            <div key={stage} className="space-y-1">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div
                    className={cn(
                      "h-2.5 w-2.5 rounded-full",
                      stageBarColors[stage],
                    )}
                  />
                  <span className="text-xs font-medium text-foreground">
                    {capitalize(stage)}
                  </span>
                </div>
                <span className="text-xs tabular-nums text-muted-foreground">
                  {pct}%
                </span>
              </div>
              <Slider
                min={0}
                max={100}
                step={1}
                value={[pct]}
                onValueChange={([v]) => handleSliderChange(stage, v)}
                className="h-1.5"
              />
            </div>
          );
        })}
      </div>

      {total > 0 && Math.abs(total - 1) > 0.01 && (
        <p className="text-xs text-amber-600">
          Distribution sums to {(total * 100).toFixed(0)}% -- values will be
          normalized automatically.
        </p>
      )}
    </div>
  );
}
