# @glass-box-solutions-inc/phi-substitution-engine

## 0.3.0 — GLY-373 namespaced substitution grammar and detection-suppression semantics

Risk tier T2 (PHI egress chokepoint, reversal-key correctness, public policy type change,
dual-consumer repin). Baseline `8105730` (0.2.0).

### Breaking

The release-notes claim mandated verbatim by SPEC-GLY373 §3.1, on one line so it is greppable and
so an oracle can assert it exactly:

`ParsedToken.valid` gains a required `namespace: string | null`; `TokenGrammar.format` gains an optional `namespace` parameter. Breaking for external `TokenGrammar` implementers and for exhaustive `ParsedToken` consumers; no change required in either pinned consumer.

`namespace` is deliberately **required**, not optional: optionality would let a consumer or an
internal reader silently ignore the field and treat a namespaced detector token as an authority
token, which is the exact invariant the field exists to carry. Verified source-compatible with both
pinned consumers' observed usage — neither Glassy `5bbf3ac` nor Adjudica `7814e57` implements
`TokenGrammar` or constructs/destructures `ParsedToken`; both consume the engine only through the
root factories and the policy/option types.

### Added

- **Detector namespace label** (§3.2.1), a 64-bit SHA-256 digest over a **length-prefixed
  (netstring)** preimage of exactly five trusted context scalars. The encoding is **injective over
  well-formed strings, enforced at ingestion** — never unqualifiedly injective: `Buffer.from(s,
  "utf8")` substitutes U+FFFD for a lone surrogate *before* the length is taken, so framing alone
  cannot separate a lone-surrogate id from its U+FFFD twin. The well-formedness check at every
  context-id entry point is what makes the claim hold, not the framing.
- **Namespaced detector grammar** (§3.1). Inner text gains one alternative: `D~<16 lowercase hex>~`
  before the role. A detector-minted token (`[[D~3f9a1c7204b8e561~SSN_2]]`) is now *structurally*
  incapable of equalling an authority-minted token under the operation-blind reversal key, with no
  key-shape change. Authority tokens (`[[Claimant]]`, `[[SSN_2]]`) are **byte-identical to 0.2.0**,
  so no existing reversal row, embedding, or consumer assertion is invalidated. A new malformed
  reason `BAD_NAMESPACE` is reported for a bad label, a missing or extra `~`, or an empty remainder,
  and the namespace layer fully validates **before** delegating to the role/sequence rules.
- **`detectorRequirement` gains two members**: the new canonical `DETERMINISTIC_STRUCTURED_ONLY`
  and the new hard-suppression `STRUCTURED_DETECTION_OFF`. `REQUIRED` is unchanged.

### Changed — behaviour, not just types

- **`DISABLED_PHASE_1` is now a deprecated alias** of `DETERMINISTIC_STRUCTURED_ONLY`, retained for
  pin compatibility and to be removed in a later major. **The alias preserves the type, not the
  behaviour.** A consumer that leaves its existing literal untouched *will* observe different
  results: baseline injected-mode detection fixed-failed, whereas the alias now succeeds with
  namespaced substitution, and default-mode detector token text changes from `[[SSN_2]]` to
  `[[D~<ns>~SSN_2]]`.
- **Deterministic structured detection is now policy-governed and exhaustively fail-closed.** It
  runs under `DETERMINISTIC_STRUCTURED_ONLY` and its alias, is *not invoked at all* under
  `STRUCTURED_DETECTION_OFF` (suppression is non-invocation, never filtering), and any unrecognised
  value fails closed with `MISSING_TRUSTED_POLICY` before any dictionary work. At 0.2.0 the field
  validated shape and gated the ML belt but suppressed nothing.
- **The injected-mode fixed-fail is deleted**, replaced by the namespaced allocation and nothing
  else. Detector tokens are namespaced in **both** injected and default mode.
- **Trusted-context routing ids are now validated at all three entry points** — `substitute`, the
  atomic `reverse()` handle, and the `createReverseStream` handle — and rejected when NUL-bearing or
  ill-formed UTF-16, with a fixed, PHI-free frozen `PhiEngineError` carrying code
  `MISSING_TRUSTED_CONTEXT` and no caller data. This closes a **pre-existing cross-tenant aliasing
  defect**: the NUL joins that scope reversal keys were documented as injective but nothing enforced
  it, so `("a", "b\0c")` and `("a\0b", "c")` produced one reversal key for two distinct tenants.
  On the two reversal paths this is **new behaviour**: they previously threw
  `Error("reversal_failed")` / `ReversalFailedError`, and `createReverseStream` had no structural
  validation at all. Guard path only; legitimate reversal failures keep their current class.
- **A divergent same-attempt replay now fails closed.** A write whose `(attemptId, token)`
  idempotency scope already exists and whose canonical *differs* is rejected with
  `AMBIGUOUS_KNOWN_IDENTIFIER` and `safeDetails.conflict = "reversal-key-canonical-mismatch"`,
  instead of silently keeping the first canonical. The baseline's silence was a cross-value PHI
  disclosure within a tenant: the caller believed its second value was tokenized while the token
  reversed to the first value's data. Cross-attempt updates and same-canonical replays are
  unaffected. **Caller contract: one context tuple = one invocation** — mint a fresh `attemptId` per
  `substitute()` call; reuse is now rejected, not merged.
- **The audit event gains `failureDetail`**, a fixed PHI-free triage discriminator with its own
  exact value allow-list, so a reversal-key conflict is distinguishable from dictionary ambiguity in
  the durable record (both surface as `AMBIGUOUS_KNOWN_IDENTIFIER`).

### Unchanged

The root runtime surface is exactly the 0.2.0 set — four factories plus the error surface — and
`exports` remains exactly `.` and `./package.json`. No new `PhiEngineFailureCode` member, no new
error class, no reversal key-shape change, no schema migration, and no new runtime or deep export.
