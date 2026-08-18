/**
 * In-process dev `SpoolVolume` (GLY-337 L2.4). NOT for production — the Azure Files (Premium) mount
 * impl lands at G4 behind the SAME `SpoolVolume` interface. No Azure SDK / filesystem client here.
 *
 * Durability model (so the oracles can simulate the real thing):
 *  - `InMemoryReversalSpoolBackend` is the DURABLE, SHARED substrate (the "mounted volume"): DEK
 *    generations, the durable nonce counters, prepared artifacts, committed record bytes, idempotency
 *    claims (tombstones), and current mappings all live here. It is shared across every replica mounted
 *    on it.
 *  - `InMemoryReversalSpoolVolume` is a per-replica handle. Its only replica-local state is the
 *    prepared-write context (a handle it minted). All claim/mapping/nonce state is on the shared
 *    backend, so a SECOND replica mounted on the same backend sees the first replica's claims.
 *
 * `publish` is CROSS-REPLICA atomic: `backend.publishAtomic` does a SYNCHRONOUS check-and-set (no
 * `await` between the claim-existence check and the claim+mapping write), so two `record()` calls
 * interleaved at their awaits — even on two different volumes over one backend — can never both create
 * a first commit. The loser gets `kind:"existing"` and flushes that shared commit.
 *
 * `flush` is the DURABILITY barrier: it promotes a published commit's record bytes AND publication
 * metadata (claim + mapping) from "published" to durably-flushed. A replica loss (`crash()`) discards
 * every published-but-unflushed claim/mapping, so an unacknowledged write leaves no readable mapping
 * and no blocking tombstone; a flushed write survives.
 *
 * Fault injection: `volume.faults.failAt` throws at a phase boundary; `volume.faults.flushGate` holds
 * `flush` pending. `backend.crash()` models a replica-loss remount. The `debug*` methods simulate an
 * attacker with raw storage access (relocation, metadata/blob tampering, ciphertext corruption) — dev
 * affordances, NOT part of the `SpoolVolume` port.
 */
import type {
  DekGeneration,
  EncryptedReversalRecordBlob,
  EnsureDekGenerationInput,
  GcmNonce96,
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
  ReversalScopeDigest,
  SpoolVolume,
  DurableReversalRecordMeta,
} from "../ports";

export type SpoolFaultPhase = "ensureDekGeneration" | "reserveNonce" | "prepare" | "publish" | "flush";

export interface SpoolFaults {
  /** Throw a fault when entering this phase (simulates a crash / backend outage at that boundary). */
  failAt?: SpoolFaultPhase;
  /** When set, `flush` awaits this before completing — lets a test hold a durable commit pending. */
  flushGate?: Promise<void> | null;
}

interface StoredClaim {
  readonly idempotencyKey: ReversalIdempotencyKey;
  readonly mappingKey: ReversalMappingKey;
  readonly scopeDigest: ReversalScopeDigest;
  readonly commit: PublishedCommitHandle;
  readonly preparedHandle: PreparedWriteHandle;
  readonly createdAtEpochMs: number;
  readonly expiresAtEpochMs: bigint;
  /** false = published but not yet durably flushed (lost on replica loss); true = durable. */
  readonly flushed: boolean;
}

interface StoredMapping {
  readonly mappingKey: ReversalMappingKey;
  readonly preparedHandle: PreparedWriteHandle;
  readonly commit: PublishedCommitHandle;
  /**
   * Atomic-publication ordinal of `commit` (§9/§10): the current record is the HIGHEST-ordinal one. A
   * `bigint` so the monotonic sequence NEVER saturates (an IEEE-754 `number` stops incrementing at 2^53,
   * which would tie ordinals and repeat handles — `MUT-ORDINAL-NUMBER-OVERFLOW`).
   */
  readonly ordinal: bigint;
  readonly flushed: boolean;
}

interface CommitContext {
  readonly idempotencyKey: ReversalIdempotencyKey;
  readonly mappingKey: ReversalMappingKey;
  readonly scopeDigest: ReversalScopeDigest;
  readonly preparedHandle: PreparedWriteHandle;
}

/** Big-endian 96-bit nonce from a durable counter. */
function nonce96(counter: bigint): GcmNonce96 {
  const buf = Buffer.alloc(12);
  buf.writeBigUInt64BE(counter >> 32n, 0);
  buf.writeUInt32BE(Number(counter & 0xffffffffn), 8);
  return new Uint8Array(buf) as unknown as GcmNonce96;
}

