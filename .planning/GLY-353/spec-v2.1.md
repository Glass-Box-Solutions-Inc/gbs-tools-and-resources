**Model: GPT-5.6-sol**

# GLY-353 specification v2.1 — production protected-AI composition factory

## 1. Status, authority, and scope

1. This is a **T2 specification only**. It authorizes no implementation, commit, push, release, or deployment in this round.
2. The implementation base is `main` at `1abf86a`; the implementation lane is `GLY-353-production-factory`.
3. GLY-353 is the package-side prerequisite for the Glassy M3 integration (GLY-338 slice B2), but this package MUST NOT import Glassy types, source files, runtime values, or dependencies. The production seam is expressed entirely in phi-substitution-engine terms.
4. Existing CONTRACT invariants and frozen tests remain authoritative. No test, allow-list, failure gate, durability requirement, routing rule, reversal rule, or capability boundary may be weakened.
5. The change is expand-only: add one production factory, production-only type seams, a protected result envelope, one internal sink-streaming path, cancellation, two evidence-version claims, compatibility documentation, and oracles. Do not remove, rename, or incompatibly overload either development factory. Do not add a package subpath export or expose a concrete engine, raw-provider implementation, audit emitter, spool, reversal store, crypto primitive, policy object, or router at the runtime root.
6. The factory is a security composition boundary. A value described below as PHI-free MUST be constructed from validated structural metadata or fully reversed display text; it MUST NOT merely be asserted or cast PHI-free.
7. `MUST`, `MUST NOT`, `SHOULD`, and `MAY` are normative.

## 2. Current state and problem statement

1. `createSubstitutionEngine()` is a development API returning a `DevSubstitutionEngine` bundle, not a bare engine.
2. `createProtectedAiProvider()` calls `buildDevEngineParts()` and constructs an independent engine, so a product cannot wrap the exact singleton engine it owns.
3. The development provider factory hard-wires development context, policy, projector, BAA route, trace, audit primary/spool, and echo-provider defaults. A raw-provider option alone is not production composition.
4. The legacy `AiProvider` shape mirrors one historical consumer but its text-only result and collected-stream contracts are not a stable cross-product contract. They cannot carry provider-neutral model, usage, or tool-call completion data.
5. A tool call is itself provider egress. Returning raw/tokenized tool arguments to a product adapter would bypass the reversal guarantee even if assistant display text were reversed.
6. Existing calls have no application cancellation seam. Sink rejection is a failure path, not a substitute for intentional interruption, and transport cancellation cannot be inferred from a rejected sink.
7. `AzureEgressPolicyEvidence` binds identity and image/deployment digests but not either the attestor's egress posture revision or the consumer's normalized engine-policy configuration.
8. The package declares Node `>=20`, while caret resolution can select later Azure SDK releases with a higher engine floor. At this base the lock resolves `@azure/identity@4.13.1`, `@azure/keyvault-keys@4.10.2`, and `@azure/storage-file-share@12.31.0`; all declare Node `>=20.0.0`. This is resolution drift, not demonstrated incompatibility in those versions.

## 3. Goals and explicit non-goals

### 3.1 Goals

1. Wrap the **exact caller-supplied `PhiSubstitutionEngine` singleton** and never construct a second engine inside the production factory.
2. Require production context, policy, projector, original-content router, trace, audit primary, encrypted spool, embedding projection, engine-version, and engine-policy-version inputs. No development fallback is legal.
3. Return a frozen null-prototype, provider-agnostic protected call facade for text, incremental display streaming, and embeddings.
4. Return a PHI-free text result envelope; reverse both assistant text and every tool-call argument in-package before the application adapter sees them.
5. Support caller interruption distinctly from failure, with an engine-boundary no-further-egress guarantee and best-effort transport cancellation.
6. Preserve original-content routing, exhaustive projection, substitution, durable audit PREPARE, exactly-one pinned raw call, tokenized-only tracing/egress, reversal before application exposure, and exactly-one terminal audit event.
7. Bind signed Azure evidence to both `egressPolicyVersion` and `enginePolicyVersion`, together with identity and image/deployment digest, under one normative canonical digest.
8. Preserve Node 20 by freezing proven-compatible Azure versions and enforcing the entire production and development lock closure in CI.

### 3.2 Non-goals

1. No Glassy import/type/dependency and no SDK-specific product result, tool, or stream type.
2. No provider construction, credential loading, database connection, environment read, or network call at import or factory construction.
3. No new production engine builder. Engine lifetime/singleton ownership stays with the application composition root.
4. No behavior change to either development factory, its defaults, bundle results, echo path, or public facades.
5. No public concrete wrapper, engine, audit emitter, serializer, or adapter implementation export.
6. No M3 verifier or M4 signer implementation; this lane defines the signed-claim shape and canonicalization they MUST share.
7. No hard promise that an already-issued network request is recalled. Cancellation at the provider transport is best-effort; the enforceable guarantee is that this package initiates no further provider egress after interruption is latched.
8. No conversion of sink rejection into interruption. Sink rejection remains the existing fixed-code failure path.
9. No runtime production guard on either development factory. The reviewed second-engine containment decision is delegated to the consumer's N7 layer-1 import scan (§4.2).
10. No Node-22-only API and no forced consumer bump while the pinned graph supports Node 20.

## 4. Constitutional decisions and invariants

### 4.1 Separate production entry point

The additive root factory is `createProductionProtectedAiProvider`. It is not an overload of either development factory. Its required dependency object prevents omission from selecting a development default.

### 4.2 Singleton ownership and reviewed containment boundary

1. `dependencies.engine` is required and serves every substitution, text reversal, tool-argument reversal, and reverse-stream creation.
2. The production factory MUST NOT call `buildDevEngineParts`, `createSubstitutionEngine`, `createProtectedAiProvider`, `new ComposedSubstitutionEngine`, or any engine-producing callback.
3. The factory does not return the engine; the application already owns it.
4. `engineVersion` is a required PHI-free composition identifier for minimal pre-substitution audit records. Matching it to the supplied engine is a documented **caller obligation**, not an interface-level invariant. The engine interface MUST NOT be widened merely to introspect a version.
5. The package cannot prevent a consumer from importing a development factory elsewhere and constructing another engine. The reviewed containment decision is to delegate that prohibition to the consumer's **N7 layer-1 import scan**, which MUST reject production source importing or calling development factories. GLY-353 adds no dev-factory production-mode guard.

### 4.3 No production defaults

