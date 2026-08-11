/**
 * Exhaustive, fail-closed provider-option projector (CONTRACT-phase1 §3.1.4,
 * §4.1 step 4, invariant L5).
 *
 * The projector walks Glassy's generate/embed option union and turns every
 * text-bearing field into a uniquely-pathed `TextSegment`. Traversal is
 * EXHAUSTIVE and FAIL-CLOSED: an unknown top-level field that could carry text
 * (a string, or a nested object/array) throws `UNCLASSIFIED_PROVIDER_FIELD`
 * before any egress rather than passing it through unprotected. Numbers and
 * booleans are non-text sampling knobs and are preserved untouched.
 *
 * `rebuild` reconstructs the option object from exactly one tokenized value per
 * classified segment path, so the raw provider only ever sees tokenized text.
 */
import type { TextSegment, TextSegmentKind, TokenizedTextSegment } from "./contracts";
import { PhiEngineError } from "./errors";
import type { AiProviderOptionProjector, ClassifiedProviderOptions } from "./protected-ai-provider";

export interface BoundaryContentPart {
  readonly type: string;
  readonly text: string;
}

export interface BoundaryMessage {
  readonly role: string;
  readonly content: readonly BoundaryContentPart[];
}

export interface BoundaryTool {
  readonly name: string;
  readonly description: string;
}

/** A concrete mirror of Glassy's text-bearing generate/embed options. */
export interface BoundaryGenerateOptions {
  readonly system?: string;
  readonly messages?: readonly BoundaryMessage[];
  readonly tools?: readonly BoundaryTool[];
  readonly embeddingText?: string;
}

const KNOWN_TOP_LEVEL_KEYS: ReadonlySet<string> = new Set([
  "system",
  "messages",
  "tools",
  "embeddingText",
  // Non-text sampling knobs that are explicitly classified as carrying no PHI.
  "temperature",
  "maxTokens",
  "topP",
  "stream",
  "model",
]);

const NON_TEXT_KNOB_KEYS: ReadonlySet<string> = new Set([
  "temperature",
  "maxTokens",
  "topP",
  "stream",
  "model",
]);

/**
 * Provider-visible message roles are a CLOSED enum, dispatched verbatim. Validating against a
 * fixed allow-list (not a permissive character pattern) is what stops a PHI value — even a
 * legal-identifier-shaped one like `Alice_Smith` — from riding in a role slot (L5 fail-closed).
 */
const ALLOWED_MESSAGE_ROLES: ReadonlySet<string> = new Set([
  "system",
  "user",
  "assistant",
  "tool",
  "developer",
]);

/** Provider-visible content-part types are likewise a closed enum. */
const ALLOWED_CONTENT_TYPES: ReadonlySet<string> = new Set([
  "text",
  "tool_result",
  "tool_use",
  "image",
  "document",
  "thinking",
]);

/**
 * A tool NAME is a developer-defined structural identifier (not case truth), but it is still
 * provider-visible, so it must be a conservative identifier — never free text that could carry a
 * PHI canary through the name slot (L5 fail-closed).
 */
const PROVIDER_VISIBLE_STRUCTURAL_STRING = /^[A-Za-z0-9_.:-]+$/u;

/** Expected runtime type of each non-text sampling knob. A knob present with any OTHER type —
 *  above all an object/array that could smuggle PHI text through a numeric/boolean slot — fails
 *  closed rather than reaching the provider unclassified (L5). */
const NON_TEXT_KNOB_TYPES: ReadonlyMap<string, "number" | "boolean" | "string"> = new Map([
  ["temperature", "number"],
  ["maxTokens", "number"],
  ["topP", "number"],
  ["stream", "boolean"],
  ["model", "string"],
]);

function assertAllowedEnum(value: string, allowed: ReadonlySet<string>, path: string): void {
  if (!allowed.has(value)) {
    throw new PhiEngineError("UNCLASSIFIED_PROVIDER_FIELD", undefined, {
      unvalidatedProviderString: path,
    });
  }
}

function assertStructuralProviderString(value: unknown, path: string): void {
  // A non-string value must fail closed BEFORE the regex: `RegExp.test` coerces via `toString`, so
  // an object whose `toString()` returns a benign token (e.g. `"safe_tool"`) would pass the pattern
  // and then be copied RAW to the provider (L5). Only a genuine string is a valid provider-visible
  // structural identifier.
  if (typeof value !== "string" || !PROVIDER_VISIBLE_STRUCTURAL_STRING.test(value)) {
    throw new PhiEngineError("UNCLASSIFIED_PROVIDER_FIELD", undefined, {
      unvalidatedProviderString: path,
    });
  }
}

function kindForRole(role: string): TextSegmentKind {
  if (role === "system") return "system";
  if (role === "tool") return "tool";
  return "user";
}

interface CollectedSegment {
  readonly segment: TextSegment;
  /** Applies the tokenized value back into a mutable draft of the options. */
  readonly write: (draft: MutableOptions, tokenized: string) => void;
}

