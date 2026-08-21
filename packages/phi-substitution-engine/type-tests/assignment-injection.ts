import {
  createProtectedAiProvider,
  createSubstitutionEngine,
} from "../src/index";
import type {
  CreateProtectedAiProviderOptions,
  CreateSubstitutionEngineOptions,
  TokenAssignmentStore,
} from "../src/index";

const authority = {
  getOrAllocate: async (
    _input: Parameters<TokenAssignmentStore["getOrAllocate"]>[0],
  ) =>
    "[[Claimant_41]]" as Awaited<
      ReturnType<TokenAssignmentStore["getOrAllocate"]>
    >,
  retire: async (_input: Parameters<TokenAssignmentStore["retire"]>[0]) =>
    undefined,
} satisfies TokenAssignmentStore;

const engineOptions: CreateSubstitutionEngineOptions = {
  assignmentStore: authority,
};
const providerOptions: CreateProtectedAiProviderOptions = {
  assignmentStore: authority,
};

void createSubstitutionEngine(engineOptions);
void createProtectedAiProvider(providerOptions);
