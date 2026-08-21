/**
 * Test harness for the L2.4 durable reversal store (GLY-337). Builds a `DurableReversalStore` over
 * the in-process dev `KeyProvider` + dev `SpoolVolume`, with a mutable clock, an injectable retention
 * classifier, and fault injection. `remount()` models a fresh replica over the SAME durable backend +
 * SAME KEK (so an acknowledged write is genuinely re-openable after replica loss).
 */
import {
  DurableReversalStore,
  InMemoryKeyProvider,
  InMemoryReversalSpoolBackend,
  mappingKeyOf,
} from "../src/tokens/durable/index";
import type {
  ReversalLookupRequest,
  ReversalLookupResult,
  ReversalRetentionClass,
  RetentionClassificationInput,
  SpoolFaults,
  SpoolVolume,
} from "../src/tokens/durable/index";
import type {
  DictionaryVersion,
  MatterId,
  OperationAttemptId,
  SubstitutionToken,
  TenantId,
} from "../src/core/brands";
import type { ReversalRecordInput } from "../src/core/contracts";

export const brand = <T>(value: unknown): T => value as unknown as T;

export const T0 = 1_700_000_000_000;
export const DETECTOR_TTL_MS = 86_400_000;

export interface MutableClock {
  now: () => number;
  set: (value: number) => void;
  advance: (deltaMs: number) => void;
}

export function makeClock(startMs = T0): MutableClock {
  let value = startMs;
  return {
    now: () => value,
    set: (v: number) => {
      value = v;
    },
    advance: (deltaMs: number) => {
      value += deltaMs;
    },
  };
}

/** Wraps a SpoolVolume to count publishes/flushes and capture the exact readCurrent keys. */
export interface VolumeSpy {
  readonly wrapper: SpoolVolume;
  readonly counts: {
    published: number;
    existing: number;
    prepare: number;
    flush: number;
    readCurrent: number;
  };
  lastReadRequests: readonly ReversalLookupRequest[];
}

export function spyVolume(inner: SpoolVolume): VolumeSpy {
  const spy: VolumeSpy = {
    counts: { published: 0, existing: 0, prepare: 0, flush: 0, readCurrent: 0 },
    lastReadRequests: [],
    wrapper: {
      ensureDekGeneration: (i) => inner.ensureDekGeneration(i),
      reserveNonce: (i) => inner.reserveNonce(i),
      prepare: (i) => {
        spy.counts.prepare += 1;
        return inner.prepare(i);
      },
      publish: async (p) => {
        const result = await inner.publish(p);
        if (result.kind === "published") {
          spy.counts.published += 1;
        } else {
          spy.counts.existing += 1;
        }
        return result;
      },
      flush: (c) => {
        spy.counts.flush += 1;
        return inner.flush(c);
      },
      readCurrent: (
        requests: readonly ReversalLookupRequest[],
      ): Promise<readonly ReversalLookupResult[]> => {
        spy.counts.readCurrent += 1;
        spy.lastReadRequests = requests;
        return inner.readCurrent(requests);
      },
    },
  };
  return spy;
}

export type RetentionOption =
  | ReversalRetentionClass
  | ((
      input: RetentionClassificationInput,
    ) => ReversalRetentionClass | Promise<ReversalRetentionClass>);

export interface HarnessOptions {
  retention?: RetentionOption;
  maximumEncounteredTokenBatch?: number;
  faults?: SpoolFaults;
  clock?: () => number;
  backend?: InMemoryReversalSpoolBackend;
  keyProvider?: InMemoryKeyProvider;
}

export interface MountedStore {
  readonly store: DurableReversalStore;
  readonly spy: VolumeSpy;
}

export interface Harness extends MountedStore {
  readonly backend: InMemoryReversalSpoolBackend;
  readonly keyProvider: InMemoryKeyProvider;
  readonly clock: () => number;
  readonly faults: SpoolFaults;
  readonly classifyRetention: (
    input: RetentionClassificationInput,
  ) => Promise<ReversalRetentionClass>;
  readonly maximumEncounteredTokenBatch: number;
  /** A fresh replica over the SAME durable backend + KEK (models replica loss / remount). */
  remount: (faults?: SpoolFaults) => MountedStore;
}

function classifierFrom(
  retention: RetentionOption,
): (input: RetentionClassificationInput) => Promise<ReversalRetentionClass> {
  if (typeof retention === "function") {
    return async (input) => retention(input);
  }
  return async () => retention;
}

