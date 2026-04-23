"use client";

import { usePathname } from "next/navigation";

const routeTitles: Record<string, string> = {
  "/": "Scenario Selector",
  "/generate": "Generate Case",
  "/batch": "Batch Generation",
};

function getTitle(pathname: string): string {
  if (routeTitles[pathname]) return routeTitles[pathname];
  if (pathname.startsWith("/jobs/")) return "Job Status";
  return "Insurance Claims Case Generator";
}

export function Header() {
  const pathname = usePathname();
  const title = getTitle(pathname);

  return (
    <header className="flex h-16 items-center justify-between border-b border-border bg-white px-8">
      <h1 className="text-lg font-semibold text-foreground">{title}</h1>
      <div className="flex items-center gap-4">
        <span className="text-xs text-muted-foreground">
          Synthetic data only — no PHI/PII
        </span>
      </div>
    </header>
  );
}
