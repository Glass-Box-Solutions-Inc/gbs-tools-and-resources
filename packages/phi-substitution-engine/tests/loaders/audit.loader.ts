import { ModuleHarness, implementationRequired } from "../harness-types";

export function loadAuditHarness(): ModuleHarness {
  return implementationRequired("audit");
}
