"""Case-level coherence, swept across a whole case rather than sampled.

The previous evidence for ISC-58 was a substring probe over three documents of
one case. Three of ninety is a spot check, and a spot check cannot distinguish
"every document shares one cast" from "the three I looked at did". This file
reads every text-bearing document of a demo case and asks two questions:

* does the case's own identity appear in all of them, and
* does any *other* case's identity appear in any of them?

The second question is the one a sampled probe can never answer, and it is the
failure that would matter most: a cast leaking across cases turns a caseload
into seven copies of one confused file.

Two honest scope limits, both load-bearing:

**Scanned PDFs carry no extractable text.** They are rasters, rendered from the
same template and cast as their native siblings. They are counted and reported,
never silently skipped.

**An ADJ number does not exist before the case is filed.** The WCAB assigns it
when the Application for Adjudication is filed, so a DWC-1 claim form or an
intake letter written weeks earlier correctly has no ADJ number on it. Asserting
otherwise would demand that the generator produce a document that could not
exist. The assertion is therefore keyed to the filing date, which is a stronger
statement than the flat version: it says every document that *should* carry the
case number does.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

from typing import Any

import pytest

from conftest import NON_TEXT_FORMATS, extract_text, iter_documents, requires_substrate

pytestmark = requires_substrate

SWEPT_CASE = "alvarez-denied-recon-remand"
"""The case swept in full — denied claim, reconsideration, settled on remand.

Chosen because it is the longest-running demo file (55 documents spanning
pre-filing intake through a post-remand settlement), so it exercises the widest
span of document kinds. Deliberately not chosen by which case passes.
"""

FILING_SUBTYPE_PREFIX = "APPLICATION_FOR_ADJUDICATION"
"""Filing the Application is what causes an ADJ number to exist."""

UNCAPTIONED_SUBTYPES: frozenset[str] = frozenset({"MEDICAL_CHRONOLOGY_TIMELINE"})
"""Post-filing documents that legitimately carry no case caption.

A medical chronology is an internal working table of treatment dates — it is
attorney work product, not a filing, and it is not captioned. One entry, listed
explicitly so that a second one has to be argued for rather than absorbed.
"""

UNCAPTIONED_TEMPLATES: frozenset[str] = frozenset({"ClientIntake"})
"""Substrate templates that render no case caption at all, for any subtype.

``pdf_templates/correspondence/client_intake.py`` builds a letter — letterhead,
date, client address, ``Re:`` line, body — and never prints an ADJ number. Sixty
subtypes route through it (registry.py), because the substrate uses it as its
generic letter shape; it takes a ``variant`` argument it does not read.

Exempting by *template* rather than by subtype is deliberate. The subtype list
would be sixty entries long and would grow silently, and it would describe
symptoms. One template name describes the cause: a class of documents whose
renderer has no caption block to put a case number in. This is a substrate
template-fidelity limitation, documented in ``README.md`` alongside the
hard-coded letterhead firm; the engine does not edit substrate templates.

The set is deliberately tiny, and
:func:`test_the_uncaptioned_template_exemption_is_narrow` keeps it that way: a
second caption-less template has to be argued for, and the exemption may never
cover so much of the case file that the assertion stops meaning anything.
"""


def _template_class(entry: dict[str, Any]) -> str:
    """The template class that rendered this document.

    Manifests record ``ClassName/variant`` (``ClientIntake/qme_105``), because a
    variant is worth knowing when reading a file listing. Caption behaviour is a
    property of the class, not the variant — ``ClientIntake`` takes a variant
    argument it never reads — so the class is what this splits out.
    """
    return str(entry.get("template", "")).split("/", 1)[0]


def _is_captioned(entry: dict[str, Any]) -> bool:
    """``True`` when this document's renderer produces a captioned filing."""
    return (
        entry["subtype"] not in UNCAPTIONED_SUBTYPES
        and _template_class(entry) not in UNCAPTIONED_TEMPLATES
    )


