import { ModuleHarness, implementationRequired } from "../harness-types";

export function loadProviderBoundaryHarness(): ModuleHarness {
  return implementationRequired("protected-provider-boundary");
}
