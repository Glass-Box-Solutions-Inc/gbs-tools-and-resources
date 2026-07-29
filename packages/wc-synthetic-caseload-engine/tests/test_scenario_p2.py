"""AJC-37 Phase 2 — treatment trajectory, surgery depth, diagnostics depth.

Same discipline as the Phase-1 harness: every knob carries a counterfactual
where the draw it supersedes would have said something else, so a knob that
silently fails to reach the plan cannot pass by coincidence. Phase 1 shipped
that bug — 32 tests on one `rng_seed` whose coin happened to agree — and the
pattern below is the standing answer to it.

Seeds are varied deliberately. A shared seed across a suite is a monoculture,
and monocultures hide exactly the class of defect this file exists to catch.
"""

from __future__ import annotations

import inspect
import json
import re
from datetime import date
from itertools import pairwise
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from conftest import extract_text, requires_substrate
from wc_caseload_engine.case_facts import (
    SUBSTRATE_STATUS_PHRASES,
    TRAJECTORY_PHRASES,
    SurgeryFact,
    _derive_visits,
)
from wc_caseload_engine.fact_templates import (
    _SUBSTRATE_HISTORY_IMAGING as SUBSTRATE_HISTORY_IMAGING,
)
from wc_caseload_engine.manifests import MANIFEST_NAME, generate_case
from wc_caseload_engine.modality_audit import MODALITY_SITES, is_excluded, sites_for
from wc_caseload_engine.planner import (
    NEVER_TREATED_SUPPRESSED_TYPES,
    NEVER_TREATED_TIER,
    POST_DISCHARGE_FORBIDDEN,
    build_case_plan,
)
from wc_caseload_engine.seeds import parse_case_seed
from wc_caseload_engine.substrate import import_substrate


def _flat(text: str) -> str:
    """Extracted PDF text with reportlab's line wrapping removed."""
    return re.sub(r"\s+", " ", text).strip().lower()

pytestmark = requires_substrate


def _body(case_id: str, **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "case_id": case_id,
        "rng_seed": 7100,
        "injury": {
            "type": "specific",
            "date_of_injury": "2022-04-11",
            "body_parts": [{"part": "lumbar_spine"}, {"part": "shoulder"}],
        },
        "lifecycle": {"target_stage": "medical_legal", "eval_type": "qme"},
        "documents": {"format_mix": {"pdf": 1.0}},
        "output": {"formats": ["pdf"]},
    }
    body.update(overrides)
    return body


def _seed(case_id: str, **overrides: Any) -> Any:
    return parse_case_seed(_body(case_id, **overrides))


def _render(seed: Any, out_dir: Path) -> tuple[dict[str, Any], dict[str, str]]:
    generate_case(seed, out_dir, case_number=1)
    case_dir = out_dir / seed.case_id
    manifest = json.loads((case_dir / MANIFEST_NAME).read_text())
    texts: dict[str, str] = {}
    for entry in manifest["documents"]:
        path = case_dir / "documents" / entry["filename"]
        texts.setdefault(entry["subtype"], "")
        texts[entry["subtype"]] += "\n" + (extract_text(path, entry["format"]) or "")
    return manifest, texts


# ---------------------------------------------------------------------------
# ISC-101 — the treatment block, and what it refuses
# ---------------------------------------------------------------------------


class TestTheTreatmentBlockLoads:
    @pytest.mark.parametrize("status", ["ongoing", "discharged", "gap", "never_treated"])
    def test_every_status_is_accepted(self, status: str) -> None:
        seed = _seed(f"t-{status}", scenario={"treatment": {"status": status}})
        assert seed.scenario.treatment.status == status

    def test_an_unknown_status_is_refused_by_name(self) -> None:
        with pytest.raises(ValueError, match="never_treated"):
            _seed("t-bad", scenario={"treatment": {"status": "sporadic"}})

    def test_provider_count_is_accepted(self) -> None:
        seed = _seed("t-prov", scenario={"treatment": {"providers": 5}})
        assert seed.scenario.treatment.providers == 5


