"use client";

import { Slider } from "@/components/ui/slider";
import { Input } from "@/components/ui/input";

interface CaseCountSliderProps {
  value: number;
  onChange: (value: number) => void;
}

export function CaseCountSlider({ value, onChange }: CaseCountSliderProps) {
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <label className="text-sm font-medium text-foreground">
          Number of Cases
        </label>
        <Input
          type="number"
          min={1}
          max={500}
          value={value}
          onChange={(e) => {
            const n = parseInt(e.target.value, 10);
            if (!isNaN(n) && n >= 1 && n <= 500) {
              onChange(n);
            }
          }}
          className="h-8 w-20 text-center text-sm"
        />
      </div>
      <Slider
        min={1}
        max={500}
        step={1}
        value={[value]}
        onValueChange={([v]) => onChange(v)}
      />
      <div className="flex justify-between text-xs text-muted-foreground">
        <span>1</span>
        <span>100</span>
        <span>250</span>
        <span>500</span>
      </div>
    </div>
  );
}
