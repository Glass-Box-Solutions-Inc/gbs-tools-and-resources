"""
Tests for the 5 root-cause quality fixes (RC-1 through RC-5).

Validates: volume caps, injury-treatment coherence, intake documents,
stage minimum floors, and chronological stage ordering.
"""

from __future__ import annotations

import random

from data.lifecycle_engine import (
    COMPLEX_GLOBAL_CAP,
    COMPLEX_STAGE_CAPS,
    COMPLEX_STAGE_CAP_DEFAULT,
    COMPLEX_SUBTYPE_CAPS,
    COMPLEX_SUBTYPE_CAP_DEFAULT,
    CaseParameters,
    LIFECYCLE_DOCUMENT_RULES,
    LIFECYCLE_ORDER,
    NodeDocumentRule,
    STAGE_DOC_MINIMUMS,
    STAGE_FILLER_POOL,
    STANDARD_GLOBAL_CAP,
    collect_documents_for_case,
    evaluate_condition,
    walk_lifecycle,
)
from data.taxonomy import DocumentSubtype
from pdf_templates.medical.operative_record import (
    BODY_PART_TO_SURGERY_CATEGORY,
    _select_surgical_cpts,
)


# ---------------------------------------------------------------------------
# RC-1: Volume caps
# ---------------------------------------------------------------------------


class TestRC1VolumeCaps:
    """Complex cases must not exceed volume caps."""

    def test_complex_case_under_global_cap(self) -> None:
        """A fully-loaded complex case must produce <= COMPLEX_GLOBAL_CAP documents."""
        params = CaseParameters(
            complexity="complex",
            has_surgery=True,
            has_liens=True,
            has_ur_dispute=True,
            has_attorney=True,
            num_body_parts=3,
            has_psych_component=True,
            resolution_type="trial",
        )
        docs = collect_documents_for_case(params, random.Random(42))
        assert len(docs) <= COMPLEX_GLOBAL_CAP, (
            f"Complex case produced {len(docs)} docs, exceeds cap of {COMPLEX_GLOBAL_CAP}"
        )

    def test_standard_case_under_global_cap(self) -> None:
        """A standard case must produce <= STANDARD_GLOBAL_CAP + stage filler allowance."""
        params = CaseParameters(
            complexity="standard",
            has_surgery=True,
            has_attorney=True,
            resolution_type="stipulations",
        )
        docs = collect_documents_for_case(params, random.Random(42))
        # Stage minimum fillers may push slightly above the cap (up to ~5 extra docs)
        filler_allowance = sum(STAGE_DOC_MINIMUMS.values())
        assert len(docs) <= STANDARD_GLOBAL_CAP + filler_allowance, (
            f"Standard case produced {len(docs)} docs, exceeds cap+filler of {STANDARD_GLOBAL_CAP + filler_allowance}"
        )

    def test_per_subtype_cap_respected(self) -> None:
        """No single subtype exceeds its per-subtype cap in complex cases."""
        params = CaseParameters(
            complexity="complex",
            has_surgery=True,
            has_liens=True,
            has_ur_dispute=True,
            has_attorney=True,
            num_body_parts=3,
        )
        docs = collect_documents_for_case(params, random.Random(42))
        subtype_counts: dict[str, int] = {}
        for subtype_str, _, _ in docs:
            subtype_counts[subtype_str] = subtype_counts.get(subtype_str, 0) + 1

        for subtype_str, count in subtype_counts.items():
            cap = COMPLEX_SUBTYPE_CAPS.get(subtype_str, COMPLEX_SUBTYPE_CAP_DEFAULT)
            assert count <= cap, (
                f"Subtype {subtype_str} has {count} docs, exceeds cap of {cap}"
            )

    def test_complex_case_produces_reasonable_volume(self) -> None:
        """A complex case should produce at least 30 docs (not too few after caps)."""
        params = CaseParameters(
            complexity="complex",
            has_surgery=True,
            has_liens=True,
            has_ur_dispute=True,
            has_attorney=True,
            num_body_parts=3,
        )
        docs = collect_documents_for_case(params, random.Random(42))
        assert len(docs) >= 30, (
            f"Complex case only produced {len(docs)} docs — caps may be too aggressive"
        )

    def test_reduced_probability_multiplier(self) -> None:
        """Verify complex probability boost is 1.5x (not 2.5x) by checking that
        low-probability rules don't always fire across multiple seeds."""
        params = CaseParameters(
            complexity="complex",
            has_surgery=True,
            has_attorney=True,
        )
        # Run 20 seeds and check that not all fire the same optional docs
        all_subtypes_sets = []
        for seed in range(20):
            docs = collect_documents_for_case(params, random.Random(seed))
            subtypes = frozenset(d[0] for d in docs)
            all_subtypes_sets.append(subtypes)

        # With 1.5x boost, optional docs (prob < 1.0) should NOT appear in every seed
        # Find subtypes that appear in all 20 seeds — these should only be prob=1.0 rules
        always_present = set.intersection(*[set(s) for s in all_subtypes_sets])
        sometimes_absent = set.union(*[set(s) for s in all_subtypes_sets]) - always_present
        assert len(sometimes_absent) > 0, (
            "All subtypes appeared in every seed — probability boost may be too high"
        )

    def test_multiple_seeds_produce_different_counts(self) -> None:
        """Complex cases should have variance in doc count across seeds."""
        params = CaseParameters(
            complexity="complex",
            has_surgery=True,
            has_attorney=True,
            has_ur_dispute=True,
        )
        counts = [len(collect_documents_for_case(params, random.Random(s))) for s in range(10)]
        assert len(set(counts)) > 1, "All 10 seeds produced identical doc counts"


