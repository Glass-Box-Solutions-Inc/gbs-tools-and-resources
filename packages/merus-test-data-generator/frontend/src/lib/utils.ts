import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return "--";
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return dateStr;
  }
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
    case "completed":
    case "done":
      return "bg-emerald-100 text-emerald-800";
    case "generating":
    case "running":
    case "in_progress":
      return "bg-blue-100 text-blue-800";
    case "error":
    case "failed":
      return "bg-red-100 text-red-800";
    case "pending":
    case "queued":
      return "bg-amber-100 text-amber-800";
    default:
      return "bg-slate-100 text-slate-800";
  }
}

export function stageColor(stage: string): string {
  switch (stage.toLowerCase()) {
    case "intake":
      return "bg-sky-100 text-sky-800";
    case "active_treatment":
      return "bg-teal-100 text-teal-800";
    case "discovery":
      return "bg-violet-100 text-violet-800";
    case "medical_legal":
      return "bg-amber-100 text-amber-800";
    case "settlement":
      return "bg-orange-100 text-orange-800";
    case "resolved":
      return "bg-emerald-100 text-emerald-800";
    default:
      return "bg-slate-100 text-slate-800";
  }
}
