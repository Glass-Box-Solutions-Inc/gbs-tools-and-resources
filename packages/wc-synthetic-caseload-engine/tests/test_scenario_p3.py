"""AJC-37 Phase 3 — adjuster and attorney personas, discovery volume.

Same discipline as Phases 1 and 2, plus one addition the review history earned.

Every phase so far has shipped the same defect at least once: a guard that
binds to the *declared* seed value while the code reads a *resolved* one, so
the explicit path rejects and the adjacent path passes in silence. Phase 1's
critical was `scenario.surgery` never reaching `has_surgery`; Phase 2's majors
were the never_treated lien guard and the `denied_by_ur` decision check, both
the same shape.

So for every knob here the *adjacent-path* test is written first — the case
where the underlying draw disagrees with the seed, or where the value arrives
by derivation rather than by declaration. If a guard only fires when the author
already spelled the problem out, it is a guard against typing.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from conftest import extract_text, requires_substrate
from wc_caseload_engine import lifecycle_bridge, planner
from wc_caseload_engine.case_facts import facts_manifest_block
from wc_caseload_engine.lifecycle_bridge import build_core_candidates, build_timeline
from wc_caseload_engine.manifests import MANIFEST_NAME, generate_case
from wc_caseload_engine.planner import build_case_plan
from wc_caseload_engine.seeds import parse_case_seed

pytestmark = requires_substrate


def _flat(text: str) -> str:
    """Extracted PDF text with reportlab's line wrapping removed."""
    return re.sub(r"\s+", " ", text).strip().lower()


