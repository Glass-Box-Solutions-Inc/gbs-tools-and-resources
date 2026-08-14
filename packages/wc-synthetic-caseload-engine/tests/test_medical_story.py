"""AJC-62 (M3) — medical-story document surfaces (R77 steps 7-8, R68).

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
import random
import re
import tempfile
from functools import cache
from pathlib import Path
from types import SimpleNamespace
from typing import Any, NamedTuple

import pytest
import yaml

from wc_caseload_engine import medical_assertions as medical_assertions_module
from wc_caseload_engine import medical_story as medical_story_module
from wc_caseload_engine import renderer as renderer_module
from wc_caseload_engine.doctrine import DOCTRINE_CONTENT
from wc_caseload_engine.fact_templates import (
    PSYCH_CONTENTION_SURFACE_REGISTER,
    PSYCH_DEFENSE_CONTEST_REGISTER,
    PSYCH_HISTORY_REGISTER,
    fact_aware_templates,
)
from wc_caseload_engine.medical_assertions import (
    ApportionmentAssertion,
    Contention,
    MedicalAssertionError,
    MedicalOpinion,
)
from wc_caseload_engine.medical_history import (
    ApplicantDemographics,
    MedicalCondition,
    PriorAward,
    PriorClaim,
)
from wc_caseload_engine.medical_story import (
    ADVOCACY_LETTER_SURFACES,
    CONTENTION_SURFACE_TEMPLATE_PAIRS,
    INITIAL_MEDLEGAL_SURFACES,
    PSYCH_MEDLEGAL_SURFACES,
    PTP_APPORTIONMENT_SURFACES,
    PTP_CAUSATION_SURFACES,
    RECORD_REFERENCE_PARENT_TYPES,
    SUPPLEMENTAL_MEDLEGAL_SURFACES,
    StoryContention,
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
from wc_caseload_engine.seeds import parse_case_seed, parse_caseload_spec
from wc_caseload_engine.taxonomy import effective_taxonomy

_FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "medical_story_surface_matrix.yaml"
_PSYCH_TRIAD_PATH = Path(__file__).resolve().parent / "fixtures" / "medical_story_psych_triad.yaml"
_IMR_MATRIX_PATH = Path(__file__).resolve().parent / "fixtures" / "medical_story_imr_matrix.yaml"

_CASE_IDS = (
    "surface-initial-medlegal",
    "surface-psych-medlegal",
    "surface-supplemental-medlegal",
    "surface-ptp-causation",
    "surface-ptp-apportionment",
    "surface-advocacy-registers",
    "surface-contention-loop",
)

_FROZEN_SURFACE_CASE_SEEDS = {
    "surface-initial-medlegal": 620101,
    "surface-psych-medlegal": 620102,
    "surface-supplemental-medlegal": 620103,
    "surface-ptp-causation": 620104,
    "surface-ptp-apportionment": 620105,
    "surface-advocacy-registers": 620106,
    "surface-contention-loop": 620107,
}

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
def _fixture_case(path: str, case_id: str) -> tuple[Any, Any]:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    spec = parse_caseload_spec(payload)
    seed = next(case for case in spec.cases if case.case_id == case_id)
    return seed, build_case_plan(seed)


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
        imr_application_content=document.imr_application_content,
        imr_outcome=document.imr_outcome,
        medical_story_render_key=document.medical_story_render_key,
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
        plan.medical_story.by_document_index.get(index) if plan.medical_story is not None else None
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


def test_surface_matrix_uses_the_frozen_r67_case_ids_and_seeds():
    """R67 — the seven fixture identities are contract, not descriptive labels."""
    actual = {entry["case_id"]: entry["rng_seed"] for entry in _fixture_payload()["cases"]}
    assert actual == _FROZEN_SURFACE_CASE_SEEDS


def test_r8_governed_surface_sets_equal_the_frozen_spec():
    """R8 — pin all six exact sets; membership loops cannot detect deletion."""
    expected = {
        "initial": frozenset(
            {
                "QME_REPORT_INITIAL",
                "QME_COMPREHENSIVE_REPORT",
                "AME_REPORT",
                "AME_COMPREHENSIVE_REPORT",
                "MEDICAL_LEGAL_QME_AME_IME",
                "APPORTIONMENT_REPORT",
            }
        ),
        "psych": frozenset({"PSYCH_EVAL_REPORT_QME_AME"}),
        "supplemental": frozenset({"QME_REPORT_SUPPLEMENTAL", "SUPPLEMENTAL_QME_AME_REPORT"}),
        "ptp_causation": frozenset(
            {
                "TREATING_PHYSICIAN_REPORT",
                "TREATING_PHYSICIAN_REPORT_PR2",
                "TREATING_PHYSICIAN_REPORT_PR4",
                "TREATING_PHYSICIAN_REPORT_FINAL",
            }
        ),
        "ptp_apportionment": frozenset(
            {"TREATING_PHYSICIAN_REPORT_PR4", "TREATING_PHYSICIAN_REPORT_FINAL"}
        ),
        "advocacy": frozenset(
            {
                "ADVOCACY_LETTERS_PTP",
                "ADVOCACY_LETTERS_QME",
                "ADVOCACY_LETTERS_AME",
                "ADVOCACY_LETTERS_PTP_QME_AME",
            }
        ),
    }
    actual = {
        "initial": INITIAL_MEDLEGAL_SURFACES,
        "psych": PSYCH_MEDLEGAL_SURFACES,
        "supplemental": SUPPLEMENTAL_MEDLEGAL_SURFACES,
        "ptp_causation": PTP_CAUSATION_SURFACES,
        "ptp_apportionment": PTP_APPORTIONMENT_SURFACES,
        "advocacy": ADVOCACY_LETTER_SURFACES,
    }
    assert actual == expected


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
                f"{case_id}[{document.index}] {document.subtype} fell back: {rendered.fallback}"
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
        ("surface-advocacy-registers", "opn-02"),
        ("surface-advocacy-registers", "opn-03"),
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


def test_psych_triad_renders_world_framing_rederivation_and_section_4660_1_c():
    """R17/R79 — consequence world, direct applicant/PTP, consequence QME.

    The QME remains industrial while distinguishing treatment compensability
    from the post-2012 added-impairment limitation. McCullough controls every
    report; no rendered quality value selects the law.
    """
    seed, plan = _fixture_case(str(_PSYCH_TRIAD_PATH), "psych-triad-consequence-as-direct")
    assert plan.medical_history is not None
    psych = next(
        condition
        for condition in plan.medical_history.conditions
        if condition.body_system == "psychiatric"
    )
    assert psych.psych_injury_kind == "compensable_consequence"
    assert plan.medical_assertions is not None
    contention = plan.medical_assertions.contention("ctn-01")
    ptp = plan.medical_assertions.opinion("opn-01")
    qme = plan.medical_assertions.opinion("opn-02")
    assert contention is not None and contention.psych_injury_kind == "direct"
    assert ptp is not None
    assert (ptp.psych_injury_kind, ptp.aoe_coe_finding) == ("direct", "industrial")
    assert qme is not None
    assert (qme.psych_injury_kind, qme.aoe_coe_finding) == (
        "compensable_consequence",
        "industrial",
    )
    assert not any(
        row.psych_exception_analysis not in (None, "none_applies")
        for row in plan.medical_assertions.apportionment_assertions
    )

    assert plan.medical_story is not None
    rendered: dict[str, str] = {}
    for document in plan.documents:
        story = plan.medical_story.by_document_index.get(document.index)
        if story is None:
            continue
        key = story.contention_surface or (
            story.medical_opinion.id if story.medical_opinion is not None else ""
        )
        if key not in {"advocacy", "opn-01", "opn-02"}:
            continue
        rendered[key] = _flat(
            _render(
                seed,
                plan,
                document,
                story,
                f"psych-triad-{document.index}",
            ).text
        )

    assert "direct injury caused by the events of employment themselves" in rendered["advocacy"]
    assert "PSYCHIATRIC CAUSATION" in rendered["opn-01"]
    assert "direct injury arising from the events of employment themselves" in rendered["opn-01"]
    qme_text = rendered["opn-02"]
    _assert_ordered(
        qme_text,
        "PSYCHIATRIC INJURY CAUSATION",
        "LABOR CODE §3208.3 ANALYSIS",
        "LABOR CODE §4660.1(c) ANALYSIS",
        "PSYCHIATRIC APPORTIONMENT",
    )
    assert "developed as a consequence of the industrial physical injury" in qme_text
    assert "arose out of and in the course of employment" in qme_text
    assert "section 3208.3(b)(1)'s predominant-cause threshold applies" in qme_text
    assert "physical injury and its medical effects" in qme_text
    assert "section 3208.3(d) is considered only as the six-month employment rule" in qme_text
    assert "is not authority for bypassing predominant cause" in qme_text
    assert "limits an additional psychiatric impairment rating" in qme_text
    assert "does not decide whether the condition itself is industrial" in qme_text
    assert re.search(r"\b(?:unsupportable|thin)\b", qme_text.lower()) is None


def test_hikida_justice_variants_render_the_frozen_four_cell_semantics():
    """R7 — all four treatment-causation/result cells render their own law."""
    seed, plan = _case("surface-advocacy-registers")
    assert plan.medical_story is not None
    document = next(
        item
        for item in plan.documents
        if (story := plan.medical_story.by_document_index.get(item.index)) is not None
        and story.contention_surface == "advocacy"
    )
    base_story = plan.medical_story.by_document_index[document.index]
    cells = (
        ("ctn-h1", "contributing_cause", "apply"),
        ("ctn-h2", "contributing_cause", "refuse"),
        ("ctn-h3", "sole_cause", "apply"),
        ("ctn-h4", "sole_cause", "refuse"),
    )
    contentions = tuple(
        StoryContention(
            id=contention_id,
            claim_type="compensable_consequence",
            party="applicant",
            position="affirm",
            target_body_part="lumbar_spine",
            doctrine_hooks=("hikida_treatment_carveout",),
            treatment_causation=treatment_causation,
            requested_apportionment=requested_apportionment,
        )
        for contention_id, treatment_causation, requested_apportionment in cells
    )
    rendered = _flat(
        _render(
            seed,
            plan,
            document,
            base_story.model_copy(update={"contentions": contentions}),
            "hikida-four-cells",
        ).text
    )
    for marker in (
        "other pathology also contributes; under Justice's narrowing of Hikida, "
        "statutory apportionment applies",
        "requested refusal of apportionment invokes Hikida even though Justice limits the carveout",
        "requested result still applies apportionment contrary to the Hikida carveout",
        "Hikida, as narrowed by Justice, therefore requires compensation without apportionment",
    ):
        assert marker in rendered
    assert re.search(r"\b(?:supported|unsupportable|thin)\b", rendered.lower()) is None


def test_sibtf_surfaces_render_exact_section_4751_alternatives_and_no_wrong_threshold():
    """R19 — the prior-35% invention is gone; both statutory limbs remain."""
    seed, plan = _case("surface-initial-medlegal")
    document, story = _bound("surface-initial-medlegal", "opn-02")
    assert document.subtype == "QME_COMPREHENSIVE_REPORT"
    rendered = _flat(
        _render(
            seed,
            plan,
            dataclasses.replace(document, content_flags=("sibtf",)),
            story,
            "sibtf-4751",
        ).text
    )
    expected = DOCTRINE_CONTENT["sibtf"]
    assert "preexisting permanent partial disability" in expected.legal_paragraphs[0]
    for marker in (
        "subsequent compensable injury producing additional permanent partial disability",
        "combined permanent disability greater than that from the subsequent injury alone",
        "combined permanent disability of at least seventy percent",
        "opposite and corresponding member",
        "unadjusted for age or occupation, of at least five percent",
        "unadjusted for age or occupation, of at least thirty-five percent",
    ):
        assert marker in rendered
    assert "preexisting disability of at least thirty-five percent" not in rendered.lower()


def _fresh_imr_case(case_id: str) -> tuple[Any, Any]:
    payload = yaml.safe_load(_IMR_MATRIX_PATH.read_text(encoding="utf-8"))
    spec = parse_caseload_spec(payload)
    seed = next(case for case in spec.cases if case.case_id == case_id)
    return seed, build_case_plan(seed)


def test_imr_request_draw_uses_only_effective_upheld_denials_with_unauthored_imr(
    monkeypatch: pytest.MonkeyPatch,
):
    """R39/R57 — authored booleans win and only one denominator draws."""
    calls: dict[str, list[str]] = {}
    original = medical_assertions_module._medical_story_rng

    def recording_rng(seed: Any, family: str, semantic_key: Any):
        calls.setdefault(seed.case_id, []).append(family)
        return original(seed, family, semantic_key)

    monkeypatch.setattr(medical_assertions_module, "_medical_story_rng", recording_rng)
    plans = {
        case_id: _fresh_imr_case(case_id)[1]
        for case_id in (
            "imr-authored-false-upheld",
            "imr-authored-true-upheld",
            "imr-sampled-upheld",
            "imr-overturned",
        )
    }
    assert plans["imr-authored-false-upheld"].medical_ur_plan is not None
    assert plans["imr-authored-false-upheld"].medical_ur_plan.imr_requested is False
    assert plans["imr-authored-true-upheld"].medical_ur_plan is not None
    assert plans["imr-authored-true-upheld"].medical_ur_plan.imr_requested is True
    assert plans["imr-sampled-upheld"].medical_ur_plan is not None
    assert plans["imr-sampled-upheld"].medical_ur_plan.imr_requested is True
    assert plans["imr-overturned"].medical_ur_plan is not None
    assert plans["imr-overturned"].medical_ur_plan.imr_requested is False

    assert "imr-request" not in calls.get("imr-authored-false-upheld", [])
    assert "imr-request" not in calls.get("imr-authored-true-upheld", [])
    assert calls["imr-sampled-upheld"].count("imr-request") == 1
    assert "imr-request" not in calls.get("imr-overturned", [])
    for case_id, plan in plans.items():
        denials = [
            document
            for document in plan.documents
            if document.subtype == "MEDICAL_TREATMENT_DENIAL_UR"
        ]
        applications = [
            document for document in plan.documents if document.subtype == "IMR_APPLICATION_FORM"
        ]
        if applications:
            assert len(denials) == 1
            assert applications[0].imr_target_denial_date == denials[0].doc_date
        if case_id == "imr-overturned":
            assert not denials


def test_medical_story_imr_uses_canonical_carrier_and_legacy_path_stays_unchanged():
    """R39 — gated decisions use the canonical carrier; legacy keeps its form."""
    seed, gated = _fresh_imr_case("imr-authored-true-upheld")
    gated_subtypes = tuple(document.subtype for document in gated.documents)
    assert gated_subtypes.count("IMR_APPLICATION_FORM") == 1
    assert gated_subtypes.count("INDEPENDENT_MEDICAL_REVIEW_DECISION") == 1
    assert "IMR_DETERMINATION_FORM" not in gated_subtypes
    decision = next(
        document
        for document in gated.documents
        if document.subtype == "INDEPENDENT_MEDICAL_REVIEW_DECISION"
    )
    application = next(
        document for document in gated.documents if document.subtype == "IMR_APPLICATION_FORM"
    )
    denial = next(
        document
        for document in gated.documents
        if document.subtype == "MEDICAL_TREATMENT_DENIAL_UR"
    )
    assert denial.doc_date < application.doc_date < decision.doc_date
    assert decision.imr_target_denial_date == denial.doc_date
    assert decision.imr_application_content is None

    storyless_seed = seed.model_copy(
        update={"scenario": seed.scenario.model_copy(update={"medical_history": None})}
    )
    legacy = build_case_plan(storyless_seed)
    legacy_subtypes = tuple(document.subtype for document in legacy.documents)
    assert legacy.medical_ur_plan is None
    assert "IMR_DETERMINATION_FORM" in legacy_subtypes


def test_sampled_imr_fields_are_sparse_without_quality_like_state():
    """R58 — omissions are visible fields, never hidden adequacy state."""
    try:
        _sampled_seed, sampled = _fresh_imr_case("imr-sampled-upheld")
    except Exception as error:
        pytest.fail(f"sampled sparse IMR construction raised: {error!r}")
    sampled_application = next(
        document for document in sampled.documents if document.subtype == "IMR_APPLICATION_FORM"
    )
    content = sampled_application.imr_application_content
    assert content is not None
    assert sampled.medical_ur_plan is not None
    assert sampled.medical_ur_plan.imr_application == content
    assert content.target_denial_subtype == "MEDICAL_TREATMENT_DENIAL_UR"
    assert content.target_denial_date == sampled_application.imr_target_denial_date
    fields = set(type(content).model_fields)
    assert fields == {
        "disputed_treatment",
        "diagnosis_icd10",
        "ur_determination_attached",
        "supporting_record_subtypes",
        "clinical_rebuttal",
        "mtus_citations",
        "target_denial_subtype",
        "target_denial_date",
    }
    assert not fields & {"thin", "underworked", "adequacy", "quality"}
    occupancy = (
        content.disputed_treatment is not None,
        content.diagnosis_icd10 is not None,
        content.ur_determination_attached is not None,
        bool(content.supporting_record_subtypes),
        content.clinical_rebuttal is not None,
        bool(content.mtus_citations),
    )
    assert any(occupancy) and not all(occupancy)

    _explicit_seed, explicit = _fresh_imr_case("imr-sparse-explicit")
    explicit_application = next(
        document for document in explicit.documents if document.subtype == "IMR_APPLICATION_FORM"
    ).imr_application_content
    assert explicit_application is not None
    assert explicit_application.disputed_treatment == "lumbar epidural steroid injection"
    assert explicit_application.diagnosis_icd10 is None
    assert explicit_application.ur_determination_attached is None
    assert explicit_application.supporting_record_subtypes == ()
    assert explicit_application.clinical_rebuttal == (
        "The requested treatment is medically necessary for the industrial "
        "condition. Reconsideration of the utilization-review determination "
        "is requested."
    )
    assert explicit_application.mtus_citations == ()


def test_ptp_sections_follow_the_frozen_order():
    """R9 — the treating register: assessment, then the physician's own
    causation conclusion, then the plan; the apportionment statement exists
    only on the P&S surfaces, immediately after the impairment rating."""
    _seed, apportionment_plan = _case("surface-ptp-apportionment")
    assert apportionment_plan.medical_story is not None
    documents_by_index = {document.index: document for document in apportionment_plan.documents}
    assert documents_by_index[54].subtype == "TREATING_PHYSICIAN_REPORT_PR4"
    assert documents_by_index[54].medical_opinion_id == "opn-01"
    assert 54 in apportionment_plan.medical_story.by_document_index
    assert documents_by_index[63].subtype == "DEPOSITION_TRANSCRIPT"
    assert 63 not in apportionment_plan.medical_story.by_document_index

    for opinion_id in ("opn-01", "opn-02"):
        document, _story = _bound("surface-ptp-causation", opinion_id)
        text = _rendered("surface-ptp-causation", document.index).text
        _assert_ordered(text, "ASSESSMENT", "INDUSTRIAL CAUSATION", "TREATMENT PLAN")
        assert "IMPAIRMENT RATING" not in text
        assert "APPORTIONMENT OF PERMANENT DISABILITY" not in text
    for opinion_id in ("opn-01", "opn-02"):
        document, _story = _bound("surface-ptp-apportionment", opinion_id)
        text = _rendered("surface-ptp-apportionment", document.index).text
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
    for case_id in ("surface-advocacy-registers", "surface-contention-loop"):
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
                assert taxonomy.parent_of(reference.subtype) in (RECORD_REFERENCE_PARENT_TYPES)
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
    for case_id in ("surface-supplemental-medlegal", "surface-contention-loop"):
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
    for case_id in ("surface-advocacy-registers", "surface-contention-loop"):
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
                    "court_reporter" if surface == "qme_deposition" else f"{actor}_attorney"
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
    document, story = _bound("surface-supplemental-medlegal", "opn-01")
    block = ajc65_story_governance(story)["apportionment"]
    assert block["register"] == "apportioned"
    assert block["nonindustrial_pct"] == 20
    assert "As to the lumbar spine, 20 percent" in block["opinion"]
    assert "As to the shoulder, 20 percent" in block["opinion"]
    text = _flat(_rendered("surface-supplemental-medlegal", document.index).text)
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
    stripped = story.model_copy(update={"medical_opinion": None, "apportionments": ()})
    governed = _flat(
        _without_page_furniture(_render(seed, plan, document, story, "draws-governed").text)
    )
    history_only = _flat(
        _without_page_furniture(_render(seed, plan, document, stripped, "draws-history-only").text)
    )

    # Non-vacuity: the two renders really did diverge where governance lives.
    assert "The multilevel degenerative disc disease predated the injury" in governed
    assert "The multilevel degenerative disc disease predated the injury" not in history_only

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
    expected_letters = frozenset(
        {
            "ADVOCACY_LETTERS_PTP",
            "ADVOCACY_LETTERS_QME",
            "ADVOCACY_LETTERS_AME",
            "ADVOCACY_LETTERS_PTP_QME_AME",
            "OBJECTION_TO_QME_AME_REPORT",
            "REQUEST_SUPPLEMENTAL_QME_AME_REPORT",
        }
    )
    expected_depositions = frozenset({"DEPOSITION_TRANSCRIPT_QME_AME"})
    assert expected_letters == AJC66_LETTER_TEMPLATE_SUBTYPES
    assert expected_depositions == AJC66_DEPOSITION_TEMPLATE_SUBTYPES

    for key in sorted(expected_letters):
        switch = ajc66_variant_content(key)
        assert switch == {"letter": True}, f"{key} -> {switch!r}"
        assert switch is not True
    for key in sorted(expected_depositions):
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

    _seed, plan = _case("surface-advocacy-registers")
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
    seed, plan = _case("surface-advocacy-registers")
    document = next(
        d for d, s in _governed("surface-advocacy-registers") if s.contention_surface == "advocacy"
    )
    absent = _flat(_render(seed, plan, document, None, "ajc66-story-absent").text)
    assert "RECORDS AND FACTS FOR REVIEW" not in absent
    assert "being served simultaneously on opposing counsel" not in absent


def test_absent_medical_story_gate_constructs_no_context_projection_or_story_rng():
    """R1/R68 — the absent gate returns before projection or story RNG and the
    renderer constructs no M3 governance context."""
    seed = parse_case_seed(
        {
            "case_id": "medical-story-absent",
            "rng_seed": 620199,
            "injury": {
                "type": "specific",
                "date_of_injury": "2024-03-01",
                "body_parts": [{"part": "lumbar_spine"}],
            },
            "lifecycle": {"target_stage": "medical_legal", "eval_type": "qme"},
            "documents": {"format_mix": {"pdf": 1.0}},
            "output": {"formats": ["pdf"]},
        }
    )
    plan = build_case_plan(seed)
    assert seed.scenario.medical_history is None
    assert plan.medical_story is None

    def fail(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("the absent medical-story gate constructed M3 state")

    with pytest.MonkeyPatch.context() as patcher:
        patcher.setattr(medical_story_module, "_project_demographics", fail)
        patcher.setattr(random, "Random", fail)
        assert derive_medical_story(seed, None, None, plan.documents) is None

    document = next(entry for entry in plan.documents if entry.subtype in INITIAL_MEDLEGAL_SURFACES)
    with pytest.MonkeyPatch.context() as patcher:
        patcher.setattr(renderer_module, "ajc65_story_governance", fail)
        patcher.setattr(renderer_module, "ajc66_variant_content", fail)
        rendered = _render(seed, plan, document, None, "medical-story-gate-absent")
    assert rendered.fallback is False


def test_governed_medical_facts_are_identical_across_every_bound_surface():
    """R4 — one world, every surface: the projected history section is
    byte-identical across every report of a case, and a bound opinion's split
    is stated with the same numbers on its report and at its deposition."""
    # (a) The PMH section, word for word, across all four initial reports.
    sections = set()
    for opinion_id in ("opn-01", "opn-02", "opn-03", "opn-04"):
        document, _story = _bound("surface-initial-medlegal", opinion_id)
        text = _flat(
            _without_page_furniture(_rendered("surface-initial-medlegal", document.index).text)
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

    try:
        with pytest.MonkeyPatch.context() as patcher:
            for model in (
                ApplicantDemographics,
                MedicalCondition,
                PriorClaim,
                PriorAward,
                MedicalOpinion,
                Contention,
                ApportionmentAssertion,
            ):
                patcher.setattr(model, "model_dump", _spy(model.__name__))
                patcher.setattr(model, "model_dump_json", _spy(model.__name__))
            story_plan = derive_medical_story(
                seed, plan.medical_history, plan.medical_assertions, plan.documents
            )
    except Exception as error:
        pytest.fail(f"literal medical-story projection raised: {error!r}")
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
    position = next(i for i, d in enumerate(documents) if d.medical_opinion_id is not None)
    documents[position] = dataclasses.replace(documents[position], medical_opinion_id="opn-99")
    message = None
    try:
        derive_medical_story(seed, plan.medical_history, plan.medical_assertions, documents)
    except MedicalAssertionError as exc:
        message = str(exc)
    assert message is not None, "a dangling opinion binding derived a story instead of failing (R5)"
    assert "'opn-99'" in message
    assert "does not exist in the completed ledger" in message
    assert "fails instead of guessing by date (R5)" in message


def _part5_psych_report(opinion_id: str) -> tuple[Any, Any, str]:
    document, story = _bound("surface-psych-medlegal", opinion_id)
    return document, story, _flat(_rendered("surface-psych-medlegal", document.index).text)


def test_part5_psych_complaint_registers_are_exact_and_fact_grounded():
    """R82 — all four speaking-layer registers render exact grounded slots."""
    _direct_doc, _direct_story, direct = _part5_psych_report("opn-01")
    _gfpa_doc, _gfpa_story, gfpa = _part5_psych_report("opn-02")
    _consequence_doc, _consequence_story, consequence = _part5_psych_report("opn-03")
    _safety_doc, _safety_story, safety = _part5_psych_report("opn-04")

    assert (
        "The reported psychiatric symptoms are attributed to industrial event "
        "itself rather than solely to the later effects of the physical injuries."
    ) in direct
    assert (
        "The applicant reports performance evaluation, progressive discipline, "
        "discipline, termination, reported mistreatment, reported discrimination, "
        "harassment, humiliation and describes the work environment as hostile work "
        "environment."
    ) in gfpa
    assert (
        "The psychiatric condition developed in the course of the applicant's "
        "response to pain, treatment, sleep disruption, loss of function, disability "
        "following the physical injury."
    ) in consequence
    assert (
        "The applicant reports trauma-related symptoms following traumatic assault "
        "while serving as Firefighter."
    ) in safety
    rendered = (direct, gfpa, consequence, safety)
    assert all("[" not in text and "]" not in text for text in rendered)
    assert all("public safety" not in text.lower() for text in rendered)
    assert tuple(key for key, _clauses in PSYCH_HISTORY_REGISTER) == (
        "harassment_gfpa",
        "direct_physical_event",
        "compensable_consequence",
        "safety_officer_ptsd",
    )


def test_part5_rolda_threshold_six_month_post_termination_and_gfpa_walk_is_exact():
    """R79/R83 — corrected McCullough, Rolda, dates, GFPA, and reservation."""
    _gfpa_doc, _gfpa_story, gfpa = _part5_psych_report("opn-02")
    _consequence_doc, _consequence_story, consequence = _part5_psych_report("opn-03")
    _safety_doc, _safety_story, safety = _part5_psych_report("opn-04")
    rolda = (
        "After consideration of the medical, documentary, and testimonial "
        "evidence, the trier of fact must determine: (1) whether the alleged "
        "psychiatric injury involves actual events of employment, a factual/legal "
        "determination; (2) if so, whether those actual events were the predominant "
        "cause of the psychiatric injury, a determination requiring medical "
        "evidence; (3) if so, whether any actual employment events were personnel "
        "actions that were lawful, nondiscriminatory, and in good faith, a "
        "factual/legal determination; and (4) if so, whether those lawful, "
        "nondiscriminatory, good-faith personnel actions were a substantial cause "
        "of the psychiatric injury, a determination requiring medical evidence."
    )
    assert rolda in gfpa
    assert (
        "Actual events of employment must be predominant as to all causes combined, "
        "meaning greater than 50 percent."
    ) in gfpa
    assert (
        "Labor Code section 3208.3(d) requires six months of employment unless the "
        "injury was caused by a sudden and extraordinary employment condition."
    ) in gfpa
    assert (
        "Labor Code section 3208.3(h) places the burden on the party asserting that "
        "lawful, nondiscriminatory, good-faith personnel actions substantially caused "
        "the injury."
    ) in gfpa
    corrective_3208_3d = (
        "Labor Code section 3208.3(d) is considered only as the six-month "
        "employment rule and is not authority for bypassing predominant cause "
        "under Labor Code section 3208.3(b)(1)."
    )
    assert corrective_3208_3d in gfpa
    assert "predominant-cause threshold applies" in consequence
    assert "physical injury and its medical effects are treated as qualifying" in consequence
    assert rolda not in safety
    assert (
        "In the absence of evidence affirmatively controverting the presumption, "
        "the ordinary Rolda analysis, including the good-faith-personnel-action "
        "contention, is not reached."
    ) in safety

    seed, plan = _case("surface-psych-medlegal")
    post_document, post_story = next(
        (document, story)
        for document, story in _governed("surface-psych-medlegal")
        if document.defense_contest_theories == ("post_termination",)
    )
    post = _flat(_render(seed, plan, post_document, post_story, "part5-post-termination").text)
    for clause in dict(PSYCH_DEFENSE_CONTEST_REGISTER)["post_termination"]:
        assert clause in post
    assert "sudden-and-extraordinary exception is not inferred from a violent-act" in gfpa

    # R79 is a prohibition, not merely a required corrective sentence. Scan
    # every rendered Part-5 psych surface, exempting only the exact frozen
    # negation frame above so a nearby affirmative bypass statement cannot hide.
    rolda_application = (
        "Whether the reported employment events occurred, and whether a personnel "
        "action was lawful, nondiscriminatory, and in good faith, are factual/legal "
        "questions. Assuming the trier of fact finds that the reported employment "
        "events occurred, it is my opinion within reasonable medical probability "
        "that those actual events were predominant as to all causes combined."
    )
    ordinary_threshold = (
        "Actual events of employment must be predominant as to all causes combined, "
        "meaning greater than 50 percent."
    )
    consequence_threshold = (
        "The industrial physical injury and its medical effects are qualifying "
        "actual events and must be predominant as to all causes combined."
    )
    corrected_mccullough = (
        "Labor Code section 3208.3(b)(1)'s predominant-cause threshold applies. "
        "The industrial physical injury and its medical effects are treated as "
        "qualifying actual events of employment. Those events must be predominant "
        "as to all causes combined unless Labor Code section 3208.3(b)(2)'s "
        "violent-act standard applies."
    )
    six_month = (
        "Labor Code section 3208.3(d) requires six months of employment unless the "
        "injury was caused by a sudden and extraordinary employment condition."
    )
    sudden_extraordinary_reservation = (
        "The available dates require the six-month issue to be addressed; the "
        "sudden-and-extraordinary exception is not inferred from a violent-act "
        "contention."
    )
    gfpa_threshold = (
        "Labor Code section 3208.3(h) places the burden on the party asserting that "
        "lawful, nondiscriminatory, good-faith personnel actions substantially "
        "caused the injury."
    )
    ordinary_dsm = (
        "The psychiatric condition is diagnosed using terminology and criteria "
        "generally approved and accepted nationally; Labor Code section 3208.3 "
        "does not itself expressly name DSM-5."
    )
    safety_presumption = (
        "Labor Code section 3212.15 applies to post-traumatic stress disorder "
        "diagnosed according to the most recent edition of the Diagnostic and "
        "Statistical Manual and developing or manifesting during qualifying service. "
        "The presumption is disputable. Once its predicates are established, the "
        "burden shifts to the defendant to affirmatively controvert industrial "
        "causation. In the absence of evidence affirmatively controverting the "
        "presumption, the ordinary Rolda analysis, including the "
        "good-faith-personnel-action contention, is not reached. The diagnosis is "
        "addressed under DSM-5-TR, as the most recent DSM edition. Labor Code section "
        "3212.15 remains in force through January 1, 2029."
    )
    expected_analysis_paragraphs = {
        "opn-01": (
            " ".join(
                (
                    rolda,
                    rolda_application,
                    ordinary_threshold,
                    corrective_3208_3d,
                    six_month,
                    sudden_extraordinary_reservation,
                    ordinary_dsm,
                )
            ),
        ),
        "opn-02": (
            " ".join(
                (
                    rolda,
                    rolda_application,
                    ordinary_threshold,
                    corrective_3208_3d,
                    six_month,
                    sudden_extraordinary_reservation,
                    gfpa_threshold,
                    ordinary_dsm,
                )
            ),
        ),
        "opn-03": (
            " ".join(
                (
                    rolda,
                    rolda_application,
                    consequence_threshold,
                    corrected_mccullough,
                    corrective_3208_3d,
                    six_month,
                    sudden_extraordinary_reservation,
                    ordinary_dsm,
                )
            ),
        ),
        "opn-04": (safety_presumption,),
    }
    footer = re.compile(
        r"GBS Generated CONFIDENTIAL — Workers' Compensation Medical/Legal "
        r"Record Page \d+"
    )
    rendered_reports = {
        opinion_id: _part5_psych_report(opinion_id)[2]
        for opinion_id in expected_analysis_paragraphs
    }
    actual_analysis_paragraphs = {
        opinion_id: (
            _flat(
                footer.sub(
                    "",
                    text.split("LABOR CODE §3208.3 ANALYSIS", maxsplit=1)[1].split(
                        "LABOR CODE §4660.1(c) ANALYSIS", maxsplit=1
                    )[0],
                )
            ).strip(),
        )
        for opinion_id, text in rendered_reports.items()
    }
    assert actual_analysis_paragraphs == expected_analysis_paragraphs

    rendered_surfaces = [
        _flat(_rendered("surface-psych-medlegal", document.index).text)
        for document, _story in _governed("surface-psych-medlegal")
    ]
    assert any(corrective_3208_3d in text for text in rendered_surfaces)
    bypass_findings: list[str] = []
    for text in rendered_surfaces:
        for sentence in re.split(r"(?<=[.!?])\s+", text):
            lowered = sentence.lower()
            if lowered == corrective_3208_3d.lower():
                continue
            if (
                "3208.3(d)" in lowered
                and "predominant" in lowered
                and any(
                    token in lowered for token in ("permits", "without", "does not apply", "bypass")
                )
            ):
                bypass_findings.append(sentence)
    assert bypass_findings == []


def test_part5_actual_events_percentages_never_become_disability_apportionment():
    """R84 — authored injury percentages and §4663 rows coexist independently."""
    seed, plan = _case("surface-psych-medlegal")
    document, story, rendered = _part5_psych_report("opn-02")
    assert story.medical_opinion is not None
    allocation = (
        "45% reported harassment/humiliation/hostile-work-environment events; "
        "30% personnel actions; 25% outside or preexisting factors"
    )
    assert allocation in rendered
    assert len(story.apportionments) == 1
    assert (
        story.apportionments[0].industrial_percent,
        story.apportionments[0].nonindustrial_percent,
    ) == (70, 30)
    assert "70 percent" in rendered and "30 percent" in rendered
    pd_section = rendered.split("PSYCHIATRIC APPORTIONMENT", maxsplit=1)[1].split(
        "FUTURE MEDICAL TREATMENT RECOMMENDATIONS", maxsplit=1
    )[0]
    assert "70 percent" in pd_section and "30 percent" in pd_section
    assert "45%" not in pd_section
    causation_section = rendered.split("PSYCHIATRIC INJURY CAUSATION", maxsplit=1)[1].split(
        "LABOR CODE §3208.3 ANALYSIS", maxsplit=1
    )[0]
    for percentage in (
        story.apportionments[0].industrial_percent,
        story.apportionments[0].nonindustrial_percent,
    ):
        assert f"{percentage} percent" not in causation_section
        assert not re.search(
            rf"\b{percentage}%\s+(?:industrial|nonindustrial)\b",
            causation_section,
            flags=re.IGNORECASE,
        )
    assert (
        "The percentages above address causation of the psychiatric injury under "
        "Labor Code section 3208.3. Apportionment of permanent disability under "
        "section 4663 is a separate analysis."
    ) in rendered

    changed_row = story.apportionments[0].model_copy(
        update={"industrial_percent": 60, "nonindustrial_percent": 40}
    )
    changed_story = story.model_copy(update={"apportionments": (changed_row,)})
    changed = _flat(_render(seed, plan, document, changed_story, "part5-pd-row-changed").text)
    assert allocation in changed
    assert "60 percent" in changed and "40 percent" in changed
    changed_causation_section = changed.split("PSYCHIATRIC INJURY CAUSATION", maxsplit=1)[1].split(
        "LABOR CODE §3208.3 ANALYSIS", maxsplit=1
    )[0]
    assert "60 percent" not in changed_causation_section
    assert "40 percent" not in changed_causation_section
    changed_pd_section = changed.split("PSYCHIATRIC APPORTIONMENT", maxsplit=1)[1].split(
        "FUTURE MEDICAL TREATMENT RECOMMENDATIONS", maxsplit=1
    )[0]
    assert "60 percent" in changed_pd_section and "40 percent" in changed_pd_section
    assert "45%" not in changed_pd_section

    changed_allocation = (
        "55% chronic adverse-work/discrimination circumstances; "
        "25% acute workplace events; "
        "20% cannabis or another specifically grounded nonindustrial factor"
    )
    changed_rationale = changed_allocation + "."
    changed_opinion = story.medical_opinion.model_copy(
        update={"aoe_coe_rationale": changed_rationale}
    )
    changed_causation_story = story.model_copy(update={"medical_opinion": changed_opinion})
    changed_causation = _flat(
        _render(
            seed,
            plan,
            document,
            changed_causation_story,
            "part5-injury-causation-changed",
        ).text
    )
    assert changed_allocation in changed_causation
    assert "70 percent" in changed_causation and "30 percent" in changed_causation
    changed_causation_pd = changed_causation.split("PSYCHIATRIC APPORTIONMENT", maxsplit=1)[
        1
    ].split("FUTURE MEDICAL TREATMENT RECOMMENDATIONS", maxsplit=1)[0]
    assert "70 percent" in changed_causation_pd
    assert "55%" not in changed_causation_pd


def test_part5_safety_officer_ptsd_presumption_and_wilson_register_is_exact():
    """R85 — structured coverage, dated DSM, presumption, Larsen, and Wilson."""
    _safety_doc, _safety_story, safety = _part5_psych_report("opn-04")
    presumption_clauses = (
        "Labor Code section 3212.15 applies to post-traumatic stress disorder "
        "diagnosed according to the most recent edition of the Diagnostic and "
        "Statistical Manual and developing or manifesting during qualifying service.",
        "The presumption is disputable. Once its predicates are established, the "
        "burden shifts to the defendant to affirmatively controvert industrial "
        "causation.",
        "In the absence of evidence affirmatively controverting the presumption, "
        "the ordinary Rolda analysis, including the good-faith-personnel-action "
        "contention, is not reached.",
    )
    for clause in presumption_clauses:
        assert clause in safety
    assert "DSM-5-TR, as the most recent DSM edition" in safety
    assert "remains in force through January 1, 2029" in safety

    seed, plan = _case("surface-psych-medlegal")
    document, story, catastrophic = _part5_psych_report("opn-03")
    assert (
        "The factors are nonexclusive, and not every factor must apply. The inquiry "
        "concerns the physical injury independently of the psychiatric condition."
    ) in catastrophic
    violent_row = story.apportionments[0].model_copy(
        update={"psych_exception_analysis": "violent_act"}
    )
    violent_story = story.model_copy(update={"apportionments": (violent_row,)})
    violent = _flat(_render(seed, plan, document, violent_story, "part5-violent-act").text)
    assert (
        "The violent-act inquiry concerns the mechanism: strong physical force, "
        "extreme or intense force, or an act that was vehemently or passionately "
        "threatening."
    ) in violent
    assert "dispatchers" not in safety.lower()


def test_part5_gaf_to_wpi_is_report_prose_not_rating_state():
    """R86 — one substrate-produced pair is repeated only in physician prose."""
    _document, story, rendered = _part5_psych_report("opn-01")
    pair = re.search(
        r"assign a current GAF of (\d+).*?a GAF of \1 corresponds to (\d+) percent",
        rendered,
    )
    assert pair is not None
    assert (
        "Starting at the top level of the GAF scale, I evaluated each range by asking "
        "whether either symptom severity or level of functioning was worse than the "
        "range description. I moved downward until reaching the range that best "
        "matched whichever was worse, checked the next lower range against stopping "
        "prematurely, and selected the specific score within the ten-point range "
        "according to the severity and frequency of the supported findings."
    ) in rendered
    assert "DSM-IV-TR/GAF terminology is retained only" in rendered
    serialized = story.model_dump(mode="json")
    assert "gaf" not in str(serialized).lower()
    assert "whole_person_impairment" not in str(serialized).lower()
    assert not {"gaf", "wpi"}.intersection(type(story).model_fields)


def test_part5_direct_consequence_honest_and_mischaracterizing_registers_are_exact():
    """R87 — advocacy may diverge; PTP/QME remain independent speaking layers."""
    seed, plan = _fixture_case(str(_PSYCH_TRIAD_PATH), "psych-triad-consequence-as-direct")
    rendered: dict[str, str] = {}
    for document in plan.documents:
        story = plan.medical_story.by_document_index.get(document.index)
        if story is None:
            continue
        key = story.contention_surface or (
            story.medical_opinion.id if story.medical_opinion is not None else ""
        )
        if key in {"advocacy", "opn-01", "opn-02"}:
            rendered[key] = _flat(
                _render(seed, plan, document, story, f"part5-triad-{document.index}").text
            )
    applicant_lead = (
        "Applicant contends that the psychiatric injury was directly caused by the "
        "events of employment and that Labor Code section 4660.1(c) therefore does "
        "not bar an increased impairment rating. Alternatively, applicant relies on "
        "[the existing violent-act or catastrophic-injury theory]."
    )
    assert applicant_lead.split(" Alternatively,", maxsplit=1)[0] in rendered["advocacy"]
    assert "independently based" not in rendered["advocacy"]
    assert "direct injury arising from the events of employment themselves" in rendered["opn-01"]
    consequence = (
        "Within reasonable medical probability, the psychiatric injury is a sequela "
        "of and derivative of the industrial physical injury, specifically [grounded "
        "physical-injury effects]. The condition may remain industrial and compensable "
        "even though Labor Code section 4660.1(c)(1) limits an additional psychiatric "
        "impairment rating."
    )
    assert (
        consequence.replace(
            "[grounded physical-injury effects]",
            "pain, treatment, disability",
        )
        in rendered["opn-02"]
    )
    assert "section 3208.3(b)(1)'s predominant-cause threshold applies" in rendered["opn-02"]
    assert "section 3208.3(d) does not apply" not in rendered["opn-02"]
    assert (
        "The condition may remain industrial and compensable for treatment and "
        "temporary disability."
    ) in rendered["opn-02"]


def test_part5_psych_defense_and_contention_surface_phrase_pools_are_exact():
    """R88/R89 — four carrier voices and three theories stay ordered."""
    contention_register = {
        "advocacy": (
            "Please state whether the psychiatric injury was caused by the "
            "employment event itself rather than by later pain, disability, or "
            "treatment.",
            "Please state the percentage of total psychiatric-injury causation "
            "attributable to actual events of employment.",
            "Please address separately whether Labor Code section 4660.1(c)(1) "
            "applies and whether either paragraph (c)(2) exception is supported.",
        ),
        "objection": (
            "The report's history attributes the psychiatric symptoms to [grounded "
            "consequence facts], but the conclusion characterizes the injury as "
            "direct without reconciling that history.",
            "The report does not separate causation of psychiatric injury under "
            "section 3208.3 from apportionment of permanent disability under section "
            "4663.",
        ),
        "supplemental_request": (
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
        "qme_deposition": (
            "Doctor, is your opinion that the psychiatric condition arose from the "
            "event itself or from the medical effects of the physical injury?",
            "What history supports that distinction?",
            "What percentage of total injury causation do you assign to actual events "
            "of employment?",
            "Which parts of your answer are medical opinions, and which predicates do "
            "you leave to the trier of fact?",
        ),
    }
    defense_register = {
        "insufficient_investigation": (
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
        "post_termination": (
            "The psychiatric claim was presented after notice of termination or "
            "layoff, and Labor Code section 3208.3(e) must be addressed.",
            "The present record must identify the dates of notice, filing, and injury "
            "and must identify evidence supporting any statutory exception.",
            "Absent those dates and records, the evaluator should reserve the "
            "post-termination analysis rather than assume that an exception applies.",
        ),
        "lack_of_substantial_medical_evidence": (
            "A compensability opinion must be stated within reasonable medical "
            "probability, rest on an adequate examination and history, consider the "
            "pertinent facts, and explain the reasoning supporting its conclusion.",
            "The report does not adequately explain how the identified employment "
            "events produced the diagnosis or how the stated percentage was selected.",
            "An opinion based on speculation, an incomplete history, facts no longer "
            "germane, or an incorrect legal theory does not constitute substantial "
            "medical evidence.",
        ),
    }
    assert dict(PSYCH_CONTENTION_SURFACE_REGISTER) == contention_register
    assert dict(PSYCH_DEFENSE_CONTEST_REGISTER) == defense_register
    assert tuple(key for key, _clauses in PSYCH_CONTENTION_SURFACE_REGISTER) == (
        "advocacy",
        "objection",
        "supplemental_request",
        "qme_deposition",
    )
    assert tuple(key for key, _clauses in PSYCH_DEFENSE_CONTEST_REGISTER) == (
        "insufficient_investigation",
        "post_termination",
        "lack_of_substantial_medical_evidence",
    )
    seed, plan = _case("surface-contention-loop")
    governed = list(_governed("surface-contention-loop"))
    for surface in ("advocacy", "objection", "supplemental_request", "qme_deposition"):
        document, story = next(
            (document, story) for document, story in governed if story.contention_surface == surface
        )
        psych_contention = story.contentions[0].model_copy(
            update={
                "claim_type": "psych_add_on",
                "target_body_part": "psyche",
                "psych_injury_kind": "direct",
            }
        )
        updates: dict[str, Any] = {"contentions": (psych_contention,)}
        if story.medical_opinion is not None:
            updates["medical_opinion"] = story.medical_opinion.model_copy(
                update={"psych_injury_kind": "direct"}
            )
        psych_story = story.model_copy(update=updates)
        if surface in {"objection", "qme_deposition"}:
            document = dataclasses.replace(
                document,
                defense_contest_theories=(
                    "insufficient_investigation",
                    "post_termination",
                    "lack_of_substantial_medical_evidence",
                ),
            )
        text = _flat(
            _render(
                seed,
                plan,
                document,
                psych_story,
                f"part5-contention-{surface}",
            ).text
        )
        for clause in contention_register[surface]:
            if "[grounded consequence facts]" not in clause:
                assert clause in text
        if surface == "objection":
            positions = []
            for theory in document.defense_contest_theories:
                first = defense_register[theory][0]
                assert first in text
                positions.append(text.index(first))
            assert positions == sorted(positions)


def test_part5_register_gaps_render_only_generic_grounded_prose():
    """R81/R82/R85 — missing details reserve; they never become inventions."""
    seed, plan = _case("surface-psych-medlegal")
    document, story = _bound("surface-psych-medlegal", "opn-01")
    assert story.medical_opinion is not None
    generic_opinion = story.medical_opinion.model_copy(
        update={
            "psych_injury_kind": None,
            "aoe_coe_rationale": None,
            "endorses_contention_ids": (),
        }
    )
    generic_story = story.model_copy(
        update={
            "contentions": (),
            "medical_opinion": generic_opinion,
            "apportionments": (),
        }
    )
    text = _flat(_render(seed, plan, document, generic_story, "part5-register-gaps").text)
    assert (
        "The available history identifies no more specific psychiatric mechanism "
        "than the facts stated in the records reviewed."
    ) in text
    assert "[" not in text and "]" not in text
    for invented in (
        "MMPI",
        "T-score",
        "validity-scale",
        "malingering",
        "psych-specific TTD",
        "return-to-work restriction",
        "billing code",
    ):
        assert invented.lower() not in text.lower()
    assert (
        "Psychological testing was performed and considered together with the "
        "clinical interview, mental-status examination, and records reviewed."
    ) in text