Every security-sensitive dependency in §5.4 is required. Production construction MUST NOT create an in-memory reversal store, development context/policy, echo provider, collecting trace, in-memory audit store, fixed spool key, fixed BAA decision, provider fallback, or engine-policy-version fallback. `clock` is the only optional dependency and retains the safe UTC fallback.

### 4.4 Capability-tight result

The result is a frozen null-prototype object with exactly `embedText`, `generateText`, and `streamText`. It has no constructor, prototype, data properties, or reference to engine, dependencies, provider, original options, context, policy, audit, trace, reversal handle, spool, or router. Methods are closure-bound.

### 4.5 PHI-free result boundary

1. `generateText` returns a new exact envelope `{ display, providerId, model?, usage?, toolCalls? }`.
2. `display` is the result of `engine.reverse`; it is never the provider's tokenized text.
3. `providerId` is copied from the pinned routing decision, never accepted from the provider response.
4. Every `toolCalls[i].arguments` is provider-returned tokenized text internally and is independently passed through `engine.reverse(arguments, sameReversalHandle)` before the envelope is constructed. The protected surface exposes `DisplayText` arguments only. One failed or non-string argument reversal fails the whole call closed; no partial envelope is returned.
5. Tool-call `id` and `name`, optional `model`, and usage fields are structural metadata. Boundary code copies only exact allowed fields and validates identifiers/model against `^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$`; usage values MUST be finite, non-negative safe integers. Invalid metadata fails closed with no raw value in error/audit/trace.
6. Unknown provider-result properties are not copied, traced, audited, or returned. No raw response object or provider-owned nested reference crosses the protected seam.
7. The application may adapt the protected envelope to its own type. It never receives `TokenizedText`, a reversal handle, a raw-provider binding, or raw tool arguments. Glassy's tool path is therefore on the protected rail, not a parallel raw rail.

### 4.6 Streaming consistency and completion envelope

1. The wrapper gains one sink-based internal streaming primitive. Legacy `generateStream(options): Promise<ProtectedStreamResult>` delegates to it using a collector, preserving its exact result and behavior.
2. The production sink is invoked only from the reverse-stream safe-output callback. Raw/tokenized chunks never reach it.
3. Before invoking the sink, production boundary code MUST check `typeof safeChunk === "string"`. A non-string value returned through a malicious/cast engine fails closed, calls the sink zero times for that value, aborts the reverse stream, and uses the ordinary failure terminal. This is parity with the existing raw-chunk string check.
4. Sink calls are awaited sequentially, providing ordering and backpressure.
5. Sink rejection uses the existing post-send failure path: abort/latch best-effort, finalize one fixed-code failure terminal, make zero additional provider calls, and reject with a fresh fixed `PhiEngineError` without raw text. It is not recorded as interruption.
6. On provider stream completion, the wrapper ends the reverse stream, reverses every completion tool-call argument with the same handle, finalizes `completed`, and resolves a tail `{ providerId, model?, usage?, toolCalls? }`. The tail uses the same validators and copy rules as `generateText` and contains no `display` field because display chunks were already emitted.
7. Completion resolves only after `stream.end()`, all tool-call arguments are reversed, and terminal finalization succeeds. A first safe chunk is observable before raw completion; production MUST NOT collect all chunks first.

### 4.7 Cancellation and terminal arbitration

1. `generateText` and `streamText` accept an optional caller `AbortSignal`. Each request creates a private `AbortController`; the production raw-provider port always receives its signal.
2. An abort observed after trusted context is available latches a single `interrupted` terminal outcome. `"interrupted"` is added to `PhiAuditOutcome`; it is distinct from `"failed_closed"`, `"reversal_failed"`, `"unknown_after_send"`, and the pre-existing `"cancelled"` value. It MUST NOT be serialized as a failure outcome.
3. The caller-facing promise rejects with a fresh fixed `PhiEngineError("CALL_INTERRUPTED")`; `CALL_INTERRUPTED` is additive to the core fixed failure-code union/error allow-list, but the interruption audit event has `failureCode: null` because interruption is not a failure terminal. **`CALL_INTERRUPTED` MUST NOT be added to `TERMINAL_FAILURE_CODES` in `src/audit/serializer.ts`; only `"interrupted"` is added to `PhiAuditOutcome`.** No abort reason crosses any boundary.
4. If the signal is already aborted on entry, the wrapper obtains trusted context so the attempt can be durably represented, attempts PREPARE, finalizes `interrupted` when the receipt is durable, and invokes route/project/substitution/provider zero times. If this zero-egress PREPARE cannot be durably written, the caller still receives the fixed `CALL_INTERRUPTED`, **not** `AUDIT_DURABILITY_UNAVAILABLE` or another durability failure; no provider egress occurred and the abort remains the authoritative caller outcome. If trusted context itself cannot be obtained, the existing missing-context failure remains authoritative because no trusted attempt identity exists to finalize.
5. If abort is latched before provider invocation, provider invocation is skipped. If abort is latched while one provider call is in flight, the private controller aborts, later raw results/chunks are ignored, reverse-stream state is aborted, and this package initiates no retry, continuation, embedding call, tool call, or other provider egress for that attempt.
6. Transport cancellation is explicitly **best-effort**: a provider or network stack may finish bytes already in flight. The production port MUST accept the signal and SHOULD propagate it to its transport, but this package claims only that no further provider egress is initiated at the engine boundary after the abort latch.
7. Terminal arbitration is a request-local once-latch. The first observed terminal cause wins: caller abort yields `interrupted`; sink rejection, provider rejection, malformed result, reversal rejection, or finalization error yields the corresponding failure path. Later abort/failure/completion events are ignored except for best-effort cleanup and can cause neither a second terminal event nor another provider call.
8. Abort listeners MUST be removed on every terminal path. Late abort after successful terminal finalization is a no-op.

### 4.8 Audit composition

The factory accepts `AuditPrimaryStore` and `EncryptedAuditSpool`, privately creates `DurablePhiAuditEmitter` with the non-injectable `ExactAllowListAuditSerializer`, and shares the safe clock with the wrapper. Primary-unavailable/spool-ready continues; both unavailable fails before provider egress. Interruption uses the same prepared receipt as success/failure. No audit-free production path exists.

### 4.9 Router authority and absence of a fallback raw provider

