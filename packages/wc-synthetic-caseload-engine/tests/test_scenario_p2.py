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
from typing import Any, get_args

import pytest

import wc_caseload_engine
from conftest import extract_text, requires_substrate
from wc_caseload_engine.case_facts import (
    SUBSTRATE_STATUS_PHRASES,
    SURGERY_CPT_CODES,
    TRAJECTORY_PHRASES,
    SurgeryFact,
    _derive_visits,
)
from wc_caseload_engine.cli import cli
from wc_caseload_engine.fact_templates import (
    _SUBSTRATE_HISTORY_IMAGING as SUBSTRATE_HISTORY_IMAGING,
)
from wc_caseload_engine.fact_templates import _SUBSTRATE_MODALITY_CHOICES, fact_aware_templates
from wc_caseload_engine.manifests import (
    MANIFEST_NAME,
    SUBPOENAED_RECORDS_SUBTYPES,
    TREATING_REPORT_SUBTYPES,
    generate_case,
)
from wc_caseload_engine.manifests import (
    OPERATIVE_SUBTYPES as MANIFEST_OPERATIVE_SUBTYPES,
)
from wc_caseload_engine.modality_audit import MODALITY_SITES, is_excluded, sites_for
from wc_caseload_engine.planner import (
    NEVER_TREATED_SUPPRESSED_TYPES,
    NEVER_TREATED_TIER,
    POST_DISCHARGE_FORBIDDEN,
    build_case_plan,
)
from wc_caseload_engine.planner import (
    OPERATIVE_SUBTYPES as PLANNER_OPERATIVE_SUBTYPES,
)
from wc_caseload_engine.seeds import (
    BODY_PART_CATALOG,
    TREATMENT_LIEN_CLAIMANTS,
    LienClaimant,
    parse_case_seed,
)
from wc_caseload_engine.substrate import import_substrate
from wc_caseload_engine.taxonomy import effective_taxonomy


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

    def test_the_ledger_records_no_visits(self) -> None:
        """A reported injury is not a treatment visit.

        This asserted a single "initial" visit until the PR #24 review: the
        first-report tier still emits documents, but publishing a visit behind
        them made the ledger claim a clinical encounter in a file whose whole
        premise is that none happened.
        """
        facts = build_case_plan(
            _seed("nt-ledger", rng_seed=7211, scenario={"treatment": {"status": "never_treated"}})
        ).case_facts
        assert facts is not None
        assert facts.visits == ()

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

    def test_every_row_marker_matches_a_real_line(self) -> None:
        """Row-level, not file-level. A marker that matches nothing is a lie.

        Without this, a row could claim to govern a site that no longer exists
        — or never did — and the file-level tests above would still pass,
        because some *other* row covers the file. The table would read as
        complete while quietly not being.
        """
        hits = _substrate_modality_hits()
        vacuous: list[str] = []
        for site in MODALITY_SITES:
            lines = hits.get(site.path, [])
            if not any(site.marker in text for _, text in lines):
                vacuous.append(f"{site.path} :: {site.marker!r}")
        assert not vacuous, "MODALITY_SITES rows match no substrate line:\n" + "\n".join(vacuous)

    def test_third_party_code_is_excluded_from_the_walk(self) -> None:
        """A substrate tree with a venv must not drag site-packages into the audit.

        The reviewer's checkout had one, and faker's "Diagnostic radiographer"
        made the audit fail on code this package does not render — which is
        also why their run did not reproduce our green suite.
        """
        for path in (
            ".venv/lib/python3.12/site-packages/faker/providers/job/__init__.py",
            "venv/lib/site-packages/anything.py",
            "some/nested/site-packages/mod.py",
        ):
            assert is_excluded(path), f"{path} would be walked as substrate content"


# ---------------------------------------------------------------------------
# The guards bind on the derived path too (PR #24 review)
# ---------------------------------------------------------------------------
#
# Every failure below was the same shape: the explicit path rejects actionably
# and the adjacent path passes in silence. A guard that only fires when the
# author already spelled out the problem is a guard against typing, not against
# incoherence.


