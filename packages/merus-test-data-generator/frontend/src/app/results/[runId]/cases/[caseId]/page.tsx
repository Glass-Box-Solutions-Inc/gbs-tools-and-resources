"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  Download,
  Loader2,
  FileText,
  User,
  Briefcase,
  Scale,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { DocumentManifest } from "@/components/results/document-manifest";
import { getCaseDetail, downloadCaseUrl } from "@/lib/api/client";
import type { CaseDetail } from "@/lib/api/types";
import { capitalize, stageColor, statusColor, cn } from "@/lib/utils";

export default function CaseDetailPage() {
  const params = useParams();
  const router = useRouter();
  const runId = Number(params.runId);
  const caseId = params.caseId as string;

  const [detail, setDetail] = useState<CaseDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchDetail() {
      try {
        setLoading(true);
        const data = await getCaseDetail(runId, caseId);
        setDetail(data);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load case");
      } finally {
        setLoading(false);
      }
    }
    if (!isNaN(runId) && caseId) {
      fetchDetail();
    }
  }, [runId, caseId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-4">
        <div className="rounded-md bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
        <Button
          variant="outline"
          onClick={() => router.back()}
          className="gap-2"
        >
          <ArrowLeft className="h-4 w-4" />
          Back
        </Button>
      </div>
    );
  }

  if (!detail) return null;

  const c = detail.case;
  const generatedDocs = detail.documents.filter((d) => d.pdf_generated).length;

  return (
    <div className="space-y-6">
      {/* Back navigation */}
      <Button
        variant="ghost"
        size="sm"
        onClick={() => router.push(`/results/${runId}`)}
        className="gap-2"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to Run Results
      </Button>

      {/* Case header */}
      <Card>
        <CardHeader className="flex-row items-start justify-between space-y-0">
          <div className="space-y-2">
            <div className="flex items-center gap-3">
              <CardTitle className="text-lg">
                Case #{c.case_number} -- {c.applicant_name}
              </CardTitle>
              <Badge variant="secondary" className={stageColor(c.litigation_stage)}>
                {capitalize(c.litigation_stage)}
              </Badge>
              <Badge variant="secondary" className={statusColor(c.status)}>
                {capitalize(c.status)}
              </Badge>
            </div>
            <CardDescription className="font-mono text-xs">
              {c.internal_id}
            </CardDescription>
          </div>
          <Button asChild variant="outline" size="sm" className="gap-2">
            <a href={downloadCaseUrl(runId, c.internal_id)} download>
              <Download className="h-4 w-4" />
              Download Case ZIP
            </a>
          </Button>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-4 gap-6">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-50">
                <User className="h-5 w-5 text-blue-600" />
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Applicant</p>
                <p className="text-sm font-medium">{c.applicant_name}</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-violet-50">
                <Briefcase className="h-5 w-5 text-violet-600" />
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Employer</p>
                <p className="text-sm font-medium">{c.employer_name}</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-amber-50">
                <Scale className="h-5 w-5 text-amber-600" />
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Litigation Stage</p>
                <p className="text-sm font-medium">
                  {capitalize(c.litigation_stage)}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-emerald-50">
                <FileText className="h-5 w-5 text-emerald-600" />
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Documents</p>
                <p className="text-sm font-medium">
                  {generatedDocs} / {c.total_docs} generated
                </p>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Document manifest */}
      <DocumentManifest
        documents={detail.documents}
        runId={runId}
        caseId={c.internal_id}
      />
    </div>
  );
}
