"""Lifecycle path coverage — liens, reconsideration, dates and statutory windows.

These tests assert on the *plan*, not on rendered files, so they run fast and
fail with a readable diff. Rendering is covered in ``test_rendering.py``.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from conftest import requires_substrate
from wc_caseload_engine.lien_machine import RESOLUTION_SUBTYPES, build_lien_tracks
from wc_caseload_engine.lifecycle_bridge import (
    SINGLETON_SUBTYPES,
    build_core_candidates,
    build_timeline,
)
from wc_caseload_engine.planner import build_case_plan
from wc_caseload_engine.recon_machine import (
    ORDER_WINDOW_DAYS,
    PETITION_WINDOW_DAYS,
    build_recon_track,
)
from wc_caseload_engine.seeds import parse_case_seed
from wc_caseload_engine.taxonomy import effective_taxonomy

pytestmark = requires_substrate


def make_seed(**lifecycle: Any) -> Any:
    """A resolved case seed with an injury old enough for any lifecycle path."""
    raw: dict[str, Any] = {
        "case_id": "path-001",
        "rng_seed": 7777,
        "injury": {
            "type": "specific",
            "date_of_injury": "2022-01-10",
            "body_parts": [{"part": "lumbar_spine", "icd10": "M54.5"}],
        },
        "lifecycle": {
            "target_stage": "resolved",
            "claim_response": "accepted",
            "eval_type": "qme",
            "resolution": {"type": "findings_award"},
            **lifecycle,
        },
        "documents": {"global_cap": 40},
    }
    return parse_case_seed(raw)


def plan_subtypes(seed: Any) -> list[str]:
    """Subtypes in a case plan (no rendering)."""
    return [document.subtype for document in build_case_plan(seed).documents]


# ---------------------------------------------------------------------------
# Liens
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("resolution", "expected"),
    [
        ("lien_resolution_agreement", "LIEN_RESOLUTION"),
        ("lien_stipulation", "LIEN_STIPULATION_AGREEMENT"),
        ("dismissal", "LIEN_DISMISSAL"),
        ("order_on_lien", "ORDER_ON_LIEN"),
    ],
)
def test_each_lien_resolution_subtype_appears_when_seeded(
    resolution: str, expected: str
) -> None:
    seed = make_seed(
        liens={"count": 2, "claimants": ["medical_provider", "hospital"], "resolution": resolution}
    )
    subtypes = plan_subtypes(seed)
    assert subtypes.count(expected) == 2, f"expected one {expected} per lien track"


def test_mixed_resolution_draws_per_track() -> None:
    """``mixed`` decides per track, so a wide caseload hits several subtypes."""
    seen: set[str] = set()
    for rng_seed in range(20):
        raw = {
            "case_id": f"mixed-{rng_seed:03d}",
            "rng_seed": 500 + rng_seed,
            "injury": {
                "type": "specific",
                "date_of_injury": "2022-01-10",
                "body_parts": [{"part": "knee", "icd10": "M23.51"}],
            },
            "lifecycle": {
                "target_stage": "resolved",
                "resolution": {"type": "c_and_r"},
                "liens": {"count": 4, "resolution": "mixed"},
            },
        }
        for track in build_lien_tracks(parse_case_seed(raw), build_timeline(parse_case_seed(raw))):
            if track.resolution_subtype:
                seen.add(track.resolution_subtype)
    assert seen == set(RESOLUTION_SUBTYPES.values()), f"mixed never produced: {seen}"


def test_every_claimant_type_maps_to_its_lien_subtype() -> None:
    claimants = [
        "medical_provider",
        "hospital",
        "pharmacy",
        "ambulance",
        "edd",
        "attorney_costs",
        "self_procured",
    ]
    seed = make_seed(
        liens={"count": 7, "claimants": claimants, "resolution": "lien_resolution_agreement"}
    )
    subtypes = set(plan_subtypes(seed))
    for expected in (
        "LIEN_MEDICAL_PROVIDER",
        "LIEN_HOSPITAL",
        "LIEN_PHARMACY",
        "LIEN_AMBULANCE_TRANSPORT",
        "LIEN_EDD_OVERPAYMENT",
        "LIEN_ATTORNEY_COSTS",
        "LIEN_SELF_PROCUREMENT_MEDICAL",
    ):
        assert expected in subtypes, f"{expected} missing"


def test_lien_conference_documents_appear_for_adjudicated_tracks() -> None:
    seed = make_seed(liens={"count": 2, "resolution": "order_on_lien"})
    subtypes = plan_subtypes(seed)
    assert "NOTICE_OF_LIEN_CONFERENCE" in subtypes
    assert "PRETRIAL_CONFERENCE_STATEMENT_LIEN" in subtypes


def test_post_resolution_liens_are_dated_after_the_case_resolves() -> None:
    """The common real-world shape: the case settles, the liens keep fighting."""
    seed = make_seed(
        resolution={"type": "c_and_r"},
        liens={
            "count": 3,
            "resolution": "lien_resolution_agreement",
            "post_resolution_litigation": True,
        },
    )
    plan = build_case_plan(seed)
    resolution_date = plan.timeline.resolution_date
    assert resolution_date is not None

    lien_dates = [
        document.doc_date for document in plan.documents if document.track == "lien"
    ]
    assert lien_dates, "no lien documents were planned"
    assert min(lien_dates) > resolution_date, (
        f"lien activity started {min(lien_dates)}, on or before the case-in-chief "
        f"resolution {resolution_date}"
    )


def test_liens_without_post_resolution_litigation_run_alongside_the_case() -> None:
    seed = make_seed(
        resolution={"type": "c_and_r"},
        liens={"count": 2, "resolution": "lien_resolution_agreement"},
    )
    plan = build_case_plan(seed)
    lien_dates = [d.doc_date for d in plan.documents if d.track == "lien"]
    assert min(lien_dates) <= plan.timeline.resolution_date


# ---------------------------------------------------------------------------
# Reconsideration
# ---------------------------------------------------------------------------


def test_recon_denied_affirmed_final_closes_the_case() -> None:
    seed = make_seed(
        reconsideration={
            "enabled": True,
            "outcome": "denied",
            "post_recon": "affirmed_final",
        }
    )
    subtypes = plan_subtypes(seed)
    assert "PETITION_RECONSIDERATION_FILED" in subtypes
    assert "ORDER_ON_RECONSIDERATION" in subtypes
    # Nothing further: the award stands.
    assert "AMENDED_FINDINGS_AWARD" not in subtypes
    assert "DECLARATION_OF_READINESS" not in subtypes


def test_recon_granted_remand_further_litigation_emits_the_full_chain() -> None:
    seed = make_seed(
        reconsideration={
            "enabled": True,
            "outcome": "granted_remand",
            "post_recon": "further_litigation",
        }
    )
    subtypes = plan_subtypes(seed)
    for expected in (
        "PETITION_RECONSIDERATION_FILED",
        "PETITION_RECONSIDERATION_OPPOSITION",
        "ORDER_ON_RECONSIDERATION",
        "DECLARATION_OF_READINESS",
        "NOTICE_OF_HEARING_COURT_ISSUED",
        "MINUTES_OF_HEARING",
        "AMENDED_FINDINGS_AWARD",
    ):
        assert expected in subtypes, f"{expected} missing from the remand chain"


def test_recon_granted_remand_settled_emits_a_post_recon_settlement() -> None:
    seed = make_seed(
        reconsideration={
            "enabled": True,
            "outcome": "granted_remand",
            "post_recon": "settled",
        }
    )
    plan = build_case_plan(seed)
    subtypes = [d.subtype for d in plan.documents]
    settlement = {
        "COMPROMISE_AND_RELEASE_STANDARD",
        "COMPROMISE_AND_RELEASE_MSA",
        "COMPROMISE_AND_RELEASE_DEPENDENCY",
        "STIPULATIONS_WITH_REQUEST_FOR_AWARD",
    }
    assert settlement & set(subtypes), "no settlement document after the remand"
    assert "ORDER_APPROVING_SETTLEMENT" in subtypes

    order_date = plan.recon.order_date
    approvals = [
        d.doc_date for d in plan.documents if d.subtype == "ORDER_APPROVING_SETTLEMENT"
    ]
    assert max(approvals) > order_date, "the approving order must post-date the recon order"


def test_recon_granted_reversed_amends_the_award() -> None:
    seed = make_seed(
        reconsideration={
            "enabled": True,
            "outcome": "granted_reversed",
            "post_recon": "affirmed_final",
        }
    )
    subtypes = plan_subtypes(seed)
    assert "ORDER_ON_RECONSIDERATION" in subtypes
    assert "AMENDED_FINDINGS_AWARD" in subtypes


def test_recon_without_an_award_warns_instead_of_inventing_one() -> None:
    """A petition needs something to attack; ``pending`` has nothing."""
    seed = make_seed(
        target_stage="post_recon",
        resolution={"type": "pending"},
        reconsideration={
            "enabled": True,
            "outcome": "denied",
            "post_recon": "affirmed_final",
        },
    )
    track = build_recon_track(seed, build_timeline(seed))
    assert track.documents == ()
    assert track.warnings and "no award to reconsider" in track.warnings[0]


@pytest.mark.parametrize("rng_seed", [11, 222, 3333, 44444, 555555])
def test_recon_dates_honour_the_statutory_windows(rng_seed: int) -> None:
    """LC 5903 (25 days to petition) and LC 5909 (60 days to decide)."""
    raw = {
        "case_id": f"window-{rng_seed}",
        "rng_seed": rng_seed,
        "injury": {
            "type": "specific",
            "date_of_injury": "2021-05-04",
            "body_parts": [{"part": "shoulder", "icd10": "M75.100"}],
        },
        "lifecycle": {
            "target_stage": "post_recon",
            "resolution": {"type": "findings_award"},
            "reconsideration": {
                "enabled": True,
                "outcome": "granted_remand",
                "post_recon": "further_litigation",
            },
        },
    }
    seed = parse_case_seed(raw)
    track = build_recon_track(seed, build_timeline(seed))
    assert track.award_date and track.petition_date and track.order_date
    assert 0 <= (track.petition_date - track.award_date).days <= PETITION_WINDOW_DAYS
    assert 0 <= (track.order_date - track.petition_date).days <= ORDER_WINDOW_DAYS


# ---------------------------------------------------------------------------
# Core lifecycle
# ---------------------------------------------------------------------------


def test_denied_claim_emits_a_denial_and_an_application() -> None:
    seed = make_seed(claim_response="denied")
    subtypes = plan_subtypes(seed)
    assert "CLAIM_DENIAL_LETTER" in subtypes
    assert "APPLICATION_FOR_ADJUDICATION_ORIGINAL" in subtypes


def test_ur_dispute_emits_rfa_then_decision_then_imr_in_order() -> None:
    seed = make_seed(
        ur_dispute={"enabled": True, "decision": "upheld", "imr": True, "imr_outcome": "upheld"}
    )
    plan = build_case_plan(seed)
    dates = {d.subtype: d.doc_date for d in plan.documents}
    for expected in (
        "MEDICAL_TREATMENT_AUTHORIZATION_RFA",
        "UTILIZATION_REVIEW_DECISION_REGULAR",
        "IMR_APPLICATION_FORM",
        "IMR_DETERMINATION_FORM",
    ):
        assert expected in dates, f"{expected} missing from the UR/IMR chain"
    assert (
        dates["MEDICAL_TREATMENT_AUTHORIZATION_RFA"]
        <= dates["UTILIZATION_REVIEW_DECISION_REGULAR"]
    )
    assert dates["IMR_APPLICATION_FORM"] <= dates["IMR_DETERMINATION_FORM"]


@pytest.mark.parametrize(
    ("resolution", "expected"),
    [
        ("c_and_r", {"COMPROMISE_AND_RELEASE_STANDARD", "ORDER_APPROVING_SETTLEMENT"}),
        ("stipulations", {"STIPULATIONS_WITH_REQUEST_FOR_AWARD", "ORDER_APPROVING_SETTLEMENT"}),
        ("findings_award", {"FINDINGS_AND_AWARD", "OPINION_ON_DECISION", "MINUTES_OF_HEARING"}),
    ],
)
def test_each_resolution_emits_its_signature_documents(
    resolution: str, expected: set[str]
) -> None:
    seed = make_seed(resolution={"type": resolution})
    subtypes = set(plan_subtypes(seed))
    assert expected <= subtypes, f"missing {expected - subtypes}"


def test_death_claims_carry_death_paperwork() -> None:
    raw = {
        "case_id": "death-001",
        "rng_seed": 909,
        "injury": {
            "type": "death",
            "date_of_injury": "2022-04-01",
            "body_parts": [{"part": "head", "icd10": "S06.0X0A"}],
        },
        "lifecycle": {
            "target_stage": "resolved",
            "resolution": {"type": "stipulations"},
            "doctrine_hooks": ["death_dependency"],
        },
    }
    subtypes = set(plan_subtypes(parse_case_seed(raw)))
    for expected in (
        "DEATH_CERTIFICATE",
        "NOTICE_OF_EMPLOYEE_DEATH",
        "DEPENDENCY_DECLARATION",
        "APPLICATION_FOR_ADJUDICATION_DEATH",
    ):
        assert expected in subtypes, f"{expected} missing from the death claim"


@pytest.mark.parametrize(
    "stage",
    ["intake", "active_treatment", "discovery", "medical_legal", "pre_trial", "resolved"],
)
def test_every_target_stage_produces_documents(stage: str) -> None:
    resolution = "c_and_r" if stage in {"resolved"} else "pending"
    seed = make_seed(target_stage=stage, resolution={"type": resolution})
    plan = build_case_plan(seed)
    assert plan.document_count > 0, f"stage {stage} produced nothing"


def test_document_dates_never_precede_the_injury_or_pass_the_anchor() -> None:
    seed = make_seed(
        liens={"count": 2, "resolution": "lien_resolution_agreement"},
        reconsideration={
            "enabled": True,
            "outcome": "granted_remand",
            "post_recon": "further_litigation",
        },
    )
    plan = build_case_plan(seed)
    for document in plan.documents:
        assert plan.timeline.injury_date <= document.doc_date <= plan.timeline.horizon, (
            f"{document.subtype} dated {document.doc_date} outside "
            f"[{plan.timeline.injury_date}, {plan.timeline.horizon}]"
        )


def test_singleton_documents_are_not_multiplied_by_complexity_scaling() -> None:
    """The substrate scales complex cases 2-3x; a claim is denied only once."""
    seed = make_seed(
        claim_response="denied",
        doctrine_hooks=["ogilvie", "kite", "benson"],
    )
    subtypes = plan_subtypes(seed)
    for singleton in SINGLETON_SUBTYPES:
        assert subtypes.count(singleton) <= 1, (
            f"{singleton} appeared {subtypes.count(singleton)} times"
        )


def test_planned_subtypes_are_always_canonical() -> None:
    """No substrate-only realism subtype may reach a plan."""
    taxonomy = effective_taxonomy()
    for rng_seed in range(8):
        raw = {
            "case_id": f"canon-{rng_seed}",
            "rng_seed": 3000 + rng_seed,
            "injury": {
                "type": "specific",
                "date_of_injury": "2021-09-09",
                "body_parts": [{"part": "knee", "icd10": "M23.51"}],
            },
            "lifecycle": {
                "target_stage": "resolved",
                "resolution": {"type": "c_and_r"},
                "liens": {"count": 2, "resolution": "mixed"},
            },
        }
        for document in build_case_plan(parse_case_seed(raw)).documents:
            assert taxonomy.is_canonical(document.subtype), (
                f"{document.subtype} is not classifier vocabulary"
            )


def test_core_candidates_carry_dates_tracks_and_roles() -> None:
    seed = make_seed()
    candidates = build_core_candidates(seed, build_timeline(seed))
    assert candidates
    for candidate in candidates:
        assert isinstance(candidate.doc_date, date)
        assert candidate.track
        assert candidate.author_role
