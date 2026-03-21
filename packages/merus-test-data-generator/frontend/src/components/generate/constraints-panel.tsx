"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Slider } from "@/components/ui/slider";
import type { CaseConstraints } from "@/lib/api/types";
import { cn } from "@/lib/utils";

interface ConstraintsPanelProps {
  constraints: CaseConstraints;
  onChange: (constraints: CaseConstraints) => void;
}

interface RateFieldProps {
  label: string;
  value: number;
  onChange: (v: number) => void;
}

function RateField({ label, value, onChange }: RateFieldProps) {
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <span className="text-xs text-foreground">{label}</span>
        <span className="text-xs tabular-nums text-muted-foreground">
          {Math.round(value * 100)}%
        </span>
      </div>
      <Slider
        min={0}
        max={100}
        step={5}
        value={[Math.round(value * 100)]}
        onValueChange={([v]) => onChange(v / 100)}
      />
    </div>
  );
}

interface MinFieldProps {
  label: string;
  value: number;
  onChange: (v: number) => void;
}

function MinField({ label, value, onChange }: MinFieldProps) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="text-xs text-foreground">{label}</span>
      <Input
        type="number"
        min={0}
        max={500}
        value={value}
        onChange={(e) => {
          const n = parseInt(e.target.value, 10);
          if (!isNaN(n) && n >= 0) onChange(n);
        }}
        className="h-7 w-16 text-center text-xs"
      />
    </div>
  );
}

export function ConstraintsPanel({
  constraints,
  onChange,
}: ConstraintsPanelProps) {
  const [open, setOpen] = useState(false);

  function update(partial: Partial<CaseConstraints>) {
    onChange({ ...constraints, ...partial });
  }

  return (
    <div className="rounded-md border border-border">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between px-4 py-3 text-left text-sm font-medium text-foreground hover:bg-muted/50"
      >
        <span>Advanced Constraints</span>
        {open ? (
          <ChevronDown className="h-4 w-4 text-muted-foreground" />
        ) : (
          <ChevronRight className="h-4 w-4 text-muted-foreground" />
        )}
      </button>

      <div
        className={cn(
          "overflow-hidden transition-all",
          open ? "max-h-[600px] opacity-100" : "max-h-0 opacity-0",
        )}
      >
        <div className="space-y-6 border-t border-border px-4 py-4">
          {/* Rate targets */}
          <div className="space-y-3">
            <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Rate Targets
            </p>
            <RateField
              label="Attorney Representation"
              value={constraints.attorney_rate ?? 0.7}
              onChange={(v) => update({ attorney_rate: v })}
            />
            <RateField
              label="Surgery Cases"
              value={constraints.surgery_rate ?? 0.25}
              onChange={(v) => update({ surgery_rate: v })}
            />
            <RateField
              label="Psych Component"
              value={constraints.psych_rate ?? 0.15}
              onChange={(v) => update({ psych_rate: v })}
            />
            <RateField
              label="UR Dispute"
              value={constraints.ur_dispute_rate ?? 0.4}
              onChange={(v) => update({ ur_dispute_rate: v })}
            />
            <RateField
              label="Liens"
              value={constraints.lien_rate ?? 0.3}
              onChange={(v) => update({ lien_rate: v })}
            />
            <RateField
              label="IMR Filed"
              value={constraints.imr_rate ?? 0.2}
              onChange={(v) => update({ imr_rate: v })}
            />
          </div>

          {/* Minimums */}
          <div className="space-y-3">
            <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Minimum Counts
            </p>
            <MinField
              label="Min Surgery Cases"
              value={constraints.min_surgery_cases ?? 0}
              onChange={(v) => update({ min_surgery_cases: v })}
            />
            <MinField
              label="Min Psych Cases"
              value={constraints.min_psych_cases ?? 0}
              onChange={(v) => update({ min_psych_cases: v })}
            />
            <MinField
              label="Min Lien Cases"
              value={constraints.min_lien_cases ?? 0}
              onChange={(v) => update({ min_lien_cases: v })}
            />
            <MinField
              label="Min UR Dispute Cases"
              value={constraints.min_ur_dispute_cases ?? 0}
              onChange={(v) => update({ min_ur_dispute_cases: v })}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
