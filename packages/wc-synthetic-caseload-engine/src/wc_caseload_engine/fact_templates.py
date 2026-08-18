"""Engine-owned template subclasses that read the ledger instead of dice.

The substrate is consumed read-only, so a template whose content contradicts
:class:`~wc_caseload_engine.case_facts.CaseFacts` is corrected by *subclassing*
it here, never by editing it. Each subclass overrides the narrowest method that
rolls the offending draw and delegates everything else — letterheads, patient
headers, section styling, prose helpers — to the substrate, which is where that
work belongs and where it is already good.

The registry at the bottom, :data:`FACT_AWARE_TEMPLATES`, is the whole of the
opt-in surface. A subtype not in it dispatches exactly as it did at 0.2.0, byte
for byte; a subtype in it is announced in the compatibility notice.
"""

from __future__ import annotations

import random
import re
from decimal import Decimal
from html import escape
from typing import Any, Final

import structlog

from wc_caseload_engine.case_facts import (
    ADJUSTER_LETTER_TYPES,
    IMAGING_MODALITIES,
    MODALITY_DISPLAY,
    SUBSTRATE_STATUS_PHRASES,
    CaseFacts,
)
from wc_caseload_engine.defense_lens import InitialFileReview, ReserveEvent
from wc_caseload_engine.medical_story import (
    PTP_APPORTIONMENT_SURFACES,
    SUPPLEMENTAL_MEDLEGAL_SURFACES,
    DocumentMedicalStory,
    StoryRecordReference,
)
from wc_caseload_engine.money import (
    PD_ADVANCE_INTERVAL_DAYS,
    PD_ADVANCE_SCHEDULE_AUTHORITY,
    TD_PAYMENT_DUE_AUTHORITY,
    TD_PAYMENT_DUE_DAYS,
    MoneyFacts,
)
from wc_caseload_engine.rating import RATING_CARRIER_SUBTYPES, RatingFacts
from wc_caseload_engine.seeds import (
    SETTLEMENT_FEE_RATE,
    settlement_deductions,
)
from wc_caseload_engine.substrate import import_substrate
from wc_caseload_engine.taxonomy import effective_taxonomy

log = structlog.get_logger(__name__)

CENTS = Decimal("0.01")
"""Quantum every currency figure on a rendered page is rounded to."""

#: The candidate list ``DiagnosticReport`` draws its modality from.
#:
#: Matched exactly, so the interception below can tell that draw apart from
#: every other ``random.choice`` in the same method (facility name, address
#: digits, field strength, severity). If the substrate ever edits this list the
#: match stops firing — and the coherence harness fails, which is the intended
#: way to find out.
_SUBSTRATE_MODALITY_CHOICES: tuple[str, ...] = ("MRI", "CT", "X-Ray")


class _ForcedChoice:
    """A stand-in for :mod:`random` that answers one specific question.

    Delegates every attribute to the real module. The single exception is
    ``choice`` over :data:`_SUBSTRATE_MODALITY_CHOICES`, which returns the
    ledger's modality instead of drawing.

    Why interception rather than reimplementation: ``DiagnosticReport``'s modality
    draw sits at the top of a hundred-line ``build_story`` whose later branches —
    the MRI sequence list, the CT slice thickness, the X-ray projection names —
    all read the value it produced. Overriding the method would mean copying all
    of that to change one line, which is the "fork half a template" outcome this
    package exists to avoid. Forcing the draw keeps every branch the substrate's
    and still guarantees the answer.
    """

    __slots__ = ("_answer", "_matches", "fired")

    def __init__(self, answer: Any, matches: Any) -> None:
        self._answer = answer
        self._matches = matches
        self.fired = False

    def choice(self, seq: Any) -> Any:
        if self._matches(seq):
            self.fired = True
            # Draw and discard. The substrate would have consumed one value
            # here, and everything it renders afterwards reads the stream from
            # wherever that left it. Returning the ledger's answer without
            # drawing would shift every later draw in the document, so pinning
            # one line would silently rewrite the rest of the page.
            random.choice(seq)
            return self._answer
        return random.choice(seq)

    def __getattr__(self, name: str) -> Any:
        return getattr(random, name)


class _SpecCapture:
    """Binds the rendering spec to the instance so the helpers below can read it.

    The substrate threads ``doc_spec`` as a *parameter* — ``generate`` hands it
    to ``_generate_pdf``, which hands it to ``build_story`` — and never assigns
    ``self.doc_spec``. Every helper here that reached for
    ``template.doc_spec.context`` therefore got ``None`` and fell through to its
    default, silently and forever.

    :func:`_facts_of` escaped because the renderer also sets
    ``_wc_case_facts`` on the instance, so the ledger arrived by the second
    route. :func:`_index_of` and :func:`_report_ordinal` had no second route:
    the treatment trajectory read ordinal 0 for every report in every case from
    the day it shipped, and the suite passed because "the first phrase of the
    arc" satisfies "some phrase of the arc".

    Capturing in ``generate`` rather than in each ``build_story`` covers the
    helpers called from ``_build_diagnostic_review`` and friends, which the
    substrate invokes without the spec, and means a subclass that overrides
    nothing still gets the seam. This is our class, not the substrate's — the
    substrate is unchanged.
    """

    def generate(self, output_path: Any, doc_spec: Any) -> Any:
        self.doc_spec = doc_spec
        return super().generate(output_path, doc_spec)  # type: ignore[misc]


def _procedure_phrase(surgery: Any) -> str:
    """The one rendering of the ledger's procedure, coded or uncoded.

    Every fact-aware document that names the operation goes through this, so
    an uncoded operation (AJC-55) reads identically everywhere and no renderer
    can interpolate a literal ``None``.
    """
    if surgery.cpt_code:
        return f"{surgery.cpt_description} (CPT {surgery.cpt_code})"
    return "an unlisted surgical procedure (uncoded)"


def _facts_of(template: Any) -> CaseFacts | None:
    """The ledger for the document being rendered, if the context carries one."""
    context = getattr(getattr(template, "doc_spec", None), "context", None)
    if isinstance(context, dict):
        facts = context.get("case_facts")
        if isinstance(facts, CaseFacts):
            return facts
    return getattr(template, "_wc_case_facts", None)


def _wants_medicare_set_aside(template: Any) -> bool:
    """Whether this file has a Medicare set-aside, off the seed's own flag.

    Read from the render context rather than the substrate case: the substrate
    carries ``is_medicare_eligible`` on its *lifecycle profile*, not on the case
    the template holds, so reading it there silently answered False for every
    document.
    """
    context = getattr(getattr(template, "doc_spec", None), "context", None)
    if isinstance(context, dict):
        return bool(context.get("medicare_set_aside", False))
    return False


def _index_of(template: Any) -> int:
    context = getattr(getattr(template, "doc_spec", None), "context", None)
    if isinstance(context, dict):
        value = context.get("document_index")
        if isinstance(value, int):
            return value
    return 0


def _money_of(template: Any) -> MoneyFacts | None:
    """The money spine for the document being rendered, or ``None``.

    ``None`` is the ordinary answer — most seeds carry no ``scenario.wages`` —
    and every money-aware template below returns the substrate's own story
    untouched on it. That is the anti-criterion expressed as a code path: the
    registry entry exists, the subclass is dispatched, and it delegates.

    Read off the instance rather than the context, because the renderer sets
    ``_wc_money_facts`` there and ``build_story`` is not the only method that
    needs it.
    """
    return getattr(template, "_wc_money_facts", None)


def _reserve_event_of(template: Any) -> InitialFileReview | ReserveEvent | None:
    """The exact R72/R73 object bound to this reserve artifact, if present."""
    context = getattr(getattr(template, "doc_spec", None), "context", None)
    if isinstance(context, dict):
        event = context.get("reserve_event")
        if isinstance(event, (InitialFileReview, ReserveEvent)):
            return event
    event = getattr(template, "_wc_reserve_event", None)
    return event if isinstance(event, (InitialFileReview, ReserveEvent)) else None


def _rating_of(template: Any) -> RatingFacts | None:
    """Return the sole canonical W2 rating object carried by CaseFacts."""
    facts = _facts_of(template)
    return None if facts is None else facts.rating


def _subtype_of(template: Any) -> str:
    """Canonical subtype of the document being rendered, or ``""``.

    One substrate class (``WageStatement``) renders both the employer's earnings
    certificate and the carrier's payment records, so the subtype is the only
    thing that says which document is on the page.
    """
    subtype = getattr(getattr(template, "doc_spec", None), "subtype", None)
    return str(getattr(subtype, "value", "") or "")


#: The substrate's initial-imaging sentence pool, drawn at
#: ``qme_ame_report.py:171``. A third independent modality draw, in the history
#: narrative rather than the diagnostic review — which is how a QME could open
#: by announcing an MRI and then review only X-rays four pages later.
_SUBSTRATE_HISTORY_IMAGING: tuple[str, ...] = (
    "X-rays which revealed no acute fracture but noted degenerative changes",
    "MRI which demonstrated structural pathology correlating with symptoms",
    "X-rays and subsequent MRI for further evaluation of the injury",
)


def _history_imaging_sentence(facts: Any) -> str:
    """What the history may say was obtained, from the ledger and nowhere else."""
    performed = [fact.display for fact in facts.performed_diagnostics]
    if not performed:
        return (
            "no imaging at the time of initial evaluation; the record reflects "
            "clinical examination only"
        )
    if len(performed) == 1:
        return f"{performed[0]} of the affected region"
    return f"{', '.join(performed[:-1])} and {performed[-1]}"


def _after_examination_line(story: list[Any]) -> int:
    """Insertion point directly below the substrate's EXAMINATION paragraph.

    Located by text rather than by a fixed offset so a substrate edit that adds
    a flowable above it moves the insertion with it. Falls back to the top of
    the story, which is visible in the rendered document rather than silently
    wrong.
    """
    for position, element in enumerate(story):
        if "EXAMINATION:" in str(getattr(element, "text", "")):
            return position + 1
    return 0


def _letter_ordinal(template: Any) -> int:
    """Which adjuster letter this is within its own case, zero-based.

    Its own counter for the same reason the treating report has one: the type
    sequence has to advance per *letter*, not per document, or two letters at
    document indices 3 and 27 would land on unrelated points of the sequence.
    """
    context = getattr(getattr(template, "doc_spec", None), "context", None)
    if isinstance(context, dict):
        value = context.get("letter_ordinal")
        if isinstance(value, int):
            return value
    return 0


#: The phrase an ``event_driven`` client letter opens its status paragraph
#: with. Owned beside the template that writes it so the guard and the
#: renderer read ONE string: a marker the test spells independently is a
#: marker that can drift out of the document while the test still passes.
ANCHOR_REFERENCE_MARKER = "further to the"


def _packet_ordinal(template: Any) -> int:
    """Which records packet this is within its case, zero-based."""
    context = getattr(getattr(template, "doc_spec", None), "context", None)
    if isinstance(context, dict):
        value = context.get("packet_ordinal")
        if isinstance(value, int):
            return value
    return 0


def _is_page_break(element: Any) -> bool:
    return type(element).__name__ == "PageBreak"


def _split_at_first_break(story: list[Any]) -> tuple[list[Any], list[Any]]:
    """Cover sheet, then everything behind it."""
    for position, element in enumerate(story):
        if _is_page_break(element):
            return story[: position + 1], story[position + 1 :]
    return story, []


def _split_pages(body: list[Any]) -> list[list[Any]]:
    """The body's flowables grouped into pages, page breaks removed."""
    pages: list[list[Any]] = [[]]
    for element in body:
        if _is_page_break(element):
            pages.append([])
        else:
            pages[-1].append(element)
    return [page for page in pages if page]


#: How many times we may ask the substrate for another records block before
#: giving up and reporting a short packet. A guard against an unbounded loop if
#: a future substrate edit ever returns nothing.
_MAX_RECORD_BLOCKS = 40

#: Measure-then-adjust rounds allowed per packet. Each is a full render, so this
#: is a real cost; in practice the first correction lands because the residual
#: between sections and pages is small and stable.
_MAX_FIT_ATTEMPTS = 6


def _page_count(path: Any) -> int:
    """Physical pages in a rendered PDF.

    The measurement the whole of ISC-126 turns on: a PageBreak-delimited section
    is what the *story* contains, and a page is what the *paper* contains, and
    the substrate's cover sheet was describing the former while claiming the
    latter.
    """
    import fitz

    with fitz.open(path) as document:
        return document.page_count


def _fit_pages(pages: list[list[Any]], wanted: int, more: Any) -> list[list[Any]]:
    """Exactly *wanted* pages, trimming or asking *more* for further content.

    Trimming is lossless: a records packet is an arbitrary-length excerpt, so
    dropping the tail leaves a shorter but coherent packet.

    Growth calls ``more()`` for a freshly built block rather than repeating the
    pages already in hand. Repetition was the first implementation and reportlab
    rejected it outright — ``LayoutError: Flowable ... too large on page 10`` —
    because a flowable carries layout state and cannot appear twice in one
    document. The error was the good outcome: repeating pages would also have
    produced a packet containing the same office visit on the same date several
    times over, which is precisely the kind of incoherence this ticket exists to
    remove. Fresh blocks carry their own drawn dates and findings.
    """
    if wanted <= len(pages):
        return pages[:wanted]
    grown = list(pages)
    for _ in range(_MAX_RECORD_BLOCKS):
        if len(grown) >= wanted:
            break
        extra = _split_pages(list(more()))
        if not extra:
            break
        grown.extend(extra)
    return grown[:wanted]


def _join_pages(pages: list[list[Any]], page_break: Any) -> list[Any]:
    joined: list[Any] = []
    for position, page in enumerate(pages):
        if position:
            joined.append(page_break())
        joined.extend(page)
    return joined


def _rewrite_page_table(head: list[Any], total: int) -> None:
    """Restate the cover sheet's page table so its rows sum to *total*.

    Scales the substrate's own per-record-type counts rather than replacing
    them, so the mix of record types stays whatever the substrate decided; only
    the arithmetic is corrected. Any rounding residue lands on the first row,
    which is what guarantees the column sums exactly rather than approximately.
    """
    for element in head:
        values = getattr(element, "_cellvalues", None)
        if not values or len(values) < 3:
            continue
        header = [str(cell) for cell in values[0]]
        if "Pages" not in header:
            continue
        column = header.index("Pages")
        rows = values[1:-1]
        counts = []
        for row in rows:
            try:
                counts.append(int(str(row[column])))
            except (TypeError, ValueError):
                counts.append(1)
        current = sum(counts) or 1
        scaled = [max(1, round(count * total / current)) for count in counts]
        scaled[0] = max(1, scaled[0] + (total - sum(scaled)))
        for row, count in zip(rows, scaled, strict=True):
            row[column] = str(count)
        values[-1][column] = f"<b>{sum(scaled)}</b>"
        return


def _preceding_anchor(template: Any, when: Any) -> tuple[str, Any] | None:
    """The most recent anchor document dated at or before ``when``.

    Chosen here rather than in the planner so the reference can never name a
    document dated *after* the letter citing it — the letter's own date is the
    only thing that decides, and it is right here.
    """
    context = getattr(getattr(template, "doc_spec", None), "context", None)
    if not isinstance(context, dict) or when is None:
        return None
    anchors = context.get("cadence_anchors") or ()
    prior = [entry for entry in anchors if entry[1] <= when]
    return max(prior, key=lambda entry: entry[1]) if prior else None


def _before_closing(story: list[Any]) -> int:
    """Insertion point above the letter's sign-off.

    Located by text so a substrate edit that adds a flowable moves the insertion
    with it. Falls back to the end of the story, which is visible on the page
    rather than silently dropped.
    """
    for position, element in enumerate(story):
        text = str(getattr(element, "text", ""))
        if text.startswith("Sincerely") or text.startswith("Very truly"):
            return position
    return len(story)


def _report_ordinal(template: Any) -> int:
    """Which treating report this is within its own case, zero-based.

    Distinct from :func:`_index_of`, which counts every document in the case.
    A trajectory has to advance per *report*, not per document, or a case whose
    PRs sit at document indices 4 and 19 would jump straight to the end of the
    arc and hold there.
    """
    context = getattr(getattr(template, "doc_spec", None), "context", None)
    if isinstance(context, dict):
        value = context.get("report_ordinal")
        if isinstance(value, int):
            return value
    return 0


# ---------------------------------------------------------------------------
# Medical story (AJC-62 / M3, R77 step 7)
# ---------------------------------------------------------------------------


type _ClauseRegister = tuple[tuple[str, tuple[str, ...]], ...]


#: Source: ``psych-harassment-gfpa.md``,
#: ``psych-compensable-consequence-vs-direct.md``, and the deliberately
#: generic safety-officer gaps identified in ``psych-ptsd-safety-officers.md``.
PSYCH_HISTORY_REGISTER: Final[_ClauseRegister] = (
    (
        "harassment_gfpa",
        (
            "The applicant reports [specific employment events] and describes "
            "the work environment as [grounded description].",
            "The history includes [performance review, discipline, transfer, "
            "supervision, termination, reported mistreatment, or reported "
            "discrimination], each of which is addressed separately rather than "
            "collapsed into a generalized allegation.",
            "Whether the reported events occurred and whether any event was a "
            "lawful, nondiscriminatory, good-faith personnel action are reserved "
            "for the trier of fact.",
        ),
    ),
    (
        "direct_physical_event",
        (
            "The reported psychiatric symptoms are attributed to [event] itself "
            "rather than solely to the later effects of the physical injuries.",
            "The history identifies the event, the reported onset, and the "
            "event-focused symptoms actually present in the record.",
            "The direct-versus-derivative analysis turns on whether the psychiatric "
            "response is focused on the triggering event or on subsequent pain, "
            "disability, treatment, or medical consequences.",
        ),
    ),
    (
        "compensable_consequence",
        (
            "The psychiatric condition developed in the course of the applicant's "
            "response to [pain, physical limitation, treatment, surgery, sleep "
            "disruption, medication effects, loss of function, or inability to "
            "work] following the physical injury.",
            "The history distinguishes the precipitating industrial physical injury "
            "from the later medical effects to which the psychiatric symptoms are "
            "attributed.",
            "The physical injury and its medical effects remain actual events of "
            "employment for the section 3208.3(b)(1) analysis.",
        ),
    ),
    (
        "safety_officer_ptsd",
        (
            "The applicant reports trauma-related symptoms following [specific event "
            "or grounded repeated occupational exposure] while serving as [covered "
            "role].",
            "The diagnosis is addressed under the most recent applicable DSM edition; "
            "the report does not infer a diagnosis from occupation or exposure alone.",
            "The medical report addresses diagnosis and manifestation. Application of "
            "the statutory presumption and the ultimate burden-of-proof result remain "
            "legal determinations.",
        ),
    ),
)

#: Source: 8 CCR §§41, 43, and 49.8 plus the generic protocol gap documented
#: in ``psych-qme-report-anatomy.md``; no instrument or scored result is added.
PSYCH_QME_PROTOCOL_REGISTER: Final[_ClauseRegister] = (
    (
        "evaluation_protocol",
        (
            "The undersigned personally conducted the clinical interview, "
            "mental-status examination, and psychiatric record review.",
            "The evaluation considered the applicant's reported history, the records "
            "identified below, the mental-status examination, and available diagnostic "
            "testing.",
            "Psychological testing was performed and considered together with the "
            "clinical interview, mental-status examination, and records reviewed.",
            "Testing was not treated as the sole basis for diagnosis or causation.",
        ),
    ),
)

#: Source: *Rolda v. Pitney Bowes, Inc.* and the medical-versus-legal role
#: boundary collected in ``psych-harassment-gfpa.md``.
PSYCH_ROLDA_REGISTER: Final[_ClauseRegister] = (
    (
        "four_step_walk",
        (
            "After consideration of the medical, documentary, and testimonial "
            "evidence, the trier of fact must determine: (1) whether the alleged "
            "psychiatric injury involves actual events of employment, a factual/legal "
            "determination; (2) if so, whether those actual events were the predominant "
            "cause of the psychiatric injury, a determination requiring medical "
            "evidence; (3) if so, whether any actual employment events were personnel "
            "actions that were lawful, nondiscriminatory, and in good faith, a "
            "factual/legal determination; and (4) if so, whether those lawful, "
            "nondiscriminatory, good-faith personnel actions were a substantial cause "
            "of the psychiatric injury, a determination requiring medical evidence.",
            "Whether [disputed events] occurred, and whether a personnel action was "
            "lawful, nondiscriminatory, and in good faith, are factual/legal questions. "
            "Assuming the trier of fact finds [predicate], it is my opinion within "
            "reasonable medical probability that [medical causation finding].",
        ),
    ),
)

#: Source: Labor Code §3208.3(b), (d), (e), and (h), *McCullough*, and the
#: §3212.15 displacement rule documented in the Part 5 research notes.
PSYCH_THRESHOLD_REGISTER: Final[_ClauseRegister] = (
    (
        "ordinary_direct",
        (
            "Actual events of employment must be predominant as to all causes "
            "combined, meaning greater than 50 percent.",
        ),
    ),
    (
        "compensable_consequence",
        (
            "The industrial physical injury and its medical effects are qualifying "
            "actual events and must be predominant as to all causes combined.",
        ),
    ),
    (
        "violent_act",
        (
            "Actual events must be a substantial cause, meaning at least 35 to 40 "
            "percent.",
        ),
    ),
    (
        "six_month",
        (
            "Labor Code section 3208.3(d) requires six months of employment unless "
            "the injury was caused by a sudden and extraordinary employment condition.",
        ),
    ),
    (
        "gfpa",
        (
            "Labor Code section 3208.3(h) places the burden on the party asserting "
            "that lawful, nondiscriminatory, good-faith personnel actions substantially "
            "caused the injury.",
        ),
    ),
    (
        "post_termination",
        (
            "Labor Code section 3208.3(e) applies when the claim was filed after "
            "notice of termination or layoff, subject to its enumerated exceptions.",
        ),
    ),
)

#: Source: the three authored case exemplars collected in
#: ``psych-harassment-gfpa.md``; these are never sampled defaults.
PSYCH_ACTUAL_EVENTS_REGISTER: Final[_ClauseRegister] = (
    (
        "harassment_personnel_outside",
        (
            "45% reported harassment/humiliation/hostile-work-environment events",
            "30% personnel actions",
            "25% outside or preexisting factors",
        ),
    ),
    (
        "assault_other_employment",
        (
            "65% traumatic assault itself",
            "35% other employment events, including coworker/supervisor or "
            "personnel-action events",
        ),
    ),
    (
        "adverse_work_acute_nonindustrial",
        (
            "55% chronic adverse-work/discrimination circumstances",
            "25% acute workplace events",
            "20% cannabis or another specifically grounded nonindustrial factor",
        ),
    ),
)

#: Source: Labor Code §3212.15 and the dated DSM table in
#: ``psych-ptsd-safety-officers.md``.
PSYCH_SAFETY_OFFICER_REGISTER: Final[_ClauseRegister] = (
    (
        "presumption",
        (
            "Labor Code section 3212.15 applies to post-traumatic stress disorder "
            "diagnosed according to the most recent edition of the Diagnostic and "
            "Statistical Manual and developing or manifesting during qualifying service.",
            "The presumption is disputable. Once its predicates are established, the "
            "burden shifts to the defendant to affirmatively controvert industrial "
            "causation.",
            "In the absence of evidence affirmatively controverting the presumption, "
            "the ordinary Rolda analysis, including the good-faith-personnel-action "
            "contention, is not reached.",
        ),
    ),
    (
        "violent_mechanism",
        (
            "The violent-act inquiry concerns the mechanism: strong physical force, "
            "extreme or intense force, or an act that was vehemently or passionately "
            "threatening.",
        ),
    ),
    (
        "catastrophic_nature",
        (
            "The factors are nonexclusive, and not every factor must apply. The "
            "inquiry concerns the physical injury independently of the psychiatric "
            "condition.",
        ),
    ),
)

#: Source: the 2005 Schedule for Rating Permanent Disabilities GAF-to-WPI
#: instruction, retained as physician prose only.
PSYCH_GAF_PDRS_REGISTER: Final[_ClauseRegister] = (
    (
        "post_2004",
        (
            "Starting at the top level of the GAF scale, I evaluated each range by "
            "asking whether either symptom severity or level of functioning was worse "
            "than the range description. I moved downward until reaching the range "
            "that best matched whichever was worse, checked the next lower range "
            "against stopping prematurely, and selected the specific score within the "
            "ten-point range according to the severity and frequency of the supported "
            "findings.",
            "Using that method, I assign a current GAF of [GAF]. Under the 2005 "
            "Schedule for Rating Permanent Disabilities GAF-to-WPI table, a GAF of "
            "[GAF] corresponds to [WPI] percent whole person impairment.",
        ),
    ),
    (
        "pre_2005",
        (
            "Psychiatric impairment was evaluated under the protocol applicable to "
            "the date of injury.",
        ),
    ),
)

#: Source: Labor Code §4660.1(c), *Larsen*, and *Wilson* as summarized in
#: ``psych-compensable-consequence-vs-direct.md``.
PSYCH_SECTION_4660_1C_REGISTER: Final[_ClauseRegister] = (
    (
        "direct_qme",
        (
            "Within reasonable medical probability, the psychiatric injury was "
            "predominantly caused by [event] itself and not as a sequela of the "
            "physical injuries sustained. It is therefore a primary injury, not a "
            "derivative or secondary psychiatric injury.",
        ),
    ),
    (
        "consequence_qme",
        (
            "Within reasonable medical probability, the psychiatric injury is a "
            "sequela of and derivative of the industrial physical injury, specifically "
            "[grounded physical-injury effects]. The condition may remain industrial "
            "and compensable even though Labor Code section 4660.1(c)(1) limits an "
            "additional psychiatric impairment rating.",
        ),
    ),
    (
        "applicant_direct",
        (
            "Applicant contends that the psychiatric injury was directly caused by "
            "the events of employment and that Labor Code section 4660.1(c) therefore "
            "does not bar an increased impairment rating. Alternatively, applicant "
            "relies on [the existing violent-act or catastrophic-injury theory].",
        ),
    ),
)

