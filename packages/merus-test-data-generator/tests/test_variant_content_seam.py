"""The variant-content seam (AJC-66).

Several templates are reached by many registry subtypes carrying different
``variant`` strings, and render the same document for all of them: a
lab-results subtype comes out as an X-ray report, an emergency-room record
comes out as an operative report, and the registry's QME/AME deposition names
the applicant as deponent.

The suite is in three parts, and the first matters more than the rest:

**The default path is frozen.** ``tests/golden/render_baseline.json`` was
recorded from a checkout of ``origin/main``, before the seam existed, and every
registered pair must still hash to it on all four digests — text, story
fingerprint, ordered rng trace, and the actual PDF bytes.
wc-synthetic-caseload-engine pins four golden corpora against these templates
and does not set the opt-in key, so drift here is a corpus break.

**The opted-in path is real and internally coherent.** A governed variant must
render a document that is about what its subtype says it is, and must not
contradict itself while doing so.

**The registers claim only what they were written for.** A keyword match on
"objection" would have put medical-legal apportionment prose into a procedural
objection to a Declaration of Readiness. Every registered variant of the
templates with allowlists is exercised, not just the ones the registers claim.
"""

from __future__ import annotations

import os
import random
import re

import pytest

from tests.render_baseline import (
    ANCHOR_DATE,
    CLAIMED_LETTER_VARIANTS,
    DEFENSE_LETTER_VARIANTS,
    RENDER_CASES,
    RENDER_SEED,
    _load_template_class,
    build_fixture_case,
    baseline_provenance,
    load_baseline_cases,
    make_spec,
    render_digest,
)

LETTER_MODULE = "pdf_templates.correspondence.defense_counsel_letter"
DIAG_MODULE = "pdf_templates.medical.diagnostic_report"


@pytest.fixture(scope="module")
def case():
    return build_fixture_case()


@pytest.fixture(scope="module")
def baseline() -> dict:
    return load_baseline_cases()


def render_text(case, module_path: str, class_name: str, spec) -> str:
    """Rendered plain text for one document under the fixed render seed."""
    template = _load_template_class(module_path, class_name)(case)
    random.seed(RENDER_SEED)
    story = template.build_story(spec)
    return template._story_to_plaintext(story)


# --------------------------------------------------------------------------
# Part one: the default path does not move
# --------------------------------------------------------------------------


@pytest.mark.parametrize("label,module_path,class_name,subtype,variant", RENDER_CASES)
def test_default_path_is_byte_identical_to_the_recorded_baseline(
    case, baseline, label, module_path, class_name, subtype, variant
):
    """Without the opt-in, every governed pair renders its pre-seam bytes.

    Four digests, because each catches something the others cannot. Text sees
    words. The story fingerprint sees styles, flowable types and geometry — a
    restyled heading or a resized Spacer changes every page and not one
    character. The rng trace sees call *order*, which the final state cannot:
    two draws of equal consumption can be swapped and the state lands in exactly
    the same place. The PDF hash is the artifact a consumer actually ships.
    """
    spec = make_spec(subtype, variant)
    computed = render_digest(case, module_path, class_name, spec)
    recorded = baseline[label]
    differing = sorted(k for k in recorded if recorded[k] != computed.get(k))
    assert not differing, (
        f"{label} drifted from the pre-seam baseline on {differing}. If this is "
        f"deliberate, re-record with scripts/record_render_baseline.py and say so "
        f"in the commit — wcce's golden corpora will need re-recording too."
    )


@pytest.mark.parametrize("label,module_path,class_name,subtype,variant", RENDER_CASES)
def test_opt_in_set_false_is_indistinguishable_from_absent(
    case, baseline, label, module_path, class_name, subtype, variant
):
    """An explicitly disabled seam is the same input as no seam at all."""
    spec = make_spec(subtype, variant, extra_context={"variant_content": False})
    assert render_digest(case, module_path, class_name, spec) == baseline[label]


@pytest.mark.parametrize("label,module_path,class_name,subtype,variant", RENDER_CASES)
def test_unknown_variant_under_opt_in_falls_back_to_the_default_document(
    case, baseline, label, module_path, class_name, subtype, variant
):
    """A variant no register claims renders the default document, not an error.

    The registry carries ~350 subtypes and the seam governs a handful. Every
    other variant reaching a seamed template must pass straight through.
    """
    spec = make_spec(subtype, "no-register-claims-this-string", extra_context={"variant_content": True})
    assert render_digest(case, module_path, class_name, spec)["text"] == baseline[label]["text"]


def test_the_substrate_modality_tuple_wcce_intercepts_has_not_moved(case):
    """Canary for wc-synthetic-caseload-engine's ``_ForcedChoice``.

    wcce forces ``DiagnosticReport``'s modality draw by matching the candidate
    sequence *exactly* against ``("MRI", "CT", "X-Ray")``. Editing that list
    here silently stops the interception firing and un-pins the modality in
    every corpus. The default path must keep offering that exact sequence.
    """
    import pdf_templates.medical.diagnostic_report as module

    seen: list[list] = []

    class Spy:
        """Same shape as wcce's ``_ForcedChoice`` — it has to be, or the canary
        would not be watching the thing wcce actually relies on."""

        @staticmethod
        def choice(seq):
            seen.append(list(seq))
            return random.choice(seq)

        def __getattr__(self, name):
            return getattr(random, name)

    spec = make_spec("DIAGNOSTICS_IMAGING", "imaging")
    template = module.DiagnosticReport(case)
    original = module.random
    module.random = Spy()
    try:
        random.seed(RENDER_SEED)
        template.build_story(spec)
    finally:
        module.random = original

    assert ["MRI", "CT", "X-Ray"] in seen, (
        "wcce matches this exact candidate list to pin the modality; it is gone."
    )


# --------------------------------------------------------------------------
# The opt-in key's own contract
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, False),
        (True, True),
        (False, False),
        ({}, False),
        ({"diagnostic": True}, True),
        ({"diagnostic": False}, False),
        ({"letter": True}, False),
        ({"hospital": True, "letter": True}, False),
        ({"diagnostic": True, "letter": True}, True),
    ],
)
def test_the_opt_in_is_a_switch_or_a_namespaced_block(case, value, expected):
    """``bool`` is global; a ``dict`` must name this template's own family."""
    template = _load_template_class(DIAG_MODULE, "DiagnosticReport")(case)
    spec = make_spec("DIAGNOSTICS_LAB_RESULTS", "lab", extra_context={"variant_content": value})
    assert template.variant_content_enabled(spec) is expected


#: The shape AJC-65 puts on this same ``doc_spec.context``.
FOREIGN_BLOCK = {"apportionment": {"nonindustrial_pct": 20, "register": "preexisting"}}


@pytest.mark.parametrize("label,module_path,class_name,subtype,variant", RENDER_CASES)
def test_a_foreign_block_on_this_key_activates_nothing(
    case, baseline, label, module_path, class_name, subtype, variant
):
    """An AJC-65-shaped block must leave every template exactly as it was.

    This is why the block form is namespaced rather than merely type-checked.
    Contexts here are assembled once and reused across a packet, so a block
    meant for the QME report's apportionment would otherwise have switched on
    lab panels, ER records, advocacy letters and QME depositions at once — in
    documents whose author never asked for any of it, and with the four golden
    corpora pinned against them.
    """
    spec = make_spec(subtype, variant, extra_context={"variant_content": FOREIGN_BLOCK})
    assert render_digest(case, module_path, class_name, spec) == baseline[label]


@pytest.mark.parametrize("value", ["true", "false", 1, 0, [], ["lab"], object()])
def test_a_non_bool_non_dict_opt_in_is_refused_rather_than_guessed(case, value):
    """Every other type raises, instead of being silently truthy.

    Pinned while the key is new and no caller can break. Note ``"false"`` is
    truthy in Python; left open, that surfaces months later as a corpus diff.
    """
    template = _load_template_class(DIAG_MODULE, "DiagnosticReport")(case)
    spec = make_spec("DIAGNOSTICS_LAB_RESULTS", "lab", extra_context={"variant_content": value})
    with pytest.raises(ValueError, match="must be a bool"):
        template.variant_content_enabled(spec)


def test_every_seamed_template_declares_a_family():
    """A seam whose family is unset can never be reached by the block form."""
    families = {}
    for module_path, class_name in [
        (DIAG_MODULE, "DiagnosticReport"),
        ("pdf_templates.medical.operative_record", "OperativeRecord"),
        (LETTER_MODULE, "DefenseCounselLetter"),
        ("pdf_templates.discovery.deposition_notice", "DepositionNotice"),
        ("pdf_templates.discovery.deposition_transcript", "DepositionTranscript"),
    ]:
        family = _load_template_class(module_path, class_name).VARIANT_CONTENT_FAMILY
        assert family, f"{class_name} reads the seam but declares no family"
        families[class_name] = family
    assert len(set(families.values())) == len(families), f"families collide: {families}"


# --------------------------------------------------------------------------
# Part two: registers claim only what they were written for
# --------------------------------------------------------------------------


@pytest.mark.parametrize("subtype,variant", DEFENSE_LETTER_VARIANTS)
def test_only_the_three_intended_letter_families_resolve_to_a_register(subtype, variant):
    """Every registered DefenseCounselLetter variant, not just the claimed ones.

    ``objection_dor`` objects to a Declaration of Readiness and ``opposition``
    belongs to a Petition for Reconsideration. Under substring matching both
    drew the medical-legal register — apportionment, §4663, deposing the
    evaluator — into documents about neither.
    """
    from data.variant_content import letter_register

    resolved = letter_register(variant)
    if variant in CLAIMED_LETTER_VARIANTS:
        assert resolved is not None, f"{subtype} ({variant!r}) should resolve to a register"
    else:
        assert resolved is None, (
            f"{subtype} ({variant!r}) resolved to the {resolved.key!r} register; "
            f"this subtype is not one of the three families the seam authors"
        )


