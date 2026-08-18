import { createHash } from "node:crypto";
import { describe, expect, it } from "vitest";
import { AzureKeyVaultKeyProvider } from "../src/tokens/durable/azure/azure-keyvault-key-provider";
import type { KekCryptoClient } from "../src/tokens/durable/azure/kek-crypto-client";
import type { MatterId, TenantId } from "../src/core/brands";
import type {
  AadBindingDigest,
  DekMaterial,
  WrappedDekMaterial,
  WrappingKeyId,
  WrappingKeyScope,
  WrappingKeyVersion,
} from "../src/tokens/durable/ports";

const FAKE_TAG = 0xa5;
const CHECKSUM_BYTES = 32;

function branded<T>(value: string): T {
  return value as unknown as T;
}

function bytes<T>(values: Uint8Array): T {
  return values as unknown as T;
}

const SCOPE: WrappingKeyScope = {
  tenantId: branded<TenantId>("tenant-a"),
  matterId: branded<MatterId>("matter-a"),
  purpose: "reversal-v1",
};

const OTHER_SCOPE: WrappingKeyScope = {
  tenantId: branded<TenantId>("tenant-a"),
  matterId: branded<MatterId>("matter-b"),
  purpose: "reversal-v1",
};

function digest(fill: number): AadBindingDigest {
  return bytes<AadBindingDigest>(new Uint8Array(32).fill(fill));
}

function dek(): DekMaterial {
  return bytes<DekMaterial>(Uint8Array.from({ length: 32 }, (_, index) => index));
}

/** Opaque reversible transport fake: it authenticates bytes but never parses the provider plaintext. */
class FakeKekCryptoClient implements KekCryptoClient {
  public readonly keyId = branded<WrappingKeyId>("https://fake.vault/keys/phi-engine-kek");
  public readonly keyVersion = branded<WrappingKeyVersion>("version-1");
  public unwrapCalls = 0;
  public unwrapResult: Uint8Array | undefined;
  public lastReturnedPlaintext: Uint8Array | undefined;

  public wrapKey(plaintext: Uint8Array): Promise<Uint8Array> {
    const payload = Uint8Array.from(plaintext, (value) => value ^ 0x5a);
    const checksum = createHash("sha256").update(payload).digest();
    return Promise.resolve(Uint8Array.from([FAKE_TAG, ...checksum, ...payload]));
  }

  public unwrapKey(wrapped: Uint8Array): Promise<Uint8Array> {
    this.unwrapCalls += 1;
    if (this.unwrapResult !== undefined) {
      const plaintext = this.unwrapResult.slice();
      this.lastReturnedPlaintext = plaintext;
      return Promise.resolve(plaintext);
    }
    if (wrapped.byteLength <= 1 + CHECKSUM_BYTES || wrapped[0] !== FAKE_TAG) {
      return Promise.reject(new Error("opaque_fake_rejected_payload"));
    }
    const checksum = wrapped.subarray(1, 1 + CHECKSUM_BYTES);
    const payload = wrapped.subarray(1 + CHECKSUM_BYTES);
    const actual = createHash("sha256").update(payload).digest();
    if (!Buffer.from(checksum).equals(actual)) {
      return Promise.reject(new Error("opaque_fake_rejected_payload"));
    }
    const plaintext = Uint8Array.from(payload, (value) => value ^ 0x5a);
    this.lastReturnedPlaintext = plaintext;
    return Promise.resolve(plaintext);
  }
}

async function wrappedFixture(client: FakeKekCryptoClient, bindingDigest = digest(0x11)) {
  const provider = new AzureKeyVaultKeyProvider(client);
  const key = await provider.getWrappingKey(SCOPE);
  const originalDek = dek();
  const wrappedDek = await provider.wrap({ scope: SCOPE, key, dek: originalDek, bindingDigest });
  return { provider, key, originalDek, wrappedDek, bindingDigest };
}

