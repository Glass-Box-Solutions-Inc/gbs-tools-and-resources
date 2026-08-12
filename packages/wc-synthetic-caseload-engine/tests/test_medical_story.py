"""AJC-62 (M3) — the medical-story document surfaces (R77 step 7, mapped by R68).

The R67 surface matrix (``tests/fixtures/medical_story_surface_matrix.yaml``)
drives every gate here: seven fully explicit cases collectively covering every
governed R8 member, both contested communication surfaces, the QME/AME
deposition, and all six AJC-65 apportionment shapes. Assertions read the plan
(bindings, projections, references) and the rendered page (section orders,
registers, splits) — never the ledger's truth grades, which no surface may see.

Every guard collects as exactly one non-parametrized pytest item (R74/R75
mutation discipline): fixtures vary inside the test body, never through
``pytest.mark.parametrize``. Guards that can meet a production exception on the
mutated path assert through it rather than erroring.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import dataclasses
import re
import tempfile
from functools import cache
from pathlib import Path
from types import SimpleNamespace
from typing import Any, NamedTuple

import pytest
import yaml

from wc_caseload_engine.fact_templates import fact_aware_templates
from wc_caseload_engine.medical_assertions import (
    ApportionmentAssertion,
    Contention,
    MedicalAssertionError,
    MedicalOpinion,
)
from wc_caseload_engine.medical_story import (
    CONTENTION_SURFACE_TEMPLATE_PAIRS,
    RECORD_REFERENCE_PARENT_TYPES,
    SUPPLEMENTAL_MEDLEGAL_SURFACES,
    derive_medical_story,
)
from wc_caseload_engine.planner import build_case_plan
from wc_caseload_engine.renderer import (
    AJC66_DEPOSITION_TEMPLATE_SUBTYPES,
    AJC66_LETTER_TEMPLATE_SUBTYPES,
    ajc65_story_governance,
    ajc66_variant_content,
    render_document,
)
from wc_caseload_engine.seeds import parse_caseload_spec
from wc_caseload_engine.taxonomy import effective_taxonomy

_FIXTURE_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "medical_story_surface_matrix.yaml"
)

_CASE_IDS = (
    "surface-initial-medlegal",
    "surface-psych-medlegal",
    "surface-supplemental",
    "surface-ptp-interim",
    "surface-ptp-final",
    "surface-advocacy",
    "surface-contention-loop",
)

#: R8 member -> the exact engine-owned subclass that must serve it. The four
#: raw-substrate mounts and the two-mount mixin design are R1's requirement,
#: not an implementation accident: subtypes first registered by M3 must
#: delegate to the unmodified substrate on the story-absent path.
_EXPECTED_SUBCLASSES = {
    "QME_REPORT_INITIAL": "FactAwareNeuroQmeReport",
    "QME_COMPREHENSIVE_REPORT": "FactAwareNeuroQmeReport",
    "AME_COMPREHENSIVE_REPORT": "FactAwareNeuroQmeReport",
    "QME_REPORT_SUPPLEMENTAL": "FactAwareNeuroQmeReport",
    "SUPPLEMENTAL_QME_AME_REPORT": "FactAwareNeuroQmeReport",
    "AME_REPORT": "FactAwareMedicalStoryQmeReport",
    "MEDICAL_LEGAL_QME_AME_IME": "FactAwareMedicalStoryQmeReport",
    "APPORTIONMENT_REPORT": "FactAwareMedicalStoryQmeReport",
    "PSYCH_EVAL_REPORT_QME_AME": "FactAwareMedicalStoryQmeReport",
    "TREATING_PHYSICIAN_REPORT_PR2": "FactAwareTreatingPhysicianReport",
    "TREATING_PHYSICIAN_REPORT_PR4": "FactAwareTreatingPhysicianReport",
    "TREATING_PHYSICIAN_REPORT": "FactAwareMedicalStoryTreatingReport",
    "TREATING_PHYSICIAN_REPORT_FINAL": "FactAwareMedicalStoryTreatingReport",
    "ADVOCACY_LETTERS_PTP": "FactAwareMedicalStoryLetter",
    "ADVOCACY_LETTERS_QME": "FactAwareMedicalStoryLetter",
    "ADVOCACY_LETTERS_AME": "FactAwareMedicalStoryLetter",
    "ADVOCACY_LETTERS_PTP_QME_AME": "FactAwareMedicalStoryLetter",
    "DEPOSITION_TRANSCRIPT": "FactAwareMedicalStoryDepositionTranscript",
}


class _Rendered(NamedTuple):
    text: str
    template: str
    fallback: str | None


def _fixture_payload() -> dict[str, Any]:
    return yaml.safe_load(_FIXTURE_PATH.read_text(encoding="utf-8"))


@cache
def _case(case_id: str, perspective: str = "applicant") -> tuple[Any, Any]:
    """(seed, plan) for one fixture case, optionally re-read as a defense file."""
    payload = _fixture_payload()
    entry = next(c for c in payload["cases"] if c["case_id"] == case_id)
    if perspective != "applicant":
        entry["perspective"] = perspective
    spec = parse_caseload_spec(payload)
    seed = next(c for c in spec.cases if c.case_id == case_id)
    return seed, build_case_plan(seed)


def _governed(case_id: str, perspective: str = "applicant"):
    _seed, plan = _case(case_id, perspective)
    assert plan.medical_story is not None, f"{case_id} derived no medical story"
    for document in plan.documents:
        story = plan.medical_story.by_document_index.get(document.index)
        if story is not None:
            yield document, story


def _bound(case_id: str, opinion_id: str):
    """The report realization bound to *opinion_id* (never a communication)."""
    for document, story in _governed(case_id):
        if (
            story.medical_opinion is not None
            and story.medical_opinion.id == opinion_id
            and story.contention_surface is None
        ):
            return document, story
    raise AssertionError(f"{case_id} has no report realization bound to {opinion_id}")


@cache
def _render_root() -> Path:
    return Path(tempfile.mkdtemp(prefix="wcce-medical-story-"))


def _render(seed: Any, plan: Any, document: Any, story: Any, stem: str) -> _Rendered:
    fitz = pytest.importorskip("fitz")
    path = _render_root() / f"{stem}.pdf"
    result = render_document(
        seed=seed,
        cast=plan.cast,
        subtype=document.subtype,
        doc_date=document.doc_date,
        doc_format="pdf",
        index=document.index,
        out_path=path,
        title=document.title,
        author_role=document.author_role,
        recipient_role=document.recipient_role,
        content_flags=document.content_flags,
        case_facts=plan.case_facts,
        money_facts=plan.money_facts,
        template_subtype=document.template_subtype,
        medical_story=story,
        contention_actor_party=document.contention_actor_party,
        defense_contest_theories=document.defense_contest_theories,
    )
    with fitz.open(path) as pdf:
        text = "\n".join(page.get_text() for page in pdf)
    return _Rendered(text=text, template=result.template, fallback=result.fallback)


@cache
def _rendered(case_id: str, index: int, perspective: str = "applicant") -> _Rendered:
    """Render one governed planned document exactly as ``generate_case`` would."""
    seed, plan = _case(case_id, perspective)
    document = next(d for d in plan.documents if d.index == index)
    story = (
        plan.medical_story.by_document_index.get(index)
        if plan.medical_story is not None
        else None
    )
    return _render(seed, plan, document, story, f"{perspective}-{case_id}-{index}")


def _flat(text: str) -> str:
    """Whitespace-normalized page text: PDF extraction wraps lines mid-phrase,
    so every multi-word phrase must be searched with wraps collapsed."""
    return re.sub(r"\s+", " ", text)


def _assert_ordered(text: str, *markers: str) -> None:
    flattened = _flat(text)
    positions = []
    for marker in markers:
        position = flattened.find(_flat(marker))
        assert position >= 0, f"missing section {marker!r}"
        positions.append(position)
    assert positions == sorted(positions), (
        f"section order violated: {list(zip(markers, positions, strict=True))}"
    )


def _without_page_furniture(text: str) -> str:
    kept = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped in {
            "GBS Generated",
            "CONFIDENTIAL — Workers' Compensation Medical/Legal Record",
        }:
            continue
        if re.fullmatch(r"Page \d+", stripped):
            continue
        kept.append(line)
    return "\n".join(kept)


def test_contention_template_subtypes_keep_canonical_manifest_carriers_and_provenance():
    """R2 — canonical subtype stays the manifest carrier; the substrate-only
    dispatch key rides ``template_subtype`` and resolves the registered
    substrate class/variant for provenance. The frozen carrier pairs are
    asserted against the *planned* documents, so a swapped pair (m20-2's
    mutation) reddens here rather than surviving as a constant nobody reads."""
    expected = {
        "objection": ("ADVOCACY_LETTERS_PTP_QME_AME", "OBJECTION_TO_QME_AME_REPORT"),
        "supplemental_request": (
            "ADVOCACY_LETTERS_PTP_QME_AME",
            "REQUEST_SUPPLEMENTAL_QME_AME_REPORT",
        ),
        "qme_deposition": ("DEPOSITION_TRANSCRIPT", "DEPOSITION_TRANSCRIPT_QME_AME"),
    }
    assert dict(CONTENTION_SURFACE_TEMPLATE_PAIRS) == expected
    taxonomy = effective_taxonomy()
    seen: set[str] = set()
    try:
        for document, story in _governed("surface-contention-loop"):
            surface = story.contention_surface
            if surface not in expected:
                continue
            canonical, template_subtype = expected[surface]
            assert document.subtype == canonical
            assert document.template_subtype == template_subtype
            assert story.template_subtype == template_subtype
            assert taxonomy.is_canonical(document.subtype)
            assert not taxonomy.is_canonical(template_subtype)
            rendered = _rendered("surface-contention-loop", document.index)
            assert not rendered.fallback
            # Provenance records the substrate class the dispatch key resolves
            # to — the manifest never presents an engine subclass as a
            # fallback, and never leaks the internal key as a subtype.
            base = {
                "objection": "DefenseCounselLetter",
                "supplemental_request": "DefenseCounselLetter",
                "qme_deposition": "DepositionTranscript",
            }[surface]
            assert rendered.template.startswith(base)
            seen.add(surface)
    except MedicalAssertionError as exc:
        pytest.fail(f"carrier verification raised instead of binding: {exc}")
    assert seen == set(expected)


def test_every_governed_surface_resolves_to_its_exact_fact_aware_subclass_without_fallback():
    """R8 — every governed member maps to its exact fact-aware subclass; no
    member is missing, none reaches the generic fallback, and every governed
    rendered surface reports a clean (non-fallback) dispatch."""
    registry = fact_aware_templates()
    for subtype, class_name in _EXPECTED_SUBCLASSES.items():
        template = registry.get(subtype)
        assert template is not None, f"{subtype} has no fact-aware registration"
        assert template.__name__ == class_name, (
            f"{subtype} resolved to {template.__name__}, expected {class_name}"
        )
    rendered_count = 0
    for case_id in _CASE_IDS:
        for document, story in _governed(case_id):
            if story.medical_opinion is None and story.contention_surface is None:
                continue
            rendered = _rendered(case_id, document.index)
            assert not rendered.fallback, (
                f"{case_id}[{document.index}] {document.subtype} fell back: "
                f"{rendered.fallback}"
            )
            rendered_count += 1
    assert rendered_count >= 24


def test_initial_medlegal_sections_follow_the_frozen_order():
    """R9 — the initial med-legal row: PMH and the record review lead the
    body, and the causation/apportionment discussion sits between the
    impairment rating and future medical."""
    checked = 0
    for case_id, opinion_id in (
        ("surface-initial-medlegal", "opn-01"),
        ("surface-initial-medlegal", "opn-02"),
        ("surface-initial-medlegal", "opn-03"),
        ("surface-initial-medlegal", "opn-04"),
        ("surface-advocacy", "opn-02"),
        ("surface-advocacy", "opn-03"),
    ):
        document, _story = _bound(case_id, opinion_id)
        text = _rendered(case_id, document.index).text
        _assert_ordered(
            text,
            "HISTORY OF PRESENT INJURY",
            "PAST MEDICAL HISTORY",
            "REVIEW OF MEDICAL RECORDS",
            "CHIEF COMPLAINTS",
            "PHYSICAL EXAMINATION FINDINGS",
            "IMPAIRMENT RATING",
            "CAUSATION AND APPORTIONMENT",
            "FUTURE MEDICAL TREATMENT RECOMMENDATIONS",
            "CONCLUSIONS AND MEDICAL-LEGAL OPINIONS",
        )
        checked += 1
    assert checked == 6


def test_psych_medlegal_sections_follow_the_frozen_order():
    """R81 — the psych med-legal order: categorized record review, the two
    history registers, diagnostic impression, causation, §3208.3, §4660.1(c),
    impairment, then psychiatric apportionment."""
    document, story = _bound("surface-psych-medlegal", "opn-01")
    assert document.subtype == "PSYCH_EVAL_REPORT_QME_AME"
    assert story.medical_opinion is not None
    assert story.medical_opinion.psych_injury_kind == "direct"
    text = _rendered("surface-psych-medlegal", document.index).text
    _assert_ordered(
        text,
        "HISTORY OF PRESENT INJURY",
        "REVIEW OF RECORDS",
        "PAST MEDICAL AND SURGICAL HISTORY",
        "PAST PSYCHIATRIC HISTORY",
        "CHIEF COMPLAINTS",
        "PHYSICAL EXAMINATION FINDINGS",
        "DIAGNOSTIC IMPRESSION",
        "PSYCHIATRIC INJURY CAUSATION",
        "LABOR CODE §3208.3 ANALYSIS",
        "LABOR CODE §4660.1(c) ANALYSIS",
        "IMPAIRMENT RATING",
        "PSYCHIATRIC APPORTIONMENT",
        "FUTURE MEDICAL TREATMENT RECOMMENDATIONS",
    )
    # The psych row replaces the generic register, it does not add beside it
    # ("PAST MEDICAL HISTORY" is not a substring of the psych heading).
    assert "REVIEW OF MEDICAL RECORDS" not in text
    assert "PAST MEDICAL HISTORY" not in text


def test_ptp_sections_follow_the_frozen_order():
    """R9 — the treating register: assessment, then the physician's own
    causation conclusion, then the plan; the apportionment statement exists
    only on the P&S surfaces, immediately after the impairment rating."""
    for opinion_id in ("opn-01", "opn-02"):
        document, _story = _bound("surface-ptp-interim", opinion_id)
        text = _rendered("surface-ptp-interim", document.index).text
        _assert_ordered(text, "ASSESSMENT", "INDUSTRIAL CAUSATION", "TREATMENT PLAN")
        assert "IMPAIRMENT RATING" not in text
        assert "APPORTIONMENT OF PERMANENT DISABILITY" not in text
    for opinion_id in ("opn-01", "opn-02"):
        document, _story = _bound("surface-ptp-final", opinion_id)
        text = _rendered("surface-ptp-final", document.index).text
        _assert_ordered(
            text,
            "ASSESSMENT",
            "INDUSTRIAL CAUSATION",
            "TREATMENT PLAN",
            "IMPAIRMENT RATING",
            "APPORTIONMENT OF PERMANENT DISABILITY",
            "FUTURE MEDICAL CARE",
        )


def test_contention_surface_sections_follow_the_frozen_order():
    """R9 — the four contention-surface skeletons, one frozen order each."""
    checked = 0
    for case_id in ("surface-advocacy", "surface-contention-loop"):
        for document, story in _governed(case_id):
            surface = story.contention_surface
            if surface is None:
                continue
            text = _rendered(case_id, document.index).text
            if surface == "advocacy":
                _assert_ordered(
                    text,
                    "RECORDS AND FACTS FOR REVIEW",
                    "ISSUES PRESENTED",
                    "REQUESTED OPINIONS",
                )
            elif surface == "objection":
                _assert_ordered(
                    text,
                    "OBJECTIONS TO THE",
                    "BASIS FOR SUPPLEMENTAL OPINION",
                )
            elif surface == "supplemental_request":
                _assert_ordered(
                    text,
                    "REQUEST FOR SUPPLEMENTAL REPORT",
                    "ISSUES FOR SUPPLEMENTAL OPINION",
                )
            else:
                assert surface == "qme_deposition"
                _assert_ordered(
                    text,
                    "CERTIFICATION",
                    "APPEARANCES",
                    "EXAMINATION BY",
                    "(Deposition concluded.)",
                    "CERTIFICATE OF REPORTER",
                )
            checked += 1
    assert checked == 7


def test_every_story_record_reference_names_an_earlier_planned_document():
    """R10 — every reference resolves to a real, earlier planned document of a
    medical parent type, field for field; a supplemental's references are the
    delta strictly after the report it responds to."""
    taxonomy = effective_taxonomy()
    total_references = 0
    for case_id in _CASE_IDS:
        _seed, plan = _case(case_id)
        by_index = {document.index: document for document in plan.documents}
        for document, story in _governed(case_id):
            references = [*story.record_references]
            if story.preceding_report is not None:
                references.append(story.preceding_report)
            for reference in references:
                planned = by_index.get(reference.document_index)
                assert planned is not None, (
                    f"{case_id}[{document.index}] cites document index "
                    f"{reference.document_index}, which is not in the plan"
                )
                assert planned.subtype == reference.subtype
                assert planned.title == reference.title
                assert planned.doc_date == reference.doc_date
                assert reference.document_index != document.index
                assert reference.doc_date < document.doc_date
                assert taxonomy.parent_of(reference.subtype) in (
                    RECORD_REFERENCE_PARENT_TYPES
                )
            if (
                document.subtype in SUPPLEMENTAL_MEDLEGAL_SURFACES
                and story.medical_opinion is not None
            ):
                assert story.preceding_report is not None
                for reference in story.record_references:
                    assert reference.doc_date > story.preceding_report.doc_date
            total_references += len(references)
    assert total_references > 40


def test_supplemental_reports_contain_only_delta_history_records_and_issues():
    """R9 — the supplemental delta form: questions presented and delta records
    only. No fresh HPI, no fresh complaints, no fresh examination — the scope
    section says so — and an empty delta window is stated, never padded."""
    checked = 0
    for case_id in ("surface-supplemental", "surface-contention-loop"):
        for document, story in _governed(case_id):
            if (
                document.subtype not in SUPPLEMENTAL_MEDLEGAL_SURFACES
                or story.medical_opinion is None
            ):
                continue
            text = _flat(_rendered(case_id, document.index).text)
            assert "QUESTIONS PRESENTED AND NEW INFORMATION" in text
            assert "RECORDS REVIEWED SINCE PRIOR REPORT" in text
            assert "SCOPE OF SUPPLEMENTAL REVIEW" in text
            assert "No new examination was performed" in text
            assert "HISTORY OF PRESENT INJURY" not in text
            assert "CHIEF COMPLAINTS" not in text
            assert "PHYSICAL EXAMINATION FINDINGS" not in text
            assert story.preceding_report is not None
            prior = story.preceding_report
            assert f"of {prior.doc_date.strftime('%B %d, %Y')}" in text
            for reference in story.record_references:
                assert reference.doc_date > prior.doc_date
            if not story.record_references:
                assert "No qualifying medical records were received for review." in text
            checked += 1
    assert checked == 3


def test_every_surface_uses_bound_author_role_not_file_perspective():
    """R14 — the bound actor owns the voice under BOTH file perspectives: the
    planner's author_role is the actor's, an applicant letter keeps applicant
    letterhead and signature inside a defense-owned file, and the deposition
    examiner is the bound examining party, not the file owner."""
    checked = 0
    for case_id in ("surface-advocacy", "surface-contention-loop"):
        for perspective in ("applicant", "defense"):
            _seed, plan = _case(case_id, perspective)
            applicant_firm = plan.cast.applicant_firm
            defense_firm = plan.cast.defense_firm
            defense_attorney = str(plan.cast.case.insurance.defense_attorney)
            surfaces_seen: set[str] = set()
            for document, story in _governed(case_id, perspective):
                surface = story.contention_surface
                if surface is None:
                    continue
                actor = document.contention_actor_party
                expected_role = (
                    "court_reporter"
                    if surface == "qme_deposition"
                    else f"{actor}_attorney"
                )
                assert document.author_role == expected_role, (
                    f"{case_id}/{perspective}[{document.index}] author_role "
                    f"{document.author_role!r} != bound {expected_role!r}"
                )
                text = _flat(_rendered(case_id, document.index, perspective).text)
                if surface == "qme_deposition":
                    assert f"EXAMINATION BY {defense_attorney}" in text
                elif actor == "applicant":
                    assert applicant_firm in text
                    assert "Attorneys for Applicant" in text
                    assert "Attorney for Defendants" not in text
                else:
                    assert defense_firm in text
                    assert "Attorney for Defendants" in text
                    assert "Attorneys for Applicant" not in text
                surfaces_seen.add(surface)
                checked += 1
            assert surfaces_seen, f"{case_id}/{perspective} emitted no surfaces"
    assert checked >= 12


def test_ajc65_projection_is_coherent_for_every_apportionment_shape():
    """R12/AJC-65 — the frozen opinion-state -> context mapping, shape by
    shape, lossless: every stated percentage is the ledger's own, prose-only
    shapes carry no scalar key, and the page shows exactly the projected
    posture. m20-27's heterogeneous block must stay prose-only."""
    # -- none (no_nonindustrial_share): register none, pct 0, reasoned opinion.
    document, story = _bound("surface-initial-medlegal", "opn-01")
    governance = ajc65_story_governance(story)
    block = governance["apportionment"]
    assert block["register"] == "none"
    assert block["nonindustrial_pct"] == 0
    assert "entire permanent disability is caused by the industrial" in block["opinion"]
    assert governance["causation"]["attribution"] == "entirely"
    text = _flat(_rendered("surface-initial-medlegal", document.index).text)
    assert "Apportionment — LC §4663" not in text
    assert "asymptomatic and non-disabling before the injury" in text

    # -- single row: an exact determined split, stated everywhere.
    document, story = _bound("surface-initial-medlegal", "opn-02")
    block = ajc65_story_governance(story)["apportionment"]
    assert block["register"] == "apportioned"
    assert block["nonindustrial_pct"] == 25
    assert "25 percent" in block["opinion"]
    text = _flat(_rendered("surface-initial-medlegal", document.index).text)
    assert "Apportionment — LC §4663" in text
    assert "25% of the current permanent disability" in text
    assert "75%" in text

    # -- equal plural: one common scalar plus a per-body-part sentence each.
    document, story = _bound("surface-supplemental", "opn-01")
    block = ajc65_story_governance(story)["apportionment"]
    assert block["register"] == "apportioned"
    assert block["nonindustrial_pct"] == 20
    assert "As to the lumbar spine, 20 percent" in block["opinion"]
    assert "As to the shoulder, 20 percent" in block["opinion"]
    text = _flat(_rendered("surface-supplemental", document.index).text)
    assert "Apportionment — LC §4663" in text
    assert "20% of the current permanent disability" in text

    # -- heterogeneous plural: PROSE-ONLY. No scalar key exists, no scalar
    #    block renders, and every row's own split appears with a table.
    document, story = _bound("surface-initial-medlegal", "opn-03")
    block = ajc65_story_governance(story)["apportionment"]
    assert set(block) == {"opinion"}, (
        "heterogeneous rows must project prose alone — a scalar here states a "
        f"split the evaluator never made: {sorted(block)}"
    )
    assert "As to the lumbar spine, 30 percent" in block["opinion"]
    assert "As to the shoulder, 10 percent" in block["opinion"]
    text = _flat(_rendered("surface-initial-medlegal", document.index).text)
    assert "Apportionment — LC §4663" not in text
    _assert_ordered(text, "Body Part", "Industrial %", "Nonindustrial %", "Basis")
    for cell in ("70%", "30%", "90%", "10%"):
        assert cell in text

    # -- unable to approximate: prose-only, the evaluator's own words.
    document, story = _bound("surface-initial-medlegal", "opn-04")
    block = ajc65_story_governance(story)["apportionment"]
    assert set(block) == {"opinion"}
    assert "cannot be approximated" in block["opinion"]
    text = _flat(_rendered("surface-initial-medlegal", document.index).text)
    assert "Apportionment — LC §4663" not in text
    assert "cannot be approximated" in text

    # -- deferred: the register alone; no percentage may exist anywhere.
    document, story = _bound("surface-psych-medlegal", "opn-01")
    governance = ajc65_story_governance(story)
    assert governance["apportionment"] == {"register": "deferred"}
    text = _flat(_rendered("surface-psych-medlegal", document.index).text)
    assert "Apportionment is deferred" in text
    assert "No apportionment percentage is determined at this time" in text

    # -- history-only: no bound opinion, no governance at all.
    for _document, unbound in _governed("surface-initial-medlegal"):
        if unbound.medical_opinion is None and unbound.contention_surface is None:
            assert ajc65_story_governance(unbound) == {}
            break
    else:  # pragma: no cover - fixture guarantees an unbound report exists
        pytest.fail("no history-only governed report in the fixture")


