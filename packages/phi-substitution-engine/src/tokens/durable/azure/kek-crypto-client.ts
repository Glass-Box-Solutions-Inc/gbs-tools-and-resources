import type { WrappingKeyId, WrappingKeyVersion } from "../ports";

/** Narrow Key Vault cryptography seam; unit tests provide an in-memory fake. */
export interface KekCryptoClient {
  readonly keyId: WrappingKeyId;
  readonly keyVersion: WrappingKeyVersion;
  wrapKey(plaintext: Uint8Array): Promise<Uint8Array>;
  unwrapKey(wrapped: Uint8Array): Promise<Uint8Array>;
}
