import type {
  DictionaryVersion,
  MatterId,
  OperationAttemptId,
  SubstitutionToken,
  TenantId,
} from "../../../core/brands";
import type {
  DekGenerationId,
  EncryptedReversalRecordBlob,
  GcmNonce96,
  WrappedDekMaterial,
  WrappingKeyId,
  WrappingKeyVersion,
} from "../ports";

const MAGIC = Buffer.from("PHIRBLB\0", "ascii");
const VERSION = 1;
const FIELD_HEADER_BYTES = 7;
const MAX_U16 = 0xffff;
const MAX_U32 = 0xffff_ffff;
const MAX_U64 = 2n ** 64n - 1n;

type FieldKind = 1 | 2 | 3;

interface EncodedField {
  readonly name: string;
  readonly kind: FieldKind;
  readonly value: Uint8Array;
}

class Cursor {
  readonly #bytes: Buffer;
  #offset = 0;

  public constructor(bytes: Uint8Array) {
    this.#bytes = Buffer.from(bytes);
  }

  public get remaining(): number {
    return this.#bytes.byteLength - this.#offset;
  }

  public read(length: number): Buffer {
    if (
      !Number.isSafeInteger(length) ||
      length < 0 ||
      length > this.remaining
    ) {
      throw new Error("reversal_blob_codec_truncated");
    }
    const result = this.#bytes.subarray(this.#offset, this.#offset + length);
    this.#offset += length;
    return result;
  }

  public u8(): number {
    return this.read(1).readUInt8(0);
  }

  public u16(): number {
    return this.read(2).readUInt16BE(0);
  }

  public u32(): number {
    return this.read(4).readUInt32BE(0);
  }
}

function utf8(value: string): Uint8Array {
  return Buffer.from(value, "utf8");
}

function bytesField(name: string, value: Uint8Array): EncodedField {
  return { name, kind: 1, value };
}

function textField(name: string, value: string): EncodedField {
  return { name, kind: 2, value: utf8(value) };
}

function u64Field(name: string, value: bigint): EncodedField {
  if (value < 0n || value > MAX_U64) {
    throw new Error(`reversal_blob_codec_invalid_${name}`);
  }
  const encoded = Buffer.alloc(8);
  encoded.writeBigUInt64BE(value);
  return { name, kind: 3, value: encoded };
}

function fieldBuffer(field: EncodedField): Buffer {
  const name = Buffer.from(field.name, "utf8");
  if (
    name.byteLength === 0 ||
    name.byteLength > MAX_U16 ||
    field.value.byteLength > MAX_U32
  ) {
    throw new Error("reversal_blob_codec_field_too_large");
  }
  const header = Buffer.alloc(FIELD_HEADER_BYTES);
  header.writeUInt16BE(name.byteLength, 0);
  header.writeUInt8(field.kind, 2);
  header.writeUInt32BE(field.value.byteLength, 3);
  return Buffer.concat([header, name, field.value]);
}

function stringValue(
  fields: ReadonlyMap<string, EncodedField>,
  name: string,
): string {
  const field = requireField(fields, name, 2);
  const value = Buffer.from(field.value).toString("utf8");
  if (!Buffer.from(value, "utf8").equals(Buffer.from(field.value))) {
    throw new Error(`reversal_blob_codec_invalid_utf8_${name}`);
  }
  return value;
}

function byteValue(
  fields: ReadonlyMap<string, EncodedField>,
  name: string,
): Uint8Array {
  return Uint8Array.from(requireField(fields, name, 1).value);
}

function bigintValue(
  fields: ReadonlyMap<string, EncodedField>,
  name: string,
): bigint {
  const value = requireField(fields, name, 3).value;
  if (value.byteLength !== 8) {
    throw new Error(`reversal_blob_codec_invalid_u64_${name}`);
  }
  return Buffer.from(value).readBigUInt64BE(0);
}

function requireField(
  fields: ReadonlyMap<string, EncodedField>,
  name: string,
  kind: FieldKind,
): EncodedField {
  const field = fields.get(name);
  if (field === undefined || field.kind !== kind) {
    throw new Error(`reversal_blob_codec_invalid_field_${name}`);
  }
  return field;
}

