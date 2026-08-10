/**
 * Canonical phase-1 egress surface registry and the matching discovered tree.
 *
 * These are the framework-free fixtures the total-classification oracle checks:
 * every discovered LLM-egress site is registered exactly once, engine-covered
 * text surfaces traverse the wrapper, and the multimodal image surface is a
 * reviewed carve-out (names remain pixels), not claimed text coverage.
 */
import type { DiscoveredEgressSite, EgressSurfaceRegistry } from "./contracts";

const GLASSY = "glassy-user-production" as const;
const ADJUDICA = "adjudica-ai-app" as const;
const PROTECTED_PROVIDER = "backend/src/modules/ai/protected-ai-provider.ts";

/** The live LLM-egress sites a tree scan would currently discover. */
export const CANONICAL_DISCOVERED: readonly DiscoveredEgressSite[] = [
  {
    source: { repository: GLASSY, file: PROTECTED_PROVIDER, symbol: "ProtectedAiProvider.generateText" },
    evidence: "KNOWN_ADAPTER_CALL",
    providerHostOrPackage: "openai.azure.com",
  },
  {
    source: { repository: GLASSY, file: PROTECTED_PROVIDER, symbol: "ProtectedAiProvider.generateStream" },
    evidence: "KNOWN_ADAPTER_CALL",
    providerHostOrPackage: "openai.azure.com",
  },
  {
    source: { repository: GLASSY, file: PROTECTED_PROVIDER, symbol: "ProtectedAiProvider.embedText" },
    evidence: "KNOWN_ADAPTER_CALL",
    providerHostOrPackage: "openai.azure.com",
  },
  {
    source: { repository: ADJUDICA, file: "src/graph/graph-extractor.ts", symbol: "GraphExtractor.extract" },
    evidence: "KNOWN_ADAPTER_CALL",
    providerHostOrPackage: "openai.azure.com",
  },
  {
    source: {
      repository: GLASSY,
      file: "backend/src/modules/vision/image-vision.service.ts",
      symbol: "ImageVisionService.describeImage",
    },
    evidence: "PROVIDER_IMPORT",
    providerHostOrPackage: "cognitiveservices.azure.com",
  },
];

/** The checked-in registry that must stay in exact 1:1 agreement with the tree. */
export const CANONICAL_REGISTRY: EgressSurfaceRegistry = {
  schemaVersion: 1,
  surfaces: [
    {
      classification: "ENGINE_COVERED",
      id: "ENG-GEN-001",
      source: { repository: GLASSY, file: PROTECTED_PROVIDER, symbol: "ProtectedAiProvider.generateText" },
      operation: "generation",
      protectedBoundary: "ProtectedAiProvider",
    },
    {
      classification: "ENGINE_COVERED",
      id: "ENG-STR-002",
      source: { repository: GLASSY, file: PROTECTED_PROVIDER, symbol: "ProtectedAiProvider.generateStream" },
      operation: "stream",
      protectedBoundary: "ProtectedAiProvider",
    },
    {
      classification: "ENGINE_COVERED",
      id: "ENG-EMB-003",
      source: { repository: GLASSY, file: PROTECTED_PROVIDER, symbol: "ProtectedAiProvider.embedText" },
      operation: "embedding",
      protectedBoundary: "ProtectedAiProvider",
    },
    {
      classification: "ENGINE_COVERED",
      id: "ENG-GRAPH-004",
      source: { repository: ADJUDICA, file: "src/graph/graph-extractor.ts", symbol: "GraphExtractor.extract" },
      operation: "graph_extraction",
      protectedBoundary: "ProtectedGraphExtractor",
    },
    {
      classification: "REVIEWED_CARVE_OUT",
      id: "CO-IMG-001",
      source: {
        repository: GLASSY,
        file: "backend/src/modules/vision/image-vision.service.ts",
        symbol: "ImageVisionService.describeImage",
      },
      kind: "MULTIMODAL_IMAGE",
      mitigation: ["BAA_PROVIDER", "MINIMUM_NECESSARY"],
      reviewDecisionId: "RVW-IMG-2026-01",
      expiresAt: null,
    },
  ],
};
