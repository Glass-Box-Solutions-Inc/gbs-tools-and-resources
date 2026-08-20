**Model: GPT-5.6-sol**

# GLY-353 specification v1 — production protected-AI composition factory

## 1. Status, authority, and scope

1. This is a **T2 specification only**. It authorizes no implementation, commit, push, release, or deployment in this round.
2. The implementation base is `main` at `1abf86a`; the implementation lane is `GLY-353-production-factory`.
3. GLY-353 is the package-side prerequisite for the Glassy M3 integration (GLY-338 slice B2), but this package MUST NOT import Glassy types, source files, runtime values, or dependencies. The production seam is expressed entirely in phi-substitution-engine terms.
4. Existing CONTRACT invariants and frozen tests remain authoritative. No test, allow-list, failure gate, durability requirement, routing rule, reversal rule, or capability boundary may be weakened.
5. The change is expand-only: add one production factory, type-only seams, one internal streaming path, evidence-version binding, compatibility documentation, and oracles. Do not remove, rename, or incompatibly overload either development factory. Do not add a package subpath export or expose a concrete engine, raw provider, audit emitter, spool, reversal store, crypto primitive, policy object, or router at the runtime root.
6. `MUST`, `MUST NOT`, `SHOULD`, and `MAY` are normative.

## 2. Current state and problem statement

1. `createSubstitutionEngine()` is a development API returning a `DevSubstitutionEngine` bundle, not a bare engine.
2. `createProtectedAiProvider()` calls `buildDevEngineParts()` and constructs an independent engine, so a product cannot wrap the exact singleton engine it owns.
3. The development provider factory hard-wires development context, policy, projector, BAA route, trace, audit primary/spool, and echo-provider defaults. A raw-provider option alone is not production composition.
4. The legacy `AiProvider` shape mirrors one historical consumer but its result and streaming contracts are not a stable cross-product contract. A production integration needs a small protected surface which a product-owned adapter can translate into its own objects.
5. `AzureEgressPolicyEvidence` binds identity and image/deployment digests but not the policy revision.
6. The package declares Node `>=20`, while caret resolution can select later Azure SDK releases with a higher engine floor. At this base the lock resolves `@azure/identity@4.13.1`, `@azure/keyvault-keys@4.10.2`, and `@azure/storage-file-share@12.31.0`; all declare Node `>=20.0.0`. This is resolution drift, not demonstrated incompatibility in those versions.

## 3. Goals and explicit non-goals

### 3.1 Goals

1. Wrap the **exact caller-supplied `PhiSubstitutionEngine` singleton** and never construct a second engine.
2. Require production context, policy, projector, original-content router, trace, raw provider, audit primary, encrypted spool, embedding projection, and engine-version inputs. No development fallback is legal.
3. Return a frozen null-prototype, provider-agnostic protected call facade for text, incremental display streaming, and embeddings.
4. Preserve original-content routing, exhaustive projection, substitution, durable audit PREPARE, exactly-one raw call, tokenized-only tracing/egress, reversal before display, and exactly-one terminal audit event.
5. Bind signed Azure egress evidence to a non-empty policy version together with identity and image/deployment digest.
6. Preserve Node 20 by freezing proven-compatible Azure versions and enforcing engine compatibility in CI.

### 3.2 Non-goals

1. No Glassy import/type/dependency and no SDK-specific product result or stream type.
2. No provider construction, credential loading, database connection, environment read, or network call at import or factory construction.
3. No new production engine builder. Engine lifetime/singleton ownership stays with the application composition root.
4. No behavior change to either development factory, its defaults, bundle results, echo path, or facades.
5. No public concrete wrapper, engine, audit emitter, serializer, or adapter export.
6. No M3 verifier or M4 signer implementation; this lane defines their required signed-claim shape.
7. No generalized cancellation/`AbortSignal` protocol and no claim that a rejecting sink cancels provider transport.
8. No Node-22-only API and no forced consumer bump while the pinned graph supports Node 20.

