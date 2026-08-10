/**
 * Dictionary-side egress decision (CONTRACT-phase1 §4.1 steps 1–2/12, §5 N4/L2).
 *
 * This is the fail-closed gate the dictionary owns before any provider egress:
 *   - N4: a missing trusted context fails closed (`MISSING_TRUSTED_CONTEXT`);
 *   - N4: a dictionary outage fails closed (`DICTIONARY_UNAVAILABLE`) and NEVER
 *     falls back to the raw provider;
 *   - L2: serving requires an active READY version (`DICTIONARY_NOT_READY`).
 *
 * The only non-failed outcome is `SUBSTITUTED`, which carries ONLY tokenized
 * text. Every early return below is load-bearing: replacing one with a
 * substituted-raw egress is precisely the regression its invariant forbids.
 */
import type { DictionaryVersion, EngineVersion } from "../core/brands";
import type { MatterAiContext, TrustedMatterAiPolicy } from "../core/contracts";
import type {
  CompileInput,
  CompiledDictionaryCache,
  DictionaryCompiler,
  DictionaryVersionCoordinator,
} from "./contracts";
import type { DetectorSpanInput } from "./tokenize";
import { getOrCompile, tokenize } from "./tokenize";
import {
  DICTIONARY_UNAVAILABLE,
  MISSING_TRUSTED_CONTEXT,
  isDictionaryError,
  type DictionaryFailureCode,
} from "./errors";

export type EgressDecision =
  | {
      readonly kind: "SUBSTITUTED";
      readonly egressText: string;
      readonly reversedText: string;
      readonly dictionaryVersion: string;
    }
  | {
      readonly kind: "FAILED_CLOSED";
      readonly code: DictionaryFailureCode;
      readonly dictionaryVersion: string | null;
    };

export interface EgressRequest {
  readonly context: MatterAiContext | null;
  readonly dictionaryHealth: "available" | "unavailable";
  readonly text: string;
  readonly policy: TrustedMatterAiPolicy;
  readonly engineVersion: EngineVersion;
  readonly sourceTruthRevision: string;
  readonly detectorSpans?: readonly DetectorSpanInput[];
}

export interface EgressDeps {
  readonly coordinator: DictionaryVersionCoordinator;
  readonly cache: CompiledDictionaryCache;
  readonly compiler: DictionaryCompiler;
}

export async function decideEgress(req: EgressRequest, deps: EgressDeps): Promise<EgressDecision> {
  // N4: missing trusted context fails closed before any provider work.
  if (req.context === null) {
    return { kind: "FAILED_CLOSED", code: MISSING_TRUSTED_CONTEXT, dictionaryVersion: null };
  }
  const context = req.context;

  // N4: a dictionary outage fails closed; the raw provider is never a fallback.
  if (req.dictionaryHealth === "unavailable") {
    return { kind: "FAILED_CLOSED", code: DICTIONARY_UNAVAILABLE, dictionaryVersion: null };
  }

  // L2: require an active READY version; reject BUILDING/FAILED/stale.
  let activeVersion: DictionaryVersion;
  try {
    activeVersion = await deps.coordinator.requireActiveReady({
      tenantId: context.tenantId,
      matterId: context.matterId,
    });
  } catch (error) {
    if (isDictionaryError(error)) {
      const reported = error.safeDetails.activeVersion;
      return {
        kind: "FAILED_CLOSED",
        code: error.code,
        dictionaryVersion: typeof reported === "string" ? reported : null,
      };
    }
    throw error;
  }

  const compileInput: CompileInput = {
    tenantId: context.tenantId,
    matterId: context.matterId,
    policy: req.policy,
    dictionaryVersion: activeVersion,
    engineVersion: req.engineVersion,
    schemaVersion: req.policy.schemaVersion,
    sourceTruthRevision: req.sourceTruthRevision,
  };
  const compiled = await getOrCompile(deps.cache, deps.compiler, compileInput);
  const { tokenizedText, reversedText } = tokenize(
    compiled,
    req.text,
    req.policy.locale as unknown as string,
    req.detectorSpans ?? [],
  );
  // Only the tokenized text ever egresses; the raw provider is never invoked.
  return {
    kind: "SUBSTITUTED",
    egressText: tokenizedText,
    reversedText,
    dictionaryVersion: activeVersion.toString(),
  };
}
