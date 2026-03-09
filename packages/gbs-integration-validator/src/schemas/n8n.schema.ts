// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// Zod schemas for validating n8n API response shapes.
// Used by the n8n validator to confirm REST API returns expected data.

import { z } from "zod";

export const N8nWorkflowSchema = z.object({
  id: z.union([z.string(), z.number()]),
  name: z.string(),
  active: z.boolean(),
  createdAt: z.string(),
  updatedAt: z.string(),
});

export const N8nWorkflowsResponseSchema = z.object({
  data: z.array(N8nWorkflowSchema),
});

export const N8nExecutionSchema = z.object({
  id: z.union([z.string(), z.number()]),
  finished: z.boolean(),
  mode: z.string(),
  startedAt: z.string(),
  stoppedAt: z.string().nullable().optional(),
  workflowId: z.union([z.string(), z.number()]),
});

export const N8nExecutionsResponseSchema = z.object({
  data: z.array(N8nExecutionSchema),
});

export const N8nHealthSchema = z.object({
  status: z.string(),
});
