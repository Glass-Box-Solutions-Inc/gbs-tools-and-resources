# Threat model — trust boundary and out-of-scope adversaries

Additive to the frozen `CONTRACT-phase1.md`. Ratified by the principal (Alex) on
2026-08-12 under GLY-336, resolving the M1 cross-family gate's systemic finding.

## What the engine defends (in scope)

The N-invariants (`CONTRACT-phase1.md §5`), above all **N2 — no raw PHI/PII reaches a
provider, trace, error, job, audit, or shared cache**, hold against **accidental egress**:
the trusted consumer uses the engine as intended and does not tamper with the JavaScript
realm the engine runs in. Within that boundary the engine is hardened against realistic
mistakes and against a consumer that pokes at the *returned* surface, including:

- forgeable-wrapper / constructor-recovery attacks on the objects the factories return
  (facades are frozen, null-prototype, expose only interface methods — `factory.ts`);
- reflective enumeration of reversal maps / case-truth stores (`#private` fields, not
  TS-`private`; no list-all/enumerate on any port — §7);
- registering a PHI-bearing role on the token grammar's allow-list (`frozenRoleSet` is
  write-immutable **and** its membership read uses a null-prototype record, not a
  poisonable `Set.prototype.has` — `tokens/grammar.ts`).

## What is explicitly OUT of scope

**A first-party consumer that replaces or poisons the JavaScript realm's global
intrinsics** — e.g. reassigning `Set.prototype.has`, `Map.prototype.get`,
`Object.getPrototypeOf`, `Array.prototype[Symbol.iterator]`, `JSON.stringify`, or any
built-in the engine transitively relies on — is **out of scope for N2 and every other
invariant.**

Rationale (why this is a principled boundary, not a gap):

1. **The consumer already holds the plaintext.** The engine's caller is trusted
   application code that *supplies* the raw case-truth values (`canonicalDisplayValue`,
   approved aliases) as input. Code that wanted to exfiltrate that PHI does not need to
   defeat the engine — it holds the plaintext and can send it anywhere directly. Defeating
   an internal `Set` to make the engine leak what the caller already has adds no capability.
2. **Realm hostility is unwinnable for any in-realm library.** Code that can reassign a
   global intrinsic runs in the same realm as the engine and can equally replace the
   engine's own methods, the provider it calls, its audit sink, or the crypto it uses. No
   library can enforce a security property against an adversary who controls the primitives
   the library is built from. This is the same boundary the frozen contract already draws
   at §7 ("branding is not an authorization mechanism; trusted adapters validate and
   construct brands").
3. **The alternative is unbounded whack-a-mole with no positive invariant.** Every
   security-relevant `Set`/`Map` membership or dedup check in the pre-egress path is
   equally poisonable; hardening each one individually never terminates and yields no
   provable boundary property.

Consequence: internal membership/dedup structures (e.g. the dictionary compiler's
`seen` dedup in `dictionary/compiler.ts`) are **not** required to be poison-resistant.
The `frozenRoleSet` read-poison hardening (GLY-336 R4) is **retained as defense-in-depth**
— a cheap win on the highest-value allow-list — but it is *beyond* the required boundary
and does not establish a general obligation to poison-proof internal collections.

## Applies program-wide

This boundary is the standing threat model for the whole GLY-335 productionization program
(M1–M5). M2–M5 durable adapters and consumers inherit it: they defend accidental egress and
returned-surface tampering, and they do **not** defend against first-party realm poisoning.
