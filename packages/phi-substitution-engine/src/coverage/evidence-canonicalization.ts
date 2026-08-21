import { createHash } from "node:crypto";
import type {
  AzureEgressPolicySignedClaims,
  EgressLoggingPlane,
  LoggingPlaneBodyAttestation,
} from "./contracts";

export type JcsValue =
  | null
  | boolean
  | number
  | string
  | readonly JcsValue[]
  | Readonly<{ [key: string]: JcsValue }>;

export interface NormalizedEnginePolicyConfiguration {
  readonly engineMode: string;
  readonly baaMatrix: JcsValue;
}

const SAFE_VERSION = /^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$/;
const SHA256_VERSION = /^sha256:[0-9a-f]{64}$/;
const EGRESS_PLANES: readonly EgressLoggingPlane[] = [
  "APP_INSIGHTS",
  "CONTAINER_APP_SYSTEM_LOGS",
  "PROVIDER_SDK",
  "PHILEAS_SIDECAR",
  "INGRESS_GATEWAY",
];

function invalid(): never {
  throw new TypeError("INVALID_AZURE_EGRESS_POLICY_CLAIMS");
}

function requireString(value: unknown): string {
  return typeof value === "string" ? value : invalid();
}

function requireLiteral<T extends boolean | string>(
  value: unknown,
  expected: T,
): T {
  return value === expected ? expected : invalid();
}

function isAllowedPlane(value: string): value is EgressLoggingPlane {
  for (let i = 0; i < EGRESS_PLANES.length; i += 1) {
    if (EGRESS_PLANES[i] === value) return true;
  }
  return false;
}

function compareStrings(left: string, right: string): number {
  return left < right ? -1 : left > right ? 1 : 0;
}

function sortedPlanes(
  input: readonly LoggingPlaneBodyAttestation[],
): readonly LoggingPlaneBodyAttestation[] {
  if (!Array.isArray(input)) invalid();
  const copied: LoggingPlaneBodyAttestation[] = [];
  for (let i = 0; i < input.length; i += 1) {
    const candidate = input[i] as unknown;
    if (
      candidate === null ||
      typeof candidate !== "object" ||
      Array.isArray(candidate)
    )
      invalid();
    const plane = requireString((candidate as { plane?: unknown }).plane);
    if (!isAllowedPlane(plane)) invalid();
    requireLiteral(
      (candidate as { bodyLoggingDisabled?: unknown }).bodyLoggingDisabled,
      true,
    );
    copied.push({ plane, bodyLoggingDisabled: true });
  }
  copied.sort((left, right) => compareStrings(left.plane, right.plane));
  for (let i = 1; i < copied.length; i += 1) {
    if (copied[i - 1]?.plane === copied[i]?.plane) invalid();
  }
  return copied;
}

function validateUnicode(value: string): void {
  for (let i = 0; i < value.length; i += 1) {
    const unit = value.charCodeAt(i);
    if (unit >= 0xd800 && unit <= 0xdbff) {
      const next = value.charCodeAt(i + 1);
      if (!(next >= 0xdc00 && next <= 0xdfff)) invalid();
      i += 1;
    } else if (unit >= 0xdc00 && unit <= 0xdfff) {
      invalid();
    }
  }
}

