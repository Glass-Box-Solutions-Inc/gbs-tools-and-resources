"""Regression tests for the date spine — runway, ordering, invariants.

Each test here reproduces a defect found by cross-model review of the Phase B
engine. The reproductions are kept verbatim rather than generalized, because a
regression test that no longer reproduces the original bug is decoration.

* **Date-spine inversion.** ``injury=2025-06-01`` seeded as ``resolved`` gave
  ``application_filed=2025-09-12`` and ``resolution=2025-06-01`` — the
  resolution clamped to ``horizon - reserve`` and fell *below* the Application.
  The reconsideration machine then dated its petition eighty days before the
  case was filed.
* **Lien/track date collapse.** Every past-horizon date was pinned to the
  horizon, so a five-document lien track came out with five identical dates and
  no legible order.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

from datetime import date, timedelta
from itertools import pairwise
from typing import Any, ClassVar

import pytest

from conftest import requires_substrate
from wc_caseload_engine.lien_machine import build_lien_tracks
from wc_caseload_engine.lifecycle_bridge import (
    MIN_RESOLUTION_LAG_DAYS,
    CaseTimeline,
    DatedCandidate,
    TimelineInvariantError,
    build_core_candidates,
    build_timeline,
    fit_dates,
    fit_track,
)
from wc_caseload_engine.recon_machine import ORDER_WINDOW_DAYS, build_recon_track
from wc_caseload_engine.seeds import (
    ANCHOR_DATE,
    DENIAL_RESPONSE_RUNWAY_DAYS,
    EVAL_RUNWAY_DAYS,
    IMR_RUNWAY_DAYS,
    POST_RESOLUTION_RUNWAY_DAYS,
    STAGE_RUNWAY_DAYS,
    UR_DISPUTE_RUNWAY_DAYS,
    AutoSpec,
    SeedValidationError,
    derive_auto_seeds,
    parse_case_seed,
    required_runway_days,
)

# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


def seed_mapping(injury_date: str, **lifecycle: Any) -> dict[str, Any]:
    """A one-body-part seed with a caller-chosen injury date and lifecycle."""
    return {
        "case_id": "runway-001",
        "rng_seed": 4242,
        "injury": {
            "type": "specific",
            "date_of_injury": injury_date,
            "body_parts": [{"part": "lumbar_spine", "icd10": "M54.5"}],
        },
        "lifecycle": {
            "target_stage": "resolved",
            "claim_response": "accepted",
            "eval_type": "qme",
            "resolution": {"type": "findings_award"},
            **lifecycle,
        },
    }


def latest_valid(required_days: int) -> date:
    """The last injury date that still leaves *required_days* of runway."""
    return ANCHOR_DATE - timedelta(days=required_days)


# ---------------------------------------------------------------------------
# 1a. Runway validation — fail loud at the seed boundary
# ---------------------------------------------------------------------------


class TestRunwayValidation:
    """The original inversion is now rejected before anything is generated."""

    def test_the_reproduction_seed_is_rejected(self) -> None:
        """injury=2025-06-01 + resolved is the seed that inverted the spine."""
        with pytest.raises(SeedValidationError) as caught:
            parse_case_seed(seed_mapping("2025-06-01"), source="repro")
        assert "injury.date_of_injury" in str(caught.value)

    def test_the_message_names_field_driver_minimum_and_latest_date(self) -> None:
        """An actionable error names all four, or the operator has to guess."""
        with pytest.raises(SeedValidationError) as caught:
            parse_case_seed(seed_mapping("2025-06-01"), source="repro")
        message = str(caught.value)
        assert "injury.date_of_injury" in message
        assert "lifecycle.target_stage 'resolved'" in message
        assert str(STAGE_RUNWAY_DAYS["resolved"]) in message
        assert latest_valid(STAGE_RUNWAY_DAYS["resolved"]).isoformat() in message

    def test_cumulative_trauma_is_measured_and_named_by_ct_end(self) -> None:
        """A CT claim's onset is the end of the exposure period, not its start."""
        raw = seed_mapping("2020-01-01")
        raw["injury"] = {
            "type": "cumulative_trauma",
            "ct_start": "2020-01-01",
            "ct_end": "2025-06-01",
            "body_parts": [{"part": "wrist", "icd10": "G56.00"}],
        }
        with pytest.raises(SeedValidationError) as caught:
            parse_case_seed(raw, source="repro")
        assert "injury.ct_end" in str(caught.value)

    @pytest.mark.parametrize("stage", sorted(STAGE_RUNWAY_DAYS))
    def test_every_stage_accepts_its_boundary_and_rejects_one_day_later(
        self, stage: str
    ) -> None:
        """The floor is exact: on it the seed loads, a day past it does not."""
        lifecycle: dict[str, Any] = {"target_stage": stage}
        if stage == "post_recon":
            lifecycle["reconsideration"] = {
                "enabled": True,
                "outcome": "denied",
                "post_recon": "affirmed_final",
            }
        if stage in {"intake", "active_treatment", "discovery", "medical_legal"}:
            lifecycle["resolution"] = {"type": "pending"}

        required = required_runway_days(parse_case_seed(
            seed_mapping(latest_valid(POST_RESOLUTION_RUNWAY_DAYS).isoformat(), **lifecycle)
        ).lifecycle)

        boundary = latest_valid(required)
        parse_case_seed(seed_mapping(boundary.isoformat(), **lifecycle))

        with pytest.raises(SeedValidationError):
            parse_case_seed(
                seed_mapping((boundary + timedelta(days=1)).isoformat(), **lifecycle)
            )

    def test_post_resolution_lien_litigation_raises_the_floor(self) -> None:
        """Liens that outlive the case need the post-resolution runway, not the stage's."""
        liens = {
            "count": 2,
            "claimants": ["medical_provider", "hospital"],
            "resolution": "lien_resolution_agreement",
            "post_resolution_litigation": True,
        }
        injury = latest_valid(STAGE_RUNWAY_DAYS["resolved"])
        with pytest.raises(SeedValidationError) as caught:
            parse_case_seed(seed_mapping(injury.isoformat(), liens=liens))
        assert "lifecycle.liens.post_resolution_litigation" in str(caught.value)

    def test_a_settled_pre_trial_case_is_held_to_the_resolved_floor(self) -> None:
        """The label says how far it got; the resolution says whether it ended."""
        injury = latest_valid(STAGE_RUNWAY_DAYS["pre_trial"])
        parse_case_seed(
            seed_mapping(injury.isoformat(), target_stage="pre_trial",
                         resolution={"type": "pending"})
        )
        with pytest.raises(SeedValidationError) as caught:
            parse_case_seed(
                seed_mapping(injury.isoformat(), target_stage="pre_trial",
                             resolution={"type": "c_and_r"})
            )
        assert "lifecycle.resolution.type 'c_and_r'" in str(caught.value)


