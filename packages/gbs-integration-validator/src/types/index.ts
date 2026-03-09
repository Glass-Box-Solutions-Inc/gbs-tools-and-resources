// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// Shared types for the GBS Integration Validator service.
// All validators, routes, and stores reference these canonical interfaces.

export type SystemName = "github" | "linear" | "n8n" | "gcp" | "stripe" | "kb" | "slack";

export interface ValidationCheck {
  name: string;
  passed: boolean;
  message: string;
  durationMs: number;
  details?: Record<string, unknown>;
}

export interface PermissionResult {
  systemName: SystemName;
  hasAccess: boolean;
  scopes: string[];
  missingScopes: string[];
}

export interface LatencyMetrics {
  p50: number;
  p95: number;
  p99: number;
  samples: number[];
}

export interface SystemValidationResult {
  systemName: SystemName;
  systemLabel: string;
  configured: boolean;
  connectivity: ValidationCheck;
  schema: ValidationCheck[];
  permissions: PermissionResult;
  latency: LatencyMetrics;
  timestamp: string;
}

export interface ValidationRun {
  runId: string;
  startedAt: string;
  completedAt: string | null;
  status: "running" | "completed" | "failed";
  systems: SystemValidationResult[];
  includeRateLimitTest: boolean;
}

export interface RunRequest {
  systems?: SystemName[];
  includeRateLimitTest?: boolean;
}
