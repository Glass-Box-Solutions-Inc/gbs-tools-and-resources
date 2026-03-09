// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// Zod schemas for validating Knowledge Base API response shapes.
// Used by the KB validator to confirm the API returns expected data.

import { z } from "zod";

export const KbHealthSchema = z.object({
  status: z.string(),
  version: z.string().optional(),
  uptime: z.number().optional(),
});

export const KbCaseSchema = z.object({
  id: z.union([z.string(), z.number()]),
  title: z.string(),
  status: z.string(),
  createdAt: z.string().optional(),
  updatedAt: z.string().optional(),
});

export const KbCasesListSchema = z.object({
  data: z.array(KbCaseSchema).optional(),
  cases: z.array(KbCaseSchema).optional(),
  total: z.number().optional(),
});

export const KbDocumentSchema = z.object({
  id: z.union([z.string(), z.number()]),
  title: z.string().optional(),
  content: z.string().optional(),
  type: z.string().optional(),
});
