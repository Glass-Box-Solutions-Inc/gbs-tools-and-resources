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
    verify_forced_subtypes,
    verify_global_cap,
    verify_type_floors,
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



def forced_warnings(result: Any, held: dict[str, int] | None = None) -> list[str]:
    """The forced-subtype verdict, taken the way the planner takes it.

    Whether an override "won" is a claim about the finished file: the scenario
    shaping downstream can remove every document it forced. `held=None` models
    nothing being removed after the controls run.
    """
    return verify_forced_subtypes(result.forced_checks, held or result.counts())


def cap_warnings(result: Any, held: int | None = None) -> list[str]:
    """The cap verdict, taken the way the planner takes it.

    Same seam as `floor_warnings`, and for the same reason: the resolver trims
    toward the cap and knows when it stopped short, but whether the cap is
    actually breached is a fact about the finished file. `held=None` models the
    case where nothing is removed after the controls run.
    """
    return verify_global_cap(
        result.cap_check, result.total if held is None else held
    )


def floor_warnings(result: Any, held: dict[str, int] | None = None) -> list[str]:
    """The floor verdict, taken the way the planner takes it.

    The resolver deliberately does not decide this — its plan is not the finished
    file, and the scenario shaping between the two can drop a whole type. It
    hands out `floor_checks`; the caller answers them against what it actually
    holds. Passing `held=None` models the case where nothing is removed after
    the controls run.
    """
    planned = result.type_totals()
    return verify_type_floors(result.floor_checks, held or planned, planned)

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
    assert any("INVESTIGATION" in warning for warning in floor_warnings(result))


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
    assert any("documents.exclude" in w for w in forced_warnings(result))


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
    assert any("cannot be met" in warning for warning in cap_warnings(result))


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
    assert any("never emits it" in warning for warning in forced_warnings(result))


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
    assert any("cannot be met" in warning for warning in cap_warnings(result))
    # Round 9: the resolver records the facts and decides nothing. Whether the
    # cap is breached depends on what the file finally holds, which it cannot
    # see — under `never_treated` every remaining document is dropped and the
    # cap of 5 is met after all.
    assert not [w for w in result.warnings if "cannot be met" in w], result.warnings
    assert not cap_warnings(result, held=0), (
        "a file holding nothing cannot breach a cap of 5"
    )


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
    assert [warning for warning in floor_warnings(result) if "min=3" in warning] == [
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
    assert not floor_warnings(result), (
        "the file holds 4 documents of a type whose floor of 3 is reported "
        f"unmet: {floor_warnings(result)}"
    )
    # Round 7 moved the verdict out of the resolver entirely: its plan is not
    # the finished file, so it must hand out the question and answer nothing.
    # Asserting only on `floor_warnings` left this guard blind to a resolver
    # that decides eagerly and writes straight into `warnings` — which is what
    # m12-20 restores, and it SURVIVED until this assertion was added.
    #
    # Matched on "is not met" — the SHAPE of a floor verdict — rather than on
    # this seed's floor value. Round 8 pointed out that the first version keyed
    # on "min=3", so an eager verdict phrased differently, or emitted for another
    # floor, would have slipped past a guard whose comment claims to assert the
    # architecture.
    assert not [w for w in result.warnings if "is not met" in w], (
        "the resolver decided a floor verdict itself, against a plan that is "
        f"not the file: {result.warnings}"
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
    unmet = floor_warnings(result)
    assert len(unmet) == 1, unmet
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
    unmet = [w for w in floor_warnings(result) if "min=10" in w]
    assert len(unmet) == 1, (
        f"a floor of 10 holding {held} was overruled and nothing said so: "
        f"{floor_warnings(result)}"
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
    assert not floor_warnings(result), floor_warnings(result)


def test_an_override_that_added_documents_is_not_blamed_for_the_shortfall() -> None:
    """Review round 7, finding 1: attribution by seed membership, not by effect.

    `cut_by` selected every override whose subtype sits under the short type.
    That named `SUBPOENAED_RECORDS_OTHER x4` — an override that INVENTED four
    documents of the very type whose floor was short — as having cut it back, in
    the same manifest that says it forced them into existence. Measured on the
    shipped code: the type went from 52 to 56 when that override was added, and
    following the implied edit moves the file further from the floor, not
    closer. Only overrides that actually lowered a count are named now.
    """
    # The floor grows MEDICAL_CLINICAL to 30 by inflating its members — PTP to
    # 17 and MRI to 13 — so an override BELOW the grown figure is a cut and one
    # ABOVE it is an addition. Both are in the seed, and only the cut may be
    # named.
    grown = resolve({"overrides": [{"type": "MEDICAL_CLINICAL", "min": 30}]})
    assert (grown.count_for("PTP_PR2_PROGRESS_REPORT"), grown.count_for("MRI_REPORT")) == (
        17,
        13,
    ), f"the growth figures this test is built on moved: {grown.counts()}"

    with_adder = resolve(
        {
            "overrides": [
                {"type": "MEDICAL_CLINICAL", "min": 30},
                {"subtype": "PTP_PR2_PROGRESS_REPORT", "count": 2},
                {"subtype": "MRI_REPORT", "count": 25},
            ]
        }
    )
    assert with_adder.count_for("MRI_REPORT") == 25 > 13, (
        "MRI_REPORT must be the override that ADDED documents of the short type"
    )
    assert with_adder.count_for("PTP_PR2_PROGRESS_REPORT") == 2 < 17, (
        "PTP_PR2_PROGRESS_REPORT must be the override that CUT the short type"
    )

    unmet = [w for w in floor_warnings(with_adder) if "min=30" in w]
    assert len(unmet) == 1, floor_warnings(with_adder)
    assert "PTP_PR2_PROGRESS_REPORT" in unmet[0], (
        f"the override that cut the type back is not named: {unmet[0]}"
    )
    assert "MRI_REPORT" not in unmet[0], (
        "an override that raised the count of the short type is blamed for "
        f"cutting it back: {unmet[0]}"
    )


def test_a_floor_the_caller_loses_after_the_controls_run_names_the_scenario() -> None:
    """Round 7, finding 2: the resolver's plan is not the finished file.

    `resolve_document_controls` returns a plan; scenario shaping runs afterwards
    and can drop a whole type. A verdict taken inside the resolver therefore
    described a file that no longer existed — measured, a warning reading "the
    file holds 23" shipped in a manifest whose file held 0.

    The resolver now hands out the question and the caller answers it against
    what it holds. Here the caller reports holding nothing, which is the shape
    `never_treated` produces, and both the count and the cause must follow.
    """
    result = resolve({"overrides": [{"type": "MEDICAL_CLINICAL", "min": 10}]})
    assert result.type_totals()["MEDICAL_CLINICAL"] >= 10, (
        "the resolver must MEET this floor, so any warning can only come from "
        "what the caller lost afterwards"
    )
    assert not floor_warnings(result), (
        f"the resolver's own plan meets the floor: {floor_warnings(result)}"
    )

    lost_it_all = floor_warnings(result, held={"MEDICAL_CLINICAL": 0})
    assert len(lost_it_all) == 1, lost_it_all
    assert "the file holds 0" in lost_it_all[0], (
        f"the count is not the caller's: {lost_it_all[0]}"
    )
    assert "the scenario removed them" in lost_it_all[0], (
        "no override lowered a count, so blaming documents.overrides would send "
        f"the author to a line that is not responsible: {lost_it_all[0]}"
    )


def test_an_override_cut_and_a_later_removal_are_both_named() -> None:
    """Both causes, because prescribing only the first does not deliver.

    Under `never_treated` a MEDICAL_CLINICAL floor reaches zero however high the
    overrides go — measured at counts 1, 10, 30 and 60, all zero. Naming only
    the override that reduced the type prescribes an edit that cannot deliver,
    which is the ISC-150 class this ticket exists to remove.
    """
    result = resolve(
        {
            "overrides": [
                {"type": "MEDICAL_CLINICAL", "min": 30},
                {"subtype": "PTP_PR2_PROGRESS_REPORT", "count": 1},
            ]
        }
    )
    planned = result.type_totals()["MEDICAL_CLINICAL"]
    assert planned > 0
    unmet = floor_warnings(result, held={"MEDICAL_CLINICAL": 0})
    assert len(unmet) == 1, unmet
    assert "PTP_PR2_PROGRESS_REPORT" in unmet[0], unmet[0]
    assert f"the scenario then removed {planned} more" in unmet[0], (
        "the override alone cannot deliver this floor and the warning does not "
        f"say what else took the documents: {unmet[0]}"
    )


def test_every_declared_floor_is_enrolled_even_when_it_already_holds() -> None:
    """Round 8: the evaluation moved to the file and enrolment stayed at step 3.

    A floor was written into `floors_to_verify` only if it was SHORT when step 3
    saw it, and `floor_checks` is built from that dict — so a floor the lifecycle
    already satisfied was never handed to the caller and never compared against
    anything, however much the file lost afterwards.

    Measured under `never_treated`, where MEDICAL_CLINICAL ends at 0: floors of 1
    through 9 were silent and 10 through 12 warned, the boundary being exactly
    the step-3 total. The weakest possible assertion — "this file must hold at
    least one clinical record" — was the one least likely to be enforced.

    Enrolment is a fact about the seed, so it cannot be filtered by an
    intermediate count. This asserts the floor is enrolled even though the
    resolver's own plan satisfies it, which is precisely the case that was lost.
    """
    result = resolve({"overrides": [{"type": "MEDICAL_CLINICAL", "min": 3}]})
    assert result.type_totals()["MEDICAL_CLINICAL"] >= 3, (
        "this floor must be MET at the resolver, or the test is about the "
        "already-covered short case instead"
    )
    enrolled = [check for check in result.floor_checks if check[0] == "MEDICAL_CLINICAL"]
    assert len(enrolled) == 1, (
        f"a floor the resolver satisfies is never handed out: {result.floor_checks}"
    )
    assert enrolled[0][1] == 3

    # And it must produce a verdict once the caller reports losing the documents.
    assert not floor_warnings(result), floor_warnings(result)
    assert len(floor_warnings(result, held={"MEDICAL_CLINICAL": 0})) == 1, (
        "enrolled but silent when the file drops to zero"
    )


def test_a_cap_the_file_no_longer_breaches_is_not_reported_as_unreachable() -> None:
    """Round 9, finding A: the fourth instance, in the last verdict left behind.

    Round 8 moved the floor verdict to the planner precisely because the
    resolver's plan is not the file. The cap verdict stayed, and it makes the
    same grammatical claim. Measured with `global_cap: 5`,
    `{type: MEDICAL_CLINICAL, min: 30}` and `never_treated`, the manifest carried
    "documents.global_cap=5 cannot be met without breaking a higher-precedence
    control (... MEDICAL_CLINICAL min=30)" for a file holding ZERO documents —
    beside a second warning stating that same floor held nothing. The cap was
    met, the floor blamed for forcing the total up was empty, and each warning
    refuted the other.
    """
    result = resolve(
        {"global_cap": 5, "overrides": [{"type": "MEDICAL_CLINICAL", "min": 30}]}
    )
    assert result.cap_check is not None, (
        "the resolver must still record that it could not reach the cap"
    )
    assert result.total > 5, "the resolver's own plan exceeds the cap"
    assert cap_warnings(result), "a genuine breach must still be reported"
    assert "the file holds" in cap_warnings(result)[0], (
        f"the verdict does not state what the file holds: {cap_warnings(result)[0]}"
    )

    # The case that shipped the false claim: the scenario empties the file.
    assert not cap_warnings(result, held=0), (
        "a file holding nothing is reported as unable to meet a cap of 5"
    )
    assert not cap_warnings(result, held=5), "at the cap is not over the cap"
    assert cap_warnings(result, held=6), "one over the cap must still report"


def test_an_override_that_reduced_without_causing_the_shortfall_is_not_named() -> None:
    """Round 9, finding B: `reducing` answered the wrong question.

    `count < before_overrides` asks "did this override reduce anything". The
    sentence claims "this override is why the floor is short". Those differ
    whenever the controls left the type at or above its floor and something
    afterwards emptied it: the override reduced a subtype, the floor was still
    satisfied, and the scenario is the sole cause.

    Naming it there implies raising it would help, and this package's own
    measurements say it cannot — under `never_treated` the type reaches zero at
    override counts 1, 10, 30 and 60 alike. Round 7 caught this predicate naming
    an override that ADDED documents; this is the subtler form.
    """
    controls = {
        "overrides": [
            {"type": "MEDICAL_CLINICAL", "min": 3},
            {"subtype": "PTP_PR2_PROGRESS_REPORT", "count": 1},
        ]
    }
    result = resolve(controls)
    planned = result.type_totals()["MEDICAL_CLINICAL"]
    assert planned >= 3, (
        f"the controls must SATISFY this floor for the test to be about a "
        f"bystander override: planned {planned}"
    )

    unmet = floor_warnings(result, held={"MEDICAL_CLINICAL": 0})
    assert len(unmet) == 1, unmet
    assert "PTP_PR2_PROGRESS_REPORT" not in unmet[0], (
        "an override that reduced a subtype without causing the shortfall is "
        f"named as the cause: {unmet[0]}"
    )
    assert "the scenario removed them" in unmet[0], unmet[0]


def test_an_override_that_did_cause_the_shortfall_is_still_named() -> None:
    """The opposite draw, so the rule above cannot pass by never naming anything."""
    result = resolve(
        {
            "overrides": [
                {"type": "MEDICAL_CLINICAL", "min": 30},
                {"subtype": "PTP_PR2_PROGRESS_REPORT", "count": 1},
            ]
        }
    )
    planned = result.type_totals()["MEDICAL_CLINICAL"]
    assert planned < 30, (
        f"the controls must leave this floor SHORT for the override to be a "
        f"genuine cause: planned {planned}"
    )
    unmet = floor_warnings(result, held={"MEDICAL_CLINICAL": 0})
    assert len(unmet) == 1, unmet
    assert "PTP_PR2_PROGRESS_REPORT" in unmet[0], (
        f"the override that genuinely caused the shortfall is not named: {unmet[0]}"
    )


def test_a_forced_subtype_the_file_never_holds_is_not_called_a_win() -> None:
    """Round 10, finding 2: the fifth site, and the only inverted one.

    "control wins, loudly" is a claim about the finished file. At
    `target_stage: intake` under `never_treated` it was published for four
    different subtypes whose final count was ZERO, beside a second warning in
    the same manifest saying the scenario had suppressed exactly that family.
    Not a stale number — the opposite of what happened. The control lost, and
    it lost silently.
    """
    result = resolve({"overrides": [{"subtype": "SURVEILLANCE_REPORT", "count": 6}]})
    assert result.count_for("SURVEILLANCE_REPORT") == 6

    won = forced_warnings(result)
    assert len(won) == 1 and "control wins, loudly" in won[0], won

    lost = forced_warnings(result, held={"SURVEILLANCE_REPORT": 0})
    assert len(lost) == 1, lost
    assert "control wins" not in lost[0], (
        "a file holding none of the forced subtype is reported as the control "
        f"winning: {lost[0]}"
    )
    assert "did NOT win" in lost[0], lost[0]

    partial = forced_warnings(result, held={"SURVEILLANCE_REPORT": 2})
    assert "control wins" not in partial[0], partial[0]
    assert "only 2" in partial[0], partial[0]


def test_the_cap_reason_counts_pinned_documents_the_file_still_holds() -> None:
    """Round 10, finding 1: the verdict moved to the file and its reason did not.

    Round 9 fixed `held`. The parenthetical explaining the breach still counted
    forced documents at resolver time, so ten of them were offered as the reason
    a cap could not be met in a file containing none. Removing that override left
    the breach byte-identical, which proves they were never a cause: the author
    is told to lower a pin that is not holding anything.
    """
    result = resolve(
        {"global_cap": 2, "overrides": [{"subtype": "PROOF_OF_SERVICE", "count": 6}]}
    )
    assert result.cap_check is not None

    survived = cap_warnings(result)
    assert survived and "6 document(s) pinned" in survived[0], survived

    # The file kept the documents but not the pinned ones.
    none_pinned = verify_global_cap(result.cap_check, result.total, 0)
    assert none_pinned, "the cap is still breached, so it must still report"
    assert "0 document(s) pinned" in none_pinned[0], (
        "the reason counts pinned documents the file no longer holds: "
        f"{none_pinned[0]}"
    )
