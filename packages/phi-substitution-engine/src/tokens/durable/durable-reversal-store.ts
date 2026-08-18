/**
 * Durable, tenant-scoped, envelope-encrypted reversal store (GLY-337 L2.4).
 *
 * The §6 productionization of the reversal WRITE seam (GLY-335 Wave 0). It is a behavior-preserving
 * swap-in for `InMemoryReversalStore` at the orchestrator's `ReversalWriteStore` port: same public
 * surface (`maximumEncounteredTokenBatch`, `record`, `resolveEncounteredTokens`), same partial-map
 * read semantics (addendum C2), same attempt-idempotency (frozen `ReversalRecordInput`) — but every
 * mapping is AES-256-GCM envelope-encrypted under a per-(tenant,matter) DEK and made DURABLE before
 * `record()` resolves, so a token can never egress without exactly one durable reversible mapping.
 *
 * Public surface is EXACTLY the three members `ReversalWriteStore` requires. There is deliberately no
 * `listAll` / `snapshot` / `export` / raw getter / `delete` / diagnostics (§7/N2; `MUT-WIDEN-LISTALL`).
 *
 * Sensitive state discipline (§7/N2, req 19): the unwrapped-DEK cache is a native ECMAScript
 * `#private` field (`MUT-TS-PRIVATE-DEK-CACHE`); the plaintext canonical is only ever a lexical local
 * (never cached, never a field); wrapped-key material rides in the durable blob, never on `this`.
 *
 * Threat model (CONTRACT/THREAT-MODEL.md): defends accidental egress + returned-surface tampering.
 * It does NOT defend against a first-party consumer replacing JS global intrinsics — out of scope.
 */
import { createHash, randomBytes } from "node:crypto";
import type { ReversalRecordInput, ReversalWriteStore } from "../../core/contracts";
import type {
  DictionaryVersion,
  MatterId,
  SubstitutionToken,
  TenantId,
} from "../../core/brands";
import { ReversalFailedError } from "../errors";
import { buildReversalAad, MATTER_EXPIRES_AT } from "./aad";
import { bytesEqual, DEK_BYTES, gcmDecrypt, gcmEncrypt } from "./envelope";
import { dekBindingDigestOf, dekGenerationIdOf, idempotencyKeyOf, mappingKeyOf, scopeDigestOf } from "./keys";
import type {
  DekMaterial,
  DurableReversalStoreDependencies,
  EncryptedReversalRecordBlob,
  KeyProvider,
  ReversalRetentionClass,
  RetentionClassificationInput,
  SpoolVolume,
  WrappedDekMaterial,
  WrappingKeyHandle,
  WrappingKeyScope,
} from "./ports";

/** §6 / roadmap A#5/D5: detector-only mappings expire 24h after creation. */
const DETECTOR_TTL_MS = 86_400_000n;
const DEFAULT_DEK_CACHE_MAX_ENTRIES = 256;
const DEFAULT_DEK_CACHE_TTL_MS = 15 * 60 * 1_000;
const MAX_TIMER_DELAY_MS = 2_147_483_647;

interface DekCacheEntry {
  /** Owned by the cache and never handed to an operation by reference. */
  readonly bytes: Uint8Array;
  readonly expiresAtEpochMs: number;
}

/**
 * Internal-only configuration. The dependency port and the store's published constructor signature
 * stay seam-frozen; tests/composition roots that need tighter bounds may structurally add this
 * optional member to the constructor input without changing any existing caller.
 */
interface DurableReversalStoreInternalDependencies extends DurableReversalStoreDependencies {
  readonly dekCacheOptions?: Readonly<{
    readonly maxEntries?: number;
    readonly ttlMs?: number;
  }>;
}

export class DurableReversalStore implements ReversalWriteStore {
  /** The ONLY public own property (required by `ReversalStore`). A number — nothing sensitive. */
  public readonly maximumEncounteredTokenBatch: number;