/**
 * The durable, SHARED "mounted volume". Every replica mounted on it sees the same claims/mappings.
 * A published-but-unflushed claim/mapping is visible to a live peer (so idempotency is cross-replica)
 * but is discarded by `crash()` (replica loss).
 */
export class InMemoryReversalSpoolBackend {
  readonly #dekGenerations = new Map<string, DekGeneration>();
  readonly #nonceNext = new Map<string, bigint>();
  /** Prepared artifacts — durable, UNREACHABLE by readCurrent (only a committed record is readable). */
  readonly #preparedBlobs = new Map<string, EncryptedReversalRecordBlob>();
  /** Durable first-seen retention class per exact tenant+attempt operation. Never garbage-collected. */
  readonly #operationRetention = new Map<string, "matter" | "detector-only">();
  /** Record bytes made durable by a completed flush — the ONLY blobs readCurrent returns. */
  readonly #committedRecords = new Map<string, EncryptedReversalRecordBlob>();
  readonly #claims = new Map<string, StoredClaim>();
  /** PROVISIONAL current pointer (last-writer). Pre-crash bookkeeping only — NOT what reads follow. */
  readonly #mappings = new Map<string, StoredMapping>();
  /**
   * DURABLE current pointer — the ONLY mapping reads follow. Written EXCLUSIVELY by a completed flush,
   * and NEVER by publish or discarded by `crash()`. The current record is defined by ATOMIC PUBLICATION
   * ORDER (§9/§10): the durable pointer advances ONLY to a commit with a HIGHER publication ordinal, so a
   * flush of an older commit — a same-attempt replay flushing its original commit, or a late flush of an
   * earlier publication — makes THAT commit's bytes durable WITHOUT rolling the current pointer back to it
   * (`MUT-DURABLE-ROLLBACK`). Because the pointer only moves forward on flush and survives `crash()`,
   * `record()` never acknowledges while the durable-readable mapping is absent or points at an unflushed
   * successor (§6/N4). Reads following `#mappings` instead is `MUT-DURABLE-MAPPING-STEAL`.
   */
  readonly #durableMappings = new Map<string, StoredMapping>();
  readonly #commitIndex = new Map<string, CommitContext>();
  /**
   * Monotonic publication ordinal per commit (assigned at atomic publish). The durable current pointer
   * compares against it so publication order — not flush-completion order — decides the current record.
   */
  readonly #commitOrdinal = new Map<string, bigint>();
  // `bigint` monotonic counters — arbitrary precision, so handles never repeat and ordinals never tie
  // (a `number` saturates at 2^53; the nonce counter above is already bigint for the same reason).
  #handleSeq = 0n;
  #publishSeq = 0n;

  public mount(faults: SpoolFaults = {}, nowEpochMilliseconds: () => number = Date.now): InMemoryReversalSpoolVolume {
    return new InMemoryReversalSpoolVolume(this, faults, nowEpochMilliseconds);
  }

  /** Replica loss: discard every published-but-unflushed claim/mapping/commit. Durable state survives. */
  public crash(): void {
    for (const [key, claim] of this.#claims) {
      if (!claim.flushed) {
        this.#claims.delete(key);
      }
    }
    for (const [key, mapping] of this.#mappings) {
      if (!mapping.flushed) {
        this.#mappings.delete(key);
      }
    }
    for (const [commit, ctx] of this.#commitIndex) {
      const claim = this.#claims.get(ctx.idempotencyKey as unknown as string);
      if (claim === undefined || (claim.commit as unknown as string) !== commit) {
        this.#commitIndex.delete(commit);
      }
    }
  }

  // ---- internal substrate API used only by the volume ----
  nextPreparedHandle(): PreparedWriteHandle {
    this.#handleSeq += 1n;
    return `prep-${this.#handleSeq}` as unknown as PreparedWriteHandle;
  }
  getDekGeneration(scopeKey: string): DekGeneration | undefined {
    return this.#dekGenerations.get(scopeKey);
  }
  putDekGeneration(scopeKey: string, generation: DekGeneration): void {
    this.#dekGenerations.set(scopeKey, generation);
  }
  reserveNonceCounter(dekGenerationId: string): bigint {
    const next = this.#nonceNext.get(dekGenerationId) ?? 0n;
    this.#nonceNext.set(dekGenerationId, next + 1n);
    return next;
  }
  putPreparedBlob(handle: PreparedWriteHandle, blob: EncryptedReversalRecordBlob): void {
    this.#preparedBlobs.set(handle as unknown as string, blob);
  }
  bindOperationRetention(blob: EncryptedReversalRecordBlob): void {
    const key = `${blob.meta.tenantId as unknown as string}\0${blob.meta.attemptId as unknown as string}`;
    const existing = this.#operationRetention.get(key);
    if (existing !== undefined && existing !== blob.meta.retentionClass) {
      throw new Error("operation_retention_binding_mismatch");
    }
    if (existing === undefined) this.#operationRetention.set(key, blob.meta.retentionClass);
  }
  getPreparedBlob(handle: PreparedWriteHandle): EncryptedReversalRecordBlob | undefined {
    return this.#preparedBlobs.get(handle as unknown as string);
  }

