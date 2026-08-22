/**
 * GLY-373 §3.2.4 — the object-level halves of the THREE LAYERED CONTROLS.
 *
 * Control 1, SHAPE (`assertGuardErrorShape`, OR-14(f)) — the PRIMARY control. It pins the thrown
 * object's own property graph, its prototype chain, its frozenness, and its serialized form.
 * Control 2, WALK (`walkForCanaries`, OR-14(g)) — the SECONDARY control, retained as defence in
 * depth for whatever (f)'s assumptions miss: nested and inherited values, `cause` chains,
 * `AggregateError.errors`, accessors, symbol keys, and `stack`.
 *
 * NEITHER IS SUFFICIENT, and the spec says so rather than over-claiming. The revision-9 scope
 * correction withdrew the claim that an object-level oracle can establish "no reachable caller
 * data": executed evasions that pass a conforming shape check include a module-level `WeakMap`
 * keyed by the error (the entry lives in the GUARD MODULE, not on the error, so no inspection of
 * the object can see it), a transparent `Proxy` wrapper, a canary interpolated into `stack`, and a
 * mutable `safeDetails` populated after the oracle runs. Control 3 — the STATIC SOURCE oracle of
 * OR-14(h) — exists precisely because controls 1 and 2 are object-level; MUT-29(a) is killed there
 * and nowhere else.
 */
import { expect } from "vitest";
import { PhiEngineError, isPhiEngineError } from "../src/core/errors";

// ---------------------------------------------------------------------------------------------
// Control 2 — the recursive reachability walk.
// ---------------------------------------------------------------------------------------------

const MAX_DEPTH = 24;
const MAX_NODES = 20_000;

/**
 * REALM INTRINSICS ARE NOT CALLER DATA, and descending into them makes the walker useless rather
 * than stronger: `Object.prototype.__proto__` is an accessor, so an unbounded walk reaches
 * `Object.assign.caller` and every other built-in, where strict-mode `caller`/`arguments` throw —
 * producing hundreds of "threw during read" records that have nothing to do with the error under
 * test and would drown a real hit.
 *
 * The bound is on the REALM, never on depth-with-silent-truncation: the walk still covers every
 * own key (string and symbol, enumerable and non-enumerable), `cause` chains, `AggregateError`
 * elements, collections, and accessors defined on the error's OWN prototype chain — which is where
 * a guard could actually park a canary. The walker's mandatory self-test proves each of those
 * channels is still detected.
 */
const INTRINSIC_PROTOTYPES: readonly object[] = [
  Object.prototype,
  Function.prototype,
  Error.prototype,
  Array.prototype,
  Map.prototype,
  Set.prototype,
  Promise.prototype,
  RegExp.prototype,
  Date.prototype,
  String.prototype,
  Number.prototype,
  Boolean.prototype,
  Symbol.prototype,
  AggregateError.prototype,
  TypeError.prototype,
];

function isIntrinsic(value: unknown): boolean {
  return INTRINSIC_PROTOTYPES.includes(value as object);
}

/**
 * Returns every `canary` string reachable from `root`, with the path at which it was found.
 * An EMPTY array is the pass condition.
 *
 * Bounds are LOUD, NEVER SILENT: hitting the depth or node bound THROWS. A walker that silently
 * truncated would turn "did not look" into "found nothing", which is the exact failure this
 * control exists to prevent.
 */
