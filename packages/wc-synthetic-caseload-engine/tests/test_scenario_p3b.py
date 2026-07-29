"""AJC-37 Phase 3b — letter lifecycle, delay chains, cadence, discovery volumes.

The file opens with the ordinal-plumbing tests because they document a defect
that shipped in Phase 2 and was invisible to Phase 2's own suite. The substrate
threads ``doc_spec`` as a *parameter* to ``build_story`` and never assigns
``self.doc_spec``, so every helper here that read ``template.doc_spec.context``
returned its fallback. ``_facts_of`` survived on the ``_wc_case_facts``
instance attribute the renderer sets; ``_report_ordinal`` and ``_index_of`` had
no such fallback and were pinned at 0 for the life of the feature.

Phase 2's render test asked ``any(phrase in body for phrase in arc)``. At
ordinal 0 the first phrase of the arc *is* a phrase of the arc, so the
assertion passed while the trajectory never advanced — the vacuous-assertion
class again, and the reason the tests below count *distinct* phrases instead.
"""

from __future__ import annotations

import json
import re
from itertools import pairwise
from pathlib import Path
from typing import Any

import pytest

import wc_caseload_engine.fact_templates as fact_templates
from conftest import extract_text, requires_substrate
from wc_caseload_engine.case_facts import TRAJECTORY_PHRASES
from wc_caseload_engine.manifests import MANIFEST_NAME, generate_case
from wc_caseload_engine.planner import (
    ATTORNEY_CADENCE_SUBTYPES,
    DELAY_CHAIN_SUBTYPE,
    build_case_plan,
)
from wc_caseload_engine.seeds import parse_case_seed
from wc_caseload_engine.substrate import import_substrate

pytestmark = requires_substrate


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


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


def _all_text(texts: dict[str, str]) -> str:
    return _flat("\n".join(texts.values()))


def _observed(monkeypatch: pytest.MonkeyPatch, name: str) -> list[int]:
    """Every value the named ordinal helper actually returned during a render."""
    seen: list[int] = []
    original = getattr(fact_templates, name)

    def spy(template: Any) -> int:
        value = original(template)
        seen.append(value)
        return value

    monkeypatch.setattr(fact_templates, name, spy)
    return seen


#: The sentence each substrate letter type opens with. Pinned so a substrate
#: edit fails here loudly rather than turning the lifecycle assertions vacuous.
LETTER_MARKERS: dict[str, str] = {
    "initial_acceptance": "accepted liability for the industrial injury",
    "pd_advance_offer": "discuss a permanent disability advance with your client",
    "settlement_discussion": "initiate discussions regarding potential resolution",
    "medical_records_request": "in the process of evaluating the above-referenced claim",
    "ur_decision": "a utilization review determination has been made",
}


def _letters_present(body: str) -> set[str]:
    return {name for name, marker in LETTER_MARKERS.items() if marker in body}


# ---------------------------------------------------------------------------
# The ordinal seam — a Phase-2 defect this phase inherits
# ---------------------------------------------------------------------------


