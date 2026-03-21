"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, FolderOpen } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { listRuns } from "@/lib/api/client";
import type { RunStatus } from "@/lib/api/types";
import { capitalize, formatDate, formatNumber, statusColor } from "@/lib/utils";

export default function ResultsIndexPage() {
  const router = useRouter();
  const [runs, setRuns] = useState<RunStatus[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetch() {
      try {
        const data = await listRuns();
        setRuns(data);
      } catch {
        // ignore
      } finally {
        setLoading(false);
      }
    }
    fetch();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (runs.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-24">
        <FolderOpen className="h-12 w-12 text-muted-foreground" />
        <p className="mt-4 text-lg font-medium text-foreground">
          No results yet
        </p>
        <p className="mt-1 text-sm text-muted-foreground">
          Generate some test cases to see results here.
        </p>
        <Button
          className="mt-6"
          onClick={() => router.push("/generate")}
        >
          Generate Cases
        </Button>
      </div>
    );
  }

  // If only one run, redirect directly
  if (runs.length === 1) {
    router.replace(`/results/${runs[0].run_id}`);
    return null;
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Select a Run</CardTitle>
        <CardDescription>
          Choose a generation run to view its results.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Run ID</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Cases</TableHead>
              <TableHead>Documents</TableHead>
              <TableHead>Started</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {runs.map((run) => (
              <TableRow key={run.run_id}>
                <TableCell className="font-mono">#{run.run_id}</TableCell>
                <TableCell>
                  <Badge variant="secondary" className={statusColor(run.status)}>
                    {capitalize(run.status)}
                  </Badge>
                </TableCell>
                <TableCell className="tabular-nums">
                  {formatNumber(run.total_cases)}
                </TableCell>
                <TableCell className="tabular-nums">
                  {formatNumber(run.total_docs)}
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {formatDate(run.started_at)}
                </TableCell>
                <TableCell>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => router.push(`/results/${run.run_id}`)}
                  >
                    View
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
