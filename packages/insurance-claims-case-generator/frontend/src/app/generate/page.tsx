"use client";

/**
 * Generate form — single case generation.
 *
 * URL param: ?scenario=<slug> (pre-populates the scenario dropdown)
 *
 * @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
 */

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Play, Loader2 } from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { generateCase, listScenarios } from "@/lib/api/client";
import type { ScenarioResponse } from "@/lib/api/types";

interface AdjudiClaimsCredentials {
  env: "local" | "staging";
  baseUrl: string;
  username: string;
  password: string;
}

const ENV_DEFAULTS: Record<"local" | "staging", string> = {
  local: "http://localhost:4900",
  staging: "https://staging.adjudiclaims.com",
};

export default function GeneratePage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const preselect = searchParams.get("scenario") ?? "";

  const [scenarios, setScenarios] = useState<ScenarioResponse[]>([]);
  const [scenario, setScenario] = useState<string>(preselect);
  const [seed, setSeed] = useState<string>("");
  const [generatePdfs, setGeneratePdfs] = useState(true);
  const [adjudiEnabled, setAdjudiEnabled] = useState(false);
  const [adjudiCreds, setAdjudiCreds] = useState<AdjudiClaimsCredentials>({
    env: "local",
    baseUrl: ENV_DEFAULTS.local,
    username: "",
    password: "",
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadingScenarios, setLoadingScenarios] = useState(true);

  useEffect(() => {
    listScenarios()
      .then((list) => {
        setScenarios(list);
        // If preselect param not already valid, default to first
        if (!preselect && list.length > 0) {
          setScenario(list[0].slug);
        }
      })
      .catch(() => {/* backend may not be running — show empty select */})
      .finally(() => setLoadingScenarios(false));
  }, [preselect]);

  // Sync env → baseUrl default
  function handleEnvChange(env: "local" | "staging") {
    setAdjudiCreds((prev) => ({
      ...prev,
      env,
      baseUrl: ENV_DEFAULTS[env],
    }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!scenario) {
      setError("Please select a scenario.");
      return;
    }
    try {
      setSubmitting(true);
      setError(null);

      const seedValue = seed.trim() !== "" ? parseInt(seed, 10) : undefined;

      const result = await generateCase({
        scenario,
        seed: seedValue,
        generate_pdfs: generatePdfs,
      });

      // Navigate to the (single-case) job status page using the case_id
      // The generate endpoint is synchronous — we fake a "done" job URL
      // so the jobs page can show the result.
      router.push(`/jobs/${encodeURIComponent(result.case_id)}?sync=1&docs=${result.document_count}&zip=${result.zip_size_bytes}&scenario=${encodeURIComponent(result.scenario_slug)}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Generation failed");
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="mx-auto max-w-2xl space-y-6">
      {/* Scenario */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Scenario</CardTitle>
          <CardDescription>
            Which claim scenario to generate.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          {loadingScenarios ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading scenarios…
            </div>
          ) : (
            <Select value={scenario} onValueChange={setScenario}>
              <SelectTrigger>
                <SelectValue placeholder="Select a scenario" />
              </SelectTrigger>
              <SelectContent>
                {scenarios.map((s) => (
                  <SelectItem key={s.slug} value={s.slug}>
                    {s.display_name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </CardContent>
      </Card>

      {/* Seed */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Random Seed</CardTitle>
          <CardDescription>
            Optional integer seed for reproducible generation. Leave blank for
            random.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Input
            type="number"
            placeholder="e.g. 42"
            value={seed}
            onChange={(e) => setSeed(e.target.value)}
            className="w-40"
            min={0}
          />
        </CardContent>
      </Card>

      {/* PDF toggle */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">PDF Generation</CardTitle>
          <CardDescription>
            Include PDF documents in the export ZIP. Disable for JSON-only
            (faster).
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-3">
            <Switch
              id="generate-pdfs"
              checked={generatePdfs}
              onCheckedChange={setGeneratePdfs}
            />
            <label
              htmlFor="generate-pdfs"
              className="text-sm text-muted-foreground"
            >
              {generatePdfs ? "PDFs enabled" : "JSON only"}
            </label>
          </div>
        </CardContent>
      </Card>

      {/* AdjudiCLAIMS seed toggle */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Seed AdjudiCLAIMS</CardTitle>
          <CardDescription>
            After generation, upload the case into a running AdjudiCLAIMS
            instance for staging seeding.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center gap-3">
            <Switch
              id="adjudi-seed"
              checked={adjudiEnabled}
              onCheckedChange={setAdjudiEnabled}
            />
            <label
              htmlFor="adjudi-seed"
              className="text-sm text-muted-foreground"
            >
              {adjudiEnabled ? "Seeding enabled" : "Seeding disabled"}
            </label>
          </div>

          {adjudiEnabled && (
            <div className="space-y-4 rounded-md border border-border p-4">
              {/* Env selector */}
              <div className="space-y-1.5">
                <label className="text-xs font-medium">Environment</label>
                <Select
                  value={adjudiCreds.env}
                  onValueChange={(v) =>
                    handleEnvChange(v as "local" | "staging")
                  }
                >
                  <SelectTrigger className="w-48">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="local">Local (localhost:4900)</SelectItem>
                    <SelectItem value="staging">Staging</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Base URL */}
              <div className="space-y-1.5">
                <label className="text-xs font-medium">Base URL</label>
                <Input
                  value={adjudiCreds.baseUrl}
                  onChange={(e) =>
                    setAdjudiCreds((p) => ({ ...p, baseUrl: e.target.value }))
                  }
                  placeholder="http://localhost:4900"
                />
              </div>

              {/* Username */}
              <div className="space-y-1.5">
                <label className="text-xs font-medium">Username</label>
                <Input
                  type="text"
                  autoComplete="off"
                  value={adjudiCreds.username}
                  onChange={(e) =>
                    setAdjudiCreds((p) => ({ ...p, username: e.target.value }))
                  }
                  placeholder="admin@example.com"
                />
              </div>

              {/* Password */}
              <div className="space-y-1.5">
                <label className="text-xs font-medium">Password</label>
                <Input
                  type="password"
                  autoComplete="off"
                  value={adjudiCreds.password}
                  onChange={(e) =>
                    setAdjudiCreds((p) => ({ ...p, password: e.target.value }))
                  }
                  placeholder="••••••••"
                />
              </div>

              <p className="text-xs text-muted-foreground">
                Credentials are sent only to the backend API server — never
                persisted in this browser.
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Error */}
      {error && (
        <div className="rounded-md bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Submit */}
      <Button
        type="submit"
        size="lg"
        disabled={submitting || !scenario}
        className="w-full gap-2 text-base"
      >
        {submitting ? (
          <Loader2 className="h-5 w-5 animate-spin" />
        ) : (
          <Play className="h-5 w-5" />
        )}
        {submitting ? "Generating…" : "Generate Case"}
      </Button>
    </form>
  );
}
