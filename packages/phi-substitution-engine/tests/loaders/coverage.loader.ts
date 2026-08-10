import { ModuleHarness, implementationRequired } from "../harness-types";

export function loadCoverageHarness(): ModuleHarness {
  return implementationRequired("n7-coverage");
}
