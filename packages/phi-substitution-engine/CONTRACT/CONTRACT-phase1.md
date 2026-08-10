# Frozen contract — Phase 1, Phileas-aware

**Status:** architecture-frozen for spark implementation

**Package:** `gbs-tools-and-resources/packages/phi-substitution-engine`

**Published artifact:** private GitHub Package using the already established Glass Box package-release pattern; the final npm scope is a repository release concern, not a reason to duplicate source.

**Compute:** Azure Container Apps environment `cae-gbs-wp`; zero GCP.

## 1. Relationship to Stream J and GLY-330

This is not a new plan alongside Stream J. `ADR-001-phileas-vs-greenfield.md` is Stream J J1's tool-selection ADR. Stream J retains ownership of the L1–L4 data-classification taxonomy, ingress classification, persisted metadata, audit UX, and in-app help. GLY-330 supersedes J1's old deployment/tool assumptions and extends J2 with a mandatory egress transformation and reversal boundary.

Glassy's `backend/src/modules/classification/DataClassificationService` is a product facade over classification results. The shared package is the implementation/security boundary for LLM egress. The facade MUST NOT expose a raw detector client, a raw provider, a reversal map, or a caller-controlled `phi: false` bypass.

## 2. Phase-1 product claim and scope

The only eligible customer claim is:

> **Client identifiers on file are replaced before AI processing.**

Phase 1 protects trusted, schema-tagged case-truth values and their deterministic approved variants. The Phileas-aware detector/redactor port is frozen now so implementation does not hard-bind core to a vendor, but probabilistic free-text coverage is disabled by the phase-1 trusted policy. Turning it on requires the Phase-2 per-class corpus and latency gate; the existence of GLiNER is not claim evidence.

Phase 1 includes all Glassy text LLM-egress surfaces in the registry, not only the existing `AiProvider` callers. Multimodal image egress is a reviewed carve-out because names remain pixels. TTS and non-LLM integrations are separate mitigation tickets, not evidence of substitution.

## 3. Ownership boundary

### 3.1 GBS TypeScript package owns

1. **Trusted matter policy and schema projection**
   - Reads tenant/matter policy from trusted application metadata.
   - Classifies every extraction-schema scalar path as `substitution: true` or `false` with rationale.
   - Never accepts protection mode from provider options or user input.

2. **Matter dictionary compiler**
   - Reads tagged case truth by tenant, matter, active dictionary version, and truth revision.
   - Allocates stable subject/role tokens, expands only allow-listed variants, applies distinctiveness/citation/collision policy, and builds/caches the Aho–Corasick matcher.
   - Owns invalidation and rejects BUILDING, FAILED, stale, or wrong-tenant versions.
   - May prepare a versioned per-matter Phileas policy for service use, but TS output remains authoritative.

3. **Token assignment, escape, reversal, and stream holdback**
   - Owns the `[[Role[_N]]]` grammar, monotonic non-reused assignments, literal token escaping, tenant-scoped encrypted reversal storage, unknown/malformed-token failure, and `M-1` UTF-16 streaming holdback.
   - Reverses only bounded grammar-validated tokens encountered in one provider response.
   - Returns current canonical case truth, including when an old substitution-only alias matched outbound text.

4. **Protected provider orchestration**
   - `ProtectedAiProvider` is the only public Glassy `AiProvider` binding for `generateText`, `generateStream`, and `embedText`.
   - Provider/BAA selection examines original content first. It is fixed before substitution and remains conjunctive with `isProductionSafe` and `CLAUDE_BAA_ENABLED`.
   - Exhaustively projects and rebuilds every text-bearing options field; an unclassified field fails before egress.
   - Traces tokenized request/response only and reverses server-side before display/storage. Embeddings are not reversed.

5. **Audit durability**
   - Emits exactly one logical metadata-only attempt event.
   - Prepares durability before provider egress in the primary store or, on primary outage, the ratified AES-256-GCM local encrypted spool.
   - If both are unavailable, fails closed. Draining is idempotent and does not publish PREPARED as a second event.