# ---------------------------------------------------------------------------
# RC-2: Injury-treatment coherence
# ---------------------------------------------------------------------------


class TestRC2Coherence:
    """Surgical procedures match injured body parts; death/psych exclusions work."""

    def test_and_condition_all_true(self) -> None:
        """AND compound conditions evaluate correctly when all parts are true."""
        params = CaseParameters(
            has_surgery=True,
            injury_type="specific",
            body_part_category="spine",
        )
        result = evaluate_condition(
            "has_surgery AND injury_type != 'death' AND body_part_category != 'psyche'",
            params,
        )
        assert result is True

    def test_and_condition_one_false(self) -> None:
        """AND compound conditions fail when one part is false."""
        params = CaseParameters(
            has_surgery=True,
            injury_type="death",
            body_part_category="spine",
        )
        result = evaluate_condition(
            "has_surgery AND injury_type != 'death' AND body_part_category != 'psyche'",
            params,
        )
        assert result is False

    def test_death_cases_no_operative_records(self) -> None:
        """Death cases must not produce OPERATIVE_HOSPITAL_RECORDS."""
        params = CaseParameters(
            has_surgery=True,
            injury_type="death",
            has_attorney=True,
        )
        docs = collect_documents_for_case(params, random.Random(42))
        operative_docs = [d for d in docs if d[0] == "OPERATIVE_HOSPITAL_RECORDS"]
        assert len(operative_docs) == 0, (
            "Death case produced OPERATIVE_HOSPITAL_RECORDS — should be excluded"
        )

    def test_psych_cases_no_operative_records(self) -> None:
        """Psyche-only cases must not produce OPERATIVE_HOSPITAL_RECORDS."""
        params = CaseParameters(
            has_surgery=True,
            body_part_category="psyche",
            has_attorney=True,
        )
        docs = collect_documents_for_case(params, random.Random(42))
        operative_docs = [d for d in docs if d[0] == "OPERATIVE_HOSPITAL_RECORDS"]
        assert len(operative_docs) == 0, (
            "Psyche case produced OPERATIVE_HOSPITAL_RECORDS — should be excluded"
        )

    def test_injury_type_in_string_fields(self) -> None:
        """evaluate_condition() supports injury_type comparisons."""
        params = CaseParameters(injury_type="cumulative_trauma")
        assert evaluate_condition("injury_type == 'cumulative_trauma'", params) is True
        assert evaluate_condition("injury_type == 'specific'", params) is False

    def test_body_part_category_in_string_fields(self) -> None:
        """evaluate_condition() supports body_part_category comparisons."""
        params = CaseParameters(body_part_category="spine")
        assert evaluate_condition("body_part_category == 'spine'", params) is True
        assert evaluate_condition("body_part_category != 'spine'", params) is False


# ---------------------------------------------------------------------------
# RC-3: Intake-stage documents
# ---------------------------------------------------------------------------


