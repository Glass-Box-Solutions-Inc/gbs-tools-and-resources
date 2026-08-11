# ADR-001 — Ratify Phileas 4.2 as the detector/redactor substrate

- **Status:** Proposed for principal ratification in Stream J / J1
- **Decision owner:** Principal
- **Architecture owner:** Sol
- **Date:** 2026-08-10
- **Applies to:** GLY-330 and Stream J J1/J2
- **Supersedes:** the unratified tool recommendation and GCP deployment assumptions in the 2026-03-05 Stream J plan
- **Does not supersede:** Stream J's L1–L4 classification taxonomy, ingress inventory, classification metadata/UX work, or J3/J4

## Decision

Adopt upstream **Phileas 4.2.0** as the production detector/redactor substrate, packaged with a thin GBS JVM HTTP service and deployed as a multi-container sidecar with the protected TypeScript AI service on **Azure Container Apps environment `cae-gbs-wp`**. Start from a clean upstream 4.2.0 import; do not advance the stale `3.3.0-SNAPSHOT` fork commit-by-commit.

The shared TypeScript package at `gbs-tools-and-resources/packages/phi-substitution-engine` remains the system of record for matter dictionary compilation, stable human-readable token assignment, reserved-token escaping, reversal, the Glassy `ProtectedAiProvider`, metadata-only audit plus encrypted spool, and N7 enforcement contracts. Phileas is accessed only through a detector/redactor port and may be replaced by an independently gated Azure AI Language PII adapter.

This ADR is the **J1 tool-selection ADR** requested by `GOAL-DATA-CLASSIFICATION-AUDIT-UX.md`. GLY-330 does not create a competing roadmap. It narrows and extends J1 as follows:

| Stream J statement | Ratified reconciliation |
|---|---|
| Candidate 1 was “Phileas, Java/Maven” and required evaluation. | Select upstream Phileas 4.2.0, subject to the same corpus and latency gate. |
| Candidate 2 assumed Google DLP and Cloud Run/GCP. | Removed from the deployment decision. All compute is Azure Container Apps; zero GCP. |
| Candidate 3 was Presidio. | Presidio is not the primary. Azure AI Language PII is the replaceable managed fallback behind the port if it passes the same gate. |
| Candidate 4 extended `OutputGuardService`. | Reject as the detection substrate; retain only product compatibility until cutover. |
| J2 proposed `DataClassificationService` in `backend/src/modules/classification/`. | Keep it as Glassy's ingress-classification facade. It consumes engine classification output; it does not own LLM substitution, reversal, or raw-provider access. |
| J2 scans ingress and persists L1–L4 metadata. | Still in Stream J. GLY-330 additionally transforms every LLM egress, reverses display output, and enforces N1–N7. |

## Decision drivers

1. Total LLM-egress coverage and real-time chat must preserve the Stream J target of **less than 100 ms P95**. The newer GLY-330 gate is stricter: detector work is at most 100 ms P99 for the declared 32 KiB interactive envelope.
2. Names found only in text need high recall with low false positives and no external content egress. Phileas 4.2's local GLiNER/ONNX path addresses this directly.
3. Known matter truth needs deterministic, tenant-scoped, subject-aware tokens with perfect server-side reversal. Detection-library pseudonymization is not sufficient.
4. Java must remain operationally isolated from the TypeScript API and independently replaceable.
5. The stale internal fork must not become a long-lived divergent security fork.
6. The principal has fixed the platform: Azure Container Apps `cae-gbs-wp`, zero GCP.

## Verified baseline and source findings

The inspected vendored tree is `/home/vncuser/projects/gbs-tools-and-resources-case-analysis/packages/phileas/`. Its `pom.xml` declares `3.3.0-SNAPSHOT` and compiles with Java release 17; Stream J's “Java 11” description is therefore stale. Ground truth supplied by the principal establishes upstream 4.2.0 at commit 2026-08-04 with local GLiNER via ONNX Runtime, Luhn/MOD11/MOD97 validators, prepared policies, concurrency-safe `FilterService`, and shared dictionaries.

The following conclusions are from the inspected source rather than marketing claims:

### FPE is deterministic pseudonymization, not the N5 reversal system

- `utils/Encryption.java` removes punctuation, encrypts the remaining alphanumeric token with FF3, and reinserts punctuation. It rejects values outside 6–56 characters.
- `StandardFilterStrategy` exposes `FPE_ENCRYPT_REPLACE` and calls only `formatPreservingEncrypt`.
- The vendored source has no format-preserving decrypt operation. The dependency may implement decryption, but Phileas does not expose a reviewed reversal contract here.
- `policy/FPE.java` resolves one key and tweak from literal policy values or environment variables. It does not bind them to tenant, matter, dictionary version, subject, operation, or role.