#: Source: the three counsel-supplied contest theories in Counsel Set Three;
#: keys remain the frozen ``DefenseContestTheory`` members.
PSYCH_DEFENSE_CONTEST_REGISTER: Final[_ClauseRegister] = (
    (
        "insufficient_investigation",
        (
            "The report does not identify the personnel records, performance "
            "materials, disciplinary documents, or sworn statements necessary to "
            "evaluate the alleged employment events.",
            "The evaluator should identify which events are assumed to have occurred, "
            "which records support those assumptions, and what information remains "
            "unavailable.",
            "Without that factual development, the medical percentage cannot resolve "
            "whether the alleged events occurred or whether a personnel action was "
            "lawful, nondiscriminatory, and in good faith.",
        ),
    ),
    (
        "post_termination",
        (
            "The psychiatric claim was presented after notice of termination or "
            "layoff, and Labor Code section 3208.3(e) must be addressed.",
            "The present record must identify the dates of notice, filing, and injury "
            "and must identify evidence supporting any statutory exception.",
            "Absent those dates and records, the evaluator should reserve the "
            "post-termination analysis rather than assume that an exception applies.",
        ),
    ),
    (
        "lack_of_substantial_medical_evidence",
        (
            "A compensability opinion must be stated within reasonable medical "
            "probability, rest on an adequate examination and history, consider the "
            "pertinent facts, and explain the reasoning supporting its conclusion.",
            "The report does not adequately explain how the identified employment "
            "events produced the diagnosis or how the stated percentage was selected.",
            "An opinion based on speculation, an incomplete history, facts no longer "
            "germane, or an incorrect legal theory does not constitute substantial "
            "medical evidence.",
        ),
    ),
)

#: Source: the carrier-specific advocacy, objection, supplemental, and sworn
#: question forms in ``psych-qme-report-anatomy.md``.
PSYCH_CONTENTION_SURFACE_REGISTER: Final[_ClauseRegister] = (
    (
        "advocacy",
        (
            "Please state whether the psychiatric injury was caused by the employment "
            "event itself rather than by later pain, disability, or treatment.",
            "Please state the percentage of total psychiatric-injury causation "
            "attributable to actual events of employment.",
            "Please address separately whether Labor Code section 4660.1(c)(1) applies "
            "and whether either paragraph (c)(2) exception is supported.",
        ),
    ),
    (
        "objection",
        (
            "The report's history attributes the psychiatric symptoms to [grounded "
            "consequence facts], but the conclusion characterizes the injury as direct "
            "without reconciling that history.",
            "The report does not separate causation of psychiatric injury under "
            "section 3208.3 from apportionment of permanent disability under section "
            "4663.",
        ),
    ),
    (
        "supplemental_request",
        (
            "1. Identify the actual events of employment assumed in forming your opinion.",
            "2. State the percentage of total causation resulting from those events.",
            "3. Distinguish event-focused symptoms from symptoms arising from pain, "
            "disability, treatment, or other physical-injury effects.",
            "4. State whether the psychiatric injury is direct or a compensable "
            "consequence and explain why.",
            "5. Address the six-month, post-termination, good-faith-personnel-action, "
            "violent-act, and section 4660.1(c) issues that are actually presented by "
            "the record.",
        ),
    ),
    (
        "qme_deposition",
        (
            "Doctor, is your opinion that the psychiatric condition arose from the "
            "event itself or from the medical effects of the physical injury?",
            "What history supports that distinction?",
            "What percentage of total injury causation do you assign to actual events "
            "of employment?",
            "Which parts of your answer are medical opinions, and which predicates do "
            "you leave to the trier of fact?",
        ),
    ),
)

#: Source: ``salerno-register-notes.md`` and the frozen R58 sparse-field
#: contract; the two forms deliberately add no unbound clinical fact.
IMR_APPLICATION_REGISTER: Final[_ClauseRegister] = (
    (
        "case_specific_rebuttal",
        (
            "The utilization-review determination denied [treatment] because "
            "[grounded denial reason]. [Supporting record] documents [grounded "
            "clinical fact], which addresses the stated criterion because [authored "
            "or grounded explanation].",
        ),
    ),
    (
        "generic_rebuttal",
        (
            "The requested treatment is medically necessary for the industrial "
            "condition. Reconsideration of the utilization-review determination is "
            "requested.",
        ),
    ),
    (
        "mtus",
        (
            "The request is submitted under [grounded MTUS citation].",
            "The cited criterion is addressed by [grounded case fact].",
        ),
    ),
)


_PSYCH_REGISTER_KEYS: Final[tuple[str, ...]] = (
    "harassment_gfpa",
    "direct_physical_event",
    "compensable_consequence",
    "safety_officer_ptsd",
)
_PSYCH_REGISTER_PRECEDENCE: Final[tuple[str, ...]] = (
    "safety_officer_ptsd",
    "harassment_gfpa",
    "compensable_consequence",
    "direct_physical_event",
)


def _register_clauses(register: _ClauseRegister, key: str) -> tuple[str, ...]:
    """The first declared clause collection for *key*, or the empty tuple."""
    return next((clauses for name, clauses in register if name == key), ())


def _psych_visible_text(story: DocumentMedicalStory) -> str:
    """All document-visible semantic prose, solely for grounded slot filling."""
    values: list[str] = []
    for condition in story.conditions:
        values.append(condition.label)
    for contention in story.contentions:
        values.extend(contention.doctrine_hooks)
        if contention.rationale:
            values.append(contention.rationale)
    opinion = story.medical_opinion
    if opinion is not None:
        for value in (
            opinion.rationale,
            opinion.revision_rationale,
            opinion.aoe_coe_rationale,
        ):
            if value:
                values.append(value)
    for row in story.apportionments:
        for value in (
            row.description,
            row.causal_rationale,
            row.percentage_rationale,
            row.revision_rationale,
        ):
            if value:
                values.append(value)
    return " ".join(values)


def _psych_speaking_kind(story: DocumentMedicalStory) -> str | None:
    """Direct/consequence value of the document's actual speaking layer."""
    if story.contention_surface is not None:
        return next(
            (
                contention.psych_injury_kind
                for contention in story.contentions
                if contention.psych_injury_kind is not None
            ),
            None,
        )
    opinion = story.medical_opinion
    return opinion.psych_injury_kind if opinion is not None else None


_SECTION_3212_15_ROLES: Final[frozenset[str]] = frozenset(
    {
        "firefighter",
        "firefighter/paramedic",
        "peace officer",
        "police officer",
        "sheriff's deputy",
        "deputy sheriff",
        "correctional officer",
        "office of emergency services fire/rescue coordinator",
    }
)


def _psych_safety_officer_role(template: Any, story: DocumentMedicalStory) -> str | None:
    """A §3212.15 role from structured cast facts, never narrative matching."""
    diagnoses = {
        condition.id
        for condition in story.conditions
        if condition.body_system == "psychiatric"
        and (
            "post-traumatic stress disorder" in condition.label.lower()
            or condition.label.strip().lower() == "ptsd"
        )
    }
    if not diagnoses:
        return None
    opinion = story.medical_opinion
    if opinion is not None and not diagnoses.intersection(opinion.reviewed_condition_ids):
        return None
    employer = getattr(getattr(template, "case", None), "employer", None)
    role = str(getattr(employer, "position", "") or "").strip()
    industry = str(getattr(employer, "department", "") or "").strip().lower()
    if industry != "government" or role.lower() not in _SECTION_3212_15_ROLES:
        return None
    return role


def _psych_register_key(template: Any, story: DocumentMedicalStory) -> str | None:
    """First applicable private register key in R80's frozen precedence."""
    applicable: set[str] = set()
    if _psych_safety_officer_role(template, story) is not None:
        applicable.add("safety_officer_ptsd")
    if any("gfpa" in contention.doctrine_hooks for contention in story.contentions):
        applicable.add("harassment_gfpa")
    speaking_kind = _psych_speaking_kind(story)
    if speaking_kind == "compensable_consequence":
        applicable.add("compensable_consequence")
    elif speaking_kind == "direct":
        applicable.add("direct_physical_event")
    return next((key for key in _PSYCH_REGISTER_PRECEDENCE if key in applicable), None)


def _first_grounded_phrase(visible: str, phrases: tuple[str, ...]) -> str | None:
    lowered = visible.lower()
    return next((phrase for phrase in phrases if phrase in lowered), None)


def _grounded_employment_events(visible: str) -> str:
    found = [
        phrase
        for phrase in (
            "performance evaluation",
            "progressive discipline",
            "discipline",
            "transfer",
            "supervision",
            "termination",
            "reported mistreatment",
            "reported discrimination",
            "harassment",
            "humiliation",
        )
        if phrase in visible.lower()
    ]
    return ", ".join(dict.fromkeys(found)) or "the employment events described in the record"


def _grounded_event(visible: str) -> str:
    return _first_grounded_phrase(
        visible,
        (
            "traumatic assault",
            "workplace assault",
            "violent workplace event",
            "industrial event",
            "employment event",
            "reported employment events",
        ),
    ) or "the employment event described in the record"


def _grounded_effects(visible: str) -> tuple[str, ...]:
    lowered = visible.lower()
    return tuple(
        phrase
        for phrase in (
            "pain",
            "physical limitation",
            "treatment",
            "surgery",
            "sleep disruption",
            "medication effects",
            "loss of function",
            "inability to work",
            "disability",
        )
        if phrase in lowered
    )


def _story_psych_complaint_text(template: Any, story: DocumentMedicalStory) -> str:
    """R82 complaint-family prose with only visible, deterministic slots."""
    key = _psych_register_key(template, story)
    if key is None:
        return (
            "The available history identifies no more specific psychiatric "
            "mechanism than the facts stated in the records reviewed."
        )
    clauses = list(_register_clauses(PSYCH_HISTORY_REGISTER, key))
    visible = _psych_visible_text(story)
    if key == "harassment_gfpa":
        events = _grounded_employment_events(visible)
        description = _first_grounded_phrase(
            visible,
            (
                "hostile work environment",
                "pushed out",
                "micromanaged",
                "humiliation",
                "mistreatment",
                "discrimination",
                "increased scrutiny",
            ),
        ) or "the work circumstances described in the record"
        history = events
        clauses[0] = clauses[0].replace("[specific employment events]", events).replace(
            "[grounded description]", description
        )
        clauses[1] = clauses[1].replace(
            "[performance review, discipline, transfer, supervision, termination, "
            "reported mistreatment, or reported discrimination]",
            history,
        )
    elif key == "direct_physical_event":
        clauses[0] = clauses[0].replace("[event]", _grounded_event(visible))
        has_onset = any(condition.onset is not None for condition in story.conditions)
        symptom = _first_grounded_phrase(
            visible,
            ("fear", "anxiety", "depressed mood", "trauma-related symptoms"),
        )
        if symptom is None:
            clauses[1] = (
                "The history identifies the event and the reported onset."
                if has_onset
                else "The history identifies the event."
            )
    elif key == "compensable_consequence":
        effects = _grounded_effects(visible)
        if effects:
            clauses[0] = clauses[0].replace(
                "[pain, physical limitation, treatment, surgery, sleep disruption, "
                "medication effects, loss of function, or inability to work]",
                ", ".join(effects),
            )
        else:
            clauses.pop(0)
    else:
        role = _psych_safety_officer_role(template, story)
        event = _grounded_event(visible)
        if role is None:
            clauses.pop(0)
        else:
            clauses[0] = clauses[0].replace(
                "[specific event or grounded repeated occupational exposure]", event
            ).replace("[covered role]", role)
    return " ".join(clauses)


def _story_psych_protocol_text() -> str:
    protocol = _register_clauses(PSYCH_QME_PROTOCOL_REGISTER, "evaluation_protocol")
    return " ".join(
        (
            protocol[0],
            protocol[1],
            "Psychiatric disability or impairment was evaluated under 8 CCR §43. "
            "Evaluator scope-of-training requirements are addressed by 8 CCR §41.",
        )
    )


def _story_psych_testing_text() -> str:
    protocol = _register_clauses(PSYCH_QME_PROTOCOL_REGISTER, "evaluation_protocol")
    return " ".join(protocol[2:])


def _story_actual_events_allocation(story: DocumentMedicalStory) -> str | None:
    """An authored exemplar only when its complete literal is visible."""
    rationale = (
        story.medical_opinion.aoe_coe_rationale
        if story.medical_opinion is not None
        else None
    )
    if not rationale:
        return None
    for _name, clauses in PSYCH_ACTUAL_EVENTS_REGISTER:
        if all(clause in rationale for clause in clauses):
            return "; ".join(clauses) + "."
    return None


def _story_psych_adoption_text(story: DocumentMedicalStory) -> str | None:
    opinion = story.medical_opinion
    if opinion is None:
        return None
    contentions = {contention.id: contention for contention in story.contentions}
    endorsed = [
        contentions[contention_id]
        for contention_id in opinion.endorses_contention_ids
        if contention_id in contentions
    ]
    if endorsed:
        theory = endorsed[0].rationale or "the psychiatric-injury characterization"
        return (
            "After review of the communication and the identified supporting "
            f"evidence, I adopt {theory.rstrip('.')} as my own medical opinion for "
            "the reasons stated here."
        )
    concurrence_ids = set(opinion.concurs_with_contention_ids)
    if concurrence_ids.intersection(contentions):
        return (
            "My conclusion is independently based on the examination, records, and "
            "medical reasoning stated in this report."
        )
    return None


def _medical_story_of(doc_spec: Any) -> DocumentMedicalStory | None:
    """The document-scoped medical story, when the renderer bound one (R11).

    ``None`` is the ordinary answer for every medical-story-absent case and
    for every ungoverned document, and every override below delegates to the
    exact pre-M3 path on it — no new draw, flowable, context mutation or
    normalization.
    """
    context = getattr(doc_spec, "context", None)
    if isinstance(context, dict):
        story = context.get("medical_story")
        if isinstance(story, DocumentMedicalStory):
            return story
    return None


def _story_of(template: Any) -> DocumentMedicalStory | None:
    """The story for the document being rendered, via the captured spec."""
    return _medical_story_of(getattr(template, "doc_spec", None))


def _region_text(body_part: str | None) -> str:
    return (body_part or "the affected region").replace("_", " ")


_BMI_PHRASE = {
    "normal_or_under": "a normal or under-weight body habitus",
    "overweight": "an overweight body habitus",
    "obese": "an obese body habitus",
    "severely_obese": "a severely obese body habitus",
}

_SMOKING_PHRASE = {
    "never": "has never smoked",
    "former": "is a former smoker",
    "current": "is a current smoker",
}


def _story_reference_line(reference: StoryRecordReference) -> str:
    role = reference.author_role.replace("_", " ")
    return (
        f"• {reference.title} of "
        f"{reference.doc_date.strftime('%B %d, %Y')} ({role})"
    )


def _story_records_text(story: DocumentMedicalStory, *, examined: bool = True) -> str:
    """The R10 records list: actual earlier planned documents, or what is absent.

    Never falls back to a generic provider pool and never fabricates a
    provider, date, diagnostic or report: when no qualifying record exists the
    section says so and states what the opinion rests on instead.
    """
    if not story.record_references:
        basis = (
            "the history obtained and the examination performed"
            if examined
            else "the history available and the prior evaluation in this matter"
        )
        return (
            "No qualifying medical records were received for review. The "
            f"opinions stated in this report rest on {basis}."
        )
    lines = "\n".join(
        _story_reference_line(reference) for reference in story.record_references
    )
    return (
        "The following records from this file were reviewed in preparation "
        "for this evaluation:\n\n" + lines
    )


def _story_pmh_text(story: DocumentMedicalStory) -> str:
    """The past-medical-history narrative, from visible facts only (R9)."""
    demographics = story.demographics
    sentences = [
        f"The applicant is a {demographics.age}-year-old {demographics.sex} "
        f"with {_BMI_PHRASE[demographics.bmi_band]} who "
        f"{_SMOKING_PHRASE[demographics.smoking_status]}."
    ]
    for condition in story.conditions:
        region = (
            f" involving the {_region_text(condition.body_part)}"
            if condition.body_part
            else ""
        )
        onset = (
            f", with onset in {condition.onset.strftime('%B %Y')}"
            if condition.onset
            else ""
        )
        sentence = (
            f"The record documents {condition.label}{region}{onset}, "
            f"{condition.severity} in severity and {condition.trajectory} in "
            "course."
        )
        if condition.symptomatic_before_doi is True:
            sentence += " This condition was symptomatic before the date of injury."
        elif condition.symptomatic_before_doi is False:
            sentence += (
                " This condition was not symptomatic before the date of injury."
            )
        if condition.billing_coded:
            sentence += " It is coded in this claim's own medical billing."
        sentences.append(sentence)
    if not story.conditions:
        sentences.append(
            "The available records do not document significant pre-existing "
            "medical conditions."
        )
    sentences.extend(_story_prior_claim_sentences(story))
    return " ".join(sentences)


def _story_prior_claim_sentences(story: DocumentMedicalStory) -> list[str]:
    sentences: list[str] = []
    for claim in story.prior_claims:
        parts = ", ".join(_region_text(part) for part in claim.body_parts)
        sentences.append(
            "The applicant filed a prior workers' compensation claim with a "
            f"date of injury of {claim.date_of_injury.strftime('%B %d, %Y')} "
            f"involving the {parts}, resolved by "
            f"{claim.resolution_type.replace('_', ' ')}."
        )
    for award in story.prior_awards:
        parts = ", ".join(_region_text(part) for part in award.body_parts)
        sentences.append(
            f"A prior permanent disability award of {award.pd_percent} percent "
            f"issued on {award.award_date.strftime('%B %d, %Y')} covering the "
            f"{parts}."
        )
    return sentences


def _story_psych_history_text(story: DocumentMedicalStory) -> str:
    psychiatric = [
        condition
        for condition in story.conditions
        if condition.body_system == "psychiatric"
    ]
    if not psychiatric:
        return (
            "The available records do not document prior psychiatric "
            "diagnosis or treatment."
        )
    sentences = []
    for condition in psychiatric:
        onset = (
            f", with onset in {condition.onset.strftime('%B %Y')}"
            if condition.onset
            else ""
        )
        sentences.append(
            f"The record documents {condition.label}{onset}, "
            f"{condition.severity} in severity and {condition.trajectory} in "
            "course."
        )
    return " ".join(sentences)


def _story_psych_records_text(story: DocumentMedicalStory) -> str:
    """R9 psych row — categorized REVIEW OF RECORDS with missing statements."""
    taxonomy = effective_taxonomy()
    treatment: list[StoryRecordReference] = []
    medlegal: list[StoryRecordReference] = []
    for reference in story.record_references:
        if taxonomy.parent_of(reference.subtype) == "MEDICAL_CLINICAL":
            treatment.append(reference)
        else:
            medlegal.append(reference)
    blocks: list[str] = []
    if treatment:
        blocks.append(
            "Medical treatment records reviewed:\n"
            + "\n".join(_story_reference_line(reference) for reference in treatment)
        )
    else:
        blocks.append(
            "No medical treatment records were received for review; treatment "
            "history rests on the applicant's account and the records "
            "identified below, if any."
        )
    if medlegal:
        blocks.append(
            "Medical-legal reports reviewed:\n"
            + "\n".join(_story_reference_line(reference) for reference in medlegal)
        )
    else:
        blocks.append("No prior medical-legal reports were received for review.")
    blocks.append(_story_psych_protocol_text())
    return "\n\n".join(blocks)


def _story_psych_causation_text(story: DocumentMedicalStory) -> str:
    """The psych causation conclusion, from the opinion's semantic fields."""
    opinion = story.medical_opinion
    if opinion is None:
        return (
            "Psychiatric injury causation is addressed on the record reviewed, "
            "the clinical interview, and the mental status examination."
        )
    sentences: list[str] = []
    if opinion.psych_injury_kind == "direct":
        sentences.append(
            "Within reasonable medical probability, the psychiatric injury "
            "was caused by the events of employment themselves and is a "
            "primary psychiatric injury."
        )
    elif opinion.psych_injury_kind == "compensable_consequence":
        sentences.append(
            "Within reasonable medical probability, the psychiatric "
            "condition developed as a consequence of the industrial physical "
            "injury and its medical effects."
        )
    if opinion.aoe_coe_finding == "industrial":
        sentences.append(
            "The psychiatric condition arose out of and in the course of "
            "employment."
        )
    elif opinion.aoe_coe_finding == "nonindustrial":
        sentences.append(
            "The psychiatric condition did not arise out of and in the "
            "course of employment."
        )
    elif opinion.aoe_coe_finding == "deferred":
        sentences.append(
            "The AOE/COE determination for the psychiatric condition is "
            "deferred pending the outstanding records identified in this "
            "report."
        )
    if opinion.aoe_coe_rationale:
        sentences.append(str(opinion.aoe_coe_rationale))
    if _story_actual_events_allocation(story) is not None and story.apportionments:
        sentences.append(
            "The percentages above address causation of the psychiatric injury "
            "under Labor Code section 3208.3. Apportionment of permanent disability "
            "under section 4663 is a separate analysis."
        )
    adoption = _story_psych_adoption_text(story)
    if adoption is not None:
        sentences.append(adoption)
    if not sentences:
        sentences.append(
            "Psychiatric injury causation is addressed on the record "
            "reviewed, the clinical interview, and the mental status "
            "examination."
        )
    return " ".join(sentences)


def _story_psych_3208_text(template: Any, story: DocumentMedicalStory) -> str:
    """R83/R85 statutory walk selected only by the speaking layer's facts."""
    opinion = story.medical_opinion
    key = _psych_register_key(template, story)
    doc_date = getattr(getattr(template, "doc_spec", None), "doc_date", None)
    before_sunset = doc_date is not None and doc_date.year < 2029
    if key == "safety_officer_ptsd" and before_sunset:
        clauses = list(
            _register_clauses(PSYCH_SAFETY_OFFICER_REGISTER, "presumption")
        )
        dsm = (
            "DSM-5-TR, as the most recent DSM edition."
            if (doc_date.year, doc_date.month, doc_date.day) >= (2022, 3, 18)
            else "DSM-5, as the most recent DSM edition."
        )
        clauses.append(f"The diagnosis is addressed under {dsm}")
        clauses.append(
            "Labor Code section 3212.15 remains in force through January 1, 2029."
        )
        return " ".join(clauses)

    consequence = bool(
        opinion is not None
        and opinion.psych_injury_kind == "compensable_consequence"
    )
    paragraphs = list(_register_clauses(PSYCH_ROLDA_REGISTER, "four_step_walk"))
    disputed = "the reported employment events"
    finding = (
        "those actual events were predominant as to all causes combined"
        if consequence or (opinion is not None and opinion.aoe_coe_finding == "industrial")
        else "the medical causation issue remains reserved on the present record"
    )
    paragraphs[1] = (
        paragraphs[1]
        .replace("[disputed events]", disputed)
        .replace("[predicate]", "that the reported employment events occurred")
        .replace("[medical causation finding]", finding)
    )

    exception = next(
        (
            row.psych_exception_analysis
            for row in story.apportionments
            if row.psych_exception_analysis not in (None, "none_applies")
        ),
        None,
    )
    threshold_key = (
        "violent_act"
        if exception in {"violent_act", "direct_exposure"}
        else ("compensable_consequence" if consequence else "ordinary_direct")
    )
    paragraphs.extend(_register_clauses(PSYCH_THRESHOLD_REGISTER, threshold_key))
    if consequence:
        paragraphs.append(
            "Labor Code section 3208.3(b)(1)'s predominant-cause threshold applies. "
            "The industrial physical injury and its medical effects are treated as "
            "qualifying actual events of employment. Those events must be predominant "
            "as to all causes combined unless Labor Code section 3208.3(b)(2)'s "
            "violent-act standard applies."
        )
    paragraphs.append(
        "Labor Code section 3208.3(d) is considered only as the six-month "
        "employment rule and is not authority for bypassing predominant cause "
        "under Labor Code section 3208.3(b)(1)."
    )

    employer = getattr(getattr(template, "case", None), "employer", None)
    hire_date = getattr(employer, "hire_date", None)
    timeline = getattr(getattr(template, "case", None), "timeline", None)
    doi = getattr(timeline, "date_of_injury", None)
    if hire_date is not None and doi is not None and (doi - hire_date).days < 183:
        paragraphs.extend(_register_clauses(PSYCH_THRESHOLD_REGISTER, "six_month"))
        paragraphs.append(
            "The available dates require the six-month issue to be addressed; the "
            "sudden-and-extraordinary exception is not inferred from a violent-act "
            "contention."
        )
    if key == "harassment_gfpa":
        paragraphs.extend(_register_clauses(PSYCH_THRESHOLD_REGISTER, "gfpa"))
    context = getattr(getattr(template, "doc_spec", None), "context", None)
    theories = context.get("defense_contest_theories", ()) if isinstance(context, dict) else ()
    if "post_termination" in theories:
        paragraphs.extend(_register_clauses(PSYCH_THRESHOLD_REGISTER, "post_termination"))
    paragraphs.append(
        "The psychiatric condition is diagnosed using terminology and criteria "
        "generally approved and accepted nationally; Labor Code section 3208.3 does "
        "not itself expressly name DSM-5."
    )
    return " ".join(paragraphs)


