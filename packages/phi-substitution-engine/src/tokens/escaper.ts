import type { EscapedSourceText, TokenizedText } from "../core/brands";
import type {
  EscapedTokenLiteral,
  SourceTokenEscaper,
  TokenGrammar,
  TokenGrammarPolicy,
} from "./ports";

/**
 * Private-use sentinels that fence an escaped source literal. They are NOT
 * bracket-shaped, so they can never be re-parsed as a reversible token, and
 * they carry the literal's index so restoration is offset-independent.
 */
export const SENTINEL_OPEN = "";
export const SENTINEL_CLOSE = "";
const SENTINEL_PATTERN = /(\d+)/g;

/**
 * Escapes reserved token-shaped source text into a non-reversible literal
 * namespace BEFORE dictionary matching (CONTRACT-phase1 L6).
 *
 * Every bracket-shaped span the grammar can see — valid OR malformed — is
 * replaced by a sentinel so a caller cannot inject `[[Role]]` into source and
 * have it reversed into a mapped value on the way back.
 */
export class SentinelSourceTokenEscaper implements SourceTokenEscaper {
  constructor(private readonly grammar: TokenGrammar) {}

  escape(
    source: string,
    policy: TokenGrammarPolicy,
  ): Readonly<{ text: EscapedSourceText; literals: readonly EscapedTokenLiteral[] }> {
    const spans = this.grammar.scan(source, policy);
    const literals: EscapedTokenLiteral[] = [];
    let out = "";
    let cursor = 0;
    let index = 0;
    for (const span of spans) {
      out += source.slice(cursor, span.startUtf16);
      const originalLiteral = source.slice(span.startUtf16, span.endUtf16);
      const internalStartUtf16 = out.length;
      out += `${SENTINEL_OPEN}${index}${SENTINEL_CLOSE}`;
      const internalEndUtf16 = out.length;
      literals.push({ internalStartUtf16, internalEndUtf16, originalLiteral });
      cursor = span.endUtf16;
      index += 1;
    }
    out += source.slice(cursor);
    return { text: out as EscapedSourceText, literals };
  }

  restoreLiterals(
    text: TokenizedText,
    literals: readonly EscapedTokenLiteral[],
  ): TokenizedText {
    // Sentinels are replaced by index, which survives any length change the
    // reversal step made to surrounding text. A missing/out-of-range index
    // collapses to empty rather than leaking a stray sentinel.
    const restored = String(text).replace(SENTINEL_PATTERN, (_match, digits: string) => {
      const literal = literals[Number(digits)];
      return literal ? literal.originalLiteral : "";
    });
    return restored as TokenizedText;
  }
}
