import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

describe("GLY-373 release contract", () => {
  it("GLY373-OR-09: package metadata is exactly 0.3.0 with a fenced root surface", () => {
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
    // 0.3.0: an additive union member plus an additive grammar production, no removal. Leaving
    // 0.2.0 or using a RANGE is MUT-16 — a range would let the two consumers resolve DIFFERENT
    // bytes, which is the whole failure mode the §9.4 cross-product equality gate exists to stop.
    expect(pkg.version).toBe("0.3.0");
    expect(pkg.main).toBe("./dist/index.js");
    expect(pkg.types).toBe("./dist/index.d.ts");
    expect(Object.keys(pkg.exports).sort()).toEqual([".", "./package.json"]);
    expect(pkg.scripts.build).toBe("tsc");
    expect(pkg.scripts.typecheck).toContain("tsconfig.public-api.json");
    expect(pkg.scripts.typecheck).toContain("tsconfig.executables.json");
    expect(pkg.scripts.lint).toContain("eslint");
    expect(pkg.scripts["format:check"]).toContain("prettier --check");
    expect(pkg.scripts.test).toBe("vitest run");
    // Every gate script is NON-MUTATING: a release gate that could rewrite the tree it is
    // measuring is not a gate.
    expect(pkg.scripts["format:check"]).not.toContain("--write");
    expect(pkg.scripts.lint).not.toContain("--fix");
  });

  it("GLY373-OR-09: the mandated breaking-change changelog entry ships with the release", () => {
    // §3.1 requires the release notes to carry this claim VERBATIM, because `ParsedToken.valid`
    // gains a REQUIRED `namespace` — deliberately not optional, since optionality would let a
    // reader silently ignore the field and treat a namespaced detector token as an authority
    // token, defeating the invariant the field exists to carry. That makes the change NOT strictly
    // additive, and the changelog is where that is stated rather than glossed.
    const changelog = readFileSync(
      new URL("../CHANGELOG.md", import.meta.url),
      "utf8",
    );
    expect(changelog).toContain(
      "`ParsedToken.valid` gains a required `namespace: string | null`; " +
        "`TokenGrammar.format` gains an optional `namespace` parameter. " +
        "Breaking for external `TokenGrammar` implementers and for exhaustive " +
        "`ParsedToken` consumers; no change required in either pinned consumer.",
    );
    expect(changelog).toContain("0.3.0");
  });
});