6. **N7 enforcement contracts**
   - Architecture/import test, provider-host egress lint, deploy network identity/policy, and checked-in surface-registry drift test.
   - Product repositories implement these gates; the framework-free package supplies types, fixtures, and contract oracles.

### 3.2 Phileas 4.2 sidecar owns

1. Local GLiNER/ONNX entity inference, built-in rule/dictionary/census filters, checksum validators, and their model/filter versions.
2. Phileas policy preparation, shared-dictionary internals, filter concurrency, and the filtering/redaction engine.
3. Applying an explicit span replacement plan or Phileas-owned FPE/redaction where policy calls for it.
4. Reporting typed spans, class labels, confidence, offset encoding, artifact identity, and counts to the adapter without request excerpts in logs.
5. JVM/model health, readiness, concurrency, memory, and bounded request handling.

Phileas does **not** own tenant authorization, stable matter subject identity, the permanent token map, canonical reversal, provider routing, browser streaming, audit N3, the spool, or N7.

### 3.3 Adapter boundary

Core depends on `DetectorRedactorPort`, never on Phileas classes, Philter wire DTOs, Azure SDKs, HTTP clients, or ONNX types.

- `PhileasServiceAdapter` translates the port to the internal HTTP service and pins service, engine, model, and prepared-policy versions.
- `AzureLanguagePiiAdapter` implements the same port. It is eligible only after independently passing the same per-class, offset, BAA/residency, no-body-logging, and latency gates.
- Phase 1 sets `detectorRequirement: DISABLED_PHASE_1`; the core must not call either adapter for a customer claim.
- Phase 2 may require the port. Primary and fallback share one deadline; both unavailable means fail closed.
- Dictionary matches always override overlapping detector spans. Invalid service offsets fail closed; the adapter never clamps, guesses, or silently drops them.
- The sidecar receives no complete reversal map. An explicit replacement plan contains only current-segment spans and the non-secret tokens already assigned for those spans.

## 4. Normative flow

### 4.1 Non-stream generation

1. Require authenticated tenant/matter/actor/operation/attempt context.
2. Load trusted matter policy and active READY dictionary version.
3. Run original-content PHI routing and provider production-safety gates; pin the raw provider decision.
4. Project all text-bearing provider options to unique `TextSegment` paths.
5. Escape reserved token-shaped source text.
6. Run the ready TS dictionary matcher and C1–C8 resolver.
7. When trusted policy requires the detection belt, call the detector/redactor port within its one deadline, normalize offsets, give dictionary spans precedence, and allocate operation tokens for detector-only spans.
8. Substitute all segments and construct a non-serializable reversal capability containing references only.
9. Durably prepare one counts/IDs-only audit record in primary storage or encrypted spool.
10. Trace tokenized input and invoke the provider exactly once with rebuilt tokenized options.
11. Trace tokenized output, atomically reverse it through bounded tenant/matter/version lookups, finalize audit, and return authorized display text.
12. On any precondition failure, invoke the provider zero times and finalize/record a visible fixed-code failed-closed result.

### 4.2 Streaming generation

Steps 1–10 are identical. Raw chunks never reach SSE/WebSocket/browser code. The reverse stream retains at least `M-1` UTF-16 code units, never splits a surrogate pair, validates every token-like sequence, and emits only safe reversed prefixes. An unknown, malformed, nested, overlong, or terminal partial token aborts before the unsafe suffix is displayed and finalizes `reversal_failed`.

### 4.3 Embedding

Steps 1–10 apply to the embedding text and any other text-bearing embedding options. Only tokenized text is vectorized or traced. There is no output reversal. Provider choice and existing production-safety gates still use original content.

## 5. Invariants — frozen release registry

All IDs below are release gates. A change may not weaken one without principal and security approval plus an updated named mutation and oracle.

