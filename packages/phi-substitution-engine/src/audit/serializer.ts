import type { OperationId } from "../core/brands";
import type { AiOperation } from "../core/contracts";
import type {
  PhiAuditEvent,
  PhiAuditOutcome,
  PhiAuditPreparedRecord,
  PhiAuditSerializer,
} from "./ports";
import { IDENTIFIER_CLASSES } from "./counts";
import { PhiAuditError } from "./errors";
import { safeOwnKeys } from "../core/boundary-snapshot";

const AI_OPERATIONS: readonly AiOperation[] = [
  "generation",
  "stream",
  "embedding",
  "graph_extraction",
];
const AUDIT_OUTCOMES: readonly PhiAuditOutcome[] = [
  "completed",
  "cancelled",
  "interrupted",
  "failed_closed",
  "reversal_failed",
  "unknown_after_send",
];

/**
 * The ONLY non-null strings a terminal `failureCode` may carry (§7/N2). Without this value
 * allow-list a terminal event constructed with `preparedToTerminalEvent(prepared, outcome, <raw>, …)`
 * would persist an arbitrary — possibly PHI-laden — string into the durable audit record. This is
 * the last gate before persistence, so it must enumerate EVERY fixed failure code the
 * coordinator/wrapper legitimately record plus the three fixed fallbacks
 * (`FAILED_CLOSED` from the wrapper's `errorCodeString`, `PRECONDITION_FAILED` /
 * `PROVIDER_INVOCATION_FAILED` from the coordinator). Keep in sync with `core/errors.ts` and those
 * two call sites; a missing entry fails a legitimate terminal closed rather than leaking.
 * `CALL_INTERRUPTED` is intentionally EXCLUDED: interruption has outcome `interrupted` and a null
 * failureCode, so admitting it here would collapse the distinct non-failure terminal (GLY-353 R1).
 */
const TERMINAL_FAILURE_CODES: readonly string[] = [
  "MISSING_TRUSTED_CONTEXT",
  "MISSING_TRUSTED_POLICY",
  "DICTIONARY_NOT_READY",
  "DICTIONARY_UNAVAILABLE",
  "AMBIGUOUS_KNOWN_IDENTIFIER",
  "DETECTOR_UNAVAILABLE",
  "INVALID_DETECTOR_OFFSET",
  "UNCLASSIFIED_PROVIDER_FIELD",
  "AUDIT_DURABILITY_UNAVAILABLE",
  "REVERSAL_FAILED",
  "PROVIDER_SAFETY_GATE_FAILED",
  "FAILED_CLOSED",
  "PRECONDITION_FAILED",
  "PROVIDER_INVOCATION_FAILED",
];

/**
 * GLY-373 §3.2.5: the ONLY non-null strings a terminal `failureDetail` may carry. Same reasoning
 * as `TERMINAL_FAILURE_CODES` above — this is the last gate before persistence, so an exact value
 * allow-list is what keeps an arbitrary (possibly PHI-laden) string out of the durable record.
 * There is exactly one member today: the reversal-key canonical-mismatch discriminator.
 */
const TERMINAL_FAILURE_DETAILS: readonly string[] = [
  "reversal-key-canonical-mismatch",
];