class TestTheTreatmentBlockRefusesIncoherentCombinations:
    """Cross-validation names the conflicting field, not just the conflict.

    An error that says "these are incompatible" leaves the author guessing
    which one to change. Each message below names both fields and states which
    edit resolves it.
    """

    def test_never_treated_with_surgery_is_refused(self) -> None:
        with pytest.raises(ValueError) as exc:
            _seed(
                "t-clash-surg",
                scenario={"treatment": {"status": "never_treated"}, "surgery": "performed"},
            )
        message = str(exc.value)
        assert "scenario.treatment.status" in message
        assert "scenario.surgery" in message

    @pytest.mark.parametrize("claimant", ["medical_provider", "hospital", "pharmacy"])
    def test_never_treated_with_a_treatment_lien_is_refused(self, claimant: str) -> None:
        with pytest.raises(ValueError) as exc:
            _seed(
                "t-clash-lien",
                scenario={"treatment": {"status": "never_treated"}},
                lifecycle={
                    "target_stage": "medical_legal",
                    "eval_type": "qme",
                    "liens": {"count": 1, "claimants": [claimant]},
                },
            )
        message = str(exc.value)
        assert "scenario.treatment.status" in message
        assert claimant in message

    def test_never_treated_tolerates_a_non_treatment_lien(self) -> None:
        """EDD and attorney costs do not imply anyone provided treatment."""
        seed = _seed(
            "t-edd",
            scenario={"treatment": {"status": "never_treated"}},
            lifecycle={
                "target_stage": "medical_legal",
                "eval_type": "qme",
                "liens": {"count": 1, "claimants": ["edd"]},
            },
        )
        assert seed.scenario.treatment.status == "never_treated"

    def test_never_treated_with_surgery_none_is_fine(self) -> None:
        seed = _seed(
            "t-ok", scenario={"treatment": {"status": "never_treated"}, "surgery": "none"}
        )
        assert seed.scenario.surgery == "none"


# ---------------------------------------------------------------------------
# ISC-107/108 — surgery depth
# ---------------------------------------------------------------------------


class TestTheSurgeryEnumGrew:
    @pytest.mark.parametrize("value", ["none", "performed", "recommended", "denied_by_ur"])
    def test_every_value_is_accepted(self, value: str) -> None:
        body = _body(f"s-{value}", scenario={"surgery": value})
        if value == "denied_by_ur":
            body["lifecycle"]["ur_dispute"] = {"enabled": True, "decision": "upheld"}
        assert parse_case_seed(body).scenario.surgery == value

    def test_denied_by_ur_without_a_ur_dispute_is_refused_actionably(self) -> None:
        """The seed is the contract: name the missing field, do not invent it."""
        with pytest.raises(ValueError) as exc:
            _seed("s-nour", scenario={"surgery": "denied_by_ur"})
        message = str(exc.value)
        assert "lifecycle.ur_dispute" in message, message
        assert "enabled" in message, message

    def test_denied_by_ur_with_a_ur_dispute_loads(self) -> None:
        seed = _seed(
            "s-ur",
            scenario={"surgery": "denied_by_ur"},
            lifecycle={
                "target_stage": "medical_legal",
                "eval_type": "qme",
                "ur_dispute": {"enabled": True, "decision": "upheld"},
            },
        )
        assert seed.scenario.surgery == "denied_by_ur"


# ---------------------------------------------------------------------------
# ISC-102 — never_treated empties the treatment record
# ---------------------------------------------------------------------------


class TestNeverTreatedEmptiesTheTreatmentRecord:
    def test_no_treating_reports_diagnostics_or_billing_survive(self) -> None:
        plan = build_case_plan(
            _seed("nt-plan", scenario={"treatment": {"status": "never_treated"}})
        )
        offenders = [
            d.subtype
            for d in plan.documents
            if d.parent_type in NEVER_TREATED_SUPPRESSED_TYPES
            and d.subtype not in NEVER_TREATED_TIER
        ]
        assert not offenders, f"never_treated case still plans a course of care: {offenders}"

    def test_the_counterfactual_case_is_full_of_them(self) -> None:
        """Opposite-draw: the same seed without the knob keeps its treatment record."""
        plan = build_case_plan(_seed("nt-plan"))
        kept = [
            d.subtype
            for d in plan.documents
            if d.parent_type in NEVER_TREATED_SUPPRESSED_TYPES
            and d.subtype not in NEVER_TREATED_TIER
        ]
        assert kept, "the control case has no treatment documents; suppression proves nothing"

    def test_the_ledger_records_a_single_visit(self) -> None:
        facts = build_case_plan(
            _seed("nt-ledger", rng_seed=7211, scenario={"treatment": {"status": "never_treated"}})
        ).case_facts
        assert facts is not None
        assert [v.kind for v in facts.visits] == ["initial"]

    def test_the_suppression_is_warned_about(self) -> None:
        plan = build_case_plan(
            _seed("nt-warn", scenario={"treatment": {"status": "never_treated"}})
        )
        assert any("never_treated" in w for w in plan.warnings), plan.warnings


