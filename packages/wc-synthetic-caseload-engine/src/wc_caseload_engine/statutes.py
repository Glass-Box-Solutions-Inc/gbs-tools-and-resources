"""AJC-64 item 0e — sha256-pinned statutory authority (M5-R47).

The distinction this module exists for is **provenance, not availability**.
Statutory text is easy to obtain; a pin is the evidence that the text we cite
is the text that was published and has not moved since. A database row with
correct content and no digest cannot discharge that — it is the
self-comparison problem one layer up, and it is the same defect item 0b fixes
for the PDRS PDF.

So each section M5 relies on is fetched once from the Legislature's own
service (``leginfo.legislature.ca.gov``), canonicalized by the rule below,
written to ``data/statutes/`` as bytes, and pinned here by the sha256 **of
those bytes**. :func:`load_section` hashes the artifact it just read and
compares that digest to the literal — never a constant to another copy of
itself. ``m24-98`` restores the self-comparison and must redden.

Refresh with ``tools/statute_pin.py --fetch``, which re-fetches, re-derives
and prints the digests; a moved digest is a deliberate, reviewable commit,
exactly as a golden re-record is.

## Canonicalization (M5-R47b)

Raw equality between an HTML page and a database string fails one hundred
percent of the time, and would be "fixed" by whoever implements it, in
whatever way makes it pass — the worst possible outcome for a provenance
check. So the rule is pinned, applied identically to both sides, and itself
mutation-guarded (``m24-127``):

1. strip HTML tags; decode HTML entities to their unicode characters
2. normalize unicode to NFC
3. replace every run of unicode whitespace (including NBSP) with one space
4. strip leading and trailing whitespace
5. **do not** alter case, punctuation, digits or subdivision markers — those
   are the content the comparison exists to check

## DOI versioning

Four sections are DOI-versioned — §§4658, 4453, 4663 and 4660.1 — because the
engine accepts injury dates from 2005 onward and each has been amended inside
that span. The ingest module's own warning governs: pinned coverage is *a hard
floor, not an absence of amendments*, so a date of injury **below** a
section's floor fails closed rather than silently using the earliest text.
§4664 needs no DOI-versioned pin and the reason is dispositive: it was
*created* by SB 899 effective 2004-04-19 and has no earlier version, and every
DOI the engine can process postdates that.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import datetime as dt
import hashlib
import html
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "CORROBORATED_SECTIONS",
    "KOPPING_PIN",
    "SECTION_4663_AMENDING_ACT",
    "SECTION_4663_AMENDING_ACT_FILENAME",
    "SECTION_4663_AMENDING_ACT_SHA256",
    "SECTION_4663_MODELLED_SUBDIVISIONS",
    "SECTION_4663_STABILITY_LIMITATION",
    "SECTION_SIGIL",
    "STATUTE_PINS",
    "CasePin",
    "StatutePin",
    "StatutePinError",
    "canonicalize_statute_text",
    "corroborate_against_snapshot",
    "load_section",
    "require_kopping_pin",
    "section_4663_amending_act_text",
    "section_text_for_doi",
    "statutes_dir",
    "strip_section_heading",
    "subdivision_text",
]

STATUTE_PIN_MISSING = "M5_STATUTE_PIN_MISSING"
STATUTE_PIN_DIGEST_MISMATCH = "M5_STATUTE_PIN_DIGEST_MISMATCH"
STATUTE_DOI_BELOW_PINNED_FLOOR = "M5_STATUTE_DOI_BELOW_PINNED_FLOOR"

LEGINFO_SECTION_URL = (
    "https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml"
    "?lawCode=LAB&sectionNum={section}"
)
"""The one retrieval path. Recorded so a pin names where its bytes came from."""


class StatutePinError(RuntimeError):
    """A pinned artifact is missing, unreadable, or not the pinned bytes."""


_TAG = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"\s+", re.UNICODE)


def canonicalize_statute_text(raw: str) -> str:
    """The M5-R47b canonical form. Pinned here; guarded by ``m24-127``.

    Deliberately **not** case-folding and **not** touching punctuation: a
    canonicalizer widened until the comparison passes is the failure this rule
    exists to prevent, and subdivision markers are precisely the content a
    cross-check is checking.
    """
    text = _TAG.sub(" ", raw)
    text = html.unescape(text)
    text = unicodedata.normalize("NFC", text)
    text = _WHITESPACE.sub(" ", text)
    return text.strip()


SECTION_SIGIL = "§"

def strip_section_heading(text: str, section: str) -> str:
    """Drop the leading ``§NNNN.`` / ``NNNN.`` heading token, and nothing else.

    The two sources format the section's own heading differently: the
    ``regulatory_sections`` row writes ``§4663.`` where the leginfo artifact
    writes ``4663.``. That is a difference in how each store labels the row,
    not a difference in the law.

    **Why this is not a widened canonicalizer.** M5-R47b forbids relaxing
    :func:`canonicalize_statute_text` until a comparison passes, and adding a
    "strip § characters" rule there would be exactly that — it would silently
    erase a sigil appearing anywhere in the body, including inside a
    cross-reference, and no test would notice. This function instead removes
    **one specific token at position zero**, matched against the section number
    it was asked about. A sigil anywhere else survives, and that is probed.
    """
    head = text
    if head.startswith(SECTION_SIGIL):
        head = head[len(SECTION_SIGIL) :].lstrip()
    prefix = f"{section}."
    if head.startswith(prefix):
        return head[len(prefix) :].strip()
    # No recognisable heading: return the text untouched rather than guessing.
    return text.strip()


def statutes_dir() -> Path:
    """Where the pinned artifacts live, as package data."""
    return Path(__file__).resolve().parent / "data" / "statutes"


@dataclass(frozen=True)
class StatutePin:
    """One pinned section: the artifact, its digest, and its applicability."""

    section: str
    filename: str
    sha256: str
    doi_versioned: bool
    doi_floor: dt.date | None
    required_markers: tuple[str, ...]
    note: str = ""

    @property
    def path(self) -> Path:
        return statutes_dir() / self.filename

    @property
    def source_url(self) -> str:
        return LEGINFO_SECTION_URL.format(section=self.section)


def _pin(
    section: str,
    sha256: str,
    *,
    doi_floor: str | None,
    markers: tuple[str, ...],
    note: str = "",
) -> StatutePin:
    return StatutePin(
        section=section,
        filename=f"lc-{section.replace('.', '-')}.txt",
        sha256=sha256,
        doi_versioned=doi_floor is not None,
        doi_floor=dt.date.fromisoformat(doi_floor) if doi_floor else None,
        required_markers=markers,
        note=note,
    )


STATUTE_PINS: dict[str, StatutePin] = {
    pin.section: pin
    for pin in (
        _pin(
            "4664",
            "809201a5ab0a1cd6c61ecd1f5b7aea0908af5e38a2db7849dbda471384aed9d1",
            doi_floor=None,
            markers=("(a)", "(b)", "(c) (1)", "(A)", "(G)", "(2)"),
            note=(
                "NOT DOI-versioned: created by Stats. 2004, Ch. 34, Sec. 35, "
                "effective 2004-04-19, so it has no earlier version and every "
                "DOI the engine accepts postdates its creation."
            ),
        ),
        _pin(
            "4658",
            "bbd8269e35869200ff2bfb32ff4ed85461eb14d0f4c7349706f1d58672b38a04",
            doi_floor="2005-01-01",
            markers=("(a)", "(b)", "(d)"),
            note="Lane B primary source for the weeks tiers.",
        ),
        _pin(
            "4453",
            "022975722ca09a2e4603d7ac9f6b1bf6f05b8da00783da8b175c222c1cb4821a",
            doi_floor="2005-01-01",
            markers=("(a)", "(b)", "(c)"),
            note="The rate/bracket basis behind SI-M5-008.",
        ),
        _pin(
            "4659",
            "f8033779717f500c4e609e1d8683afffd803c78e338f3a983f75d81ca2353ec3",
            doi_floor=None,
            markers=("(a)", "(b)", "(c)"),
            note="Life pension (SI-M5-009). Lane B.",
        ),
        _pin(
            "4751",
            "a66bafbd14ca82354e73a12983cf3546afb3e736816783e7bf3e0b9557b179ec",
            doi_floor=None,
            markers=("hand, arm, foot, leg, or eye",),
            note="SIBTF elements, including the member-limited branch (M5-R36a).",
        ),
        _pin(
            "4663",
            "812e3436572afb62a1c3021f2995ee5bd6afd56bc546f1484de5b364c4d2f30b",
            doi_floor="2005-01-01",
            markers=("(a)", "(b)", "(c)", "(d)"),
            note=(
                "Causal apportionment and its burden split (M5-R16). "
                "DOI-versioned: last amended 2016-01-01 while the engine "
                "accepts 2005-era DOIs."
            ),
        ),
        _pin(
            "4660.1",
            "3d8daae5d283023301f7efed6e93f295c99dd0fa0eee2ec03eb535af01459eba",
            doi_floor="2013-01-01",
            markers=("(a)", "(b)", "(c)"),
            note=(
                "The post-2013 1.4 DFEC modifier. Item 0b's docstring citation "
                "does not ship without this pin (M5-R47)."
            ),
        ),
    )
}


SECTION_4663_AMENDING_ACT = "Stats. 2016, Ch. 86, Sec. 218 (SB 1171)"
SECTION_4663_AMENDING_ACT_FILENAME = "lc-4663-stats2016-ch86-sec218.txt"
SECTION_4663_AMENDING_ACT_SHA256 = (
    "05d5e4d58551b610a50d11981e70a821efc9e04c4e17a60eee4f439583c44e86"
)

#: The subdivisions M5-R16 actually models. Only these are asserted stable.
SECTION_4663_MODELLED_SUBDIVISIONS = ("(a)", "(c)")

SECTION_4663_STABILITY_LIMITATION = (
    "PARTIAL. M5-R47a prescribes fetching BOTH the current and the pre-2016 "
    "text of section 4663 and asserting the (a) and (c) subdivisions are "
    "identical between them. leginfo serves only the CURRENT text of a code "
    "section and its chaptered bill texts carry no strikeout markup, so the "
    "pre-2016 text is not retrievable from the pinned source at all. What IS "
    "retrievable, and is pinned here, is the amending act's own enacted text: "
    "Stats. 2016, Ch. 86, Sec. 218, whose bill SB 1171 is the Legislature's "
    "annual 'Maintenance of the codes' measure. Two things are therefore "
    "tested rather than assumed: that the enacted amendment's (a) and (c) are "
    "identical to the current pinned artifact's, and that the amendment is the "
    "sole one since the section's SB 899 creation. The residual gap — the "
    "pre-2016 text itself — is REPORTED, not closed, and not papered over by "
    "asserting the exemption revision 7 asserted without checking."
)
"""Recorded as a limitation because 'we believe the amendment was elsewhere' is
not evidence, and neither is a test that quietly compares a text to itself."""


def section_4663_amending_act_text() -> str:
    """The 2016 amendment as enacted, hashed from its own bytes."""
    path = statutes_dir() / SECTION_4663_AMENDING_ACT_FILENAME
    if not path.is_file():
        raise StatutePinError(
            f"{STATUTE_PIN_MISSING}: {path} is not on disk. This artifact is "
            "NOT produced by tools/statute_pin.py --fetch, which fetches code "
            "sections; it is SEC. 218 of the chaptered bill text at "
            "leginfo.legislature.ca.gov/faces/billTextClient.xhtml"
            "?bill_id=201520160SB1171, from '4663.' to the start of SEC. 219, "
            "tag-stripped and whitespace-collapsed"
        )
    payload = path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != SECTION_4663_AMENDING_ACT_SHA256:
        raise StatutePinError(
            f"{STATUTE_PIN_DIGEST_MISMATCH}: the section 4663 amending act "
            f"artifact hashes {digest}, pinned {SECTION_4663_AMENDING_ACT_SHA256}"
        )
    return payload.decode("utf-8")


def subdivision_text(text: str, marker: str, markers: tuple[str, ...]) -> str:
    """The canonical text of one subdivision, bounded by the next marker.

    Bounded rather than "from the marker onwards": an unbounded slice makes
    every subdivision comparison also a comparison of everything after it, so a
    change in (d) would fail an assertion about (a) and a reader would draw the
    wrong conclusion about which clause moved.
    """
    canonical = canonicalize_statute_text(text)
    start = canonical.find(marker)
    if start < 0:
        raise StatutePinError(
            f"{STATUTE_PIN_MISSING}: subdivision {marker} is absent from the text"
        )
    following = [
        canonical.find(other, start + len(marker))
        for other in markers
        if other != marker
    ]
    ends = [index for index in following if index > start]
    return canonical[start : min(ends)].strip() if ends else canonical[start:].strip()


@dataclass(frozen=True)
class CasePin:
    """A pinned published opinion. ``sha256 is None`` means **not pinned**."""

    citation: str
    holding: str
    retrieved_url: str | None
    retrieved_on: dt.date | None
    filename: str | None
    sha256: str | None

    @property
    def pinned(self) -> bool:
        return self.sha256 is not None


KOPPING_PIN = CasePin(
    citation="Kopping v. WCAB (2006) 142 Cal.App.4th 1099",
    holding=(
        "the defendant bears the burden of proving overlap between the prior and "
        "the current permanent disability in order to obtain the section 4664 credit"
    ),
    retrieved_url=None,
    retrieved_on=None,
    filename=None,
    sha256=None,
)
"""**NOT PINNED — blocking finding escalated by item 0e (M5-R20a).**

