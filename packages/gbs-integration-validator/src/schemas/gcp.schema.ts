// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// Zod schemas for validating GCP API response shapes.
// Used by the GCP validator to confirm Resource Manager responses.

import { z } from "zod";

export const GcpProjectSchema = z.object({
  projectId: z.string(),
  name: z.string().optional(),
  state: z.string().optional(),
  displayName: z.string().optional(),
});

export const GcpIamPolicySchema = z.object({
  bindings: z
    .array(
      z.object({
        role: z.string(),
        members: z.array(z.string()),
      }),
    )
    .optional(),
  etag: z.string().optional(),
  version: z.number().optional(),
});

export const GcpBillingAccountSchema = z.object({
  name: z.string(),
  open: z.boolean().optional(),
  displayName: z.string().optional(),
  masterBillingAccount: z.string().optional(),
});

export const GcpBillingInfoSchema = z.object({
  name: z.string().optional(),
  projectId: z.string().optional(),
  billingAccountName: z.string().optional(),
  billingEnabled: z.boolean().optional(),
});