# ---------------------------------------------------------------------------
# ISC-103 / ISC-104 — gap and discharge
# ---------------------------------------------------------------------------


class TestTheGapIsInTheDates:
    def test_the_visit_series_contains_a_gap_wider_than_the_cadence(self) -> None:
        """The gap is real on any case, however short its runway."""
        facts = build_case_plan(
            _seed("gap-1", rng_seed=7302, scenario={"treatment": {"status": "gap"}})
        ).case_facts
        assert facts is not None
        span = facts.treatment_gap
        assert span is not None
        assert (span[1] - span[0]).days > 45, "the gap is no wider than ordinary follow-up"

    def test_a_long_runway_gets_the_full_seeded_gap(self) -> None:
        """Where the timeline can hold it, the gap is the length that was drawn.

        Exercised against ``_derive_visits`` directly with a deliberately long
        horizon rather than through a seed, because every lifecycle this engine
        builds has a runway shorter than the largest gap in the pool — so a
        seed-level test would only ever prove the clamped path. Both paths
        matter and this is the one the clamp hides.
        """
        seed = _seed("gap-unclamped", rng_seed=7304)
        timeline = SimpleNamespace(
            injury_date=date(2022, 4, 11),
            resolution_date=date(2026, 4, 11),  # four years of room
            application_filed_date=date(2022, 8, 23),
        )
        visits = _derive_visits(seed, timeline, SurgeryFact(status="none"), "gap")
        spans = [(b.date - a.date).days for a, b in pairwise(visits)]
        assert max(spans) - 45 in (120, 150, 180, 210), spans

    def test_a_short_runway_shortens_the_gap_rather_than_dropping_it(self) -> None:
        """The clamp is the honest behaviour, and it must not clamp to zero."""
        seed = _seed("gap-clamped", rng_seed=7305)
        timeline = SimpleNamespace(
            injury_date=date(2022, 4, 11),
            resolution_date=date(2022, 10, 1),
            application_filed_date=date(2022, 8, 23),
        )
        visits = _derive_visits(seed, timeline, SurgeryFact(status="none"), "gap")
        spans = [(b.date - a.date).days for a, b in pairwise(visits)]
        assert max(spans) > 45, "the gap was clamped away entirely"

    def test_a_case_without_the_knob_has_no_gap(self) -> None:
        """Opposite-draw: the same arc, minus the knob, has evenly spaced visits."""
        facts = build_case_plan(_seed("gap-control", rng_seed=7302)).case_facts
        assert facts is not None
        assert facts.treatment_gap is None
        spans = [
            (b.date - a.date).days for a, b in pairwise(facts.visits)
        ]
        assert spans and max(spans) < 120, spans

    def test_visits_stay_ordered_across_the_gap(self) -> None:
        facts = build_case_plan(
            _seed("gap-order", rng_seed=7303, scenario={"treatment": {"status": "gap"}})
        ).case_facts
        assert facts is not None
        dates = [v.date for v in facts.visits]
        assert dates == sorted(dates)


class TestDischargeEndsTheRecord:
    def test_a_discharge_summary_is_emitted(self) -> None:
        plan = build_case_plan(
            _seed("dis-1", rng_seed=7401, scenario={"treatment": {"status": "discharged"}})
        )
        assert any(d.subtype == "DISCHARGE_SUMMARY" for d in plan.documents)

    def test_no_treating_report_post_dates_the_discharge(self) -> None:
        plan = build_case_plan(
            _seed("dis-2", rng_seed=7402, scenario={"treatment": {"status": "discharged"}})
        )
        assert plan.case_facts is not None
        discharge = plan.case_facts.discharge_date
        assert discharge is not None
        late = [
            (d.subtype, d.doc_date)
            for d in plan.documents
            if d.subtype in POST_DISCHARGE_FORBIDDEN and d.doc_date > discharge
        ]
        assert not late, f"treating documents after discharge {discharge}: {late}"

    def test_the_discharge_summary_does_not_call_itself_an_operative_report(
        self, tmp_path: Path
    ) -> None:
        """The trap: DISCHARGE_SUMMARY renders through OperativeRecord."""
        seed = _seed(
            "dis-title",
            rng_seed=7403,
            scenario={"treatment": {"status": "discharged"}, "surgery": "none"},
        )
        _, texts = _render(seed, tmp_path)
        body = texts.get("DISCHARGE_SUMMARY", "")
        assert body, "no discharge summary rendered"
        assert "OPERATIVE REPORT" not in body
        assert "DISCHARGE SUMMARY" in body
        assert "DISPOSITION" in body