With an identical key/tweak, FPE can produce a stable format-shaped ciphertext. That is not a human token such as `[[Claimant]]`; it does not map several aliases to one stable subject, restore the current canonical value after a correction, reject unknown generated tokens, or enforce a bounded tenant-scoped lookup. Therefore Phileas FPE **does not satisfy N5, L1, L6, or L8 by itself**. It remains a Phileas-owned optional redaction primitive, not GLY-330's authoritative token scheme.

### “Consistent replacement” is not tenant-scoped coreference identity

- `AbstractFilterStrategy.getAnonymizedToken` supports `DOCUMENT` and `CONTEXT` replacement scopes.
- At `CONTEXT` scope it looks up a replacement by the raw token string.
- `DefaultContextService` is an in-memory `HashMap<String,String>`. The method accepts `filterType` but ignores it; the caller's context name is not part of the key.
- The map is not persistent, tenant-scoped, matter-scoped, dictionary-versioned, subject-aware, or reversible.

This can make repeated identical spellings receive the same random replacement during the lifetime of one context service. It also collapses two different subjects who share a spelling, loses stability after restart unless an external service is supplied, and cannot join `Maria Garcia`, `Garcia, Maria`, and an approved alias by stable subject ID. It therefore **does not satisfy N5 or L1/L8**. The TypeScript token assignment and tenant persistence remain mandatory.

### Policy and dictionary APIs are useful but not authoritative case-truth identity

- `CustomDictionary` accepts in-memory `terms`, files, classification, priority, exact/fuzzy choice, ignored terms, and filter strategies.
- `FilterPolicyLoader` creates multiple custom dictionary filters from policy terms. Exact dictionaries use a Bloom-filter-backed exact membership check; fuzzy dictionaries use Levenshtein matching.
- A strategy belongs to a custom dictionary as a whole. A static replacement is not a first-class per-subject term-to-token map.
- The stale loader has a TODO for custom-dictionary caching. Upstream 4.2's prepared-policy and shared-dictionary APIs reduce repeated policy construction and are the correct high-volume integration path.
- `PlainTextFilterService.apply` applies explicit span replacements from the end of the string, which is useful for a thin service endpoint accepting an already validated replacement plan.

The sidecar can receive a prepared, versioned policy containing a matter's approved terms, and it can return detector spans or apply explicit replacements. The TypeScript dictionary compiler nevertheless remains authoritative for schema projection, deterministic variants, subject ambiguity, citation policy, leftmost-longest precedence, token assignment, and version invalidation. Matter values must never be placed in a shared Phileas dictionary. A prepared policy/dictionary identifier must include tenant, matter, dictionary version, schema version, and engine version, and must be evicted on invalidation.

### Where Phileas does not fit

- **Multimodal images:** text substitution cannot remove a name rendered as pixels. Those rows remain reviewed carve-outs protected by BAA routing and minimum-necessary controls.
- **Audit N3:** Phileas explanations/spans contain text and offsets. They cannot be forwarded as GLY-330 audit. The TS audit serializer emits only opaque IDs, total class counts, versions, latency, outcome, and fixed failure code.
- **Encrypted fail-closed spool:** this is a ratified Glassy availability/durability subsystem. It is outside Phileas.
- **Provider and trace chokepoint:** Phileas does not control Nest bindings, `generateText`/`generateStream`/`embedText`, original-content BAA routing, Langfuse/Sentry ordering, or N7's call-site inventory.
- **Server-side display reversal:** Phileas redaction output is not an operation capability and has no browser boundary.

## Options considered

Estimates are engineering effort, not elapsed calendar time, and include production hardening rather than only a spike. Latency figures are budgets to prove, not measured results. No candidate is production-eligible until the pinned artifact passes the WCCE gate.

### Option 1 — Build on upstream Phileas 4.2 with a TS orchestration package

**Shape.** Multi-container Azure Container App: the protected Nest service calls a JVM sidecar over loopback HTTP/JSON. The sidecar wraps Phileas 4.2 prepared policies, GLiNER detection, validators, and span application. The TS package owns matter truth, tokens, reversal, wrapper, audit/spool, and enforcement.

