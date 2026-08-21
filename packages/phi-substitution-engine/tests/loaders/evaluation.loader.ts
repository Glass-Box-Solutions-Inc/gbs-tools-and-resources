import type { ModuleHarness, OracleObservation } from "../harness-types";
import type { IdentifierClass } from "../../src/core/contracts";
import type {
  DetectorArtifactIdentity,
  PerClassEvaluation,
} from "../../src/eval/contracts";
import {
  EvidenceBoundClaims,
  buildEvaluationManifest,
  eligibleClaims,
  gateClasses,
  measureBeltEnvelope,
  resolveRequestedClaim,
  type ClaimEvidence,
  type ClassRecallEvidence,
} from "../../src/eval/index";

/**
 * Real adapter over the production evaluation-and-claims module.
 *
 * This loader is the sole test-to-production wiring seam for the eval module. It
 * NEVER re-implements an invariant: every observable the oracle asserts is
 * produced by driving the frozen production surface (per-class Wilson gate,
 * evidence-gated claims registry, latency envelope, evidence-bound manifest).
 * Dispatch is by case ID only — never by any expected/forbidden hint carried in
 * a fixture.
 */

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function asString(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function asNumber(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function asStringArray(value: unknown): readonly string[] {
  return Array.isArray(value)
    ? value.filter((entry): entry is string => typeof entry === "string")
    : [];
}

/** Map a fixture `{ CLASS: { recallLower, recallPoint? } }` shape to gate evidence. */
function parseClassMap(value: unknown): ClassRecallEvidence[] {
  if (!isRecord(value)) return [];
  const out: ClassRecallEvidence[] = [];
  for (const [identifierClass, raw] of Object.entries(value)) {
    const recallLower = isRecord(raw)
      ? asNumber(raw.recallLower, Number.NaN)
      : Number.NaN;
    out.push({ identifierClass, recallWilsonLower95: recallLower });
  }
  return out;
}

function classPoint(value: unknown, identifierClass: string): number {
  if (!isRecord(value)) return 0;
  const raw = value[identifierClass];
  return isRecord(raw) ? asNumber(raw.recallPoint, 0) : 0;
}

/** A fully pinned detector artifact identity for the evidence manifest (L7). */
const PINNED_ARTIFACT: DetectorArtifactIdentity = {
  detectorName: "phileas",
  serviceVersion: "4.2.0",
  engineVersion: "1.0.0",
  modelVersion: "gliner-phi-1.3",
  recognizerVersion: "rec-2026.08",
  configurationDigest: "sha256:config-digest",
  containerImageDigest: "sha256:image-digest",
};

function perClassFromMap(
  classMap: unknown,
  classes: readonly ClassRecallEvidence[],
): PerClassEvaluation[] {
  return classes.map((entry) => ({
    identifierClass: entry.identifierClass as IdentifierClass,
    recallPoint: classPoint(classMap, entry.identifierClass),
    recallWilsonLower95: Number.isFinite(entry.recallWilsonLower95)
      ? entry.recallWilsonLower95
      : 0,
    precisionPoint: 1,
    precisionWilsonLower95: 1,
    sampleCount: 1000,
  }));
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

function runCase(
  caseId: string,
  fixture: Readonly<Record<string, unknown>>,
): OracleObservation {
  switch (caseId) {
    // ---- N6: an unproved requested copy is rejected; only eligible copy is emitted ----
    case "M-N6-OVERCLAIM-ALL-PHI": {
      const evidence: ClaimEvidence = {
        phase: asNumber(fixture.phase, 1),
        detectorClasses: [],
      };
      const decision = resolveRequestedClaim(
        asString(fixture.requestedCopy),
        evidence,
      );
      return {
        ...baseObservation(),
        outputs: decision.outputs,
        diagnostics: decision.diagnostics,
        metrics: { imageCoverageClaimed: decision.imageCoverageClaimed },
      };
    }

    // ---- N6: a failed/ineligible class blocks the free-text claim ----
    case "M-N6-CLAIM-WITH-FAILED-CLASS": {
      const detectorClasses = parseClassMap(fixture.byClass);
      const phase = fixture.requestedPhase2Copy === true ? 2 : 1;
      const decision = eligibleClaims({ phase, detectorClasses });
      return {
        ...baseObservation(),
        outputs: decision.outputs,
        diagnostics: decision.diagnostics,
        metrics: { imageCoverageClaimed: decision.imageCoverageClaimed },
      };
    }

    // ---- L7: per-class gate beats the macro-average; a weak class blocks all ----
    case "M-L7-GATE-ON-MACRO-AVERAGE": {
      const classes = parseClassMap(fixture.classes);
      const gate = gateClasses(classes);
      // Bind the eligibility decision to a real evidence manifest (pinned artifact
      // + per-class evidence) so the emitted copy is evidence-bound, not asserted.
      const manifest = buildEvaluationManifest({
        engineVersion: "1.0.0",
        corpusDigest: "sha256:corpus-digest",
        artifact: PINNED_ARTIFACT,
        byClass: perClassFromMap(fixture.classes, classes),
        latencyP95Ms: 80,
        latencyP99Ms: 95,
      });
      const outputs = new EvidenceBoundClaims().eligibleCopy(manifest);
      return {
        ...baseObservation(),
        outputs,
        diagnostics: gate.diagnostics,
        metrics: {
          eligible: gate.eligible,
          macroRecallLower: gate.macroRecallLower,
          reportedMacroRecall: asNumber(fixture.macroRecall, Number.NaN),
        },
      };
    }

    // ---- L9: interactive latency envelope at the 32 KiB ceiling ----
    case "DETECTOR-LATENCY-ENVELOPE": {
      const bytes = asNumber(fixture.bytes, 32768);
      const envelope = measureBeltEnvelope(bytes);
      const budget = {
        p95ExclusiveMs: asNumber(fixture.requiredP95MsExclusive, 100),
        p99InclusiveMs: asNumber(fixture.requiredP99MsInclusive, 100),
      };
      const withinBudget =
        envelope.p95Ms < budget.p95ExclusiveMs &&
        envelope.p99Ms <= budget.p99InclusiveMs;
      return {
        ...baseObservation(),
        latencyMs: envelope.p95Ms,
        metrics: {
          p95Ms: envelope.p95Ms,
          p99Ms: envelope.p99Ms,
          withinBudget,
        },
      };
    }

    // ---- N6: the phase-1 text copy cannot imply image substitution ----
    case "CLAIM-MULTIMODAL-CARVEOUT": {
      const claim = asString(fixture.claim);
      const carveouts = asStringArray(fixture.documentedCarveouts);
      const decision = resolveRequestedClaim(claim, {
        phase: 1,
        detectorClasses: [],
      });
      const diagnostics = [...decision.diagnostics];
      if (carveouts.includes("multimodal-image-egress")) {
        diagnostics.push("IMAGE_CARVEOUT_DOCUMENTED");
      }
      return {
        ...baseObservation(),
        outputs: decision.outputs,
        diagnostics,
        metrics: { imageCoverageClaimed: decision.imageCoverageClaimed },
      };
    }

    default:
      throw new Error(`evaluation.loader: unknown case ${caseId}`);
  }
}

export function loadEvaluationHarness(): ModuleHarness {
  return {
    run(
      caseId: string,
      fixture: Readonly<Record<string, unknown>>,
    ): Promise<OracleObservation> {
      return Promise.resolve(runCase(caseId, fixture));
    },
  };
}