def test_ajc65_governance_consumes_and_discards_legacy_draws():
    """AJC-65's stream contract: a governed document still consumes the
    substrate's legacy apportionment draws, so everything drawn after them is
    byte-identical between the governed render and a history-only render of
    the same document. Skipping the draws instead of discarding them would
    shift every later section."""
    seed, plan = _case("surface-initial-medlegal")
    document, story = _bound("surface-initial-medlegal", "opn-02")
    stripped = story.model_copy(
        update={"medical_opinion": None, "apportionments": ()}
    )
    governed = _flat(
        _without_page_furniture(_render(seed, plan, document, story, "draws-governed").text)
    )
    history_only = _flat(
        _without_page_furniture(
            _render(seed, plan, document, stripped, "draws-history-only").text
        )
    )

    # Non-vacuity: the two renders really did diverge where governance lives.
    assert "The multilevel degenerative disc disease predated the injury" in governed
    assert (
        "The multilevel degenerative disc disease predated the injury"
        not in history_only
    )

    def _after_apportionment(text: str) -> str:
        start = text.index("FUTURE MEDICAL TREATMENT RECOMMENDATIONS")
        end = text.index("CONCLUSIONS AND MEDICAL-LEGAL OPINIONS")
        return text[start:end]

    assert _after_apportionment(governed) == _after_apportionment(history_only), (
        "the sections drawn after the apportionment seam diverged — a governed "
        "document stopped consuming the substrate's legacy draws"
    )


