# Frozen Phase-1 engine contract

This directory is the architecture and red-test oracle for `gbs-tools-and-resources/packages/phi-substitution-engine` and its Phileas 4.2 Azure sidecar.

Start with:

1. `ADR-001-phileas-vs-greenfield.md` — Stream J/J1 tool decision and source assessment.
2. `CONTRACT-phase1.md` — normative ownership line, invariants, flow, retention, audit spool, and enforcement.
3. `MODULE-DEPENDENCY-GRAPH.md` — parallel spark tracks and serialized integration chain.
4. `PACKAGE-PLACEMENT.md` — principal-ratified monorepo/package/deployment placement.

The TypeScript files are declarations and ports, not a partial implementation. Core has no framework, provider SDK, HTTP, Phileas, Azure SDK, Prisma, tracing, or error-monitoring dependency. Vendor/product dependencies live behind explicit adapters.

The tests intentionally use `tests/implementation-under-test.ts` as their one wiring seam. Its loaders throw `IMPLEMENTATION_REQUIRED` until spark modules attach production constructors. Implementers replace loaders; they do not weaken mutation IDs, test IDs, canaries, fixtures, or assertions.

Suites are partitioned by independently buildable module:

- `variants.test.ts` — allow-listed deterministic expansion (L10);
- `collision.test.ts` — Unicode boundaries, distinctiveness, citation, overlap, ambiguity, offsets (L3/C1–C8);
- `tokens.test.ts` — stable assignments, source escape, bounded reversal, stream holdback, tenant lookup (N5/L1/L4/L6/L8);
- `dictionary.test.ts` — version/cache/compilation/orchestration and Phileas prepared-policy isolation (N4/L2/L3/L8/L9/L12);
- `detector-redactor-port.test.ts` — Phileas/Azure replaceability, version/offset/deadline, phase-1-disabled behavior (N4/L7/L9/L12);
- `provider-boundary.test.ts` — all provider methods, safe trace ordering, option traversal, original-content BAA routing (N1/N2/L5/L11);
- `audit.test.ts` — exact metadata schema, one logical event, primary outbox, encrypted local spool (N3/N4);
- `evaluation-claims.test.ts` — per-class evidence, latency, copy/image boundary (N6/L7/L9);
- `coverage-n7.test.ts` — architecture, egress-lint, registry drift, and carve-out structure (N7).

Consumer repositories must additionally run real framework/import/DI, provider-host, live file/symbol registry, and Azure deployment-policy checks. A framework-free npm package cannot prove those boundaries on its own.

All compute is Azure Container Apps `cae-gbs-wp`; zero GCP.
