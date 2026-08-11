/**
 * The C1–C8 collision resolver (invariants L3 and L12).
 *
 * Fixed order:
 *   C1 boundary        -> drop dictionary matches on a non-boundary.
 *   C2 distinctiveness -> drop indistinct standalone dictionary matches.
 *   C3 citation        -> suppress a claimant surname inside a validated citation.
 *   C6 ambiguity       -> equal-specificity subjects sharing one span are
 *                         quarantined and force fail-closed (never guessed).
 *   C4/C5 selection    -> leftmost-longest over a TOTAL, input-order-independent
 *                         ordering; dictionary spans always beat overlapping
 *                         detector spans (L12), and remaining ties break by class
 *                         precedence then a stable key.
 */
import type { IdentifierClass } from "../core/contracts";
import type { DictionaryMatchCandidate } from "../dictionary/contracts";
import type {
  BoundaryRule,
  CitationRule,
  CollisionResolver,
  DetectorCollisionSpan,
  DistinctivenessRule,
  ResolvedCollisionSet,
} from "./ports";
import type { Utf16Offset } from "../core/brands";

const asUtf16 = (value: number): Utf16Offset => value as unknown as Utf16Offset;
const num = (value: Utf16Offset): number => value as unknown as number;

/** Lower rank wins an otherwise-tied overlap (C4/class precedence). */
const CLASS_RANK: Readonly<Record<IdentifierClass, number>> = {
  PERSON_NAME: 0,
  SSN: 1,
  DEA: 2,
  MRN: 3,
  DOB: 4,
  EMAIL: 5,
  PHONE: 6,
  ADDRESS: 7,
  CLAIM_NUMBER: 8,
  POLICY_NUMBER: 9,
  ACCOUNT_NUMBER: 10,
  OTHER_TAGGED: 11,
};

interface Interval {
  readonly start: number;
  readonly end: number;
  readonly source: "dict" | "det";
  readonly rank: number;
  readonly tieKey: string;
  readonly dict?: DictionaryMatchCandidate;
  readonly det?: DetectorCollisionSpan;
}

/** Total order: start asc, length desc, dictionary>detector, class rank, stable key. */
function compareIntervals(a: Interval, b: Interval): number {
  if (a.start !== b.start) return a.start - b.start;
  const lenA = a.end - a.start;
  const lenB = b.end - b.start;
  if (lenA !== lenB) return lenB - lenA;
  if (a.source !== b.source) return a.source === "dict" ? -1 : 1;
  if (a.rank !== b.rank) return a.rank - b.rank;
  if (a.tieKey < b.tieKey) return -1;
  if (a.tieKey > b.tieKey) return 1;
  return 0;
}

export class Phase1CollisionResolver implements CollisionResolver {
  private readonly boundaryRule: BoundaryRule;
  private readonly distinctivenessRule: DistinctivenessRule;
  private readonly citationRule: CitationRule;

  public constructor(
    boundaryRule: BoundaryRule,
    distinctivenessRule: DistinctivenessRule,
    citationRule: CitationRule,
  ) {
    this.boundaryRule = boundaryRule;
    this.distinctivenessRule = distinctivenessRule;
    this.citationRule = citationRule;
  }