| Dimension | Assessment |
|---|---|
| Initial build | **10–16 engineer-weeks** through the Phase-1 gate including the ratified spool, product adapters, and N7 enforcement; **4–7 additional weeks** for the Phase-2 corpus, detector tuning, failover, and deploy gate. Phileas reduces detector implementation, not the security wrapper. |
| Chat latency budget | Sidecar transport/serialization **≤5 ms P95**, warm prepared-policy lookup **≤5 ms P95**, Phileas detection/redaction **≤75 ms P95**, TS validation/collision/merge **≤10 ms P95**, total belt **<100 ms P95** and **≤100 ms P99** at ≤32 KiB. Cold model load is a readiness event and cannot serve traffic. |
| Integration | Prefer internal HTTP/JSON over loopback with request body logging disabled, strict size/deadline limits, mTLS/service identity where loopback cannot be guaranteed, and no public ingress. A versioned wire contract is published beside the TS port. |
| Fork strategy | Clean re-fork/import from upstream 4.2.0 plus a small GBS service module: **1–2 weeks** including license/SBOM/model provenance and parity checks. Forward-porting the stale fork is estimated **2–4 weeks** and creates harder-to-audit merge history. |
| Phase-1 collapse | Roughly **15–25%**: reuses span/redaction primitives, entity taxonomy, validators, policies, and test fixtures. It does **not** collapse tagged-field projection, variants, collisions, tokens/reversal, versioning, wrapper, audit/spool, or N7. |
| Phase-2 collapse | Roughly **50–65%**: local GLiNER, 30+ types, checksum validators, prepared policies, concurrency safety, and shared dictionaries replace a new detector runtime/recognizer framework. Corpus construction, threshold proof, WC-specific mappings, offset normalization, fallback, and operations remain. |
| Operational cost | One extra JVM container and ONNX model per protected-app replica. Set explicit CPU/memory reservations, startup/readiness probes, minimum warm replicas, concurrency limits, and a maximum request size. |

**Java-in-TS paths.**

1. **HTTP sidecar — selected.** Existing Philter precedent, independent deployment/lifecycle, easy health/deadline semantics, and acceptable local transport overhead. It also keeps a clean replaceable port for Azure.
2. **gRPC sidecar — not selected initially.** Saves little at ≤32 KiB and adds protobuf/codegen/versioning/health infrastructure. Reconsider only if benchmarks show HTTP serialization consumes more than 10% of the belt budget. Estimated migration: 1–2 weeks after the HTTP contract is stable.
3. **TypeScript port — rejected.** Estimated 8–14 weeks for mechanical translation before parity, followed by ongoing double maintenance of NER/ONNX/tokenization/validator behavior. It discards upstream improvements and creates the largest security drift surface.

### Option 2 — Greenfield TypeScript orchestration plus Presidio

**Shape.** Build the same TS dictionary/token/audit wrapper, but deploy a Python Presidio sidecar and create WC recognizers. Do not use Phileas.

| Dimension | Assessment |
|---|---|
| Initial build | **13–21 engineer-weeks** through Phase 2, plus the 2–4 week spool cost already included in the high end. More custom recognizer/entity mapping and replacement integration than option 1. |
| Chat latency budget | Loopback transport **≤5 ms P95**, Presidio/spaCy/transformer analysis **≤80 ms P95**, TS merge **≤10 ms P95**; total still must be <100 ms P95/≤100 ms P99. This is plausible only with warm models and must be benchmarked. |
| Integration | HTTP sidecar is still preferred. Python becomes a second non-TS runtime without reusing the already Production-marked internal engine. |
| Update cost | Presidio upgrades and model/recognizer bundles become GBS-owned compatibility work. No stale-fork cleanup, but a new internal recognizer fork is likely. Expect 1–3 weeks per major update/evaluation cycle. |
| Phase-1 collapse | **5–10%**. Presidio supplies detection/anonymization utilities that are mostly phase 2; the deterministic phase-1 contract remains. |
| Phase-2 collapse | **30–45%**. Framework and common recognizers are reused, but WC entity mappings, checksum validation gaps, model selection, concurrency behavior, and policy caching are ours. |

Presidio remains a credible benchmark candidate but offers no decisive benefit over upstream Phileas 4.2 given the verified local GLiNER path and existing Phileas investment.

### Option 3 — Dual-engine hybrid (Phileas plus Presidio)

**Shape.** Use Phileas for structured identifiers/checksums/FPE and Presidio for names, or run both and merge/consensus-score spans. The TS package still owns tokens and reversal.

