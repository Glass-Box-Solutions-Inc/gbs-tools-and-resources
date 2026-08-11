import type { ModuleHarness, OracleObservation } from "../harness-types";
import type {
  DictionaryVersion,
  MatterId,
  OperationAttemptId,
  OperationId,
  SubjectId,
  SubstitutionToken,
  TenantId,
  TokenizedText,
  TokenRole,
} from "../../src/core/brands";
import type { ReversalHandle, ReversalStore } from "../../src/core/contracts";
import {
  createTokensModule,
  InProcessReversalHandle,
  reverseText,
  REVERSAL_FAILED,
  DIAG_REVERSAL_HANDLE_NOT_SERIALIZABLE,
  type TokensModule,
} from "../../src/tokens/index";

/**
 * Real adapter over the production token/escape/reversal/stream ports.
 *
 * This loader is the sole test-to-production wiring seam for the tokens module.
 * It NEVER re-implements an invariant; every observable the oracle asserts is
 * produced by driving the frozen production ports (grammar, assignment store,
 * escaper, reversal store, atomic reverser, holdback reverse stream). Each
 * `run` builds a fresh module so cases never share state.
 */

// -- branding helpers (test-adapter side; brands are constructed by the harness) --
const tenant = (s: string): TenantId => s as TenantId;
const matter = (s: string): MatterId => s as MatterId;
const subject = (s: string): SubjectId => s as SubjectId;
const roleOf = (s: string): TokenRole => s as TokenRole;
const token = (s: string): SubstitutionToken => s as SubstitutionToken;
const op = (s: string): OperationId => s as OperationId;
const attempt = (s: string): OperationAttemptId => s as OperationAttemptId;
const version = (n: bigint): DictionaryVersion => n as DictionaryVersion;

const V1 = version(1n);
const V2 = version(2n);
const TENANT = tenant("tenant-1");
const MATTER = matter("matter-1");
const OP = op("op-1");
const ATTEMPT = attempt("att-1");

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

function failureCode(error: unknown): string {
  if (
    error !== null &&
    typeof error === "object" &&
    "code" in error &&
    typeof (error as { code?: unknown }).code === "string"
  ) {
    return (error as { code: string }).code;
  }
  return REVERSAL_FAILED;
}

/** Counts reversal lookups and captures the exact tokens each call resolved (N2: bounded, encountered-only). */
class SpyReversalStore implements ReversalStore {
  calls = 0;
  readonly lookedUp: string[] = [];
  constructor(private readonly inner: ReversalStore) {}
  get maximumEncounteredTokenBatch(): number {
    return this.inner.maximumEncounteredTokenBatch;
  }
  async resolveEncounteredTokens(input: Readonly<{
    tenantId: TenantId;
    matterId: MatterId;
    dictionaryVersion: DictionaryVersion;
    tokens: readonly SubstitutionToken[];
  }>): Promise<ReadonlyMap<SubstitutionToken, string>> {
    this.calls += 1;
    for (const t of input.tokens) {
      this.lookedUp.push(String(t));
    }
    return this.inner.resolveEncounteredTokens(input);
  }
}

/** All UTF-16-boundary partitions: every two-chunk split, plus one unit/chunk, plus the whole text. */
function enumeratePartitions(text: string): string[][] {
  const partitions: string[][] = [];
  const length = text.length;
  for (let i = 1; i < length; i += 1) {
    partitions.push([text.slice(0, i), text.slice(i)]);
  }
  const units: string[] = [];
  for (let i = 0; i < length; i += 1) {
    units.push(text.slice(i, i + 1));
  }
  partitions.push(units);
  partitions.push([text]);
  return partitions;
}

async function runStream(
  parts: readonly string[],
  module: TokensModule,
  handle: ReversalHandle,
): Promise<{ chunks: string[]; error: string | null }> {
  const chunks: string[] = [];
  const stream = module.streamFactory.create({
    handle,
    store: module.reversalStore,
    grammar: module.grammar,
    policy: module.policy,
    sink: (safe) => {
      chunks.push(String(safe));
    },
  });
  let error: string | null = null;
  try {
    for (const part of parts) {
      await stream.push(part as TokenizedText);
    }
    await stream.end();
  } catch (thrown) {
    error = failureCode(thrown);
  }
  return { chunks, error };
}

function newHandle(module: TokensModule, tenantId: TenantId = TENANT): ReversalHandle {
  void module;
  return new InProcessReversalHandle({
    tenantId,
    matterId: MATTER,
    dictionaryVersion: V1,
    operationId: OP,
    attemptId: ATTEMPT,
  });
}

