// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// Unit tests for GitHub Zod schemas. Validates that the schemas
// correctly accept valid payloads and reject invalid ones.

import { describe, it, expect } from "vitest";
import {
  GitHubOrgSchema,
  GitHubRepoSchema,
  GitHubReposListSchema,
  GitHubRateLimitSchema,
} from "../../src/schemas/github.schema.js";

describe("GitHubOrgSchema", () => {
  const validOrg = {
    login: "Glass-Box-Solutions-Inc",
    id: 12345,
    node_id: "O_abc123",
    url: "https://api.github.com/orgs/Glass-Box-Solutions-Inc",
    repos_url: "https://api.github.com/orgs/Glass-Box-Solutions-Inc/repos",
    description: "Glass Box Solutions",
    name: "Glass Box Solutions, Inc.",
    company: null,
    blog: "https://glassboxsolutions.com",
    location: "California",
    email: null,
    public_repos: 10,
    followers: 5,
    following: 0,
    created_at: "2023-01-01T00:00:00Z",
    updated_at: "2024-06-01T00:00:00Z",
    type: "Organization",
  };

  it("accepts a valid org response", () => {
    const result = GitHubOrgSchema.safeParse(validOrg);
    expect(result.success).toBe(true);
  });

  it("accepts org with null optional fields", () => {
    const org = {
      ...validOrg,
      name: null,
      company: null,
      blog: null,
      location: null,
      email: null,
      description: null,
    };
    const result = GitHubOrgSchema.safeParse(org);
    expect(result.success).toBe(true);
  });

  it("rejects org missing required login", () => {
    const { login: _, ...incomplete } = validOrg;
    const result = GitHubOrgSchema.safeParse(incomplete);
    expect(result.success).toBe(false);
  });

  it("rejects org missing required id", () => {
    const { id: _, ...incomplete } = validOrg;
    const result = GitHubOrgSchema.safeParse(incomplete);
    expect(result.success).toBe(false);
  });

  it("rejects org with wrong type for id", () => {
    const result = GitHubOrgSchema.safeParse({
      ...validOrg,
      id: "not_a_number",
    });
    expect(result.success).toBe(false);
  });

  it("rejects org missing required node_id", () => {
    const { node_id: _, ...incomplete } = validOrg;
    const result = GitHubOrgSchema.safeParse(incomplete);
    expect(result.success).toBe(false);
  });

  it("rejects org missing created_at", () => {
    const { created_at: _, ...incomplete } = validOrg;
    const result = GitHubOrgSchema.safeParse(incomplete);
    expect(result.success).toBe(false);
  });

  it("rejects completely empty object", () => {
    const result = GitHubOrgSchema.safeParse({});
    expect(result.success).toBe(false);
  });

  it("rejects null input", () => {
    const result = GitHubOrgSchema.safeParse(null);
    expect(result.success).toBe(false);
  });
});

describe("GitHubRepoSchema", () => {
  const validRepo = {
    id: 1,
    node_id: "R_abc",
    name: "test-repo",
    full_name: "Glass-Box-Solutions-Inc/test-repo",
    private: true,
    owner: { login: "Glass-Box-Solutions-Inc", id: 12345 },
    html_url: "https://github.com/Glass-Box-Solutions-Inc/test-repo",
    description: "A test repo",
    fork: false,
    created_at: "2023-01-01T00:00:00Z",
    updated_at: "2024-06-01T00:00:00Z",
    pushed_at: "2024-06-01T00:00:00Z",
    default_branch: "main",
    visibility: "private",
    language: "TypeScript",
    archived: false,
  };

  it("accepts a valid repo response", () => {
    const result = GitHubRepoSchema.safeParse(validRepo);
    expect(result.success).toBe(true);
  });

  it("accepts repo with null description and language", () => {
    const repo = { ...validRepo, description: null, language: null };
    const result = GitHubRepoSchema.safeParse(repo);
    expect(result.success).toBe(true);
  });

  it("accepts repo with null timestamps", () => {
    const repo = {
      ...validRepo,
      created_at: null,
      updated_at: null,
      pushed_at: null,
    };
    const result = GitHubRepoSchema.safeParse(repo);
    expect(result.success).toBe(true);
  });

  it("rejects repo missing name", () => {
    const { name: _, ...incomplete } = validRepo;
    const result = GitHubRepoSchema.safeParse(incomplete);
    expect(result.success).toBe(false);
  });

  it("rejects repo missing owner", () => {
    const { owner: _, ...incomplete } = validRepo;
    const result = GitHubRepoSchema.safeParse(incomplete);
    expect(result.success).toBe(false);
  });

  it("rejects repo with invalid owner shape", () => {
    const result = GitHubRepoSchema.safeParse({
      ...validRepo,
      owner: { invalid: "shape" },
    });
    expect(result.success).toBe(false);
  });

  it("rejects repo missing private field", () => {
    const { private: _, ...incomplete } = validRepo;
    const result = GitHubRepoSchema.safeParse(incomplete);
    expect(result.success).toBe(false);
  });
});

