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
        and entry["subtype"] not in UNCAPTIONED_SUBTYPES
        and adj.lower() not in text.lower()
    ]
    assert not missing, f"{len(missing)} post-filing document(s) omit {adj}: {missing[:20]}"


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
        if entry["documentDate"] >= filed_on and entry["subtype"] not in UNCAPTIONED_SUBTYPES
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
