/**
 * The sole test-to-production wiring seam. The frozen contract intentionally ships red.
 * Each module implementer replaces its loader with a real adapter over production ports.
 */
export interface OracleObservation {
  readonly providerCalls: number;
  readonly providerPayloads: readonly string[];
  readonly selectedProvider: string | null;
  readonly routerInput: string | null;
  readonly tracePayloads: readonly string[];
  readonly displayText: string | null;
  readonly displayChunks: readonly string[];
  readonly errorCode: string | null;
  readonly tokenizedText: string | null;
  readonly reversedText: string | null;
  readonly candidates: readonly string[];
  readonly tokensBySubject: Readonly<Record<string, string>>;
  readonly ambiguityCount: number;
  readonly dictionaryVersion: string | null;
  readonly compileCount: number;
  readonly detectorCalls: number;
  readonly detectorName: string | null;
  readonly detectorRequestBodiesLogged: number;
  readonly appliedSpanIds: readonly string[];
  readonly reversalLookupCount: number;
  readonly reversalLookupTokens: readonly string[];
  readonly latencyMs: number;
  readonly auditEvents: readonly unknown[];
  readonly primaryAuditAttempts: number;
  readonly spoolRecords: readonly Readonly<{
    attemptId: string;
    plaintextOnDisk: string | null;
    ciphertextBytes: number;
    decrypted: unknown;
  }>[];
  readonly drain: Readonly<{ delivered: number; duplicates: number; remaining: number }>;
  readonly buildPassed: boolean;
  readonly diagnostics: readonly string[];
  readonly outputs: readonly string[];
  readonly metrics: Readonly<Record<string, number | string | boolean | null>>;
}

export interface ModuleHarness {
  run(caseId: string, fixture: Readonly<Record<string, unknown>>): Promise<OracleObservation>;
}

function implementationRequired(moduleName: string): never {
  throw new Error(`IMPLEMENTATION_REQUIRED:${moduleName}`);
}

export function loadVariantsHarness(): ModuleHarness {
  return implementationRequired("variants");
}

export function loadCollisionHarness(): ModuleHarness {
  return implementationRequired("collision");
}

export function loadTokensHarness(): ModuleHarness {
  return implementationRequired("tokens");
}

export function loadDictionaryHarness(): ModuleHarness {
  return implementationRequired("dictionary");
}

export function loadAuditHarness(): ModuleHarness {
  return implementationRequired("audit");
}

export function loadDetectorHarness(): ModuleHarness {
  return implementationRequired("detector-redactor-port");
}

export function loadProviderBoundaryHarness(): ModuleHarness {
  return implementationRequired("protected-provider-boundary");
}

export function loadEvaluationHarness(): ModuleHarness {
  return implementationRequired("evaluation-and-claims");
}

export function loadCoverageHarness(): ModuleHarness {
  return implementationRequired("n7-coverage");
}
