/**
 * UTF-16 boundary primitives for detector offset validation (CONTRACT-phase1 §3.3, §5 L3/L12).
 *
 * Detector responses are validated against the ORIGINAL UTF-16 text. A boundary that
 * would split a surrogate pair is invalid and must fail closed — never be clamped or moved.
 */

export function isHighSurrogate(code: number): boolean {
  return code >= 0xd800 && code <= 0xdbff;
}

export function isLowSurrogate(code: number): boolean {
  return code >= 0xdc00 && code <= 0xdfff;
}

/** True when UTF-16 index `index` falls between the high and low unit of a surrogate pair. */
export function splitsSurrogatePair(text: string, index: number): boolean {
  if (index <= 0 || index >= text.length) {
    return false;
  }
  return (
    isHighSurrogate(text.charCodeAt(index - 1)) &&
    isLowSurrogate(text.charCodeAt(index))
  );
}
