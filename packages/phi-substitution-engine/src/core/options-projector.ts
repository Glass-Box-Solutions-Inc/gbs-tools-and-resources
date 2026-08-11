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

function assertStructuralProviderString(value: string, path: string): void {
  if (!PROVIDER_VISIBLE_STRUCTURAL_STRING.test(value)) {
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
    const raw = options as unknown as Record<string, unknown>;
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

    // system
    if (typeof options.system === "string") {
      collected.push({
        segment: { path: "system", kind: "system", text: options.system },
        write: (draft, tokenized) => {
          draft.system = tokenized;
        },
      });
    }

    // messages[i].content[j].text — EVERY text-bearing part, regardless of `type`.
    // A non-"text" part (e.g. `tool_result`) that still carries a `text` string must
    // be classified and tokenized, never egressed raw (L5 / fail-closed).
    (options.messages ?? []).forEach((message, i) => {
      assertAllowedEnum(message.role, ALLOWED_MESSAGE_ROLES, `messages[${i}].role`);
      message.content.forEach((part, j) => {
        assertAllowedEnum(part.type, ALLOWED_CONTENT_TYPES, `messages[${i}].content[${j}].type`);
        if (typeof part.text === "string") {
          const path = `messages[${i}].content[${j}].text`;
          collected.push({
            segment: { path, kind: kindForRole(message.role), text: part.text },
            write: (draft, tokenized) => {
              const target = draft.messages?.[i]?.content?.[j];
              if (target !== undefined) target.text = tokenized;
            },
          });
        }
      });
    });

    // tools[k].description
    (options.tools ?? []).forEach((tool, k) => {
      assertStructuralProviderString(tool.name, `tools[${k}].name`);
      const path = `tools[${k}].description`;
      collected.push({
        segment: { path, kind: "tool", text: tool.description },
        write: (draft, tokenized) => {
          const target = draft.tools?.[k];
          if (target !== undefined) target.description = tokenized;
        },
      });
    });

    // embeddingText
    if (typeof options.embeddingText === "string") {
      collected.push({
        segment: { path: "embedding", kind: "embedding", text: options.embeddingText },
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
        const draft: MutableOptions = structuredCloneOptions(options);
        for (const entry of collected) {
          entry.write(draft, byPath.get(entry.segment.path) as string);
        }
        return draft as BoundaryGenerateOptions;
      },
    };
  }
}

/** Deep-enough clone of the classified text carriers so rebuild never mutates the caller's input. */
function structuredCloneOptions(options: BoundaryGenerateOptions): MutableOptions {
  // Preserve every option field (incl. non-text sampling knobs model/temperature/maxTokens/
  // topP/stream) so the provider receives them unchanged; deep-clone the text carriers so a
  // tokenized write never mutates the caller's input.
  const draft: MutableOptions = { ...(options as unknown as Record<string, unknown>) };
  if (options.messages !== undefined) {
    draft.messages = options.messages.map((message) => ({
      role: message.role,
      content: message.content.map((part) => ({ type: part.type, text: part.text })),
    }));
  }
  if (options.tools !== undefined) {
    draft.tools = options.tools.map((tool) => ({ name: tool.name, description: tool.description }));
  }
  return draft;
}

export { NON_TEXT_KNOB_KEYS };