/** A single field's expected shape. The allow-list is exact and recursive. */
type FieldSpec =
  | { readonly kind: "literal"; readonly value: string }
  | { readonly kind: "string" }
  | { readonly kind: "stringOrNull" }
  | { readonly kind: "bigintOrNull" }
  | { readonly kind: "number" }
  | { readonly kind: "enum"; readonly values: readonly string[] }
  | { readonly kind: "enumOrNull"; readonly values: readonly string[] }
  | { readonly kind: "timestamp" }
  | { readonly kind: "versionOrNull" }
  | { readonly kind: "slug" }
  | { readonly kind: "slugOrNull" }
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
  dictionaryVersion: { kind: "versionOrNull" },
  engineVersion: { kind: "slug" },
  counts: { kind: "totalCounts" },
  ambiguityCount: { kind: "number" },
  detectorName: { kind: "slugOrNull" },
  detectorVersion: { kind: "slugOrNull" },
  latencyMs: { kind: "exactObject", fields: LATENCY_SCHEMA },
  outcome: { kind: "enum", values: AUDIT_OUTCOMES },
  failureCode: { kind: "enumOrNull", values: TERMINAL_FAILURE_CODES },
  failureDetail: { kind: "enumOrNull", values: TERMINAL_FAILURE_DETAILS },
  occurredAt: { kind: "timestamp" },
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
  engineVersion: { kind: "slug" },
  counts: { kind: "totalCounts" },
  ambiguityCount: { kind: "number" },
  detectorName: { kind: "slugOrNull" },
  detectorVersion: { kind: "slugOrNull" },
  latencyMs: { kind: "exactObject", fields: LATENCY_SCHEMA },
  preparedAt: { kind: "timestamp" },
};

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * Membership test that touches NO `Array.prototype`/`Set.prototype` method (§7/N2): an in-scope
 * single-method override (`Array.prototype.includes = () => true`) must not be able to approve a
 * value that is NOT in the fixed allow-list — e.g. a raw/PHI `failureCode`. Own-index + own-`length`
 * + `===` only.
 */
function listIncludes(values: readonly string[], value: string): boolean {
  const len = (values as { length: number }).length;
  for (let i = 0; i < len; i += 1) {
    if (values[i] === value) {
      return true;
    }
  }
  return false;
}

/** Strict ISO-8601 UTC instant — the ONLY shape a timestamp field may take. A caller-supplied
 *  `occurredAt` (via `reconcileUnknownAfterSend`) is otherwise free text that would persist raw. */
const ISO_8601_UTC = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?Z$/;

/** A projected dictionary version is a bigint's decimal string (or null). Without this, a metadata
 *  string field (§7 line 73) would accept arbitrary — possibly PHI — text into the durable record. */
const DECIMAL_VERSION = /^\d{1,20}$/;

/** A detector name/version is a conservative slug (or null) — never free text. */
const SAFE_SLUG = /^[A-Za-z0-9._-]{1,64}$/;

function safeOperationId(candidate: unknown): OperationId | null {
  if (
    isPlainObject(candidate) &&
    typeof candidate["operationId"] === "string"
  ) {
    return candidate["operationId"] as OperationId;
  }
  return null;
}

function reject(candidate: unknown, path: string): never {
  throw new PhiAuditError("AUDIT_SCHEMA_REJECTED", safeOperationId(candidate), {
    path,
  });
}

function missing(candidate: unknown, path: string): never {
  throw new PhiAuditError(
    "AUDIT_REQUIRED_FIELD_MISSING",
    safeOperationId(candidate),
    { path },
  );
}