| ID | Frozen requirement | Primary owners |
|---|---|---|
| N1 | No generation, streaming, embedding, graph extraction, SDK client, raw fetch, or model handle reaches an AI provider outside the protected boundary. | wrapper + N7 product gates |
| N2 | Content observability occurs after substitution and before reversal. Maps, variants, source values, and raw pre-substitution content never enter trace, error, job, provider metadata, or shared cache payloads. | safe trace + serializers |
| N3 | Every attempted AI call creates exactly one metadata-only terminal audit event; a durable PREPARED record exists in primary store or encrypted spool before provider egress. | audit emitter/spool |
| N4 | Missing policy/context, unavailable/unready dictionary, required-detector failure, ambiguity, invalid offsets, unclassified text field, or simultaneous audit-store/spool outage fails visibly before provider invocation. Primary audit outage alone proceeds through the spool. | orchestration |
| N5 | Known tokens reverse to current canonical values before display/storage; unknown/malformed tokens fail visibly and no raw provider chunk is displayed. | tokens/reversal |
| N6 | Claims are limited to passing evidence. Phase-1 text is exactly the sentence in §2; images are explicitly outside it. | claims registry |
| N7 | Every LLM egress site is engine-covered or a live, reviewed carve-out; unregistered, stale, or directly constructed egress fails CI/runtime policy. | four enforcement layers |
| L1 | Token identity is stable by tenant+matter+subject+role across versions and never coalesced by text alone. | token assignment |
| L2 | Tagged truth writes atomically advance version/outbox; no old READY version serves while the active version builds. | product persistence adapter |
| L3 | Unicode boundaries, deterministic normalization/original offsets, C1–C8, leftmost-longest, class precedence, and ambiguity quarantine are fixed policy. | dictionary/collision |
| L4 | Streaming reversal is chunk-independent with `M-1` UTF-16 holdback and validated terminal flush. | reverse stream |
| L5 | Provider option traversal is exhaustive and fail-closed for new/unclassified text-bearing fields. | options projector |
| L6 | Reserved token-shaped source text is escaped into a non-reversible literal namespace before matching. | token escaper |
| L7 | Detector eligibility is per class and pinned to exact model/recognizer/config identity; averages cannot hide a weak class. | eval/release manifest |
| L8 | Tenant ID is present in policy, prepared-policy, dictionary, cache, token, and reversal keys/queries. | all persistence/cache adapters |
| L9 | Warm dictionary is <5 ms p50/<20 ms p99; belt is <100 ms P95 and ≤100 ms P99 at ≤32 KiB. Larger text is pre-scanned before egress. | perf gate |
| L10 | Variants are deterministic and allow-listed; no nickname/fuzzy name, ambiguous date, partial email, bare extension, or lossy identifier is invented. | expanders |
| L11 | BAA routing uses original content before substitution; `isProductionSafe` and `CLAUDE_BAA_ENABLED` remain conjunctive. | provider router/wrapper |
| L12 | Dictionary identity wins overlaps; detector offsets validate against original text; detector-only replacements use the same protected reversal boundary. | detector adapter/collision |

## 6. Ratified persistence and retention decisions

- Matter reversal mappings persist under normal matter retention and tenant-scoped envelope encryption.
- Detector-only operation mappings expire after 24 hours and are non-retryable after expiry.
- Authorized stored notes and case truth contain real values. AI output is reversed server-side before display or authorized derived-truth storage.
- Prior corrected tagged values remain encrypted substitution-only aliases until matter retention ends and reverse to the current canonical value.
- Ambiguous known values fail closed and require staff to add a distinctive approved alias.
- Interactive failure is visible plus manual retry; jobs use bounded backoff then operator hold.
- Primary audit-store outage writes the counts/IDs-only record to encrypted local spool and proceeds. Primary plus spool outage fails closed.
- In Azure Container Apps, “local spool” means an application-local append/drain protocol on a mounted durable Azure storage volume, not disposable container scratch. A PREPARED append succeeds only after authenticated encryption, atomic publication, and durable flush. Replica loss or scale-in must not erase an acknowledged record.

