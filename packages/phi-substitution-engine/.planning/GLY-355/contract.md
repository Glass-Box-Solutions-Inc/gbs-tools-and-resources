# GLY-355 — production original-egress authorizer frozen contract

**Status:** FROZEN

**Parent:** GLY-335

**Base implementation:** `ce554c4`

**Frozen:** 2026-08-18

## 1. Purpose and boundary

This additive package-root capability authorizes a single operation to send an original-content
class to one policy-approved destination. It transports authorization metadata only. Original text,
case identifiers, and audio bytes are neither inputs nor outputs of this contract.

## 2. Public package-root types

```ts
export type OriginalEgressProtocol = "HTTPS" | "WSS";
export type OriginalEgressContentClass = "case-identifier" | "tts-text" | "audio-stream";

export interface OriginalEgressPolicyQuery {
  readonly context: MatterAiContext;
  readonly destinationKey: string;
  readonly protocol: OriginalEgressProtocol;
  readonly contentClass: OriginalEgressContentClass;
  readonly enginePolicyVersion: string;
}

export interface AuthorizedOriginalEgressDecision {
  readonly kind: "AUTHORIZED_ORIGINAL";
  readonly decisionId: string;
  readonly evidenceId: string;
  readonly destinationKey: string;
  readonly protocol: OriginalEgressProtocol;
  readonly contentClass: OriginalEgressContentClass;
  readonly enginePolicyVersion: string;
  readonly expiresAt: string;
}

export interface OriginalEgressPolicyPort {
  requireAuthorizedOriginalEgress(
    query: OriginalEgressPolicyQuery,
  ): Promise<AuthorizedOriginalEgressDecision>;
}

export interface OriginalEgressAuthorizationRequest extends OriginalEgressPolicyQuery {
  readonly purpose: AiOperation;
}

export interface OriginalEgressAuthorization {
  readonly tenantId: MatterAiContext["tenantId"];
  readonly matterId: MatterAiContext["matterId"];
  readonly operationId: MatterAiContext["operationId"];
  readonly attemptId: MatterAiContext["attemptId"];
  readonly destinationKey: string;
  readonly protocol: OriginalEgressProtocol;
  readonly contentClass: OriginalEgressContentClass;
  readonly decisionId: string;
  readonly evidenceId: string;
  readonly enginePolicyVersion: string;
  readonly expiresAt: string;
  finalize(outcome: PhiAuditOutcome, failureCode?: PhiEngineFailureCode): Promise<void>;
  toJSON(): never;
}

export interface ProtectedOriginalEgressAuthorizer {
  authorizeOriginalEgress(
    request: OriginalEgressAuthorizationRequest,
  ): Promise<OriginalEgressAuthorization>;
}

export interface CreateProductionProtectedOriginalEgressAuthorizerOptions {
  readonly engineVersion: EngineVersion;
  readonly enginePolicyVersion: string;
  readonly policy: OriginalEgressPolicyPort;
  readonly auditPrimary: AuditPrimaryStore;
  readonly auditSpool: EncryptedAuditSpool;
  readonly clock?: () => string;
}

export function createProductionProtectedOriginalEgressAuthorizer(
  options: CreateProductionProtectedOriginalEgressAuthorizerOptions,
): ProtectedOriginalEgressAuthorizer;
```

## 3. Binding semantics

1. No original text, case-identifier content, or audio bytes enter or leave this contract.
2. No caller-controlled `baaSatisfied`, `allowOriginal`, or equivalent permissive boolean exists.
3. A returned decision must exactly match `destinationKey`, `protocol`, `contentClass`, and
   `enginePolicyVersion`; otherwise authorization rejects.
4. Missing, expired, mismatched, or denied evidence rejects before authorization.
5. Durable metadata-only audit PREPARE completes before `authorizeOriginalEgress()` resolves.
6. Authorization is non-serializable, scoped to one operation/attempt, and finalize-once; a second
   successful finalization attempt rejects.
7. Simultaneous primary and spool PREPARE failure rejects with `AUDIT_DURABILITY_UNAVAILABLE`.
8. Selective authorization never changes `TrustedMatterAiPolicy.mode` to `OFF_APPROVED`.
9. The production factory has no permissive development fallback.
10. All public types and the factory export through package export `"."` only.

## 4. Amendment 2026-08-18 — Opus review rulings

### 4.1 One authorization per attempt

The authorizer closure reserves `attemptId` before any asynchronous policy or audit operation. A
concurrent or later authorization request for the same attempt rejects before policy or PREPARE, so
`DurablePhiAuditEmitter.#inFlight` cannot be overwritten. A reservation is released only when the
attempt fails before durable PREPARE. Once PREPARE succeeds, the reservation remains for the
authorizer lifetime, including after terminal finalization. The shared emitter's one-shot semantics
remain unchanged.

### 4.2 Published API coverage

The public-API TypeScript fixture constructs the production options, calls
`authorizeOriginalEgress`, and proves with `@ts-expect-error` that original content cannot occupy the
request. README documents the production capability and its lifecycle.

### 4.3 Destination grammar

`destinationKey` must match `^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$`. Invalid destination metadata
rejects before policy access or PREPARE.

### 4.4 Retryable durable finalization

The handle rejects concurrent finalization, but sets its permanent `finalized` latch only after the
emitter reports a successful durable terminal write. A transient durability failure is therefore
retryable. The emitter, not the handle, owns durable terminal idempotency; after successful
finalization, every later call rejects.

## 5. Non-goals

- No original-content transport, provider adapter, BAA router, or policy-mode mutation is added.
- No changes are made to `DurablePhiAuditEmitter` one-shot or reconciliation semantics.
- No development factory or fallback is added.
- No subpath export is added.