class TestBranchRunwayFloors:
    """Runway used to be validated against the stage and the resolution only.

    A lifecycle branch is a dated document chain like any other, and three of
    them were invisible to the check: the denial response, the UR/IMR appeal
    and the medical-legal evaluation. The reproduction is a 30-day ``intake``
    seed that also says ``claim_response: denied`` — it validated, and then
    produced a denial letter, the Application answering it and the Declaration
    of Readiness advancing it, all dated 2026-01-01.
    """

    @staticmethod
    def _denied_intake(injury: str) -> dict[str, Any]:
        return {
            "case_id": "denied-intake",
            "rng_seed": 7,
            "injury": {
                "type": "specific",
                "date_of_injury": injury,
                "body_parts": [{"part": "knee", "icd10": "M23.51"}],
            },
            "lifecycle": {
                "target_stage": "intake",
                "claim_response": "denied",
                "eval_type": "none",
            },
        }

    def test_the_thirty_day_denied_reproduction_is_rejected(self) -> None:
        """The exact seed from the release review, and the message names the branch."""
        with pytest.raises(SeedValidationError) as caught:
            parse_case_seed(self._denied_intake("2025-12-02"), source="repro")
        message = str(caught.value)
        assert "lifecycle.claim_response 'denied'" in message, message
        assert str(DENIAL_RESPONSE_RUNWAY_DAYS) in message
        assert latest_valid(DENIAL_RESPONSE_RUNWAY_DAYS).isoformat() in message
        assert "injury.date_of_injury" in message

    def test_the_denial_floor_boundary_is_exact(self) -> None:
        """On the floor the seed loads; one day later it does not."""
        boundary = latest_valid(DENIAL_RESPONSE_RUNWAY_DAYS)
        parse_case_seed(self._denied_intake(boundary.isoformat()))
        with pytest.raises(SeedValidationError):
            parse_case_seed(
                self._denied_intake((boundary + timedelta(days=1)).isoformat())
            )

    @pytest.mark.parametrize(
        ("lifecycle", "days", "driver"),
        [
            ({"ur_dispute": {"enabled": True, "decision": "overturned"}},
             UR_DISPUTE_RUNWAY_DAYS, "lifecycle.ur_dispute.enabled"),
            ({"ur_dispute": {"enabled": True, "decision": "upheld", "imr": True,
                             "imr_outcome": "upheld"}},
             IMR_RUNWAY_DAYS, "lifecycle.ur_dispute.imr"),
            ({"eval_type": "qme"}, EVAL_RUNWAY_DAYS, "lifecycle.eval_type 'qme'"),
            ({"eval_type": "ame"}, EVAL_RUNWAY_DAYS, "lifecycle.eval_type 'ame'"),
        ],
    )
    def test_each_branch_floor_binds_and_names_itself(
        self, lifecycle: dict[str, Any], days: int, driver: str
    ) -> None:
        """Every branch that consumes calendar time raises the floor it needs."""
        base: dict[str, Any] = {
            "target_stage": "intake",
            "claim_response": "accepted",
            "eval_type": "none",
            **lifecycle,
        }
        raw = {
            "case_id": "branch-floor",
            "rng_seed": 11,
            "injury": {
                "type": "specific",
                "date_of_injury": latest_valid(days).isoformat(),
                "body_parts": [{"part": "knee", "icd10": "M23.51"}],
            },
            "lifecycle": base,
        }
        parse_case_seed(raw)

        raw["injury"]["date_of_injury"] = (  # type: ignore[index]
            latest_valid(days) + timedelta(days=1)
        ).isoformat()
        with pytest.raises(SeedValidationError) as caught:
            parse_case_seed(raw, source="branch")
        assert driver in str(caught.value)

    @requires_substrate
    def test_a_boundary_valid_denied_seed_orders_its_chain_strictly(self) -> None:
        """The other half of the fix: the chain is fitted, not clamped.

        Three documents that each independently overran the horizon were each
        independently pinned to it. They are one sequence — denial, then the
        Application answering it, then the DOR advancing it — so they are fitted
        as one, and strict ordering is the assertion that proves it.
        """
        seed = parse_case_seed(
            self._denied_intake(latest_valid(DENIAL_RESPONSE_RUNWAY_DAYS).isoformat())
        )
        timeline = build_timeline(seed)
        chain = {
            "CLAIM_DENIAL_LETTER": None,
            "APPLICATION_FOR_ADJUDICATION_ORIGINAL": None,
            "DECLARATION_OF_READINESS": None,
        }
        for candidate in build_core_candidates(seed, timeline):
            if candidate.subtype in chain and chain[candidate.subtype] is None:
                chain[candidate.subtype] = candidate.doc_date  # type: ignore[assignment]

        missing = [name for name, value in chain.items() if value is None]
        assert not missing, f"denial chain incomplete: {missing}"
        denial = chain["CLAIM_DENIAL_LETTER"]
        application = chain["APPLICATION_FOR_ADJUDICATION_ORIGINAL"]
        readiness = chain["DECLARATION_OF_READINESS"]
        assert denial < application < readiness, (
            f"denial chain is not strictly ordered: {denial} / {application} / {readiness}"
        )
        assert readiness <= timeline.horizon


