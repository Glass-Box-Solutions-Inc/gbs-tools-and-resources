# @glass-box-solutions-inc/phi-substitution-engine

Reversible PHI/PII substitution at the AI-egress chokepoint. A shared, framework-free TypeScript engine that replaces trusted client identifiers with opaque tokens **before** any text reaches an LLM provider, and restores them **after** — so the model works over `[[Claimant]]`, never `Alice Smith`.

> **Ticket:** GLY-330 · **Status:** Phase 1 (architecture-frozen contract in [`CONTRACT/`](CONTRACT/))

## The claim it enforces

Phase 1 supports exactly one customer-facing claim:

> **Client identifiers on file are replaced before AI processing.**

It protects trusted, **schema-tagged case-truth values** (and their deterministic, allow-listed variants) for a tenant/matter. Probabilistic free-text detection (the Phileas/GLiNER belt) is frozen behind an adapter but **disabled** under the Phase-1 policy; enabling it is a Phase-2 decision gated on a per-class corpus and latency budget. The engine never accepts a "protection off" flag from provider options or user input.

## How it works

Every LLM-egress call flows through one protected boundary:

1. **Substitute** — text-bearing provider options are projected to segments; reserved token-shaped source text is escaped; the ready per-matter dictionary (Aho–Corasick matcher + C1–C8 collision policy) replaces tagged identifiers with stable `[[Role[_N]]]` tokens. An unclassified text field **fails before egress**.
2. **Audit** — exactly one metadata-only (counts/IDs) audit record is durably prepared **before** the provider is invoked — in the primary store, or an AES-256-GCM encrypted local spool on primary outage. If neither is durable, it fails closed.
3. **Egress** — only tokenized text is sent to the provider (and only tokenized text is traced). Provider/BAA routing is decided from the original content and pinned before substitution.
4. **Reverse** — the tokenized response is atomically reversed through bounded, tenant/matter/version-scoped lookups back to current canonical values before display or storage. Streaming reversal holds back `M-1` UTF-16 units, never splits a token or surrogate pair, and aborts before an unknown/malformed token's unsafe suffix can reach the browser. Embeddings are not reversed.

## Fail-closed invariants (frozen release gates)

| ID | Guarantee |
|----|-----------|
| **N1** | No generation/streaming/embedding/SDK/raw-fetch egress reaches a provider outside the protected boundary. |
| **N2** | Content is observable only *after* substitution and *before* reversal; maps, variants, source values, and raw pre-substitution content never enter a trace, error, job, provider metadata, or shared cache. |
| **N3** | Every attempted call emits exactly one metadata-only terminal audit event, with a durable PREPARED record before egress. |
| **N4** | Missing policy/context, an unready dictionary, ambiguity, invalid offsets, an unclassified field, or a simultaneous audit+spool outage **fails visibly before the provider is called**. |
| **N5** | Known tokens reverse to current canonical values; unknown/malformed tokens fail visibly and no raw chunk is displayed. |
| **N6** | Claims are limited to passing evidence (the sentence above; images are explicitly out of scope). |
| **N7** | Every LLM-egress site is engine-covered or a reviewed carve-out; unregistered or directly-constructed egress fails CI/runtime policy. |

These are captured operationally by the engine's `§7/N2` hardening: every value crossing a public API boundary — or returned, thrown, or exposed by an injected port — is snapshotted / shape-validated / grammar-validated at its consumption chokepoint and fails closed to a fixed code. No raw PHI reaches a caller, a trace, an error message, or an audit record.

## Architecture

Framework-free core with vendor/product dependencies behind explicit adapters — **no** provider SDK, HTTP client, Phileas, Azure SDK, Prisma, or tracing dependency in core:

- **Dictionary** — READY-version coordinator, tagged-truth reader, per-matter compiler (variant expansion + subject-scoped tokens + Aho–Corasick), warm cache, and match-time C1–C8 resolution.
- **Collision** — deterministic structured-identifier detection and canonical normalization.
- **Tokens** — `[[Role[_N]]]` grammar, monotonic non-reused assignment store, source-literal escaper, tenant-scoped reversal store, atomic reverser, and the `M-1` holdback reverse stream.
- **Audit** — metadata-only emitter and the AES-256-GCM encrypted spool.
- **Wrapper** — `ProtectedAiProvider`, the only public binding for `generateText` / `generateStream` / `embedText`, with original-content BAA routing.
- **Detector/redactor port** — `PhileasServiceAdapter` / `AzureLanguagePiiAdapter` implement one frozen port (Phase-2; disabled in Phase 1).

