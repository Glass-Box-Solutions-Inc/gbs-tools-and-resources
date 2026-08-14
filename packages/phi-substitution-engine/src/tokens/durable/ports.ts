/**
 * L2.4 durable reversal store — dev/prod seam ports (GLY-337).
 *
 * The `DurableReversalStore` (§6 persistence, L8 tenant-scope, N5 reversal) depends ONLY on these
 * two ports, never on an Azure SDK or a filesystem client. The in-process dev implementations in
 * `./dev` let the oracles simulate replica-loss/remount, crash-injection between persistence phases,
 * and durable-flush. The Azure implementations (Azure Files Premium mount + Key Vault KEK) land at
 * G4 against these SAME interfaces; nothing in core imports an Azure type (CONTRACT §3.3).
 *
 * Two ports:
 *   - `KeyProvider` owns the KEK. It NEVER exposes the KEK to application memory; it only wraps and
 *     unwraps a per-(tenant,matter) 256-bit DEK. `WrappingKeyHandle` is a non-secret reference.
 *   - `SpoolVolume` owns the durable substrate: durable nonce reservation, the atomic PREPARE →
 *     PUBLISH → durable FLUSH protocol, exact-key bounded reads, and the v1 DEK-generation election
 *     (Q4 disposition: single DEK generation per (tenant,matter), its wrapped form persisted durably
 *     so a remounted replica recovers the same generation).
 */
import type { Brand, DictionaryVersion, MatterId, OperationAttemptId, SubstitutionToken, TenantId } from "../../core/brands";

/** 256-bit plaintext data-encryption key. Sensitive: only ever a lexical local or a `#private` cache slot. */
export type DekMaterial = Brand<Uint8Array, "DekMaterial">;
/** Opaque KEK-wrapped DEK bytes. Durable, non-secret-at-rest (only the KEK can unwrap). */
export type WrappedDekMaterial = Brand<Uint8Array, "WrappedDekMaterial">;
/** 96-bit AES-GCM nonce, durably and monotonically allocated per DEK generation. */
export type GcmNonce96 = Brand<Uint8Array, "GcmNonce96">;
/** Digest binding a wrap operation to its scope + KEK version (wrap-AAD substitute for backends without native wrap-AAD). */
export type AadBindingDigest = Brand<Uint8Array, "AadBindingDigest">;

export type WrappingKeyId = Brand<string, "WrappingKeyId">;
export type WrappingKeyVersion = Brand<string, "WrappingKeyVersion">;
export type DekGenerationId = Brand<string, "DekGenerationId">;

/** Opaque handles produced/consumed by the SpoolVolume; core never inspects their internals. */
export type PreparedWriteHandle = Brand<string, "PreparedWriteHandle">;
export type PublishedCommitHandle = Brand<string, "PublishedCommitHandle">;

/** Physical/logical keys, always tenant-scoped (L8). Opaque branded strings; only the store builds them. */
export type ReversalIdempotencyKey = Brand<string, "ReversalIdempotencyKey">;
export type ReversalMappingKey = Brand<string, "ReversalMappingKey">;
export type ReversalScopeDigest = Brand<string, "ReversalScopeDigest">;

/** §6 retention discriminator. Never carried by the frozen `ReversalRecordInput`; supplied by `classifyRetention`. */
export type ReversalRetentionClass = "matter" | "detector-only";

export interface RetentionClassificationInput {
  readonly tenantId: TenantId;
  readonly matterId: MatterId;
  readonly attemptId: OperationAttemptId;
}

// ---- KeyProvider ------------------------------------------------------------------------------

export interface WrappingKeyScope {
  readonly tenantId: TenantId;
  readonly matterId: MatterId;
  readonly purpose: "reversal-v1";
}

/** A non-secret reference to the wrapping key (KEK). The KEK itself never enters application memory. */
export interface WrappingKeyHandle {
  readonly keyId: WrappingKeyId;
  readonly keyVersion: WrappingKeyVersion;
  readonly scope: WrappingKeyScope;
}

export interface WrapDekInput {
  readonly scope: WrappingKeyScope;
  readonly key: WrappingKeyHandle;
  readonly dek: DekMaterial;
  readonly bindingDigest: AadBindingDigest;
}

export interface UnwrapDekInput {
  readonly scope: WrappingKeyScope;
  readonly key: WrappingKeyHandle;
  readonly wrappedDek: WrappedDekMaterial;
  readonly bindingDigest: AadBindingDigest;
}

export interface KeyProvider {
  getWrappingKey(scope: WrappingKeyScope): Promise<WrappingKeyHandle>;
  /** Binds the wrapped payload to `bindingDigest`; unwrap fails closed unless the same digest is presented. */
  wrap(input: WrapDekInput): Promise<WrappedDekMaterial>;
  unwrap(input: UnwrapDekInput): Promise<DekMaterial>;
}

// ---- SpoolVolume ------------------------------------------------------------------------------

/** The authenticated, tenant-scoped record metadata needed to reconstruct AAD on read (§6, L8). */
export interface DurableReversalRecordMeta {
  readonly tenantId: TenantId;
  readonly matterId: MatterId;
  readonly dictionaryVersion: DictionaryVersion;
  readonly token: SubstitutionToken;
  readonly attemptId: OperationAttemptId;
  readonly retentionClass: ReversalRetentionClass;
  readonly createdAtEpochMs: number;
  /** Detector: created + 86_400_000. Matter: MaxUint64 (`2n**64n - 1n`). */
  readonly expiresAtEpochMs: bigint;
}