# ---------------------------------------------------------------------------
# ISC-105 — the trajectory is monotone
# ---------------------------------------------------------------------------


class TestTreatingReportsFollowOneTrajectory:
    def test_phrases_advance_and_never_reverse(self) -> None:
        facts = build_case_plan(_seed("traj", rng_seed=7501)).case_facts
        assert facts is not None
        arc = TRAJECTORY_PHRASES[facts.trajectory]
        positions = [arc.index(facts.phrase_for(i)) for i in range(6)]
        assert positions == sorted(positions), positions
        assert positions[-1] == len(arc) - 1, "the arc wrapped instead of holding"

    def test_every_phrase_belongs_to_exactly_one_arc(self) -> None:
        """A phrase shared between arcs would make the trajectory unreadable."""
        everything = [p for arc in TRAJECTORY_PHRASES.values() for p in arc]
        assert len(everything) == len(set(everything))

    def test_the_substrate_pool_it_replaces_is_pinned(self) -> None:
        """If the substrate's list moves the shim stops firing — fail loudly here."""
        source = inspect.getsource(
            import_substrate("pdf_templates.medical.treating_physician_report")
        )
        for phrase in SUBSTRATE_STATUS_PHRASES:
            assert phrase in source, (
                f"{phrase!r} is no longer in the substrate; the trajectory override "
                "is silently reverting to a random draw"
            )

    def test_rendered_reports_carry_the_ledger_phrase(self, tmp_path: Path) -> None:
        seed = _seed(
            "traj-render",
            rng_seed=7502,
            documents={
                "overrides": [{"subtype": "TREATING_PHYSICIAN_REPORT_PR2", "count": 3}],
                "format_mix": {"pdf": 1.0},
            },
        )
        plan = build_case_plan(seed)
        assert plan.case_facts is not None
        _, texts = _render(seed, tmp_path)
        body = _flat(texts.get("TREATING_PHYSICIAN_REPORT_PR2", ""))
        assert body
        arc = TRAJECTORY_PHRASES[plan.case_facts.trajectory]
        assert any(p.lower() in body for p in arc), (
            f"no {plan.case_facts.trajectory} phrase in the rendered reports"
        )
        foreign = [
            p
            for name, other in TRAJECTORY_PHRASES.items()
            if name != plan.case_facts.trajectory
            for p in other
        ]
        assert not [p for p in foreign if p.lower() in body], "a phrase from another arc appeared"


# ---------------------------------------------------------------------------
# ISC-106 — roster size
# ---------------------------------------------------------------------------


class TestTheProviderRosterFollowsTheSeed:
    @pytest.mark.parametrize("count", [1, 2, 4])
    def test_the_ledger_holds_exactly_the_requested_number(self, count: int) -> None:
        facts = build_case_plan(
            _seed(
                f"prov-{count}",
                rng_seed=7600 + count,
                scenario={"treatment": {"providers": count}},
            )
        ).case_facts
        assert facts is not None
        assert len(facts.providers) == count

    def test_the_manifest_agrees(self, tmp_path: Path) -> None:
        seed = _seed("prov-manifest", rng_seed=7610, scenario={"treatment": {"providers": 3}})
        manifest, _ = _render(seed, tmp_path)
        assert len(manifest["caseFacts"]["providers"]) == 3


# ---------------------------------------------------------------------------
# ISC-107 / ISC-108 / ISC-109 — surgery depth
# ---------------------------------------------------------------------------


