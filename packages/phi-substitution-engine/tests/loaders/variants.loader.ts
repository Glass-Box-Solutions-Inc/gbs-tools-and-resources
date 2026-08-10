import type { ModuleHarness, OracleObservation } from "../harness-types";
import {
  expandDateVariants,
  expandPersonNameVariants,
  expandStructuredIdVariants,
  replaceAllowListedVariants,
  type StructuredSeparator,
  type VariantExpansion,
} from "../../src/variants/index";

const VARIANT_PLACEHOLDER = "[[Subject_1]]";
const KNOWN_SEPARATORS: readonly StructuredSeparator[] = ["-", " ", "/", "."];

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function asString(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function asStringArray(value: unknown): readonly string[] {
  return Array.isArray(value) ? value.filter((entry): entry is string => typeof entry === "string") : [];
}

function asNumber(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function asSeparators(value: unknown): readonly StructuredSeparator[] {
  if (!Array.isArray(value)) return [];
  const out: StructuredSeparator[] = [];
  for (const entry of value) {
    if (typeof entry === "string" && (KNOWN_SEPARATORS as readonly string[]).includes(entry)) {
      out.push(entry as StructuredSeparator);
    }
  }
  return out;
}

/** A complete, safe-default observation; each run overrides only its fields. */
function baseObservation(): OracleObservation {
  return {
    providerCalls: 0,
    providerPayloads: [],
    selectedProvider: null,
    routerInput: null,
    tracePayloads: [],
    displayText: null,
    displayChunks: [],
    errorCode: null,
    tokenizedText: null,
    reversedText: null,
    candidates: [],
    tokensBySubject: {},
    ambiguityCount: 0,
    dictionaryVersion: null,
    compileCount: 0,
    detectorCalls: 0,
    detectorName: null,
    detectorRequestBodiesLogged: 0,
    appliedSpanIds: [],
    reversalLookupCount: 0,
    reversalLookupTokens: [],
    latencyMs: 0,
    auditEvents: [],
    primaryAuditAttempts: 0,
    spoolRecords: [],
    drain: { delivered: 0, duplicates: 0, remaining: 0 },
    buildPassed: true,
    diagnostics: [],
    outputs: [],
    metrics: {},
  };
}

/**
 * Drives the real phase-1 variant expanders. The expander to use is chosen from
 * the fixture's shape — a structured-id policy, a name (approved-alias) request,
 * or a date — and never from any `expected`/`forbidden` hint in the fixture.
 */
function expandFromFixture(fixture: Readonly<Record<string, unknown>>): VariantExpansion {
  const canonical = asString(fixture.canonical) ?? "";

  if (isRecord(fixture.policy)) {
    const policy = fixture.policy;
    return expandStructuredIdVariants({
      canonical,
      policy: {
        requiredAlphaPrefix: asString(policy.requiredAlphaPrefix),
        permittedSeparators: asSeparators(policy.permittedSeparators),
        allowCompactForm: policy.allowCompactForm === true,
        minimumAlphanumericLength: asNumber(policy.minimumAlphanumericLength, 0),
      },
    });
  }

  if ("approvedAliases" in fixture) {
    return expandPersonNameVariants({
      canonical,
      approvedAliases: asStringArray(fixture.approvedAliases),
      locale: asString(fixture.locale),
    });
  }

  return expandDateVariants({
    canonical,
    locale: asString(fixture.locale),
  });
}

function runVariants(
  caseId: string,
  fixture: Readonly<Record<string, unknown>>,
): OracleObservation {
  const expansion = expandFromFixture(fixture);

  // If the fixture carries surrounding free text, model egress: only exact
  // allow-listed candidates are substituted, so unrelated look-alike digits
  // survive. This is what proves no lossy identifier was invented.
  const unrelatedText = asString(fixture.unrelatedText);
  const providerPayloads =
    unrelatedText === null
      ? []
      : [replaceAllowListedVariants(unrelatedText, expansion.candidates, VARIANT_PLACEHOLDER)];

  return {
    ...baseObservation(),
    candidates: expansion.candidates,
    errorCode: expansion.errorCode,
    providerPayloads,
    providerCalls: providerPayloads.length,
    ambiguityCount: expansion.errorCode === "AMBIGUOUS_LOCALE" ? 1 : 0,
    diagnostics: [caseId],
  };
}

export function loadVariantsHarness(): ModuleHarness {
  return {
    run(caseId: string, fixture: Readonly<Record<string, unknown>>): Promise<OracleObservation> {
      return Promise.resolve(runVariants(caseId, fixture));
    },
  };
}
