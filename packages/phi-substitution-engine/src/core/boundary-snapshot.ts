/**
 * Getter-throw-safe ingestion primitives (§7/N2).
 *
 * Every value that crosses a PUBLIC engine API boundary is UNTRUSTED: its own property getters may
 * throw a PHI-laden error, mutate between reads, or be a poisoned own `Symbol.iterator`/`.map`/
 * `.filter`; the carrier may be a non-array where an array is expected. These helpers read such a
 * value EXACTLY ONCE into inert, plain data at the boundary, so NOTHING downstream ever touches a
 * live getter — a mutating/throwing getter can no longer surface raw PHI to a caller, trace sink,
 * thrown error, or durable audit record, and a poisoned own iterator/map/filter can no longer hide
 * elements (own-index/own-length access never consults them).
 *
 * These defeat OWN-property hostility only. GLOBAL reassignment of a realm built-in (`Array.isArray`,
 * `Object.getOwnPropertyDescriptor`, `Array.prototype.*`) is ACE-equivalent and out of scope.
 */

/** Read one own property EXACTLY ONCE, getter-throw-safe. A throwing getter yields `undefined`. */
export function safeRead(obj: unknown, key: string): unknown {
  try {
    return (obj as Record<string, unknown> | null | undefined)?.[key];
  } catch {
    return undefined;
  }
}

/**
 * Own enumerable keys of a boundary object, trap-safe. A hostile `Proxy` with an `ownKeys`/
 * `getOwnPropertyDescriptor` trap that throws yields `[]` rather than propagating the raw (PHI) throw
 * out of a sanitizer (`Object.keys` would otherwise re-throw the trap).
 */
export function safeOwnKeys(obj: unknown): string[] {
  try {
    return Object.keys(obj as object);
  } catch {
    return [];
  }
}

/** Getter-safe read of a property that MUST be a string; `undefined` on throw or non-string. */
export function safeString(obj: unknown, key: string): string | undefined {
  const value = safeRead(obj, key);
  return typeof value === "string" ? value : undefined;
}

/**
 * Own-index/own-length copy of a boundary array — defeats a poisoned own `Symbol.iterator`/`.map`/
 * `.filter`/`.forEach` and a mutating own-index getter (each element read exactly once). Returns
 * `null` when `input` is NOT a genuine array (a non-array carrier is a compromised boundary) or when
 * any element read throws (fail closed) — the caller decides how to fail on `null`.
 */
export function intrinsicCopy<T>(input: unknown): T[] | null {
  if (!Array.isArray(input)) {
    return null;
  }
  const out: T[] = [];
  try {
    const len = (input as { length: number }).length;
    // A genuine array's `length` is always a non-negative integer. A Proxy-over-array whose `length`
    // trap returns anything else is not a faithful carrier — fail closed.
    if (!Number.isInteger(len) || len < 0) {
      return null;
    }
    for (let i = 0; i < len; i += 1) {
      out[out.length] = (input as T[])[i] as T;
    }
    // §7/N2: a Proxy-over-array whose `length` UNDER-reports (hides trailing elements) would silently
    // TRUNCATE this copy — a fail-OPEN when the copy feeds a REQUIRED set (e.g. approved surface forms,
    // whose omission egresses the value RAW). Reject if an OWN element exists AT the claimed length: the
    // carrier is then not a faithful array. (A Proxy that ALSO traps getOwnPropertyDescriptor/has to
    // fully conceal that element is indistinguishable from the source simply OMITTING it — a trusted-
    // source concealment no boundary read can detect, out of scope per the accepted threat line.)
    if (Object.prototype.hasOwnProperty.call(input, len)) {
      return null;
    }
  } catch {
    return null;
  }
  return out;
}
