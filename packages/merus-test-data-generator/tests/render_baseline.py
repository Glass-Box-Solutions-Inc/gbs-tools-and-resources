"""Deterministic render digests for the variant-content seam (AJC-66).

The seam added in AJC-66 lets a caller opt a template into variant-appropriate
body content. The whole point of the seam is that it is *additive*: with the
opt-in absent, every governed template must render exactly what it rendered
before the seam existed. This module is the instrument that proves it.

**Four digests per (template, variant) pair**, because the obvious two are not
enough and a guard that cannot see a class of change is worse than none — it
reads as coverage.

``text``
    SHA-256 of the story's plain text. Catches content drift.

``story``
    SHA-256 of a canonical fingerprint of the *flowables* — class name, style
    name, and the geometry of every Spacer, Table and rule. Plain text sees a
    Paragraph's words and nothing else, so a restyled heading, a resized
    Spacer, or a Paragraph that quietly became a Table is invisible to it while
    changing every rendered page.

``rng``
    SHA-256 of an **ordered trace** of every ``random`` call the render makes —
    name, argument shape, and result — plus the final state. Final state alone
    records position, not order: two draws of equal consumption could be swapped
    and the state would land in exactly the same place. The trace sees the swap.

``pdf``
    SHA-256 of the rendered PDF bytes, with ReportLab pinned to invariant output
    so the creation date and file id stop moving. This is the artifact a
    consumer actually ships, and it is the only digest that is a *byte*
    comparison in the literal sense the ticket asked for.

Recording is deliberate and explicit::

    python scripts/record_render_baseline.py

Regenerating without a reviewed reason defeats the guard.
"""

from __future__ import annotations

import hashlib
import os
import random
import re
import sys
import tempfile
from datetime import date
from pathlib import Path
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

#: The ``random`` module functions a template can reach. Wrapped as a set rather
#: than the handful currently in use, so a template that starts calling
#: ``sample`` or ``shuffle`` is traced without anyone remembering to add it.
_TRACED_CALLS = (
    "choice", "choices", "randint", "random", "randrange",
    "sample", "shuffle", "uniform", "gauss", "triangular",
)


def _ensure_invariant_pdfs() -> None:
    """Pin ReportLab so PDF bytes depend on content, not on the clock.

    ``rl_config.invariant`` fixes the creation date and the document id. Without
    it every render differs and a PDF digest would be worthless.
    """
    from reportlab import rl_config

    rl_config.invariant = 1


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

#: Every registered DefenseCounselLetter variant, so the allowlist is proven
#: against the real registry rather than against the three it was written for.
DEFENSE_LETTER_VARIANTS: tuple[tuple[str, str | None], ...] = (
    ("DEFENSE_COUNSEL_LETTER", None),
    ("DEFENSE_COUNSEL_LETTER_INFORMATIONAL", "informational"),
    ("DEFENSE_COUNSEL_LETTER_DEMAND", "demand"),
    ("SETTLEMENT_DEMAND_LETTER", "settlement_demand"),
    ("PETITION_RECONSIDERATION_OPPOSITION", "opposition"),
    ("PETITION_RECONSIDERATION_REPLY", "reply"),
    ("PETITION_REMOVAL_ANSWER", "answer"),
    ("ADVOCACY_LETTERS_PTP", "advocacy_ptp"),
    ("ADVOCACY_LETTERS_QME", "advocacy_qme"),
    ("ADVOCACY_LETTERS_AME", "advocacy_ame"),
    ("ADVOCACY_LETTERS_PTP_QME_AME", "advocacy"),
    ("DEMAND_LETTER_FORMAL", "formal_demand"),
    ("ANSWER_TO_APPLICATION", "answer_application"),
    ("OBJECTION_TO_DOR", "objection_dor"),
    ("SUBROGATION_DEMAND", "subrogation"),
    ("COVERAGE_OPINION_LETTER", "coverage_opinion"),
    ("OBJECTION_TO_QME_AME_REPORT", "Objection to QME/AME Report"),
    ("REQUEST_SUPPLEMENTAL_QME_AME_REPORT", "Request for Supplemental QME/AME Report"),
)

#: The only DefenseCounselLetter variants a register may claim.
CLAIMED_LETTER_VARIANTS = frozenset(
    {"advocacy_ptp", "advocacy_qme", "advocacy_ame", "advocacy",
     "Objection to QME/AME Report", "Request for Supplemental QME/AME Report"}
)


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


