"""AJC-64 item 0b — an INDEPENDENT re-parse of the pinned PDRS extracted text.

`tests/test_rating_coherence.py` compared the vendored JSON to production
lookups that read the same JSON. That oracle passes identically against
fabricated tables: it asks the artifact to report on itself, which is the same
self-comparison defect the PDF pin had one layer up (M5-R42(b)).

This module parses the five tables **out of the pinned extracted text** so the
shipped JSON can be checked cell for cell against something that is not itself.
Two properties make it an independent parse rather than a second copy of the
audit's:

* **it anchors on content, never on line numbers.** The audit script hand-tuned
  slices like ``L[2910:2990]``; a parser that agrees with a JSON *because both
  were produced by the same hand-tuned slice* has not checked anything. Every
  region here is located by its printed heading;
* **its cell counts are pinned as literals and asserted**, so a parser that
  finds nothing fails loudly instead of vacuously agreeing with an empty
  intersection. FEC 800 · impairment 215 · occupational 808 · age 1,000 ·
  Section 4 5,085.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import hashlib
import re
from functools import lru_cache
from pathlib import Path

from wc_caseload_engine.rating_sources import PDRS_2005_EXTRACTED_TEXT_SHA256

#: Cell counts, as literals. A parser finding nothing must FAIL, not pass.
EXPECTED_CELL_COUNTS = {
    "fec": 800,
    "imp": 215,
    "occ": 808,
    "age": 1_000,
    "section4": 5_085,
}

FEC_RANK_WORDS = {
    "One": 1,
    "Two": 2,
    "Three": 3,
    "Four": 4,
    "Five": 5,
    "Six": 6,
    "Seven": 7,
    "Eight": 8,
}

_INT = re.compile(r"-?\d+")


def extracted_text_path() -> Path:
    """The pinned extracted text, as PACKAGE DATA (round-1 finding F5).

    Moved out of ``tests/fixtures`` so that the artifact the parity oracles
    parse is the same artifact ``PDRS_VENDORED_ARTIFACTS`` pins and the same one
    ``tools/pdrs_extract.py`` derives. One canonical location: a pin naming one
    copy while the oracles read another is provenance about a file nothing
    consumes.
    """
    from wc_caseload_engine import rating_sources

    return rating_sources.pdrs_data_dir() / "pdrs-2005-extracted-text.txt"


@lru_cache(maxsize=1)
def extracted_text() -> str:
    """The pinned artifact, hashed from **its own bytes** before it is used.

    The chain terminates in a file. Comparing a pinned digest to another copy
    of the same constant — the defect ``m24-31`` restores — proves that a
    string equals itself and nothing about the artifact.
    """
    payload = extracted_text_path().read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != PDRS_2005_EXTRACTED_TEXT_SHA256:
        raise AssertionError(
            "PDRS extracted text hashes "
            f"{digest}, pinned {PDRS_2005_EXTRACTED_TEXT_SHA256}"
        )
    return payload.decode("utf-8")


def _lines() -> list[str]:
    return extracted_text().split("\n")


def _region(start_anchor: str, end_anchor: str | None = None) -> list[str]:
    """Lines between two printed headings, located by content.

    Anchored rather than sliced. A hand-tuned line range is how a "second"
    parser ends up being the first one wearing a different name.
    """
    lines = _lines()
    start = next(
        (i for i, line in enumerate(lines) if start_anchor in line), None
    )
    if start is None:
        raise AssertionError(f"anchor {start_anchor!r} is not in the pinned text")
    if end_anchor is None:
        return lines[start:]
    end = next(
        (i for i, line in enumerate(lines[start + 1 :], start + 1) if end_anchor in line),
        None,
    )
    if end is None:
        raise AssertionError(f"anchor {end_anchor!r} is not after {start_anchor!r}")
    return lines[start:end]


def _ints(text: str) -> list[int]:
    return [int(match) for match in _INT.findall(text)]


def parse_fec() -> dict[str, int]:
    """FEC rank x AMA whole-person impairment standard — 8 x 100 = 800 cells."""
    region = _region(
        "FUTURE EARNING CAPACITY (FEC) ADJUSTMENT TABLE", "SECTION 3"
    )
    cells: dict[str, int] = {}
    header: list[int] = []
    for line in region:
        head = re.match(r"\s*Rank\s+(\d.*)$", line)
        if head:
            header = _ints(head.group(1))
            continue
        row = re.match(
            r"\s*(One|Two|Three|Four|Five|Six|Seven|Eight)\s+(\d.*)$", line
        )
        if row and header:
            values = _ints(row.group(2))
            if len(values) != len(header):
                continue
            rank = FEC_RANK_WORDS[row.group(1)]
            for standard, value in zip(header, values, strict=True):
                cells[f"{rank}|{standard}"] = value
    return cells


def parse_impairment() -> dict[str, list[object]]:
    """Impairment number -> (FEC rank, description) — 215 entries."""
    region = _region("IMPAIRMENT", "FUTURE EARNING CAPACITY (FEC) ADJUSTMENT TABLE")
    entries: dict[str, list[object]] = {}
    pattern = re.compile(
        r"(\d\d\.\d\d\.\d\d\.\d\d)\s+(\d)\s+(\S.*?)(?=\s{3,}\d\d\.\d\d|\Z)"
    )
    for line in region:
        for match in pattern.finditer(line):
            entries[match.group(1)] = [int(match.group(2)), match.group(3).strip()]
    return entries


def parse_occupational() -> dict[str, list[int]]:
    """Standard rating percent x variant C-J — 101 rows x 8 = 808 cells."""
    region = _region("SECTION 5 - OCCUPATIONAL ADJUSTMENT", "SECTION 6 - AGE ADJUSTMENT")
    rows: dict[str, list[int]] = {}
    for line in region:
        values = _ints(line)
        # The page prints two half-tables side by side: one logical row on the
        # left (percent + 8 variants) and another on the right.
        if len(values) == 18 and values[0] <= 100 and values[9] <= 100:
            rows[str(values[0])] = values[1:9]
            rows[str(values[9])] = values[10:18]
        elif (
            len(values) == 9
            and values[0] <= 100
            and line.strip().startswith(str(values[0]))
        ):
            rows[str(values[0])] = values[1:]
    return rows


def parse_age() -> dict[str, list[int]]:
    """Rating x age band — 100 rows x 10 bands = 1,000 cells."""
    region = _region("AGE AT TIME OF INJURY", "SECTION 7")
    rows: dict[str, list[int]] = {}
    for line in region:
        if "-" in line:
            # The band header line ("22 - 26" ...) is not a data row.
            continue
        values = _ints(line)
        if len(values) == 11 and 1 <= values[0] <= 100:
            rows[str(values[0])] = values[1:]
    return rows


def parse_section4(groups: tuple[str, ...]) -> dict[str, dict[str, str]]:
    """Impairment row x occupational group -> variant letter C-J.

    113 rows x 45 groups = 5,085 cells. Each logical row is printed across two
    column-half pages — groups 110-330 then 331-590 — so the halves are joined
    on the row label rather than assumed adjacent.
    """
    region = _region("SECTION 4 - OCCUPATIONAL VARIANTS", "SECTION 5 - OCCUPATIONAL")
    label = r"(\d\d\.\d\d(?:\.(?:\d\d|XX)\.(?:\d\d|XX)|\s*--\s*\d\d\.\d\d)?)"
    row_pattern = re.compile(
        rf"^\s*{label}\s{{2,}}(\S.*?)\s{{2,}}((?:[C-J]\s+){{5,}}[C-J])\s*$"
    )
    halves: dict[str, list[tuple[str, list[str]]]] = {}
    for line in region:
        match = row_pattern.match(line.rstrip())
        if not match:
            continue
        printed = re.sub(r"\s*--\s*", " -- ", match.group(1).strip())
        key = SECTION4_SOURCE_LABEL_VARIANTS.get(printed, printed)
        halves.setdefault(key, []).append((match.group(2).strip(), match.group(3).split()))
    matrix: dict[str, dict[str, str]] = {}
    for key, parts in halves.items():
        # Whitespace only: the source prints `FACE-EYE` on one half page and
        # `FACE - EYE` on the other. Collapsing whitespace is a typographic
        # normalization; case, letters and punctuation are left alone, because
        # those are the content the agreement check exists to compare.
        names = {re.sub(r"\s+", "", name) for name, _ in parts}
        if len(names) != 1:
            # The two halves disagree about which row this is. Refused rather
            # than merged: a mis-joined row would silently mix two impairments'
            # variants and still count 45 cells.
            continue
        letters = [letter for _, part in parts for letter in part]
        if len(letters) != len(groups):
            continue
        matrix[key] = dict(zip(groups, letters, strict=True))
    return matrix


SECTION4_SOURCE_LABEL_VARIANTS = {
    # The SOURCE prints two different labels for one logical row: the
    # groups 110-330 half heads it `17.01.02.XX` and the groups 331-590 half
    # heads it `17.01.02.00`. Both halves print the same row name, `LEG-AMPUT`,
    # in the same row position on their respective pages, which is the evidence
    # that they are one row rather than two.
    #
    # Recorded as a single named exception, not absorbed into the label regex.
    # Widening the pattern until the join succeeded is exactly the failure mode
    # M5-R47b names one layer up: a canonicalizer quietly relaxed until the
    # comparison passes. `parse_section4` additionally refuses any row whose
    # halves disagree on the row NAME, so this exception cannot be used to merge
    # two genuinely different rows.
    "17.01.02.00": "17.01.02.XX",
}