1. `rawProvider` is **not** a production dependency.
2. `router.selectUsingOriginalContent()` is authoritative and returns the exact private provider capability pinned for the request. The production wrapper invokes only that provider.
3. The currently redundant internal `invokeRaw` obligation MUST NOT force production callers to inject a second/fallback provider. The internal composed-dependency shape is refactored so production raw invocation is satisfied by `prepared.provider`, obtained from the router decision. Legacy development options may retain `invokeRaw` for source compatibility and continue to install it into their fixed router; production never supplies a dummy provider.
4. Router selection occurs once on original options before projection/substitution, and the selected reference is snapshotted request-locally. No other provider owned by the router or dependencies is invoked, including on errors, abort, retry-like conditions, tool calls, or embedding.

## 5. Exact additive public API

### 5.1 Provider-neutral protected envelopes

```ts
export interface ProtectedAiUsage {
  readonly inputTokens?: number;
  readonly outputTokens?: number;
  readonly totalTokens?: number;
}

export interface ProtectedAiToolCall {
  readonly id: string;
  readonly name: string;
  /** Reversed in-package. Never provider/tokenized arguments. */
  readonly arguments: DisplayText;
}

export interface ProtectedAiResultTail {
  /** Authoritative id from the original-content routing decision. */
  readonly providerId: string;
  readonly model?: string;
  readonly usage?: ProtectedAiUsage;
  readonly toolCalls?: readonly ProtectedAiToolCall[];
}

export interface ProtectedAiTextResult extends ProtectedAiResultTail {
  readonly display: DisplayText;
}
```

All returned objects and arrays are fresh, recursively frozen copies. Optional properties are omitted when absent; they are not emitted with `undefined`. `toolCalls` preserves provider order. The envelope has no index signature or metadata escape hatch.

### 5.2 Private-provider type seam

The port is a public **type-only** export so a product can implement an adapter; no provider implementation or instance is exported at runtime.

```ts
export interface ProductionRawToolCall {
  readonly id: string;
  readonly name: string;
  readonly arguments: TokenizedText;
}

export interface ProductionRawResultTail {
  readonly model?: string;
  readonly usage?: ProtectedAiUsage;
  readonly toolCalls?: readonly ProductionRawToolCall[];
}

export interface ProductionRawTextResult extends ProductionRawResultTail {
  readonly text: TokenizedText;
}

export interface ProductionRawProviderPort<GenerateOptions, EmbeddingKind = string> {
  generateText(options: GenerateOptions, signal: AbortSignal): Promise<ProductionRawTextResult>;
  generateStream(
    options: GenerateOptions,
    onChunk: (chunk: TokenizedText) => void | Promise<void>,
    signal: AbortSignal,
  ): Promise<ProductionRawResultTail>;
  embedText(text: TokenizedText, kind: EmbeddingKind): Promise<readonly number[]>;
}
```

The raw seam is private to production composition. `ProductionRawToolCall.arguments` may exist only between the selected adapter and engine wrapper and MUST NOT be forwarded by a product-facing adapter.

### 5.3 Protected call surface

```ts
export type DisplayChunkSink = (chunk: DisplayText) => void | Promise<void>;

export interface ProtectedAiCallSurface<GenerateOptions, EmbeddingKind = string> {
  generateText(options: GenerateOptions, signal?: AbortSignal): Promise<ProtectedAiTextResult>;
  streamText(
    options: GenerateOptions,
    sink: DisplayChunkSink,
    signal?: AbortSignal,
  ): Promise<ProtectedAiResultTail>;
  embedText(text: string, kind: EmbeddingKind): Promise<readonly number[]>;
}
```

Cancellation is deliberately scoped to `generateText` and `streamText` in this lane. Adding an embedding stop handle requires a separate compatibility decision.

### 5.4 Factory dependencies

```ts
export interface CreateProductionProtectedAiProviderOptions<
  GenerateOptions,
  EmbeddingKind = string,
> {
  readonly engine: PhiSubstitutionEngine;
  readonly engineVersion: EngineVersion;
  /** Consumer boot-config digest defined by §7.2; no default or inference. */
  readonly enginePolicyVersion: string;
  readonly context: MatterAiContextAccessor;
  readonly policy: MatterAiPolicyAccessor;
  readonly projector: AiProviderOptionProjector<GenerateOptions>;
  readonly router: OriginalContentProviderRouter<
    GenerateOptions,
    ProductionRawProviderPort<GenerateOptions, EmbeddingKind>
  >;
  readonly safeTrace: SafeAiTrace;
  readonly auditPrimary: AuditPrimaryStore;
  readonly auditSpool: EncryptedAuditSpool;
  readonly embeddingOptionsFactory: (text: string) => GenerateOptions;
  readonly clock?: () => string;
}

export function createProductionProtectedAiProvider<GenerateOptions, EmbeddingKind = string>(
  dependencies: CreateProductionProtectedAiProviderOptions<GenerateOptions, EmbeddingKind>,
): ProtectedAiCallSurface<GenerateOptions, EmbeddingKind>;
```

`enginePolicyVersion` is copied only into PHI-free audit metadata/evidence plumbing expressly authorized for that field; it is not a substitute for `engineVersion`.

### 5.5 Construction behavior

1. Snapshot top-level dependency references exactly once. A throwing getter or missing/non-callable required method causes a fresh `PhiEngineError("PROVIDER_SAFETY_GATE_FAILED")` with no cause or caller details.
2. Construction invokes **no port method** and reads no context/policy. It performs no routing, projection, substitution, audit prepare/finalize/health, trace, provider, spool, clock, environment, filesystem, or network call. Reading and validating dependency references is not a port invocation.
3. The wrapper receives the exact injected engine, projector, router, trace, and private durable audit emitter. There is no raw-provider/fallback argument.
4. Return the §4.4 facade directly, not a development bundle.

## 6. Call protocol and failure boundaries

### 6.1 Normative state/protocol table

