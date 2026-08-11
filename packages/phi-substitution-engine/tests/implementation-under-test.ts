/**
 * The sole test-to-production wiring seam. The frozen contract intentionally ships red.
 * Each module implementer replaces its loader with a real adapter over production ports.
 */
export type { OracleObservation, ModuleHarness } from "./harness-types";

export { loadVariantsHarness } from "./loaders/variants.loader";
export { loadCollisionHarness } from "./loaders/collision.loader";
export { loadTokensHarness } from "./loaders/tokens.loader";
export { loadDictionaryHarness } from "./loaders/dictionary.loader";
export { loadAuditHarness } from "./loaders/audit.loader";
export { loadDetectorHarness } from "./loaders/detector.loader";
export { loadProviderBoundaryHarness } from "./loaders/provider-boundary.loader";
export { loadEvaluationHarness } from "./loaders/evaluation.loader";
export { loadCoverageHarness } from "./loaders/coverage.loader";
