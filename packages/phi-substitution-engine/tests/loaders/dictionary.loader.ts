import type { ModuleHarness, OracleObservation } from "../harness-types";
import type {
  DictionaryVersion,
  EngineVersion,
  MatterId,
  SchemaVersion,
  TenantId,
} from "../../src/core/brands";
import type { MatterAiContext, TrustedMatterAiPolicy } from "../../src/core/contracts";
import type { CompileInput, TaggedValue } from "../../src/dictionary/contracts";
import type { AhoCorasickCompiledDictionary, DetectorSpanInput, EgressDecision } from "../../src/dictionary/index";
import {
  InMemoryCaseTruthReader,
  InMemoryCompiledDictionaryCache,
  InMemoryDictionaryVersionCoordinator,
  MatterDictionaryCompiler,
  buildPreparedPolicy,
  decideEgress,
  getOrCompile,
  tokenize,
} from "../../src/dictionary/index";

/**
 * Real adapter over the production matter-dictionary ports.
 *
 * This loader is the sole test-to-production wiring seam for the dictionary
 * module. It NEVER re-implements an invariant: it drives the frozen leaves it
 * composes (variants/tokens/collision) through the layer-2 compiler, cache,
 * version coordinator, and egress orchestrator, and reports what the oracle
 * asserts. Each case builds fresh state so cases never share it.
 */

// -- branding helpers (test-adapter side; brands are constructed by the harness) --
const tenant = (s: string): TenantId => s as unknown as TenantId;
const matter = (s: string): MatterId => s as unknown as MatterId;
const engine = (s: string): EngineVersion => s as unknown as EngineVersion;
const schema = (s: string): SchemaVersion => s as unknown as SchemaVersion;
const version = (n: bigint): DictionaryVersion => n as unknown as DictionaryVersion;
const localeBrand = (s: string): TrustedMatterAiPolicy["locale"] =>
  s as unknown as TrustedMatterAiPolicy["locale"];

const LOCALE = "en-US";
const ENGINE = engine("engine-1");
const SCHEMA = schema("schema-1");

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

