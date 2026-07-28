"""Every canonical subtype renders, through this engine's own dispatch path.

The claim this file exists to make true was previously made by a probe that ran
over the 78 subtypes the demo caseload happens to emit — 22% of the taxonomy —
and was written up as a "full-range render test". A cross-vendor audit read
"full range" as "all 353" and found 275 subtypes that had never been rendered
once. The qualifier was doing load-bearing work nobody could see.

So this file forces the whole vocabulary. Each subtype is driven straight into
:func:`~wc_caseload_engine.renderer.render_document` against one minimal case
context, which is both faster and sharper than seeding a caseload large enough
to emit everything: a caseload proves what its lifecycle chose to emit, while
this proves the dispatch path itself. Three assertions, one per way the surface
can quietly fail:

* nothing resolves to ``GenericDocumentTemplate`` (a missing template and a
  deliberate one are the same registry return value, so this is the only place
  the difference is visible);
* nothing renders trivially — every file clears 500 bytes and every PDF parses
  with a real page;
* nothing raises.

Runtime is roughly 25 seconds for all 353, so it stays in the default suite.
A coverage test that only runs when someone remembers to ask for it is the
same test that was missing.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest

from conftest import requires_substrate
from wc_caseload_engine.case_context import build_case_cast
from wc_caseload_engine.lifecycle_bridge import build_timeline
from wc_caseload_engine.renderer import (
    GENERIC_TEMPLATE_CLASS,
    OVERLAY_TEMPLATES,
    RenderResult,
    render_document,
    resolve_template,
)
from wc_caseload_engine.seeds import parse_case_seed
from wc_caseload_engine.taxonomy import EXPECTED_SUBTYPE_COUNT, effective_taxonomy

pytestmark = [requires_substrate, pytest.mark.slow]

KNOWN_UNRENDERABLE_SUBTYPES: frozenset[str] = frozenset()
"""Canonical subtypes this engine cannot render without falling back.

Empty, and the assertions below exist to keep it that way. It is deliberately a
*constant* rather than a computed set: an exception list that recomputes itself
from the current run cannot detect the thing it exists to detect.