| Dimension | Assessment |
|---|---|
| Initial build | **17–27 engineer-weeks** through Phase 2. Requires two runtimes, entity-taxonomy reconciliation, duplicate/overlap semantics, two artifact manifests, and two failure models. |
| Chat latency budget | Sequential analysis is unlikely to meet 100 ms. Parallel analysis still pays the slower tail and 5–15 ms merge/normalization overhead. Each engine would need a roughly 70 ms P95 ceiling. |
| Integration | Two HTTP sidecars or an aggregator; gRPC does not remove model compute. A TS port remains unjustified. |
| Update cost | Highest. Every Phileas or Presidio/model update reruns compatibility, merge, corpus, and operational gates. Expect 2–5 weeks per major dual-engine refresh. |
| Phase-1 collapse | **15–25%**, no better than option 1. |
| Phase-2 collapse | Superficially **65–75%** of detector implementation, but much of that is replaced by merge, tuning, and operations; net schedule benefit is doubtful. |

This option is warranted only if the immutable corpus proves a material per-class gap that one engine cannot close alone. It should not be the starting architecture.

## HTTP sidecar contract and deployment guardrails

The thin service is a GBS adapter, not a general public Philter endpoint.

- Internal endpoints: readiness, prepared-policy load/evict, detect, and apply an explicit replacement plan.
- Every request carries opaque operation/attempt IDs and a pinned engine/model/prepared-policy identity. Tenant/matter IDs are used for authorization/cache isolation and are not logged.
- Response spans declare offset encoding and exact model/policy versions. The TS adapter validates them against the original UTF-16 text; it never clamps or guesses.
- The service never returns an internal context map, policy terms, FPE key/tweak, or raw-value diagnostics.
- HTTP body access logs, APM body capture, exception excerpts, heap dumps, and request sampling are disabled.
- The sidecar has no public ingress and no GCP route. All images and compute are promoted into `cae-gbs-wp`.
- The ratified encrypted audit spool is mounted as durable Azure-backed storage; ACA container scratch does not count as durable preparation. Writes are envelope-encrypted, atomically published, and durably flushed before provider egress.
- A cold/unready GLiNER model fails readiness. Protected calls fail closed or use only an independently eligible Azure fallback within the one total deadline.
- The TypeScript package never sends a complete reversal map. For explicit redaction it sends only the spans and already assigned replacement tokens for the current segment.

## Consequences

### Positive

- Reuses a Production-marked, Apache-licensed engine and upstream's current local NER/validator/policy work.
- Keeps raw content inside the Azure Container App for the primary path.
- Avoids a Java-to-TypeScript rewrite while preserving a replaceable boundary.
- Makes Stream J's classification facade and GLY-330's egress transformer complementary rather than competing services.
- Limits the GBS fork to service/wire/security glue and enables upstream refreshes.

### Negative and accepted

- A JVM/ONNX container increases memory, startup time, SBOM, patching, and autoscaling complexity.
- Phase 1 is not “mostly done” by Phileas; its hardest identity/reversal/audit/enforcement work remains.
- The <100 ms target is unproven until production-like benchmark evidence exists.
- The sidecar wire contract becomes a security-sensitive versioned API.

## Rejected shortcuts

- Do not expose Phileas's in-memory context map as the reversal map.
- Do not use FPE ciphertext as N5 display tokens.
- Do not key prepared policies or dictionaries by policy name alone.
- Do not place per-matter values in a shared dictionary.
- Do not call the JVM with a child process per request.
- Do not route to GCP services.
- Do not treat Azure fallback eligibility as inherited from Phileas eligibility; each artifact passes independently.
- Do not substitute before Glassy's original-content BAA routing decision.

## Ratification gates

J1 is ratified when the principal approves this ADR and the following evidence is attached:

1. upstream 4.2.0 source/model/license/SBOM digest and the minimal GBS patch inventory;
2. warm/cold sidecar benchmark at declared ACA CPU/memory and payload buckets;
3. immutable WCCE per-class accuracy/offset report for Phileas and Azure fallback;
4. proof of zero body logging/public ingress/GCP dependencies;
5. prepared-policy tenant/matter/version isolation and eviction test;
6. a consumer contract run proving the TypeScript port can swap Phileas for the fake and Azure adapter without core changes.

## Recommendation

Build on upstream Phileas 4.2.0 as an Azure Container Apps HTTP sidecar.
Keep the tenant dictionary, stable tokens, reversal, wrapper, audit/spool, and enforcement in TypeScript.
Use a clean upstream re-fork and keep GBS patches limited to the service/security adapter.
Retain Azure AI Language PII only as an independently gated fallback behind the same port.
