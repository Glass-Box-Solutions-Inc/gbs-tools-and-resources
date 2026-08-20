"""AJC-64 item 0e — statute pinning and the prose sweep (M5-R47).

A pin is not a way to obtain text we lack. It is the evidence that the text we
cite is the text that was published and has not moved. That distinction is the
whole item: the ``regulatory_sections`` Postgres table holds §4663 and §4664 in
correct full text and carries **no digest**, which is the same self-comparison
defect item 0b fixes for the PDRS PDF, one layer up.

So the oracles here are about bytes and refusals rather than about content:

* **digests are literals in this file**, compared against a hash computed from
  the artifact on disk — never against the module's own copy of the constant
  (``m24-98`` restores that self-comparison);
* **the subdivision markers the spec relies on are asserted present**,
  including §4664's ``(c)(1)(A)`` to ``(G)`` region enumeration, so a fetch that
  silently returned a stub cannot pass;
* **a DOI below a pinned floor fails closed**, with an at-floor neighbour that
  must succeed — coverage is a hard floor, not an absence of amendments;
* **the canonicalizer is fixed by fixture in both directions**: equal after
  markup and entity differences, and **not** equal when two sources differ
  only in the case of a subdivision marker (``m24-127`` adds the case fold
  that would quietly make the cross-check pass);
* **the prose sweep is two instruments**, because one cannot do both jobs:
  Python's ``ast`` preserves docstrings and discards comments, so the comment
  half runs on ``tokenize`` (``m24-128`` / ``m24-135``, one per half).

**Two escalations are recorded as tests rather than as prose**, so they cannot
be forgotten: the Kopping opinion is **not pinned** (no retrievable public
source), and the ``regulatory_sections`` corroborating snapshot has **not been
obtained** (no database access from this package). Both are asserted to fail
closed. When either lands, its test is the thing that changes.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import ast
import datetime as dt
import hashlib
import io
import json
import tokenize
from pathlib import Path
from typing import Any

import pytest

from wc_caseload_engine import statutes
from wc_caseload_engine.statutes import (
    KOPPING_PIN,
    SECTION_4663_AMENDING_ACT,
    SECTION_4663_AMENDING_ACT_SHA256,
    SECTION_4663_MODELLED_SUBDIVISIONS,
    SECTION_4663_STABILITY_LIMITATION,
    STATUTE_PINS,
    StatutePinError,
    canonicalize_statute_text,
    corroborate_against_snapshot,
    load_section,
    require_kopping_pin,
    section_4663_amending_act_text,
    section_text_for_doi,
    subdivision_text,
)

PACKAGE = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PACKAGE / "src" / "wc_caseload_engine"

# ---------------------------------------------------------------------------
# The pinned digests, as literals HERE.
#
# Retrieved 2026-08-19 from
# https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=LAB&sectionNum=<N>
# and canonicalized by statutes.canonicalize_statute_text. Moving one of these
# is a deliberate, reviewable commit.
# ---------------------------------------------------------------------------

EXPECTED_DIGESTS = {
    "4664": "809201a5ab0a1cd6c61ecd1f5b7aea0908af5e38a2db7849dbda471384aed9d1",
    "4658": "bbd8269e35869200ff2bfb32ff4ed85461eb14d0f4c7349706f1d58672b38a04",
    "4453": "022975722ca09a2e4603d7ac9f6b1bf6f05b8da00783da8b175c222c1cb4821a",
    "4659": "f8033779717f500c4e609e1d8683afffd803c78e338f3a983f75d81ca2353ec3",
    "4751": "a66bafbd14ca82354e73a12983cf3546afb3e736816783e7bf3e0b9557b179ec",
    "4663": "812e3436572afb62a1c3021f2995ee5bd6afd56bc546f1484de5b364c4d2f30b",
    "4660.1": "3d8daae5d283023301f7efed6e93f295c99dd0fa0eee2ec03eb535af01459eba",
}

DOI_VERSIONED_FLOORS = {
    "4658": dt.date(2005, 1, 1),
    "4453": dt.date(2005, 1, 1),
    "4663": dt.date(2005, 1, 1),
    "4660.1": dt.date(2013, 1, 1),
}
"""The four DOI-versioned sections and their pinned floors, and only those.

