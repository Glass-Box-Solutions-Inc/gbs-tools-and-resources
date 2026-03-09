// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// Slack validator. Checks connectivity to the GBS Slack workspace,
// validates response schemas for auth.test and conversations endpoints,
// and verifies the bot token has required scopes.

import { WebClient } from "@slack/web-api";
import { env } from "../lib/env.js";
import { BaseValidator } from "./base.validator.js";
import {
  SlackAuthTestSchema,
  SlackConversationsListSchema,
  SlackUsersListSchema,
} from "../schemas/slack.schema.js";
import type {
  ValidationCheck,
  PermissionResult,
} from "../types/index.js";

export class SlackValidator extends BaseValidator {
  readonly systemName = "slack" as const;
  readonly systemLabel = "Slack";

  private client: WebClient | null = null;

  constructor() {
    super();
    if (this.isConfigured()) {
      this.client = new WebClient(env.SLACK_BOT_TOKEN);
    }
  }

  isConfigured(): boolean {
    return Boolean(env.SLACK_BOT_TOKEN);
  }

  async checkConnectivity(): Promise<ValidationCheck> {
    const start = performance.now();
    try {
      const result = await this.client!.auth.test();
      const durationMs = performance.now() - start;
      if (!result.ok) {
        return {
          name: "connectivity",
          passed: false,
          message: `Slack auth.test returned ok=false`,
          durationMs,
        };
      }
      return {
        name: "connectivity",
        passed: true,
        message: `Connected to Slack workspace: ${result.team}`,
        durationMs,
        details: {
          team: result.team,
          teamId: result.team_id,
          user: result.user,
          userId: result.user_id,
          botId: result.bot_id,
        },
      };
    } catch (error) {
      const durationMs = performance.now() - start;
      const message =
        error instanceof Error ? error.message : "Unknown error";
      return {
        name: "connectivity",
        passed: false,
        message: `Slack connectivity failed: ${message}`,
        durationMs,
      };
    }
  }

  async validateSchemas(): Promise<ValidationCheck[]> {
    const checks: ValidationCheck[] = [];

    // -- auth.test schema check --
    const authStart = performance.now();
    try {
      const result = await this.client!.auth.test();
      const parseResult = SlackAuthTestSchema.safeParse(result);
      checks.push({
        name: "schema:authTest",
        passed: parseResult.success,
        message: parseResult.success
          ? `auth.test response matches schema: ${result.team}`
          : `auth.test schema mismatch: ${parseResult.error.issues.map((i) => `${i.path.join(".")}: ${i.message}`).join("; ")}`,
        durationMs: performance.now() - authStart,
        details: parseResult.success
          ? { team: result.team }
          : { errors: parseResult.error.issues },
      });
    } catch (error) {
      checks.push({
        name: "schema:authTest",
        passed: false,
        message: `Failed to call auth.test: ${error instanceof Error ? error.message : "Unknown"}`,
        durationMs: performance.now() - authStart,
      });
    }

    // -- conversations.list schema check --
    const convStart = performance.now();
    try {
      const result = await this.client!.conversations.list({
        limit: 5,
        types: "public_channel",
      });
      const parseResult = SlackConversationsListSchema.safeParse(result);
      checks.push({
        name: "schema:conversationsList",
        passed: parseResult.success,
        message: parseResult.success
          ? `conversations.list response matches schema (${result.channels?.length ?? 0} channels)`
          : `conversations.list schema mismatch: ${parseResult.error.issues.map((i) => `${i.path.join(".")}: ${i.message}`).join("; ")}`,
        durationMs: performance.now() - convStart,
        details: parseResult.success
          ? { count: result.channels?.length ?? 0 }
          : { errors: parseResult.error.issues },
      });
    } catch (error) {
      checks.push({
        name: "schema:conversationsList",
        passed: false,
        message: `Failed to call conversations.list: ${error instanceof Error ? error.message : "Unknown"}`,
        durationMs: performance.now() - convStart,
      });
    }

    // -- users.list schema check --
    const usersStart = performance.now();
    try {
      const result = await this.client!.users.list({ limit: 5 });
      const parseResult = SlackUsersListSchema.safeParse(result);
      checks.push({
        name: "schema:usersList",
        passed: parseResult.success,
        message: parseResult.success
          ? `users.list response matches schema (${result.members?.length ?? 0} users)`
          : `users.list schema mismatch: ${parseResult.error.issues.map((i) => `${i.path.join(".")}: ${i.message}`).join("; ")}`,
        durationMs: performance.now() - usersStart,
        details: parseResult.success
          ? { count: result.members?.length ?? 0 }
          : { errors: parseResult.error.issues },
      });
    } catch (error) {
      checks.push({
        name: "schema:usersList",
        passed: false,
        message: `Failed to call users.list: ${error instanceof Error ? error.message : "Unknown"}`,
        durationMs: performance.now() - usersStart,
      });
    }

    return checks;
  }

  async checkPermissions(): Promise<PermissionResult> {
    const scopes: string[] = [];
    const missingScopes: string[] = [];

    // Check auth.test (basic auth scope)
    try {
      const result = await this.client!.auth.test();
      if (result.ok) {
        scopes.push("auth:test");
      } else {
        missingScopes.push("auth:test");
      }
    } catch {
      missingScopes.push("auth:test");
    }

    // Check channels:read
    try {
      const result = await this.client!.conversations.list({
        limit: 1,
        types: "public_channel",
      });
      if (result.ok) {
        scopes.push("channels:read");
      } else {
        missingScopes.push("channels:read");
      }
    } catch {
      missingScopes.push("channels:read");
    }

    // Check users:read
    try {
      const result = await this.client!.users.list({ limit: 1 });
      if (result.ok) {
        scopes.push("users:read");
      } else {
        missingScopes.push("users:read");
      }
    } catch {
      missingScopes.push("users:read");
    }

    // Check chat:write (attempt to send a message to check scope, but don't actually send)
    // We can only detect this from the scopes header, so we infer from auth.test
    // The Slack API returns scopes in the x-oauth-scopes header, but the SDK doesn't expose it.
    // We'll just report what we can verify.

    return {
      systemName: "slack",
      hasAccess: scopes.length > 0 && missingScopes.length === 0,
      scopes,
      missingScopes,
    };
  }
}
