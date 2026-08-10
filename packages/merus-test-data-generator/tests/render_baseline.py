"""Deterministic render digests for the variant-content seam (AJC-66).

The seam added in AJC-66 lets a caller opt a template into variant-appropriate
body content. The whole point of the seam is that it is *additive*: with the
opt-in absent, every governed template must render exactly what it rendered
before the seam existed. This module is the instrument that proves it.

Two digests are recorded per (template, variant) pair, because content equality
alone is not enough:

``text``
    SHA-256 of the story's plain text. Catches content drift in the document
    under test.

``rng``
    SHA-256 of ``random.getstate()`` *after* the render. Catches rng drift —
    a seam that quietly consumes one extra draw leaves this document identical
    while shifting every *subsequent* document in the same case. A content-only
    digest cannot see that, and it is the exact failure mode that would break
    wcce's golden corpora.

Recording is deliberate and explicit::

    python scripts/record_render_baseline.py

Regenerating without a reviewed reason defeats the guard.
"""

from __future__ import annotations

import hashlib
import os
import random
import sys
from datetime import date
from typing import Any

_PACKAGE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PACKAGE_ROOT not in sys.path:
    sys.path.insert(0, _PACKAGE_ROOT)

from data.fake_data_generator import FakeDataGenerator  # noqa: E402
from data.lifecycle_engine import CaseParameters  # noqa: E402
from data.models import DocumentSpec, DocumentSubtype, OutputFormat  # noqa: E402

#: Seed for the render itself. Fixed forever — changing it invalidates every
#: recorded digest and proves nothing.
RENDER_SEED = 20260808

#: Seed for the case fixture. Independent of RENDER_SEED: the case is built
#: first, then the rng is re-seeded immediately before each render, so case
#: construction can never perturb a render digest.
CASE_SEED = 4242

BASELINE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden", "render_baseline.json")


def build_fixture_case() -> Any:
    """A single deterministic case shared by every digest in the baseline.

    ``has_surgery=True`` so the operative record renders a coherent surgical
    document rather than the degenerate no-procedure path.
    """
    gen = FakeDataGenerator(seed=CASE_SEED)
    params = CaseParameters(
        target_stage="settlement",
        injury_type="specific",
        body_part_category="spine",
        num_body_parts=2,
        has_surgery=True,
        has_attorney=True,
        has_psych_component=False,
        complexity="standard",
    )
    return gen.generate_case_from_params(case_number=1, params=params)


