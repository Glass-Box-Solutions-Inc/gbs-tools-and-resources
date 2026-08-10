/** Pure, dependency-free helpers shared by the phase-1 variant expanders. */

/** De-duplicates while preserving first-seen order. Output order is stable. */
export function dedupeInOrder(values: readonly string[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const value of values) {
    if (!seen.has(value)) {
      seen.add(value);
      out.push(value);
    }
  }
  return out;
}

/** Counts alphanumeric code points; used to reject lossy/too-short identifiers. */
export function alphanumericLength(value: string): number {
  let count = 0;
  for (const ch of value) {
    if (ch >= "0" && ch <= "9") count += 1;
    else if (ch >= "A" && ch <= "Z") count += 1;
    else if (ch >= "a" && ch <= "z") count += 1;
  }
  return count;
}
