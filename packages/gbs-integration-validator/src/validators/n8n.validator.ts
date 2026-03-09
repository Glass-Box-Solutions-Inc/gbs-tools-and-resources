// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// n8n validator. Checks connectivity to the GBS n8n instance,
// validates response schemas for workflows and executions endpoints,
// and verifies the API key grants read access.

import ky from "ky";
import { env } from "../lib/env.js";
import { BaseValidator } from "./base.validator.js";
import {
  N8nWorkflowsResponseSchema,
  N8nExecutionsResponseSchema,
} from "../schemas/n8n.schema.js";
import type {
  ValidationCheck,
  PermissionResult,
} from "../types/index.js";

export class N8nValidator extends BaseValidator {
  readonly systemName = "n8n" as const;
  readonly systemLabel = "n8n";

  private apiUrl: string | null = null;
  private apiKey: string | null = null;

  constructor() {
    super();
    if (this.isConfigured()) {
      this.apiUrl = env.N8N_API_URL!;
      this.apiKey = env.N8N_API_KEY!;
    }
  }

  isConfigured(): boolean {
    return Boolean(env.N8N_API_URL && env.N8N_API_KEY);
  }

  private getClient() {
    return ky.create({
      prefixUrl: this.apiUrl!,
      headers: {
        "X-N8N-API-KEY": this.apiKey!,
      },
      timeout: 15000,
    });
  }

  async checkConnectivity(): Promise<ValidationCheck> {
    const start = performance.now();
    try {
      const client = this.getClient();
      const data = await client.get("api/v1/workflows", {
        searchParams: { limit: "1" },
      }).json();
      const durationMs = performance.now() - start;
      return {
        name: "connectivity",
        passed: true,
        message: "Connected to n8n instance",
        durationMs,
        details: { url: this.apiUrl },
      };
    } catch (error) {
      const durationMs = performance.now() - start;
      const message =
        error instanceof Error ? error.message : "Unknown error";
      return {
        name: "connectivity",
        passed: false,
        message: `n8n connectivity failed: ${message}`,
        durationMs,
      };
    }
  }

  async validateSchemas(): Promise<ValidationCheck[]> {
    const checks: ValidationCheck[] = [];
    const client = this.getClient();

    // -- Workflows schema check --
    const wfStart = performance.now();
    try {
      const data = await client
        .get("api/v1/workflows", { searchParams: { limit: "5" } })
        .json();
      const parseResult = N8nWorkflowsResponseSchema.safeParse(data);
      checks.push({
        name: "schema:workflows",
        passed: parseResult.success,
        message: parseResult.success
          ? `Workflows response matches schema`
          : `Workflows schema mismatch: ${parseResult.error.issues.map((i) => `${i.path.join(".")}: ${i.message}`).join("; ")}`,
        durationMs: performance.now() - wfStart,
        details: parseResult.success
          ? { sampleSize: (data as { data: unknown[] }).data?.length }
          : { errors: parseResult.error.issues },
      });
    } catch (error) {
      checks.push({
        name: "schema:workflows",
        passed: false,
        message: `Failed to fetch workflows: ${error instanceof Error ? error.message : "Unknown"}`,
        durationMs: performance.now() - wfStart,
      });
    }

    // -- Executions schema check --
    const exStart = performance.now();
    try {
      const data = await client
        .get("api/v1/executions", { searchParams: { limit: "5" } })
        .json();
      const parseResult = N8nExecutionsResponseSchema.safeParse(data);
      checks.push({
        name: "schema:executions",
        passed: parseResult.success,
        message: parseResult.success
          ? `Executions response matches schema`
          : `Executions schema mismatch: ${parseResult.error.issues.map((i) => `${i.path.join(".")}: ${i.message}`).join("; ")}`,
        durationMs: performance.now() - exStart,
        details: parseResult.success
          ? { sampleSize: (data as { data: unknown[] }).data?.length }
          : { errors: parseResult.error.issues },
      });
    } catch (error) {
      checks.push({
        name: "schema:executions",
        passed: false,
        message: `Failed to fetch executions: ${error instanceof Error ? error.message : "Unknown"}`,
        durationMs: performance.now() - exStart,
      });
    }

    return checks;
  }

  async checkPermissions(): Promise<PermissionResult> {
    const scopes: string[] = [];
    const missingScopes: string[] = [];
    const client = this.getClient();

    // Read workflows
    try {
      await client.get("api/v1/workflows", { searchParams: { limit: "1" } }).json();
      scopes.push("read:workflows");
    } catch {
      missingScopes.push("read:workflows");
    }

    // Read executions
    try {
      await client.get("api/v1/executions", { searchParams: { limit: "1" } }).json();
      scopes.push("read:executions");
    } catch {
      missingScopes.push("read:executions");
    }

    // Read credentials (may require higher privilege)
    try {
      await client.get("api/v1/credentials", { searchParams: { limit: "1" } }).json();
      scopes.push("read:credentials");
    } catch {
      missingScopes.push("read:credentials");
    }

    return {
      systemName: "n8n",
      hasAccess: scopes.length > 0 && missingScopes.length === 0,
      scopes,
      missingScopes,
    };
  }
}
