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
from typing import Any

import structlog

from wc_caseload_engine.case_facts import (
    IMAGING_MODALITIES,
    MODALITY_DISPLAY,
    SUBSTRATE_STATUS_PHRASES,
    CaseFacts,
)
from wc_caseload_engine.substrate import import_substrate

log = structlog.get_logger(__name__)

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


def _facts_of(template: Any) -> CaseFacts | None:
    """The ledger for the document being rendered, if the context carries one."""
    context = getattr(getattr(template, "doc_spec", None), "context", None)
    if isinstance(context, dict):
        facts = context.get("case_facts")
        if isinstance(facts, CaseFacts):
            return facts
    return getattr(template, "_wc_case_facts", None)


def _index_of(template: Any) -> int:
    context = getattr(getattr(template, "doc_spec", None), "context", None)
    if isinstance(context, dict):
        value = context.get("document_index")
        if isinstance(value, int):
            return value
    return 0


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

    class FactAwareDiagnosticReport(diagnostic_module.DiagnosticReport):  # type: ignore[misc,name-defined]
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

    class FactAwareQmeAmeReport(qme_module.QmeAmeReport):  # type: ignore[misc,name-defined]
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

    class FactAwareTreatingPhysicianReport(tpr_module.TreatingPhysicianReport):  # type: ignore[misc,name-defined]
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

    class FactAwareOperativeRecord(operative_module.OperativeRecord):  # type: ignore[misc,name-defined]
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

    class FactAwareUtilizationReview(ur_module.UtilizationReview):  # type: ignore[misc,name-defined]
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

    class FactAwareDischargeSummary(operative_module.OperativeRecord):  # type: ignore[misc,name-defined]
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

    _ = Paragraph  # imported for subclasses that grow to need it

    return {
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
