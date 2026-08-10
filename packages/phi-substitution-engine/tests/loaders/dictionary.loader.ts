import { ModuleHarness, implementationRequired } from "../harness-types";

export function loadDictionaryHarness(): ModuleHarness {
  return implementationRequired("dictionary");
}