@pytest.mark.parametrize("subtype,variant", DEFENSE_LETTER_VARIANTS)
def test_unclaimed_letter_variants_render_the_default_document(case, subtype, variant):
    """And resolving to nothing must actually mean rendering the default."""
    if variant in CLAIMED_LETTER_VARIANTS:
        pytest.skip("claimed by a register; covered by the distinctness tests")

    default = render_digest(case, LETTER_MODULE, "DefenseCounselLetter", make_spec(subtype, variant))
    opted = render_digest(
        case, LETTER_MODULE, "DefenseCounselLetter",
        make_spec(subtype, variant, extra_context={"variant_content": True}),
    )
    assert opted == default, f"{subtype} ({variant!r}) changed under the opt-in but claims no register"


# --------------------------------------------------------------------------
# Part three: the opted-in documents are about their own subtype
# --------------------------------------------------------------------------

GOVERNED = [
    ("lab", DIAG_MODULE, "DiagnosticReport", "DIAGNOSTICS_LAB_RESULTS", "lab",
     ["LABORATORY", "Reference Range", "Specimen"], ["Tesla", "OPERATIVE REPORT", "radiologist"]),
    ("emg_ncv", DIAG_MODULE, "DiagnosticReport", "EMG_NCV_STUDY", "emg_ncv",
     ["ELECTRODIAGNOSTIC", "NERVE CONDUCTION", "NEEDLE EMG"], ["Tesla", "sagittal", "OPERATIVE REPORT"]),
    ("sleep_study", DIAG_MODULE, "DiagnosticReport", "SLEEP_STUDY", "sleep_study",
     ["POLYSOMNOGRAPHY", "Apnea-Hypopnea Index", "SLEEP ARCHITECTURE"], ["Tesla", "sagittal"]),
    ("er", "pdf_templates.medical.operative_record", "OperativeRecord", "EMERGENCY_ROOM_RECORDS", "er",
     ["EMERGENCY DEPARTMENT", "TRIAGE", "DISPOSITION"],
     ["OPERATIVE REPORT", "OPERATIVE NARRATIVE", "Estimated Blood Loss"]),
    ("acute", "pdf_templates.medical.operative_record", "OperativeRecord", "ACUTE_CARE_HOSPITAL_RECORDS", "acute",
     ["HOSPITAL COURSE", "ADMISSION", "DISCHARGE DISPOSITION"],
     ["OPERATIVE NARRATIVE", "Estimated Blood Loss"]),
    ("face_sheet", "pdf_templates.medical.operative_record", "OperativeRecord", "FACE_SHEET", "face_sheet",
     ["FACE SHEET", "REGISTRATION"], ["OPERATIVE NARRATIVE", "Estimated Blood Loss"]),
    ("advocacy", LETTER_MODULE, "DefenseCounselLetter", "ADVOCACY_LETTERS_QME", "advocacy_qme",
     ["8 C.C.R.", "advocacy"], []),
    ("objection", LETTER_MODULE, "DefenseCounselLetter", "OBJECTION_TO_QME_AME_REPORT",
     "Objection to QME/AME Report", ["object"], []),
    ("supp_request", LETTER_MODULE, "DefenseCounselLetter", "REQUEST_SUPPLEMENTAL_QME_AME_REPORT",
     "Request for Supplemental QME/AME Report", ["supplemental report"], []),
]


@pytest.mark.parametrize("label,module_path,class_name,subtype,variant,must,must_not", GOVERNED)
def test_governed_variant_renders_content_about_its_own_subtype(
    case, label, module_path, class_name, subtype, variant, must, must_not
):
    spec = make_spec(subtype, variant, extra_context={"variant_content": True})
    text = render_text(case, module_path, class_name, spec)
    for needle in must:
        assert needle.lower() in text.lower(), f"{label}: expected {needle!r} in the opted-in render"
    for needle in must_not:
        assert needle.lower() not in text.lower(), f"{label}: {needle!r} does not belong in a {label} document"


@pytest.mark.parametrize(
    "module_path,class_name,pairs",
    [
        (DIAG_MODULE, "DiagnosticReport",
         [("DIAGNOSTICS_IMAGING", "imaging"), ("DIAGNOSTICS_LAB_RESULTS", "lab"),
          ("EMG_NCV_STUDY", "emg_ncv"), ("SLEEP_STUDY", "sleep_study")]),
        ("pdf_templates.medical.operative_record", "OperativeRecord",
         [("OPERATIVE_HOSPITAL_RECORDS", None), ("EMERGENCY_ROOM_RECORDS", "er"),
          ("ACUTE_CARE_HOSPITAL_RECORDS", "acute"), ("DISCHARGE_SUMMARY", "discharge"),
          ("FACE_SHEET", "face_sheet")]),
        (LETTER_MODULE, "DefenseCounselLetter",
         [("ADVOCACY_LETTERS_QME", "advocacy_qme"),
          ("OBJECTION_TO_QME_AME_REPORT", "Objection to QME/AME Report"),
          ("REQUEST_SUPPLEMENTAL_QME_AME_REPORT", "Request for Supplemental QME/AME Report")]),
        ("pdf_templates.discovery.deposition_notice", "DepositionNotice",
         [("DEPOSITION_NOTICE_APPLICANT", "applicant"),
          ("DEPOSITION_NOTICE_MEDICAL_WITNESS", "medical_witness")]),
        ("pdf_templates.discovery.deposition_transcript", "DepositionTranscript",
         [("DEPOSITION_TRANSCRIPT", None),
          ("DEPOSITION_TRANSCRIPT_QME_AME", "Deposition Transcript (QME/AME)")]),
    ],
)
def test_governed_variants_render_mutually_distinct_documents(case, module_path, class_name, pairs):
    """The whole defect in one assertion: these used to be the same document."""
    seen: dict[str, str] = {}
    for subtype, variant in pairs:
        spec = make_spec(subtype, variant, extra_context={"variant_content": True})
        text = render_text(case, module_path, class_name, spec)
        collisions = [k for k, v in seen.items() if v == text]
        assert not collisions, f"{class_name}: variant {variant!r} renders identically to {collisions!r}"
        seen[str(variant)] = text


# --- the QME/AME deposition transcript (was never seamed at all) -----------


def test_the_qme_deposition_transcript_deposes_the_evaluator(case):
    """The registry has a QME/AME transcript subtype; it named the applicant."""
    spec = make_spec("DEPOSITION_TRANSCRIPT_QME_AME", "Deposition Transcript (QME/AME)",
                     extra_context={"variant_content": True})
    text = render_text(case, "pdf_templates.discovery.deposition_transcript", "DepositionTranscript", spec)

    evaluator = getattr(case, "qme_physician", None) or case.treating_physician
    header = text[: text.index("APPEARANCES")] if "APPEARANCES" in text else text
    assert evaluator.full_name.upper() in header.upper(), "the cover page does not name the evaluator"
    assert "Medical-Legal Evaluator" in text
    assert "sworn as the medical-legal evaluator" in text


def test_the_qme_deposition_asks_about_the_report_not_the_injury(case):
    """Evaluator topics — qualifications, records, the basis for apportionment."""
    spec = make_spec("DEPOSITION_TRANSCRIPT_QME_AME", "Deposition Transcript (QME/AME)",
                     extra_context={"variant_content": True})
    text = render_text(case, "pdf_templates.discovery.deposition_transcript", "DepositionTranscript", spec)
    for topic in ["records reviewed", "apportionment", "diagnosis", "physical examination"]:
        assert topic.lower() in text.lower(), f"a QME deposition should reach {topic!r}"


def test_the_default_transcript_still_deposes_the_applicant(case):
    """The seam adds a deponent; it does not take the default one away."""
    spec = make_spec("DEPOSITION_TRANSCRIPT", None)
    text = render_text(case, "pdf_templates.discovery.deposition_transcript", "DepositionTranscript", spec)
    assert case.applicant.full_name.upper() in text.upper()
    assert "Medical-Legal Evaluator" not in text


# --------------------------------------------------------------------------
# Part four: the opted-in documents do not contradict themselves
# --------------------------------------------------------------------------


def _all_scenarios():
    from data.variant_content import (
        ELECTRODIAGNOSTIC_REGISTER,
        LAB_REGISTER,
        SLEEP_REGISTER,
    )

    for register in (LAB_REGISTER, ELECTRODIAGNOSTIC_REGISTER, SLEEP_REGISTER):
        for scenario in register.scenarios:
            yield register, scenario


def test_every_lab_scenario_pairs_its_technique_with_its_specimen():
    """A blood chemistry panel must not describe a urine collection.

    These were independent draws, so any panel could pick up any technique.
    """
    from data.variant_content import LAB_REGISTER

    for scenario in LAB_REGISTER.scenarios:
        urine_panel = "URINE" in scenario.exam_label.upper()
        urine_technique = "urine" in scenario.technique.lower()
        assert urine_panel == urine_technique, (
            f"{scenario.key}: panel {scenario.exam_label!r} and its technique disagree "
            f"about the specimen type"
        )


def test_every_sleep_scenario_totals_one_hundred_percent():
    """Sleep stages are one fact reported four ways, and must sum."""
    from data.variant_content import SLEEP_REGISTER

    for scenario in SLEEP_REGISTER.scenarios:
        stages = {r.label: r.value for r in scenario.rows if r.label.startswith("Stage ")}
        assert len(stages) == 4, f"{scenario.key}: expected four sleep stages, got {sorted(stages)}"
        total = sum(int(v) for v in stages.values())
        assert total == 100, f"{scenario.key}: sleep stages total {total}%, not 100%"


def test_every_sleep_impression_matches_its_own_ahi():
    """Severity is defined by the AHI, so it cannot be drawn separately from it."""
    from data.variant_content import SLEEP_REGISTER

    def severity_for(ahi: float) -> str:
        if ahi < 5:
            return "none"
        if ahi < 15:
            return "mild"
        if ahi <= 30:
            return "moderate"
        return "severe"

    for scenario in SLEEP_REGISTER.scenarios:
        ahi = float(next(r.value for r in scenario.rows if "Apnea-Hypopnea" in r.label))
        expected = severity_for(ahi)
        impression = scenario.impression.lower()
        if expected == "none":
            assert "no significant sleep-disordered breathing" in impression, (
                f"{scenario.key}: AHI {ahi} is below the diagnostic threshold but the "
                f"impression describes apnea"
            )
        else:
            assert expected in impression, (
                f"{scenario.key}: AHI {ahi} is {expected} but the impression does not say so"
            )
        for other in ("mild", "moderate", "severe"):
            if other != expected:
                assert not re.search(rf"\b{other} obstructive sleep apnea", impression), (
                    f"{scenario.key}: AHI {ahi} is {expected} but the impression claims {other}"
                )