| Call/state | Required action | Output | Failure/interruption behavior |
|---|---|---|---|
| construction | snapshot capabilities; compose serializer/emitter; wrap exact engine | frozen facade | invalid composition: fresh fixed error, zero port calls |
| context | `context.require()` once | none | fixed missing-context, zero provider calls; pre-aborted without context cannot be audited |
| pre-abort | if already aborted after context, create durable PREPARE then terminal `interrupted` | none | fixed `CALL_INTERRUPTED`, zero route/provider calls |
| policy | `policy.require(context)` once | none | fixed failure; one failure terminal after context |
| route | inspect original options once and pin exact provider/providerId | none | unsafe/BAA-unsatisfied fails pre-egress; no fallback provider |
| project/substitute | classify all carriers, rebuild tokenized options, call supplied engine | reversal handle | unclassified carrier fails closed |
| audit PREPARE | primary then encrypted spool | internal receipt | both unavailable: zero provider calls |
| abort gate | re-check once-latch immediately before raw call | none | interrupted means zero raw calls |
| raw text | pinned provider once with tokenized options and private signal | internal tokenized result | sanitized rejection; interruption race follows §4.7 |
| text/tool reversal | validate/trace text; reverse display and each tool argument with same handle | fresh result envelope | any bad value/reversal fails whole call; no partial result |
| raw stream chunk | string-validate/trace tokenized chunk and push reverse stream | none | bad chunk aborts/latches failure |
| reversed chunk | string-validate and await display sink | safe chunk | non-string/sink rejection latches failure, never interruption |
| stream completion | `end`; reverse completion tool args; copy tail; finalize terminal | fresh result tail | no tail until every argument is safe and terminal is durable |
| caller abort | latch; abort private controller/reverse stream; ignore late output | no value | terminal `interrupted`; zero new egress after latch |
| embedding | route original, substitute, PREPARE, trace, pinned raw embed | numeric vector | no output reversal; existing failure gates apply |

No call may expose original/tokenized text through errors, metadata, audit, factory results, result envelopes, stream tails, tool calls, or product adapters.

### 6.2 Exact ordering for text

`context → abort check → policy → route(original) → project → substitute → PREPARE → abort gate → trace(tokenized input) → pinned generateText(signal) → abort gate → validate/copy raw result → trace(tokenized text) → reverse text → reverse each tool argument → freeze envelope → finalize completed → return`.

Provider invocation occurs exactly once. Reversal failures after egress use existing post-send semantics. The envelope remains request-local until finalization succeeds.

### 6.3 Exact ordering for streams

`context → abort check → policy → route(original) → project → substitute → PREPARE → create reverse stream → abort gate → trace(tokenized input) → pinned generateStream(signal)`.

For each chunk: `abort gate → typeof tokenized chunk check → trace → reverseStream.push → typeof safe chunk check → await sink`. On raw completion: `abort gate → reverseStream.end → validate/copy tail → reverse each tool argument → freeze tail → finalize completed → resolve tail`.

After the once-latch closes on abort or failure, later callbacks perform zero trace/sink/reversal output and initiate zero egress; they may only perform idempotent cleanup.

## 7. Azure evidence: two policy-version bindings

### 7.1 Required signed claims

`AzureEgressPolicyEvidence` gains both fields:

```ts
/** Immutable revision of the attestor's observed egress posture. */
readonly egressPolicyVersion: string;

/**
 * SHA-256 digest of the consumer's normalized engine mode + BAA matrix boot configuration.
 * Supplied by consumer boot configuration; the attestor binds it but need not observe the matrix.
 */
readonly enginePolicyVersion: string;
```

Both are non-empty, PHI-free deployment identifiers. Neither defaults, aliases the other, derives from `deploymentDigest`/image tags, or is inferred by this package. The attestor MUST observe and identify its own egress posture to issue `egressPolicyVersion`. The consumer supplies the expected `enginePolicyVersion` at boot; the attestor need not inspect or independently understand the BAA matrix, but its signature MUST bind the supplied digest into the evidence.

### 7.2 Engine-policy normalization

The consumer computes `enginePolicyVersion` as:

```text
"sha256:" + lowercaseHex(
  SHA-256(
    UTF-8(
      RFC8785_JCS({ engineMode: normalizedEngineMode, baaMatrix: normalizedBaaMatrix })
    )
  )
)
```

The consumer-owned boot schema defines the allowed `engineMode` and BAA-matrix values and MUST reject free text, `undefined`, non-finite numbers, duplicate logical provider ids, and ambiguous aliases before hashing. Object member ordering is provided by JCS. Any arrays whose source order is not semantically meaningful MUST be sorted by the consumer schema before JCS. This package treats the resulting 71-character `sha256:<64 lowercase hex>` value as an opaque required version and does not need the BAA matrix.

### 7.3 Signed-claim canonicalization

```ts
export type AzureEgressPolicySignedClaims = Omit<AzureEgressPolicyEvidence, "signature">;
```

1. The signature covers the exact `AzureEgressPolicySignedClaims`, including `protectedServiceIdentity`, `imageDigest`, `deploymentDigest`, `egressPolicyVersion`, and `enginePolicyVersion`.
2. Before canonicalization, `loggingPlanes` MUST be copied and sorted ascending by its `plane` string using Unicode code-point order. Duplicate plane ids are invalid. No other array is reordered by this evidence contract.
3. The canonical bytes are UTF-8 bytes of **RFC 8785 JSON Canonicalization Scheme (JCS)** output over the sorted claims object. JSON.stringify insertion order, ad-hoc stable-stringify, locale collation, and signature-object inclusion are forbidden.
4. `signature.signedClaimsDigest` MUST equal `"sha256:" + lowercaseHex(SHA-256(canonicalBytes))`.
5. M3 exact-matches all expected identity/deployment/image and both policy-version claims before accepting the signature. A valid signature over another value of either version is invalid.

This is an authorized evidence-schema expansion. The seam defines interoperability for M3/M4 but GLY-353 adds no in-package runtime signer or verifier. M4 emitters/fixtures add both fields before M3 enforcement; reclaim and Q6 do not construct evidence.

## 8. Node engine resolution

### 8.1 Ruling: Node 20 remains supported

The current locked Azure direct dependencies genuinely support Node 20, so GLY-353 does not force Node 22.

1. Pin exact direct versions: `@azure/identity: "4.13.1"`, `@azure/keyvault-keys: "4.10.2"`, and `@azure/storage-file-share: "12.31.0"`.
2. Regenerate the lock without changing those resolutions; verify the **production and development** lock closures on Node 20. A development-only transitive engine mismatch is still an install/CI failure.
3. Use `@types/node` major 20 so Node-22-only APIs cannot typecheck accidentally.
4. Keep runtime `engines.node` at `>=20`. CI is normatively pinned to Node `20.20.2` or a later `20.x`, and MUST NOT be below `20.19.0` because Vite's development closure requires at least 20.19.
5. Run `npm ci` with `engine-strict=true`; an incompatible production or development resolution is a hard failure, not an ignored warning.
6. Document that Node-20 support is the exact checked-in graph. Any future upgrade raising the floor needs a separate compatibility decision and cannot drift through a caret.

