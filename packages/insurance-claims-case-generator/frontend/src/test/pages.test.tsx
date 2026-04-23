/**
 * Smoke tests — verify each page renders without crashing.
 *
 * Uses vi.mock to stub Next.js navigation hooks so components can render
 * outside a full Next.js runtime.
 *
 * @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";

// ---------------------------------------------------------------------------
// Stub Next.js navigation
// ---------------------------------------------------------------------------

const mockPush = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush, replace: vi.fn() }),
  usePathname: () => "/",
  useParams: () => ({ id: "test-job-id-1234" }),
  useSearchParams: () => ({
    get: (_key: string) => null,
  }),
}));

// Stub the API client — all calls resolve to sensible defaults
vi.mock("@/lib/api/client", () => ({
  listScenarios: vi.fn().mockResolvedValue([
    {
      slug: "standard_claim",
      display_name: "Standard Accepted Claim",
      description: "A straightforward accepted claim.",
      litigated: false,
      attorney_represented: false,
      ct: false,
      denied_scenario: false,
      death_claim: false,
      ptd_claim: false,
      psych_overlay: false,
      multi_employer: false,
      split_carrier: false,
      high_liens: false,
      sjdb_dispute: false,
      expedited: false,
      investigation_active: false,
      expected_doc_min: 8,
      expected_doc_max: 14,
    },
  ]),
  generateCase: vi.fn().mockResolvedValue({
    case_id: "case-abc-123",
    scenario_slug: "standard_claim",
    seed: 42,
    document_count: 10,
    stages_visited: ["intake"],
    document_events: [],
    zip_size_bytes: 12345,
  }),
  submitBatch: vi.fn().mockResolvedValue({
    job_id: "batch-xyz-456",
    status: "pending",
    total: 10,
    message: "Batch submitted",
  }),
  getJobStatus: vi.fn().mockResolvedValue({
    job_id: "test-job-id-1234",
    status: "running",
    progress: 50,
    total: 10,
    completed: 5,
    error: null,
  }),
  exportUrl: vi.fn((id: string) => `http://localhost:8001/api/v1/export/${id}`),
  getHealth: vi.fn().mockResolvedValue({ status: "ok", version: "1.0.0", scenario_count: 13, active_jobs: 0 }),
}));

// Stub next/link (simple anchor)
vi.mock("next/link", () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));

// ---------------------------------------------------------------------------
// Import pages after mocks are established
// ---------------------------------------------------------------------------

import ScenariosPage from "@/app/page";
import GeneratePage from "@/app/generate/page";
import BatchPage from "@/app/batch/page";
import JobStatusPage from "@/app/jobs/[id]/page";

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.clearAllMocks();
});

describe("Scenarios page (Home)", () => {
  it("renders without crashing", async () => {
    const { container } = render(<ScenariosPage />);
    expect(container).toBeTruthy();
  });

  it("shows a loading spinner initially", () => {
    render(<ScenariosPage />);
    // The spinner or loading state should be present while the API resolves
    const spinners = document.querySelectorAll(".animate-spin");
    expect(spinners.length).toBeGreaterThan(0);
  });
});

describe("Generate page", () => {
  it("renders without crashing", () => {
    const { container } = render(<GeneratePage />);
    expect(container).toBeTruthy();
  });

  it("shows the Generate Case heading area", () => {
    render(<GeneratePage />);
    // The form should render — check for the submit button text
    expect(document.body.textContent).toContain("Generate Case");
  });
});

describe("Batch page", () => {
  it("renders without crashing", () => {
    const { container } = render(<BatchPage />);
    expect(container).toBeTruthy();
  });

  it("shows total cases slider section", () => {
    render(<BatchPage />);
    expect(document.body.textContent).toContain("Total Cases");
  });
});

describe("Job status page", () => {
  it("renders without crashing", () => {
    const { container } = render(<JobStatusPage />);
    expect(container).toBeTruthy();
  });

  it("shows a loading spinner while status loads", () => {
    render(<JobStatusPage />);
    const spinners = document.querySelectorAll(".animate-spin");
    expect(spinners.length).toBeGreaterThan(0);
  });
});