@requires_substrate
class TestBranchChainsAreFittedNotClamped:
    """The floors alone were only half the fix, and the second review found it.

    ``TestBranchRunwayFloors`` proves a too-short seed is *rejected*. It says
    nothing about a seed that sits exactly on its floor, and those seeds were
    still building their chains with per-date clamping — so a boundary-valid
    QME seed produced a panel request, the order appointing the panel and the
    report all dated 2026-01-01, and a boundary-valid UR seed did the same to
    the RFA, the decision answering it and the denial issuing from it.

    The denial chain was fixed structurally (fitted as one track); these two
    were not. The evaluation and the UR/IMR appeal are sequences with a legal
    order — an order appointing a panel cannot precede the request for one, and
    an IMR determination cannot precede the application for it — so they get the
    same treatment.
    """

    EVAL_CHAIN = (
        "QME_PANEL_REQUEST_FORM_105",
        "ORDER_APPOINTING_QME_PANEL",
        "QME_REPORT_INITIAL",
    )
    """Panel request -> panel issuance -> report, in the only order 8 CCR 30-31.5 allows."""

    UR_CHAIN = (
        "MEDICAL_TREATMENT_AUTHORIZATION_RFA",
        "UTILIZATION_REVIEW_DECISION_REGULAR",
        "MEDICAL_TREATMENT_DENIAL_UR",
    )
    """RFA -> UR decision -> the written denial that issues from it (LC 4610)."""

    IMR_CHAIN = (*UR_CHAIN, "IMR_APPLICATION_FORM", "IMR_DETERMINATION_FORM")
    """The UR chain plus the appeal it feeds (LC 4610.5)."""

    @staticmethod
    def _boundary_seed(days: int, rng_seed: int, **lifecycle: Any) -> Any:
        """A seed whose injury sits *exactly* on the floor the branch demands."""
        return parse_case_seed(
            {
                "case_id": "branch-chain",
                "rng_seed": rng_seed,
                "injury": {
                    "type": "specific",
                    "date_of_injury": latest_valid(days).isoformat(),
                    "body_parts": [{"part": "knee", "icd10": "M23.51"}],
                },
                "lifecycle": {
                    "target_stage": "intake",
                    "claim_response": "accepted",
                    "eval_type": "none",
                    **lifecycle,
                },
            }
        )

    @staticmethod
    def _chain_dates(seed: Any, subtypes: tuple[str, ...]) -> list[tuple[str, date]]:
        """The first emitted date for each subtype, in the chain's legal order."""
        timeline = build_timeline(seed)
        found: dict[str, date] = {}
        for candidate in build_core_candidates(seed, timeline):
            if candidate.subtype in subtypes and candidate.subtype not in found:
                found[candidate.subtype] = candidate.doc_date
        missing = [name for name in subtypes if name not in found]
        assert not missing, f"chain incomplete: {missing}"
        return [(name, found[name]) for name in subtypes]

    def _assert_strict(self, seed: Any, subtypes: tuple[str, ...]) -> None:
        pairs = self._chain_dates(seed, subtypes)
        rendered = ", ".join(f"{name}={value}" for name, value in pairs)
        for (_, earlier), (later_name, later) in pairwise(pairs):
            assert earlier < later, f"{later_name} does not follow its predecessor: {rendered}"
        assert pairs[-1][1] <= build_timeline(seed).horizon

    LIFECYCLES: ClassVar[dict[str, tuple[int, dict[str, Any], tuple[str, ...]]]] = {
        "qme": (EVAL_RUNWAY_DAYS, {"eval_type": "qme"}, EVAL_CHAIN),
        "ur": (
            UR_DISPUTE_RUNWAY_DAYS,
            {"ur_dispute": {"enabled": True, "decision": "upheld"}},
            UR_CHAIN,
        ),
        "imr": (
            IMR_RUNWAY_DAYS,
            {
                "ur_dispute": {
                    "enabled": True,
                    "decision": "upheld",
                    "imr": True,
                    "imr_outcome": "upheld",
                }
            },
            IMR_CHAIN,
        ),
    }
    """Each branch at its own floor, with the chain its machine emits there."""

    @pytest.mark.parametrize("branch", sorted(LIFECYCLES))
    def test_a_boundary_valid_seed_orders_its_chain_strictly(self, branch: str) -> None:
        """The reproduction: injury exactly on the floor, chain must still order."""
        days, lifecycle, chain = self.LIFECYCLES[branch]
        self._assert_strict(self._boundary_seed(days, 4242, **lifecycle), chain)

    def test_an_overturned_ur_orders_its_authorization_after_the_decision(self) -> None:
        """The other UR branch — approval instead of denial — is a chain too."""
        seed = self._boundary_seed(
            UR_DISPUTE_RUNWAY_DAYS,
            17,
            ur_dispute={"enabled": True, "decision": "overturned"},
        )
        self._assert_strict(
            seed,
            (
                "MEDICAL_TREATMENT_AUTHORIZATION_RFA",
                "UTILIZATION_REVIEW_DECISION_REGULAR",
                "MEDICAL_TREATMENT_AUTHORIZATION",
            ),
        )

    @pytest.mark.parametrize("branch", sorted(LIFECYCLES))
    def test_thirty_boundary_seeds_all_order_strictly(self, branch: str) -> None:
        """One passing seed is an anecdote; the property has to hold across draws.

        Every date in these chains comes from an ``rng.randint``, so a single
        seed proves only that one set of draws survived. Thirty different
        ``rng_seed`` values at the same boundary injury date is the property.
        """
        days, lifecycle, chain = self.LIFECYCLES[branch]
        for rng_seed in range(1, 31):
            self._assert_strict(self._boundary_seed(days, rng_seed, **lifecycle), chain)