  /**
   * SYNCHRONOUS cross-replica atomic publish (§6 / F1): the claim-existence check and the claim +
   * current-mapping write happen with NO `await` between them, so two await-interleaved callers — even
   * on two volumes over this one backend — cannot both create a first commit. First writer wins.
   */
  publishAtomic(ctx: CommitContext, blob: EncryptedReversalRecordBlob, nowEpochMs: number): PublishReversalResult {
    const idempotencyKey = ctx.idempotencyKey as unknown as string;
    const existing = this.#claims.get(idempotencyKey);
    if (existing !== undefined) {
      const expired = BigInt(nowEpochMs) >= existing.expiresAtEpochMs;
      return { kind: "existing", commit: existing.commit, immutableScopeDigest: existing.scopeDigest, expired };
    }
    this.#handleSeq += 1n;
    const commit = `commit-${this.#handleSeq}` as unknown as PublishedCommitHandle;
    // Atomic publication ordinal: this establishes commit order for "current record" (§9/§10).
    this.#publishSeq += 1n;
    const ordinal = this.#publishSeq;
    const claim: StoredClaim = {
      idempotencyKey: ctx.idempotencyKey,
      mappingKey: ctx.mappingKey,
      scopeDigest: ctx.scopeDigest,
      commit,
      preparedHandle: ctx.preparedHandle,
      createdAtEpochMs: blob.meta.createdAtEpochMs,
      expiresAtEpochMs: blob.meta.expiresAtEpochMs,
      flushed: false,
    };
    this.#claims.set(idempotencyKey, claim);
    this.#commitOrdinal.set(commit as unknown as string, ordinal);
    this.#mappings.set(ctx.mappingKey as unknown as string, {
      mappingKey: ctx.mappingKey,
      preparedHandle: ctx.preparedHandle,
      commit,
      ordinal,
      flushed: false,
    });
    this.#commitIndex.set(commit as unknown as string, ctx);
    return { kind: "published", commit };
  }

  /** Durability barrier: promote a commit's record bytes AND publication metadata to durable. */
  flushCommit(commit: PublishedCommitHandle): void {
    const ctx = this.#commitIndex.get(commit as unknown as string);
    if (ctx === undefined) {
      // The commit is UNKNOWN — never published, or published-but-unflushed then lost to `crash()` (a
      // durably-flushed commit ALWAYS retains its commit-index entry). Durability cannot be positively
      // proven, so fail closed rather than acknowledge a vanished write (§6/N4). Reverting this to a
      // silent no-op lets a gated peer of a crashed claim ack with no durable mapping (MUT-FLUSH-LOST-COMMIT).
      throw new Error("flush_unknown_or_lost_commit");
    }
    const blob = this.#preparedBlobs.get(ctx.preparedHandle as unknown as string);
    if (blob === undefined) {
      throw new Error("flush_missing_prepared_blob");
    }
    // Skipping the bytes is MUT-CONTAINER-SCRATCH; skipping the metadata is MUT-FLUSH-FILE-ONLY.
    this.#persistRecordBytes(ctx.preparedHandle, blob);
    this.#persistPublicationMetadata(commit, ctx);
  }

  #persistRecordBytes(handle: PreparedWriteHandle, blob: EncryptedReversalRecordBlob): void {
    this.#committedRecords.set(handle as unknown as string, blob);
  }

  #persistPublicationMetadata(commit: PublishedCommitHandle, ctx: CommitContext): void {
    const commitStr = commit as unknown as string;
    const claim = this.#claims.get(ctx.idempotencyKey as unknown as string);
    if (claim !== undefined && (claim.commit as unknown as string) === commitStr) {
      this.#claims.set(ctx.idempotencyKey as unknown as string, { ...claim, flushed: true });
    }
    // Advance the durable current pointer to THIS commit ONLY when it is newer by publication order
    // (§9/§10). A flush of an older commit — a same-attempt replay flushing its original commit, or a
    // late flush of an earlier publication — still makes that commit's bytes/claim durable above, but must
    // NOT roll the current canonical back over a newer publication (MUT-DURABLE-ROLLBACK). Because the
    // pointer only moves forward and survives crash, an acknowledged commit's durable mapping is never
    // absent nor superseded by an unflushed successor.
    const ordinal = this.#commitOrdinal.get(commitStr) ?? 0n;
    const durableCurrent = this.#durableMappings.get(ctx.mappingKey as unknown as string);
    if (durableCurrent === undefined || ordinal > durableCurrent.ordinal) {
      this.#durableMappings.set(ctx.mappingKey as unknown as string, {
        mappingKey: ctx.mappingKey,
        preparedHandle: ctx.preparedHandle,
        commit,
        ordinal,
        flushed: true,
      });
    }
    // Keep the provisional pointer's flushed flag consistent when it still points here (bookkeeping only).
    const mapping = this.#mappings.get(ctx.mappingKey as unknown as string);
    if (mapping !== undefined && (mapping.commit as unknown as string) === commitStr) {
      this.#mappings.set(ctx.mappingKey as unknown as string, { ...mapping, flushed: true });
    }
  }

  readMapping(mappingKey: ReversalMappingKey): StoredMapping | undefined {
    // Reads follow the DURABLE pointer only — a published-but-unflushed commit is not readable, and an
    // acknowledged commit's durable pointer survives a concurrent successor's publish and a `crash()`.
    // Pointing this at `#mappings` is MUT-DURABLE-MAPPING-STEAL.
    return this.#durableMappings.get(mappingKey as unknown as string);
  }
  /** Only a committed (durably flushed) record is readable. */
  readCommittedBlob(handle: PreparedWriteHandle): EncryptedReversalRecordBlob | undefined {
    return this.#committedRecords.get(handle as unknown as string);
  }

  // ---- dev/attacker-simulation affordances (NOT part of the SpoolVolume port) ----

  #blobFor(mappingKey: ReversalMappingKey): { handle: PreparedWriteHandle; blob: EncryptedReversalRecordBlob } {
    // Attacker-sim operates on the DURABLE pointer — the same one reads follow.
    const m = this.#durableMappings.get(mappingKey as unknown as string);
    if (m === undefined) {
      throw new Error("debug_mapping_absent");
    }
    const blob =
      this.#committedRecords.get(m.preparedHandle as unknown as string) ??
      this.#preparedBlobs.get(m.preparedHandle as unknown as string);
    if (blob === undefined) {
      throw new Error("debug_blob_absent");
    }
    return { handle: m.preparedHandle, blob };
  }

  #restore(handle: PreparedWriteHandle, blob: EncryptedReversalRecordBlob): void {
    this.#committedRecords.set(handle as unknown as string, blob);
    this.#preparedBlobs.set(handle as unknown as string, blob);
  }

  /** Read a stored blob (for attacker-simulation tests that reuse valid-but-wrong material). */
  public debugReadBlob(mappingKey: ReversalMappingKey): EncryptedReversalRecordBlob {
    return this.#blobFor(mappingKey).blob;
  }

  /** Simulates raw-storage relocation of an envelope to another mapping key. */
  public debugRelocate(from: ReversalMappingKey, to: ReversalMappingKey): void {
    const m = this.#durableMappings.get(from as unknown as string);
    if (m === undefined) {
      throw new Error("debug_relocate_source_absent");
    }
    this.#durableMappings.set(to as unknown as string, { ...m, mappingKey: to });
  }

  /** Simulates tampering of stored (authenticated) record metadata. */
  public debugMutateMeta(mappingKey: ReversalMappingKey, patch: Partial<DurableReversalRecordMeta>): void {
    const { handle, blob } = this.#blobFor(mappingKey);
    this.#restore(handle, { ...blob, meta: { ...blob.meta, ...patch } });
  }

  /** Simulates tampering of a top-level stored blob field (wrappedDek, wrappingKeyId, dekGenerationId…). */
  public debugPatchBlob(mappingKey: ReversalMappingKey, patch: Partial<EncryptedReversalRecordBlob>): void {
    const { handle, blob } = this.#blobFor(mappingKey);
    this.#restore(handle, { ...blob, ...patch });
  }

  /** Simulates a one-bit ciphertext corruption (tamper). */
  public debugCorruptCiphertext(mappingKey: ReversalMappingKey): void {
    const { handle, blob } = this.#blobFor(mappingKey);
    const flipped = Uint8Array.from(blob.ciphertext);
    if (flipped.length === 0) {
      throw new Error("debug_corrupt_empty");
    }
    flipped[0] = flipped[0]! ^ 0x01;
    this.#restore(handle, { ...blob, ciphertext: flipped });
  }
}

