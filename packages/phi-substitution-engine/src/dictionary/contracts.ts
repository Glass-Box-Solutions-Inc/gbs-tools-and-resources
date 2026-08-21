import type {
  DictionaryVersion,
  EngineVersion,
  KnownLocale,
  MatterId,
  SchemaVersion,
  SubjectId,
  SubstitutionToken,
  TenantId,
  TokenRole,
  Utf16Offset,
} from "../core/brands";
import type { IdentifierClass, TrustedMatterAiPolicy } from "../core/contracts";

export type ExpanderKind =
  | "person-name"
  | "date"
  | "ssn"
  | "structured-id"
  | "email"
  | "phone"
  | "address"
  | "literal";

export interface TaggedFieldDefinition {
  readonly schemaPath: string;
  readonly substitution: true;
  readonly identifierClass: IdentifierClass;
  /** Versioned allow-listed metadata, never derived from case data. */
  readonly tokenRole: TokenRole;
  readonly subjectKeyPath?: string;
  readonly expander: ExpanderKind;
  readonly options?: Readonly<Record<string, boolean | number | string>>;
}

export interface NonSubstitutedFieldDefinition {
  readonly schemaPath: string;
  readonly substitution: false;
  readonly rationale: string;
}

export type ScalarFieldPrivacyClassification =
  | TaggedFieldDefinition
  | NonSubstitutedFieldDefinition;

export interface ExtractionSchemaScalarPath {
  readonly schemaPath: string;
  readonly valueType: "string" | "number" | "boolean" | "date";
}

/** CI-facing, total projection. Missing, duplicate, or stale classifications are errors. */
export interface FieldTagProjection {
  readonly schemaVersion: SchemaVersion;
  readonly tagged: readonly TaggedFieldDefinition[];
  readonly untaggedWithRationale: readonly NonSubstitutedFieldDefinition[];
}

export interface FieldTagProjector {
  project(
    input: Readonly<{
      schemaVersion: SchemaVersion;
      scalarPaths: readonly ExtractionSchemaScalarPath[];
      classifications: readonly ScalarFieldPrivacyClassification[];
    }>,
  ): FieldTagProjection;
}

export interface TaggedValue {
  readonly field: TaggedFieldDefinition;
  readonly subjectId: SubjectId;
  readonly canonicalDisplayValue: string;
  /** Trusted aliases only. Old corrected values remain encrypted substitution-only aliases. */
  readonly approvedAliases: readonly string[];
}

export interface CaseTruthReader {
  readTaggedValues(
    key: Readonly<{
      tenantId: TenantId;
      matterId: MatterId;
      dictionaryVersion: DictionaryVersion;
      sourceTruthRevision: string;
    }>,
  ): Promise<readonly TaggedValue[]>;
}

export type VariantSource = "canonical" | "expanded" | "approved_alias";
export type BoundaryMode = "unicode_word" | "unicode_digit" | "structured";

export interface VariantCandidate {
  readonly normalized: string;
  readonly matchText: string;
  readonly identifierClass: IdentifierClass;
  readonly subjectId: SubjectId;
  readonly token: SubstitutionToken;
  readonly source: VariantSource;
  readonly specificity: number;
  readonly suffixMode: "none" | "possessive";
  readonly boundaryMode: BoundaryMode;
}

export interface CompileInput {
  readonly tenantId: TenantId;
  readonly matterId: MatterId;
  readonly policy: TrustedMatterAiPolicy;
  readonly dictionaryVersion: DictionaryVersion;
  readonly engineVersion: EngineVersion;
  readonly schemaVersion: SchemaVersion;
  readonly sourceTruthRevision: string;
}

export interface DictionaryMatchCandidate {
  readonly startUtf16: Utf16Offset;
  readonly endUtf16: Utf16Offset;
  readonly candidate: VariantCandidate;
}

