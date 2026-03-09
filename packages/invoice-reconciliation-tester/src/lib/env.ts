// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// Environment variable validation with Zod.
// All required variables are validated at startup -- missing vars crash with a clear message
// rather than failing silently at runtime.

import { z } from "zod";

const envSchema = z.object({
  // -- Node -------------------------------------------------------------------
  NODE_ENV: z
    .enum(["development", "production", "test"])
    .default("development"),
  PORT: z.coerce.number().default(5520),

  // -- Database (own PostgreSQL) ----------------------------------------------
  DATABASE_URL: z.string().min(1, "DATABASE_URL is required"),

  // -- GBS GitHub (optional, for live validation) -----------------------------
  GITHUB_TOKEN: z.string().optional(),

  // -- GBS Linear (optional, for live validation) -----------------------------
  LINEAR_API_KEY: z.string().optional(),
});

function parseEnv() {
  const result = envSchema.safeParse(process.env);
  if (!result.success) {
    const formatted = result.error.issues
      .map((i) => `  - ${i.path.join(".")}: ${i.message}`)
      .join("\n");
    throw new Error(
      `[invoice-reconciliation-tester] Invalid environment configuration:\n${formatted}\n\nCheck your .env file.`,
    );
  }
  return result.data;
}

export const env = parseEnv();
export type Env = typeof env;