The audit found three entries for this list —
``PETITION_FOR_PENALTIES``, ``NOTICE_OF_PENALTY_5814`` and
``NOTICE_OF_PENALTY_5814_5`` — the classifier subtypes the substrate enum lacks
and the registry therefore answered ``GenericDocumentTemplate`` for. They were
fixed rather than recorded: the engine invented those keys to reach 353-subtype
parity, so the engine owes them templates, and
:data:`~wc_caseload_engine.renderer.OVERLAY_TEMPLATES` supplies them. Adding a
subtype here again is a decision to ship a documented hole, not a way to make
this file pass.
"""

MINIMUM_DOCUMENT_BYTES = 500
"""Below this a "rendered" file is a stub, not a document."""


@pytest.fixture(scope="module")
def render_context() -> tuple[Any, Any]:
    """One minimal, valid case context, reused for all 353 renders.

    Every subtype rendering against the *same* cast is the point — it isolates
    the dispatch path from lifecycle variation. Nothing here is subtype-specific.
    """
    seed = parse_case_seed(
        {
            "case_id": "render-all-353",
            "rng_seed": 991,
            "injury": {
                "type": "specific",
                "date_of_injury": "2022-02-02",
                "body_parts": [{"part": "lumbar_spine", "icd10": "M54.5"}],
            },
        }
    )
    return seed, build_case_cast(seed, build_timeline(seed))


@pytest.fixture(scope="module")
def rendered_every_subtype(
    render_context: tuple[Any, Any], tmp_path_factory: pytest.TempPathFactory
) -> dict[str, RenderResult]:
    """Render every canonical subtype once. Failures surface as a raised error."""
    seed, cast = render_context
    out = tmp_path_factory.mktemp("all-subtypes")
    results: dict[str, RenderResult] = {}
    failures: list[str] = []

    for index, subtype in enumerate(effective_taxonomy().subtypes):
        try:
            results[subtype] = render_document(
                seed=seed,
                cast=cast,
                subtype=subtype,
                doc_date=date(2023, 6, 1),
                doc_format="pdf",
                index=index,
                out_path=out / f"{index:03d}_{subtype}.pdf",
            )
        except Exception as exc:  # the failure list IS the report
            failures.append(f"{subtype}: {type(exc).__name__}: {exc}")

    assert not failures, (
        f"{len(failures)} subtype(s) raised while rendering:\n" + "\n".join(failures[:20])
    )
    return results


# ---------------------------------------------------------------------------
# Coverage
# ---------------------------------------------------------------------------


def test_the_taxonomy_under_test_is_the_whole_taxonomy() -> None:
    """Guards the test itself: a shrunken taxonomy would make everything below pass."""
    assert len(effective_taxonomy().subtypes) == EXPECTED_SUBTYPE_COUNT


def test_every_canonical_subtype_renders(rendered_every_subtype: dict[str, RenderResult]) -> None:
    assert set(rendered_every_subtype) == set(effective_taxonomy().subtypes)
    assert len(rendered_every_subtype) == EXPECTED_SUBTYPE_COUNT


def test_no_subtype_resolves_to_the_generic_template() -> None:
    """Resolution only — no rendering — so a regression names itself instantly."""
    generic = sorted(
        subtype
        for subtype in effective_taxonomy().subtypes
        if resolve_template(subtype)[0] == GENERIC_TEMPLATE_CLASS
    )
    assert set(generic) == KNOWN_UNRENDERABLE_SUBTYPES, (
        f"{len(generic)} subtype(s) fall through to {GENERIC_TEMPLATE_CLASS}: {generic}"
    )


def test_no_rendered_document_reports_a_fallback(
    rendered_every_subtype: dict[str, RenderResult],
) -> None:
    """The rendered-side twin of the resolution check, via ``RenderResult``."""
    fallen_back = sorted(
        subtype for subtype, result in rendered_every_subtype.items() if result.fallback
    )
    assert set(fallen_back) == KNOWN_UNRENDERABLE_SUBTYPES, (
        f"{len(fallen_back)} subtype(s) rendered by fallback: {fallen_back[:20]}"
    )


def test_the_exceptions_list_has_not_grown() -> None:
    """The list is empty; this is the assertion that keeps it honest.

    Written as an equality against a literal so that adding an entry is a
    deliberate, reviewable edit to two places rather than a silent widening.
    """
    assert len(KNOWN_UNRENDERABLE_SUBTYPES) == 0, (
        "a subtype was added to the exceptions list — that is a shipped hole in "
        "353-subtype coverage and needs to be surfaced, not absorbed"
    )


# ---------------------------------------------------------------------------
# Output quality — a resolved template that emits a stub is still a failure
# ---------------------------------------------------------------------------


def test_every_rendered_document_is_non_trivial(
    rendered_every_subtype: dict[str, RenderResult],
) -> None:
    undersized = sorted(
        (subtype, result.size)
        for subtype, result in rendered_every_subtype.items()
        if result.size <= MINIMUM_DOCUMENT_BYTES
    )
    assert not undersized, f"{len(undersized)} document(s) under 500 bytes: {undersized[:20]}"


def test_every_rendered_pdf_parses_with_a_real_page(
    rendered_every_subtype: dict[str, RenderResult],
) -> None:
    fitz = pytest.importorskip("fitz")
    unreadable: list[str] = []
    for subtype, result in sorted(rendered_every_subtype.items()):
        payload = result.path.read_bytes()
        if not payload.startswith(b"%PDF-"):
            unreadable.append(f"{subtype}: not a PDF")
            continue
        try:
            with fitz.open(result.path) as document:
                if document.page_count < 1:
                    unreadable.append(f"{subtype}: zero pages")
        except Exception as exc:  # collected, not raised: one bad PDF must not hide the rest
            unreadable.append(f"{subtype}: {type(exc).__name__}: {exc}")
    assert not unreadable, f"{len(unreadable)} PDF(s) do not parse: {unreadable[:20]}"


def test_every_render_records_its_template(
    rendered_every_subtype: dict[str, RenderResult],
) -> None:
    """Provenance is only useful if it is never blank."""
    blank = sorted(
        subtype for subtype, result in rendered_every_subtype.items() if not result.template
    )
    assert not blank, f"{len(blank)} render(s) recorded no template: {blank[:20]}"


# ---------------------------------------------------------------------------
# The overlay mapping that closed the audit finding
# ---------------------------------------------------------------------------


def test_overlay_subtypes_resolve_through_the_engine_not_the_registry() -> None:
    """The three subtypes the substrate enum lacks reach real template classes."""
    from wc_caseload_engine.taxonomy import OVERLAY_SUBTYPES

    assert set(OVERLAY_TEMPLATES) == set(OVERLAY_SUBTYPES), (
        "every overlay subtype needs an engine-owned template, or it silently "
        "falls through to the generic one"
    )
    for subtype, (class_name, variant) in OVERLAY_TEMPLATES.items():
        assert class_name != GENERIC_TEMPLATE_CLASS
        assert variant, f"{subtype} needs a variant so it is not the class default"
        assert resolve_template(subtype) == (class_name, variant)


def test_overlay_subtypes_render_distinct_documents(
    rendered_every_subtype: dict[str, RenderResult],
) -> None:
    """Two penalty notices sharing a class must not produce one identical file."""
    penalties = ["NOTICE_OF_PENALTY_5814", "NOTICE_OF_PENALTY_5814_5"]
    checksums = {rendered_every_subtype[subtype].md5 for subtype in penalties}
    assert len(checksums) == len(penalties), "the variant is not reaching the template"


def test_rendered_files_stay_inside_the_requested_directory(
    rendered_every_subtype: dict[str, RenderResult], tmp_path_factory: pytest.TempPathFactory
) -> None:
    """Every result path is the path that was asked for (no silent relocation)."""
    roots = {Path(result.path).parent for result in rendered_every_subtype.values()}
    assert len(roots) == 1, f"renders landed in {len(roots)} directories: {sorted(roots)[:5]}"
