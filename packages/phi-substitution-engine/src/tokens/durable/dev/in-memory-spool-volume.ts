/**
 * In-process dev `SpoolVolume` (GLY-337 L2.4). NOT for production — the Azure Files (Premium) mount
 * impl lands at G4 behind the SAME `SpoolVolume` interface. No Azure SDK / filesystem client here.
 *
 * Durability model (so the oracles can simulate the real thing):
 *  - `InMemoryReversalSpoolBackend` is the DURABLE substrate (the "mounted volume"): DEK generations,
 *    the durable nonce counters, prepared artifacts, committed record bytes, idempotency claims
 *    (tombstones), and current mappings all live here and SURVIVE a remount.
 *  - `InMemoryReversalSpoolVolume` is a per-replica handle. PENDING state — a published-but-not-yet-
 *    flushed commit — lives on the VOLUME and is LOST on replica loss / remount. A fresh replica is
 *    `backend.mount()`.
 *
 * `publish` is atomic: it writes the idempotency claim AND the current mapping into pending in one
 * synchronous critical section; only `flush` promotes them (together with the record bytes) to the
 * durable backend. So an acknowledged (flushed) write survives remount, and an unflushed one leaves
 * no readable current mapping.
 *
 * Crash + fault injection: set `volume.faults.failAt` to throw at a phase boundary, or
 * `volume.faults.flushGate` to hold `flush` pending. `backend.mount()` models a replica takeover.
 * The `debug*` methods on the backend simulate an attacker with raw storage access (record
 * relocation, metadata tampering, ciphertext corruption) — they are dev/test affordances, NOT part
 * of the `SpoolVolume` port.
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

interface ClaimRecord {
  readonly idempotencyKey: ReversalIdempotencyKey;
  readonly mappingKey: ReversalMappingKey;
  readonly scopeDigest: ReversalScopeDigest;
  readonly commit: PublishedCommitHandle;
  readonly preparedHandle: PreparedWriteHandle;
  readonly createdAtEpochMs: number;
  readonly expiresAtEpochMs: bigint;
}

interface MappingRecord {
  readonly mappingKey: ReversalMappingKey;
  readonly preparedHandle: PreparedWriteHandle;
  readonly commit: PublishedCommitHandle;
}

interface PendingCommit {
  readonly commit: PublishedCommitHandle;
  readonly claim: ClaimRecord;
  readonly mapping: MappingRecord;
  readonly preparedHandle: PreparedWriteHandle;
}

/** Big-endian 96-bit nonce from a durable counter. */
function nonce96(counter: bigint): GcmNonce96 {
  const buf = Buffer.alloc(12);
  buf.writeBigUInt64BE(counter >> 32n, 0); // high 64 bits (0 for realistic counts) into bytes 0..7
  buf.writeUInt32BE(Number(counter & 0xffffffffn), 8); // low 32 bits into bytes 8..11
  return new Uint8Array(buf) as unknown as GcmNonce96;
}

/**
 * The durable "mounted volume". Persists across a remount; only PENDING (unflushed) state on the
 * per-replica {@link InMemoryReversalSpoolVolume} is lost.
 */
export class InMemoryReversalSpoolBackend {
  readonly #dekGenerations = new Map<string, DekGeneration>();
  readonly #nonceNext = new Map<string, bigint>();
  /** Prepared artifacts on the mounted volume — durable but UNREACHABLE without a durable mapping. */
  readonly #preparedBlobs = new Map<string, EncryptedReversalRecordBlob>();
  /** Record bytes made durable by a completed flush. */
  readonly #committedRecords = new Map<string, EncryptedReversalRecordBlob>();
  /** Durable idempotency claims (tombstones persist past detector expiry). */
  readonly #claims = new Map<string, ClaimRecord>();
  /** Durable current mappings. */
  readonly #mappings = new Map<string, MappingRecord>();
  #handleSeq = 0;

  public mount(faults: SpoolFaults = {}, nowEpochMilliseconds: () => number = Date.now): InMemoryReversalSpoolVolume {
    return new InMemoryReversalSpoolVolume(this, faults, nowEpochMilliseconds);
  }

