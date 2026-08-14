/**
 * Binary AAD for the reversal envelope (sol spec §B.6; CONTRACT §6/L8). NOT JSON.
 *
 * ```text
 * UTF8("phi-substitution-engine/reversal-record") || 0x00 ||
 * U16BE(1) ||
 * FIELD(1, tenantId) || FIELD(2, matterId) || FIELD(3, dictionaryVersion) ||
 * FIELD(4, token) || FIELD(5, attemptId) || FIELD(6, retentionClass) ||
 * FIELD_U64(7, createdAtEpochMs) || FIELD_U64(8, expiresAtEpochMsOrMaxUint64) ||
 * FIELD(9, dekGenerationId) || FIELD(10, wrappingKeyVersion)
 * ```
 *
 * `FIELD(tag, value) = U8(tag) || U32BE(byteLength) || UTF8(validated branded lexeme)`.
 * `FIELD_U64(tag, value) = U8(tag) || U32BE(8) || U64BE(value)`. Values are NOT normalized.
 *
 * Every field is authenticated: domain+schema prevent cross-protocol/version use; tenant+matter
 * prevent cross-scope replay; version+token bind the lookup identity; attempt binds the idempotent
 * event; retention+timestamps prevent expiry tampering; DEK generation + KEK version prevent
 * key-metadata substitution. Dropping ANY field is a named mutation (`MUT-AAD-DROP-*`).
 */
import type { ReversalRetentionClass } from "./ports";

const DOMAIN = "phi-substitution-engine/reversal-record";
const SCHEMA_VERSION = 1;
const MAX_UINT64 = 2n ** 64n - 1n;

/** Sentinel expiry for matter records: never expires at the store. */
export const MATTER_EXPIRES_AT: bigint = MAX_UINT64;

export interface ReversalAadFields {
  readonly tenantId: string;
  readonly matterId: string;
  /** The dictionary version's decimal lexeme (`bigint.toString()`), not normalized. */
  readonly dictionaryVersion: string;
  readonly token: string;
  readonly attemptId: string;
  readonly retentionClass: ReversalRetentionClass;
  readonly createdAtEpochMs: number;
  readonly expiresAtEpochMs: bigint;
  readonly dekGenerationId: string;
  readonly wrappingKeyVersion: string;
}

function field(tag: number, value: string): Buffer {
  const utf8 = Buffer.from(value, "utf8");
  const header = Buffer.alloc(5);
  header.writeUInt8(tag, 0);
  header.writeUInt32BE(utf8.byteLength, 1);
  return Buffer.concat([header, utf8]);
}

function fieldU64(tag: number, value: bigint): Buffer {
  if (value < 0n || value > MAX_UINT64) {
    // A value outside the U64 domain cannot be authenticated safely; fail closed at construction.
    throw new RangeError("aad_u64_out_of_range");
  }
  const buf = Buffer.alloc(13);
  buf.writeUInt8(tag, 0);
  buf.writeUInt32BE(8, 1);
  buf.writeBigUInt64BE(value, 5);
  return buf;
}

/**
 * Builds the exact §B.6 AAD bytes. The field order is fixed and every field is present; this ordered
 * concat is the single point a `MUT-AAD-DROP-*` mutation would omit a binding from.
 */
export function buildReversalAad(fields: ReversalAadFields): Uint8Array {
  const prefix = Buffer.alloc(Buffer.byteLength(DOMAIN, "utf8") + 1 + 2);
  const domainLen = prefix.write(DOMAIN, 0, "utf8");
  prefix.writeUInt8(0x00, domainLen); // domain separator
  prefix.writeUInt16BE(SCHEMA_VERSION, domainLen + 1);

  const parts: Buffer[] = [
    prefix,
    field(1, fields.tenantId),
    field(2, fields.matterId),
    field(3, fields.dictionaryVersion),
    field(4, fields.token),
    field(5, fields.attemptId),
    field(6, fields.retentionClass),
    fieldU64(7, BigInt(fields.createdAtEpochMs)),
    fieldU64(8, fields.expiresAtEpochMs),
    field(9, fields.dekGenerationId),
    field(10, fields.wrappingKeyVersion),
  ];
  return Buffer.concat(parts);
}