export class InMemoryReversalSpoolVolume implements SpoolVolume {
  readonly #backend: InMemoryReversalSpoolBackend;
  readonly #nowEpochMilliseconds: () => number;
  /** The only replica-local state: prepared-write context for handles THIS replica minted. */
  readonly #preparedContext = new Map<string, CommitContext>();
  /** Mutable so a test can inject a fault/gate on an already-constructed volume. */
  public readonly faults: SpoolFaults;

  public constructor(
    backend: InMemoryReversalSpoolBackend,
    faults: SpoolFaults = {},
    nowEpochMilliseconds: () => number = Date.now,
  ) {
    this.#backend = backend;
    this.faults = faults;
    this.#nowEpochMilliseconds = nowEpochMilliseconds;
  }

  #faultCheck(phase: SpoolFaultPhase): void {
    if (this.faults.failAt === phase) {
      throw new Error(`spool_fault_${phase}`);
    }
  }

  public async ensureDekGeneration(input: EnsureDekGenerationInput): Promise<DekGeneration> {
    this.#faultCheck("ensureDekGeneration");
    const scopeKey = `${input.scope.tenantId} ${input.scope.matterId} ${input.scope.purpose}`;
    const existing = this.#backend.getDekGeneration(scopeKey);
    if (existing !== undefined) {
      return existing;
    }
    const minted = await input.mint();
    const raced = this.#backend.getDekGeneration(scopeKey);
    if (raced !== undefined) {
      return raced;
    }
    this.#backend.putDekGeneration(scopeKey, minted);
    return minted;
  }

  public reserveNonce(input: NonceReservationInput): Promise<GcmNonce96> {
    this.#faultCheck("reserveNonce");
    // Durable reservation: advance the backend counter BEFORE returning, so the value survives crash
    // and remount and is never handed out twice for one DEK generation.
    const counter = this.#backend.reserveNonceCounter(input.dekGenerationId as unknown as string);
    return Promise.resolve(nonce96(counter));
  }

  public prepare(input: PrepareReversalWriteInput): Promise<PreparedReversalWrite> {
    this.#faultCheck("prepare");
    const handle = this.#backend.nextPreparedHandle();
    // Synchronous with the prepared artifact insert: no replica-local classifier result can race or
    // override the durable first winner, and crash() deliberately retains this map.
    this.#backend.bindOperationRetention(input.encryptedRecord);
    this.#backend.putPreparedBlob(handle, input.encryptedRecord);
    this.#preparedContext.set(handle as unknown as string, {
      idempotencyKey: input.idempotencyKey,
      mappingKey: input.mappingKey,
      scopeDigest: input.immutableScopeDigest,
      preparedHandle: handle,
    });
    return Promise.resolve({ handle });
  }

  public publish(prepared: PreparedReversalWrite): Promise<PublishReversalResult> {
    this.#faultCheck("publish");
    const ctx = this.#preparedContext.get(prepared.handle as unknown as string);
    if (ctx === undefined) {
      return Promise.reject(new Error("publish_without_prepare"));
    }
    const blob = this.#backend.getPreparedBlob(prepared.handle);
    if (blob === undefined) {
      return Promise.reject(new Error("publish_missing_prepared_blob"));
    }
    // Read the clock and run the atomic check-and-set synchronously (no await between) → cross-replica
    // atomic. Splitting the check from the claim, or claiming in replica-local state, is MUT-NONATOMIC-PUBLISH.
    const now = this.#nowEpochMilliseconds();
    const result = this.#backend.publishAtomic(ctx, blob, now);
    return Promise.resolve(result);
  }

  public async flush(commit: PublishedCommitHandle): Promise<void> {
    if (this.faults.flushGate != null) {
      await this.faults.flushGate;
    }
    this.#faultCheck("flush");
    this.#backend.flushCommit(commit);
  }

  public readCurrent(requests: readonly ReversalLookupRequest[]): Promise<readonly ReversalLookupResult[]> {
    if (requests.length === 0) {
      return Promise.reject(new Error("read_current_requires_exact_keys"));
    }
    const out: ReversalLookupResult[] = [];
    for (const request of requests) {
      const mapping = this.#backend.readMapping(request.mappingKey);
      if (mapping === undefined) {
        continue; // exact-key miss → absent
      }
      const blob = this.#backend.readCommittedBlob(mapping.preparedHandle);
      if (blob === undefined) {
        continue; // published-but-unflushed → not yet readable
      }
      out.push({ mappingKey: request.mappingKey, encryptedRecord: blob });
    }
    return Promise.resolve(out);
  }
}