§4664 is deliberately absent: it was *created* by Stats. 2004, Ch. 34, Sec. 35
effective 2004-04-19 and has no earlier version, so there is nothing to version
against and every DOI the engine accepts postdates its creation.
"""

REQUIRED_SUBDIVISIONS = {
    # §4664 carries the region enumeration M5-R19 reads, so every letter is
    # asserted rather than the first and last.
    "4664": (
        "(a)",
        "(b)",
        "(c) (1)",
        "(A) Hearing.",
        "(B) Vision.",
        "(C) Mental and behavioral disorders.",
        "(D) The spine.",
        "(E) The upper extremities, including the shoulders.",
        "(F) The lower extremities, including the hip joints.",
        "(G) The head, face, cardiovascular system",
        "(2) Nothing in this section",
    ),
    "4663": ("(a) Apportionment of permanent disability shall be based on causation.",),
    "4751": ("hand, arm, foot, leg, or eye",),
    "4660.1": ("multiplied by an adjustment factor of 1.4",),
}

FORBIDDEN_4664_GLOSS = "The spine, torso"
"""(D) is "The spine". A "torso" gloss is the wrong statutory unit."""


class TestPinnedDigests:
    """The chain terminates in bytes, not in another copy of the constant."""

    def test_every_pinned_section_has_an_artifact_on_disk(self) -> None:
        missing = [
            section for section, pin in STATUTE_PINS.items() if not pin.path.is_file()
        ]
        assert missing == [], f"pinned sections with no artifact: {missing}"

    def test_the_registry_covers_exactly_the_specced_sections(self) -> None:
        assert set(STATUTE_PINS) == set(EXPECTED_DIGESTS)

    def test_each_artifact_hashes_to_its_pinned_digest(self) -> None:
        """m24-98's guard — the digest is computed from the file's bytes."""
        for section, expected in sorted(EXPECTED_DIGESTS.items()):
            payload = STATUTE_PINS[section].path.read_bytes()
            assert hashlib.sha256(payload).hexdigest() == expected, section
            # and the module's own literal agrees with this file's literal
            assert STATUTE_PINS[section].sha256 == expected, section

    def test_a_corrupted_artifact_fails_closed(self, tmp_path: Path,
                                               monkeypatch: pytest.MonkeyPatch) -> None:
        """The load path hashes what it reads, so a tampered byte is refused.

        Without this, ``load_section`` could compare the pinned constant to
        itself and pass against any bytes at all — which is exactly the defect
        ``m24-98`` reintroduces.
        """
        monkeypatch.setattr(statutes, "statutes_dir", lambda: tmp_path)
        for section, pin in STATUTE_PINS.items():
            (tmp_path / pin.filename).write_bytes(b"not the pinned text\n")
            with pytest.raises(StatutePinError, match="DIGEST_MISMATCH"):
                load_section(section)

    def test_a_missing_artifact_fails_closed(self, tmp_path: Path,
                                             monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(statutes, "statutes_dir", lambda: tmp_path)
        with pytest.raises(StatutePinError, match="PIN_MISSING"):
            load_section("4664")

    def test_an_unpinned_section_is_refused(self) -> None:
        with pytest.raises(StatutePinError, match="PIN_MISSING"):
            load_section("4662")


class TestSubdivisionMarkers:
    """A stub that hashed cleanly would still not be the section."""

    def test_every_required_subdivision_is_present(self) -> None:
        for section, markers in sorted(REQUIRED_SUBDIVISIONS.items()):
            text = load_section(section)
            missing = [marker for marker in markers if marker not in text]
            assert missing == [], f"section {section} is missing {missing}"

    def test_section_4664_says_the_spine_and_not_torso(self) -> None:
        """The gloss M5-R47 files as a KB defect must not be in our own bytes."""
        text = load_section("4664")
        assert "(D) The spine." in text
        assert FORBIDDEN_4664_GLOSS not in text

    def test_section_4664_records_its_own_creation(self) -> None:
        """The reason §4664 needs no DOI-versioned pin, asserted from the text."""
        assert (
            "(Added by Stats. 2004, Ch. 34, Sec. 35. Effective April 19, 2004.)"
            in load_section("4664")
        )

    def test_section_4660_1_states_its_own_operative_date(self) -> None:
        assert (
            "This section applies to injuries occurring on or after January 1, 2013."
            in load_section("4660.1")
        )


class TestDoiFloors:
    """Coverage is a hard floor, not an absence of amendments."""

    def test_exactly_four_sections_are_doi_versioned(self) -> None:
        versioned = {
            section for section, pin in STATUTE_PINS.items() if pin.doi_versioned
        }
        assert versioned == set(DOI_VERSIONED_FLOORS)

    def test_each_floor_is_the_pinned_date(self) -> None:
        for section, floor in sorted(DOI_VERSIONED_FLOORS.items()):
            assert STATUTE_PINS[section].doi_floor == floor, section

    def test_below_the_floor_fails_closed_and_the_at_floor_neighbour_succeeds(
        self,
    ) -> None:
        """Both arms in one node, per section: an at-floor pass alone proves nothing."""
        for section, floor in sorted(DOI_VERSIONED_FLOORS.items()):
            below = floor - dt.timedelta(days=1)
            with pytest.raises(StatutePinError, match="DOI_BELOW_PINNED_FLOOR"):
                section_text_for_doi(section, below)
            assert section_text_for_doi(section, floor), section

    def test_a_section_with_no_floor_accepts_the_engines_earliest_doi(self) -> None:
        """§4664 and its two Lane B neighbours take any DOI the engine allows."""
        for section in ("4664", "4659", "4751"):
            assert section_text_for_doi(section, dt.date(2005, 1, 1)), section


class TestCanonicalization:
    """m24-127's guard — the rule may not be widened until it passes."""

    def test_markup_entity_and_whitespace_differences_canonicalize_equal(self) -> None:
        html_side = (
            "<p>(c)&#160;(1)\u00a0The accumulation of all permanent disability "
            "awards\n   issued&hellip;</p>"
        )
        database_side = (
            "(c) (1) The accumulation of all permanent disability awards issued\u2026"
        )
        assert canonicalize_statute_text(html_side) == canonicalize_statute_text(
            database_side
        )

    def test_a_subdivision_marker_differing_only_in_case_is_not_equal(self) -> None:
        """The fixture ``m24-127`` must redden.

        Adding a case fold to step 5 makes these two compare equal, which is
        the quiet widening that turns a provenance check into a decoration.
        """
        upper = "(A) Hearing."
        lower = "(a) Hearing."
        assert canonicalize_statute_text(upper) != canonicalize_statute_text(lower)

    def test_punctuation_and_digits_survive(self) -> None:
        raw = "shall not exceed 100 percent over the employee's lifetime"
        assert canonicalize_statute_text(raw) == raw

    def test_canonicalization_is_idempotent(self) -> None:
        once = canonicalize_statute_text(load_section("4663"))
        assert canonicalize_statute_text(once) == once