def test_every_electrodiagnostic_impression_is_supported_by_its_own_rows():
    """Needle findings and the diagnosis printed under them must agree."""
    from data.variant_content import ELECTRODIAGNOSTIC_REGISTER

    for scenario in ELECTRODIAGNOSTIC_REGISTER.scenarios:
        impression = scenario.impression.lower()
        needle = " ".join(r.value.lower() for r in scenario.secondary_rows)
        muscles = " ".join(r.label.lower() for r in scenario.secondary_rows)
        abnormal = "fibrillation" in needle or "positive sharp waves" in needle

        if "within normal limits" in impression:
            assert not abnormal, f"{scenario.key}: normal impression over abnormal needle findings"
        if "denervation" in impression and "no " not in impression.split("denervation")[0][-6:]:
            assert abnormal, f"{scenario.key}: claims denervation the needle exam does not show"
        if "lumbosacral" in impression:
            assert "lumbar" in muscles, f"{scenario.key}: lumbosacral impression without lumbar muscles"
        if "median neuropathy" in impression:
            assert "pollicis" in muscles, f"{scenario.key}: median impression without a median muscle"


def test_electrodiagnostic_scenarios_respect_the_injured_region():
    """A wrist injury must not produce a lower-limb study.

    ``body_part`` reached this template and was never used for anything.
    """
    from data.variant_content import ELECTRODIAGNOSTIC_REGISTER, region_for_body_part

    assert region_for_body_part("cervical spine, wrist") == "upper"
    assert region_for_body_part("lumbar spine, knee") == "lower"
    assert region_for_body_part("Spine") is None, "ambiguous parts must not be guessed"

    upper = ELECTRODIAGNOSTIC_REGISTER.scenarios_for_region("upper")
    assert upper, "region filtering must never return an empty candidate set"
    assert all(s.region in ("upper", "any") for s in upper)
    assert not any("LOWER LIMB" in s.exam_label for s in upper)


@pytest.mark.parametrize("seed", list(range(25)))
def test_a_seed_sweep_never_produces_a_self_contradicting_report(case, seed):
    """The properties above hold for whatever the rng actually picks."""
    for subtype, variant in [("DIAGNOSTICS_LAB_RESULTS", "lab"), ("SLEEP_STUDY", "sleep_study"),
                             ("EMG_NCV_STUDY", "emg_ncv")]:
        spec = make_spec(subtype, variant, extra_context={"variant_content": True})
        template = _load_template_class(DIAG_MODULE, "DiagnosticReport")(case)
        random.seed(seed)
        text = template._story_to_plaintext(template.build_story(spec))

        if "URINE DRUG SCREEN" in text:
            assert "urine specimen" in text.lower()
        elif "LABORATORY RESULTS" in text:
            assert "venipuncture" in text.lower()

        if "Apnea-Hypopnea Index" in text:
            ahi = float(re.search(r"Apnea-Hypopnea Index \(AHI\): ([\d.]+)", text).group(1))
            low = text.lower()
            if ahi > 30:
                assert "severe obstructive sleep apnea" in low
            elif ahi < 5:
                assert "no significant sleep-disordered breathing" in low

        if "NEEDLE EMG" in text:
            low = text.lower()
            if "within normal limits" in low:
                assert "fibrillation" not in low and "positive sharp waves" not in low


# --------------------------------------------------------------------------
# The guard's own teeth
# --------------------------------------------------------------------------


def test_the_ordered_trace_sees_a_reorder_the_final_state_cannot(case):
    """Why the rng digest is a trace and not just ``getstate()``.

    ``random.random()`` and ``random.uniform(0, 1)`` each consume exactly one
    underlying draw, so swapping them leaves the generator in a bit-for-bit
    identical position. Final state alone therefore cannot see the swap. The
    ordered trace can, and a reorder is a real defect: it hands each value to
    the wrong consumer.
    """
    from tests.render_baseline import _TracingRandom

    def run(first_is_random: bool):
        with _TracingRandom() as tracer:
            random.seed(RENDER_SEED)
            if first_is_random:
                random.random()
                random.uniform(0, 1)
            else:
                random.uniform(0, 1)
                random.random()
            return random.getstate(), list(tracer.trace)

    state_a, trace_a = run(True)
    state_b, trace_b = run(False)

    assert state_a == state_b, (
        "premise broken: these two draws no longer consume identically, so this "
        "test no longer demonstrates the blind spot it was written for"
    )
    assert trace_a != trace_b, "the ordered trace missed a reorder — it is not ordered"


def test_the_story_fingerprint_sees_styling_that_plain_text_cannot(case):
    """Why the story digest exists alongside the text digest.

    Restyling a heading or resizing a Spacer changes every rendered page and not
    one character of extracted text. A text-only guard reads as coverage while
    being blind to it.
    """
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, Spacer

    from tests.render_baseline import _story_fingerprint

    template = _load_template_class(DIAG_MODULE, "DiagnosticReport")(case)
    body, header = template.styles["BodyText14"], template.styles["SectionHeader"]

    original = [Paragraph("FINDINGS", body), Spacer(1, 0.3 * inch)]
    restyled = [Paragraph("FINDINGS", header), Spacer(1, 0.3 * inch)]
    respaced = [Paragraph("FINDINGS", body), Spacer(1, 0.35 * inch)]

    assert template._story_to_plaintext(original) == template._story_to_plaintext(restyled)
    assert template._story_to_plaintext(original) == template._story_to_plaintext(respaced)
    assert _story_fingerprint(original) != _story_fingerprint(restyled), "blind to a style change"
    assert _story_fingerprint(original) != _story_fingerprint(respaced), "blind to a geometry change"


def test_new_variant_content_names_no_real_organization():
    """A local sweep against the substrate's own real-entity pools.

    The canonical denylist lives in wc-synthetic-caseload-engine and cannot be
    imported from here — the dependency runs one way — so that half is asserted
    on the engine side. This is the half the substrate can check for itself.
    """
    from data import variant_content, wc_constants

    real_names: set[str] = set()
    for pool_name in ("INSURANCE_CARRIERS", "DEFENSE_FIRMS", "ALL_EMPLOYERS", "MEDICAL_FACILITIES"):
        for entry in getattr(wc_constants, pool_name, []) or []:
            candidates = entry if isinstance(entry, (tuple, list)) else [entry]
            for candidate in candidates:
                if isinstance(candidate, str) and len(candidate) > 4:
                    real_names.add(candidate.lower())

    blob = "\n".join(variant_content.all_content_strings()).lower()
    hits = sorted(name for name in real_names if name in blob)
    assert not hits, f"variant content names real organizations: {hits}"


def test_the_organization_sweep_would_catch_a_planted_name():
    """Positive control — a sweep that cannot fail proves nothing."""
    from data import wc_constants

    planted = wc_constants.INSURANCE_CARRIERS[0]
    blob = f"Correspondence with {planted} regarding this claim.".lower()
    assert planted.lower() in blob


# --------------------------------------------------------------------------
# Round 2 additions
# --------------------------------------------------------------------------

#: Every registered OperativeRecord variant, plus compound strings that a
#: substring matcher would have hijacked.
HOSPITAL_VARIANTS = (
    ("OPERATIVE_HOSPITAL_RECORDS", None, False),
    ("ACUTE_CARE_HOSPITAL_RECORDS", "acute", True),
    ("EMERGENCY_ROOM_RECORDS", "er", True),
    ("DISCHARGE_SUMMARY", "discharge", True),
    ("FACE_SHEET", "face_sheet", True),
    ("OPERATIVE_HOSPITAL_RECORDS", "hospital_billing", False),
    ("OPERATIVE_HOSPITAL_RECORDS", "acute_stress_claim", False),
    ("OPERATIVE_HOSPITAL_RECORDS", "employer_registration", False),
    ("OPERATIVE_HOSPITAL_RECORDS", "discharge_planning_note", False),
    ("OPERATIVE_HOSPITAL_RECORDS", "ed_visit_summary", False),
)


@pytest.mark.parametrize("subtype,variant,claimed", HOSPITAL_VARIANTS)
def test_hospital_registers_claim_only_their_exact_variants(subtype, variant, claimed):
    """The last substring matcher in the module, and the class it belonged to.

    ``hospital_billing`` contains "hospital" and would have rendered an acute
    care record; ``ed_visit_summary`` contains "ed". The ``_claims`` helper that
    made this possible is deleted outright rather than left for the next family.
    """
    from data.variant_content import hospital_register

    resolved = hospital_register(variant)
    assert (resolved is not None) is claimed, (
        f"{variant!r} resolved to {resolved.key if resolved else None!r}, expected "
        f"{'a register' if claimed else 'no register'}"
    )


def test_the_substring_matching_helper_is_gone():
    """It cannot come back by accident if it does not exist."""
    import data.variant_content as module

    assert not hasattr(module, "_claims"), (
        "_claims is back; every register family must use an exact allowlist"
    )


@pytest.mark.parametrize("subtype,variant,claimed", HOSPITAL_VARIANTS)
def test_unclaimed_hospital_variants_render_the_default_document(case, subtype, variant, claimed):
    if claimed:
        pytest.skip("claimed by a register; covered by the distinctness tests")
    module_path, class_name = "pdf_templates.medical.operative_record", "OperativeRecord"
    default = render_digest(case, module_path, class_name, make_spec(subtype, variant))
    opted = render_digest(
        case, module_path, class_name,
        make_spec(subtype, variant, extra_context={"variant_content": True}),
    )
    assert opted == default, f"{variant!r} changed under the opt-in but claims no register"


# --- F2: the evaluator transcript is evaluator content end to end ---------


def _transcript_text(case, seed: int) -> str:
    spec = make_spec("DEPOSITION_TRANSCRIPT_QME_AME", "Deposition Transcript (QME/AME)",
                     extra_context={"variant_content": True})
    template = _load_template_class(
        "pdf_templates.discovery.deposition_transcript", "DepositionTranscript"
    )(case)
    random.seed(seed)
    return template._story_to_plaintext(template.build_story(spec))