def _story_psych_4660_text(
    template: Any, story: DocumentMedicalStory, date_of_injury: Any
) -> str:
    """The DOI-anchored §4660.1(c) structure from existing semantic fields."""
    opinion = story.medical_opinion
    if opinion is None:
        return (
            "The application of Labor Code section 4660.1(c) turns on the "
            "direct-versus-consequence classification of the psychiatric injury."
        )
    if getattr(date_of_injury, "year", 9999) < 2013:
        return (
            "The date of injury predates January 1, 2013, so Labor Code "
            "section 4660.1(c)'s limitation does not apply by date; the "
            "direct-versus-consequence and section 3208.3 analyses remain separate."
        )
    if opinion.psych_injury_kind == "direct":
        direct = _register_clauses(
            PSYCH_SECTION_4660_1C_REGISTER, "direct_qme"
        )[0].replace("[event]", _grounded_event(_psych_visible_text(story)))
        conclusion = (
            "Because the psychiatric injury is classified as a direct injury, "
            "Labor Code section 4660.1(c)(1) does not bar an increased psychiatric "
            "impairment rating on that ground."
        )
        return f"{direct} {conclusion}"
    if opinion.psych_injury_kind == "compensable_consequence":
        exception = next(
            (
                row.psych_exception_analysis
                for row in story.apportionments
                if row.psych_exception_analysis is not None
            ),
            None,
        )
        effects = _grounded_effects(_psych_visible_text(story))
        consequence = (
            _register_clauses(
                PSYCH_SECTION_4660_1C_REGISTER, "consequence_qme"
            )[0].replace(
                "[grounded physical-injury effects]", ", ".join(effects)
            )
            if effects
            else (
                "The available record supports a consequential classification but "
                "does not identify a more specific physical-injury effect."
            )
        )
        consequence += (
            " The impairment limitation does not decide whether the condition "
            "itself is industrial or compensable for treatment. The condition may "
            "remain industrial and compensable for treatment and temporary disability."
        )
        exception_text = ""
        if exception in {"violent_act", "direct_exposure"}:
            exception_text = " " + _register_clauses(
                PSYCH_SAFETY_OFFICER_REGISTER, "violent_mechanism"
            )[0]
        elif exception == "catastrophic_injury":
            exception_text = (
                " The available record does not permit an unsupported finding on "
                "treatment intensity, permanent physical outcome, activities of "
                "daily living, analogous injuries, or progressive disease. "
                + _register_clauses(
                    PSYCH_SAFETY_OFFICER_REGISTER, "catastrophic_nature"
                )[0]
            )
        return consequence + exception_text
    return (
        "The application of Labor Code section 4660.1(c) turns on the "
        "direct-versus-consequence classification of the psychiatric injury, "
        "which is addressed above on this record."
    )


def _story_tpr_causation_text(opinion: Any, final: bool) -> str:
    """The treating physician's independent causation finding (R14/R16).

    First-person clinical treatment voice: observed course, examinations,
    mechanism, and an independent AOE/COE conclusion. Never an
    attorney-responsive register — no communication is cited as the source of
    the finding.
    """
    sentences: list[str] = []
    if opinion.aoe_coe_finding == "industrial":
        sentences.append(
            "Based on the treatment course, the serial examinations, the "
            "reported mechanism of injury, and the clinical findings, it is "
            "my opinion that the condition arose out of and in the course of "
            "employment."
        )
    elif opinion.aoe_coe_finding == "nonindustrial":
        sentences.append(
            "Based on the treatment course, the serial examinations, the "
            "reported mechanism of injury, and the clinical findings, it is "
            "my opinion that the condition did not arise out of and in the "
            "course of employment."
        )
    elif opinion.aoe_coe_finding == "deferred":
        sentences.append(
            "The causation determination is deferred pending further records "
            "and clinical course; my working assessment rests on the "
            "treatment history and examinations to date."
        )
    else:
        sentences.append(
            "The causation conclusions stated in this report rest on the "
            "treatment course, the examinations performed, the reported "
            "mechanism of injury, and the clinical course observed."
        )
    if opinion.aoe_coe_rationale:
        sentences.append(str(opinion.aoe_coe_rationale))
    if opinion.psych_injury_kind == "direct":
        sentences.append(
            "The psychiatric component is assessed clinically as a direct "
            "injury arising from the events of employment themselves."
        )
    elif opinion.psych_injury_kind == "compensable_consequence":
        sentences.append(
            "The psychiatric component is assessed clinically as a "
            "compensable consequence of the physical injury and its effects."
        )
    if final and opinion.psych_injury_kind == "direct":
        sentences.append(
            "As classified, Labor Code section 4660.1(c) does not bar an "
            "increased psychiatric impairment rating on that ground."
        )
    elif final and opinion.psych_injury_kind == "compensable_consequence":
        sentences.append(
            "As classified, Labor Code section 4660.1(c) limits an "
            "additional psychiatric impairment rating; the condition may "
            "remain industrial and compensable for treatment."
        )
    return " ".join(sentences)


def _story_contention_sentence(position: int, contention: Any) -> str:
    """One numbered issue, from the contention's semantic fields only (R15)."""
    claim = contention.claim_type.replace("_", " ")
    target = (
        f" concerning the {_region_text(contention.target_body_part)}"
        if contention.target_body_part
        else ""
    )
    stance = "affirms" if contention.position == "affirm" else "denies"
    sentence = (
        f"{position}. The {contention.party} {stance} the issue of "
        f"{claim}{target}."
    )
    if contention.psych_injury_kind == "direct":
        sentence += (
            " The psychiatric injury is characterized as a direct injury "
            "caused by the events of employment themselves."
        )
    elif contention.psych_injury_kind == "compensable_consequence":
        sentence += (
            " The psychiatric injury is characterized as a compensable "
            "consequence of the physical injury."
        )
    if contention.requested_apportionment == "apply":
        sentence += (
            " Apportionment of permanent disability should be applied on "
            "this record."
        )
    elif contention.requested_apportionment == "refuse":
        sentence += (
            " Apportionment of permanent disability should be refused on "
            "this record."
        )
    if (
        "hikida_treatment_carveout" in contention.doctrine_hooks
        or contention.treatment_causation is not None
    ):
        if (
            contention.treatment_causation == "contributing_cause"
            and contention.requested_apportionment == "apply"
        ):
            sentence += (
                " Industrial medical treatment contributed to the permanent "
                "disability, but other pathology also contributes; under "
                "Justice's narrowing of Hikida, statutory apportionment applies."
            )
        elif (
            contention.treatment_causation == "contributing_cause"
            and contention.requested_apportionment == "refuse"
        ):
            sentence += (
                " Industrial medical treatment contributed to the permanent "
                "disability, and the requested refusal of apportionment invokes "
                "Hikida even though Justice limits the carveout to disability "
                "caused solely by that treatment."
            )
        elif (
            contention.treatment_causation == "sole_cause"
            and contention.requested_apportionment == "apply"
        ):
            sentence += (
                " Industrial medical treatment is stated to be the sole cause "
                "of the permanent disability, while the requested result still "
                "applies apportionment contrary to the Hikida carveout as "
                "narrowed by Justice."
            )
        elif (
            contention.treatment_causation == "sole_cause"
            and contention.requested_apportionment == "refuse"
        ):
            sentence += (
                " Industrial medical treatment is stated to be the sole cause "
                "of the permanent disability; Hikida, as narrowed by Justice, "
                "therefore requires compensation without apportionment."
            )
    if contention.rationale:
        sentence += f" {contention.rationale.rstrip('.')}."
    return sentence


#: R30 — one professional clause per frozen defense-contest theory, rendered
#: in the tuple order the binding carries. Adversarial attorney prose, never
#: an analyzer verdict; the psych-specific litigation registers land with P5.
_DEFENSE_THEORY_SENTENCES: dict[str, str] = {
    "insufficient_investigation": (
        "The report does not identify the records, factual investigation, "
        "and history necessary to evaluate the issues presented, and the "
        "required investigation is incomplete."
    ),
    "post_termination": (
        "The record presents post-termination defenses that the report does "
        "not address, and the statutory analysis required for a claim "
        "presented after notice of termination or layoff must be made."
    ),
    "lack_of_substantial_medical_evidence": (
        "The report's conclusions are not stated upon an adequate history "
        "and examination with reasoned explanation, and do not constitute "
        "substantial medical evidence."
    ),
}


def _defense_theory_sentences(theories: Any) -> list[str]:
    return [_DEFENSE_THEORY_SENTENCES[theory] for theory in theories or ()]


def _psych_defense_theory_sentences(theories: Any) -> list[str]:
    """Every psych clause, preserving the binding's theory tuple order."""
    register = dict(PSYCH_DEFENSE_CONTEST_REGISTER)
    return [
        clause
        for theory in theories or ()
        for clause in register[str(theory)]
    ]


# ---------------------------------------------------------------------------
# Money
# ---------------------------------------------------------------------------

#: The bounds of ``compromise_and_release.py``'s gross-settlement draw.
#:
#: Matched exactly, so the interception can tell it from the four other
#: ``randint`` calls in the same method (costs, set-aside, and two identifier
#: digits). If the substrate edits these bounds the match stops firing — and
#: says so, loudly, because a silent miss is a manifest publishing a gross the
#: document contradicts.
_SUBSTRATE_SETTLEMENT_RANGE: tuple[int, int] = (25000, 150000)

#: The release's costs-and-expenses draw. Pinned as a fraction of the gross so
#: the deductions cannot exceed the settlement they come out of.
_SUBSTRATE_CR_COSTS_RANGE: tuple[int, int] = (500, 3000)

#: The release's Medicare set-aside draw, pinned for the same reason.
_SUBSTRATE_CR_MSA_RANGE: tuple[int, int] = (5000, 25000)

#: Header text of the substrate wage statement's pay-period table.
_PAY_TABLE_HEADER = "Pay Period"

#: First label of the substrate wage statement's summary table.
_SUMMARY_TABLE_LABEL = "Average Weekly Wage (AWW):"

#: The payment-record subtypes ``WageStatement`` also renders.
#:
#: The substrate registry routes all eight wage/payment subtypes to one class,
#: so the class has to know which document it is drawing. Named here rather than
#: inferred from a prefix, because ``WAGE_STATEMENTS_POST_INJURY`` is an
#: earnings document whose name begins the same way a payment record's does not.
BENEFIT_RECORD_SUBTYPES: frozenset[str] = frozenset(
    {
        "TD_PAYMENT_RECORD_ONGOING",
        "TD_PAYMENT_RECORD_RETROACTIVE",
        "PD_PAYMENT_RECORD_ADVANCE",
        "PD_PAYMENT_RECORD_ONGOING",
        "PD_PAYMENT_RECORD_FINAL",
    }
)

#: The words the wage statement uses for the derivation's own label.
#:
#: Printed verbatim so the method name is greppable in extracted text. The
#: method is the eval label; a label spelled one way in the manifest and another
#: on the page is a label an analyzer cannot be scored on.
METHOD_LABEL = "AWW Method:"

#: The caveat every rate line carries. Not decoration — the corpus must never
#: present an unverified statutory binding as a settled one, and a reader of the
#: document (as opposed to the manifest) sees only this.
UNCONFIRMED_NOTICE = "Statutory basis COUNSEL-UNCONFIRMED"

#: The same caveat, on the payment-due yardstick.
#:
#: The due-day count is as much a legal binding as a rate ceiling is, and it is
#: the baseline every ``days_late`` on the page is measured from. It carries its
#: own caveat for the same reason the rate line does: a reader of the document
#: never sees the manifest.
DUE_NOTICE = "COUNSEL-UNCONFIRMED"


#: The self-procured medical reimbursement draw in the substrate's stipulated
#: award. The second cash component on that page, and the one reconciled against
#: the award so the two sum to the published settlement gross.
_SUBSTRATE_STIPS_SELF_PROCURED_RANGE = (500, 5000)

#: The permanent-disability award draw in the substrate's stipulated award
#: (``pdf_templates/legal/stipulations.py``). Matched by its bounds so the
#: interception cannot catch the three other ``randint`` calls on the same page.
_SUBSTRATE_STIPS_AWARD_RANGE = (5000, 75000)


class _ForcedRandint:
    """A stand-in for :mod:`random` that answers one specific ``randint``.

    The counterpart of :class:`_ForcedChoice`, and for the same reason: the
    substrate computes a value at the top of a method and derives four more from
    it further down. Overriding the method would mean copying all of that to pin
    one number.

    Draws and discards on a match, so every later draw in the document reads the
    stream from where the substrate left it. Returning without drawing would
    shift the rest of the page.
    """

    __slots__ = ("_answer", "bounds", "fired")

    def __init__(self, answer: int, bounds: tuple[int, int]) -> None:
        self._answer = answer
        self.bounds = bounds
        self.fired = False

    def randint(self, low: int, high: int) -> int:
        if (low, high) == self.bounds:
            self.fired = True
            random.randint(low, high)
            return self._answer
        return random.randint(low, high)

    def __getattr__(self, name: Any) -> Any:
        return getattr(random, name)


class _ForcedChain:
    """Several :class:`_ForcedRandint` interceptions over one document.

    The stipulated award has two cash components that must reconcile to one
    published total, and they are drawn at different points in the same method.
    Each interception still matches on its own bounds, so the pair cannot catch
    each other's draw or the two non-monetary ones on the same page.
    """

    __slots__ = ("_members",)

    def __init__(self, members: list[_ForcedRandint]) -> None:
        self._members = members

    def randint(self, low: int, high: int) -> int:
        for member in self._members:
            if (low, high) == member.bounds:
                return member.randint(low, high)
        return random.randint(low, high)

    def __getattr__(self, name: Any) -> Any:
        return getattr(random, name)


def _find_table(story: list[Any], matches: Any) -> int:
    """Index of the first table in *story* whose cell values satisfy *matches*.

    ``-1`` when there is none, which every caller treats as "the substrate
    moved" and reports rather than guesses around.
    """
    for index, element in enumerate(story):
        values = getattr(element, "_cellvalues", None)
        if values and matches(values):
            return index
    return -1


def _money_table(rows: list[list[Any]], widths: list[float], styles: Any) -> Any:
    """A plain two-column figures table in the substrate's own visual register."""
    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle

    del styles  # matched to the substrate's tables by explicit style, not by theme
    table = Table(rows, colWidths=widths)
    table.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
                ("FONT", (0, 1), (-1, -1), "Helvetica", 9),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("ALIGN", (0, 0), (0, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return table


def _rewrite_wage_statement(story: list[Any], money: MoneyFacts, styles: Any) -> list[Any]:
    """Swap the drawn pay periods and the drawn summary for the ledger's.

    Two replacements, each keyed on the table's own text. A table that cannot be
    found is logged rather than skipped over silently: the document would then
    print invented earnings under a manifest publishing derived ones, which is
    the disagreement the whole layer exists to prevent, and it must not be
    possible to ship it quietly.
    """
    from reportlab.lib.units import inch

    wage = money.wages
    computation = wage.computation
    rate = wage.rate

    pay_index = _find_table(
        story, lambda values: bool(values) and _PAY_TABLE_HEADER in (values[0] or [])
    )
    if pay_index < 0:
        log.warning("fact_templates.wage_pay_table_not_found", header=_PAY_TABLE_HEADER)
    else:
        rows: list[list[Any]] = [
            ["Pay Period", "Employer", "Weeks", "Regular Pay", "OT Pay", "Gross Pay"]
        ]
        for period in wage.periods:
            rows.append(
                [
                    f"{period.period_start:%m/%d/%y}-{period.period_end:%m/%d/%y}",
                    "Concurrent" if period.concurrent else "Primary",
                    f"{period.weeks.normalize():f}",
                    f"${period.regular_gross:,.2f}",
                    f"${period.overtime_gross:,.2f}" if period.overtime_gross else "-",
                    f"${period.gross:,.2f}",
                ]
            )
        rows.append(
            [
                "TOTAL",
                "",
                f"{computation.weeks_considered.normalize():f}",
                "",
                "",
                f"${computation.gross_considered:,.2f}",
            ]
        )
        story[pay_index] = _money_table(
            rows,
            [1.4 * inch, 0.9 * inch, 0.6 * inch, 1.1 * inch, 0.9 * inch, 1.1 * inch],
            styles,
        )

    summary_index = _find_table(
        story,
        lambda values: any(
            row and str(row[0]).startswith(_SUMMARY_TABLE_LABEL) for row in values
        ),
    )
    if summary_index < 0:
        log.warning("fact_templates.wage_summary_table_not_found", label=_SUMMARY_TABLE_LABEL)
        return story

    basis = rate.basis
    bound_note = {
        "max": " (at statutory maximum)",
        "min": " (at statutory minimum)",
        "unbounded": "",
    }
    # Every row below is a governed manifest field, and that is not a
    # coincidence — ``GOVERNED_MONEY_FIELDS`` says a published fact is one a
    # document renders, and ``pattern``, ``basisAuthority`` and ``basisSource``
    # were published without ever reaching paper. Three labels an analyzer would
    # have been scored on recovering from a document that did not contain them.
    summary: list[list[Any]] = [
        ["Wage Summary", ""],
        [METHOD_LABEL, computation.method],
        ["Method Source:", computation.method_source],
        ["Basis of Method:", computation.method_reason],
        ["Earnings Pattern:", wage.pattern],
        ["Earnings Pattern Source:", wage.pattern_source],
        ["Concurrent Employment:", "yes" if wage.concurrent_employment else "no"],
        ["Earnings Considered:", f"${computation.gross_considered:,.2f}"],
        ["Weeks Considered:", f"{computation.weeks_considered.normalize():f}"],
        ["Periods Considered:", str(computation.periods_considered)],
    ]
    # Printed even at zero. `inKindWeekly` is published unconditionally, and a
    # governed field whose row appears only when the value is interesting is a
    # field an analyzer is scored on recovering from a page that does not carry
    # it. Zero is a fact about this file too.
    summary.append(["Non-Cash Wages (weekly):", f"${computation.in_kind_weekly:,.2f}"])
    summary.extend(
        [
            ["Average Weekly Wage (AWW):", f"${computation.aww:,.2f}"],
            [
                "Temporary Disability Rate:",
                f"${rate.td_weekly_rate:,.2f}/week{bound_note[rate.td_bound]}",
            ],
            # The bound token itself, not only the parenthetical. "Unbounded" has
            # no parenthetical — it renders as nothing — so the single most
            # consequential fact about a rate was recoverable from the page only
            # when it happened to be true. A capped rate is the same number for
            # every high earner in a vintage; an analyzer that recovers the
            # number without the cap has learnt nothing about the wage behind it,
            # and it cannot recover a word that is not there.
            ["TD Rate Bound:", rate.td_bound],
            [
                "Permanent Disability Rate:",
                f"${rate.pd_weekly_rate:,.2f}/week{bound_note[rate.pd_bound]}",
            ],
            ["PD Rate Bound:", rate.pd_bound],
            ["Rate Basis:", f"{basis.label} — {UNCONFIRMED_NOTICE}"],
            ["Rate Basis Source:", basis.source],
            ["Rate Basis Authority:", basis.authority],
        ]
    )
    story[summary_index] = _money_table(summary, [2.6 * inch, 3.4 * inch], styles)
    return story


def _rewrite_benefit_record(story: list[Any], money: MoneyFacts, styles: Any) -> list[Any]:
    """Turn the wage statement's tables into the carrier's payment history.

    The same substrate class renders both documents, so the same two tables are
    replaced — with what was *paid* rather than what was *earned*. Gaps and
    lateness are printed as their own rows rather than left for a reader to
    subtract out of the dates, because a delay the eval cannot see is a delay
    the corpus does not contain.
    """
    from reportlab.lib.units import inch

    benefits = money.benefits

    pay_index = _find_table(
        story, lambda values: bool(values) and _PAY_TABLE_HEADER in (values[0] or [])
    )
    if pay_index < 0:
        log.warning("fact_templates.benefit_pay_table_not_found", header=_PAY_TABLE_HEADER)
    else:
        # ``Due`` is here because ``Days Late`` is meaningless without it. The
        # first cut printed the lateness and kept its own yardstick — the due
        # date, computed one line above where it was discarded — off the page, so
        # the operational delay was asserted rather than derivable. This remains
        # an engine-cadence fact; §4650(d) uses the separate statutory schedule.
        rows: list[list[Any]] = [
            [
                "Benefit Period",
                "Type",
                "Weeks",
                "Weekly Rate",
                "Due",
                "Paid",
                "Days Late",
                "Amount",
            ]
        ]
        for period in benefits.td_periods:
            rows.append(
                [
                    f"{period.start:%m/%d/%y}-{period.end:%m/%d/%y}",
                    "TD",
                    f"{period.weeks.normalize():f}",
                    f"${period.weekly_rate:,.2f}",
                    f"{period.date_due:%m/%d/%y}",
                    f"{period.date_paid:%m/%d/%y}" if period.date_paid else "UNPAID",
                    str(period.days_late) if period.days_late else "-",
                    f"${period.amount:,.2f}",
                ]
            )
        for advance in benefits.pd_advances:
            rows.append(
                [
                    f"{advance.date_due:%m/%d/%y}",
                    "PD advance",
                    f"{advance.weeks.normalize():f}",
                    f"${advance.weekly_rate:,.2f}",
                    f"{advance.date_due:%m/%d/%y}",
                    f"{advance.date_paid:%m/%d/%y}",
                    str(advance.days_late) if advance.days_late else "-",
                    f"${advance.amount:,.2f}",
                ]
            )
        for gap in benefits.gaps:
            rows.append(
                [
                    f"{gap.start:%m/%d/%y}-{gap.end:%m/%d/%y}",
                    "NO BENEFITS PAID",
                    "",
                    "",
                    "",
                    "",
                    str(gap.days),
                    "$0.00",
                ]
            )
        if len(rows) == 1:
            rows.append(["-", "no benefits paid", "", "", "", "", "-", "$0.00"])
        story[pay_index] = _money_table(
            rows,
            [
                1.2 * inch,
                0.9 * inch,
                0.45 * inch,
                0.8 * inch,
                0.65 * inch,
                0.65 * inch,
                0.55 * inch,
                0.85 * inch,
            ],
            styles,
        )

    summary_index = _find_table(
        story,
        lambda values: any(
            row and str(row[0]).startswith(_SUMMARY_TABLE_LABEL) for row in values
        ),
    )
    if summary_index < 0:
        log.warning("fact_templates.benefit_summary_table_not_found")
        return story

    rate = money.wages.rate
    summary: list[list[Any]] = [
        ["Benefit Summary", ""],
        ["Average Weekly Wage (AWW):", f"${money.aww:,.2f}"],
        [METHOD_LABEL, money.method],
        ["Temporary Disability Rate:", f"${rate.td_weekly_rate:,.2f}/week"],
        ["Temporary Disability Periods:", str(len(benefits.td_periods))],
        ["Total Temporary Disability Paid:", f"${benefits.td_total:,.2f}"],
        ["Permanent Disability Advance Count:", str(len(benefits.pd_advances))],
        ["Permanent Disability Advances:", f"${benefits.pd_total:,.2f}"],
        ["Payment Due Within (days of period end):", f"{TD_PAYMENT_DUE_DAYS} — {DUE_NOTICE}"],
        ["Payment Due Authority:", TD_PAYMENT_DUE_AUTHORITY],
        ["PD Advance Interval (days):", str(PD_ADVANCE_INTERVAL_DAYS)],
        ["PD Advance Schedule Authority:", PD_ADVANCE_SCHEDULE_AUTHORITY],
        ["Payments Issued Late:", str(benefits.late_payment_count)],
        ["Longest Delay (days):", str(benefits.max_days_late)],
        ["Days Without Benefits:", str(sum(gap.days for gap in benefits.gaps))],
        ["Rate Basis:", f"{rate.basis.label} — {UNCONFIRMED_NOTICE}"],
        ["Rate Basis Source:", rate.basis.source],
        ["Rate Basis Authority:", rate.basis.authority],
    ]
    penalties = money.penalties
    if penalties is not None and penalties.assessments:
        summary.append(["§4650(d) Automatic Increase", UNCONFIRMED_NOTICE])
        for assessment in penalties.assessments:
            source = "TD period" if assessment.source == "td_period" else "PD advance"
            summary.extend(
                [
                    [
                        f"§4650(d) {source} {assessment.ordinal} Principal:",
                        f"${assessment.principal:,.2f}",
                    ],
                    [
                        f"§4650(d) {source} {assessment.ordinal} Statutory Due:",
                        f"{assessment.statutory_due_date:%m/%d/%y}",
                    ],
                    [
                        f"§4650(d) {source} {assessment.ordinal} Operational Due:",
                        f"{assessment.operational_due_date:%m/%d/%y}",
                    ],
                    [
                        f"§4650(d) {source} {assessment.ordinal} Paid / Statutory Days Late:",
                        f"{assessment.date_paid:%m/%d/%y} / {assessment.days_late}",
                    ],
                    [
                        f"§4650(d) {source} {assessment.ordinal} Increase:",
                        f"${assessment.amount:,.2f}",
                    ],
                ]
            )
        summary.extend(
            [
                ["§4650(d) Principal Assessed:", f"${penalties.principal_assessed:,.2f}"],
                [
                    "§4650(d) Increase Fraction:",
                    f"{penalties.basis.increase_fraction.normalize():f}",
                ],
                ["§4650(d) Total Increase:", f"${penalties.total_increase:,.2f}"],
                [
                    "§4650(d) Penalty Basis:",
                    f"{penalties.basis.label} — {UNCONFIRMED_NOTICE}",
                ],
                ["§4650(d) Penalty Authority:", penalties.basis.authority],
            ]
        )
    # No settlement rows. A payment record is dated when the benefits it lists
    # were paid, which on a real file is years before the case settles — one
    # here carries an approval **819 days** in its own future. The release was
    # repaired for exactly this and this older path was missed, so the rule is
    # now stated once and applied everywhere: a document reports its own past.
    # The approval and funding dates live on the order and the ledger.
    story[summary_index] = _money_table(summary, [2.6 * inch, 3.4 * inch], styles)
    return story


def _append_settlement_terms(
    story: list[Any], money: MoneyFacts, styles: Any, scope: str
) -> list[Any]:
    """Print the settlement terms **the document at hand could know**.

    Forcing the gross was not enough. ``approvalDate``, ``fundingDate`` and
    ``fundingLagDays`` were published as ground truth and appeared on no page in
    the folder: the substrate's release leaves its approval line blank and has no
    funding date at all, and the payment record that prints them exists only when
    the case paid benefits. Measured — a settled case with no temporary or
    permanent disability published all three and ``validate --out`` passed it.

    The first fix put all three on the compromise and release, and that was
    wrong in a way worth recording. A C&R is the parties' agreement, signed and
    filed *before* the Board approves it — this engine dates one at 2023-11-13
    against an approval of 2023-12-27 — so printing the approval on it produced
    a document asserting an event 44 days in its own future. An anachronism is
    not weaker evidence than a missing line; it is worse, because it reads as
    evidence. The date spine's rule for payment records (ISC-175, no document is
    dated before what it prints) is a rule about documents, not about payment
    records.

    So each date is printed by the document that effects it, and ``scope`` names
    how far along the settlement that document sits:

    ``agreement``
        The release itself: type and gross, which are what the parties agreed.
    ``approval``
        The order approving the settlement, dated on the approval date it
        carries.
    ``funding``
        The payment ledger, dated after the money moved, and therefore the only
        document in the file that can report the interval between approval and
        funding — which is the whole substance of a late-funding argument and
        the stated reason those are two fields rather than one.
    """
    from reportlab.lib.units import inch
    from reportlab.platypus import Spacer

    settlement = money.settlement
    if settlement is None:
        return story

    rows: list[list[Any]] = [
        ["Settlement Terms", ""],
        ["Settlement Type:", settlement.kind],
        ["Settlement Gross:", f"${settlement.gross_amount:,.2f}"],
    ]
    if scope in ("approval", "funding"):
        rows.append(
            [
                "Date Approved:",
                settlement.approval_date.isoformat() if settlement.approval_date else "-",
            ]
        )
    if scope == "funding":
        rows.append(
            [
                "Date Funded:",
                settlement.funding_date.isoformat()
                if settlement.funding_date
                else "not yet funded",
            ]
        )
        rows.append(
            [
                "Days From Approval To Funding:",
                str(settlement.funding_lag_days)
                if settlement.funding_lag_days is not None
                else "-",
            ]
        )
    story.append(Spacer(1, 0.2 * inch))
    story.append(_money_table(rows, [2.6 * inch, 3.4 * inch], styles))
    return story


#: Every prose site that states the fee, one pattern per sentence the substrate
#: writes. There are two, and they are not the same shape: the stipulated award
#: bolds the figure (``which equals <b>$783</b>``) and the release does not
#: (``in the amount of $4,900 (15% of gross settlement)``). Matching on the bold
#: wrapper alone corrected the award and silently missed the release for two
#: rounds, because a truncated fee only differs from an exact one in the cents
#: the whole-dollar step was hiding. Each pattern is anchored to its own
#: sentence, so neither can land on the *next* money figure in the paragraph —
#: the release's own costs sit three words further along.
_FEE_IN_PROSE: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?<=which equals )<b>\$[\d,]+(?:\.\d+)?</b>"),
    re.compile(r"(?<=in the amount of )\$[\d,]+(?:\.\d+)?(?= \(15% of gross settlement\))"),
)

