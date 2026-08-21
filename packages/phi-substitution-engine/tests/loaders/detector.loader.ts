import type { ModuleHarness, OracleObservation } from "../harness-types";
import type {
  MatterId,
  OperationAttemptId,
  OperationId,
  SubstitutionToken,
  TenantId,
  Utf16Offset,
} from "../../src/core/brands";
import type { IdentifierClass } from "../../src/core/contracts";
import type {
  DetectorArtifactDescriptor,
  DetectorInput,
  DetectorProviderName,
  DetectorRedactorPort,
  OffsetEncoding,
  RawDetectedSpan,
  RedactionInstruction,
} from "../../src/detectors/ports";
import type {
  BodyLoggingDisabledHttpClient,
  PhileasWireResponse,
} from "../../src/detectors/phileas-service-adapter";
import type { DetectorArtifactIdentity } from "../../src/detectors/artifact-pin";
import type { DetectorRequestMeta } from "../../src/detectors/phileas-http-adapter";

import { Utf16SpanNormalizer } from "../../src/detectors/normalizer";
import { applyReplacementPlan } from "../../src/detectors/redaction";
import { verifyDetectorArtifact } from "../../src/detectors/artifact-pin";
import { SharedDeadlineDetectorRunner } from "../../src/detectors/deadline-runner";
import { runDetectionBelt } from "../../src/detectors/belt";
import { PhileasHttpAdapter } from "../../src/detectors/phileas-http-adapter";

const DETECTOR_VERSION = "det-v1";

