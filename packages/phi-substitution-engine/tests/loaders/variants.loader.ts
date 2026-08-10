import { ModuleHarness, implementationRequired } from "../harness-types";

export function loadVariantsHarness(): ModuleHarness {
  return implementationRequired("variants");
}
