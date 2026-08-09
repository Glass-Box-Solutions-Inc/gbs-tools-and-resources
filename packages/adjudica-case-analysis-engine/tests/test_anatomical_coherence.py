"""Rule pack #1 — surgical CPT codes that contradict the injured anatomy.

Restraint is the property under test as much as detection is. Roughly two thirds
of these cases assert that nothing fires, because a detector that cries wolf on a
clean corpus is worse than no detector at all.
"""

import json
from pathlib import Path

from click.testing import CliRunner

from adjudica_case_analysis_engine.cli import cli
from adjudica_case_analysis_engine.input import normalize_paths
from adjudica_case_analysis_engine.rules import run_rules
from adjudica_case_analysis_engine.rules.anatomical_coherence import (
    NON_OPERATIVE_CPT_CODES,
    OPERATIVE_CPT_ANATOMY,
    UNLISTED_CPT_CODES,
    contradicts,
    regions_named_by,
)

FIXTURES = Path(__file__).parent / "fixtures"
CODE = "anatomical_contradiction"


def _findings(tmp_path: Path, payload: object, name: str = "case.json"):
    source = tmp_path / name
    source.write_text(json.dumps(payload), encoding="utf-8")
    return run_rules(normalize_paths([source]))


def _codes(findings) -> list[str]:
    return [finding.code for finding in findings]


# ── The knowledge table ──────────────────────────────────────────────────────


def test_the_three_code_classes_are_disjoint() -> None:
    """A code is operative, non-operative, or unlisted — never two of those at once."""
    operative = set(OPERATIVE_CPT_ANATOMY)
    assert not operative & NON_OPERATIVE_CPT_CODES
    assert not operative & UNLISTED_CPT_CODES
    assert not NON_OPERATIVE_CPT_CODES & UNLISTED_CPT_CODES


def test_every_table_entry_is_a_five_digit_code_naming_a_known_region() -> None:
    """A typo in the table would otherwise sit there silently never matching anything."""
    every_code = set(OPERATIVE_CPT_ANATOMY) | NON_OPERATIVE_CPT_CODES | UNLISTED_CPT_CODES
    assert all(len(code) == 5 and code.isdigit() for code in every_code)
    for code, region in OPERATIVE_CPT_ANATOMY.items():
        assert regions_named_by(region.replace("_", " ")), f"{code} names unmatchable {region!r}"


def test_the_codes_this_detector_exists_for_are_all_covered() -> None:
    """The AJC-55 pools are the defect surface; every code in them must be classified."""
    for code in ("63030", "63075", "22551", "63055", "29827", "23412", "29881", "27447"):
        assert code in OPERATIVE_CPT_ANATOMY
    for code in ("64721", "26055", "24357", "64718", "27130", "27822", "28285"):
        assert code in OPERATIVE_CPT_ANATOMY
    assert "64483" in NON_OPERATIVE_CPT_CODES, "an injection is not an operation"
    assert "64999" in UNLISTED_CPT_CODES, "the retired generator fallback asserts no anatomy"


def test_positive_control_the_table_can_actually_contradict() -> None:
    """House doctrine: prove the oracle is capable of failing, or it proves nothing."""
    # Wrong region entirely — the AJC-55 defect class.
    assert contradicts("29827", frozenset({"wrist"}))
    # Wrong segment inside the right region — the subtler half of the same defect.
    assert contradicts("63030", frozenset({"thoracic_spine"}))
    assert contradicts("63075", frozenset({"lumbar_spine"}))
    # And the matching cases are genuinely not contradictions.
    assert not contradicts("29827", frozenset({"shoulder"}))
    assert not contradicts("63030", frozenset({"lumbar_spine"}))


def test_body_parts_match_whole_tokens_never_substrings() -> None:
    """'background' is not a back and 'secondhand' is not a hand — AJC-55 learned this."""
    assert regions_named_by("background noise") == frozenset()
    assert regions_named_by("secondhand report") == frozenset()
    assert regions_named_by("handled the forklift") == frozenset()
    assert regions_named_by("shoulders") == frozenset({"shoulder"})


def test_the_longest_body_part_phrase_wins() -> None:
    """'low back' is the lumbar spine; letting bare 'back' also match would mask a segment."""
    assert regions_named_by("low back") == frozenset({"lumbar_spine"})
    assert regions_named_by("lumbar spine") == frozenset({"lumbar_spine"})
    assert regions_named_by("upper back") == frozenset({"thoracic_spine"})


def test_laterality_is_not_anatomy() -> None:
    """A left/right mismatch is a different detector; this one reads the region only."""
    assert regions_named_by("left shoulder") == frozenset({"shoulder"})
    assert regions_named_by("right wrist") == frozenset({"wrist"})
    assert not contradicts("29827", frozenset({"shoulder"}))