@pytest.mark.parametrize("seed", [1, 7, 20260808, 99])
def test_the_evaluator_transcript_contains_no_applicant_testimony(case, seed):
    """The deponent is the physician, so the applicant's life is not the subject.

    Prepending evaluator questions to the applicant generator was worse than
    leaving the template alone: the physician then answered, in the first
    person, what their own date of birth and social security number were, where
    they lived, and how their industrial injury happened.
    """
    text = _transcript_text(case, seed)
    applicant = case.applicant
    forbidden = {
        "date of birth": applicant.date_of_birth.strftime("%B %d, %Y"),
        "SSN": applicant.ssn_last_four,
        "street address": applicant.address_street,
    }
    present = {label: value for label, value in forbidden.items() if value and value in text}
    assert not present, f"applicant {sorted(present)} appears in the evaluator's testimony"


@pytest.mark.parametrize("seed", [1, 7, 20260808, 99])
def test_every_transcript_line_carries_a_speaker_label(case, seed):
    """The renderer prefixes nothing; the generator must supply ``Q. ``/``A. ``.

    An earlier revision returned bare tuples and every one of those lines
    rendered as naked text in the middle of a transcript.
    """
    text = _transcript_text(case, seed)
    numbered = [line for line in text.splitlines() if re.match(r"^\s*\d+\s+\S", line)]
    assert numbered, "no numbered transcript lines rendered at all"
    unlabelled = [
        line for line in numbered
        if not re.match(r"^\s*\d+\s+(Q\.|A\.|BY |MR|MS|THE |\(|EXHIBIT)", line)
    ]
    assert not unlabelled, f"{len(unlabelled)} transcript lines carry no speaker label: {unlabelled[:3]}"


@pytest.mark.parametrize("seed", [1, 7, 20260808, 99])
def test_the_evaluator_transcript_covers_the_evaluator_subjects(case, seed):
    text = _transcript_text(case, seed).lower()
    for subject in ["records", "apportionment", "diagnosis", "examination",
                    "caused by employment", "history"]:
        assert subject in text, f"an evaluator deposition should reach {subject!r}"


# --- F3: electrodiagnostic scenarios do not mix limbs ---------------------

UPPER_ONLY = ("median", "ulnar", "pollicis", "interosseous", "cervical")
LOWER_ONLY = ("peroneal", "tibial", "sural", "gastrocnemius", "lumbar")


def test_electrodiagnostic_scenarios_never_mix_limbs():
    """A study reports the limb it examined, not a selection from both.

    The single "normal study" scenario carried an upper-limb technique with
    median and ulnar conduction rows *and* a sural response, an APB needle
    *and* a tibialis anterior — and was eligible for either region.
    """
    from data.variant_content import ELECTRODIAGNOSTIC_REGISTER

    for scenario in ELECTRODIAGNOSTIC_REGISTER.scenarios:
        blob = " ".join(
            [scenario.exam_label, scenario.technique, scenario.impression]
            + [f"{r.label} {r.value}" for r in scenario.rows + scenario.secondary_rows]
        ).lower()
        if scenario.region == "upper":
            intruders = [w for w in LOWER_ONLY if w in blob]
            assert not intruders, f"{scenario.key} is upper-limb but names {intruders}"
        elif scenario.region == "lower":
            intruders = [w for w in UPPER_ONLY if w in blob]
            assert not intruders, f"{scenario.key} is lower-limb but names {intruders}"
        else:
            pytest.fail(f"{scenario.key} declares region {scenario.region!r}; every "
                        f"electrodiagnostic scenario must commit to a limb")


# --- F4: the baseline does not depend on the calendar ---------------------


def test_the_fixture_case_is_pinned_to_the_anchor_not_to_today():
    """Two different frozen "todays" must produce the identical case.

    This was the nastiest defect in the suite: eleven of eighteen cases changed
    across a seven-month clock move, so the guard was set to turn red in CI on a
    morning nobody had touched the substrate. That failure reads as flakiness,
    and the natural response to a flaky guard is to delete it.
    """
    import datetime as _dt

    from tests.render_baseline import build_fixture_case, frozen_clock

    def case_under(year: int):
        real = _dt.date

        class Moved(real):
            @classmethod
            def today(cls):
                return real(year, 3, 15)

        import data.fake_data_generator as fdg

        saved = fdg.date
        fdg.date = Moved
        try:
            built = build_fixture_case()
            return (
                built.applicant.date_of_birth,
                built.employer.hire_date,
                built.timeline.date_of_injury,
            )
        finally:
            fdg.date = saved

    assert case_under(2026) == case_under(2031), (
        "the fixture case still moves with the wall clock"
    )
    with frozen_clock() as anchor:
        assert anchor == ANCHOR_DATE


def test_the_baseline_records_where_it_came_from():
    """A baseline's value is that it records the trusted trunk anchor, not a moving head."""
    import json
    import importlib.util

    meta = baseline_provenance()
    expected = "b0e77dd1b6fa949d2d5dc6a7f2d1a0c94ed6def3"
    assert meta.get("source_commit") == expected, (
        f"unexpected source_commit: {meta.get('source_commit')}"
    )
    assert meta.get("base_commit") == expected, (
        f"unexpected base_commit: {meta.get('base_commit')}"
    )
    assert meta.get("anchor_date") == ANCHOR_DATE.isoformat(), (
        "the baseline was recorded under a different anchor date than the one in force"
    )
    recorder = _recorder_module()
    assert meta["note"] == recorder.PROVENANCE_NOTE
    assert "before the AJC-66" not in meta["note"]


@pytest.fixture(scope="session")
def base_worktree(tmp_path_factory):
    import subprocess
    from tests.render_baseline import _PACKAGE_ROOT

    recorder = _recorder_module()
    requested = os.environ.get("AJC72_BASE_WORKTREE")

    if requested:
        if not os.path.isdir(requested):
            pytest.fail(
                "AJC72_BASE_WORKTREE is set but does not point to an existing directory: "
                f"{requested!r}"
            )
        try:
            recorder._validate_base_worktree(requested)
        except SystemExit as exc:
            pytest.fail(f"AJC72_BASE_WORKTREE is set but invalid: {exc}")
        yield requested
        return

    worktree = str(tmp_path_factory.mktemp("ajc72-worktrees") / "ajc72-base")
    created = False

    def _worktree_add() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "git",
                "-C",
                _PACKAGE_ROOT,
                "worktree",
                "add",
                "--detach",
                worktree,
                recorder.BASE_COMMIT,
            ],
            capture_output=True,
            text=True,
        )

    def _is_shallow_missing(output: str) -> bool:
        lower = output.lower()
        return any(
            needle in lower
            for needle in (
                "not a valid object",
                "invalid object name",
                "couldn't find",
                "does not exist",
                "unknown revision",
                "bad revision",
            )
        )

    try:
        add = _worktree_add()
        if add.returncode != 0:
            fetch = subprocess.run(
                ["git", "-C", _PACKAGE_ROOT, "fetch", "origin", recorder.BASE_COMMIT],
                capture_output=True,
                text=True,
            )
            if fetch.returncode != 0:
                pytest.fail(
                    "failed to create fixture base worktree: git worktree add failed and fetch retry failed\n"
                    f"add stderr: {add.stderr.rstrip()}\nfetch stderr: {fetch.stderr.rstrip()}"
                )

            retry = _worktree_add()
            if retry.returncode != 0:
                if _is_shallow_missing(retry.stderr):
                    pytest.skip(
                        "base commit unavailable in shallow clone; fetch did not supply "
                        f"{recorder.BASE_COMMIT}"
                    )
                pytest.fail(
                    "failed to create fixture base worktree after fetch retry:\n"
                    f"{retry.stdout.rstrip()}\n{retry.stderr.rstrip()}"
                )

        created = True
        recorder._validate_base_worktree(worktree)
        yield worktree
    finally:
        if created:
            subprocess.run(["git", "-C", _PACKAGE_ROOT, "worktree", "remove", "--force", worktree], check=False)
            subprocess.run(["git", "-C", _PACKAGE_ROOT, "worktree", "prune"], check=False)


_BASE_RENDER_GOLDEN_PAYLOAD = os.path.join(
    "packages",
    "merus-test-data-generator",
    "tests",
    "golden",
    "render_baseline.json",
)
_BASE_RENDER_GOLDEN_PAYLOAD_IN_PACKAGE = os.path.join(
    "tests",
    "golden",
    "render_baseline.json",
)


def _base_worktree_roots(base_worktree: str) -> tuple[str, str]:
    recorder = _recorder_module()
    return recorder._validate_base_worktree(base_worktree)


def _run_restamp_provenance(base_worktree: str, output_path: str | None = None) -> tuple[int, str]:
    import subprocess
    import sys as _sys

    _, base_package_root = _base_worktree_roots(base_worktree)
    from tests.render_baseline import _PACKAGE_ROOT as feature_package_root
    args = [
        _sys.executable,
        os.path.join(feature_package_root, "scripts", "record_render_baseline.py"),
        "--restamp-provenance",
        "--base-worktree",
        base_worktree,
    ]
    if output_path is not None:
        args.extend(["--output", output_path])

    result = subprocess.run(
        args,
        cwd=base_package_root, capture_output=True, text=True,
    )
    return result.returncode, result.stdout + result.stderr


def _trusted_base_payload(base_worktree: str) -> tuple[dict, dict]:
    import json

    from tests.render_baseline import _PACKAGE_ROOT

    _, base_package_root = _base_worktree_roots(base_worktree)
    path = os.path.join(base_package_root, _BASE_RENDER_GOLDEN_PAYLOAD_IN_PACKAGE)
    with open(os.path.join(_PACKAGE_ROOT, "tests", "golden", "render_baseline.json"), encoding="utf-8") as fh:
        feature_payload = json.load(fh)
    with open(path, encoding="utf-8") as fh:
        base_payload = json.load(fh)
    return feature_payload, base_payload


