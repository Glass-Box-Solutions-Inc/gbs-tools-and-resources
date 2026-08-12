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
import { randomBytes } from "node:crypto";
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

export class DurableReversalStore implements ReversalWriteStore {
  /** The ONLY public own property (required by `ReversalStore`). A number — nothing sensitive. */
  public readonly maximumEncounteredTokenBatch: number;

  // §7/N2 (req 19): every sensitive/held reference is a native `#private` slot. `#dekCache` holds
  // UNWRAPPED DEK bytes and MUST be `#`, not TS `private` (which stays reflectively enumerable at
  // runtime under ES2022) — replacing it with `private dekCache` is `MUT-TS-PRIVATE-DEK-CACHE`.
  readonly #keyProvider: KeyProvider;
  readonly #spool: SpoolVolume;
  readonly #classifyRetention: (input: RetentionClassificationInput) => Promise<ReversalRetentionClass>;
  readonly #nowEpochMilliseconds: () => number;
  readonly #dekCache = new Map<string, Uint8Array>();

  public constructor(dependencies: DurableReversalStoreDependencies) {
    this.#keyProvider = dependencies.keyProvider;
    this.#spool = dependencies.spoolVolume;
    this.#classifyRetention = dependencies.classifyRetention;
    this.#nowEpochMilliseconds = dependencies.nowEpochMilliseconds;
    this.maximumEncounteredTokenBatch = dependencies.maximumEncounteredTokenBatch;
  }

  /**
   * Durably record `token → current canonical` (§6, N5). Resolves ONLY after encrypt → prepare →
   * atomic publish → durable flush all succeed, so the orchestrator's `await record(...)` gates
   * provider egress on durability. ANY failure rejects with the fixed, safe `REVERSAL_FAILED`
   * surface — no `cause`, no canonical/token/tenant/provider/db/path/ciphertext/nonce/key text.
   */
  public async record(input: ReversalRecordInput): Promise<void> {
    // The plaintext canonical stays a lexical local for this method's scope only — never a field.
    const canonical = input.canonical;
    try {
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
    } catch (error) {
      // Fixed, safe surface only. No underlying error, message, `cause`, or PHI ever escapes
      // (MUT-LEAK-UNDERLYING-ERROR). Deliberate rejections above are already `ReversalFailedError`.
      if (error instanceof ReversalFailedError) {
        throw error;
      }
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

    try {
      const keyToToken = new Map<string, SubstitutionToken>();
      const requests = distinct.map((token) => {
        const mappingKey = mappingKeyOf(input.tenantId, input.matterId, input.dictionaryVersion, token);
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
        const canonical = await this.#openRecord(input.tenantId, input.matterId, input.dictionaryVersion, token, result.encryptedRecord, nowEpochMs);
        if (canonical !== undefined) {
          resolved.set(token, canonical);
        }
      }
    } catch (error) {
      // (b) crypto-integrity / tamper already threw `ReversalFailedError`; scrub any other (infra)
      // error into the same fixed, safe surface and fail closed — never a partial map on a throw.
      if (error instanceof ReversalFailedError) {
        throw error;
      }
      throw new ReversalFailedError();
    }
    return resolved;
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

  /** Unwrap + cache the DEK (Q5: cache key includes tenant/matter/DEK-generation + KEK version). */
  async #unwrapDek(
    scope: WrappingKeyScope,
    keyHandle: WrappingKeyHandle,
    dekGenerationId: string,
    wrappedDek: WrappedDekMaterial,
    wrappingKeyVersion: string,
  ): Promise<Uint8Array> {
    const cacheKey = `${dekGenerationId} ${wrappingKeyVersion}`;
    const cached = this.#dekCache.get(cacheKey);
    if (cached !== undefined) {
      return cached;
    }
    const bindingDigest = dekBindingDigestOf(scope, keyHandle);
    const dek = await this.#keyProvider.unwrap({ scope, key: keyHandle, wrappedDek, bindingDigest });
    if ((dek as Uint8Array).byteLength !== DEK_BYTES) {
      throw new ReversalFailedError();
    }
    const bytes = dek as unknown as Uint8Array;
    this.#dekCache.set(cacheKey, bytes);
    return bytes;
  }
}