def test_an_unsegmented_spine_injury_never_contradicts_a_segment() -> None:
    """Bare 'back' names no segment, and an unknown segment is not a wrong one."""
    assert regions_named_by("back") == frozenset({"spine"})
    assert regions_named_by("spine") == frozenset({"spine"})
    assert not contradicts("63075", frozenset({"spine"}))
    assert not contradicts("63030", frozenset({"spine"}))


def test_an_unknown_or_non_operative_code_never_contradicts() -> None:
    """Unknown is not wrong, and an injection is not an operation."""
    assert not contradicts("99213", frozenset({"wrist"}))
    assert not contradicts("64483", frozenset({"wrist"}))
    assert not contradicts("64999", frozenset({"wrist"}))
    assert not contradicts("29827", frozenset())


# ── The detector over a ledger ───────────────────────────────────────────────


def test_a_wrist_case_asserting_a_shoulder_arthroscopy_is_flagged(tmp_path: Path) -> None:
    """The AJC-55 defect class, seen from the analyzer side."""
    findings = _findings(
        tmp_path,
        {
            "injury": {"body_part": "right wrist"},
            "caseFacts": {"surgery": {"status": "performed", "cptCode": "29827"}},
        },
    )

    assert _codes(findings) == [CODE]
    assert findings[0].severity == "error"
    assert findings[0].category == "medical"


def test_the_finding_names_the_code_both_anatomies_and_its_source(tmp_path: Path) -> None:
    """A reviewer must be able to act on the message without opening the ledger."""
    findings = _findings(
        tmp_path,
        {
            "injury": {"body_part": "right wrist"},
            "caseFacts": {"surgery": {"status": "performed", "cptCode": "29827"}},
        },
        name="manifest.json",
    )

    message = findings[0].message
    assert "29827" in message
    assert "shoulder" in message
    assert "wrist" in message
    assert "manifest.json" in message
    # Every cited fact is traceable, and the operative assertion leads.
    assert findings[0].fact_ids[0] == "manifest.json:$.caseFacts.surgery.cptCode"
    assert any("injury" in fact_id for fact_id in findings[0].fact_ids)


def test_a_multi_part_case_matching_any_injured_part_is_clean(tmp_path: Path) -> None:
    """A knee operation on a lumbar-and-knee case contradicts nothing."""
    findings = _findings(
        tmp_path,
        {
            "injury": {"body_parts": ["lumbar spine", "left knee"]},
            "caseFacts": {"surgery": {"status": "performed", "cptCode": "29881"}},
        },
    )

    assert CODE not in _codes(findings)


def test_an_uncoded_operation_is_never_a_contradiction(tmp_path: Path) -> None:
    """Post-AJC-55 corpora legitimately carry operations with no code at all."""
    for surgery in (
        {"status": "performed", "cptCode": None, "uncoded": True},
        {"status": "performed", "cptCode": "N/A", "procedure": "Unlisted surgical procedure"},
        {"status": "performed", "procedure": "an unlisted surgical procedure (uncoded)"},
        {"status": "performed", "cptCode": "29999", "uncoded": False},
    ):
        findings = _findings(
            tmp_path,
            {"injury": {"body_part": "right wrist"}, "caseFacts": {"surgery": surgery}},
        )
        assert CODE not in _codes(findings), surgery


def test_an_uncoded_declaration_suppresses_a_stray_code(tmp_path: Path) -> None:
    """The record says it named no code; a sibling that looks like one is not an assertion."""
    findings = _findings(
        tmp_path,
        {
            "injury": {"body_part": "right wrist"},
            "caseFacts": {
                "surgery": {"status": "performed", "uncoded": True, "priorCptCode": "29827"}
            },
        },
    )

    assert CODE not in _codes(findings)


def test_an_injection_code_is_never_an_anatomical_contradiction(tmp_path: Path) -> None:
    """Injections keep their own category for non-surgical paths — flagging them is noise."""
    findings = _findings(
        tmp_path,
        {
            "injury": {"body_part": "right wrist"},
            "caseFacts": {"surgery": {"status": "performed", "cptCode": "64483"}},
        },
    )

    assert CODE not in _codes(findings)


def test_an_unknown_code_produces_no_finding_at_all(tmp_path: Path) -> None:
    """Unknown is not a contradiction, and a per-case note about it would be pure noise."""
    findings = _findings(
        tmp_path,
        {
            "injury": {"body_part": "right wrist"},
            "caseFacts": {"surgery": {"status": "performed", "cptCode": "12345"}},
        },
    )

    assert findings == () or CODE not in _codes(findings)


