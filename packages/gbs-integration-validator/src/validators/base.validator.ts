// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// Abstract base class for GBS integration validators. Each validator
// implements connectivity, schema, and permission checks for a specific
// GBS platform API. The base class provides shared latency measurement
// and the composite `validate()` orchestration method.

import type {
  SystemName,
  SystemValidationResult,
  ValidationCheck,
  PermissionResult,
  LatencyMetrics,
} from "../types/index.js";

export abstract class BaseValidator {
  abstract readonly systemName: SystemName;
  abstract readonly systemLabel: string;

  /** Returns true if the required env vars for this system are present. */
  abstract isConfigured(): boolean;

  /** Verify basic connectivity to the API (e.g. a health or auth check). */
  abstract checkConnectivity(): Promise<ValidationCheck>;

  /** Validate the shapes of key API responses using Zod schemas. */
  abstract validateSchemas(): Promise<ValidationCheck[]>;

  /** Check which permissions/scopes the current credentials have. */
  abstract checkPermissions(): Promise<PermissionResult>;

  /**
   * Measure latency by calling `fn` repeatedly and computing percentiles.
   * @param fn - The function to benchmark (typically a lightweight API call).
   * @param samples - Number of iterations (default 5).
   */
  async measureLatency(
    fn: () => Promise<void>,
    samples = 5,
  ): Promise<LatencyMetrics> {
    const times: number[] = [];
    for (let i = 0; i < samples; i++) {
      const start = performance.now();
      await fn();
      times.push(performance.now() - start);
    }
    times.sort((a, b) => a - b);
    return {
      p50: times[Math.floor(times.length * 0.5)] ?? 0,
      p95: times[Math.floor(times.length * 0.95)] ?? 0,
      p99: times[Math.floor(times.length * 0.99)] ?? 0,
      samples: times,
    };
  }

  /**
   * Orchestrate a full validation run for this system.
   * If unconfigured, returns early with a clear "not configured" result.
   * Otherwise runs connectivity -> schema -> permissions -> latency in order.
   */
  async validate(): Promise<SystemValidationResult> {
    const timestamp = new Date().toISOString();

    if (!this.isConfigured()) {
      return {
        systemName: this.systemName,
        systemLabel: this.systemLabel,
        configured: false,
        connectivity: {
          name: "connectivity",
          passed: false,
          message: "Not configured — missing credentials",
          durationMs: 0,
        },
        schema: [],
        permissions: {
          systemName: this.systemName,
          hasAccess: false,
          scopes: [],
          missingScopes: [],
        },
        latency: { p50: 0, p95: 0, p99: 0, samples: [] },
        timestamp,
      };
    }

    const connectivity = await this.checkConnectivity();

    const schema = connectivity.passed ? await this.validateSchemas() : [];

    const permissions = connectivity.passed
      ? await this.checkPermissions()
      : {
          systemName: this.systemName,
          hasAccess: false,
          scopes: [],
          missingScopes: [],
        };

    const latency = connectivity.passed
      ? await this.measureLatency(() =>
          this.checkConnectivity().then(() => {}),
        )
      : { p50: 0, p95: 0, p99: 0, samples: [] };

    return {
      systemName: this.systemName,
      systemLabel: this.systemLabel,
      configured: true,
      connectivity,
      schema,
      permissions,
      latency,
      timestamp,
    };
  }
}