describe("AzureKeyVaultKeyProvider", () => {
  it("round-trips a DEK under the same scope and binding digest", async () => {
    const fixture = await wrappedFixture(new FakeKekCryptoClient());

    const unwrapped = await fixture.provider.unwrap({
      scope: SCOPE,
      key: fixture.key,
      wrappedDek: fixture.wrappedDek,
      bindingDigest: fixture.bindingDigest,
    });

    expect(unwrapped).toEqual(fixture.originalDek);
  });

  it("zeroizes the provider-owned unwrap intermediate after transferring a fresh caller-owned DEK", async () => {
    const client = new FakeKekCryptoClient();
    const fixture = await wrappedFixture(client);

    const unwrapped = await fixture.provider.unwrap({
      scope: SCOPE,
      key: fixture.key,
      wrappedDek: fixture.wrappedDek,
      bindingDigest: fixture.bindingDigest,
    });

    expect(unwrapped).toEqual(fixture.originalDek);
    expect(unwrapped).not.toBe(client.lastReturnedPlaintext);
    expect(client.lastReturnedPlaintext).toEqual(new Uint8Array(65));
  });

  it("MUT-KEK-BINDING-BYPASS: rejects relocation under a different binding digest", async () => {
    const fixture = await wrappedFixture(new FakeKekCryptoClient());

    await expect(
      fixture.provider.unwrap({
        scope: SCOPE,
        key: fixture.key,
        wrappedDek: fixture.wrappedDek,
        bindingDigest: digest(0x22),
      }),
    ).rejects.toThrow("azure_keyvault_key_provider_validation_failed");
  });

  it.each([
    // Both fixtures embed the SAME digest the caller presents (digest(0x11)) at offset 1, so the
    // constant-time digest compare would PASS — the length/version guard is the SOLE catcher. This
    // makes each an isolating oracle for that guard (removing it → RED), per the mutation-evidence
    // doctrine (a malformed fixture that also fails the digest compare cannot prove the length/version
    // guard). Layout: version(1) || bindingDigest(32) || dek(rest).
    [
      "64-byte plaintext (correct version + matching digest, short dek)",
      Uint8Array.from([0x01, ...new Uint8Array(32).fill(0x11), ...new Uint8Array(31)]),
    ],
    [
      "wrong encoding version (matching digest + full dek)",
      Uint8Array.from([0x02, ...new Uint8Array(32).fill(0x11), ...new Uint8Array(32)]),
    ],
  ])("rejects %s returned by the KEK client", async (_description, malformedPlaintext) => {
    const client = new FakeKekCryptoClient();
    const fixture = await wrappedFixture(client);
    client.unwrapResult = malformedPlaintext;

    await expect(
      fixture.provider.unwrap({
        scope: SCOPE,
        key: fixture.key,
        wrappedDek: fixture.wrappedDek,
        bindingDigest: fixture.bindingDigest,
      }),
    ).rejects.toThrow("azure_keyvault_key_provider_validation_failed");
  });

  it("rejects an unequal-length digest before the constant-time comparison or remote unwrap", async () => {
    const client = new FakeKekCryptoClient();
    const fixture = await wrappedFixture(client);
    const shortDigest = bytes<AadBindingDigest>(new Uint8Array(31));

    await expect(
      fixture.provider.unwrap({
        scope: SCOPE,
        key: fixture.key,
        wrappedDek: fixture.wrappedDek,
        bindingDigest: shortDigest,
      }),
    ).rejects.toThrow("azure_keyvault_key_provider_validation_failed");
    expect(client.unwrapCalls).toBe(0);
  });

  it("rejects a key handle whose configured scope binding differs", async () => {
    const fixture = await wrappedFixture(new FakeKekCryptoClient());

    await expect(
      fixture.provider.unwrap({
        scope: OTHER_SCOPE,
        key: fixture.key,
        wrappedDek: fixture.wrappedDek,
        bindingDigest: fixture.bindingDigest,
      }),
    ).rejects.toThrow("azure_keyvault_key_provider_validation_failed");
  });

  it("rejects a corrupted wrapped payload", async () => {
    const fixture = await wrappedFixture(new FakeKekCryptoClient());
    const corrupted = fixture.wrappedDek.slice();
    corrupted[corrupted.length - 1] ^= 0xff;

    await expect(
      fixture.provider.unwrap({
        scope: SCOPE,
        key: fixture.key,
        wrappedDek: corrupted as unknown as WrappedDekMaterial,
        bindingDigest: fixture.bindingDigest,
      }),
    ).rejects.toThrow();
  });
});

// AzureKekCryptoClient itself is covered by the Q6 Azure smoke, not by these no-network unit tests.
