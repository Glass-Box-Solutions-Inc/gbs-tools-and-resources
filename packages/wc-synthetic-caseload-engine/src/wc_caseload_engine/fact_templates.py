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
from typing import Any

import structlog

from wc_caseload_engine.case_facts import (
    ADJUSTER_LETTER_TYPES,
    IMAGING_MODALITIES,
    MODALITY_DISPLAY,
    SUBSTRATE_STATUS_PHRASES,
    CaseFacts,
)
from wc_caseload_engine.money import (
    PD_ADVANCE_INTERVAL_DAYS,
    PD_ADVANCE_SCHEDULE_AUTHORITY,
    TD_PAYMENT_DUE_AUTHORITY,
    TD_PAYMENT_DUE_DAYS,
    MoneyFacts,
)
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
        # the single most consequential number on a delay file was asserted
        # rather than derivable. Wave 3 computes a penalty against this column.
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

    from reportlab.platypus import Paragraph

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

            if facts.surgery.performed and facts.surgery.cpt_code:
                elements.extend(
                    self.make_section(
                        "SURGICAL HISTORY",
                        f"The applicant underwent {facts.surgery.cpt_description} "
                        f"(CPT {facts.surgery.cpt_code}) of the "
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

    class FactAwareTreatingPhysicianReport(_SpecCapture, tpr_module.TreatingPhysicianReport):  # type: ignore[misc,name-defined]
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
                f"The applicant is status post {surgery.cpt_description} "
                f"(CPT {surgery.cpt_code}) of the {region}{dated}. Care is directed "
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
                    f"A Request for Authorization for {surgery.cpt_description} "
                    f"(CPT {surgery.cpt_code}) of the {region} was submitted and "
                    "denied on utilization review as not medically necessary. The "
                    "applicant remains symptomatic and the denial is under appeal."
                )
            else:
                outcome = (
                    f"Surgical consultation has been obtained and "
                    f"{surgery.cpt_description} (CPT {surgery.cpt_code}) of the "
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

    class FactAwareNeuroQmeReport(FactAwareQmeAmeReport):
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
            """
            facts = _facts_of(self)
            if facts is None:
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

        def _build_request_details(self, body_parts: Any) -> list[Any]:
            facts = _facts_of(self)
            if facts is None or not facts.surgery.names_a_procedure:
                return list(super()._build_request_details(body_parts))

            surgery = facts.surgery
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

    class FactAwareDischargeSummary(_SpecCapture, operative_module.OperativeRecord):  # type: ignore[misc,name-defined]
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
            story.append(
                _money_table(rows, [2.1 * inch, 1.9 * inch, 1.1 * inch, 1.0 * inch], self.styles)
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
        "OPERATIVE_HOSPITAL_RECORDS": FactAwareOperativeRecord,
        "DIAGNOSTICS_IMAGING": FactAwareDiagnosticReport,
        "QME_COMPREHENSIVE_REPORT": FactAwareNeuroQmeReport,
        "AME_COMPREHENSIVE_REPORT": FactAwareNeuroQmeReport,
        "QME_REPORT_INITIAL": FactAwareNeuroQmeReport,
        "QME_REPORT_SUPPLEMENTAL": FactAwareNeuroQmeReport,
        "SUPPLEMENTAL_QME_AME_REPORT": FactAwareNeuroQmeReport,
        "TREATING_PHYSICIAN_REPORT_PR2": FactAwareTreatingPhysicianReport,
        "TREATING_PHYSICIAN_REPORT_PR4": FactAwareTreatingPhysicianReport,
    }


_CACHE: dict[str, type] | None = None


def fact_aware_templates() -> dict[str, type]:
    """The registry, built once per process."""
    global _CACHE
    if _CACHE is None:
        _CACHE = build_fact_aware_templates()
    return _CACHE


__all__ = ["build_fact_aware_templates", "fact_aware_templates"]