class TestNeverTreatedBindsOnDerivedLiens:
    def test_an_auto_filled_roster_cannot_smuggle_a_treatment_lien(self) -> None:
        """The proven seed: no claimants named, six drawn, treatment liens land."""
        seed = _seed(
            "nt-derived-liens",
            rng_seed=8101,
            scenario={"treatment": {"status": "never_treated"}},
            lifecycle={
                "target_stage": "medical_legal",
                "eval_type": "qme",
                "liens": {"count": 6, "claimants": []},
            },
        )
        plan = build_case_plan(seed)
        offenders = sorted(
            {
                track.claimant
                for track in plan.lien_tracks
                if track.claimant in TREATMENT_LIEN_CLAIMANTS
            }
        )
        assert not offenders, (
            f"never_treated case resolved treatment lien claimants {offenders} — "
            "a provider only holds a lien for treatment it gave"
        )

    def test_the_derived_roster_still_fills_to_the_requested_count(self) -> None:
        """Filtering the pool must not quietly shrink the case."""
        seed = _seed(
            "nt-derived-count",
            rng_seed=8102,
            scenario={"treatment": {"status": "never_treated"}},
            lifecycle={
                "target_stage": "medical_legal",
                "eval_type": "qme",
                "liens": {"count": 4, "claimants": []},
            },
        )
        assert len(build_case_plan(seed).lien_tracks) == 4

    def test_an_ordinary_case_still_draws_treatment_claimants(self) -> None:
        """Opposite-draw: the filter is scoped to never_treated, not global."""
        seen: set[str] = set()
        for rng_seed in range(8110, 8120):
            seed = _seed(
                f"ord-liens-{rng_seed}",
                rng_seed=rng_seed,
                lifecycle={
                    "target_stage": "medical_legal",
                    "eval_type": "qme",
                    "liens": {"count": 6, "claimants": []},
                },
            )
            seen.update(track.claimant for track in build_case_plan(seed).lien_tracks)
        assert seen & set(TREATMENT_LIEN_CLAIMANTS), (
            "no ordinary case drew a treatment claimant; the filter is too wide"
        )

    def test_an_explicit_treatment_claimant_is_still_rejected(self) -> None:
        """Stated beats derived, in both directions: name it and it is an error."""
        with pytest.raises(ValueError, match="never_treated"):
            _seed(
                "nt-explicit",
                scenario={"treatment": {"status": "never_treated"}},
                lifecycle={
                    "target_stage": "medical_legal",
                    "eval_type": "qme",
                    "liens": {"count": 2, "claimants": ["hospital"]},
                },
            )


class TestDeniedByUrRequiresTheDenialToStand:
    def test_an_overturned_decision_is_refused(self) -> None:
        """The proven seed: UR overturned, surgery 'denied_by_ur', both rendered."""
        with pytest.raises(ValueError) as exc:
            _seed(
                "ur-overturned",
                scenario={"surgery": "denied_by_ur"},
                lifecycle={
                    "target_stage": "medical_legal",
                    "eval_type": "qme",
                    "ur_dispute": {"enabled": True, "decision": "overturned"},
                },
            )
        message = str(exc.value)
        assert "overturned" in message
        assert "upheld" in message

    def test_an_unstated_decision_is_refused(self) -> None:
        """The same bug one level down.

        ``decision: None`` maps to the substrate's ``"random"``, which resolves
        via ``rng.choice(["approved", "denied"])`` — so it can land on approved
        and produce the identical contradiction, non-deterministically from the
        seed author's point of view. ``denied_by_ur`` therefore requires the
        decision to be stated, not merely for a dispute to exist.
        """
        with pytest.raises(ValueError) as exc:
            _seed(
                "ur-unstated",
                scenario={"surgery": "denied_by_ur"},
                lifecycle={
                    "target_stage": "medical_legal",
                    "eval_type": "qme",
                    "ur_dispute": {"enabled": True},
                },
            )
        assert "upheld" in str(exc.value)

    def test_the_substrate_really_can_draw_approved(self) -> None:
        """Evidence for the docstring above, not an assumption."""
        source = inspect.getsource(import_substrate("data.lifecycle_engine"))
        assert 'rng.choice(["approved", "denied"])' in source

    def test_upheld_is_accepted(self) -> None:
        seed = _seed(
            "ur-upheld",
            scenario={"surgery": "denied_by_ur"},
            lifecycle={
                "target_stage": "medical_legal",
                "eval_type": "qme",
                "ur_dispute": {"enabled": True, "decision": "upheld"},
            },
        )
        assert seed.scenario.surgery == "denied_by_ur"


