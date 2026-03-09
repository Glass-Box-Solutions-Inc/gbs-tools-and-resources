// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// Zod schemas for validating GitHub API response shapes.
// Used by the GitHub validator to confirm Octokit returns expected data.

import { z } from "zod";

export const GitHubOrgSchema = z.object({
  login: z.string(),
  id: z.number(),
  node_id: z.string(),
  url: z.string(),
  repos_url: z.string(),
  description: z.string().nullable(),
  name: z.string().nullable().optional(),
  company: z.string().nullable().optional(),
  blog: z.string().nullable().optional(),
  location: z.string().nullable().optional(),
  email: z.string().nullable().optional(),
  public_repos: z.number(),
  followers: z.number(),
  following: z.number(),
  created_at: z.string(),
  updated_at: z.string(),
  type: z.string(),
});

export const GitHubRepoSchema = z.object({
  id: z.number(),
  node_id: z.string(),
  name: z.string(),
  full_name: z.string(),
  private: z.boolean(),
  owner: z.object({
    login: z.string(),
    id: z.number(),
  }),
  html_url: z.string(),
  description: z.string().nullable(),
  fork: z.boolean(),
  created_at: z.string().nullable(),
  updated_at: z.string().nullable(),
  pushed_at: z.string().nullable(),
  default_branch: z.string(),
  visibility: z.string().optional(),
  language: z.string().nullable(),
  archived: z.boolean(),
});

export const GitHubReposListSchema = z.array(GitHubRepoSchema);

export const GitHubRateLimitSchema = z.object({
  resources: z.object({
    core: z.object({
      limit: z.number(),
      remaining: z.number(),
      reset: z.number(),
      used: z.number(),
    }),
    search: z.object({
      limit: z.number(),
      remaining: z.number(),
      reset: z.number(),
      used: z.number(),
    }),
  }),
  rate: z.object({
    limit: z.number(),
    remaining: z.number(),
    reset: z.number(),
    used: z.number(),
  }),
});