export function walkForCanaries(
  root: unknown,
  canaries: readonly string[],
): string[] {
  const hits: string[] = [];
  const seen = new WeakSet<object>();
  let nodes = 0;

  const testLeaf = (value: string, path: string): void => {
    for (const canary of canaries) {
      if (canary !== "" && value.includes(canary)) {
        // The hit carries the PATH, the canary, AND the matched value — the value is what lets the
        // self-test verify that a specific CHANNEL was detected rather than merely that some hit
        // occurred, which is the difference between a walker that works and one that looks like it.
        hits.push(`${path}: ${canary} :: ${value}`);
      }
    }
  };

  const visit = (value: unknown, path: string, depth: number): void => {
    nodes += 1;
    if (depth > MAX_DEPTH) {
      throw new Error(`canary walker exceeded depth bound at ${path}`);
    }
    if (nodes > MAX_NODES) {
      throw new Error(`canary walker exceeded node bound at ${path}`);
    }
    if (value === null || value === undefined) return;

    // Leaves. Coercion is guarded; a THROWING coercion is a failure, never a pass.
    if (typeof value === "string") return testLeaf(value, path);
    if (typeof value === "number" || typeof value === "boolean") {
      return testLeaf(String(value), path);
    }
    if (typeof value === "bigint") return testLeaf(value.toString(), path);
    if (typeof value === "symbol") {
      return testLeaf(value.description ?? "", `${path}[symbol description]`);
    }
    if (typeof value === "function") {
      // A function is a LEAF: its body is engine or realm code, never caller data, and descending
      // into `.caller`/`.arguments`/`.prototype` only reaches intrinsics. Its NAME is still tested,
      // since that is the one part an attacker could control.
      return testLeaf(value.name, `${path}[function name]`);
    }
    if (typeof value !== "object") {
      return;
    }
    if (isIntrinsic(value)) return;

    const object = value as object;
    if (seen.has(object)) return; // cycle safety
    seen.add(object);

    // Collections.
    if (Array.isArray(object)) {
      object.forEach((element, index) =>
        visit(element, `${path}[${index}]`, depth + 1),
      );
    }
    if (object instanceof Map) {
      let i = 0;
      for (const [k, v] of object) {
        visit(k, `${path}.mapKey[${i}]`, depth + 1);
        visit(v, `${path}.mapValue[${i}]`, depth + 1);
        i += 1;
      }
    }
    if (object instanceof Set) {
      let i = 0;
      for (const member of object) {
        visit(member, `${path}.setMember[${i}]`, depth + 1);
        i += 1;
      }
    }
    if (object instanceof AggregateError) {
      visit(object.errors, `${path}.errors`, depth + 1);
    }

    // OWN keys — string AND symbol, enumerable AND non-enumerable alike. `message` and `stack` are
    // own non-enumerable on `Error` and MUST both be inspected; `stack` is included because a guard
    // that interpolates a rejected id into a constructed error's message leaves it in the stack
    // header, where `Object.keys` and `JSON.stringify` both miss it.
    for (const key of Reflect.ownKeys(object)) {
      // `__proto__` is an accessor for the prototype, which the chain sweep below already covers.
      if (key === "__proto__") continue;
      const label = typeof key === "symbol" ? `[${String(key)}]` : `.${key}`;
      let read: unknown;
      try {
        read = (object as Record<PropertyKey, unknown>)[key];
      } catch (error) {
        // A throwing OWN accessor is RECORDED and skipped, never treated as clean.
        hits.push(`${path}${label}: threw during read (${String(error)})`);
        continue;
      }
      visit(read, `${path}${label}`, depth + 1);
    }

    // PROTOTYPE-CHAIN accessors are invoked inside try/catch and their returned values walked.
    let proto: unknown = Object.getPrototypeOf(object);
    let protoDepth = 0;
    while (
      proto !== null &&
      proto !== undefined &&
      !isIntrinsic(proto) &&
      protoDepth < 8
    ) {
      for (const key of Reflect.ownKeys(proto as object)) {
        if (key === "__proto__") continue;
        const descriptor = Object.getOwnPropertyDescriptor(
          proto as object,
          key,
        );
        if (descriptor?.get === undefined) continue;
        const label =
          typeof key === "symbol"
            ? `[${String(key)}]`
            : `.${key}(prototype getter)`;
        try {
          visit(descriptor.get.call(object), `${path}${label}`, depth + 1);
        } catch (error) {
          hits.push(`${path}${label}: threw during read (${String(error)})`);
        }
      }
      proto = Object.getPrototypeOf(proto as object);
      protoDepth += 1;
    }

    // `cause` chains to their end — retained as defence in depth for FUTURE engine errors and for
    // consumer-wrapped errors that may chain one. NO engine error carries a `cause` at 8105730
    // (`tokens/errors.ts:15-23`, `core/errors.ts:13-33`), so the traversal is not justified by any
    // current error and the spec says so rather than inventing a rationale. It is already covered
    // by the own-key sweep above; this is the explicit, named traversal.
    const cause = (object as { cause?: unknown }).cause;
    if (cause !== undefined) visit(cause, `${path}.cause`, depth + 1);

    return;
  };

  visit(root, "root", 0);
  return hits;
}