#: (label, module path, class name, subtype, variant-or-None).
#:
#: ``None`` means "no ``variant`` key in context at all" — the bare-registry
#: path. Every other entry is a variant string the registry actually ships
#: (``pdf_templates/registry.py``), including the display-string variants
#: ("Objection to QME/AME Report") that are not lowercase slugs.
RENDER_CASES: list[tuple[str, str, str, str, str | None]] = [
    # --- medical: the two templates note D names directly -------------------
    ("diagnostic:none", "pdf_templates.medical.diagnostic_report", "DiagnosticReport", "DIAGNOSTICS", None),
    ("diagnostic:imaging", "pdf_templates.medical.diagnostic_report", "DiagnosticReport", "DIAGNOSTICS_IMAGING", "imaging"),
    ("diagnostic:lab", "pdf_templates.medical.diagnostic_report", "DiagnosticReport", "DIAGNOSTICS_LAB_RESULTS", "lab"),
    ("diagnostic:sleep_study", "pdf_templates.medical.diagnostic_report", "DiagnosticReport", "SLEEP_STUDY", "sleep_study"),
    ("diagnostic:emg_ncv", "pdf_templates.medical.diagnostic_report", "DiagnosticReport", "EMG_NCV_STUDY", "emg_ncv"),
    ("operative:none", "pdf_templates.medical.operative_record", "OperativeRecord", "OPERATIVE_HOSPITAL_RECORDS", None),
    ("operative:acute", "pdf_templates.medical.operative_record", "OperativeRecord", "ACUTE_CARE_HOSPITAL_RECORDS", "acute"),
    ("operative:er", "pdf_templates.medical.operative_record", "OperativeRecord", "EMERGENCY_ROOM_RECORDS", "er"),
    ("operative:discharge", "pdf_templates.medical.operative_record", "OperativeRecord", "DISCHARGE_SUMMARY", "discharge"),
    ("operative:face_sheet", "pdf_templates.medical.operative_record", "OperativeRecord", "FACE_SHEET", "face_sheet"),
    # --- correspondence / discovery: the families note D also flags ---------
    ("defense_letter:none", "pdf_templates.correspondence.defense_counsel_letter", "DefenseCounselLetter", "DEFENSE_COUNSEL_LETTER", None),
    ("defense_letter:advocacy_qme", "pdf_templates.correspondence.defense_counsel_letter", "DefenseCounselLetter", "ADVOCACY_LETTERS_QME", "advocacy_qme"),
    ("defense_letter:objection", "pdf_templates.correspondence.defense_counsel_letter", "DefenseCounselLetter", "OBJECTION_TO_QME_AME_REPORT", "Objection to QME/AME Report"),
    ("defense_letter:supp_request", "pdf_templates.correspondence.defense_counsel_letter", "DefenseCounselLetter", "REQUEST_SUPPLEMENTAL_QME_AME_REPORT", "Request for Supplemental QME/AME Report"),
    ("depo_notice:none", "pdf_templates.discovery.deposition_notice", "DepositionNotice", "DEPOSITION_NOTICE", None),
    ("depo_notice:medical_witness", "pdf_templates.discovery.deposition_notice", "DepositionNotice", "DEPOSITION_NOTICE_MEDICAL_WITNESS", "medical_witness"),
    ("depo_transcript:none", "pdf_templates.discovery.deposition_transcript", "DepositionTranscript", "DEPOSITION_TRANSCRIPT", None),
    ("depo_transcript:qme_ame", "pdf_templates.discovery.deposition_transcript", "DepositionTranscript", "DEPOSITION_TRANSCRIPT_QME_AME", "Deposition Transcript (QME/AME)"),
]


def _load_template_class(module_path: str, class_name: str) -> type:
    module = __import__(module_path, fromlist=[class_name])
    return getattr(module, class_name)


def make_spec(subtype_name: str, variant: str | None, extra_context: dict | None = None) -> DocumentSpec:
    """A DocumentSpec carrying exactly the context keys under test.

    ``variant=None`` omits the key entirely rather than setting it empty — the
    two are different inputs and the seam must be correct for both.
    """
    context: dict[str, Any] = {}
    if variant is not None:
        context["variant"] = variant
    if extra_context:
        context.update(extra_context)
    return DocumentSpec(
        subtype=getattr(DocumentSubtype, subtype_name),
        title=subtype_name.replace("_", " ").title(),
        doc_date=date(2024, 6, 17),
        template_class="AJC66Baseline",
        output_format=OutputFormat.PDF,
        context=context,
    )


def render_digest(case: Any, module_path: str, class_name: str, spec: DocumentSpec) -> dict[str, str]:
    """Render one document under a fixed seed and digest content + rng position.

    The rng is seeded immediately before ``build_story`` so the digest depends
    only on the template's own draws, and ``getstate()`` is read immediately
    after so the rng digest measures exactly what this render consumed.
    """
    template_cls = _load_template_class(module_path, class_name)
    template = template_cls(case)

    random.seed(RENDER_SEED)
    story = template.build_story(spec)
    rng_state_after = random.getstate()

    text = template._story_to_plaintext(story)
    return {
        "text": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "rng": hashlib.sha256(repr(rng_state_after).encode("utf-8")).hexdigest(),
    }


def compute_baseline() -> dict[str, dict[str, str]]:
    """Digest every registered (template, variant) pair on the default path."""
    case = build_fixture_case()
    results: dict[str, dict[str, str]] = {}
    for label, module_path, class_name, subtype_name, variant in RENDER_CASES:
        spec = make_spec(subtype_name, variant)
        results[label] = render_digest(case, module_path, class_name, spec)
    return results
