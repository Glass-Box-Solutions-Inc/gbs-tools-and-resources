gpt-5.6-sol

## A. Contract

The supplied ground truth omits the frozen `PhiEngineError` code registry. This specification therefore uses the normative aliases `WRITE_FAIL`, `RESOLVE_FAIL`, and `EXPIRED_FAIL`; Opus must bind each alias to exactly one pre-existing allowed code before implementation. No new error code may be invented without changing the frozen contract.

```ts
export type ReversalRetentionClass = "matter" | "detector-only";

export interface RetentionClassificationInput {
  readonly tenantId: TenantId;
  readonly matterId: MatterId;
  readonly attemptId: OperationAttemptId;
}

export interface DurableReversalStoreDependencies {
  readonly keyProvider: KeyProvider;
  readonly spoolVolume: SpoolVolume;

  /**
   * Required because frozen ReversalRecordInput carries no retention discriminator.
   * Receives identifiers only, never canonical or token.
   */
  readonly classifyRetention: (
    input: RetentionClassificationInput,
  ) => Promise<ReversalRetentionClass>;

  readonly nowEpochMilliseconds: () => number;
  readonly maximumEncounteredTokenBatch: number;
}

export declare class DurableReversalStore implements ReversalWriteStore {
  constructor(dependencies: DurableReversalStoreDependencies);

  readonly maximumEncounteredTokenBatch: number;

  record(input: ReversalRecordInput): Promise<void>;

  resolveEncounteredTokens(input: Readonly<{
    tenantId: TenantId;
    matterId: MatterId;
    dictionaryVersion: DictionaryVersion;
    tokens: readonly SubstitutionToken[];
  }>): Promise<ReadonlyMap<SubstitutionToken, string>>;
}
```

There are no other public instance methods. In particular: no `listAll`, `entriesForMatter`, `snapshot`, raw-record getter, export, diagnostics, cache accessor, delete, or unbounded query.

### `KeyProvider`

```ts
export interface WrappingKeyScope {
  readonly tenantId: TenantId;
  readonly matterId: MatterId;
  readonly purpose: "reversal-v1";
}

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
  wrap(input: WrapDekInput): Promise<WrappedDekMaterial>;
  unwrap(input: UnwrapDekInput): Promise<DekMaterial>;
}
```

`WrappingKeyHandle` is a non-secret reference. The KEK itself never enters application memory. `wrap` must bind the wrapped payload to `bindingDigest`; if the backend lacks native wrapping AAD, it must wrap a structured `DEK || bindingDigest` payload and verify the digest after unwrap.

### `SpoolVolume`

```ts
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
  | Readonly<{
      kind: "published";
      commit: PublishedCommitHandle;
    }>
  | Readonly<{
      kind: "existing";
      commit: PublishedCommitHandle;
      immutableScopeDigest: ReversalScopeDigest;
      expired: boolean;
    }>;

export interface ReversalLookupRequest {
  readonly mappingKey: ReversalMappingKey;
}

export interface ReversalLookupResult {
  readonly mappingKey: ReversalMappingKey;
  readonly encryptedRecord: EncryptedReversalRecordBlob;
}

export interface SpoolVolume {
  reserveNonce(input: NonceReservationInput): Promise<GcmNonce96>;

  prepare(
    input: PrepareReversalWriteInput,
  ): Promise<PreparedReversalWrite>;

  publish(
    prepared: PreparedReversalWrite,
  ): Promise<PublishReversalResult>;

  flush(commit: PublishedCommitHandle): Promise<void>;

  readCurrent(
    requests: readonly ReversalLookupRequest[],
  ): Promise<readonly ReversalLookupResult[]>;
}
```

`readCurrent` is exact-key and bounded. It must neither accept an empty “all records” selector nor expose an iterator over stored records.

## B. Behavioral requirements

1. **Exact surface (§7, N2).**  
   The public store surface is exactly `maximumEncounteredTokenBatch`, `record`, and `resolveEncounteredTokens`. The resolved map is bounded to the validated tokens supplied by the caller.

