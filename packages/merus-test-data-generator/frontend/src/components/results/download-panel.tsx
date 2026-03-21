"use client";

import { Download, FileArchive } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { downloadRunUrl } from "@/lib/api/client";
import { formatNumber } from "@/lib/utils";

interface DownloadPanelProps {
  runId: number;
  totalCases: number;
  totalDocs: number;
}

export function DownloadPanel({
  runId,
  totalCases,
  totalDocs,
}: DownloadPanelProps) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Download</CardTitle>
        <CardDescription>
          Download all generated PDFs as a ZIP archive.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex items-center gap-3 rounded-md bg-muted/50 px-4 py-3">
          <FileArchive className="h-8 w-8 text-muted-foreground" />
          <div className="flex-1">
            <p className="text-sm font-medium text-foreground">
              Full Run Archive
            </p>
            <p className="text-xs text-muted-foreground">
              {formatNumber(totalCases)} cases, {formatNumber(totalDocs)}{" "}
              documents
            </p>
          </div>
          <Button asChild size="sm">
            <a href={downloadRunUrl(runId)} download>
              <Download className="h-4 w-4" />
              Download ZIP
            </a>
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
