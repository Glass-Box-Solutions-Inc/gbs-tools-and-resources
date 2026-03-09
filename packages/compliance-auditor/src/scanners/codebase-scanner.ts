// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// Git clone (shallow, depth=1) + recursive file discovery + analyzer
// orchestration. Clones repos to /tmp, discovers relevant source files,
// runs all applicable analyzers, and cleans up. Git clone uses piped stdio
// to prevent the GitHub token from appearing in logs.

import { execSync } from "node:child_process";
import { readdir, readFile, rm, stat } from "node:fs/promises";
import { join, extname } from "node:path";
import { env } from "../lib/env.js";
import type {
  ScannedFile,
  AnalyzerResult,
  ComplianceFindingInput,
} from "../types/index.js";
import type { BaseAnalyzer } from "../analyzers/base.analyzer.js";

const SCANNABLE_EXTENSIONS = new Set([
  ".ts",
  ".js",
  ".tsx",
  ".jsx",
  ".json",
  ".prisma",
  ".sql",
  ".env",
  ".example",
]);

const SKIP_DIRECTORIES = new Set([
  "node_modules",
  ".git",
  "dist",
  "build",
  ".next",
  ".nuxt",
  "coverage",
  ".turbo",
  ".cache",
  "vendor",
]);

// Maximum file size to scan (256 KB) — skip minified bundles and large assets
const MAX_FILE_SIZE = 256 * 1024;

/**
 * Scan a single repository: clone, discover files, run analyzers, clean up.
 */
export async function scanRepo(
  repo: string,
  analyzers: BaseAnalyzer[],
): Promise<{
  findings: ComplianceFindingInput[];
  filesScanned: number;
  analyzerResults: AnalyzerResult[];
}> {
  const cloneDir = `/tmp/compliance-scan-${repo}-${Date.now()}`;
  try {
    // Shallow clone — stdio piped to prevent token leakage in logs
    execSync(
      `git clone --depth=1 https://x-access-token:${env.GITHUB_TOKEN}@github.com/${env.GITHUB_ORG}/${repo}.git ${cloneDir}`,
      { stdio: "pipe", timeout: 60_000 },
    );

    // Discover files
    const files = await discoverFiles(cloneDir, repo);

    // Run analyzers
    const analyzerResults: AnalyzerResult[] = [];
    const allFindings: ComplianceFindingInput[] = [];

    for (const analyzer of analyzers) {
      const start = performance.now();
      const findings = await analyzer.analyze(files);
      analyzerResults.push({
        analyzerName: analyzer.analyzerName,
        findings,
        filesScanned: files.length,
        durationMs: Math.round(performance.now() - start),
      });
      allFindings.push(...findings);
    }

    return {
      findings: allFindings,
      filesScanned: files.length,
      analyzerResults,
    };
  } finally {
    await rm(cloneDir, { recursive: true, force: true });
  }
}

/**
 * Recursively discover scannable files in a cloned repository.
 * Skips node_modules, .git, dist, build, and files exceeding MAX_FILE_SIZE.
 */
async function discoverFiles(
  rootDir: string,
  repo: string,
): Promise<ScannedFile[]> {
  const files: ScannedFile[] = [];

  async function walk(dir: string): Promise<void> {
    const entries = await readdir(dir, { withFileTypes: true });
    for (const entry of entries) {
      if (SKIP_DIRECTORIES.has(entry.name)) continue;

      const fullPath = join(dir, entry.name);

      if (entry.isDirectory()) {
        await walk(fullPath);
        continue;
      }

      if (!entry.isFile()) continue;

      const ext = extname(entry.name);

      // Handle .env files and .example files specially (they have no ext or different ext)
      const isScannable =
        SCANNABLE_EXTENSIONS.has(ext) ||
        entry.name.startsWith(".env") ||
        entry.name.endsWith(".example");

      if (!isScannable) continue;

      // Skip files that are too large (likely minified/generated)
      const fileStat = await stat(fullPath);
      if (fileStat.size > MAX_FILE_SIZE) continue;

      const content = await readFile(fullPath, "utf-8");
      const relativePath = fullPath.slice(rootDir.length + 1);

      files.push({
        repo,
        filePath: relativePath,
        content,
        extension: ext || `.${entry.name.split(".").pop() ?? ""}`,
      });
    }
  }

  await walk(rootDir);
  return files;
}
