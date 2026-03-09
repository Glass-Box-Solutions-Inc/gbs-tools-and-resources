// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// Latency recorder. Maintains a circular buffer of latency samples
// per system and computes p50/p95/p99 percentiles. Persists to
// /tmp/validation-state.json for crash recovery (Squeegee pattern).

import { readFile, writeFile } from "node:fs/promises";
import type { SystemName, LatencyMetrics } from "../types/index.js";

const LATENCY_FILE = "/tmp/validation-latency.json";
const MAX_SAMPLES_PER_SYSTEM = 500;

interface LatencyStore {
  [systemName: string]: number[];
}

let store: LatencyStore = {};

export async function loadLatencyState(): Promise<void> {
  try {
    const raw = await readFile(LATENCY_FILE, "utf-8");
    const parsed = JSON.parse(raw);
    if (typeof parsed === "object" && parsed !== null) {
      store = parsed;
    }
  } catch {
    store = {};
  }
}

export async function saveLatencyState(): Promise<void> {
  await writeFile(LATENCY_FILE, JSON.stringify(store, null, 2));
}

export function recordSamples(
  systemName: SystemName,
  samples: number[],
): void {
  if (!store[systemName]) {
    store[systemName] = [];
  }
  store[systemName].push(...samples);
  // Enforce circular buffer — keep only the latest MAX_SAMPLES_PER_SYSTEM
  if (store[systemName].length > MAX_SAMPLES_PER_SYSTEM) {
    store[systemName] = store[systemName].slice(-MAX_SAMPLES_PER_SYSTEM);
  }
}

export function computePercentiles(
  systemName: SystemName,
): LatencyMetrics | null {
  const samples = store[systemName];
  if (!samples || samples.length === 0) {
    return null;
  }
  const sorted = [...samples].sort((a, b) => a - b);
  return {
    p50: sorted[Math.floor(sorted.length * 0.5)] ?? 0,
    p95: sorted[Math.floor(sorted.length * 0.95)] ?? 0,
    p99: sorted[Math.floor(sorted.length * 0.99)] ?? 0,
    samples: sorted,
  };
}

export function getSystemLatency(
  systemName: SystemName,
): LatencyMetrics | null {
  return computePercentiles(systemName);
}

export function getAllLatencies(): Record<
  string,
  LatencyMetrics | null
> {
  const result: Record<string, LatencyMetrics | null> = {};
  for (const systemName of Object.keys(store)) {
    result[systemName] = computePercentiles(systemName as SystemName);
  }
  return result;
}