/** RFC 8785/JCS serialization for already-normalized JSON values. */
function canonicalizeJcs(value: JcsValue, ancestors: Set<object>): string {
  if (value === null) return "null";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") {
    if (!Number.isFinite(value)) invalid();
    return JSON.stringify(value);
  }
  if (typeof value === "string") {
    validateUnicode(value);
    return JSON.stringify(value);
  }
  if (typeof value !== "object") invalid();
  if (ancestors.has(value)) invalid();
  ancestors.add(value);
  try {
    if (Array.isArray(value)) {
      const parts: string[] = [];
      for (let i = 0; i < value.length; i += 1) {
        parts.push(canonicalizeJcs(value[i] as JcsValue, ancestors));
      }
      return `[${parts.join(",")}]`;
    }

    const prototype = Object.getPrototypeOf(value);
    if (prototype !== Object.prototype && prototype !== null) invalid();
    const keys = Object.keys(value).sort(compareStrings);
    const parts: string[] = [];
    for (let i = 0; i < keys.length; i += 1) {
      const key = keys[i];
      if (key === undefined) invalid();
      validateUnicode(key);
      const member = (value as Readonly<Record<string, JcsValue>>)[key];
      if (member === undefined) invalid();
      parts.push(
        `${JSON.stringify(key)}:${canonicalizeJcs(member, ancestors)}`,
      );
    }
    return `{${parts.join(",")}}`;
  } finally {
    ancestors.delete(value);
  }
}

function sha256(bytes: Uint8Array): string {
  return `sha256:${createHash("sha256").update(bytes).digest("hex")}`;
}

function canonicalClaims(input: AzureEgressPolicySignedClaims): JcsValue {
  try {
    const egressPolicyVersion = requireString(input.egressPolicyVersion);
    const enginePolicyVersion = requireString(input.enginePolicyVersion);
    if (
      !SAFE_VERSION.test(egressPolicyVersion) ||
      !SHA256_VERSION.test(enginePolicyVersion)
    )
      invalid();

    return {
      environment: requireLiteral(input.environment, "cae-gbs-wp"),
      protectedServiceIdentity: requireString(input.protectedServiceIdentity),
      providerHostsReachableOnlyByProtectedIdentity: requireLiteral(
        input.providerHostsReachableOnlyByProtectedIdentity,
        true,
      ),
      phileasHasPublicIngress: requireLiteral(
        input.phileasHasPublicIngress,
        false,
      ),
      phileasHasGcpRoute: requireLiteral(input.phileasHasGcpRoute, false),
      requestBodyLoggingDisabled: requireLiteral(
        input.requestBodyLoggingDisabled,
        true,
      ),
      checkedAt: requireString(input.checkedAt),
      deploymentDigest: requireString(input.deploymentDigest),
      imageDigest: requireString(input.imageDigest),
      issuedAt: requireString(input.issuedAt),
      expiresAt: requireString(input.expiresAt),
      nonce: requireString(input.nonce),
      denyByDefaultEgress: requireLiteral(input.denyByDefaultEgress, true),
      loggingPlanes: sortedPlanes(input.loggingPlanes).map(
        (plane): JcsValue => ({
          plane: plane.plane,
          bodyLoggingDisabled: true,
        }),
      ),
      egressPolicyVersion,
      enginePolicyVersion,
    };
  } catch {
    return invalid();
  }
}

/** Canonical RFC 8785 UTF-8 bytes for the exact signed evidence claims. */
export function canonicalizeAzureEgressPolicySignedClaims(
  claims: AzureEgressPolicySignedClaims,
): Uint8Array {
  try {
    return new TextEncoder().encode(
      canonicalizeJcs(canonicalClaims(claims), new Set<object>()),
    );
  } catch {
    return invalid();
  }
}

/** `sha256:<lowercase hex>` digest bound by `EgressEvidenceSignature`. */
export function computeAzureEgressPolicySignedClaimsDigest(
  claims: AzureEgressPolicySignedClaims,
): string {
  return sha256(canonicalizeAzureEgressPolicySignedClaims(claims));
}

/** Computes the consumer boot-config digest after its schema has normalized mode and BAA matrix. */
export function computeEnginePolicyVersion(
  config: NormalizedEnginePolicyConfiguration,
): string {
  try {
    if (!SAFE_VERSION.test(requireString(config.engineMode))) invalid();
    const canonical = canonicalizeJcs(
      { engineMode: config.engineMode, baaMatrix: config.baaMatrix },
      new Set<object>(),
    );
    return sha256(new TextEncoder().encode(canonical));
  } catch {
    return invalid();
  }
}