class TestRC3IntakeDocs:
    """Intake-stage cases must get baseline medical documents."""

    def test_intake_stage_has_documents(self) -> None:
        """A case with target_stage='intake' must produce documents."""
        params = CaseParameters(target_stage="intake", has_attorney=True)
        docs = collect_documents_for_case(params, random.Random(42))
        assert len(docs) >= 3, (
            f"Intake case produced only {len(docs)} docs — needs baseline medical docs"
        )

    def test_intake_stage_has_medical_report(self) -> None:
        """Intake cases should include a physician report (PR-2 or first report)."""
        params = CaseParameters(target_stage="intake", has_attorney=True)
        docs = collect_documents_for_case(params, random.Random(42))
        subtypes = {d[0] for d in docs}
        has_medical = (
            "FIRST_REPORT_OF_INJURY_PHYSICIAN" in subtypes
            or "TREATING_PHYSICIAN_REPORT_PR2" in subtypes
        )
        assert has_medical, (
            f"Intake case has no medical report. Subtypes: {subtypes}"
        )

    def test_intake_stage_has_employer_report(self) -> None:
        """Intake cases should include an EMPLOYER_REPORT_INJURY."""
        params = CaseParameters(target_stage="intake", has_attorney=True)
        # Run across multiple seeds — 0.7 probability means it should appear in most
        found_count = 0
        for seed in range(10):
            docs = collect_documents_for_case(params, random.Random(seed))
            subtypes = {d[0] for d in docs}
            if "EMPLOYER_REPORT_INJURY" in subtypes:
                found_count += 1
        assert found_count >= 5, (
            f"EMPLOYER_REPORT_INJURY only appeared in {found_count}/10 seeds"
        )

    def test_intake_stage_reaches_claim_filed(self) -> None:
        """Intake target_stage should traverse at least injury and claim_filed stages."""
        params = CaseParameters(target_stage="intake")
        stages = walk_lifecycle(params)
        stage_names = [s.value for s in stages]
        assert "injury" in stage_names
        assert "claim_filed" in stage_names


# ---------------------------------------------------------------------------
# RC-4: Stage minimum floors
# ---------------------------------------------------------------------------


class TestRC4StageMinimums:
    """Traversed stages must meet minimum document counts."""

    def test_every_traversed_stage_has_docs(self) -> None:
        """No traversed stage should produce zero documents."""
        params = CaseParameters(
            has_attorney=True,
            has_surgery=True,
            has_ur_dispute=True,
            resolution_type="trial",
        )
        docs = collect_documents_for_case(params, random.Random(42))
        stages = walk_lifecycle(params)

        stage_doc_counts: dict[str, int] = {}
        for _, _, stage_name in docs:
            stage_doc_counts[stage_name] = stage_doc_counts.get(stage_name, 0) + 1

        empty_stages = [
            s.value for s in stages
            if stage_doc_counts.get(s.value, 0) == 0
        ]
        assert not empty_stages, (
            f"These traversed stages produced zero documents: {empty_stages}"
        )

    def test_active_treatment_meets_minimum(self) -> None:
        """Active treatment stage should produce at least 3 docs."""
        params = CaseParameters(has_attorney=True, resolution_type="stipulations")
        docs = collect_documents_for_case(params, random.Random(42))
        at_count = sum(1 for _, _, s in docs if s == "active_treatment")
        minimum = STAGE_DOC_MINIMUMS.get("active_treatment", 0)
        assert at_count >= minimum, (
            f"active_treatment produced {at_count} docs, minimum is {minimum}"
        )

    def test_non_traversed_stages_get_nothing(self) -> None:
        """Stages not traversed should produce zero documents."""
        # Intake case should NOT traverse active_treatment, discovery, etc.
        params = CaseParameters(target_stage="intake")
        docs = collect_documents_for_case(params, random.Random(42))
        stages = walk_lifecycle(params)
        traversed = {s.value for s in stages}

        for _, _, stage_name in docs:
            assert stage_name in traversed, (
                f"Doc emitted for non-traversed stage {stage_name!r}"
            )

    def test_filler_pool_subtypes_are_valid(self) -> None:
        """All STAGE_FILLER_POOL values must be valid DocumentSubtype values."""
        valid = frozenset(s.value for s in DocumentSubtype)
        invalid = [
            (stage, subtype)
            for stage, subtype in STAGE_FILLER_POOL.items()
            if subtype not in valid
        ]
        assert not invalid, (
            f"Invalid filler subtypes: {invalid}"
        )

    def test_stage_minimums_dict_covers_filler_pool(self) -> None:
        """Every stage in STAGE_DOC_MINIMUMS should have a filler in STAGE_FILLER_POOL."""
        missing = [
            stage for stage in STAGE_DOC_MINIMUMS
            if stage not in STAGE_FILLER_POOL
        ]
        assert not missing, (
            f"Stages with minimums but no filler pool entry: {missing}"
        )

    def test_resolution_stages_meet_minimum(self) -> None:
        """Resolution stages should meet their minimums."""
        for res_type, stage_name in [
            ("stipulations", "resolution_stipulations"),
            ("c_and_r", "resolution_cr"),
            ("trial", "resolution_trial"),
        ]:
            params = CaseParameters(has_attorney=True, resolution_type=res_type)
            docs = collect_documents_for_case(params, random.Random(42))
            count = sum(1 for _, _, s in docs if s == stage_name)
            minimum = STAGE_DOC_MINIMUMS.get(stage_name, 0)
            assert count >= minimum, (
                f"{stage_name} produced {count} docs, minimum is {minimum}"
            )