2. **Promise and durable acknowledgment (§6, N4/N5).**  
   The concrete `record` method always returns `Promise<void>`. It resolves only after encryption, PREPARE, atomic publication, and durable flush have all succeeded. A successful return must survive process death, replica loss, scale-in, and remount by another replica.

3. **Fixed safe write failure (§7, N2/N4).**  
   Any validation, classification, key-provider, encryption, nonce-reservation, prepare, publication, or flush failure rejects with `PhiEngineError(WRITE_FAIL)`. Its message and metadata are fixed. It carries no `cause` and contains no canonical, token, tenant/matter pairing, provider text, database error, path, ciphertext, nonce, key reference, or encryption material.

4. **Envelope construction (§6, L8).**  
   The canonical UTF-8 bytes are encrypted using AES-256-GCM with a 256-bit per-tenant/per-matter DEK generation, a 128-bit authentication tag, and a unique 96-bit nonce. Every durable record contains ciphertext, authentication tag, nonce, wrapped DEK, DEK generation identifier, KEK reference/version, and the exact AAD bytes.

5. **Nonce uniqueness (§6).**  
   Nonces are durable, monotonically allocated 96-bit unsigned counters per DEK generation. `reserveNonce` must durably reserve a value before returning. Gaps are allowed; reuse is forbidden across crashes and replicas. Counter exhaustion rotates the DEK or fails closed before encryption.

6. **Exact AAD (§6, L8).**  
   AAD is binary, not JSON:

   ```text
   UTF8("phi-substitution-engine/reversal-record") || 0x00 ||
   U16BE(1) ||
   FIELD(1, tenantId) ||
   FIELD(2, matterId) ||
   FIELD(3, dictionaryVersion) ||
   FIELD(4, token) ||
   FIELD(5, attemptId) ||
   FIELD(6, retentionClass) ||
   FIELD_U64(7, createdAtEpochMs) ||
   FIELD_U64(8, expiresAtEpochMsOrMaxUint64) ||
   FIELD(9, dekGenerationId) ||
   FIELD(10, wrappingKeyVersion)
   ```

   `FIELD(tag, value)` is `U8(tag) || U32BE(byteLength) || UTF8(validated branded lexeme)`. Values are not normalized during AAD construction. `FIELD_U64` is `U8(tag) || U32BE(8) || U64BE(value)`.

   The domain and schema prevent cross-protocol/version use. Tenant and matter prevent cross-scope replay. Dictionary version and token bind the lookup identity. Attempt binds the idempotent event. Retention class and timestamps prevent expiry tampering. DEK generation and KEK version prevent key-metadata substitution.

7. **AAD verification (§6, L8, N5).**  
   Reads derive tenant, matter, version, and token from the requested lookup key—not merely from stored metadata. They reconstruct AAD using those values plus authenticated record metadata. Stored AAD must byte-equal the reconstruction before unwrap/decrypt. Any mismatch or GCM failure rejects the entire resolution with `RESOLVE_FAIL`.

8. **Tenant-scoped keys and queries (L8).**  
   The logical mapping key is `(tenantId, matterId, dictionaryVersion, token)`. Key selection, DEK generation, physical namespace, encryption AAD, and lookup all include tenant. No fallback or tenant-agnostic token index is permitted.

9. **Idempotency key and first-write rule (§3.1.3, §6, L8).**  
   The idempotency key is `(tenantId, attemptId, token)`. Matter ID and dictionary version form immutable associated scope metadata. Atomic publication must claim the idempotency key and advance the current mapping as one transaction.

   - First publication wins.
   - A replay with the same tenant/attempt/token and matching matter/version is a no-op, even if its canonical differs.
   - It must flush the existing commit before acknowledging, covering a race with an incompletely flushed first caller.
   - A replay whose matter/version differs rejects safely; it never creates a second mapping.
   - The canonical is never compared or returned in a conflict error.
   - Different attempts may publish a new current canonical; atomic commit order determines the current record.

10. **Atomic publication (§6).**  
    A prepared encrypted record is invisible to reads until `publish` atomically establishes both its idempotency claim and current-mapping state. A crash may leave an unreachable prepared artifact, but never a visible partial mapping, duplicate idempotency claim, or current pointer without its encrypted record.