class TestAutoDerivedSeedsAreCompliant:
    """Auto-derivation must generate valid dates by construction, not by luck."""

    @pytest.mark.parametrize(
        "distribution",
        ["balanced", "early_stage", "settlement_heavy", "complex_litigation"],
    )
    def test_every_derived_seed_satisfies_its_own_runway(self, distribution: str) -> None:
        """Sixty draws per distribution — the validator never fires."""
        seeds = derive_auto_seeds(
            AutoSpec(count=60, distribution=distribution, rng_seed=20260727)
        )
        for seed in seeds:
            required = required_runway_days(seed.lifecycle)
            available = (ANCHOR_DATE - seed.injury.onset_date).days
            assert available >= required, (
                f"{distribution}/{seed.case_id}: {seed.lifecycle.target_stage} has "
                f"{available} days of runway, needs {required}"
            )


# ---------------------------------------------------------------------------
# 1b. Timeline invariants — floors, not silent clamps
# ---------------------------------------------------------------------------


@requires_substrate
class TestTimelineInvariants:
    """The spine holds for every seed the schema admits."""

    def test_resolution_follows_the_application_on_a_boundary_valid_seed(self) -> None:
        """The tightest legal seed is where the old clamp inverted the spine."""
        injury = latest_valid(STAGE_RUNWAY_DAYS["resolved"])
        seed = parse_case_seed(seed_mapping(injury.isoformat()))
        timeline = build_timeline(seed)

        assert timeline.application_filed_date >= timeline.injury_date
        assert timeline.resolution_date is not None
        assert timeline.resolution_date >= timeline.application_filed_date + timedelta(
            days=MIN_RESOLUTION_LAG_DAYS
        )

    def test_the_award_never_precedes_the_resolution(self) -> None:
        """A findings-and-award case's award is the resolution, never before it."""
        injury = latest_valid(POST_RESOLUTION_RUNWAY_DAYS)
        seed = parse_case_seed(
            seed_mapping(
                injury.isoformat(),
                target_stage="post_recon",
                reconsideration={
                    "enabled": True,
                    "outcome": "granted_remand",
                    "post_recon": "further_litigation",
                },
            )
        )
        timeline = build_timeline(seed)
        assert timeline.award_date is not None
        assert timeline.resolution_date is not None
        assert timeline.award_date >= timeline.resolution_date

    def test_the_petition_never_precedes_the_application(self) -> None:
        """The original symptom: a petition dated 80 days before the Application."""
        injury = latest_valid(POST_RESOLUTION_RUNWAY_DAYS)
        seed = parse_case_seed(
            seed_mapping(
                injury.isoformat(),
                target_stage="post_recon",
                reconsideration={
                    "enabled": True,
                    "outcome": "granted_remand",
                    "post_recon": "settled",
                },
            )
        )
        timeline = build_timeline(seed)
        recon = build_recon_track(seed, timeline)

        assert recon.petition_date is not None
        assert recon.petition_date > timeline.application_filed_date
        assert timeline.award_date is not None
        assert recon.petition_date > timeline.award_date

    def test_the_dataclass_rejects_an_inverted_spine_outright(self) -> None:
        """Construct the broken timeline directly; it must refuse to exist."""
        with pytest.raises(TimelineInvariantError):
            CaseTimeline(
                injury_date=date(2025, 6, 1),
                claim_filed_date=date(2025, 6, 8),
                application_filed_date=date(2025, 9, 12),
                resolution_date=date(2025, 6, 1),
                award_date=date(2025, 6, 1),
            )