## 4. Constitutional decisions and invariants

### 4.1 Separate production entry point

The additive root factory is `createProductionProtectedAiProvider`. It is not an overload of either development factory. Its required dependency object prevents omission from selecting a development default.

### 4.2 Singleton ownership

1. `dependencies.engine` is required and serves every substitution, reversal, and reverse-stream creation.
2. The factory MUST NOT call `buildDevEngineParts`, `createSubstitutionEngine`, `new ComposedSubstitutionEngine`, or any engine-producing callback.
3. The factory does not return the engine; the application already owns it.
4. `engineVersion` is a required PHI-free composition identifier for minimal pre-substitution audit records and MUST match the supplied engine. The current engine interface is intentionally not widened for introspection.

### 4.3 No production defaults

Every security-sensitive dependency in §5.2 is required. Production construction MUST NOT create an in-memory reversal store, development context/policy, echo provider, collecting trace, in-memory audit store, fixed spool key, or fixed BAA decision. `clock` is the only optional dependency and retains the safe UTC fallback.

### 4.4 Capability-tight result

The result is a frozen null-prototype object with exactly `embedText`, `generateText`, and `streamText`. It has no constructor, prototype, data properties, or reference to engine, dependencies, provider, original options, context, policy, audit, trace, reversal handle, spool, or router. Methods are closure-bound.

### 4.5 Provider-agnostic boundary

The new surface does not extend or implement legacy `AiProvider`. `generateText` yields `DisplayText`; `streamText` delivers ordered `DisplayText` chunks and resolves after completion; `embedText` yields the numeric vector. Product adapters may wrap these into local result/stream types but never receive `TokenizedText`, reversal handles, or raw provider bindings.

### 4.6 Streaming consistency

1. The wrapper gains one sink-based streaming primitive. Legacy `generateStream(options): Promise<ProtectedStreamResult>` delegates to it using a collector, preserving behavior.
2. The production sink is invoked only from the reverse-stream safe-output callback; raw/tokenized chunks never reach it.
3. Sink calls are awaited sequentially, providing ordering and backpressure.
4. Sink rejection uses the existing post-send failure path: abort/latch best-effort, finalize one fixed-code terminal, make zero additional provider calls, and reject with a fresh fixed `PhiEngineError` without raw text.
5. Completion resolves only after `stream.end()` and terminal finalization. A first safe chunk is observable before raw completion; production MUST NOT collect all chunks first.
6. Sink rejection may stop local delivery but this ticket makes no upstream transport-cancellation guarantee.

### 4.7 Audit composition

The factory accepts `AuditPrimaryStore` and `EncryptedAuditSpool`, privately creates `DurablePhiAuditEmitter` with the non-injectable `ExactAllowListAuditSerializer`, and shares the safe clock with the wrapper. Primary-unavailable/spool-ready continues; both unavailable fails before provider egress. No audit-free production path exists.

### 4.8 Router authority

`rawProvider` is the product's primary private provider adapter and satisfies the legacy internal dependency shape. `router.selectUsingOriginalContent()` is authoritative: the wrapper invokes the exact provider returned by the pinned routing decision, which may be `rawProvider` or another route-specific adapter. Neither is exported and no second raw invocation occurs.

## 5. Exact additive public API

### 5.1 Protected call surface

```ts
export type DisplayChunkSink = (chunk: DisplayText) => void | Promise<void>;

export interface ProtectedAiCallSurface<GenerateOptions, EmbeddingKind = string> {
  generateText(options: GenerateOptions): Promise<DisplayText>;
  streamText(options: GenerateOptions, sink: DisplayChunkSink): Promise<void>;
  embedText(text: string, kind: EmbeddingKind): Promise<readonly number[]>;
}
```

### 5.2 Factory dependencies

