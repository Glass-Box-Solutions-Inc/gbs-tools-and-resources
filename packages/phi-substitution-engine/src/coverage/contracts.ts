export type EgressSurfaceClassification = "ENGINE_COVERED" | "REVIEWED_CARVE_OUT";

export interface SourceSymbolRef {
  readonly repository: "glassy-user-production" | "adjudica-ai-app";
  readonly file: string;
  readonly symbol: string;
}

export interface EngineCoveredSurface {
  readonly classification: "ENGINE_COVERED";
  readonly id: string;
  readonly source: SourceSymbolRef;
  readonly operation: "generation" | "stream" | "embedding" | "graph_extraction";
  readonly protectedBoundary: string;
}

export interface ReviewedCarveOutSurface {
  readonly classification: "REVIEWED_CARVE_OUT";
  readonly id: string;
  readonly source: SourceSymbolRef;
  readonly kind: "MULTIMODAL_IMAGE" | "NON_LLM_EGRESS";
  readonly mitigation: readonly ("BAA_PROVIDER" | "MINIMUM_NECESSARY" | "SEPARATE_TICKET")[];
  readonly reviewDecisionId: string;
  readonly expiresAt: string | null;
}

export type EgressSurface = EngineCoveredSurface | ReviewedCarveOutSurface;

export interface EgressSurfaceRegistry {
  readonly schemaVersion: 1;
  readonly surfaces: readonly EgressSurface[];
}

export interface DiscoveredEgressSite {
  readonly source: SourceSymbolRef;
  readonly evidence: "PROVIDER_IMPORT" | "SDK_CONSTRUCTION" | "RAW_FETCH" | "MODEL_HANDLE" | "KNOWN_ADAPTER_CALL";
  readonly providerHostOrPackage: string;
}

export interface SurfaceRegistryVerifier {
  /** Fails for zero matches, multiple matches, stale file/symbol refs, or an expired carve-out. */
  verify(input: Readonly<{
    registry: EgressSurfaceRegistry;
    discovered: readonly DiscoveredEgressSite[];
  }>): Readonly<{
    ok: boolean;
    diagnostics: readonly Readonly<{
      code:
        | "UNREGISTERED_EGRESS"
        | "MULTIPLY_CLASSIFIED_EGRESS"
        | "STALE_REGISTRY_SYMBOL"
        | "EXPIRED_CARVE_OUT";
      surfaceId: string | null;
      source: SourceSymbolRef;
    }>[];
  }>;
}

export interface ProviderEgressArchitecturePolicy {
  readonly protectedModuleRoots: readonly string[];
  readonly forbiddenImports: readonly string[];
  readonly forbiddenConstructors: readonly string[];
  readonly deniedProviderHosts: readonly string[];
}

export interface ProviderEgressArchitectureVerifier {
  verify(policy: ProviderEgressArchitecturePolicy): Promise<Readonly<{
    ok: boolean;
    violations: readonly Readonly<{
      file: string;
      line: number;
      rule: "RAW_IMPORT" | "SDK_CONSTRUCTION" | "RAW_PROVIDER_FETCH" | "RAW_MODEL_HANDLE";
    }>[];
  }>>;
}

/** Evidence emitted by deploy-policy checks, never assumed from application tests. */
export interface AzureEgressPolicyEvidence {
  readonly environment: "cae-gbs-wp";
  readonly protectedServiceIdentity: string;
  readonly providerHostsReachableOnlyByProtectedIdentity: true;
  readonly phileasHasPublicIngress: false;
  readonly phileasHasGcpRoute: false;
  readonly requestBodyLoggingDisabled: true;
  readonly checkedAt: string;
  readonly deploymentDigest: string;
}