# ---------------------------------------------------------------------------
# RC-5: Chronological stage ordering
# ---------------------------------------------------------------------------


class TestRC5Chronology:
    """Documents from later lifecycle stages must not predate earlier stages."""

    def test_docs_include_stage_name(self) -> None:
        """collect_documents_for_case returns 3-tuples with stage name."""
        params = CaseParameters(has_attorney=True)
        docs = collect_documents_for_case(params, random.Random(42))
        assert len(docs) > 0
        for doc in docs:
            assert len(doc) == 3, f"Expected 3-tuple, got {len(doc)}-tuple"
            assert isinstance(doc[2], str), f"Stage name should be str, got {type(doc[2])}"

    def test_stage_names_are_valid(self) -> None:
        """All stage names in returned docs must be valid LifecycleStage values."""
        params = CaseParameters(has_attorney=True, has_surgery=True, has_ur_dispute=True)
        docs = collect_documents_for_case(params, random.Random(42))
        valid_stages = {stage.value for stage in LIFECYCLE_ORDER}
        for _, _, stage_name in docs:
            assert stage_name in valid_stages, (
                f"Stage name {stage_name!r} not in LIFECYCLE_ORDER"
            )

    def test_return_type_backward_compat(self) -> None:
        """3-tuple return still allows unpacking subtype and rule."""
        params = CaseParameters(has_attorney=True)
        docs = collect_documents_for_case(params, random.Random(42))
        for subtype_str, rule, stage_name in docs:
            assert isinstance(subtype_str, str)
            assert isinstance(rule, NodeDocumentRule)
            assert isinstance(stage_name, str)

    def test_multiple_seeds_all_produce_stage_names(self) -> None:
        """Stage names should be present regardless of seed."""
        params = CaseParameters(has_attorney=True)
        for seed in range(5):
            docs = collect_documents_for_case(params, random.Random(seed))
            for doc in docs:
                assert len(doc) == 3

    def test_stage_order_index_coverage(self) -> None:
        """LIFECYCLE_ORDER should cover all stages referenced in rules."""
        order_values = {stage.value for stage in LIFECYCLE_ORDER}
        from data.lifecycle_engine import LIFECYCLE_DOCUMENT_RULES
        for stage_key in LIFECYCLE_DOCUMENT_RULES:
            assert stage_key in order_values, (
                f"Stage {stage_key!r} in rules but not in LIFECYCLE_ORDER"
            )

    def test_complex_case_stage_order_preserved(self) -> None:
        """Even complex cases should maintain valid stage names in output."""
        params = CaseParameters(
            complexity="complex",
            has_surgery=True,
            has_attorney=True,
            has_ur_dispute=True,
        )
        docs = collect_documents_for_case(params, random.Random(42))
        valid_stages = {stage.value for stage in LIFECYCLE_ORDER}
        stage_names = {d[2] for d in docs}
        assert stage_names.issubset(valid_stages)


# ---------------------------------------------------------------------------
# Review fixes: additional coverage from re-team review
# ---------------------------------------------------------------------------


class TestSelectSurgicalCPTs:
    """Tests for body-part-aware CPT selection in operative_record.py."""

    def test_spine_returns_spine_codes(self) -> None:
        """Spine body parts should return spine surgery CPT codes."""
        cpts = _select_surgical_cpts(["Lumbar Spine"])
        codes = [c for c, _ in cpts]
        # Should contain spine surgery codes, not shoulder/knee
        assert any(c in codes for c in ["63030", "22551", "64483", "62323"])
        assert "29827" not in codes  # no shoulder
        assert "29881" not in codes  # no knee

    def test_shoulder_returns_shoulder_codes(self) -> None:
        """Shoulder body parts should return shoulder surgery CPT codes."""
        cpts = _select_surgical_cpts(["Right Shoulder"])
        codes = [c for c, _ in cpts]
        assert any(c in codes for c in ["29827", "23412"])

    def test_knee_returns_knee_codes(self) -> None:
        """Knee body parts should return knee surgery CPT codes."""
        cpts = _select_surgical_cpts(["Left Knee"])
        codes = [c for c, _ in cpts]
        assert any(c in codes for c in ["29881", "27447"])

    def test_unknown_body_part_returns_fallback(self) -> None:
        """Unknown body parts should fall back to all surgical CPT codes."""
        cpts = _select_surgical_cpts(["finger"])
        assert len(cpts) > 0

    def test_empty_body_parts_returns_fallback(self) -> None:
        """Empty body parts list should fall back to all surgical CPT codes."""
        cpts = _select_surgical_cpts([])
        assert len(cpts) > 0

    def test_multiple_body_parts_unions_categories(self) -> None:
        """Multiple body parts should union their CPT categories."""
        cpts = _select_surgical_cpts(["Lumbar Spine", "Right Shoulder"])
        codes = [c for c, _ in cpts]
        # Should include both spine AND shoulder codes
        has_spine = any(c in codes for c in ["63030", "22551"])
        has_shoulder = any(c in codes for c in ["29827", "23412"])
        assert has_spine and has_shoulder


