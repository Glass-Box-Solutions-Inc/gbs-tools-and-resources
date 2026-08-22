/**
 * GLY-373 §3.2.1 — the DETECTOR namespace label.
 *
 * The label is derived ONCE per `substitute()` call, before the segment loop, from exactly five
 * trusted context scalars. It is a one-way SHA-256 digest over a LENGTH-PREFIXED (netstring)
 * preimage, truncated to 64 bits and rendered as 16 lowercase hex characters.
 *
 * THE CLAIM, STATED ONCE AND CORRECTLY: the encoding is INJECTIVE OVER WELL-FORMED STRINGS,
 * ENFORCED AT INGESTION. It is never unqualifiedly injective, and it must never be described as
 * such — that overclaim is exactly what `tokens/durable/keys.ts:25` used to assert.
 *
 * WHY LENGTH PREFIXING IS NORMATIVE, NOT STYLISTIC. A bare separator join — of ANY separator,
 * NUL included — is non-injective: `("a", "b\0c")` and `("a\0b", "c")` produce the identical
 * joined byte string, so two distinct operations under two distinct tenants would derive the
 * identical label and mint colliding tokens. Netstring framing removes that whole family — for
 * NUL-bearing field content included — so the digest is sound even if the ingestion NUL check were
 * ever weakened. It does NOT extend the claim past well-formedness; see below.
 * MUT-18 kills a bare-join preimage; OR-GLY373-10 is its oracle.
 *
 * PRECISE INJECTIVITY CLAIM — INJECTIVE OVER WELL-FORMED STRINGS, ENFORCED AT INGESTION.
 * It is NOT unqualified injectivity, and must never be stated as such. `Buffer.from(s, "utf8")`
 * substitutes U+FFFD for a lone surrogate, so a lone-surrogate string and the corresponding
 * U+FFFD string yield identical bytes AND identical byte lengths, hence identical netstrings —
 * the lossiness happens BEFORE the length is taken, so framing cannot rescue it. Executed on
 * Node v20.20.2: `ns("t-ka","m-ka","op\uD800","1","1")` === `ns("t-ka","m-ka","op�","1","1")`
 * === `74b2c51a28c355a5`. The well-formedness check at every context-id entry point
 * (`assertTrustedContextIdShape`, §3.2.2) is therefore LOAD-BEARING FOR THIS CLAIM ITSELF, not
 * merely defence in depth for the NUL case. MUT-22 is its kill probe.
 *
 * The label is structurally PHI-free: all five inputs are trusted routing scalars, never caller
 * display text, and the derivation is a one-way digest regardless.
 */
import { createHash } from "node:crypto";

/** `field(s) = utf8(decimalLength(utf8(s))) ∥ 0x3A ∥ utf8(s)` — i.e. `"<byteLen>:<bytes>"`. */
const LENGTH_DELIMITER = ":";

/** §3.2.1 / AMB-GLY373-02: 64 bits of digest, rendered as 16 lowercase hex characters. */
export const DETECTOR_NAMESPACE_HEX_LENGTH = 16;

function field(value: string): Buffer {
  const bytes = Buffer.from(value, "utf8");
  return Buffer.concat([
    Buffer.from(`${bytes.length}${LENGTH_DELIMITER}`, "utf8"),
    bytes,
  ]);
}

/**
 * Derives the detector namespace label for one operation attempt.
 *
 * Every field genuinely participates (OR-GLY373-13(b) asserts an exact expected label per
 * single-field variation; MUT-21 drops one field at a time and each application must be killed).
 * `dictionaryVersion` arrives already stringified: it is a branded BIGINT at runtime — a
 * non-`bigint` fixed-fails upstream — so its `toString()` is decimal digits only.
 */
export function deriveDetectorNamespace(
  input: Readonly<{
    tenantId: string;
    matterId: string;
    operationId: string;
    attemptId: string;
    dictionaryVersion: string;
  }>,
): string {
  const preimage = Buffer.concat([
    field(input.tenantId),
    field(input.matterId),
    field(input.operationId),
    field(input.attemptId),
    field(input.dictionaryVersion),
  ]);
  return createHash("sha256")
    .update(preimage)
    .digest("hex")
    .slice(0, DETECTOR_NAMESPACE_HEX_LENGTH);
}
