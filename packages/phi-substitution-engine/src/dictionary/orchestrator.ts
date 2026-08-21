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
  AMBIGUOUS_KNOWN_IDENTIFIER,
  DICTIONARY_UNAVAILABLE,
  MISSING_TRUSTED_CONTEXT,
  isDictionaryError,
  type DictionaryFailureCode,
} from "./errors";
import type { AhoCorasickCompiledDictionary } from "./compiled-dictionary";
import { isPhiEngineFailureCode, safeCodeString } from "../core/errors";

/**
 * Maps a caught error on the dictionary egress path to a fixed-code FAILED_CLOSED decision (§7/N2):
 * a raw cache/compiler/tokenize rejection must NEVER surface its message/code. A recognized
 * DictionaryError code is preserved (getter-throw-safe); anything else → the fixed fallback.
 */
function dictionaryFailClosed(
  error: unknown,
  fallback: DictionaryFailureCode,
): EgressDecision {
  const rawCode = isDictionaryError(error) ? safeCodeString(error) : undefined;
  const code: DictionaryFailureCode =
    rawCode !== undefined && isPhiEngineFailureCode(rawCode)
      ? (rawCode as DictionaryFailureCode)
      : fallback;
  return { kind: "FAILED_CLOSED", code, dictionaryVersion: null };
}

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

export async function decideEgress(
  req: EgressRequest,
  deps: EgressDeps,
): Promise<EgressDecision> {
  // N4: missing trusted context fails closed before any provider work.
  if (req.context === null) {
    return {
      kind: "FAILED_CLOSED",
      code: MISSING_TRUSTED_CONTEXT,
      dictionaryVersion: null,
    };
  }
  const context = req.context;

  // N4: a dictionary outage fails closed; the raw provider is never a fallback.
  if (req.dictionaryHealth === "unavailable") {
    return {
      kind: "FAILED_CLOSED",
      code: DICTIONARY_UNAVAILABLE,
      dictionaryVersion: null,
    };
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
      // §7/N2: a DictionaryError's `.code` is UNTRUSTED here — an injected coordinator can construct
      // one with a raw (PHI-laden) code via an `as any` cast or expose it through a throwing getter.
      // Read it through the getter-throw guard and honor it ONLY as a recognized fixed failure code;
      // otherwise fail closed with a fixed code. `safeDetails.activeVersion` is forwarded only when it
      // has the safe decimal-version shape, never as an arbitrary attacker-supplied string.
      const rawCode = safeCodeString(error);
      const code: DictionaryFailureCode =
        rawCode !== undefined && isPhiEngineFailureCode(rawCode)
          ? (rawCode as DictionaryFailureCode)
          : DICTIONARY_UNAVAILABLE;
      let dictionaryVersion: string | null = null;
      try {
        const reported: unknown = error.safeDetails?.activeVersion;
        if (typeof reported === "string" && /^\d{1,20}$/.test(reported)) {
          dictionaryVersion = reported;
        }
      } catch {
        /* a hostile safeDetails getter cannot leak — drop the version and keep the fixed code. */
      }
      return { kind: "FAILED_CLOSED", code, dictionaryVersion };
    }
    // §7/N2: an unexpected non-DictionaryError must never surface a raw message/code — fail closed.
    return {
      kind: "FAILED_CLOSED",
      code: DICTIONARY_UNAVAILABLE,
      dictionaryVersion: null,
    };
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
  // §7/N2: the cache/compiler are injected adapters — a raw rejection (message/`.code` could carry
  // PHI) must never propagate out of decideEgress; fail closed with a fixed code.
  let compiled: AhoCorasickCompiledDictionary;
  try {
    compiled = await getOrCompile(deps.cache, deps.compiler, compileInput);
  } catch (error) {
    return dictionaryFailClosed(error, DICTIONARY_UNAVAILABLE);
  }
  let tokenizedText: string;
  let reversedText: string;
  try {
    ({ tokenizedText, reversedText } = tokenize(
      compiled,
      req.text,
      req.policy.locale as unknown as string,
      req.detectorSpans ?? [],
    ));
  } catch (error) {
    // C6 ambiguity (and any other tokenize failure) fails closed; a known value is never guessed.
    return dictionaryFailClosed(error, AMBIGUOUS_KNOWN_IDENTIFIER);
  }
  // §7/N2: `activeVersion` is an injected-coordinator result — its `toString()` is untrusted. Read
  // it ONCE, getter/throw-safe, and accept only the safe decimal-version shape; a throwing or
  // non-decimal `toString` (a compromised coordinator) fails closed rather than surfacing raw text.
  let versionString: string;
  try {
    const s = String(activeVersion);
    versionString = /^\d{1,20}$/.test(s) ? s : "";
  } catch {
    versionString = "";
  }
  if (versionString === "") {
    return dictionaryFailClosed(undefined, DICTIONARY_UNAVAILABLE);
  }
  // Only the tokenized text ever egresses; the raw provider is never invoked.
  return {
    kind: "SUBSTITUTED",
    egressText: tokenizedText,
    reversedText,
    dictionaryVersion: versionString,
  };
}
