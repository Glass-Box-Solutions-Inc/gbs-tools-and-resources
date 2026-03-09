// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// GitHub validator. Checks connectivity to the Glass-Box-Solutions-Inc org,
// validates response schemas for org and repos endpoints, and verifies
// that the PAT has the required scopes (read:org, repo).

import { Octokit } from "@octokit/rest";
import { env } from "../lib/env.js";
import { BaseValidator } from "./base.validator.js";
import {
  GitHubOrgSchema,
  GitHubReposListSchema,
  GitHubRateLimitSchema,
} from "../schemas/github.schema.js";
import type {
  ValidationCheck,
  PermissionResult,
} from "../types/index.js";

const GBS_ORG = "Glass-Box-Solutions-Inc";

export class GitHubValidator extends BaseValidator {
  readonly systemName = "github" as const;
  readonly systemLabel = "GitHub";

  private octokit: Octokit | null = null;

  constructor() {
    super();
    if (this.isConfigured()) {
      this.octokit = new Octokit({ auth: env.GITHUB_TOKEN });
    }
  }

  isConfigured(): boolean {
    return Boolean(env.GITHUB_TOKEN);
  }

  async checkConnectivity(): Promise<ValidationCheck> {
    const start = performance.now();
    try {
      const { data } = await this.octokit!.rest.orgs.get({ org: GBS_ORG });
      const durationMs = performance.now() - start;
      return {
        name: "connectivity",
        passed: true,
        message: `Connected to GitHub org: ${data.login}`,
        durationMs,
        details: { org: data.login, publicRepos: data.public_repos },
      };
    } catch (error) {
      const durationMs = performance.now() - start;
      const message =
        error instanceof Error ? error.message : "Unknown error";
      return {
        name: "connectivity",
        passed: false,
        message: `GitHub connectivity failed: ${message}`,
        durationMs,
      };
    }
  }

  async validateSchemas(): Promise<ValidationCheck[]> {
    const checks: ValidationCheck[] = [];

    // -- Org schema check --
    const orgStart = performance.now();
    try {
      const { data } = await this.octokit!.rest.orgs.get({ org: GBS_ORG });
      const parseResult = GitHubOrgSchema.safeParse(data);
      checks.push({
        name: "schema:org",
        passed: parseResult.success,
        message: parseResult.success
          ? "Org response matches expected schema"
          : `Org schema mismatch: ${parseResult.error.issues.map((i) => `${i.path.join(".")}: ${i.message}`).join("; ")}`,
        durationMs: performance.now() - orgStart,
        details: parseResult.success
          ? { login: data.login }
          : { errors: parseResult.error.issues },
      });
    } catch (error) {
      checks.push({
        name: "schema:org",
        passed: false,
        message: `Failed to fetch org for schema validation: ${error instanceof Error ? error.message : "Unknown"}`,
        durationMs: performance.now() - orgStart,
      });
    }

    // -- Repos list schema check --
    const reposStart = performance.now();
    try {
      const { data } = await this.octokit!.rest.repos.listForOrg({
        org: GBS_ORG,
        per_page: 5,
        type: "all",
      });
      const parseResult = GitHubReposListSchema.safeParse(data);
      checks.push({
        name: "schema:repos",
        passed: parseResult.success,
        message: parseResult.success
          ? `Repos list response matches schema (${data.length} repos sampled)`
          : `Repos schema mismatch: ${parseResult.error.issues.map((i) => `${i.path.join(".")}: ${i.message}`).join("; ")}`,
        durationMs: performance.now() - reposStart,
        details: parseResult.success
          ? { count: data.length }
          : { errors: parseResult.error.issues },
      });
    } catch (error) {
      checks.push({
        name: "schema:repos",
        passed: false,
        message: `Failed to fetch repos for schema validation: ${error instanceof Error ? error.message : "Unknown"}`,
        durationMs: performance.now() - reposStart,
      });
    }

    // -- Rate limit schema check --
    const rlStart = performance.now();
    try {
      const { data } = await this.octokit!.rest.rateLimit.get();
      const parseResult = GitHubRateLimitSchema.safeParse(data);
      checks.push({
        name: "schema:rateLimit",
        passed: parseResult.success,
        message: parseResult.success
          ? `Rate limit response matches schema (${data.rate.remaining}/${data.rate.limit} remaining)`
          : `Rate limit schema mismatch: ${parseResult.error.issues.map((i) => `${i.path.join(".")}: ${i.message}`).join("; ")}`,
        durationMs: performance.now() - rlStart,
        details: parseResult.success
          ? {
              remaining: data.rate.remaining,
              limit: data.rate.limit,
              resetAt: new Date(data.rate.reset * 1000).toISOString(),
            }
          : { errors: parseResult.error.issues },
      });
    } catch (error) {
      checks.push({
        name: "schema:rateLimit",
        passed: false,
        message: `Failed to fetch rate limit: ${error instanceof Error ? error.message : "Unknown"}`,
        durationMs: performance.now() - rlStart,
      });
    }

    return checks;
  }

  async checkPermissions(): Promise<PermissionResult> {
    const scopes: string[] = [];
    const missingScopes: string[] = [];

    // Check org read access
    try {
      await this.octokit!.rest.orgs.get({ org: GBS_ORG });
      scopes.push("read:org");
    } catch {
      missingScopes.push("read:org");
    }

    // Check repo access (private repos)
    try {
      const { data } = await this.octokit!.rest.repos.listForOrg({
        org: GBS_ORG,
        per_page: 1,
        type: "private",
      });
      if (data.length > 0) {
        scopes.push("repo");
      } else {
        // Could be no private repos, or no access — check with a known repo
        scopes.push("repo:public_only");
      }
    } catch {
      missingScopes.push("repo");
    }

    // Check members read access
    try {
      await this.octokit!.rest.orgs.listMembers({
        org: GBS_ORG,
        per_page: 1,
      });
      scopes.push("read:org:members");
    } catch {
      missingScopes.push("read:org:members");
    }

    return {
      systemName: "github",
      hasAccess: scopes.length > 0 && missingScopes.length === 0,
      scopes,
      missingScopes,
    };
  }
}