## Production composition

`createProductionProtectedAiProvider(...)` wraps the exact caller-owned
`PhiSubstitutionEngine` singleton. The application composition root supplies trusted context and
policy accessors, an exhaustive projector, an original-content BAA router, safe trace, durable audit
primary/spool adapters, and its private provider adapters through the router. The production factory
has no development defaults and never constructs a second engine or fallback provider.

The protected surface is provider-neutral: `generateText` resolves a frozen
`{ display, providerId, model?, usage?, toolCalls? }` envelope and `streamText` resolves the same
completion tail after delivering ordered display chunks. Assistant text, streamed chunks, and every
tool-call argument are reversed inside this package; `TokenizedText` and raw provider objects never
cross the application seam. `providerId` always comes from the pinned original-content routing
decision.

`generateText` and `streamText` accept an optional `AbortSignal`. Interruption is audited as the
distinct `interrupted` terminal and rejects with the fixed `CALL_INTERRUPTED` code. Once interruption
is latched, the engine initiates no further provider egress. Transport cancellation is best-effort for
an already-issued request; caller abort reasons are never traced, audited, or surfaced.

The composition root has two deployment obligations which deliberately do not widen the engine
interface: its documented `engineVersion` must identify the supplied engine, and its
`enginePolicyVersion` must be the RFC-8785/SHA-256 digest of normalized engine mode plus BAA matrix.
Production source must also enforce N7 layer-1 import scanning so development factories cannot create
a second engine outside this boundary.

### Production original-egress authorization

`createProductionProtectedOriginalEgressAuthorizer(...)` is the narrow exception path for original
case identifiers, TTS text, and audio streams sent to an explicitly authorized HTTPS/WSS
destination. Its request and returned capability contain identity and policy metadata only—there is
no field for text, identifiers, audio bytes, or a caller-controlled BAA/allow boolean. The injected
policy must return unexpired evidence exactly matching the destination, protocol, content class, and
`enginePolicyVersion`; otherwise authorization fails closed.

Authorization resolves only after metadata-only audit PREPARE is durable. A given `attemptId` can
receive only one operation-scoped, non-serializable capability. Call `finalize(outcome, failureCode?)`
after the protected operation; duplicate finalization rejects, while a transient terminal-write
failure may be retried because the audit emitter owns durable idempotency. The production factory has
no development or permissive fallback.

### Node support

The supported floor is Node `>=20.19.0`; CI pins Node `20.20.2` and installs with
`engine-strict=true`. Direct Azure dependencies are exactly pinned to the checked-in Node-20-compatible
graph, and CI verifies the complete production **and development** lock closure. Node 22 remains
allowed, not required. Any future dependency upgrade that raises the engine floor requires a separate
compatibility decision rather than a caret-driven lock drift.

## Develop

```bash
npm_config_engine_strict=true npm ci
npm run typecheck   # tsc --noEmit (strict, noUncheckedIndexedAccess)
npm test            # vitest run
```

The suites in [`tests/`](tests/) are frozen oracles partitioned by module (variants, collision, tokens, dictionary, detector port, provider boundary, audit, evaluation claims, N7). The hardening suite adds mutation-proven regression tests. Consumer repositories additionally run the N7 framework/import/DI, provider-host, registry-drift, and Azure deployment-policy checks that a framework-free package cannot prove on its own.

## Contract

The normative source of truth lives in [`CONTRACT/`](CONTRACT/):

- [`CONTRACT-phase1.md`](CONTRACT/CONTRACT-phase1.md) — ownership line, invariants, flow, retention, audit spool, enforcement.
- [`MODULE-DEPENDENCY-GRAPH.md`](CONTRACT/MODULE-DEPENDENCY-GRAPH.md) — module tracks and integration chain.
- [`PACKAGE-PLACEMENT.md`](CONTRACT/PACKAGE-PLACEMENT.md) — monorepo/package/deployment placement.
- [`ADR-001-phileas-vs-greenfield.md`](CONTRACT/ADR-001-phileas-vs-greenfield.md) — tool-selection decision.

Compute target: Azure Container Apps environment `cae-gbs-wp`.