class TestProposedSurgeryEmitsNoOperation:
    @pytest.mark.parametrize("status", ["recommended", "denied_by_ur"])
    def test_zero_operative_documents(self, status: str) -> None:
        body = _body(f"prop-{status}", scenario={"surgery": status}, rng_seed=7700)
        if status == "denied_by_ur":
            body["lifecycle"]["ur_dispute"] = {"enabled": True, "decision": "upheld"}
        plan = build_case_plan(parse_case_seed(body))
        assert not [d.subtype for d in plan.documents if "OPERATIVE" in d.subtype]
        assert plan.case_facts is not None
        assert plan.case_facts.surgery.cpt_code, "a proposed procedure still names a CPT"

    def test_the_recommendation_reaches_the_treating_report(self, tmp_path: Path) -> None:
        seed = _seed(
            "prop-text",
            rng_seed=7701,
            scenario={"surgery": "recommended"},
            documents={
                "overrides": [{"subtype": "TREATING_PHYSICIAN_REPORT_PR2", "count": 1}],
                "format_mix": {"pdf": 1.0},
            },
        )
        plan = build_case_plan(seed)
        _, texts = _render(seed, tmp_path)
        body = _flat(texts.get("TREATING_PHYSICIAN_REPORT_PR2", ""))
        assert plan.case_facts is not None
        assert "recommended" in body
        assert plan.case_facts.surgery.cpt_code in body
        assert "status post" not in body, "a proposed surgery is described as having happened"

    def test_the_denial_reaches_the_treating_report(self, tmp_path: Path) -> None:
        body = _body(
            "denied-text",
            rng_seed=7702,
            scenario={"surgery": "denied_by_ur"},
            documents={
                "overrides": [{"subtype": "TREATING_PHYSICIAN_REPORT_PR2", "count": 1}],
                "format_mix": {"pdf": 1.0},
            },
        )
        body["lifecycle"]["ur_dispute"] = {"enabled": True, "decision": "upheld"}
        _, texts = _render(parse_case_seed(body), tmp_path)
        text = _flat(texts.get("TREATING_PHYSICIAN_REPORT_PR2", ""))
        assert "denied" in text
        assert "request for authorization" in text


class TestAStatedSurgeryIsAlwaysDocumented:
    @pytest.mark.parametrize("rng_seed", [7801, 7802, 7803, 7804])
    def test_the_floor_holds_across_seeds(self, rng_seed: int) -> None:
        """ISC-109. Includes seeds whose coin says no — the opposite-draw case."""
        plan = build_case_plan(
            _seed(f"floor-{rng_seed}", rng_seed=rng_seed, scenario={"surgery": "performed"})
        )
        operative = [
            d.subtype for d in plan.documents if d.subtype == "OPERATIVE_HOSPITAL_RECORDS"
        ]
        assert operative, "a stated surgery produced no operative document"

    def test_at_least_one_fixture_seed_disagrees_with_the_coin(self) -> None:
        """Guard the guard: the floor is only meaningful where the coin says no."""
        disagreeing = [
            s
            for s in (7801, 7802, 7803, 7804)
            if not _seed(f"c-{s}", rng_seed=s).rng("clinical").random() < 0.35
        ]
        assert disagreeing, "every floor fixture's coin already said surgery"


# ---------------------------------------------------------------------------
# ISC-110 / ISC-111 — diagnostics depth
# ---------------------------------------------------------------------------


class TestImagingReportsNameTheirRegion:
    def test_the_examined_region_is_the_ledger_body_part(self, tmp_path: Path) -> None:
        seed = _seed(
            "region",
            rng_seed=7901,
            scenario={
                "diagnostics": {"performed": [{"modality": "mri", "body_part": "shoulder"}]}
            },
            documents={
                "overrides": [{"subtype": "DIAGNOSTICS_IMAGING", "count": 1}],
                "format_mix": {"pdf": 1.0},
            },
        )
        _, texts = _render(seed, tmp_path)
        body = _flat(texts.get("DIAGNOSTICS_IMAGING", ""))
        assert "examined region" in body
        assert "shoulder" in body


class TestTheQmeHistoryIsGoverned:
    def test_the_history_names_no_absent_modality(self, tmp_path: Path) -> None:
        seed = _seed(
            "hist",
            rng_seed=7902,
            scenario={
                "diagnostics": {
                    "performed": [{"modality": "xray", "body_part": "lumbar_spine"}],
                    "absent": [{"modality": "mri", "body_part": "lumbar_spine"}],
                }
            },
            documents={
                "overrides": [{"subtype": "QME_REPORT_INITIAL", "count": 1}],
                "format_mix": {"pdf": 1.0},
            },
        )
        _, texts = _render(seed, tmp_path)
        body = _flat(texts.get("QME_REPORT_INITIAL", ""))
        assert body
        assert "diagnostic imaging was obtained including" in body
        claim = body.split("diagnostic imaging was obtained including", 1)[1][:200]
        assert "mri" not in claim, f"the history announces an absent MRI: {claim!r}"

    def test_the_substrate_pool_it_replaces_is_pinned(self) -> None:
        source = inspect.getsource(import_substrate("pdf_templates.medical.qme_ame_report"))
        for phrase in SUBSTRATE_HISTORY_IMAGING:
            assert phrase in source, (
                f"{phrase!r} is no longer in the substrate; the history override is "
                "silently reverting to a random draw"
            )


