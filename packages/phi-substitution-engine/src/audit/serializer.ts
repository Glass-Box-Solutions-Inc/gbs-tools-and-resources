import type { OperationId } from "../core/brands";
import type { AiOperation } from "../core/contracts";
import type { PhiAuditEvent, PhiAuditOutcome, PhiAuditPreparedRecord, PhiAuditSerializer } from "./ports";
import { IDENTIFIER_CLASSES } from "./counts";
import { PhiAuditError } from "./errors";

const AI_OPERATIONS: readonly AiOperation[] = ["generation", "stream", "embedding", "graph_extraction"];
const AUDIT_OUTCOMES: readonly PhiAuditOutcome[] = [
  "completed",
  "cancelled",
  "failed_closed",
  "reversal_failed",
  "unknown_after_send",
];

/** A single field's expected shape. The allow-list is exact and recursive. */
type FieldSpec =
  | { readonly kind: "literal"; readonly value: string }
  | { readonly kind: "string" }
  | { readonly kind: "stringOrNull" }
  | { readonly kind: "bigintOrNull" }
  | { readonly kind: "number" }
  | { readonly kind: "enum"; readonly values: readonly string[] }
  | { readonly kind: "totalCounts" }
  | { readonly kind: "exactObject"; readonly fields: ObjectSchema };

type ObjectSchema = Readonly<Record<string, FieldSpec>>;

const LATENCY_SCHEMA: ObjectSchema = {
  dictionary: { kind: "number" },
  detector: { kind: "number" },
  total: { kind: "number" },
};

/** Ordered so the canonical byte form is deterministic. */
const EVENT_SCHEMA: ObjectSchema = {
  eventType: { kind: "literal", value: "AI_SUBSTITUTION_ATTEMPT" },
  attemptId: { kind: "string" },
  operationId: { kind: "string" },
  tenantId: { kind: "string" },
  matterId: { kind: "string" },
  actorId: { kind: "string" },
  operation: { kind: "enum", values: AI_OPERATIONS },
  dictionaryVersion: { kind: "stringOrNull" },
  engineVersion: { kind: "string" },
  counts: { kind: "totalCounts" },
  ambiguityCount: { kind: "number" },
  detectorName: { kind: "stringOrNull" },
  detectorVersion: { kind: "stringOrNull" },
  latencyMs: { kind: "exactObject", fields: LATENCY_SCHEMA },
  outcome: { kind: "enum", values: AUDIT_OUTCOMES },
  failureCode: { kind: "stringOrNull" },
  occurredAt: { kind: "string" },
};

const PREPARED_SCHEMA: ObjectSchema = {
  state: { kind: "literal", value: "PREPARED" },
  attemptId: { kind: "string" },
  operationId: { kind: "string" },
  tenantId: { kind: "string" },
  matterId: { kind: "string" },
  actorId: { kind: "string" },
  operation: { kind: "enum", values: AI_OPERATIONS },
  dictionaryVersion: { kind: "bigintOrNull" },
  engineVersion: { kind: "string" },
  counts: { kind: "totalCounts" },
  ambiguityCount: { kind: "number" },
  detectorName: { kind: "stringOrNull" },
  detectorVersion: { kind: "stringOrNull" },
  latencyMs: { kind: "exactObject", fields: LATENCY_SCHEMA },
  preparedAt: { kind: "string" },
};

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function safeOperationId(candidate: unknown): OperationId | null {
  if (isPlainObject(candidate) && typeof candidate["operationId"] === "string") {
    return candidate["operationId"] as OperationId;
  }
  return null;
}

function reject(candidate: unknown, path: string): never {
  throw new PhiAuditError("AUDIT_SCHEMA_REJECTED", safeOperationId(candidate), { path });
}

function missing(candidate: unknown, path: string): never {
  throw new PhiAuditError("AUDIT_REQUIRED_FIELD_MISSING", safeOperationId(candidate), { path });
}

