import { ModuleHarness, implementationRequired } from "../harness-types";

export function loadTokensHarness(): ModuleHarness {
  return implementationRequired("tokens");
}