class TestNeverTreatedPublishesAnEmptyRecord:
    def test_the_provider_roster_is_empty(self) -> None:
        facts = build_case_plan(
            _seed("nt-roster", rng_seed=8201, scenario={"treatment": {"status": "never_treated"}})
        ).case_facts
        assert facts is not None
        assert facts.providers == (), (
            "never_treated publishes a treating roster; the manifest asserts "
            "providers for a case whose documents say nobody treated"
        )

    def test_there_are_no_visits(self) -> None:
        facts = build_case_plan(
            _seed("nt-visits", rng_seed=8202, scenario={"treatment": {"status": "never_treated"}})
        ).case_facts
        assert facts is not None
        assert facts.visits == ()

    def test_the_published_outputs_agree(self, tmp_path: Path) -> None:
        seed = _seed(
            "nt-published", rng_seed=8203, scenario={"treatment": {"status": "never_treated"}}
        )
        manifest, _ = _render(seed, tmp_path)
        assert manifest["caseFacts"]["providers"] == []
        yaml_text = (tmp_path / seed.case_id / "case_facts.yaml").read_text()
        assert "providers: []" in yaml_text

    def test_subpoena_attribution_degrades_to_the_treating_physician(
        self, tmp_path: Path
    ) -> None:
        """An empty roster must not crash or index into nothing.

        The renderer only sets ``provider_index`` when the roster is non-empty,
        so the substrate takes the fallback it has always had. Asserted rather
        than assumed, because the alternative is a modulo by zero.
        """
        seed = _seed(
            "nt-subpoena",
            rng_seed=8204,
            scenario={"treatment": {"status": "never_treated"}},
            documents={
                "overrides": [{"subtype": "SUBPOENAED_RECORDS_MEDICAL", "count": 2}],
                "format_mix": {"pdf": 1.0},
            },
        )
        _, texts = _render(seed, tmp_path)
        assert texts.get("SUBPOENAED_RECORDS_MEDICAL"), "rendering failed on an empty roster"

    def test_an_ordinary_case_still_has_providers(self) -> None:
        """Opposite-draw: the emptying is scoped to never_treated."""
        facts = build_case_plan(_seed("ord-roster", rng_seed=8201)).case_facts
        assert facts is not None
        assert facts.providers


