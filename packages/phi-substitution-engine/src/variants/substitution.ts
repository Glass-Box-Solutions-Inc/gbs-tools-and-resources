/**
 * Minimal egress-substitution model. It proves that a variant expander did not
 * fabricate a lossy identifier that would otherwise match unrelated free text:
 * only EXACT occurrences of an allow-listed candidate are replaced, and nothing
 * is fuzzy-matched. Because the correct expanders never emit a bare or truncated
 * form, unrelated look-alike digits in surrounding prose survive unchanged.
 */
export function replaceAllowListedVariants(
  text: string,
  candidates: readonly string[],
  placeholder: string,
): string {
  // Longest candidates first, so a longer allow-listed form is not pre-empted by
  // a shorter substring of it.
  const ordered = candidates
    .filter((candidate) => candidate.length > 0)
    .slice()
    .sort((left, right) => right.length - left.length);

  let out = text;
  for (const candidate of ordered) {
    out = out.split(candidate).join(placeholder);
  }
  return out;
}
