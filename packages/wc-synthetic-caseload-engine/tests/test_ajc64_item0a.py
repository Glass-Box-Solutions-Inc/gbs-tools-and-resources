"""AJC-64 item 0a — the section 4751 corrected-law oracles (M5-R39, M5-R36a).

``doctrine.py`` shipped a legal paragraph that attached the thirty-five and
five percent floors to the **preexisting** disability. Both floors attach to
the **subsequent** injury. A corrected statement of the elements already
existed at :data:`MEDICAL_STORY_SIBTF_SECTION_4751_PARAGRAPHS`, and
``renderer.py`` selected it **only when the M3 medical-story flag was set** —
so every carrier without that flag rendered wrong law into ``TRIAL_BRIEF``,
``CASE_ANALYSIS_MEMO``, ``SETTLEMENT_VALUATION_MEMO`` and
``MOTION_FOR_JOINDER``.

Item 0a is deliberately **surgical** (M5-R39a). Only
``sibtf.legal_paragraphs[1]`` moves. The three ``medical_paragraphs`` are
evaluator prose carrying no threshold misstatement and are untouched — putting
a statutory recitation in a doctor's mouth would be a different defect. The
joinder sentences that shared the defective paragraph are preserved, because
``MOTION_FOR_JOINDER`` is one of the four legal targets and they are the
doctrinal content that document exists to carry.

Four oracles, each guarding a way the fix could be wrong rather than absent:

* **the elements are verbatim substrings** (M5-R36a) — the inventory is a copy
  of the shipped paragraph, not a restatement of it, so a reworded element
  that still reads as correct law fails;
* **the complete pool is pinned per target subtype**, both flag arms — pinning
  the whole tuple rather than the forbidden phrase's absence is what makes
  *deletion* detectable: an implementation that emptied ``legal_paragraphs``
  would satisfy an absence check perfectly;
* **the forbidden phrase sweep is AST-folded**, because the live defect was
  written as two adjacent string literals and a raw substring search returned
  ``False`` against it — the sweep would have passed vacuously on the very
  code this item exists to fix. A positive control asserts the folding
  instrument really sees a split phrase;
* **the rendered output is swept too**, because a phrase can be assembled at
  runtime from parts no single literal contains.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest

from conftest import extract_text, iter_documents
from wc_caseload_engine.doctrine import (
    DOCTRINE_CONTENT,
    MEDICAL_STORY_SIBTF_SECTION_4751_PARAGRAPHS,
)

PACKAGE = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PACKAGE / "src" / "wc_caseload_engine"

# ---------------------------------------------------------------------------
# M5-R36a — the literal inventory.
#
# CONTRACT: every entry is an EXACT SUBSTRING of the doctrine.py paragraph.
# Written as copies rather than restatements: earlier drafts abbreviated
# "permanent partial disability" to "PD" and reworded element five, each of
# which reads as perfectly correct law and fails the substring oracle.
# ---------------------------------------------------------------------------

SECTION_4751_ELEMENTS: tuple[str, ...] = (
    "a preexisting permanent partial disability",  # LEGAL_BINDING
    "a subsequent compensable injury producing additional permanent "
    "partial disability",  # LEGAL_BINDING
    "combined permanent disability greater than that from the subsequent "
    "injury alone",  # LEGAL_BINDING
    "combined permanent disability of at least seventy percent",  # LEGAL_BINDING - 70
    "either prior disability affecting a hand, arm, foot, leg, or eye "
    "with subsequent injury to the opposite and corresponding member and "
    "subsequent disability alone, unadjusted for age or occupation, of at "
    "least five percent, or subsequent disability alone, unadjusted for "
    "age or occupation, of at least thirty-five percent",  # LEGAL_BINDING - 5, 35
)

SECTION_4751_THRESHOLDS = {"combined": 70, "opposite_member": 5, "subsequent_alone": 35}
"""LEGAL_BINDING (LC section 4751). Three floors, none of them interchangeable."""

SECTION_4751_OPPOSITE_MEMBERS = ("hand", "arm", "foot", "leg", "eye")
"""LEGAL_BINDING closed list.

The five percent branch is member-limited: section 4751 confines it to a
previous disability affecting a hand, arm, foot, leg or eye with the subsequent
injury to the *opposite and corresponding* member. Omitting the list would
state the branch more broadly than the statute does. This is a spec-side
decomposition for classification, so each member is asserted to appear within
element five rather than against the paragraph directly.
"""

FORBIDDEN_4751_PHRASE = "a preexisting disability of at least thirty-five percent"
"""The superseded text's misattribution of the thirty-five percent floor."""

