/**
 * N7 enforcement layer 4 (CONTRACT §9.4 surface-registry drift).
 *
 * Every registry file/symbol must exist in the live discovered tree and be
 * classified as exactly one of engine-covered or reviewed carve-out. Discovery
 * of an unregistered call site, a registered symbol that was deleted/renamed
 * without a registry change (drift), a surface classified twice, or an expired
 * carve-out, all fail.
 */
import type {
  DiscoveredEgressSite,
  EgressSurfaceRegistry,
  SourceSymbolRef,
  SurfaceRegistryVerifier,
} from "./contracts";

type DriftCode =
  | "UNREGISTERED_EGRESS"
  | "MULTIPLY_CLASSIFIED_EGRESS"
  | "STALE_REGISTRY_SYMBOL"
  | "EXPIRED_CARVE_OUT";

interface DriftDiagnostic {
  readonly code: DriftCode;
  readonly surfaceId: string | null;
  readonly source: SourceSymbolRef;
}

/** Structural identity of an egress site: repository + file + symbol. */
export function sameSource(a: SourceSymbolRef, b: SourceSymbolRef): boolean {
  return (
    a.repository === b.repository && a.file === b.file && a.symbol === b.symbol
  );
}

export interface StaticSurfaceRegistryVerifierOptions {
  /** Injectable clock so expiry checks are deterministic under test. */
  readonly now?: () => number;
}

export class StaticSurfaceRegistryVerifier implements SurfaceRegistryVerifier {
  private readonly now: () => number;

  constructor(options: StaticSurfaceRegistryVerifierOptions = {}) {
    this.now = options.now ?? (() => Date.now());
  }

  verify(
    input: Readonly<{
      registry: EgressSurfaceRegistry;
      discovered: readonly DiscoveredEgressSite[];
    }>,
  ): Readonly<{ ok: boolean; diagnostics: readonly DriftDiagnostic[] }> {
    const { registry, discovered } = input;
    const diagnostics: DriftDiagnostic[] = [];

    // Every discovered egress site must map to exactly one registry surface.
    for (const site of discovered) {
      const matches = registry.surfaces.filter((surface) =>
        sameSource(surface.source, site.source),
      );
      if (matches.length === 0) {
        diagnostics.push({
          code: "UNREGISTERED_EGRESS",
          surfaceId: null,
          source: site.source,
        });
      } else if (matches.length > 1) {
        diagnostics.push({
          code: "MULTIPLY_CLASSIFIED_EGRESS",
          surfaceId: matches[0]?.id ?? null,
          source: site.source,
        });
      }
    }

    // Every registered surface must still exist in the live discovered tree;
    // a deleted/renamed symbol whose registry row survived is drift.
    for (const surface of registry.surfaces) {
      const live = discovered.some((site) =>
        sameSource(site.source, surface.source),
      );
      if (!live) {
        diagnostics.push({
          code: "STALE_REGISTRY_SYMBOL",
          surfaceId: surface.id,
          source: surface.source,
        });
      }
    }

    // Reviewed carve-outs may not be past their review expiry.
    const now = this.now();
    for (const surface of registry.surfaces) {
      if (surface.classification !== "REVIEWED_CARVE_OUT") continue;
      if (surface.expiresAt === null) continue;
      const expiry = Date.parse(surface.expiresAt);
      if (Number.isFinite(expiry) && expiry <= now) {
        diagnostics.push({
          code: "EXPIRED_CARVE_OUT",
          surfaceId: surface.id,
          source: surface.source,
        });
      }
    }

    return { ok: diagnostics.length === 0, diagnostics };
  }
}
