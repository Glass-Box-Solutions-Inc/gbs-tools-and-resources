import { expect } from "vitest";
import type { OracleObservation } from "./implementation-under-test";

export const SEEDED_CANARIES = [
  "Maria García",
  "Robert O'Neil",
  "078-05-1120",
  "MRN-A7719",
  "DEA-AB1234567",
  "maria@example.test",
  "+1 (415) 555-0199",
  "412 May Street",
  "CLM-00421",
  "POL-7788",
  "ACCT-91234",
] as const;

export function expectNoCanary(payloads: readonly string[]): void {
  const joined = payloads.join("\n").normalize("NFKC").toLocaleLowerCase("en-US");
  for (const canary of SEEDED_CANARIES) {
    expect(joined).not.toContain(canary.normalize("NFKC").toLocaleLowerCase("en-US"));
  }
}

export function expectFailedClosed(observation: OracleObservation, code: string): void {
  expect(observation.providerCalls).toBe(0);
  expect(observation.errorCode).toBe(code);
}

export function expectExactlyOneProviderCall(observation: OracleObservation): void {
  expect(observation.providerCalls).toBe(1);
  expectNoCanary(observation.providerPayloads);
}

export function serialized(value: unknown): string {
  return JSON.stringify(value);
}