# ---------------------------------------------------------------------------
# 2. Ordering-preserving compression
# ---------------------------------------------------------------------------


class TestFitDates:
    """The compression primitive, tested without a case around it."""

    def test_a_roomy_window_leaves_the_proposed_dates_alone(self) -> None:
        proposed = [date(2024, 1, 1), date(2024, 3, 1), date(2024, 6, 1)]
        assert fit_dates(
            proposed, floor=date(2023, 1, 1), ceiling=date(2025, 1, 1)
        ) == proposed

    def test_an_overflowing_chain_compresses_instead_of_stacking(self) -> None:
        """Five documents proposed past the ceiling keep five distinct dates."""
        proposed = [date(2026, 6, 1) + timedelta(days=30 * i) for i in range(5)]
        fitted = fit_dates(proposed, floor=date(2025, 1, 1), ceiling=date(2026, 1, 1))

        assert len(set(fitted)) == 5
        assert fitted == sorted(fitted)
        assert fitted[-1] <= date(2026, 1, 1)
        assert fitted[0] >= date(2025, 1, 1)

    def test_a_chain_below_the_floor_is_lifted_in_order(self) -> None:
        proposed = [date(2020, 1, 1), date(2020, 1, 1), date(2020, 1, 1)]
        fitted = fit_dates(proposed, floor=date(2024, 1, 1), ceiling=date(2025, 1, 1))
        assert fitted == [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3)]

    def test_a_window_narrower_than_the_chain_saturates_without_inverting(self) -> None:
        """Not reachable through the schema, but it must degrade, not scramble."""
        proposed = [date(2026, 1, 1) + timedelta(days=i) for i in range(5)]
        fitted = fit_dates(proposed, floor=date(2026, 1, 1), ceiling=date(2026, 1, 2))
        assert fitted == sorted(fitted)
        assert all(date(2026, 1, 1) <= value <= date(2026, 1, 2) for value in fitted)

    def test_fit_track_raises_when_a_roomy_window_still_ties(self) -> None:
        """A guard on the fit itself — ties in a roomy window mean a bug here."""
        candidates = [
            DatedCandidate(subtype="A", doc_date=date(2024, 1, 1)),
            DatedCandidate(subtype="B", doc_date=date(2024, 1, 1)),
        ]
        fitted = fit_track(
            candidates, floor=date(2024, 1, 1), ceiling=date(2024, 12, 31), label="probe"
        )
        assert fitted[0].doc_date < fitted[1].doc_date


