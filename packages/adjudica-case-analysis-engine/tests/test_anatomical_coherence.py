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
    CURRENT_CARE_NAMESPACES,
    HISTORICAL_CODE_FIELDS,
    HISTORICAL_NAMESPACES,
    INJURED_PART_PATH_SHAPES,
    LOCALIZABLE_UNLISTED_CPT_ANATOMY,
    NON_OPERATIVE_CPT_CODES,
    NONLOCALIZABLE_UNLISTED_CPT_CODES,
    OPERATIVE_CPT_ANATOMY,
    UNLISTED_CPT_CODES,
    contradicts,
    regions_named_by,
)

FIXTURES = Path(__file__).parent / "fixtures"
CODE = "anatomical_contradiction"

# ── Independently committed table membership ─────────────────────────────────
#
# The behavioural matrices below generate their cases *from* the production tables, so
# they cover additions but not deletions: removing or misspelling an entry takes its own
# generated control away with it, and the suite stays green. Membership therefore has to
# be pinned by something that does not move when the table moves.
#
# These literals are that anchor. Changing a production table means changing the matching
# literal here, in the same commit, deliberately — which is the point.

EXPECTED_INJURED_PART_PATH_SHAPES = frozenset(
    {
        "body_part_injured",
        "body_parts_injured",
        "injured_body_part",
        "injured_body_parts",
        "injured_body_parts[]",
        "injured_part",
        "injured_parts",
        "injured_parts[]",
        "injured_site",
        "injuries[].body_part",
        "injuries[].body_parts[]",
        "injury.body_part",
        "injury.body_parts",
        "injury.body_parts[]",
        "injury.body_parts[].part",
        "injury.site",
        "injury.sites[]",
        "injury_body_part",
        "injury_body_parts",
        "injury_body_parts[]",
        "injury_site",
        "injury_sites",
        "injury_sites[]",
    }
)

EXPECTED_HISTORICAL_NAMESPACES = frozenset(
    {
        "history",
        "medical_history",
        "past_medical_history",
        "past_surgeries",
        "previous_surgeries",
        "prior_injuries",
        "prior_injury",
        "prior_surgeries",
        "prior_surgery",
        "prior_treatment",
        "surgical_history",
    }
)

EXPECTED_CURRENT_CARE_NAMESPACES = frozenset(
    {
        "current_care",
        "current_episode",
        "current_surgery",
        "current_treatment",
        "history_and_physical",
        "prior_authorization",
        "prior_authorizations",
    }
)

EXPECTED_HISTORICAL_CODE_FIELDS = frozenset(
    {
        "past_cpt_code",
        "previous_cpt_code",
        "previous_procedure_code",
        "prior_cpt_code",
        "prior_procedure_code",
        "prior_surgical_code",
    }
)

EXPECTED_OPERATIVE_CPT_ANATOMY = {
    "22551": "cervical_spine",
    "22554": "cervical_spine",
    "22556": "thoracic_spine",
    "22558": "lumbar_spine",
    "22612": "lumbar_spine",
    "22630": "lumbar_spine",
    "23412": "shoulder",
    "23430": "shoulder",
    "23472": "shoulder",
    "24342": "elbow",
    "24357": "elbow",
    "24358": "elbow",
    "25000": "wrist",
    "25111": "wrist",
    "26055": "hand",
    "26123": "hand",
    "26160": "hand",
    "27125": "hip",
    "27130": "hip",
    "27132": "hip",
    "27446": "knee",
    "27447": "knee",
    "27650": "ankle",
    "27792": "ankle",
    "27822": "ankle",
    "28060": "foot",
    "28110": "foot",
    "28285": "foot",
    "28296": "foot",
    "29806": "shoulder",
    "29826": "shoulder",
    "29827": "shoulder",
    "29862": "hip",
    "29880": "knee",
    "29881": "knee",
    "29888": "knee",
    "29891": "ankle",
    "63020": "cervical_spine",
    "63030": "lumbar_spine",
    "63042": "lumbar_spine",
    "63046": "thoracic_spine",
    "63047": "lumbar_spine",
    "63055": "thoracic_spine",
    "63075": "cervical_spine",
    "63081": "cervical_spine",
    "64718": "elbow",
    "64721": "wrist",
}