def _story_fingerprint(story: list) -> str:
    """A canonical description of the story's flowables, not just their words.

    Records what plain text throws away: which flowable class, which paragraph
    style, and the dimensions of the spacing and rules between them. A Spacer
    that changes height or a heading that changes style moves this and nothing
    else.
    """
    parts: list[str] = []
    for flowable in story:
        cls = type(flowable).__name__
        style = getattr(getattr(flowable, "style", None), "name", "")
        detail = ""
        if cls == "Spacer":
            detail = f"{getattr(flowable, 'width', '')}x{getattr(flowable, 'height', '')}"
        elif cls == "Table":
            rows = getattr(flowable, "_cellvalues", []) or []
            detail = f"rows={len(rows)}"
            if rows:
                detail += f",cols={len(rows[0])}"
        elif cls == "HRFlowable":
            detail = f"{getattr(flowable, 'width', '')}/{getattr(flowable, 'thickness', '')}"
        parts.append(f"{cls}|{style}|{detail}")
    return "\n".join(parts)


_ADDRESS = re.compile(r" at 0x[0-9a-fA-F]+")


def _stable_repr(value: Any) -> str:
    """``repr`` with memory addresses stripped.

    ``DefenseCounselLetter`` picks its body with ``random.choice`` over a list
    of *bound methods*, and the repr of one carries the instance address. That
    changes every process, so a raw repr made the trace unreproducible while
    looking, at a glance, like real drift. The method's name is the part that
    identifies the draw; the address never was.
    """
    return _ADDRESS.sub("", repr(value))


class _TracingRandom:
    """Records every ``random`` call in order, then delegates to the real one.

    Patched onto the ``random`` module itself rather than onto each template
    module, because every template does ``import random`` and therefore shares
    one module object — patching there catches base-class helpers such as
    ``lorem_medical`` that a per-module patch would miss entirely.
    """

    def __init__(self) -> None:
        self.trace: list[str] = []
        self._originals: dict[str, Any] = {}

    def __enter__(self) -> "_TracingRandom":
        for name in _TRACED_CALLS:
            original = getattr(random, name, None)
            if original is None:
                continue
            self._originals[name] = original
            setattr(random, name, self._wrap(name, original))
        return self

    def __exit__(self, *exc: Any) -> None:
        for name, original in self._originals.items():
            setattr(random, name, original)

    def _wrap(self, name: str, original: Any):
        def wrapper(*args: Any, **kwargs: Any):
            result = original(*args, **kwargs)
            # Argument *shape* plus the result. The result is what makes a
            # reordering of two equal-consumption draws visible: the state would
            # land in the same place, but the values swap.
            shape = ",".join(
                str(len(a)) if isinstance(a, (list, tuple, str)) else _stable_repr(a)
                for a in args
            )
            self.trace.append(f"{name}({shape})->{_stable_repr(result)}")
            return result

        return wrapper


def render_digest(case: Any, module_path: str, class_name: str, spec: DocumentSpec) -> dict[str, str]:
    """Render one document under a fixed seed and digest it four ways.

    The story pass and the PDF pass are seeded identically and run separately,
    so the PDF is a render of the same document rather than of whatever the rng
    happened to hold afterwards.
    """
    _ensure_invariant_pdfs()
    template_cls = _load_template_class(module_path, class_name)
    template = template_cls(case)

    with _TracingRandom() as tracer:
        random.seed(RENDER_SEED)
        story = template.build_story(spec)
        rng_state_after = random.getstate()

    text = template._story_to_plaintext(story)
    trace_blob = "\n".join(tracer.trace) + f"\nSTATE:{rng_state_after!r}"

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "render.pdf"
        random.seed(RENDER_SEED)
        template_cls(case).generate(out, spec)
        pdf_bytes = out.read_bytes()

    def sha(value: str | bytes) -> str:
        return hashlib.sha256(value if isinstance(value, bytes) else value.encode("utf-8")).hexdigest()

    return {
        "text": sha(text),
        "story": sha(_story_fingerprint(story)),
        "rng": sha(trace_blob),
        "pdf": sha(pdf_bytes),
    }


def compute_baseline() -> dict[str, dict[str, str]]:
    """Digest every registered (template, variant) pair on the default path."""
    case = build_fixture_case()
    results: dict[str, dict[str, str]] = {}
    for label, module_path, class_name, subtype_name, variant in RENDER_CASES:
        spec = make_spec(subtype_name, variant)
        results[label] = render_digest(case, module_path, class_name, spec)
    return results