Three candidate public sources were attempted on 2026-08-19 and none yielded
retrievable opinion **text**:

* ``courts.ca.gov`` — the published-opinion archive returns 404 for a 2006
  opinion; the archive does not retain them;
* ``courtlistener.com`` — the search API is reachable anonymously and confirms
  the opinion exists (cluster ``2296517``, filed 2006-09-11, Cal. Ct. App.),
  but the opinion-detail endpoint answers ``401`` without an API token and the
  public HTML page is behind a WAF challenge (``x-amzn-waf-action: challenge``);
* ``law.justia.com`` / ``caselaw.findlaw.com`` — ``403``.

Re-attempted independently the same day rather than inherited on trust, because
"a previous attempt failed" is the claim most likely to be wrong. The result was
the same, and the failure modes were observed directly:
``courtlistener.com``'s search API answers 200 anonymously and returns the
cluster metadata quoted above, while ``/api/rest/v4/opinions/?cluster=2296517``
and ``/api/rest/v4/clusters/2296517/`` both answer ``401`` and the public HTML
page returns an empty body under ``x-amzn-waf-action: challenge``;
``law.justia.com`` and ``caselaw.findlaw.com`` answer ``403``; ``casetext.com``
answers ``410``.

Confirming that a case exists is metadata, not provenance: nothing above lets
the holding sentence be asserted as a literal substring of retrieved bytes.
Per M5-R20a this is **never** resolved by downgrading the grade — the pin is
recorded absent, the Kopping-dependent burden grading stays DRAFT, and item 4
does not start until counsel or the orchestrator supplies a retrievable
source. :func:`require_kopping_pin` is the fail-closed accessor that keeps
that decision out of an implementer's hands.
"""

KOPPING_PIN_ABSENT = "M5_KOPPING_PIN_ABSENT"


def require_kopping_pin() -> CasePin:
    """The Kopping pin, or a refusal. Never a fallback grade."""
    if not KOPPING_PIN.pinned:
        raise StatutePinError(
            f"{KOPPING_PIN_ABSENT}: {KOPPING_PIN.citation} has no retrieved "
            "artifact or digest; the burden grading it authorizes stays DRAFT "
            "(M5-R20a)"
        )
    return KOPPING_PIN


REGULATORY_SECTIONS_SNAPSHOT_ABSENT = "M5_REGULATORY_SECTIONS_SNAPSHOT_ABSENT"
REGULATORY_SECTIONS_MISMATCH = "M5_REGULATORY_SECTIONS_MISMATCH"

CORROBORATED_SECTIONS = ("4663", "4664")
"""The two sections the ``regulatory_sections`` table holds in full text.