Node 22 remains allowed by `>=20`; it is not required.

### 8.2 Compatibility gate and CI scope

```text
npm_config_engine_strict=true npm ci
npm run typecheck
npm test
npm run build
npm run build:executables
```

A lock/source oracle asserts exact Azure pins, Node-20 `@types/node`, and no resolved production **or development** dependency whose engine excludes the pinned CI Node-20 version.

CI edits are limited to the phi-substitution-engine job in monorepo-root `.github/workflows/ci.yml:208-230`; no unrelated job, global runner, or change filter is changed. The workflow's change filter is evaluated before that job. This PR necessarily touches `packages/phi-substitution-engine/**`, so the existing filter selects the job and the Node/engine-strict gates execute.

## 9. Backward compatibility and rollout

1. `createSubstitutionEngine(options?)` retains its exact development bundle, defaults, facade, and behavior.
2. `createProtectedAiProvider(options?)` retains its independent development engine and `DevProtectedAiProvider` result. It is not silently changed to singleton reuse and gains no production-mode guard.
3. Legacy `AiProvider`, `RawProviderPort`, `DevBoundaryProvider`, and `ProtectedStreamResult` retain their signatures and semantics. The new production port/result types do not replace them. **One explicit public-type widening is authorized:** `ProtectedAiProviderDependencies.invokeRaw` changes from required to optional (`readonly invokeRaw?: RawProvider`) so production composition is not forced to inject a fallback provider. Existing callers remain source-compatible; legacy development composition still supplies `invokeRaw`, while production obtains its request-local provider only from the router. Runtime code MUST fail closed if a legacy path actually requires an absent `invokeRaw`; absence never selects a default.
4. The runtime root allow-list gains only `createProductionProtectedAiProvider`. §5 types and `AzureEgressPolicySignedClaims` are type-only root exports. No wildcard/subpath is added.
5. Reclaim and Q6 retain imports/behavior and both executable targets compile without production dependencies.
6. Root import and production-factory construction without Azure credentials, PostgreSQL environment, or network access succeed and invoke no port.
7. Rollout order: publish additive API/type and exact lock → update M4 to produce both policy claims under §7.3 → compose singleton/router/adapters → add product adapter → enable M3 exact-version enforcement.
8. The product composition root MUST ensure its documented `engineVersion` matches the supplied engine and MUST enforce one production engine through the consumer N7 layer-1 import scan. These are deployment acceptance obligations, not new `PhiSubstitutionEngine` methods.

## 10. Required implementation/edit boundaries

- `src/factory.ts`: production types, composition, fixed audit construction, facade; no raw-provider option.
- `src/index.ts`: one runtime factory plus required type-only exports.
- `src/core/wrapper.ts`: production result metadata/tool reversal, cancellation/once-latch, shared sink primitive, and router-derived invocation; legacy collection delegates unchanged.
- `src/core/protected-ai-provider.ts`: provider-agnostic type-only seams if not colocated in factory; legacy `AiProvider` unchanged.
- `src/core/contracts.ts` and `src/core/errors.ts` only as required for additive `CALL_INTERRUPTED` and fixed sanitization.
- `src/audit/ports.ts`, serializer, and exact allow-list tests: additive `interrupted` audit outcome with `failureCode: null`; `src/audit/serializer.ts:18` `TERMINAL_FAILURE_CODES` remains unchanged and MUST NOT contain `CALL_INTERRUPTED`.
- `src/core/protected-ai-provider.ts`: explicitly widen public `ProtectedAiProviderDependencies.invokeRaw` from required to optional; preserve legacy behavior and prohibit a production fallback/default (§9.3).
- `src/coverage/contracts.ts`: both version fields, signed-claims alias/signature canonicalization docs, and the seam-freeze comment at lines 121-123 amended with a dated note: **`2026-08-18 — GLY-353 additive amendment: egressPolicyVersion and enginePolicyVersion are required signed claims; RFC 8785/SHA-256 canonicalization is normative.`** The existing GLY-335 freeze is preserved, not deleted or rewritten.
- `package.json` / lock: exact Azure pins and Node-20 declarations.
- monorepo-root `.github/workflows/ci.yml:208-230`: only the phi-substitution-engine job, per §8.2.
- `README.md`: production composition, protected envelopes/cancellation, caller singleton/version obligations, N7 import-scan boundary, and Node support.
- `tests/production-factory.test.ts`: production behavior/capability oracles.
- evidence contract tests: dual claims, JCS known-answer vector, sorted logging planes.
- `type-tests/production-factory.ts` plus `tsconfig.public-api.json`: external-consumer contract included in `npm run typecheck`.
- Existing tests only for additive allow-list/fixtures. No `CONTRACT/**` file or frozen expectation may be weakened.

## 11. Test oracle plan

### 11.1 API, construction, and singleton

1. **ORACLE-PROD-ROOT-IMPORT:** only the new factory is a runtime export; production/provider/envelope seams are type-only; no concrete capability runtime export.
2. **ORACLE-PROD-TYPE-ADAPTER:** a product-local result/stream/tool adapter compiles with no Glassy import; `TokenizedText` cannot be assigned to any application-facing result field.
3. **ORACLE-PROD-NOT-LEGACY-AIPROVIDER:** negative type fixture proves explicit adaptation is required.
4. **ORACLE-PROD-SINGLETON:** a canary engine's substitute/reverse/createReverseStream counters prove every path uses the injected engine and no factory/constructor path builds another.
5. **ORACLE-PROD-NO-DEFAULTS:** negative type fixtures omit each port/version; runtime cast/missing/throwing-getter matrix rejects fixed with zero calls.
6. **ORACLE-PROD-FACADE:** null prototype, frozen, exact methods, no constructor/capability leak.
7. **ORACLE-PROD-SNAPSHOT:** mutating the top-level dependency object after construction cannot swap ports.
8. **ORACLE-PROD-CONSTRUCTION-PURE:** instrument every engine/context/policy/projector/router/trace/audit-primary/spool/provider/clock method; create the factory and assert every count is zero and no I/O occurs.
9. **ORACLE-PROD-CALLER-ENGINE-VERSION-OBLIGATION:** README/public docs explicitly require the composition root to keep `engineVersion` consistent with the injected engine, while type/source tests prove no version-introspection method was added to `PhiSubstitutionEngine`.
10. **ORACLE-PROD-N7-CONTAINMENT-DOC:** docs state second-engine containment belongs to the consumer N7 layer-1 import scan and source proves no development-factory guard was introduced.