class TestEveryActionableMessageResolvesWhenFollowed:
    """The meta-guard: an actionable error must actually be actionable.

    The ``denied_by_ur`` message told authors to add ``decision: denied``, which
    is not a legal enum value — following it verbatim produced a second error.
    A message that sends the reader somewhere that also fails is worse than a
    terse one, because it costs a round trip to discover.
    """

    def test_the_denied_by_ur_message_names_a_legal_value(self) -> None:
        with pytest.raises(ValueError) as exc:
            _seed("msg-ur", scenario={"surgery": "denied_by_ur"})
        message = str(exc.value)
        assert "decision: denied" not in message, "the suggested value is not in the enum"
        assert "upheld" in message

    def test_following_the_ur_message_produces_a_valid_seed(self) -> None:
        """Apply the suggested edit; the seed must now load."""
        seed = _seed(
            "msg-ur-fixed",
            scenario={"surgery": "denied_by_ur"},
            lifecycle={
                "target_stage": "medical_legal",
                "eval_type": "qme",
                "ur_dispute": {"enabled": True, "decision": "upheld"},
            },
        )
        assert seed.scenario.surgery == "denied_by_ur"

    def test_following_the_never_treated_surgery_message_works(self) -> None:
        seed = _seed(
            "msg-nt-surg",
            scenario={"treatment": {"status": "never_treated"}, "surgery": "none"},
        )
        assert seed.scenario.surgery == "none"

    def test_every_cli_invocation_in_the_source_is_real(self) -> None:
        """A message that tells the author to run a command that does not exist.

        ``planner.py`` sent anyone with a bad control key to
        ``wc-caseload taxonomy --list``. There is no ``taxonomy`` command and no
        ``--list`` flag anywhere in the CLI, so the one instruction attached to
        the error was a dead end — the same class as the ``decision: denied``
        suggestion, and invisible for the same reason: nothing executes the
        text of an error message.

        Scanned statically across the whole package rather than asserted on the
        messages I happen to know about, because the ones I know about are not
        the ones that rot.
        """
        # An *invocation*, not every mention. The string also appears in prose —
        # ``# wc-caseload case facts — the resolved clinical ledger`` heads the
        # YAML artifact — so a bare-words match would flag English. A real
        # invocation is either quoted for the reader, or carries a flag.
        pattern = re.compile(
            r"(?:`+wc-caseload ([a-z][a-z-]*)((?: --[a-z][a-z-]*)*)"
            r"|wc-caseload ([a-z][a-z-]*)((?: --[a-z][a-z-]*)+))"
        )
        root = Path(wc_caseload_engine.__file__).parent
        problems: list[str] = []

        for path in sorted(root.rglob("*.py")):
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                for quoted_cmd, quoted_flags, bare_cmd, bare_flags in pattern.findall(line):
                    command = quoted_cmd or bare_cmd
                    flags = quoted_flags or bare_flags
                    where = f"{path.name}:{number}"
                    if command not in cli.commands:
                        problems.append(
                            f"{where}: names `wc-caseload {command}`, which is not a "
                            f"command (have: {', '.join(sorted(cli.commands))})"
                        )
                        continue
                    known = {
                        opt
                        for param in cli.commands[command].params
                        for opt in param.opts
                        if opt.startswith("--")
                    }
                    for flag in flags.split():
                        if flag not in known:
                            problems.append(
                                f"{where}: `wc-caseload {command} {flag}` is not a flag "
                                f"of that command (have: {', '.join(sorted(known))})"
                            )

        assert not problems, "source text names CLI surface that does not exist:\n" + "\n".join(
            problems
        )

    def test_following_the_never_treated_lien_message_works(self) -> None:
        """The message names edd/ambulance/attorney_costs/self_procured as safe."""
        seed = _seed(
            "msg-nt-lien",
            scenario={"treatment": {"status": "never_treated"}},
            lifecycle={
                "target_stage": "medical_legal",
                "eval_type": "qme",
                "liens": {"count": 2, "claimants": ["edd", "attorney_costs"]},
            },
        )
        assert seed.scenario.treatment.status == "never_treated"


# ---------------------------------------------------------------------------
# Hand-written lists name things that exist
# ---------------------------------------------------------------------------


#: Every hand-maintained subtype list this phase added or relies on.
SUBTYPE_LISTS: tuple[tuple[str, frozenset[str]], ...] = (
    ("planner.NEVER_TREATED_TIER", NEVER_TREATED_TIER),
    ("planner.POST_DISCHARGE_FORBIDDEN", POST_DISCHARGE_FORBIDDEN),
    ("planner.OPERATIVE_SUBTYPES", PLANNER_OPERATIVE_SUBTYPES),
    ("manifests.OPERATIVE_SUBTYPES", MANIFEST_OPERATIVE_SUBTYPES),
    ("manifests.SUBPOENAED_RECORDS_SUBTYPES", SUBPOENAED_RECORDS_SUBTYPES),
    ("manifests.TREATING_REPORT_SUBTYPES", TREATING_REPORT_SUBTYPES),
)