#: The net figure that follows the fee in the same sentence on the award.
_NET_IN_PROSE: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?<=payable to applicant is )<b>\$[\d,]+(?:\.\d+)?</b>"),
)

_MONEY_AFTER_AWW = re.compile(r"average weekly wage of \$[\d,]+(?:\.\d+)?")

#: Any money token at all — used only to decide whether an uncorrected
#: fifteen-percent paragraph was stating a figure or merely a percentage.
_ANY_MONEY = re.compile(r"\$[\d,]+(?:\.\d+)?")

#: The settlement memo's permanent-disability paragraph, which states a duration
#: in weeks, a weekly rate the substrate hardcodes to 290, and their product.
_MEMO_PD_WEEKS = re.compile(r"<b>PD Duration:</b> (\d+) weeks")
_MEMO_PD_RATE = re.compile(r"<b>Weekly Rate:</b> \$[\d,]+(?:\.\d+)?")
_MEMO_PD_TOTAL = re.compile(r"<b>Total PD Indemnity:</b> <b>\$[\d,]+(?:\.\d+)?</b>")

#: The supplemental job displacement voucher, as the substrate states it. A
#: statutory figure rather than a draw, and the engine publishes no voucher
#: fact, so it is carried through rather than governed. Named here so the memo
#: and any future carrier of it cannot drift apart.
_SJDB_VOUCHER = 6000


#: The substrate's working week, as ``data/fake_data_generator.py`` sets it.
#: An hourly rate is only comparable to a weekly wage through this number.
_SUBSTRATE_WEEKLY_HOURS = 40

#: An hourly figure inside a table cell.
_HOURLY_CELL = re.compile(r"^\$([\d,]+\.\d\d)/hr$")


def _rescale_hourly_column(table: Any, published: Decimal) -> None:
    """Scale a pay-rate column so its highest figure is the published rate.

    In place, on the ``Table`` flowable's own cell data. The relative shape of
    the history is the substrate's and worth keeping — a hire rate below a
    promotion rate is what a career looks like — but the top of it has to be the
    wage the manifest publishes, because that is the one an analyzer is scored
    on recovering.
    """
    rows = getattr(table, "_cellvalues", None)
    if not rows:
        log.warning("fact_templates.hourly_column_unreadable")
        return
    figures: list[tuple[int, int, Decimal]] = []
    for row_index, row in enumerate(rows):
        for cell_index, cell in enumerate(row):
            if not isinstance(cell, str):
                continue
            found = _HOURLY_CELL.match(cell)
            if found is not None:
                figures.append(
                    (row_index, cell_index, Decimal(found.group(1).replace(",", "")))
                )
    if not figures:
        log.warning("fact_templates.hourly_column_empty")
        return
    top = max(value for _, _, value in figures)
    if top <= 0:  # pragma: no cover - a substrate rate is always positive
        return
    for row_index, cell_index, value in figures:
        scaled = (value / top * published).quantize(CENTS)
        rows[row_index][cell_index] = f"${scaled:,.2f}/hr"


def _restate_distribution(
    story: list[Any],
    gross: int,
    costs: int,
    set_aside: int,
    wants_msa: bool,
    styles: Any,
) -> None:
    """Rebuild the release's distribution table with an exact fee.

    Every figure in it is one this module pins or computes, so it is rebuilt
    rather than edited: the gross is forced, the two deductions are forced, and
    the fee and net follow from them to the cent. The set-aside row appears only
    when the file has an allocation — ``lifecycle.resolution.msa`` governs that,
    and a release printing one for a seed that said ``msa: false`` was
    contradicting a fact the schema already owns.
    """
    from reportlab.lib.units import inch

    fee, _ = _fee_and_net(gross)
    net = Decimal(gross) - fee - Decimal(costs) - Decimal(set_aside)
    rows: list[list[Any]] = [
        ["Gross Settlement Amount", f"${gross:,.2f}"],
        ["Less: Attorney Fees (15%)", f"(${fee:,.2f})"],
        ["Less: Costs and Expenses", f"(${costs:,.2f})"],
    ]
    if wants_msa:
        rows.append(["Less: Medicare Set-Aside Allocation", f"(${set_aside:,.2f})"])
    rows.append(["Net to Applicant", f"${net:,.2f}"])
    if not _replace_table_after(
        story, "Distribution of Settlement", rows, [4 * inch, 2.5 * inch], styles
    ):
        log.warning("fact_templates.distribution_table_not_restated")
    _restate_fee_prose(story, fee)


def _restate_award_summary(
    story: list[Any],
    gross: int,
    award: Any,
    reimbursement: Any,
    styles: Any,
) -> None:
    """Rebuild the stipulated award's summary with an exact fee."""
    from reportlab.lib.units import inch

    fee, net_award = _fee_and_net(award._answer)
    rows: list[list[Any]] = [
        ["Permanent Disability (Gross)", f"${award._answer:,.2f}"],
        ["Less: Attorney Fees (15%)", f"(${fee:,.2f})"],
        ["Net Permanent Disability to Applicant", f"${net_award:,.2f}"],
        ["Self-Procured Medical Reimbursement", f"${reimbursement._answer:,.2f}"],
        ["Settlement Gross", f"${gross:,.2f}"],
    ]
    if not _replace_table_after(
        story, "SUMMARY OF AWARD", rows, [4 * inch, 2.5 * inch], styles
    ):
        log.warning("fact_templates.award_summary_not_restated")
    _restate_fee_prose(story, fee, net_award)


def _restate_fee_prose(story: list[Any], fee: Decimal, net: Decimal | None = None) -> None:
    """Correct the fee figure where a paragraph states it in words.

    Both documents say the fee "equals" or "is" fifteen percent and then print a
    truncated number. The table is rebuilt above; the prose is substituted here,
    so the page does not disagree with itself.

    A paragraph that states the fee and is left uncorrected is reported. That
    is the whole point of the miss check: the release's sentence went two rounds
    uncorrected precisely because nothing said so out loud.
    """
    from reportlab.platypus import Paragraph

    for index, item in enumerate(story):
        text = getattr(item, "text", None)
        if not isinstance(text, str) or "15%" not in text:
            continue
        replaced = text
        for pattern in _FEE_IN_PROSE:
            replaced = pattern.sub(_bold_like(pattern, f"${fee:,.2f}"), replaced, count=1)
        if net is not None:
            for pattern in _NET_IN_PROSE:
                replaced = pattern.sub(
                    _bold_like(pattern, f"${net:,.2f}"), replaced, count=1
                )
        if replaced != text:
            story[index] = Paragraph(replaced, item.style)
        elif _ANY_MONEY.search(text):
            log.warning("fact_templates.fee_prose_not_restated", sentence=text[:120])


def _bold_like(pattern: re.Pattern[str], money: str) -> str:
    """Wrap *money* the way the sentence this pattern matches wraps its own.

    The award bolds the figure and the release does not; a substitution that
    imposed one house style on both would edit emphasis the substrate chose.
    """
    return f"<b>{money}</b>" if "<b>" in pattern.pattern else money


def _replace_table_after(
    story: list[Any], marker: str, rows: list[list[Any]], widths: list[float], styles: Any
) -> bool:
    """Swap the first table following *marker* for one built from the ledger.

    The substrate's distribution and award summaries are ``Table`` flowables, so
    they cannot be rewritten the way a paragraph can. Every figure in them is
    one this module already pins or computes, so the table is rebuilt rather
    than edited. Returns whether it found one, so the caller reports a miss
    instead of leaving a stale table on the page.
    """
    start = _index_of_text(story, marker)
    if start is None:
        return False
    for index in range(start, len(story)):
        item = story[index]
        if item.__class__.__name__ == "Table":
            story[index] = _money_table(rows, widths, styles)
            return True
    return False


def _index_of_text(story: list[Any], marker: str) -> int | None:
    """Where a flowable carrying ``marker`` sits, or ``None`` if none does.

    Used to cut a substrate story at a known seam. ``None`` is returned rather
    than guessed at, so a caller reports a miss instead of writing its body over
    whatever happened to be at a hardcoded index.
    """
    for index, item in enumerate(story):
        text = getattr(item, "text", None)
        if isinstance(text, str) and marker in text:
            return index
    return None




def _fee_and_net(base: Decimal | int) -> tuple[Decimal, Decimal]:
    """The attorney fee a document calls fifteen percent, and what is left.

    To the cent, because fifteen percent of a real settlement usually has
    cents in it. The substrate truncates the product to whole dollars, so a
    $32,668 gross printed a fee of $4,900 beside the words "15%" for a true
    $4,900.20 — a figure the page contradicts, and it was live on shipped
    cases.

    A twenty-dollar lattice on ``gross_amount`` was tried first and withdrawn on
    review: narrowing a *published* field to work around a renderer's rounding
    makes the corpus systematically unrealistic in a figure the analyzer is
    scored on. Real settlements are not multiples of twenty. The document states
    cents instead, which is what a real one does.
    """
    amount = Decimal(base)
    fee = (amount * SETTLEMENT_FEE_RATE).quantize(CENTS)
    return fee, amount - fee


def _reimbursement_nearest_five_percent(total: int) -> int:
    """The self-procured reimbursement, as near five percent of the total as a dollar allows.

    The two cash components must sum to *total* and each must be at least a
    whole dollar, which is the whole constraint now that the fee is printed to
    cents. An earlier version floored the target before comparing candidates and
    returned $1 for a total of $221 when $21 was nearer to $11.05.
    """
    nearest = int(Decimal(total * 5) / Decimal(100) + Decimal("0.5"))
    return max(1, min(nearest, total - 1))


def _rewrite_stipulations(story: list[Any], money: MoneyFacts, styles: Any) -> list[Any]:
    """Rewrite the stipulations that state money, from the ledger.

    ``STIPULATIONS_WITH_REQUEST_FOR_AWARD`` is the primary settlement document
    of every ``stipulations`` case, and it was computing its own money: an
    average weekly wage from ``hourly_rate * weekly_hours``, a temporary
    disability run from ``random.randint(4, 52)``, a rate from a hardcoded 0.67,
    and a permanent disability award from ``random.randint(5000, 75000)``.

    Measured on the shipped ``steady-earner`` case: ``caseFacts`` published an
    average weekly wage of 1151.42, a temporary disability rate of 767.65 and a
    total of 26867.75, while the document beside it read 1331.20, 891.90 and
    40135.68. Two money ontologies in one case, on the page an analyzer would be
    trained against — the precise failure this layer exists to remove, sitting
    on the document that matters most to the branch it appears in.

    Rewritten by index like the payment record's own summary, so everything else
    the substrate wrote — the caption, the eight non-monetary stipulations, the
    award and signature blocks — is left exactly as it was. A miss is reported
    rather than swallowed, because a silent miss is a page contradicting the
    manifest.
    """
    from reportlab.platypus import Paragraph

    computation = money.wages.computation
    rate = money.wages.rate
    benefits = money.benefits
    rewrote = 0
    for index, item in enumerate(story):
        text = getattr(item, "text", None)
        if not isinstance(text, str):
            continue
        if "average weekly wage of $" in text:
            # Substituted by pattern, not by partitioning on the next ".". The
            # first cut split on the *decimal point* of the substrate's own
            # figure, so `$1331.20.` became `$1,001.23.20.` — a mangled number
            # that the probe's substring search could not see, because
            # "1001.23" is a substring of "1001.23.20". Found by review, and it
            # is the reason the probe now parses the amount instead.
            replaced, count = _MONEY_AFTER_AWW.subn(
                lambda _: f"average weekly wage of ${computation.aww:,.2f}", text
            )
            if count != 1:
                log.warning("fact_templates.stipulated_aww_not_substituted", count=count)
                continue
            story[index] = Paragraph(replaced, styles["DoubleSpaced"])
            rewrote += 1
        elif "temporary disability indemnity has been paid for" in text:
            weeks = sum((period.weeks for period in benefits.td_periods), Decimal(0))
            story[index] = Paragraph(
                f"<b>9.</b> That temporary disability indemnity has been paid for "
                f"{weeks.normalize():f} weeks at the rate of "
                f"${rate.td_weekly_rate:,.2f} per week, totaling "
                f"${benefits.td_total:,.2f}, and no further temporary disability is owed.",
                styles["DoubleSpaced"],
            )
            rewrote += 1
    if rewrote != 2:
        log.warning("fact_templates.stipulations_money_not_rewritten", rewrote=rewrote)
    return story