describe("GitHubReposListSchema", () => {
  it("accepts empty array", () => {
    const result = GitHubReposListSchema.safeParse([]);
    expect(result.success).toBe(true);
  });

  it("accepts array of valid repos", () => {
    const repos = [
      {
        id: 1,
        node_id: "R_a",
        name: "repo-a",
        full_name: "org/repo-a",
        private: false,
        owner: { login: "org", id: 1 },
        html_url: "https://github.com/org/repo-a",
        description: null,
        fork: false,
        created_at: "2023-01-01T00:00:00Z",
        updated_at: "2023-01-01T00:00:00Z",
        pushed_at: null,
        default_branch: "main",
        language: null,
        archived: false,
      },
      {
        id: 2,
        node_id: "R_b",
        name: "repo-b",
        full_name: "org/repo-b",
        private: true,
        owner: { login: "org", id: 1 },
        html_url: "https://github.com/org/repo-b",
        description: "Second repo",
        fork: true,
        created_at: "2023-06-01T00:00:00Z",
        updated_at: "2023-06-01T00:00:00Z",
        pushed_at: "2023-06-15T00:00:00Z",
        default_branch: "develop",
        language: "Python",
        archived: true,
      },
    ];
    const result = GitHubReposListSchema.safeParse(repos);
    expect(result.success).toBe(true);
  });

  it("rejects array with invalid repo object", () => {
    const repos = [{ invalid: "repo" }];
    const result = GitHubReposListSchema.safeParse(repos);
    expect(result.success).toBe(false);
  });

  it("rejects non-array input", () => {
    const result = GitHubReposListSchema.safeParse({ data: [] });
    expect(result.success).toBe(false);
  });
});

describe("GitHubRateLimitSchema", () => {
  const validRateLimit = {
    resources: {
      core: { limit: 5000, remaining: 4950, reset: 1700000000, used: 50 },
      search: { limit: 30, remaining: 29, reset: 1700000000, used: 1 },
    },
    rate: { limit: 5000, remaining: 4950, reset: 1700000000, used: 50 },
  };

  it("accepts a valid rate limit response", () => {
    const result = GitHubRateLimitSchema.safeParse(validRateLimit);
    expect(result.success).toBe(true);
  });

  it("rejects rate limit missing resources", () => {
    const { resources: _, ...incomplete } = validRateLimit;
    const result = GitHubRateLimitSchema.safeParse(incomplete);
    expect(result.success).toBe(false);
  });

  it("rejects rate limit missing rate", () => {
    const { rate: _, ...incomplete } = validRateLimit;
    const result = GitHubRateLimitSchema.safeParse(incomplete);
    expect(result.success).toBe(false);
  });

  it("rejects rate limit with missing core fields", () => {
    const result = GitHubRateLimitSchema.safeParse({
      ...validRateLimit,
      resources: {
        core: { limit: 5000 }, // missing remaining, reset, used
        search: { limit: 30, remaining: 29, reset: 1700000000, used: 1 },
      },
    });
    expect(result.success).toBe(false);
  });

  it("rejects non-numeric values in rate", () => {
    const result = GitHubRateLimitSchema.safeParse({
      ...validRateLimit,
      rate: { limit: "five thousand", remaining: 4950, reset: 1700000000, used: 50 },
    });
    expect(result.success).toBe(false);
  });
});