function validateField(
  root: unknown,
  value: unknown,
  spec: FieldSpec,
  path: string,
): void {
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
      if (typeof value !== "number" || !Number.isFinite(value))
        reject(root, path);
      return;
    case "enum":
      if (typeof value !== "string" || !listIncludes(spec.values, value))
        reject(root, path);
      return;
    case "enumOrNull":
      if (
        value !== null &&
        (typeof value !== "string" || !listIncludes(spec.values, value))
      )
        reject(root, path);
      return;
    case "timestamp":
      if (typeof value !== "string" || !ISO_8601_UTC.test(value))
        reject(root, path);
      return;
    case "versionOrNull":
      if (
        value !== null &&
        (typeof value !== "string" || !DECIMAL_VERSION.test(value))
      )
        reject(root, path);
      return;
    case "slugOrNull":
      if (
        value !== null &&
        (typeof value !== "string" || !SAFE_SLUG.test(value))
      )
        reject(root, path);
      return;
    case "slug":
      if (typeof value !== "string" || !SAFE_SLUG.test(value))
        reject(root, path);
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

function validateTotalCounts(
  root: unknown,
  value: unknown,
  path: string,
): void {
  if (!isPlainObject(value)) reject(root, path);
  const record = value as Record<string, unknown>;
  // Missing-required first: every identifier class must be present (explicit zeroes).
  for (const identifierClass of IDENTIFIER_CLASSES) {
    if (!Object.prototype.hasOwnProperty.call(record, identifierClass)) {
      missing(root, `${path}.${identifierClass}`);
    }
  }
  // Extra keys are rejected even when nested (CONTRACT §7 recursive allow-list). Membership is
  // override-proof (no `Set.prototype.has`), so a hostile `has` cannot approve a sensitive key. §7/N2:
  // the unexpected key itself is attacker-controlled and could BE the PHI, so it is NEVER echoed into
  // the rejection's caller-visible `.path` — only the fixed nested location is reported.
  for (const key of Object.keys(record)) {
    if (!listIncludes(IDENTIFIER_CLASSES, key))
      reject(root, `${path}.<unexpected>`);
  }
  for (const identifierClass of IDENTIFIER_CLASSES) {
    const count = record[identifierClass];
    if (typeof count !== "number" || !Number.isFinite(count))
      reject(root, `${path}.${identifierClass}`);
  }
}

function validateObject(
  root: unknown,
  value: unknown,
  schema: ObjectSchema,
  path: string,
): void {
  if (!isPlainObject(value)) reject(root, path);
  const record = value as Record<string, unknown>;
  const allowed = Object.keys(schema);
  // 1. Missing-required.
  for (const key of allowed) {
    if (!Object.prototype.hasOwnProperty.call(record, key)) {
      missing(root, path === "" ? key : `${path}.${key}`);
    }
  }
  // 2. Extra keys (recursive exact allow-list) — sensitive fields are rejected here. Membership is
  // override-proof (no `Set.prototype.has`). §7/N2: the UNEXPECTED key is attacker-controlled and
  // could ITSELF be the PHI, so it is NEVER echoed into the rejection's `.path` (which reaches the
  // caller) — only the fixed parent location is reported.
  for (const key of Object.keys(record)) {
    if (!listIncludes(allowed, key))
      reject(root, path === "" ? "<unexpected>" : `${path}.<unexpected>`);
  }
  // 3. Per-field types / nested shapes.
  for (const [key, spec] of Object.entries(schema)) {
    validateField(
      root,
      record[key],
      spec,
      path === "" ? key : `${path}.${key}`,
    );
  }
}

function canonicalize(
  value: unknown,
  schema: ObjectSchema,
): Record<string, unknown> {
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

/** A field whose getter THROWS (its message could carry PHI) is replaced with this sentinel, which
 *  fails EVERY FieldSpec — the record is AUDIT_SCHEMA_REJECTED, never persisted or surfaced raw. */
const THROWING_FIELD_SENTINEL: unique symbol = Symbol(
  "phi-audit-throwing-field",
);

/** Reads one own field getter-throw-safe (§7/N2): a throwing getter yields the reject sentinel. */
function readOnceSafe(obj: Record<string, unknown>, key: string): unknown {
  try {
    return obj[key];
  } catch {
    return THROWING_FIELD_SENTINEL;
  }
}

function materializeShallow(value: unknown): unknown {
  if (!isPlainObject(value)) {
    return value;
  }
  const out: Record<string, unknown> = {};
  // §7/N2: `value` is boundary data — a hostile `Proxy` `ownKeys`/`getOwnPropertyDescriptor` trap must
  // yield NO keys, never re-throw a raw (PHI) error out of this sanitizer (`Object.keys` would).
  for (const key of safeOwnKeys(value)) {
    out[key] = readOnceSafe(value, key); // single, throw-safe read
  }
  return out;
}

/**
 * Reads every own field of `value` EXACTLY ONCE into a plain snapshot (recursively for the schema's
 * nested objects), so the subsequent validate + canonicalize passes read inert data (§7/N2 TOCTOU):
 * a getter that returns a valid value on the validation read and a PHI value on the canonicalization
 * / persistence read cannot get a validated-but-different value into the durable bytes. Extra keys
 * are preserved so the exact-allow-list rejection still fires on them.
 */
function materialize(value: unknown, schema: ObjectSchema): unknown {
  if (!isPlainObject(value)) {
    return value;
  }
  const out: Record<string, unknown> = {};
  // §7/N2: `value` is boundary data — a hostile `Proxy` `ownKeys` trap must yield NO keys, never
  // re-throw a raw (PHI) error out of this sanitizer (`Object.keys` would).
  for (const key of safeOwnKeys(value)) {
    const spec = schema[key];
    const raw = readOnceSafe(value, key); // single, throw-safe read of a possibly-getter field
    if (spec !== undefined && spec.kind === "exactObject") {
      out[key] = materialize(raw, spec.fields);
    } else if (spec !== undefined && spec.kind === "totalCounts") {
      out[key] = materializeShallow(raw);
    } else {
      out[key] = raw;
    }
  }
  return out;
}

/**
 * Read-once, validated, plain-object projection of a terminal event (§7/N2). Every field is read a
 * SINGLE time, validated against the exact allow-list, and returned as inert data — so a store that
 * persists the returned event can never re-read a mutating getter into a PHI value.
 */
export function sanitizeTerminalEvent(event: PhiAuditEvent): PhiAuditEvent {
  const snapshot = materialize(event, EVENT_SCHEMA);
  validateObject(snapshot, snapshot, EVENT_SCHEMA, "");
  return canonicalize(snapshot, EVENT_SCHEMA) as unknown as PhiAuditEvent;
}

/**
 * Read-once, validated, plain-object projection of a PREPARED record (§7/N2), symmetric with
 * {@link sanitizeTerminalEvent}: every field is read a SINGLE time and validated, so a durable store
 * that persists the returned record can never re-read a mutating/throwing getter into a PHI value.
 */
export function sanitizePreparedRecord(
  record: PhiAuditPreparedRecord,
): PhiAuditPreparedRecord {
  const snapshot = materialize(record, PREPARED_SCHEMA);
  validateObject(snapshot, snapshot, PREPARED_SCHEMA, "");
  return canonicalize(
    snapshot,
    PREPARED_SCHEMA,
  ) as unknown as PhiAuditPreparedRecord;
}

/**
 * Enforces the exact, recursive metadata-only allow-list for audit records and produces a
 * deterministic canonical byte form. Any extra property (sensitive or otherwise), at any nesting
 * depth, is `AUDIT_SCHEMA_REJECTED`; any missing required field is `AUDIT_REQUIRED_FIELD_MISSING`.
 */
export class ExactAllowListAuditSerializer implements PhiAuditSerializer {
  public serialize(event: PhiAuditEvent): Uint8Array {
    // Read-once snapshot → validate → canonical bytes (§7/N2 TOCTOU-safe).
    return new TextEncoder().encode(
      JSON.stringify(sanitizeTerminalEvent(event)),
    );
  }

  public validatePrepared(record: PhiAuditPreparedRecord): void {
    // §7/N2: validate a READ-ONCE, throw-safe snapshot — a hostile throwing/mutating field getter
    // yields the reject sentinel via `materialize`, so validation fails closed with
    // AUDIT_SCHEMA_REJECTED instead of propagating the getter's raw (PHI) throw to the caller. (The
    // emitter already hands this an inert snapshot; this keeps the EXPORTED port safe on its own.)
    const snapshot = materialize(record, PREPARED_SCHEMA);
    validateObject(snapshot, snapshot, PREPARED_SCHEMA, "");
  }
}
