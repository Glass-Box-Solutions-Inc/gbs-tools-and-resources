import { ModuleHarness, implementationRequired } from "../harness-types";

export function loadEvaluationHarness(): ModuleHarness {
  return implementationRequired("evaluation-and-claims");
}