// ---------------------------------------------------------------------------
// Fixture coercion helpers
// ---------------------------------------------------------------------------

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function asString(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function asNumber(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function codeOf(error: unknown): string | null {
  if (error && typeof error === "object" && "code" in error) {
    const code = (error as { code?: unknown }).code;
    if (typeof code === "string") {
      return code;
    }
  }
  return null;
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

function makeRequest(text: string): DetectorInput {
  return {
    tenantId: "tenant-1" as TenantId,
    matterId: "matter-1" as MatterId,
    operationId: "op-1" as OperationId,
    attemptId: "attempt-1" as OperationAttemptId,
    text,
    locale: "en-US",
    classes: ["PERSON_NAME"] as IdentifierClass[],
    preparedPolicy: null,
  };
}

function descriptorFor(
  name: DetectorProviderName,
  overrides: Partial<DetectorArtifactDescriptor> = {},
): DetectorArtifactDescriptor {
  return {
    name,
    serviceVersion: "svc-1.0.0",
    engineVersion: DETECTOR_VERSION,
    modelVersion: "model-1",
    recognizerVersion: "wc-7",
    configurationDigest: "sha256:test",
    residency: "local",
    localProcessing: name === "phileas-4-gliner",
    ...overrides,
  };
}

interface DetectCounter {
  calls: number;
}

function makeFakePort(opts: {
  descriptor: DetectorArtifactDescriptor;
  health: "ready" | "degraded" | "unavailable";
  counter: DetectCounter;
  onDetect: (signal: AbortSignal) => Promise<readonly RawDetectedSpan[]>;
}): DetectorRedactorPort {
  return {
    descriptor: opts.descriptor,
    async health() {
      return opts.health;
    },
    async detect(_input: DetectorInput, signal: AbortSignal) {
      opts.counter.calls += 1;
      return opts.onDetect(signal);
    },
    async redact() {
      throw new Error("REDACT_NOT_SUPPORTED_IN_FAKE");
    },
  };
}

/** Abortable delay used only to simulate sidecar latency in the deadline tests. */
function delay(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(new Error("aborted"));
      return;
    }
    const timer = setTimeout(() => {
      signal.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    const onAbort = (): void => {
      clearTimeout(timer);
      reject(new Error("aborted"));
    };
    signal.addEventListener("abort", onAbort, { once: true });
  });
}

function asInstructions(value: unknown): RedactionInstruction[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.map((entry) => {
    const record = isRecord(entry) ? entry : {};
    const span = Array.isArray(record.span) ? record.span : [0, 0];
    return {
      detectedSpanId: String(record.id),
      startUtf16: Number(span[0]) as Utf16Offset,
      endUtf16: Number(span[1]) as Utf16Offset,
      replacement: String(record.token) as SubstitutionToken,
    };
  });
}

function asRawSpans(value: unknown): RawDetectedSpan[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.map((entry) => {
    const record = isRecord(entry) ? entry : {};
    return {
      id: String(record.id),
      start: Number(record.start),
      end: Number(record.end),
      offsetEncoding: (asString(record.encoding) ?? "UTF16") as OffsetEncoding,
      identifierClass: "PERSON_NAME" as IdentifierClass,
      confidence: 1,
      detectorVersion: DETECTOR_VERSION,
    };
  });
}

function asArtifactIdentity(value: unknown): DetectorArtifactIdentity {
  const record = isRecord(value) ? value : {};
  return {
    engine: String(record.engine ?? ""),
    model: String(record.model ?? ""),
    recognizers: String(record.recognizers ?? ""),
    configDigest: String(record.configDigest ?? ""),
  };
}

// ---------------------------------------------------------------------------
// Per-case drivers over real production ports
// ---------------------------------------------------------------------------

/** SEC-PHASE1-01: DISABLED_PHASE_1 → core must not touch either adapter. */
async function runDisabled(
  fixture: Readonly<Record<string, unknown>>,
): Promise<OracleObservation> {
  const counter: DetectCounter = { calls: 0 };
  const primary = makeFakePort({
    descriptor: descriptorFor("phileas-4-gliner"),
    health: "ready",
    counter,
    onDetect: async () => [
      {
        id: "would-not-run",
        start: 0,
        end: 3,
        offsetEncoding: "UTF16",
        identifierClass: "PERSON_NAME" as IdentifierClass,
        confidence: 1,
        detectorVersion: DETECTOR_VERSION,
      },
    ],
  });

  const result = await runDetectionBelt({
    detectorRequirement: "DISABLED_PHASE_1",
    primary,
    fallback: null,
    fallbackEligibility: null,
    request: makeRequest(asString(fixture.input) ?? ""),
    deadlineMs: 100,
    runner: new SharedDeadlineDetectorRunner(),
    normalizer: new Utf16SpanNormalizer(),
  });

  return {
    ...baseObservation(),
    detectorCalls: counter.calls,
    detectorName: result.invoked ? result.descriptor.name : null,
  };
}

/** SEC-PHILEAS-01: Phileas adapter returns versioned typed spans and never logs bodies. */
async function runWireContract(
  fixture: Readonly<Record<string, unknown>>,
): Promise<OracleObservation> {
  const descriptorFixture = isRecord(fixture.descriptor)
    ? fixture.descriptor
    : {};
  const descriptor = descriptorFor("phileas-4-gliner", {
    engineVersion: asString(descriptorFixture.engineVersion) ?? "4.2.0",
    modelVersion: asString(descriptorFixture.modelVersion) ?? "gliner-pinned",
    localProcessing: descriptorFixture.localProcessing === true,
  });

  let bodyLogCount = 0;
  const observe = (meta: DetectorRequestMeta): void => {
    // A metadata event carries no body/headers/text by type; count any leak defensively.
    if ("body" in meta || "text" in meta || "headers" in meta) {
      bodyLogCount += 1;
    }
  };

  const http: BodyLoggingDisabledHttpClient = {
    async postJson(): Promise<PhileasWireResponse> {
      return {
        kind: "DETECTED",
        descriptor,
        spans: [
          {
            id: "d1",
            start: 0,
            end: 12,
            offsetEncoding: "UTF16",
            identifierClass: "PERSON_NAME" as IdentifierClass,
            confidence: 0.99,
            detectorVersion: descriptor.engineVersion,
          },
        ],
      };
    },
    async delete(): Promise<void> {
      /* no-op fake */
    },
  };

  const adapter = new PhileasHttpAdapter({ descriptor }, http, observe);
  const text = asString(fixture.text) ?? "";
  const spans = await adapter.detect(
    makeRequest(text),
    new AbortController().signal,
  );

  return {
    ...baseObservation(),
    detectorName: descriptor.name,
    detectorCalls: 1,
    detectorRequestBodiesLogged: bodyLogCount,
    metrics: {
      localProcessing: descriptor.localProcessing,
      engineVersion: descriptor.engineVersion,
      spanCount: spans.length,
    },
  };
}

/** SEC-PHILEAS-02: explicit replacement plan applied exactly, not invented. */
async function runReplacementPlan(
  fixture: Readonly<Record<string, unknown>>,
): Promise<OracleObservation> {
  const text = asString(fixture.text) ?? "";
  const plan = applyReplacementPlan(text, asInstructions(fixture.instructions));
  if (!plan.ok) {
    return { ...baseObservation(), errorCode: "INVALID_DETECTOR_OFFSET" };
  }
  return {
    ...baseObservation(),
    tokenizedText: plan.text as string,
    appliedSpanIds: plan.appliedSpanIds,
  };
}

/** SEC-L12-02 / M-L12-TRUST-INVALID-DETECTOR-OFFSET: invalid offsets fail closed. */
async function runInvalidOffset(
  fixture: Readonly<Record<string, unknown>>,
): Promise<OracleObservation> {
  const text = asString(fixture.text) ?? "";
  const normalizer = new Utf16SpanNormalizer();
  const result = normalizer.normalize(
    text,
    DETECTOR_VERSION,
    asRawSpans(fixture.rawSpans),
  );
  if (result.ok) {
    return { ...baseObservation(), providerCalls: 0, errorCode: null };
  }
  return {
    ...baseObservation(),
    providerCalls: 0,
    errorCode: "INVALID_DETECTOR_OFFSET",
  };
}

/** SEC-N4-03 / M-N4-BELT-FAIL-OPEN: required belt outage fails closed. */
async function runBothUnavailable(
  fixture: Readonly<Record<string, unknown>>,
): Promise<OracleObservation> {
  const counter: DetectCounter = { calls: 0 };
  const primary = makeFakePort({
    descriptor: descriptorFor("phileas-4-gliner"),
    health: "unavailable",
    counter,
    onDetect: async () => [],
  });
  const fallback = makeFakePort({
    descriptor: descriptorFor("azure-ai-language-phi"),
    health: "unavailable",
    counter,
    onDetect: async () => [],
  });

  try {
    await runDetectionBelt({
      detectorRequirement: "REQUIRED",
      primary,
      fallback,
      fallbackEligibility: {
        eligible: true,
        residencyApproved: true,
        baaApproved: true,
      },
      request: makeRequest(asString(fixture.freeTextCanary) ?? ""),
      deadlineMs: 100,
      runner: new SharedDeadlineDetectorRunner(),
      normalizer: new Utf16SpanNormalizer(),
    });
    return { ...baseObservation(), providerCalls: 0, errorCode: null };
  } catch (error) {
    return { ...baseObservation(), providerCalls: 0, errorCode: codeOf(error) };
  }
}

/** PERF-L9-02 / M-L9-BELT-NO-DEADLINE: primary and fallback share one deadline. */
async function runSharedDeadline(
  fixture: Readonly<Record<string, unknown>>,
): Promise<OracleObservation> {
  const deadlineMs = asNumber(fixture.deadlineMs, 100);
  const primaryDelay = asNumber(fixture.primaryDelayMs, 90);
  const fallbackDelay = asNumber(fixture.fallbackDelayMs, 90);
  const counter: DetectCounter = { calls: 0 };

  const primary = makeFakePort({
    descriptor: descriptorFor("phileas-4-gliner"),
    health: "degraded",
    counter,
    onDetect: async (signal) => {
      await delay(primaryDelay, signal);
      throw new Error("primary-unavailable");
    },
  });
  const fallback = makeFakePort({
    descriptor: descriptorFor("azure-ai-language-phi"),
    health: "degraded",
    counter,
    onDetect: async (signal) => {
      await delay(fallbackDelay, signal);
      throw new Error("fallback-unavailable");
    },
  });

  const start = performance.now();
  let errorCode: string | null = null;
  try {
    await runDetectionBelt({
      detectorRequirement: "REQUIRED",
      primary,
      fallback,
      fallbackEligibility: {
        eligible: true,
        residencyApproved: true,
        baaApproved: true,
      },
      request: makeRequest("x"),
      deadlineMs,
      runner: new SharedDeadlineDetectorRunner(),
      normalizer: new Utf16SpanNormalizer(),
    });
  } catch (error) {
    errorCode = codeOf(error);
  }
  const latencyMs = performance.now() - start;

  return { ...baseObservation(), providerCalls: 0, errorCode, latencyMs };
}

/** SEC-L7-02 / M-L7-UNPIN-DETECTOR-VERSION: response artifact equals evaluated artifact. */
async function runArtifactPin(
  fixture: Readonly<Record<string, unknown>>,
): Promise<OracleObservation> {
  const result = verifyDetectorArtifact(
    asArtifactIdentity(fixture.evaluated),
    asArtifactIdentity(fixture.deployed),
  );
  return {
    ...baseObservation(),
    buildPassed: result.buildPassed,
    diagnostics: result.diagnostics,
  };
}

/** SEC-AZURE-01: Azure fallback is replaceable and independently eligible. */
async function runAzureFallback(
  fixture: Readonly<Record<string, unknown>>,
): Promise<OracleObservation> {
  const counter: DetectCounter = { calls: 0 };
  const primaryHealth = (asString(fixture.primaryHealth) ?? "unavailable") as
    | "ready"
    | "degraded"
    | "unavailable";
  const primary = makeFakePort({
    descriptor: descriptorFor("phileas-4-gliner"),
    health: primaryHealth,
    counter,
    onDetect: async () => [],
  });
  const fallback = makeFakePort({
    descriptor: descriptorFor("azure-ai-language-phi"),
    health: "ready",
    counter,
    onDetect: async () => [],
  });

  const result = await runDetectionBelt({
    detectorRequirement: "REQUIRED",
    primary,
    fallback,
    fallbackEligibility: {
      eligible: fixture.fallbackEligible === true,
      residencyApproved: fixture.residencyApproved === true,
      baaApproved: fixture.baaApproved === true,
    },
    request: makeRequest(""),
    deadlineMs: 100,
    runner: new SharedDeadlineDetectorRunner(),
    normalizer: new Utf16SpanNormalizer(),
  });

  return {
    ...baseObservation(),
    detectorCalls: counter.calls,
    detectorName: result.invoked ? result.descriptor.name : null,
    providerPayloads: [],
  };
}

export function loadDetectorHarness(): ModuleHarness {
  return {
    run(
      caseId: string,
      fixture: Readonly<Record<string, unknown>>,
    ): Promise<OracleObservation> {
      switch (caseId) {
        case "PHASE1-DETECTOR-DISABLED":
          return runDisabled(fixture);
        case "PHILEAS-WIRE-CONTRACT":
          return runWireContract(fixture);
        case "PHILEAS-EXPLICIT-REPLACEMENT-PLAN":
          return runReplacementPlan(fixture);
        case "M-L12-TRUST-INVALID-DETECTOR-OFFSET":
          return runInvalidOffset(fixture);
        case "M-N4-BELT-FAIL-OPEN":
          return runBothUnavailable(fixture);
        case "M-L9-BELT-NO-DEADLINE":
          return runSharedDeadline(fixture);
        case "M-L7-UNPIN-DETECTOR-VERSION":
          return runArtifactPin(fixture);
        case "AZURE-INDEPENDENT-FALLBACK":
          return runAzureFallback(fixture);
        default:
          return Promise.resolve(baseObservation());
      }
    },
  };
}
