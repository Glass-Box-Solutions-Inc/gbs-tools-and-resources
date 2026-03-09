// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// Unit tests for GitHubValidator. Mocks Octokit responses to test
// configuration detection, connectivity, schema validation, and
// permission checks without requiring actual GitHub API access.

import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock Octokit — vi.mock is hoisted so must use factory returning the mock
const mockOctokitInstance = {
  rest: {
    orgs: {
      get: vi.fn(),
      listMembers: vi.fn(),
    },
    repos: {
      listForOrg: vi.fn(),
    },
    rateLimit: {
      get: vi.fn(),
    },
  },
};

vi.mock("@octokit/rest", () => ({
  Octokit: vi.fn(() => mockOctokitInstance),
}));

// Mock env — the import specifier as seen from the validator source file
vi.mock("../../src/lib/env.js", () => ({
  env: {
    NODE_ENV: "test",
    PORT: 5510,
    GITHUB_TOKEN: "ghp_test_token_1234567890",
  },
}));

import { GitHubValidator } from "../../src/validators/github.validator.js";

describe("GitHubValidator", () => {
  let validator: GitHubValidator;

  beforeEach(() => {
    vi.clearAllMocks();
    validator = new GitHubValidator();
  });

  describe("isConfigured", () => {
    it("returns true when GITHUB_TOKEN is set", () => {
      expect(validator.isConfigured()).toBe(true);
    });
  });

  describe("checkConnectivity", () => {
    it("returns passed=true when org is accessible", async () => {
      mockOctokitInstance.rest.orgs.get.mockResolvedValue({
        data: {
          login: "Glass-Box-Solutions-Inc",
          id: 12345,
          public_repos: 42,
        },
      });

      const result = await validator.checkConnectivity();

      expect(result.passed).toBe(true);
      expect(result.name).toBe("connectivity");
      expect(result.message).toContain("Glass-Box-Solutions-Inc");
      expect(result.durationMs).toBeGreaterThanOrEqual(0);
      expect(result.details?.org).toBe("Glass-Box-Solutions-Inc");
    });

    it("returns passed=false when org is not accessible", async () => {
      mockOctokitInstance.rest.orgs.get.mockRejectedValue(
        new Error("Bad credentials"),
      );

      const result = await validator.checkConnectivity();

      expect(result.passed).toBe(false);
      expect(result.message).toContain("Bad credentials");
      expect(result.durationMs).toBeGreaterThanOrEqual(0);
    });
  });

  describe("validateSchemas", () => {
    it("returns all checks passed for valid responses", async () => {
      // Mock org response
      mockOctokitInstance.rest.orgs.get.mockResolvedValue({
        data: {
          login: "Glass-Box-Solutions-Inc",
          id: 12345,
          node_id: "O_abc123",
          url: "https://api.github.com/orgs/Glass-Box-Solutions-Inc",
          repos_url:
            "https://api.github.com/orgs/Glass-Box-Solutions-Inc/repos",
          description: "Glass Box Solutions",
          name: "Glass Box Solutions, Inc.",
          company: null,
          blog: "",
          location: null,
          email: null,
          public_repos: 10,
          followers: 5,
          following: 0,
          created_at: "2023-01-01T00:00:00Z",
          updated_at: "2024-06-01T00:00:00Z",
          type: "Organization",
        },
      });

      // Mock repos response
      mockOctokitInstance.rest.repos.listForOrg.mockResolvedValue({
        data: [
          {
            id: 1,
            node_id: "R_abc",
            name: "test-repo",
            full_name: "Glass-Box-Solutions-Inc/test-repo",
            private: true,
            owner: { login: "Glass-Box-Solutions-Inc", id: 12345 },
            html_url:
              "https://github.com/Glass-Box-Solutions-Inc/test-repo",
            description: "A test repo",
            fork: false,
            created_at: "2023-01-01T00:00:00Z",
            updated_at: "2024-06-01T00:00:00Z",
            pushed_at: "2024-06-01T00:00:00Z",
            default_branch: "main",
            visibility: "private",
            language: "TypeScript",
            archived: false,
          },
        ],
      });

      // Mock rate limit response
      mockOctokitInstance.rest.rateLimit.get.mockResolvedValue({
        data: {
          resources: {
            core: {
              limit: 5000,
              remaining: 4950,
              reset: 1700000000,
              used: 50,
            },
            search: {
              limit: 30,
              remaining: 29,
              reset: 1700000000,
              used: 1,
            },
          },
          rate: {
            limit: 5000,
            remaining: 4950,
            reset: 1700000000,
            used: 50,
          },
        },
      });

      const results = await validator.validateSchemas();

      expect(results).toHaveLength(3);
      expect(results.every((r) => r.passed)).toBe(true);
      expect(results.map((r) => r.name)).toEqual([
        "schema:org",
        "schema:repos",
        "schema:rateLimit",
      ]);
    });

    it("reports schema mismatch for invalid org response", async () => {
      // Return an object missing required fields
      mockOctokitInstance.rest.orgs.get.mockResolvedValue({
        data: {
          login: "Glass-Box-Solutions-Inc",
          // Missing id, node_id, url, etc.
        },
      });

      mockOctokitInstance.rest.repos.listForOrg.mockResolvedValue({
        data: [],
      });

      mockOctokitInstance.rest.rateLimit.get.mockResolvedValue({
        data: {
          resources: {
            core: {
              limit: 5000,
              remaining: 4950,
              reset: 1700000000,
              used: 50,
            },
            search: {
              limit: 30,
              remaining: 29,
              reset: 1700000000,
              used: 1,
            },
          },
          rate: {
            limit: 5000,
            remaining: 4950,
            reset: 1700000000,
            used: 50,
          },
        },
      });

      const results = await validator.validateSchemas();
      const orgCheck = results.find((r) => r.name === "schema:org");

      expect(orgCheck).toBeDefined();
      expect(orgCheck!.passed).toBe(false);
      expect(orgCheck!.message).toContain("schema mismatch");
    });

    it("handles API errors gracefully", async () => {
      mockOctokitInstance.rest.orgs.get.mockRejectedValue(
        new Error("API rate limit exceeded"),
      );
      mockOctokitInstance.rest.repos.listForOrg.mockRejectedValue(
        new Error("API rate limit exceeded"),
      );
      mockOctokitInstance.rest.rateLimit.get.mockRejectedValue(
        new Error("API rate limit exceeded"),
      );

      const results = await validator.validateSchemas();

      expect(results).toHaveLength(3);
      expect(results.every((r) => !r.passed)).toBe(true);
      expect(
        results.every((r) =>
          r.message.includes("API rate limit exceeded"),
        ),
      ).toBe(true);
    });
  });

  describe("checkPermissions", () => {
    it("reports all scopes present when fully authorized", async () => {
      mockOctokitInstance.rest.orgs.get.mockResolvedValue({
        data: { login: "Glass-Box-Solutions-Inc" },
      });
      mockOctokitInstance.rest.repos.listForOrg.mockResolvedValue({
        data: [{ name: "private-repo" }],
      });
      mockOctokitInstance.rest.orgs.listMembers.mockResolvedValue({
        data: [{ login: "user1" }],
      });

      const result = await validator.checkPermissions();

      expect(result.systemName).toBe("github");
      expect(result.hasAccess).toBe(true);
      expect(result.scopes).toContain("read:org");
      expect(result.scopes).toContain("repo");
      expect(result.scopes).toContain("read:org:members");
      expect(result.missingScopes).toHaveLength(0);
    });

    it("reports missing scopes on permission errors", async () => {
      mockOctokitInstance.rest.orgs.get.mockResolvedValue({
        data: { login: "Glass-Box-Solutions-Inc" },
      });
      mockOctokitInstance.rest.repos.listForOrg.mockRejectedValue(
        new Error("Resource not accessible"),
      );
      mockOctokitInstance.rest.orgs.listMembers.mockRejectedValue(
        new Error("Resource not accessible"),
      );

      const result = await validator.checkPermissions();

      expect(result.hasAccess).toBe(false);
      expect(result.scopes).toContain("read:org");
      expect(result.missingScopes).toContain("repo");
      expect(result.missingScopes).toContain("read:org:members");
    });
  });

  describe("validate (full orchestration)", () => {
    it("returns not-configured result when token is missing", async () => {
      // Create a new instance that reports unconfigured
      const unconfiguredValidator = Object.create(
        GitHubValidator.prototype,
      );
      unconfiguredValidator.systemName = "github";
      unconfiguredValidator.systemLabel = "GitHub";
      unconfiguredValidator.isConfigured = () => false;

      // Use the base class validate method
      const result = await unconfiguredValidator.validate();

      expect(result.configured).toBe(false);
      expect(result.connectivity.passed).toBe(false);
      expect(result.connectivity.message).toContain("Not configured");
      expect(result.schema).toHaveLength(0);
      expect(result.permissions.hasAccess).toBe(false);
    });

    it("skips schema and permissions when connectivity fails", async () => {
      mockOctokitInstance.rest.orgs.get.mockRejectedValue(
        new Error("Network error"),
      );

      const result = await validator.validate();

      expect(result.configured).toBe(true);
      expect(result.connectivity.passed).toBe(false);
      expect(result.schema).toHaveLength(0);
      expect(result.permissions.hasAccess).toBe(false);
      expect(result.latency.samples).toHaveLength(0);
    });
  });
});