interface MutableOptions {
  system?: string;
  messages?: { role: string; content: { type: string; text: string }[] }[];
  tools?: { name: string; description: string }[];
  embeddingText?: string;
  [key: string]: unknown;
}

/**
 * Enforces L5: every reachable text field is classified, and any unclassified
 * text-bearing top-level field fails closed before egress. The list of skipped
 * fields is deliberately absent — omitting a known field here is exactly the
 * "new text option silently egresses" regression the invariant forbids.
 */
export class StructuralOptionsProjector
  implements AiProviderOptionProjector<BoundaryGenerateOptions>
{
  public classify(options: BoundaryGenerateOptions): ClassifiedProviderOptions<BoundaryGenerateOptions> {
    // Snapshot the caller's options ONCE into an inert, getter-free object; every read below (and
    // the rebuild) uses the snapshot, so a getter cannot pass validation and then egress a
    // different, PHI-laden value (TOCTOU / L5 fail-closed).
    const snap = snapshotBoundaryOptions(options);
    const raw = snap as unknown as Record<string, unknown>;
    const collected: CollectedSegment[] = [];

    // L5: fail closed on ANY unknown, potentially text-bearing top-level field.
    for (const key of Object.keys(raw)) {
      if (!KNOWN_TOP_LEVEL_KEYS.has(key)) {
        const value = raw[key];
        const textBearing =
          typeof value === "string" || (typeof value === "object" && value !== null);
        if (textBearing) {
          throw new PhiEngineError("UNCLASSIFIED_PROVIDER_FIELD", undefined, {
            unclassifiedField: key,
          });
        }
      }
    }

    // L5: a KNOWN non-text knob present with an unexpected runtime type (e.g. an object that
    // could smuggle PHI text through a numeric/boolean "temperature"/"stream" slot) fails closed.
    for (const [knob, expected] of NON_TEXT_KNOB_TYPES) {
      const value = raw[knob];
      if (value !== undefined && value !== null && typeof value !== expected) {
        throw new PhiEngineError("UNCLASSIFIED_PROVIDER_FIELD", undefined, {
          malformedKnob: knob,
        });
      }
    }

    // model is a developer-controlled provider identifier dispatched verbatim; validate it as a
    // conservative structural identifier so PHI free text can never ride the model slot (L5).
    if (typeof raw["model"] === "string") {
      assertStructuralProviderString(raw["model"] as string, "model");
    }

    // system — a known text carrier: if present it MUST be a string. A non-string value (e.g. an
    // object that could smuggle PHI text past the `typeof === "string"` classification and egress
    // RAW via the clone) fails closed rather than passing through unclassified (L5).
    const systemValue = raw["system"];
    if (systemValue !== undefined && systemValue !== null) {
      if (typeof systemValue !== "string") {
        throw new PhiEngineError("UNCLASSIFIED_PROVIDER_FIELD", undefined, {
          malformedTextCarrier: "system",
        });
      }
      collected.push({
        segment: { path: "system", kind: "system", text: systemValue },
        write: (draft, tokenized) => {
          draft.system = tokenized;
        },
      });
    }

    // messages[i].content[j].text — EVERY text-bearing part, regardless of `type`.
    // A non-"text" part (e.g. `tool_result`) that still carries a `text` string must
    // be classified and tokenized, never egressed raw (L5 / fail-closed).
    (snap.messages ?? []).forEach((message, i) => {
      assertAllowedEnum(message.role, ALLOWED_MESSAGE_ROLES, `messages[${i}].role`);
      message.content.forEach((part, j) => {
        assertAllowedEnum(part.type, ALLOWED_CONTENT_TYPES, `messages[${i}].content[${j}].type`);
        const partText = (part as unknown as Record<string, unknown>)["text"];
        // A `text` carrier that is present but NON-string (an object smuggling PHI) fails closed;
        // it must never bypass tokenization and egress raw via the clone (L5).
        if (partText !== undefined && partText !== null) {
          if (typeof partText !== "string") {
            throw new PhiEngineError("UNCLASSIFIED_PROVIDER_FIELD", undefined, {
              malformedTextCarrier: `messages[${i}].content[${j}].text`,
            });
          }
          const path = `messages[${i}].content[${j}].text`;
          collected.push({
            segment: { path, kind: kindForRole(message.role), text: partText },
            write: (draft, tokenized) => {
              const target = draft.messages?.[i]?.content?.[j];
              if (target !== undefined) target.text = tokenized;
            },
          });
        }
      });
    });

    // tools[k].description
    (snap.tools ?? []).forEach((tool, k) => {
      assertStructuralProviderString(tool.name, `tools[${k}].name`);
      // A tool description is a known text carrier and MUST be a string. A present-but-non-string
      // value (an object smuggling PHI text past the segment's `text` typing, then egressed RAW via
      // the clone) fails closed rather than passing through unclassified (L5).
      const descriptionValue = (tool as unknown as Record<string, unknown>)["description"];
      if (typeof descriptionValue !== "string") {
        throw new PhiEngineError("UNCLASSIFIED_PROVIDER_FIELD", undefined, {
          malformedTextCarrier: `tools[${k}].description`,
        });
      }
      const path = `tools[${k}].description`;
      collected.push({
        segment: { path, kind: "tool", text: descriptionValue },
        write: (draft, tokenized) => {
          const target = draft.tools?.[k];
          if (target !== undefined) target.description = tokenized;
        },
      });
    });

    // embeddingText — a known text carrier: present-but-non-string fails closed (L5).
    const embeddingValue = raw["embeddingText"];
    if (embeddingValue !== undefined && embeddingValue !== null) {
      if (typeof embeddingValue !== "string") {
        throw new PhiEngineError("UNCLASSIFIED_PROVIDER_FIELD", undefined, {
          malformedTextCarrier: "embeddingText",
        });
      }
      collected.push({
        segment: { path: "embedding", kind: "embedding", text: embeddingValue },
        write: (draft, tokenized) => {
          draft.embeddingText = tokenized;
        },
      });
    }

    const segments = collected.map((entry) => entry.segment);

    const expectedPaths = new Set(collected.map((entry) => entry.segment.path));

    return {
      segments,
      rebuild: (tokenized: readonly TokenizedTextSegment[]): BoundaryGenerateOptions => {
        // L5 / fail-closed: rebuild requires an EXACT 1:1 mapping between the classified
        // paths and the tokenized segments. A missing segment (which would leave the raw
        // original value in place), an unexpected path, or a duplicate path all fail
        // closed before egress rather than silently egressing an unprotected value.
        const byPath = new Map<string, string>();
        for (const seg of tokenized) {
          if (!expectedPaths.has(seg.path)) {
            throw new PhiEngineError("UNCLASSIFIED_PROVIDER_FIELD", undefined, {
              unexpectedTokenizedPath: seg.path,
            });
          }
          if (byPath.has(seg.path)) {
            throw new PhiEngineError("UNCLASSIFIED_PROVIDER_FIELD", undefined, {
              duplicateTokenizedPath: seg.path,
            });
          }
          byPath.set(seg.path, seg.text as unknown as string);
        }
        if (byPath.size !== collected.length) {
          throw new PhiEngineError("UNCLASSIFIED_PROVIDER_FIELD", undefined, {
            missingTokenizedSegments: collected.length - byPath.size,
          });
        }
        const draft: MutableOptions = cloneSnapshot(snap);
        for (const entry of collected) {
          entry.write(draft, byPath.get(entry.segment.path) as string);
        }
        return draft as BoundaryGenerateOptions;
      },
    };
  }
}