def build_fact_aware_templates() -> dict[str, type]:
    """Construct the subclasses. Deferred so importing this module is substrate-free.

    The base classes live in the substrate, which is located at runtime through
    the bridge, so the classes cannot be defined at module scope without making
    every importer pay for the substrate.
    """
    diagnostic_module = import_substrate("pdf_templates.medical.diagnostic_report")
    qme_module = import_substrate("pdf_templates.medical.qme_ame_report")
    tpr_module = import_substrate("pdf_templates.medical.treating_physician_report")
    apportionment_module = import_substrate("data.apportionment")

    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

    class FactAwareDiagnosticReport(_SpecCapture, diagnostic_module.DiagnosticReport):  # type: ignore[misc,name-defined]
        """Reports the study the ledger says was performed.

        The substrate drew ``MRI``/``CT``/``X-Ray`` per document, independently
        of every other document in the case, so a file could hold an imaging
        report for a study its QME never mentions and vice versa.
        """

        def build_story(self, doc_spec: Any) -> list[Any]:
            facts = _facts_of(self)
            fact = facts.diagnostic_for(_index_of(self)) if facts else None

            if fact is None and facts is not None:
                # ISC-128. The ledger has no *performed imaging* study to report
                # — the case may have had only an EMG, or nothing. Phase 1
                # handed the document straight back to the substrate here, which
                # then drew freely from MRI/CT/X-Ray and could name a modality
                # the ledger explicitly marks absent. Rare, because a case with
                # no imaging rarely carries an imaging report, but reachable
                # through an explicit document override — and "rare" is not the
                # standard this ledger holds itself to.
                #
                # Force to an imaging modality the ledger does not deny. If it
                # denies all three the document is unsatisfiable, so say so
                # rather than picking the least-wrong lie.
                absent = facts.absent_modalities()
                available = [m for m in IMAGING_MODALITIES if m not in absent]
                if not available:
                    log.warning(
                        "fact_templates.imaging_report_unsatisfiable",
                        absent=sorted(absent),
                    )
                else:
                    forced = _ForcedChoice(
                        MODALITY_DISPLAY[available[0]],
                        lambda seq: tuple(seq) == _SUBSTRATE_MODALITY_CHOICES,
                    )
                    original = diagnostic_module.random
                    diagnostic_module.random = forced
                    try:
                        return list(super().build_story(doc_spec))
                    finally:
                        diagnostic_module.random = original

            if fact is None:
                return list(super().build_story(doc_spec))

            forced = _ForcedChoice(
                fact.display, lambda seq: tuple(seq) == _SUBSTRATE_MODALITY_CHOICES
            )
            original = diagnostic_module.random
            diagnostic_module.random = forced
            try:
                story = list(super().build_story(doc_spec))
            finally:
                diagnostic_module.random = original

            if not forced.fired:
                # The substrate's candidate list moved. Loud, because a silent
                # miss here is a document contradicting the ledger.
                log.warning(
                    "fact_templates.modality_not_forced",
                    expected=list(_SUBSTRATE_MODALITY_CHOICES),
                    modality=fact.modality,
                )

            # ISC-110. The substrate prints every injured region in its
            # EXAMINATION line, so the document never says which region *this*
            # study covered — the ledger knows, and until now nothing rendered
            # it. Engine-added content rather than an intercepted draw, because
            # there is no draw here to intercept.
            region = fact.body_part.replace("_", " ").title()
            story.insert(
                _after_examination_line(story),
                Paragraph(
                    f"<b>EXAMINED REGION:</b> {region} — {fact.display}",
                    self.styles["BodyText14"],
                ),
            )
            return story

    class FactAwareQmeAmeReport(_SpecCapture, qme_module.QmeAmeReport):  # type: ignore[misc,name-defined]
        """Cites only studies the ledger says happened, and says what did not.

        The substrate drew an imaging type *per body part* and asserted a
        finding for every one, so every QME claimed imaging of everything —
        including regions no diagnostic report in the case covered.
        """

        def _build_diagnostic_review(self, injury: Any) -> list[Any]:
            facts = _facts_of(self)
            if facts is None or not facts.diagnostics:
                return list(super()._build_diagnostic_review(injury))

            elements: list[Any] = []
            findings: list[str] = []
            # No RNG here at all. This method builds its text from the ledger,
            # in ledger order, so it touches no stream — which is what lets it
            # replace the substrate's version without moving any later draw.
            observations = [
                "disc herniation with moderate foraminal narrowing",
                "degenerative change without significant neural compression",
                "partial-thickness tearing with associated bursitis",
                "chronic tendinopathy",
                "no acute osseous abnormality",
            ]
            for position, fact in enumerate(facts.performed_diagnostics):
                observation = observations[position % len(observations)]
                dated = f" ({fact.date.strftime('%B %d, %Y')})" if fact.date else ""
                findings.append(
                    f"<b>{fact.body_part.replace('_', ' ').title()}:</b> "
                    f"{fact.display}{dated} demonstrates {observation}."
                )

            for fact in facts.absent_diagnostics:
                findings.append(
                    f"<b>{fact.body_part.replace('_', ' ').title()}:</b> no "
                    f"{fact.display} study was obtained; this opinion is based on "
                    "the clinical examination and the records reviewed."
                )

            if not findings:
                return list(super()._build_diagnostic_review(injury))

            elements.extend(self.make_section("DIAGNOSTIC REVIEW", "\n".join(findings)))

            if facts.surgery.performed:
                elements.extend(
                    self.make_section(
                        "SURGICAL HISTORY",
                        f"The applicant underwent {_procedure_phrase(facts.surgery)} "
                        f"of the "
                        f"{(facts.surgery.body_part or '').replace('_', ' ')}"
                        + (
                            f" on {facts.surgery.date.strftime('%B %d, %Y')}."
                            if facts.surgery.date
                            else "."
                        )
                        + " Post-operative course and residual impairment are "
                        "discussed below.",
                    )
                )
            return elements

    class _MedicalStoryTprSections:
        """R9's treating-physician section owners for the medical-story path.

        The PTP register is a first-person clinical treatment voice with an
        independent AOE/COE conclusion (R14/R16): the causation section rests
        on the treatment course, examinations, mechanism and clinical course,
        and never answers an attorney's theory as its causal source. Every
        override delegates through ``super()`` on the story-absent path.
        """

        def _build_assessment(self, injury: Any) -> list[Any]:
            elements = list(super()._build_assessment(injury))
            story = _story_of(self)
            opinion = story.medical_opinion if story is not None else None
            if opinion is None:
                return elements
            # R9: INDUSTRIAL CAUSATION follows the assessment; PSYCHIATRIC
            # CAUSATION replaces the generic heading for a psych finding.
            psych = opinion.psych_injury_kind is not None
            heading = "PSYCHIATRIC CAUSATION" if psych else "INDUSTRIAL CAUSATION"
            final = _subtype_of(self) in PTP_APPORTIONMENT_SURFACES
            elements.extend(
                self.make_section(heading, _story_tpr_causation_text(opinion, final))
            )
            return elements

        def impairment_rating_section(self, apportionment: Any = None) -> list[Any]:
            story = _story_of(self)
            if (
                story is None
                or story.medical_opinion is None
                or _subtype_of(self) not in PTP_APPORTIONMENT_SURFACES
            ):
                return list(super().impairment_rating_section(apportionment))
            # R12: the PR-4/final subclass parses and passes the same AJC-65
            # decision into the impairment section, then states the
            # apportionment immediately after the impairment block (R9).
            context = getattr(getattr(self, "doc_spec", None), "context", None)
            decision = (
                apportionment
                if apportionment is not None
                else apportionment_module.parse_apportionment(context)
            )
            elements = list(super().impairment_rating_section(decision))
            if decision is not None:
                elements.extend(
                    self.make_section(
                        "APPORTIONMENT OF PERMANENT DISABILITY",
                        decision.conclusion_sentence(),
                    )
                )
                heterogeneous = _story_heterogeneous_rows(story)
                if heterogeneous:
                    elements.append(
                        _story_apportionment_table(heterogeneous, self.styles)
                    )
                    elements.append(Spacer(1, 0.15 * inch))
            return elements

    class FactAwareTreatingPhysicianReport(
        _MedicalStoryTprSections, _SpecCapture, tpr_module.TreatingPhysicianReport  # type: ignore[misc,name-defined]
    ):
        """Describes post-operative care when the ledger says surgery happened.

        ``treatment_type`` drew from ``conservative`` / ``physical_therapy`` /
        ``medication_management`` — "surgical" was not even in the list — so a
        progress report written after an operation recommended conservative
        management of the condition that had just been operated on.
        """

        def _build_chief_complaints(self, injury: Any) -> list[Any]:
            """Walks the ledger's trajectory instead of re-rolling per document.

            The substrate drew one of four status phrases inline per report, so
            a case with three PRs could read "worsening despite treatment", then
            "slowly improving", then "worsening despite treatment" again. Each
            document was individually plausible and the sequence was not.

            The draw is intercepted rather than the method rewritten: the phrase
            sits inside a four-line f-string that also builds the per-body-part
            complaint list and the functional-status sentence, none of which
            this governs.
            """
            facts = _facts_of(self)
            if facts is None:
                return list(super()._build_chief_complaints(injury))

            phrase = facts.phrase_for(_report_ordinal(self))
            forced = _ForcedChoice(
                phrase, lambda seq: tuple(seq) == tuple(SUBSTRATE_STATUS_PHRASES)
            )
            original = tpr_module.random
            tpr_module.random = forced
            try:
                story = list(super()._build_chief_complaints(injury))
            finally:
                tpr_module.random = original

            if not forced.fired:
                log.warning(
                    "fact_templates.status_phrase_not_forced",
                    expected=list(SUBSTRATE_STATUS_PHRASES),
                    trajectory=facts.trajectory,
                )
            return story

        def _build_treatment_plan(self, specialty: Any, variant: Any) -> list[Any]:
            facts = _facts_of(self)
            if facts is not None and facts.surgery.proposed:
                return list(self._proposed_surgery_plan(facts))
            if facts is None or not facts.surgery.performed:
                # Not our business: identical to the substrate, byte for byte.
                return list(super()._build_treatment_plan(specialty, variant))

            surgery = facts.surgery
            region = (surgery.body_part or "the affected region").replace("_", " ")
            dated = f" on {surgery.date.strftime('%B %d, %Y')}" if surgery.date else ""
            content = (
                f"The applicant is status post {_procedure_phrase(surgery)} "
                f"of the {region}{dated}. Care is directed "
                "at post-operative rehabilitation rather than further conservative "
                "management.\n\n"
                "<b>Treatment Plan:</b>\n"
                "• Supervised post-operative physical therapy, two visits per week\n"
                "• Activity modification with progressive loading as tolerated\n"
                "• Wound and neurovascular surveillance at each visit\n\n"
                "<b>Goals:</b> Protect the surgical repair, restore range of motion, "
                "and progress toward maximum medical improvement.\n\n"
                "Patient is scheduled for follow-up in 4 weeks."
            )
            elements: list[Any] = []
            elements.extend(self.make_section("TREATMENT PLAN", content))
            return elements

        def _proposed_surgery_plan(self, facts: Any) -> list[Any]:
            """A procedure that was asked for, not one that happened.

            ``recommended`` and ``denied_by_ur`` differ in one sentence and that
            sentence is the whole point of the distinction: one file is waiting
            on an authorization, the other has been refused one and is deciding
            whether to appeal.
            """
            surgery = facts.surgery
            region = (surgery.body_part or "the affected region").replace("_", " ")
            if surgery.status == "denied_by_ur":
                outcome = (
                    f"A Request for Authorization for {_procedure_phrase(surgery)} "
                    f"of the {region} was submitted and "
                    "denied on utilization review as not medically necessary. The "
                    "applicant remains symptomatic and the denial is under appeal."
                )
            else:
                outcome = (
                    f"Surgical consultation has been obtained and "
                    f"{_procedure_phrase(surgery)} of the "
                    f"{region} is recommended. A Request for Authorization has been "
                    "submitted and no determination has issued."
                )
            content = (
                f"{outcome}\n\n"
                "<b>Interim Treatment Plan:</b>\n"
                "• Continued conservative care pending authorization\n"
                "• Activity modification within current work restrictions\n"
                "• Reassessment on receipt of the determination\n\n"
                "Patient is scheduled for follow-up in 4 weeks."
            )
            return list(self.make_section("TREATMENT PLAN", content))

    class FactAwareMedicalStoryTreatingReport(
        _MedicalStoryTprSections, _SpecCapture, tpr_module.TreatingPhysicianReport  # type: ignore[misc,name-defined]
    ):
        """The R9 story sections over the RAW substrate treating report.

        Mount for ``TREATING_PHYSICIAN_REPORT`` and
        ``TREATING_PHYSICIAN_REPORT_FINAL``, which had no fact-aware
        registration before M3: their exact pre-M3 path is the unmodified
        substrate, so the story-absent delegation must land there — mounting
        them on :class:`FactAwareTreatingPhysicianReport` would force the
        ledger's trajectory phrase and surgical plan into documents whose
        feature-absent bytes R1 freezes.
        """

    operative_module = import_substrate("pdf_templates.medical.operative_record")

    class FactAwareOperativeRecord(_SpecCapture, operative_module.OperativeRecord):  # type: ignore[misc,name-defined]
        """Performs the operation the ledger says was performed.

        The substrate already narrows CPTs to the case's body parts and then
        draws one; this pins that draw to ``facts.surgery.cpt_code`` so the
        operative record, the QME's surgical history and the treating
        physician's plan all name one procedure (ISC-93). The ledger draws from
        the same pool, so pinning never contradicts the template's body-part
        logic.
        """

        def build_story(self, doc_spec: Any) -> list[Any]:
            facts = _facts_of(self)
            surgery = facts.surgery if facts else None
            if surgery is None or not surgery.performed or not surgery.cpt_code:
                return list(super().build_story(doc_spec))

            answer = (surgery.cpt_code, surgery.cpt_description)
            codes = {surgery.cpt_code}
            forced = _ForcedChoice(
                answer,
                lambda seq: bool(seq)
                and isinstance(seq[0], tuple)
                and len(seq[0]) == 2
                and str(seq[0][0]).isdigit(),
            )
            original = operative_module.random
            operative_module.random = forced
            try:
                story = list(super().build_story(doc_spec))
            finally:
                operative_module.random = original
            if not forced.fired:
                log.warning("fact_templates.cpt_not_forced", expected=sorted(codes))
            return story

    def _story_apportionment_table(rows: Any, styles: Any) -> Any:
        """R12 — the body-part table for heterogeneous plural apportionment.

        Rendered by the wcce subclass exactly where AJC-65 suppressed its
        scalar block: the rows carry different nonindustrial percentages, so
        the table states each split the evaluator actually made and no scalar
        is invented anywhere.
        """
        data: list[list[Any]] = [
            ["Body Part", "Industrial %", "Nonindustrial %", "Basis"]
        ]
        for row in rows:
            basis = row.description or ", ".join(
                kind.replace("_", " ") for kind in row.basis_kinds
            ) or "nonindustrial factors"
            data.append(
                [
                    _region_text(row.body_part).title(),
                    f"{row.industrial_percent}%",
                    f"{row.nonindustrial_percent}%",
                    basis,
                ]
            )
        return _money_table(
            data, [1.3 * inch, 1.0 * inch, 1.1 * inch, 2.6 * inch], styles
        )

    def _story_heterogeneous_rows(story: DocumentMedicalStory) -> tuple[Any, ...]:
        rows = story.apportionments
        if len(rows) > 1 and len({row.nonindustrial_percent for row in rows}) > 1:
            return rows
        return ()

    def _story_causation_paragraph(context: Any) -> str:
        """The med-legal causation discussion, from the parsed AJC-65 block."""
        causation = apportionment_module.parse_causation(context)
        if causation is not None and causation.discussion:
            return causation.discussion
        attribution = (
            causation.attribution if causation is not None else None
        ) or "predominantly"
        return (
            f"The current condition is {attribution} attributable to the "
            "industrial injury. This opinion rests on the history obtained, "
            "the records reviewed, and the examination findings documented in "
            "this report, and is stated to a reasonable degree of medical "
            "probability."
        )

    _revision_kind_sentences: dict[str, str] = {
        "unchanged_additional_reasoning": (
            "The opinions stated in the prior report are unchanged; "
            "additional reasoning is provided below."
        ),
        "new_records_no_change": (
            "The newly received records were reviewed and acknowledged; the "
            "opinions stated in the prior report are unchanged."
        ),
        "revised_causation": (
            "Upon the further review stated in this report, the causation "
            "opinion is revised."
        ),
        "revised_apportionment": (
            "Upon the further review stated in this report, the "
            "apportionment opinion is revised."
        ),
        "revised_causation_and_apportionment": (
            "Upon the further review stated in this report, the causation "
            "and apportionment opinions are both revised."
        ),
    }

    class _MedicalStoryQmeSections:
        """R9's QME/AME section owners for the medical-story path (AJC-62).

        Mixed in FRONT of a governed QME/AME base class so the story-present
        path owns the frozen R9 splice points while every story-absent call
        delegates through ``super()`` to the exact pre-M3 MRO — the existing
        fact-aware clinical overrides for the subtypes that had them, the raw
        substrate for the subtypes that did not. One mixin, two mounts, zero
        competing wrappers (R11).
        """

        def _story_supplemental(self) -> bool:
            return _subtype_of(self) in SUPPLEMENTAL_MEDLEGAL_SURFACES

        def _story_psych(self) -> bool:
            return _subtype_of(self) == "PSYCH_EVAL_REPORT_QME_AME"

        def _build_history(self, injury: Any, doc_spec: Any) -> list[Any]:
            story = _medical_story_of(doc_spec)
            if story is None:
                return list(super()._build_history(injury, doc_spec))
            if self._story_psych() and not self._story_supplemental():
                elements = list(
                    self.make_section(
                        "HISTORY OF PRESENT INJURY",
                        _story_psych_complaint_text(self, story),
                    )
                )
                elements.append(Spacer(1, 0.15 * inch))
                return elements
            if not self._story_supplemental():
                return list(super()._build_history(injury, doc_spec))
            # R9 supplemental row: the "specific questions / new information"
            # voice. No fresh HPI — the prior report owns the history, and
            # only changed or new information appears here.
            prior = story.preceding_report
            cited = (
                f"my {prior.title} of {prior.doc_date.strftime('%B %d, %Y')}"
                if prior is not None
                else "the prior medical-legal evaluation in this matter"
            )
            lead = (
                f"This supplemental report responds to {cited}. It is limited "
                "to the specific questions presented and the new information "
                "received since that report; the history of the present "
                "injury is not restated."
            )
            if story.contentions:
                numbered = "\n".join(
                    _story_contention_sentence(position + 1, contention)
                    for position, contention in enumerate(story.contentions)
                )
                content = f"{lead}\n\nThe questions presented are:\n\n{numbered}"
            else:
                content = lead
            elements = list(
                self.make_section("QUESTIONS PRESENTED AND NEW INFORMATION", content)
            )
            elements.append(Spacer(1, 0.15 * inch))
            return elements

        def _build_records_review(self, doc_spec: Any) -> list[Any]:
            story = _medical_story_of(doc_spec)
            if story is None:
                return list(super()._build_records_review(doc_spec))
            elements: list[Any] = []
            if self._story_supplemental():
                # R9/R10: delta records only — the projector already limited
                # the references to documents later than the prior report.
                elements.extend(
                    self.make_section(
                        "RECORDS REVIEWED SINCE PRIOR REPORT",
                        _story_records_text(story, examined=False),
                    )
                )
            elif self._story_psych():
                elements.extend(
                    self.make_section(
                        "REVIEW OF RECORDS", _story_psych_records_text(story)
                    )
                )
                elements.extend(
                    self.make_section(
                        "PAST MEDICAL AND SURGICAL HISTORY", _story_pmh_text(story)
                    )
                )
                elements.extend(
                    self.make_section(
                        "PAST PSYCHIATRIC HISTORY",
                        _story_psych_history_text(story),
                    )
                )
            else:
                # R9 initial row: PMH prepended here, and the generic record
                # pool replaced with the actual prior-file references.
                elements.extend(
                    self.make_section("PAST MEDICAL HISTORY", _story_pmh_text(story))
                )
                elements.extend(
                    self.make_section(
                        "REVIEW OF MEDICAL RECORDS", _story_records_text(story)
                    )
                )
            elements.append(Spacer(1, 0.15 * inch))
            return elements

        def _build_chief_complaints(self, injury: Any) -> list[Any]:
            story = _story_of(self)
            if story is None or not self._story_supplemental():
                return list(super()._build_chief_complaints(injury))
            # R9 supplemental row: no fresh complaints are elicited.
            return []

        def _build_physical_exam(
            self, specialty: Any, body_parts: Any, doc_spec: Any
        ) -> list[Any]:
            story = _medical_story_of(doc_spec)
            if story is None:
                return list(
                    super()._build_physical_exam(specialty, body_parts, doc_spec)
                )
            if self._story_psych() and not self._story_supplemental():
                content = (
                    "A mental-status examination was performed and considered with "
                    "the clinical interview and the records reviewed. "
                    + _story_psych_testing_text()
                )
                elements = list(
                    self.make_section("PHYSICAL EXAMINATION FINDINGS", content)
                )
                elements.append(Spacer(1, 0.15 * inch))
                return elements
            if not self._story_supplemental():
                return list(
                    super()._build_physical_exam(specialty, body_parts, doc_spec)
                )
            elements = list(
                self.make_section(
                    "SCOPE OF SUPPLEMENTAL REVIEW",
                    "No new examination was performed for this supplemental "
                    "report. The findings of the prior examination stand "
                    "except as expressly revisited below; the opinions stated "
                    "here rest on the record review and the reasoning set "
                    "forth in this report.",
                )
            )
            elements.append(Spacer(1, 0.15 * inch))
            return elements

        def _build_diagnostic_review(self, injury: Any) -> list[Any]:
            elements = list(super()._build_diagnostic_review(injury))
            story = _story_of(self)
            if story is None or not self._story_psych():
                return elements
            opinion = story.medical_opinion
            if opinion is None:
                return elements
            # R9 psych row / R81 order: the causation and statutory blocks
            # follow the diagnostic impression and precede impairment and
            # apportionment. Register CONTENT is Part 5's; the frozen heading
            # structure and current-generic prose are this step's.
            elements.extend(
                self.make_section(
                    "DIAGNOSTIC IMPRESSION",
                    "The diagnostic impression is stated under the most "
                    "recent applicable diagnostic criteria and rests on the "
                    "clinical interview, the mental status findings above, "
                    "and the records reviewed.",
                )
            )
            elements.extend(
                self.make_section(
                    "PSYCHIATRIC INJURY CAUSATION",
                    _story_psych_causation_text(story),
                )
            )
            elements.extend(
                self.make_section(
                    "LABOR CODE §3208.3 ANALYSIS",
                    _story_psych_3208_text(self, story),
                )
            )
            elements.extend(
                self.make_section(
                    "LABOR CODE §4660.1(c) ANALYSIS",
                    _story_psych_4660_text(
                        self, story, self.case.timeline.date_of_injury
                    ),
                )
            )
            return elements

        def impairment_rating_section(self, apportionment: Any = None) -> list[Any]:
            """Retain the substrate's single psych pair for R86 report prose."""
            story = _story_of(self)
            if story is None or not self._story_psych():
                return list(super().impairment_rating_section(apportionment))

            ama_module = import_substrate("data.ama_guides_content")
            body_parts = (
                self.case.injuries[0].body_parts if self.case.injuries else []
            )
            specialty = (
                getattr(self.case, "qme_physician", None)
                and self.case.qme_physician.specialty
            ) or self.case.treating_physician.specialty
            drawn_pct = random.choice([0, 0, 0, 10, 15, 20, 25])
            if apportionment is None:
                narrative, _total_wpi, ratings = (
                    ama_module.generate_impairment_narrative(
                        body_parts, specialty, drawn_pct
                    )
                )
            else:
                narrative, _total_wpi, ratings = (
                    ama_module.generate_impairment_narrative(
                        body_parts,
                        specialty,
                        drawn_pct,
                        governed_block=apportionment.impairment_block(body_parts),
                    )
                )
            elements: list[Any] = [
                Paragraph(
                    "<b>IMPAIRMENT RATING — AMA GUIDES 5TH EDITION</b>",
                    self.styles["SectionHeader"],
                ),
                Spacer(1, 0.1 * inch),
            ]
            for paragraph in narrative.split("\n"):
                if paragraph.strip():
                    elements.append(
                        Paragraph(paragraph, self.styles["BodyText14"])
                    )

            date_of_injury = self.case.timeline.date_of_injury
            if date_of_injury.year < 2005:
                pdrs = _register_clauses(
                    PSYCH_GAF_PDRS_REGISTER, "pre_2005"
                )[0]
                elements.append(Paragraph(pdrs, self.styles["BodyText14"]))
            else:
                pair = next(
                    (
                        (rating.get("gaf"), rating.get("wpi"))
                        for rating in ratings
                        if rating.get("gaf") is not None
                        and rating.get("wpi") is not None
                    ),
                    None,
                )
                if pair is not None:
                    method, result = _register_clauses(
                        PSYCH_GAF_PDRS_REGISTER, "post_2004"
                    )
                    result = result.replace("[GAF]", str(pair[0])).replace(
                        "[WPI]", str(pair[1])
                    )
                    elements.append(Paragraph(method, self.styles["BodyText14"]))
                    elements.append(Paragraph(result, self.styles["BodyText14"]))
                    elements.append(
                        Paragraph(
                            "DSM-IV-TR/GAF terminology is retained only for the 2005 "
                            "PDRS impairment instruction, not as the current diagnostic "
                            "standard.",
                            self.styles["BodyText14"],
                        )
                    )
            elements.append(Spacer(1, 0.15 * inch))
            return elements

        def _build_future_medical(self, body_parts: Any) -> list[Any]:
            story = _story_of(self)
            if story is None or story.medical_opinion is None:
                return list(super()._build_future_medical(body_parts))
            context = getattr(getattr(self, "doc_spec", None), "context", None)
            decision = apportionment_module.parse_apportionment(context)
            elements: list[Any] = []
            if self._story_psych():
                # R81: PSYCHIATRIC APPORTIONMENT sits after the impairment
                # content; this splice point is immediately after it.
                content = (
                    decision.conclusion_sentence()
                    if decision is not None
                    else (
                        "Psychiatric apportionment is addressed under Labor "
                        "Code sections 4663 and 4664 on the record reviewed."
                    )
                )
                elements.extend(
                    self.make_section("PSYCHIATRIC APPORTIONMENT", content)
                )
            elif self._story_supplemental():
                # R9 supplemental row: only issues actually revisited.
                opinion = story.medical_opinion
                sentences: list[str] = []
                if opinion.revision_kind is not None:
                    sentences.append(_revision_kind_sentences[opinion.revision_kind])
                if opinion.revision_rationale:
                    sentences.append(opinion.revision_rationale)
                if decision is not None:
                    sentences.append(decision.conclusion_sentence())
                if sentences:
                    elements.extend(
                        self.make_section(
                            "SUPPLEMENTAL CAUSATION AND APPORTIONMENT OPINIONS",
                            " ".join(sentences),
                        )
                    )
            else:
                # R9 initial row: the discussion sits immediately after the
                # impairment section and before future medical treatment.
                sentences = [_story_causation_paragraph(context)]
                if decision is not None:
                    sentences.append(decision.conclusion_sentence())
                elements.extend(
                    self.make_section("CAUSATION AND APPORTIONMENT", " ".join(sentences))
                )
            heterogeneous = _story_heterogeneous_rows(story)
            if heterogeneous:
                elements.append(
                    _story_apportionment_table(heterogeneous, self.styles)
                )
                elements.append(Spacer(1, 0.15 * inch))
            elements.extend(super()._build_future_medical(body_parts))
            return elements

    class FactAwareNeuroQmeReport(_MedicalStoryQmeSections, FactAwareQmeAmeReport):
        """As above, and it does not electrodiagnose a study that never happened.

        ``_build_neuro_exam`` appended an EMG/NCV paragraph unconditionally,
        which is how a ledger-absent EMG still reached the page. It is kept when
        the ledger says EMG was performed and dropped when the ledger calls it
        absent — dropped rather than negated because the diagnostic review
        already records the absence, and saying it twice in two registers reads
        like two different findings.
        """

        def _build_neuro_exam(self, body_parts: Any) -> list[Any]:
            elements = list(super()._build_neuro_exam(body_parts))
            facts = _facts_of(self)
            if facts is None or "emg" not in facts.absent_modalities():
                return elements
            return [
                element
                for element in elements
                if "Electrodiagnostic Studies" not in getattr(element, "text", "")
            ]

        def _build_history(self, *args: Any, **kwargs: Any) -> list[Any]:
            """The third modality draw, in the history narrative.

            ``_build_diagnostic_review`` was governed in Phase 1 and
            ``_build_neuro_exam`` above, but the history opened with its own
            independent sentence about what imaging was obtained — so a QME
            could still announce an MRI in paragraph two and review only X-rays
            four pages later. Same interception, same narrow target.

            The supplemental medical-story path (AJC-62) replaces the history
            with the delta form and never reaches the substrate's imaging
            sentence, so the interception is skipped there — wrapping a path
            that makes no draw would fire the not-forced warning on every
            governed supplemental and drown the real diagnostic.
            """
            facts = _facts_of(self)
            if facts is None or (
                _story_of(self) is not None and self._story_supplemental()
            ):
                return list(super()._build_history(*args, **kwargs))

            forced = _ForcedChoice(
                _history_imaging_sentence(facts),
                lambda seq: tuple(seq) == _SUBSTRATE_HISTORY_IMAGING,
            )
            original = qme_module.random
            qme_module.random = forced
            try:
                story = list(super()._build_history(*args, **kwargs))
            finally:
                qme_module.random = original

            if not forced.fired:
                log.warning("fact_templates.history_imaging_not_forced")
            return story

    class FactAwareMedicalStoryQmeReport(
        _MedicalStoryQmeSections, _SpecCapture, qme_module.QmeAmeReport  # type: ignore[misc,name-defined]
    ):
        """The R9 story sections over the RAW substrate QME/AME report.

        Mount for the R8 members that had no fact-aware registration before
        M3 — ``AME_REPORT``, ``MEDICAL_LEGAL_QME_AME_IME``,
        ``APPORTIONMENT_REPORT`` and ``PSYCH_EVAL_REPORT_QME_AME``. Their
        exact pre-M3 path is the unmodified substrate, so the story-absent
        delegation lands there rather than on the clinical overrides the
        five previously registered QME subtypes carry — mounting these on
        :class:`FactAwareNeuroQmeReport` would have changed their
        feature-absent bytes, which R1 forbids (R11's "delegate through the
        exact pre-M3 path").
        """

    ur_module = import_substrate("pdf_templates.medical.utilization_review")

    class FactAwareUtilizationReview(_SpecCapture, ur_module.UtilizationReview):  # type: ignore[misc,name-defined]
        """Reviews the procedure the case is actually about.

        ``_build_request_details`` drew one to three CPTs at random from the
        *whole* code table, so a UR determination on a lumbar case could be
        adjudicating a cervical MRI and a work-disability exam. When the ledger
        names a procedure — ``recommended`` or ``denied_by_ur``, the two states
        that exist precisely because a request was made — the request is that
        procedure, and the RFA, the determination and the treating report all
        finally name one thing.

        Left alone otherwise: a case with no surgical request has UR activity
        about something this ledger does not model, and inventing a subject for
        it would be worse than the substrate's own draw.
        """

        def build_story(self, doc_spec: Any) -> list[Any]:
            context = doc_spec.context if isinstance(doc_spec.context, dict) else {}
            content = context.get("imr_application_content")
            if _subtype_of(self) != "IMR_APPLICATION_FORM" or content is None:
                return list(super().build_story(doc_spec))

            applicant_firm = str(
                context.get("imr_applicant_firm") or "Counsel for the Applicant"
            )
            flow: list[Any] = []
            flow.extend(
                self.make_letterhead(
                    applicant_firm,
                    "Applicant Counsel Address on File",
                    "Telephone on File",
                )
            )
            flow.append(Spacer(1, 0.3 * inch))
            flow.append(
                Paragraph(
                    "<b>INDEPENDENT MEDICAL REVIEW APPLICATION</b>",
                    self.styles["CenterBold"],
                )
            )
            flow.append(Spacer(1, 0.2 * inch))
            claim_rows = [
                ["Applicant:", self.case.applicant.full_name],
                ["Claim Number:", self.case.insurance.claim_number],
                [
                    "Date of Injury:",
                    self.case.timeline.date_of_injury.strftime("%m/%d/%Y"),
                ],
                ["Employer:", self.case.employer.company_name],
                ["Application Date:", doc_spec.doc_date.strftime("%m/%d/%Y")],
            ]
            claim_table = Table(claim_rows, colWidths=[2 * inch, 4 * inch])
            claim_table.setStyle(
                TableStyle(
                    [
                        ("ALIGN", (0, 0), (0, -1), "RIGHT"),
                        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, -1), 9),
                        ("TOPPADDING", (0, 0), (-1, -1), 3),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ]
                )
            )
            flow.append(claim_table)
            flow.append(Spacer(1, 0.3 * inch))

            if content.disputed_treatment is not None:
                flow.extend(
                    self.make_section(
                        "DISPUTED TREATMENT", content.disputed_treatment
                    )
                )
            flow.extend(
                self.make_section(
                    "UTILIZATION-REVIEW DETERMINATION",
                    f"{content.target_denial_subtype.replace('_', ' ')} dated "
                    f"{content.target_denial_date.strftime('%B %d, %Y')}.",
                )
            )
            if content.diagnosis_icd10 is not None:
                flow.extend(
                    self.make_section(
                        "PRIMARY DIAGNOSIS", content.diagnosis_icd10
                    )
                )
            if content.ur_determination_attached is not None:
                attachment = (
                    "The utilization-review determination is attached."
                    if content.ur_determination_attached
                    else "The utilization-review determination is not attached."
                )
                flow.extend(self.make_section("ATTACHMENT", attachment))
            if content.supporting_record_subtypes:
                records = "\n".join(
                    f"• {subtype.replace('_', ' ')}"
                    for subtype in content.supporting_record_subtypes
                )
                flow.extend(
                    self.make_section("SUPPORTING MEDICAL RECORDS", records)
                )
            if content.clinical_rebuttal is not None:
                flow.extend(
                    self.make_section(
                        "CLINICAL REBUTTAL", content.clinical_rebuttal
                    )
                )
            if content.mtus_citations:
                sentences = [
                    _register_clauses(IMR_APPLICATION_REGISTER, "mtus")[0].replace(
                        "[grounded MTUS citation]", citation
                    )
                    for citation in content.mtus_citations
                ]
                flow.extend(self.make_section("MTUS SUPPORT", " ".join(sentences)))

            flow.append(Spacer(1, 0.3 * inch))
            flow.extend(
                self.make_signature_block(
                    applicant_firm,
                    "Attorneys for Applicant",
                    "",
                )
            )
            return flow

        def _build_request_details(self, body_parts: Any) -> list[Any]:
            facts = _facts_of(self)
            if facts is None or not facts.surgery.names_a_procedure:
                return list(super()._build_request_details(body_parts))

            surgery = facts.surgery
            if not surgery.cpt_code:
                # An uncoded operation (AJC-55): the request must say so in the
                # ledger's own words. Delegating to the substrate here would
                # free-draw coded procedures the ledger refuses to name.
                region = (surgery.body_part or "the injured body part").replace("_", " ")
                bp_str = ", ".join(body_parts).lower() if body_parts else region
                content = (
                    f"<b>Requesting Physician:</b> {self.case.treating_physician.full_name}, "
                    f"{self.case.treating_physician.specialty}\n\n"
                    f"<b>Body Part(s):</b> {bp_str}\n\n"
                    "<b>Treatment Requested:</b>\n"
                    f"\u2022 Authorization for an unlisted surgical procedure (uncoded) "
                    f"of the {region}; no procedure code is asserted for this request."
                )
                return list(self.make_section("REQUEST DETAILS", content))
            forced = _ForcedChoice(
                [(surgery.cpt_code, surgery.cpt_description)],
                lambda seq: bool(seq)
                and isinstance(seq[0], tuple)
                and len(seq[0]) == 2
                and str(seq[0][0]).isdigit(),
            )
            original = ur_module.random
            ur_module.random = forced
            try:
                story = list(super()._build_request_details(body_parts))
            finally:
                ur_module.random = original

            if not forced.fired:
                log.warning("fact_templates.ur_procedure_not_forced", cpt=surgery.cpt_code)
            return story

        def _pick_decision(self, is_imr: bool) -> str:
            """R57 — one governed IMR outcome, never a second render draw."""
            context = getattr(getattr(self, "doc_spec", None), "context", None)
            outcome = context.get("imr_outcome") if isinstance(context, dict) else None
            if is_imr and outcome == "upheld":
                return "UPHELD — NOT MEDICALLY NECESSARY"
            if is_imr and outcome == "overturned":
                return "OVERTURNED — APPROVED"
            return str(super()._pick_decision(is_imr))

    class FactAwareDischargeSummary(FactAwareOperativeRecord):
        """A discharge summary that does not call itself an operative report.

        ``DISCHARGE_SUMMARY`` is mapped to ``OperativeRecord`` with a
        ``discharge`` variant the template never reads, so every discharge
        summary rendered with the heading "OPERATIVE REPORT". On a discharged
        case with no surgery that is not a cosmetic problem — it is an
        operation appearing in a file whose ledger denies one.

        The heading is retitled and a disposition section appended. The clinical
        body is left exactly as the substrate wrote it: a discharge summary
        legitimately recites the course of care, and rewriting all of it here
        would be forking the template to fix a title.

        Subclasses ``FactAwareOperativeRecord`` — not the substrate template —
        so the body inherits the ledger's CPT pinning (round-4 review: the
        direct substrate parent let a shoulder case discharge a different
        shoulder operation than the one the file performed).
        """

        def build_story(self, doc_spec: Any) -> list[Any]:
            story = list(super().build_story(doc_spec))
            facts = _facts_of(self)

            # Replaced rather than edited in place: reportlab parses a
            # Paragraph's markup in ``__init__``, so assigning to ``.text``
            # afterwards changes the attribute and nothing that renders. The
            # first version of this did exactly that and the heading still read
            # OPERATIVE REPORT in the PDF.
            for position, element in enumerate(story):
                text = str(getattr(element, "text", ""))
                if "OPERATIVE REPORT" in text:
                    story[position] = Paragraph(
                        text.replace("OPERATIVE REPORT", "DISCHARGE SUMMARY"),
                        getattr(element, "style", self.styles["CenterBold"]),
                    )

            discharged = facts.discharge_date if facts is not None else None
            dated = f" on {discharged.strftime('%B %d, %Y')}" if discharged else ""
            story.extend(
                self.make_section(
                    "DISPOSITION",
                    f"The applicant was discharged from active care{dated}. Care is "
                    "concluded; no further treating appointments are scheduled. The "
                    "applicant was advised to return on an as-needed basis should "
                    "symptoms recur.",
                )
            )
            return story

    adjuster_module = import_substrate("pdf_templates.correspondence.adjuster_letter")

    class FactAwareAdjusterLetter(_SpecCapture, adjuster_module.AdjusterLetter):  # type: ignore[misc,name-defined]
        """Writes a letter this case could actually have produced.

        The substrate drew one of five letter bodies per document, independently
        — so a file with three adjuster letters could open the claim for the
        first time three separate times, and a case with no UR dispute could
        receive a determination letter about a review that never happened.

        Two rules, both from the lifecycle rather than from a draw:

        * the type must be one the case can support
          (``CaseFacts.adjuster_letter_types_allowed``), and
        * the case walks *through* the allowed types rather than sampling them,
          so the once-only ones happen once.

        Ordered so the chronology reads correctly: a case accepts the claim
        before it discusses settling it.
        """

        #: Allowed types in the order a file would produce them.
        ORDER = (
            "initial_acceptance",
            "medical_records_request",
            "ur_decision",
            "pd_advance_offer",
            "settlement_discussion",
        )

        #: Types a file can legitimately repeat. A claim is accepted once.
        REPEATABLE = ("medical_records_request", "settlement_discussion", "pd_advance_offer")

        def _letter_type_for(self, facts: Any, ordinal: int) -> str:
            allowed = [name for name in self.ORDER if name in facts.adjuster_letter_types_allowed]
            if not allowed:
                return "medical_records_request"
            if ordinal < len(allowed):
                return allowed[ordinal]
            # Past the one-time types, cycle only what can honestly recur.
            repeatable = [name for name in allowed if name in self.REPEATABLE] or allowed
            return repeatable[(ordinal - len(allowed)) % len(repeatable)]

        def build_story(self, doc_spec: Any) -> list[Any]:
            facts = _facts_of(self)
            if facts is None or not facts.adjuster_letter_types_allowed:
                return list(super().build_story(doc_spec))

            wanted = self._letter_type_for(facts, _letter_ordinal(self))
            target = getattr(self, f"_{wanted}", None)
            if target is None:
                log.warning("fact_templates.adjuster_letter_method_missing", wanted=wanted)
                return list(super().build_story(doc_spec))

            forced = _ForcedChoice(
                target,
                lambda seq: len(seq) == len(ADJUSTER_LETTER_TYPES)
                and all(callable(item) for item in seq),
            )
            original = adjuster_module.random
            adjuster_module.random = forced
            try:
                story = list(super().build_story(doc_spec))
            finally:
                adjuster_module.random = original

            if not forced.fired:
                log.warning(
                    "fact_templates.adjuster_letter_type_not_forced",
                    wanted=wanted,
                    expected=len(ADJUSTER_LETTER_TYPES),
                )
            return story

    _ = Paragraph  # imported for subclasses that grow to need it

    records_module = import_substrate("pdf_templates.discovery.subpoenaed_records")

    class FactAwareSubpoenaedRecords(_SpecCapture, records_module.SubpoenaedRecords):  # type: ignore[misc,name-defined]
        """ISC-126. Makes the cover sheet tell the truth about the packet it fronts.

        The substrate built its table of contents from one set of
        ``random.randint`` draws (``subpoenaed_records.py:163-186``) and then
        generated the body from an entirely separate set (``264+``). Neither
        number was wrong on its own — they were simply strangers, so a cover
        sheet could promise 23 pages in front of a packet holding 6.

        One number now decides both. ``CaseFacts.packet_pages`` is drawn once on
        the ``facts:`` stream at plan time; the body is cut to it and the table
        of contents is rewritten to sum to what the body actually holds.

        The rewrite mutates ``Table._cellvalues`` rather than rebuilding the
        flowable, which preserves the substrate's column widths and style
        commands. Verified deliberately: unlike ``Paragraph``, which parses its
        markup in ``__init__`` and ignores later edits to ``.text``, ``Table``
        reads ``_cellvalues`` at draw time, so the mutation reaches the page.
        """

        #: Sections the current render should use; ``None`` means "take what the
        #: substrate produced". Set by the measure-then-adjust loop.
        _wc_sections: int | None = None
        #: Page count the cover sheet should state, once one has been measured.
        _wc_toc_total: int | None = None
        #: Sections the last render actually used, which is what the loop steers.
        _wc_last_sections: int = 0
        #: Blank continuation pages appended to reach the budget exactly.
        _wc_pad: int = 0

        def _page_budget(self, facts: Any) -> int | None:
            pages = getattr(facts, "packet_pages", ())
            if not pages:
                return None
            return pages[_packet_ordinal(self) % len(pages)]

        def build_story(self, doc_spec: Any) -> list[Any]:
            story = list(super().build_story(doc_spec))
            facts = _facts_of(self)
            if facts is None:
                return story
            budget = self._page_budget(facts)
            if budget is None:
                return story

            head, body = _split_at_first_break(story)
            sections = _split_pages(body)
            if not sections:
                return story

            provider, facility = self._select_provider(doc_spec)
            subtype = str(getattr(doc_spec, "subtype", ""))
            build_more = (
                (lambda: self._build_employment_records(doc_spec))
                if "EMPLOYMENT" in subtype
                else (lambda: self._build_medical_records(doc_spec, provider, facility))
            )

            # A section is a PageBreak-delimited block, which is NOT a physical
            # page — a long one overflows. ``_generate_pdf`` measures the
            # rendered result and drives this number until the paper agrees;
            # the first pass just asks for the budget and lets it correct.
            wanted = self._wc_sections
            if wanted is None:
                wanted = max(1, budget - 1)
            realised = _fit_pages(sections, wanted, build_more)
            self._wc_last_sections = len(realised)
            # Written from the MEASURED page count once one exists, so the cover
            # sheet describes the packet as printed rather than as intended.
            _rewrite_page_table(head, self._wc_toc_total or len(realised) + 1)
            body_out = _join_pages(realised, records_module.PageBreak)
            # Sections are atomic and one can overflow, so section count alone
            # cannot hit an arbitrary page total. The loop undershoots and the
            # remainder is made up in whole continuation pages, which a real
            # records production contains anyway.
            for _ in range(self._wc_pad):
                body_out.append(records_module.PageBreak())
                body_out.append(
                    Paragraph(
                        "[This page intentionally contains no further records.]",
                        self.styles["BodyText"],
                    )
                )
            return head + body_out

        def _generate_pdf(self, output_path: Any, doc_spec: Any) -> Any:
            """Render, count the pages that came out, adjust, render again.

            The only honest way to make ``pages_per_set`` mean *pages*. Section
            count is a proxy the layout is free to ignore, so it is measured
            rather than assumed, and the table of contents is written from the
            measurement.

            Every attempt restores the RNG state it started from. Without that
            each re-render draws different clinical content, so the page count
            that was measured would not be the page count finally written — the
            measurement would describe a document that no longer exists.
            """
            facts = _facts_of(self)
            budget = self._page_budget(facts) if facts is not None else None
            if budget is None:
                return super()._generate_pdf(output_path, doc_spec)

            entry_state = random.getstate()
            self._wc_sections = None
            self._wc_toc_total = None
            self._wc_pad = 0

            result = super()._generate_pdf(output_path, doc_spec)
            pages = _page_count(output_path)
            sections = self._wc_last_sections

            # Walk down to the largest section count that fits inside the
            # budget. Down rather than towards, because overshoot cannot be
            # repaired -- there is no way to remove part of a page -- while an
            # undershoot is made up exactly by padding.
            for _ in range(_MAX_FIT_ATTEMPTS):
                if pages <= budget:
                    break
                adjusted = max(1, sections - max(1, pages - budget))
                if adjusted == sections:
                    break
                sections = adjusted
                random.setstate(entry_state)
                self._wc_sections = sections
                result = super()._generate_pdf(output_path, doc_spec)
                pages = _page_count(output_path)
                sections = self._wc_last_sections

            # Final pass: same content, remainder padded, table restated from
            # the number the paper will actually carry.
            random.setstate(entry_state)
            self._wc_sections = sections
            self._wc_pad = max(0, budget - pages)
            self._wc_toc_total = pages + self._wc_pad
            result = super()._generate_pdf(output_path, doc_spec)
            pages = self._wc_toc_total
            if _page_count(output_path) != pages:
                # Restating the table changed the pagination, which would leave
                # the cover sheet describing the previous render. Say so rather
                # than ship a packet whose own first page is wrong.
                log.warning(
                    "fact_templates.packet_page_table_unstable",
                    expected=pages,
                    actual=_page_count(output_path),
                )
            return result

    client_module = import_substrate("pdf_templates.correspondence.client_intake")

    class FactAwareClientIntake(_SpecCapture, client_module.ClientIntake):  # type: ignore[misc,name-defined]
        """ISC-125. Names the event that prompted the letter.

        ISC-123/124 put ``event_driven`` letters on the right dates; a reader
        still had to recompute the cadence to see *why* a letter was written
        when it was. The reference makes it checkable on the page: the letter
        cites a document that is in the same folder, dated before it.

        Only ``event_driven``. Under the other two cadences the letter is not
        responding to anything — a thirty-day letter is written because thirty
        days passed — so a reference would be a claim the file does not support.
        That distinction is also what makes the guard meaningful: an
        unconditional sentence would prove the string exists and nothing else.
        """

        def build_story(self, doc_spec: Any) -> list[Any]:
            story = list(super().build_story(doc_spec))
            facts = _facts_of(self)
            if facts is None or facts.attorney_cadence != "event_driven":
                return story

            anchor = _preceding_anchor(self, getattr(doc_spec, "doc_date", None))
            if anchor is None:
                # Nothing precedes this letter, so there is nothing to answer.
                # Silence is the honest rendering.
                return story

            subtype, when = anchor
            label = effective_taxonomy().label(subtype) or subtype.replace("_", " ").title()
            sentence = (
                f"{ANCHOR_REFERENCE_MARKER.capitalize()} {label} of "
                f"{when.strftime('%B %d, %Y')}, we are writing to update you on "
                "the status of your claim and what happens next."
            )
            story.insert(
                _before_closing(story),
                Paragraph(sentence, self.styles["BodyText14"]),
            )
            return story

    wage_module = import_substrate("pdf_templates.employment.wage_statement")
    cr_module = import_substrate("pdf_templates.legal.compromise_and_release")
    minutes_module = import_substrate("pdf_templates.legal.minutes_orders")
    stips_module = import_substrate("pdf_templates.legal.stipulations")
    billing_module = import_substrate("pdf_templates.medical.billing_records")
    memo_module = import_substrate("pdf_templates.summaries.settlement_memo")

    reserve_bucket_rows = (
        ("Indemnity", "indemnity"),
        ("Medical", "medical"),
        ("Expense / ALAE", "expense_alae"),
        ("Total", "total"),
    )

    def reserve_money(value: Decimal) -> str:
        return f"${value:,.2f}"

    def reserve_table_style() -> Any:
        from reportlab.lib import colors

        return TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ]
        )

    def exposure_table(exposure: Any) -> Any:
        data = [["Bucket", "Low", "Expected", "High"]]
        for label, field in reserve_bucket_rows:
            data.append(
                [
                    label,
                    reserve_money(getattr(exposure.low, field)),
                    reserve_money(getattr(exposure.expected, field)),
                    reserve_money(getattr(exposure.high, field)),
                ]
            )
        table = Table(
            data,
            colWidths=[1.45 * inch, 1.35 * inch, 1.35 * inch, 1.35 * inch],
        )
        table.setStyle(reserve_table_style())
        return table

    def snapshot_table(snapshot: Any) -> Any:
        data = [["Bucket", "Paid", "Outstanding Reserve", "Incurred"]]
        for label, field in reserve_bucket_rows:
            data.append(
                [
                    label,
                    reserve_money(getattr(snapshot.paid, field)),
                    reserve_money(getattr(snapshot.outstanding_reserve, field)),
                    reserve_money(getattr(snapshot.incurred, field)),
                ]
            )
        table = Table(
            data,
            colWidths=[1.45 * inch, 1.2 * inch, 1.65 * inch, 1.2 * inch],
        )
        table.setStyle(reserve_table_style())
        return table

    def reserve_header(template: Any, title: str, effective_date: Any) -> list[Any]:
        story: list[Any] = []
        story.append(Paragraph(escape(title), template.styles["CenterBold"]))
        story.append(Spacer(1, 0.12 * inch))
        story.append(
            Paragraph(
                f"<b>Effective Date:</b> {effective_date.strftime('%B %d, %Y')}",
                template.styles["BodyText14"],
            )
        )
        return story

    def reserve_section(story: list[Any], template: Any, title: str, table: Any) -> None:
        story.append(Spacer(1, 0.14 * inch))
        story.append(Paragraph(f"<b>{escape(title)}</b>", template.styles["SectionHeader"]))
        story.append(Spacer(1, 0.06 * inch))
        story.append(table)

    def reserve_list(story: list[Any], template: Any, title: str, values: Any) -> None:
        story.append(Spacer(1, 0.12 * inch))
        story.append(Paragraph(f"<b>{escape(title)}</b>", template.styles["SectionHeader"]))
        for value in values:
            story.append(
                Paragraph(f"• {escape(str(value))}", template.styles["BodyText14"])
            )

    class FactAwareInitialFileReview(_SpecCapture, billing_module.BillingRecords):  # type: ignore[misc,name-defined]
        """The sole IFR worksheet, rendered only from its bound R72 object."""

        def build_story(self, doc_spec: Any) -> list[Any]:
            event = _reserve_event_of(self)
            if not isinstance(event, InitialFileReview):
                return list(super().build_story(doc_spec))

            story = reserve_header(self, "Initial File Review", event.review_date)
            story.extend(
                [
                    Paragraph(
                        f"<b>Event ID:</b> {escape(event.event_id)}",
                        self.styles["BodyText14"],
                    ),
                    Paragraph(
                        f"<b>Compensability Posture:</b> "
                        f"{escape(event.compensability_posture)}",
                        self.styles["BodyText14"],
                    ),
                    Paragraph(
                        f"<b>Case Evaluation:</b> {escape(event.case_evaluation)}",
                        self.styles["BodyText14"],
                    ),
                    Paragraph(
                        f"<b>Litigation Budget:</b> "
                        f"{reserve_money(event.litigation_budget)}",
                        self.styles["BodyText14"],
                    ),
                    Paragraph(
                        f"<b>Authority Status:</b> {escape(event.authority_status)}",
                        self.styles["BodyText14"],
                    ),
                    Paragraph(
                        f"<b>Adoption Lag:</b> {event.adoption_lag_days} days",
                        self.styles["BodyText14"],
                    ),
                ]
            )
            reserve_section(
                story, self, "Ultimate Exposure Range", exposure_table(event.exposure)
            )
            reserve_section(
                story,
                self,
                "Recommended Snapshot",
                snapshot_table(event.recommendation),
            )
            reserve_section(
                story,
                self,
                "Booked Snapshot",
                snapshot_table(event.booked_snapshot),
            )
            reserve_list(story, self, "Discovery Plan", event.discovery_plan)
            reserve_list(story, self, "IFR Assumptions", event.assumptions)
            reserve_list(story, self, "Exposure Assumptions", event.exposure.assumptions)
            return story

    class FactAwareReserveChangeNotice(_SpecCapture, billing_module.BillingRecords):  # type: ignore[misc,name-defined]
        """One changed post-IFR reserve event, rendered from that exact R73 object."""

        def build_story(self, doc_spec: Any) -> list[Any]:
            event = _reserve_event_of(self)
            if not isinstance(event, ReserveEvent):
                return list(super().build_story(doc_spec))

            story = reserve_header(self, "Reserve Change Notice", event.event_date)
            story.extend(
                [
                    Paragraph(
                        f"<b>Event ID:</b> {escape(event.id)}",
                        self.styles["BodyText14"],
                    ),
                    Paragraph(
                        f"<b>Trigger:</b> {escape(event.trigger)}",
                        self.styles["BodyText14"],
                    ),
                    Paragraph(
                        f"<b>Reason:</b> {escape(event.reason)}",
                        self.styles["BodyText14"],
                    ),
                    Paragraph(
                        f"<b>Adoption Lag:</b> {event.adoption_lag_days} days",
                        self.styles["BodyText14"],
                    ),
                ]
            )
            reserve_section(
                story, self, "Ultimate Exposure Range", exposure_table(event.exposure)
            )
            reserve_section(
                story,
                self,
                "Prior Booked Snapshot",
                snapshot_table(event.prior_snapshot),
            )
            reserve_section(
                story,
                self,
                "Recommended Snapshot",
                snapshot_table(event.recommendation),
            )
            reserve_section(
                story,
                self,
                "New Booked Snapshot",
                snapshot_table(event.booked_snapshot),
            )
            reserve_list(story, self, "Exposure Assumptions", event.exposure.assumptions)
            return story

    class FactAwareWageStatement(_SpecCapture, wage_module.WageStatement):  # type: ignore[misc,name-defined]
        """Prints the ledger's earnings and rate instead of inventing both.

        The substrate's wage statement is the sharpest instance in the corpus of
        the defect this package exists to remove. It draws eight to twelve pay
        periods from ``random.randint``, averages them, and then prints:

            Temporary Total Disability Rate: $X/week (2/3 AWW, max $1,619.15)

        Three separate problems in one line. The fraction and the ceiling are
        hardcoded, so every file in a multi-year caseload is rated under one
        vintage regardless of its date of injury. The method is asserted in
        passing rather than recorded, so there is no label to score an analyzer
        against. And the earnings behind the average are dice, so the average is
        not derivable from anything — which is the one property that makes money
        worth generating at all.

        Fixed by **replacing two tables**, not by forking the method. The
        letterhead, the employee block, the styling, the HR signature and the
        attestation are all the substrate's and all fine; only the numbers are
        wrong. The tables are found by their own header text rather than by
        position, so a substrate edit that moves them is a miss this class
        *reports* instead of silently writing over the wrong table.

        One class serves the whole family because the substrate registry routes
        every wage and payment-record subtype to ``WageStatement``. Which
        document is on the page is decided by the subtype, not by the class.

        This docstring used to say *eight* subtypes, and the map below listed
        eight. The registry routes ten the engine can actually emit. The two
        nobody had counted were ``PRIOR_CLAIMS_EDD_SDI_INFO``, which printed a
        temporary-disability rate of $848.53 beside a ledger publishing $767.59,
        and ``TIMECARDS_SCHEDULES``. The family is now bound from the registry,
        so counting is not something anybody has to get right again.
        """

        def build_story(self, doc_spec: Any) -> list[Any]:
            story = list(super().build_story(doc_spec))
            money = _money_of(self)
            if money is None:
                # No money layer. The exact original story, untouched — this is
                # the branch the anti-criterion asserts.
                return story
            if _subtype_of(self) in BENEFIT_RECORD_SUBTYPES:
                return _rewrite_benefit_record(story, money, self.styles)
            return _rewrite_wage_statement(story, money, self.styles)

    class FactAwareCompromiseAndRelease(_SpecCapture, cr_module.CompromiseAndRelease):  # type: ignore[misc,name-defined]
        """Settles for the ledger's gross rather than a free draw.

        A single intercepted draw, and deliberately only one. The substrate
        computes ``gross_settlement = random.randint(25000, 150000)`` and then
        derives the attorney fee, the costs, the set-aside and the net *from
        it*, in its own code. Forcing the base number leaves that arithmetic
        internally consistent and unforked; forcing the derived figures as well
        would be writing the disbursement, which is the applicant-lens ticket's
        work, not this one's.

        The interception is by argument match, so it can tell this draw from the
        four other ``randint`` calls in the same method — and reports a miss
        rather than swallowing one, because a silent miss here is a manifest
        publishing a gross the document contradicts.
        """

        def build_story(self, doc_spec: Any) -> list[Any]:
            money = _money_of(self)
            if money is None or money.settlement is None:
                return list(super().build_story(doc_spec))

            gross = money.settlement.gross_amount
            if gross != int(gross):
                # Unreachable by construction — the ledger quantizes to whole
                # dollars and the seed schema refuses cents — and reported
                # rather than truncated anyway, because the substrate's draw is
                # an integer and truncating here is exactly how the manifest
                # would come to publish a gross the release contradicts.
                log.warning(
                    "fact_templates.settlement_gross_not_whole_dollars",
                    gross=str(gross),
                )
            # The gross, and the two deductions taken out of it. The substrate
            # draws costs and a Medicare set-aside from ranges that know nothing
            # about the settlement they are subtracted from, so a small gross
            # printed **Net to Applicant $-17,608** — a release stating that the
            # applicant owes money for settling. Both are pinned as fractions of
            # the gross, which keeps the net positive by construction and keeps
            # the release's own arithmetic reproducible from the page.
            total = int(gross)
            # The set-aside is a *governed* fact, not just an amount:
            # ``lifecycle.resolution.msa`` says whether this file has one, and
            # forcing an allocation regardless meant a seed stating `msa: false`
            # still got a release printing a Medicare Set-Aside Allocation.
            wants_msa = _wants_medicare_set_aside(self)
            _, costs, allocation = settlement_deductions(total)
            set_aside = allocation if wants_msa else 0
            forced = _ForcedRandint(total, _SUBSTRATE_SETTLEMENT_RANGE)
            deductions = _ForcedChain(
                [
                    forced,
                    _ForcedRandint(costs, _SUBSTRATE_CR_COSTS_RANGE),
                    _ForcedRandint(set_aside, _SUBSTRATE_CR_MSA_RANGE),
                ]
            )
            original = cr_module.random
            cr_module.random = deductions
            try:
                story = list(super().build_story(doc_spec))
            finally:
                cr_module.random = original

            if not forced.fired:
                log.warning(
                    "fact_templates.settlement_gross_not_forced",
                    expected=list(_SUBSTRATE_SETTLEMENT_RANGE),
                    gross=str(money.settlement.gross_amount),
                )
            _restate_distribution(story, total, costs, set_aside, wants_msa, self.styles)
            return _append_settlement_terms(story, money, self.styles, "agreement")

    class FactAwareStipulations(_SpecCapture, stips_module.Stipulations):  # type: ignore[misc,name-defined]
        """The stipulated award states the ledger's money, not its own.

        The counterpart of :class:`FactAwareCompromiseAndRelease` for the other
        resolution type, and it was missing — so every ``stipulations`` case
        shipped its primary settlement document computing an average weekly
        wage, a temporary-disability run and a permanent-disability award from
        scratch, contradicting the manifest beside it.

        The permanent-disability award is forced through the same interception
        the release uses; the two money stipulations are rewritten in place.
        """

        def build_story(self, doc_spec: Any) -> list[Any]:
            money = _money_of(self)
            if money is None:
                return list(super().build_story(doc_spec))

            forced: list[_ForcedRandint] = []
            original = stips_module.random
            scope = "agreement"
            if money.settlement is not None:
                # The first cut forced the settlement gross into the substrate's
                # ``base_pd_award``, where the page labels it "Permanent
                # Disability (Gross)" and then adds a self-procured medical
                # reimbursement on top. The same number therefore meant "the
                # whole settlement" in the manifest and "one component of the
                # award" on the page, and the components summed past the total.
                # A shared extraction key needs one stable meaning, and the one
                # ``grossAmount`` has on the release is *the total resolution
                # value* — so the components are reconciled to it here instead.
                #
                # Only the two **cash** components are reconciled. The SJDB
                # voucher is a training benefit rather than money out of the
                # award, and the attorney fee and net are the substrate's own
                # derivations from the award figure, so they stay consistent
                # without help. Disbursement past that line is AJC-46's.
                total = int(money.settlement.gross_amount)
                # The split holds for **every** gross the schema accepts. An
                # earlier cut clamped the reimbursement into the substrate's own
                # ``randint`` bounds and gave up beneath them, so a gross of
                # $5,499 printed components totalling $32,696 beside a published
                # $5,499. Those bounds select *which draw* to answer and never
                # constrained the answer.
                self_procured = _reimbursement_nearest_five_percent(total)
                award = total - self_procured
                forced = [
                    _ForcedRandint(award, _SUBSTRATE_STIPS_AWARD_RANGE),
                    _ForcedRandint(self_procured, _SUBSTRATE_STIPS_SELF_PROCURED_RANGE),
                ]
                stips_module.random = _ForcedChain(forced)
            try:
                story = list(super().build_story(doc_spec))
            finally:
                stips_module.random = original
            for interception in forced:
                if not interception.fired:
                    log.warning(
                        "fact_templates.stipulated_component_not_forced",
                        bounds=list(interception.bounds),
                        gross=str(money.settlement.gross_amount),
                    )
            story = _rewrite_stipulations(story, money, self.styles)
            if money.settlement is not None and forced:
                _restate_award_summary(story, int(money.settlement.gross_amount),
                                       forced[0], forced[1], self.styles)
            # And the total itself on the page, under its own label, so the two
            # components can be checked against it rather than merely believed.
            return _append_settlement_terms(story, money, self.styles, scope)

    class FactAwareOrderApprovingSettlement(_SpecCapture, minutes_module.MinutesOrders):  # type: ignore[misc,name-defined]
        """An order approving a settlement says the settlement was approved.

        The first version of this class appended an approval table to
        ``MinutesOrders`` and left the base's own body alone, which was worse
        than printing nothing. ``MinutesOrders`` ignores its
        ``approving_settlement`` variant and draws its proceedings from a pool
        about ongoing litigation, so the designated evidence for the approval
        read: *"The parties have been unable to reach a settlement agreement at
        this time"*, immediately above a row reading ``Date Approved``. A
        document that contradicts the fact it is carrying is not weak evidence,
        it is counter-evidence.

        The substrate's WCAB caption is right and is kept; everything from its
        title onward is replaced with the order this subtype names. Truncating
        at the title is the same index surgery the payment record already uses,
        and it reports a miss rather than silently emitting the litigation body.
        """

        def build_story(self, doc_spec: Any) -> list[Any]:
            from reportlab.lib.units import inch
            from reportlab.platypus import Paragraph, Spacer

            story = list(super().build_story(doc_spec))
            money = _money_of(self)
            if money is None or money.settlement is None:
                return story

            cut = _index_of_text(story, "MINUTES OF HEARING AND ORDERS")
            if cut is None:
                log.warning("fact_templates.order_body_not_replaced")
                return story
            story = story[:cut]

            settlement = money.settlement
            title = (
                "ORDER APPROVING COMPROMISE AND RELEASE"
                if settlement.kind == "c_and_r"
                else "ORDER APPROVING STIPULATED AWARD"
            )
            instrument = (
                "Compromise and Release"
                if settlement.kind == "c_and_r"
                else "Stipulations with Request for Award"
            )
            approved = (
                settlement.approval_date.strftime("%B %d, %Y")
                if settlement.approval_date
                else doc_spec.doc_date.strftime("%B %d, %Y")
            )
            story.append(Paragraph(title, self.styles["CenterBold"]))
            story.append(Spacer(1, 12))
            story.append(
                Paragraph(
                    f"The {instrument} filed herein having been considered, and good "
                    f"cause appearing, the Workers' Compensation Appeals Board finds "
                    f"that its terms are adequate and that its approval is in the best "
                    f"interest of the parties.",
                    self.styles["DoubleSpaced"],
                )
            )
            story.append(Spacer(1, 8))
            story.append(
                Paragraph(
                    f"IT IS HEREBY ORDERED that the {instrument} be, and it is hereby, "
                    f"APPROVED as of {approved}.",
                    self.styles["DoubleSpaced"],
                )
            )
            _append_settlement_terms(story, money, self.styles, "approval")
            story.append(Spacer(1, 0.3 * inch))
            story.extend(
                self.make_signature_block(self.case.judge_name, "Workers' Compensation Judge")
            )
            return story

    class FactAwareBenefitPaymentLedger(_SpecCapture, billing_module.BillingRecords):  # type: ignore[misc,name-defined]
        """The claims administrator's ledger of what it paid, and when.

        The first version of this class appended a funding table to
        ``BillingRecords``, whose base is a *provider* statement of charges —
        doctor's letterhead, random CPT codes, a balance due. A benefit-free
        settled case therefore evidenced its settlement funding with a
        $16,724.23 medical bill. The problem was not the date or the table; it
        was that the document was about somebody else's money.

        So this one is built rather than decorated. It uses the substrate's own
        letterhead and claim-reference helpers with the *carrier* as author,
        which is who actually issues a benefit payment ledger, and its body is
        the ledger: every temporary-disability period, every permanent-disability
        advance, the settlement disbursement, and the totals the manifest
        publishes. It is the one document in the folder dated after the draft
        cleared, which is what makes it the only honest carrier for the funding
        date and the interval.
        """

        def build_story(self, doc_spec: Any) -> list[Any]:
            from reportlab.lib.units import inch
            from reportlab.platypus import Paragraph, Spacer

            money = _money_of(self)
            if money is None:
                return list(super().build_story(doc_spec))

            carrier = self.case.insurance
            story: list[Any] = []
            story.extend(
                self.make_letterhead(
                    carrier.carrier_name,
                    f"Claims Service Center, Claim {carrier.claim_number}",
                    carrier.adjuster_phone,
                )
            )
            story.append(Spacer(1, 0.3 * inch))
            story.extend(self.make_claim_reference_block())
            story.append(Spacer(1, 0.2 * inch))
            story.append(Paragraph("<b>BENEFIT PAYMENT LEDGER</b>", self.styles["CenterBold"]))
            story.append(Spacer(1, 0.2 * inch))
            story.append(
                Paragraph(
                    f"<b>Ledger Date:</b> {doc_spec.doc_date.strftime('%B %d, %Y')}",
                    self.styles["BodyText14"],
                )
            )
            story.append(Spacer(1, 0.2 * inch))

            benefits = money.benefits
            rows: list[list[Any]] = [["Benefit", "Period / Due", "Paid", "Amount"]]
            for period in benefits.td_periods:
                rows.append(
                    [
                        "Temporary Disability",
                        f"{period.start.isoformat()} to {period.end.isoformat()}",
                        period.date_paid.isoformat() if period.date_paid else "unpaid",
                        f"${period.amount:,.2f}",
                    ]
                )
            for advance in benefits.pd_advances:
                rows.append(
                    [
                        "Permanent Disability Advance",
                        advance.date_due.isoformat(),
                        advance.date_paid.isoformat(),
                        f"${advance.amount:,.2f}",
                    ]
                )
            rows.append(["Temporary Disability Paid To Date", "", "", f"${benefits.td_total:,.2f}"])
            rows.append(
                ["Permanent Disability Paid To Date", "", "", f"${benefits.pd_total:,.2f}"]
            )
            ledger_penalties = money.penalties
            if ledger_penalties is not None and ledger_penalties.assessments:
                for assessment in ledger_penalties.assessments:
                    source = (
                        "TD period" if assessment.source == "td_period" else "PD advance"
                    )
                    rows.append(
                        [
                            f"§4650(d) {source} {assessment.ordinal} Increase",
                            f"Principal ${assessment.principal:,.2f}; operational due "
                            f"{assessment.operational_due_date:%m/%d/%y}",
                            f"Statutory due {assessment.statutory_due_date:%m/%d/%y}; "
                            f"paid {assessment.date_paid:%m/%d/%y}; "
                            f"{assessment.days_late} statutory day(s) late",
                            f"${assessment.amount:,.2f}",
                        ]
                    )
                rows.extend(
                    [
                        [
                            "§4650(d) Principal Assessed",
                            "",
                            "",
                            f"${ledger_penalties.principal_assessed:,.2f}",
                        ],
                        [
                            "§4650(d) Increase Fraction",
                            "",
                            DUE_NOTICE,
                            f"{ledger_penalties.basis.increase_fraction.normalize():f}",
                        ],
                        [
                            "§4650(d) Total Increase",
                            "",
                            DUE_NOTICE,
                            f"${ledger_penalties.total_increase:,.2f}",
                        ],
                    ]
                )
            story.append(
                _money_table(rows, [2.1 * inch, 1.9 * inch, 1.1 * inch, 1.0 * inch], self.styles)
            )
            if ledger_penalties is not None and ledger_penalties.assessments:
                story.append(
                    Paragraph(
                        f"<b>§4650(d) Penalty Authority:</b> "
                        f"{ledger_penalties.basis.authority} — {UNCONFIRMED_NOTICE}",
                        self.styles["BodyText14"],
                    )
                )
            _append_settlement_terms(story, money, self.styles, "funding")
            return story

    class FactAwareSettlementMemo(_SpecCapture, memo_module.SettlementMemo):  # type: ignore[misc,name-defined]
        """The valuation memo's money comes from the ledger, and its rows add up.

        Twenty-seven registry subtypes render through ``SettlementMemo`` — the
        valuation memo, both rating worksheets, the MSA submission, the
        conference statements, the trial briefs — and not one of them was
        fact-aware. It is the largest money-bearing template family in the
        substrate and it had never been swept, which is why the sweep that found
        it derives its matrix from the *registry* rather than from the list of
        classes already overridden. A matrix built from what is governed can
        only ever confirm what is governed.

        Three defects, all confirmed on rendered output of one settled case:

        * **Its temporary-disability paragraph was a second wage ontology.** It
          printed ``$157,467 (138 weeks @ $1141.07/week)`` beside a ledger that
          published ``tdWeeklyRate 767.59`` and ``$28,400.83`` paid — a governed
          fact contradicted on the same case. Both figures now come from the
          ledger.
        * **Its permanent-disability rate was the literal 290.** It agreed with
          the ledger on the case it was found on, by luck: $290 is the capped
          maximum for one rate vintage. On any other vintage it is simply wrong.
        * **A row of its own settlement-range table did not add up.** The
          Optimistic row's Other column and its Total came from two independent
          draws of the same range, so the columns summed to $432,073 beside a
          printed total of $427,428. Round 10's negative-net class exactly: a
          document whose arithmetic cannot be reproduced from its own page,
          except that here it contradicts itself across one row.

        Where the file actually settled, the recommended target *is* the
        settlement. A memo written before the settlement may legitimately
        propose a different number, but this corpus dates these documents into
        settled files, and a target twelve times the executed gross is not a
        valuation — it is a label an analyzer would learn as noise.
        """

        def build_story(self, doc_spec: Any) -> list[Any]:
            subtype = str(doc_spec.subtype.value)
            rating = _rating_of(self)
            if subtype not in RATING_CARRIER_SUBTYPES or rating is None:
                return list(super().build_story(doc_spec))

            title = {
                "IMPAIRMENT_RATING_WORKSHEET": "IMPAIRMENT RATING WORKSHEET",
                "PD_RATING_CALCULATION_WORKSHEET": (
                    "PERMANENT DISABILITY RATING CALCULATION WORKSHEET"
                ),
                "PD_RATING_CONVERSION": "PERMANENT DISABILITY RATING CONVERSION",
            }[subtype]
            story: list[Any] = [
                Paragraph(title, self.styles["CenterBold"]),
                Spacer(1, 0.2 * inch),
                Paragraph(
                    f"<b>Applicant:</b> {self.case.applicant.full_name}",
                    self.styles["BodyText14"],
                ),
                Paragraph(
                    f"<b>Date of Injury:</b> {rating.date_of_injury:%m/%d/%Y}",
                    self.styles["BodyText14"],
                ),
                Paragraph(
                    f"<b>Schedule:</b> {rating.schedule.edition} PDRS",
                    self.styles["BodyText14"],
                ),
                Paragraph(
                    f"<b>Occupation:</b> {rating.occupation_title} "
                    f"(group {rating.occupation_group}); "
                    f"<b>Age at injury:</b> {rating.applicant_age}",
                    self.styles["BodyText14"],
                ),
                Spacer(1, 0.15 * inch),
                self.make_hr(),
                Paragraph("RATING STRING", self.styles["SectionHeader"]),
            ]
            for line in rating.rating_string.splitlines():
                story.append(Paragraph(line, self.styles["BodyText14"]))
            story.extend(
                [
                    Spacer(1, 0.15 * inch),
                    Paragraph(
                        "Selected unapportioned permanent disability: "
                        f"{rating.final_pd_percent}%",
                        self.styles["BodyText14"],
                    ),
                ]
            )
            return story

        def _make_pd_analysis_section(self) -> list[Any]:
            story = list(super()._make_pd_analysis_section())
            money = _money_of(self)
            if money is None:
                return story
            rate = money.wages.rate.pd_weekly_rate
            for index, item in enumerate(story):
                text = getattr(item, "text", None)
                if not isinstance(text, str) or "Total PD Indemnity" not in text:
                    continue
                weeks = _MEMO_PD_WEEKS.search(text)
                if weeks is None:
                    log.warning("fact_templates.memo_pd_weeks_not_found")
                    break
                total = (Decimal(weeks.group(1)) * rate).quantize(CENTS)
                replaced = _MEMO_PD_RATE.sub(f"<b>Weekly Rate:</b> ${rate:,.2f}", text, count=1)
                replaced = _MEMO_PD_TOTAL.sub(
                    f"<b>Total PD Indemnity:</b> <b>${total:,.2f}</b>", replaced, count=1
                )
                from reportlab.platypus import Paragraph

                story[index] = Paragraph(replaced, item.style)
                self._pd_value = int(total)
                break
            return story

        def _make_other_benefits_section(self) -> list[Any]:
            money = _money_of(self)
            if money is None:
                return list(super()._make_other_benefits_section())
            from reportlab.lib.units import inch
            from reportlab.platypus import Paragraph, Spacer

            benefits = money.benefits
            weeks = sum((period.weeks for period in benefits.td_periods), Decimal(0))
            story: list[Any] = [
                Paragraph("<b>4. OTHER BENEFITS</b>", self.styles["SectionHeader"]),
                Spacer(1, 0.1 * inch),
            ]
            # ``sjdb_voucher`` is a statutory figure the substrate states, not a
            # draw, and the engine does not publish one — so it is carried
            # through rather than governed. Self-procured medical is the
            # settlement's own reimbursement where there is a settlement.
            self_procured = (
                _reimbursement_nearest_five_percent(int(money.settlement.gross_amount))
                if money.settlement is not None
                else 0
            )
            story.append(
                Paragraph(
                    f"<b>Temporary Total Disability (TTD):</b> ${benefits.td_total:,.2f} "
                    f"({weeks:g} weeks @ ${money.wages.rate.td_weekly_rate:,.2f}/week)\n"
                    f"<b>SJDB Voucher:</b> ${_SJDB_VOUCHER:,} (LC §4658.7)\n"
                    f"<b>Self-Procured Medical:</b> ${self_procured:,}",
                    self.styles["BodyText14"],
                )
            )
            self._other_benefits = _SJDB_VOUCHER + self_procured
            return story

        def _make_settlement_range_section(self) -> list[Any]:
            money = _money_of(self)
            if money is None:
                return list(super()._make_settlement_range_section())
            from reportlab.lib import colors
            from reportlab.lib.units import inch
            from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

            pd_value = int(self._pd_value)
            fmc_value = int(self._fmc_value)
            other = int(self._other_benefits)
            # One draw per column that varies, and every Total is the sum of the
            # row it sits on. The substrate drew the Optimistic row's Other and
            # its Total independently, so the row disagreed with itself.
            # Derived, not drawn. The substrate's optimistic premium was a
            # second ``random.randint(5000, 15000)`` — a draw is what let the
            # row disagree with its own total, and nothing about this figure
            # needs to be random for the document to read as one.
            optimistic_other = other + max(fmc_value // 10, 5000)
            rows = [
                ["Scenario", "PD Value", "FMC Value", "Other", "Total"],
                ["Conservative", pd_value, fmc_value // 2, other],
                ["Expected", pd_value, fmc_value, other],
                ["Optimistic", pd_value, fmc_value, optimistic_other],
            ]
            data = [rows[0]] + [
                [name, f"${a:,}", f"${b:,}", f"${c:,}", f"${a + b + c:,}"]
                for name, a, b, c in rows[1:]
            ]
            widths = [1.2 * inch, 1.2 * inch, 1.2 * inch, 1 * inch, 1.2 * inch]
            table = Table(data, colWidths=widths)
            table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, -1), 9),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                    ]
                )
            )
            story: list[Any] = [
                Paragraph("<b>6. SETTLEMENT RANGE ANALYSIS</b>", self.styles["SectionHeader"]),
                Spacer(1, 0.1 * inch),
                table,
                Spacer(1, 0.15 * inch),
            ]
            if money.settlement is not None:
                target = int(money.settlement.gross_amount)
            else:
                target = pd_value + fmc_value + other
            story.append(
                Paragraph(
                    f"<b><u>Recommended Settlement Target: ${target:,}</u></b>",
                    self.styles["BodyText14"],
                )
            )
            story.append(Spacer(1, 0.05 * inch))
            story.append(
                Paragraph(
                    f"Comparable cases with similar body parts and impairment levels have "
                    f"settled in the range of ${int(target * 0.8):,} to "
                    f"${int(target * 1.2):,} in the {self.case.venue} district.",
                    self.styles["BodyText14"],
                )
            )
            return story

    personnel_module = import_substrate("pdf_templates.employment.personnel_file")

    class FactAwarePersonnelFile(_SpecCapture, personnel_module.PersonnelFile):  # type: ignore[misc,name-defined]
        """The pay-rate history ends at the wage the manifest publishes.

        ``align_employer_wage`` already puts the published average weekly wage
        behind ``employer.hourly_rate``, which is where the hire row and the
        transfer row come from. The promotion row does not come from there: it
        is ``hourly_rate * random.uniform(1.05, 1.15)``, so it printed $32.02 an
        hour on a file publishing an average weekly wage of $1,151.33 — $28.78.

        Two things wrong with that, and the second is worse. It contradicts a
        governed fact. And it is incoherent on its own terms: the promotion
        predates the injury, so a table showing a raise *above* the rate the
        employee is currently on is describing a pay cut nobody recorded.

        The correction scales the column so its highest figure is the published
        rate and the earlier ones keep their proportions. A promotion still
        raises pay; it raises it *to* what the file says the applicant earns.
        """

        def build_story(self, doc_spec: Any) -> list[Any]:
            story = list(super().build_story(doc_spec))
            money = _money_of(self)
            if money is None:
                return story
            published = (
                Decimal(money.wages.computation.aww) / Decimal(_SUBSTRATE_WEEKLY_HOURS)
            ).quantize(CENTS)
            index = _index_of_text(story, "Position History")
            if index is None:
                log.warning("fact_templates.position_history_not_found")
                return story
            for item in story[index:]:
                if item.__class__.__name__ != "Table":
                    continue
                _rescale_hourly_column(item, published)
                return story
            log.warning("fact_templates.position_history_table_not_found")
            return story

    letter_module = import_substrate("pdf_templates.correspondence.defense_counsel_letter")
    depo_module = import_substrate("pdf_templates.discovery.deposition_transcript")
    variant_module = import_substrate("data.variant_content")

    class FactAwareMedicalStoryLetter(_SpecCapture, letter_module.DefenseCounselLetter):  # type: ignore[misc,name-defined]
        """The contention-loop letter, written by its actual actor (AJC-62).

        Rebuilds ``build_story`` (R11 permits it for letters): the substrate
        mounts every letter on a fixed defense letterhead, and an
        applicant-authored advocacy letter cannot be corrected by appending a
        paragraph. Substrate letterhead, date-line, styles and signature
        helpers are reused; the body is written from the bound assertions and
        the R14 author register — the contention's party owns the voice, not
        the file owner. Story-absent and surface-absent documents delegate to
        the exact substrate path, byte for byte.
        """

        def _story_actor(self, context: dict[str, Any]) -> str:
            actor = context.get("contention_actor_party")
            if actor in ("applicant", "defense"):
                return str(actor)
            return (
                "defense"
                if context.get("author_role") == "defense_attorney"
                else "applicant"
            )

        def _story_evaluator(self, story: DocumentMedicalStory) -> Any:
            if story.subtype == "ADVOCACY_LETTERS_PTP":
                return self.case.treating_physician
            return (
                getattr(self.case, "qme_physician", None)
                or self.case.treating_physician
            )

        def _story_addressee(
            self,
            story: DocumentMedicalStory,
            actor: str,
            firms: dict[str, Any],
        ) -> tuple[str, str]:
            """(address block, salutation) for the surface's recipient."""
            if story.contention_surface == "objection":
                # Served on opposing counsel, with the evaluator copied.
                if actor == "defense":
                    block = (
                        "Applicant's Attorney<br/>"
                        f"{firms.get('applicant', 'Counsel for Applicant')}"
                    )
                else:
                    # ``defense_attorney`` already carries its own ", Esq.".
                    block = (
                        f"{self.case.insurance.defense_attorney}<br/>"
                        f"{self.case.insurance.defense_firm}"
                    )
                return block, "Dear Counsel:"
            evaluator = self._story_evaluator(story)
            block = (
                f"{evaluator.full_name}<br/>"
                + str(evaluator.address).replace("\n", "<br/>")
            )
            return block, "Dear Doctor:"

        def _story_service_paragraph(
            self, actor: str, register: Any, surface: str
        ) -> str:
            if actor == "defense" and register is not None:
                # AJC-66 supplies the registered document register; the
                # engine supplies the case-specific content below it.
                return str(register.paragraphs[0])
            served = {
                "advocacy": (
                    "This office represents the applicant in the "
                    "above-referenced matter. This letter is served as an "
                    "advocacy letter pursuant to 8 C.C.R. section 35, and a "
                    "copy is served simultaneously on defense counsel in "
                    "accordance with the simultaneous-exchange requirement "
                    "of that section."
                ),
                "objection": (
                    "This office represents the applicant in the "
                    "above-referenced matter. The applicant hereby objects "
                    "to the medical-legal report referenced below on the "
                    "grounds set forth in this letter."
                ),
                "supplemental_request": (
                    "This office represents the applicant in the "
                    "above-referenced matter. The applicant respectfully "
                    "requests a supplemental report from the medical-legal "
                    "evaluator addressing the issues identified below, and "
                    "serves a copy of this request simultaneously on defense "
                    "counsel."
                ),
            }
            return served[surface]

        def _story_sections(
            self,
            story: DocumentMedicalStory,
            actor: str,
            theories: Any,
        ) -> list[tuple[str, list[str]]]:
            """(heading, paragraphs) per R9's frozen contention-surface map."""
            numbered = [
                _story_contention_sentence(position + 1, contention)
                for position, contention in enumerate(story.contentions)
            ]
            psych_bound = any(
                contention.psych_injury_kind is not None
                or contention.claim_type == "psych_add_on"
                for contention in story.contentions
            )
            surface = story.contention_surface
            if surface == "advocacy":
                # A letter encloses records for the evaluator; it does not
                # "review them in preparation for this evaluation" — that is
                # the report's voice, not counsel's (R14).
                if story.record_references:
                    records = (
                        "The following records from this file are enclosed "
                        "for your review:\n\n"
                        + "\n".join(
                            _story_reference_line(reference)
                            for reference in story.record_references
                        )
                    )
                else:
                    records = (
                        "The records available to date accompany this letter "
                        "and are identified in the enclosure list."
                    )
                asks = [
                    "Please state, with your reasoning, whether the claimed "
                    "condition arose out of and in the course of employment.",
                    "Please address apportionment of permanent disability "
                    "under Labor Code sections 4663 and 4664, stating the "
                    "approximate percentages and the basis for each.",
                ]
                if psych_bound:
                    psych_asks = _register_clauses(
                        PSYCH_CONTENTION_SURFACE_REGISTER, "advocacy"
                    )
                    asks.extend(psych_asks)
                    direct = next(
                        (
                            contention
                            for contention in story.contentions
                            if contention.psych_injury_kind == "direct"
                        ),
                        None,
                    )
                    if direct is not None:
                        lead = _register_clauses(
                            PSYCH_SECTION_4660_1C_REGISTER, "applicant_direct"
                        )[0]
                        exception = next(
                            (
                                row.psych_exception_analysis
                                for row in story.apportionments
                                if row.psych_exception_analysis
                                in {"violent_act", "catastrophic_injury"}
                            ),
                            None,
                        )
                        if exception is None:
                            lead = lead.split(" Alternatively,", maxsplit=1)[0]
                        else:
                            theory = exception.replace("_", "-")
                            lead = lead.replace(
                                "[the existing violent-act or catastrophic-injury theory]",
                                f"the existing {theory} theory",
                            )
                        asks.insert(0, lead)
                return [
                    ("RECORDS AND FACTS FOR REVIEW", [records]),
                    (
                        "ISSUES PRESENTED",
                        numbered
                        or ["The issues presented are set forth in the record."],
                    ),
                    ("REQUESTED OPINIONS", asks),
                ]
            prior = story.preceding_report
            cited = (
                f"the {prior.title} of {prior.doc_date.strftime('%B %d, %Y')}"
                if prior is not None
                else "the medical-legal report served in this matter"
            )
            if surface == "objection":
                grounds = (
                    _psych_defense_theory_sentences(theories)
                    if psych_bound
                    else list(_defense_theory_sentences(theories))
                )
                paragraphs = [f"This objection is directed to {cited}."]
                paragraphs.extend(numbered)
                if psych_bound:
                    objection_clauses = list(
                        _register_clauses(
                            PSYCH_CONTENTION_SURFACE_REGISTER, "objection"
                        )
                    )
                    effects = _grounded_effects(_psych_visible_text(story))
                    if effects:
                        objection_clauses[0] = objection_clauses[0].replace(
                            "[grounded consequence facts]", ", ".join(effects)
                        )
                    else:
                        objection_clauses.pop(0)
                    paragraphs.extend(objection_clauses)
                paragraphs.extend(grounds)
                basis = [
                    "The report's conclusions should be corrected or "
                    "supplemented upon the complete record. The reviewed and "
                    "missing evidence identified above must be addressed "
                    "before the report can support the findings it states.",
                ]
                heading = (
                    "OBJECTIONS TO THE "
                    f"{prior.doc_date.strftime('%B %d, %Y')} REPORT"
                    if prior is not None
                    else "OBJECTIONS TO THE REPORT"
                )
                return [
                    (heading, paragraphs),
                    ("BASIS FOR SUPPLEMENTAL OPINION", basis),
                ]
            # supplemental_request
            fresh = [
                reference
                for reference in story.record_references
                if prior is None or reference.doc_date > prior.doc_date
            ]
            if fresh:
                supplied = (
                    "The following records, newly supplied since "
                    f"{cited}, are enclosed for review:\n\n"
                    + "\n".join(
                        _story_reference_line(reference) for reference in fresh
                    )
                )
            else:
                supplied = (
                    "No additional records have been received since "
                    f"{cited}; the questions below arise from the report "
                    "itself and the records already served."
                )
            questions = numbered or [
                "1. Please state the basis for each conclusion reached in "
                "the report."
            ]
            if psych_bound:
                questions = list(
                    _register_clauses(
                        PSYCH_CONTENTION_SURFACE_REGISTER,
                        "supplemental_request",
                    )
                )
            theory_paragraphs = (
                _psych_defense_theory_sentences(theories)
                if psych_bound
                else list(_defense_theory_sentences(theories))
            )
            return [
                (
                    "REQUEST FOR SUPPLEMENTAL REPORT",
                    [
                        f"This request is directed to {cited}.",
                        supplied,
                        *theory_paragraphs,
                    ],
                ),
                ("ISSUES FOR SUPPLEMENTAL OPINION", questions),
            ]

        def build_story(self, doc_spec: Any) -> list[Any]:
            story = _medical_story_of(doc_spec)
            if story is None or story.contention_surface is None:
                return list(super().build_story(doc_spec))
            context = doc_spec.context if isinstance(doc_spec.context, dict) else {}
            actor = self._story_actor(context)
            firms = dict(context.get("medical_story_firms") or {})
            theories = context.get("defense_contest_theories") or ()
            register = (
                variant_module.letter_register(self.variant_of(doc_spec))
                if self.variant_content_enabled(doc_spec)
                else None
            )

            if actor == "defense":
                firm = self.case.insurance.defense_firm
                phone = self.case.insurance.defense_phone
                # ``defense_attorney`` already carries its own ", Esq.".
                signer = str(self.case.insurance.defense_attorney)
                signer_title = "Attorney for Defendants"
            else:
                firm = str(firms.get("applicant") or "Counsel for the Applicant")
                phone = f"(555) {random.randint(200, 999)}-{random.randint(1000, 9999)}"
                signer = firm
                signer_title = "Attorneys for Applicant"
            firm_address = (
                f"{random.randint(100, 9999)} Tower Boulevard\n"
                f"Suite {random.randint(100, 900)}\n"
                f"Los Angeles, CA 9001{random.randint(1, 9)}"
            )

            flow: list[Any] = []
            flow.extend(self.make_letterhead(firm, firm_address, phone))
            flow.append(Spacer(1, 0.3 * inch))
            flow.append(self.make_date_line("Date", doc_spec.doc_date))
            flow.append(Spacer(1, 0.2 * inch))
            flow.append(
                Paragraph("<i>Via Email and U.S. Mail</i>", self.styles["SmallItalic"])
            )
            flow.append(Spacer(1, 0.2 * inch))
            addressee, salutation = self._story_addressee(story, actor, firms)
            flow.append(Paragraph(addressee, self.styles["BodyText14"]))
            flow.append(Spacer(1, 0.2 * inch))
            re_text = (
                f"<b>Re:</b> {self.case.applicant.full_name} v. "
                f"{self.case.employer.company_name}<br/>"
                f"&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;ADJ "
                f"{self.case.injuries[0].adj_number}<br/>"
                f"&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Date of Injury: "
                f"{self.case.injuries[0].date_of_injury.strftime('%m/%d/%Y')}"
            )
            flow.append(Paragraph(re_text, self.styles["BodyText14"]))
            flow.append(Spacer(1, 0.3 * inch))
            flow.append(Paragraph(salutation, self.styles["BodyText14"]))
            flow.append(Spacer(1, 0.2 * inch))

            flow.append(
                Paragraph(
                    self._story_service_paragraph(
                        actor, register, story.contention_surface
                    ),
                    self.styles["DoubleSpaced"],
                )
            )
            flow.append(Spacer(1, 0.15 * inch))
            for heading, paragraphs in self._story_sections(story, actor, theories):
                flow.append(Paragraph(f"<b>{heading}</b>", self.styles["SectionHeader"]))
                flow.append(Spacer(1, 0.1 * inch))
                for paragraph in paragraphs:
                    flow.append(
                        Paragraph(
                            paragraph.replace("\n", "<br/>"),
                            self.styles["DoubleSpaced"],
                        )
                    )
                    flow.append(Spacer(1, 0.15 * inch))

            flow.append(Spacer(1, 0.2 * inch))
            flow.append(Paragraph("Very truly yours,", self.styles["BodyText14"]))
            flow.append(Spacer(1, 0.5 * inch))
            flow.extend(self.make_signature_block(signer, signer_title, ""))
            return flow

    class FactAwareMedicalStoryDepositionTranscript(_SpecCapture, depo_module.DepositionTranscript):  # type: ignore[misc,name-defined]
        """The QME/AME deposition, examined by its bound party (AJC-62).

        Rebuilds ``build_story`` (R11 permits it for depositions): the
        substrate hardcodes the examining attorney to the defense and its
        question pools carry no case percentages, and neither can be
        corrected by appending flowables. The substrate cover, certification,
        appearances, objection and reporter helpers are reused; the Q&A body
        is the verbatim reporter register — attorney question, objection,
        evaluator sworn answer — with every answer preserving the report's
        percentages and any reasoned revision (R14). Ordinary depositions
        (no ``qme_deposition`` surface) delegate byte for byte.
        """

        _REPORTER_NAMES = (
            "Jennifer Martinez", "Robert Chen", "Sarah Williams",
            "Michael Johnson", "Lisa Thompson", "Patricia Nguyen",
            "David Morales", "Karen O'Brien",
        )

        def _story_exchanges(
            self,
            story: DocumentMedicalStory,
            register: Any,
            theories: Any,
        ) -> list[tuple[str, str]]:
            data = self._deponent_case_data()
            exchanges: list[tuple[str, str]] = []
            if register is not None:
                for _topic, pairs, _low, _high in register.topic_pools[:1]:
                    for question, answer in pairs[:2]:
                        exchanges.append(
                            (question.format(**data), answer.format(**data))
                        )
            prior = story.preceding_report
            if prior is not None:
                exchanges.append(
                    (
                        f"Doctor, you prepared the {prior.title} dated "
                        f"{prior.doc_date.strftime('%B %d, %Y')} in this "
                        "matter, is that correct?",
                        "Yes. That is my report, and I reviewed it in "
                        "preparation for today's testimony.",
                    )
                )
            exchanges.append(
                (
                    "What records did you review in forming the opinions "
                    "stated in that report?",
                    "The records I reviewed are enumerated in the "
                    "records-review section of my report; my opinions rest "
                    "on those records together with the history and the "
                    "examination.",
                )
            )
            opinion = story.medical_opinion
            if opinion is not None:
                if opinion.aoe_coe_finding is not None:
                    finding = {
                        "industrial": (
                            "My opinion, within reasonable medical "
                            "probability, is that the condition arose out of "
                            "and in the course of employment."
                        ),
                        "nonindustrial": (
                            "My opinion, within reasonable medical "
                            "probability, is that the condition did not "
                            "arise out of and in the course of employment."
                        ),
                        "deferred": (
                            "I deferred that determination pending the "
                            "outstanding records identified in my report."
                        ),
                    }[opinion.aoe_coe_finding]
                    exchanges.append(
                        (
                            "What is your opinion on industrial causation, "
                            "Doctor?",
                            finding,
                        )
                    )
                if opinion.psych_injury_kind is not None:
                    kind_answer = (
                        "The psychiatric condition arose from the event "
                        "itself; it is a primary psychiatric injury."
                        if opinion.psych_injury_kind == "direct"
                        else "The psychiatric condition arose from the "
                        "medical effects of the physical injury; it is a "
                        "compensable consequence rather than a primary "
                        "psychiatric injury."
                    )
                    exchanges.append(
                        (
                            "Doctor, is your opinion that the psychiatric condition "
                            "arose from the event itself or from the medical "
                            "effects of the physical injury?",
                            kind_answer,
                        )
                    )
                    exchanges.append(
                        (
                            "What history supports that distinction?",
                            opinion.aoe_coe_rationale
                            or "The distinction rests on the history stated in my "
                            "examined report; I do not add an unrecorded history here.",
                        )
                    )
                    allocation = _story_actual_events_allocation(story)
                    threshold = (
                        allocation
                        or (
                            "At least 35 to 40 percent under the supported "
                            "violent-act standard."
                            if any(
                                row.psych_exception_analysis
                                in {"violent_act", "direct_exposure"}
                                for row in story.apportionments
                            )
                            else "Greater than 50 percent under the "
                            "predominant-cause standard."
                        )
                    )
                    exchanges.append(
                        (
                            "What percentage of total injury causation do you assign "
                            "to actual events of employment?",
                            threshold,
                        )
                    )
                    adoption = _story_psych_adoption_text(story)
                    if adoption is not None:
                        exchanges.append(
                            (
                                "Did you adopt counsel's characterization as your own "
                                "medical opinion?",
                                adoption,
                            )
                        )
                for row in story.apportionments:
                    part = _region_text(row.body_part)
                    basis = row.description or ", ".join(
                        kind.replace("_", " ") for kind in row.basis_kinds
                    ) or "nonindustrial factors"
                    exchanges.append(
                        (
                            f"As to the {part}, your report apportions "
                            f"{row.nonindustrial_percent} percent of the "
                            "permanent disability to nonindustrial factors, "
                            "is that correct?",
                            f"Yes. As stated in my report, "
                            f"{row.nonindustrial_percent} percent is "
                            f"apportioned to {basis} and "
                            f"{row.industrial_percent} percent is caused by "
                            "the industrial injury. That remains my opinion.",
                        )
                    )
                    if row.revised_from_percent is not None:
                        reason = row.revision_rationale or (
                            "The basis for the revision is stated in the "
                            "report itself."
                        )
                        exchanges.append(
                            (
                                "Your earlier report stated "
                                f"{row.revised_from_percent} percent for the "
                                f"{part}. Why the change, Doctor?",
                                f"{reason}",
                            )
                        )
                if opinion.event_kind == "deposition" and opinion.revision_kind is not None:
                    revised = opinion.revision_kind not in (
                        "unchanged_additional_reasoning",
                        "new_records_no_change",
                    )
                    revision_answer = (
                        (
                            "Yes, to the extent stated on the record today: "
                            + (
                                opinion.revision_rationale
                                or opinion.rationale
                                or "the revision and its basis are as I have "
                                "described them."
                            )
                        )
                        if revised
                        else (
                            "No. My opinions are unchanged; I have provided "
                            "additional reasoning under oath today."
                        )
                    )
                    exchanges.append(
                        (
                            "Has anything you have reviewed or heard today "
                            "changed the opinions stated in your report?",
                            revision_answer,
                        )
                    )
            psych_bound = bool(
                opinion is not None and opinion.psych_injury_kind is not None
            ) or any(
                contention.psych_injury_kind is not None
                or contention.claim_type == "psych_add_on"
                for contention in story.contentions
            )
            for theory in theories or ():
                question, answer = {
                    "insufficient_investigation": (
                        "Doctor, what investigation and records would be "
                        "necessary to fully evaluate the issues presented?",
                        "I identified the records I reviewed in my report, "
                        "and I would review any additional records provided "
                        "through the ordinary process.",
                    ),
                    "post_termination": (
                        "Did your report address the timing of this claim "
                        "relative to the notice of termination or layoff?",
                        "My report addresses the medical record before me; "
                        "the legal significance of that timing is for the "
                        "trier of fact.",
                    ),
                    "lack_of_substantial_medical_evidence": (
                        "Can you identify the records and reasoning "
                        "supporting the percentage stated in your report?",
                        "Yes. The basis and reasoning appear in the "
                        "apportionment discussion of my report, and I have "
                        "restated them today.",
                    ),
                }[theory]
                if psych_bound:
                    answer = " ".join(
                        _register_clauses(
                            PSYCH_DEFENSE_CONTEST_REGISTER, str(theory)
                        )
                    )
                exchanges.append((question, answer))
            exchanges.append(
                (
                    "Which parts of your answer are medical opinions, and which "
                    "predicates do you leave to the trier of fact?",
                    "The causation and apportionment conclusions are medical "
                    "opinions stated within reasonable medical probability; "
                    "whether the underlying events occurred is for the trier "
                    "of fact.",
                )
            )
            return exchanges

        def build_story(self, doc_spec: Any) -> list[Any]:
            story = _medical_story_of(doc_spec)
            if story is None or story.contention_surface != "qme_deposition":
                return list(super().build_story(doc_spec))
            context = doc_spec.context if isinstance(doc_spec.context, dict) else {}
            register = (
                variant_module.transcript_register(self.variant_of(doc_spec))
                if self.variant_content_enabled(doc_spec)
                else None
            )
            deponent_name, deponent_role = self._transcript_deponent(register)
            reporter_name = random.choice(list(self._REPORTER_NAMES))
            reporter_number = random.randint(5000, 15000)

            actor = context.get("contention_actor_party")
            firms = dict(context.get("medical_story_firms") or {})
            theories = context.get("defense_contest_theories") or ()
            if actor == "applicant":
                examiner = (
                    "COUNSEL FOR APPLICANT "
                    f"({firms.get('applicant', 'Applicant')})"
                )
            else:
                examiner = str(self.case.insurance.defense_attorney)

            flow: list[Any] = []
            flow.extend(
                self._build_cover_page(
                    doc_spec, reporter_name, reporter_number, deponent_name, deponent_role
                )
            )
            flow.extend(
                self._build_certification(doc_spec, reporter_name, reporter_number)
            )
            flow.extend(self._build_appearances(register))
            flow.append(self.make_hr())
            flow.append(Spacer(1, 0.2 * inch))
            flow.append(
                Paragraph(f"<b>EXAMINATION BY {examiner}</b>", self.styles["SectionHeader"])
            )
            flow.append(Spacer(1, 0.2 * inch))

            exchanges = self._story_exchanges(story, register, theories)
            line_number = 1
            objection_at = min(4, max(len(exchanges) - 2, 0))
            for position, (question, answer) in enumerate(exchanges):
                flow.append(
                    Paragraph(
                        f"{line_number:>3}  Q. {question}", self.styles["Transcript"]
                    )
                )
                line_number += 1
                flow.append(Spacer(1, 0.1 * inch))
                if position == objection_at:
                    objection = depo_module.generate_objection()
                    flow.append(
                        Paragraph(
                            f"{line_number:>3}  MR./MS. ATTORNEY: {objection}",
                            self.styles["Transcript"],
                        )
                    )
                    line_number += 1
                    flow.append(
                        Paragraph(
                            f"{line_number:>3}  BY {examiner}: You may answer.",
                            self.styles["Transcript"],
                        )
                    )
                    line_number += 1
                    flow.append(Spacer(1, 0.05 * inch))
                flow.append(
                    Paragraph(
                        f"{line_number:>3}  A. {answer}", self.styles["Transcript"]
                    )
                )
                line_number += 1
                flow.append(Spacer(1, 0.15 * inch))

            flow.append(Spacer(1, 0.3 * inch))
            flow.append(
                Paragraph(
                    f"{line_number:>3}  (Deposition concluded.)",
                    self.styles["Transcript"],
                )
            )
            flow.append(depo_module.PageBreak())
            flow.extend(
                self._build_final_certification(doc_spec, reporter_name, reporter_number)
            )
            return flow

    # Two families are bound from the registry rather than listed by hand,
    # because a hand-written list is how a sibling gets missed and that is the
    # defect class this whole sweep exists to close.
    #
    # The memo family is twenty-seven emittable subtypes that had no override at
    # all. The wage family already had one, and its own docstring said it served
    # "all eight wage and payment-record subtypes" — the registry routes ten
    # emittable ones. The two nobody had counted were PRIOR_CLAIMS_EDD_SDI_INFO
    # and TIMECARDS_SCHEDULES, both of which print this case's own earnings, and
    # the first of them was printing a temporary-disability rate of $848.53
    # against a ledger publishing $767.59. A claim of completeness that nothing
    # checked, live for eleven review rounds.
    registry_module = import_substrate("pdf_templates.registry")

    canonical = effective_taxonomy().subtypes

    def _family(module_path: str, template: type) -> dict[str, type]:
        """Every *canonical* subtype the registry routes to one substrate module.

        Canonical, because the registry is the substrate's list and the taxonomy
        is the engine's. Five registry keys are not classifier vocabulary — the
        engine can never emit them — and mapping one here would put a subtype in
        the fact-aware registry that no document can carry. ``test_scenario_p2``
        already refuses that, and it refused this on the first run.
        """
        return {
            subtype: template
            for subtype, entry in registry_module.TEMPLATE_REGISTRY.items()
            if entry.module_path == module_path and subtype in canonical
        }

    families = {
        **_family("pdf_templates.summaries.settlement_memo", FactAwareSettlementMemo),
        **_family("pdf_templates.employment.wage_statement", FactAwareWageStatement),
        **_family("pdf_templates.employment.personnel_file", FactAwarePersonnelFile),
    }

    return {
        **families,
        "WAGE_STATEMENTS_PRE_INJURY": FactAwareWageStatement,
        "WAGE_STATEMENTS_POST_INJURY": FactAwareWageStatement,
        "WAGE_STATEMENTS_EARNING_RECORDS": FactAwareWageStatement,
        "TD_PAYMENT_RECORD_ONGOING": FactAwareWageStatement,
        "TD_PAYMENT_RECORD_RETROACTIVE": FactAwareWageStatement,
        "PD_PAYMENT_RECORD_ADVANCE": FactAwareWageStatement,
        "PD_PAYMENT_RECORD_ONGOING": FactAwareWageStatement,
        "PD_PAYMENT_RECORD_FINAL": FactAwareWageStatement,
        "ORDER_APPROVING_SETTLEMENT": FactAwareOrderApprovingSettlement,
        "STIPULATIONS_WITH_REQUEST_FOR_AWARD": FactAwareStipulations,
        "STIPULATIONS_WITH_REQUEST_FOR_AWARD_FULL": FactAwareStipulations,
        "STIPULATIONS_WITH_REQUEST_FOR_AWARD_PARTIAL": FactAwareStipulations,
        "STIPS_WITH_REQUEST_FOR_AWARD_PACKAGE": FactAwareStipulations,
        "BENEFIT_PAYMENT_LEDGER": FactAwareBenefitPaymentLedger,
        "RESERVE_WORKSHEET": FactAwareInitialFileReview,
        "RESERVE_CHANGE_NOTICE": FactAwareReserveChangeNotice,
        "COMPROMISE_AND_RELEASE": FactAwareCompromiseAndRelease,
        "COMPROMISE_AND_RELEASE_STANDARD": FactAwareCompromiseAndRelease,
        "COMPROMISE_AND_RELEASE_PD_ONLY": FactAwareCompromiseAndRelease,
        "COMPROMISE_AND_RELEASE_MSA": FactAwareCompromiseAndRelease,
        "COMPROMISE_AND_RELEASE_DEPENDENCY": FactAwareCompromiseAndRelease,
        "COMPROMISE_AND_RELEASE_THIRD_PARTY": FactAwareCompromiseAndRelease,
        "SUBPOENAED_RECORDS": FactAwareSubpoenaedRecords,
        "SUBPOENAED_RECORDS_MEDICAL": FactAwareSubpoenaedRecords,
        "SUBPOENAED_RECORDS_EMPLOYMENT": FactAwareSubpoenaedRecords,
        "SUBPOENAED_RECORDS_OTHER": FactAwareSubpoenaedRecords,
        "CLIENT_CORRESPONDENCE_INFORMATIONAL": FactAwareClientIntake,
        "CLIENT_CORRESPONDENCE_REQUEST": FactAwareClientIntake,
        "CLIENT_STATUS_LETTERS": FactAwareClientIntake,
        "STATUS_UPDATE_INFORMATIONAL": FactAwareClientIntake,
        "ADJUSTER_LETTER": FactAwareAdjusterLetter,
        "ADJUSTER_LETTER_INFORMATIONAL": FactAwareAdjusterLetter,
        "ADJUSTER_LETTER_REQUEST": FactAwareAdjusterLetter,
        "ADJUSTER_DEMANDS_REQUESTS": FactAwareAdjusterLetter,
        "DISCHARGE_SUMMARY": FactAwareDischargeSummary,
        "MEDICAL_TREATMENT_AUTHORIZATION": FactAwareUtilizationReview,
        "MEDICAL_TREATMENT_DENIAL_UR": FactAwareUtilizationReview,
        "UTILIZATION_REVIEW_DECISION": FactAwareUtilizationReview,
        "UTILIZATION_REVIEW_DECISION_REGULAR": FactAwareUtilizationReview,
        "UTILIZATION_REVIEW_DECISION_EXPEDITED": FactAwareUtilizationReview,
        "IMR_APPLICATION_FORM": FactAwareUtilizationReview,
        "INDEPENDENT_MEDICAL_REVIEW_DECISION": FactAwareUtilizationReview,
        "OPERATIVE_HOSPITAL_RECORDS": FactAwareOperativeRecord,
        "DIAGNOSTICS_IMAGING": FactAwareDiagnosticReport,
        "QME_COMPREHENSIVE_REPORT": FactAwareNeuroQmeReport,
        "AME_COMPREHENSIVE_REPORT": FactAwareNeuroQmeReport,
        "QME_REPORT_INITIAL": FactAwareNeuroQmeReport,
        "QME_REPORT_SUPPLEMENTAL": FactAwareNeuroQmeReport,
        "SUPPLEMENTAL_QME_AME_REPORT": FactAwareNeuroQmeReport,
        "TREATING_PHYSICIAN_REPORT_PR2": FactAwareTreatingPhysicianReport,
        "TREATING_PHYSICIAN_REPORT_PR4": FactAwareTreatingPhysicianReport,
        # AJC-62 (M3, R77 step 7) — the medical-story surfaces. Every R8
        # member resolves to its exact fact-aware subclass with no fallback
        # (R8's own rule). The four raw-substrate mounts are deliberate: the
        # clinical overrides on FactAwareNeuroQmeReport /
        # FactAwareTreatingPhysicianReport fire on the feature-absent path,
        # and these subtypes were never registered before M3, so mounting the
        # story mixins over the raw substrate is what keeps a storyless case
        # byte-identical to the previous release (R1).
        "AME_REPORT": FactAwareMedicalStoryQmeReport,
        "MEDICAL_LEGAL_QME_AME_IME": FactAwareMedicalStoryQmeReport,
        "APPORTIONMENT_REPORT": FactAwareMedicalStoryQmeReport,
        "PSYCH_EVAL_REPORT_QME_AME": FactAwareMedicalStoryQmeReport,
        "TREATING_PHYSICIAN_REPORT": FactAwareMedicalStoryTreatingReport,
        "TREATING_PHYSICIAN_REPORT_FINAL": FactAwareMedicalStoryTreatingReport,
        "ADVOCACY_LETTERS_PTP": FactAwareMedicalStoryLetter,
        "ADVOCACY_LETTERS_QME": FactAwareMedicalStoryLetter,
        "ADVOCACY_LETTERS_AME": FactAwareMedicalStoryLetter,
        "ADVOCACY_LETTERS_PTP_QME_AME": FactAwareMedicalStoryLetter,
        "DEPOSITION_TRANSCRIPT": FactAwareMedicalStoryDepositionTranscript,
    }


_CACHE: dict[str, type] | None = None


def fact_aware_templates() -> dict[str, type]:
    """The registry, built once per process."""
    global _CACHE
    if _CACHE is None:
        _CACHE = build_fact_aware_templates()
    return _CACHE


__all__ = ["build_fact_aware_templates", "fact_aware_templates"]