@requires_substrate
class TestLienTrackOrdering:
    """The five-lien-documents-on-one-day reproduction."""

    @staticmethod
    def _post_resolution_seed() -> Any:
        injury = latest_valid(POST_RESOLUTION_RUNWAY_DAYS + 30)
        return parse_case_seed(
            seed_mapping(
                injury.isoformat(),
                resolution={"type": "c_and_r"},
                liens={
                    "count": 3,
                    "claimants": ["medical_provider", "hospital", "pharmacy"],
                    "resolution": "lien_resolution_agreement",
                    "post_resolution_litigation": True,
                },
            )
        )

    def test_every_track_is_strictly_increasing(self) -> None:
        seed = self._post_resolution_seed()
        tracks = build_lien_tracks(seed, build_timeline(seed))

        assert tracks
        for track in tracks:
            dates = [document.doc_date for document in track.documents]
            assert len(set(dates)) == len(dates), (
                f"lien track {track.index} ({track.claimant}) repeats a date: {dates}"
            )
            assert dates == sorted(dates)

    def test_post_resolution_tracks_start_after_the_resolution(self) -> None:
        seed = self._post_resolution_seed()
        timeline = build_timeline(seed)
        tracks = build_lien_tracks(seed, timeline)

        assert timeline.resolution_date is not None
        for track in tracks:
            for document in track.documents:
                assert document.doc_date > timeline.resolution_date

    def test_a_post_resolution_track_may_run_past_the_case_horizon(self) -> None:
        """Extending the track horizon is the fix; compressing it was the bug.

        The ordering matters more than the anchor: post-resolution lien practice
        genuinely outlives the case-in-chief, so the track is allowed past the
        horizon rather than squeezed into the days before it.
        """
        seed = self._post_resolution_seed()
        timeline = build_timeline(seed)
        tracks = build_lien_tracks(seed, timeline)

        documents = [doc for track in tracks for doc in track.documents]
        assert documents
        assert all(doc.doc_date > timeline.injury_date for doc in documents)

    def test_a_concurrent_track_stays_inside_the_case_horizon(self) -> None:
        """Without post-resolution litigation the horizon still binds."""
        injury = latest_valid(STAGE_RUNWAY_DAYS["resolved"] + 200)
        seed = parse_case_seed(
            seed_mapping(
                injury.isoformat(),
                resolution={"type": "c_and_r"},
                liens={"count": 2, "claimants": ["medical_provider", "edd"],
                       "resolution": "lien_stipulation"},
            )
        )
        timeline = build_timeline(seed)
        for track in build_lien_tracks(seed, timeline):
            for document in track.documents:
                assert document.doc_date <= timeline.horizon


