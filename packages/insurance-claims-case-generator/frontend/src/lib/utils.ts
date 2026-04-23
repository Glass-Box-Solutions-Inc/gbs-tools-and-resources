import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";
import type { ScenarioResponse } from "@/lib/api/types";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatNumber(n: number): string {
  return new Intl.NumberFormat("en-US").format(n);
}

export function capitalize(s: string): string {
  return s
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

export function statusColor(status: string): string {
  switch (status.toLowerCase()) {
    case "done":
    case "completed":
      return "bg-emerald-100 text-emerald-800";
    case "running":
      return "bg-blue-100 text-blue-800";
    case "failed":
    case "error":
      return "bg-red-100 text-red-800";
    case "pending":
    case "queued":
      return "bg-amber-100 text-amber-800";
    default:
      return "bg-slate-100 text-slate-800";
  }
}

/**
 * Return an array of human-readable flag badge labels for a scenario.
 * Matches the flags exposed by ScenarioResponse.
 */
export function scenarioFlags(s: ScenarioResponse): string[] {
  const flags: string[] = [];
  if (s.litigated) flags.push("Litigated");
  if (s.ct) flags.push("CT");
  if (s.psych_overlay) flags.push("Psych");
  if (s.ptd_claim) flags.push("PTD");
  if (s.denied_scenario) flags.push("Denied");
  if (s.death_claim) flags.push("Death");
  if (s.multi_employer) flags.push("Multi-Employer");
  if (s.split_carrier) flags.push("Split Carrier");
  if (s.high_liens) flags.push("High Liens");
  if (s.sjdb_dispute) flags.push("SJDB");
  if (s.expedited) flags.push("Expedited");
  if (s.investigation_active) flags.push("Investigation");
  return flags;
}
