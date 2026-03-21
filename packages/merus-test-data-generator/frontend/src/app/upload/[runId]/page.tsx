"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  Loader2,
  Upload,
  FileUp,
  AlertCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import {
  getRunStatus,
  createMerusCases,
  uploadMerusDocuments,
  connectSSE,
} from "@/lib/api/client";
import type { RunStatus } from "@/lib/api/types";
import { formatNumber, cn } from "@/lib/utils";

type WizardStep = "review" | "create-cases" | "upload-docs" | "complete";

const STEPS: { id: WizardStep; label: string; description: string }[] = [
  {
    id: "review",
    label: "Review",
    description: "Confirm run data before upload",
  },
  {
    id: "create-cases",
    label: "Create Cases",
    description: "Create cases in MerusCase via browser",
  },
  {
    id: "upload-docs",
    label: "Upload Documents",
    description: "Upload PDFs to MerusCase via API",
  },
  {
    id: "complete",
    label: "Complete",
    description: "Upload finished",
  },
];

export default function UploadPage() {
  const params = useParams();
  const router = useRouter();
  const runId = Number(params.runId);

  const [run, setRun] = useState<RunStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [currentStep, setCurrentStep] = useState<WizardStep>("review");
  const [dryRun, setDryRun] = useState(false);
  const [stepStatus, setStepStatus] = useState<
    Record<string, "idle" | "running" | "done" | "error">
  >({
    "create-cases": "idle",
    "upload-docs": "idle",
  });
  const [stepMessages, setStepMessages] = useState<string[]>([]);
  const [stepProgress, setStepProgress] = useState(0);
  const [stepError, setStepError] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [stepMessages]);

  const fetchRun = useCallback(async () => {
    try {
      setLoading(true);
      const data = await getRunStatus(runId);
      setRun(data);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [runId]);

  useEffect(() => {
    if (!isNaN(runId)) fetchRun();
  }, [runId, fetchRun]);

  function addMessage(msg: string) {
    setStepMessages((prev) => [...prev, msg]);
  }

  async function handleCreateCases() {
    setCurrentStep("create-cases");
    setStepStatus((prev) => ({ ...prev, "create-cases": "running" }));
    setStepMessages([]);
    setStepProgress(0);
    setStepError(null);

    try {
      await createMerusCases(runId, dryRun);
      addMessage(dryRun ? "Dry run started..." : "Creating cases in MerusCase...");

      // Connect to SSE for progress
      const es = connectSSE(`/api/meruscase/status/${runId}`, {
        onPhase: (data) => {
          addMessage(`Phase: ${data.phase} - ${data.status}`);
        },
        onComplete: (data) => {
          addMessage("Case creation complete.");
          setStepStatus((prev) => ({ ...prev, "create-cases": "done" }));
          setStepProgress(100);
          es.close();
        },
        onError: (data) => {
          setStepError((data.message as string) || "Case creation failed");
          setStepStatus((prev) => ({ ...prev, "create-cases": "error" }));
          es.close();
        },
      });
    } catch (err) {
      setStepError(err instanceof Error ? err.message : "Failed");
      setStepStatus((prev) => ({ ...prev, "create-cases": "error" }));
    }
  }

  async function handleUploadDocs() {
    setCurrentStep("upload-docs");
    setStepStatus((prev) => ({ ...prev, "upload-docs": "running" }));
    setStepMessages([]);
    setStepProgress(0);
    setStepError(null);

    try {
      await uploadMerusDocuments(runId);
      addMessage("Uploading documents to MerusCase...");

      const es = connectSSE(`/api/meruscase/status/${runId}`, {
        onPhase: (data) => {
          addMessage(`Phase: ${data.phase} - ${data.status}`);
        },
        onComplete: () => {
          addMessage("Document upload complete.");
          setStepStatus((prev) => ({ ...prev, "upload-docs": "done" }));
          setStepProgress(100);
          setCurrentStep("complete");
          es.close();
        },
        onError: (data) => {
          setStepError((data.message as string) || "Upload failed");
          setStepStatus((prev) => ({ ...prev, "upload-docs": "error" }));
          es.close();
        },
      });
    } catch (err) {
      setStepError(err instanceof Error ? err.message : "Failed");
      setStepStatus((prev) => ({ ...prev, "upload-docs": "error" }));
    }
  }

  function currentStepIndex() {
    return STEPS.findIndex((s) => s.id === currentStep);
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Back */}
      <Button
        variant="ghost"
        size="sm"
        onClick={() => router.push(`/results/${runId}`)}
        className="gap-2"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to Results
      </Button>

      {/* Step indicators */}
      <div className="flex items-center justify-center gap-0">
        {STEPS.map((step, idx) => {
          const isActive = currentStep === step.id;
          const isPast = currentStepIndex() > idx;
          return (
            <div key={step.id} className="flex items-center">
              <div className="flex flex-col items-center gap-1.5">
                <div
                  className={cn(
                    "flex h-10 w-10 items-center justify-center rounded-full border-2 text-sm font-medium transition-colors",
                    isPast && "border-emerald-500 bg-emerald-500 text-white",
                    isActive && "border-primary bg-primary/10 text-primary",
                    !isPast && !isActive && "border-border bg-background text-muted-foreground",
                  )}
                >
                  {isPast ? <Check className="h-5 w-5" /> : idx + 1}
                </div>
                <span
                  className={cn(
                    "text-xs font-medium",
                    isActive
                      ? "text-primary"
                      : isPast
                        ? "text-emerald-600"
                        : "text-muted-foreground",
                  )}
                >
                  {step.label}
                </span>
              </div>
              {idx < STEPS.length - 1 && (
                <div
                  className={cn(
                    "mx-3 h-0.5 w-16 transition-colors",
                    isPast ? "bg-emerald-500" : "bg-border",
                  )}
                />
              )}
            </div>
          );
        })}
      </div>

      {/* Step content */}
      {currentStep === "review" && run && (
        <Card>
          <CardHeader>
            <CardTitle>Review Run Data</CardTitle>
            <CardDescription>
              Confirm the generation run before uploading to MerusCase.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="grid grid-cols-3 gap-6 rounded-lg bg-muted/50 p-6">
              <div>
                <p className="text-xs text-muted-foreground">Run ID</p>
                <p className="text-lg font-semibold">#{run.run_id}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Cases</p>
                <p className="text-lg font-semibold">
                  {formatNumber(run.total_cases)}
                </p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Documents</p>
                <p className="text-lg font-semibold">
                  {formatNumber(run.total_docs)}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-3">
              <input
                type="checkbox"
                id="dry-run"
                checked={dryRun}
                onChange={(e) => setDryRun(e.target.checked)}
                className="h-4 w-4 rounded border-border text-primary focus:ring-primary"
              />
              <label htmlFor="dry-run" className="text-sm text-foreground">
                Dry run (preview without creating actual cases)
              </label>
            </div>

            <div className="flex justify-end">
              <Button onClick={handleCreateCases} className="gap-2">
                Create Cases in MerusCase
                <ArrowRight className="h-4 w-4" />
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {currentStep === "create-cases" && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              {stepStatus["create-cases"] === "running" && (
                <Loader2 className="h-5 w-5 animate-spin text-primary" />
              )}
              {stepStatus["create-cases"] === "done" && (
                <Check className="h-5 w-5 text-emerald-500" />
              )}
              {stepStatus["create-cases"] === "error" && (
                <AlertCircle className="h-5 w-5 text-red-500" />
              )}
              Creating Cases
            </CardTitle>
            <CardDescription>
              {dryRun
                ? "Dry run -- previewing case creation."
                : "Creating cases in MerusCase via browser automation."}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Progress value={stepProgress} />

            <div className="scrollbar-thin h-48 overflow-y-auto rounded-md bg-slate-900 p-4 font-mono text-xs text-slate-200">
              {stepMessages.map((msg, i) => (
                <div key={i}>{msg}</div>
              ))}
              <div ref={messagesEndRef} />
            </div>

            {stepError && (
              <div className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
                {stepError}
              </div>
            )}

            {stepStatus["create-cases"] === "done" && (
              <div className="flex justify-end">
                <Button onClick={handleUploadDocs} className="gap-2">
                  Upload Documents
                  <ArrowRight className="h-4 w-4" />
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {currentStep === "upload-docs" && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              {stepStatus["upload-docs"] === "running" && (
                <Loader2 className="h-5 w-5 animate-spin text-primary" />
              )}
              {stepStatus["upload-docs"] === "done" && (
                <Check className="h-5 w-5 text-emerald-500" />
              )}
              {stepStatus["upload-docs"] === "error" && (
                <AlertCircle className="h-5 w-5 text-red-500" />
              )}
              Uploading Documents
            </CardTitle>
            <CardDescription>
              Uploading generated PDFs to MerusCase via API.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Progress value={stepProgress} />

            <div className="scrollbar-thin h-48 overflow-y-auto rounded-md bg-slate-900 p-4 font-mono text-xs text-slate-200">
              {stepMessages.map((msg, i) => (
                <div key={i}>{msg}</div>
              ))}
              <div ref={messagesEndRef} />
            </div>

            {stepError && (
              <div className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
                {stepError}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {currentStep === "complete" && (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-16">
            <div className="flex h-16 w-16 items-center justify-center rounded-full bg-emerald-100">
              <Check className="h-8 w-8 text-emerald-600" />
            </div>
            <h2 className="mt-4 text-xl font-semibold text-foreground">
              Upload Complete
            </h2>
            <p className="mt-2 text-sm text-muted-foreground">
              All cases and documents have been uploaded to MerusCase.
            </p>
            <div className="mt-6 flex gap-3">
              <Button
                variant="outline"
                onClick={() => router.push(`/results/${runId}`)}
              >
                View Results
              </Button>
              <Button onClick={() => router.push("/dashboard")}>
                Back to Dashboard
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
