"""Document-control precedence matrix (ISC-22..29). No substrate required.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

from typing import Any

import pytest

from wc_caseload_engine.doc_controls import (
    TRACK_CORE,
    TRACK_FILLER,
    TRACK_LIEN,
    TRACK_SUPPORTING,
    DocumentCandidate,
    resolve_document_controls,
)
from wc_caseload_engine.seeds import DocumentControls

# A miniature lifecycle proposal: two parent types, three tracks, mixed priority.
PARENTS: dict[str, str] = {
    "APPLICATION_FOR_ADJUDICATION": "PLEADINGS_FILINGS",
    "DECLARATION_OF_READINESS": "PLEADINGS_FILINGS",
    "PROOF_OF_SERVICE": "PLEADINGS_FILINGS",
    "PTP_PR2_PROGRESS_REPORT": "MEDICAL_CLINICAL",
    "MRI_REPORT": "MEDICAL_CLINICAL",
    "DEPOSITION_TRANSCRIPT": "DISCOVERY",
    "NOTICE_OF_LIEN_FILING": "LIENS",
    # Known to the taxonomy, proposed by nothing in `candidates()` — the shape a
    # `min` on an unproposed type needs, with an override able to supply it.
    "MEDICAL_BILL": "BILLING",
}


def parent_of(subtype: str) -> str | None:
    return PARENTS.get(subtype)


def candidates() -> list[DocumentCandidate]:
    return [
        DocumentCandidate("APPLICATION_FOR_ADJUDICATION", priority=0, track=TRACK_CORE),
        DocumentCandidate("DECLARATION_OF_READINESS", priority=20, track=TRACK_CORE),
        DocumentCandidate("PROOF_OF_SERVICE", priority=80, track=TRACK_FILLER, count=4),
        DocumentCandidate("PTP_PR2_PROGRESS_REPORT", priority=30, track=TRACK_CORE, count=6),
        DocumentCandidate("MRI_REPORT", priority=60, track=TRACK_SUPPORTING, count=2),
        DocumentCandidate("DEPOSITION_TRANSCRIPT", priority=40, track=TRACK_CORE),
        DocumentCandidate("NOTICE_OF_LIEN_FILING", priority=10, track=TRACK_LIEN, count=2),
    ]


def resolve(controls: dict[str, Any], **kwargs: Any) -> Any:
    return resolve_document_controls(
        candidates(),
        DocumentControls.model_validate(controls),
        parent_type_of=parent_of,
        **kwargs,
    )


BASELINE_TOTAL = 17


# 1 — lifecycle defaults pass straight through
def test_no_controls_emits_the_lifecycle_defaults() -> None:
    result = resolve({})
    assert result.total == BASELINE_TOTAL
    assert result.count_for("PROOF_OF_SERVICE") == 4
    assert result.warnings == ()


# 2 — include_only whitelist by subtype and by parent type (ISC-22)
def test_include_only_restricts_to_named_subtypes_and_types() -> None:
    result = resolve({"include_only": ["MEDICAL_CLINICAL", "DEPOSITION_TRANSCRIPT"]})
    assert set(result.counts()) == {
        "PTP_PR2_PROGRESS_REPORT",
        "MRI_REPORT",
        "DEPOSITION_TRANSCRIPT",
    }
    assert result.dropped["APPLICATION_FOR_ADJUDICATION"] == "not in documents.include_only"


# 3 — exclude blacklist (ISC-23)
def test_exclude_suppresses_named_subtypes_and_types() -> None:
    result = resolve({"exclude": ["PLEADINGS_FILINGS", "MRI_REPORT"]})
    assert "APPLICATION_FOR_ADJUDICATION" not in result.counts()
    assert "PROOF_OF_SERVICE" not in result.counts()
    assert "MRI_REPORT" not in result.counts()
    assert result.count_for("PTP_PR2_PROGRESS_REPORT") == 6


# 4 — exact per-subtype count (ISC-24)
def test_subtype_override_sets_an_exact_count() -> None:
    result = resolve({"overrides": [{"subtype": "DEPOSITION_TRANSCRIPT", "count": 3}]})
    assert result.count_for("DEPOSITION_TRANSCRIPT") == 3
    assert result.total == BASELINE_TOTAL + 2


def test_subtype_override_to_zero_removes_the_subtype() -> None:
    result = resolve({"overrides": [{"subtype": "PROOF_OF_SERVICE", "count": 0}]})
    assert result.count_for("PROOF_OF_SERVICE") == 0
    assert "PROOF_OF_SERVICE" not in result.counts()


# 5 — per-parent-type max and min (ISC-25)
def test_type_max_trims_the_type_lowest_priority_first() -> None:
    result = resolve({"overrides": [{"type": "MEDICAL_CLINICAL", "max": 5}]})
    assert result.type_totals()["MEDICAL_CLINICAL"] == 5
    # MRI_REPORT is supporting/priority-60, so it gives way before the PR-2s.
    assert result.count_for("MRI_REPORT") == 0
    assert result.count_for("PTP_PR2_PROGRESS_REPORT") == 5


def test_type_min_grows_the_type_most_essential_first() -> None:
    result = resolve({"overrides": [{"type": "DISCOVERY", "min": 4}]})
    assert result.type_totals()["DISCOVERY"] == 4
    assert result.count_for("DEPOSITION_TRANSCRIPT") == 4


def test_type_min_without_candidates_warns_instead_of_inventing() -> None:
    result = resolve({"overrides": [{"type": "INVESTIGATION", "min": 3}]})
    assert result.total == BASELINE_TOTAL
    assert any("INVESTIGATION" in warning for warning in result.warnings)


# 6 — global cap (ISC-26)
def test_global_cap_trims_filler_before_core() -> None:
    result = resolve({"global_cap": 14})
    assert result.total == 14
    assert result.count_for("PROOF_OF_SERVICE") == 1  # filler absorbs all 3 cuts
    assert result.count_for("APPLICATION_FOR_ADJUDICATION") == 1
    assert result.count_for("NOTICE_OF_LIEN_FILING") == 2


def test_global_cap_falls_through_to_supporting_then_core() -> None:
    result = resolve({"global_cap": 8})
    assert result.total == 8
    assert result.count_for("PROOF_OF_SERVICE") == 0  # filler drained first
    assert result.count_for("MRI_REPORT") == 0  # then supporting
    assert result.count_for("NOTICE_OF_LIEN_FILING") == 2  # lien track survives


def test_global_cap_above_the_plan_changes_nothing() -> None:
    assert resolve({"global_cap": 500}).total == BASELINE_TOTAL


# 7 — precedence: subtype override beats exclude (ISC-28/29)
def test_subtype_override_beats_exclude_and_warns() -> None:
    result = resolve(
        {
            "exclude": ["DISCOVERY"],
            "overrides": [{"subtype": "DEPOSITION_TRANSCRIPT", "count": 2}],
        }
    )
    assert result.count_for("DEPOSITION_TRANSCRIPT") == 2
    assert "DEPOSITION_TRANSCRIPT" in result.forced_subtypes()
    assert any("documents.exclude" in w for w in result.warnings)


# 8 — precedence: subtype override beats include_only
def test_subtype_override_beats_include_only() -> None:
    result = resolve(
        {
            "include_only": ["MEDICAL_CLINICAL"],
            "overrides": [{"subtype": "DEPOSITION_TRANSCRIPT", "count": 1}],
        }
    )
    assert result.count_for("DEPOSITION_TRANSCRIPT") == 1
    assert result.count_for("PTP_PR2_PROGRESS_REPORT") == 6
    assert "APPLICATION_FOR_ADJUDICATION" not in result.counts()


# 9 — precedence: subtype override beats a per-type bound
def test_subtype_override_beats_type_max() -> None:
    result = resolve(
        {
            "overrides": [
                {"type": "MEDICAL_CLINICAL", "max": 3},
                {"subtype": "PTP_PR2_PROGRESS_REPORT", "count": 9},
            ]
        }
    )
    assert result.count_for("PTP_PR2_PROGRESS_REPORT") == 9
    assert result.type_totals()["MEDICAL_CLINICAL"] == 9


# 10 — precedence: subtype override beats the global cap
def test_subtype_override_is_never_trimmed_by_the_cap() -> None:
    result = resolve(
        {"global_cap": 6, "overrides": [{"subtype": "PROOF_OF_SERVICE", "count": 6}]}
    )
    assert result.count_for("PROOF_OF_SERVICE") == 6
    assert result.total == 6


def test_cap_below_pinned_overrides_warns_and_keeps_the_overrides() -> None:
    result = resolve(
        {"global_cap": 2, "overrides": [{"subtype": "PROOF_OF_SERVICE", "count": 6}]}
    )
    assert result.count_for("PROOF_OF_SERVICE") == 6
    assert result.total == 6
    assert any("cannot be met" in warning for warning in result.warnings)


# 11 — lifecycle-invalid forced subtype still emits, loudly (ISC-29)
def test_lifecycle_invalid_subtype_is_emitted_with_a_warning() -> None:
    warnings: list[dict[str, Any]] = []

    class _Recorder:
        def warning(self, event: str, **kwargs: Any) -> None:
            warnings.append({"event": event, **kwargs})

    result = resolve(
        {"overrides": [{"subtype": "SURVEILLANCE_REPORT", "count": 2}]},
        logger=_Recorder(),
    )
    assert result.count_for("SURVEILLANCE_REPORT") == 2
    assert "SURVEILLANCE_REPORT" in result.forced_subtypes()
    assert warnings[0]["event"] == "doc_controls.forced_subtype"
    assert warnings[0]["subtype"] == "SURVEILLANCE_REPORT"
    assert any("never emits it" in warning for warning in result.warnings)


# 12 — full composition: whitelist + type bound + override + cap
def test_full_control_stack_resolves_deterministically() -> None:
    controls = {
        "include_only": ["MEDICAL_CLINICAL", "PLEADINGS_FILINGS"],
        "exclude": ["PROOF_OF_SERVICE"],
        "overrides": [
            {"type": "MEDICAL_CLINICAL", "max": 4},
            {"subtype": "DEPOSITION_TRANSCRIPT", "count": 2},
        ],
        "global_cap": 7,
    }
    first = resolve(controls)
    second = resolve(controls)
    assert first.counts() == second.counts()
    assert first.count_for("DEPOSITION_TRANSCRIPT") == 2  # forced back in
    # The type max is an upper bound; the cap may legitimately trim below it.
    assert first.type_totals()["MEDICAL_CLINICAL"] <= 4
    assert "PROOF_OF_SERVICE" not in first.counts()  # blacklist honoured
    assert first.total == 7  # cap honoured


# 14 — the cap never breaks a higher-precedence type minimum
def test_global_cap_respects_a_type_minimum_floor() -> None:
    result = resolve(
        {"global_cap": 5, "overrides": [{"type": "MEDICAL_CLINICAL", "min": 6}]}
    )
    assert result.type_totals()["MEDICAL_CLINICAL"] == 6
    assert result.total == 6  # cap yields to the min floor
    assert any("cannot be met" in warning for warning in result.warnings)


def test_global_cap_trims_types_that_have_slack_above_their_minimum() -> None:
    result = resolve(
        {"global_cap": 12, "overrides": [{"type": "MEDICAL_CLINICAL", "min": 6}]}
    )
    assert result.total == 12
    assert result.type_totals()["MEDICAL_CLINICAL"] >= 6


# 13 — plumbing details
def test_duplicate_candidates_for_one_subtype_are_summed() -> None:
    result = resolve_document_controls(
        [
            DocumentCandidate("MRI_REPORT", priority=60, track=TRACK_SUPPORTING),
            DocumentCandidate("MRI_REPORT", priority=20, track=TRACK_CORE, count=2),
        ],
        DocumentControls(),
        parent_type_of=parent_of,
    )
    assert result.count_for("MRI_REPORT") == 3  # counts sum
    entry = result.planned[0]
    # Merged metadata is the most protective of the two proposals.
    assert entry.priority == 20  # most essential priority wins
    assert entry.track == TRACK_CORE  # least trimmable track wins


def test_parent_resolution_prefers_the_candidate_declaration() -> None:
    result = resolve_document_controls(
        [DocumentCandidate("MRI_REPORT", parent_type="CUSTOM_TYPE")],
        DocumentControls(),
        parent_type_of=parent_of,
    )
    assert result.planned[0].parent_type == "CUSTOM_TYPE"


def test_resolver_works_without_any_taxonomy_at_all() -> None:
    """Pure function: no substrate, no taxonomy, no I/O."""
    result = resolve_document_controls(
        [DocumentCandidate("ANY_SUBTYPE", count=2)], DocumentControls(global_cap=1)
    )
    assert result.total == 1
    assert result.planned[0].parent_type is None


def test_negative_candidate_count_is_rejected() -> None:
    with pytest.raises(ValueError, match="negative count"):
        resolve_document_controls(
            [DocumentCandidate("X", count=-1)], DocumentControls()
        )


# 15 — the unsatisfiable-min verdict is about the finished file, not step 3
def test_a_min_on_an_unproposed_type_still_warns_when_nothing_supplies_it() -> None:
    """The claim's true case, kept as the control for the one below it.

    Nothing in the miniature lifecycle carries parent type ``BILLING``, and no
    override supplies any, so the floor genuinely cannot be met and the manifest
    must say so.
    """
    result = resolve({"overrides": [{"type": "BILLING", "min": 3}]})
    assert "BILLING" not in result.type_totals()
    assert [warning for warning in result.warnings if "min=3" in warning] == [
        "documents.overrides min=3 for type BILLING is not met: the file holds "
        "0 — the lifecycle proposed no documents of that type"
    ], result.warnings


def test_a_min_an_override_then_satisfies_does_not_warn_that_it_cannot_be() -> None:
    """Review round 5, finding 3: two warnings, and the file refutes one.

    Type bounds are resolved at step 3 and per-subtype overrides at step 1 — the
    highest precedence control in the system, and the only one that can *invent*
    documents of a type the lifecycle never proposed. Deciding "cannot be
    satisfied" before it runs decides it against a plan that is not the plan.

    Measured on the shipped code: ``{type: DISCOVERY, min: 5}`` at
    ``target_stage: intake`` beside ``{subtype: SUBPOENAED_RECORDS_MEDICAL,
    count: 6}`` produced a manifest carrying both the warning and six DISCOVERY
    documents. Restated here on the pure resolver, whose ``BILLING`` type no
    candidate proposes.
    """
    result = resolve(
        {
            "overrides": [
                {"type": "BILLING", "min": 3},
                {"subtype": "MEDICAL_BILL", "count": 4},
            ]
        }
    )
    assert result.type_totals().get("BILLING") == 4, (
        f"the override did not supply the type at all: {result.type_totals()}"
    )
    assert not [w for w in result.warnings if "is not met" in w], (
        "the file holds 4 documents of a type whose floor of 3 is reported "
        f"unsatisfiable: {result.warnings}"
    )


def test_a_partly_supplied_min_says_how_far_short_the_file_falls() -> None:
    """Between the two: the override supplies some, but not the floor.

    "The lifecycle proposed no documents of that type" is still true and no
    longer the whole truth — the file holds two, and a reader told only that
    nothing was proposed will look for a file holding none.
    """
    result = resolve(
        {
            "overrides": [
                {"type": "BILLING", "min": 3},
                {"subtype": "MEDICAL_BILL", "count": 2},
            ]
        }
    )
    assert result.type_totals().get("BILLING") == 2
    unmet = [w for w in result.warnings if "is not met" in w]
    assert len(unmet) == 1, result.warnings
    assert "the file holds 2" in unmet[0], unmet[0]
    assert "the overrides supply only 2" in unmet[0], unmet[0]


def test_a_floor_an_override_cuts_back_below_is_reported() -> None:
    """Review round 6, finding 3: one principle, applied to one arm of two.

    Round 5 established that "is this floor met" is a claim about the finished
    file — the per-subtype overrides run last and are the highest precedence
    control in the system — and then fed the deferred check from only the arm
    where the lifecycle proposed NOTHING. The overrides move the count in both
    directions. Here the lifecycle proposes 6 PTP_PR2_PROGRESS_REPORTs,
    `_apply_type_min` grows MEDICAL_CLINICAL toward a floor of 10, and a
    per-subtype override then pins one of its members back down.

    Measured on the shipped code: the file held less than the floor and the
    warning list was EMPTY. A silent overrule of a control the author wrote is
    the exact failure this whole class of warning exists to prevent, and it was
    silent because the grown arm recorded nothing to check.
    """
    result = resolve(
        {
            "overrides": [
                {"type": "MEDICAL_CLINICAL", "min": 10},
                {"subtype": "PTP_PR2_PROGRESS_REPORT", "count": 1},
            ]
        }
    )
    held = result.type_totals().get("MEDICAL_CLINICAL", 0)
    assert held < 10, (
        f"the seed no longer leaves the floor short, so it proves nothing: {held}"
    )
    unmet = [w for w in result.warnings if "min=10" in w]
    assert len(unmet) == 1, (
        f"a floor of 10 holding {held} was overruled and nothing said so: "
        f"{result.warnings}"
    )
    assert f"the file holds {held}" in unmet[0], unmet[0]
    assert "PTP_PR2_PROGRESS_REPORT" in unmet[0], (
        "the warning does not name the override that cut the type back, so the "
        f"author is told a floor failed but not by what: {unmet[0]}"
    )


def test_a_floor_the_lifecycle_already_meets_says_nothing() -> None:
    """The opposite draw, so the check above cannot pass by warning always."""
    result = resolve({"overrides": [{"type": "MEDICAL_CLINICAL", "min": 4}]})
    assert result.type_totals()["MEDICAL_CLINICAL"] >= 4
    assert not [w for w in result.warnings if "is not met" in w], result.warnings