```ts
export interface CreateProductionProtectedAiProviderOptions<GenerateOptions, EmbeddingKind = string> {
  readonly engine: PhiSubstitutionEngine;
  readonly engineVersion: EngineVersion;
  readonly context: MatterAiContextAccessor;
  readonly policy: MatterAiPolicyAccessor;
  readonly projector: AiProviderOptionProjector<GenerateOptions>;
  readonly router: OriginalContentProviderRouter<GenerateOptions, RawProviderPort<GenerateOptions, EmbeddingKind>>;
  readonly safeTrace: SafeAiTrace;
  readonly rawProvider: RawProviderPort<GenerateOptions, EmbeddingKind>;
  readonly auditPrimary: AuditPrimaryStore;
  readonly auditSpool: EncryptedAuditSpool;
  readonly embeddingOptionsFactory: (text: string) => GenerateOptions;
  readonly clock?: () => string;
}

export function createProductionProtectedAiProvider<GenerateOptions, EmbeddingKind = string>(
  dependencies: CreateProductionProtectedAiProviderOptions<GenerateOptions, EmbeddingKind>,
): ProtectedAiCallSurface<GenerateOptions, EmbeddingKind>;
```

### 5.3 Construction behavior

1. Snapshot top-level dependency references once. A throwing getter or missing/non-callable required method causes a fresh `PhiEngineError("PROVIDER_SAFETY_GATE_FAILED")` with no cause or caller details.
2. Construction invokes no port and reads no context/policy; those stay request-scoped.
3. The wrapper receives the exact injected engine, projector, router, trace, and provider plus the private durable audit emitter.
4. Return the §4.4 facade directly, not a development bundle.

## 6. Call protocol and failure boundaries

| Call/state | Required action | Output | Failure/recovery |
|---|---|---|---|
| construction | snapshot capabilities; compose serializer/emitter; wrap exact engine | frozen facade | invalid composition: fresh fixed error, zero port calls |
| context | `context.require()` once | none | fixed missing-context, zero provider calls |
| policy | `policy.require(context)` once | none | fixed failure; one terminal after context |
| route | inspect original options and pin provider | none | unsafe/BAA-unsatisfied fails pre-egress |
| project/substitute | classify all carriers, rebuild tokenized options, call supplied engine | none | unclassified carrier fails closed |
| audit PREPARE | primary then encrypted spool | internal receipt | both unavailable: zero provider calls |
| raw text | selected provider once with tokenized options | internal tokenized value | sanitized rejection, one terminal |
| reversal | trace tokenized output, reverse with supplied engine | `DisplayText` | sanitized rejection, one terminal |
| raw stream chunk | validate/trace tokenized chunk and push reverse stream | none | bad chunk aborts/latches |
| reversed chunk | await display sink | safe chunk | sink failure aborts/latches and sanitizes |
| stream end | end holdback, finalize terminal | resolve `void` | fixed rejection on finalization failure |
| embedding | route original, substitute, PREPARE, trace, pinned raw embed | numeric vector | no output reversal; all other gates apply |

No call may expose original/tokenized text through errors, metadata, audit, factory results, or product result metadata.

## 7. Azure egress evidence policy-version binding

### 7.1 Required claim

`AzureEgressPolicyEvidence` gains:

```ts
/** Immutable egress policy revision evaluated by the attestor. Missing, empty, or mismatch rejects. */
readonly policyVersion: string;
```

It is a PHI-free deployment identifier, not policy contents or free text. No default, image-tag inference, or fallback to `deploymentDigest` is permitted.

### 7.2 Signed claims

```ts
export type AzureEgressPolicySignedClaims = Omit<AzureEgressPolicyEvidence, "signature">;
```

`signature.signedClaimsDigest` is the digest of canonical `AzureEgressPolicySignedClaims`, binding `protectedServiceIdentity`, `imageDigest`, `deploymentDigest`, and `policyVersion` together. M3 must exact-match all four expected claims; a valid signature over another policy version is invalid.