### 11.2 Protected text, tools, routing, audit, and embedding

1. **ORACLE-PROD-TEXT-ENVELOPE:** router sees original PHI canary; selected provider/trace see only token; result is the exact frozen envelope; caller sees reversed display and authoritative routed providerId; audit/errors contain no canary.
2. **ORACLE-PROD-TOOL-ARGUMENT-REVERSAL:** provider returns a tool argument containing a valid substitution token. The injected canary engine observes `reverse` on both response text and that argument; the returned tool argument contains the original display value and contains no token. No raw tool object reference is retained.
3. **ORACLE-PROD-TOOL-FAIL-CLOSED:** non-string or failed tool-argument reversal returns no partial envelope, one failure terminal, and a fixed safe error.
4. **ORACLE-PROD-ROUTE-PIN:** router owns providers A and B and selects B; only B is invoked exactly once and A is invoked **zero** times. There is no independently injected fallback provider.
5. **ORACLE-PROD-METADATA-VALIDATION:** malicious model/tool id/tool name, negative/non-integer usage, and extra raw fields cannot reach result/audit/trace; valid metadata is copied/frozen.
6. **ORACLE-PROD-AUDIT-PRIMARY:** PREPARE precedes raw call; exactly one terminal follows.
7. **ORACLE-PROD-AUDIT-SPOOL:** primary unavailable/spool ready permits one egress; both unavailable permits zero.
8. **ORACLE-PROD-EMBED:** original route; tokenized raw/trace; durable order; numeric-only result; non-selected providers zero.

### 11.3 Streaming and cancellation

1. **ORACLE-PROD-STREAM-LIVE:** sink observes reversed chunk 1 before controlled raw stream release.
2. **ORACLE-PROD-STREAM-BACKPRESSURE:** unresolved sink 1 prevents raw chunk 2 advancement.
3. **ORACLE-PROD-STREAM-COMPLETION-TAIL:** completion resolves the frozen `{providerId, model?, usage?, toolCalls?}` tail only after `end`, tool-argument reversal, and audit finalization.
4. **ORACLE-PROD-STREAM-TOOL-ARGUMENT-REVERSAL:** a token inside a completion tool-call argument round-trips to display text before the tail resolves; token/raw object never crosses the seam.
5. **ORACLE-PROD-STREAM-NONSTRING-REVERSED:** a cast/malicious reverse stream invokes its safe callback with a non-string; production sink receives zero calls for it, reverse stream aborts, one failure terminal is attempted, and caller receives only a fixed error.
6. **ORACLE-PROD-STREAM-SINK-FAILURE:** one provider call, one failure terminal, no later display, no interruption terminal, fixed error only.
7. **ORACLE-PROD-ABORT-BEFORE-EGRESS:** pre-aborted call prepares/finalizes `interrupted`, routes/providers zero times, returns fixed `CALL_INTERRUPTED`, and emits no failure terminal.
8. **ORACLE-PROD-ABORT-IN-FLIGHT-TEXT:** controlled provider observes the private signal abort; late result is ignored; provider count remains one; no reversal/result; one `interrupted` terminal.
9. **ORACLE-PROD-ABORT-IN-FLIGHT-STREAM:** after one safe chunk, abort prevents any later sink/trace output or new egress, calls reverse-stream abort, propagates the signal best-effort, and finalizes one `interrupted` terminal.
10. **ORACLE-PROD-ABORT-SINK-RACE:** deterministic gates test both orders: abort-first yields interrupted; sink-rejection-first yields failure. Each has one terminal and no raw abort reason.
11. **ORACLE-PROD-LATE-ABORT:** abort after successful finalization is a no-op and proves listener cleanup.
12. **ORACLE-PROD-LEGACY-STREAM:** dev `generateStream()` still returns the same collected result and has no signature/result change.

### 11.4 Evidence, Node, CI, and compatibility

1. **ORACLE-EVIDENCE-DUAL-POLICY-VERSION-TYPE:** complete evidence/claims compile; separate `@ts-expect-error` fixtures reject missing `egressPolicyVersion` and missing `enginePolicyVersion`.
2. **ORACLE-EVIDENCE-SIGNED-CLAIMS:** type equality/excess-property probe proves claims include both versions and omit only signature.
3. **ORACLE-EVIDENCE-JCS-KNOWN-ANSWER:** a fixed Unicode/numeric evidence vector with deliberately shuffled object keys and `loggingPlanes` order produces one checked-in RFC-8785 UTF-8 preimage and `sha256:<lowercase hex>` digest. Permuting object keys or plane order yields the same preimage/digest; changing either policy version changes it; including `signature` does not match.
4. **ORACLE-EVIDENCE-ENGINE-POLICY-NORMALIZATION:** fixed normalized boot-config vector yields the specified 71-character digest; matrix/key input order variants normalize identically and a semantic mode/matrix change differs.
5. **ORACLE-NODE20-EXACT-PINS:** inspect manifest/lock exact versions and Node-20 types.
6. **ORACLE-NODE20-ENGINE-STRICT:** clean engine-strict install on pinned Node20 plus typecheck/test/build/build:executables.
7. **ORACLE-NODE20-LOCK-CLOSURE:** traverse all lock packages reachable through **dependencies and devDependencies** and fail any effective engine range excluding the exact CI Node version.
8. **ORACLE-CI-PHI-JOB-SCOPE:** diff/source test proves only root `ci.yml` phi-substitution-engine job changed, its Node version is `>=20.19.0`, engine-strict is active before install, and the existing package change filter still selects this PR.
9. **ORACLE-BACKCOMPAT-EXECUTABLES:** Q6/reclaim compile with no factory config.
10. **ORACLE-NO-GLASSY-DEPENDENCY:** zero Glassy imports/dependencies in active source/manifests/type tests.
11. **ORACLE-SEAM-FREEZE-AMENDMENT:** source-shape test preserves the GLY-335 freeze text and finds the dated GLY-353 additive amendment required by §10.

### 11.5 Evidence contract

Implementation evidence includes raw clean engine-strict install on the exact CI Node version, all type targets, full suite, both builds, every mutant alone verified-applied RED/restored GREEN, full diff/check/status, and a changed-file allow-list proving no CONTRACT/unrelated change. For every mutant, evidence names its mutation anchor, RED oracle/test name, restore command, and post-restore GREEN result.

## 12. Named mutations