  // ---- internal substrate API used only by the volume ----
  nextPreparedHandle(): PreparedWriteHandle {
    this.#handleSeq += 1;
    return `prep-${this.#handleSeq}` as unknown as PreparedWriteHandle;
  }
  nextCommit(): PublishedCommitHandle {
    this.#handleSeq += 1;
    return `commit-${this.#handleSeq}` as unknown as PublishedCommitHandle;
  }
  getDekGeneration(scopeKey: string): DekGeneration | undefined {
    return this.#dekGenerations.get(scopeKey);
  }
  putDekGeneration(scopeKey: string, generation: DekGeneration): void {
    this.#dekGenerations.set(scopeKey, generation);
  }
  /** Durably reserve + advance the per-generation nonce counter BEFORE returning (survives remount). */
  reserveNonceCounter(dekGenerationId: string): bigint {
    const next = this.#nonceNext.get(dekGenerationId) ?? 0n;
    this.#nonceNext.set(dekGenerationId, next + 1n);
    return next;
  }
  putPreparedBlob(handle: PreparedWriteHandle, blob: EncryptedReversalRecordBlob): void {
    this.#preparedBlobs.set(handle as unknown as string, blob);
  }
  getClaim(idempotencyKey: ReversalIdempotencyKey): ClaimRecord | undefined {
    return this.#claims.get(idempotencyKey as unknown as string);
  }
  putClaim(claim: ClaimRecord): void {
    this.#claims.set(claim.idempotencyKey as unknown as string, claim);
  }
  putMapping(mapping: MappingRecord): void {
    this.#mappings.set(mapping.mappingKey as unknown as string, mapping);
  }
  getMapping(mappingKey: ReversalMappingKey): MappingRecord | undefined {
    return this.#mappings.get(mappingKey as unknown as string);
  }
  putCommittedRecord(handle: PreparedWriteHandle, blob: EncryptedReversalRecordBlob): void {
    this.#committedRecords.set(handle as unknown as string, blob);
  }
  getBlobForRead(handle: PreparedWriteHandle): EncryptedReversalRecordBlob | undefined {
    const h = handle as unknown as string;
    return this.#committedRecords.get(h) ?? this.#preparedBlobs.get(h);
  }

  // ---- dev/attacker-simulation affordances (NOT part of the SpoolVolume port) ----

  /** Simulates an attacker with raw storage access relocating an envelope to another mapping key. */
  public debugRelocate(from: ReversalMappingKey, to: ReversalMappingKey): void {
    const m = this.#mappings.get(from as unknown as string);
    if (m === undefined) {
      throw new Error("debug_relocate_source_absent");
    }
    this.#mappings.set(to as unknown as string, { mappingKey: to, preparedHandle: m.preparedHandle, commit: m.commit });
  }

  /** Simulates tampering of stored (authenticated) record metadata. */
  public debugMutateMeta(mappingKey: ReversalMappingKey, patch: Partial<DurableReversalRecordMeta>): void {
    const m = this.#mappings.get(mappingKey as unknown as string);
    if (m === undefined) {
      throw new Error("debug_mutate_meta_absent");
    }
    const blob = this.getBlobForRead(m.preparedHandle);
    if (blob === undefined) {
      throw new Error("debug_mutate_meta_blob_absent");
    }
    const mutated: EncryptedReversalRecordBlob = { ...blob, meta: { ...blob.meta, ...patch } };
    this.putCommittedRecord(m.preparedHandle, mutated);
    this.#preparedBlobs.set(m.preparedHandle as unknown as string, mutated);
  }

  /** Simulates tampering of a top-level stored blob field (e.g. dekGenerationId, wrappingKeyVersion, nonce). */
  public debugPatchBlob(mappingKey: ReversalMappingKey, patch: Partial<EncryptedReversalRecordBlob>): void {
    const m = this.#mappings.get(mappingKey as unknown as string);
    if (m === undefined) {
      throw new Error("debug_patch_blob_absent");
    }
    const blob = this.getBlobForRead(m.preparedHandle);
    if (blob === undefined) {
      throw new Error("debug_patch_blob_missing");
    }
    const mutated: EncryptedReversalRecordBlob = { ...blob, ...patch };
    this.putCommittedRecord(m.preparedHandle, mutated);
    this.#preparedBlobs.set(m.preparedHandle as unknown as string, mutated);
  }

  /** Simulates a one-bit ciphertext corruption (tamper). */
  public debugCorruptCiphertext(mappingKey: ReversalMappingKey): void {
    const m = this.#mappings.get(mappingKey as unknown as string);
    if (m === undefined) {
      throw new Error("debug_corrupt_absent");
    }
    const blob = this.getBlobForRead(m.preparedHandle);
    if (blob === undefined) {
      throw new Error("debug_corrupt_blob_absent");
    }
    const flipped = Uint8Array.from(blob.ciphertext);
    if (flipped.length === 0) {
      throw new Error("debug_corrupt_empty");
    }
    flipped[0] = flipped[0]! ^ 0x01;
    const mutated: EncryptedReversalRecordBlob = { ...blob, ciphertext: flipped };
    this.putCommittedRecord(m.preparedHandle, mutated);
    this.#preparedBlobs.set(m.preparedHandle as unknown as string, mutated);
  }
}