  public resolve(
    input: Readonly<{
      originalText: string;
      locale: string;
      dictionaryCandidates: readonly DictionaryMatchCandidate[];
      detectorCandidates: readonly DetectorCollisionSpan[];
    }>,
  ): ResolvedCollisionSet {
    const { originalText, locale } = input;
    const citationSpans = this.citationRule.validatedSpans(originalText, locale);

    // C1 -> C2 -> C3 in fixed order over dictionary candidates.
    const survivingDictionary = input.dictionaryCandidates.filter(
      (candidate) =>
        this.boundaryRule.accepts(originalText, candidate) &&
        this.distinctivenessRule.accepts(candidate, locale) &&
        !this.citationRule.suppresses(candidate, citationSpans),
    );

    // C6 ambiguity quarantine: same span, >=2 distinct subjects, equal top specificity.
    const quarantined = findAmbiguities(survivingDictionary);
    const quarantinedKeys = new Set(
      quarantined.map((q) => `${num(q.startUtf16)}:${num(q.endUtf16)}`),
    );

    const intervals: Interval[] = [];
    for (const candidate of survivingDictionary) {
      const start = num(candidate.startUtf16);
      const end = num(candidate.endUtf16);
      if (quarantinedKeys.has(`${start}:${end}`)) continue;
      intervals.push({
        start,
        end,
        source: "dict",
        rank: CLASS_RANK[candidate.candidate.identifierClass],
        tieKey: `${candidate.candidate.subjectId as unknown as string}|${candidate.candidate.token as unknown as string}`,
        dict: candidate,
      });
    }
    for (const span of input.detectorCandidates) {
      const start = num(span.startUtf16);
      const end = num(span.endUtf16);
      // C3 also governs detector-only spans, but only a PERSON_NAME is ever
      // suppressed inside a validated citation; a structured identifier is not.
      if (span.identifierClass === "PERSON_NAME" && insideCitation(start, end, citationSpans)) {
        continue;
      }
      intervals.push({
        start,
        end,
        source: "det",
        rank: CLASS_RANK[span.identifierClass],
        tieKey: `det|${span.identifierClass}`,
        det: span,
      });
    }

    // C4/C5: deterministic leftmost-longest greedy selection over non-overlaps.
    intervals.sort(compareIntervals);
    const selectedDictionary: DictionaryMatchCandidate[] = [];
    const selectedDetector: DetectorCollisionSpan[] = [];
    let lastEnd = -1;
    for (const interval of intervals) {
      if (interval.start < lastEnd) continue;
      lastEnd = interval.end;
      if (interval.dict !== undefined) selectedDictionary.push(interval.dict);
      else if (interval.det !== undefined) selectedDetector.push(interval.det);
    }

    return {
      selectedDictionary,
      selectedDetector,
      quarantinedAmbiguities: quarantined,
      mustFailClosed: quarantined.length > 0,
    };
  }
}

function insideCitation(
  start: number,
  end: number,
  spans: ReturnType<CitationRule["validatedSpans"]>,
): boolean {
  for (const span of spans) {
    if (start >= num(span.startUtf16) && end <= num(span.endUtf16)) return true;
  }
  return false;
}

function findAmbiguities(
  candidates: readonly DictionaryMatchCandidate[],
): ResolvedCollisionSet["quarantinedAmbiguities"] {
  const bySpan = new Map<string, DictionaryMatchCandidate[]>();
  for (const candidate of candidates) {
    const key = `${num(candidate.startUtf16)}:${num(candidate.endUtf16)}`;
    const bucket = bySpan.get(key);
    if (bucket === undefined) bySpan.set(key, [candidate]);
    else bucket.push(candidate);
  }

  const out: Array<{
    startUtf16: Utf16Offset;
    endUtf16: Utf16Offset;
    identifierClass: IdentifierClass;
    subjectCount: number;
  }> = [];

  for (const bucket of bySpan.values()) {
    const first = bucket[0];
    if (first === undefined) continue;
    let topSpecificity = -Infinity;
    for (const candidate of bucket) {
      if (candidate.candidate.specificity > topSpecificity) {
        topSpecificity = candidate.candidate.specificity;
      }
    }
    const subjectsAtTop = new Set<string>();
    for (const candidate of bucket) {
      if (candidate.candidate.specificity === topSpecificity) {
        subjectsAtTop.add(candidate.candidate.subjectId as unknown as string);
      }
    }
    if (subjectsAtTop.size >= 2) {
      out.push({
        startUtf16: first.startUtf16,
        endUtf16: first.endUtf16,
        identifierClass: first.candidate.identifierClass,
        subjectCount: subjectsAtTop.size,
      });
    }
  }
  return out;
}
