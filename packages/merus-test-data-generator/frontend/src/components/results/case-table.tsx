"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowUpDown, ExternalLink } from "lucide-react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { CasePreview } from "@/lib/api/types";
import { capitalize, stageColor, statusColor } from "@/lib/utils";

interface CaseTableProps {
  cases: CasePreview[];
  runId: number;
}

type SortField = "case_number" | "applicant_name" | "litigation_stage" | "total_docs";
type SortDir = "asc" | "desc";

export function CaseTable({ cases, runId }: CaseTableProps) {
  const [sortField, setSortField] = useState<SortField>("case_number");
  const [sortDir, setSortDir] = useState<SortDir>("asc");

  function toggleSort(field: SortField) {
    if (sortField === field) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortField(field);
      setSortDir("asc");
    }
  }

  const sorted = [...cases].sort((a, b) => {
    let cmp = 0;
    switch (sortField) {
      case "case_number":
        cmp = a.case_number - b.case_number;
        break;
      case "applicant_name":
        cmp = a.applicant_name.localeCompare(b.applicant_name);
        break;
      case "litigation_stage":
        cmp = a.litigation_stage.localeCompare(b.litigation_stage);
        break;
      case "total_docs":
        cmp = a.total_docs - b.total_docs;
        break;
    }
    return sortDir === "asc" ? cmp : -cmp;
  });

  function SortButton({ field, children }: { field: SortField; children: React.ReactNode }) {
    return (
      <Button
        variant="ghost"
        size="sm"
        onClick={() => toggleSort(field)}
        className="-ml-3 h-8 gap-1 text-xs font-medium"
      >
        {children}
        <ArrowUpDown className="h-3 w-3" />
      </Button>
    );
  }

  return (
    <div className="rounded-lg border border-border bg-white">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>
              <SortButton field="case_number">#</SortButton>
            </TableHead>
            <TableHead>
              <SortButton field="applicant_name">Applicant</SortButton>
            </TableHead>
            <TableHead>Employer</TableHead>
            <TableHead>
              <SortButton field="litigation_stage">Stage</SortButton>
            </TableHead>
            <TableHead>Status</TableHead>
            <TableHead>
              <SortButton field="total_docs">Docs</SortButton>
            </TableHead>
            <TableHead className="w-12" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {sorted.map((c) => (
            <TableRow key={c.internal_id}>
              <TableCell className="font-mono text-sm">
                {c.case_number}
              </TableCell>
              <TableCell className="font-medium">
                {c.applicant_name}
              </TableCell>
              <TableCell className="text-muted-foreground">
                {c.employer_name}
              </TableCell>
              <TableCell>
                <Badge
                  variant="secondary"
                  className={stageColor(c.litigation_stage)}
                >
                  {capitalize(c.litigation_stage)}
                </Badge>
              </TableCell>
              <TableCell>
                <Badge
                  variant="secondary"
                  className={statusColor(c.status)}
                >
                  {capitalize(c.status)}
                </Badge>
              </TableCell>
              <TableCell className="tabular-nums">
                {c.docs_generated} / {c.total_docs}
              </TableCell>
              <TableCell>
                <Link
                  href={`/results/${runId}/cases/${c.internal_id}`}
                  className="text-primary hover:text-primary/80"
                >
                  <ExternalLink className="h-4 w-4" />
                </Link>
              </TableCell>
            </TableRow>
          ))}
          {sorted.length === 0 && (
            <TableRow>
              <TableCell colSpan={7} className="py-8 text-center text-muted-foreground">
                No cases found.
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </div>
  );
}
