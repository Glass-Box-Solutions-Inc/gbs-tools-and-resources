// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology

import { z } from "zod";

const envSchema = z.object({
  NODE_ENV: z
    .enum(["development", "production", "test"])
    .default("development"),
  PORT: z.coerce.number().default(5530),
  DATABASE_URL: z.string().min(1, "DATABASE_URL is required"),
  GITHUB_TOKEN: z.string().min(1, "GITHUB_TOKEN is required"),
  GITHUB_ORG: z.string().default("Glass-Box-Solutions-Inc"),
});

function parseEnv() {
  const result = envSchema.safeParse(process.env);
  if (!result.success) {
    const formatted = result.error.issues
      .map((i) => `  \u2022 ${i.path.join(".")}: ${i.message}`)
      .join("\n");
    throw new Error(
      `[compliance-auditor] Invalid environment:\n${formatted}`,
    );
  }
  return result.data;
}

export const env = parseEnv();
export type Env = typeof env;