def test_ajc66_activates_only_the_bound_letter_or_deposition_family():
    """R13/AJC-66 — the variant-content switch is namespaced to exactly the
    bound family ({'letter': True} or {'deposition_transcript': True}), never
    the global True, and the activated register actually reaches the page."""
    for key in sorted(AJC66_LETTER_TEMPLATE_SUBTYPES):
        switch = ajc66_variant_content(key)
        assert switch == {"letter": True}, f"{key} -> {switch!r}"
        assert switch is not True
    for key in sorted(AJC66_DEPOSITION_TEMPLATE_SUBTYPES):
        switch = ajc66_variant_content(key)
        assert switch == {"deposition_transcript": True}, f"{key} -> {switch!r}"

    # The objection letter renders its registered service paragraph (register
    # prose, absent from the engine's own applicant paragraphs) and the
    # deposition opens with the register's qualification examination.
    for document, story in _governed("surface-contention-loop"):
        if story.contention_surface == "objection":
            text = _flat(_rendered("surface-contention-loop", document.index).text)
            assert "to its admission into evidence" in text
        if story.contention_surface == "qme_deposition":
            text = _flat(_rendered("surface-contention-loop", document.index).text)
            assert "state your full name and business address" in text
            assert "What is your medical specialty?" in text


def test_ajc66_absent_false_and_empty_contexts_are_inert():
    """R13 — absent, ``None``, ``False``, ``{}`` and a block naming only some
    other family all read as off, on the engine's own registered classes; a
    story-absent document renders the substrate default with no register."""
    assert ajc66_variant_content(None) is None
    assert ajc66_variant_content("QME_REPORT_INITIAL") is None
    assert ajc66_variant_content("TREATING_PHYSICIAN_REPORT_PR4") is None

    _seed, plan = _case("surface-advocacy")
    letter_class = fact_aware_templates()["ADVOCACY_LETTERS_PTP"]
    template = letter_class(plan.cast.case)
    for context in (
        None,
        {},
        {"variant_content": None},
        {"variant_content": False},
        {"variant_content": {}},
        {"variant_content": {"deposition_transcript": True}},
        {"variant_content": {"letter": False}},
    ):
        spec = SimpleNamespace(context=context)
        assert template.variant_content_enabled(spec) is False, f"{context!r}"
    on = SimpleNamespace(context={"variant_content": {"letter": True}})
    assert template.variant_content_enabled(on) is True

    # Story-absent render of a governed letter subtype: the substrate default,
    # with neither the engine's story sections nor any register prose.
    seed, plan = _case("surface-advocacy")
    document = next(
        d for d, s in _governed("surface-advocacy") if s.contention_surface == "advocacy"
    )
    absent = _flat(_render(seed, plan, document, None, "ajc66-story-absent").text)
    assert "RECORDS AND FACTS FOR REVIEW" not in absent
    assert "being served simultaneously on opposing counsel" not in absent