11. **Durable flush (§6).**  
    `flush` covers record content and publication metadata. For a filesystem adapter this includes file data, atomic same-volume rename/link, parent-directory metadata, and the mounted backend’s durable barrier. Merely closing a file, flushing userspace buffers, or writing container scratch is insufficient.

12. **Post-publication failure (§6, N4).**  
    If publication may have succeeded but flush fails, `record` still rejects `WRITE_FAIL`. A later retry may encounter the existing idempotency claim, flush that same commit, and then succeed. Provider invocation remains prohibited after the rejected call.

13. **Retention classification (§6).**  
    Because the frozen input lacks a retention field, a trusted identifier-only classifier supplies the class. Failure or an unknown class fails closed. The classifier must never receive canonical or token.

14. **Detector TTL (§6, roadmap A#5/D5).**  
    `createdAtEpochMs` is captured once before PREPARE. A detector-only record gets `expiresAt = createdAt + 86_400_000`; matter records use `MaxUint64`. At `now >= expiresAt`, the detector record is absent for resolution and must not be decrypted or returned. One expired or missing requested token rejects the entire lookup.

15. **Non-retryability after expiry (§6).**  
    Expiration does not erase the idempotency tombstone. A same-attempt replay after expiry rejects `EXPIRED_FAIL`; it must not create a fresh 24-hour window. Detector ciphertext may be purged, but enough non-PHI idempotency state must remain to reject future replay.

16. **Matter retention (§6).**  
    Matter records have no store-level TTL and remain resolvable until the governing matter-retention mechanism removes the tenant/matter namespace. No public deletion API is added to `ReversalWriteStore`.

17. **Bounded all-or-nothing resolution (§7, N2/N5).**  
    Resolution rejects before I/O for empty, duplicate, malformed, or oversized token batches. It reads only exact requested keys. Missing, expired, corrupt, unauthenticated, or undecryptable entries reject the whole call; no partial map escapes.

18. **Hardened returned map (§7, N2/N5).**  
    The result is not a native mutable `Map`. It is a module-constructed `ReadonlyMap` view whose backing map is an ECMAScript `#private` slot. `Map.prototype.set.call(result, …)` must throw; constructor recovery cannot create a forged populated view; `Reflect.ownKeys(result)` reveals no backing map or canonical.

19. **Private sensitive state (§7, N2).**  
    Unwrapped DEK caches and any fields holding plaintext canonical or wrapped-key material use native ECMAScript `#private` fields. TypeScript `private`, underscored properties, symbols, closures attached as properties, and enumerable/transpiled fields are not substitutes. Prefer retaining canonical only as a lexical local and never caching it.

20. **No intrinsic-poisoning scope creep.**  
    Tests may exercise ordinary reflection, forged receivers, constructor recovery, and native-Map mutation. They must not require resilience to first-party replacement of JS global intrinsics.

## C. NAMED MUTATIONS (§10 oracle discipline)

| Named mutation | Concrete change | Oracle that must go red |
|---|---|---|
| `MUT-AAD-DROP-TENANT` | Omit tenant ID from AAD. | `aad rejects cross-tenant record relocation`: relocating A’s envelope to B must reject and return no canonical. |
| `MUT-AAD-DROP-MATTER` | Omit matter ID from AAD. | `aad rejects cross-matter record relocation`: same tenant/token under another matter must reject. |
| `MUT-AAD-DROP-VERSION` | Omit dictionary version from AAD. | `aad rejects cross-version replay`: envelope moved to another version must reject. |
| `MUT-AAD-DROP-TOKEN` | Omit token from AAD. | `aad rejects token-slot substitution`: swapping two token envelopes must reject. |
| `MUT-AAD-DROP-ATTEMPT` | Omit attempt ID from AAD. | `aad authenticates attempt identity`: tampering persisted attempt ID must reject. |
| `MUT-AAD-DROP-TTL` | Omit retention class or expiry from AAD. | `aad authenticates retention metadata`: extending expiry or changing detector to matter must reject. |
| `MUT-RETURN-BEFORE-FLUSH` | Resolve `record` after publish but before `flush`. | `record rejection prevents provider egress`: blocked flush must leave provider spy at zero calls. |
| `MUT-FLUSH-FILE-ONLY` | Flush record bytes but not publication/directory metadata. | `acknowledged write survives replica loss`: remount after simulated metadata loss must still resolve. |
| `MUT-NONATOMIC-PUBLISH` | Publish current pointer separately from idempotency claim/record. | `publication is atomic under every injected crash point`: no partial state may be readable or acknowledged. |
| `MUT-OVERWRITE-SAME-ATTEMPT` | Replace the first canonical on a divergent same-attempt replay. | `same attempt divergent replay keeps first canonical`: resolution must equal the first value. |
| `MUT-IDEMPOTENCY-OMIT-TENANT` | Key idempotency by attempt/token only. | `idempotency is tenant scoped`: identical attempt/token in A and B must commit independently. |
| `MUT-IDEMPOTENCY-INCLUDE-CANONICAL` | Treat changed canonical as a new idempotent record. | `same attempt canonical divergence creates no second commit`: publish count remains one. |
| `MUT-CONFLICT-ACK-WITHOUT-FLUSH` | Existing-claim branch immediately returns. | `concurrent replay waits for original durable flush`: neither caller resolves before shared commit flushes. |
| `MUT-SKIP-READ-TTL` | Decrypt and return expired detector records. | `expired detector mapping is absent`: resolution at the exact expiry instant must reject. |
| `MUT-REFRESH-EXPIRED-REPLAY` | Reinsert an expired attempt with a new expiry. | `expired detector attempt is non-retryable`: replay rejects and creates no new commit. |
| `MUT-FALLBACK-TENANTLESS-LOOKUP` | On miss, query by matter/version/token without tenant. | `colliding token never crosses tenants`: B cannot resolve A’s mapping. |
| `MUT-REUSE-GCM-NONCE` | Reuse a nonce after crash or across replicas. | `nonce reservation is durable and unique`: all reservations for one DEK remain distinct across remount/concurrency. |
| `MUT-IGNORE-GCM-TAG` | Return plaintext despite failed authentication. | `ciphertext bit flip fails closed`: a one-bit ciphertext/tag change rejects the whole batch. |
| `MUT-WIDEN-LISTALL` | Add `listAll`, snapshot, raw-record, or unbounded iterator. | `store public surface remains frozen`: prototype surface equals the approved constructor/getter/two-method set. |
| `MUT-TS-PRIVATE-DEK-CACHE` | Replace `#dekCache` with `private dekCache`. | `sensitive fields use native private identifiers`: source/AST and reflection oracle must fail. |
| `MUT-NATIVE-MAP-RESULT` | Return a native `Map` typed as `ReadonlyMap`. | `resolved view rejects native Map mutation`: `Map.prototype.set.call` must throw and state remain unchanged. |
| `MUT-FORGEABLE-VIEW-CTOR` | Permit recovered result constructor to accept arbitrary entries. | `resolved view constructor recovery is non-forgeable`: reflective construction with PHI entries must throw. |
| `MUT-PARTIAL-RESOLVE` | Return found mappings while omitting missing/expired tokens. | `resolution is all-or-nothing`: one missing token rejects and exposes no result. |
| `MUT-LEAK-UNDERLYING-ERROR` | Preserve provider/DB error as message, metadata, or `cause`. | `write errors have fixed safe surface`: serialized and reflected error contains only the approved fixed fields. |
| `MUT-CONTAINER-SCRATCH` | Place prepared records on disposable local storage. | `ack survives new replica on mounted volume`: a fresh process/adapter resolves every acknowledged record. |

## D. Test oracle list

Vitest suites must include:

- `record resolves only after durable flush` — the promise remains pending through prepare and publish and resolves only after `flush`.
- `record rejection prevents provider egress` — an orchestrator integration test where flush rejects and the provider spy remains uncalled.
- `record errors have the fixed safe surface` — exact `WRITE_FAIL`, exact fixed message, no cause or input/provider substrings.
- `acknowledged write survives replica loss` — reopen through a fresh store and volume adapter and resolve the acknowledged canonical.
- `publication is atomic under every injected crash point` — inject failure before/after every persistence phase and observe no partial readable state.
- `same attempt exact replay creates one commit` — the second call is a durable no-op.
- `same attempt divergent replay keeps first canonical` — the first canonical remains current.
- `same attempt scope divergence fails closed` — changed matter/version under the same tenant/attempt/token is rejected.
- `concurrent replay waits for original durable flush` — the conflict path cannot acknowledge an unflushed commit.
- `different attempts advance current canonical` — the latest atomically published attempt resolves.
- `aad authenticates every field` — table-driven mutation of all ten AAD fields rejects.
- `ciphertext and tag tampering fail closed` — bit flips never yield plaintext.
- `nonce reservation is unique across concurrency and remount` — no duplicate nonce under one DEK generation.
- `colliding token never crosses tenants` — tenant B receives `RESOLVE_FAIL`, never A’s canonical.
- `bounded read requests exact keys only` — volume spy sees only the supplied tenant-scoped keys.
- `oversized duplicate malformed or empty batches reject before I/O` — no volume/key-provider call occurs.
- `resolution is all-or-nothing` — one absent or corrupt token prevents any map result.
- `expired detector mapping is absent` — `now === expiresAt` rejects without unwrap.
- `expired detector attempt is non-retryable` — replay cannot refresh TTL or publish again.
- `matter mapping has no 24-hour expiry` — it remains resolvable past the detector boundary.
- `sensitive fields use native private identifiers` — source/AST requires `PrivateIdentifier` fields for DEK cache and sensitive retained state.
- `store reflection exposes no sensitive state` — after write/read, `Reflect.ownKeys(store)` reveals no canonical, DEK cache, or wrapped key material.
- `resolved view reflection exposes no backing map` — own-key inspection reveals no raw backing container or canonical.
- `resolved view rejects native Map mutation` — native `Map` mutation methods fail on the returned view.
- `resolved view constructor recovery is non-forgeable` — recovered constructor cannot create a populated forged view.
- `store public surface remains frozen` — no enumeration, snapshot, export, or raw-record method exists.

## E. Open questions / decisions for Opus spec-check

1. **Blocking: exact error-code literals.** The supplied excerpt does not include the frozen allowed-code registry. Opus must bind `WRITE_FAIL`, `RESOLVE_FAIL`, and `EXPIRED_FAIL` to existing members before implementation. In particular, the write path must use one fixed code for every underlying failure.

2. **Blocking: retention discriminator.** `ReversalRecordInput` does not say whether a record is matter-retained or detector-only. This spec proposes an identifier-only constructor dependency, preserving the frozen store surface. Opus must confirm the authoritative registry it consults and reject any inference based on token shape, matter-ID conventions, or branding.

3. **Detector idempotency-tombstone retention.** “Non-retryable after expiry” requires remembering expired attempts after ciphertext removal. If upstream provides no finite attempt-replay horizon, tombstones must persist indefinitely or until tenant deletion. Governance must ratify that duration and the tombstone’s permitted identifiers.

4. **DEK generation and rotation.** Ratify whether rotation is time-based, count-based, KEK-version-driven, or manual; how concurrent replicas elect the active tenant/matter DEK; and how old generations remain unwrap-capable through matter retention.

5. **KEK/DEK caching.** Ratify maximum cache entries and TTL. Correctness and tenant separation must not depend on caching. Cache keys must include tenant, matter, DEK generation, and KEK version; eviction must best-effort zero mutable DEK bytes.

6. **Mounted-volume guarantees.** G4 must demonstrate that the selected Azure mount supports the port’s cross-replica atomic publication, durable nonce reservation, and flush semantics. If it cannot, deployment is blocked; container-local `fsync` is not evidence.

7. **TTL clock authority.** Ratify the production clock source, acceptable skew, and rollback behavior. The exact boundary remains `now >= expiresAt`.

8. **Matter-retention deletion.** The frozen store cannot gain a delete API. Opus must identify the external lifecycle mechanism that removes records, wrapped DEKs, tombstones, and nonce state when matter retention ends.

9. **Expired-current collision behavior.** Confirm whether detector-only and matter mappings occupy disjoint token namespaces. If they can share a mapping key, specify whether expiry of a newer detector record exposes an older matter record or makes the key absent; this spec defaults to absent and fail closed.
