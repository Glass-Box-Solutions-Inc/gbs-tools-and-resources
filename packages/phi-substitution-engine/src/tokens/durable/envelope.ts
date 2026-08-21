/**
 * AES-256-GCM envelope primitives (CONTRACT §6/L8). Node built-in `crypto` only — no external
 * crypto dependency. 256-bit DEK, 96-bit nonce, 128-bit authentication tag, binary AAD.
 *
 * GCM authentication is the cryptographic enforcement of AAD integrity: `decrypt` supplies the
 * reconstructed AAD and the stored tag, and `final()` throws if either the ciphertext or the AAD
 * differs by a single bit from what was authenticated at encrypt time. Returning plaintext despite
 * that throw is `MUT-IGNORE-GCM-TAG`.
 */
import { createCipheriv, createDecipheriv, timingSafeEqual } from "node:crypto";

const AUTH_TAG_BYTES = 16;
export const DEK_BYTES = 32;
export const NONCE_BYTES = 12;

export interface GcmSealed {
  readonly ciphertext: Uint8Array;
  readonly authTag: Uint8Array;
}

export function gcmEncrypt(
  dek: Uint8Array,
  nonce: Uint8Array,
  aad: Uint8Array,
  plaintext: Uint8Array,
): GcmSealed {
  const cipher = createCipheriv("aes-256-gcm", dek, nonce, {
    authTagLength: AUTH_TAG_BYTES,
  });
  cipher.setAAD(aad, { plaintextLength: plaintext.byteLength });
  const ciphertext = Buffer.concat([cipher.update(plaintext), cipher.final()]);
  const authTag = cipher.getAuthTag();
  return { ciphertext, authTag };
}

/** Decrypts and authenticates. Throws on ANY tag / AAD mismatch — the caller treats a throw as tamper. */
export function gcmDecrypt(
  dek: Uint8Array,
  nonce: Uint8Array,
  aad: Uint8Array,
  ciphertext: Uint8Array,
  authTag: Uint8Array,
): Uint8Array {
  const decipher = createDecipheriv("aes-256-gcm", dek, nonce, {
    authTagLength: AUTH_TAG_BYTES,
  });
  decipher.setAAD(aad, { plaintextLength: ciphertext.byteLength });
  decipher.setAuthTag(authTag);
  return Buffer.concat([decipher.update(ciphertext), decipher.final()]);
}

/** Length-safe constant-time byte comparison (AAD pre-check). Different lengths → not equal, no throw. */
export function bytesEqual(a: Uint8Array, b: Uint8Array): boolean {
  if (a.byteLength !== b.byteLength) {
    return false;
  }
  return timingSafeEqual(a, b);
}