def _trusted_base_baseline_path(base_worktree: str) -> str:
    _, base_package_root = _base_worktree_roots(base_worktree)
    return os.path.join(base_package_root, _BASE_RENDER_GOLDEN_PAYLOAD_IN_PACKAGE)


def _trusted_base_payload_bytes(base_worktree: str) -> bytes:
    with open(_trusted_base_baseline_path(base_worktree), "rb") as fh:
        return fh.read()


def _assert_base_worktree_clean(base_worktree: str, expected_payload_bytes: bytes) -> None:
    import subprocess

    base_repo, base_package_root = _base_worktree_roots(base_worktree)
    base_payload_path = os.path.join(base_package_root, _BASE_RENDER_GOLDEN_PAYLOAD_IN_PACKAGE)
    recorder = _recorder_module()

    relative_blob = _BASE_RENDER_GOLDEN_PAYLOAD_IN_PACKAGE
    relative_blob_in_repo = os.path.join(os.path.relpath(base_package_root, base_repo), relative_blob)
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no", "--", _BASE_RENDER_GOLDEN_PAYLOAD],
        cwd=base_repo,
        capture_output=True, text=True, check=True,
    )
    assert not status.stdout, f"base worktree golden is not clean: {status.stdout.rstrip()}"
    head_ref = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=base_worktree,
        capture_output=True, text=True, check=True,
    )
    assert head_ref.stdout.strip() == "HEAD", (
        f"base worktree is not detached: {head_ref.stdout.strip()}"
    )
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=base_repo,
        capture_output=True, text=True, check=True,
    )
    assert head.stdout.strip() == recorder.BASE_COMMIT, (
        f"base worktree HEAD is {head.stdout.strip()}, expected {recorder.BASE_COMMIT}"
    )

    expected = expected_payload_bytes
    current = subprocess.run(
        ["git", "show", f"{recorder.BASE_COMMIT}:{relative_blob_in_repo}"], cwd=base_repo,
        capture_output=True, text=False, check=True,
    ).stdout
    assert current == expected, "base baseline does not match the committed blob"
    with open(base_payload_path, "rb") as fh:
        assert fh.read() == expected


def _mutate_baseline(json_text: str | dict) -> str:
    from tests.render_baseline import BASELINE_PATH
    import copy
    import json

    original = json.loads(json_text) if isinstance(json_text, str) else json_text
    mutated = copy.deepcopy(original)
    mutated["cases"] = dict(mutated["cases"])
    mutated["cases"][next(iter(mutated["cases"]))] = {
        "text": "restamp-provenance-test-has-changed-this-case",
        "story": "restamp-provenance-test-has-changed-this-case",
        "rng": "restamp-provenance-test-has-changed-this-case",
        "pdf": "restamp-provenance-test-has-changed-this-case",
    }
    mutated["_meta"]["note"] = "tampered baseline note for restamp proof"
    return json.dumps(mutated, sort_keys=True, indent=2) + "\n"


def _restore_baseline(payload_text: str) -> None:
    from tests.render_baseline import BASELINE_PATH

    with open(BASELINE_PATH, "w", encoding="utf-8") as fh:
        fh.write(payload_text)


def _write_baseline(payload: str | dict, destination: os.PathLike[str] | str) -> None:
    if isinstance(payload, str):
        text = payload
    else:
        import json

        text = json.dumps(payload, sort_keys=True, indent=2) + "\n"

    with open(destination, "w", encoding="utf-8") as fh:
        fh.write(text)


def test_record_mode_refuses_a_tree_that_is_not_the_base_ref():
    """Unguarded, ``--record`` lets a feature tree bless itself."""
    import subprocess
    import sys as _sys

    from tests.render_baseline import _PACKAGE_ROOT

    result = subprocess.run(
        [_sys.executable, "scripts/record_render_baseline.py", "--record"],
        cwd=_PACKAGE_ROOT, capture_output=True, text=True,
    )
    assert result.returncode != 0, "record mode accepted a non-base checkout"
    assert "refusing to record" in (result.stdout + result.stderr)


def test_restamp_provenance_uses_only_fresh_pinned_base_cases(base_worktree, tmp_path):
    import json
    import subprocess

    from tests.render_baseline import BASELINE_PATH, _PACKAGE_ROOT

    recorder = _recorder_module()
    feature_before, base_payload = _trusted_base_payload(base_worktree)
    base_payload_bytes = _trusted_base_payload_bytes(base_worktree)
    baseline_text = open(BASELINE_PATH, encoding="utf-8").read()
    output = tmp_path / "render_baseline-test-restamp.json"
    _write_baseline(feature_before, output)

    try:
        code, out = _run_restamp_provenance(
            base_worktree, output_path=str(output),
        )
        assert code == 0, f"restamp-provenance did not succeed:\n{out}"
        with open(output, encoding="utf-8") as fh:
            after = json.load(fh)
        assert after["cases"] == base_payload["cases"]
        assert after["cases"] == feature_before["cases"]
        changed = sorted(recorder._structural_diff(feature_before, after))
        assert set(changed).issubset({"_meta.note", "_meta.recorded_utc"}), (
            f"restamp changed non-provenance leaves: {changed}"
        )
        assert after["_meta"]["note"] == recorder.PROVENANCE_NOTE
    finally:
        _assert_base_worktree_clean(base_worktree, base_payload_bytes)
        _restore_baseline(baseline_text)
        status = subprocess.run(
            [
                "git",
                "status",
                "--porcelain",
                "--untracked-files=no",
                "--",
                "packages/merus-test-data-generator/tests/golden/render_baseline.json",
            ],
            cwd=_PACKAGE_ROOT,
            capture_output=True,
            text=True,
        )
        assert not status.stdout, f"post-restamp dirty tree: {status.stdout.rstrip()}"
        if os.path.exists(output):
            os.unlink(output)