/** Opaque, immutable READY automaton. Expanded values must never be serialized or logged. */
export interface CompiledDictionary {
  readonly tenantId: TenantId;
  readonly matterId: MatterId;
  readonly dictionaryVersion: DictionaryVersion;
  readonly engineVersion: EngineVersion;
  readonly schemaVersion: SchemaVersion;
  readonly status: "READY";
  match(originalText: string): readonly DictionaryMatchCandidate[];
}

export interface DictionaryCompiler {
  /** Never returns BUILDING/FAILED/old versions and never silently serves stale cache content. */
  compile(input: CompileInput): Promise<CompiledDictionary>;
}

export interface CompiledDictionaryCache {
  get(
    key: Readonly<{
      tenantId: TenantId;
      matterId: MatterId;
      dictionaryVersion: DictionaryVersion;
      engineVersion: EngineVersion;
      schemaVersion: SchemaVersion;
    }>,
  ): Promise<CompiledDictionary | null>;
  publish(dictionary: CompiledDictionary): Promise<void>;
  invalidateMatter(
    input: Readonly<{ tenantId: TenantId; matterId: MatterId }>,
  ): Promise<void>;
}

export interface TokenAssignmentPort {
  /** Stable by tenant+matter+subject+role; sequence numbers are monotonic and never reused. */
  requireAssignment(
    input: Readonly<{
      tenantId: TenantId;
      matterId: MatterId;
      subjectId: SubjectId;
      role: TokenRole;
      dictionaryVersion: DictionaryVersion;
    }>,
  ): Promise<SubstitutionToken>;
}

export interface DictionaryVersionCoordinator {
  /** Participates in the same transaction as a tagged case-truth write. */
  advanceForCommittedTruthWrite(
    input: Readonly<{
      tenantId: TenantId;
      matterId: MatterId;
      schemaVersion: SchemaVersion;
      sourceTruthRevision: string;
    }>,
  ): Promise<DictionaryVersion>;
  requireActiveReady(
    input: Readonly<{
      tenantId: TenantId;
      matterId: MatterId;
    }>,
  ): Promise<DictionaryVersion>;
}

export interface VariantExpansionContext {
  readonly locale: KnownLocale;
  readonly token: SubstitutionToken;
}

export interface VariantExpansionResult {
  readonly candidates: readonly VariantCandidate[];
  readonly rejected: readonly Readonly<{
    reason:
      | "AMBIGUOUS_LOCALE"
      | "INSUFFICIENT_DISTINCTIVENESS"
      | "UNAPPROVED_ALIAS"
      | "LOSSY_FORM"
      | "UNSUPPORTED_FORMAT";
    source: VariantSource;
  }>[];
}

export interface VariantExpander<K extends ExpanderKind = ExpanderKind> {
  readonly kind: K;
  expand(
    value: TaggedValue,
    context: VariantExpansionContext,
  ): VariantExpansionResult;
}

/** Deterministic name forms only; nicknames require `approvedAliases`. */
export type PersonNameVariantExpander = VariantExpander<"person-name">;

/** Full dates only; an ambiguous numeric date requires a known locale and one interpretation. */
export type DateVariantExpander = VariantExpander<"date">;

export interface StructuredIdentifierPolicy {
  readonly identifierClass:
    | "SSN"
    | "MRN"
    | "DEA"
    | "CLAIM_NUMBER"
    | "POLICY_NUMBER"
    | "ACCOUNT_NUMBER";
  readonly requiredAlphaPrefix: string | null;
  readonly permittedSeparators: readonly ("-" | " " | "/" | ".")[];
  readonly allowCompactForm: boolean;
  readonly allowSsnLastFour: boolean;
  readonly minimumAlphanumericLength: number;
}

/** Applies only explicit class policy; arbitrary punctuation stripping is forbidden. */
export interface StructuredIdVariantExpander extends VariantExpander<
  "ssn" | "structured-id"
> {
  expand(
    value: TaggedValue,
    context: VariantExpansionContext &
      Readonly<{ policy: StructuredIdentifierPolicy }>,
  ): VariantExpansionResult;
}
