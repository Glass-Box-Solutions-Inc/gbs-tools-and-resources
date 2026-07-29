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

from wc_caseload_engine.case_facts import CaseFacts
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

        def _build_treatment_plan(self, specialty: Any, variant: Any) -> list[Any]:
            facts = _facts_of(self)
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

    _ = Paragraph  # imported for subclasses that grow to need it

    return {
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