The row is a **corroborant only, never the pinned source** — it carries no
hash-pinned provenance chain. What it earns is a named cross-check: two
independent sources agreeing is materially stronger than one pinned source
alone, and it is free.
"""


def corroborate_against_snapshot(section: str, snapshot_dir: Path) -> None:
    """Assert the pinned text equals the ``regulatory_sections`` row.

    Both sides go through :func:`canonicalize_statute_text` — the same
    function, not two implementations of the same idea — and a discrepancy
    **fails closed** rather than being reconciled by preference. An absent
    snapshot is also a failure: silently passing when the corroborant is
    missing would turn a cross-check into a decoration.
    """
    path = snapshot_dir / f"regulatory-sections-{section.replace('.', '-')}.txt"
    if not path.is_file():
        raise StatutePinError(
            f"{REGULATORY_SECTIONS_SNAPSHOT_ABSENT}: no corroborating snapshot "
            f"for section {section} at {path}"
        )
    corroborant = strip_section_heading(
        canonicalize_statute_text(path.read_text(encoding="utf-8")), section
    )
    pinned = strip_section_heading(
        canonicalize_statute_text(load_section(section)), section
    )
    # EXACT equality on the FULL remaining text, in both directions. The
    # previous form accepted substring containment either way, which is not a
    # comparison at all: a corroborant holding one sentence of the section
    # passed, and so did one holding the section plus a paragraph of anything
    # else. Truncation and appended text are the two failure modes a
    # containment test is structurally blind to, and both are probed.
    if corroborant != pinned:
        raise StatutePinError(
            f"{REGULATORY_SECTIONS_MISMATCH}: section {section} — leginfo and "
            "regulatory_sections disagree after canonicalization "
            f"(leginfo {len(pinned)} chars, regulatory_sections "
            f"{len(corroborant)} chars; first divergence at index "
            f"{_first_divergence(pinned, corroborant)})"
        )


def _first_divergence(left: str, right: str) -> int:
    """Index of the first differing character, for a readable failure."""
    for index, (a, b) in enumerate(zip(left, right, strict=False)):
        if a != b:
            return index
    return min(len(left), len(right))


def load_section(section: str) -> str:
    """Read a pinned artifact, hash **the bytes**, and fail closed on a miss.

    The digest is computed from the file that was just read and compared to
    the literal above. Comparing the literal to another copy of itself — the
    defect ``m24-98`` restores — proves only that a constant equals itself.
    """
    pin = STATUTE_PINS.get(section)
    if pin is None:
        raise StatutePinError(f"{STATUTE_PIN_MISSING}: no pin for section {section}")
    if not pin.path.is_file():
        raise StatutePinError(
            f"{STATUTE_PIN_MISSING}: {pin.path} is not on disk; run "
            "tools/statute_pin.py --fetch"
        )
    payload = pin.path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != pin.sha256:
        raise StatutePinError(
            f"{STATUTE_PIN_DIGEST_MISMATCH}: section {section} artifact hashes "
            f"{digest}, pinned {pin.sha256}"
        )
    return payload.decode("utf-8")


def section_text_for_doi(section: str, date_of_injury: dt.date) -> str:
    """The pinned text, refused for a DOI below the section's pinned floor.

    Pinned coverage is a hard floor, not an absence of amendments. Returning
    the earliest text we happen to hold for an injury that predates it would
    be citing law that was not in force, silently.
    """
    pin = STATUTE_PINS.get(section)
    if pin is None:
        raise StatutePinError(f"{STATUTE_PIN_MISSING}: no pin for section {section}")
    if pin.doi_versioned:
        assert pin.doi_floor is not None
        if date_of_injury < pin.doi_floor:
            raise StatutePinError(
                f"{STATUTE_DOI_BELOW_PINNED_FLOOR}: section {section} is pinned "
                f"from {pin.doi_floor.isoformat()}; date of injury "
                f"{date_of_injury.isoformat()} is below the floor"
            )
    return load_section(section)
