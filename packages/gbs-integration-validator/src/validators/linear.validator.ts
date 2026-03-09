// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// Linear validator. Checks connectivity to the GBS Linear workspace,
// validates response schemas for organization, teams, and issues,
// and verifies the API key has read access.

import { LinearClient } from "@linear/sdk";
import { env } from "../lib/env.js";
import { BaseValidator } from "./base.validator.js";
import {
  LinearOrganizationSchema,
  LinearTeamsSchema,
  LinearIssuesConnectionSchema,
  LinearViewerSchema,
} from "../schemas/linear.schema.js";
import type {
  ValidationCheck,
  PermissionResult,
} from "../types/index.js";

export class LinearValidator extends BaseValidator {
  readonly systemName = "linear" as const;
  readonly systemLabel = "Linear";

  private client: LinearClient | null = null;

  constructor() {
    super();
    if (this.isConfigured()) {
      this.client = new LinearClient({ apiKey: env.LINEAR_API_KEY! });
    }
  }

  isConfigured(): boolean {
    return Boolean(env.LINEAR_API_KEY);
  }

  async checkConnectivity(): Promise<ValidationCheck> {
    const start = performance.now();
    try {
      const org = await this.client!.organization;
      const durationMs = performance.now() - start;
      return {
        name: "connectivity",
        passed: true,
        message: `Connected to Linear workspace: ${org.name}`,
        durationMs,
        details: { workspace: org.name, urlKey: org.urlKey },
      };
    } catch (error) {
      const durationMs = performance.now() - start;
      const message =
        error instanceof Error ? error.message : "Unknown error";
      return {
        name: "connectivity",
        passed: false,
        message: `Linear connectivity failed: ${message}`,
        durationMs,
      };
    }
  }

  async validateSchemas(): Promise<ValidationCheck[]> {
    const checks: ValidationCheck[] = [];

    // -- Organization schema check --
    const orgStart = performance.now();
    try {
      const org = await this.client!.organization;
      const parseResult = LinearOrganizationSchema.safeParse(org);
      checks.push({
        name: "schema:organization",
        passed: parseResult.success,
        message: parseResult.success
          ? `Organization response matches schema: ${org.name}`
          : `Organization schema mismatch: ${parseResult.error.issues.map((i) => `${i.path.join(".")}: ${i.message}`).join("; ")}`,
        durationMs: performance.now() - orgStart,
        details: parseResult.success
          ? { name: org.name }
          : { errors: parseResult.error.issues },
      });
    } catch (error) {
      checks.push({
        name: "schema:organization",
        passed: false,
        message: `Failed to fetch organization: ${error instanceof Error ? error.message : "Unknown"}`,
        durationMs: performance.now() - orgStart,
      });
    }

    // -- Teams schema check --
    const teamsStart = performance.now();
    try {
      const teams = await this.client!.teams();
      const parseResult = LinearTeamsSchema.safeParse(teams);
      checks.push({
        name: "schema:teams",
        passed: parseResult.success,
        message: parseResult.success
          ? `Teams response matches schema (${teams.nodes.length} teams)`
          : `Teams schema mismatch: ${parseResult.error.issues.map((i) => `${i.path.join(".")}: ${i.message}`).join("; ")}`,
        durationMs: performance.now() - teamsStart,
        details: parseResult.success
          ? { count: teams.nodes.length }
          : { errors: parseResult.error.issues },
      });
    } catch (error) {
      checks.push({
        name: "schema:teams",
        passed: false,
        message: `Failed to fetch teams: ${error instanceof Error ? error.message : "Unknown"}`,
        durationMs: performance.now() - teamsStart,
      });
    }

    // -- Issues schema check --
    const issuesStart = performance.now();
    try {
      const issues = await this.client!.issues({ first: 5 });
      const parseResult = LinearIssuesConnectionSchema.safeParse(issues);
      checks.push({
        name: "schema:issues",
        passed: parseResult.success,
        message: parseResult.success
          ? `Issues response matches schema (${issues.nodes.length} issues sampled)`
          : `Issues schema mismatch: ${parseResult.error.issues.map((i) => `${i.path.join(".")}: ${i.message}`).join("; ")}`,
        durationMs: performance.now() - issuesStart,
        details: parseResult.success
          ? { count: issues.nodes.length }
          : { errors: parseResult.error.issues },
      });
    } catch (error) {
      checks.push({
        name: "schema:issues",
        passed: false,
        message: `Failed to fetch issues: ${error instanceof Error ? error.message : "Unknown"}`,
        durationMs: performance.now() - issuesStart,
      });
    }

    // -- Viewer schema check --
    const viewerStart = performance.now();
    try {
      const viewer = await this.client!.viewer;
      const parseResult = LinearViewerSchema.safeParse(viewer);
      checks.push({
        name: "schema:viewer",
        passed: parseResult.success,
        message: parseResult.success
          ? `Viewer response matches schema: ${viewer.name}`
          : `Viewer schema mismatch: ${parseResult.error.issues.map((i) => `${i.path.join(".")}: ${i.message}`).join("; ")}`,
        durationMs: performance.now() - viewerStart,
        details: parseResult.success
          ? { name: viewer.name, email: viewer.email }
          : { errors: parseResult.error.issues },
      });
    } catch (error) {
      checks.push({
        name: "schema:viewer",
        passed: false,
        message: `Failed to fetch viewer: ${error instanceof Error ? error.message : "Unknown"}`,
        durationMs: performance.now() - viewerStart,
      });
    }

    return checks;
  }

  async checkPermissions(): Promise<PermissionResult> {
    const scopes: string[] = [];
    const missingScopes: string[] = [];

    // Read organization
    try {
      await this.client!.organization;
      scopes.push("read:organization");
    } catch {
      missingScopes.push("read:organization");
    }

    // Read teams
    try {
      await this.client!.teams({ first: 1 });
      scopes.push("read:teams");
    } catch {
      missingScopes.push("read:teams");
    }

    // Read issues
    try {
      await this.client!.issues({ first: 1 });
      scopes.push("read:issues");
    } catch {
      missingScopes.push("read:issues");
    }

    // Read viewer (self)
    try {
      await this.client!.viewer;
      scopes.push("read:user");
    } catch {
      missingScopes.push("read:user");
    }

    return {
      systemName: "linear",
      hasAccess: scopes.length > 0 && missingScopes.length === 0,
      scopes,
      missingScopes,
    };
  }
}