def _body(case_id: str, **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "case_id": case_id,
        "rng_seed": 9100,
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
# ISC-117 / ISC-122 / ISC-126 — the schema
# ---------------------------------------------------------------------------


class TestThePersonaBlocksLoad:
    @pytest.mark.parametrize("diligence", ["attentive", "ordinary", "negligent"])
    def test_every_diligence_is_accepted(self, diligence: str) -> None:
        seed = _seed(f"a-{diligence}", scenario={"adjuster": {"diligence": diligence}})
        assert seed.scenario.adjuster.diligence == diligence

    @pytest.mark.parametrize("cadence", ["every_30_days", "event_driven", "sporadic"])
    def test_every_cadence_is_accepted(self, cadence: str) -> None:
        seed = _seed(f"c-{cadence}", scenario={"attorney": {"cadence": cadence}})
        assert seed.scenario.attorney.cadence == cadence

    def test_an_unknown_diligence_is_refused_by_name(self) -> None:
        with pytest.raises(ValueError, match="negligent"):
            _seed("a-bad", scenario={"adjuster": {"diligence": "lackadaisical"}})

    def test_an_unknown_cadence_is_refused_by_name(self) -> None:
        with pytest.raises(ValueError, match="event_driven"):
            _seed("c-bad", scenario={"attorney": {"cadence": "whenever"}})

    def test_the_discovery_block_is_accepted(self) -> None:
        seed = _seed(
            "d-ok",
            scenario={"discovery": {"subpoena_sets": 3, "pages_per_set": {"min": 20, "max": 60}}},
        )
        assert seed.scenario.discovery.subpoena_sets == 3
        assert seed.scenario.discovery.pages_per_set.min == 20

    def test_an_inverted_page_range_is_refused_actionably(self) -> None:
        with pytest.raises(ValueError) as exc:
            _seed(
                "d-bad",
                scenario={"discovery": {"pages_per_set": {"min": 90, "max": 30}}},
            )
        message = str(exc.value)
        assert "pages_per_set" in message
        assert "min" in message and "max" in message


class TestUnspecifiedPersonasDeriveDeterministically:
    """ISC-117/122. Derivation must be a function of the seed, not of luck."""

    def test_the_adjuster_derives_identically_twice(self) -> None:
        body = _body("a-derive", rng_seed=9201)
        assert "scenario" not in body
        first = build_case_plan(parse_case_seed(body)).case_facts
        second = build_case_plan(parse_case_seed(body)).case_facts
        assert first is not None and second is not None
        assert first.adjuster_diligence == second.adjuster_diligence

    def test_the_attorney_derives_identically_twice(self) -> None:
        body = _body("c-derive", rng_seed=9202)
        first = build_case_plan(parse_case_seed(body)).case_facts
        second = build_case_plan(parse_case_seed(body)).case_facts
        assert first is not None and second is not None
        assert first.attorney_cadence == second.attorney_cadence

    def test_derivation_spans_the_vocabulary(self) -> None:
        """A derivation that always lands on one value is a constant, not a draw."""
        seen = {
            build_case_plan(_seed(f"span-{s}", rng_seed=s)).case_facts.adjuster_diligence
            for s in range(9300, 9340)
        }
        assert len(seen) > 1, f"adjuster diligence never varies across 40 seeds: {seen}"


# ---------------------------------------------------------------------------
# ISC-127 — the declared-vs-resolved class, designed out
# ---------------------------------------------------------------------------


class TestEveryPersonaGuardReadsTheResolvedValue:
    """The class that has shipped in every phase so far.

    Written before the features, not after. Each test states the adjacent path:
    the value arrives by *derivation* rather than declaration, and the rule that
    depends on it must behave identically.
    """

    def test_penalty_gating_reads_resolved_lateness_not_the_seed(self) -> None:
        """ISC-120 + ISC-127. A derived-negligent case can also be late.

        Note the subtype. The substrate key is ``PETITION_FOR_PENALTIES_LC_5814``
        and ``normalize_subtype`` maps it to ``PETITION_FOR_PENALTIES`` before it
        reaches a plan, so asserting on the raw name matches nothing and passes
        for the wrong reason. The first version of this test did exactly that —
        the same vacuous-assertion class the modality audit's row markers hit.
        """
        assert any(
            d.subtype == "PETITION_FOR_PENALTIES"
            for d in build_case_plan(
                _seed("pen-live", rng_seed=100, scenario={"adjuster": {"diligence": "negligent"}})
            ).documents
        ), "the subtype this test greps for never appears; the sweep below is vacuous"

        offenders: list[str] = []
        for rng_seed in range(9400, 9440):
            plan = build_case_plan(_seed(f"pen-{rng_seed}", rng_seed=rng_seed))
            assert plan.case_facts is not None
            late = bool(plan.case_facts.late_benefit_events)
            emitted = any(d.subtype == "PETITION_FOR_PENALTIES" for d in plan.documents)
            if emitted and not late:
                offenders.append(f"rng_seed={rng_seed}: penalty petition with no late event")
        assert not offenders, "\n".join(offenders[:10])

    def test_letter_type_coherence_reads_the_resolved_lifecycle(self) -> None:
        """ISC-121 + ISC-127. UR letters gate on the resolved dispute, not the seed."""
        seed = _seed("ur-absent", rng_seed=9501)
        assert seed.lifecycle.ur_dispute.enabled is False
        plan = build_case_plan(seed)
        assert plan.case_facts is not None
        assert not plan.case_facts.adjuster_letter_types_allowed & {"ur_decision"}

    def test_an_imaging_report_with_no_performed_study_still_cannot_name_an_absent_one(
        self, tmp_path: Path
    ) -> None:
        """ISC-128. The ``diagnostic_report.py:69`` question, answered by probe.

        The "Radiographic examination of the ..." line sits in the ``else``
        branch under the forced ``exam_type``, so on any case with a performed
        imaging study it is fully governed: it renders exactly when the ledger
        says X-Ray, and never otherwise.

        The gap is the case with *no* performed imaging study. The Phase-1
        override returns the substrate's own ``build_story`` unforced when the
        ledger hands it nothing, and the substrate then draws freely from
        MRI/CT/X-Ray — so a case whose ledger marks X-Ray deliberately absent
        could still render a radiographic examination report. Narrow, but real,
        and exactly the class the ledger exists to close.
        """
        seed = _seed(
            "no-performed-imaging",
            rng_seed=9701,
            scenario={
                "diagnostics": {
                    "performed": [{"modality": "emg", "body_part": "lumbar_spine"}],
                    "absent": [
                        {"modality": "xray", "body_part": "lumbar_spine"},
                        {"modality": "mri", "body_part": "lumbar_spine"},
                    ],
                }
            },
            documents={
                "overrides": [{"subtype": "DIAGNOSTICS_IMAGING", "count": 1}],
                "format_mix": {"pdf": 1.0},
            },
        )
        plan = build_case_plan(seed)
        assert plan.case_facts is not None
        assert plan.case_facts.diagnostic_for(0) is None, (
            "fixture no longer starves the imaging report; the probe proves nothing"
        )
        absent = plan.case_facts.absent_modalities()
        assert {"xray", "mri"} <= absent

        _, texts = _render(seed, tmp_path)
        body = _flat(texts.get("DIAGNOSTICS_IMAGING", ""))
        assert body, "no imaging report rendered"
        assert "radiographic examination" not in body, (
            "an imaging report named an X-Ray the ledger marks absent"
        )
        assert "mri of the" not in body, "an imaging report named an MRI the ledger marks absent"

    def test_the_substrate_flat_coin_is_really_suppressed(self) -> None:
        """ISC-120. The suppression is load-bearing, not merely never exercised.

        The demo caseload contains zero penalty petitions at v0.4.0 *and* at
        v0.5.0, so the zero-byte diff proves nothing about the suppression on
        its own — the rule might simply never have been drawn there. Toggling
        the owned-subtypes set off is the probe that actually distinguishes
        "suppressed" from "never fired".
        """
        seeds = [
            parse_case_seed(
                {
                    "case_id": f"sup-{rng_seed}",
                    "rng_seed": rng_seed,
                    "injury": {
                        "type": "specific",
                        "date_of_injury": "2021-01-11",
                        "body_parts": [{"part": "lumbar_spine"}],
                    },
                    "lifecycle": {"target_stage": "resolved", "eval_type": "qme"},
                }
            )
            for rng_seed in range(400, 500)
        ]

        def walk_emissions() -> int:
            total = 0
            for seed in seeds:
                timeline = build_timeline(seed)
                total += sum(
                    1
                    for candidate in build_core_candidates(seed, timeline)
                    if candidate.subtype == "PETITION_FOR_PENALTIES"
                )
            return total

        assert walk_emissions() == 0, "the substrate's flat coin still reaches the plan"

        original = lifecycle_bridge.PENALTY_OWNED_SUBTYPES
        lifecycle_bridge.PENALTY_OWNED_SUBTYPES = frozenset()
        try:
            unsuppressed = walk_emissions()
        finally:
            lifecycle_bridge.PENALTY_OWNED_SUBTYPES = original

        assert unsuppressed > 0, (
            "with suppression disabled the walk still emits no penalty petition, so "
            "the suppression is untested — find seeds that reach the rule"
        )

    def test_a_stated_negligent_case_earns_its_petition(self) -> None:
        """ISC-120, the positive direction."""
        emitted = 0
        for rng_seed in range(100, 120):
            plan = build_case_plan(
                _seed(f"neg-{rng_seed}", rng_seed=rng_seed,
                      scenario={"adjuster": {"diligence": "negligent"}})
            )
            assert plan.case_facts is not None
            if any(d.subtype == "PETITION_FOR_PENALTIES" for d in plan.documents):
                emitted += 1
                assert plan.case_facts.late_benefit_events
        assert emitted == 20, f"only {emitted}/20 negligent cases pleaded penalties"

    def test_an_attentive_case_never_pleads_penalties(self) -> None:
        """ISC-120, the anti-direction. Opposite draw from the test above."""
        for rng_seed in range(100, 120):
            plan = build_case_plan(
                _seed(f"att-{rng_seed}", rng_seed=rng_seed,
                      scenario={"adjuster": {"diligence": "attentive"}})
            )
            assert plan.case_facts is not None
            assert not plan.case_facts.late_benefit_events
            assert not [d for d in plan.documents if d.subtype == "PETITION_FOR_PENALTIES"]

    def test_the_petition_post_dates_every_delay_it_punishes(self) -> None:
        """Against the *latest* late event, not the earliest.

        The first version of this compared against ``min(...)`` and allowed
        equality, so a petition filed between two late notices passed — it would
        have been pleading a delay that had not happened yet on the day it was
        filed. The invariant is that the pleading follows every event it
        complains about, strictly.
        """
        checked = 0
        for rng_seed in range(100, 140):
            plan = build_case_plan(
                _seed(f"date-{rng_seed}", rng_seed=rng_seed,
                      scenario={"adjuster": {"diligence": "negligent"}})
            )
            assert plan.case_facts is not None
            petitions = [d for d in plan.documents if d.subtype == "PETITION_FOR_PENALTIES"]
            if not petitions:
                continue
            checked += 1
            latest_late = max(e.actual_date for e in plan.case_facts.late_benefit_events)
            assert petitions[0].doc_date > latest_late, (
                f"rng_seed={rng_seed}: petition dated {petitions[0].doc_date} does not "
                f"follow its latest punished event {latest_late}"
            )
        assert checked >= 10, f"only {checked} cases exercised the invariant"

    def test_document_controls_reach_the_penalty_petition(self) -> None:
        """The petition is a candidate like any other, not a late append.

        It was appended to the dated list *after* ``resolve_document_controls``
        ran, so `documents.exclude` and `include_only` silently did not apply to
        it — the one subtype this phase added was the one the control contract
        did not cover. Both proven seeds are below.
        """
        base = {"adjuster": {"diligence": "negligent"}}

        uncontrolled = build_case_plan(_seed("ctl-none", rng_seed=100, scenario=base))
        assert any(d.subtype == "PETITION_FOR_PENALTIES" for d in uncontrolled.documents), (
            "the fixture no longer earns a petition; the controls below prove nothing"
        )

        excluded = build_case_plan(
            _seed(
                "ctl-exclude",
                rng_seed=100,
                scenario=base,
                documents={
                    "exclude": ["PETITION_FOR_PENALTIES"],
                    "format_mix": {"pdf": 1.0},
                },
            )
        )
        assert not [d for d in excluded.documents if d.subtype == "PETITION_FOR_PENALTIES"]

        included = build_case_plan(
            _seed(
                "ctl-include",
                rng_seed=100,
                scenario=base,
                documents={
                    "include_only": ["FIRST_REPORT_OF_INJURY_PHYSICIAN"],
                    "format_mix": {"pdf": 1.0},
                },
            )
        )
        assert not [d for d in included.documents if d.subtype == "PETITION_FOR_PENALTIES"]

    def test_suppressing_an_earned_petition_is_loud(self) -> None:
        """Explicit control wins — and says so.

        The precedence follows ISC-29: an explicit document control beats a
        derived rule. But a file whose ledger records late benefit notices and
        holds no penalty petition is only coherent if somebody meant it, so the
        suppression lands in ``manifest.warnings`` — the mirror of the
        emit-with-warning cases, where the seed asked for something the
        substrate excludes and got it with a note.
        """
        plan = build_case_plan(
            _seed(
                "ctl-warn",
                rng_seed=100,
                scenario={"adjuster": {"diligence": "negligent"}},
                documents={
                    "exclude": ["PETITION_FOR_PENALTIES"],
                    "format_mix": {"pdf": 1.0},
                },
            )
        )
        assert plan.case_facts is not None
        assert plan.case_facts.late_benefit_events
        warned = [w for w in plan.warnings if "PETITION_FOR_PENALTIES" in w]
        assert warned, plan.warnings
        assert "documents.exclude" in warned[0]

    def test_an_attentive_case_excluding_the_petition_warns_about_nothing(self) -> None:
        """Opposite draw: no earned petition, no suppression, no noise."""
        plan = build_case_plan(
            _seed(
                "ctl-quiet",
                rng_seed=100,
                scenario={"adjuster": {"diligence": "attentive"}},
                documents={
                    "exclude": ["PETITION_FOR_PENALTIES"],
                    "format_mix": {"pdf": 1.0},
                },
            )
        )
        assert not [w for w in plan.warnings if "PETITION_FOR_PENALTIES" in w]

    def test_the_ledger_is_derived_exactly_once_per_plan(self) -> None:
        """One derivation, cast-bearing.

        Two derivations ran per case and disagreed: the planning copy had no
        cast and saw one provider, the published copy had a cast and saw five.
        Threading one cast-bearing derivation is both the truth fix and the
        cheaper path.
        """
        calls: list[bool] = []
        original = planner.derive_case_facts

        def spy(seed: Any, timeline: Any, cast: Any = None) -> Any:
            calls.append(cast is not None)
            return original(seed, timeline, cast)

        planner.derive_case_facts = spy  # type: ignore[assignment]
        try:
            plan = build_case_plan(_seed("once", rng_seed=100))
        finally:
            planner.derive_case_facts = original  # type: ignore[assignment]

        assert calls == [True], f"derivations per plan: {calls}"
        assert plan.case_facts is not None
        assert plan.case_facts.providers, "the surviving derivation lost the cast"

    def test_diligence_is_not_published(self) -> None:
        """m5. A persona input no rendered document reflects.

        Published while ``attorney_cadence`` was withheld for precisely that
        reason — the governed-facts rule applied inconsistently to its own
        author.
        """
        facts = build_case_plan(_seed("m5", rng_seed=100)).case_facts
        assert facts is not None
        block = facts_manifest_block(facts)
        assert "diligence" not in block["adjuster"]
        assert set(block["adjuster"]) == {"lateBenefitEvents", "maxDaysLate"}
        assert facts.adjuster_diligence, "still resolved on the ledger, just unpublished"

    def test_cadence_derivation_reaches_event_driven(self) -> None:
        """Only checks that derivation *reaches* the value — nothing more.

        Named for what it does. It was called
        ``test_cadence_dating_reads_the_resolved_cadence`` with an ISC-124
        docstring about anchoring, and asserted no letter, date or anchor: it
        passed with cadence entirely unwired, which is the actual state. A test
        whose name promises what a later phase will deliver is worse than no
        test, because the suite reads as covering it. The real ISC-124 assertion
        arrives with the feature.
        """
        anchored = 0
        for rng_seed in range(9600, 9640):
            plan = build_case_plan(_seed(f"cad-{rng_seed}", rng_seed=rng_seed))
            assert plan.case_facts is not None
            if plan.case_facts.attorney_cadence == "event_driven":
                anchored += 1
        assert anchored, "no seed derived event_driven; the adjacent path is untested"
