"use client";

import { Check, Loader2, Circle } from "lucide-react";
import { cn } from "@/lib/utils";

export type PhaseStatus = "pending" | "active" | "completed" | "error";

export interface Phase {
  id: string;
  label: string;
  status: PhaseStatus;
}

interface ProgressTimelineProps {
  phases: Phase[];
}

export function ProgressTimeline({ phases }: ProgressTimelineProps) {
  return (
    <div className="flex items-center gap-0">
      {phases.map((phase, idx) => (
        <div key={phase.id} className="flex items-center">
          {/* Step indicator */}
          <div className="flex flex-col items-center gap-1.5">
            <div
              className={cn(
                "flex h-10 w-10 items-center justify-center rounded-full border-2 transition-colors",
                phase.status === "completed" &&
                  "border-emerald-500 bg-emerald-500 text-white",
                phase.status === "active" &&
                  "border-primary bg-primary/10 text-primary",
                phase.status === "pending" &&
                  "border-border bg-background text-muted-foreground",
                phase.status === "error" &&
                  "border-red-500 bg-red-50 text-red-600",
              )}
            >
              {phase.status === "completed" && <Check className="h-5 w-5" />}
              {phase.status === "active" && (
                <Loader2 className="h-5 w-5 animate-spin" />
              )}
              {phase.status === "pending" && (
                <Circle className="h-4 w-4" />
              )}
              {phase.status === "error" && (
                <span className="text-sm font-bold">!</span>
              )}
            </div>
            <span
              className={cn(
                "text-xs font-medium",
                phase.status === "active"
                  ? "text-primary"
                  : phase.status === "completed"
                    ? "text-emerald-600"
                    : "text-muted-foreground",
              )}
            >
              {phase.label}
            </span>
          </div>

          {/* Connector line */}
          {idx < phases.length - 1 && (
            <div
              className={cn(
                "mx-2 h-0.5 w-16 transition-colors",
                phase.status === "completed" ? "bg-emerald-500" : "bg-border",
              )}
            />
          )}
        </div>
      ))}
    </div>
  );
}
