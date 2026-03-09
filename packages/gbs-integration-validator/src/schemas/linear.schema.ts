// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// Zod schemas for validating Linear API response shapes.
// Used by the Linear validator to confirm SDK responses match expected data.

import { z } from "zod";

export const LinearOrganizationSchema = z.object({
  id: z.string(),
  name: z.string(),
  urlKey: z.string(),
  createdAt: z.coerce.date(),
});

export const LinearTeamSchema = z.object({
  id: z.string(),
  name: z.string(),
  key: z.string(),
});

export const LinearTeamsSchema = z.object({
  nodes: z.array(LinearTeamSchema),
});

export const LinearIssueSchema = z.object({
  id: z.string(),
  title: z.string(),
  identifier: z.string(),
  createdAt: z.coerce.date(),
  updatedAt: z.coerce.date(),
});

export const LinearIssuesConnectionSchema = z.object({
  nodes: z.array(LinearIssueSchema),
});

export const LinearViewerSchema = z.object({
  id: z.string(),
  name: z.string(),
  email: z.string(),
  active: z.boolean(),
});