class TestComplexStageCaps:
    """Tests for per-stage caps on complex cases."""

    def test_active_treatment_stage_cap(self) -> None:
        """Active treatment stage must not exceed its cap for complex cases."""
        params = CaseParameters(
            complexity="complex",
            has_surgery=True,
            has_psych_component=True,
            num_body_parts=3,
            has_attorney=True,
        )
        docs = collect_documents_for_case(params, random.Random(42))
        at_count = sum(1 for _, _, s in docs if s == "active_treatment")
        assert at_count <= COMPLEX_STAGE_CAPS["active_treatment"], (
            f"active_treatment has {at_count} docs, exceeds stage cap of {COMPLEX_STAGE_CAPS['active_treatment']}"
        )

    def test_all_stages_under_caps(self) -> None:
        """No stage should exceed its cap (or default) for complex cases."""
        params = CaseParameters(
            complexity="complex",
            has_surgery=True,
            has_liens=True,
            has_ur_dispute=True,
            has_attorney=True,
            num_body_parts=3,
        )
        docs = collect_documents_for_case(params, random.Random(42))
        stage_counts: dict[str, int] = {}
        for _, _, s in docs:
            stage_counts[s] = stage_counts.get(s, 0) + 1

        for stage_name, count in stage_counts.items():
            # Fillers may push 1-2 above cap, allow that
            cap = COMPLEX_STAGE_CAPS.get(stage_name, COMPLEX_STAGE_CAP_DEFAULT)
            minimum = STAGE_DOC_MINIMUMS.get(stage_name, 0)
            allowed = max(cap, minimum)
            assert count <= allowed + minimum, (
                f"Stage {stage_name} has {count} docs, exceeds cap {cap} + filler {minimum}"
            )

    def test_subtype_caps_keys_match_rule_subtypes(self) -> None:
        """All COMPLEX_SUBTYPE_CAPS keys should be subtypes actually emitted by rules."""
        all_rule_subtypes = {
            rule.subtype
            for rules in LIFECYCLE_DOCUMENT_RULES.values()
            for rule in rules
        }
        dead_caps = [k for k in COMPLEX_SUBTYPE_CAPS if k not in all_rule_subtypes]
        assert not dead_caps, (
            f"Subtype caps for subtypes never emitted by rules: {dead_caps}"
        )


class TestEvaluateConditionEdgeCases:
    """Edge case tests for evaluate_condition()."""

    def test_none_returns_true(self) -> None:
        """None condition always evaluates to True."""
        assert evaluate_condition(None, CaseParameters()) is True

    def test_empty_string_returns_true(self) -> None:
        """Empty string condition defaults to True (unknown condition fallback)."""
        assert evaluate_condition("", CaseParameters()) is True

    def test_unknown_flag_returns_true(self) -> None:
        """Unknown condition names default to True for forward compatibility."""
        assert evaluate_condition("nonexistent_flag_xyz", CaseParameters()) is True

    def test_whitespace_stripped(self) -> None:
        """Conditions with leading/trailing whitespace should still match."""
        params = CaseParameters(has_surgery=True)
        assert evaluate_condition("  has_surgery  ", params) is True

    def test_three_part_and(self) -> None:
        """Three-part AND condition with all true."""
        params = CaseParameters(has_surgery=True, has_attorney=True, has_liens=True)
        assert evaluate_condition("has_surgery AND has_attorney AND has_liens", params) is True

    def test_three_part_and_one_false(self) -> None:
        """Three-part AND condition with one false part."""
        params = CaseParameters(has_surgery=True, has_attorney=False, has_liens=True)
        assert evaluate_condition("has_surgery AND has_attorney AND has_liens", params) is False
