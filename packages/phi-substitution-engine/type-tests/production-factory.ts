import type {
  AuditPrimaryStore,
  EncryptedAuditSpool,
  CreateProductionProtectedAiProviderOptions,
  CreateProductionProtectedOriginalEgressAuthorizerOptions,
  DisplayText,
  EngineVersion,
  AzureEgressPolicyEvidence,
  AzureEgressPolicySignedClaims,
  ProtectedAiCallSurface,
  ProtectedAiProviderDependencies,
  ProtectedAiTextResult,
  MatterAiContext,
  OriginalEgressAuthorizationRequest,
  OriginalEgressPolicyPort,
  TokenizedText,
} from "../src/index";
import { createProductionProtectedOriginalEgressAuthorizer } from "../src/index";

declare const display: DisplayText;
declare const tokenized: TokenizedText;

const protectedResult: ProtectedAiTextResult = {
  display,
  providerId: "azure-baa",
  toolCalls: [{ id: "call-1", name: "lookup", arguments: display }],
};
void protectedResult;

// Tokenized tool arguments cannot cross the protected application seam.
const invalidProtectedResult: ProtectedAiTextResult = {
  display,
  providerId: "azure-baa",
  toolCalls: [{
    id: "call-1",
    name: "lookup",
    // @ts-expect-error TokenizedText is not DisplayText.
    arguments: tokenized,
  }],
};
void invalidProtectedResult;

declare const surface: ProtectedAiCallSurface<{ prompt: string }>;
const generated: Promise<ProtectedAiTextResult> = surface.generateText({ prompt: "x" });
void generated;

// R2: optional widening preserves callers that do not supply the legacy fallback capability.
declare const withoutInvokeRaw: Omit<ProtectedAiProviderDependencies<{ prompt: string }, unknown>, "invokeRaw">;
const widenedDependencies: ProtectedAiProviderDependencies<{ prompt: string }, unknown> = withoutInvokeRaw;
void widenedDependencies;

declare const productionDependencies: CreateProductionProtectedAiProviderOptions<{ prompt: string }>;
const engineVersion: EngineVersion = productionDependencies.engineVersion;
const enginePolicyVersion: string = productionDependencies.enginePolicyVersion;
void engineVersion;
void enginePolicyVersion;

declare const originalPolicy: OriginalEgressPolicyPort;
declare const auditPrimary: AuditPrimaryStore;
declare const auditSpool: EncryptedAuditSpool;
declare const originalContext: MatterAiContext;

const originalEgressOptions: CreateProductionProtectedOriginalEgressAuthorizerOptions = {
  engineVersion,
  enginePolicyVersion,
  policy: originalPolicy,
  auditPrimary,
  auditSpool,
};
const originalEgressAuthorizer = createProductionProtectedOriginalEgressAuthorizer(originalEgressOptions);
const originalEgressRequest: OriginalEgressAuthorizationRequest = {
  context: originalContext,
  destinationKey: "azure-speech-westus",
  protocol: "WSS",
  contentClass: "audio-stream",
  enginePolicyVersion,
  purpose: "stream",
};
void originalEgressAuthorizer.authorizeOriginalEgress(originalEgressRequest);

const invalidContentBearingRequest: OriginalEgressAuthorizationRequest = {
  ...originalEgressRequest,
  // @ts-expect-error Original content bytes are structurally absent from the authorization seam.
  content: new Uint8Array([1]),
};
void invalidContentBearingRequest;

declare const missingEgressVersion: Omit<AzureEgressPolicyEvidence, "egressPolicyVersion">;
// @ts-expect-error egressPolicyVersion is a required signed claim.
const invalidMissingEgressVersion: AzureEgressPolicyEvidence = missingEgressVersion;
void invalidMissingEgressVersion;

declare const missingEngineVersion: Omit<AzureEgressPolicyEvidence, "enginePolicyVersion">;
// @ts-expect-error enginePolicyVersion is a required signed claim.
const invalidMissingEngineVersion: AzureEgressPolicyEvidence = missingEngineVersion;
void invalidMissingEngineVersion;

declare const completeEvidence: AzureEgressPolicyEvidence;
const signedClaims: AzureEgressPolicySignedClaims = completeEvidence;
// @ts-expect-error signature is intentionally absent from the signed-claims type.
const signature = signedClaims.signature;
void signature;
