import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

interface LockPackage {
  readonly version?: string;
  readonly dependencies?: Readonly<Record<string, string>>;
  readonly optionalDependencies?: Readonly<Record<string, string>>;
  readonly peerDependencies?: Readonly<Record<string, string>>;
  readonly peerDependenciesMeta?: Readonly<
    Record<string, Readonly<{ optional?: boolean }>>
  >;
  readonly devDependencies?: Readonly<Record<string, string>>;
  readonly engines?: Readonly<{ node?: string }>;
}

interface PackageLock {
  readonly packages: Readonly<Record<string, LockPackage>>;
}

interface PackageManifest {
  readonly dependencies: Readonly<Record<string, string>>;
  readonly devDependencies: Readonly<Record<string, string>>;
  readonly engines: Readonly<{ node: string }>;
}

const CI_NODE = "20.20.2";
const packageJson = JSON.parse(
  readFileSync(new URL("../package.json", import.meta.url), "utf8"),
) as PackageManifest;
const lock = JSON.parse(
  readFileSync(new URL("../package-lock.json", import.meta.url), "utf8"),
) as PackageLock;

const require = createRequire(import.meta.url);
const semver = require("semver") as Readonly<{
  satisfies(
    version: string,
    range: string,
    options?: Readonly<{ includePrerelease?: boolean }>,
  ): boolean;
}>;

function resolveDependency(from: string, dependency: string): string | null {
  let cursor = from;
  while (true) {
    const candidate =
      cursor === ""
        ? `node_modules/${dependency}`
        : `${cursor}/node_modules/${dependency}`;
    if (lock.packages[candidate] !== undefined) return candidate;
    const marker = cursor.lastIndexOf("/node_modules/");
    if (marker < 0) {
      if (cursor === "") return null;
      cursor = "";
    } else {
      cursor = cursor.slice(0, marker);
    }
  }
}

function installedClosure(): ReadonlySet<string> {
  const visited = new Set<string>();
  const queue: string[] = [];
  const root = lock.packages[""];
  if (root === undefined) throw new Error("package-lock root missing");

  for (const dependency of Object.keys({
    ...(root.dependencies ?? {}),
    ...(root.devDependencies ?? {}),
  })) {
    const resolved = resolveDependency("", dependency);
    if (resolved === null)
      throw new Error(`unresolved root dependency: ${dependency}`);
    queue.push(resolved);
  }

  while (queue.length > 0) {
    const packagePath = queue.shift()!;
    if (visited.has(packagePath)) continue;
    visited.add(packagePath);
    const entry = lock.packages[packagePath];
    if (entry === undefined)
      throw new Error(`missing lock package: ${packagePath}`);
    const edges = {
      ...(entry.dependencies ?? {}),
      ...(entry.optionalDependencies ?? {}),
      ...(entry.peerDependencies ?? {}),
    };
    for (const dependency of Object.keys(edges)) {
      const resolved = resolveDependency(packagePath, dependency);
      const optionalPeer =
        entry.peerDependenciesMeta?.[dependency]?.optional === true;
      const optionalDependency =
        entry.optionalDependencies?.[dependency] !== undefined;
      if (resolved === null) {
        if (optionalPeer || optionalDependency) continue;
        throw new Error(
          `unresolved dependency ${dependency} from ${packagePath}`,
        );
      }
      queue.push(resolved);
    }
  }
  return visited;
}

function phiJob(workflow: string): Readonly<{ job: string; outside: string }> {
  const marker = "\n  phi-substitution-engine:\n";
  const start = workflow.indexOf(marker);
  if (start < 0) throw new Error("phi-substitution-engine job missing");
  const afterStart = start + marker.length;
  const next = workflow.slice(afterStart).search(/\n {2}[A-Za-z0-9_-]+:\n/);
  const end = next < 0 ? workflow.length : afterStart + next;
  return {
    job: workflow.slice(start, end),
    outside: workflow.slice(0, start) + workflow.slice(end),
  };
}