@pytest.fixture(scope="module")
def swept(demo_manifests: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """The manifest of the case being swept."""
    assert SWEPT_CASE in demo_manifests, f"{SWEPT_CASE} is not in the demo caseload"
    return demo_manifests[SWEPT_CASE]


@pytest.fixture(scope="module")
def swept_texts(swept: dict[str, Any]) -> list[tuple[dict[str, Any], str]]:
    """``(manifest entry, extracted text)`` for every text-bearing document."""
    texts: list[tuple[dict[str, Any], str]] = []
    for entry, path in iter_documents(swept):
        if entry["format"] in NON_TEXT_FORMATS:
            continue
        text = extract_text(path, entry["format"])
        if text.strip():
            texts.append((entry, text))
    return texts


def test_the_sweep_actually_covers_the_case(
    swept: dict[str, Any], swept_texts: list[tuple[dict[str, Any], str]]
) -> None:
    """Guards the sweep: an empty text list would make everything below pass."""
    total = len(swept["documents"])
    scanned = sum(1 for entry in swept["documents"] if entry["format"] in NON_TEXT_FORMATS)
    assert total >= 40, f"{SWEPT_CASE} has only {total} documents"
    assert len(swept_texts) == total - scanned, (
        f"{total - scanned - len(swept_texts)} text-bearing document(s) yielded no text"
    )
    assert len(swept_texts) >= 30, "too few text-bearing documents to call this a sweep"


def test_every_document_names_the_applicant(
    swept: dict[str, Any], swept_texts: list[tuple[dict[str, Any], str]]
) -> None:
    """The applicant's surname is the one identity every document must carry."""
    surname = swept["applicant"].split()[-1]
    missing = [
        f"{entry['filename']} ({entry['subtype']})"
        for entry, text in swept_texts
        if surname.lower() not in text.lower()
    ]
    assert not missing, f"{len(missing)} document(s) omit {surname!r}: {missing[:20]}"


def test_every_post_filing_document_carries_the_adj_number(
    swept: dict[str, Any], swept_texts: list[tuple[dict[str, Any], str]]
) -> None:
    """Once the case is filed, every captioned document states the case number."""
    adj = swept["adjNumber"]
    filing_dates = [
        entry["documentDate"]
        for entry in swept["documents"]
        if entry["subtype"].startswith(FILING_SUBTYPE_PREFIX)
    ]
    assert filing_dates, f"{SWEPT_CASE} never files an Application — pick another case"
    filed_on = min(filing_dates)

    missing = [
        f"{entry['filename']} ({entry['subtype']}, {entry['documentDate']})"
        for entry, text in swept_texts
        if entry["documentDate"] >= filed_on
        and _is_captioned(entry)
        and adj.lower() not in text.lower()
    ]
    assert not missing, f"{len(missing)} post-filing document(s) omit {adj}: {missing[:20]}"


def test_the_uncaptioned_template_exemption_is_narrow(
    swept: dict[str, Any], swept_texts: list[tuple[dict[str, Any], str]]
) -> None:
    """An exemption large enough to hide a regression is not an exemption.

    The caption assertion above cannot demand a case number from a renderer that
    has no caption block. That is a real limit, but it is only acceptable while
    it stays a minority of the file — if half the case file routed through the
    letter template, "every post-filing document carries the ADJ number" would
    be true of almost nothing.
    """
    exempt = [entry for entry, _ in swept_texts if not _is_captioned(entry)]
    captioned = [entry for entry, _ in swept_texts if _is_captioned(entry)]

    assert captioned, "every document is exempt — the caption assertion is vacuous"
    assert len(exempt) <= len(swept_texts) // 3, (
        f"{len(exempt)}/{len(swept_texts)} documents are exempt from the caption "
        f"assertion: {[e['subtype'] for e in exempt][:10]}"
    )

    unexpected = {
        _template_class(entry)
        for entry in exempt
        if entry["subtype"] not in UNCAPTIONED_SUBTYPES
    } - UNCAPTIONED_TEMPLATES
    assert not unexpected, (
        f"documents exempted by a template not declared caption-less: {sorted(unexpected)}"
    )


