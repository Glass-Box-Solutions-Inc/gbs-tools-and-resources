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

import json
import random
import re

import pytest

from tests.render_baseline import (
    BASELINE_PATH,
    CLAIMED_LETTER_VARIANTS,
    DEFENSE_LETTER_VARIANTS,
    RENDER_CASES,
    RENDER_SEED,
    _load_template_class,
    build_fixture_case,
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
    with open(BASELINE_PATH, encoding="utf-8") as fh:
        return json.load(fh)


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


@pytest.mark.parametrize("value,expected", [(True, True), (False, False), ({}, False), ({"a": 1}, True)])
def test_the_opt_in_accepts_a_bool_or_a_block(case, value, expected):
    """``bool`` for the switch, ``dict`` for a future block of parameters.

    An empty block reads as off, matching AJC-65's seam on the same context
    channel: the engine sets a dozen keys on every context, and a key arriving
    empty must read exactly like a key that is not there.
    """
    template = _load_template_class(DIAG_MODULE, "DiagnosticReport")(case)
    spec = make_spec("DIAGNOSTICS_LAB_RESULTS", "lab", extra_context={"variant_content": value})
    assert template.variant_content_enabled(spec) is expected


@pytest.mark.parametrize("value", ["true", "false", 1, 0, [], ["lab"], object()])
def test_a_non_bool_non_dict_opt_in_is_refused_rather_than_guessed(case, value):
    """Every other type raises, instead of being silently truthy.

    Pinned now because the key is new and no caller can yet break, and because
    ``"false"`` is truthy in Python. Left open, that would surface months later
    as an unexplained corpus diff.
    """
    template = _load_template_class(DIAG_MODULE, "DiagnosticReport")(case)
    spec = make_spec("DIAGNOSTICS_LAB_RESULTS", "lab", extra_context={"variant_content": value})
    with pytest.raises(ValueError, match="must be a bool or a dict"):
        template.variant_content_enabled(spec)


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
    for topic in ["board certified", "records reviewed", "apportionment", "impairment rating",
                  "supplemental report"]:
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