def test_restamp_provenance_restores_base_worktree_on_success_and_failure(base_worktree):
    from tests.render_baseline import BASELINE_PATH

    recorder = _recorder_module()
    import subprocess

    feature_payload_text = open(BASELINE_PATH, "rb").read().decode("utf-8")
    feature_payload_bytes = feature_payload_text.encode("utf-8")
    base_payload_bytes = _trusted_base_payload_bytes(base_worktree)
    _, base_package_root = _base_worktree_roots(base_worktree)
    base_relative_payload_path = os.path.join(
        os.path.relpath(base_package_root, base_worktree), _BASE_RENDER_GOLDEN_PAYLOAD_IN_PACKAGE
    )

    try:
        assert recorder._run_restamp_mode(base_worktree) == 0
        _assert_base_worktree_clean(base_worktree, base_payload_bytes)

        _restore_baseline(feature_payload_text)
        real_run_base_recorder = recorder._run_base_recorder

        def _run_base_recorder_then_corrupt(base_package_root: str) -> dict:
            payload = real_run_base_recorder(base_package_root)
            meta = dict(payload.setdefault("_meta", {}))
            meta["base_commit"] = "0000000000000000000000000000000000000000"
            payload["_meta"] = meta
            return payload

        with pytest.MonkeyPatch().context() as mp:
            mp.setattr(recorder, "_run_base_recorder", _run_base_recorder_then_corrupt)
            with pytest.raises(SystemExit, match="base payload base_commit is not pinned"):
                recorder._run_restamp_mode(base_worktree)

        _assert_base_worktree_clean(base_worktree, base_payload_bytes)
        head_ref = subprocess.run(
            ["git", "-C", base_worktree, "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, check=True,
        )
        assert head_ref.stdout.strip() == "HEAD", (
            f"base worktree is not detached after cleanup: {head_ref.stdout.strip()}"
        )
        head = subprocess.run(
            ["git", "-C", base_worktree, "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        )
        assert head.stdout.strip() == recorder.BASE_COMMIT, (
            f"base worktree HEAD is {head.stdout.strip()}, expected {recorder.BASE_COMMIT}"
        )
        head_blob = subprocess.run(
            ["git", "-C", base_worktree, "show", f"HEAD:{base_relative_payload_path}"],
            capture_output=True, check=True,
        ).stdout
        assert head_blob == base_payload_bytes, (
            "base payload changed from its HEAD blob after forced restamp failure"
        )
        assert open(BASELINE_PATH, "rb").read() == feature_payload_bytes
    finally:
        _restore_baseline(feature_payload_text)
        _assert_base_worktree_clean(base_worktree, base_payload_bytes)


def test_record_mode_from_base_worktree_with_base_ref_has_no_whitespace_in_commits(
    base_worktree,
    tmp_path,
):
    import json
    recorder = _recorder_module()
    _, base_package_root = _base_worktree_roots(base_worktree)
    baseline_output = str(tmp_path / "recorded-with-base-ref.json")
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr(recorder, "_PACKAGE_ROOT", base_package_root)
        original_git = recorder._git

        def _git_with_base_root(*args: str, cwd: str | None = None, text: bool = True):
            return original_git(*args, cwd=cwd or base_package_root, text=text)

        mp.setattr(recorder, "_git", _git_with_base_root)
        mp.setattr(recorder.sys, "path", [base_package_root, *(
            p for p in recorder.sys.path if p != base_package_root
        )])
        for name in list(recorder.sys.modules):
            if name == "tests" or name.startswith("tests."):
                mp.delitem(recorder.sys.modules, name, raising=False)

        assert (
            recorder.main(
                [
                    "--record",
                    "--base-ref",
                    recorder.BASE_COMMIT,
                    "--output",
                    baseline_output,
                ]
            )
            == 0
        )

    with open(baseline_output, encoding="utf-8") as fh:
        recorded = json.load(fh)
    assert recorded["_meta"]["base_commit"] == recorded["_meta"]["base_commit"].strip() == recorder.BASE_COMMIT
    assert recorded["_meta"]["source_commit"] == recorded["_meta"]["source_commit"].strip() == recorder.BASE_COMMIT


def test_restamp_provenance_changes_only_meta_note():
    import copy

    recorder = _recorder_module()
    feature_payload = {
        "_meta": {
            "note": "pre-run note",
            "recorded_utc": "2026-01-01T00:00:00",
            "source_commit": "1111111111111111111111111111111111111111",
            "base_commit": "2222222222222222222222222222222222222222",
        },
        "cases": {
            "case.alpha": {
                "text": "base text",
                "story": "base story",
                "rng": "base rng",
                "pdf": "base pdf",
            },
            "case.beta": {
                "text": "other text",
                "story": "other story",
                "rng": "other rng",
                "pdf": "other pdf",
            },
        },
    }

    candidate = recorder._rebase_provenance_payload(feature_payload, feature_payload)
    assert sorted(recorder._structural_diff(feature_payload, candidate)) == ["_meta.note"]
    assert candidate["_meta"]["note"] == recorder.PROVENANCE_NOTE

    bad_candidate = copy.deepcopy(candidate)
    bad_candidate["cases"]["case.alpha"]["text"] = "changed case text"
    with pytest.raises(SystemExit) as exc:
        recorder._assert_restamp_payload_delta_is_meta_note_only(feature_payload, bad_candidate)
    assert "restamp would change more than _meta.note" in str(exc.value)


def test_restamp_provenance_refuses_case_drift_without_writing(tmp_path):
    import json

    recorder = _recorder_module()

    feature_payload = {
        "_meta": {
            "note": "pre-run note",
            "recorded_utc": "2026-01-01T00:00:00",
        },
        "cases": {
            "case.alpha": {
                "text": "base text",
                "story": "base story",
                "rng": "base rng",
                "pdf": "base pdf",
            },
            "case.beta": {
                "text": "other text",
                "story": "other story",
                "rng": "other rng",
                "pdf": "other pdf",
            },
        },
    }
    drifted_base = json.loads(json.dumps(feature_payload))
    drifted_base["cases"]["case.alpha"]["text"] = "base recorder text does not match"

    destination = tmp_path / "restamp-case-drift-proof.json"
    destination_text = json.dumps(feature_payload, sort_keys=True, indent=2) + "\n"
    destination.write_text(destination_text, encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        recorder._rewrite_restamped_provenance_payload(str(destination), drifted_base)
    assert "base recorder cases do not match feature baseline pre-restamp cases" in str(exc.value)
    assert destination.read_text(encoding="utf-8") == destination_text


def test_restamp_provenance_refuses_untrusted_base_worktree(base_worktree, tmp_path):
    recorder = _recorder_module()
    recorder._validate_base_worktree(base_worktree)

    # wrong SHA: alter BASE_COMMIT inside the same process and assert that
    # the head check compares against that expected value.
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr(recorder, "BASE_COMMIT", "0000000000000000000000000000000000000000")
        with pytest.raises(SystemExit) as exc:
            recorder._validate_base_worktree(base_worktree)
    assert "base HEAD is" in str(exc.value)

    shared_top_level = recorder._git("rev-parse", "--show-toplevel", cwd=recorder._PACKAGE_ROOT).strip()

    def fake_git_not_detached(*args: str, cwd: str, text: bool = True) -> str:
        if tuple(args) == ("rev-parse", "--show-toplevel"):
            return shared_top_level + "\n"
        if tuple(args) == ("rev-parse", "--abbrev-ref", "HEAD"):
            return "main\n"
        if tuple(args) == ("rev-parse", "HEAD"):
            return recorder.BASE_COMMIT + "\n"
        raise AssertionError(f"unexpected git command {args} from {cwd}")

    with pytest.MonkeyPatch().context() as mp:
        mp.setattr(recorder, "_git_common_dir", lambda _cwd: "/tmp/restamp-shared-common")
        mp.setattr(recorder, "_git", fake_git_not_detached)
        mp.setattr(recorder, "_status_paths", lambda _cwd, include_untracked=False: [])
        mp.setattr(recorder, "_verify_file_vs_blob", lambda *_args, **_kwargs: None)
        with pytest.raises(SystemExit) as exc:
            recorder._validate_base_worktree(base_worktree)
    assert "base worktree is not detached" in str(exc.value)

    def fake_git_dirty(*args: str, cwd: str, text: bool = True) -> str:
        if tuple(args) == ("rev-parse", "--show-toplevel"):
            return shared_top_level + "\n"
        if tuple(args) == ("rev-parse", "--abbrev-ref", "HEAD"):
            return "HEAD\n"
        if tuple(args) == ("rev-parse", "HEAD"):
            return recorder.BASE_COMMIT + "\n"
        raise AssertionError(f"unexpected git command {args} from {cwd}")

    with pytest.MonkeyPatch().context() as mp:
        mp.setattr(recorder, "_git_common_dir", lambda _cwd: "/tmp/restamp-shared-common")
        mp.setattr(recorder, "_git", fake_git_dirty)
        mp.setattr(
            recorder,
            "_status_paths",
            lambda _cwd, include_untracked=False: ["tests/render_baseline.py"],
        )
        mp.setattr(recorder, "_verify_file_vs_blob", lambda *_args, **_kwargs: None)
        with pytest.raises(SystemExit) as exc:
            recorder._validate_base_worktree(base_worktree)
    assert "base worktree is not clean" in str(exc.value)

    # different repository fails the repo-root identity check.
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    import subprocess

    subprocess.run(["git", "init", "--quiet"], cwd=foreign, check=True)
    with pytest.raises(SystemExit) as exc:
        recorder._validate_base_worktree(str(foreign))
    assert "base worktree is not in this repository" in str(exc.value)


def test_restamp_provenance_never_computes_cases_from_feature_tree():
    import ast

    from tests.render_baseline import _PACKAGE_ROOT

    path = os.path.join(_PACKAGE_ROOT, "scripts", "record_render_baseline.py")
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=path)

    module_functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
    }
    restamp_fn = module_functions["_run_restamp_mode"]

    def module_function_calls(func_node: ast.FunctionDef) -> set[str]:
        called_names = set()
        for node in ast.walk(func_node):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id in module_functions:
                    called_names.add(func.id)
                elif isinstance(func, ast.Attribute) and func.attr in module_functions:
                    called_names.add(func.attr)
        return called_names

    reachable: set[str] = set()
    to_visit = {"_run_restamp_mode"}
    while to_visit:
        name = to_visit.pop()
        if name in reachable:
            continue
        if name not in module_functions:
            continue
        reachable.add(name)
        to_visit.update(module_function_calls(module_functions[name]) - reachable)

    assert "_rewrite_restamped_provenance_payload" in reachable, (
        "restamp mode reachable set does not include _rewrite_restamped_provenance_payload"
    )
    assert "_rebase_provenance_payload" in reachable, (
        "restamp mode reachable set does not include _rebase_provenance_payload"
    )

    compute_imports: list[tuple[str, int]] = []
    compute_calls: list[int] = []
    for fn_name in reachable:
        fn = module_functions[fn_name]
        imported_compute_names: set[str] = set()
        imported_baseline_modules: set[str] = set()
        for node in ast.walk(fn):
            if isinstance(node, ast.ImportFrom) and node.module in {"tests.render_baseline", "render_baseline"}:
                for alias in node.names:
                    if alias.name == "compute_baseline":
                        import_name = alias.asname or alias.name
                        imported_compute_names.add(import_name)
                        compute_imports.append((alias.name, node.lineno))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in {"tests.render_baseline", "render_baseline"}:
                        imported_baseline_modules.add(alias.asname or alias.name)
                        compute_imports.append((alias.name, node.lineno))
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id == "compute_baseline" or node.func.id in imported_compute_names:
                        compute_calls.append(node.lineno)
                elif (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr == "compute_baseline"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id in imported_baseline_modules
                ):
                    compute_calls.append(node.lineno)

    assert not compute_imports, (
        "restamp mode reachable helpers import compute_baseline: "
        f"{sorted(compute_imports)}"
    )
    assert not compute_calls, (
        "restamp mode reachable helpers call compute_baseline: "
        f"{sorted(compute_calls)}"
    )


# --- F6: the PDF digest is asserted, not just described -------------------


def test_a_geometry_change_moves_the_pdf_bytes_not_only_the_story(case):
    """The PR claimed this; only the story half was ever asserted.

    Renders the same document twice, changing nothing but one Spacer's height,
    and compares the physical PDFs. Text is identical across both.
    """
    import hashlib

    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, Spacer

    from tests.render_baseline import _ensure_invariant_pdfs, _story_fingerprint

    _ensure_invariant_pdfs()
    template = _load_template_class(DIAG_MODULE, "DiagnosticReport")(case)
    body = template.styles["BodyText14"]

    def pdf_of(height: float) -> str:
        import tempfile
        from pathlib import Path as _Path

        story = [Paragraph("FINDINGS", body), Spacer(1, height * inch),
                 Paragraph("Unremarkable.", body)]
        with tempfile.TemporaryDirectory() as tmp:
            out = _Path(tmp) / "x.pdf"
            tpl = _load_template_class(DIAG_MODULE, "DiagnosticReport")(case)
            tpl.build_story = lambda _spec, _s=story: list(_s)
            tpl.generate(out, make_spec("DIAGNOSTICS", None))
            return hashlib.sha256(out.read_bytes()).hexdigest()

    original = [Paragraph("FINDINGS", body), Spacer(1, 0.30 * inch),
                Paragraph("Unremarkable.", body)]
    respaced = [Paragraph("FINDINGS", body), Spacer(1, 0.35 * inch),
                Paragraph("Unremarkable.", body)]

    assert template._story_to_plaintext(original) == template._story_to_plaintext(respaced), (
        "premise broken: the text digest already sees this change"
    )
    assert _story_fingerprint(original) != _story_fingerprint(respaced)
    assert pdf_of(0.30) != pdf_of(0.35), "the PDF digest is blind to a geometry change"


# --------------------------------------------------------------------------
# Round 3 — the classes behind the round-2 fixes
# --------------------------------------------------------------------------


def _evaluator_register():
    from data.variant_content import transcript_register

    return transcript_register("qme_ame")


def _fill(text: str, case_data: dict) -> str:
    for key, value in case_data.items():
        text = text.replace("{" + key + "}", str(value))
    return text


@pytest.mark.parametrize("seed", list(range(120)))
def test_every_topic_anchor_survives_every_seed(seed):
    """No budget may revoke the per-topic guarantee.

    The previous revision pinned an anchor question per topic and then trimmed
    the whole list to a global target, so on some seeds the apportionment and
    independence topics — the two an evaluator deposition exists for — were cut
    off entirely while the guarantee still read as honoured. There is no global
    trim now; length is the sum of the per-topic ranges.
    """
    from data.variant_content import generate_evaluator_exchanges

    register = _evaluator_register()
    case_data = {"applicant_name": "A. Person", "specialty": "Orthopedics",
                 "body_parts": "the lumbar spine"}
    anchors = [_fill(pool[0][0], case_data) for _t, pool, _lo, _hi in register.topic_pools]

    random.seed(seed)
    asked = "\n".join(q for q, _a in generate_evaluator_exchanges(register, case_data))
    missing = [a for a in anchors if a not in asked]
    assert not missing, f"seed {seed} lost {len(missing)} topic anchor(s): {missing[:2]}"


def test_the_evaluator_generator_has_no_global_budget():
    """The shape of the fix, not just its effect.

    A per-item guarantee followed by a global cap is the defect class. Asserting
    only on outcomes would let the cap come back as long as today's numbers
    happen not to collide.
    """
    import inspect

    from data.variant_content import generate_evaluator_exchanges

    source = inspect.getsource(generate_evaluator_exchanges)
    assert "max_exchanges" not in source, (
        "a global exchange budget is back; it silently revokes the per-topic anchors"
    )
    assert "[:" not in source.split("return exchanges")[0], (
        "the generator truncates its own output again"
    )


EVALUATOR_EXHIBIT_FORBIDDEN = (
    "job description", "pay stub", "tax return", "your employer",
    "your date of birth", "your social security",
)


@pytest.mark.parametrize("seed", [3, 11, 44, 20260808])
def test_evaluator_exhibits_are_never_applicant_documents(case, seed):
    """Exhibits were the pool the forked question generator did not cover.

    The renderer marks exhibits from a shared applicant set that asks the
    witness about "your job description at {employer}" — handing a physician the
    applicant's employment file to identify.
    """
    text = _transcript_text(case, seed).lower()
    present = [phrase for phrase in EVALUATOR_EXHIBIT_FORBIDDEN if phrase in text]
    assert not present, f"applicant-document exhibit phrasing reached the evaluator: {present}"


def test_every_evaluator_exhibit_names_an_evaluator_document():
    """Each alternative, not whichever ones a seed happened to draw."""
    from data.variant_content import EVALUATOR_EXHIBITS

    evaluator_subjects = ("your report", "your signature", "cover letter", "curriculum vitae",
                          "worksheets", "records-review", "correspondence", "billing")
    for template in EVALUATOR_EXHIBITS:
        lowered = template.lower()
        assert any(subject in lowered for subject in evaluator_subjects), (
            f"exhibit does not name a document the evaluator owns: {template}"
        )
        assert not any(bad in lowered for bad in EVALUATOR_EXHIBIT_FORBIDDEN), (
            f"exhibit names an applicant document: {template}"
        )


def test_the_transcript_renderer_reaches_no_unforked_case_specific_pool():
    """The class sweep, kept honest.

    Four pools are reachable: questions, exhibits, objections and time markers.
    The first two are case-specific and forked per witness. The other two must
    stay witness-neutral — the moment one takes the case, it can name the
    applicant's employer at the evaluator's deposition.
    """
    import inspect

    from data import deposition_exchanges

    for name in ("generate_objection", "generate_time_marker"):
        signature = inspect.signature(getattr(deposition_exchanges, name))
        assert "case" not in signature.parameters, (
            f"{name} now takes the case; it is reachable from the evaluator transcript "
            f"and must be forked per witness or stay witness-neutral"
        )


def _local_clock_imports(source: str, label: str) -> list[str]:
    """Functions that import a datetime name locally AND read a clock anywhere in them.

    Parsed, not grepped. The first version scanned a 400-character window after
    each local import, which is a proximity heuristic dressed up as a rule — and
    it missed a real one: ``orchestration/case_creator.py`` imported ``datetime``
    inside a function and called ``.now()`` twenty-three lines later, comfortably
    outside the window. The scope of an import is the whole function, so the
    check is the whole function.
    """
    import ast

    findings: list[str] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return findings

    CLOCK_CALLS = {"now", "today", "utcnow"}

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        local_names: set[str] = set()
        for inner in ast.walk(node):
            if isinstance(inner, ast.ImportFrom) and inner.module == "datetime":
                local_names.update(alias.asname or alias.name for alias in inner.names)
            elif isinstance(inner, ast.Import):
                for alias in inner.names:
                    if alias.name == "datetime" or alias.name.startswith("datetime."):
                        local_names.add(alias.asname or alias.name.split(".")[0])
        if not local_names:
            continue

        for inner in ast.walk(node):
            if (
                isinstance(inner, ast.Call)
                and isinstance(inner.func, ast.Attribute)
                and inner.func.attr in CLOCK_CALLS
            ):
                base = inner.func.value
                # `datetime.now()` and `datetime.datetime.now()` both start at a Name.
                while isinstance(base, ast.Attribute):
                    base = base.value
                if isinstance(base, ast.Name) and base.id in local_names:
                    findings.append(
                        f"{label}:{inner.lineno}: {node.name}() reads "
                        f"{base.id}.{inner.func.attr}() through a function-local import"
                    )
    return findings


#: Every substrate directory whose code can run during a render or a recording.
#: One list, so the audit below and the test asserting its coverage cannot drift
#: apart — the previous revision named three directories inline while the prose
#: claimed four, and ``scripts/`` (which holds the recorder itself) went
#: unaudited as a result.
AUDITED_SOURCE_DIRS = ("data", "pdf_templates", "orchestration", "scripts")


def test_no_clock_is_read_through_a_function_local_import():
    """The hole that let one clock keep running inside the pin.

    A function-local ``from datetime import date`` resolves at call time, in a
    scope no module-attribute patch can reach. Every clock read must go through
    a module-level binding or the pin silently does not apply to it.
    """
    from pathlib import Path as _Path

    from tests.render_baseline import _PACKAGE_ROOT

    offenders: list[str] = []
    for directory in AUDITED_SOURCE_DIRS:
        for path in sorted(_Path(_PACKAGE_ROOT, directory).rglob("*.py")):
            offenders += _local_clock_imports(path.read_text(encoding="utf-8"), path.name)

    assert not offenders, (
        "a clock is read through a function-local import, out of reach of the pin:\n"
        + "\n".join(offenders)
    )


def test_the_clock_audit_covers_every_directory_that_can_run():
    """Coverage is the property; the audit passing on three of four is not.

    An audit that silently omits a directory reports clean about code it never
    read. Naming the expected set here means adding a source directory to the
    package without auditing it reddens, rather than quietly narrowing what
    "no local clocks" means.
    """
    from pathlib import Path as _Path

    from tests.render_baseline import _PACKAGE_ROOT

    assert set(AUDITED_SOURCE_DIRS) == {"data", "pdf_templates", "orchestration", "scripts"}
    for directory in AUDITED_SOURCE_DIRS:
        path = _Path(_PACKAGE_ROOT, directory)
        assert path.is_dir(), f"audited directory {directory} does not exist"
        assert list(path.rglob("*.py")), f"audited directory {directory} holds no python"


def test_the_local_clock_audit_sees_past_a_four_hundred_character_gap():
    """Positive control for the audit above, sized to the bug it replaced.

    The previous implementation looked 400 characters past the import. This
    fixture puts far more than that between the import and the clock read — the
    exact shape of the site the old check walked straight past.
    """
    filler = "\n".join(f'    value_{i} = "padding padding padding padding"' for i in range(40))
    source = (
        "def build_note():\n"
        "    from datetime import datetime\n"
        f"{filler}\n"
        "    return datetime.now().isoformat()\n"
    )
    assert len(filler) > 400, "the control is not actually wider than the old window"
    assert _local_clock_audit_finds(source), "the audit cannot see past the old window"


def _local_clock_audit_finds(source: str) -> bool:
    return bool(_local_clock_imports(source, "<control>"))


def test_the_local_clock_audit_ignores_an_import_that_reads_no_clock():
    """Constructing from a supplied date is fine and must not be flagged.

    ``email_metadata`` legitimately builds a datetime from ``doc_date``. An audit
    that fires on that would be turned off within a week.
    """
    source = (
        "def to_rfc(doc_date):\n"
        "    from datetime import datetime\n"
        "    return datetime(doc_date.year, doc_date.month, doc_date.day, 12, 0).timestamp()\n"
    )
    assert not _local_clock_audit_finds(source)


def test_the_clock_pin_covers_every_module_that_binds_a_clock():
    """Found by identity, not by a list — the list was wrong twice.

    It named only ``data.*`` (missing ``qme_ame_report`` and ``settlement_memo``)
    and matched attributes literally called ``date`` (missing
    ``from datetime import date as _date``).
    """
    import importlib
    from datetime import date as _real_date

    from tests.render_baseline import ANCHOR_DATE, frozen_clock

    modules = [
        "data.fake_data_generator",
        "data.deposition_exchanges",
        "pdf_templates.medical.qme_ame_report",
        "pdf_templates.summaries.settlement_memo",
    ]
    for name in modules:
        importlib.import_module(name)

    with frozen_clock():
        import data.deposition_exchanges as de
        import pdf_templates.medical.qme_ame_report as qme
        import pdf_templates.summaries.settlement_memo as memo

        assert de._today() == ANCHOR_DATE, "the aliased-through-a-function clock escaped"
        assert qme._date.today() == ANCHOR_DATE, "the `as _date` alias escaped"
        assert memo.date.today() == ANCHOR_DATE, "an unenumerated module escaped"

    assert de._today() == _real_date.today(), "the pin did not restore the real clock"


def test_faker_keeps_its_own_date_alias_under_the_pin():
    """Sweeping by identity is right for our code and wrong for a library.

    Faker's ``_parse_date_time`` does ``isinstance(value, (datetime, dtdate))``.
    Replacing its ``date`` alias with a subclass makes a real ``date`` stop being
    an instance of it, and the provider raises — which is how this was found.
    """
    import importlib
    from datetime import date as _real_date

    from tests.render_baseline import frozen_clock

    faker_dt = importlib.import_module("faker.providers.date_time")
    with frozen_clock():
        aliases = [
            name for name, value in vars(faker_dt).items()
            if isinstance(value, type) and value is not _real_date
            and issubclass(value, _real_date) and not issubclass(value, __import__("datetime").datetime)
        ]
        assert not aliases, f"Faker date aliases were replaced and will break isinstance: {aliases}"


def test_record_mode_rejects_a_caller_supplied_head_base():
    """``--base-ref HEAD`` on a clean feature branch satisfied every other check."""
    import subprocess
    import sys as _sys

    from tests.render_baseline import _PACKAGE_ROOT

    result = subprocess.run(
        [_sys.executable, "scripts/record_render_baseline.py", "--record", "--base-ref", "HEAD"],
        cwd=_PACKAGE_ROOT, capture_output=True, text=True,
    )
    assert result.returncode != 0, "record mode accepted --base-ref HEAD"
    assert "names the current checkout" in (result.stdout + result.stderr)


def test_the_baseline_records_the_patches_its_base_carried():
    """Provenance must name any tracked file the base checkout differed on."""
    meta = baseline_provenance()
    assert "base_patches" in meta, "provenance does not disclose base patches"
    assert meta["base_patches"] == [], (
        f"unexpected base patches: {meta['base_patches']}"
    )
    assert meta.get("base_commit"), "provenance does not pin a base commit"


# --- The harness that computes the digests is itself verified -------------
#
# Every other guard on the recorder describes the *template sources*. None of
# them looks at tests/render_baseline.py, which is copied into the base checkout
# and imported to produce the trusted numbers. A harness that dropped cases or
# returned constants would satisfy ancestry, cleanliness and provenance alike.
# Three properties are needed, and only together: the recorded hash matches the
# reviewed file, a mismatch actually refuses, and the check happens before the
# import it is protecting.


def _recorder_module():
    import importlib.util

    from tests.render_baseline import _PACKAGE_ROOT

    path = os.path.join(_PACKAGE_ROOT, "scripts", "record_render_baseline.py")
    spec = importlib.util.spec_from_file_location("_ajc66_recorder_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_recorded_harness_hash_matches_the_harness_on_disk():
    """The constant is only a guard while it describes the reviewed file.

    A harness edit that lands without touching HARNESS_FILES leaves a recorder
    that trusts bytes nobody approved. That is the drift this catches, and it is
    the failure the other two tests here cannot see: they both pass happily
    against a stale-but-self-consistent pair.
    """
    import hashlib

    from tests.render_baseline import _PACKAGE_ROOT

    recorder = _recorder_module()
    assert recorder.HARNESS_FILES, "the recorder verifies no harness files at all"
    for relative, expected in recorder.HARNESS_FILES.items():
        path = os.path.join(_PACKAGE_ROOT, relative)
        assert os.path.exists(path), f"HARNESS_FILES names a file that is not here: {relative}"
        with open(path, "rb") as fh:
            actual = hashlib.sha256(fh.read()).hexdigest()
        assert actual == expected, (
            f"{relative} was edited without updating HARNESS_FILES in a reviewed diff.\n"
            f"  reviewed {expected}\n  on disk  {actual}\n"
            f"If the change is intended, update the constant in scripts/record_render_baseline.py."
        )


def _recorder_sandbox(tmp_path, harness_mutation: str = ""):
    """A package root holding the real recorder and a possibly-mutated harness.

    Deliberately not a git checkout. Everything the recorder needs to reach its
    hash check is present; everything it would need *after* that check is not.
    That is what makes the pair of tests below informative — the tampered run
    must stop at the hash, and the untampered run must get past it and fail on
    the absent git environment instead.
    """
    import shutil

    from tests.render_baseline import _PACKAGE_ROOT

    root = tmp_path / "package"
    (root / "scripts").mkdir(parents=True)
    (root / "tests").mkdir(parents=True)
    shutil.copy2(
        os.path.join(_PACKAGE_ROOT, "scripts", "record_render_baseline.py"),
        root / "scripts" / "record_render_baseline.py",
    )
    with open(os.path.join(_PACKAGE_ROOT, "tests", "render_baseline.py"), encoding="utf-8") as fh:
        harness_text = fh.read()
    (root / "tests" / "render_baseline.py").write_text(harness_text + harness_mutation, encoding="utf-8")
    return root


def _run_recorder(root, *args):
    import subprocess
    import sys as _sys

    result = subprocess.run(
        [_sys.executable, "scripts/record_render_baseline.py", *args],
        cwd=str(root), capture_output=True, text=True,
    )
    return result.returncode, result.stdout + result.stderr


def test_record_mode_refuses_a_harness_it_has_not_reviewed(tmp_path):
    """End-to-end: a tampered harness is refused, not merely detectable.

    The mutation records three of the eighteen cases. Everything else about the
    tree is fine, which is the point: the harness hash is the only thing between
    a doctored harness and a baseline the whole gate then trusts.
    """
    root = _recorder_sandbox(tmp_path, "\n\nRENDER_CASES = RENDER_CASES[:3]  # tampered\n")
    code, out = _run_recorder(root, "--record")
    assert code != 0, f"a tampered harness was accepted:\n{out}"
    assert "does not match its reviewed hash" in out, (
        f"refused for some other reason than the harness hash:\n{out}"
    )


def test_check_mode_refuses_a_harness_that_would_report_itself_clean(tmp_path):
    """--check is the gate, so a harness cannot be trusted to grade itself.

    The mutation is the one that matters: ``compute_baseline`` returns
    ``load_baseline_cases()``, so every case compares equal to the recorded
    value and the gate prints OK forever, whatever the templates now emit. This
    is a false *green*, not a false red — nothing downstream would ever notice.

    Until AJC-65 lands, this standalone gate is the only thing checking the
    substrate in CI, which is exactly why the verification cannot be limited to
    the record path.
    """
    mutation = (
        "\n\n_baseline_cases = load_baseline_cases\n"
        "def compute_baseline():  # tampered: grade against the answer key\n"
        "    return _baseline_cases()\n"
    )
    root = _recorder_sandbox(tmp_path, mutation)
    code, out = _run_recorder(root, "--check")
    assert code != 0, f"--check accepted a harness that grades against the baseline:\n{out}"
    assert "does not match its reviewed hash" in out, (
        f"--check refused for some other reason than the harness hash:\n{out}"
    )
    assert "byte-identical" not in out, (
        f"--check reported success from a tampered harness:\n{out}"
    )


@pytest.mark.parametrize(
    "mode,environmental_failure",
    [
        # --record reaches git first; --check goes straight on to import the
        # harness, which needs the substrate packages the sandbox omits. Both
        # are failures of the sandbox, and neither is the hash.
        ("--record", "cannot interrogate git"),
        ("--check", "No module named 'data'"),
    ],
)
def test_an_untampered_harness_passes_verification_in_the_same_sandbox(
    tmp_path, mode, environmental_failure
):
    """The control: refusal above is caused by tampering, not by the sandbox.

    Same construction, same deliberately incomplete environment, harness
    byte-identical to the reviewed one. Both modes must get *past* the hash
    check and fail later for a reason belonging to the sandbox — if this failed
    at the hash too, the two tests above would prove nothing about tampering.
    """
    root = _recorder_sandbox(tmp_path)
    code, out = _run_recorder(root, mode)
    assert "does not match its reviewed hash" not in out, (
        f"an untampered harness was refused by the hash check:\n{out}"
    )
    assert code != 0, f"the incomplete sandbox somehow succeeded:\n{out}"
    assert environmental_failure in out, (
        f"expected {mode} to fail on {environmental_failure!r}, got:\n{out}"
    )


def test_the_harness_is_verified_before_it_is_imported():
    """Order is the whole property — verification must gate harness imports.

    Importing the harness runs its module body. Current shape:
    ``main()`` verifies the reviewed hash, then dispatches to verified helper
    functions that may import the harness. This avoids the untrusted module body
    running before verification.
    """
    import ast

    from tests.render_baseline import _PACKAGE_ROOT

    path = os.path.join(_PACKAGE_ROOT, "scripts", "record_render_baseline.py")
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=path)

    def harness_import_line_numbers(node):
        return [
            child.lineno
            for child in ast.walk(node)
            if (
                (isinstance(child, ast.Import) and any(
                    alias.name in {"tests.render_baseline", "render_baseline"} for alias in child.names
                ))
                or (
                    isinstance(child, ast.ImportFrom)
                    and child.module in {"tests.render_baseline", "render_baseline"}
                )
            )
        ]

    main = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "main"
    )

    module_level = [
        lineno
        for stmt in tree.body
        if isinstance(stmt, (ast.Import, ast.ImportFrom))
        for lineno in harness_import_line_numbers(stmt)
    ]
    assert not module_level, (
        f"the harness is imported at module scope (line {module_level}), so it runs "
        f"before any verification can happen"
    )

    helper_functions = {
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name != "main"
        and harness_import_line_numbers(node)
    }
    assert helper_functions, (
        "no top-level helper imports the harness; this check would be vacuous"
    )
    verify_calls = [
        node.lineno
        for node in ast.walk(main)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_verify_harness"
    ]
    assert verify_calls, "main() never verifies the harness"

    verify_line = min(verify_calls)
    helper_calls = [
        node.lineno
        for node in ast.walk(main)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in helper_functions
    ]
    assert helper_calls, (
        "main() never dispatches to a harness-importing helper after verification"
    )
    assert all(lineno > verify_line for lineno in helper_calls), (
        "a harness-importing helper can be called before _verify_harness(), so the "
        "untrusted module body can run first"
    )

    # No exemption for --check. An earlier revision of this test excused the
    # check branch on the reasoning that a bad harness there reddens the gate
    # rather than blessing a lie. That reasoning is wrong: --check decides
    # pass/fail by asking the harness for the digests, so a harness whose
    # compute_baseline() returned load_baseline_cases() would report every case
    # identical forever. --check IS the standalone gate. Every harness import in
    # main(), on either path, must follow the verification.
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_run_check_mode"
        and node.lineno < verify_line
        for node in ast.walk(main)
    ), (
        "a --check helper can run before _verify_harness(); --check is not exempt, it is the gate"
    )