| Mutant | Mutation | RED oracle |
|---|---|---|
| `GLY-353-MUT-FACTORY-REBUILDS-ENGINE` | replace injected engine with dev/new engine | ORACLE-PROD-SINGLETON |
| `GLY-353-MUT-FACTORY-DEV-DEFAULT` | default a required production port/version | ORACLE-PROD-NO-DEFAULTS |
| `GLY-353-MUT-FACTORY-LEAKS-CAPABILITY` | add engine/provider/router/audit property or prototype | ORACLE-PROD-FACADE |
| `GLY-353-MUT-FACTORY-LIVE-DEPS` | retain/re-read mutable dependency object | ORACLE-PROD-SNAPSHOT |
| `GLY-353-MUT-CONSTRUCTION-CALLS-PORT` | invoke any port/clock during factory construction | ORACLE-PROD-CONSTRUCTION-PURE |
| `GLY-353-MUT-CONTEXT-BYPASS` | use fixed/dev context | ORACLE-PROD-TEXT-ENVELOPE |
| `GLY-353-MUT-POLICY-BYPASS` | use fixed/dev policy | ORACLE-PROD-TEXT-ENVELOPE |
| `GLY-353-MUT-PROJECTOR-BYPASS` | send original options to provider | ORACLE-PROD-TEXT-ENVELOPE |
| `GLY-353-MUT-ROUTE-TOKENIZED` | route after substitution | ORACLE-PROD-ROUTE-PIN |
| `GLY-353-MUT-ROUTE-IGNORED` | call A/fallback rather than router-pinned B | ORACLE-PROD-ROUTE-PIN |
| `GLY-353-MUT-AUDIT-AFTER-EGRESS` | move PREPARE after raw call | ORACLE-PROD-AUDIT-PRIMARY |
| `GLY-353-MUT-AUDIT-DROP-SPOOL` | skip spool fallback | ORACLE-PROD-AUDIT-SPOOL |
| `GLY-353-MUT-TRACE-RAW` | trace original/display text | ORACLE-PROD-TEXT-ENVELOPE |
| `GLY-353-MUT-TEXT-RESULT-RAW` | return tokenized text/raw response instead of exact envelope | ORACLE-PROD-TEXT-ENVELOPE |
| `GLY-353-MUT-TOOL-ARGUMENT-RAW` | return provider tool arguments without `engine.reverse` | ORACLE-PROD-TOOL-ARGUMENT-REVERSAL |
| `GLY-353-MUT-TOOL-ARGUMENT-PARTIAL` | return envelope when one tool argument fails | ORACLE-PROD-TOOL-FAIL-CLOSED |
| `GLY-353-MUT-PROVIDER-ID-FROM-RAW` | trust provider-returned id rather than route decision | ORACLE-PROD-TEXT-ENVELOPE |
| `GLY-353-MUT-STREAM-TOKENIZED` | send provider chunk to display sink | ORACLE-PROD-STREAM-LIVE |
| `GLY-353-MUT-STREAM-DROP-NONSTRING` | remove the non-string reversed-chunk fail-closed guard | ORACLE-PROD-STREAM-NONSTRING-REVERSED |
| `GLY-353-MUT-STREAM-NO-BACKPRESSURE` | do not await sink | ORACLE-PROD-STREAM-BACKPRESSURE |
| `GLY-353-MUT-STREAM-BUFFER-ALL` | collect before production sink | ORACLE-PROD-STREAM-LIVE |
| `GLY-353-MUT-STREAM-DOUBLE-SEND` | retry/reinvoke raw stream | ORACLE-PROD-STREAM-SINK-FAILURE |
| `GLY-353-MUT-STREAM-TAIL-BEFORE-TOOLS` | resolve completion before tool argument reversal | ORACLE-PROD-STREAM-TOOL-ARGUMENT-REVERSAL |
| `GLY-353-MUT-ABORT-AS-FAILURE` | finalize abort as failed_closed/cancelled | ORACLE-PROD-ABORT-BEFORE-EGRESS |
| `GLY-353-MUT-ABORT-STARTS-EGRESS` | invoke/retry provider after abort latch | ORACLE-PROD-ABORT-BEFORE-EGRESS + IN-FLIGHT oracles |
| `GLY-353-MUT-ABORT-DROPS-SIGNAL` | do not pass/abort private transport signal | ORACLE-PROD-ABORT-IN-FLIGHT-TEXT |
| `GLY-353-MUT-ABORT-DOUBLE-TERMINAL` | omit terminal once-latch | ORACLE-PROD-ABORT-SINK-RACE |
| `GLY-353-MUT-EMBED-BYPASS` | original embed text or skip route/audit | ORACLE-PROD-EMBED |
| `GLY-353-MUT-DEV-FACTORY-CHANGED` | alter legacy dev semantics/add guard | ORACLE-PROD-LEGACY-STREAM + N7 containment oracle |
| `GLY-353-MUT-EVIDENCE-DROP-EGRESS-POLICY-VERSION` | remove/make egressPolicyVersion optional | ORACLE-EVIDENCE-DUAL-POLICY-VERSION-TYPE |
| `GLY-353-MUT-EVIDENCE-DROP-ENGINE-POLICY-VERSION` | remove/make enginePolicyVersion optional | ORACLE-EVIDENCE-DUAL-POLICY-VERSION-TYPE |
| `GLY-353-MUT-EVIDENCE-DIGEST-OMITS-VERSION` | omit either version from signed claims | ORACLE-EVIDENCE-SIGNED-CLAIMS/JCS-KNOWN-ANSWER |
| `GLY-353-MUT-EVIDENCE-JSON-STRINGIFY` | use insertion-order JSON instead of RFC 8785 JCS | ORACLE-EVIDENCE-JCS-KNOWN-ANSWER |
| `GLY-353-MUT-EVIDENCE-UNSORTED-PLANES` | hash loggingPlanes in supplied order | ORACLE-EVIDENCE-JCS-KNOWN-ANSWER |
| `GLY-353-MUT-NODE20-RESTORE-CARET` | restore Azure caret | ORACLE-NODE20-EXACT-PINS |
| `GLY-353-MUT-NODE20-RESOLVE-NODE22` | resolved prod/dev engine excludes Node20 | ORACLE-NODE20-ENGINE-STRICT/LOCK-CLOSURE |
| `GLY-353-MUT-NODE20-TYPES-22` | restore Node22 types | ORACLE-NODE20-EXACT-PINS |
| `GLY-353-MUT-CI-WRONG-JOB` | apply Node/strict change globally or outside phi job | ORACLE-CI-PHI-JOB-SCOPE |
| `GLY-353-MUT-ROOT-EXPORTS-CONCRETE` | export wrapper/provider/audit runtime | ORACLE-PROD-ROOT-IMPORT |
| `GLY-353-MUT-SEAM-AMENDMENT-DROPPED` | omit/delete dated GLY-353 freeze amendment | ORACLE-SEAM-FREEZE-AMENDMENT |

