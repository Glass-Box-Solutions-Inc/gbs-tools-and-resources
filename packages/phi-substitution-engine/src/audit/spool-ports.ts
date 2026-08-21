/**
 * Injected dependencies for the encrypted local spool. In Azure Container Apps the volume is an
 * application-local append/drain protocol on a mounted durable Azure storage volume — never
 * disposable container scratch (CONTRACT §6). The key provider references a service-side key;
 * key material never crosses onto the volume.
 */

/** A durable, append-oriented byte store. Only ciphertext envelopes are ever written to it. */
export interface SpoolVolume {
  /** True when an acknowledged write survives replica loss / scale-in. */
  readonly durable: boolean;
  /**
   * Writes `bytes` under `recordId` atomically and reports whether the durable flush completed.
   * Publication is atomic: a partially written record is never observable.
   */
  putAtomic(
    recordId: string,
    bytes: Uint8Array,
  ): Promise<Readonly<{ flushed: boolean }>>;
  read(recordId: string): Promise<Uint8Array | null>;
  list(): Promise<readonly string[]>;
  remove(recordId: string): Promise<void>;
}

/** Supplies the AES-256 data key used for spool envelopes. Key bytes never touch the volume. */
export interface SpoolKeyProvider {
  readonly keyVersion: string;
  /** Returns exactly 32 bytes of key material. */
  dataKey(): Uint8Array;
}