def test_governed_medical_facts_are_identical_across_every_bound_surface():
    """R4 — one world, every surface: the projected history section is
    byte-identical across every report of a case, and a bound opinion's split
    is stated with the same numbers on its report and at its deposition."""
    # (a) The PMH section, word for word, across all four initial reports.
    sections = set()
    for opinion_id in ("opn-01", "opn-02", "opn-03", "opn-04"):
        document, _story = _bound("surface-initial-medlegal", opinion_id)
        text = _flat(
            _without_page_furniture(
                _rendered("surface-initial-medlegal", document.index).text
            )
        )
        start = text.index("PAST MEDICAL HISTORY")
        end = text.index("REVIEW OF MEDICAL RECORDS")
        sections.add(text[start:end])
    assert len(sections) == 1, "the four initial reports told different histories"
    history = next(iter(sections))
    assert "prior permanent disability award of 12 percent" in history
    assert "31-year-old female" in history

    # (b) opn-01's split: identical numbers on the report and under oath.
    document, _story = _bound("surface-contention-loop", "opn-01")
    report = _flat(_rendered("surface-contention-loop", document.index).text)
    deposition = next(
        _flat(_rendered("surface-contention-loop", d.index).text)
        for d, s in _governed("surface-contention-loop")
        if s.contention_surface == "qme_deposition"
    )
    for text in (report, deposition):
        assert "30 percent" in text
        assert "70 percent" in text
        assert "preexisting degenerative pathology" in text


