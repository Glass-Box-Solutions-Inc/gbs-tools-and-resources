/**
 * Phase-1 matter dictionary compiler, cache, version coordinator, and match-time
 * orchestration (CONTRACT-phase1 §3.1.2, §5 L2/L3/L8/L9/L12, §8).
 *
 * This layer-2 module COMPOSES three already-frozen leaves — it never re-invents
 * them:
 *   - `../variants`  : deterministic, allow-listed surface-form expansion (L10);
 *   - `../tokens`    : stable subject/role token allocation and grammar (L1/L6);
 *   - `../collision` : NFKC normalization, C1–C8, and dictionary-over-detector
 *                      precedence (L3/L12).
 *
 * On top of them it owns: the Aho–Corasick automaton, the tenant-scoped compiled
 * cache, the version/outbox coordinator that rejects BUILDING/FAILED/stale/
 * wrong-tenant versions, and the fail-closed egress gate.
 */
export * from "./errors";
export * from "./aho-corasick";
export * from "./normalize";
export * from "./compiled-dictionary";
export * from "./compiler";
export * from "./cache";
export * from "./version-coordinator";
export * from "./token-port";
export * from "./tokenize";
export * from "./orchestrator";
export * from "./prepared-policy";
export type * from "./contracts";
