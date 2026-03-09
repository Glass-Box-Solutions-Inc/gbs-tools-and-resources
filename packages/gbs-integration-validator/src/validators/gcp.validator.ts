// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// GCP validator. Checks connectivity to the GBS GCP project,
// validates response schemas for project and IAM endpoints,
// and verifies that the service account has required roles.

import { ProjectsClient } from "@google-cloud/resource-manager";
import { env } from "../lib/env.js";
import { BaseValidator } from "./base.validator.js";
import { GcpProjectSchema } from "../schemas/gcp.schema.js";
import type {
  ValidationCheck,
  PermissionResult,
} from "../types/index.js";

export class GcpValidator extends BaseValidator {
  readonly systemName = "gcp" as const;
  readonly systemLabel = "Google Cloud Platform";

  private projectsClient: ProjectsClient | null = null;

  constructor() {
    super();
    if (this.isConfigured()) {
      this.projectsClient = new ProjectsClient();
    }
  }

  isConfigured(): boolean {
    return Boolean(env.GCP_PROJECT_ID);
  }

  async checkConnectivity(): Promise<ValidationCheck> {
    const start = performance.now();
    try {
      const [project] = await this.projectsClient!.getProject({
        name: `projects/${env.GCP_PROJECT_ID}`,
      });
      const durationMs = performance.now() - start;
      return {
        name: "connectivity",
        passed: true,
        message: `Connected to GCP project: ${env.GCP_PROJECT_ID}`,
        durationMs,
        details: {
          projectId: project.projectId,
          displayName: project.displayName,
          state: project.state,
        },
      };
    } catch (error) {
      const durationMs = performance.now() - start;
      const message =
        error instanceof Error ? error.message : "Unknown error";
      return {
        name: "connectivity",
        passed: false,
        message: `GCP connectivity failed: ${message}`,
        durationMs,
      };
    }
  }

  async validateSchemas(): Promise<ValidationCheck[]> {
    const checks: ValidationCheck[] = [];

    // -- Project schema check --
    const projStart = performance.now();
    try {
      const [project] = await this.projectsClient!.getProject({
        name: `projects/${env.GCP_PROJECT_ID}`,
      });
      const parseResult = GcpProjectSchema.safeParse(project);
      checks.push({
        name: "schema:project",
        passed: parseResult.success,
        message: parseResult.success
          ? `Project response matches schema: ${project.projectId}`
          : `Project schema mismatch: ${parseResult.error.issues.map((i) => `${i.path.join(".")}: ${i.message}`).join("; ")}`,
        durationMs: performance.now() - projStart,
        details: parseResult.success
          ? { projectId: project.projectId }
          : { errors: parseResult.error.issues },
      });
    } catch (error) {
      checks.push({
        name: "schema:project",
        passed: false,
        message: `Failed to fetch project: ${error instanceof Error ? error.message : "Unknown"}`,
        durationMs: performance.now() - projStart,
      });
    }

    // -- IAM policy schema check --
    const iamStart = performance.now();
    try {
      const [policy] = await this.projectsClient!.getIamPolicy({
        resource: `projects/${env.GCP_PROJECT_ID}`,
      });
      const hasBindings = Array.isArray(policy.bindings);
      checks.push({
        name: "schema:iamPolicy",
        passed: hasBindings,
        message: hasBindings
          ? `IAM policy response has ${policy.bindings!.length} bindings`
          : "IAM policy missing bindings array",
        durationMs: performance.now() - iamStart,
        details: hasBindings
          ? { bindingsCount: policy.bindings!.length }
          : {},
      });
    } catch (error) {
      checks.push({
        name: "schema:iamPolicy",
        passed: false,
        message: `Failed to fetch IAM policy: ${error instanceof Error ? error.message : "Unknown"}`,
        durationMs: performance.now() - iamStart,
      });
    }

    return checks;
  }

  async checkPermissions(): Promise<PermissionResult> {
    const scopes: string[] = [];
    const missingScopes: string[] = [];

    // Check project read access
    try {
      await this.projectsClient!.getProject({
        name: `projects/${env.GCP_PROJECT_ID}`,
      });
      scopes.push("resourcemanager.projects.get");
    } catch {
      missingScopes.push("resourcemanager.projects.get");
    }

    // Check IAM policy read access
    try {
      await this.projectsClient!.getIamPolicy({
        resource: `projects/${env.GCP_PROJECT_ID}`,
      });
      scopes.push("resourcemanager.projects.getIamPolicy");
    } catch {
      missingScopes.push("resourcemanager.projects.getIamPolicy");
    }

    return {
      systemName: "gcp",
      hasAccess: scopes.length > 0 && missingScopes.length === 0,
      scopes,
      missingScopes,
    };
  }
}