def test_pre_filing_documents_are_the_ones_without_a_case_number(
    swept: dict[str, Any], swept_texts: list[tuple[dict[str, Any], str]]
) -> None:
    """The date rule above must be doing work, not excusing an empty set.

    If every document carried the ADJ number regardless of date, the filing-date
    condition would be decorative and a real regression could hide behind it.
    """
    adj = swept["adjNumber"]
    filed_on = min(
        entry["documentDate"]
        for entry in swept["documents"]
        if entry["subtype"].startswith(FILING_SUBTYPE_PREFIX)
    )
    without = [
        entry for entry, text in swept_texts if adj.lower() not in text.lower()
    ]
    assert without, "no document lacks the ADJ number — the filing-date rule is untested"
    late = [
        f"{entry['filename']} ({entry['subtype']}, {entry['documentDate']})"
        for entry in without
        if entry["documentDate"] >= filed_on and _is_captioned(entry)
    ]
    assert not late, f"post-filing documents without a case number: {late}"


def test_no_other_cases_identity_appears_in_this_case(
    swept: dict[str, Any],
    swept_texts: list[tuple[dict[str, Any], str]],
    demo_manifests: dict[str, dict[str, Any]],
) -> None:
    """Cross-contamination guard, using the other six casts as the probe set.

    A hit here is either a genuine cast leak or a Faker draw that happened to
    reuse another case's surname for a doctor or a judge. Both warrant a look:
    the first is a correctness bug, the second makes a generated corpus
    ambiguous to anyone reading it.
    """
    others = {
        case_id: (manifest["applicant"].split()[-1], manifest["adjNumber"])
        for case_id, manifest in demo_manifests.items()
        if case_id != SWEPT_CASE
    }
    assert len(others) >= 5, "need the rest of the caseload to make this a real guard"

    intrusions: list[str] = []
    for entry, text in swept_texts:
        lowered = text.lower()
        for case_id, (surname, adj) in sorted(others.items()):
            if surname.lower() in lowered:
                intrusions.append(f"{entry['filename']}: surname {surname!r} from {case_id}")
            if adj.lower() in lowered:
                intrusions.append(f"{entry['filename']}: {adj} from {case_id}")
    assert not intrusions, f"{len(intrusions)} cross-case intrusion(s): {intrusions[:20]}"


def test_every_case_manifest_agrees_with_itself(
    demo_manifests: dict[str, dict[str, Any]],
) -> None:
    """Cheap whole-caseload invariant: identities are distinct per case."""
    adjs = [manifest["adjNumber"] for manifest in demo_manifests.values()]
    surnames = [manifest["applicant"].split()[-1] for manifest in demo_manifests.values()]
    assert len(set(adjs)) == len(adjs), f"duplicate ADJ numbers: {adjs}"
    assert len(set(surnames)) == len(surnames), f"duplicate applicant surnames: {surnames}"


# ---------------------------------------------------------------------------
# The employer trio
# ---------------------------------------------------------------------------


