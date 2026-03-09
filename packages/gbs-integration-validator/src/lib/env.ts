// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// Environment variable validation with Zod.
// All API credentials are optional so the validator can report which
// systems are configured vs not, rather than crashing on startup.

import { z } from "zod";

const envSchema = z.object({
  // -- Node ----------------------------------------------------------------
  NODE_ENV: z
    .enum(["development", "production", "test"])
    .default("development"),
  PORT: z.coerce.number().default(5510),

  // -- GitHub (Octokit) ----------------------------------------------------
  GITHUB_TOKEN: z.string().optional(),

  // -- Linear --------------------------------------------------------------
  LINEAR_API_KEY: z.string().optional(),

  // -- n8n -----------------------------------------------------------------
  N8N_API_URL: z.string().optional(),
  N8N_API_KEY: z.string().optional(),

  // -- GCP -----------------------------------------------------------------
  GCP_PROJECT_ID: z.string().optional(),

  // -- Stripe --------------------------------------------------------------
  STRIPE_SECRET_KEY: z.string().optional(),

  // -- Knowledge Base ------------------------------------------------------
  KB_API_URL: z.string().optional(),
  KB_API_KEY: z.string().optional(),

  // -- Slack ---------------------------------------------------------------
  SLACK_BOT_TOKEN: z.string().optional(),
});

function parseEnv() {
  const result = envSchema.safeParse(process.env);
  if (!result.success) {
    const formatted = result.error.issues
      .map((i) => `  \u2022 ${i.path.join(".")}: ${i.message}`)
      .join("\n");
    throw new Error(
      `[gbs-integration-validator] Invalid environment:\n${formatted}`,
    );
  }
  return result.data;
}

export const env = parseEnv();
export type Env = typeof env;
