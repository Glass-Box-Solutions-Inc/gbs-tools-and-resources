"use client";

import { usePathname } from "next/navigation";
import { Activity } from "lucide-react";

const routeTitles: Record<string, string> = {
  "/dashboard": "Dashboard",
  "/generate": "Generate Test Cases",
  "/results": "Results",
  "/upload": "MerusCase Upload",
  "/taxonomy": "Document Taxonomy",
};

function getTitle(pathname: string): string {
  // Exact match first
  if (routeTitles[pathname]) return routeTitles[pathname];

  // Check prefix matches
  if (pathname.startsWith("/progress/")) return "Generation Progress";
  if (pathname.startsWith("/results/") && pathname.includes("/cases/"))
    return "Case Detail";
  if (pathname.startsWith("/results/")) return "Run Results";
  if (pathname.startsWith("/upload/")) return "MerusCase Upload";

  return "WC Test Data Generator";
}

export function Header() {
  const pathname = usePathname();
  const title = getTitle(pathname);

  return (
    <header className="flex h-16 items-center justify-between border-b border-border bg-white px-8">
      <h1 className="text-lg font-semibold text-foreground">{title}</h1>
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2 rounded-full bg-emerald-50 px-3 py-1.5">
          <Activity className="h-3.5 w-3.5 text-emerald-600" />
          <span className="text-xs font-medium text-emerald-700">
            Backend Connected
          </span>
        </div>
      </div>
    </header>
  );
}