/**
 * One durable envelope-encrypted reversal record (§6, L8). Every field the read path needs to
 * reconstruct + verify AAD and to unwrap+decrypt is present. `canonical` NEVER appears in plaintext
 * anywhere in this structure — only as `ciphertext`.
 */
export interface EncryptedReversalRecordBlob {
  readonly ciphertext: Uint8Array;
  readonly authTag: Uint8Array;
  readonly nonce: GcmNonce96;
  readonly wrappedDek: WrappedDekMaterial;
  readonly dekGenerationId: DekGenerationId;
  readonly wrappingKeyId: WrappingKeyId;
  readonly wrappingKeyVersion: WrappingKeyVersion;
  /** The exact AAD bytes (§B.6). Read path byte-compares its reconstruction to these before unwrap/decrypt. */
  readonly aad: Uint8Array;
  readonly meta: DurableReversalRecordMeta;
}

export interface NonceReservationInput {
  readonly tenantId: TenantId;
  readonly matterId: MatterId;
  readonly dekGenerationId: DekGenerationId;
}

export interface PreparedReversalWrite {
  readonly handle: PreparedWriteHandle;
}

export interface PrepareReversalWriteInput {
  readonly idempotencyKey: ReversalIdempotencyKey;
  readonly mappingKey: ReversalMappingKey;
  readonly immutableScopeDigest: ReversalScopeDigest;
  readonly encryptedRecord: EncryptedReversalRecordBlob;
}

export type PublishReversalResult =
  | Readonly<{ kind: "published"; commit: PublishedCommitHandle }>
  | Readonly<{
      kind: "existing";
      commit: PublishedCommitHandle;
      immutableScopeDigest: ReversalScopeDigest;
      /** True when the existing detector claim is past its expiry at publish time (drives non-retryable EXPIRED). */
      expired: boolean;
    }>;

export interface ReversalLookupRequest {
  readonly mappingKey: ReversalMappingKey;
}

export interface ReversalLookupResult {
  readonly mappingKey: ReversalMappingKey;
  readonly encryptedRecord: EncryptedReversalRecordBlob;
}

/**
 * The v1 DEK-generation election seam (sol §E Q4 disposition; addendum "single DEK generation per
 * (tenant,matter)"). First mint wins durably; every later caller — including a remounted replica —
 * receives the SAME `{dekGenerationId, wrappedDek}`, so all records for a (tenant,matter) share one
 * DEK generation and one durable nonce counter. The Azure impl persists the wrapped DEK as a
 * generation artifact on the mounted volume with atomic first-writer-wins semantics.
 */
export interface EnsureDekGenerationInput {
  readonly scope: WrappingKeyScope;
  readonly mint: () => Promise<{ readonly dekGenerationId: DekGenerationId; readonly wrappedDek: WrappedDekMaterial }>;
}

export interface DekGeneration {
  readonly dekGenerationId: DekGenerationId;
  readonly wrappedDek: WrappedDekMaterial;
}

export interface SpoolVolume {
  ensureDekGeneration(input: EnsureDekGenerationInput): Promise<DekGeneration>;

  /** Durably reserves a unique 96-bit nonce before returning. Gaps allowed; reuse forbidden across crashes/replicas. */
  reserveNonce(input: NonceReservationInput): Promise<GcmNonce96>;

  /** Persists a prepared encrypted record that is INVISIBLE to reads until published. */
  prepare(input: PrepareReversalWriteInput): Promise<PreparedReversalWrite>;

  /**
   * Atomically claims the idempotency key AND advances the current mapping as ONE transaction.
   * A crash may leave an unreachable prepared artifact but never a visible partial mapping.
   */
  publish(prepared: PreparedReversalWrite): Promise<PublishReversalResult>;

  /** Durable barrier over record content AND publication metadata. Insufficient: closing a file or userspace flush alone. */
  flush(commit: PublishedCommitHandle): Promise<void>;

  /** Exact-key, bounded. Rejects an empty/all selector and never iterates stored records. */
  readCurrent(requests: readonly ReversalLookupRequest[]): Promise<readonly ReversalLookupResult[]>;
}

// ---- DurableReversalStore dependencies --------------------------------------------------------

export interface DurableReversalStoreDependencies {
  readonly keyProvider: KeyProvider;
  readonly spoolVolume: SpoolVolume;
  /**
   * Identifier-only retention classifier (addendum C3 + C3-determinism amendment). A TRUSTED injected
   * seam. Receives identifiers ONLY — `{tenantId, matterId, attemptId}`, never canonical or token — so
   * it is operation-scoped by construction. CONTRACT (relied on, not re-enforced by the store): it MUST
   * be DETERMINISTIC — identical `{tenantId, matterId, attemptId}` yields the SAME class for every
   * `record()` of an operation — so retention is "determined once, consistent across every record()"
   * without the store keeping cross-record state. Fail-closed on unknown/error (the store rejects). A
   * non-deterministic classifier is a misbehaving trusted dependency (out of the bounded threat model);
   * store-enforced operation-retention binding is a governance follow-up, not an M2 requirement.
   */
  readonly classifyRetention: (input: RetentionClassificationInput) => Promise<ReversalRetentionClass>;
  readonly nowEpochMilliseconds: () => number;
  readonly maximumEncounteredTokenBatch: number;
}
