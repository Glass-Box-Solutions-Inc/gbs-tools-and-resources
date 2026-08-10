import { ModuleHarness, implementationRequired } from "../harness-types";

export function loadDetectorHarness(): ModuleHarness {
  return implementationRequired("detector-redactor-port");
}