## 7. Error and type boundary

Allowed failure codes are declared in `core/contracts.ts`. Errors contain only the operation ID and fixed safe metadata. They never contain input text, matched text, tokens paired with values, variants, excerpts, offsets, detector response bodies, policy terms, or encryption material.

`TokenizedText`, `DisplayText`, IDs, versions, tokens, ciphertext, and offsets are branded. Branding is not an authorization mechanism; trusted adapters validate and construct brands. Content traces accept only `TokenizedText`. The browser accepts only server-produced `DisplayText`.

`ReversalHandle.toJSON()` throws. It contains tenant, matter, version, operation, attempt, and an in-process non-serializable capability; it never contains a map. `ReversalStore` exposes only a bounded `resolveEncounteredTokens` query. No list-all API is allowed.

## 8. Phileas prepared-policy constraints

If case-truth terms are injected into Phileas for detection assistance:

1. the prepared-policy identity includes tenant ID, matter ID, dictionary version, schema version, engine version, and a non-value digest;
2. the policy name alone is never a cache key;
3. shared dictionaries contain only globally approved non-customer lexicons, never matter values;
4. exact matching is used for known values; Phileas fuzzy dictionary mode is forbidden for Phase 1 under L10;
5. policy request/response bodies are not logged and are not written to shared caches;
6. invalidation evicts the exact prior matter/version policy after the tagged write commits;
7. TS collision output remains authoritative, even if Phileas returns a different overlap set;
8. no FPE key/tweak crosses the TS/JVM wire in request payloads; secrets are service-side key references.

## 9. Four N7 enforcement layers

1. **Architecture test:** only the security module may import/bind raw adapters, SDK constructors, raw model handles, or the detector sidecar client. Exactly one public Glassy `AiProvider` binding exists.
2. **Egress lint:** denylisted provider/OCR/vision hosts and direct SDK construction are checked across the product tree. An approved protected-module allow-list is exact and minimal.
3. **Network policy/service identity:** provider endpoints are reachable only from the protected AI service identity in `cae-gbs-wp`. The Phileas sidecar has internal-only ingress and no provider/GCP egress.
4. **Surface registry drift:** every registry file/symbol exists and is exactly one of engine-covered or reviewed carve-out. Discovery of an unregistered call site, or deletion/rename of a registered symbol without registry change, fails CI.

These gates are product repository responsibilities and must run in the same release evidence as the shared package tests.

## 10. Named-mutation completion rule

The `.test.ts` files in `tests/` are Sol-authored frozen oracles. `implementation-under-test.ts` is the sole wiring seam. Spark implementers may replace loaders with real constructors/adapters but MUST NOT weaken case IDs, mutation IDs, fixtures, assertions, canaries, or expected safe outcomes.

A mutation is killed only if its named test fails for the intended oracle. Compilation failures count only for explicit architecture/build mutations. Phase 1 requires:

- every N1–N7 and L1–L12 mutation in the source specification;
- the three independent N7 mutations;
- original-content BAA routing under L11;
- four encrypted-spool mutations;
- Phileas port isolation, prepared-policy tenant/version isolation, invalid offset rejection, and phase-1 detector-disabled behavior.

PR runs affected unit/contract mutations; nightly runs the full named matrix and streaming partitions; the release candidate adds production-like ACA latency, sidecar readiness, network/body-logging, artifact-digest, claims, and package-provenance gates.

## 11. Done means

Phase 1 is complete only when all Glassy engine-covered registry rows traverse the wrapper or an equivalent protected adapter, the four N7 layers are green, known-value leakage is zero, reversal/chunk partition accuracy is 100%, the audit spool mutations are killed, exact customer copy is eligible, package and sidecar artifact identities match the evidence manifest, and rollback disables protected AI or returns to the last gated engine combination without restoring a raw provider.
