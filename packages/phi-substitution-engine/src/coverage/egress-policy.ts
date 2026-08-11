/**
 * N7 enforcement layers 1 & 2 (CONTRACT §9.1 architecture test, §9.2 egress lint).
 *
 * Framework-free contract oracles: the product repositories run the real
 * tree-wide gates, but the checkable enforcement predicates live here so a
 * change that would let an unprotected provider host, or a raw SDK/model-handle
 * construction outside the protected module, reach an LLM provider is a failing
 * contract, not a matter of opinion.
 */
import type { ProviderEgressArchitecturePolicy } from "./contracts";

/**
 * The frozen phase-1 denylist policy. `protectedModuleRoots` is the exact,
 * minimal allow-list of paths permitted to bind raw provider surfaces; every
 * other product path is denied by construction.
 */
export const DEFAULT_EGRESS_POLICY: ProviderEgressArchitecturePolicy = {
  protectedModuleRoots: [
    "backend/src/modules/ai/",
    "backend/src/security/egress/",
    "src/security/egress/",
  ],
  forbiddenImports: [
    "openai",
    "@azure/openai",
    "@anthropic-ai/sdk",
    "@anthropic-ai/bedrock-sdk",
    "@anthropic-ai/vertex-sdk",
    "@google/generative-ai",
    "@google-cloud/vertexai",
  ],
  forbiddenConstructors: [
    "OpenAI",
    "AzureOpenAI",
    "AzureOpenAIClient",
    "Anthropic",
    "AnthropicBedrock",
    "AnthropicVertex",
    "GoogleGenerativeAI",
    "VertexAI",
  ],
  deniedProviderHosts: [
    "openai.azure.com",
    "api.openai.com",
    "openai.com",
    "api.anthropic.com",
    "anthropic.com",
    "generativelanguage.googleapis.com",
    "aiplatform.googleapis.com",
    "vision.googleapis.com",
    "cognitiveservices.azure.com",
  ],
};

/** True only when the file lives under an approved protected-module root. */
export function isProtectedModule(
  file: string,
  protectedModuleRoots: readonly string[],
): boolean {
  return protectedModuleRoots.some((root) => file.startsWith(root));
}

/** Pull the hostnames out of any absolute http(s) URLs appearing in source. */
export function extractHostnames(source: string): readonly string[] {
  const hosts: string[] = [];
  const urlPattern = /https?:\/\/([^/\s'"`)]+)/gi;
  let match: RegExpExecArray | null;
  while ((match = urlPattern.exec(source)) !== null) {
    const authority = match[1];
    if (authority === undefined) continue;
    const withoutUserInfo = authority.replace(/^[^@]*@/, "");
    const hostOnly = withoutUserInfo.split(":")[0];
    if (hostOnly !== undefined && hostOnly.length > 0) {
      hosts.push(hostOnly.toLowerCase());
    }
  }
  return hosts;
}

/** A host is denied if it equals, or is a subdomain of, any denylisted host. */
export function hostIsDenied(host: string, deniedProviderHosts: readonly string[]): boolean {
  return deniedProviderHosts.some(
    (denied) => host === denied || host.endsWith(`.${denied}`),
  );
}

export interface EgressLintInput {
  readonly addedFile: string;
  readonly source: string;
  readonly policy?: ProviderEgressArchitecturePolicy;
}

export interface EgressLintResult {
  readonly ok: boolean;
  readonly violations: readonly Readonly<{ file: string; host: string; rule: "RAW_PROVIDER_FETCH" }>[];
  readonly diagnostics: readonly string[];
}

/**
 * Layer 2. A denylisted provider host reached from anywhere outside the
 * protected module is an unprotected egress site — a raw fetch is never
 * "covered", so registration cannot whitewash it.
 */
export function lintProviderHostEgress(input: EgressLintInput): EgressLintResult {
  const policy = input.policy ?? DEFAULT_EGRESS_POLICY;
  const fileProtected = isProtectedModule(input.addedFile, policy.protectedModuleRoots);
  const violations: { file: string; host: string; rule: "RAW_PROVIDER_FETCH" }[] = [];
  for (const host of extractHostnames(input.source)) {
    if (hostIsDenied(host, policy.deniedProviderHosts) && !fileProtected) {
      violations.push({ file: input.addedFile, host, rule: "RAW_PROVIDER_FETCH" });
    }
  }
  return {
    ok: violations.length === 0,
    violations,
    diagnostics: violations.length > 0 ? ["UNPROTECTED_PROVIDER_HOST"] : [],
  };
}

export interface RawConstructionInput {
  readonly addedFile: string;
  readonly sourceKind: string;
  readonly outsideProtectedModule: boolean;
  readonly policy?: ProviderEgressArchitecturePolicy;
}

export interface RawConstructionResult {
  readonly ok: boolean;
  readonly diagnostics: readonly string[];
}

/**
 * Layer 1. Direct construction of a raw provider SDK / model handle
 * (`new AzureOpenAI`, `new Anthropic`, …) is forbidden anywhere but the single
 * protected module that owns the wrapper binding.
 */
export function checkRawConstruction(input: RawConstructionInput): RawConstructionResult {
  const policy = input.policy ?? DEFAULT_EGRESS_POLICY;
  const constructor = input.sourceKind.replace(/^new\s+/i, "").trim();
  const forbidden = policy.forbiddenConstructors.includes(constructor);
  const violated = forbidden && input.outsideProtectedModule;
  return {
    ok: !violated,
    diagnostics: violated ? ["RAW_PROVIDER_CONSTRUCTION_FORBIDDEN"] : [],
  };
}
