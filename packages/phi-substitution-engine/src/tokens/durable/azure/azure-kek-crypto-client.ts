import { DefaultAzureCredential, ManagedIdentityCredential } from "@azure/identity";
import { CryptographyClient } from "@azure/keyvault-keys";
import type { WrappingKeyId, WrappingKeyVersion } from "../ports";
import type { KekCryptoClient } from "./kek-crypto-client";

const KEY_WRAP_ALGORITHM = "RSA-OAEP-256" as const;

export interface AzureKekCryptoClientOptions {
  /** Versioned Azure Key Vault key URL. */
  readonly keyId: string;
  readonly keyVersion: string;
  /** Client ID of the user-assigned managed identity used in Azure. */
  readonly managedIdentityClientId?: string;
}

/** Azure SDK adapter for the versioned KEK used by the durable reversal store. */
export class AzureKekCryptoClient implements KekCryptoClient {
  public readonly keyId: WrappingKeyId;
  public readonly keyVersion: WrappingKeyVersion;
  readonly #client: CryptographyClient;

  public constructor(options: AzureKekCryptoClientOptions) {
    this.keyId = options.keyId as unknown as WrappingKeyId;
    this.keyVersion = options.keyVersion as unknown as WrappingKeyVersion;

    const credential =
      options.managedIdentityClientId === undefined
        ? new DefaultAzureCredential()
        : new ManagedIdentityCredential({ clientId: options.managedIdentityClientId });
    this.#client = new CryptographyClient(options.keyId, credential);
  }

  public async wrapKey(plaintext: Uint8Array): Promise<Uint8Array> {
    const result = await this.#client.wrapKey(KEY_WRAP_ALGORITHM, plaintext);
    return result.result;
  }

  public async unwrapKey(wrapped: Uint8Array): Promise<Uint8Array> {
    const result = await this.#client.unwrapKey(KEY_WRAP_ALGORITHM, wrapped);
    return result.result;
  }
}
