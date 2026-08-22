/**
 * Deterministic key derivation for the durable reversal store (§6, L8). Every physical key is
 * TENANT-SCOPED (L8): tenant is present in the mapping key, the idempotency key, the scope digest,
 * and the DEK-generation id. There is no tenant-agnostic index — a tenantless fallback lookup is the
 * named mutation `MUT-FALLBACK-TENANTLESS-LOOKUP`.
 */
import { createHash } from "node:crypto";
import type {
  DictionaryVersion,
  MatterId,
  OperationAttemptId,
  SubstitutionToken,
  TenantId,
} from "../../core/brands";
import type {
  AadBindingDigest,
  DekGenerationId,
  ReversalIdempotencyKey,
  ReversalMappingKey,
  ReversalScopeDigest,
  WrappingKeyHandle,
  WrappingKeyScope,
} from "./ports";

/**
 * NUL fence.
 *
 * GLY-373 §3.2.2 — CORRECTED. The previous wording ("branded validated lexemes never contain NUL,
 * so the join is injective") asserted a property NOTHING ENFORCED: ingestion read these ids through
 * `safeString`, which checks `typeof value === "string"` and nothing else, so an embedded U+0000
 * passed. EXECUTED counterexample against these very join expressions: `("a", "b\u0000c")` and
 * `("a\u0000b", "c")` produce the IDENTICAL joined string, i.e. two distinct tenants aliasing onto
 * one reversal row — a live cross-tenant defect, not a hypothetical one.
 *
 * The join is now injective BECAUSE `assertTrustedContextIdShape` (`core/errors.ts`) rejects
 * NUL-bearing and ill-formed-UTF-16 routing ids at ALL THREE context-id entry points —
 * `#ingestContext`, the atomic `reverse()` handle, and the `createReverseStream` handle — before
 * any key is derived. That check, not this comment, is what establishes the property. The key
 * SHAPE is deliberately unchanged: changing it would invalidate every existing durable mapping row,
 * and it does not need to change once no NUL-bearing id can reach it.
 */
const SEP = "\0";

/** Logical reversal mapping identity (L8): `(tenant, matter, version, token)`. Tenant is FIRST and mandatory. */
export function mappingKeyOf(
  tenantId: TenantId,
  matterId: MatterId,
  dictionaryVersion: DictionaryVersion,
  token: SubstitutionToken,
): ReversalMappingKey {
  return `${tenantId}${SEP}${matterId}${SEP}${dictionaryVersion.toString()}${SEP}${token}` as unknown as ReversalMappingKey;
}

/** Idempotency identity (§3.1.3, §6): `(tenant, attempt, token)`. Matter/version are immutable associated scope. */
export function idempotencyKeyOf(
  tenantId: TenantId,
  attemptId: OperationAttemptId,
  token: SubstitutionToken,
): ReversalIdempotencyKey {
  return `${tenantId}${SEP}${attemptId}${SEP}${token}` as unknown as ReversalIdempotencyKey;
}

/** Immutable associated-scope digest bound to the idempotency claim; a divergent-scope replay is rejected. */
export function scopeDigestOf(
  tenantId: TenantId,
  matterId: MatterId,
  dictionaryVersion: DictionaryVersion,
): ReversalScopeDigest {
  const digest = createHash("sha256")
    .update(
      `${tenantId}${SEP}${matterId}${SEP}${dictionaryVersion.toString()}`,
      "utf8",
    )
    .digest("hex");
  return digest as unknown as ReversalScopeDigest;
}

/** v1 DEK-generation id: one generation per (tenant, matter). Rotation later carries a new suffix. */
export function dekGenerationIdOf(scope: WrappingKeyScope): DekGenerationId {
  return `${scope.tenantId}${SEP}${scope.matterId}${SEP}${scope.purpose}${SEP}gen-1` as unknown as DekGenerationId;
}

/**
 * Digest binding a DEK wrap to its scope + KEK identity/version. Passed to `KeyProvider.wrap`/`unwrap`
 * so a wrapped DEK cannot be unwrapped under a substituted scope or KEK version (fail closed).
 */
export function dekBindingDigestOf(
  scope: WrappingKeyScope,
  key: WrappingKeyHandle,
): AadBindingDigest {
  const digest = createHash("sha256")
    .update(
      `reversal-dek-wrap-v1${SEP}${scope.tenantId}${SEP}${scope.matterId}${SEP}${scope.purpose}${SEP}${key.keyId}${SEP}${key.keyVersion}`,
      "utf8",
    )
    .digest();
  return new Uint8Array(digest) as unknown as AadBindingDigest;
}
