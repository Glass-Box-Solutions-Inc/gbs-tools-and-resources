import { ModuleHarness, implementationRequired } from "../harness-types";

export function loadCollisionHarness(): ModuleHarness {
  return implementationRequired("collision");
}