def test_medical_story_projection_uses_literal_allowlists_and_never_model_dump():
    """R4/m20-3 — the projection copies fields through literal allowlists. The
    ledger models really do carry the truth-only ``quality`` field, and the
    projection executed with ``model_dump`` spies planted never touches one —
    so no future field (grade, note, digest) can leak by default."""
    seed, plan = _case("surface-contention-loop")
    assert plan.medical_assertions is not None
    # The planted truth-only field exists on every upstream ledger model.
    assert all(hasattr(o, "quality") for o in plan.medical_assertions.medical_opinions)
    assert all(hasattr(c, "quality") for c in plan.medical_assertions.contentions)

    def _spy(name: str):
        def fail(self: Any, *args: Any, **kwargs: Any) -> Any:
            raise AssertionError(
                f"{name} was serialized wholesale during the story projection; "
                "R4 requires a literal field allowlist, never model_dump"
            )

        return fail

    with pytest.MonkeyPatch.context() as patcher:
        for model in (MedicalOpinion, Contention, ApportionmentAssertion):
            patcher.setattr(model, "model_dump", _spy(model.__name__))
            patcher.setattr(model, "model_dump_json", _spy(model.__name__))
        story_plan = derive_medical_story(
            seed, plan.medical_history, plan.medical_assertions, plan.documents
        )
    assert story_plan is not None and story_plan.by_document_index

    for story in story_plan.by_document_index.values():
        projected = [story.medical_opinion, *story.contentions, *story.apportionments]
        for item in projected:
            if item is None:
                continue
            assert "quality" not in type(item).model_fields, type(item).__name__
            assert not hasattr(item, "quality"), type(item).__name__


def test_unbound_or_missing_opinion_id_fails_instead_of_guessing_by_date():
    """R5/m20-4 — a dangling opinion binding is a failure, never repaired by
    nearest report date, report ordinal, subtype coincidence or collection
    order."""
    seed, plan = _case("surface-contention-loop")
    documents = list(plan.documents)
    position = next(
        i for i, d in enumerate(documents) if d.medical_opinion_id is not None
    )
    documents[position] = dataclasses.replace(
        documents[position], medical_opinion_id="opn-99"
    )
    message = None
    try:
        derive_medical_story(seed, plan.medical_history, plan.medical_assertions, documents)
    except MedicalAssertionError as exc:
        message = str(exc)
    assert message is not None, (
        "a dangling opinion binding derived a story instead of failing (R5)"
    )
    assert "'opn-99'" in message
    assert "does not exist in the completed ledger" in message
    assert "fails instead of guessing by date (R5)" in message