class TestSeededIndustryIsCoherent:
    """A seeded industry has to reach everything the industry decides.

    The substrate draws ``(industry, company, position)`` as one unit, so the
    trio is coherent until something changes one member of it. The seed's
    ``profile.employer.industry`` did exactly that, and too late: the coined
    company name and the position were both derived from the substrate's
    *pre-override* industry, and only ``department`` carried the seed's.

    The second release review's reproduction is ``rng_seed=2`` with
    ``industry: healthcare`` — a coined name from another industry's suffix
    pool, a healthcare department, and a position from that other industry
    again. Three fields, two industries, one employer.

    The fix applies the seed's industry *before* anything derives from it, so
    "industry" means one thing for the whole cast.
    """

    INDUSTRIES = ("healthcare", "construction", "government", "retail_service")

    @staticmethod
    def _cast_employer(rng_seed: int, industry: str) -> Any:
        from wc_caseload_engine.case_context import build_case_cast
        from wc_caseload_engine.lifecycle_bridge import build_timeline
        from wc_caseload_engine.seeds import parse_case_seed

        seed = parse_case_seed(
            {
                "case_id": "industry-coherence",
                "rng_seed": rng_seed,
                "injury": {
                    "type": "specific",
                    "date_of_injury": "2024-03-04",
                    "body_parts": [{"part": "lumbar_spine", "icd10": "M54.5"}],
                },
                "lifecycle": {"target_stage": "discovery", "eval_type": "none"},
                "profile": {"employer": {"industry": industry}},
            }
        )
        return build_case_cast(seed, build_timeline(seed)).case.employer

    def test_the_reproduction_seed_produces_one_coherent_trio(self) -> None:
        """rng_seed=2 + healthcare — name, department and position must agree."""
        from wc_caseload_engine.case_context import employer_suffixes_for_industry
        from wc_caseload_engine.substrate import import_substrate

        employer = self._cast_employer(2, "healthcare")
        suffixes = employer_suffixes_for_industry("healthcare")
        positions = import_substrate("data.wc_constants").EMPLOYER_TEMPLATES["healthcare"]

        assert any(employer.company_name.endswith(suffix) for suffix in suffixes), (
            f"{employer.company_name!r} carries no healthcare suffix — "
            f"expected one of {suffixes}"
        )
        assert employer.department == "healthcare"
        assert employer.position in {position for _company, position in positions}, (
            f"{employer.position!r} is not a healthcare position"
        )

    @pytest.mark.parametrize("industry", INDUSTRIES)
    def test_every_seeded_industry_reaches_all_three_fields(self, industry: str) -> None:
        """The class, not the instance — four industries, ten draws each."""
        from wc_caseload_engine.case_context import employer_suffixes_for_industry
        from wc_caseload_engine.substrate import import_substrate

        suffixes = employer_suffixes_for_industry(industry)
        templates = import_substrate("data.wc_constants").EMPLOYER_TEMPLATES[industry]
        positions = {position for _company, position in templates}

        for rng_seed in range(1, 11):
            employer = self._cast_employer(rng_seed, industry)
            assert any(employer.company_name.endswith(suffix) for suffix in suffixes), (
                f"rng_seed={rng_seed}: {employer.company_name!r} is not a {industry} name"
            )
            assert employer.department == industry
            assert employer.position in positions, (
                f"rng_seed={rng_seed}: {employer.position!r} is not a {industry} position"
            )

    def test_a_seeded_occupation_still_outranks_the_industry(self) -> None:
        """The seed is the contract, and the more specific field wins.

        Re-deriving the position from the industry must not overwrite a position
        the seeder named outright.
        """
        from wc_caseload_engine.case_context import build_case_cast
        from wc_caseload_engine.lifecycle_bridge import build_timeline
        from wc_caseload_engine.seeds import parse_case_seed

        seed = parse_case_seed(
            {
                "case_id": "occupation-wins",
                "rng_seed": 2,
                "injury": {
                    "type": "specific",
                    "date_of_injury": "2024-03-04",
                    "body_parts": [{"part": "lumbar_spine", "icd10": "M54.5"}],
                },
                "lifecycle": {"target_stage": "discovery", "eval_type": "none"},
                "profile": {
                    "employer": {"industry": "healthcare"},
                    "applicant": {"occupation": "Surgical Technologist"},
                },
            }
        )
        employer = build_case_cast(seed, build_timeline(seed)).case.employer
        assert employer.position == "Surgical Technologist"

    def test_an_unknown_industry_falls_through_without_breaking(self) -> None:
        """A free-text industry is legal; it just cannot be made coherent.

        ``profile.employer.industry`` is an open string, so a seed may name an
        industry the substrate has no positions for. That must degrade to the
        neutral suffix pool and the substrate's own position, not raise.
        """
        employer = self._cast_employer(5, "aerospace")
        assert employer.department == "aerospace"
        assert employer.company_name
        assert employer.position
