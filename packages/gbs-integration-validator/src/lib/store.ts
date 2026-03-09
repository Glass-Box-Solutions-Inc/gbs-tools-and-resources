// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// In-memory circular buffer store for validation runs.
// Persists to /tmp/validation-state.json for crash recovery (Squeegee pattern).
// Max 100 runs retained — oldest are evicted on insert.

import { readFile, writeFile } from "node:fs/promises";
import type { ValidationRun } from "../types/index.js";

const STATE_FILE = "/tmp/validation-state.json";
const MAX_RUNS = 100;

let runs: ValidationRun[] = [];

export async function loadState(): Promise<void> {
  try {
    const raw = await readFile(STATE_FILE, "utf-8");
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) {
      runs = parsed;
    }
  } catch {
    runs = [];
  }
}

export async function saveState(): Promise<void> {
  await writeFile(STATE_FILE, JSON.stringify(runs, null, 2));
}

export function getRuns(): ValidationRun[] {
  return runs;
}

export function getRun(runId: string): ValidationRun | undefined {
  return runs.find((r) => r.runId === runId);
}

export function addRun(run: ValidationRun): void {
  runs.unshift(run);
  if (runs.length > MAX_RUNS) {
    runs.pop();
  }
}

export function updateRun(
  runId: string,
  update: Partial<ValidationRun>,
): void {
  const idx = runs.findIndex((r) => r.runId === runId);
  if (idx !== -1) {
    runs[idx] = { ...runs[idx], ...update } as ValidationRun;
  }
}
