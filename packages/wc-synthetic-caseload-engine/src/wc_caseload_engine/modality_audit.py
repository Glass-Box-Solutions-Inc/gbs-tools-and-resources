"""Every substrate site that names a diagnostic modality, and who governs it.

The ledger's promise — "no document claims a study the case did not have" — is
only as good as the enumeration behind it. Phase 1 governed the diagnostic
report and thought it was done; the QME turned out to name modalities in three
*other* places, each found one failing test at a time. That is not a search
strategy, it is luck running out slowly.

So the sites are enumerated here, and :mod:`tests.test_scenario_p2` greps the
substrate and fails if it finds one this table does not list. A new modality
site upstream becomes a failing test rather than a silent incoherence.

Each row is either **governed** (an override forces it to agree with the ledger)
or **documented** (it is left alone, with the reason). "Documented" is a real
answer — several sites name modalities in contexts where the ledger has nothing
to say, and forcing them would invent facts rather than align them.

Rows are keyed by a marker substring rather than a line number, because line
numbers drift on every upstream edit and a table that goes stale silently is
worse than no table.
"""

from __future__ import annotations

from typing import Literal, NamedTuple


class ModalitySite(NamedTuple):
    """One substrate location that puts a modality name in front of a reader."""

    path: str
    """Substrate-relative module path."""

    marker: str
    """A distinctive substring of the naming line, used to match the grep hit."""

    disposition: Literal["governed", "documented"]

    by: str
    """The override that governs it, or the reason it is left alone."""


#: File suffixes the audit does not consider rendered content.
#:
#: ``tests/`` is the substrate's own test suite, ``batch*.py`` are standalone
#: corpus-generation scripts this engine never calls, and ``data/taxonomy.py``
#: holds subtype *vocabulary* — ``EMG_NCV_STUDY`` is the name of a document
#: kind, not a clinical assertion about a case.
EXCLUDED_PATHS: tuple[str, ...] = (
    "tests/",
    "batch1_",
    "batch2_",
    "batch3_",
    "batch4_",
    "data/taxonomy.py",
)