class TestHandWrittenListsNameLiveKeys:
    """A list whose members do not exist is a rule that never fires.

    This generalizes the lesson from the modality audit table, where five rows
    of mine claimed to govern substrate lines that did not exist and every
    file-level check still passed. The table read as complete while being partly
    fiction, and nothing would have caught it.

    The same failure is available to every hand-written subtype list here.
    ``NEVER_TREATED_TIER`` is the sharpest case: a typo in an allowlist member
    does not raise, it silently suppresses a document the seed meant to keep,
    and the resulting case looks plausible. These lists are all correct today —
    the point is that they stay correct after a taxonomy rename.
    """

    @pytest.mark.parametrize(("name", "keys"), SUBTYPE_LISTS, ids=[n for n, _ in SUBTYPE_LISTS])
    def test_every_member_is_a_canonical_subtype(self, name: str, keys: frozenset[str]) -> None:
        taxonomy = effective_taxonomy()
        dead = sorted(key for key in keys if not taxonomy.is_canonical(key))
        assert not dead, f"{name} names subtypes the taxonomy does not have: {dead}"

    @pytest.mark.parametrize(("name", "keys"), SUBTYPE_LISTS, ids=[n for n, _ in SUBTYPE_LISTS])
    def test_no_member_is_substrate_only_vocabulary(
        self, name: str, keys: frozenset[str]
    ) -> None:
        """Canonical is not enough — a substrate-only key never reaches a manifest."""
        taxonomy = effective_taxonomy()
        offenders = sorted(key for key in keys if key in taxonomy.substrate_only)
        assert not offenders, f"{name} names substrate-only subtypes: {offenders}"

    @pytest.mark.parametrize(("name", "keys"), SUBTYPE_LISTS, ids=[n for n, _ in SUBTYPE_LISTS])
    def test_no_list_is_empty(self, name: str, keys: frozenset[str]) -> None:
        """An emptied list is a silently disabled rule."""
        assert keys, f"{name} is empty; the rule it drives no longer does anything"

    def test_the_fact_aware_registry_names_live_renderable_subtypes(self) -> None:
        taxonomy = effective_taxonomy()
        registry = set(fact_aware_templates())
        dead = sorted(key for key in registry if not taxonomy.is_canonical(key))
        assert not dead, f"FACT_AWARE_TEMPLATES maps subtypes the taxonomy lacks: {dead}"
        unrenderable = sorted(key for key in registry if not taxonomy.is_renderable(key))
        assert not unrenderable, (
            f"FACT_AWARE_TEMPLATES maps subtypes nothing can render: {unrenderable}"
        )

    def test_the_suppressed_types_are_live_parent_types(self) -> None:
        """``never_treated`` filters on parent type, not subtype — same exposure."""
        taxonomy = effective_taxonomy()
        dead = sorted(name for name in NEVER_TREATED_SUPPRESSED_TYPES if name not in taxonomy.types)
        assert not dead, f"NEVER_TREATED_SUPPRESSED_TYPES names unknown types: {dead}"

    def test_treatment_lien_claimants_are_legal_claimant_values(self) -> None:
        """The never_treated lien rule filters a pool it does not own."""
        legal = set(get_args(LienClaimant.__value__))
        unknown = sorted(set(TREATMENT_LIEN_CLAIMANTS) - legal)
        assert not unknown, f"TREATMENT_LIEN_CLAIMANTS names non-claimants: {unknown}"

    def test_surgery_cpt_body_parts_are_real_body_parts(self) -> None:
        """A CPT keyed to a body part the seed cannot name is unreachable."""
        parts = {part for entries in BODY_PART_CATALOG.values() for part, _icd, _detail in entries}
        unknown = sorted(set(SURGERY_CPT_CODES) - parts)
        assert not unknown, f"SURGERY_CPT_CODES is keyed by unknown body parts: {unknown}"

    def test_the_substrate_modality_pool_still_exists(self) -> None:
        """The last unpinned substrate list — the imaging shim's match target."""
        source = inspect.getsource(import_substrate("pdf_templates.medical.diagnostic_report"))
        missing = [choice for choice in _SUBSTRATE_MODALITY_CHOICES if f'"{choice}"' not in source]
        assert not missing, (
            f"{missing} are no longer in the substrate's exam-type list; the imaging "
            "override is silently reverting to a random draw"
        )