@requires_substrate
class TestReconTrackOrdering:
    """The reconsideration round trip is a chain, and reads like one."""

    def test_the_round_trip_is_strictly_ordered(self) -> None:
        injury = latest_valid(POST_RESOLUTION_RUNWAY_DAYS + 60)
        seed = parse_case_seed(
            seed_mapping(
                injury.isoformat(),
                target_stage="post_recon",
                reconsideration={
                    "enabled": True,
                    "outcome": "granted_remand",
                    "post_recon": "further_litigation",
                },
            )
        )
        recon = build_recon_track(seed, build_timeline(seed))
        dates = [document.doc_date for document in recon.documents]

        assert len(dates) >= 6
        assert len(set(dates)) == len(dates), f"recon chain repeats a date: {dates}"
        assert dates == sorted(dates)

    def test_the_order_on_reconsideration_follows_the_petition(self) -> None:
        injury = latest_valid(POST_RESOLUTION_RUNWAY_DAYS)
        seed = parse_case_seed(
            seed_mapping(
                injury.isoformat(),
                target_stage="post_recon",
                reconsideration={
                    "enabled": True,
                    "outcome": "denied",
                    "post_recon": "affirmed_final",
                },
            )
        )
        recon = build_recon_track(seed, build_timeline(seed))
        assert recon.petition_date is not None
        assert recon.order_date is not None
        assert recon.order_date > recon.petition_date


# ---------------------------------------------------------------------------
# 1d. Reconsideration briefing order — legal sequence, not date sort
# ---------------------------------------------------------------------------


RECON_BRIEFING_ORDER: tuple[str, ...] = (
    "PETITION_RECONSIDERATION_FILED",
    "PETITION_RECONSIDERATION_OPPOSITION",
    "PETITION_RECONSIDERATION_REPLY",
    "ORDER_ON_RECONSIDERATION",
)
"""The briefing sequence, in the only order it can legally occur.

The petitioner petitions, the respondent opposes, the petitioner may reply, and
only then does the Board rule. Every step is a response to the one before it,
which is what makes the order structural rather than stylistic.
"""


