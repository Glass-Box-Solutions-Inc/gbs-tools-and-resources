import type { ModuleHarness, OracleObservation } from "../harness-types";
import {
  inferIdentifierClass,
  runCollision,
  type CollisionResult,
  type KnownValue,
} from "../../src/collision/index";

const DEFAULT_LOCALE = "en-US";

function asString(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function asStringArray(value: unknown): readonly string[] {
  return Array.isArray(value)
    ? value.filter((entry): entry is string => typeof entry === "string")
    : [];
}

function asNumberArray(value: unknown): readonly number[] {
  return Array.isArray(value)
    ? value.filter(
        (entry): entry is number =>
          typeof entry === "number" && Number.isFinite(entry),
      )
    : [];
}

/**
 * Projects a frozen fixture into trusted known values. PERSON_NAME entries come
 * only from explicit trusted inputs (variants / surname / shared variant /
 * normalized variant); structured identifiers are recovered by the engine's
 * rigid-format detectors, never guessed here.
 */
function buildKnownValues(
  fixture: Readonly<Record<string, unknown>>,
): KnownValue[] {
  const known: KnownValue[] = [];

  for (const variant of asStringArray(fixture.variants)) {
    known.push({
      literal: variant,
      identifierClass: inferIdentifierClass(variant),
      subjectId: "subject-1",
    });
  }

  const surname = asString(fixture.surname);
  if (surname !== null) {
    known.push({
      literal: surname,
      identifierClass: "PERSON_NAME",
      subjectId: "subject-1",
    });
  }

  const sameVariant = asString(fixture.sameVariant);
  if (sameVariant !== null) {
    for (const subject of asStringArray(fixture.subjects)) {
      known.push({
        literal: sameVariant,
        identifierClass: "PERSON_NAME",
        subjectId: subject,
      });
    }
  }

  const normalizedVariant = asString(fixture.normalizedVariant);
  if (normalizedVariant !== null) {
    known.push({
      normalizedForm: normalizedVariant,
      identifierClass: "PERSON_NAME",
      subjectId: "subject-1",
    });
  }

  return known;
}

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

function runCollisionCase(
  caseId: string,
  fixture: Readonly<Record<string, unknown>>,
): OracleObservation {
  const originalText = asString(fixture.text) ?? "";
  const locale = asString(fixture.locale) ?? DEFAULT_LOCALE;
  const knownValues = buildKnownValues(fixture);

  const seeds = asNumberArray(fixture.randomOrderSeeds);
  if (seeds.length > 0) {
    const outputs = seeds.map((seed) => {
      const result = runCollision({
        originalText,
        locale,
        knownValues,
        shuffleSeed: seed,
      });
      return result.tokenizedText ?? "";
    });
    return { ...baseObservation(), outputs, diagnostics: [caseId] };
  }

  const result: CollisionResult = runCollision({
    originalText,
    locale,
    knownValues,
  });
  return {
    ...baseObservation(),
    tokenizedText: result.tokenizedText,
    reversedText: result.reversedText,
    candidates: result.candidates,
    ambiguityCount: result.ambiguityCount,
    errorCode: result.errorCode,
    diagnostics: [caseId],
  };
}

export function loadCollisionHarness(): ModuleHarness {
  return {
    run(
      caseId: string,
      fixture: Readonly<Record<string, unknown>>,
    ): Promise<OracleObservation> {
      return Promise.resolve(runCollisionCase(caseId, fixture));
    },
  };
}