def test_a_billing_line_item_is_not_an_operation_assertion(tmp_path: Path) -> None:
    """AJC-55 left billing/TPR/UR sampling CPTs flat on purpose.

    A lumbar case's billing record may legitimately name 29827. Reading every CPT
    in the ledger as an asserted operation would false-positive across the whole
    generated corpus, which is exactly what the Phase 3 precision gate punishes.
    """
    findings = _findings(
        tmp_path,
        {
            "injury": {"body_part": "lumbar spine"},
            "billing": {"lineItems": [{"cptCode": "29827"}, {"cptCode": "27447"}]},
            "treatingPhysicianReport": {"cptCode": "23412"},
            "utilizationReview": {"cptCode": "29881"},
        },
    )

    assert CODE not in _codes(findings)


def test_a_case_with_no_recognized_injured_part_is_not_flagged(tmp_path: Path) -> None:
    """With nothing to contradict, silence is the only correct answer."""
    findings = _findings(
        tmp_path,
        {
            "injury": {"body_part": "psyche"},
            "caseFacts": {"surgery": {"status": "performed", "cptCode": "29827"}},
        },
    )

    assert CODE not in _codes(findings)


def test_the_operated_part_is_never_read_back_as_an_injured_part(tmp_path: Path) -> None:
    """surgery.bodyPart is chosen with the code, so trusting it would disarm the detector."""
    findings = _findings(
        tmp_path,
        {
            "injury": {"body_part": "right wrist"},
            "caseFacts": {
                "surgery": {"status": "performed", "cptCode": "29827", "bodyPart": "shoulder"}
            },
        },
    )

    assert _codes(findings) == [CODE]


def test_a_code_embedded_in_operative_prose_is_still_an_assertion(tmp_path: Path) -> None:
    """'(CPT 29827)' inside an operative narrative asserts the operation just as plainly."""
    findings = _findings(
        tmp_path,
        {
            "injury": {"body_part": "right wrist"},
            "caseFacts": {
                "surgery": {
                    "status": "performed",
                    "narrative": "Applicant underwent rotator cuff repair (CPT 29827).",
                }
            },
        },
    )

    assert _codes(findings) == [CODE]


def test_a_bare_number_outside_a_code_field_is_not_a_code(tmp_path: Path) -> None:
    """Claim numbers and ZIP codes are five digits too."""
    findings = _findings(
        tmp_path,
        {
            "injury": {"body_part": "right wrist"},
            "caseFacts": {"surgery": {"status": "performed", "authorizationRef": "29827"}},
        },
    )

    assert CODE not in _codes(findings)


def test_wrong_segment_within_the_spine_is_flagged(tmp_path: Path) -> None:
    """A thoracic case publishing a lumbar discectomy is the subtler AJC-55 defect."""
    findings = _findings(
        tmp_path,
        {
            "injury": {"body_part": "thoracic spine"},
            "caseFacts": {"surgery": {"status": "performed", "cptCode": "63030"}},
        },
    )

    assert _codes(findings) == [CODE]
    assert "thoracic spine" in findings[0].message


def test_a_proposed_or_denied_operation_is_still_an_assertion(tmp_path: Path) -> None:
    """recommended and denied_by_ur both name a CPT, and both describe this case's anatomy."""
    for status in ("recommended", "denied_by_ur"):
        findings = _findings(
            tmp_path,
            {
                "injury": {"body_part": "right wrist"},
                "caseFacts": {"surgery": {"status": status, "cptCode": "27447"}},
            },
        )
        assert _codes(findings) == [CODE], status


# ── Whole-corpus restraint ───────────────────────────────────────────────────


def test_the_existing_clean_fixtures_stay_clean() -> None:
    """The zero-false-positive invariant, asserted rather than demonstrated by hand."""
    for fixture in ("intake.json", "generator_manifest.json", "case_facts.yaml"):
        findings = run_rules(normalize_paths([FIXTURES / fixture]))
        assert CODE not in _codes(findings), fixture

    combined = run_rules(normalize_paths([FIXTURES / "intake.json", FIXTURES / "case_facts.yaml"]))
    assert CODE not in _codes(combined)


def test_a_matching_operation_across_two_inputs_is_clean() -> None:
    """Intake names the injury, the manifest names the operation, and they agree."""
    findings = run_rules(
        normalize_paths(
            [FIXTURES / "anatomy_intake_wrist.json", FIXTURES / "anatomy_manifest_wrist.json"]
        )
    )

    assert CODE not in _codes(findings)


def test_a_contradiction_across_two_inputs_fails_the_validate_cli() -> None:
    """An error-severity finding is what turns a corpus regression into a red gate."""
    result = CliRunner().invoke(
        cli,
        [
            "validate",
            str(FIXTURES / "anatomy_intake_wrist.json"),
            str(FIXTURES / "anatomy_manifest_shoulder.json"),
        ],
    )

    assert result.exit_code != 0
    assert CODE in result.output

    clean = CliRunner().invoke(
        cli,
        [
            "validate",
            str(FIXTURES / "anatomy_intake_wrist.json"),
            str(FIXTURES / "anatomy_manifest_wrist.json"),
        ],
    )
    assert CODE not in clean.output