function validateField(root: unknown, value: unknown, spec: FieldSpec, path: string): void {
  switch (spec.kind) {
    case "literal":
      if (value !== spec.value) reject(root, path);
      return;
    case "string":
      if (typeof value !== "string") reject(root, path);
      return;
    case "stringOrNull":
      if (value !== null && typeof value !== "string") reject(root, path);
      return;
    case "bigintOrNull":
      if (value !== null && typeof value !== "bigint") reject(root, path);
      return;
    case "number":
      if (typeof value !== "number" || !Number.isFinite(value)) reject(root, path);
      return;
    case "enum":
      if (typeof value !== "string" || !spec.values.includes(value)) reject(root, path);
      return;
    case "totalCounts":
      validateTotalCounts(root, value, path);
      return;
    case "exactObject":
      validateObject(root, value, spec.fields, path);
      return;
    default: {
      const exhaustive: never = spec;
      throw new Error(`unreachable field spec: ${String(exhaustive)}`);
    }
  }
}

function validateTotalCounts(root: unknown, value: unknown, path: string): void {
  if (!isPlainObject(value)) reject(root, path);
  const record = value as Record<string, unknown>;
  const allowed = new Set<string>(IDENTIFIER_CLASSES);
  // Missing-required first: every identifier class must be present (explicit zeroes).
  for (const identifierClass of IDENTIFIER_CLASSES) {
    if (!Object.prototype.hasOwnProperty.call(record, identifierClass)) {
      missing(root, `${path}.${identifierClass}`);
    }
  }
  // Extra keys are rejected even when nested (CONTRACT §7 recursive allow-list).
  for (const key of Object.keys(record)) {
    if (!allowed.has(key)) reject(root, `${path}.${key}`);
  }
  for (const identifierClass of IDENTIFIER_CLASSES) {
    const count = record[identifierClass];
    if (typeof count !== "number" || !Number.isFinite(count)) reject(root, `${path}.${identifierClass}`);
  }
}

function validateObject(root: unknown, value: unknown, schema: ObjectSchema, path: string): void {
  if (!isPlainObject(value)) reject(root, path);
  const record = value as Record<string, unknown>;
  const allowed = new Set<string>(Object.keys(schema));
  // 1. Missing-required.
  for (const key of Object.keys(schema)) {
    if (!Object.prototype.hasOwnProperty.call(record, key)) {
      missing(root, path === "" ? key : `${path}.${key}`);
    }
  }
  // 2. Extra keys (recursive exact allow-list) — sensitive fields are rejected here.
  for (const key of Object.keys(record)) {
    if (!allowed.has(key)) reject(root, path === "" ? key : `${path}.${key}`);
  }
  // 3. Per-field types / nested shapes.
  for (const [key, spec] of Object.entries(schema)) {
    validateField(root, record[key], spec, path === "" ? key : `${path}.${key}`);
  }
}

function canonicalize(value: unknown, schema: ObjectSchema): Record<string, unknown> {
  const record = value as Record<string, unknown>;
  const ordered: Record<string, unknown> = {};
  for (const [key, spec] of Object.entries(schema)) {
    if (spec.kind === "totalCounts") {
      const counts = record[key] as Record<string, unknown>;
      const orderedCounts: Record<string, unknown> = {};
      for (const identifierClass of IDENTIFIER_CLASSES) {
        orderedCounts[identifierClass] = counts[identifierClass];
      }
      ordered[key] = orderedCounts;
    } else if (spec.kind === "exactObject") {
      ordered[key] = canonicalize(record[key], spec.fields);
    } else {
      ordered[key] = record[key];
    }
  }
  return ordered;
}

/**
 * Enforces the exact, recursive metadata-only allow-list for audit records and produces a
 * deterministic canonical byte form. Any extra property (sensitive or otherwise), at any nesting
 * depth, is `AUDIT_SCHEMA_REJECTED`; any missing required field is `AUDIT_REQUIRED_FIELD_MISSING`.
 */
export class ExactAllowListAuditSerializer implements PhiAuditSerializer {
  public serialize(event: PhiAuditEvent): Uint8Array {
    validateObject(event, event, EVENT_SCHEMA, "");
    const canonical = canonicalize(event, EVENT_SCHEMA);
    return new TextEncoder().encode(JSON.stringify(canonical));
  }

  public validatePrepared(record: PhiAuditPreparedRecord): void {
    validateObject(record, record, PREPARED_SCHEMA, "");
  }
}
