/**
 * GLY-373 §3.2.4 — QUERY 2b: UTF-8 round-trip suspects.  NON-BLOCKING.  READ-ONLY.
 *
 * WHY THIS RUNS OUTSIDE SQL.  Query 1's `decodable` predicate is scoped to CANONICALITY and no
 * further: `encodeTextKey` also guarantees its bytes are VALID UTF-8, and canonical base64url does
 * not.  Executed counterexample — `b64url-v1:gA` decodes to the single byte `0x80`, which is
 * canonical base64url (`decodable = true`), carries zero NULs, and contains no `EF BF BD`, so
 * NONE of the three finding-producing SQL statements returns a row for a value that no
 * `encodeTextKey` call could have written.  PostgreSQL cannot close that gap in the same statement:
 * `convert_from(…, 'UTF8')` RAISES on invalid bytes, which is the very reason the NUL counting is
 * done on `bytea` in the first place.
 *
 * INPUT.  The COMPLETE `(tbl, col, enc)` set exported by QUERY 2a — the whole decodable set, never
 * a subset.  Query 2a exists precisely because no other statement exported that set, which made
 * this check VACUOUS for exactly the class it detects.  A NARROWED input reintroduces that defect.
 *
 * OUTPUT AND HANDLING.  NON-BLOCKING, for the same reason as Query 2: a flagged row is a SUSPECT,
 * NOT A PROVEN ALIAS — after the U+FFFD substitution, a key derived from a lone surrogate and one
 * derived from legitimate U+FFFD content are byte-identical and cannot be told apart after the
 * fact — so blocking on it would block on evidence that can never be resolved either way.
 * Enumerate suspects on the GLY-373 ticket for principal review and attach this output to the
 * release manifest WHETHER OR NOT IT IS EMPTY, alongside the Query 2a export, so a reviewer can see
 * that 2b was fed 2a's complete decodable set rather than a narrowed one.
 *
 * NO ROW MAY BE DELETED OR REWRITTEN ON THIS EVIDENCE.  Keys are reported AS STORED, never decoded
 * (the Query 1c constraint): an ill-formed key is exactly what must not be re-emitted as text.
 *
 * USAGE
 *   psql "$CONNECTION" -At -F $'\t' -f migrations/audit/gly373-historical-key-audit.sql   # 2a rows
 *   ... | npx tsx jobs/gly373-key-audit-2b.ts
 * Reads TSV `tbl<TAB>col<TAB>enc` on stdin, one Query 2a row per line, and writes a JSON report to
 * stdout.  It opens no database connection and performs no write of any kind.
 */

const KEY_PREFIX = "b64url-v1:";

export interface ExportedKeyRow {
  readonly tbl: string;
  readonly col: string;
  readonly enc: string;
}

export interface RoundTripReport {
  readonly checked: number;
  readonly suspects: readonly ExportedKeyRow[];
  /** Rows lacking the frozen prefix — Query 1b's blocking finding, surfaced here for completeness. */
  readonly unprefixed: readonly ExportedKeyRow[];
}

/**
 * `Buffer.prototype.toString("utf8")` substitutes U+FFFD for EVERY invalid sequence, so a mismatch
 * between the stored payload and the re-encoded round trip means exactly one thing: the stored
 * bytes are not what any `Buffer.from(value, "utf8")` produced.
 */
export function isRoundTripSuspect(enc: string): boolean {
  const b64u = enc.slice(KEY_PREFIX.length);
  const roundTrip =
    KEY_PREFIX +
    Buffer.from(
      Buffer.from(b64u, "base64url").toString("utf8"),
      "utf8",
    ).toString("base64url");
  return roundTrip !== enc;
}

export function auditExportedKeys(
  rows: readonly ExportedKeyRow[],
): RoundTripReport {
  const suspects: ExportedKeyRow[] = [];
  const unprefixed: ExportedKeyRow[] = [];
  for (const row of rows) {
    if (!row.enc.startsWith(KEY_PREFIX)) {
      unprefixed.push(row);
      continue;
    }
    if (isRoundTripSuspect(row.enc)) suspects.push(row);
  }
  return { checked: rows.length, suspects, unprefixed };
}

function parseTsv(input: string): ExportedKeyRow[] {
  const rows: ExportedKeyRow[] = [];
  for (const line of input.split("\n")) {
    if (line.trim() === "") continue;
    const [tbl, col, enc] = line.split("\t");
    if (tbl === undefined || col === undefined || enc === undefined) {
      throw new Error(
        `gly373_query_2b_malformed_input_line: expected 3 tab-separated fields`,
      );
    }
    rows.push({ tbl, col, enc });
  }
  return rows;
}

async function main(): Promise<void> {
  const chunks: Buffer[] = [];
  for await (const chunk of process.stdin) {
    chunks.push(Buffer.from(chunk as Buffer));
  }
  const report = auditExportedKeys(
    parseTsv(Buffer.concat(chunks).toString("utf8")),
  );
  // An EMPTY export is a legitimate result on an empty or newly-provisioned store, and is attached
  // to the manifest as such; what the manifest establishes is that the export was UNFILTERED.
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
  // Exit ZERO even with suspects: this check is NON-BLOCKING by ruling, and an exit code that
  // failed a pipeline would quietly turn a reporting obligation into a gate.
  process.exitCode = 0;
}

// This module is an ENTRYPOINT, invoked as `npx tsx jobs/gly373-key-audit-2b.ts`, and follows the
// same unconditional-`main()` shape as `jobs/reclaim-entrypoint.ts`. An `import.meta`-based guard
// is not available here: `tsconfig.executables.json` builds to CommonJS, where `import.meta` is a
// compile error (TS1470). The pure functions above are exported so a test can drive them without
// running `main()`.
void main();