EXPECTED_LOCALIZABLE_UNLISTED_CPT_ANATOMY = {
    "22899": frozenset({"cervical_spine", "lumbar_spine", "spine", "thoracic_spine"}),
    "23929": frozenset({"shoulder"}),
    "24999": frozenset({"elbow", "shoulder"}),
    "26989": frozenset({"hand"}),
    "27299": frozenset({"hip"}),
    "27599": frozenset({"hip", "knee"}),
    "27899": frozenset({"ankle", "knee"}),
    "28899": frozenset({"foot"}),
}

EXPECTED_NON_OPERATIVE_CPT_CODES = frozenset(
    {
        "20550",
        "20551",
        "20605",
        "20610",
        "62321",
        "62323",
        "64483",
        "64484",
        "64490",
        "64493",
        "72148",
        "73721",
        "95886",
    }
)

EXPECTED_NONLOCALIZABLE_UNLISTED_CPT_CODES = frozenset({"29999", "64999"})


def _findings(tmp_path: Path, payload: object, name: str = "case.json"):
    source = tmp_path / name
    source.write_text(json.dumps(payload), encoding="utf-8")
    return run_rules(normalize_paths([source]))


def _codes(findings) -> list[str]:
    return [finding.code for finding in findings]


# ── The knowledge table ──────────────────────────────────────────────────────


def _assert_membership(actual, expected, table: str) -> None:
    """Compare a production table against its committed literal, naming what drifted."""
    removed = sorted(set(expected) - set(actual))
    added = sorted(set(actual) - set(expected))
    assert not removed, f"{table}: entries removed without updating the committed list: {removed}"
    assert not added, f"{table}: entries added without updating the committed list: {added}"


def test_the_injured_part_shape_table_matches_its_committed_membership() -> None:
    """A deleted shape must fail here, where the generated matrices cannot see it."""
    _assert_membership(
        INJURED_PART_PATH_SHAPES, EXPECTED_INJURED_PART_PATH_SHAPES, "INJURED_PART_PATH_SHAPES"
    )
    assert len(INJURED_PART_PATH_SHAPES) == 23


def test_the_namespace_tables_match_their_committed_membership() -> None:
    """Historical and current-care classification is the boundary; pin both sides of it."""
    _assert_membership(
        HISTORICAL_NAMESPACES, EXPECTED_HISTORICAL_NAMESPACES, "HISTORICAL_NAMESPACES"
    )
    _assert_membership(
        CURRENT_CARE_NAMESPACES, EXPECTED_CURRENT_CARE_NAMESPACES, "CURRENT_CARE_NAMESPACES"
    )
    _assert_membership(
        HISTORICAL_CODE_FIELDS, EXPECTED_HISTORICAL_CODE_FIELDS, "HISTORICAL_CODE_FIELDS"
    )
    assert len(HISTORICAL_NAMESPACES) == 11
    assert len(CURRENT_CARE_NAMESPACES) == 7
    assert len(HISTORICAL_CODE_FIELDS) == 6


def test_the_cpt_tables_match_their_committed_membership() -> None:
    """Both the codes and the anatomy each one claims, so a silent re-mapping fails too."""
    _assert_membership(
        OPERATIVE_CPT_ANATOMY, EXPECTED_OPERATIVE_CPT_ANATOMY, "OPERATIVE_CPT_ANATOMY"
    )
    assert dict(OPERATIVE_CPT_ANATOMY) == EXPECTED_OPERATIVE_CPT_ANATOMY

    _assert_membership(
        LOCALIZABLE_UNLISTED_CPT_ANATOMY,
        EXPECTED_LOCALIZABLE_UNLISTED_CPT_ANATOMY,
        "LOCALIZABLE_UNLISTED_CPT_ANATOMY",
    )
    assert dict(LOCALIZABLE_UNLISTED_CPT_ANATOMY) == EXPECTED_LOCALIZABLE_UNLISTED_CPT_ANATOMY

    _assert_membership(
        NON_OPERATIVE_CPT_CODES, EXPECTED_NON_OPERATIVE_CPT_CODES, "NON_OPERATIVE_CPT_CODES"
    )
    _assert_membership(
        NONLOCALIZABLE_UNLISTED_CPT_CODES,
        EXPECTED_NONLOCALIZABLE_UNLISTED_CPT_CODES,
        "NONLOCALIZABLE_UNLISTED_CPT_CODES",
    )

    assert len(OPERATIVE_CPT_ANATOMY) == 47
    assert len(LOCALIZABLE_UNLISTED_CPT_ANATOMY) == 8
    assert len(NON_OPERATIVE_CPT_CODES) == 13
    assert len(NONLOCALIZABLE_UNLISTED_CPT_CODES) == 2