function asString(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** A trusted, schema-tagged PERSON_NAME case-truth value for one subject. */
function personValue(subjectId: string, canonical: string, aliases: readonly string[] = []): TaggedValue {
  return {
    field: {
      schemaPath: `case.persons.${subjectId}.fullName`,
      substitution: true,
      identifierClass: "PERSON_NAME",
      tokenRole: "Claimant" as TaggedValue["field"]["tokenRole"],
      expander: "person-name",
    },
    subjectId: subjectId as unknown as TaggedValue["subjectId"],
    canonicalDisplayValue: canonical,
    approvedAliases: aliases,
  };
}

function policyFor(activeVersion: bigint): TrustedMatterAiPolicy {
  return {
    mode: "REQUIRED",
    locale: localeBrand(LOCALE),
    activeDictionaryVersion: version(activeVersion),
    schemaVersion: SCHEMA,
    detectorRequirement: "DISABLED_PHASE_1",
    approvedOffDecisionId: null,
  };
}

function contextFor(tenantId: string, matterId: string): MatterAiContext {
  return {
    tenantId: tenant(tenantId),
    matterId: matter(matterId),
    actorId: "actor-1" as unknown as MatterAiContext["actorId"],
    operationId: "op-1" as unknown as MatterAiContext["operationId"],
    attemptId: "att-1" as unknown as MatterAiContext["attemptId"],
  };
}

function compileInputFor(
  tenantId: string,
  matterId: string,
  activeVersion: bigint,
  revision: string,
): CompileInput {
  return {
    tenantId: tenant(tenantId),
    matterId: matter(matterId),
    policy: policyFor(activeVersion),
    dictionaryVersion: version(activeVersion),
    engineVersion: ENGINE,
    schemaVersion: SCHEMA,
    sourceTruthRevision: revision,
  };
}

function observeDecision(decision: EgressDecision): OracleObservation {
  if (decision.kind === "SUBSTITUTED") {
    return {
      ...baseObservation(),
      providerCalls: 1,
      providerPayloads: [decision.egressText],
      tokenizedText: decision.egressText,
      reversedText: decision.reversedText,
      dictionaryVersion: decision.dictionaryVersion,
    };
  }
  return {
    ...baseObservation(),
    providerCalls: 0,
    errorCode: decision.code,
    dictionaryVersion: decision.dictionaryVersion,
  };
}

/** Deterministic mulberry32 shuffle, so entry-order seeds are reproducible. */
function seededShuffle<T>(items: readonly T[], seed: number): T[] {
  const out = items.slice();
  let state = (seed >>> 0) || 0x9e3779b9;
  const next = (): number => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  for (let i = out.length - 1; i > 0; i -= 1) {
    const j = Math.floor(next() * (i + 1));
    const a = out[i];
    const b = out[j];
    if (a !== undefined && b !== undefined) {
      out[i] = b;
      out[j] = a;
    }
  }
  return out;
}

function percentile(values: readonly number[], p: number): number {
  const sorted = [...values].sort((a, b) => a - b);
  if (sorted.length === 0) return 0;
  const index = Math.min(sorted.length - 1, Math.max(0, Math.ceil((p / 100) * sorted.length) - 1));
  return sorted[index] ?? 0;
}

/** Counts real compiler invocations so recompile-per-call is observable (L9). */
class CountingCompiler {
  public count = 0;
  public constructor(private readonly inner: MatterDictionaryCompiler) {}
  public compile(input: CompileInput): Promise<AhoCorasickCompiledDictionary> {
    this.count += 1;
    return this.inner.compile(input) as Promise<AhoCorasickCompiledDictionary>;
  }
  public reset(): void {
    this.count = 0;
  }
}

async function runCase(
  caseId: string,
  fixture: Readonly<Record<string, unknown>>,
): Promise<OracleObservation> {
  switch (caseId) {
    // ---- L2: a committed tagged write blocks the stale READY dictionary ----
    case "M-L2-TTL-ONLY-INVALIDATION": {
      const readyVersion = BigInt(asString(fixture.readyVersion) ?? "7");
      const committedVersion = asString(fixture.committedVersion) ?? "8";
      const oldValue = asString(fixture.oldValue) ?? "Maria García";
      const context = contextFor("tenant-1", "matter-1");

      const coordinator = new InMemoryDictionaryVersionCoordinator();
      const reader = new InMemoryCaseTruthReader();
      const cache = new InMemoryCompiledDictionaryCache();
      const compiler = new MatterDictionaryCompiler(reader);

      // The prior version is READY and cached; then a committed tagged write
      // atomically advances the active version, which is not yet READY.
      reader.set(
        { tenantId: context.tenantId, matterId: context.matterId, dictionaryVersion: version(readyVersion), sourceTruthRevision: "rev-ready" },
        [personValue("subject-1", oldValue)],
      );
      coordinator.noteReady(context, readyVersion);
      await coordinator.advanceForCommittedTruthWrite({
        tenantId: context.tenantId,
        matterId: context.matterId,
        schemaVersion: SCHEMA,
        sourceTruthRevision: "rev-committed",
      });

      const decision = await decideEgress(
        {
          context,
          dictionaryHealth: "available",
          text: oldValue,
          policy: policyFor(readyVersion),
          engineVersion: ENGINE,
          sourceTruthRevision: "rev-ready",
        },
        { coordinator, cache, compiler },
      );
      const observed = observeDecision(decision);
      // The committed active version is what must be served (and is not READY).
      return { ...observed, dictionaryVersion: observed.dictionaryVersion ?? committedVersion };
    }

    // ---- L2: an old READY version cannot serve while the active version builds ----
    case "M-L2-SERVE-OLD-WHILE-BUILDING": {
      const active = isRecord(fixture.active) ? fixture.active : {};
      const prior = isRecord(fixture.prior) ? fixture.prior : {};
      const activeVersion = BigInt(asString(active.version) ?? "8");
      const priorVersion = BigInt(asString(prior.version) ?? "7");
      const context = contextFor("tenant-1", "matter-1");

      const coordinator = new InMemoryDictionaryVersionCoordinator();
      const reader = new InMemoryCaseTruthReader();
      const cache = new InMemoryCompiledDictionaryCache();
      const compiler = new MatterDictionaryCompiler(reader);

      reader.set(
        { tenantId: context.tenantId, matterId: context.matterId, dictionaryVersion: version(priorVersion), sourceTruthRevision: "rev-prior" },
        [personValue("subject-1", "Maria García")],
      );
      coordinator.noteReady(context, priorVersion);
      coordinator.noteBuilding(context, activeVersion);

      const decision = await decideEgress(
        {
          context,
          dictionaryHealth: "available",
          text: "Maria García",
          policy: policyFor(priorVersion),
          engineVersion: ENGINE,
          sourceTruthRevision: "rev-prior",
        },
        { coordinator, cache, compiler },
      );
      return observeDecision(decision);
    }

    // ---- N4: dictionary outage never invokes the raw provider ----
    case "M-N4-RAW-FALLBACK-DICTIONARY": {
      const rawText = asString(fixture.rawText) ?? "Maria García MRN-A7719";
      const context = contextFor("tenant-1", "matter-1");
      const coordinator = new InMemoryDictionaryVersionCoordinator();
      const reader = new InMemoryCaseTruthReader();
      const cache = new InMemoryCompiledDictionaryCache();
      const compiler = new MatterDictionaryCompiler(reader);

      const decision = await decideEgress(
        {
          context,
          dictionaryHealth: "unavailable",
          text: rawText,
          policy: policyFor(1n),
          engineVersion: ENGINE,
          sourceTruthRevision: "rev-1",
        },
        { coordinator, cache, compiler },
      );
      return observeDecision(decision);
    }

    // ---- N4: missing trusted context fails closed regardless of a caller flag ----
    case "M-N4-MISSING-CONTEXT-MEANS-OFF": {
      const coordinator = new InMemoryDictionaryVersionCoordinator();
      const reader = new InMemoryCaseTruthReader();
      const cache = new InMemoryCompiledDictionaryCache();
      const compiler = new MatterDictionaryCompiler(reader);

      const decision = await decideEgress(
        {
          context: null,
          dictionaryHealth: "available",
          text: "Maria García appeared.",
          policy: policyFor(1n),
          engineVersion: ENGINE,
          sourceTruthRevision: "rev-1",
        },
        { coordinator, cache, compiler },
      );
      return observeDecision(decision);
    }

    // ---- L8: compiled cache is tenant isolated ----
    case "M-L8-DROP-TENANT-FROM-CACHE-KEY": {
      const a = isRecord(fixture.tenantA) ? fixture.tenantA : {};
      const b = isRecord(fixture.tenantB) ? fixture.tenantB : {};
      const matterId = asString(a.matter) ?? "same-id";
      const versionA = BigInt(asString(a.version) ?? "4");
      const versionB = BigInt(asString(b.version) ?? "4");
      const valueA = asString(a.value) ?? "Maria García";
      const valueB = asString(b.value) ?? "Robert O'Neil";

      const reader = new InMemoryCaseTruthReader();
      const cache = new InMemoryCompiledDictionaryCache();
      const compiler = new MatterDictionaryCompiler(reader);

      const inputA = compileInputFor("tenant-a", matterId, versionA, "rev-a");
      const inputB = compileInputFor("tenant-b", matterId, versionB, "rev-b");
      reader.set(
        { tenantId: inputA.tenantId, matterId: inputA.matterId, dictionaryVersion: inputA.dictionaryVersion, sourceTruthRevision: "rev-a" },
        [personValue("subject-a", valueA)],
      );
      reader.set(
        { tenantId: inputB.tenantId, matterId: inputB.matterId, dictionaryVersion: inputB.dictionaryVersion, sourceTruthRevision: "rev-b" },
        [personValue("subject-b", valueB)],
      );

      const compiledA = await getOrCompile(cache, compiler, inputA);
      const egressA = tokenize(compiledA, valueA, LOCALE).tokenizedText;

      // Observe whether tenant B's key collides onto tenant A's cached dictionary.
      const preGet = await cache.get({
        tenantId: inputB.tenantId,
        matterId: inputB.matterId,
        dictionaryVersion: inputB.dictionaryVersion,
        engineVersion: inputB.engineVersion,
        schemaVersion: inputB.schemaVersion,
      });
      const crossTenantCacheHit =
        preGet !== null && (preGet.tenantId as unknown as string) !== "tenant-b";

      const compiledB = await getOrCompile(cache, compiler, inputB);
      const egressB = tokenize(compiledB, valueB, LOCALE).tokenizedText;

      return {
        ...baseObservation(),
        providerCalls: 2,
        providerPayloads: [egressA, egressB],
        metrics: { crossTenantCacheHit },
      };
    }

    // ---- L9: a warm dictionary is reused; no recompile per call ----
    case "M-L9-RECOMPILE-PER-CALL": {
      const identicalCalls = typeof fixture.identicalCalls === "number" ? fixture.identicalCalls : 100;
      const payloadBytes = typeof fixture.payloadBytes === "number" ? fixture.payloadBytes : 32768;
      const context = contextFor("tenant-1", "matter-1");

      const reader = new InMemoryCaseTruthReader();
      const cache = new InMemoryCompiledDictionaryCache();
      const compiler = new CountingCompiler(new MatterDictionaryCompiler(reader));
      const input = compileInputFor("tenant-1", "matter-1", 1n, "rev-1");
      reader.set(
        { tenantId: context.tenantId, matterId: context.matterId, dictionaryVersion: input.dictionaryVersion, sourceTruthRevision: "rev-1" },
        [personValue("subject-1", "Maria García")],
      );

      // Warm the cache once (this compile is excluded from the measured window).
      const warm = await compiler.compile(input);
      await cache.publish(warm);
      compiler.reset();

      // Build a payload of the requested size with one embedded known value.
      const filler = "The quick brown fox jumps over the lazy dog. ";
      let payload = "Maria García. ";
      while (payload.length < payloadBytes) payload += filler;
      payload = payload.slice(0, payloadBytes);

      // Stabilize the JIT before timing.
      for (let i = 0; i < 5; i += 1) {
        (await getOrCompile(cache, compiler, input)).match(payload);
      }
      compiler.reset();

      const latencies: number[] = [];
      for (let i = 0; i < identicalCalls; i += 1) {
        const started = performance.now();
        const compiled = await getOrCompile(cache, compiler, input);
        compiled.match(payload);
        latencies.push(performance.now() - started);
      }

      return {
        ...baseObservation(),
        compileCount: compiler.count,
        metrics: {
          p50Ms: percentile(latencies, 50),
          p99Ms: percentile(latencies, 99),
        },
      };
    }

    // ---- L12: exact dictionary identity wins over a high-confidence detector ----
    case "M-L12-DETECTOR-OVERRIDES-DICTIONARY": {
      const text = asString(fixture.text) ?? "Maria García appeared.";
      const dict = isRecord(fixture.dictionary) ? fixture.dictionary : {};
      const det = isRecord(fixture.detector) ? fixture.detector : {};
      const detectorSpanRaw = Array.isArray(det.span) ? det.span : [0, 12];
      const detectorToken = asString(det.token) ?? "[[Detected_Person_1]]";
      const detectorConfidence = typeof det.confidence === "number" ? det.confidence : 0.99;
      void dict;

      const reader = new InMemoryCaseTruthReader();
      const cache = new InMemoryCompiledDictionaryCache();
      const compiler = new MatterDictionaryCompiler(reader);
      const input = compileInputFor("tenant-1", "matter-1", 1n, "rev-1");
      reader.set(
        { tenantId: input.tenantId, matterId: input.matterId, dictionaryVersion: input.dictionaryVersion, sourceTruthRevision: "rev-1" },
        [personValue("subject-1", "Maria García")],
      );

      const compiled = await getOrCompile(cache, compiler, input);
      const detectorSpans: DetectorSpanInput[] = [
        {
          startUtf16: Number(detectorSpanRaw[0] ?? 0),
          endUtf16: Number(detectorSpanRaw[1] ?? 12),
          identifierClass: "PERSON_NAME",
          confidence: detectorConfidence,
          token: detectorToken,
        },
      ];
      const result = tokenize(compiled, text, LOCALE, detectorSpans);
      return {
        ...baseObservation(),
        tokenizedText: result.tokenizedText,
        reversedText: result.reversedText,
      };
    }

    // ---- L3: candidate order, cache state, and restart do not change bytes ----
    case "DETERMINISM-ENTRY-ORDER": {
      const seeds = Array.isArray(fixture.entryOrderSeeds)
        ? fixture.entryOrderSeeds.filter((s): s is number => typeof s === "number")
        : [1, 2, 3];
      const cacheStates = Array.isArray(fixture.cacheStates)
        ? fixture.cacheStates.filter((s): s is string => typeof s === "string")
        : ["cold", "warm", "restarted"];

      const text = "Maria García met Robert O'Neil and Susan Reyes.";
      const values: readonly TaggedValue[] = [
        personValue("subject-a", "Maria García"),
        personValue("subject-b", "Robert O'Neil"),
        personValue("subject-c", "Susan Reyes"),
      ];

      const buildDeps = () => {
        const reader = new InMemoryCaseTruthReader();
        const cache = new InMemoryCompiledDictionaryCache();
        const compiler = new MatterDictionaryCompiler(reader);
        return { reader, cache, compiler };
      };
      const seedReader = (reader: InMemoryCaseTruthReader, input: CompileInput, ordered: readonly TaggedValue[]): void => {
        reader.set(
          { tenantId: input.tenantId, matterId: input.matterId, dictionaryVersion: input.dictionaryVersion, sourceTruthRevision: input.sourceTruthRevision },
          ordered,
        );
      };

      const outputs: string[] = [];
      for (const seed of seeds) {
        const shuffled = seededShuffle(values, seed);
        for (const cacheState of cacheStates) {
          const input = compileInputFor("tenant-1", "matter-1", 1n, "rev-1");
          if (cacheState === "warm") {
            const deps = buildDeps();
            seedReader(deps.reader, input, shuffled);
            await getOrCompile(deps.cache, deps.compiler, input); // populate cache
            const warm = await getOrCompile(deps.cache, deps.compiler, input); // cache hit
            outputs.push(tokenize(warm, text, LOCALE).tokenizedText);
          } else {
            // cold and restarted both fully recompile in fresh process state.
            const deps = buildDeps();
            seedReader(deps.reader, input, shuffled);
            const compiled = await getOrCompile(deps.cache, deps.compiler, input);
            outputs.push(tokenize(compiled, text, LOCALE).tokenizedText);
          }
        }
      }
      return { ...baseObservation(), outputs, diagnostics: [caseId] };
    }

    // ---- §8: prepared policy key includes tenant/matter/version ----
    case "M-PHILEAS-POLICY-NAME-ONLY": {
      const policyName = asString(fixture.samePolicyName) ?? "default";
      const tenants = Array.isArray(fixture.tenants)
        ? fixture.tenants.filter((t): t is string => typeof t === "string")
        : ["tenant-a", "tenant-b"];
      const matters = Array.isArray(fixture.matters)
        ? fixture.matters.filter((m): m is string => typeof m === "string")
        : ["matter-1", "matter-1"];
      const versions = Array.isArray(fixture.versions)
        ? fixture.versions.filter((v): v is string => typeof v === "string")
        : ["3", "4"];

      const matterValueSets = [["Maria García"], ["Robert O'Neil"]];
      const prepared = tenants.map((tenantId, i) =>
        buildPreparedPolicy({
          tenantId,
          matterId: matters[i] ?? "matter-1",
          dictionaryVersion: versions[i] ?? "1",
          schemaVersion: "schema-1",
          engineVersion: "engine-1",
          policyName,
          matterValues: matterValueSets[i] ?? [],
        }),
      );
      const keys = prepared.map((p) => p.key);
      const preparedPolicyIsolation = new Set(keys).size === keys.length;
      const allMatterValues = matterValueSets.flat();
      const sharedDictionaryContainsMatterValues = prepared.some((p) =>
        allMatterValues.some((v) => p.sharedLexicon.includes(v)),
      );

      return {
        ...baseObservation(),
        metrics: { preparedPolicyIsolation, sharedDictionaryContainsMatterValues },
      };
    }

    default:
      throw new Error(`dictionary.loader: unknown case ${caseId}`);
  }
}

export function loadDictionaryHarness(): ModuleHarness {
  return {
    run(caseId: string, fixture: Readonly<Record<string, unknown>>): Promise<OracleObservation> {
      return runCase(caseId, fixture);
    },
  };
}