  // §7/N2 (req 19): every sensitive/held reference is a native `#private` slot. The DEK cache holds
  // UNWRAPPED DEK bytes and MUST be a `#`-field, not a TS-`private` one (which stays reflectively
  // enumerable at runtime under ES2022) — downgrading it to TS-private is `MUT-TS-PRIVATE-DEK-CACHE`.
  readonly #keyProvider: KeyProvider;
  readonly #spool: SpoolVolume;
  readonly #classifyRetention: (input: RetentionClassificationInput) => Promise<ReversalRetentionClass>;
  readonly #nowEpochMilliseconds: () => number;
  readonly #dekCache = new Map<string, DekCacheEntry>();
  readonly #dekCacheMaxEntries: number;
  readonly #dekCacheTtlMs: number;
  #dekCacheExpiryTimer: ReturnType<typeof setTimeout> | undefined;

  public constructor(dependencies: DurableReversalStoreDependencies) {
    const internalDependencies = dependencies as DurableReversalStoreInternalDependencies;
    const maxEntries = internalDependencies.dekCacheOptions?.maxEntries ?? DEFAULT_DEK_CACHE_MAX_ENTRIES;
    const ttlMs = internalDependencies.dekCacheOptions?.ttlMs ?? DEFAULT_DEK_CACHE_TTL_MS;
    if (!Number.isSafeInteger(maxEntries) || maxEntries < 0) {
      throw new RangeError("dek_cache_max_entries_must_be_a_nonnegative_safe_integer");
    }
    if (!Number.isFinite(ttlMs) || ttlMs < 0) {
      throw new RangeError("dek_cache_ttl_ms_must_be_a_nonnegative_finite_number");
    }
    this.#keyProvider = dependencies.keyProvider;
    this.#spool = dependencies.spoolVolume;
    this.#classifyRetention = dependencies.classifyRetention;
    this.#nowEpochMilliseconds = dependencies.nowEpochMilliseconds;
    this.#dekCacheMaxEntries = maxEntries;
    this.#dekCacheTtlMs = ttlMs;
    this.maximumEncounteredTokenBatch = dependencies.maximumEncounteredTokenBatch;
  }

  /**
   * Durably record `token → current canonical` (§6, N5). Resolves ONLY after encrypt → prepare →
   * atomic publish → durable flush all succeed, so the orchestrator's `await record(...)` gates
   * provider egress on durability. ANY failure rejects with the fixed, safe `REVERSAL_FAILED`
   * surface — no `cause`, no canonical/token/tenant/provider/db/path/ciphertext/nonce/key text.
   */
  public async record(input: ReversalRecordInput): Promise<void> {
    try {
      // Snapshot ALL boundary input INSIDE the scrub boundary (finding F3-boundary): a throwing getter on
      // a passed-in field must reject with the fixed REVERSAL_FAILED surface, never escape carrying its
      // own message/cause/PHI. The plaintext canonical stays a lexical local — never a field.
      const canonical = input.canonical;
      const { tenantId, matterId, dictionaryVersion, token, attemptId } = input;
      // The durable store's idempotency key REQUIRES an attemptId (frozen ReversalRecordInput carries
      // it). A write without one cannot be made idempotent — fail closed.
      if (attemptId === undefined || (attemptId as unknown as string) === "") {
        throw new ReversalFailedError();
      }

      // Retention is a property of the OPERATION (attemptId), from trusted context — never inferred
      // from token/matter shape (addendum C3). Unknown/throwing → fail closed.
      const retentionClass = await this.#classifyRetention({ tenantId, matterId, attemptId });
      if (retentionClass !== "matter" && retentionClass !== "detector-only") {
        throw new ReversalFailedError();
      }

      // Captured ONCE before PREPARE (§6, roadmap D5).
      const createdAtEpochMs = this.#nowEpochMilliseconds();
      const expiresAtEpochMs =
        retentionClass === "detector-only" ? BigInt(createdAtEpochMs) + DETECTOR_TTL_MS : MATTER_EXPIRES_AT;

      const scope: WrappingKeyScope = { tenantId, matterId, purpose: "reversal-v1" };
      const keyHandle = await this.#keyProvider.getWrappingKey(scope);
      const dekGeneration = await this.#spool.ensureDekGeneration({
        scope,
        mint: async () => {
          const freshDek = randomBytes(DEK_BYTES) as unknown as DekMaterial;
          const bindingDigest = dekBindingDigestOf(scope, keyHandle);
          const wrappedDek = await this.#keyProvider.wrap({ scope, key: keyHandle, dek: freshDek, bindingDigest });
          return { dekGenerationId: dekGenerationIdOf(scope), wrappedDek };
        },
      });
      // Always encrypt under the WINNING durable generation's DEK (recovered by unwrapping its wrapped
      // form), so a lost mint race can never encrypt under a stale key.
      const dek = await this.#unwrapDek(scope, keyHandle, dekGeneration.dekGenerationId, dekGeneration.wrappedDek, keyHandle.keyVersion);