def test_the_three_code_classes_are_disjoint() -> None:
    """A code is operative, non-operative, or unlisted — never two of those at once."""
    operative = set(OPERATIVE_CPT_ANATOMY)
    assert not operative & NON_OPERATIVE_CPT_CODES
    assert not operative & UNLISTED_CPT_CODES
    assert not NON_OPERATIVE_CPT_CODES & UNLISTED_CPT_CODES
    # And the two halves of the unlisted class partition it exactly.
    assert not set(LOCALIZABLE_UNLISTED_CPT_ANATOMY) & NONLOCALIZABLE_UNLISTED_CPT_CODES
    assert (
        set(LOCALIZABLE_UNLISTED_CPT_ANATOMY) | NONLOCALIZABLE_UNLISTED_CPT_CODES
        == UNLISTED_CPT_CODES
    )


def test_every_table_entry_is_a_five_digit_code_naming_a_known_region() -> None:
    """A typo in the table would otherwise sit there silently never matching anything."""
    every_code = set(OPERATIVE_CPT_ANATOMY) | NON_OPERATIVE_CPT_CODES | UNLISTED_CPT_CODES
    assert all(len(code) == 5 and code.isdigit() for code in every_code)
    for code, region in OPERATIVE_CPT_ANATOMY.items():
        assert regions_named_by(region.replace("_", " ")), f"{code} names unmatchable {region!r}"
    for code, regions in LOCALIZABLE_UNLISTED_CPT_ANATOMY.items():
        assert regions, f"{code} is listed as localizable but names no region"
        for region in regions:
            assert regions_named_by(region.replace("_", " ")), f"{code}: unmatchable {region!r}"


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


def test_a_localizable_unlisted_code_is_still_checked() -> None:
    """23929 is "unlisted procedure, shoulder" — it names an area even with no procedure."""
    assert contradicts("23929", frozenset({"wrist"}))
    assert not contradicts("23929", frozenset({"shoulder"}))
    assert contradicts("28899", frozenset({"shoulder"}))
    assert not contradicts("28899", frozenset({"foot"}))
    assert contradicts("22899", frozenset({"knee"}))
    assert not contradicts("22899", frozenset({"lumbar_spine"}))


def test_a_nonlocalizable_unlisted_code_stays_silent() -> None:
    """Codes meaning any arthroscopy or any nerve name no body area to contradict."""
    assert not contradicts("29999", frozenset({"wrist"}))
    assert not contradicts("64999", frozenset({"wrist"}))