/**
 * MANDATORY SELF-TEST for the walker (OR-14(g) step 8). Without it, a broken walker makes every
 * downstream assertion pass VACUOUSLY. The positive control deliberately carries a canary at every
 * channel the walker claims to cover; the walker MUST detect every one.
 */
export function assertWalkerSelfTest(): void {
  const canary = "GLY373-WALKER-SELFTEST";
  const symbolKey = Symbol("gly373-symbol-key");

  class WithGetter extends Error {
    get exposed(): string {
      return `${canary}-prototype-getter`;
    }
  }

  const deep = new Error(`${canary}-cause-cause`);
  const middle = new Error("middle");
  (middle as { cause?: unknown }).cause = deep;

  const control = new WithGetter(`${canary}-message`);
  (control as { cause?: unknown }).cause = middle;
  Object.defineProperty(control, "hidden", {
    value: `${canary}-own-non-enumerable`,
    enumerable: false,
  });
  (control as Record<PropertyKey, unknown>)[symbolKey] =
    `${canary}-symbol-keyed`;
  (control as { aggregate?: unknown }).aggregate = new AggregateError(
    [new Error(`${canary}-aggregate-element`)],
    "agg",
  );

  const found = walkForCanaries(control, [canary]);
  const channels = [
    "-message",
    "-own-non-enumerable",
    "-cause-cause",
    "-aggregate-element",
    "-symbol-keyed",
    "-prototype-getter",
  ];
  for (const channel of channels) {
    expect(
      found.some((hit) => hit.includes(`${canary}${channel}`)),
      `walker self-test: ${channel} must be detected`,
    ).toBe(true);
  }
}

// ---------------------------------------------------------------------------------------------
// Control 1 — the frozen-shape oracle.
// ---------------------------------------------------------------------------------------------

export interface GuardShapeExpectation {
  readonly code: string;
  readonly operationId: string;
  /** Sorted own keys expected on `safeDetails`; `[]` for the §3.2.4 guard error. */
  readonly safeDetailKeys: readonly string[];
  readonly canaries: readonly string[];
  /** `message` defaults to `code`, which is what `super(code)` sets. */
  readonly message?: string;
}

/**
 * OR-14(f), applied to the value ACTUALLY CAUGHT at the call site — never to a locally constructed
 * instance, which would prove nothing about what was thrown.
 *
 * PARAMETERISED, because §3.2.5 requirement 3 requires it: the conflict error legitimately carries
 * `AMBIGUOUS_KNOWN_IDENTIFIER`, the call's real `operationId`, and a one-key `safeDetails`, none of
 * which hold for the §3.2.4 guard error. A spec that mandated an impossible assertion here would
 * be a spec that gets quietly ignored, so the structural rows are shared and the values are inputs.
 */
