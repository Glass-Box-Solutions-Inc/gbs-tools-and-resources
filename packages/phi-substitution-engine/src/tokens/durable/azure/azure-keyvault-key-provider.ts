import { timingSafeEqual } from "node:crypto";
import type { KekCryptoClient } from "./kek-crypto-client";
import type {
  DekMaterial,
  KeyProvider,
  UnwrapDekInput,
  WrapDekInput,
  WrappedDekMaterial,
  WrappingKeyHandle,
  WrappingKeyScope,
} from "../ports";

const ENCODING_VERSION = 0x01;
const VERSION_BYTES = 1;
const BINDING_DIGEST_BYTES = 32;
const DEK_BYTES = 32;
const WRAPPED_PLAINTEXT_BYTES = VERSION_BYTES + BINDING_DIGEST_BYTES + DEK_BYTES;
const VALIDATION_ERROR = "azure_keyvault_key_provider_validation_failed";

function failValidation(): never {
  throw new Error(VALIDATION_ERROR);
}

function scopesEqual(left: WrappingKeyScope, right: WrappingKeyScope): boolean {
  return left.tenantId === right.tenantId && left.matterId === right.matterId && left.purpose === right.purpose;
}

/**
 * Production `KeyProvider` that keeps the KEK inside Azure Key Vault.
 *
 * RSA-OAEP-256 has no AAD input, so the authenticated scope binding is encoded inside the
 * wrapped plaintext and verified before the DEK is released.
 */
export class AzureKeyVaultKeyProvider implements KeyProvider {
  readonly #client: KekCryptoClient;

  public constructor(client: KekCryptoClient) {
    this.#client = client;
  }

  public getWrappingKey(scope: WrappingKeyScope): Promise<WrappingKeyHandle> {
    return Promise.resolve({ keyId: this.#client.keyId, keyVersion: this.#client.keyVersion, scope });
  }

  public async wrap(input: WrapDekInput): Promise<WrappedDekMaterial> {
    if (
      input.dek.byteLength !== DEK_BYTES ||
      input.bindingDigest.byteLength !== BINDING_DIGEST_BYTES ||
      !this.#handleMatches(input.scope, input.key)
    ) {
      failValidation();
    }

    const plaintext = new Uint8Array(WRAPPED_PLAINTEXT_BYTES);
    plaintext[0] = ENCODING_VERSION;
    plaintext.set(input.bindingDigest, VERSION_BYTES);
    plaintext.set(input.dek, VERSION_BYTES + BINDING_DIGEST_BYTES);

    const wrapped = await this.#client.wrapKey(plaintext);
    return wrapped as unknown as WrappedDekMaterial;
  }

  public async unwrap(input: UnwrapDekInput): Promise<DekMaterial> {
    // Reject malformed caller input before invoking the remote unwrap operation. This also guards
    // timingSafeEqual's equal-length precondition.
    if (input.bindingDigest.byteLength !== BINDING_DIGEST_BYTES) {
      failValidation();
    }

    const plaintext = await this.#client.unwrapKey(input.wrappedDek);
    if (plaintext.byteLength !== WRAPPED_PLAINTEXT_BYTES || plaintext[0] !== ENCODING_VERSION) {
      failValidation();
    }

    const embeddedDigest = plaintext.subarray(VERSION_BYTES, VERSION_BYTES + BINDING_DIGEST_BYTES);
    const digestMatches =
      embeddedDigest.byteLength === input.bindingDigest.byteLength &&
      timingSafeEqual(Buffer.from(embeddedDigest), Buffer.from(input.bindingDigest));

    if (!this.#handleMatches(input.scope, input.key) || !digestMatches) {
      // All provider-controlled mismatches expose the same fail-closed error surface.
      failValidation();
    }

    const dek = plaintext.slice(VERSION_BYTES + BINDING_DIGEST_BYTES, WRAPPED_PLAINTEXT_BYTES);
    return dek as unknown as DekMaterial;
  }

  #handleMatches(scope: WrappingKeyScope, key: WrappingKeyHandle): boolean {
    return (
      key.keyId === this.#client.keyId &&
      key.keyVersion === this.#client.keyVersion &&
      scopesEqual(scope, key.scope)
    );
  }
}