export class InMemoryReversalSpoolVolume implements SpoolVolume {
  readonly #backend: InMemoryReversalSpoolBackend;
  readonly #nowEpochMilliseconds: () => number;
  // Per-replica PENDING state — lost on remount.
  readonly #pendingRecords = new Map<string, EncryptedReversalRecordBlob>();
  readonly #pendingClaims = new Map<string, ClaimRecord>();
  readonly #pendingMappings = new Map<string, MappingRecord>();
  readonly #pendingCommits = new Map<string, PendingCommit>();
  readonly #preparedContext = new Map<
    string,
    { readonly idempotencyKey: ReversalIdempotencyKey; readonly mappingKey: ReversalMappingKey; readonly scopeDigest: ReversalScopeDigest }
  >();
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
    // Re-check after the async mint in case a concurrent caller won the race (first mint wins durably).
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
    // Prepared artifact goes to the durable substrate (unreachable) AND the live replica.
    this.#backend.putPreparedBlob(handle, input.encryptedRecord);
    this.#pendingRecords.set(handle as unknown as string, input.encryptedRecord);
    this.#preparedContext.set(handle as unknown as string, {
      idempotencyKey: input.idempotencyKey,
      mappingKey: input.mappingKey,
      scopeDigest: input.immutableScopeDigest,
    });
    return Promise.resolve({ handle });
  }

  #lookupClaim(idempotencyKey: ReversalIdempotencyKey): ClaimRecord | undefined {
    return this.#pendingClaims.get(idempotencyKey as unknown as string) ?? this.#backend.getClaim(idempotencyKey);
  }

  public publish(prepared: PreparedReversalWrite): Promise<PublishReversalResult> {
    this.#faultCheck("publish");
    const ctx = this.#preparedContext.get(prepared.handle as unknown as string);
    if (ctx === undefined) {
      return Promise.reject(new Error("publish_without_prepare"));
    }
    const existing = this.#lookupClaim(ctx.idempotencyKey);
    if (existing !== undefined) {
      // Atomic no-op: the claim already exists. Never create a second claim/mapping.
      const expired = BigInt(this.#nowEpochMilliseconds()) >= existing.expiresAtEpochMs;
      return Promise.resolve({
        kind: "existing",
        commit: existing.commit,
        immutableScopeDigest: existing.scopeDigest,
        expired,
      });
    }
    const blob = this.#backend.getBlobForRead(prepared.handle);
    if (blob === undefined) {
      return Promise.reject(new Error("publish_missing_prepared_blob"));
    }
    const commit = this.#backend.nextCommit();
    const claim: ClaimRecord = {
      idempotencyKey: ctx.idempotencyKey,
      mappingKey: ctx.mappingKey,
      scopeDigest: ctx.scopeDigest,
      commit,
      preparedHandle: prepared.handle,
      createdAtEpochMs: blob.meta.createdAtEpochMs,
      expiresAtEpochMs: blob.meta.expiresAtEpochMs,
    };
    const mapping: MappingRecord = { mappingKey: ctx.mappingKey, preparedHandle: prepared.handle, commit };
    // ATOMIC critical section: claim + current mapping become visible together, into PENDING only.
    // Nothing is durable until flush. (Splitting these, or writing either straight to the durable
    // backend here, is MUT-NONATOMIC-PUBLISH.)
    this.#pendingClaims.set(ctx.idempotencyKey as unknown as string, claim);
    this.#pendingMappings.set(ctx.mappingKey as unknown as string, mapping);
    this.#pendingCommits.set(commit as unknown as string, { commit, claim, mapping, preparedHandle: prepared.handle });
    return Promise.resolve({ kind: "published", commit });
  }

  public async flush(commit: PublishedCommitHandle): Promise<void> {
    if (this.faults.flushGate != null) {
      await this.faults.flushGate;
    }
    this.#faultCheck("flush");
    const pending = this.#pendingCommits.get(commit as unknown as string);
    if (pending === undefined) {
      // Already durable (a prior flush of the same commit) — flush is idempotent.
      return;
    }
    // Durable barrier: BOTH the record bytes AND the publication metadata (claim + mapping) are
    // promoted to the mounted backend. Skipping the bytes is MUT-CONTAINER-SCRATCH; skipping the
    // metadata is MUT-FLUSH-FILE-ONLY.
    const blob = this.#backend.getBlobForRead(pending.preparedHandle);
    if (blob === undefined) {
      throw new Error("flush_missing_prepared_blob");
    }
    this.#persistRecordBytes(pending.preparedHandle, blob);
    this.#persistPublicationMetadata(pending.claim, pending.mapping);
    this.#pendingCommits.delete(commit as unknown as string);
  }

  #persistRecordBytes(handle: PreparedWriteHandle, blob: EncryptedReversalRecordBlob): void {
    this.#backend.putCommittedRecord(handle, blob);
  }

  #persistPublicationMetadata(claim: ClaimRecord, mapping: MappingRecord): void {
    this.#backend.putClaim(claim);
    this.#backend.putMapping(mapping);
  }

  public readCurrent(requests: readonly ReversalLookupRequest[]): Promise<readonly ReversalLookupResult[]> {
    if (requests.length === 0) {
      // Exact-key only: an empty "all records" selector is not permitted.
      return Promise.reject(new Error("read_current_requires_exact_keys"));
    }
    const out: ReversalLookupResult[] = [];
    for (const request of requests) {
      const key = request.mappingKey as unknown as string;
      const mapping = this.#pendingMappings.get(key) ?? this.#backend.getMapping(request.mappingKey);
      if (mapping === undefined) {
        continue; // exact-key miss → absent (partial map at the store level)
      }
      const blob =
        this.#pendingRecords.get(mapping.preparedHandle as unknown as string) ??
        this.#backend.getBlobForRead(mapping.preparedHandle);
      if (blob === undefined) {
        continue;
      }
      out.push({ mappingKey: request.mappingKey, encryptedRecord: blob });
    }
    return Promise.resolve(out);
  }
}