# The threshold words as the paragraph spells them, so a digit-only pin cannot
# pass against prose that spells the number differently.
_THRESHOLD_WORDS = {
    70: "at least seventy percent",
    5: "of at least five percent",
    35: "of at least thirty-five percent",
}

MEDICAL_TARGETS = (
    "QME_COMPREHENSIVE_REPORT",
    "AME_COMPREHENSIVE_REPORT",
    "IMPAIRMENT_RATING_WORKSHEET",
)
LEGAL_TARGETS = (
    "MOTION_FOR_JOINDER",
    "TRIAL_BRIEF",
    "CASE_ANALYSIS_MEMO",
    "SETTLEMENT_VALUATION_MEMO",
)

# ---------------------------------------------------------------------------
# M5-R39b — the complete resulting pools, as literals in the test.
#
# Read from the shipped tree and pinned here, NOT read back from doctrine.py:
# an oracle that imports the value it checks agrees with any value.
# ---------------------------------------------------------------------------

EXPECTED_MEDICAL_PARAGRAPHS: tuple[str, ...] = (
    "This addendum addresses what Labor Code section 4751 asks of a medical evaluator: "
    "whether a preexisting condition, if established, was labor disabling before the "
    "industrial injury, and what the combined effect of it and the current impairment "
    "would be. I have answered on the records provided and identified what a section "
    "4751 claim would still need.",
    "Section 4751 requires that the preexisting disability be labor disabling rather than "
    "merely present, and that the subsequent industrial injury combine with it to produce "
    "a substantially greater disability. Where the records establish a prior condition I "
    "have stated it as a whole person figure with the basis for it, so the section 4751 "
    "threshold can be tested against evidence rather than asserted.",
    "Where a prior labor-disabling condition is established, my opinion on whether its "
    "combined effect with the current industrial injury exceeds the sum of their separate "
    "effects is stated above with the reasoning. Whether that satisfies the thresholds of "
    "section 4751 is a legal determination that I do not make.",
)

_CORRECTED_ELEMENTS_PARAGRAPH = (
    "Labor Code section 4751 requires a preexisting permanent partial disability; "
    "a subsequent compensable injury producing additional permanent partial "
    "disability; combined permanent disability greater than that from the subsequent "
    "injury alone; combined permanent disability of at least seventy percent; and "
    "either prior disability affecting a hand, arm, foot, leg, or eye with subsequent "
    "injury to the opposite and corresponding member and subsequent disability alone, "
    "unadjusted for age or occupation, of at least five percent, or subsequent "
    "disability alone, unadjusted for age or occupation, of at least thirty-five percent."
)

_JOINDER_SENTENCES = (
    " The Fund is a separate party and must be joined; a case in chief resolved "
    "without joinder does not resolve the claim against it."
)

EXPECTED_LEGAL_PARAGRAPHS: tuple[str, ...] = (
    "Labor Code section 4751 provides benefits from the Subsequent Injuries Benefits "
    "Trust Fund where an employee with a preexisting permanent partial disability "
    "sustains a subsequent industrial injury and the combined permanent disability "
    "reaches seventy percent or more. The section 4751 thresholds must be pleaded and "
    "proved.",
    _CORRECTED_ELEMENTS_PARAGRAPH + _JOINDER_SENTENCES,
    "The applicant is on notice that the section 4751 claim will require evidence of the "
    "labor-disabling character of the preexisting condition at the time of the subsequent "
    "injury, independent of the medical evidence supporting the case in chief.",
)


# ---------------------------------------------------------------------------
# The AST-folding instrument (M5-R39c).
# ---------------------------------------------------------------------------