This is an authorized evidence-schema expansion. There is no in-package runtime producer. M4 emitters/fixtures add the field before M3 enforcement; reclaim and Q6 do not construct it. Runtime signer/verifier work remains in M4/M3.

## 8. Node engine resolution

### 8.1 Ruling: Node 20 remains supported

The current locked Azure direct dependencies genuinely support Node 20, so GLY-353 does not force Node 22.

1. Pin exact direct versions: `@azure/identity: "4.13.1"`, `@azure/keyvault-keys: "4.10.2"`, and `@azure/storage-file-share: "12.31.0"`.
2. Regenerate the lock without changing those resolutions; verify the full production closure on Node 20.
3. Use `@types/node` major 20 so Node-22-only APIs cannot typecheck accidentally.
4. Keep runtime `engines.node` at `>=20`. CI uses Node `20.20.2` or latest `20.x` not below `20.19.0` because Vite's development-only floor is 20.19.
5. Run `npm ci` with `engine-strict=true`; an incompatible resolution is a hard failure, not an ignored warning.
6. Document that Node-20 support is the exact checked-in graph. Any future Azure upgrade raising the engine floor needs a separate compatibility decision and cannot drift through a caret.

Node 22 remains allowed by `>=20`; it is not required.

### 8.2 Compatibility gate

```text
npm_config_engine_strict=true npm ci
npm run typecheck
npm test
npm run build
npm run build:executables
```

A lock/source oracle asserts exact Azure pins, Node-20 `@types/node`, and no resolved production dependency whose engine excludes the CI Node-20 version.

## 9. Backward compatibility and rollout

1. `createSubstitutionEngine(options?)` retains its exact development bundle, defaults, facade, and behavior.
2. `createProtectedAiProvider(options?)` retains its independent development engine and `DevProtectedAiProvider` result. It is not silently changed to singleton reuse.
3. Legacy `AiProvider`, `DevBoundaryProvider`, and `ProtectedStreamResult` remain unchanged.
4. The runtime root allow-list gains only `createProductionProtectedAiProvider`; type-only exports gain §5 and `AzureEgressPolicySignedClaims`. No wildcard/subpath is added.
5. Reclaim and Q6 retain imports/behavior and both executable targets compile without production dependencies.
6. Root import without Azure credentials, PostgreSQL environment, or network succeeds.
7. Rollout order: publish API/type → update M4 to sign policyVersion → compose singleton and adapters → add product adapter → enable M3 exact-version enforcement.

## 10. Implementation boundaries

- `src/factory.ts`: production types, composition, fixed audit construction, facade.
- `src/index.ts`: one runtime factory and type-only exports.
- `src/core/wrapper.ts`: shared sink-based stream primitive; legacy collection delegates.
- `src/core/protected-ai-provider.ts`: provider-agnostic type-only seams if not in factory; legacy `AiProvider` unchanged.
- `src/coverage/contracts.ts`: required `policyVersion`, signed-claims alias, signature docs.
- `package.json` / lock: exact Azure pins and Node-20 declarations.
- `.github/workflows/ci.yml`: engine-strict Node-20 install.
- `README.md`: production composition and Node support.
- `tests/production-factory.test.ts`: production behavior/capability oracles.
- `type-tests/production-factory.ts` plus `tsconfig.public-api.json`: external-consumer contract included in `npm run typecheck`.
- Existing tests only for additive allow-list/fixtures.

No `CONTRACT/**` file or frozen expectation may be weakened.

## 11. Test oracle plan

### 11.1 API and singleton