describe("GLY-353 Node 20 and scoped CI compatibility", () => {
  it("ORACLE-NODE20-EXACT-PINS: manifest and lock use the approved Node-20 graph", () => {
    expect(packageJson.engines.node).toBe(">=20.19.0");
    expect(packageJson.dependencies).toMatchObject({
      "@azure/identity": "4.13.1",
      "@azure/keyvault-keys": "4.10.2",
      "@azure/storage-file-share": "12.31.0",
    });
    expect(packageJson.devDependencies["@types/node"]).toMatch(/^\^?20\./);
    expect(lock.packages["node_modules/@azure/identity"]?.version).toBe(
      "4.13.1",
    );
    expect(lock.packages["node_modules/@azure/keyvault-keys"]?.version).toBe(
      "4.10.2",
    );
    expect(
      lock.packages["node_modules/@azure/storage-file-share"]?.version,
    ).toBe("12.31.0");
    expect(lock.packages["node_modules/@types/node"]?.version).toMatch(/^20\./);
  });

  it("ORACLE-NODE20-LOCK-CLOSURE: production and development closures admit CI Node", () => {
    const closure = installedClosure();
    expect(closure.has("node_modules/@azure/identity")).toBe(true);
    expect(closure.has("node_modules/vitest")).toBe(true);
    const incompatible: string[] = [];
    for (const packagePath of closure) {
      const range = lock.packages[packagePath]?.engines?.node;
      if (
        range !== undefined &&
        !semver.satisfies(CI_NODE, range, { includePrerelease: true })
      ) {
        incompatible.push(`${packagePath}:${range}`);
      }
    }
    expect(incompatible).toEqual([]);
  });

  it("ORACLE-CI-PHI-JOB-SCOPE: exact Node and engine-strict install stay inside the selected job", () => {
    const workflow = readFileSync(
      new URL("../../../.github/workflows/ci.yml", import.meta.url),
      "utf8",
    );
    const selected = phiJob(workflow);
    expect(selected.job).toContain("needs: changes");
    expect(selected.job).toContain(
      "needs.changes.outputs.phi-substitution-engine == 'true'",
    );
    expect(selected.job).toContain('node-version: "20.20.2"');
    expect(selected.job).toContain(
      "- run: npm_config_engine_strict=true npm ci",
    );
    expect(selected.job).toContain("- run: npm run typecheck");
    expect(selected.job).toContain("- run: npm test");
    expect(selected.outside).not.toContain("npm_config_engine_strict");
    expect(selected.outside).not.toContain('node-version: "20.20.2"');
    expect(workflow).toContain(
      "phi-substitution-engine:\n              - 'packages/phi-substitution-engine/**'",
    );
  });

  it("ORACLE-PROD-VERSION/N7-DOC: deployment obligations and Node graph are explicit", () => {
    const readme = readFileSync(
      new URL("../README.md", import.meta.url),
      "utf8",
    );
    expect(readme).toContain(
      "documented `engineVersion` must identify the supplied engine",
    );
    expect(readme).toContain("N7 layer-1 import scanning");
    expect(readme).toContain(
      "complete production **and development** lock closure",
    );
    expect(JSON.stringify(packageJson).toLowerCase()).not.toContain("glassy");
  });

  it("ORACLE-SEAM-FREEZE-AMENDMENT: the GLY-335 freeze and dated additive amendment coexist", () => {
    const source = readFileSync(
      new URL("../src/coverage/contracts.ts", import.meta.url),
      "utf8",
    );
    expect(source).toContain("SEAM (GLY-335 Wave 0 seam-freeze)");
    expect(source).toContain(
      "2026-08-18 — GLY-353 additive amendment: egressPolicyVersion and enginePolicyVersion are",
    );
    expect(source).toContain(
      "required signed claims; RFC 8785/SHA-256 canonicalization is normative",
    );
  });
});