class TestReconBriefingOrder:
    """A reply filed after the ruling it replies to is not a document, it is a bug.

    ``recon_machine`` drew the order independently of the briefing schedule and
    then sorted the whole chain by ``(date, subtype)``. The sort faithfully
    recorded whatever the independent draws produced, so an order drawn at
    petition+30 and a reply drawn at opposition+15 came out in that order — the
    Board ruling first, the petitioner's reply filed the day after.
    """

    @staticmethod
    def _seed(rng_seed: int) -> Any:
        return parse_case_seed(
            {
                "case_id": f"recon-{rng_seed}",
                "rng_seed": rng_seed,
                "injury": {
                    "type": "specific",
                    "date_of_injury": "2022-01-05",
                    "body_parts": [{"part": "knee", "icd10": "M23.51"}],
                },
                "lifecycle": {
                    "target_stage": "post_recon",
                    "resolution": {"type": "findings_award"},
                    "reconsideration": {
                        "enabled": True,
                        "outcome": "denied",
                        "post_recon": "affirmed_final",
                    },
                },
            }
        )

    @staticmethod
    def _briefing_dates(documents: Any) -> dict[str, date]:
        wanted = set(RECON_BRIEFING_ORDER)
        return {
            document.subtype: document.doc_date
            for document in documents
            if document.subtype in wanted
        }

    def test_the_rng_seed_155_reproduction_files_the_reply_before_the_order(self) -> None:
        """The exact seed from the release review, which had reply == order + 1."""
        seed = self._seed(155)
        recon = build_recon_track(seed, build_timeline(seed))
        dates = self._briefing_dates(recon.documents)

        assert "PETITION_RECONSIDERATION_REPLY" in dates, (
            "this seed must draw a reply, or the reproduction proves nothing"
        )
        assert dates["PETITION_RECONSIDERATION_REPLY"] < dates["ORDER_ON_RECONSIDERATION"], (
            f"reply {dates['PETITION_RECONSIDERATION_REPLY']} does not precede order "
            f"{dates['ORDER_ON_RECONSIDERATION']}"
        )

    def test_the_briefing_invariant_holds_over_fifty_seeds(self) -> None:
        """Property-style: petition < opposition < reply < order, strictly, always."""
        offences: list[str] = []
        replies = 0
        for rng_seed in range(50):
            seed = self._seed(rng_seed)
            recon = build_recon_track(seed, build_timeline(seed))
            dates = self._briefing_dates(recon.documents)
            if "PETITION_RECONSIDERATION_REPLY" in dates:
                replies += 1

            sequence = [
                (subtype, dates[subtype])
                for subtype in RECON_BRIEFING_ORDER
                if subtype in dates
            ]
            for (earlier, earlier_date), (later, later_date) in pairwise(sequence):
                if later_date <= earlier_date:
                    offences.append(
                        f"rng_seed={rng_seed}: {later} ({later_date}) does not follow "
                        f"{earlier} ({earlier_date})"
                    )

        assert replies >= 10, (
            f"only {replies}/50 seeds drew a reply — the invariant is barely exercised"
        )
        assert not offences, f"{len(offences)} ordering violation(s): {offences[:10]}"

    def test_the_order_still_lands_inside_the_statutory_window_when_it_can(self) -> None:
        """LC 5909 is honoured except where the briefing schedule outruns it.

        Constraining the order to follow the last brief can push it past sixty
        days from the petition. That is the right trade — a ruling a few days
        late is an ordinary file, a ruling that predates the briefing is not —
        but it should stay the exception, so the exception is counted.
        """
        late = 0
        for rng_seed in range(50):
            seed = self._seed(rng_seed)
            recon = build_recon_track(seed, build_timeline(seed))
            assert recon.petition_date is not None
            assert recon.order_date is not None
            if (recon.order_date - recon.petition_date).days > ORDER_WINDOW_DAYS:
                late += 1
        assert late <= 10, f"{late}/50 orders fell outside the LC 5909 window"
