# Ratified package placement

The principal has decided placement. This is not an open option analysis.

```text
gbs-tools-and-resources/
└── packages/
    ├── case-analysis-engine/
    ├── wc-synthetic-caseload-engine/
    └── phi-substitution-engine/
```

The TypeScript source of truth lives at `gbs-tools-and-resources/packages/phi-substitution-engine`. It is released as one private, immutable, provenance-attested GitHub Package and consumed cross-repository at pinned versions, following the existing `@glass-box-solutions-inc/glassy-shared` pattern.

The exact npm scope must use a Glass Box-controlled GitHub Packages namespace. If `@gbs` is not controlled, the package is published as `@glass-box-solutions-inc/phi-substitution-engine`; source placement and architecture do not change. The package must not be published under two scopes.

The upstream Phileas 4.2 source and thin JVM service also belong in this monorepo under the same package/security ownership, but they produce a container artifact rather than being embedded in the npm tarball. Product repositories contain only framework/persistence/provider adapters and their N1/N7 gates.

Release rules:

1. Path-scoped CODEOWNERS, CI, tags/changelog, SBOM, provenance, mutation evidence, and package-content allow-list are mandatory for this T2 package.
2. Product repositories pin an exact npm version and exact sidecar image digest. Floating production ranges/tags are forbidden.
3. Core exports are explicit. NestJS, Prisma, provider SDK, Langfuse, Sentry, Azure SDK, HTTP client, and Phileas wire code remain in opt-in adapter entry points or product repositories.
4. Persistence migrations are sequenced by product adapters; npm installation never runs a migration.
5. Consumer promotion occurs through ordinary product PRs that run the product's option traversal, DI/import, surface registry, egress lint, and deployment policy tests.
6. Rollback returns both npm package and JVM image only to a previously gated compatible pair; otherwise protected AI remains disabled.

All compute runs on Azure Container Apps environment `cae-gbs-wp`. No GCP dependency, registry, runtime, fallback, or deployment path is permitted for this engine.
