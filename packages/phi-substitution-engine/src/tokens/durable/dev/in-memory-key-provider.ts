/**
 * In-process dev `KeyProvider` (GLY-337 L2.4). NOT for production — the Azure Key Vault KEK impl
 * lands at G4 behind the SAME `KeyProvider` interface. No Azure SDK is imported here.
 *
 * The KEK is a `#private` slot that never leaves the object; the provider only wraps/unwraps a DEK.
 * `wrap` binds the wrapped payload to `bindingDigest` by using it as the GCM AAD, so `unwrap` fails
 * closed (GCM auth throws) unless the caller presents the identical scope+KEK-version digest — the
 * structured "wrap a `DEK || bindingDigest` payload and verify after unwrap" requirement, achieved
 * cryptographically rather than by a plaintext compare.
 */
import { randomBytes } from "node:crypto";
import { gcmDecrypt, gcmEncrypt } from "../envelope";
import type {
  DekMaterial,
  KeyProvider,
  UnwrapDekInput,
  WrapDekInput,
  WrappedDekMaterial,
  WrappingKeyHandle,
  WrappingKeyId,
  WrappingKeyScope,
  WrappingKeyVersion,
} from "../ports";

const KEK_BYTES = 32;
const WRAP_NONCE_BYTES = 12;
const WRAP_TAG_BYTES = 16;

export interface InMemoryKeyProviderOptions {
  readonly kek?: Uint8Array;
  readonly keyId?: string;
  readonly keyVersion?: string;
}

export class InMemoryKeyProvider implements KeyProvider {
  // §7/N2 discipline: the KEK is native-private; it never appears on the reflectable surface.
  readonly #kek: Buffer;
  readonly #keyId: WrappingKeyId;
  readonly #keyVersion: WrappingKeyVersion;

  public constructor(options: InMemoryKeyProviderOptions = {}) {
    this.#kek = options.kek ? Buffer.from(options.kek) : randomBytes(KEK_BYTES);
    if (this.#kek.byteLength !== KEK_BYTES) {
      throw new Error("dev_kek_must_be_32_bytes");
    }
    this.#keyId = (options.keyId ?? "dev-kek") as unknown as WrappingKeyId;
    this.#keyVersion = (options.keyVersion ?? "v1") as unknown as WrappingKeyVersion;
  }

  public getWrappingKey(scope: WrappingKeyScope): Promise<WrappingKeyHandle> {
    return Promise.resolve({ keyId: this.#keyId, keyVersion: this.#keyVersion, scope });
  }

  public wrap(input: WrapDekInput): Promise<WrappedDekMaterial> {
    const nonce = randomBytes(WRAP_NONCE_BYTES);
    const { ciphertext, authTag } = gcmEncrypt(this.#kek, nonce, input.bindingDigest, input.dek);
    // wrappedDek = nonce || authTag || ciphertext
    const wrapped = Buffer.concat([nonce, authTag, ciphertext]);
    return Promise.resolve(wrapped as unknown as WrappedDekMaterial);
  }

  public unwrap(input: UnwrapDekInput): Promise<DekMaterial> {
    const wrapped = Buffer.from(input.wrappedDek);
    const nonce = wrapped.subarray(0, WRAP_NONCE_BYTES);
    const authTag = wrapped.subarray(WRAP_NONCE_BYTES, WRAP_NONCE_BYTES + WRAP_TAG_BYTES);
    const ciphertext = wrapped.subarray(WRAP_NONCE_BYTES + WRAP_TAG_BYTES);
    // The bindingDigest is the GCM AAD: a wrong scope/KEK-version digest fails authentication and
    // throws, so a wrapped DEK cannot be unwrapped under a substituted scope (fail closed).
    const dek = gcmDecrypt(this.#kek, nonce, input.bindingDigest, ciphertext, authTag);
    return Promise.resolve(dek as unknown as DekMaterial);
  }
}