def folded_string_constants(source: str) -> list[str]:
    """Every string constant in *source*, with implicit concatenation folded.

    ``ast`` already folds adjacent string literals into one ``Constant``, and
    ``JoinedStr`` (an f-string) is walked so its constant parts contribute
    their own text. Comments are out of scope **by construction** — the parser
    discards them — which is why M5-R47c's comment half needs a separate
    ``tokenize`` instrument rather than a regex exception here.
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


def _source_files() -> list[Path]:
    return sorted(SOURCE_ROOT.rglob("*.py"))


class TestSection4751Elements:
    """M5-R36a — the inventory is a copy of the paragraph, not a paraphrase."""

    def test_the_corrected_paragraph_is_the_one_this_test_pins(self) -> None:
        """Form A: the pinned text is a literal here, then compared."""
        assert MEDICAL_STORY_SIBTF_SECTION_4751_PARAGRAPHS == (
            _CORRECTED_ELEMENTS_PARAGRAPH,
        )

    @pytest.mark.parametrize("element", SECTION_4751_ELEMENTS)
    def test_each_element_is_a_verbatim_substring(self, element: str) -> None:
        paragraph = "".join(MEDICAL_STORY_SIBTF_SECTION_4751_PARAGRAPHS)
        assert element in paragraph, (
            f"element {element!r} is not a substring of the shipped paragraph — "
            "the inventory was reworded rather than copied, which is the failure "
            "a label-matching contract would have hidden"
        )

    def test_the_inventory_is_exactly_five_elements(self) -> None:
        assert len(SECTION_4751_ELEMENTS) == 5

    def test_the_whole_element_inventory_is_verbatim_and_complete(self) -> None:
        """m24-68's guard — one node, so the gate collects exactly one test.

        Every element and every opposite member in one assertion set: a mutant
        that drops one element from the shipped paragraph, or drops one member
        from the closed list inside element five, reddens here. A *reworded*
        element that stays true law also reddens, which is the failure a
        label-matching contract would have let through.
        """
        paragraph = "".join(MEDICAL_STORY_SIBTF_SECTION_4751_PARAGRAPHS)
        missing = [element for element in SECTION_4751_ELEMENTS if element not in paragraph]
        assert missing == [], f"elements no longer stated verbatim: {missing}"
        assert len(SECTION_4751_ELEMENTS) == 5
        absent = [
            member
            for member in SECTION_4751_OPPOSITE_MEMBERS
            if member not in SECTION_4751_ELEMENTS[4]
        ]
        assert absent == [], f"opposite members dropped from the closed list: {absent}"

    @pytest.mark.parametrize(("name", "value"), sorted(SECTION_4751_THRESHOLDS.items()))
    def test_each_threshold_is_stated_in_the_paragraph(self, name: str, value: int) -> None:
        paragraph = "".join(MEDICAL_STORY_SIBTF_SECTION_4751_PARAGRAPHS)
        assert _THRESHOLD_WORDS[value] in paragraph, (
            f"threshold {name}={value} is no longer stated in the paragraph"
        )

    def test_the_thresholds_are_exactly_the_three_frozen_values(self) -> None:
        assert SECTION_4751_THRESHOLDS == {
            "combined": 70,
            "opposite_member": 5,
            "subsequent_alone": 35,
        }

    def test_every_threshold_is_stated_and_no_other_number_is(self) -> None:
        """m24-69's guard — one node.

        The three floors are asserted present *in the words the paragraph
        uses*, and the paragraph is asserted to state no fourth threshold: a
        mutant that retunes seventy to seventy-five reddens on both halves,
        and one that adds a floor reddens on the second.
        """
        paragraph = "".join(MEDICAL_STORY_SIBTF_SECTION_4751_PARAGRAPHS)
        for name, value in sorted(SECTION_4751_THRESHOLDS.items()):
            assert _THRESHOLD_WORDS[value] in paragraph, (
                f"threshold {name}={value} is no longer stated as "
                f"{_THRESHOLD_WORDS[value]!r}"
            )
        assert paragraph.count("percent") == 3, (
            "the paragraph states a number of percentage floors other than the "
            "three section 4751 carries"
        )

    @pytest.mark.parametrize("member", SECTION_4751_OPPOSITE_MEMBERS)
    def test_each_opposite_member_appears_in_element_five(self, member: str) -> None:
        assert member in SECTION_4751_ELEMENTS[4], (
            f"{member!r} left the member-limited branch, which would state the "
            "five percent alternative more broadly than section 4751 does"
        )

    def test_the_member_list_is_closed_at_five(self) -> None:
        assert SECTION_4751_OPPOSITE_MEMBERS == ("hand", "arm", "foot", "leg", "eye")


class TestSibtfPools:
    """M5-R39b — the complete pool per target subtype, exact tuple equality."""

    @pytest.mark.parametrize("subtype", MEDICAL_TARGETS)
    def test_a_medical_target_still_draws_the_untouched_evaluator_prose(
        self, subtype: str
    ) -> None:
        assert (
            DOCTRINE_CONTENT["sibtf"].paragraphs_for(subtype)
            == EXPECTED_MEDICAL_PARAGRAPHS
        ), (
            "the medical pool moved; item 0a touches nothing in it, and a "
            "statutory recitation does not belong in a medical evaluator's prose"
        )

    @pytest.mark.parametrize("subtype", LEGAL_TARGETS)
    def test_a_legal_target_draws_the_corrected_pool(self, subtype: str) -> None:
        assert (
            DOCTRINE_CONTENT["sibtf"].paragraphs_for(subtype)
            == EXPECTED_LEGAL_PARAGRAPHS
        ), (
            "the legal pool is not the pinned three-paragraph tuple — either the "
            "correction did not land, or the pool was collapsed/emptied, which "
            "an absence-only check would have accepted"
        )

    def test_every_target_subtype_pool_is_exactly_pinned(self) -> None:
        """m24-125's guard — all seven target subtypes in one node.

        Pinning the **whole** pool per subtype, rather than asserting the
        forbidden phrase's absence, is what makes deletion detectable: an
        implementation that replaced both pools with the one-element corrected
        tuple — or emptied ``legal_paragraphs`` outright — satisfies an
        absence check perfectly and fails here.
        """
        content = DOCTRINE_CONTENT["sibtf"]
        for subtype in MEDICAL_TARGETS:
            assert content.paragraphs_for(subtype) == EXPECTED_MEDICAL_PARAGRAPHS, subtype
        for subtype in LEGAL_TARGETS:
            assert content.paragraphs_for(subtype) == EXPECTED_LEGAL_PARAGRAPHS, subtype
        assert content.medical_paragraphs == EXPECTED_MEDICAL_PARAGRAPHS
        assert content.legal_paragraphs == EXPECTED_LEGAL_PARAGRAPHS

    def test_the_legal_pool_still_carries_all_three_paragraphs(self) -> None:
        """The deletion guard, stated on its own so the failure names itself."""
        assert len(DOCTRINE_CONTENT["sibtf"].legal_paragraphs) == 3
        assert len(DOCTRINE_CONTENT["sibtf"].medical_paragraphs) == 3

    def test_the_corrected_paragraph_keeps_the_joinder_sentences(self) -> None:
        corrected = DOCTRINE_CONTENT["sibtf"].legal_paragraphs[1]
        assert "The Fund is a separate party and must be joined" in corrected
        assert (
            "a case in chief resolved without joinder does not resolve the claim "
            "against it" in corrected
        )

    def test_only_the_second_legal_paragraph_moved(self) -> None:
        """The surgical claim, asserted rather than asserted-about."""
        assert (
            DOCTRINE_CONTENT["sibtf"].legal_paragraphs[0]
            == EXPECTED_LEGAL_PARAGRAPHS[0]
        )
        assert (
            DOCTRINE_CONTENT["sibtf"].legal_paragraphs[2]
            == EXPECTED_LEGAL_PARAGRAPHS[2]
        )
        assert DOCTRINE_CONTENT["sibtf"].legal_paragraphs[1].startswith(
            "Labor Code section 4751 requires a preexisting permanent partial disability"
        )


class TestFlagArms:
    """M5-R39a(3) — the corrected pool is selected unconditionally.

    The renderer's ``medical_story_enabled`` keyword no longer selects content.
    Asserted by observing the pool **through the renderer**, over both arms and
    over enough draws to see every member, rather than by reading the source:
    a fix applied to one path only would pass a single-arm probe.
    """

    @staticmethod
    def _observed_pool(subtype: str, *, enabled: bool) -> set[str]:
        pytest.importorskip("reportlab")
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

        from wc_caseload_engine.renderer import doctrine_flowables

        styles = getSampleStyleSheet()
        for name in ("BodyText14", "SmallItalic", "SectionHeader"):
            if name not in styles:
                styles.add(ParagraphStyle(name=name, parent=styles["BodyText"]))

        class _Template:
            def __init__(self) -> None:
                self.styles = styles
                self._wc_case_facts = None

            @staticmethod
            def make_hr() -> Any:
                from reportlab.platypus import HRFlowable

                return HRFlowable()

        class _Seed:
            rng_seed = 4751

        drawn: set[str] = set()
        for index in range(64):
            flowables = doctrine_flowables(
                _Template(),
                subtype=subtype,
                seed=_Seed(),  # type: ignore[arg-type]
                index=index,
                content_flags=("sibtf",),
                medical_story_enabled=enabled,
            )
            texts = [
                item.getPlainText() for item in flowables if hasattr(item, "getPlainText")
            ]
            drawn.update(texts)
        return drawn

    def test_both_flag_arms_draw_identical_pools_for_every_target(self) -> None:
        """m24-27's guard — all seven targets, both arms, in one node.

        Restoring the ``medical_story_enabled`` condition puts the corrected
        elements back on the flagged arm only, so the two arms diverge on
        every target and this reddens. A single-arm probe would not: with the
        condition back, the *unflagged* arm renders exactly what this item was
        written to stop shipping.
        """
        for subtype in LEGAL_TARGETS + MEDICAL_TARGETS:
            on = self._observed_pool(subtype, enabled=True)
            off = self._observed_pool(subtype, enabled=False)
            assert on == off, (
                f"{subtype}: the medical-story flag still steers section 4751 "
                "content; the corrected text must be the only text on every "
                "render path"
            )
            expected = set(DOCTRINE_CONTENT["sibtf"].paragraphs_for(subtype))
            assert expected <= on, (
                f"{subtype}: only {len(expected & on)} of {len(expected)} pool "
                "members were ever drawn"
            )

    @pytest.mark.parametrize("subtype", LEGAL_TARGETS + MEDICAL_TARGETS)
    def test_both_flag_arms_draw_the_same_pool(self, subtype: str) -> None:
        on = self._observed_pool(subtype, enabled=True)
        off = self._observed_pool(subtype, enabled=False)
        assert on == off, (
            "the medical-story flag still steers section 4751 content; the "
            "corrected text must be the only text on every render path"
        )
        expected = set(DOCTRINE_CONTENT["sibtf"].paragraphs_for(subtype))
        assert expected <= on, (
            f"only {len(expected & on)} of {len(expected)} pool members were "
            "ever drawn; the observed pool is not the declared pool"
        )

    @pytest.mark.parametrize("subtype", LEGAL_TARGETS)
    def test_a_legal_target_renders_the_corrected_elements_on_both_arms(
        self, subtype: str
    ) -> None:
        for enabled in (True, False):
            drawn = " ".join(sorted(self._observed_pool(subtype, enabled=enabled)))
            assert "unadjusted for age or occupation, of at least five percent" in drawn
            assert FORBIDDEN_4751_PHRASE not in drawn


class TestForbiddenPhraseSweep:
    """M5-R39c — AST-folded over source, and over rendered output."""

    def test_the_folding_instrument_sees_a_split_phrase(self) -> None:
        """Positive control.

        The live defect was written as two adjacent literals split mid-phrase.
        A raw substring search over the source returns False against exactly
        that shape, so the control plants it and requires the instrument to
        find it. Without this the sweep below could pass vacuously.
        """
        planted = (
            'x = (\n'
            '    "A claim under section 4751 requires either '
            'a preexisting disability of at least "\n'
            '    "thirty-five percent, or a subsequent injury."\n'
            ')\n'
        )
        assert FORBIDDEN_4751_PHRASE not in planted, (
            "the control is not testing folding — the phrase is already "
            "contiguous in the raw source"
        )
        assert any(
            FORBIDDEN_4751_PHRASE in value for value in folded_string_constants(planted)
        )

    def test_the_sweep_covers_the_whole_package(self) -> None:
        files = _source_files()
        assert len(files) >= 20, f"the sweep collected only {len(files)} source files"
        assert SOURCE_ROOT / "doctrine.py" in files
        assert SOURCE_ROOT / "renderer.py" in files

    def test_no_folded_literal_states_the_forbidden_phrase(self) -> None:
        offenders = [
            str(path.relative_to(PACKAGE))
            for path in _source_files()
            if any(
                FORBIDDEN_4751_PHRASE in value
                for value in folded_string_constants(
                    path.read_text(encoding="utf-8")
                )
            )
        ]
        assert offenders == [], (
            f"the superseded section 4751 threshold survives in {offenders}"
        )

    def test_no_rendered_document_states_the_forbidden_phrase(
        self, demo_manifests: dict[str, dict[str, Any]]
    ) -> None:
        """The runtime half: a phrase can be assembled from parts no literal holds.

        Scope is the generated demo corpus — the package output this suite
        already builds once per session. It is an absence assertion, so the
        instrument's liveness is carried by the folding control above and by
        ``m24-126``, which restores the phrase into ``doctrine.py`` as split
        literals and must redden the source sweep.
        """
        assert demo_manifests, "no demo case manifests were generated"
        for case_id, manifest in demo_manifests.items():
            for entry, path in iter_documents(manifest):
                text = extract_text(path, entry.get("format", ""))
                assert FORBIDDEN_4751_PHRASE not in text, (
                    f"{case_id}/{entry['filename']} renders the superseded "
                    "section 4751 threshold"
                )
