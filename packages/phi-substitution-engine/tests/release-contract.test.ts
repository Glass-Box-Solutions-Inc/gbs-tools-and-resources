import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

describe("GLY-372 release contract", () => {
  it("GLY372-OR-07: package metadata is exactly 0.2.0 with a fenced root surface", () => {
    const pkg = JSON.parse(
      readFileSync(new URL("../package.json", import.meta.url), "utf8"),
    ) as {
      name: string;
      version: string;
      main: string;
      types: string;
      exports: Record<string, unknown>;
      scripts: Record<string, string>;
    };
    expect(pkg.name).toBe("@glass-box-solutions-inc/phi-substitution-engine");
    expect(pkg.version).toBe("0.2.0");
    expect(pkg.main).toBe("./dist/index.js");
    expect(pkg.types).toBe("./dist/index.d.ts");
    expect(Object.keys(pkg.exports).sort()).toEqual([".", "./package.json"]);
    expect(pkg.scripts.build).toBe("tsc");
    expect(pkg.scripts.typecheck).toContain("tsconfig.public-api.json");
    expect(pkg.scripts.typecheck).toContain("tsconfig.executables.json");
    expect(pkg.scripts.lint).toContain("eslint");
    expect(pkg.scripts["format:check"]).toContain("prettier --check");
    expect(pkg.scripts.test).toBe("vitest run");
  });
});