# ---------------------------------------------------------------------------
# ISC-114 — keep-and-warn parity
# ---------------------------------------------------------------------------


class TestOverridingASubstrateExclusionWarns:
    def test_surgery_on_a_psych_claim_is_honoured_and_warned(self) -> None:
        plan = build_case_plan(
            _seed(
                "psych-surg",
                rng_seed=8001,
                injury={
                    "type": "specific",
                    "date_of_injury": "2022-04-11",
                    "body_parts": [{"part": "psyche"}, {"part": "lumbar_spine"}],
                },
                scenario={"surgery": "performed"},
            )
        )
        assert plan.case_facts is not None
        assert plan.case_facts.surgery.performed, "the seed was silently overruled"
        assert any("psychiatric claim" in w for w in plan.warnings), plan.warnings

    def test_an_ordinary_case_warns_about_nothing_new(self) -> None:
        plan = build_case_plan(_seed("no-warn", rng_seed=8002, scenario={"surgery": "performed"}))
        assert not [w for w in plan.warnings if "excludes from surgery" in w]


# ---------------------------------------------------------------------------
# ISC-112 — the modality audit table
# ---------------------------------------------------------------------------

MODALITY_PATTERN = re.compile(
    r"\b(MRI|CT scan|X-[Rr]ay|X-rays|EMG|NCV|nerve conduction|[Ee]lectrodiagnostic"
    r"|radiograph[a-z]*)\b"
)


def _substrate_modality_hits() -> dict[str, list[tuple[int, str]]]:
    """Every substrate line naming a modality, keyed by substrate-relative path."""
    root = Path(import_substrate("data.wc_constants").__file__).parent.parent
    hits: dict[str, list[tuple[int, str]]] = {}
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        if is_excluded(rel):
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if MODALITY_PATTERN.search(line):
                hits.setdefault(rel, []).append((number, line.strip()))
    return hits


class TestTheModalityAuditTableIsComplete:
    """The enumeration behind the ledger's promise, kept honest by a grep.

    Phase 1 governed the diagnostic report and believed the job done; the QME
    named modalities in three other places, each discovered one failing test at
    a time. This test is the alternative to discovering the fourth the same way.
    """

    def test_every_naming_file_is_listed(self) -> None:
        listed = {site.path for site in MODALITY_SITES}
        found = set(_substrate_modality_hits())
        missing = sorted(found - listed)
        assert not missing, (
            f"substrate files name a modality but are absent from MODALITY_SITES: "
            f"{missing}. Add a row for each — governed or documented-with-reason."
        )

    def test_every_listed_file_still_names_a_modality(self) -> None:
        """The table must not accumulate rows for sites that no longer exist."""
        listed = {site.path for site in MODALITY_SITES}
        found = set(_substrate_modality_hits())
        stale = sorted(listed - found)
        assert not stale, f"MODALITY_SITES lists files that name no modality: {stale}"

    def test_every_naming_line_matches_a_row_marker(self) -> None:
        """Line-level coverage, so a *new* site in a known file fails too."""
        uncovered: list[str] = []
        for path, lines in _substrate_modality_hits().items():
            markers = [site.marker for site in sites_for(path)]
            for number, text in lines:
                if not any(marker in text for marker in markers):
                    uncovered.append(f"{path}:{number}: {text[:90]}")
        assert not uncovered, (
            "substrate lines name a modality and match no MODALITY_SITES marker:\n"
            + "\n".join(uncovered[:20])
        )

    def test_every_row_states_who_governs_it(self) -> None:
        for site in MODALITY_SITES:
            assert site.disposition in ("governed", "documented")
            assert site.by.strip(), f"{site.path} row states no reason"

    def test_the_governed_rows_cover_the_flagship_templates(self) -> None:
        governed = {site.path for site in MODALITY_SITES if site.disposition == "governed"}
        assert "pdf_templates/medical/diagnostic_report.py" in governed
        assert "pdf_templates/medical/qme_ame_report.py" in governed
