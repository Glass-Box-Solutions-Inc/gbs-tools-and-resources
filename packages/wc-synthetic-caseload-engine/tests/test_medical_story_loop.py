"""AJC-62 (M3) — the contention-loop topology gates (R43, mapped by R69).

R77 step 4 opens this module with the two response-semantics gates whose
production surface lands with the disposition remodel: the R37 revision-kind
predicates and the exact changed/unchanged percentage-row metadata. The loop
topology gates (decision table, branching, truncation, caps, explicit
composition, non-recursion, planner integration) land here with their
producers at steps 5-6; nothing in this module may be weakened when they do.

Every guard collects as exactly one non-parametrized pytest item (R74/R75
mutation discipline): fixtures vary inside the test body, never through
``pytest.mark.parametrize``.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from wc_caseload_engine.medical_assertions import (
    ApportionmentAssertion,
    AssertionValidationContext,
    AssertionWorldProjection,
    Contention,
    MedicalAssertionLedger,
    MedicalOpinion,
    ProjectedCondition,
    ProjectedPriorClaim,
    validate_medical_assertions,
)


def _context(**overrides: Any) -> AssertionValidationContext:
    values: dict[str, Any] = {
        "date_of_injury": dt.date(2022, 4, 11),
        "anchor_date": dt.date(2026, 1, 1),
        "current_body_parts": ("lumbar_spine", "shoulder"),
        "target_stage": "medical_legal",
        "claim_response": "accepted",
        "eval_type": "qme",
    }
    values.update(overrides)
    return AssertionValidationContext(**values)


def _world() -> AssertionWorldProjection:
    return AssertionWorldProjection(
        conditions=(
            ProjectedCondition(
                id="cond-01",
                key="seeded",
                label="degenerative lumbar disease",
                causal_ground_truth="nonindustrial",
                onset=dt.date(2015, 6, 1),
                body_system="musculoskeletal",
                body_part="lumbar_spine",
                apportionment_targets=("lumbar_spine",),
                wholly_unrelated=False,
                severity="moderate",
                trajectory="stable",
                symptomatic_before_doi=True,
                surfaces_in_file=True,
            ),
        ),
        prior_claims=(
            ProjectedPriorClaim(
                id="prior-01",
                date_of_injury=dt.date(2015, 1, 5),
                body_parts=("lumbar_spine",),
                resolution_type="stipulated_award",
                overlaps_current=True,
                award=None,
            ),
        ),
    )


def _contention(contention_id: str = "ctn-01", **overrides: Any) -> Contention:
    values: dict[str, Any] = {
        "id": contention_id,
        "claim_type": "industrial_causation",
        "party": "applicant",
        "position": "affirm",
        "target_condition_id": "cond-01",
        "rationale": "the lumbar condition arose from the industrial injury",
        "quality": "supported",
    }
    values.update(overrides)
    return Contention(**values)


def _base_opinion(**overrides: Any) -> MedicalOpinion:
    values: dict[str, Any] = {
        "id": "opn-01",
        "author_role": "qme",
        "report_stage": "final",
        "report_date": dt.date(2023, 6, 1),
        "apportionment_state": "determined",
        "determination_kind": "allocated",
        "determination_rationale": "the split follows the imaging severity",
        "examination_performed": True,
        "reviewed_condition_ids": ("cond-01",),
        "endorses_contention_ids": ("ctn-01",),
        "aoe_coe_finding": "industrial",
        "aoe_coe_rationale": "mechanism and course support industrial causation",
        "rationale": "reviewed the record and examined the applicant",
        "quality": "supported",
    }
    values.update(overrides)
    return MedicalOpinion(**values)


def _response_opinion(**overrides: Any) -> MedicalOpinion:
    values: dict[str, Any] = {
        "id": "opn-02",
        "author_role": "qme",
        "report_stage": "final",
        "report_date": dt.date(2023, 11, 1),
        "apportionment_state": "determined",
        "determination_kind": "allocated",
        "determination_rationale": "the split stands as previously stated",
        "examination_performed": False,
        "event_kind": "supplemental_report",
        "revision_kind": "unchanged_additional_reasoning",
        "responds_to_opinion_id": "opn-01",
        "reviewed_condition_ids": ("cond-01",),
        "endorses_contention_ids": ("ctn-01",),
        "aoe_coe_finding": "industrial",
        "aoe_coe_rationale": "mechanism and course support industrial causation",
        "rationale": "the written conclusions stand with additional reasoning",
        "quality": "supported",
    }
    values.update(overrides)
    return MedicalOpinion(**values)


def _row(
    assertion_id: str, opinion_id: str, nonindustrial: int, **overrides: Any
) -> ApportionmentAssertion:
    values: dict[str, Any] = {
        "id": assertion_id,
        "opinion_id": opinion_id,
        "body_part": "lumbar_spine",
        "industrial_percent": 100 - nonindustrial,
        "nonindustrial_percent": nonindustrial,
        "basis_kinds": ("preexisting_degenerative_pathology",),
        "condition_ids": ("cond-01",),
        "description": "chronic lumbar disability limiting weight-bearing",
        "disability_causation_stated": True,
        "reasonable_medical_probability": True,
        "causal_rationale": "degenerative pathology contributes to the disability",
        "percentage_rationale": "the share reflects the imaging severity",
        "quality": "supported",
    }
    values.update(overrides)
    return ApportionmentAssertion(**values)


def _problems(
    opinions: tuple[MedicalOpinion, ...],
    assertions: tuple[ApportionmentAssertion, ...] = (),
) -> tuple[str, ...]:
    ledger = MedicalAssertionLedger(
        contentions=(_contention(),),
        medical_opinions=opinions,
        apportionment_assertions=assertions,
    )
    return validate_medical_assertions(_context(), _world(), ledger)


def test_revision_kind_predicates_accept_and_reject_exact_field_changes() -> None:
    """R43's revision-taxonomy gate (R37, enforced at R77 step 4): each of the
    five kinds permits and forbids exactly its stated field changes, the
    supersession rule follows the kind, and the combined kind is a COMPLETE
    conjunction — one changed family alone is rejected in both directions."""
    base = _base_opinion()
    base_row = _row("app-01", "opn-01", 20)

    # unchanged_additional_reasoning: nothing changes, supersedes nothing —
    # accepted exactly as constructed.
    unchanged = _response_opinion()
    accepted = _problems((base, unchanged), (base_row, _row("app-02", "opn-02", 20)))
    assert accepted == ()

    # …but a causation-family change under the no-change kind is rejected —
    # here a disposition result moves (the endorsement is dropped).
    moved_disposition = _response_opinion(endorses_contention_ids=())
    problems = _problems((base, moved_disposition), (base_row, _row("app-02", "opn-02", 20)))
    assert (
        "medical opinion 'opn-02' has revision_kind "
        "'unchanged_additional_reasoning' but changes a causation-family "
        "result relative to predecessor 'opn-01'; AOE/COE, psych "
        "classification and every disposition result must remain the same "
        "under this kind"
    ) in problems

    # …an apportionment-family change under the no-change kind is rejected —
    # here the percentage moves.
    moved_percentage = _response_opinion()
    problems = _problems(
        (base, moved_percentage),
        (
            base_row,
            _row(
                "app-02",
                "opn-02",
                30,
                revised_from_percent=20,
                revision_rationale="the share moved with the new imaging",
            ),
        ),
    )
    assert any(
        problem.startswith(
            "medical opinion 'opn-02' has revision_kind "
            "'unchanged_additional_reasoning' but changes an "
            "apportionment-family result"
        )
        for problem in problems
    )

    # …and claiming supersession without a revision is rejected.
    superseding_unchanged = _response_opinion(supersedes_opinion_id="opn-01")
    problems = _problems(
        (base, superseding_unchanged), (base_row, _row("app-02", "opn-02", 20))
    )
    assert (
        "medical opinion 'opn-02' has revision_kind "
        "'unchanged_additional_reasoning' but sets supersedes_opinion_id; a "
        "response that changes no result supersedes nothing"
    ) in problems

    # new_records_no_change: accepted only when the reviewed-record union is
    # a strict superset and no result moves.
    new_records = _response_opinion(
        revision_kind="new_records_no_change",
        reviewed_condition_ids=("cond-01",),
        reviewed_prior_claim_ids=(),
    )
    problems = _problems((base, new_records), (base_row, _row("app-02", "opn-02", 20)))
    assert (
        "medical opinion 'opn-02' has revision_kind 'new_records_no_change' "
        "but its reviewed-record union is not a strict superset of "
        "predecessor 'opn-01''s; acknowledging new records is what this kind "
        "states"
    ) in problems
    base_narrow = _base_opinion(reviewed_condition_ids=("cond-01",))
    grew = _response_opinion(
        revision_kind="new_records_no_change",
        reviewed_condition_ids=("cond-01",),
        reviewed_prior_claim_ids=("prior-01",),
    )
    accepted = _problems(
        (base_narrow, grew), (base_row, _row("app-02", "opn-02", 20))
    )
    assert accepted == ()

    # revised_causation: requires a causation change, supersession of the
    # predecessor, and NO apportionment change.
    revised_causation = _response_opinion(
        revision_kind="revised_causation",
        supersedes_opinion_id="opn-01",
        aoe_coe_finding="nonindustrial",
        aoe_coe_rationale="the record now shows a nonindustrial mechanism",
        endorses_contention_ids=(),
        rejects_contention_ids=("ctn-01",),
        revision_rationale="the causation conclusion is revised",
    )
    accepted = _problems(
        (base, revised_causation), (base_row, _row("app-02", "opn-02", 20))
    )
    assert accepted == ()
    no_causation_change = _response_opinion(
        revision_kind="revised_causation",
        supersedes_opinion_id="opn-01",
        revision_rationale="claims revision while changing nothing",
    )
    problems = _problems(
        (base, no_causation_change), (base_row, _row("app-02", "opn-02", 20))
    )
    assert (
        "medical opinion 'opn-02' has revision_kind 'revised_causation' but "
        "changes no causation-family result relative to predecessor 'opn-01'"
    ) in problems
    causation_plus_percentage = _response_opinion(
        revision_kind="revised_causation",
        supersedes_opinion_id="opn-01",
        aoe_coe_finding="nonindustrial",
        revision_rationale="the causation conclusion is revised",
    )
    problems = _problems(
        (base, causation_plus_percentage),
        (
            base_row,
            _row(
                "app-02",
                "opn-02",
                30,
                revised_from_percent=20,
                revision_rationale="the share moved too",
            ),
        ),
    )
    assert (
        "medical opinion 'opn-02' has revision_kind 'revised_causation' but "
        "also changes an apportionment-family result relative to predecessor "
        "'opn-01'; use 'revised_causation_and_apportionment'"
    ) in problems
    missing_supersession = _response_opinion(
        revision_kind="revised_causation",
        aoe_coe_finding="nonindustrial",
        revision_rationale="the causation conclusion is revised",
    )
    problems = _problems(
        (base, missing_supersession), (base_row, _row("app-02", "opn-02", 20))
    )
    assert (
        "medical opinion 'opn-02' has revision_kind 'revised_causation' but "
        "supersedes_opinion_id is not its immediate predecessor 'opn-01'; a "
        "revising response supersedes exactly the report it revises"
    ) in problems

    # revised_apportionment: requires an apportionment change and NO
    # causation change.
    revised_apportionment = _response_opinion(
        revision_kind="revised_apportionment",
        supersedes_opinion_id="opn-01",
        revision_rationale="the share follows the new imaging",
    )
    accepted = _problems(
        (base, revised_apportionment),
        (
            base_row,
            _row(
                "app-02",
                "opn-02",
                30,
                revised_from_percent=20,
                revision_rationale="the share follows the new imaging",
            ),
        ),
    )
    assert accepted == ()
    no_apportionment_change = _response_opinion(
        revision_kind="revised_apportionment",
        supersedes_opinion_id="opn-01",
        revision_rationale="claims a revision while changing nothing",
    )
    problems = _problems(
        (base, no_apportionment_change), (base_row, _row("app-02", "opn-02", 20))
    )
    assert (
        "medical opinion 'opn-02' has revision_kind 'revised_apportionment' "
        "but changes no apportionment-family result relative to predecessor "
        "'opn-01'"
    ) in problems
    apportionment_plus_causation = _response_opinion(
        revision_kind="revised_apportionment",
        supersedes_opinion_id="opn-01",
        aoe_coe_finding="nonindustrial",
        revision_rationale="the share follows the new imaging",
    )
    problems = _problems(
        (base, apportionment_plus_causation),
        (
            base_row,
            _row(
                "app-02",
                "opn-02",
                30,
                revised_from_percent=20,
                revision_rationale="the share follows the new imaging",
            ),
        ),
    )
    assert (
        "medical opinion 'opn-02' has revision_kind 'revised_apportionment' "
        "but also changes a causation-family result relative to predecessor "
        "'opn-01'; use 'revised_causation_and_apportionment'"
    ) in problems

    # revised_causation_and_apportionment: the COMPLETE conjunction — both
    # families must actually change; one alone is rejected in each direction.
    combined = _response_opinion(
        revision_kind="revised_causation_and_apportionment",
        supersedes_opinion_id="opn-01",
        aoe_coe_finding="nonindustrial",
        revision_rationale="both conclusions are revised",
    )
    accepted = _problems(
        (base, combined),
        (
            base_row,
            _row(
                "app-02",
                "opn-02",
                30,
                revised_from_percent=20,
                revision_rationale="both conclusions are revised",
            ),
        ),
    )
    assert accepted == ()
    combined_missing_apportionment = _response_opinion(
        revision_kind="revised_causation_and_apportionment",
        supersedes_opinion_id="opn-01",
        aoe_coe_finding="nonindustrial",
        revision_rationale="only causation actually moved",
    )
    problems = _problems(
        (base, combined_missing_apportionment),
        (base_row, _row("app-02", "opn-02", 20)),
    )
    assert (
        "medical opinion 'opn-02' has revision_kind "
        "'revised_causation_and_apportionment' but changes no "
        "apportionment-family result relative to predecessor 'opn-01'"
    ) in problems
    combined_missing_causation = _response_opinion(
        revision_kind="revised_causation_and_apportionment",
        supersedes_opinion_id="opn-01",
        revision_rationale="only the share actually moved",
    )
    problems = _problems(
        (base, combined_missing_causation),
        (
            base_row,
            _row(
                "app-02",
                "opn-02",
                30,
                revised_from_percent=20,
                revision_rationale="only the share actually moved",
            ),
        ),
    )
    assert (
        "medical opinion 'opn-02' has revision_kind "
        "'revised_causation_and_apportionment' but changes no "
        "causation-family result relative to predecessor 'opn-01'"
    ) in problems


def test_changed_and_unchanged_percentage_rows_carry_exact_revision_metadata() -> None:
    """R43's percentage-revision gate (R37, R77 step 4): on an allocated
    predecessor, a changed row carries the exact predecessor percentage and a
    reason; an unchanged row does not claim revision; a row on a body part
    the predecessor never allocated revises nothing."""
    base = _base_opinion()
    base_row = _row("app-01", "opn-01", 20)

    def revising(**row_overrides: Any) -> tuple[str, ...]:
        response = _response_opinion(
            revision_kind="revised_apportionment",
            supersedes_opinion_id="opn-01",
            revision_rationale="the share follows the new imaging",
        )
        return _problems(
            (base, response),
            (base_row, _row("app-02", "opn-02", 30, **row_overrides)),
        )

    # The exact compliant changed row.
    assert (
        revising(
            revised_from_percent=20,
            revision_rationale="the share follows the new imaging",
        )
        == ()
    )

    # A changed row whose revised_from_percent is not the predecessor's exact
    # nonindustrial percentage.
    problems = revising(
        revised_from_percent=15,
        revision_rationale="the share follows the new imaging",
    )
    assert (
        "apportionment assertion 'app-02' changes body part 'lumbar_spine' "
        "from predecessor 'opn-01''s nonindustrial 20% but "
        "revised_from_percent is 15; a changed row carries the exact "
        "predecessor percentage"
    ) in problems

    # A changed row that claims no prior percentage at all.
    problems = revising(revision_rationale="the share follows the new imaging")
    assert (
        "apportionment assertion 'app-02' changes body part 'lumbar_spine' "
        "from predecessor 'opn-01''s nonindustrial 20% but "
        "revised_from_percent is None; a changed row carries the exact "
        "predecessor percentage"
    ) in problems

    # A changed row without a stated reason.
    problems = revising(revised_from_percent=20, revision_rationale=None)
    assert (
        "apportionment assertion 'app-02' changes body part 'lumbar_spine' "
        "from predecessor 'opn-01' without a revision_rationale; a changed "
        "percentage states its reason"
    ) in problems

    # An unchanged row claiming revision.
    unchanged_claiming = _response_opinion()
    problems = _problems(
        (base, unchanged_claiming),
        (
            base_row,
            _row(
                "app-02",
                "opn-02",
                20,
                revised_from_percent=20,
                revision_rationale="claims a revision that never happened",
            ),
        ),
    )
    assert (
        "apportionment assertion 'app-02' keeps predecessor 'opn-01''s "
        "nonindustrial 20% for body part 'lumbar_spine' but sets "
        "revised_from_percent; an unchanged row does not claim revision"
    ) in problems

    # A row on a body part the predecessor never allocated cannot claim a
    # revision source there.
    new_part = _response_opinion(
        revision_kind="revised_apportionment",
        supersedes_opinion_id="opn-01",
        revision_rationale="a fresh shoulder allocation",
    )
    problems = _problems(
        (base, new_part),
        (
            base_row,
            _row("app-02", "opn-02", 20),
            _row(
                "app-03",
                "opn-02",
                10,
                body_part="shoulder",
                condition_ids=(),
                basis_kinds=("nonindustrial_medical_condition",),
                revised_from_percent=10,
                revision_rationale="claims a shoulder revision from nothing",
            ),
        ),
    )
    assert (
        "apportionment assertion 'app-03' sets revised_from_percent but "
        "predecessor 'opn-01' allocated no percentage for body part "
        "'shoulder'"
    ) in problems
