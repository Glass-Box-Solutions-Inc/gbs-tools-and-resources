/**
 * L2.4 durable reversal store barrel (GLY-337). Internal surface — the durable store and its dev
 * seam are wired by the composition factory (production injects the Azure impls at G4). The
 * capability-tight PUBLIC root (`src/index.ts`) deliberately does NOT re-export the concrete store
 * or dev impls; it exposes only the port TYPES (for a production consumer to type its injection).
 */
export { DurableReversalStore } from "./durable-reversal-store";
export {
  buildReversalAad,
  MATTER_EXPIRES_AT,
  type ReversalAadFields,
} from "./aad";
export {
  bytesEqual,
  DEK_BYTES,
  NONCE_BYTES,
  gcmDecrypt,
  gcmEncrypt,
  type GcmSealed,
} from "./envelope";
export {
  dekBindingDigestOf,
  dekGenerationIdOf,
  idempotencyKeyOf,
  mappingKeyOf,
  scopeDigestOf,
} from "./keys";
export {
  InMemoryKeyProvider,
  type InMemoryKeyProviderOptions,
} from "./dev/in-memory-key-provider";
export {
  InMemoryReversalSpoolBackend,
  InMemoryReversalSpoolVolume,
  type SpoolFaults,
  type SpoolFaultPhase,
} from "./dev/in-memory-spool-volume";

export type {
  AadBindingDigest,
  DekGeneration,
  DekGenerationId,
  DekMaterial,
  DurableReversalRecordMeta,
  DurableReversalStoreDependencies,
  EncryptedReversalRecordBlob,
  EnsureDekGenerationInput,
  GcmNonce96,
  KeyProvider,
  NonceReservationInput,
  PrepareReversalWriteInput,
  PreparedReversalWrite,
  PreparedWriteHandle,
  PublishReversalResult,
  PublishedCommitHandle,
  ReversalIdempotencyKey,
  ReversalLookupRequest,
  ReversalLookupResult,
  ReversalMappingKey,
  ReversalRetentionClass,
  ReversalScopeDigest,
  RetentionClassificationInput,
  SpoolVolume,
  UnwrapDekInput,
  WrapDekInput,
  WrappedDekMaterial,
  WrappingKeyHandle,
  WrappingKeyId,
  WrappingKeyScope,
  WrappingKeyVersion,
} from "./ports";