1. **ORACLE-PROD-ROOT-IMPORT:** only new factory runtime export; no concrete/raw export.
2. **ORACLE-PROD-TYPE-ADAPTER:** product-local result and stream adapter compiles with no Glassy import.
3. **ORACLE-PROD-NOT-LEGACY-AIPROVIDER:** negative type fixture proves explicit adaptation is required.
4. **ORACLE-PROD-SINGLETON:** canary engine outputs/counters prove all paths use the injected engine and no dev engine.
5. **ORACLE-PROD-NO-DEFAULTS:** negative type fixtures omit each port; runtime cast/missing/throwing-getter matrix rejects fixed with zero calls.
6. **ORACLE-PROD-FACADE:** null prototype, frozen, exact methods, no constructor/capability leak.
7. **ORACLE-PROD-SNAPSHOT:** mutating the top-level dependency object after construction cannot swap ports.

### 11.2 Protected calls

1. **ORACLE-PROD-TEXT:** router sees original PHI canary; provider/trace see only token; caller sees reversed display; audit/errors contain no canary.
2. **ORACLE-PROD-ROUTE-PIN:** rawProvider A but router selects B; only B is invoked once.
3. **ORACLE-PROD-AUDIT-PRIMARY:** PREPARE precedes raw call; exactly one terminal follows.
4. **ORACLE-PROD-AUDIT-SPOOL:** primary unavailable/spool ready permits one egress; both unavailable permits zero.
5. **ORACLE-PROD-STREAM-LIVE:** sink observes reversed chunk 1 before controlled raw stream release.
6. **ORACLE-PROD-STREAM-BACKPRESSURE:** unresolved sink 1 prevents raw chunk 2 advancement.
7. **ORACLE-PROD-STREAM-SINK-FAILURE:** one provider call, one terminal, no later display, fixed error only.
8. **ORACLE-PROD-LEGACY-STREAM:** dev `generateStream()` still returns the same collected result.
9. **ORACLE-PROD-EMBED:** original route; tokenized raw/trace; durable order; numeric-only result.

### 11.3 Evidence, Node, and compatibility

1. **ORACLE-EVIDENCE-POLICY-VERSION-TYPE:** complete evidence/claims compile; `@ts-expect-error` missing policyVersion.
2. **ORACLE-EVIDENCE-SIGNED-CLAIMS:** type equality/excess-property probe proves claims include policyVersion and omit only signature.
3. **ORACLE-NODE20-EXACT-PINS:** inspect manifest/lock exact versions and Node-20 types.
4. **ORACLE-NODE20-ENGINE-STRICT:** clean engine-strict install on Node20 plus typecheck/test/build/build:executables.
5. **ORACLE-NODE20-LOCK-CLOSURE:** fail any resolved production engine excluding CI Node20.
6. **ORACLE-BACKCOMPAT-EXECUTABLES:** Q6/reclaim compile with no factory config.
7. **ORACLE-NO-GLASSY-DEPENDENCY:** zero Glassy imports/dependencies in active source/manifests/type tests.

### 11.4 Evidence contract

Implementation evidence includes raw clean install, all type targets, full suite, both builds, every mutant alone verified-applied RED/restored GREEN, full diff/check/status, and a changed-file allow-list proving no CONTRACT/unrelated change.

## 12. Named mutations