def test_region_matching_stays_purely_lexical() -> None:
    """regions_named_by reports what a string names; whether it is *claimed* is decided
    by which field the string came from, never by parsing the sentence."""
    assert regions_named_by("No shoulder injury") == frozenset({"shoulder"})
    assert regions_named_by("Lumbar strain") == frozenset({"lumbar_spine"})


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
            "caseFacts": {"surgery": {"status": "performed", "uncoded": True, "cptCode": "29827"}},
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
    """An operation record's own body part is chosen with the code, so trusting it
    would let the check answer itself.

    Deliberately uses `injuredPart` under the surgery namespace: `surgery.bodyPart` is
    already refused by shape, so it would no longer exercise the operation-surface
    guard this test exists to cover.
    """
    findings = _findings(
        tmp_path,
        {
            "injury": {"body_part": "right wrist"},
            "caseFacts": {
                "surgery": {"status": "performed", "cptCode": "29827", "injuredPart": "shoulder"}
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


def test_a_generic_code_field_is_not_a_procedure_code(tmp_path: Path) -> None:
    """A postal code is not a CPT. "code" alone is not affirmative procedure vocabulary."""
    for field in ("postalCode", "authorizationCode", "diagnosisCode", "facilityCode", "zipCode"):
        findings = _findings(
            tmp_path,
            {
                "injury": {"body_part": "right wrist"},
                "caseFacts": {"surgery": {"status": "performed", field: "29827"}},
            },
        )
        assert CODE not in _codes(findings), field


def test_the_fields_that_do_name_procedure_codes_are_still_read(tmp_path: Path) -> None:
    """Narrowing the code vocabulary must not disarm the detector on real code fields."""
    for field in ("cptCode", "cpt", "procedureCode", "surgicalCode", "cpt_code"):
        findings = _findings(
            tmp_path,
            {
                "injury": {"body_part": "right wrist"},
                "caseFacts": {"surgery": {"status": "performed", field: "29827"}},
            },
        )
        assert _codes(findings) == [CODE], field


def test_free_form_prose_never_contributes_anatomy(tmp_path: Path) -> None:
    """Prose is not read for anatomy at all, in either direction.

    Deciding whether "No evidence of injury to shoulder" asserts or denies the
    shoulder means resolving negation scope across clauses, and every window rule
    tried got some ordering wrong. This corpus always materializes structured
    body-part fields, so the parsing problem is declined rather than half-solved.
    """
    for prose in (
        "No evidence of injury to shoulder",
        "lifting to shoulder height",
        "denies shoulder complaints",
        "wrist sprain; no shoulder injury",
        "no shoulder injury; wrist sprain",
    ):
        findings = _findings(
            tmp_path,
            {
                "injury": {"body_part": "right wrist", "mechanism": prose},
                "diagnosis": prose,
                "narrative": prose,
                "caseFacts": {"surgery": {"status": "performed", "cptCode": "29827"}},
            },
        )
        assert _codes(findings) == [CODE], prose


def test_prose_alone_leaves_nothing_to_contradict(tmp_path: Path) -> None:
    """The other direction: prose naming a region does not clear an operation either."""
    findings = _findings(
        tmp_path,
        {
            "diagnosis": "Full-thickness rotator cuff tear of the left shoulder",
            "caseFacts": {"surgery": {"status": "performed", "cptCode": "29827"}},
        },
    )

    assert CODE not in _codes(findings)


def test_injured_anatomy_is_read_only_from_enumerated_shapes(tmp_path: Path) -> None:
    """A recognized leaf name in the wrong namespace is not an injury claim.

    The generator seed really carries `scenario.diagnostics[].body_part` — a diagnostic
    scoped to a region, including regions explicitly *not* imaged — and a history block
    can carry `priorInjury.bodyPart`. Accepting a leaf name wherever it appeared let any
    of them silently clear a contradiction.
    """
    for extra in (
        {"scenario": {"diagnostics": {"absent": [{"body_part": "shoulder"}]}}},
        {"scenario": {"diagnostics": [{"modality": "mri", "body_part": "shoulder"}]}},
        {"exam": {"body_parts": [{"part": "shoulder"}]}},
        {"medicalHistory": {"priorInjury": {"bodyPart": "shoulder"}}},
    ):
        findings = _findings(
            tmp_path,
            {
                "injury": {"body_parts": [{"part": "right wrist"}]},
                **extra,
                "caseFacts": {"surgery": {"status": "performed", "cptCode": "29827"}},
            },
        )
        assert _codes(findings) == [CODE], extra


def _payload_for_shape(shape: str, value: str) -> dict:
    """The minimal payload that materializes one path shape, built from the shape itself.

    Generating rather than hand-listing is what keeps the matrix exhaustive: a shape
    added to the table without a control cannot slip through, because the controls *are*
    the table.
    """
    node: object = value
    for segment in reversed(shape.split(".")):
        node = {segment[:-2]: [node]} if segment.endswith("[]") else {segment: node}
    return node  # type: ignore[return-value]


_SHOULDER_OPERATION = {"caseFacts": {"surgery": {"status": "performed", "cptCode": "29827"}}}


def test_every_enumerated_shape_clears_a_matching_operation(tmp_path: Path) -> None:
    """Every shape in the closed list, exercised as a positive control."""
    checked = set()
    for shape in sorted(INJURED_PART_PATH_SHAPES):
        payload = {**_payload_for_shape(shape, "shoulder"), **_SHOULDER_OPERATION}
        assert CODE not in _codes(_findings(tmp_path, payload)), shape
        checked.add(shape)

    assert checked == set(INJURED_PART_PATH_SHAPES)


def test_no_enumerated_shape_survives_a_foreign_namespace(tmp_path: Path) -> None:
    """The same shapes, nested under a history block, must claim nothing.

    Exactness is the whole guarantee: a shape is an assertion where the archive puts
    injuries, and nowhere else.
    """
    checked = set()
    for shape in sorted(INJURED_PART_PATH_SHAPES):
        payload = {
            "injury": {"body_part": "right wrist"},
            "medicalHistory": _payload_for_shape(shape, "shoulder"),
            **_SHOULDER_OPERATION,
        }
        assert _codes(_findings(tmp_path, payload)) == [CODE], shape
        checked.add(shape)

    assert checked == set(INJURED_PART_PATH_SHAPES)


def test_an_archive_wrapper_is_the_only_accepted_prefix(tmp_path: Path) -> None:
    """`case.` and `caseFacts.` are supported wrappers; nothing else may stand in front."""
    for wrapper in ("case", "caseFacts"):
        payload = {wrapper: {"injury": {"body_part": "shoulder"}}, **_SHOULDER_OPERATION}
        assert CODE not in _codes(_findings(tmp_path, payload)), wrapper

    for foreign in ("scenario", "exam", "medicalHistory", "priorInjury"):
        payload = {
            "injury": {"body_part": "right wrist"},
            foreign: {"injury": {"body_part": "shoulder"}},
            **_SHOULDER_OPERATION,
        }
        assert _codes(_findings(tmp_path, payload)) == [CODE], foreign


def test_a_self_describing_shape_is_still_namespace_scoped(tmp_path: Path) -> None:
    """A one-segment shape must not suffix-match its way into any ancestor.

    `injuredPart` names itself, but `medicalHistory.priorInjury.injuredPart` is a past
    injury — accepting it cleared a current contradiction that the equivalent
    `bodyPart` path correctly refused.
    """
    for extra in (
        {"medicalHistory": {"priorInjury": {"injuredPart": "shoulder"}}},
        {"medicalHistory": {"injury": {"site": "shoulder"}}},
        {"scenario": {"diagnostics": {"injuredPart": "shoulder"}}},
    ):
        payload = {"injury": {"body_part": "right wrist"}, **extra, **_SHOULDER_OPERATION}
        assert _codes(_findings(tmp_path, payload)) == [CODE], extra


def test_a_claim_promoted_inside_a_history_block_is_not_current_anatomy(tmp_path: Path) -> None:
    """A promoted claim names its own field, so only its container can scope it.

    This is the one path where shape matching cannot help — the claim's own path is the
    container, not an anatomy shape — so the historical classification has to carry it.
    """
    payload = {
        "injury": {"body_part": "right wrist"},
        "medicalHistory": {"claims": [{"field": "injured_part", "value": "shoulder"}]},
        **_SHOULDER_OPERATION,
    }

    assert _codes(_findings(tmp_path, payload)) == [CODE]

    # The same claim outside a history block is a current assertion.
    current = {
        "claims": [{"field": "injured_part", "value": "shoulder"}],
        **_SHOULDER_OPERATION,
    }
    assert CODE not in _codes(_findings(tmp_path, current))


def test_the_nearest_namespace_decides_not_any_namespace(tmp_path: Path) -> None:
    """Nesting order matters: the namespace closest to the code wins.

    An unordered scan let any current-care namespace anywhere reactivate a nested
    history block, so `currentEpisode.medicalHistory.priorSurgeries` read as current.
    """
    for historical in (
        {"currentEpisode": {"medicalHistory": {"priorSurgeries": [{"cptCode": "29827"}]}}},
        {"historyAndPhysical": {"pastSurgeries": [{"cptCode": "29827"}]}},
    ):
        payload = {"injury": {"body_part": "right wrist"}, **historical}
        assert CODE not in _codes(_findings(tmp_path, payload)), historical

    # And the reverse nesting stays current.
    payload = {
        "injury": {"body_part": "right wrist"},
        "medicalHistory": {"currentSurgery": {"cptCode": "29827"}},
    }
    assert _codes(_findings(tmp_path, payload)) == [CODE]


def test_every_historical_namespace_silences_an_operation(tmp_path: Path) -> None:
    """Each entry of the historical table, exercised."""
    checked = set()
    for namespace in sorted(HISTORICAL_NAMESPACES):
        payload = {
            "injury": {"body_part": "right wrist"},
            namespace: {"surgery": {"cptCode": "29827"}},
        }
        assert CODE not in _codes(_findings(tmp_path, payload)), namespace
        checked.add(namespace)

    assert checked == set(HISTORICAL_NAMESPACES)


def test_every_current_care_namespace_keeps_an_operation(tmp_path: Path) -> None:
    """Each entry of the current-care table, exercised."""
    checked = set()
    for namespace in sorted(CURRENT_CARE_NAMESPACES):
        payload = {
            "injury": {"body_part": "right wrist"},
            namespace: {"surgery": {"cptCode": "29827"}},
        }
        assert _codes(_findings(tmp_path, payload)) == [CODE], namespace
        checked.add(namespace)

    assert checked == set(CURRENT_CARE_NAMESPACES)


def test_every_historical_code_field_silences_an_operation(tmp_path: Path) -> None:
    """Each entry of the historical code-field table, exercised."""
    checked = set()
    for field in sorted(HISTORICAL_CODE_FIELDS):
        payload = {
            "injury": {"body_part": "right wrist"},
            "caseFacts": {"surgery": {"status": "performed", field: "29827"}},
        }
        assert CODE not in _codes(_findings(tmp_path, payload)), field
        checked.add(field)

    assert checked == set(HISTORICAL_CODE_FIELDS)


def test_every_cpt_table_entry_behaves_as_its_class_promises() -> None:
    """Behavioural pin on all four code tables, entry by entry.

    `test_every_table_entry_is_a_five_digit_code_naming_a_known_region` proves the rows
    are well formed; this proves each one actually decides something.
    """
    for code, region in sorted(OPERATIVE_CPT_ANATOMY.items()):
        mismatch = "shoulder" if region == "foot" else "foot"
        assert contradicts(code, frozenset({mismatch})), code
        assert not contradicts(code, frozenset({region})), code

    for code, regions in sorted(LOCALIZABLE_UNLISTED_CPT_ANATOMY.items()):
        mismatch = next(r for r in ("foot", "shoulder", "hand") if r not in regions)
        assert contradicts(code, frozenset({mismatch})), code
        for region in regions:
            assert not contradicts(code, frozenset({region})), (code, region)

    for code in sorted(NON_OPERATIVE_CPT_CODES | NONLOCALIZABLE_UNLISTED_CPT_CODES):
        assert not contradicts(code, frozenset({"wrist"})), code
        assert not contradicts(code, frozenset({"shoulder"})), code


def test_current_care_records_are_not_historical(tmp_path: Path) -> None:
    """`priorAuthorization` and `historyAndPhysical` read historical word by word but
    describe care being requested or given now — the classification is by namespace."""
    for extra in (
        {"priorAuthorization": {"surgery": {"cptCode": "29827"}}},
        {"historyAndPhysical": {"currentSurgery": {"cptCode": "29827"}}},
    ):
        findings = _findings(tmp_path, {"injury": {"body_part": "right wrist"}, **extra})
        assert _codes(findings) == [CODE], extra


def test_current_care_wins_where_both_classifications_appear(tmp_path: Path) -> None:
    """A surgery labelled current inside a history block is this case's operation.

    Without this the current-care table is dead weight: whole-segment matching already
    keeps `priorAuthorization` out of the historical set, so only a genuine overlap
    exercises the override.
    """
    findings = _findings(
        tmp_path,
        {
            "injury": {"body_part": "right wrist"},
            "medicalHistory": {"currentSurgery": {"cptCode": "29827"}},
        },
    )

    assert _codes(findings) == [CODE]

    # And the same block without the current-care marker stays silent.
    historical = _findings(
        tmp_path,
        {
            "injury": {"body_part": "right wrist"},
            "medicalHistory": {"priorSurgeries": [{"cptCode": "29827"}]},
        },
    )
    assert CODE not in _codes(historical)


def test_a_non_injury_region_field_is_not_an_injured_part(tmp_path: Path) -> None:
    """An examined or serviced region is not a claim that the region was injured."""
    for extra in (
        {"diagnostic": {"examinedRegion": "shoulder"}},
        {"provider": {"serviceRegion": "shoulder"}},
        {"exam": {"site": "shoulder"}},
        {"condition": "shoulder"},
    ):
        findings = _findings(
            tmp_path,
            {
                "injury": {"body_part": "right wrist"},
                **extra,
                "caseFacts": {"surgery": {"status": "performed", "cptCode": "29827"}},
            },
        )
        assert _codes(findings) == [CODE], extra


def test_every_structured_injured_part_shape_is_recognized(tmp_path: Path) -> None:
    """The allowlist must cover every shape a real record uses, including the seed's."""
    for payload in (
        {"injuredPart": "shoulder"},
        {"injurySite": "shoulder"},
        {"injury": {"bodyPart": "shoulder"}},
        {"injury": {"body_parts": ["shoulder"]}},
        {"injury": {"body_parts": [{"part": "shoulder"}]}},
    ):
        findings = _findings(
            tmp_path,
            {**payload, "caseFacts": {"surgery": {"status": "performed", "cptCode": "29827"}}},
        )
        assert CODE not in _codes(findings), payload


def test_a_historical_operation_is_not_this_cases_operation(tmp_path: Path) -> None:
    """Prior surgeries on other anatomy are legitimate content, not a contradiction.

    The medical-history ledger will make them routine, so a detector that read them
    as this case's operation would fire on every case that records a patient's past.
    """
    findings = _findings(
        tmp_path,
        {
            "injury": {"body_part": "right wrist"},
            "caseFacts": {
                "surgery": {"status": "performed", "cptCode": "64721", "priorCptCode": "29827"}
            },
        },
    )
    assert CODE not in _codes(findings)

    findings = _findings(
        tmp_path,
        {
            "injury": {"body_part": "right wrist"},
            "caseFacts": {"surgery": {"status": "performed", "cptCode": "64721"}},
            "medicalHistory": {"priorSurgeries": [{"cptCode": "29827"}]},
        },
    )
    assert CODE not in _codes(findings)

    # The control: a current-surgery contradiction must still fire.
    findings = _findings(
        tmp_path,
        {
            "injury": {"body_part": "right wrist"},
            "caseFacts": {"surgery": {"status": "performed", "cptCode": "29827"}},
        },
    )
    assert _codes(findings) == [CODE]


def test_an_unrelated_uncoded_claim_does_not_suppress_an_operation(tmp_path: Path) -> None:
    """Each promoted claim is its own record; one claim's flag is not another claim's."""
    findings = _findings(
        tmp_path,
        {
            "claims": [
                {"field": "injury_body_part", "value": "right wrist"},
                {"field": "surgery_cpt_code", "value": "29827"},
                {"field": "uncoded", "value": True},
            ]
        },
    )

    assert _codes(findings) == [CODE]


def test_a_localizable_unlisted_operation_is_flagged(tmp_path: Path) -> None:
    """An unlisted shoulder procedure on a wrist case is still the wrong body area."""
    findings = _findings(
        tmp_path,
        {
            "injury": {"body_part": "right wrist"},
            "caseFacts": {"surgery": {"status": "performed", "cptCode": "23929"}},
        },
    )

    assert _codes(findings) == [CODE]
    assert "shoulder" in findings[0].message


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
    """An error-severity finding is what turns a corpus regression into a red gate.

    Both exit codes are asserted exactly: "any nonzero" would be satisfied by a crash,
    and a clean run that never asserts success cannot catch a detector that fires on
    everything.
    """
    result = CliRunner().invoke(
        cli,
        [
            "validate",
            str(FIXTURES / "anatomy_intake_wrist.json"),
            str(FIXTURES / "anatomy_manifest_shoulder.json"),
        ],
    )

    assert result.exit_code == 1, result.output
    payload = json.loads(result.output)
    contradictions = [item for item in payload["findings"] if item["code"] == CODE]
    assert len(contradictions) == 1
    assert contradictions[0]["severity"] == "error"
    assert contradictions[0]["category"] == "medical"
    assert contradictions[0]["factIds"]

    clean = CliRunner().invoke(
        cli,
        [
            "validate",
            str(FIXTURES / "anatomy_intake_wrist.json"),
            str(FIXTURES / "anatomy_manifest_wrist.json"),
        ],
    )
    assert clean.exit_code == 0, clean.output
    clean_payload = json.loads(clean.output)
    assert isinstance(clean_payload["findings"], list)
    assert CODE not in [item["code"] for item in clean_payload["findings"]]
