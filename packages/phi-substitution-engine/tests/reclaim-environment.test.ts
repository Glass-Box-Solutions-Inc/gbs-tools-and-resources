import { describe, expect, it } from "vitest";
import { integerEnvironment } from "../jobs/reclaim-environment";

const INTEGER_VARIABLES = [
  { name: "RECLAIM_HORIZON_MS", fallback: 86_400_000, allowZero: true },
  { name: "RECLAIM_GRACE_MS", fallback: 86_400_000, allowZero: true },
  { name: "RECLAIM_LIMIT", fallback: 1_000, allowZero: false },
] as const;

describe.each(INTEGER_VARIABLES)("integerEnvironment($name)", ({ name, fallback, allowZero }) => {
  it.each(["", " ", "1e3", "0x10"])("rejects non-decimal input %j", (raw) => {
    expect(() => integerEnvironment(name, fallback, allowZero, { [name]: raw }))
      .toThrow(`invalid_${name}`);
  });

  it("rejects decimal digits outside the safe-integer range", () => {
    expect(() => integerEnvironment(name, fallback, allowZero, { [name]: "9007199254740992" }))
      .toThrow(`invalid_${name}`);
  });

  it("uses the fallback only when the variable is undefined", () => {
    expect(integerEnvironment(name, fallback, allowZero, {})).toBe(fallback);
  });

  it("enforces the variable's zero bound", () => {
    if (allowZero) {
      expect(integerEnvironment(name, fallback, allowZero, { [name]: "0" })).toBe(0);
    } else {
      expect(() => integerEnvironment(name, fallback, allowZero, { [name]: "0" }))
        .toThrow(`invalid_${name}`);
    }
  });
});