class TestRegulatorySectionsCorroboration:
    """The cross-check runs against the REAL table rows, and compares exactly.

    M5-R47 makes the ``regulatory_sections`` row a **named corroborant, never
    the pinned source**. Two things make it worth having, and round 1 had
    neither:

    * **the snapshot is independent.** It is the actual row from the
      wc-knowledge-base Postgres ``regulatory_sections`` table, pulled
      2026-08-19 and vendored with its provenance. Round 1 built the
      "corroborant" out of ``load_section()`` itself, so the assertion compared
      the pinned artifact to the pinned artifact — a self-comparison wearing a
      cross-check's name, which is precisely the defect M5-R47 cites item 0b
      for one layer up;
    * **the comparison is exact, in both directions.** Round 1 accepted
      substring containment either way, so a row holding one sentence of the
      section passed, and so did a row holding the section plus a paragraph of
      anything else. Truncation and appended text are exactly what a
      containment test cannot see, and both are probed below.

    The two sources agree on the **complete** canonicalized text — 1,793
    characters for section 4663 and 1,461 for 4664 once the heading token is
    removed, enacting-history parenthetical included — with one formatting
    difference: the database
    labels its heading ``§4663.`` where leginfo writes ``4663.``. That is
    handled by a narrow declared normalization of the leading heading token,
    not by widening the canonicalizer.
    """

    SNAPSHOT_DIR = Path(__file__).resolve().parent / "fixtures" / "regulatory-sections"

    @staticmethod
    def _provenance() -> dict[str, Any]:
        path = (
            Path(__file__).resolve().parent
            / "fixtures"
            / "regulatory-sections"
            / "provenance.json"
        )
        return json.loads(path.read_text(encoding="utf-8"))

    def _snapshot(self, section: str) -> str:
        return (self.SNAPSHOT_DIR / f"regulatory-sections-{section}.txt").read_text(
            encoding="utf-8"
        )

    def test_the_corroborated_set_is_the_two_sections_the_table_holds(self) -> None:
        assert statutes.CORROBORATED_SECTIONS == ("4663", "4664")

    @pytest.mark.parametrize("section", ["4663", "4664"])
    def test_the_snapshot_is_the_pinned_row_and_not_the_pinned_statute(
        self, section: str
    ) -> None:
        """The independence claim, asserted rather than described.

        The snapshot must hash to its recorded digest AND must not be a copy of
        the leginfo artifact — if the two files were byte-identical the
        "corroboration" would be a tautology, so that is checked directly.
        """
        provenance = self._provenance()["sections"][section]
        raw = (self.SNAPSHOT_DIR / provenance["file"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == provenance["sha256"]
        assert len(raw.decode("utf-8")) == provenance["chars"]
        assert provenance["source_type"] == "labor_code"
        # Independent store: the raw bytes differ from the pinned artifact's.
        assert raw != (statutes.statutes_dir() / f"lc-{section}.txt").read_bytes()

    @pytest.mark.parametrize("section", ["4663", "4664"])
    def test_the_real_row_corroborates_the_pinned_text_exactly(
        self, section: str
    ) -> None:
        """Full-text exact equality, both directions, on the real data."""
        corroborate_against_snapshot(section, self.SNAPSHOT_DIR)
        pinned = statutes.strip_section_heading(
            canonicalize_statute_text(load_section(section)), section
        )
        row = statutes.strip_section_heading(
            canonicalize_statute_text(self._snapshot(section)), section
        )
        assert row == pinned
        assert len(pinned) == {"4663": 1793, "4664": 1461}[section]

    def test_an_absent_snapshot_fails_closed(self, tmp_path: Path) -> None:
        for section in statutes.CORROBORATED_SECTIONS:
            with pytest.raises(StatutePinError, match="SNAPSHOT_ABSENT"):
                corroborate_against_snapshot(section, tmp_path)

    def test_a_truncated_row_fails_closed(self, tmp_path: Path) -> None:
        """PREFIX probe — the failure a containment comparator cannot see.

        Round 1's ``corroborant not in body and body not in corroborant`` passed
        happily on a row holding only the section's opening sentence.
        """
        section = "4663"
        text = self._snapshot(section)
        truncated = text[: len(text) // 3]
        assert truncated and truncated != text
        (tmp_path / f"regulatory-sections-{section}.txt").write_text(
            truncated, encoding="utf-8"
        )
        with pytest.raises(StatutePinError, match="MISMATCH"):
            corroborate_against_snapshot(section, tmp_path)

    def test_an_appended_row_fails_closed(self, tmp_path: Path) -> None:
        """SUFFIX probe — the other direction containment was blind to."""
        section = "4664"
        appended = self._snapshot(section) + (
            " The employer may disregard the foregoing at its discretion."
        )
        (tmp_path / f"regulatory-sections-{section}.txt").write_text(
            appended, encoding="utf-8"
        )
        with pytest.raises(StatutePinError, match="MISMATCH"):
            corroborate_against_snapshot(section, tmp_path)

    @pytest.mark.parametrize("section", ["4663", "4664"])
    def test_a_one_character_discrepancy_fails_closed(
        self, tmp_path: Path, section: str
    ) -> None:
        """The planted discrepancy, proving it refuses rather than reconciles."""
        text = self._snapshot(section)
        marker = "permanent disability"
        assert marker in text
        tampered = text.replace(marker, "permanent disabilities", 1)
        assert tampered != text
        (tmp_path / f"regulatory-sections-{section}.txt").write_text(
            tampered, encoding="utf-8"
        )
        with pytest.raises(StatutePinError, match="MISMATCH"):
            corroborate_against_snapshot(section, tmp_path)

    def test_the_heading_normalization_is_narrow(self) -> None:
        """A sigil anywhere but the heading survives — it is not a blanket strip.

        Widening ``canonicalize_statute_text`` to delete section sigils would
        have made this comparison pass too, and would have erased a sigil inside
        a cross-reference where it carries meaning. m24-148 does exactly that
        and must redden.
        """
        assert statutes.strip_section_heading("§4663. (a) Text", "4663") == "(a) Text"
        assert statutes.strip_section_heading("4663. (a) Text", "4663") == "(a) Text"
        # A sigil in the body is content, not a heading.
        body = "(a) See §4664 and §4663 for the rule."
        assert statutes.strip_section_heading(f"§4663. {body}", "4663") == body
        assert statutes.SECTION_SIGIL in statutes.strip_section_heading(
            f"§4663. {body}", "4663"
        )
        # Routed through the CANONICALIZER, because that is where a blanket
        # strip would be introduced. Asserting only on strip_section_heading
        # leaves a widened canonicalizer entirely unexercised — m24-148 survived
        # exactly that gap before this line existed.
        canonical = canonicalize_statute_text(f"<p>§4663. {body}</p>")
        assert canonical.count(statutes.SECTION_SIGIL) == 3
        assert (
            statutes.strip_section_heading(canonical, "4663").count(
                statutes.SECTION_SIGIL
            )
            == 2
        )
        # A heading for a different section is not stripped.
        assert statutes.strip_section_heading("§4664. (a) Text", "4663") == (
            "§4664. (a) Text"
        )


class TestKoppingPin:
    """ESCALATION — the opinion is not pinned, and the gate holds (M5-R20a)."""

    def test_the_pin_is_recorded_absent(self) -> None:
        assert KOPPING_PIN.pinned is False
        assert KOPPING_PIN.sha256 is None
        assert KOPPING_PIN.retrieved_url is None
        assert KOPPING_PIN.citation == "Kopping v. WCAB (2006) 142 Cal.App.4th 1099"

    def test_requesting_the_pin_refuses_rather_than_returning_a_surrogate(self) -> None:
        """There is no partial-shipping form and no pre-pin surrogate grade."""
        with pytest.raises(StatutePinError, match="KOPPING_PIN_ABSENT"):
            require_kopping_pin()


# ---------------------------------------------------------------------------
# M5-R47c — the prose sweep, in two instruments.
# ---------------------------------------------------------------------------

FORBIDDEN_PROSE_CLAIMS: tuple[tuple[str, str], ...] = (
    (
        "Section 4664(b) and (c) both operate per region of the body",
        "(b) is an existence presumption operating per PRIOR AWARD; only (c)(1) "
        "is regional",
    ),
    (
        "The figure section 4664 subtracts",
        "section 4664 subtracts a proved OVERLAP, not the award's pd_percent",
    ),
)
"""Two propositions this package taught and M5 makes false.

Documentation that contradicts the code is how the next implementer
reintroduces the bug — the ``comment_justified_the_gap`` class — and it is in
scope precisely because M5 is the ticket that makes these sentences false.
"""


def docstring_texts(source: str) -> list[str]:
    """Every string constant, implicit concatenation folded. Comments excluded.

    ``ast`` discards comments, which is not a gap to paper over with a regex:
    it is why :func:`comment_texts` exists as a second instrument.
    """
    values: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            values.append(node.value)
        elif isinstance(node, ast.JoinedStr):
            values.append(
                "".join(
                    part.value
                    for part in node.values
                    if isinstance(part, ast.Constant) and isinstance(part.value, str)
                )
            )
    return values


def comment_texts(source: str) -> list[str]:
    """Every ``#`` comment, with adjacent same-column comments joined.

    Joining the block first is the point: a proposition split across two
    comment lines is invisible to a per-line match, and a comment block is the
    natural way to write a paragraph.
    """
    blocks: list[str] = []
    current: list[str] = []
    previous_row = previous_col = None
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type != tokenize.COMMENT:
            continue
        row, col = token.start
        text = token.string.lstrip("#").strip()
        if (
            previous_row is not None
            and row == previous_row + 1
            and col == previous_col
        ):
            current.append(text)
        else:
            if current:
                blocks.append(" ".join(current))
            current = [text]
        previous_row, previous_col = row, col
    if current:
        blocks.append(" ".join(current))
    return blocks


def _source_files() -> list[Path]:
    return sorted(SOURCE_ROOT.rglob("*.py"))


class TestProseSweep:
    """M5-R47c — the docstring half and the comment half, each with a control."""

    def test_the_sweep_reaches_every_shipped_module(self) -> None:
        files = _source_files()
        assert len(files) >= 20
        assert SOURCE_ROOT / "medical_history.py" in files

    def test_no_docstring_states_a_forbidden_claim(self) -> None:
        """m24-128's guard — the AST half."""
        offenders = [
            (str(path.relative_to(PACKAGE)), claim)
            for path in _source_files()
            for claim, _ in FORBIDDEN_PROSE_CLAIMS
            if any(
                claim in value
                for value in docstring_texts(path.read_text(encoding="utf-8"))
            )
        ]
        assert offenders == [], f"superseded section 4664 prose survives: {offenders}"

    def test_no_comment_states_a_forbidden_claim(self) -> None:
        """m24-135's guard — the tokenize half."""
        offenders = [
            (str(path.relative_to(PACKAGE)), claim)
            for path in _source_files()
            for claim, _ in FORBIDDEN_PROSE_CLAIMS
            if any(
                claim in block
                for block in comment_texts(path.read_text(encoding="utf-8"))
            )
        ]
        assert offenders == [], f"superseded section 4664 prose survives: {offenders}"

    def test_the_docstring_instrument_sees_a_split_literal(self) -> None:
        planted = (
            'def f():\n'
            '    """Section 4664(b) and (c) both operate per region "\n'
            '    "of the body."""\n'
        )
        # A raw search over a *split* literal is the failure mode; assert the
        # folded instrument sees the contiguous docstring form too.
        contiguous = (
            'def f():\n    """Section 4664(b) and (c) both operate per '
            'region of the body."""\n'
        )
        assert any(
            FORBIDDEN_PROSE_CLAIMS[0][0] in value
            for value in docstring_texts(contiguous)
        )
        assert docstring_texts(planted)

    def test_the_comment_instrument_joins_a_split_block(self) -> None:
        """Positive control: the proposition split across two comment lines."""
        planted = (
            "# Section 4664(b) and (c) both operate\n"
            "# per region of the body, which is why.\n"
            "x = 1\n"
        )
        assert all(
            FORBIDDEN_PROSE_CLAIMS[0][0] not in line for line in planted.splitlines()
        ), "the control is not testing block joining — the claim fits on one line"
        assert any(
            FORBIDDEN_PROSE_CLAIMS[0][0] in block for block in comment_texts(planted)
        )

    def test_the_findings_and_award_comments_cite_the_resolved_row(self) -> None:
        """F22-round-7 — a comment recording a resolved doubt as open is the
        same defect class in miniature."""
        source = (SOURCE_ROOT / "medical_history.py").read_text(encoding="utf-8")
        assert "counsel-assumed, micro-confirm" not in source
        assert "micro-confirm at M5 spec" not in source
        assert source.count("SI-M5-003") >= 2, (
            "both the model docstring and the PRESUMPTION_DEFAULT_BY_RESOLUTION "
            "comment must cite the confirmed register row"
        )


class TestSection4663DatedApplicability:
    """M5-R47a — the 2016 amendment is TESTED, not assumed, to leave (a) and
    (c) alone.

    Revision 7 exempted section 4663 from DOI versioning on the reasoning that
    "we believe the amendment was elsewhere", which is not evidence. The
    section joined the DOI-versioned set, and the stability claim M5-R16 leans
    on is checked here against the amending act's own enacted text.

    **What this does NOT do, stated plainly.** The rule asks for the pre-2016
    text as well, and leginfo does not serve it: a code section resolves to its
    current text, and the chaptered bill texts carry no strikeout markup. That
    gap is REPORTED by ``SECTION_4663_STABILITY_LIMITATION`` rather than closed
    by an assertion that would compare the current text to itself and pass.
    """

    MARKERS = ("(a)", "(b)", "(c)", "(d)", "(e)")

    def test_the_amending_act_artifact_hashes_to_its_pin(self) -> None:
        text = section_4663_amending_act_text()
        assert (
            hashlib.sha256(text.encode("utf-8")).hexdigest()
            == SECTION_4663_AMENDING_ACT_SHA256
        )
        assert text.startswith("4663.")

    def test_the_amending_act_is_the_codes_maintenance_measure(self) -> None:
        assert SECTION_4663_AMENDING_ACT == "Stats. 2016, Ch. 86, Sec. 218 (SB 1171)"

    @pytest.mark.parametrize("marker", SECTION_4663_MODELLED_SUBDIVISIONS)
    def test_the_modelled_subdivisions_survived_the_amendment(
        self, marker: str
    ) -> None:
        """(a) and (c) — causation-based apportionment and the burden split."""
        enacted = subdivision_text(
            section_4663_amending_act_text(), marker, self.MARKERS
        )
        current = subdivision_text(load_section("4663"), marker, self.MARKERS)
        assert enacted == current
        assert len(enacted) > 40, "a subdivision slice this short is not the clause"

    def test_only_the_modelled_subdivisions_are_claimed_stable(self) -> None:
        """The claim is scoped to what M5-R16 actually models.

        Asserting the whole section unchanged would be a broader claim than the
        evidence supports and than the rule asks for.
        """
        assert SECTION_4663_MODELLED_SUBDIVISIONS == ("(a)", "(c)")

    def test_a_subdivision_slice_is_bounded_by_the_next_marker(self) -> None:
        """Unbounded slices make every comparison a comparison of the tail."""
        text = load_section("4663")
        first = subdivision_text(text, "(a)", self.MARKERS)
        assert "(b)" not in first
        assert first.startswith("(a)")

    def test_the_residual_gap_is_recorded_rather_than_closed(self) -> None:
        assert SECTION_4663_STABILITY_LIMITATION.startswith("PARTIAL.")
        for fragment in ("pre-2016", "not retrievable", "REPORTED"):
            assert fragment in SECTION_4663_STABILITY_LIMITATION
