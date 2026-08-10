/** Compile-time nominal brand. Values must be constructed only by trusted adapters. */
declare const brand: unique symbol;
export type Brand<T, Name extends string> = T & { readonly [brand]: Name };

export type TenantId = Brand<string, "TenantId">;
export type MatterId = Brand<string, "MatterId">;
export type ActorId = Brand<string, "ActorId">;
export type OperationId = Brand<string, "OperationId">;
export type OperationAttemptId = Brand<string, "OperationAttemptId">;
export type DictionaryVersion = Brand<bigint, "DictionaryVersion">;
export type EngineVersion = Brand<string, "EngineVersion">;
export type SchemaVersion = Brand<string, "SchemaVersion">;
export type SubjectId = Brand<string, "SubjectId">;
export type TokenRole = Brand<string, "TokenRole">;
export type SubstitutionToken = Brand<string, "SubstitutionToken">;
export type TokenizedText = Brand<string, "TokenizedText">;
export type DisplayText = Brand<string, "DisplayText">;
export type EscapedSourceText = Brand<string, "EscapedSourceText">;
export type KnownLocale = Brand<string, "KnownLocale">;
export type Utf16Offset = Brand<number, "Utf16Offset">;

/** Opaque encrypted bytes. No adapter may coerce these to an audit/content string. */
export type Ciphertext = Brand<Uint8Array, "Ciphertext">;
