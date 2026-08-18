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

/**
 * A logging plane that could observe request/response bodies on the egress path. Each plane
 * attests INDEPENDENTLY that body logging is disabled, so a single global flag can never stand
 * in for a plane that still logs (R2/T-M: prove truth, not shape).
 */
export type EgressLoggingPlane =
  | "APP_INSIGHTS"
  | "CONTAINER_APP_SYSTEM_LOGS"
  | "PROVIDER_SDK"
  | "PHILEAS_SIDECAR"
  | "INGRESS_GATEWAY";

/** Per-plane attestation that a specific logging plane does not log request/response bodies. */
export interface LoggingPlaneBodyAttestation {
  readonly plane: EgressLoggingPlane;
  /** Literal `true`: a plane that still logs bodies is structurally unrepresentable here. */
  readonly bodyLoggingDisabled: true;
}

/**
 * Detached signature over the canonical evidence claims, produced by the M4 deploy-time attestor.
 * The verifier (M3, N7 layer 3) rejects evidence whose signature is absent, unverifiable under
 * `issuer`/`keyId`, or does not cover `signedClaimsDigest` — this is what makes the evidence
 * self-authenticating rather than merely well-shaped.
 */
export interface EgressEvidenceSignature {
  /** Attestor service identity that SIGNED the evidence — never the service being attested. */
  readonly issuer: string;
  /** Signing key / certificate id, for trust-anchor lookup and key rotation. */
  readonly keyId: string;
  readonly algorithm: "ES256" | "RS256" | "EdDSA";
  /** Base64 signature bytes over `signedClaimsDigest`. */
  readonly value: string;
  /** Digest of the exact claim set the signature covers; binds every field below into the signature. */
  readonly signedClaimsDigest: string;
}

/**
 * Deploy-time proof that the egress network/logging posture in `cae-gbs-wp` actually holds
 * (CONTRACT-phase1 §9 layer 3; roadmap M3/M4; R2 finding T-M). This shape proves TRUTH, not
 * shape: the hardening fields let a consumer REJECT evidence that is stale, self-issued,
 * replayed, or bound to a different deployment/image — not merely observe that the expected
 * booleans are present (the R2/T-M weakness of the original shape).
 *
 * SEAM (GLY-335 Wave 0 seam-freeze): frozen as ONE hardened shape that M3 VERIFIES (N7 layer 3)
 * and M4 EMITS. Populating and SIGNING it is the M4 attestor lane; this seam-freeze authors the
 * TYPE + doc only. Per §9 no field here is ever assumed from application tests.
 *
 * 2026-08-18 — GLY-353 additive amendment: egressPolicyVersion and enginePolicyVersion are
 * required signed claims; RFC 8785/SHA-256 canonicalization is normative. The original GLY-335
 * seam freeze remains in force.
 */
export interface AzureEgressPolicyEvidence {
  readonly environment: "cae-gbs-wp";
  readonly protectedServiceIdentity: string;
  readonly providerHostsReachableOnlyByProtectedIdentity: true;
  readonly phileasHasPublicIngress: false;
  readonly phileasHasGcpRoute: false;
  /**
   * Retained global body-logging flag. Superseded for verification by the per-plane
   * `loggingPlanes` attestations below, which a single global boolean cannot substitute for.
   */
  readonly requestBodyLoggingDisabled: true;
  readonly checkedAt: string;
  readonly deploymentDigest: string;

  // --- GLY-335 Wave 0 hardening (R2/T-M). Populated + signed by the M4 attestor lane. ---
  /** Container image digest the evidence is bound to; verified TOGETHER with `deploymentDigest`. */
  readonly imageDigest: string;
  /** Freshness window start — when the attestor observed this posture. */
  readonly issuedAt: string;
  /** Freshness window end — evidence outside [`issuedAt`, `expiresAt`] is rejected as stale. */
  readonly expiresAt: string;
  /** Single-use anti-replay nonce, bound into the signature; a replayed nonce is rejected. */
  readonly nonce: string;
  /**
   * Egress is deny-by-default (default-deny network policy) — a STRONGER guarantee than the
   * `phileasHasGcpRoute: false` allow-list negation: no route exists unless explicitly allowed.
   */
  readonly denyByDefaultEgress: true;
  /** Per-logging-plane body-logging attestations; every egress-observing plane must be present. */
  readonly loggingPlanes: readonly LoggingPlaneBodyAttestation[];
  /** Immutable revision of the attestor's observed egress posture. */
  readonly egressPolicyVersion: string;
  /**
   * `sha256:<64 lowercase hex>` digest of normalized engine mode + BAA matrix consumer boot
   * configuration. The attestor binds this supplied value but need not observe the matrix.
   */
  readonly enginePolicyVersion: string;
  /** Attestor signature + issuer identity binding all fields above (rejects self-issued/forged). */
  readonly signature: EgressEvidenceSignature;
}

/** Exact claims covered by `signature`; the signature object itself is never in its own digest. */
export type AzureEgressPolicySignedClaims = Omit<AzureEgressPolicyEvidence, "signature">;