/**
 * Reads every provider-visible value out of the caller's option object EXACTLY ONCE into an inert,
 * getter-free snapshot. The projector then both VALIDATES and REBUILDS from this snapshot and never
 * re-reads the original — closing the check-vs-use (TOCTOU) gap where a property getter returns a
 * benign value during validation and a PHI-laden one during rebuild (L5 fail-closed). Nested
 * message/tool carriers are normalized so their getters are read once too.
 */
function snapshotBoundaryOptions(options: BoundaryGenerateOptions): MutableOptions {
  const src = options as unknown as Record<string, unknown>;
  const snap: Record<string, unknown> = {};
  for (const key of Object.keys(src)) {
    snap[key] = src[key]; // one read per own-enumerable top-level property
  }
  const messages = snap["messages"];
  if (Array.isArray(messages)) {
    snap["messages"] = messages.map((message) => {
      const m = message as Record<string, unknown>;
      const content = m["content"];
      return {
        role: m["role"],
        content: Array.isArray(content)
          ? content.map((part) => {
              const p = part as Record<string, unknown>;
              return { type: p["type"], text: p["text"] };
            })
          : content,
      };
    });
  }
  const tools = snap["tools"];
  if (Array.isArray(tools)) {
    snap["tools"] = tools.map((tool) => {
      const t = tool as Record<string, unknown>;
      return { name: t["name"], description: t["description"] };
    });
  }
  return snap as MutableOptions;
}

/** Fresh deep clone of the inert snapshot so a tokenized write never mutates the shared snapshot.
 *  Reads only the snapshot (never the caller's original), so it introduces no new getter reads. */
function cloneSnapshot(snap: MutableOptions): MutableOptions {
  const draft: MutableOptions = { ...(snap as unknown as Record<string, unknown>) };
  if (Array.isArray(snap.messages)) {
    draft.messages = snap.messages.map((message) => ({
      role: message.role,
      content: (message.content as { type: string; text: string }[]).map((part) => ({
        type: part.type,
        text: part.text,
      })),
    }));
  }
  if (Array.isArray(snap.tools)) {
    draft.tools = snap.tools.map((tool) => ({ name: tool.name, description: tool.description }));
  }
  return draft;
}

export { NON_TEXT_KNOB_KEYS };
