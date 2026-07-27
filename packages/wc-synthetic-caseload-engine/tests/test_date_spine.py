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
from typing import Any

import pytest

from conftest import requires_substrate
from wc_caseload_engine.lien_machine import build_lien_tracks
from wc_caseload_engine.lifecycle_bridge import (
    MIN_RESOLUTION_LAG_DAYS,
    CaseTimeline,
    DatedCandidate,
    TimelineInvariantError,
    build_timeline,
    fit_dates,
    fit_track,
)
from wc_caseload_engine.recon_machine import build_recon_track
from wc_caseload_engine.seeds import (
    ANCHOR_DATE,
    POST_RESOLUTION_RUNWAY_DAYS,
    STAGE_RUNWAY_DAYS,
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
