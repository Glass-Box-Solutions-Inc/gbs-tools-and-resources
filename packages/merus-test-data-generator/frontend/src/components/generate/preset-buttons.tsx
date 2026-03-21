"use client";

import { Button } from "@/components/ui/button";
import { STAGE_PRESETS } from "@/lib/api/types";
import { capitalize, cn } from "@/lib/utils";

interface PresetButtonsProps {
  activePreset: string | null;
  onSelect: (presetName: string, distribution: Record<string, number>) => void;
}

const presetDescriptions: Record<string, string> = {
  balanced: "Even distribution across all stages",
  early_stage: "Skewed toward intake and treatment",
  settlement_heavy: "Focused on resolution phases",
  complex_litigation: "Heavy discovery and med-legal",
};

export function PresetButtons({ activePreset, onSelect }: PresetButtonsProps) {
  return (
    <div className="space-y-2">
      <label className="text-sm font-medium text-foreground">
        Quick Presets
      </label>
      <div className="grid grid-cols-2 gap-2">
        {Object.entries(STAGE_PRESETS).map(([name, dist]) => (
          <button
            key={name}
            type="button"
            onClick={() => onSelect(name, dist)}
            className={cn(
              "flex flex-col items-start gap-0.5 rounded-lg border px-3 py-2.5 text-left transition-colors",
              activePreset === name
                ? "border-primary bg-primary/5 ring-1 ring-primary"
                : "border-border hover:border-primary/50 hover:bg-muted/50",
            )}
          >
            <span className="text-sm font-medium text-foreground">
              {capitalize(name)}
            </span>
            <span className="text-xs text-muted-foreground">
              {presetDescriptions[name]}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