/** Encodes every envelope field as a named, typed, length-prefixed record. */
export function encodeReversalBlob(
  record: EncryptedReversalRecordBlob,
): Uint8Array {
  if (
    !Number.isSafeInteger(record.meta.createdAtEpochMs) ||
    record.meta.createdAtEpochMs < 0
  ) {
    throw new Error("reversal_blob_codec_invalid_createdAtEpochMs");
  }
  const fields: readonly EncodedField[] = [
    bytesField("ciphertext", record.ciphertext),
    bytesField("authTag", record.authTag),
    bytesField("nonce", record.nonce),
    bytesField("wrappedDek", record.wrappedDek),
    textField("dekGenerationId", record.dekGenerationId as unknown as string),
    textField("wrappingKeyId", record.wrappingKeyId as unknown as string),
    textField(
      "wrappingKeyVersion",
      record.wrappingKeyVersion as unknown as string,
    ),
    bytesField("aad", record.aad),
    textField("meta.tenantId", record.meta.tenantId as unknown as string),
    textField("meta.matterId", record.meta.matterId as unknown as string),
    u64Field(
      "meta.dictionaryVersion",
      record.meta.dictionaryVersion as unknown as bigint,
    ),
    textField("meta.token", record.meta.token as unknown as string),
    textField("meta.attemptId", record.meta.attemptId as unknown as string),
    textField("meta.retentionClass", record.meta.retentionClass),
    u64Field("meta.createdAtEpochMs", BigInt(record.meta.createdAtEpochMs)),
    u64Field("meta.expiresAtEpochMs", record.meta.expiresAtEpochMs),
  ];
  const header = Buffer.alloc(MAGIC.byteLength + 4);
  MAGIC.copy(header, 0);
  header.writeUInt16BE(VERSION, MAGIC.byteLength);
  header.writeUInt16BE(fields.length, MAGIC.byteLength + 2);
  return Buffer.concat([header, ...fields.map(fieldBuffer)]);
}

/** Decodes the named record and rejects truncation, duplication, unknown fields, or invalid types. */
export function decodeReversalBlob(
  bytes: Uint8Array,
): EncryptedReversalRecordBlob {
  const cursor = new Cursor(bytes);
  if (
    !cursor.read(MAGIC.byteLength).equals(MAGIC) ||
    cursor.u16() !== VERSION
  ) {
    throw new Error("reversal_blob_codec_invalid_header");
  }
  const fieldCount = cursor.u16();
  const fields = new Map<string, EncodedField>();
  for (let index = 0; index < fieldCount; index += 1) {
    const nameLength = cursor.u16();
    const kind = cursor.u8();
    const valueLength = cursor.u32();
    if (kind !== 1 && kind !== 2 && kind !== 3) {
      throw new Error("reversal_blob_codec_invalid_kind");
    }
    const name = cursor.read(nameLength).toString("utf8");
    if (name.length === 0 || fields.has(name)) {
      throw new Error("reversal_blob_codec_duplicate_or_empty_field");
    }
    fields.set(name, {
      name,
      kind,
      value: Uint8Array.from(cursor.read(valueLength)),
    });
  }
  if (cursor.remaining !== 0 || fields.size !== 16) {
    throw new Error("reversal_blob_codec_invalid_field_set");
  }

  const expectedFields = new Set([
    "ciphertext",
    "authTag",
    "nonce",
    "wrappedDek",
    "dekGenerationId",
    "wrappingKeyId",
    "wrappingKeyVersion",
    "aad",
    "meta.tenantId",
    "meta.matterId",
    "meta.dictionaryVersion",
    "meta.token",
    "meta.attemptId",
    "meta.retentionClass",
    "meta.createdAtEpochMs",
    "meta.expiresAtEpochMs",
  ]);
  for (const name of fields.keys()) {
    if (!expectedFields.has(name)) {
      throw new Error("reversal_blob_codec_unknown_field");
    }
  }

  const createdAt = bigintValue(fields, "meta.createdAtEpochMs");
  if (createdAt > BigInt(Number.MAX_SAFE_INTEGER)) {
    throw new Error("reversal_blob_codec_invalid_createdAtEpochMs");
  }
  const retentionClass = stringValue(fields, "meta.retentionClass");
  if (retentionClass !== "matter" && retentionClass !== "detector-only") {
    throw new Error("reversal_blob_codec_invalid_retentionClass");
  }

  return {
    ciphertext: byteValue(fields, "ciphertext"),
    authTag: byteValue(fields, "authTag"),
    nonce: byteValue(fields, "nonce") as unknown as GcmNonce96,
    wrappedDek: byteValue(
      fields,
      "wrappedDek",
    ) as unknown as WrappedDekMaterial,
    dekGenerationId: stringValue(
      fields,
      "dekGenerationId",
    ) as unknown as DekGenerationId,
    wrappingKeyId: stringValue(
      fields,
      "wrappingKeyId",
    ) as unknown as WrappingKeyId,
    wrappingKeyVersion: stringValue(
      fields,
      "wrappingKeyVersion",
    ) as unknown as WrappingKeyVersion,
    aad: byteValue(fields, "aad"),
    meta: {
      tenantId: stringValue(fields, "meta.tenantId") as unknown as TenantId,
      matterId: stringValue(fields, "meta.matterId") as unknown as MatterId,
      dictionaryVersion: bigintValue(
        fields,
        "meta.dictionaryVersion",
      ) as unknown as DictionaryVersion,
      token: stringValue(fields, "meta.token") as unknown as SubstitutionToken,
      attemptId: stringValue(
        fields,
        "meta.attemptId",
      ) as unknown as OperationAttemptId,
      retentionClass,
      createdAtEpochMs: Number(createdAt),
      expiresAtEpochMs: bigintValue(fields, "meta.expiresAtEpochMs"),
    },
  };
}
