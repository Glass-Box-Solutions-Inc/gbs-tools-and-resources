export type * from "./core/brands";
export type * from "./core/contracts";
export type * from "./core/protected-ai-provider";
export type * from "./core/original-egress-authorizer";
export type * from "./dictionary/contracts";
export type * from "./collision/ports";
export type * from "./tokens/ports";
export type * from "./tokens/durable/ports";
export type * from "./detectors/ports";
export type * from "./detectors/phileas-service-adapter";
export type * from "./audit/ports";
export type * from "./eval/contracts";
export type * from "./coverage/contracts";

// ===========================================================================
// Runtime root surface (GLY-336 M1, tightened after the GPT cross-family gate)
//
// TIGHT PUBLIC BOUNDARY. The runtime root exports ONLY: (1) the composition FACTORIES,
// (2) interface/option TYPES, and (3) fixed, PHI-free error classes/guards. It deliberately
// exports NO concrete internal class, primitive, or live policy object. Consumers compose via
// the factories, which wire the internals privately. Rationale (§7/N2): TypeScript `private` is
// NOT runtime-private — own named fields stay reflectively enumerable under ES2022 — so exporting
// a concrete store/handle/reverser, a mutable grammar policy, or a forgeable wrapper constructor
// each opens a PHI-egress path. Everything not listed below (ComposedSubstitutionEngine,
// ComposedProtectedAiProvider, InMemory* stores, InProcessReversalHandle, reverseText,
// AtomicTokenReverser, BracketTokenGrammar, SentinelSourceTokenEscaper, HoldbackReverseStreamFactory,
// the live grammar-policy constants, the dev seed) is INTENTIONALLY not a root export.
// ===========================================================================

// -- (1) Composition factories: the ONLY runtime entry points --
// `createTokensModule` is deliberately NOT re-exported (GLY-336 gate finding 4): it hands out the
// low-level reversal store / reverser / stream-factory capability. It stays internal for the
// factories; the production and development factories below are the whole public composition path.
export {
  createSubstitutionEngine,
  createProtectedAiProvider,
  createProductionProtectedAiProvider,
} from "./factory";
export { createProductionProtectedOriginalEgressAuthorizer } from "./core/original-egress-authorizer";

// -- (3) Fixed, PHI-free error surface (a consumer catches/inspects these) --
export { PhiEngineError, isPhiEngineError, isPhiEngineFailureCode } from "./core/errors";
export { ReversalFailedError, REVERSAL_FAILED } from "./tokens/errors";

// -- (2) Types only: factory option/result shapes. The provider/engine INTERFACES
//        (AiProvider, PhiSubstitutionEngine) and all brands come from the `export type *`
//        lines above; the boundary option shapes + the product-implemented raw-provider PORT
//        let a consumer name `generateText` args and inject a production provider. No concrete
//        class or live policy value is exported — only types. --
export type {
  CreateSubstitutionEngineOptions,
  DevSubstitutionEngine,
  CreateProtectedAiProviderOptions,
  DevProtectedAiProvider,
} from "./factory";
export type {
  BoundaryGenerateOptions,
  BoundaryMessage,
  BoundaryContentPart,
  BoundaryTool,
} from "./core/options-projector";
export type { RawProviderPort, ProtectedStreamResult } from "./core/wrapper";
