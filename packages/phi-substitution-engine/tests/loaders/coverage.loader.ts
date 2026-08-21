import type { ModuleHarness, OracleObservation } from "../harness-types";
import {
  CANONICAL_DISCOVERED,
  CANONICAL_REGISTRY,
  StaticSurfaceRegistryVerifier,
  checkRawConstruction,
  classifyMultimodalCarveOut,
  lintProviderHostEgress,
} from "../../src/coverage/index";
import type {
  DiscoveredEgressSite,
  EgressSurface,
  EgressSurfaceRegistry,
  SourceSymbolRef,
} from "../../src/coverage/contracts";

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

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function asString(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function asBool(value: unknown): boolean {
  return value === true;
}

function asStringArray(value: unknown): readonly string[] {
  return Array.isArray(value)
    ? value.filter((v): v is string => typeof v === "string")
    : [];
}

/** Maps a fixture `classification` label to the frozen contract classification. */
function normalizeClassification(
  raw: string | null,
): EgressSurface["classification"] {
  return raw === "reviewed-carve-out" || raw === "REVIEWED_CARVE_OUT"
    ? "REVIEWED_CARVE_OUT"
    : "ENGINE_COVERED";
}

/** Builds a live discovered site from a fixture symbol reference. */
function toDiscoveredSite(entry: unknown): DiscoveredEgressSite | null {
  if (!isRecord(entry)) return null;
  const file = asString(entry.file);
  const symbol = asString(entry.symbol);
  if (file === null || symbol === null) return null;
  const repository =
    asString(entry.repository) === "adjudica-ai-app"
      ? "adjudica-ai-app"
      : "glassy-user-production";
  return {
    source: { repository, file, symbol },
    evidence: "KNOWN_ADAPTER_CALL",
    providerHostOrPackage:
      asString(entry.providerHostOrPackage) ?? "openai.azure.com",
  };
}

/** Builds a single-entry registry from the M-N7-STALE-REGISTRY-ENTRY fixture. */
function registryFromFixtureEntry(
  entry: Record<string, unknown>,
): EgressSurfaceRegistry {
  const file = asString(entry.file) ?? "unknown.ts";
  const symbol = asString(entry.symbol) ?? "unknownSymbol";
  const source: SourceSymbolRef = {
    repository: "glassy-user-production",
    file,
    symbol,
  };
  const classification = normalizeClassification(
    asString(entry.classification),
  );
  const surface: EgressSurface =
    classification === "REVIEWED_CARVE_OUT"
      ? {
          classification: "REVIEWED_CARVE_OUT",
          id: `REG-${symbol}`,
          source,
          kind: "MULTIMODAL_IMAGE",
          mitigation: ["BAA_PROVIDER", "MINIMUM_NECESSARY"],
          reviewDecisionId: `RVW-${symbol}`,
          expiresAt: null,
        }
      : {
          classification: "ENGINE_COVERED",
          id: `REG-${symbol}`,
          source,
          operation: "generation",
          protectedBoundary: "ProtectedAiProvider",
        };
  return { schemaVersion: 1, surfaces: [surface] };
}

function runCoverage(
  caseId: string,
  fixture: Readonly<Record<string, unknown>>,
): OracleObservation {
  const base = baseObservation();

  switch (caseId) {
    case "M-N7-RAW-FETCH-NEW-FILE": {
      const result = lintProviderHostEgress({
        addedFile: asString(fixture.addedFile) ?? "",
        source: asString(fixture.source) ?? "",
      });
      return {
        ...base,
        buildPassed: result.ok,
        diagnostics: result.diagnostics,
      };
    }

    case "M-N7-CONSTRUCT-OUTSIDE-WRAPPER": {
      const result = checkRawConstruction({
        addedFile: asString(fixture.addedFile) ?? "",
        sourceKind: asString(fixture.sourceKind) ?? "",
        outsideProtectedModule: asBool(fixture.outsideProtectedModule),
      });
      return {
        ...base,
        buildPassed: result.ok,
        diagnostics: result.diagnostics,
      };
    }

    case "M-N7-STALE-REGISTRY-ENTRY": {
      const entry = isRecord(fixture.registryEntry)
        ? fixture.registryEntry
        : {};
      const registry = registryFromFixtureEntry(entry);
      const liveSymbols = Array.isArray(fixture.liveSymbols)
        ? fixture.liveSymbols
        : [];
      const discovered = liveSymbols
        .map(toDiscoveredSite)
        .filter((s): s is DiscoveredEgressSite => s !== null);
      const verdict = new StaticSurfaceRegistryVerifier().verify({
        registry,
        discovered,
      });
      const driftCodes = verdict.diagnostics.map((d) => d.code);
      return {
        ...base,
        buildPassed: verdict.ok,
        diagnostics: verdict.ok
          ? []
          : ["SURFACE_REGISTRY_DRIFT", ...driftCodes],
      };
    }

    case "N7-TOTAL-CLASSIFICATION": {
      const allowed = new Set(asStringArray(fixture.allowedClasses));
      const verdict = new StaticSurfaceRegistryVerifier().verify({
        registry: CANONICAL_REGISTRY,
        discovered: CANONICAL_DISCOVERED,
      });
      const unregistered = verdict.diagnostics.filter(
        (d) => d.code === "UNREGISTERED_EGRESS",
      ).length;
      const multiply = verdict.diagnostics.filter(
        (d) => d.code === "MULTIPLY_CLASSIFIED_EGRESS",
      ).length;
      // Every registered surface must fall inside the allowed class set.
      const classToLabel: Record<EgressSurface["classification"], string> = {
        ENGINE_COVERED: "engine-covered",
        REVIEWED_CARVE_OUT: "reviewed-carve-out",
      };
      const allClassesAllowed = CANONICAL_REGISTRY.surfaces.every((s) =>
        allowed.has(classToLabel[s.classification]),
      );
      return {
        ...base,
        buildPassed: verdict.ok && allClassesAllowed,
        diagnostics: verdict.diagnostics.map((d) => d.code),
        metrics: {
          unregisteredSurfaces: unregistered,
          multiplyClassifiedSurfaces: multiply,
          registeredSurfaces: CANONICAL_REGISTRY.surfaces.length,
        },
      };
    }

    case "N7-MULTIMODAL-CARVEOUT": {
      const result = classifyMultimodalCarveOut({
        surfaceKind: asString(fixture.surfaceKind) ?? "",
        substitutionClaimed: asBool(fixture.substitutionClaimed),
        mitigation: asStringArray(fixture.mitigation),
      });
      return {
        ...base,
        buildPassed: result.buildPassed,
        metrics: {
          engineCovered: result.engineCovered,
          reviewedCarveout: result.reviewedCarveout,
        },
      };
    }

    default:
      return {
        ...base,
        buildPassed: false,
        diagnostics: [`UNKNOWN_COVERAGE_CASE:${caseId}`],
      };
  }
}

export function loadCoverageHarness(): ModuleHarness {
  return {
    run(
      caseId: string,
      fixture: Readonly<Record<string, unknown>>,
    ): Promise<OracleObservation> {
      return Promise.resolve(runCoverage(caseId, fixture));
    },
  };
}