| Mutant | Mutation | RED oracle |
|---|---|---|
| `GLY-353-MUT-FACTORY-REBUILDS-ENGINE` | replace injected engine with dev/new engine | ORACLE-PROD-SINGLETON |
| `GLY-353-MUT-FACTORY-DEV-DEFAULT` | default a required production port | ORACLE-PROD-NO-DEFAULTS |
| `GLY-353-MUT-FACTORY-LEAKS-CAPABILITY` | add engine/raw/router/audit property or prototype | ORACLE-PROD-FACADE |
| `GLY-353-MUT-FACTORY-LIVE-DEPS` | retain/re-read mutable dependency object | ORACLE-PROD-SNAPSHOT |
| `GLY-353-MUT-CONTEXT-BYPASS` | use fixed/dev context | ORACLE-PROD-TEXT |
| `GLY-353-MUT-POLICY-BYPASS` | use fixed/dev policy | ORACLE-PROD-TEXT |
| `GLY-353-MUT-PROJECTOR-BYPASS` | send original options to provider | ORACLE-PROD-TEXT |
| `GLY-353-MUT-ROUTE-TOKENIZED` | route after substitution | ORACLE-PROD-ROUTE-PIN |
| `GLY-353-MUT-ROUTE-IGNORED` | call rawProvider instead of pinned provider | ORACLE-PROD-ROUTE-PIN |
| `GLY-353-MUT-AUDIT-AFTER-EGRESS` | move PREPARE after raw call | ORACLE-PROD-AUDIT-PRIMARY |
| `GLY-353-MUT-AUDIT-DROP-SPOOL` | skip spool fallback | ORACLE-PROD-AUDIT-SPOOL |
| `GLY-353-MUT-TRACE-RAW` | trace original/display text | ORACLE-PROD-TEXT |
| `GLY-353-MUT-STREAM-TOKENIZED` | send provider chunk to display sink | ORACLE-PROD-STREAM-LIVE |
| `GLY-353-MUT-STREAM-NO-BACKPRESSURE` | do not await sink | ORACLE-PROD-STREAM-BACKPRESSURE |
| `GLY-353-MUT-STREAM-BUFFER-ALL` | collect before production sink | ORACLE-PROD-STREAM-LIVE |
| `GLY-353-MUT-STREAM-DOUBLE-SEND` | retry/reinvoke raw stream | ORACLE-PROD-STREAM-SINK-FAILURE |
| `GLY-353-MUT-EMBED-BYPASS` | original embed text or skip route/audit | ORACLE-PROD-EMBED |
| `GLY-353-MUT-DEV-FACTORY-CHANGED` | alter legacy dev semantics | ORACLE-PROD-LEGACY-STREAM + factory smoke |
| `GLY-353-MUT-EVIDENCE-DROP-POLICY-VERSION` | remove/make policyVersion optional | ORACLE-EVIDENCE-POLICY-VERSION-TYPE |
| `GLY-353-MUT-EVIDENCE-DIGEST-OMITS-POLICY-VERSION` | omit it from claims alias | ORACLE-EVIDENCE-SIGNED-CLAIMS |
| `GLY-353-MUT-NODE20-RESTORE-CARET` | restore Azure caret | ORACLE-NODE20-EXACT-PINS |
| `GLY-353-MUT-NODE20-RESOLVE-NODE22` | resolved engine excludes Node20 | ORACLE-NODE20-ENGINE-STRICT/LOCK-CLOSURE |
| `GLY-353-MUT-NODE20-TYPES-22` | restore Node22 types | ORACLE-NODE20-EXACT-PINS |
| `GLY-353-MUT-ROOT-EXPORTS-CONCRETE` | export wrapper/raw/audit runtime | ORACLE-PROD-ROOT-IMPORT |

Equivalent mutants must be strengthened, never deleted or excused by weakening an oracle.

## 13. Acceptance criteria

1. The §5 additive API is root-importable with no Glassy dependency.
2. Exact supplied engine serves text/stream/embed; no hidden engine exists.
3. All production security/durability ports are required and no dev fallback is reachable.
4. Facade is frozen, null-prototype, capability-tight, and product-contract agnostic.
5. Streaming delivers reversed display live, ordered, with awaited backpressure and exactly-one provider/audit semantics.
6. Fixed serializer composes injected primary/spool; both unavailable means zero egress.
7. policyVersion is required and part of signed claims/digest contract.
8. Node20 passes engine-strict clean install, all type targets, tests, and builds on exact compatible Azure resolutions.
9. Dev factories, Q6, reclaim, subpath fence, errors, and frozen CONTRACT tests do not regress.
10. Every `GLY-353-MUT-*` is alone RED, restored, and GREEN.

## 14. Open questions

None for the principal. This spec chooses a direct protected call facade, caller-owned engine singleton, fixed internal audit serializer over injected primary/spool ports, required signed policy-version evidence, and Node-20 support through exact Azure resolutions plus engine-strict CI.