class TestOrdinalsReachTheTemplate:
    def test_the_markers_are_still_the_substrate_s_own_sentences(self) -> None:
        """If the substrate rewrites a letter, every lifecycle assertion below
        would quietly match nothing. Fail here instead."""
        source = _flat(
            __import__("inspect").getsource(
                import_substrate("pdf_templates.correspondence.adjuster_letter")
            )
        )
        for name, marker in LETTER_MARKERS.items():
            assert marker in source, (
                f"{name} no longer opens with {marker!r}; the letter-lifecycle "
                "tests are matching nothing"
            )

    def test_report_ordinal_advances_across_treating_reports(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = _observed(monkeypatch, "_report_ordinal")
        seed = _seed(
            "ord-report",
            rng_seed=7502,
            documents={
                "overrides": [{"subtype": "TREATING_PHYSICIAN_REPORT_PR2", "count": 4}],
                "format_mix": {"pdf": 1.0},
            },
        )
        _render(seed, tmp_path)
        assert seen, "no treating report rendered; the probe proves nothing"
        assert len(set(seen)) > 1, (
            f"every treating report saw report_ordinal={seen[0]}; the trajectory "
            "cannot advance, so the arc renders its first phrase forever"
        )

    def test_letter_ordinal_advances_across_adjuster_letters(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = _observed(monkeypatch, "_letter_ordinal")
        seed = _seed(
            "ord-letter",
            rng_seed=7503,
            documents={
                "overrides": [{"subtype": "ADJUSTER_LETTER", "count": 4}],
                "format_mix": {"pdf": 1.0},
            },
        )
        _render(seed, tmp_path)
        assert seen, "no adjuster letter rendered; the probe proves nothing"
        assert len(set(seen)) > 1, (
            f"every adjuster letter saw letter_ordinal={seen[0]}; the type "
            "sequence cannot advance"
        )


# ---------------------------------------------------------------------------
# ISC-105 (carried) — the trajectory has to advance in the rendered file
# ---------------------------------------------------------------------------


class TestTheTrajectoryAdvancesOnThePage:
    def test_a_multi_report_case_renders_more_than_one_arc_phrase(
        self, tmp_path: Path
    ) -> None:
        """Phase 2 asserted ``any(phrase in body)``, which the first phrase
        alone satisfies. Counting distinct phrases is what makes it bite."""
        seed = _seed(
            "traj-advance",
            rng_seed=7502,
            documents={
                "overrides": [{"subtype": "TREATING_PHYSICIAN_REPORT_PR2", "count": 4}],
                "format_mix": {"pdf": 1.0},
            },
        )
        plan = build_case_plan(seed)
        assert plan.case_facts is not None
        _, texts = _render(seed, tmp_path)
        body = _flat(texts.get("TREATING_PHYSICIAN_REPORT_PR2", ""))
        arc = TRAJECTORY_PHRASES[plan.case_facts.trajectory]
        landed = [phrase for phrase in arc if phrase.lower() in body]
        assert len(landed) > 1, (
            f"four reports rendered {len(landed)} distinct {plan.case_facts.trajectory} "
            f"phrase(s): {landed}. The arc is frozen at its first step."
        )


# ---------------------------------------------------------------------------
# ISC-121 — a case accepts the claim once
# ---------------------------------------------------------------------------


class TestAdjusterLetterLifecycle:
    def test_the_claim_is_accepted_at_most_once(self, tmp_path: Path) -> None:
        seed = _seed(
            "letter-once",
            rng_seed=7504,
            documents={
                "overrides": [{"subtype": "ADJUSTER_LETTER", "count": 4}],
                "format_mix": {"pdf": 1.0},
            },
        )
        _, texts = _render(seed, tmp_path)
        body = _flat(texts.get("ADJUSTER_LETTER", ""))
        assert body, "no adjuster letter text extracted"
        acceptances = body.count(LETTER_MARKERS["initial_acceptance"])
        assert acceptances <= 1, (
            f"the carrier accepted liability {acceptances} times in one file"
        )

    def test_four_letters_are_not_all_the_same_letter(self, tmp_path: Path) -> None:
        seed = _seed(
            "letter-varied",
            rng_seed=7504,
            documents={
                "overrides": [{"subtype": "ADJUSTER_LETTER", "count": 4}],
                "format_mix": {"pdf": 1.0},
            },
        )
        _, texts = _render(seed, tmp_path)
        present = _letters_present(_flat(texts.get("ADJUSTER_LETTER", "")))
        assert len(present) > 1, f"four letters, one flavour: {present}"

    def test_a_denied_claim_never_sends_an_acceptance_letter(
        self, tmp_path: Path
    ) -> None:
        """The counterfactual for the same knob: the ledger withholds
        ``initial_acceptance`` when liability was denied."""
        seed = _seed(
            "letter-denied",
            rng_seed=7505,
            lifecycle={
                "target_stage": "medical_legal",
                "eval_type": "qme",
                "claim_response": "denied",
            },
            documents={
                "overrides": [{"subtype": "ADJUSTER_LETTER", "count": 4}],
                "format_mix": {"pdf": 1.0},
            },
        )
        plan = build_case_plan(seed)
        assert plan.case_facts is not None
        assert "initial_acceptance" not in plan.case_facts.adjuster_letter_types_allowed
        _, texts = _render(seed, tmp_path)
        body = _flat(texts.get("ADJUSTER_LETTER", ""))
        assert body, "no adjuster letter text extracted"
        assert LETTER_MARKERS["initial_acceptance"] not in body, (
            "the carrier accepted liability on a denied claim"
        )


# ---------------------------------------------------------------------------
# ISC-119 — a delay chain: late benefits draw correspondence after them
# ---------------------------------------------------------------------------


def _plan_for(case_id: str, **overrides: Any) -> Any:
    plan = build_case_plan(_seed(case_id, **overrides))
    assert plan.case_facts is not None
    return plan


def _dates_of(plan: Any, subtype: str) -> list[Any]:
    return sorted(d.doc_date for d in plan.documents if d.subtype == subtype)


class TestDelayChains:
    def test_each_late_benefit_draws_its_own_demand_letter(self) -> None:
        plan = _plan_for(
            "chain-neg",
            rng_seed=8100,
            scenario={"adjuster": {"diligence": "negligent"}},
        )
        facts = plan.case_facts
        letters = _dates_of(plan, DELAY_CHAIN_SUBTYPE)
        assert facts.late_benefit_events, "seed drew no late benefits; probe is vacuous"
        assert len(letters) >= len(facts.late_benefit_events), (
            f"{len(facts.late_benefit_events)} late benefit(s), "
            f"{len(letters)} demand letter(s) — the delay went unanswered"
        )

    def test_every_demand_letter_post_dates_the_delay_it_chases(self) -> None:
        plan = _plan_for(
            "chain-order",
            rng_seed=8101,
            scenario={"adjuster": {"diligence": "negligent"}},
        )
        facts = plan.case_facts
        assert facts.late_benefit_events
        earliest = min(e.actual_date for e in facts.late_benefit_events)
        chain = _dates_of(plan, DELAY_CHAIN_SUBTYPE)
        # Without this the loop below is a no-op on a file with no chain in it,
        # and a passing test would mean "the feature is absent".
        assert chain, "no demand letters planned; the ordering assertion is vacuous"
        for when in chain:
            assert when >= earliest, (
                f"a demand letter dated {when} chases a delay that had not "
                f"happened yet (first late benefit {earliest})"
            )

    def test_an_attentive_adjuster_draws_a_shorter_chain(self) -> None:
        """The opposite draw of the same knob, on one seed."""
        negligent = _plan_for(
            "chain-cf", rng_seed=8102, scenario={"adjuster": {"diligence": "negligent"}}
        )
        attentive = _plan_for(
            "chain-cf", rng_seed=8102, scenario={"adjuster": {"diligence": "attentive"}}
        )
        assert len(negligent.case_facts.late_benefit_events) > len(
            attentive.case_facts.late_benefit_events
        ), "the two personas drew the same lateness; the counterfactual proves nothing"
        assert len(_dates_of(negligent, DELAY_CHAIN_SUBTYPE)) > len(
            _dates_of(attentive, DELAY_CHAIN_SUBTYPE)
        ), "correspondence density did not follow the persona"


# ---------------------------------------------------------------------------
# ISC-123/124 — the cadence decides when counsel wrote
# ---------------------------------------------------------------------------


class TestAttorneyCadenceMovesTheDates:
    def _letters(self, cadence: str, case_id: str, rng_seed: int = 8200) -> list[Any]:
        plan = _plan_for(
            case_id, rng_seed=rng_seed, scenario={"attorney": {"cadence": cadence}}
        )
        assert plan.case_facts.attorney_cadence == cadence
        return sorted(
            doc.doc_date
            for doc in plan.documents
            if doc.subtype in ATTORNEY_CADENCE_SUBTYPES
        )

    def test_thirty_day_cadence_sits_on_a_thirty_day_clock(self) -> None:
        dates = self._letters("every_30_days", "cad-30")
        assert len(dates) >= 3, f"only {len(dates)} letters; the rhythm is untestable"
        gaps = [(b - a).days for a, b in pairwise(dates)]
        assert max(gaps) <= 45, f"a 30-day cadence left a {max(gaps)}-day hole: {gaps}"

    def test_sporadic_opens_a_hole_a_reviewer_would_notice(self) -> None:
        dates = self._letters("sporadic", "cad-sp")
        assert len(dates) >= 3, f"only {len(dates)} letters; the rhythm is untestable"
        gaps = [(b - a).days for a, b in pairwise(dates)]
        assert max(gaps) >= 90, f"sporadic never went quiet: {gaps}"

    def test_the_three_cadences_do_not_agree(self) -> None:
        """Opposite draws of one knob: if the dates match, nothing is honoured."""
        rhythms = {
            name: self._letters(name, "cad-cf")
            for name in ("every_30_days", "event_driven", "sporadic")
        }
        distinct = {tuple(dates) for dates in rhythms.values()}
        assert len(distinct) == 3, (
            "two cadences produced identical letter dates: "
            f"{ {name: [str(d) for d in v] for name, v in rhythms.items()} }"
        )