export function assertGuardErrorShape(
  caught: unknown,
  expected: GuardShapeExpectation,
): void {
  // 1. The published contract is preserved; there is no subclass to assert.
  expect(caught instanceof PhiEngineError).toBe(true);
  expect(isPhiEngineError(caught)).toBe(true);
  const err = caught as PhiEngineError & Record<PropertyKey, unknown>;

  // 2. The own-key set, compared as a SORTED SET — never an ordered list. V8's placement of
  //    `stack`/`message` is an implementation detail; pinning the order makes the oracle brittle
  //    without making it stronger.
  expect([...Reflect.ownKeys(err)].map(String).sort()).toEqual(
    ["code", "message", "name", "operationId", "safeDetails", "stack"].sort(),
  );

  // 3. Each own value equals its spec literal.
  expect(err.name).toBe("PhiEngineError");
  expect(err.message).toBe(expected.message ?? expected.code);
  expect(err.code).toBe(expected.code);
  expect(String(err.operationId)).toBe(expected.operationId);

  // 3a. `safeDetails` is INERT. Deep-equality against `{}` alone is insufficient — a MUTABLE empty
  //     object passes it and can be populated after the oracle returns (MUT-29(d)).
  expect(Object.isFrozen(err.safeDetails)).toBe(true);
  expect([...Reflect.ownKeys(err.safeDetails)].map(String).sort()).toEqual(
    [...expected.safeDetailKeys].sort(),
  );

  // 3b. `stack` is CLEAN. Asserted here, in the PRIMARY control, so a canary interpolated into the
  //     stack header is caught by (f) and not only by the walker.
  expect(typeof err.stack).toBe("string");
  for (const canary of expected.canaries) {
    expect(err.stack).not.toContain(canary);
  }

  // 4. Frozen.
  expect(Object.isFrozen(err)).toBe(true);

  // 5. The prototype chain, walked to null. This does NOT exclude a transparent `Proxy` — an
  //    executed probe returns `instanceof:true`, `isFrozen:true`, identical own keys and this exact
  //    chain — and the spec records that as a stated residual rather than over-claiming. What (5)
  //    DOES exclude is a substituted or EXTENDED prototype chain. In-engine `Proxy` construction is
  //    excluded by OR-14(h)'s token ban; a Proxy applied above the engine boundary is out of scope.
  const chain: unknown[] = [];
  let proto: unknown = Object.getPrototypeOf(err);
  while (proto !== null) {
    chain.push(proto);
    proto = Object.getPrototypeOf(proto as object);
  }
  expect(chain).toEqual([
    PhiEngineError.prototype,
    Error.prototype,
    Object.prototype,
  ]);

  // 6. The `in` operator, so an INHERITED definition anywhere on the chain fails too.
  expect("cause" in err).toBe(false);
  expect("toJSON" in err).toBe(false);
  expect(Symbol.toPrimitive in err).toBe(false);
  expect(Symbol.toStringTag in err).toBe(false);

  // 7. No own symbol keys and no own function-valued property.
  expect(Object.getOwnPropertySymbols(err)).toEqual([]);
  for (const key of Reflect.ownKeys(err)) {
    expect(typeof err[key]).not.toBe("function");
  }

  // 8. Serialized form. Deep-equality on the PARSED object rather than string equality on the raw
  //    output, because key order in the string is creation-order dependent; the raw string is
  //    additionally asserted canary-free.
  const raw = JSON.stringify(err);
  const parsed = JSON.parse(raw) as Record<string, unknown>;
  expect(Object.keys(parsed).sort()).toEqual(
    ["code", "name", "operationId", "safeDetails"].sort(),
  );
  expect(parsed.name).toBe("PhiEngineError");
  expect(parsed.code).toBe(expected.code);
  expect(parsed.operationId).toBe(expected.operationId);
  for (const canary of expected.canaries) {
    expect(raw).not.toContain(canary);
  }

  // 9. POST-ORACLE WRITE ATTEMPT. An oracle that only READS cannot distinguish a frozen object
  //    from one that is about to be mutated, so the writes must be attempted and must THROW —
  //    then step 3a is re-asserted. (Vitest runs ES modules in strict mode, so a write to a frozen
  //    object throws rather than failing silently.)
  const canary = expected.canaries[0] ?? "GLY373-POST-ORACLE";
  expect(() => {
    (err.safeDetails as Record<string, unknown>).injected = canary;
  }).toThrow();
  expect(() => {
    (err as Record<string, unknown>).code = canary;
  }).toThrow();
  expect(Object.isFrozen(err.safeDetails)).toBe(true);
  expect([...Reflect.ownKeys(err.safeDetails)].map(String).sort()).toEqual(
    [...expected.safeDetailKeys].sort(),
  );
}
