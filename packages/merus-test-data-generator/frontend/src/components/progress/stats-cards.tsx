"use client";

import { FileText, FolderOpen, AlertTriangle, CheckCircle2 } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { formatNumber, cn } from "@/lib/utils";

interface StatsCardsProps {
  casesGenerated: number;
  totalCases: number;
  docsGenerated: number;
  totalDocs: number;
  errors: number;
}

export function StatsCards({
  casesGenerated,
  totalCases,
  docsGenerated,
  totalDocs,
  errors,
}: StatsCardsProps) {
  const stats = [
    {
      label: "Cases",
      value: casesGenerated,
      total: totalCases,
      icon: FolderOpen,
      color: "text-blue-600",
      bg: "bg-blue-50",
    },
    {
      label: "Documents",
      value: docsGenerated,
      total: totalDocs,
      icon: FileText,
      color: "text-violet-600",
      bg: "bg-violet-50",
    },
    {
      label: "Completed",
      value: totalCases > 0 ? Math.round((casesGenerated / totalCases) * 100) : 0,
      total: 100,
      icon: CheckCircle2,
      color: "text-emerald-600",
      bg: "bg-emerald-50",
      suffix: "%",
    },
    {
      label: "Errors",
      value: errors,
      total: null,
      icon: AlertTriangle,
      color: errors > 0 ? "text-red-600" : "text-slate-400",
      bg: errors > 0 ? "bg-red-50" : "bg-slate-50",
    },
  ];

  return (
    <div className="grid grid-cols-4 gap-4">
      {stats.map((stat) => (
        <Card key={stat.label}>
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className={cn("flex h-10 w-10 items-center justify-center rounded-lg", stat.bg)}>
                <stat.icon className={cn("h-5 w-5", stat.color)} />
              </div>
              <div>
                <p className="text-xs text-muted-foreground">{stat.label}</p>
                <p className="text-xl font-semibold tabular-nums text-foreground">
                  {formatNumber(stat.value)}
                  {stat.suffix || ""}
                  {stat.total !== null && !stat.suffix && (
                    <span className="text-sm font-normal text-muted-foreground">
                      {" "}
                      / {formatNumber(stat.total)}
                    </span>
                  )}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
