import { describe, expect, it } from "vitest";
import type {
  AzureEgressPolicySignedClaims,
  LoggingPlaneBodyAttestation,
} from "../src/coverage/contracts";
import {
  canonicalizeAzureEgressPolicySignedClaims,
  computeAzureEgressPolicySignedClaimsDigest,
  computeEnginePolicyVersion,
} from "../src/coverage/evidence-canonicalization";

const planes: readonly LoggingPlaneBodyAttestation[] = [
  { plane: "PROVIDER_SDK", bodyLoggingDisabled: true },
  { plane: "APP_INSIGHTS", bodyLoggingDisabled: true },
];

function claims(loggingPlanes = planes): AzureEgressPolicySignedClaims {
  return {
    environment: "cae-gbs-wp",
    protectedServiceIdentity: "svc-prod",
    providerHostsReachableOnlyByProtectedIdentity: true,
    phileasHasPublicIngress: false,
    phileasHasGcpRoute: false,
    requestBodyLoggingDisabled: true,
    checkedAt: "2026-08-18T00:00:00.000Z",
    deploymentDigest: "sha256:deployment",
    imageDigest: "sha256:image",
    issuedAt: "2026-08-18T00:00:00.000Z",
    expiresAt: "2026-08-18T01:00:00.000Z",
    nonce: "nonce-1",
    denyByDefaultEgress: true,
    loggingPlanes,
    egressPolicyVersion: "egress-2026-08-18",
    enginePolicyVersion:
      "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  };
}

describe("GLY-353 RFC 8785 evidence canonicalization", () => {
  it("ORACLE-EVIDENCE-JCS-KNOWN-ANSWER: keys and logging planes canonicalize deterministically", () => {
    const canonical = new TextDecoder().decode(
      canonicalizeAzureEgressPolicySignedClaims(claims()),
    );
    expect(canonical).toBe(
      '{"checkedAt":"2026-08-18T00:00:00.000Z","denyByDefaultEgress":true,"deploymentDigest":"sha256:deployment","egressPolicyVersion":"egress-2026-08-18","enginePolicyVersion":"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","environment":"cae-gbs-wp","expiresAt":"2026-08-18T01:00:00.000Z","imageDigest":"sha256:image","issuedAt":"2026-08-18T00:00:00.000Z","loggingPlanes":[{"bodyLoggingDisabled":true,"plane":"APP_INSIGHTS"},{"bodyLoggingDisabled":true,"plane":"PROVIDER_SDK"}],"nonce":"nonce-1","phileasHasGcpRoute":false,"phileasHasPublicIngress":false,"protectedServiceIdentity":"svc-prod","providerHostsReachableOnlyByProtectedIdentity":true,"requestBodyLoggingDisabled":true}',
    );
    expect(computeAzureEgressPolicySignedClaimsDigest(claims())).toBe(
      "sha256:fee98d2eb9bb20531ebc8a96848e65235f35659c10de00220adc1b4e3d65d248",
    );

    const reversed = [...planes].reverse();
    expect(computeAzureEgressPolicySignedClaimsDigest(claims(reversed))).toBe(
      computeAzureEgressPolicySignedClaimsDigest(claims()),
    );
  });

  it("ORACLE-EVIDENCE-JCS-VERSION-BINDING: either policy version changes the signed digest", () => {
    const baseline = claims();
    expect(
      computeAzureEgressPolicySignedClaimsDigest({
        ...baseline,
        egressPolicyVersion: "egress-2026-08-19",
      }),
    ).not.toBe(computeAzureEgressPolicySignedClaimsDigest(baseline));
    expect(
      computeAzureEgressPolicySignedClaimsDigest({
        ...baseline,
        enginePolicyVersion:
          "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      }),
    ).not.toBe(computeAzureEgressPolicySignedClaimsDigest(baseline));
  });

  it("ORACLE-EVIDENCE-JCS-DUPLICATE-PLANE: duplicate plane ids reject before hashing", () => {
    expect(() =>
      computeAzureEgressPolicySignedClaimsDigest(
        claims([
          { plane: "APP_INSIGHTS", bodyLoggingDisabled: true },
          { plane: "APP_INSIGHTS", bodyLoggingDisabled: true },
        ]),
      ),
    ).toThrowError("INVALID_AZURE_EGRESS_POLICY_CLAIMS");
  });

  it("ORACLE-EVIDENCE-PLANE-LOGGING-ENABLED: an enabled body-logging plane rejects", () => {
    const loggingPlanes = [
      {
        plane: "APP_INSIGHTS",
        bodyLoggingDisabled: false,
      },
    ] as unknown as readonly LoggingPlaneBodyAttestation[];
    expect(() =>
      canonicalizeAzureEgressPolicySignedClaims(claims(loggingPlanes)),
    ).toThrowError("INVALID_AZURE_EGRESS_POLICY_CLAIMS");
  });

  it("ORACLE-EVIDENCE-ENGINE-POLICY-NORMALIZATION: normalized mode and BAA matrix bind under JCS", () => {
    const a = computeEnginePolicyVersion({
      engineMode: "production",
      baaMatrix: {
        providers: { azure: true, unprotected: false },
        default: "deny",
      },
    });
    const b = computeEnginePolicyVersion({
      baaMatrix: {
        default: "deny",
        providers: { unprotected: false, azure: true },
      },
      engineMode: "production",
    });
    expect(a).toBe(b);
    expect(a).toMatch(/^sha256:[0-9a-f]{64}$/);
    expect(
      computeEnginePolicyVersion({
        engineMode: "production",
        baaMatrix: {
          default: "deny",
          providers: { azure: false, unprotected: false },
        },
      }),
    ).not.toBe(a);
  });
});
