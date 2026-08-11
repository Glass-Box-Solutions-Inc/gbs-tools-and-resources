/**
 * Aho–Corasick multi-pattern automaton (CONTRACT-phase1 §3.1.2).
 *
 * The compiler builds ONE immutable automaton over the allow-listed, folded
 * surface forms of a matter's tagged case truth, so a single linear pass over
 * the (already length-bounded) request text finds every known-value occurrence.
 * The automaton stores no plaintext beyond the folded patterns it was built
 * from and is never serialized. It reports matches in text-scan order as
 * `(endExclusive, patternId)` pairs; the caller maps those back to original
 * UTF-16 spans and applies the C1–C8 collision policy.
 *
 * Matching is over UTF-16 code units, matching the offset convention used by
 * the normalizer and the collision boundary rules; boundary correctness is the
 * boundary rule's responsibility, not the automaton's.
 */

export interface AhoCorasickMatch {
  /** Exclusive end offset (UTF-16 code units) of the match in the scanned text. */
  readonly end: number;
  /** Pattern id returned by {@link AhoCorasickBuilder.add}. */
  readonly patternId: number;
  /** Length (UTF-16 code units) of the matched pattern. */
  readonly length: number;
}

interface FrozenAutomaton {
  readonly next: ReadonlyArray<Map<number, number>>;
  readonly fail: ReadonlyArray<number>;
  readonly output: ReadonlyArray<ReadonlyArray<number>>;
  readonly lengths: ReadonlyArray<number>;
}

/** An opaque, built automaton. Its only capability is a forward scan. */
export class AhoCorasickAutomaton {
  private readonly a: FrozenAutomaton;

  public constructor(automaton: FrozenAutomaton) {
    this.a = automaton;
  }

  /** Total number of distinct patterns compiled into the automaton. */
  public get patternCount(): number {
    return this.a.lengths.length;
  }

  /** Single forward pass; matches are reported in ascending end-offset order. */
  public match(text: string): readonly AhoCorasickMatch[] {
    const matches: AhoCorasickMatch[] = [];
    const { next, fail, output, lengths } = this.a;
    let node = 0;
    for (let i = 0; i < text.length; i += 1) {
      const unit = text.charCodeAt(i);
      // Follow failure links until a goto exists or we fall back to the root.
      let candidate = next[node]?.get(unit);
      while (candidate === undefined && node !== 0) {
        node = fail[node] ?? 0;
        candidate = next[node]?.get(unit);
      }
      node = candidate ?? 0;
      const hits = output[node];
      if (hits !== undefined && hits.length > 0) {
        const end = i + 1;
        for (const patternId of hits) {
          matches.push({ end, patternId, length: lengths[patternId] ?? 0 });
        }
      }
    }
    return matches;
  }
}

/** Mutable builder; call {@link build} exactly once to freeze the automaton. */
export class AhoCorasickBuilder {
  private readonly next: Array<Map<number, number>> = [new Map()];
  private readonly fail: number[] = [0];
  private readonly output: number[][] = [[]];
  private readonly lengths: number[] = [];

  /** Adds a pattern and returns its stable id. Empty patterns are rejected. */
  public add(pattern: string): number {
    if (pattern.length === 0) {
      throw new Error("aho_corasick_empty_pattern");
    }
    let node = 0;
    for (let i = 0; i < pattern.length; i += 1) {
      const unit = pattern.charCodeAt(i);
      const existing = this.next[node]?.get(unit);
      if (existing === undefined) {
        const created = this.next.length;
        this.next.push(new Map());
        this.fail.push(0);
        this.output.push([]);
        this.next[node]?.set(unit, created);
        node = created;
      } else {
        node = existing;
      }
    }
    const patternId = this.lengths.length;
    this.lengths.push(pattern.length);
    this.output[node]?.push(patternId);
    return patternId;
  }

  /** Computes failure links (BFS) and merges suffix outputs, then freezes. */
  public build(): AhoCorasickAutomaton {
    const queue: number[] = [];
    const root = 0;
    for (const child of this.next[root]?.values() ?? []) {
      this.fail[child] = root;
      queue.push(child);
    }
    let head = 0;
    while (head < queue.length) {
      const node = queue[head] as number;
      head += 1;
      for (const [unit, child] of this.next[node]?.entries() ?? []) {
        // Failure link: longest proper suffix that is also a prefix.
        let candidate = this.fail[node] ?? root;
        let link = this.next[candidate]?.get(unit);
        while (link === undefined && candidate !== root) {
          candidate = this.fail[candidate] ?? root;
          link = this.next[candidate]?.get(unit);
        }
        this.fail[child] = link !== undefined && link !== child ? link : root;
        // Merge the failure node's outputs so every terminal suffix reports.
        const inherited = this.output[this.fail[child] as number];
        if (inherited !== undefined && inherited.length > 0) {
          const own = this.output[child] as number[];
          for (const id of inherited) own.push(id);
        }
        queue.push(child);
      }
    }
    return new AhoCorasickAutomaton({
      next: this.next,
      fail: this.fail,
      output: this.output,
      lengths: this.lengths,
    });
  }
}
