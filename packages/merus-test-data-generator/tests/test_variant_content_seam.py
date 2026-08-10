"""The variant-content seam (AJC-66).

Several templates are reached by many registry subtypes carrying different
``variant`` strings, and render the same document for all of them: a
lab-results subtype comes out as an X-ray report, an emergency-room record
comes out as an operative report. This suite governs the seam that fixes that
without moving a single byte on the path everything currently uses.

The suite is in two halves, and the first matters more than the second:

**Default path is frozen.** ``tests/golden/render_baseline.json`` was recorded
before the seam existed. Every registered (template, variant) pair must still
hash to it, in content *and* in rng position. wc-synthetic-caseload-engine pins
four golden corpora against these templates and does not set the opt-in key, so
any drift here is a corpus break.

**Opted-in path is real.** With the opt-in present, a governed variant must
render a document that is actually about what its subtype says it is — not the
same document with a different heading.
"""

from __future__ import annotations

import json
import random

import pytest

from tests.render_baseline import (
    BASELINE_PATH,
    RENDER_CASES,
    RENDER_SEED,
    _load_template_class,
    build_fixture_case,
    make_spec,
    render_digest,
)


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
# Half one: the default path does not move
# --------------------------------------------------------------------------


@pytest.mark.parametrize("label,module_path,class_name,subtype,variant", RENDER_CASES)
def test_default_path_is_byte_identical_to_the_recorded_baseline(
    case, baseline, label, module_path, class_name, subtype, variant
):
    """Without the opt-in, every governed pair renders its pre-seam bytes.

    The rng half of the digest is the one that catches the subtle break: a seam
    that consumes a draw it should not leaves this document identical and
    shifts every later document in the same case.
    """
    spec = make_spec(subtype, variant)
    assert render_digest(case, module_path, class_name, spec) == baseline[label], (
        f"{label} drifted from the pre-seam baseline. If this change is "
        f"deliberate, re-record with scripts/record_render_baseline.py and say "
        f"so in the commit — but wcce's golden corpora will need re-recording too."
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
    other variant that reaches a seamed template must pass straight through.
    """
    spec = make_spec(subtype, "no-register-claims-this-string", extra_context={"variant_content": True})
    digest = render_digest(case, module_path, class_name, spec)
    assert digest["text"] == baseline[label]["text"]


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
        """Records every ``choice`` candidate list, delegates everything else.

        This is the same shape as wcce's ``_ForcedChoice`` — it has to be, or
        the canary would not be watching the thing wcce actually relies on.
        """

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
# Half two: the opted-in path renders documents that are about their subtype
# --------------------------------------------------------------------------

#: (label, module, class, subtype, variant, substrings that must appear,
#:  substrings that must NOT appear).
GOVERNED = [
    (
        "lab",
        "pdf_templates.medical.diagnostic_report",
        "DiagnosticReport",
        "DIAGNOSTICS_LAB_RESULTS",
        "lab",
        ["LABORATORY", "Reference Range", "Specimen"],
        ["Tesla", "OPERATIVE REPORT", "radiologist"],
    ),
    (
        "emg_ncv",
        "pdf_templates.medical.diagnostic_report",
        "DiagnosticReport",
        "EMG_NCV_STUDY",
        "emg_ncv",
        ["ELECTRODIAGNOSTIC", "NERVE CONDUCTION", "NEEDLE EMG"],
        ["Tesla", "sagittal", "OPERATIVE REPORT"],
    ),
    (
        "sleep_study",
        "pdf_templates.medical.diagnostic_report",
        "DiagnosticReport",
        "SLEEP_STUDY",
        "sleep_study",
        ["POLYSOMNOGRAPHY", "Apnea-Hypopnea Index", "SLEEP ARCHITECTURE"],
        ["Tesla", "sagittal"],
    ),
    (
        "er",
        "pdf_templates.medical.operative_record",
        "OperativeRecord",
        "EMERGENCY_ROOM_RECORDS",
        "er",
        ["EMERGENCY DEPARTMENT", "TRIAGE", "DISPOSITION"],
        ["OPERATIVE REPORT", "OPERATIVE NARRATIVE", "Estimated Blood Loss"],
    ),
    (
        "acute",
        "pdf_templates.medical.operative_record",
        "OperativeRecord",
        "ACUTE_CARE_HOSPITAL_RECORDS",
        "acute",
        ["HOSPITAL COURSE", "ADMISSION", "DISCHARGE DISPOSITION"],
        ["OPERATIVE NARRATIVE", "Estimated Blood Loss"],
    ),
    (
        "face_sheet",
        "pdf_templates.medical.operative_record",
        "OperativeRecord",
        "FACE_SHEET",
        "face_sheet",
        ["FACE SHEET", "REGISTRATION"],
        ["OPERATIVE NARRATIVE", "Estimated Blood Loss"],
    ),
    (
        "advocacy",
        "pdf_templates.correspondence.defense_counsel_letter",
        "DefenseCounselLetter",
        "ADVOCACY_LETTERS_QME",
        "advocacy_qme",
        ["8 C.C.R.", "advocacy"],
        [],
    ),
    (
        "objection",
        "pdf_templates.correspondence.defense_counsel_letter",
        "DefenseCounselLetter",
        "OBJECTION_TO_QME_AME_REPORT",
        "Objection to QME/AME Report",
        ["object"],
        [],
    ),
    (
        "supp_request",
        "pdf_templates.correspondence.defense_counsel_letter",
        "DefenseCounselLetter",
        "REQUEST_SUPPLEMENTAL_QME_AME_REPORT",
        "Request for Supplemental QME/AME Report",
        ["supplemental report"],
        [],
    ),
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
        (
            "pdf_templates.medical.diagnostic_report",
            "DiagnosticReport",
            [
                ("DIAGNOSTICS_IMAGING", "imaging"),
                ("DIAGNOSTICS_LAB_RESULTS", "lab"),
                ("EMG_NCV_STUDY", "emg_ncv"),
                ("SLEEP_STUDY", "sleep_study"),
            ],
        ),
        (
            "pdf_templates.medical.operative_record",
            "OperativeRecord",
            [
                ("OPERATIVE_HOSPITAL_RECORDS", None),
                ("EMERGENCY_ROOM_RECORDS", "er"),
                ("ACUTE_CARE_HOSPITAL_RECORDS", "acute"),
                ("DISCHARGE_SUMMARY", "discharge"),
                ("FACE_SHEET", "face_sheet"),
            ],
        ),
        (
            "pdf_templates.correspondence.defense_counsel_letter",
            "DefenseCounselLetter",
            [
                ("ADVOCACY_LETTERS_QME", "advocacy_qme"),
                ("OBJECTION_TO_QME_AME_REPORT", "Objection to QME/AME Report"),
                ("REQUEST_SUPPLEMENTAL_QME_AME_REPORT", "Request for Supplemental QME/AME Report"),
            ],
        ),
        (
            "pdf_templates.discovery.deposition_notice",
            "DepositionNotice",
            [
                ("DEPOSITION_NOTICE_APPLICANT", "applicant"),
                ("DEPOSITION_NOTICE_MEDICAL_WITNESS", "medical_witness"),
            ],
        ),
    ],
)
def test_governed_variants_render_mutually_distinct_documents(case, module_path, class_name, pairs):
    """The whole defect in one assertion: these used to be the same document."""
    texts = {}
    for subtype, variant in pairs:
        spec = make_spec(subtype, variant, extra_context={"variant_content": True})
        texts[variant] = render_text(case, module_path, class_name, spec)

    seen: dict[str, str] = {}
    for variant, text in texts.items():
        assert text not in seen.values(), (
            f"{class_name}: variant {variant!r} renders the identical document as "
            f"{[k for k, v in seen.items() if v == text]!r}"
        )
        seen[variant] = text


def test_new_variant_content_names_no_real_organization():
    """New prose must not name a real body.

    ``data/wc_constants.py`` carries pools of genuinely real carriers, defense
    firms and employers — the substrate draws from them when a seed names none,
    and wcce substitutes coined names on every one of those paths for exactly
    this reason. Content added for the seam must not reintroduce any of them.
    """
    from data import variant_content
    from data import wc_constants

    real_names: set[str] = set()
    for pool_name in ("INSURANCE_CARRIERS", "DEFENSE_FIRMS", "ALL_EMPLOYERS", "MEDICAL_FACILITIES"):
        for entry in getattr(wc_constants, pool_name, []) or []:
            name = entry if isinstance(entry, str) else (entry.get("name") if isinstance(entry, dict) else None)
            if name and len(name) > 4:
                real_names.add(name.lower())

    blob = json.dumps(variant_content.all_content_strings()).lower()
    hits = sorted(name for name in real_names if name in blob)
    assert not hits, f"variant content names real organizations: {hits}"
