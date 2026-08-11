/**
 * N7 total LLM-egress coverage — contract oracles for the four enforcement
 * layers (CONTRACT §5 N7, §9). Framework-free: this package supplies the types,
 * fixtures, and checkable predicates; product repositories run the real gates.
 */
export type * from "./contracts";

export {
  DEFAULT_EGRESS_POLICY,
  isProtectedModule,
  extractHostnames,
  hostIsDenied,
  lintProviderHostEgress,
  checkRawConstruction,
  type EgressLintInput,
  type EgressLintResult,
  type RawConstructionInput,
  type RawConstructionResult,
} from "./egress-policy";

export {
  sameSource,
  StaticSurfaceRegistryVerifier,
  type StaticSurfaceRegistryVerifierOptions,
} from "./surface-registry";

export { CANONICAL_DISCOVERED, CANONICAL_REGISTRY } from "./canonical";

export {
  classifyMultimodalCarveOut,
  type CarveOutMitigation,
  type MultimodalCarveOutInput,
  type MultimodalCarveOutResult,
} from "./multimodal";