function mountStore(
  backend: InMemoryReversalSpoolBackend,
  keyProvider: InMemoryKeyProvider,
  clock: () => number,
  classifyRetention: (
    input: RetentionClassificationInput,
  ) => Promise<ReversalRetentionClass>,
  maximumEncounteredTokenBatch: number,
  faults: SpoolFaults,
): MountedStore {
  const rawVolume = backend.mount(faults, clock);
  const spy = spyVolume(rawVolume);
  const store = new DurableReversalStore({
    keyProvider,
    spoolVolume: spy.wrapper,
    classifyRetention,
    nowEpochMilliseconds: clock,
    maximumEncounteredTokenBatch,
  });
  return { store, spy };
}

export function makeHarness(options: HarnessOptions = {}): Harness {
  const backend = options.backend ?? new InMemoryReversalSpoolBackend();
  const keyProvider = options.keyProvider ?? new InMemoryKeyProvider();
  const clock = options.clock ?? (() => Date.now());
  const maximumEncounteredTokenBatch =
    options.maximumEncounteredTokenBatch ?? 256;
  const classifyRetention = classifierFrom(options.retention ?? "matter");
  const faults: SpoolFaults = options.faults ?? {};
  const mounted = mountStore(
    backend,
    keyProvider,
    clock,
    classifyRetention,
    maximumEncounteredTokenBatch,
    faults,
  );
  return {
    ...mounted,
    backend,
    keyProvider,
    clock,
    faults,
    classifyRetention,
    maximumEncounteredTokenBatch,
    remount: (remountFaults: SpoolFaults = {}) => {
      // Replica loss: a fresh replica takes over the durable volume; unflushed writes are discarded.
      backend.crash();
      return mountStore(
        backend,
        keyProvider,
        clock,
        classifyRetention,
        maximumEncounteredTokenBatch,
        remountFaults,
      );
    },
  };
}

/** Two LIVE replicas mounted on ONE shared durable backend + one KEK (for cross-replica race oracles). */
export interface TwoMounts {
  readonly backend: InMemoryReversalSpoolBackend;
  readonly keyProvider: InMemoryKeyProvider;
  readonly clock: () => number;
  readonly a: MountedStore;
  readonly b: MountedStore;
  /** Total real (first-write) commits across both replicas. */
  publishedTotal: () => number;
}

export function twoMounts(
  options: { retention?: RetentionOption; clock?: () => number } = {},
): TwoMounts {
  const backend = new InMemoryReversalSpoolBackend();
  const keyProvider = new InMemoryKeyProvider();
  const clock = options.clock ?? (() => Date.now());
  const classifyRetention = classifierFrom(options.retention ?? "matter");
  const a = mountStore(backend, keyProvider, clock, classifyRetention, 256, {});
  const b = mountStore(backend, keyProvider, clock, classifyRetention, 256, {});
  return {
    backend,
    keyProvider,
    clock,
    a,
    b,
    publishedTotal: () => a.spy.counts.published + b.spy.counts.published,
  };
}

// ---- input builders ----

export const DEFAULT_TENANT = brand<TenantId>("tenant-a");
export const DEFAULT_MATTER = brand<MatterId>("matter-1");
export const DEFAULT_VERSION = brand<DictionaryVersion>(1n);
export const DEFAULT_TOKEN = brand<SubstitutionToken>("[[Claimant]]");
export const DEFAULT_CANONICAL = "Maria García";

export function recordInput(
  over: Partial<ReversalRecordInput> = {},
): ReversalRecordInput {
  return {
    tenantId: DEFAULT_TENANT,
    matterId: DEFAULT_MATTER,
    dictionaryVersion: DEFAULT_VERSION,
    token: DEFAULT_TOKEN,
    canonical: DEFAULT_CANONICAL,
    attemptId: brand<OperationAttemptId>("att-1"),
    ...over,
  };
}

export interface ResolveInput {
  tenantId: TenantId;
  matterId: MatterId;
  dictionaryVersion: DictionaryVersion;
  tokens: readonly SubstitutionToken[];
}

export function resolveInput(over: Partial<ResolveInput> = {}): ResolveInput {
  return {
    tenantId: DEFAULT_TENANT,
    matterId: DEFAULT_MATTER,
    dictionaryVersion: DEFAULT_VERSION,
    tokens: [DEFAULT_TOKEN],
    ...over,
  };
}

export function keyFor(
  over: Partial<ResolveInput> & { token?: SubstitutionToken } = {},
) {
  const tenantId = over.tenantId ?? DEFAULT_TENANT;
  const matterId = over.matterId ?? DEFAULT_MATTER;
  const dictionaryVersion = over.dictionaryVersion ?? DEFAULT_VERSION;
  const token = over.token ?? DEFAULT_TOKEN;
  return mappingKeyOf(tenantId, matterId, dictionaryVersion, token);
}

/** Yields to the macrotask queue so all pending microtasks settle (for pending-promise assertions). */
export function macrotask(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 0));
}
