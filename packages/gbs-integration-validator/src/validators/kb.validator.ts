// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// Knowledge Base validator. Checks connectivity to the GBS KB API,
// validates response schemas for health and cases endpoints,
// and verifies the API key grants read access.

import ky from "ky";
import { env } from "../lib/env.js";
import { BaseValidator } from "./base.validator.js";
import { KbHealthSchema, KbCasesListSchema } from "../schemas/kb.schema.js";
import type {
  ValidationCheck,
  PermissionResult,
} from "../types/index.js";

export class KbValidator extends BaseValidator {
  readonly systemName = "kb" as const;
  readonly systemLabel = "Knowledge Base";

  private apiUrl: string | null = null;
  private apiKey: string | null = null;

  constructor() {
    super();
    if (this.isConfigured()) {
      this.apiUrl = env.KB_API_URL!;
      this.apiKey = env.KB_API_KEY!;
    }
  }

  isConfigured(): boolean {
    return Boolean(env.KB_API_URL && env.KB_API_KEY);
  }

  private getClient() {
    return ky.create({
      prefixUrl: this.apiUrl!,
      headers: {
        Authorization: `Bearer ${this.apiKey}`,
      },
      timeout: 15000,
    });
  }

  async checkConnectivity(): Promise<ValidationCheck> {
    const start = performance.now();
    try {
      const client = this.getClient();
      const data = await client.get("health").json();
      const durationMs = performance.now() - start;
      return {
        name: "connectivity",
        passed: true,
        message: "Connected to Knowledge Base API",
        durationMs,
        details: { url: this.apiUrl, response: data },
      };
    } catch (error) {
      const durationMs = performance.now() - start;
      const message =
        error instanceof Error ? error.message : "Unknown error";
      return {
        name: "connectivity",
        passed: false,
        message: `Knowledge Base connectivity failed: ${message}`,
        durationMs,
      };
    }
  }

  async validateSchemas(): Promise<ValidationCheck[]> {
    const checks: ValidationCheck[] = [];
    const client = this.getClient();

    // -- Health schema check --
    const healthStart = performance.now();
    try {
      const data = await client.get("health").json();
      const parseResult = KbHealthSchema.safeParse(data);
      checks.push({
        name: "schema:health",
        passed: parseResult.success,
        message: parseResult.success
          ? "Health response matches schema"
          : `Health schema mismatch: ${parseResult.error.issues.map((i) => `${i.path.join(".")}: ${i.message}`).join("; ")}`,
        durationMs: performance.now() - healthStart,
        details: parseResult.success
          ? { data }
          : { errors: parseResult.error.issues },
      });
    } catch (error) {
      checks.push({
        name: "schema:health",
        passed: false,
        message: `Failed to fetch health: ${error instanceof Error ? error.message : "Unknown"}`,
        durationMs: performance.now() - healthStart,
      });
    }

    // -- Cases list schema check --
    const casesStart = performance.now();
    try {
      const data = await client
        .get("api/cases", { searchParams: { limit: "5" } })
        .json();
      const parseResult = KbCasesListSchema.safeParse(data);
      checks.push({
        name: "schema:cases",
        passed: parseResult.success,
        message: parseResult.success
          ? "Cases response matches schema"
          : `Cases schema mismatch: ${parseResult.error.issues.map((i) => `${i.path.join(".")}: ${i.message}`).join("; ")}`,
        durationMs: performance.now() - casesStart,
        details: parseResult.success
          ? {}
          : { errors: parseResult.error.issues },
      });
    } catch (error) {
      checks.push({
        name: "schema:cases",
        passed: false,
        message: `Failed to fetch cases: ${error instanceof Error ? error.message : "Unknown"}`,
        durationMs: performance.now() - casesStart,
      });
    }

    return checks;
  }

  async checkPermissions(): Promise<PermissionResult> {
    const scopes: string[] = [];
    const missingScopes: string[] = [];
    const client = this.getClient();

    // Read health
    try {
      await client.get("health").json();
      scopes.push("read:health");
    } catch {
      missingScopes.push("read:health");
    }

    // Read cases
    try {
      await client
        .get("api/cases", { searchParams: { limit: "1" } })
        .json();
      scopes.push("read:cases");
    } catch {
      missingScopes.push("read:cases");
    }

    // Read documents
    try {
      await client
        .get("api/documents", { searchParams: { limit: "1" } })
        .json();
      scopes.push("read:documents");
    } catch {
      missingScopes.push("read:documents");
    }

    return {
      systemName: "kb",
      hasAccess: scopes.length > 0 && missingScopes.length === 0,
      scopes,
      missingScopes,
    };
  }
}
