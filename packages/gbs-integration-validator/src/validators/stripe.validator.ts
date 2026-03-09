// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// Stripe validator. Checks connectivity to the GBS Stripe account,
// validates response schemas for account, charges, and balance endpoints,
// and verifies the secret key has read access.

import Stripe from "stripe";
import { env } from "../lib/env.js";
import { BaseValidator } from "./base.validator.js";
import {
  StripeAccountSchema,
  StripeChargesListSchema,
  StripeBalanceSchema,
} from "../schemas/stripe.schema.js";
import type {
  ValidationCheck,
  PermissionResult,
} from "../types/index.js";

export class StripeValidator extends BaseValidator {
  readonly systemName = "stripe" as const;
  readonly systemLabel = "Stripe";

  private stripe: Stripe | null = null;

  constructor() {
    super();
    if (this.isConfigured()) {
      this.stripe = new Stripe(env.STRIPE_SECRET_KEY!);
    }
  }

  isConfigured(): boolean {
    return Boolean(env.STRIPE_SECRET_KEY);
  }

  async checkConnectivity(): Promise<ValidationCheck> {
    const start = performance.now();
    try {
      const account = await this.stripe!.accounts.retrieve();
      const durationMs = performance.now() - start;
      return {
        name: "connectivity",
        passed: true,
        message: `Connected to Stripe account: ${account.id}`,
        durationMs,
        details: {
          accountId: account.id,
          chargesEnabled: account.charges_enabled,
          payoutsEnabled: account.payouts_enabled,
        },
      };
    } catch (error) {
      const durationMs = performance.now() - start;
      const message =
        error instanceof Error ? error.message : "Unknown error";
      return {
        name: "connectivity",
        passed: false,
        message: `Stripe connectivity failed: ${message}`,
        durationMs,
      };
    }
  }

  async validateSchemas(): Promise<ValidationCheck[]> {
    const checks: ValidationCheck[] = [];

    // -- Account schema check --
    const acctStart = performance.now();
    try {
      const account = await this.stripe!.accounts.retrieve();
      const parseResult = StripeAccountSchema.safeParse(account);
      checks.push({
        name: "schema:account",
        passed: parseResult.success,
        message: parseResult.success
          ? `Account response matches schema: ${account.id}`
          : `Account schema mismatch: ${parseResult.error.issues.map((i) => `${i.path.join(".")}: ${i.message}`).join("; ")}`,
        durationMs: performance.now() - acctStart,
        details: parseResult.success
          ? { id: account.id }
          : { errors: parseResult.error.issues },
      });
    } catch (error) {
      checks.push({
        name: "schema:account",
        passed: false,
        message: `Failed to fetch account: ${error instanceof Error ? error.message : "Unknown"}`,
        durationMs: performance.now() - acctStart,
      });
    }

    // -- Charges list schema check --
    const chgStart = performance.now();
    try {
      const charges = await this.stripe!.charges.list({ limit: 3 });
      const parseResult = StripeChargesListSchema.safeParse(charges);
      checks.push({
        name: "schema:charges",
        passed: parseResult.success,
        message: parseResult.success
          ? `Charges list response matches schema (${charges.data.length} charges sampled)`
          : `Charges schema mismatch: ${parseResult.error.issues.map((i) => `${i.path.join(".")}: ${i.message}`).join("; ")}`,
        durationMs: performance.now() - chgStart,
        details: parseResult.success
          ? { count: charges.data.length }
          : { errors: parseResult.error.issues },
      });
    } catch (error) {
      checks.push({
        name: "schema:charges",
        passed: false,
        message: `Failed to fetch charges: ${error instanceof Error ? error.message : "Unknown"}`,
        durationMs: performance.now() - chgStart,
      });
    }

    // -- Balance schema check --
    const balStart = performance.now();
    try {
      const balance = await this.stripe!.balance.retrieve();
      const parseResult = StripeBalanceSchema.safeParse(balance);
      checks.push({
        name: "schema:balance",
        passed: parseResult.success,
        message: parseResult.success
          ? "Balance response matches schema"
          : `Balance schema mismatch: ${parseResult.error.issues.map((i) => `${i.path.join(".")}: ${i.message}`).join("; ")}`,
        durationMs: performance.now() - balStart,
        details: parseResult.success
          ? {
              availableCurrencies: balance.available.map((a) => a.currency),
            }
          : { errors: parseResult.error.issues },
      });
    } catch (error) {
      checks.push({
        name: "schema:balance",
        passed: false,
        message: `Failed to fetch balance: ${error instanceof Error ? error.message : "Unknown"}`,
        durationMs: performance.now() - balStart,
      });
    }

    return checks;
  }

  async checkPermissions(): Promise<PermissionResult> {
    const scopes: string[] = [];
    const missingScopes: string[] = [];

    // Read account
    try {
      await this.stripe!.accounts.retrieve();
      scopes.push("read:account");
    } catch {
      missingScopes.push("read:account");
    }

    // Read charges
    try {
      await this.stripe!.charges.list({ limit: 1 });
      scopes.push("read:charges");
    } catch {
      missingScopes.push("read:charges");
    }

    // Read balance
    try {
      await this.stripe!.balance.retrieve();
      scopes.push("read:balance");
    } catch {
      missingScopes.push("read:balance");
    }

    // Read customers
    try {
      await this.stripe!.customers.list({ limit: 1 });
      scopes.push("read:customers");
    } catch {
      missingScopes.push("read:customers");
    }

    // Read invoices
    try {
      await this.stripe!.invoices.list({ limit: 1 });
      scopes.push("read:invoices");
    } catch {
      missingScopes.push("read:invoices");
    }

    return {
      systemName: "stripe",
      hasAccess: scopes.length > 0 && missingScopes.length === 0,
      scopes,
      missingScopes,
    };
  }
}