async function runCase(
  caseId: string,
  fixture: Readonly<Record<string, unknown>>,
): Promise<OracleObservation> {
  const module = createTokensModule();

  switch (caseId) {
    // ---- L1: identity stable by tenant+matter+subject+role, never version, never text ----
    case "M-L1-RENUMBER-TOKENS": {
      const version1 = (fixture.version1 as string[]) ?? [];
      const version2 = (fixture.version2 as string[]) ?? [];
      const role = roleOf("Treating_Physician");
      const tokensBySubject: Record<string, string> = {};
      for (const id of version1) {
        tokensBySubject[id] = String(
          await module.assignmentStore.getOrAllocate({
            tenantId: TENANT,
            matterId: MATTER,
            subjectId: subject(id),
            role,
            dictionaryVersion: V1,
          }),
        );
      }
      for (const id of version2) {
        // A different dictionary version must not renumber an existing subject.
        tokensBySubject[id] = String(
          await module.assignmentStore.getOrAllocate({
            tenantId: TENANT,
            matterId: MATTER,
            subjectId: subject(id),
            role,
            dictionaryVersion: V2,
          }),
        );
      }
      return { ...baseObservation(), tokensBySubject, dictionaryVersion: V2.toString() };
    }

    case "M-L1-COALESCE-BY-TEXT-ONLY": {
      const subjects =
        (fixture.subjects as { id: string; value: string; role: string }[]) ?? [];
      const tokensBySubject: Record<string, string> = {};
      for (const s of subjects) {
        // Identity carries subject+role; the display value is never passed in,
        // so equal spelling under distinct identities cannot collapse.
        tokensBySubject[s.id] = String(
          await module.assignmentStore.getOrAllocate({
            tenantId: TENANT,
            matterId: MATTER,
            subjectId: subject(s.id),
            role: roleOf(s.role),
            dictionaryVersion: V1,
          }),
        );
      }
      return { ...baseObservation(), tokensBySubject };
    }

    // ---- L6: reserved token-shaped source text escaped before matching ----
    case "M-C7-NO-RESERVED-TOKEN-ESCAPE": {
      const source = fixture.source as string;
      const mappedClaimant = fixture.mappedClaimant as string;
      // A real mapping exists for [[Claimant]] in this matter; escaping must
      // keep source-injected token shapes from ever reaching reversal.
      module.reversalStore.record({
        tenantId: TENANT,
        matterId: MATTER,
        dictionaryVersion: V1,
        token: token("[[Claimant]]"),
        canonical: mappedClaimant,
      });
      const escaped = module.escaper.escape(source, module.policy);
      // The provider only ever receives the escaped (tokenized) text; it echoes
      // that back — the raw [[Claimant]] is already a non-reversible literal.
      const providerOut = String(escaped.text);
      const reversed = await reverseText(
        providerOut,
        { tenantId: TENANT, matterId: MATTER, dictionaryVersion: V1, operationId: OP },
        module.reversalStore,
        module.grammar,
        module.policy,
      );
      const displayText = String(
        module.escaper.restoreLiterals(reversed as TokenizedText, escaped.literals),
      );
      return { ...baseObservation(), displayText, tokenizedText: providerOut, reversedText: reversed };
    }

    // ---- N2: reversal handle is non-serializable (holds refs, never a map) ----
    case "M-N2-EXPORT-REVERSAL-MAP": {
      const handle = newHandle(module);
      const attachTo = (fixture.attachTo as string[]) ?? ["trace"];
      let buildPassed = false;
      const diagnostics = new Set<string>();
      for (const target of attachTo) {
        try {
          // toJSON throws, so no trace/job/providerMetadata/sharedCache payload
          // can ever carry the reversal capability.
          JSON.stringify({ [target]: handle });
          buildPassed = true;
        } catch {
          diagnostics.add(DIAG_REVERSAL_HANDLE_NOT_SERIALIZABLE);
        }
      }
      return { ...baseObservation(), buildPassed, diagnostics: [...diagnostics] };
    }

    // ---- N2: store resolves only the encountered tokens, in one bounded lookup ----
    case "M-N2-LIST-ENTIRE-REVERSAL-MAP": {
      const providerText = fixture.providerText as string;
      const matterMapSize = (fixture.matterMapSize as number) ?? 2;
      module.reversalStore.record({
        tenantId: TENANT,
        matterId: MATTER,
        dictionaryVersion: V1,
        token: token("[[Claimant]]"),
        canonical: "Maria García",
      });
      module.reversalStore.record({
        tenantId: TENANT,
        matterId: MATTER,
        dictionaryVersion: V1,
        token: token("[[Treating_Physician]]"),
        canonical: "Dr. Smith",
      });
      for (let i = 2; i < matterMapSize; i += 1) {
        module.reversalStore.record({
          tenantId: TENANT,
          matterId: MATTER,
          dictionaryVersion: V1,
          token: token(`[[Adjuster_${i}]]`),
          canonical: `filler-${i}`,
        });
      }
      const spy = new SpyReversalStore(module.reversalStore);
      const reversed = await reverseText(
        providerText,
        { tenantId: TENANT, matterId: MATTER, dictionaryVersion: V1, operationId: OP },
        spy,
        module.grammar,
        module.policy,
      );
      return {
        ...baseObservation(),
        reversedText: reversed,
        reversalLookupCount: spy.calls,
        reversalLookupTokens: spy.lookedUp,
      };
    }

    // ---- N5: known tokens reverse to current canonical value ----
    case "M-N5-SHOW-TOKEN": {
      const providerText = fixture.providerText as string;
      const canonical = fixture.canonical as string;
      module.reversalStore.record({
        tenantId: TENANT,
        matterId: MATTER,
        dictionaryVersion: V1,
        token: token("[[Claimant]]"),
        canonical,
      });
      const reversed = await reverseText(
        providerText,
        { tenantId: TENANT, matterId: MATTER, dictionaryVersion: V1, operationId: OP },
        module.reversalStore,
        module.grammar,
        module.policy,
      );
      return { ...baseObservation(), displayText: reversed, reversedText: reversed };
    }

    // ---- N5: unknown/malformed tokens fail atomically, no raw chunk shown ----
    case "M-N5-UNKNOWN-TOKEN-PASSTHROUGH": {
      const providerText = fixture.providerText as string;
      try {
        const reversed = await reverseText(
          providerText,
          { tenantId: TENANT, matterId: MATTER, dictionaryVersion: V1, operationId: OP },
          module.reversalStore,
          module.grammar,
          module.policy,
        );
        return { ...baseObservation(), displayText: reversed };
      } catch (thrown) {
        return { ...baseObservation(), displayText: null, errorCode: failureCode(thrown) };
      }
    }

    // ---- N5/L4: streaming reversal is chunk-independent across every partition ----
    case "M-N5-STREAM-NO-HOLDBACK": {
      const providerText = fixture.providerText as string;
      const canonical = fixture.canonical as string;
      module.reversalStore.record({
        tenantId: TENANT,
        matterId: MATTER,
        dictionaryVersion: V1,
        token: token("[[Claimant]]"),
        canonical,
      });
      const handle = newHandle(module);
      const outputs: string[] = [];
      let errorCode: string | null = null;
      for (const parts of enumeratePartitions(providerText)) {
        const result = await runStream(parts, module, handle);
        if (result.error) {
          errorCode = result.error;
        }
        outputs.push(result.chunks.join(""));
      }
      const representative = await runStream([providerText], module, handle);
      if (representative.error) {
        errorCode = representative.error;
      }
      return { ...baseObservation(), outputs, displayChunks: representative.chunks, errorCode };
    }

    // ---- L4: M-1 UTF-16 holdback keeps the longest token whole across every split ----
    case "M-L4-HOLDBACK-OFF-BY-ONE": {
      const maximumToken = fixture.maximumToken as string;
      module.reversalStore.record({
        tenantId: TENANT,
        matterId: MATTER,
        dictionaryVersion: V1,
        token: token(maximumToken),
        canonical: "Dr. Canonical Longform Value",
      });
      const handle = newHandle(module);
      const outputs: string[] = [];
      let errorCode: string | null = null;
      for (const parts of enumeratePartitions(maximumToken)) {
        const result = await runStream(parts, module, handle);
        if (result.error) {
          errorCode = result.error;
        }
        outputs.push(result.chunks.join(""));
      }
      return { ...baseObservation(), outputs, errorCode };
    }

    // ---- L4: terminal token fragment is validated on flush, never emitted ----
    case "M-L4-FLUSH-WITHOUT-VALIDATE": {
      const chunks = (fixture.chunks as string[]) ?? [];
      const handle = newHandle(module);
      const result = await runStream(chunks, module, handle);
      return { ...baseObservation(), displayChunks: result.chunks, errorCode: result.error };
    }

    // ---- L8: tenant is part of every reversal key; cross-tenant reversal misses ----
    case "M-L8-DROP-TENANT-FROM-DB-WHERE": {
      const storedTenant = tenant(fixture.storedTenant as string);
      const handleTenant = tenant(fixture.handleTenant as string);
      const sharedMatter = matter("matter-shared");
      module.reversalStore.record({
        tenantId: storedTenant,
        matterId: sharedMatter,
        dictionaryVersion: V1,
        token: token("[[Claimant]]"),
        canonical: "Maria García",
      });
      try {
        const reversed = await reverseText(
          "[[Claimant]] reported the injury.",
          { tenantId: handleTenant, matterId: sharedMatter, dictionaryVersion: V1, operationId: OP },
          module.reversalStore,
          module.grammar,
          module.policy,
        );
        return { ...baseObservation(), displayText: reversed };
      } catch (thrown) {
        return { ...baseObservation(), displayText: null, errorCode: failureCode(thrown) };
      }
    }

    default:
      throw new Error(`tokens.loader: unknown case ${caseId}`);
  }
}

export function loadTokensHarness(): ModuleHarness {
  return {
    run(caseId: string, fixture: Readonly<Record<string, unknown>>): Promise<OracleObservation> {
      return runCase(caseId, fixture);
    },
  };
}