MODALITY_SITES: tuple[ModalitySite, ...] = (
    # -- Governed -----------------------------------------------------------
    ModalitySite(
        "pdf_templates/medical/diagnostic_report.py",
        'exam_type = random.choice(["MRI", "CT", "X-Ray"])',
        "governed",
        "FactAwareDiagnosticReport forces the ledger's modality (ISC-90)",
    ),
    ModalitySite(
        "pdf_templates/medical/diagnostic_report.py",
        'if exam_type == "MRI"',
        "governed",
        "technique branch, downstream of the forced exam_type above",
    ),
    ModalitySite(
        "pdf_templates/medical/diagnostic_report.py",
        "MRI of the",
        "governed",
        "technique prose, downstream of the forced exam_type",
    ),
    ModalitySite(
        "pdf_templates/medical/diagnostic_report.py",
        "Diagnostic Report Template",
        "documented",
        "module docstring — never rendered",
    ),
    ModalitySite(
        "pdf_templates/medical/diagnostic_report.py",
        "Advanced MRI & CT Center",
        "documented",
        "a facility name, not a claim that a study happened",
    ),
    ModalitySite(
        "pdf_templates/medical/qme_ame_report.py",
        "X-rays which revealed no acute fracture",
        "governed",
        "FactAwareNeuroQmeReport._build_history forces it (ISC-111)",
    ),
    ModalitySite(
        "pdf_templates/medical/qme_ame_report.py",
        "EMG/NCV",
        "governed",
        "FactAwareNeuroQmeReport._build_neuro_exam drops it when absent (ISC-91)",
    ),
    ModalitySite(
        "pdf_templates/medical/qme_ame_report.py",
        "Electrodiagnostic Studies",
        "governed",
        "same override, matched on the section heading",
    ),
    ModalitySite(
        "pdf_templates/medical/qme_ame_report.py",
        "imaging_type = random.choice",
        "governed",
        "FactAwareQmeAmeReport._build_diagnostic_review replaces the section",
    ),
    # -- Documented ---------------------------------------------------------
    ModalitySite(
        "pdf_templates/discovery/subpoenaed_records.py",
        "MRI",
        "documented",
        "records from *prior* providers — history predating this claim, which "
        "the ledger deliberately does not model. Governing it would assert the "
        "applicant's whole medical past agrees with one injury's imaging.",
    ),
    ModalitySite(
        "pdf_templates/discovery/subpoenaed_records.py",
        "CT scan",
        "documented",
        "same: prior-provider record content",
    ),
    ModalitySite(
        "pdf_templates/discovery/subpoenaed_records.py",
        "radiographic",
        "documented",
        "same: prior-provider record content",
    ),
    ModalitySite(
        "pdf_templates/correspondence/adjuster_letter.py",
        "MRI",
        "documented",
        "an adjuster *requesting* or discussing imaging, not reporting it. "
        "Adjuster behaviour is a Phase-3 axis (personas); until the ledger "
        "models what was requested, forcing this would invent a request.",
    ),
    ModalitySite(
        "pdf_templates/legal/declaration_of_readiness.py",
        "X-rays",
        "documented",
        "an evidence list in a procedural filing, naming document kinds rather "
        "than asserting studies occurred",
    ),
    ModalitySite(
        "pdf_templates/discovery/subpoena.py",
        "X-rays",
        "documented",
        "the categories of record a subpoena demands — a request, not a finding",
    ),
    ModalitySite(
        "data/content_pools.py",
        "MRI",
        "documented",
        "shared narrative and exam-finding pools drawn by many templates. "
        "Governing them needs a per-draw ledger channel rather than a template "
        "override — Phase 3.",
    ),
    ModalitySite(
        "data/content_pools.py",
        "EMG",
        "documented",
        "same shared pools",
    ),
    ModalitySite(
        "data/content_pools.py",
        "X-ray",
        "documented",
        "same shared pools",
    ),
    ModalitySite(
        "data/content_pools.py",
        "electrodiagnostic",
        "documented",
        "same shared pools",
    ),
    ModalitySite(
        "data/content_pools.py",
        "nerve conduction",
        "documented",
        "same shared pools",
    ),
    ModalitySite(
        "data/content_pools.py",
        "CT scan",
        "documented",
        "same shared pools",
    ),
    ModalitySite(
        "data/content_pools.py",
        "radiograph",
        "documented",
        "MTUS treatment-guideline criteria quoted in a utilization pool — the "
        "modality belongs to the standard being applied, not to this case",
    ),
    ModalitySite(
        "data/ama_guides_content.py",
        "EMG",
        "documented",
        "AMA Guides impairment criteria — the modality is part of a *rating "
        "standard's* text, not an assertion that this applicant had the study",
    ),
    ModalitySite(
        "data/ama_guides_content.py",
        "electrodiagnostic",
        "documented",
        "same: quoted rating criteria",
    ),
    ModalitySite(
        "data/ama_guides_content.py",
        "nerve conduction",
        "documented",
        "same: quoted rating criteria",
    ),
    ModalitySite(
        "data/ama_guides_content.py",
        "MRI",
        "documented",
        "same: quoted rating criteria",
    ),
    ModalitySite(
        "data/ama_guides_content.py",
        "radiograph",
        "documented",
        "same: quoted rating criteria",
    ),
    ModalitySite(
        "data/deposition_exchanges.py",
        "MRI",
        "documented",
        "deposition Q&A — a witness recalling imaging under oath. Aligning it "
        "to the ledger is a Phase-3 axis (testimony consistency).",
    ),
    ModalitySite(
        "data/deposition_exchanges.py",
        "X-ray",
        "documented",
        "same deposition transcript content",
    ),
    ModalitySite(
        "data/deposition_exchanges.py",
        "EMG",
        "documented",
        "same deposition transcript content",
    ),
    ModalitySite(
        "data/wc_constants.py",
        "MRI",
        "documented",
        "facility and body-part constant tables — vocabulary, not case facts",
    ),
    ModalitySite(
        "data/wc_constants.py",
        "EMG",
        "documented",
        "same constant tables",
    ),
    ModalitySite(
        "data/wc_constants.py",
        "X-ray",
        "documented",
        "same constant tables",
    ),
    ModalitySite(
        "data/case_context.py",
        "MRI",
        "documented",
        "the substrate's own unused accumulator, never wired on the engine path",
    ),
)


def sites_for(path: str) -> tuple[ModalitySite, ...]:
    """Every table row covering *path*."""
    return tuple(site for site in MODALITY_SITES if site.path == path)


def is_excluded(path: str) -> bool:
    """Whether *path* is outside the audit's definition of rendered content."""
    return any(fragment in path for fragment in EXCLUDED_PATHS)


__all__ = [
    "EXCLUDED_PATHS",
    "MODALITY_SITES",
    "ModalitySite",
    "is_excluded",
    "sites_for",
]