      const nonce = await this.#spool.reserveNonce({
        tenantId,
        matterId,
        dekGenerationId: dekGeneration.dekGenerationId,
      });

      const aad = buildReversalAad({
        tenantId,
        matterId,
        dictionaryVersion: dictionaryVersion.toString(),
        token,
        attemptId,
        retentionClass,
        createdAtEpochMs,
        expiresAtEpochMs,
        dekGenerationId: dekGeneration.dekGenerationId,
        wrappingKeyVersion: keyHandle.keyVersion,
      });

      const sealed = gcmEncrypt(dek, nonce, aad, Buffer.from(canonical, "utf8"));

      const blob: EncryptedReversalRecordBlob = {
        ciphertext: sealed.ciphertext,
        authTag: sealed.authTag,
        nonce,
        wrappedDek: dekGeneration.wrappedDek,
        dekGenerationId: dekGeneration.dekGenerationId,
        wrappingKeyId: keyHandle.keyId,
        wrappingKeyVersion: keyHandle.keyVersion,
        aad,
        meta: { tenantId, matterId, dictionaryVersion, token, attemptId, retentionClass, createdAtEpochMs, expiresAtEpochMs },
      };

      const idempotencyKey = idempotencyKeyOf(tenantId, attemptId, token);
      const mappingKey = mappingKeyOf(tenantId, matterId, dictionaryVersion, token);
      const scopeDigest = scopeDigestOf(tenantId, matterId, dictionaryVersion);

      const prepared = await this.#spool.prepare({
        idempotencyKey,
        mappingKey,
        immutableScopeDigest: scopeDigest,
        encryptedRecord: blob,
      });

      const published = await this.#spool.publish(prepared);
      if (published.kind === "existing") {
        // First-write-wins. A same-attempt replay whose associated scope diverges is rejected and
        // NEVER creates a second mapping (§3.1.3).
        if ((published.immutableScopeDigest as unknown as string) !== (scopeDigest as unknown as string)) {
          throw new ReversalFailedError();
        }
        // A same-attempt replay after detector expiry is non-retryable — the tombstone stands (§6).
        if (published.expired) {
          throw new ReversalFailedError();
        }
        // Valid same-scope replay (exact OR divergent canonical): flush the EXISTING commit before
        // acknowledging (covers a race with an incompletely-flushed first caller), keep the FIRST
        // canonical (never overwrite), and return a durable no-op.
        await this.#spool.flush(published.commit);
        return;
      }

      // First publication: durable flush BEFORE acknowledging — the token cannot egress until the
      // mapping survives process death / replica loss / remount. Removing this is MUT-RETURN-BEFORE-FLUSH.
      await this.#spool.flush(published.commit);
      return;
    } catch {
      // Fixed, safe surface only (C1 / finding F3). DISCARD every caught value — never inspect,
      // preserve, or re-throw it, not even a `ReversalFailedError` (an injected dependency can throw
      // one carrying a `cause` / provider / DB text). Always construct a FRESH error so no underlying
      // message, `cause`, or PHI can ride out. (MUT-LEAK-UNDERLYING-ERROR / contaminated-error oracle.)
      throw new ReversalFailedError();
    }
  }

  /**
   * Resolve encountered tokens to their current canonical values (§6, N5, addendum C2). Behavioral
   * PARITY with `InMemoryReversalStore`: a token that is missing OR expired is simply ABSENT from the
   * returned map (a partial map). It throws `REVERSAL_FAILED` ONLY on (a) a batch-size violation and
   * (b) a crypto-integrity failure (AAD mismatch / GCM tag = tamper). The reverser (`reverseText`)
   * enforces N5 all-or-nothing on absence and contains any throw. Returns a plain `Map` typed as a
   * `ReadonlyMap` (addendum C4 — parity with the dev store; not over-hardened).
   */
  public async resolveEncounteredTokens(
    input: Readonly<{
      tenantId: TenantId;
      matterId: MatterId;
      dictionaryVersion: DictionaryVersion;
      tokens: readonly SubstitutionToken[];
    }>,
  ): Promise<ReadonlyMap<SubstitutionToken, string>> {
    try {
      // Snapshot ALL boundary input INSIDE the scrub boundary (finding F3-boundary + resolve/record
      // symmetry). Read each passed-in SCOPE field ONCE into a local so a hostile flipping getter cannot
      // make the mapping-key scope diverge from the AAD-reconstruction scope, i.e. a TOCTOU confused-deputy
      // read (MUT-RESOLVE-SCOPE-TOCTOU). A throwing `length` getter or `tokens` iterator likewise rejects
      // with the fixed REVERSAL_FAILED surface, never escaping with its own message/cause/PHI.
      const { tenantId, matterId, dictionaryVersion } = input;
      // (a) Batch-size violation rejects BEFORE any I/O (parity with InMemoryReversalStore).
      if (input.tokens.length > this.maximumEncounteredTokenBatch) {
        throw new ReversalFailedError();
      }
      const resolved = new Map<SubstitutionToken, string>();
      const distinct: SubstitutionToken[] = [];
      const seen = new Set<string>();
      for (const token of input.tokens) {
        if (!seen.has(token)) {
          seen.add(token);
          distinct.push(token);
        }
      }
      if (distinct.length === 0) {
        return resolved;
      }

      const keyToToken = new Map<string, SubstitutionToken>();
      const requests = distinct.map((token) => {
        const mappingKey = mappingKeyOf(tenantId, matterId, dictionaryVersion, token);
        keyToToken.set(mappingKey as unknown as string, token);
        // Exact, TENANT-SCOPED key only. There is NO tenantless fallback (MUT-FALLBACK-TENANTLESS-LOOKUP).
        return { mappingKey };
      });

      const nowEpochMs = this.#nowEpochMilliseconds();
      const results = await this.#spool.readCurrent(requests);
      for (const result of results) {
        const token = keyToToken.get(result.mappingKey as unknown as string);
        if (token === undefined) {
          continue;
        }
        const canonical = await this.#openRecord(tenantId, matterId, dictionaryVersion, token, result.encryptedRecord, nowEpochMs);
        if (canonical !== undefined) {
          resolved.set(token, canonical);
        }
      }
      return resolved;
    } catch {
      // (b) crypto-integrity / tamper and any other (infra) failure fail closed identically (C1 / F3):
      // DISCARD the caught value and throw a FRESH fixed, safe surface — never a partial map on a
      // throw, never a preserved/`cause`-bearing error. (contaminated-error oracle.)
      throw new ReversalFailedError();
    }
  }

  /**
   * Open one durable record for a REQUESTED lookup key. Returns the canonical string, or `undefined`
   * when the record is expired (absent). THROWS `ReversalFailedError` on any tamper: an AAD that does
   * not byte-equal the reconstruction from the requested scope + authenticated metadata, or a GCM tag
   * failure. AAD is reconstructed from the REQUESTED tenant/matter/version/token (never merely from
   * stored metadata) plus the authenticated record metadata (§6, N5).
   */
  async #openRecord(
    tenantId: TenantId,
    matterId: MatterId,
    dictionaryVersion: DictionaryVersion,
    token: SubstitutionToken,
    blob: EncryptedReversalRecordBlob,
    nowEpochMs: number,
  ): Promise<string | undefined> {
    const expectedAad = buildReversalAad({
      tenantId,
      matterId,
      dictionaryVersion: dictionaryVersion.toString(),
      token,
      attemptId: blob.meta.attemptId,
      retentionClass: blob.meta.retentionClass,
      createdAtEpochMs: blob.meta.createdAtEpochMs,
      expiresAtEpochMs: blob.meta.expiresAtEpochMs,
      dekGenerationId: blob.dekGenerationId,
      wrappingKeyVersion: blob.wrappingKeyVersion,
    });
    // Byte-equality pre-check authenticates the full scope + metadata binding (catches relocation and
    // metadata tampering) before any unwrap/decrypt.
    if (!bytesEqual(expectedAad, blob.aad)) {
      throw new ReversalFailedError();
    }
    // Expired detector mapping → absent, WITHOUT unwrap/decrypt (§6; MUT-SKIP-READ-TTL removes this).
    if (BigInt(nowEpochMs) >= blob.meta.expiresAtEpochMs) {
      return undefined;
    }
    const scope: WrappingKeyScope = { tenantId, matterId, purpose: "reversal-v1" };
    const keyHandle: WrappingKeyHandle = { keyId: blob.wrappingKeyId, keyVersion: blob.wrappingKeyVersion, scope };
    const dek = await this.#unwrapDek(scope, keyHandle, blob.dekGenerationId, blob.wrappedDek, blob.wrappingKeyVersion);
    let plaintext: Uint8Array;
    try {
      // GCM verifies the reconstructed AAD + tag: a one-bit ciphertext/tag/AAD change throws
      // (MUT-IGNORE-GCM-TAG returns plaintext here instead).
      plaintext = gcmDecrypt(dek, blob.nonce, expectedAad, blob.ciphertext, blob.authTag);
    } catch {
      throw new ReversalFailedError();
    }
    return Buffer.from(plaintext).toString("utf8");
  }

  /**
   * Unwrap + cache the DEK. The cache identity is bound to the EXACT wrapped-key material — a sha256
   * fingerprint of `wrappedDek` PLUS the `wrappingKeyId`, alongside tenant/matter/generation/version
   * (Q5). `wrappedDek` and `wrappingKeyId` are NOT covered by the 10-field AAD, so binding the cache
   * key to them is what makes the WARM path fail closed identically to a cold read (finding F2): a
   * post-warm swap of the stored wrapped-key material misses the cache → re-authenticates via
   * `unwrap` → throws, instead of silently decrypting under the cached original DEK.
   */
  async #unwrapDek(
    scope: WrappingKeyScope,
    keyHandle: WrappingKeyHandle,
    dekGenerationId: string,
    wrappedDek: WrappedDekMaterial,
    wrappingKeyVersion: string,
  ): Promise<Uint8Array> {
    const cacheKey = createHash("sha256")
      .update(`${scope.tenantId}\0${scope.matterId}\0${dekGenerationId}\0${wrappingKeyVersion}\0${keyHandle.keyId}\0`, "utf8")
      .update(wrappedDek as unknown as Uint8Array)
      .digest("hex");
    const nowEpochMs = this.#nowEpochMilliseconds();
    this.#pruneExpiredDeks(nowEpochMs);
    const cached = this.#dekCache.get(cacheKey);
    if (cached !== undefined) {
      // Map insertion order is the LRU order. Promote on every hit.
      this.#dekCache.delete(cacheKey);
      this.#dekCache.set(cacheKey, cached);
      // Never expose the cache-owned bytes. A concurrent miss may evict/zero its own cache entry
      // while this operation is suspended at a later await; the operation's copy remains intact.
      return Buffer.from(cached.bytes);
    }
    const bindingDigest = dekBindingDigestOf(scope, keyHandle);
    const dek = await this.#keyProvider.unwrap({ scope, key: keyHandle, wrappedDek, bindingDigest });
    if ((dek as Uint8Array).byteLength !== DEK_BYTES) {
      throw new ReversalFailedError();
    }
    // The provider-returned allocation becomes cache-owned. Only a copy leaves this method, so
    // eviction can best-effort-zero the cached allocation without corrupting an in-flight operation.
    const cacheBytes = dek as unknown as Uint8Array;
    const operationBytes = Buffer.from(cacheBytes);

    if (this.#dekCacheMaxEntries === 0 || this.#dekCacheTtlMs === 0) {
      cacheBytes.fill(0);
      return operationBytes;
    }

    // Two concurrent cold misses can finish out of order. Replacing the first cache-owned allocation
    // must zero it before the second becomes authoritative.
    this.#evictDek(cacheKey);
    this.#dekCache.set(cacheKey, {
      bytes: cacheBytes,
      expiresAtEpochMs: this.#nowEpochMilliseconds() + this.#dekCacheTtlMs,
    });
    this.#evictLeastRecentlyUsedDeks();
    this.#scheduleDekCacheExpiry();
    return operationBytes;
  }

  #pruneExpiredDeks(nowEpochMs: number): void {
    for (const [cacheKey, entry] of this.#dekCache) {
      if (nowEpochMs >= entry.expiresAtEpochMs) {
        this.#evictDek(cacheKey);
      }
    }
  }

  #evictLeastRecentlyUsedDeks(): void {
    while (this.#dekCache.size > this.#dekCacheMaxEntries) {
      const leastRecentlyUsed = this.#dekCache.keys().next().value;
      if (leastRecentlyUsed === undefined) {
        return;
      }
      this.#evictDek(leastRecentlyUsed);
    }
  }

  #evictDek(cacheKey: string): void {
    const entry = this.#dekCache.get(cacheKey);
    if (entry === undefined) {
      return;
    }
    this.#dekCache.delete(cacheKey);
    // Defense-in-depth only: this overwrites the cache's live allocation, not copies the runtime,
    // crypto implementation, allocator, or process may have made.
    entry.bytes.fill(0);
  }

  #scheduleDekCacheExpiry(): void {
    if (this.#dekCacheExpiryTimer !== undefined) {
      clearTimeout(this.#dekCacheExpiryTimer);
      this.#dekCacheExpiryTimer = undefined;
    }
    let nextExpiry = Number.POSITIVE_INFINITY;
    for (const entry of this.#dekCache.values()) {
      nextExpiry = Math.min(nextExpiry, entry.expiresAtEpochMs);
    }
    if (!Number.isFinite(nextExpiry)) {
      return;
    }
    const delayMs = Math.min(
      MAX_TIMER_DELAY_MS,
      Math.max(0, nextExpiry - this.#nowEpochMilliseconds()),
    );
    this.#dekCacheExpiryTimer = setTimeout(() => {
      this.#dekCacheExpiryTimer = undefined;
      this.#pruneExpiredDeks(this.#nowEpochMilliseconds());
      this.#scheduleDekCacheExpiry();
    }, delayMs);
    // Cache hygiene must not keep an otherwise-idle process alive.
    this.#dekCacheExpiryTimer.unref();
  }
}
