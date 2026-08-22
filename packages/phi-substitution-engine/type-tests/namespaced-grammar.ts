/**
 * GLY-373 OR-GLY373-08 — the PUBLIC TYPE surface, imported from the package root ONLY.
 *
 * This file must import nothing but `../src/index`: reaching into an internal module would prove
 * something about the internals rather than about what a consumer can actually name, which is the
 * whole question. It is compiled by `tsconfig.public-api.json` as part of `npm run typecheck`.
 */
import type { ParsedToken, TrustedMatterAiPolicy } from "../src/index";

// ---------------------------------------------------------------------------------------------
// All FOUR `detectorRequirement` literals are assignable to the published policy type.
// ---------------------------------------------------------------------------------------------
type DetectorRequirement = TrustedMatterAiPolicy["detectorRequirement"];

const canonical: DetectorRequirement = "DETERMINISTIC_STRUCTURED_ONLY";
/** The DEPRECATED alias — retained for pin compatibility (AMB-GLY373-05). */
const alias: DetectorRequirement = "DISABLED_PHASE_1";
const suppressed: DetectorRequirement = "STRUCTURED_DETECTION_OFF";
const required: DetectorRequirement = "REQUIRED";
void canonical;
void alias;
void suppressed;
void required;

// An ARBITRARY string is NOT assignable — the union stays closed, so a consumer cannot smuggle an
// unrecognised (or future) value past the type system and rely on runtime leniency.
// @ts-expect-error an arbitrary string is not a detectorRequirement
const rejected: DetectorRequirement = "NOT_A_VALUE";
void rejected;

// @ts-expect-error the widened `string` type is not assignable either
const widened: DetectorRequirement = "REQUIRED" as string;
void widened;

// ---------------------------------------------------------------------------------------------
// `ParsedToken`'s `valid` arm exposes `namespace`, and it is REQUIRED, not optional.
// ---------------------------------------------------------------------------------------------
type ValidToken = Extract<ParsedToken, { kind: "valid" }>;
type MalformedToken = Extract<ParsedToken, { kind: "malformed" }>;

declare const parsed: ValidToken;
const namespace: string | null = parsed.namespace;
void namespace;

/**
 * The field is REQUIRED. If it were optional, `undefined` would be assignable here — and that is
 * exactly the silent-ignore failure mode §3.1 rejects: a consumer or internal reader could omit it
 * and treat a namespaced DETECTOR token as an AUTHORITY token, defeating the invariant the field
 * exists to carry. This `@ts-expect-error` is what makes "required" a compile-time fact rather
 * than a comment.
 */
// @ts-expect-error `namespace` is required on the valid arm, so this object literal is incomplete
const incomplete: ValidToken = {
  kind: "valid",
  token: parsed.token,
  role: parsed.role,
  sequence: null,
};
void incomplete;

// The new malformed reason is part of the published union.
const badNamespace: MalformedToken["reason"] = "BAD_NAMESPACE";
void badNamespace;

// ---------------------------------------------------------------------------------------------
// NO new capability is nameable from the root: the namespace derivation, the length-prefix
// encoder, the conflict sentinel, and any detector seam all stay internal (OR-08 / MUT-17).
// ---------------------------------------------------------------------------------------------
import type * as Root from "../src/index";

type RootKeys = keyof typeof Root;
type Forbidden =
  | "deriveDetectorNamespace"
  | "DETECTOR_NAMESPACE_HEX_LENGTH"
  | "REVERSAL_CANONICAL_CONFLICT"
  | "REVERSAL_CANONICAL_CONFLICT_DETAIL"
  | "assertTrustedContextIdShape"
  | "missingTrustedContextError"
  | "BracketTokenGrammar"
  | "detectStructuredIdentifiers";

/** Resolves to `never` only while NONE of the forbidden names is a root export. */
type LeakedRootCapabilities = Extract<RootKeys, Forbidden>;
const noLeakedCapabilities: LeakedRootCapabilities extends never
  ? true
  : false = true;
void noLeakedCapabilities;