Equivalent mutants must be strengthened, never deleted, declared inapplicable without a verified anchor, or excused by weakening an oracle.

## 13. Acceptance criteria

1. The §5 additive API is root-importable with no Glassy dependency.
2. Exact supplied engine serves text/stream/embed, main-output reversal, every tool-argument reversal, and stream reversal; the production factory creates no hidden engine.
3. All production security/durability ports and both version values are required; no dev or provider fallback is reachable.
4. Facade and all returned envelopes/tails are frozen, copied, capability-tight, provider-neutral, and PHI-free.
5. Text and streaming results carry authoritative providerId plus validated optional metadata, and every tool-call argument is reversed in-package before application exposure.
6. Streaming delivers reversed display live, ordered, string-validated, with awaited backpressure and exactly-one provider/audit semantics.
7. Abort is a distinct `interrupted` terminal, starts no further egress after its latch, propagates best-effort transport cancellation, and cannot be confused with sink failure.
8. Fixed serializer composes injected primary/spool; both unavailable means zero egress.
9. `egressPolicyVersion` and `enginePolicyVersion` are required signed claims; digest interoperability is RFC 8785 JCS plus SHA-256 with logging planes sorted by plane id.
10. The consumer documents and enforces that supplied `engineVersion` matches the supplied engine; GLY-353 does not widen `PhiSubstitutionEngine` to police that obligation.
11. Node20 at `>=20.19.0` passes engine-strict clean install, all type targets, tests, and builds against the full production and development closure on exact Azure resolutions.
12. CI changes are confined to the root workflow's phi-substitution-engine job and execute under its existing change-filter ordering.
13. Dev factories, Q6, reclaim, subpath fence, fixed errors (except authorized additive interruption), and frozen CONTRACT tests do not regress; the consumer N7 layer-1 scan remains the reviewed second-engine containment.
14. The dated GLY-353 amendment is present beside the preserved GLY-335 evidence seam-freeze comment.
15. Every `GLY-353-MUT-*` is independently verified-applied, RED on its named oracle, restored, and GREEN.

## 14. Open questions

None for the principal. The binding rulings select: a PHI-free envelope with in-package tool-argument reversal; explicit abort/interrupted semantics; separate egress and engine-policy signed claims; RFC 8785/SHA-256 canonicalization; caller-owned version consistency; router-only provider authority; consumer N7 import-scan containment; Node 20 across both lock closures; scoped CI; and a dated seam-freeze amendment.

## 15. Revision v2 changelog

| Finding | Binding change in v2 |
|---|---|
| F1 | Added exact PHI-free text/tail envelopes (§4.5-4.6, §5.1-5.3), in-package main/tool-argument reversal, tool round-trip oracles (§11.2.2, §11.3.4), and raw-tool mutants. |
| F2 | Added `AbortSignal` to text/stream, distinct `interrupted` audit terminal, fixed interruption error, once-latch race rules, no-new-egress boundary, and best-effort transport cancellation (§4.7, §5.2-5.3, §6, §11.3). |
| F3 | Replaced `policyVersion` with signed `egressPolicyVersion` plus consumer-supplied `enginePolicyVersion`; attestor binds but need not observe the BAA matrix (§5.4, §7). |
| F4 | Made RFC 8785 JCS + SHA-256 normative, including pre-sort of `loggingPlanes` by plane id and a known-answer oracle (§7.2-7.3, §11.4.3-4). |
| F5 | Demoted engine-version matching to a documented caller/deployment obligation and explicitly forbade widening `PhiSubstitutionEngine` (§4.2.4, §9.8, §13.10). |
| F6 | Removed `rawProvider` from production dependencies; request-local router result alone supplies the internal invocation capability; added selected-B/A-zero oracle (§4.9, §5.4, §11.2.4). |
| F7 | Recorded reviewed delegation of second-engine containment to consumer N7 layer-1 import scanning; no dev-factory runtime guard (§3.2.9, §4.2.5, §9.2/8). |
| F8 | Required fail-closed runtime validation for non-string reversed chunks and added `GLY-353-MUT-STREAM-DROP-NONSTRING` (§4.6.3, §11.3.5, §12). |
| F9 | Extended the Node-20 closure gate to dependencies and devDependencies and made CI Node `>=20.19.0` normative (§8, §11.4.5-7). |
| F10 | Confined CI edits to monorepo-root `ci.yml:208-230` phi-substitution-engine job and documented pre-job change-filter sequencing (§8.2, §10, §11.4.8). |
| F11 | Required the dated GLY-353 additive note at `src/coverage/contracts.ts:121-123`, preserving the GLY-335 freeze, with a source oracle (§10, §11.4.11, §13.14). |
| Additional | Added `GLY-353-MUT-CONSTRUCTION-CALLS-PORT` and its all-ports-zero construction oracle (§5.5.2, §11.1.8, §12). |

## 16. Revision v2.1 changelog — frozen build spec

| Residual | Binding amendment |
|---|---|
| R1 | §4.7.3 and §10 state that only `interrupted` enters `PhiAuditOutcome`; `CALL_INTERRUPTED` is forbidden from serializer `TERMINAL_FAILURE_CODES`. |
| R2 | §9.3 and §10 explicitly authorize the source-compatible optional widening of public `ProtectedAiProviderDependencies.invokeRaw`, without a runtime default. |
| R3 | §4.7.4 makes `CALL_INTERRUPTED` authoritative when a pre-abort, zero-egress PREPARE is not durable; the caller never receives the durability failure. |

**Freeze:** v2.1 is the implementation contract. Later implementation changes require an explicit dated amendment or a new reviewed specification revision.

## Amendment 2026-08-18 — orchestrator ruling: exact Node engine floor

This is a **legitimately-better-design** amendment to §8.1, ruled by the orchestrator on 2026-08-18: the normative `package.json` `engines.node` floor is `>=20.19.0`, not `>=20`. The exact floor aligns the published package contract with the Node 20 CI pin and the transitive development-tool closure validated by `ORACLE-NODE20-LOCK-CLOSURE`. It changes no production API or runtime behavior.
