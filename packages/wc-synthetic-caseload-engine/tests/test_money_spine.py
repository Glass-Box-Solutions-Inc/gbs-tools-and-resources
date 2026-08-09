"""AJC-43 — the money spine: wage facts, rate derivation, ledger, settlement.

Money is the one part of a workers' compensation file where a claim is
*arithmetically* checkable, so these probes are held to a higher standard than
"the string appears". Wherever a number is asserted, the test recomputes it from
the published operands by the recorded method and compares — which is exactly
what an analyzer scored against this corpus has to do.

Three disciplines this package has learnt the hard way, applied here:

**A zero that is not earned is not evidence.** Every anti-probe runs on a case
that genuinely *could* have carried the artifact it is asserting the absence of.

**Every knob carries an opposite draw.** Asserting that ``late_payments: 3``
produces lateness proves nothing unless ``late_payments: 0`` on the same seed
produces none — otherwise the knob might be inert and the lateness incidental.

**A green test proves nothing alone.** The controls below are written so that
reverting the code under test turns them red; the mutation results are recorded
in the ISA rather than asserted here.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import decimal
import json
import re
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from conftest import extract_text, requires_substrate
from wc_caseload_engine import money as money_module
from wc_caseload_engine.case_facts import derive_case_facts
from wc_caseload_engine.fact_templates import (
    BENEFIT_RECORD_SUBTYPES,
    METHOD_LABEL,
    UNCONFIRMED_NOTICE,
    fact_aware_templates,
)
from wc_caseload_engine.lifecycle_bridge import build_timeline
from wc_caseload_engine.manifests import (
    CASE_FACTS_NAME,
    MANIFEST_NAME,
    generate_case,
    validate_output_tree,
)
from wc_caseload_engine.money import (
    IRREGULARITY_THRESHOLD,
    SHORT_HISTORY_WEEKS,
    TD_PAYMENT_DUE_DAYS,
    UNCONFIRMED_RATE_TABLE,
    analyzer_money_manifest_block,
    compute_aww,
    compute_comp_rate,
    derive_money_facts,
    dollars,
    exact,
    money,
    money_manifest_block,
    penalty_basis_for,
    rate_basis_for,
    select_method,
    statutory_deadline_basis_for,
)
from wc_caseload_engine.planner import (
    MONEY_FLOOR_SUBTYPES,
    MONEY_PD_SUBTYPE,
    MONEY_TD_SUBTYPE,
    MONEY_WAGE_SUBTYPE,
    build_case_plan,
)
from wc_caseload_engine.renderer import _load_template
from wc_caseload_engine.seeds import (
    AWW_METHODS,
    SeedValidationError,
    WageScenario,
    parse_case_seed,
    settlement_deductions,
)


def _refusals(block: dict, documents: list, case_id: str, *, given: str) -> list[str]:
    """``_validate_money``, with a crash reported as a failure of the calling guard.

    The defect these probes cover *is* a crash: a validator that trusts its
    input raises out of the very input it exists to reject. Letting the
    exception escape makes the probe a test *error* rather than a test failure,
    which reads as infrastructure noise — and to the mutation gate it is not
    evidence about the defect at all, because an ``AttributeError`` from a
    broken mutation and an ``AssertionError`` from a guard are both "did not
    pass" and only one of them means anything. Caught here so the verdict comes
    from the guard.
    """
    from wc_caseload_engine.manifests import _validate_money

    try:
        return _validate_money(block, documents, case_id)
    except Exception as exc:
        pytest.fail(
            f"the validator raised {type(exc).__name__} on {given} rather than "
            f"refusing it: {exc}"
        )


def _seed_body(
    scenario: dict[str, Any] | None = None,
    *,
    case_id: str = "money-probe",
    rng_seed: int = 4242,
    lifecycle: dict[str, Any] | None = None,
    documents: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """A seed that resolves, so a probe breaks in exactly one way."""
    body: dict[str, Any] = {
        "case_id": case_id,
        "rng_seed": rng_seed,
        "injury": {
            "type": "specific",
            "date_of_injury": "2021-06-14",
            "body_parts": [{"part": "lumbar_spine"}],
        },
        "lifecycle": lifecycle
        or {
            "target_stage": "resolved",
            "eval_type": "qme",
            "resolution": {"type": "c_and_r"},
        },
        "output": {"formats": ["pdf"]},
        "documents": documents or {"format_mix": {"pdf": 1.0}},
    }
    if scenario is not None:
        body["scenario"] = scenario
    return body


def _facts(scenario: dict[str, Any] | None, diligence: str = "ordinary", **kwargs: Any) -> Any:
    seed = parse_case_seed(_seed_body(scenario, **kwargs))
    return derive_money_facts(seed, build_timeline(seed), diligence)


WAGES = {"pattern": "regular", "base_weekly_wage": 1000.0}

def _docs(
    *subtypes: str,
    settlement: dict[str, Any] | None = None,
    carriers: bool = True,
) -> list[dict[str, Any]]:
    """Manifest-shaped document entries for the validator's own probes.

    The default probe seed resolves by compromise and release, so nearly every
    block under test carries a settlement — and a settlement needs its two
    carriers, dated where the rule says they belong: the approving order **on**
    the approval date, the ledger on or after the funding date. Pass the block's
    own ``settlement`` so the carriers match it.

    Without this, every probe in these classes would fail on the settlement rule
    instead of the rule it names, which is the "a probe another rule can satisfy"
    trap this review has already hit twice.
    """
    names = list(subtypes)
    entries = [{"subtype": name, "documentDate": "2021-01-01"} for name in names]
    if carriers:
        approval = (settlement or {}).get("approvalDate") or "2026-01-01"
        funding = (settlement or {}).get("fundingDate") or "2026-01-01"
        entries.append(
            {"subtype": "ORDER_APPROVING_SETTLEMENT", "documentDate": approval}
        )
        entries.append({"subtype": "BENEFIT_PAYMENT_LEDGER", "documentDate": funding})
    return entries

"""A plain, steady history. The baseline every opposite draw varies from."""

CONFIRMED_BASIS: dict[str, Any] = {
    "td_fraction": 0.6667,
    "td_max_weekly": 1800.0,
    "td_min_weekly": 240.0,
    "pd_fraction": 0.6667,
    "pd_max_weekly": 300.0,
    "pd_min_weekly": 160.0,
    "authority": "verified by counsel, memo of 2026-07-01",
    "counsel_confirmed": True,
}
"""A *complete* authored binding — the only shape that may claim confirmation.

Every figure and the authority behind them. Confirming is a claim about numbers,
so it takes the numbers; adopting the engine's unverified table and calling it
confirmed is the thing this shape exists to make impossible.
"""


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------


class TestTheGateIsTheWageBlock:
    """No ``scenario.wages`` means no money, everywhere, by one decision."""

    def test_a_seed_without_wages_derives_no_money_at_all(self) -> None:
        assert _facts(None) is None
        assert _facts({"treatment": {"status": "gap"}}) is None

    def test_a_seed_with_wages_derives_money(self) -> None:
        assert _facts({"wages": WAGES}) is not None

    @pytest.mark.parametrize("block", ["benefits", "settlement", "penalties"])
    def test_money_without_a_wage_block_is_rejected(self, block: str) -> None:
        payload = (
            {"td_weeks": 10}
            if block == "benefits"
            else ({"gross_amount": 40000} if block == "settlement" else {})
        )
        with pytest.raises(Exception) as raised:
            parse_case_seed(_seed_body({block: payload}))
        message = str(raised.value)
        assert "scenario.wages" in message
        assert block in message

    def test_the_plan_carries_the_absence_as_none(self) -> None:
        """The planner's own answer, not just the deriver's.

        Three consumers short-circuit on this ``None``; the probe checks the
        value they actually read rather than the function they read it from.
        """
        assert build_case_plan(parse_case_seed(_seed_body(None))).money_facts is None
        assert build_case_plan(parse_case_seed(_seed_body({"wages": WAGES}))).money_facts


# ---------------------------------------------------------------------------
# Method selection — the label the analyzer is scored against
# ---------------------------------------------------------------------------


class TestTheNamedMethod:
    """The method is ground truth, so it is recorded, not inferred."""

    def test_every_method_the_schema_admits_is_reachable(self) -> None:
        """No method may exist in the vocabulary and nowhere in the output.

        A label an analyzer can be scored against but no seed can produce is a
        label the corpus never teaches — the eval would be measuring a class
        with no examples in it.

        Each method is given the shape it *names*, not the same history under a
        different label. The first version of this probe gave every method the
        plain steady history, which meant it codified a seed asserting
        ``concurrent_aggregate`` over a single employment — a ground-truth label
        the manifest contradicted one field later, in a test whose job was to
        prove the labels are real.
        """
        required: dict[str, dict[str, Any]] = {
            "earning_capacity": {"earning_capacity_weekly": 1500.0},
            "concurrent_aggregate": {"concurrent_employment": True},
        }
        reached = set()
        for method in AWW_METHODS:
            wages = dict(WAGES, method=method, **required.get(method, {}))
            facts = _facts({"wages": wages})
            reached.add(facts.method)
            assert facts.wages.computation.method_source == "seed"
        assert reached == set(AWW_METHODS)

    def test_the_aggregate_label_needs_an_aggregate_to_name(self) -> None:
        """A seed may argue any method — except one that asserts a fact it lacks.

        The other four label an *argument* about how to average one history, and
        an author may make that argument over any history. ``concurrent_aggregate``
        labels a *fact*: that earnings from more than one employer were combined.
        Over a single employment there was nothing to combine, and the seed used
        to load and publish ``method: concurrent_aggregate`` beside
        ``concurrentEmployment: false``.
        """
        with pytest.raises(SeedValidationError) as caught:
            _facts({"wages": dict(WAGES, method="concurrent_aggregate")})
        assert "concurrent" in str(caught.value)

        # Both ways of supplying the fact are accepted.
        described = _facts(
            {"wages": dict(WAGES, method="concurrent_aggregate", concurrent_employment=True)}
        )
        assert described.method == "concurrent_aggregate"
        assert described.wages.concurrent_employment is True

        # And the other four are still free to be argued over the plain history.
        for method in ("actual_weekly_earnings", "irregular_earnings_average",
                       "short_history_projection"):
            assert _facts({"wages": dict(WAGES, method=method)}).method == method

    def test_a_seeded_method_wins_and_is_recorded_as_authored(self) -> None:
        facts = _facts(
            {"wages": dict(WAGES, method="concurrent_aggregate", concurrent_employment=True)}
        )
        assert facts.method == "concurrent_aggregate"
        assert facts.wages.computation.method_source == "seed"
        # ... and the opposite draw: the same history without the statement
        # selects something else, so the statement is doing the work.
        assert _facts({"wages": WAGES}).method == "actual_weekly_earnings"

    def test_concurrent_employment_selects_the_aggregate(self) -> None:
        facts = _facts({"wages": dict(WAGES, concurrent_employment=True)})
        assert facts.method == "concurrent_aggregate"
        assert facts.wages.computation.method_source == "derived"
        assert _facts({"wages": WAGES}).method != "concurrent_aggregate"

    def test_a_short_employment_history_selects_the_projection(self) -> None:
        facts = _facts({"wages": dict(WAGES, employment_start="2021-04-01")})
        assert facts.method == "short_history_projection"
        weeks = facts.wages.computation.weeks_considered
        assert weeks < SHORT_HISTORY_WEEKS, "the probe must actually be short"
        assert _facts({"wages": WAGES}).method != "short_history_projection"

    def test_irregular_earnings_select_the_irregular_average(self) -> None:
        facts = _facts({"wages": dict(WAGES, pattern="irregular")})
        assert facts.method == "irregular_earnings_average"
        # The threshold is the rule, so the probe proves the rule fired rather
        # than that the label happened to differ: the steady history's spread
        # must sit below it and the irregular one's above.
        from wc_caseload_engine.money import _coefficient_of_variation

        assert _coefficient_of_variation(facts.wages.periods) > IRREGULARITY_THRESHOLD
        steady = _facts({"wages": WAGES})
        assert _coefficient_of_variation(steady.wages.periods) <= IRREGULARITY_THRESHOLD
        assert steady.method == "actual_weekly_earnings"

    def test_earning_capacity_is_never_derived(self) -> None:
        """The catch-all is a legal argument, so only an author may reach for it.

        Swept over the shape knobs rather than asserted on one seed: a rule that
        holds for the default history and nowhere else is not a rule.
        """
        for pattern in ("regular", "irregular", "seasonal"):
            for concurrent in (False, True):
                facts = _facts(
                    {
                        "wages": dict(
                            WAGES, pattern=pattern, concurrent_employment=concurrent
                        )
                    }
                )
                assert facts.method != "earning_capacity"

    def test_earning_capacity_publishes_no_operands_and_adds_nothing(self) -> None:
        """The stated figure is the answer — the whole answer, and only it.

        The first cut published the *derived* history's operands beside a figure
        none of them produced: 26 periods, 52 weeks and $51,830.08 "considered"
        for an AWW of 1500, and then in-kind wages added on top so the published
        number was not even the number the author stated. Every other method
        publishes operands a reader can divide to reach the answer; this one
        published operands that reach a different answer.
        """
        stated = 1500.0
        facts = _facts(
            {
                "wages": dict(
                    WAGES,
                    method="earning_capacity",
                    earning_capacity_weekly=stated,
                    in_kind=[{"kind": "lodging", "weekly_value": 175.0}],
                )
            }
        )
        computation = facts.wages.computation
        assert computation.aww == money(stated)
        assert computation.in_kind_weekly == money(0)
        assert computation.periods_considered == 0
        assert computation.weeks_considered == Decimal("0.0000")
        assert computation.gross_considered == money(0)

        # The opposite draw: a computing method on the same seed *does* add the
        # in-kind value and *does* publish its operands, so the zeroes above are
        # this method's rule rather than an inert field.
        computed = _facts(
            {"wages": dict(WAGES, in_kind=[{"kind": "lodging", "weekly_value": 175.0}])}
        ).wages.computation
        assert computed.in_kind_weekly == money(175.0)
        assert computed.periods_considered > 0
        assert computed.gross_considered > money(0)
        assert computed.aww == money(
            (computed.gross_considered / computed.weeks_considered).quantize(Decimal("0.01"))
            + computed.in_kind_weekly
        )

    def test_a_listed_history_derives_its_own_pattern(self) -> None:
        """A seed that cannot state a pattern must not be given a false one.

        Forbidding the shape knobs beside a listed history (the previous review
        round) left `pattern` at its field default, so an explicit history
        alternating $100 and $3,900 a fortnight — coefficient **0.9500**, and
        selected as `irregular_earnings_average` — published `pattern: regular`.
        One history, two contradictory published labels, neither of them the
        author's doing.

        Derived from the periods now, by the same threshold `select_method`
        uses, so the two cannot disagree; `patternSource` records which happened.
        """
        start = date(2020, 6, 15)
        swinging = [
            {
                "period_start": (start + timedelta(days=14 * i)).isoformat(),
                "period_end": (start + timedelta(days=14 * i + 13)).isoformat(),
                "gross": 100.0 if i % 2 == 0 else 3900.0,
            }
            for i in range(26)
        ]
        facts = _facts({"wages": {"earnings": swinging}})
        block = money_manifest_block(facts)["wage"]
        assert block["method"] == "irregular_earnings_average"
        assert block["pattern"] == "irregular", "the pattern contradicts the method"
        assert block["patternSource"] == "derived"

        # The opposite draw on the same shape: a steady listed history derives
        # `regular`, so the label follows the earnings rather than the default.
        steady = [
            {
                "period_start": (start + timedelta(days=14 * i)).isoformat(),
                "period_end": (start + timedelta(days=14 * i + 13)).isoformat(),
                "gross": 2000.0,
            }
            for i in range(26)
        ]
        flat = money_manifest_block(_facts({"wages": {"earnings": steady}}))["wage"]
        assert flat["pattern"] == "regular"
        assert flat["patternSource"] == "derived"

        # And a described history is authored, because the knob drew the periods.
        described = money_manifest_block(
            _facts({"wages": dict(WAGES, pattern="seasonal")})
        )["wage"]
        assert described["pattern"] == "seasonal"
        assert described["patternSource"] == "seed"

    def test_pattern_provenance_names_an_author_only_when_there_was_one(self) -> None:
        """`patternSource: seed` is a claim about the seed, so it reads the seed.

        `pattern` has a default, so taking "the history was described" as
        "the author stated a pattern" published `patternSource: seed` over a
        label Pydantic supplied — provenance asserting an author who never
        spoke. `model_fields_set` is the only thing that can tell them apart.
        """
        assert (
            money_manifest_block(_facts({"wages": {}}))["wage"]["patternSource"]
            == "derived"
        )
        assert (
            money_manifest_block(_facts({"wages": {"base_weekly_wage": 1000.0}}))["wage"][
                "patternSource"
            ]
            == "derived"
        )
        # The opposite draw: state it, at its own default value, and it is authored.
        authored = money_manifest_block(
            _facts({"wages": {"base_weekly_wage": 1000.0, "pattern": "regular"}})
        )["wage"]
        assert authored["pattern"] == "regular"
        assert authored["patternSource"] == "seed"

    def test_a_figure_no_setting_consumes_is_refused(self) -> None:
        """Both fields say "required by, and only by" — and both were ignored without it."""
        with pytest.raises(SeedValidationError) as capacity:
            _facts({"wages": dict(WAGES, earning_capacity_weekly=7777.0)})
        assert "earning_capacity" in str(capacity.value)

        with pytest.raises(SeedValidationError) as concurrent:
            _facts({"wages": dict(WAGES, concurrent_weekly_wage=8888.0)})
        assert "concurrent_employment" in str(concurrent.value)

        # The controls: each figure is honoured once its enabler is present.
        capped = _facts(
            {
                "wages": dict(
                    WAGES, method="earning_capacity", earning_capacity_weekly=7777.0
                )
            }
        )
        assert capped.aww == money(7777.0)
        both = _facts(
            {"wages": dict(WAGES, concurrent_employment=True, concurrent_weekly_wage=400.0)}
        )
        assert both.wages.concurrent_periods

    def test_the_reason_is_recorded_beside_the_method(self) -> None:
        for wages in (WAGES, dict(WAGES, pattern="irregular")):
            computation = _facts({"wages": wages}).wages.computation
            assert computation.method_reason
            assert computation.method_reason != computation.method


# ---------------------------------------------------------------------------
# The arithmetic — the property that makes money worth generating
# ---------------------------------------------------------------------------


class TestTheAverageIsDerivableNotAsserted:
    """Recompute the published AWW from the published operands."""

    @pytest.mark.parametrize(
        "wages",
        [
            WAGES,
            dict(WAGES, pattern="irregular"),
            dict(WAGES, pattern="seasonal"),
            dict(WAGES, overtime_share=0.2),
            dict(WAGES, employment_start="2021-01-04"),
            dict(WAGES, concurrent_employment=True, concurrent_weekly_wage=450.0),
            dict(WAGES, in_kind=[{"kind": "lodging", "weekly_value": 175.0}]),
        ],
        ids=[
            "regular",
            "irregular",
            "seasonal",
            "overtime",
            "short",
            "concurrent",
            "in-kind",
        ],
    )
    def test_the_aww_follows_from_the_periods_on_the_statement(
        self, wages: dict[str, Any]
    ) -> None:
        facts = _facts({"wages": wages})
        computation = facts.wages.computation
        primary = facts.wages.primary_periods
        considered = (
            facts.wages.periods
            if computation.method == "concurrent_aggregate"
            else primary
        )

        gross = sum((period.gross for period in considered), Decimal("0"))
        weeks = sum((period.weeks for period in primary), Decimal("0"))
        expected = money(gross / weeks + computation.in_kind_weekly)

        assert computation.aww == expected
        assert computation.gross_considered == money(gross)
        assert computation.periods_considered == len(considered)

    def test_the_aggregate_divides_by_the_calendar_both_employers_cover(self) -> None:
        """The denominator is the union of the periods, not the sum of their weeks.

        Two employments running over the same calendar are combined by adding
        their earnings and dividing by the calendar they share. Summing period
        weeks instead double-counts any day two periods both cover, and a
        payroll history has such days in it: a re-issued or corrected pay period
        overlaps the one it corrects. It is a well-formed history — every period
        is valid, and the two employments still cover the same span, so the rule
        that refuses unequal concurrent coverage does not reach it.

        Reproduced before it was asserted. The overlapping fortnight below makes
        the summed denominator fifty weeks against a real calendar of
        forty-eight, and moves the published average weekly wage from $1,491.67
        to $1,432.00 — a wage the page's own operands do not reproduce.

        This guard exists because the mutation naming it pointed at a class that
        never existed, so pytest collected nothing, exited 4, and the gate
        scored it green. The open question when that surfaced was whether any
        valid history still tells the two denominators apart, now that unequal
        concurrent coverage is refused outright. It does, and this is it.
        """
        start = date(2021, 1, 4)
        fortnights = 24

        def series(gross: float, *, concurrent: bool) -> list[dict[str, Any]]:
            return [
                {
                    "period_start": (start + timedelta(days=14 * index)).isoformat(),
                    "period_end": (start + timedelta(days=14 * index + 13)).isoformat(),
                    "gross": gross,
                    **({"concurrent": True} if concurrent else {}),
                }
                for index in range(fortnights)
            ]

        primary = series(2000.0, concurrent=False)
        # A corrected pay period, re-issued across the boundary of the one it
        # replaces. Seven days of it are days the history already covers.
        primary.append(
            {
                "period_start": (start + timedelta(days=14 * 5 + 7)).isoformat(),
                "period_end": (start + timedelta(days=14 * 6 + 6)).isoformat(),
                "gross": 2000.0,
            }
        )
        # Built here rather than through `_seed_body`, whose fixed date of injury
        # sits in the middle of this history.
        seed = parse_case_seed(
            {
                "case_id": "concurrent-overlap",
                "rng_seed": 7,
                "injury": {
                    "type": "specific",
                    "date_of_injury": "2021-12-20",
                    "body_parts": [{"part": "lumbar_spine", "icd10": "M54.5"}],
                },
                "lifecycle": {"target_stage": "medical_legal", "eval_type": "qme"},
                "scenario": {
                    "wages": {
                        "earnings": primary + series(900.0, concurrent=True),
                        "concurrent_employment": True,
                    }
                },
            }
        )
        facts = derive_money_facts(seed, build_timeline(seed), "ordinary")
        computation = facts.wages.computation
        assert computation.method == "concurrent_aggregate", computation.method

        summed = sum(
            (period.weeks for period in facts.wages.periods if not period.concurrent),
            Decimal("0"),
        )
        covered = computation.weeks_considered
        assert summed > covered, (
            f"the probe needs an overlap to discriminate: summed {summed} against "
            f"covered {covered}"
        )
        assert covered == Decimal("48.0000"), covered
        assert computation.aww == (computation.gross_considered / covered).quantize(
            Decimal("0.01")
        ), (computation.aww, computation.gross_considered, covered)
        # …and explicitly not the summed-weeks answer the defect published.
        assert computation.aww != (computation.gross_considered / summed).quantize(
            Decimal("0.01")
        )

    def test_the_gross_on_each_period_is_its_own_parts(self) -> None:
        """Overtime is *inside* gross, as payroll prints it — checked, not assumed."""
        facts = _facts({"wages": dict(WAGES, overtime_share=0.25)})
        for period in facts.wages.periods:
            assert period.gross == money(period.regular_gross + period.overtime_gross)
        assert any(period.overtime_gross > 0 for period in facts.wages.periods)
        # Opposite draw: no overtime share, no overtime anywhere.
        plain = _facts({"wages": WAGES})
        assert all(period.overtime_gross == 0 for period in plain.wages.periods)

    def test_in_kind_wages_raise_the_average_by_exactly_their_weekly_value(self) -> None:
        without = _facts({"wages": WAGES})
        with_kind = _facts(
            {"wages": dict(WAGES, in_kind=[{"kind": "lodging", "weekly_value": 175.0}])}
        )
        assert with_kind.aww - without.aww == money(175.0)

    def test_explicit_earnings_are_used_verbatim(self) -> None:
        """A stated history is the history — no derivation may edit it."""
        entries = [
            {"period_start": "2021-01-04", "period_end": "2021-01-17", "gross": 2400.0},
            {
                "period_start": "2021-01-18",
                "period_end": "2021-01-31",
                "gross": 1600.0,
                "overtime": 200.0,
            },
        ]
        facts = _facts({"wages": {"earnings": entries}})
        assert [str(p.gross) for p in facts.wages.periods] == ["2400.00", "1600.00"]
        assert facts.wages.computation.gross_considered == money(4000.0)
        assert facts.wages.computation.weeks_considered == Decimal("4.0000")
        assert facts.aww == money(1000.0)


class TestTheRateFollowsFromTheAverage:
    """The comp rate is reproducible from the wage facts by the named method."""

    @pytest.mark.parametrize("base", [400.0, 1000.0, 2200.0, 6000.0])
    def test_the_rate_recomputes_from_the_aww_and_the_published_basis(
        self, base: float
    ) -> None:
        facts = _facts({"wages": dict(WAGES, base_weekly_wage=base)})
        rate = facts.wages.rate
        recomputed = compute_comp_rate(facts.aww, rate.basis)
        assert recomputed.td_weekly_rate == rate.td_weekly_rate
        assert recomputed.pd_weekly_rate == rate.pd_weekly_rate
        assert recomputed.td_bound == rate.td_bound

    def test_a_high_earner_is_capped_and_the_cap_is_recorded(self) -> None:
        facts = _facts({"wages": dict(WAGES, base_weekly_wage=6000.0)})
        rate = facts.wages.rate
        assert rate.td_bound == "max"
        assert rate.td_weekly_rate == rate.basis.td_max_weekly
        # Opposite draw on the same axis: a mid earner is not capped, so the
        # cap is a consequence of the wage rather than a constant.
        mid = _facts({"wages": dict(WAGES, base_weekly_wage=1000.0)}).wages.rate
        assert mid.td_bound == "unbounded"
        assert mid.td_weekly_rate < mid.basis.td_max_weekly

    def test_a_low_earner_is_floored_and_the_floor_is_recorded(self) -> None:
        facts = _facts({"wages": dict(WAGES, base_weekly_wage=50.0)})
        rate = facts.wages.rate
        assert rate.td_bound == "min"
        assert rate.td_weekly_rate == rate.basis.td_min_weekly

    def test_the_rate_is_keyed_to_the_date_of_injury(self) -> None:
        """Two seeds alike but for the injury date get different bindings.

        The substrate's own wage statement hardcodes one vintage's ceiling, so
        every file in a multi-year caseload was rated under it. This is the
        probe that would have caught that.
        """
        seen: dict[str, str] = {}
        for doi in ("2010-03-02", "2016-03-02", "2020-03-02", "2024-03-02"):
            body = _seed_body({"wages": dict(WAGES, base_weekly_wage=6000.0)})
            body["injury"]["date_of_injury"] = doi
            body["lifecycle"] = {"target_stage": "medical_legal", "eval_type": "qme"}
            seed = parse_case_seed(body)
            facts = derive_money_facts(seed, build_timeline(seed))
            seen[doi] = f"{facts.wages.rate.basis.label}:{facts.wages.rate.td_weekly_rate}"
        assert len(set(seen.values())) == len(seen), seen


# ---------------------------------------------------------------------------
# Legal accuracy — no number here is verified law
# ---------------------------------------------------------------------------


class TestNoStatutoryNumberIsPresentedAsVerified:
    """Every binding is table-supplied and marked counsel-unconfirmed."""

    def test_no_shipped_vintage_claims_confirmation(self) -> None:
        for basis in UNCONFIRMED_RATE_TABLE:
            assert basis.counsel_confirmed is False, basis.label
            assert basis.source == "engine_default_table"

    def test_every_shipped_authority_says_so_in_its_own_text(self) -> None:
        """The caveat travels with the citation, not only with the flag.

        A reader who copies the authority string out of a manifest and pastes it
        into a brief must not be able to lose the caveat on the way.
        """
        for basis in UNCONFIRMED_RATE_TABLE:
            assert "COUNSEL-UNCONFIRMED" in basis.authority, basis.label

    def test_the_table_is_the_only_source_of_a_binding(self) -> None:
        """``rate_basis_for`` is the seam, and it answers for any date."""
        for doi in ("1971-01-01", "2013-12-31", "2014-01-01", "2099-06-06"):
            basis = rate_basis_for(parse_case_seed(_seed_body(None)).injury.onset_date)
            assert basis in UNCONFIRMED_RATE_TABLE
            from datetime import date as _date

            year, month, day = (int(part) for part in doi.split("-"))
            assert rate_basis_for(_date(year, month, day)) in UNCONFIRMED_RATE_TABLE

    def test_a_seed_may_supply_a_confirmed_binding_and_it_is_recorded_as_authored(
        self,
    ) -> None:
        facts = _facts(
            {
                "wages": dict(
                    WAGES,
                    base_weekly_wage=6000.0,
                    rate_basis=dict(CONFIRMED_BASIS, td_max_weekly=2500.0),
                )
            }
        )
        basis = facts.wages.rate.basis
        assert basis.counsel_confirmed is True
        assert basis.source == "seed"
        assert facts.wages.rate.td_weekly_rate == money(2500.0)
        # The engine's own default cannot reach that state.
        default = _facts({"wages": dict(WAGES, base_weekly_wage=6000.0)})
        assert default.wages.rate.basis.counsel_confirmed is False

    def test_confirmation_without_the_numbers_is_refused(self) -> None:
        """The five-word laundering: confirm the engine's table without restating it.

        Found by review. ``rate_basis: {counsel_confirmed: true}`` alone used to
        publish every engine-default figure as counsel-confirmed, under an
        authority string still reading ``COUNSEL-UNCONFIRMED`` — the one claim
        this package promises it can never make, reachable from a seed.
        """
        with pytest.raises(SeedValidationError) as caught:
            _facts({"wages": dict(WAGES, rate_basis={"counsel_confirmed": True})})
        assert "counsel_confirmed" in str(caught.value)

        # Opposite draw: the same block short of exactly one figure is still refused,
        # so the rule is "a whole binding", not "some numbers were mentioned".
        short = {k: v for k, v in CONFIRMED_BASIS.items() if k != "pd_min_weekly"}
        with pytest.raises(SeedValidationError):
            _facts({"wages": dict(WAGES, rate_basis=short)})

    def test_an_unstated_override_leaves_the_table_untouched(self) -> None:
        """An override that authors nothing must not be recorded as authored."""
        plain = _facts({"wages": WAGES}).wages.rate.basis
        empty = _facts(
            {"wages": dict(WAGES, rate_basis={"counsel_confirmed": False})}
        ).wages.rate.basis
        assert empty == plain
        assert empty.source == "engine_default_table"

    def test_a_partial_override_cannot_invert_the_merged_bounds(self) -> None:
        """A floor above a defaulted ceiling used to produce a rate above the maximum.

        The seed-level check compares the override's *own* pair, so a block
        stating only a minimum showed it a floor with no ceiling beside it and
        passed. Measured before the fix: a $5,000 floor merged under the
        $1,539.71 default ceiling and ``compute_comp_rate`` returned $5,000,
        recorded as ``tdBound: min`` — a temporary-disability rate above the
        maximum the same basis published.
        """
        from pydantic import ValidationError as _ModelValidationError

        # What the seed rule buys is the *message*, and the mutation gate is
        # what made that precise. Remove the rule and the number is still
        # refused — by `RateBasis._bounds_are_ordered`, one layer down, as a
        # pydantic error about a merged ceiling the seed author never wrote.
        # Letting that escape scores ERROR-ValidationError, which proves a
        # crash; caught here, the guard proves the defect it is actually for.
        try:
            with pytest.raises(SeedValidationError) as caught:
                _facts({"wages": dict(WAGES, rate_basis={"td_min_weekly": 5000.0})})
        except _ModelValidationError as exc:
            pytest.fail(
                "a lone td_min_weekly reached the model backstop and raised "
                f"{type(exc).__name__} — the seed-level pairing rule that names "
                "td_max_weekly, at the layer holding the line the author wrote, "
                "is gone"
            )
        assert "td_max_weekly" in str(caught.value)

        # And stated as a pair but the wrong way round, which is the plain case.
        with pytest.raises(SeedValidationError) as inverted:
            _facts(
                {
                    "wages": dict(
                        WAGES,
                        rate_basis={"td_min_weekly": 5000.0, "td_max_weekly": 1000.0},
                    )
                }
            )
        assert "ceiling" in str(inverted.value)

        # The control: the same figure under a ceiling that admits it is fine.
        ok = _facts(
            {
                "wages": dict(
                    WAGES,
                    base_weekly_wage=9000.0,
                    rate_basis={"td_min_weekly": 5000.0, "td_max_weekly": 6000.0},
                )
            }
        )
        assert ok.wages.rate.basis.td_min_weekly == money(5000.0)

    def test_no_shipped_vintage_inverts_its_own_bounds(self) -> None:
        for basis in UNCONFIRMED_RATE_TABLE:
            assert basis.td_min_weekly <= basis.td_max_weekly
            assert basis.pd_min_weekly <= basis.pd_max_weekly

    def test_the_model_refuses_an_inverted_basis_however_it_was_built(self) -> None:
        """The backstop, probed where the seed rule cannot shadow it.

        Found by mutation: deleting :meth:`RateBasis._bounds_are_ordered`
        entirely left every probe green, because the seed-level pairing rule
        rejects the reported seed first and nothing else ever built a basis by
        hand. A guard reached only through a guard that already refused the
        input is not being tested.

        So this constructs one directly. The model is the layer every path goes
        through — the shipped table, the merge in
        ``_apply_rate_basis_override``, and any future authority (KB-167) that
        returns a :class:`RateBasis` of its own — and it is the only layer that
        sees the *merged* numbers.
        """
        import datetime as dt

        from pydantic import ValidationError

        from wc_caseload_engine.money import RateBasis

        good = UNCONFIRMED_RATE_TABLE[-1].model_dump()
        with pytest.raises(ValidationError) as caught:
            RateBasis(**{**good, "td_min_weekly": Decimal("5000.00")})
        assert "ceiling" in str(caught.value)

        with pytest.raises(ValidationError):
            RateBasis(**{**good, "pd_min_weekly": Decimal("9999.00")})

        # The control: the same construction with an ordered pair is fine, so the
        # refusals above are about the inversion and not about building one here.
        ok = RateBasis(
            **{
                **good,
                "label": "probe",
                "effective_from": dt.date(2023, 1, 1),
                "td_min_weekly": Decimal("240.00"),
                "td_max_weekly": Decimal("1800.00"),
            }
        )
        assert ok.td_min_weekly < ok.td_max_weekly

    def test_the_manifest_publishes_the_caveat(self) -> None:
        block = money_manifest_block(_facts({"wages": WAGES}))
        assert block["rate"]["counselConfirmed"] is False
        assert "COUNSEL-UNCONFIRMED" in block["rate"]["basisAuthority"]


# ---------------------------------------------------------------------------
# Benefit ledger
# ---------------------------------------------------------------------------


class TestTheBenefitLedger:
    """Gaps and lateness are stated facts with the days recorded."""

    def test_the_gap_knob_opens_a_gap_and_records_it(self) -> None:
        wet = _facts({"wages": WAGES, "benefits": {"td_weeks": 24, "td_gap_days": 90}})
        assert [gap.days for gap in wet.benefits.gaps] == [90]
        gap = wet.benefits.gaps[0]
        assert (gap.end - gap.start).days + 1 == 90
        # ... and the periods on either side genuinely straddle it.
        before = [p for p in wet.benefits.td_periods if p.end < gap.start]
        after = [p for p in wet.benefits.td_periods if p.start > gap.end]
        assert before and after
        # Opposite draw: same seed, no gap knob, no gap.
        dry = _facts({"wages": WAGES, "benefits": {"td_weeks": 24}})
        assert dry.benefits.gaps == ()

    def test_the_late_payment_knobs_produce_recorded_lateness(self) -> None:
        wet = _facts(
            {
                "wages": WAGES,
                "benefits": {"td_weeks": 24, "late_payments": 3, "max_days_late": 40},
            }
        )
        assert wet.benefits.late_payment_count == 3
        assert wet.benefits.max_days_late == 40
        for period in wet.benefits.td_periods:
            if period.days_late:
                assert period.date_paid is not None
                assert (period.date_paid - period.end).days > period.days_late
        dry = _facts(
            {"wages": WAGES, "benefits": {"td_weeks": 24, "late_payments": 0}}
        )
        assert dry.benefits.late_payment_count == 0
        assert dry.benefits.max_days_late == 0

    def test_diligence_drives_lateness_when_the_seed_states_none(self) -> None:
        """One persona, both the paperwork and the payments.

        This is the property Wave 3 attaches to: a negligent administrator
        produces *known* exposure without the seed having to spell it out.
        """
        scenario = {"wages": WAGES, "benefits": {"td_weeks": 24}}
        attentive = _facts(scenario, "attentive")
        negligent = _facts(scenario, "negligent")
        assert attentive.benefits.late_payment_count == 0
        assert attentive.benefits.max_days_late == 0
        assert negligent.benefits.late_payment_count > 0
        assert negligent.benefits.max_days_late > attentive.benefits.max_days_late

    def test_the_persona_reaches_the_money_through_the_planner(self) -> None:
        """Not just the deriver: the seed's own persona has to arrive.

        ``derive_money_facts`` takes diligence as an argument, so passing it
        directly proves only that the argument works. This checks the wiring —
        a seed stating ``adjuster.diligence`` reaches the ledger through
        ``build_case_plan``.
        """
        counts = {}
        for diligence in ("attentive", "negligent"):
            seed = parse_case_seed(
                _seed_body(
                    {
                        "wages": WAGES,
                        "benefits": {"td_weeks": 24},
                        "adjuster": {"diligence": diligence},
                    }
                )
            )
            counts[diligence] = build_case_plan(seed).money_facts.benefits.max_days_late
        assert counts["attentive"] == 0
        assert counts["negligent"] > 0

    def test_a_stated_control_the_ledger_cannot_honour_is_refused(self) -> None:
        """ISC-29's rule applied to money: an explicit control wins, or says it did not.

        Both shapes below loaded and were silently dropped — the first published
        `latePayments: 0` for a seed asking for three, the second `gapDays: 0`
        for a seed asking for ninety.
        """
        with pytest.raises(SeedValidationError) as caught:
            _facts(
                {
                    "wages": WAGES,
                    "benefits": {
                        "td_weeks": 0,
                        "pd_advances": 0,
                        "late_payments": 3,
                        "max_days_late": 62,
                    },
                }
            )
        assert "late" in str(caught.value)

        with pytest.raises(SeedValidationError) as gap:
            _facts({"wages": WAGES, "benefits": {"td_weeks": 0, "td_gap_days": 90}})
        assert "td_gap_days" in str(gap.value)

        # The controls: the same knobs on a run that can hold them are honoured.
        honoured = _facts(
            {
                "wages": WAGES,
                "benefits": {"td_weeks": 12, "late_payments": 3, "max_days_late": 62},
            }
        )
        assert honoured.benefits.late_payment_count == 3
        gapped = _facts({"wages": WAGES, "benefits": {"td_weeks": 12, "td_gap_days": 90}})
        assert sum(g.days for g in gapped.benefits.gaps) == 90

    def test_a_control_the_runway_truncates_is_reported(self) -> None:
        """What the seed cannot see, the planner says out loud.

        Truncation needs the timeline, so it is a plan warning rather than a
        seed error — the same distinction this package already draws between an
        impossible seed and one whose story outruns its calendar. Silence was
        the third option and the wrong one: `td_weeks: 520` on a file whose
        runway holds a dozen is a request reduced by a factor of forty.
        """
        plan = build_case_plan(
            parse_case_seed(
                _seed_body({"wages": WAGES, "benefits": {"td_weeks": 520}})
            )
        )
        assert any("td_weeks" in warning for warning in plan.warnings), plan.warnings

        # The opposite draw: a run the runway holds warns about nothing.
        quiet = build_case_plan(
            parse_case_seed(_seed_body({"wages": WAGES, "benefits": {"td_weeks": 8}}))
        )
        assert not any("td_weeks" in warning for warning in quiet.warnings), quiet.warnings

    def test_lateness_the_ledger_could_not_deliver_is_reported(self) -> None:
        """Eight weeks is two four-week blocks, so three late payments cannot happen.

        The seed schema refuses lateness with nothing paid at all; it cannot
        count blocks. `{td_weeks: 8, pd_advances: 0, late_payments: 3}`
        published `latePayments: 2` and said nothing.
        """
        plan = build_case_plan(
            parse_case_seed(
                _seed_body(
                    {
                        "wages": WAGES,
                        "benefits": {
                            "td_weeks": 8,
                            "pd_advances": 0,
                            "late_payments": 3,
                            "max_days_late": 62,
                        },
                    }
                )
            )
        )
        assert any("late_payments" in w for w in plan.warnings), plan.warnings

        # The opposite draw: a run long enough to carry three is silent.
        quiet = build_case_plan(
            parse_case_seed(
                _seed_body(
                    {
                        "wages": WAGES,
                        "benefits": {
                            "td_weeks": 20,
                            "late_payments": 3,
                            "max_days_late": 62,
                        },
                    }
                )
            )
        )
        assert not any("late_payments" in w for w in quiet.warnings), quiet.warnings

    def test_a_max_delay_without_a_count_is_refused(self) -> None:
        """The pair is the fact. Alone, the count came from the persona.

        On an `attentive` administrator that is zero, so a stated sixty-two-day
        delay published no lateness at all.
        """
        with pytest.raises(SeedValidationError) as caught:
            _facts({"wages": WAGES, "benefits": {"td_weeks": 12, "max_days_late": 62}})
        assert "late_payments" in str(caught.value)

    def test_a_settlement_the_case_never_funded_says_so(self) -> None:
        """Approved and not yet funded is a state, and `funding_date` is optional for it.

        `approval_date: 2025-12-31` with `funding_days: 730` derived a funding
        date of 2027-12-31 — two years past the date this engine calls today,
        published as fact beside documents dated 2026-01-01 or earlier.
        """
        facts = _facts(
            {
                "wages": WAGES,
                "settlement": {"approval_date": "2025-12-31", "funding_days": 730},
            }
        )
        assert facts.settlement is not None
        assert facts.settlement.approval_date == date(2025, 12, 31)
        assert facts.settlement.funding_date is None
        assert facts.settlement.funding_lag_days is None

        # Both return paths of ``_money_control_warnings``: a seed with no
        # benefits block takes the early return, one with a block takes the main
        # one. Mutation found that only the first was probed, so deleting the
        # settlement report from the main path stayed green.
        for benefits in (None, {"td_weeks": 12}):
            scenario: dict[str, Any] = {
                "wages": WAGES,
                "settlement": {"approval_date": "2025-12-31", "funding_days": 730},
            }
            if benefits is not None:
                scenario["benefits"] = benefits
            plan = build_case_plan(parse_case_seed(_seed_body(scenario)))
            assert any("not yet funded" in w for w in plan.warnings), (
                benefits,
                plan.warnings,
            )

        # The opposite draw: a lag the case reaches is funded and reported.
        funded = _facts(
            {
                "wages": WAGES,
                "settlement": {"approval_date": "2025-01-06", "funding_days": 30},
            }
        )
        assert funded.settlement.funding_date == date(2025, 2, 5)
        assert funded.settlement.funding_lag_days == 30

    def test_no_gap_outlives_the_run_it_interrupts(self) -> None:
        """A hole in a series needs a series on both sides of it.

        The gap was banked when it was planned rather than when the period on
        its far side was emitted, so the run could end *on* a gap — one reaching
        past the horizon, printed on a payment record dated before most of it.

        The gap has to be long enough to walk the run off the end of the case,
        which is the corner the first version of this sweep missed entirely: a
        200-day gap on a 2025 injury still leaves room for the next block, so
        eager banking and lazy banking agree and the mutant lived. `td_gap_days:
        700` on a 2024-06-01 intake file banks a gap running to **2026-06-01** —
        five months past the horizon, on a ledger with nothing after it.
        """
        checked = 0
        gapped = 0
        for doi, stage in (
            ("2024-06-01", "intake"),
            ("2024-11-01", "discovery"),
            ("2025-01-15", "intake"),
            ("2025-03-01", "active_treatment"),
        ):
            for gap_days in (200, 400, 700, 1000):
                for weeks in (12, 20, 40):
                    body = _seed_body(
                        {
                            "wages": WAGES,
                            "benefits": {"td_weeks": weeks, "td_gap_days": gap_days},
                        },
                        lifecycle={"target_stage": stage, "eval_type": "none"},
                    )
                    body["injury"]["date_of_injury"] = doi
                    try:
                        seed = parse_case_seed(body)
                    except SeedValidationError:
                        continue
                    timeline = build_timeline(seed)
                    facts = derive_money_facts(seed, timeline, "ordinary")
                    assert facts is not None
                    checked += 1
                    ledger = facts.benefits
                    gapped += len(ledger.gaps)
                    for gap in ledger.gaps:
                        assert gap.end <= timeline.horizon, (
                            f"a gap ran to {gap.end}, past the horizon "
                            f"{timeline.horizon} — doi={doi} td_gap_days={gap_days}"
                        )
                        assert any(p.start > gap.end for p in ledger.td_periods), (
                            f"a gap ending {gap.end} interrupts nothing — no benefit "
                            f"period resumes after it (doi={doi} td_gap_days={gap_days})"
                        )
        assert checked > 20, f"the sweep only reached {checked} seeds"
        assert gapped > 0, (
            "the sweep produced no gaps at all, so it proves nothing about them"
        )

    def test_no_benefit_event_falls_past_the_horizon(self) -> None:
        """A payment no document in the case can report is one the case never reached.

        Measured before the fix: a loadable seed put a temporary-disability
        payment **588 days** past the timeline horizon, and `timeline.clamp`
        then dated the payment record before its own payment — clamping cannot
        repair a future event. The rule the advances already followed now covers
        the periods too, and covers advances by their *paid* date rather than
        only their schedule.

        The advances need their own corner of the sweep. Their schedule is
        bounded by the *benefit* window, which always sits inside the timeline
        horizon, so a schedule-only check looks sufficient until a long delay is
        applied to an advance scheduled near the end of a recent file: DOI
        2024-01-10, resolved, `max_days_late: 730` schedules an advance on
        2024-01-25 and pays it 2026-01-24, three weeks past the horizon.
        """
        checked = 0
        advances_checked = 0
        cases: list[tuple[str, dict[str, Any]]] = [
            (doi, {"target_stage": stage, "eval_type": "none"})
            for doi in ("2024-06-01", "2025-01-15", "2025-06-01")
            for stage in ("intake", "discovery", "active_treatment")
        ] + [
            (doi, {"target_stage": "resolved", "eval_type": "none",
                   "resolution": {"type": resolution}})
            for doi in ("2023-06-01", "2024-01-10")
            for resolution in ("c_and_r", "stipulations")
        ]
        for doi, lifecycle in cases:
            for late in (365, 500, 730):
                body = _seed_body(
                    {
                        "wages": WAGES,
                        "benefits": {
                            "td_weeks": 8,
                            "pd_advances": 6,
                            "late_payments": 9,
                            "max_days_late": late,
                        },
                    },
                    lifecycle=lifecycle,
                )
                body["injury"]["date_of_injury"] = doi
                try:
                    seed = parse_case_seed(body)
                except SeedValidationError:
                    continue
                timeline = build_timeline(seed)
                facts = derive_money_facts(seed, timeline, "ordinary")
                assert facts is not None
                checked += 1
                for period in facts.benefits.td_periods:
                    assert period.date_paid is None or period.date_paid <= timeline.horizon, (
                        f"a TD payment landed {period.date_paid}, past the horizon "
                        f"{timeline.horizon} — doi={doi} max_days_late={late}"
                    )
                for advance in facts.benefits.pd_advances:
                    advances_checked += 1
                    assert advance.date_paid <= timeline.horizon, (
                        f"a PD advance was paid {advance.date_paid}, past the horizon "
                        f"{timeline.horizon} — doi={doi} max_days_late={late}"
                    )
        assert checked > 10, f"the sweep only reached {checked} seeds"
        assert advances_checked > 5, (
            f"the sweep reached only {advances_checked} advances — the PD half of this "
            "rule would go unprobed"
        )

    def test_pd_advances_carry_their_due_date_and_are_ordered_by_it(self) -> None:
        """The same fix as TD's, applied to the half no reviewer had named.

        Four advances came back dated 08-30, 10-14, 11-28 and 11-11, three of
        them marked 62 days late, with nothing on the record saying late against
        *what*. The apparent disorder is a real fact of a neglected file — a
        delayed advance can land after a later on-time one — but it only reads
        as a fact once the schedule it slipped from is on the page.
        """
        facts = _facts(
            {
                "wages": WAGES,
                "benefits": {"td_weeks": 4, "pd_advances": 4, "late_payments": 4,
                             "max_days_late": 62},
            }
        )
        advances = facts.benefits.pd_advances
        assert advances, "the probe needs advances to say anything"
        due = [a.date_due for a in advances]
        assert due == sorted(due), "the ledger is ordered by the schedule"
        for advance in advances:
            assert (advance.date_paid - advance.date_due).days == advance.days_late

        published = money_manifest_block(facts)["benefits"]["pdAdvances"]
        assert published and all("dateDue" in a for a in published)

    def test_amounts_are_the_rate_times_the_weeks(self) -> None:
        facts = _facts({"wages": WAGES, "benefits": {"td_weeks": 20}})
        rate = facts.wages.rate.td_weekly_rate
        for period in facts.benefits.td_periods:
            assert period.amount == money(rate * period.weeks)
        assert facts.benefits.td_total == money(
            sum(p.amount for p in facts.benefits.td_periods)
        )

    def test_pd_advances_are_countable_and_dated(self) -> None:
        wet = _facts({"wages": WAGES, "benefits": {"pd_advances": 4}})
        assert len(wet.benefits.pd_advances) == 4
        dates = [advance.date_paid for advance in wet.benefits.pd_advances]
        assert dates == sorted(dates)
        dry = _facts({"wages": WAGES, "benefits": {"pd_advances": 0}})
        assert dry.benefits.pd_advances == ()


# ---------------------------------------------------------------------------
# Settlement
# ---------------------------------------------------------------------------


class TestTheAutomaticLateIndemnityIncrease:
    """The §4650(d) ledger is pure arithmetic over the decided payment ledger."""

    @staticmethod
    def _penalised() -> Any:
        return _facts(
            {
                "wages": WAGES,
                "benefits": {
                    "td_weeks": 8,
                    "late_payments": 2,
                    "max_days_late": 15,
                },
                "penalties": {},
            }
        )

    def test_the_planted_positive_control_assesses_the_stated_45_day_delay(self) -> None:
        """Planted control: at least one late payment must carry a §4650(d) increase."""
        facts = self._penalised()
        ledger = facts.penalties
        assert ledger is not None
        assert ledger.assessed_count == 2
        assert [item.days_late for item in ledger.assessments] == [45, 59]
        assert ledger.assessments[0].days_late == 45
        assert [(item.source, item.ordinal) for item in ledger.assessments] == [
            ("td_period", 1),
            ("td_period", 2),
        ]
        for assessment in ledger.assessments:
            assert assessment.amount == money(
                assessment.principal * assessment.increase_fraction
            )
        assert ledger.total_increase == money(sum(item.amount for item in ledger.assessments))
        assert ledger.principal_assessed == money(
            sum(item.principal for item in ledger.assessments)
        )

    @staticmethod
    def _seed(case_id: str) -> Any:
        return parse_case_seed(
            _seed_body({"wages": WAGES, "penalties": {}}, case_id=case_id)
        )

    def test_operationally_late_but_statutorily_timely_is_not_assessed(self) -> None:
        onset = date(2021, 6, 14)
        advance = money_module.PdAdvance(
            date_due=onset + timedelta(days=5),
            date_paid=onset + timedelta(days=10),
            amount=Decimal("400.00"),
            weekly_rate=Decimal("100.00"),
            weeks=Decimal("4"),
            days_late=5,
        )
        ledger = money_module._derive_penalties(
            self._seed("operational-only-delay"),
            money_module.BenefitLedger(pd_advances=(advance,)),
            onset,
            onset,
        )

        entry = ledger.schedule[0]
        assert entry.operational_due_date < entry.date_paid
        assert entry.statutory_due_date is not None
        assert entry.date_paid <= entry.statutory_due_date
        assert entry.days_late == 0
        assert ledger.assessments == ()

    def test_paid_td_after_its_statutory_deadline_is_assessed_exactly(self) -> None:
        onset = date(2021, 6, 14)
        period = money_module.TdPeriod(
            start=onset,
            end=onset + timedelta(days=6),
            weeks=Decimal("1"),
            weekly_rate=Decimal("100.00"),
            amount=Decimal("100.00"),
            date_due=onset + timedelta(days=20),
            date_paid=onset + timedelta(days=21),
            days_late=1,
        )
        ledger = money_module._derive_penalties(
            self._seed("statutory-td-delay"),
            money_module.BenefitLedger(td_periods=(period,)),
            onset,
            onset,
        )

        assessment = ledger.assessments[0]
        assert assessment.rule == "first_td_payment"
        assert assessment.days_late == (
            assessment.date_paid - assessment.statutory_due_date
        ).days
        assert assessment.amount == money(
            assessment.principal * assessment.increase_fraction
        )

    def test_only_first_pd_advance_can_have_a_statutory_assessment(self) -> None:
        onset = date(2021, 6, 14)
        td_paid = onset + timedelta(days=20)
        period = money_module.TdPeriod(
            start=onset,
            end=onset + timedelta(days=6),
            weeks=Decimal("1"),
            weekly_rate=Decimal("100.00"),
            amount=Decimal("100.00"),
            date_due=onset + timedelta(days=14),
            date_paid=td_paid,
            days_late=6,
        )
        advances = (
            money_module.PdAdvance(
                date_due=onset + timedelta(days=25),
                date_paid=onset + timedelta(days=40),
                amount=Decimal("400.00"),
                weekly_rate=Decimal("100.00"),
                weeks=Decimal("4"),
                days_late=15,
            ),
            money_module.PdAdvance(
                date_due=onset + timedelta(days=70),
                date_paid=onset + timedelta(days=115),
                amount=Decimal("400.00"),
                weekly_rate=Decimal("100.00"),
                weeks=Decimal("4"),
                days_late=45,
            ),
        )
        ledger = money_module._derive_penalties(
            self._seed("statutory-pd-delay"),
            money_module.BenefitLedger(td_periods=(period,), pd_advances=advances),
            onset,
            onset,
        )

        pd_assessments = [a for a in ledger.assessments if a.source == "pd_advance"]
        assert len(pd_assessments) == 1
        first = pd_assessments[0]
        assert first.ordinal == 1
        assert first.statutory_due_date == (
            td_paid + timedelta(days=ledger.deadlines.first_pd_payment_days)
        )
        assert first.days_late == (first.date_paid - first.statutory_due_date).days
        later = ledger.schedule[-1]
        assert later.operational_due_date < later.date_paid
        assert later.rule == "discretionary_advance"
        assert later.statutory_due_date is None
        assert later.days_late == 0

    @pytest.mark.parametrize(
        ("override", "source"),
        [
            ({}, "engine_default_table"),
            ({"increase_fraction": "0.25"}, "mixed"),
            ({"authority": "seed authority"}, "mixed"),
            (
                {"increase_fraction": "0.25", "authority": "seed authority"},
                "seed",
            ),
        ],
    )
    def test_the_basis_records_how_much_the_seed_authored(
        self, override: dict[str, Any], source: str
    ) -> None:
        facts = _facts(
            {
                "wages": WAGES,
                "benefits": {"td_weeks": 8, "late_payments": 1, "max_days_late": 45},
                "penalties": override,
            }
        )
        assert facts.penalties is not None
        assert facts.penalties.basis.source == source
        if "increase_fraction" in override:
            assert facts.penalties.basis.increase_fraction == Decimal("0.25")

    def test_absence_and_an_empty_assessment_are_different_public_facts(self) -> None:
        absent = self._penalised().model_copy(update={"penalties": None})
        assert "penalties" not in money_manifest_block(absent)

        timely = _facts(
            {
                "wages": WAGES,
                "benefits": {"td_weeks": 0, "pd_advances": 0, "late_payments": 0},
                "penalties": {},
            }
        )
        assert timely.penalties is not None
        assert timely.penalties.assessments == ()
        published = money_manifest_block(timely)
        assert published["penalties"]["assessmentCount"] == 0
        assert published["penalties"]["assessments"] == []
        assert published["penalties"]["totalIncrease"] == "0.00"

    def test_a_never_paid_period_is_not_assessed_as_a_delay(self) -> None:
        never_paid = money_module.TdPeriod(
            start=date(2021, 6, 17),
            end=date(2021, 7, 14),
            weeks=Decimal("4"),
            weekly_rate=Decimal("100.00"),
            amount=Decimal("400.00"),
            date_due=date(2021, 7, 28),
            date_paid=None,
            days_late=0,
        )
        benefits = money_module.BenefitLedger(td_periods=(never_paid,))
        seed = parse_case_seed(
            _seed_body({"wages": WAGES, "penalties": {}}, case_id="never-paid-penalty")
        )

        onset = date(2021, 6, 14)
        ledger = money_module._derive_penalties(seed, benefits, onset, onset)

        assert ledger.schedule[0].unpaid is True
        assert ledger.schedule[0].date_paid is None
        assert ledger.schedule[0].days_late == 0
        assert ledger.assessments == ()

    def test_the_manifest_validator_recomputes_every_penalty_aggregate(self) -> None:
        from wc_caseload_engine.manifests import _validate_money

        facts = self._penalised()
        documents = _docs(
            MONEY_WAGE_SUBTYPE,
            MONEY_TD_SUBTYPE,
            settlement=money_manifest_block(facts).get("settlement"),
        )
        clean = {"money": money_manifest_block(facts)}
        assert not _validate_money(clean, documents, "penalty-case")

        probes = (
            ("assessmentCount", lambda p: p.__setitem__("assessmentCount", 99)),
            (
                "amount",
                lambda p: p["assessments"][0].__setitem__("amount", "0.01"),
            ),
            ("totalIncrease", lambda p: p.__setitem__("totalIncrease", "0.01")),
            ("principalAssessed", lambda p: p.__setitem__("principalAssessed", "0.01")),
            (
                "daysLate",
                lambda p: p["assessments"][0].__setitem__("daysLate", 1),
            ),
        )
        for field, alter in probes:
            block = {"money": money_manifest_block(facts)}
            alter(block["money"]["penalties"])
            if field == "amount":
                block["money"]["penalties"]["totalIncrease"] = dollars(
                    sum(
                        Decimal(item["amount"])
                        for item in block["money"]["penalties"]["assessments"]
                    )
                )
            problems = _validate_money(block, documents, "penalty-case")
            assert any(field in problem for problem in problems), (field, problems)

        null_due = {"money": money_manifest_block(facts)}
        null_due["money"]["penalties"]["assessments"][0]["statutoryDueDate"] = None
        problems = _validate_money(null_due, documents, "penalty-case")
        assert any("statutoryDueDate" in problem and "null" in problem for problem in problems)

        missing_schedule_entry = {"money": money_manifest_block(facts)}
        missing_schedule_entry["money"]["penalties"]["schedule"].pop()
        problems = _validate_money(missing_schedule_entry, documents, "penalty-case")
        assert any("schedule holds" in problem for problem in problems)

        unpaid_assessment = {"money": money_manifest_block(facts)}
        unpaid_assessment["money"]["penalties"]["schedule"][0]["unpaid"] = True
        unpaid_assessment["money"]["penalties"]["unpaidCount"] = 1
        problems = _validate_money(unpaid_assessment, documents, "penalty-case")
        assert any("unpaid" in problem and "remove assessments" in problem for problem in problems)

        discretionary_assessment = {"money": money_manifest_block(facts)}
        discretionary_assessment["money"]["penalties"]["schedule"][0]["rule"] = (
            "discretionary_advance"
        )
        problems = _validate_money(discretionary_assessment, documents, "penalty-case")
        assert any(
            "discretionary_advance" in problem and "remove assessments" in problem
            for problem in problems
        )

        no_surface = _validate_money(
            clean, _docs(MONEY_WAGE_SUBTYPE, carriers=False), "penalty-case"
        )
        assert any("0 benefit-payment documents" in problem for problem in no_surface)

        missing_flag = {"money": money_manifest_block(facts)}
        del missing_flag["money"]["penalties"]["counselConfirmed"]
        problems = _validate_money(missing_flag, documents, "penalty-case")
        assert any("penalties.counselConfirmed" in problem for problem in problems)

        missing_deadline_flag = {"money": money_manifest_block(facts)}
        del missing_deadline_flag["money"]["penalties"]["deadlineConfirmed"]
        problems = _validate_money(missing_deadline_flag, documents, "penalty-case")
        assert any("penalties.deadlineConfirmed" in problem for problem in problems)


class TestTheSettlementObject:
    """Approval and funding are two events, and the interval between them."""

    def test_a_settled_case_gets_a_settlement_and_an_unsettled_one_does_not(self) -> None:
        settled = _facts({"wages": WAGES})
        assert settled.settlement is not None
        assert settled.settlement.kind == "c_and_r"

        pending = _facts(
            {"wages": WAGES},
            lifecycle={"target_stage": "medical_legal", "eval_type": "qme"},
        )
        assert pending.settlement is None

    def test_stipulations_are_a_settlement_too(self) -> None:
        facts = _facts(
            {"wages": WAGES},
            lifecycle={
                "target_stage": "resolved",
                "eval_type": "qme",
                "resolution": {"type": "stipulations"},
            },
        )
        assert facts.settlement.kind == "stipulations"

    def test_a_trial_award_is_an_ending_but_not_a_settlement(self) -> None:
        """The anti-draw the ``kind`` enum exists for.

        ``findings_award`` and ``take_nothing`` both end a case; neither is
        approved and funded, so neither may carry an approval date.
        """
        for resolution in ("findings_award", "take_nothing"):
            facts = _facts(
                {"wages": WAGES},
                lifecycle={
                    "target_stage": "resolved",
                    "eval_type": "qme",
                    "resolution": {"type": resolution},
                },
            )
            assert facts.settlement is None

    def test_approval_and_funding_are_separate_and_the_lag_is_the_knob(self) -> None:
        for days in (0, 30, 180):
            facts = _facts({"wages": WAGES, "settlement": {"funding_days": days}})
            settlement = facts.settlement
            assert settlement.approval_date is not None
            assert settlement.funding_date is not None
            assert settlement.funding_lag_days == days
            assert (
                settlement.funding_date - settlement.approval_date
            ).days == days

    def test_an_exact_funding_date_overrides_the_interval(self) -> None:
        import datetime as dt

        facts = _facts(
            {
                "wages": WAGES,
                "settlement": {
                    "approval_date": "2025-01-06",
                    "funding_date": "2025-03-04",
                },
            }
        )
        assert facts.settlement.funding_date == dt.date(2025, 3, 4)
        assert facts.settlement.approval_date == dt.date(2025, 1, 6)

    def test_a_funding_date_without_an_approval_date_is_refused(self) -> None:
        """The pair is the fact. One half of it can only be measured against a guess.

        A lone ``funding_date`` used to be measured against an approval date
        derived from the timeline, which the seed cannot see — so a 2025 funding
        date under a 2021 derived approval loaded cleanly and published a
        negative funding lag. ``validate --out`` caught it, one whole generation
        downstream of the seed that caused it.
        """
        with pytest.raises(SeedValidationError) as caught:
            _facts({"wages": WAGES, "settlement": {"funding_date": "2025-03-04"}})
        assert "approval_date" in str(caught.value)

    def test_a_settlement_gross_with_cents_is_refused(self) -> None:
        """The release prints whole dollars, so the ledger may not hold cents.

        The substrate draws its gross with ``random.randint`` and derives the
        fee, costs, set-aside and net from it; the interception can only hand it
        an integer. A ledger holding ``88000.99`` therefore labelled a document
        reading ``$88,000`` — measured, off by 99 cents, which in an
        arithmetic check is simply a wrong label.
        """
        with pytest.raises(SeedValidationError) as caught:
            _facts({"wages": WAGES, "settlement": {"gross_amount": 88000.99}})
        assert "whole" in str(caught.value)

        whole = _facts({"wages": WAGES, "settlement": {"gross_amount": 88000}})
        assert whole.settlement.gross_amount == money(88000)

    def test_a_derived_gross_is_whole_dollars_too(self) -> None:
        """Not only the stated one — the derived gross reaches the same release."""
        for rng_seed in range(4242, 4262):
            facts = _facts({"wages": WAGES}, rng_seed=rng_seed)
            gross = facts.settlement.gross_amount
            assert gross == int(gross), f"{gross} carries cents the release cannot print"

    def test_diligence_drives_the_funding_lag_when_unstated(self) -> None:
        attentive = _facts({"wages": WAGES}, "attentive").settlement
        negligent = _facts({"wages": WAGES}, "negligent").settlement
        assert negligent.funding_lag_days > attentive.funding_lag_days

    def test_a_stated_gross_is_used_verbatim(self) -> None:
        facts = _facts({"wages": WAGES, "settlement": {"gross_amount": 87500.0}})
        assert facts.settlement.gross_amount == money(87500.0)


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    """Same seed, same version, same money — under any ambient state."""

    def test_double_derivation_is_identical(self) -> None:
        scenario = {
            "wages": dict(WAGES, pattern="irregular"),
            "benefits": {"td_weeks": 24, "td_gap_days": 45},
            "settlement": {"funding_days": 21},
        }
        assert _facts(scenario).model_dump() == _facts(scenario).model_dump()

    def test_the_ambient_decimal_context_cannot_change_the_answer(self) -> None:
        """The leak this module was written to be immune to.

        :mod:`decimal`'s context is thread-local mutable state and this package
        is a library, so any caller can change it. Reproduced red at ``prec=6``
        before the fix — every quantize raised ``InvalidOperation`` — and pinned
        since.
        """
        scenario = {"wages": dict(WAGES, pattern="irregular"), "benefits": {"td_weeks": 24}}
        original = decimal.getcontext().prec
        try:
            answers = []
            for prec in (28, 6, 9, 40):
                decimal.getcontext().prec = prec
                facts = _facts(scenario)
                answers.append((facts.model_dump(), money_manifest_block(facts)))
        finally:
            decimal.getcontext().prec = original
        assert all(answer == answers[0] for answer in answers)

    def test_the_public_currency_helper_is_pinned_on_its_own(self) -> None:
        """``money()`` is exported, so it must not rely on a caller's context.

        Found by mutation testing, and worth recording why. The whole-derivation
        probe above stayed **green** when ``money()``'s own pin was removed —
        ``derive_money_facts`` wraps its body, so the inner calls were covered
        by the outer context and the mutant was invisible. A guard that cannot
        see a defect in the code it names is not guarding it.

        ``money`` and ``money_manifest_block`` are both public. A caller that
        reaches for either from inside a ``localcontext`` — a report writer, a
        downstream eval harness — gets the same answer or the pin is not real.
        """
        facts = _facts({"wages": WAGES, "benefits": {"td_weeks": 12}})
        original = decimal.getcontext().prec
        try:
            baseline = (money(1234.567), money_manifest_block(facts))
            # ``prec=2`` is in the sweep because ``Decimal.normalize`` — which
            # the manifest block uses to print week counts — renders 52 as
            # ``5.2E+1`` under a short context. Mutation testing found that:
            # a sweep starting at 5 left the manifest block's own pin
            # unguarded.
            for prec in (2, 3, 5, 6, 9, 50):
                decimal.getcontext().prec = prec
                assert (money(1234.567), money_manifest_block(facts)) == baseline
        finally:
            decimal.getcontext().prec = original

    def test_every_exported_callable_is_pinned_on_its_own(self) -> None:
        """The systematic version. ``__all__`` is the surface, so ``__all__`` is the sweep.

        The two probes above name the functions somebody thought to name, and
        that is exactly how two live defects survived a seventeen-mutant
        campaign: ``compute_aww`` and ``select_method`` are exported, unwrapped,
        and were only ever reached through ``derive_money_facts``, whose pin
        covered them from the outside. Measured before the fix — ``compute_aww``
        raised ``InvalidOperation`` at ``prec`` 2 through 5 and moved a published
        ``gross_considered`` from ``58732.37`` to ``58732.30`` at 6.

        Enumerating the export list rather than a hand-written tuple is the
        point: a new public function is covered the day it is exported, not the
        day somebody remembers to add it here.
        """
        seed = parse_case_seed(
            _seed_body({"wages": dict(WAGES, pattern="irregular", base_weekly_wage=1500.0)})
        )
        wages = seed.scenario.wages
        timeline = build_timeline(seed)
        facts = derive_money_facts(seed, timeline, "ordinary")
        periods = facts.wages.periods
        basis = facts.wages.rate.basis
        doi = seed.injury.date_of_injury

        def inside_exact() -> Decimal:
            with exact():
                return Decimal(1) / Decimal(3)

        calls = {
            "money": lambda: money(1234.567),
            "dollars": lambda: dollars(Decimal("1234.567")),
            "exact": inside_exact,
            "rate_basis_for": lambda: rate_basis_for(doi),
            "penalty_basis_for": lambda: penalty_basis_for(doi),
            "statutory_deadline_basis_for": lambda: statutory_deadline_basis_for(doi),
            "select_method": lambda: select_method(wages, periods),
            "compute_aww": lambda: compute_aww(wages, periods),
            "compute_comp_rate": lambda: compute_comp_rate(money(1234.56), basis),
            "derive_money_facts": lambda: derive_money_facts(seed, timeline, "ordinary"),
            "money_manifest_block": lambda: money_manifest_block(facts),
            "analyzer_money_manifest_block": lambda: analyzer_money_manifest_block(facts),
        }
        exported = {
            name
            for name in money_module.__all__
            if callable(getattr(money_module, name)) and not isinstance(
                getattr(money_module, name), type
            )
        }
        assert exported == set(calls), (
            "money.__all__ exports a callable this sweep does not exercise: "
            f"{sorted(exported ^ set(calls))}. Add it — an exported function whose "
            "answer depends on the caller's decimal context is a determinism leak "
            "that no in-process double run can see."
        )

        original = decimal.getcontext().prec
        try:
            decimal.getcontext().prec = 28
            baseline = {name: repr(call()) for name, call in calls.items()}
            for prec in (2, 3, 4, 5, 6, 7, 8, 9, 50):
                decimal.getcontext().prec = prec
                for name, call in calls.items():
                    try:
                        answer = repr(call())
                    except decimal.DecimalException as exc:
                        # An unpinned callable does not merely answer
                        # differently at a short context — it cannot answer at
                        # all. Letting that exception escape makes the MUTATION
                        # prove an error; catching it and failing here makes the
                        # GUARD prove the defect. The mutation gate scores only
                        # a call-phase assertion as evidence (ASSERTION_TYPES =
                        # AssertionError | Failed), so m1-1 previously scored
                        # ERROR-InvalidOperation — a shipped fix with no
                        # standing proof — rather than RED.
                        pytest.fail(
                            f"{name}() raised {type(exc).__name__} at "
                            f"prec={prec} — its arithmetic is running under the "
                            "caller's context, not the module's; restore the "
                            "module's own pin around it"
                        )
                    assert answer == baseline[name], (
                        f"{name}() answers differently at prec={prec} — its arithmetic "
                        "is running under the caller's context, not the module's"
                    )
        finally:
            decimal.getcontext().prec = original

    def test_the_selected_method_survives_a_hostile_context(self) -> None:
        """The label, specifically — a rounded week total picks a different method.

        ``select_method`` compares a ``Decimal`` week total against
        :data:`SHORT_HISTORY_WEEKS`. Unpinned, a short ambient context rounds
        the sum, and a history sitting near the threshold is labelled by the
        caller's precision rather than by its own earnings. That is not a
        rounding difference; the method is the eval label, so it is a wrong
        label.
        The history is chosen, not arbitrary. Twenty-three eight-day periods
        total **26.2867** weeks — just above the twenty-six-week threshold, so
        the honest label is ``actual_weekly_earnings``. Accumulated under a short
        context the same sum reads 24, which is below it, and the label becomes
        ``short_history_projection``: a file whose employment was long enough,
        labelled as one that was not. A history comfortably clear of the
        threshold cannot show this, which is why the first version of this probe
        left the mutant alive.
        """
        from datetime import date as _date

        doi = _date(2021, 6, 14)
        span = 8
        count = 23
        first = doi - timedelta(days=span * count)
        earnings = [
            {
                "period_start": (first + timedelta(days=span * i)).isoformat(),
                "period_end": (first + timedelta(days=span * i + span - 1)).isoformat(),
                "gross": 2000.0,
            }
            for i in range(count)
        ]
        seed = parse_case_seed(_seed_body({"wages": {"earnings": earnings}}))
        wages = seed.scenario.wages
        periods = derive_money_facts(seed, build_timeline(seed), "ordinary").wages.periods

        exact_weeks = sum((p.weeks for p in periods), Decimal("0"))
        assert exact_weeks > SHORT_HISTORY_WEEKS, (
            f"the probe history must sit just *above* the threshold; it totals "
            f"{exact_weeks}"
        )

        original = decimal.getcontext().prec
        try:
            decimal.getcontext().prec = 28
            expected = select_method(wages, periods)
            assert expected[0] == "actual_weekly_earnings"
            for prec in (2, 3, 4, 5, 6, 7):
                decimal.getcontext().prec = prec
                assert select_method(wages, periods) == expected, (
                    f"at prec={prec} the label moved to "
                    f"{select_method(wages, periods)[0]!r} — the eval label decided by "
                    "the caller's precision rather than by the earnings"
                )
        finally:
            decimal.getcontext().prec = original

    def test_money_draws_never_touch_a_stream_another_fact_reads(self) -> None:
        """Varying a money knob moves no clinical fact.

        The ``money:`` namespace exists for this. Borrowing a ``facts:`` salt
        would make a wage knob silently rewrite a diagnostic report, which is
        the class of coupling this engine has already paid for twice.
        """
        seed_a = parse_case_seed(_seed_body({"wages": WAGES}))
        seed_b = parse_case_seed(
            _seed_body({"wages": dict(WAGES, base_weekly_wage=3300.0, pattern="irregular")})
        )
        facts_a = derive_case_facts(seed_a, build_timeline(seed_a))
        facts_b = derive_case_facts(seed_b, build_timeline(seed_b))
        assert facts_a.model_dump() == facts_b.model_dump()


# ---------------------------------------------------------------------------
# Planning and controls
# ---------------------------------------------------------------------------


class TestThePlan:
    """Money documents are a floor, and the controls still bind."""

    def test_a_money_bearing_case_holds_a_wage_statement(self) -> None:
        plan = build_case_plan(parse_case_seed(_seed_body({"wages": WAGES})))
        assert MONEY_WAGE_SUBTYPE in {document.subtype for document in plan.documents}

    def test_no_payment_record_predates_the_payments_it_prints(self) -> None:
        """A carrier's printout cannot report a cheque it has not cut yet.

        The floor decides the date these documents need; the first cut then
        threw that decision away whenever the lifecycle walk had already
        proposed the subtype, and the walk dates from the stage rather than
        from the ledger. Measured across this sweep before the fix: **106 of
        132** planned temporary-disability records were dated before the last
        payment printed on them, one of them by 123 days.

        Swept across stages and thirty seeds because a single draw of a
        date chain proves nothing about the chain — the same discipline the
        date-spine rules demand of every new path.
        """
        scenario = {
            "wages": WAGES,
            "benefits": {"td_weeks": 520, "late_payments": 3, "max_days_late": 60},
        }
        checked = 0
        for stage in ("active_treatment", "pre_trial", "resolved"):
            lifecycle: dict[str, Any] = {"target_stage": stage, "eval_type": "qme"}
            if stage == "resolved":
                lifecycle["resolution"] = {"type": "c_and_r"}
            for rng_seed in range(4242, 4272):
                plan = build_case_plan(
                    parse_case_seed(
                        _seed_body(scenario, rng_seed=rng_seed, lifecycle=lifecycle)
                    )
                )
                facts = plan.money_facts
                assert facts is not None
                if not facts.benefits.td_periods:
                    continue
                last = max(
                    (p.date_paid or p.end) for p in facts.benefits.td_periods
                )
                for document in plan.documents:
                    if document.subtype == MONEY_TD_SUBTYPE:
                        checked += 1
                        assert document.doc_date >= last, (
                            f"{MONEY_TD_SUBTYPE} dated {document.doc_date} prints a "
                            f"payment made {last} ({(last - document.doc_date).days} "
                            f"days later) — stage={stage} rng_seed={rng_seed}"
                        )
                if facts.benefits.pd_advances:
                    last_pd = max(a.date_paid for a in facts.benefits.pd_advances)
                    for document in plan.documents:
                        if document.subtype == MONEY_PD_SUBTYPE:
                            assert document.doc_date >= last_pd
        assert checked > 50, f"the sweep only reached {checked} payment records"

    def test_re_dating_never_moves_a_document_earlier(self) -> None:
        """Forward only. These documents report events; they may lag, never lead.

        The control on the fix above, and asserted on the rule itself rather
        than by comparing two plans — a wage-free plan and a money-bearing one
        allocate different document counts, so a date that differs between them
        says nothing about the direction of a move.

        A candidate the walk placed *after* the ledger is left exactly where it
        was. Moving it back would be the money floor overruling the lifecycle
        walk rather than correcting it.
        """
        from wc_caseload_engine.lifecycle_bridge import DatedCandidate
        from wc_caseload_engine.planner import _money_candidates

        seed = parse_case_seed(_seed_body({"wages": WAGES, "benefits": {"td_weeks": 8}}))
        timeline = build_timeline(seed)
        facts = derive_money_facts(seed, timeline, "ordinary")
        assert facts is not None

        far = timeline.clamp(
            max((p.date_paid or p.end) for p in facts.benefits.td_periods)
            + timedelta(days=400)
        )
        existing = [DatedCandidate(subtype=MONEY_TD_SUBTYPE, doc_date=far)]
        added = _money_candidates(seed, facts, timeline, existing)

        assert existing[0].doc_date == far, "a later candidate was dragged backwards"
        assert MONEY_TD_SUBTYPE not in {c.subtype for c in added}, (
            "the floor doubled a document the walk already proposed"
        )

        # And the opposite draw on the same call: a candidate the walk placed
        # too early *is* moved, so the branch above is a rule rather than an
        # inert early return.
        early = [DatedCandidate(subtype=MONEY_TD_SUBTYPE, doc_date=timeline.injury_date)]
        _money_candidates(seed, facts, timeline, early)
        assert early[0].doc_date > timeline.injury_date

    def test_the_floor_fires_where_the_walk_proposes_nothing(self) -> None:
        """A floor that never fires is dead code claiming to be a guarantee.

        ``intake`` is the stage measured to propose no payment record, so it is
        the stage that proves the floor is live.
        """
        lifecycle = {"target_stage": "intake", "eval_type": "none"}
        dry = build_case_plan(parse_case_seed(_seed_body(None, lifecycle=lifecycle)))
        wet = build_case_plan(
            parse_case_seed(_seed_body({"wages": WAGES}, lifecycle=lifecycle))
        )
        added = {d.subtype for d in wet.documents} - {d.subtype for d in dry.documents}
        assert added & set(MONEY_FLOOR_SUBTYPES), added

    def test_an_explicit_exclude_still_suppresses_a_floored_document(self) -> None:
        """Control wins, loudly — the ISC-29 rule, applied to the money floor.

        Emitting the floor after ``resolve_document_controls`` would have made
        it invisible to the controls, which is a defect this package has shipped
        once already (PR #25, M1).
        """
        plan = build_case_plan(
            parse_case_seed(
                _seed_body(
                    {"wages": WAGES},
                    documents={
                        "exclude": [MONEY_WAGE_SUBTYPE],
                        "format_mix": {"pdf": 1.0},
                    },
                )
            )
        )
        assert MONEY_WAGE_SUBTYPE not in {d.subtype for d in plan.documents}

    def test_include_only_reaches_a_floored_document(self) -> None:
        plan = build_case_plan(
            parse_case_seed(
                _seed_body(
                    {"wages": WAGES},
                    documents={
                        "include_only": [MONEY_WAGE_SUBTYPE],
                        "format_mix": {"pdf": 1.0},
                    },
                )
            )
        )
        assert {d.subtype for d in plan.documents} == {MONEY_WAGE_SUBTYPE}

    def test_the_floor_never_doubles_a_document_the_walk_already_proposed(self) -> None:
        plan = build_case_plan(parse_case_seed(_seed_body({"wages": WAGES})))
        subtypes = [d.subtype for d in plan.documents]
        for subtype in MONEY_FLOOR_SUBTYPES:
            assert subtypes.count(subtype) <= 1, subtype


# ---------------------------------------------------------------------------
# Publication
# ---------------------------------------------------------------------------


@requires_substrate
class TestTheFloorGuaranteesTheSettlementCarriers:
    """A published date needs a document dated on or after the event it reports.

    The ISC-92.1 pattern — a stated scenario fact guarantees the document that
    carries it — reaches the settlement. Neither carrier could be the release:
    the parties sign before the Board approves, and the Board approves before
    the draft clears.
    """

    def test_a_settled_case_gets_carriers_that_could_know_its_dates(self) -> None:
        from wc_caseload_engine.planner import (
            MONEY_APPROVAL_SUBTYPE,
            MONEY_FUNDING_SUBTYPE,
        )

        # Derived dates *and* authored ones. Mutation testing found this sweep
        # blind on its first pass: for a derived settlement the walk happens to
        # date its own order on the approval day, so the floor looked redundant.
        # An authored approval is where they diverge — the walk dated one order
        # 2021-10-09 against an authored approval of 2024-06-03, nearly three
        # years early, on 80 seeds. The floor's forward re-dating is what closes
        # that, and nothing was exercising it.
        settlements: list[dict[str, Any] | None] = [
            None,
            {"gross_amount": 88000, "approval_date": "2024-06-03"},
            {
                "gross_amount": 88000,
                "approval_date": "2025-01-06",
                "funding_date": "2025-02-05",
            },
        ]
        seen = {"approval": 0, "funding": 0}
        for offset in range(5):
            for resolution in ("c_and_r", "stipulations"):
                for settlement_scenario in settlements:
                    scenario: dict[str, Any] = {
                        "wages": WAGES,
                        "benefits": {"td_weeks": 10},
                    }
                    if settlement_scenario is not None:
                        scenario["settlement"] = settlement_scenario
                    plan = build_case_plan(
                        parse_case_seed(
                            _seed_body(
                                scenario,
                                rng_seed=1000 + offset,
                                lifecycle={
                                    "target_stage": "resolved",
                                    "eval_type": "qme",
                                    "resolution": {"type": resolution},
                                },
                            )
                        )
                    )
                    settlement = plan.money_facts.settlement
                    assert settlement is not None
                    dated: dict[str, list[date]] = {}
                    for candidate in plan.documents:
                        dated.setdefault(candidate.subtype, []).append(
                            candidate.doc_date
                        )

                    where = f"seed {1000 + offset}/{resolution}/{settlement_scenario}"
                    if settlement.approval_date is not None:
                        assert any(
                            when >= settlement.approval_date
                            for when in dated.get(MONEY_APPROVAL_SUBTYPE, [])
                        ), (
                            f"{where}: approval {settlement.approval_date} has no "
                            f"order dated on or after it — "
                            f"{dated.get(MONEY_APPROVAL_SUBTYPE, [])}"
                        )
                        seen["approval"] += 1
                    if settlement.funding_date is not None:
                        assert any(
                            when >= settlement.funding_date
                            for when in dated.get(MONEY_FUNDING_SUBTYPE, [])
                        ), (
                            f"{where}: funding {settlement.funding_date} has no "
                            f"ledger dated on or after it — "
                            f"{dated.get(MONEY_FUNDING_SUBTYPE, [])}"
                        )
                        seen["funding"] += 1
        # A sweep that reached neither branch would pass vacuously.
        assert seen["approval"] >= 30 and seen["funding"] >= 20, seen

    def test_a_case_that_never_settled_gets_neither(self) -> None:
        """The opposite draw: the floor adds carriers for a fact, not by habit."""
        from wc_caseload_engine.planner import (
            MONEY_APPROVAL_SUBTYPE,
            MONEY_FUNDING_SUBTYPE,
        )

        plan = build_case_plan(
            parse_case_seed(
                _seed_body(
                    {"wages": WAGES},
                    lifecycle={"target_stage": "discovery", "eval_type": "qme"},
                )
            )
        )
        assert plan.money_facts.settlement is None
        subtypes = {candidate.subtype for candidate in plan.documents}
        assert MONEY_FUNDING_SUBTYPE not in subtypes
        assert MONEY_APPROVAL_SUBTYPE not in subtypes


class TestPublication:
    """A published fact is a promise the documents keep."""

    def test_a_listed_history_admits_no_shape_knob(self) -> None:
        """Listed or described, never both — for **all six** knobs, not the two nullable ones.

        The first cut checked the two knobs whose default is ``None``, because
        "is it None" is the obvious test. The other four carry real defaults, so
        an author's ``pattern: irregular`` was indistinguishable from Pydantic's
        ``pattern: regular`` and passed. ``pattern`` is the sharp one: it is a
        **published ground-truth label**, so a seed listing a steady history
        under ``pattern: irregular`` shipped a wrong label to the analyzer
        without a word. ``model_fields_set`` is the only thing that can see it.
        """
        listed = [
            {"period_start": "2021-01-04", "period_end": "2021-01-17", "gross": 2000.0},
            {"period_start": "2021-01-18", "period_end": "2021-01-31", "gross": 2000.0},
        ]
        knobs: dict[str, Any] = {
            "pattern": "irregular",
            "base_weekly_wage": 1500.0,
            "lookback_weeks": 26,
            "pay_frequency": "weekly",
            "overtime_share": 0.2,
            "concurrent_weekly_wage": 400.0,
        }
        assert set(knobs) == WageScenario.SHAPE_KNOBS, (
            "the knob set moved; this probe and the class docstring must move with it"
        )
        for knob, value in knobs.items():
            with pytest.raises(SeedValidationError) as caught:
                _facts({"wages": {"earnings": listed, knob: value}})
            assert knob in str(caught.value)

        # The control: the listed history alone loads, so the refusals above are
        # about the pairing rather than about the earnings.
        assert _facts({"wages": {"earnings": listed}}) is not None

        # And a knob restated at its own default is still a stated knob.
        with pytest.raises(SeedValidationError):
            _facts({"wages": {"earnings": listed, "pattern": "regular"}})

    def test_an_unequal_concurrent_history_is_refused_rather_than_averaged(self) -> None:
        """One gross over one denominator cannot express two employments of different lengths.

        A two-week primary period paying $2,000 beside a fifty-two-week
        concurrent history paying $52,000 aggregated to $54,000 — and *every*
        single denominator is wrong for it. Two weeks says $27,000 (capped to
        the statutory maximum, recorded as `tdBound: max`). Fifty-two weeks says
        $1,038.46, diluting the primary job across fifty weeks it did not exist.
        The answer a reader would defend is $2,000 — the sum of the two weekly
        rates while both were running — and reaching it needs per-employment
        operands, which needs employer identity. A boolean cannot say *which*
        employer a period belongs to, so it cannot group them.

        Refused, therefore, rather than approximated. An additive Wave-2 field
        opens the shape properly; publishing a number here that no arithmetic on
        the page reproduces would put the asserted figure this layer exists to
        remove into the one method whose whole point is combining employments.
        """
        primary = [
            {"period_start": "2021-05-31", "period_end": "2021-06-13", "gross": 2000.0}
        ]
        start = date(2020, 6, 15)
        concurrent = [
            {
                "period_start": (start + timedelta(days=14 * i)).isoformat(),
                "period_end": (start + timedelta(days=14 * i + 13)).isoformat(),
                "gross": 2000.0,
                "concurrent": True,
            }
            for i in range(26)
        ]
        with pytest.raises(SeedValidationError) as caught:
            _facts({"wages": {"earnings": primary + concurrent}})
        assert "different dates" in str(caught.value)

        # The control: matched coverage is accepted, and the aggregate is then a
        # sum over one span that a reader can reproduce from the printed table.
        matched = [
            {"period_start": e["period_start"], "period_end": e["period_end"], "gross": 2000.0}
            for e in concurrent
        ] + concurrent
        facts = _facts({"wages": {"earnings": matched}})
        computation = facts.wages.computation
        assert computation.method == "concurrent_aggregate"
        assert computation.gross_considered == money(104000)
        assert computation.aww == money(
            (computation.gross_considered / computation.weeks_considered).quantize(
                Decimal("0.01")
            )
        )

        # And a derived concurrent history — where the engine builds both sides
        # over the same windows — is unaffected, which is what keeps every
        # money-showcase figure where it was.
        aligned = _facts({"wages": dict(WAGES, concurrent_employment=True)})
        primary_weeks = sum(
            (p.weeks for p in aligned.wages.primary_periods), Decimal("0")
        )
        assert aligned.wages.computation.weeks_considered == primary_weeks

    def test_a_history_with_no_primary_period_is_refused(self) -> None:
        """Every period concurrent divides a real gross by zero primary weeks.

        Measured before the fix: two concurrent periods totalling $4,000 loaded
        cleanly and published ``averageWeeklyWage: 0.00`` — an asserted zero,
        which is the same defect as an asserted average wearing the opposite
        sign.
        """
        concurrent = [
            {
                "period_start": "2021-01-04",
                "period_end": "2021-01-17",
                "gross": 2000.0,
                "concurrent": True,
            },
            {
                "period_start": "2021-01-18",
                "period_end": "2021-01-31",
                "gross": 2000.0,
                "concurrent": True,
            },
        ]
        with pytest.raises(SeedValidationError) as caught:
            _facts({"wages": {"earnings": concurrent}})
        # Name *this* refusal, not any refusal. With no primary periods the
        # matched-dates check one clause below also fires — its message says
        # "different dates from the primary ones" — so asserting on the bare
        # word "primary" passed with this guard removed entirely. The seed
        # author needs to be told which of the two shapes they wrote.
        assert "marks every period" in str(caught.value)

        # The control: matched primary periods make the aggregate real money.
        mixed = [
            {"period_start": e["period_start"], "period_end": e["period_end"], "gross": 1800.0}
            for e in concurrent
        ] + concurrent
        facts = _facts({"wages": {"earnings": mixed}})
        assert facts.aww > money(0)
        assert facts.method == "concurrent_aggregate"

    def test_the_block_publishes_only_governed_fields(self) -> None:
        from wc_caseload_engine.money import GOVERNED_MONEY_FIELDS

        block = money_manifest_block(_facts({"wages": WAGES}))
        assert set(block) <= set(GOVERNED_MONEY_FIELDS)
        for group, fields in block.items():
            assert set(fields) <= set(GOVERNED_MONEY_FIELDS[group]), group

    def test_the_ledger_publishes_events_not_only_counts(self) -> None:
        """``tdPeriods`` holds periods. It held a number.

        An extraction label is expensive to move — the analyzer is scored on
        these names — so a key named for a collection had to become the
        collection now or never. Wave 3 computes a penalty per late payment;
        given ``latePayments: 2`` and nothing else it cannot say *which* two,
        and given only a total it cannot recompute an exposure at all.
        """
        block = money_manifest_block(
            _facts(
                {
                    "wages": WAGES,
                    "benefits": {"td_weeks": 20, "late_payments": 2, "max_days_late": 30},
                }
            )
        )
        benefits = block["benefits"]
        assert isinstance(benefits["tdPeriods"], list)
        assert isinstance(benefits["pdAdvances"], list)
        assert isinstance(benefits["gaps"], list)
        assert benefits["tdPeriodCount"] == len(benefits["tdPeriods"])
        assert benefits["pdAdvanceCount"] == len(benefits["pdAdvances"])
        assert benefits["tdPeriods"], "a 20-week TD run published no periods"

        # The count and the array are two publications of one ledger; the
        # totals must follow from the records rather than from a second sum.
        assert Decimal(benefits["tdTotal"]) == sum(
            Decimal(period["amount"]) for period in benefits["tdPeriods"]
        )
        assert benefits["latePaymentCount"] == sum(
            1 for period in benefits["tdPeriods"] if period["daysLate"]
        ) + sum(1 for advance in benefits["pdAdvances"] if advance["daysLate"])

    def test_lateness_is_recomputable_from_the_published_due_date(self) -> None:
        """``daysLate`` without ``dateDue`` is an effect with its cause off the page.

        The due date was computed one line above where it was discarded, and the
        yardstick it came from lived in a module constant nothing published. A
        reader holding the ledger could see that a payment was 30 days late and
        had no way to check it — which is the asserted-not-derived shape this
        whole layer exists to remove, in miniature.
        """
        from datetime import date as _date

        block = money_manifest_block(
            _facts(
                {
                    "wages": WAGES,
                    "benefits": {"td_weeks": 20, "late_payments": 2, "max_days_late": 30},
                }
            )
        )
        benefits = block["benefits"]
        # Presence before value. A missing yardstick is the defect this guard
        # exists for, and subscripting it raises KeyError — which the mutation
        # gate scores as ERROR, not RED, because an error proves a crash and
        # only an assertion proves a defect.
        assert "tdPaymentDueDays" in benefits, (
            "the ledger publishes daysLate but not the yardstick it was measured "
            "against — an effect with its cause off the page"
        )
        assert benefits["tdPaymentDueDays"] == TD_PAYMENT_DUE_DAYS
        late = 0
        for period in benefits["tdPeriods"]:
            due = _date.fromisoformat(period["dateDue"])
            end = _date.fromisoformat(period["end"])
            # The due date follows from the period's own end and the published
            # yardstick — no third number, and nothing to take on trust.
            assert (due - end).days == benefits["tdPaymentDueDays"]
            paid = _date.fromisoformat(period["datePaid"])
            assert (paid - due).days == period["daysLate"]
            late += 1 if period["daysLate"] else 0
        assert late == 2, "the opposite draw is the point: exactly the seeded lateness"

        # And with the knob off, every payment recomputes to zero days late.
        timely = money_manifest_block(
            _facts({"wages": WAGES, "benefits": {"td_weeks": 20, "late_payments": 0}})
        )
        assert all(p["daysLate"] == 0 for p in timely["benefits"]["tdPeriods"])

    def test_currency_is_published_as_exact_decimal_strings(self) -> None:
        """Never a float. A label rounded through binary can disagree by a cent.

        The key walk is over *values*, not a spot check, so a new currency field
        added as a float fails here rather than in an eval six months later.
        """
        block = money_manifest_block(_facts({"wages": WAGES, "benefits": {"td_weeks": 20}}))
        for group in ("wage", "rate", "benefits", "settlement"):
            for key, value in block[group].items():
                if any(token in key for token in ("Wage", "Rate", "Total", "Amount", "Gross")):
                    assert isinstance(value, str), f"{group}.{key} is {type(value).__name__}"
                    Decimal(value)  # parses exactly, or this raises

    def test_the_method_on_the_page_is_the_method_in_the_manifest(self) -> None:
        facts = _facts({"wages": dict(WAGES, pattern="irregular")})
        block = money_manifest_block(facts)
        assert block["wage"]["method"] == facts.method
        assert block["wage"]["method"] in AWW_METHODS


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


@requires_substrate
class TestTheDocumentsCarryTheNumbers:
    """The ledger is only checkable if the paper says the same thing."""

    @staticmethod
    def _generate(tmp_path: Path, scenario: dict[str, Any] | None, **kwargs: Any) -> Any:
        seed = parse_case_seed(_seed_body(scenario, **kwargs))
        generate_case(seed, tmp_path, 1)
        directory = tmp_path / seed.case_id
        manifest = json.loads((directory / MANIFEST_NAME).read_text(encoding="utf-8"))
        texts = {
            document["subtype"]: " ".join(
                extract_text(
                    directory / "documents" / document["filename"], document["format"]
                ).split()
            )
            for document in manifest["documents"]
        }
        return manifest, texts, directory

    def test_the_wage_statement_prints_the_method_the_aww_and_the_rate(
        self, tmp_path: Path
    ) -> None:
        manifest, texts, _ = self._generate(
            tmp_path,
            {"wages": dict(WAGES, pattern="irregular")},
            documents={
                "include_only": [MONEY_WAGE_SUBTYPE],
                "format_mix": {"pdf": 1.0},
            },
        )
        block = manifest["caseFacts"]["money"]
        page = texts[MONEY_WAGE_SUBTYPE].replace(",", "")
        assert METHOD_LABEL.rstrip(":") in texts[MONEY_WAGE_SUBTYPE]
        assert block["wage"]["method"] in page
        assert block["wage"]["averageWeeklyWage"] in page
        assert block["rate"]["tdWeeklyRate"] in page
        assert block["rate"]["pdWeeklyRate"] in page
        assert UNCONFIRMED_NOTICE in texts[MONEY_WAGE_SUBTYPE]

    def test_every_governed_wage_and_rate_field_reaches_the_page(
        self, tmp_path: Path
    ) -> None:
        """The governance rule, checked instead of stated.

        ``GOVERNED_MONEY_FIELDS`` says a published fact is one a document
        renders. Three were not: ``pattern``, ``basisSource`` and
        ``basisAuthority`` were published as ground truth and appeared on no
        page — labels an analyzer would have been scored on recovering from a
        document that did not contain them.

        Driven off the governance table rather than a hand-written list, so a
        field added to the table without a row on the statement fails here on the
        day it is added, not in an eval later.
        """
        from wc_caseload_engine.money import GOVERNED_MONEY_FIELDS

        manifest, texts, _ = self._generate(
            tmp_path,
            {"wages": dict(WAGES, pattern="seasonal")},
            documents={
                "include_only": [MONEY_WAGE_SUBTYPE],
                "format_mix": {"pdf": 1.0},
            },
        )
        block = manifest["caseFacts"]["money"]
        page = texts[MONEY_WAGE_SUBTYPE].replace(",", "")
        normalized = " ".join(page.split())

        # Label *and* value, in that order, not the value anywhere on the page.
        # Found by review: `methodSource` and `patternSource` are both usually
        # "derived", so deleting the pattern-source row left this test green on
        # the method-source row's text. A sweep that a duplicate value can
        # satisfy is not checking the field it names.
        labels = {
            "method": "AWW Method:",
            "methodSource": "Method Source:",
            "methodReason": "Basis of Method:",
            "averageWeeklyWage": "Average Weekly Wage (AWW):",
            "periodsConsidered": "Periods Considered:",
            "weeksConsidered": "Weeks Considered:",
            "grossConsidered": "Earnings Considered:",
            "inKindWeekly": "Non-Cash Wages (weekly):",
            "pattern": "Earnings Pattern:",
            "patternSource": "Earnings Pattern Source:",
            "concurrentEmployment": "Concurrent Employment:",
            "tdWeeklyRate": "Temporary Disability Rate:",
            "tdBound": "TD Rate Bound:",
            "pdWeeklyRate": "Permanent Disability Rate:",
            "pdBound": "PD Rate Bound:",
            "basisLabel": "Rate Basis:",
            "basisAuthority": "Rate Basis Authority:",
            "counselConfirmed": "Rate Basis:",
            "basisSource": "Rate Basis Source:",
        }
        governed = set(GOVERNED_MONEY_FIELDS["wage"]) | set(GOVERNED_MONEY_FIELDS["rate"])
        assert governed <= set(labels), (
            "a governed field has no label in this probe: "
            f"{sorted(governed - set(labels))}. Give it a row on the wage statement and "
            "name the row here — a published fact is one a document renders."
        )
        for group in ("wage", "rate"):
            for field in GOVERNED_MONEY_FIELDS[group]:
                value = block[group][field]
                label = labels[field]
                assert label in normalized, f"the wage statement lost the {label!r} row"
                if isinstance(value, bool):
                    # Rendered as the caveat text a reader of paper sees, beside
                    # the basis label rather than as the word "False".
                    assert UNCONFIRMED_NOTICE in normalized
                    continue
                needle = " ".join(str(value).replace(",", "").split())
                after = normalized.split(label, 1)[1][: len(needle) + 80]
                assert needle in after, (
                    f"caseFacts.money.{group}.{field} publishes {value!r}, which does not "
                    f"appear after its own {label!r} row on the wage statement — a "
                    "published fact is one a document renders, or it is a label with "
                    "nothing behind it"
                )

    def test_each_settlement_date_is_printed_by_a_document_that_could_know_it(
        self, tmp_path: Path
    ) -> None:
        """Every governed settlement field reaches a page, and no page reports its own future.

        Two rules that only mean something together. `approvalDate`,
        `fundingDate` and `fundingLagDays` were published as ground truth and
        appeared on no page: the substrate's release leaves its approval line
        blank and carries no funding date at all.

        The first fix put all three on the release, and review was right to
        refuse it. A compromise and release is signed and filed *before* the
        Board approves it — the planner dates one 44 days ahead of its own
        approval — so a release printing that date asserts an event in its own
        future. An anachronism is worse evidence than a blank line, because it
        reads as evidence. So the release carries what the parties agreed, the
        order carries the approval it effects, and a ledger dated after the
        draft cleared carries the funding and the interval.
        """
        from wc_caseload_engine.money import GOVERNED_MONEY_FIELDS

        manifest, texts, _ = self._generate(
            tmp_path,
            {
                "wages": WAGES,
                "settlement": {
                    "gross_amount": 88000,
                    "approval_date": "2025-01-06",
                    "funding_date": "2025-02-05",
                },
            },
            documents={"format_mix": {"pdf": 1.0}},
        )
        block = manifest["caseFacts"]["money"]["settlement"]
        assert block["fundingLagDays"] == 30

        # Which document is allowed to print which field. The keys cover
        # GOVERNED_MONEY_FIELDS["settlement"] exactly, so a sixth field cannot be
        # added to the group without a decision about who prints it.
        carried = {
            "kind": ("COMPROMISE_AND_RELEASE_STANDARD", "Settlement Type:"),
            "grossAmount": ("COMPROMISE_AND_RELEASE_STANDARD", "Settlement Gross:"),
            "approvalDate": ("ORDER_APPROVING_SETTLEMENT", "Date Approved:"),
            "fundingDate": ("BENEFIT_PAYMENT_LEDGER", "Date Funded:"),
            "fundingLagDays": (
                "BENEFIT_PAYMENT_LEDGER",
                "Days From Approval To Funding:",
            ),
        }
        assert set(GOVERNED_MONEY_FIELDS["settlement"]) == set(carried)

        dates = {
            d["subtype"]: date.fromisoformat(d["documentDate"])
            for d in manifest["documents"]
        }
        for field, (subtype, label) in carried.items():
            assert subtype in texts, f"no {subtype} in the folder to carry {field}"
            page = " ".join(texts[subtype].replace(",", "").split())
            assert label in page, f"{subtype} lost the {label!r} row"
            value = " ".join(str(block[field]).replace(",", "").split())
            after = page.split(label, 1)[1][: len(value) + 60]
            assert value in after, (
                f"caseFacts.money.settlement.{field} publishes {block[field]!r}, which "
                f"does not appear after its own {label!r} row on the {subtype}"
            )
            # The carrier's own date is on or after the event it reports, which
            # is the half of the rule the first fix failed.
            if field.endswith("Date"):
                assert dates[subtype] >= date.fromisoformat(block[field]), (
                    f"{subtype} is dated {dates[subtype]} and prints a {field} of "
                    f"{block[field]} — a document cannot report its own future"
                )

        # And the opposite draw: the release, which is dated before both events,
        # names neither of them.
        release = " ".join(texts["COMPROMISE_AND_RELEASE_STANDARD"].split())
        assert dates["COMPROMISE_AND_RELEASE_STANDARD"] < date.fromisoformat(
            block["approvalDate"]
        )
        assert "Date Approved:" not in release
        assert "Date Funded:" not in release

    def test_the_stipulated_award_states_the_ledgers_money_not_its_own(
        self, tmp_path: Path
    ) -> None:
        """The other resolution type's primary settlement document was inventing money.

        `FactAwareCompromiseAndRelease` had no counterpart for stipulations, so
        every `stipulations` case shipped a `STIPULATIONS_WITH_REQUEST_FOR_AWARD`
        computing an average weekly wage from `hourly_rate * weekly_hours`, a
        temporary-disability run from `random.randint(4, 52)`, a rate from a
        hardcoded 0.67 and an award from `random.randint(5000, 75000)`.
        Measured on the shipped `steady-earner`: caseFacts said 1151.42 / 767.65
        / 26867.75 and the document said 1331.20 / 891.90 / 40135.68 — two money
        ontologies in one case, on the page an analyzer is trained against.
        """
        manifest, texts, _ = self._generate(
            tmp_path,
            {"wages": WAGES, "benefits": {"td_weeks": 12}},
            lifecycle={
                "target_stage": "resolved",
                "eval_type": "qme",
                "resolution": {"type": "stipulations"},
            },
            documents={"format_mix": {"pdf": 1.0}},
        )
        block = manifest["caseFacts"]["money"]
        page = texts["STIPULATIONS_WITH_REQUEST_FOR_AWARD"]

        # Parsed, not substring-matched. The first version of this probe asserted
        # `aww in page` and stayed green while the page read `$1,001.23.20.` —
        # the rewrite had split on the decimal point of the substrate's own
        # figure, and "1001.23" is a substring of "1001.23.20". A probe that
        # cannot tell a number from a prefix of a longer one is not reading the
        # number.
        def amount(pattern: str) -> Decimal:
            found = re.search(pattern, page)
            assert found, f"{pattern!r} not on the stipulated award"
            return Decimal(found.group(1).replace(",", ""))

        assert amount(r"average weekly wage of \$([\d,]+\.\d\d)(?!\d|\.\d)") == Decimal(
            block["wage"]["averageWeeklyWage"]
        )
        assert amount(
            r"at the rate of \$([\d,]+\.\d\d)(?!\d|\.\d) per week"
        ) == Decimal(block["rate"]["tdWeeklyRate"])
        assert amount(r"totaling \$([\d,]+\.\d\d)(?!\d|\.\d)") == Decimal(
            block["benefits"]["tdTotal"]
        )

        # And the gross means one thing. It used to be forced into the
        # substrate's `base_pd_award`, where the page labels it "Permanent
        # Disability (Gross)" and adds a self-procured reimbursement on top — so
        # the same number was the whole settlement in the manifest and one
        # component of the award on the page, and the components summed past the
        # total. The cash components must now add up to it.
        gross = Decimal(block["settlement"]["grossAmount"])
        pd_gross = amount(r"Permanent Disability \(Gross\) \$([\d,]+\.\d\d)")
        self_procured = amount(r"Self-Procured Medical Reimbursement \$([\d,]+\.\d\d)")
        assert pd_gross + self_procured == gross, (
            f"the award's cash components are {pd_gross} + {self_procured} = "
            f"{pd_gross + self_procured}, but the settlement gross is {gross}"
        )
        assert amount(r"Settlement Gross: \$([\d,]+\.\d\d)(?!\d|\.\d)") == gross

    def test_the_award_reconciles_at_every_gross_the_schema_accepts(
        self, tmp_path: Path
    ) -> None:
        """The split held above $5,500 and gave up below it, silently.

        The first version clamped the reimbursement into the substrate's own
        `randint` bounds and abandoned the reconciliation when the award fell
        under 5000 — leaving both draws random. A gross of $5,499 printed
        components totalling $32,696 beside a published $5,499, with no warning
        and a clean `validate --out`. Those bounds select which draw to answer;
        they never constrained the answer.
        """
        for gross in (3, 5499, 11500, 32668, 88000):
            manifest, texts, _ = self._generate(
                tmp_path / f"g{gross}",
                {
                    "wages": WAGES,
                    "benefits": {"td_weeks": 0, "pd_advances": 0},
                    "settlement": {"gross_amount": gross},
                },
                case_id=f"reconcile-{gross}",
                lifecycle={
                    "target_stage": "resolved",
                    "eval_type": "none",
                    "resolution": {"type": "stipulations"},
                },
                documents={"format_mix": {"pdf": 1.0}},
            )
            page = texts["STIPULATIONS_WITH_REQUEST_FOR_AWARD"]
            published = Decimal(
                manifest["caseFacts"]["money"]["settlement"]["grossAmount"]
            )

            def amount(pattern: str, text: str = page, where: int = gross) -> Decimal:
                found = re.search(pattern, text)
                assert found, f"{pattern!r} not on the award for gross {where}"
                return Decimal(found.group(1).replace(",", ""))

            pd_gross = amount(r"Permanent Disability \(Gross\) \$([\d,]+\.\d\d)")
            self_procured = amount(r"Self-Procured Medical Reimbursement \$([\d,]+\.\d\d)")
            assert pd_gross + self_procured == published, (
                f"gross {gross}: the award prints {pd_gross} + {self_procured} = "
                f"{pd_gross + self_procured} against a published {published}"
            )
            assert pd_gross >= 1 and self_procured >= 1

            # …and it is the *nearest* whole-dollar reimbursement to five
            # percent, not merely a valid one. Mutation found this claim
            # unasserted: shifting the choice keeps the sum, so the docstring's
            # "nearest" was describing behaviour nothing checked.
            target = published * Decimal("0.05")
            valid = [Decimal(value) for value in range(1, int(published))]
            assert valid, gross
            best = min(valid, key=lambda value: (abs(value - target), value))
            assert self_procured == best, (
                f"gross {gross}: chose a reimbursement of {self_procured} when "
                f"{best} is nearer five percent ({target})"
            )

            # And the fee the page calls fifteen percent *is* fifteen percent.
            # The substrate truncates `award * 0.15` to an integer, so an award
            # of $5,225 printed "$783" for a true $783.75 — a sentence the page
            # contradicts, and one this round's split had made reachable.
            fee = amount(r"which equals \$([\d,]+\.\d\d)")
            assert fee == (pd_gross * Decimal("0.15")).quantize(Decimal("0.01")), (
                f"gross {gross}: the award prints a 15% fee of {fee} on {pd_gross}, "
                f"which is {pd_gross * Decimal('0.15')}"
            )
            # The same figure appears twice on this page — once in the summary
            # table, once in stipulation 6 — and a fix that reached only one of
            # them is the defect this whole class keeps reproducing.
            tabled = amount(r"Less: Attorney Fees \(15%\) \(\$([\d,]+\.\d\d)\)")
            assert tabled == fee, (
                f"gross {gross}: the award's table says {tabled} and its "
                f"stipulation 6 says {fee}"
            )
            stated_net = amount(r"payable to applicant is \$([\d,]+\.\d\d)")
            assert stated_net == pd_gross - fee, (
                f"gross {gross}: stipulation 6 states a net of {stated_net} "
                f"against {pd_gross} - {fee}"
            )

    def test_the_release_reconciles_and_never_owes_the_applicant_money(
        self, tmp_path: Path
    ) -> None:
        """The release's deductions knew nothing about the settlement they came out of.

        The substrate draws costs from $500 to $3,000 and a Medicare set-aside from
        $5,000 to $25,000 regardless of the gross, so a $21 settlement printed
        **Net to Applicant $-17,608** — a release stating that the applicant
        owes money for settling. Both deductions are now fractions of the gross.

        And the fee: the substrate truncates `gross * 0.15`, so $32,668 printed
        $4,900 for a true $4,900.20. Round 9 fixed that sentence on the
        stipulated award and left it false on the release, which is the more
        important document; the twenty-dollar step on the gross makes it true on
        both.
        """
        for gross in (3, 13810, 32668, 88000):
            manifest, texts, _ = self._generate(
                tmp_path / f"cr{gross}",
                {
                    "wages": WAGES,
                    "benefits": {"td_weeks": 0, "pd_advances": 0},
                    "settlement": {"gross_amount": gross},
                },
                case_id=f"release-{gross}",
                lifecycle={
                    "target_stage": "resolved",
                    "eval_type": "none",
                    "resolution": {"type": "c_and_r", "msa": True},
                },
                documents={"format_mix": {"pdf": 1.0}},
            )
            page = texts["COMPROMISE_AND_RELEASE_STANDARD"]
            published = Decimal(
                manifest["caseFacts"]["money"]["settlement"]["grossAmount"]
            )

            def amount(pattern: str, text: str = page, where: int = gross) -> Decimal:
                found = re.search(pattern, text)
                assert found, f"{pattern!r} not on the release for gross {where}"
                return Decimal(found.group(1).replace(",", ""))

            printed = amount(r"Gross Settlement Amount \$([\d,]+\.\d\d)")
            fee = amount(r"Less: Attorney Fees \(15%\) \(\$([\d,]+\.\d\d)\)")
            costs = amount(r"Less: Costs and Expenses \(\$([\d,]+\.\d\d)\)")
            set_aside = amount(r"Less: Medicare Set-Aside Allocation \(\$([\d,]+\.\d\d)\)")
            net = amount(r"Net to Applicant \$(-?[\d,]+\.\d\d)")

            assert printed == published
            assert fee == (published * Decimal("0.15")).quantize(Decimal("0.01")), (
                f"gross {gross}: the release calls {fee} fifteen percent of "
                f"{published}, which is {published * Decimal('0.15')}"
            )
            # Section 9 states the fee in prose, unbolded — which is why the
            # round-9 correction, matched on the substrate's bold wrapper, fixed
            # the award and missed the release for two rounds. The release is
            # the document that gets signed.
            prose_fee = amount(
                r"in the amount of \$([\d,]+\.\d\d) \(15% of gross settlement\)"
            )
            assert prose_fee == fee, (
                f"gross {gross}: the release's table says {fee} and its section 9 "
                f"says {prose_fee}"
            )
            # Costs are whole dollars by construction, so section 9 prints them
            # without cents where the table pads them. Same figure, and the
            # assertion is on the figure.
            prose_costs = amount(r"plus costs of \$([\d,]+(?:\.\d\d)?)")
            assert prose_costs == costs, (
                f"gross {gross}: the release's table says costs of {costs} and "
                f"its section 9 says {prose_costs}"
            )
            assert net > 0, f"gross {gross}: the release owes the applicant {net}"
            # …and the deductions are the settlement's own. Reconciliation alone
            # does not say so: forcing both to zero keeps the page internally
            # consistent and the net positive, which is how mutation found this
            # claim unguarded. The figures themselves are asserted here.
            expected_costs, expected_set_aside = (
                Decimal(value) for value in settlement_deductions(gross)[1:]
            )
            assert costs == expected_costs, (
                f"gross {gross}: costs of {costs} are not this settlement's "
                f"({expected_costs})"
            )
            assert set_aside == expected_set_aside, (
                f"gross {gross}: a set-aside of {set_aside} is not this "
                f"settlement's ({expected_set_aside})"
            )
            assert printed - fee - costs - set_aside == net, (
                f"gross {gross}: {printed} - {fee} - {costs} - {set_aside} != {net}"
            )

    def test_the_order_approving_the_settlement_says_it_approved_one(
        self, tmp_path: Path
    ) -> None:
        """The designated approval evidence was a document denying a settlement existed.

        `MinutesOrders` ignores its `approving_settlement` variant and draws its
        proceedings from a pool about ongoing litigation, so the first version
        of this carrier printed *"The parties have been unable to reach a
        settlement agreement at this time"* directly above a `Date Approved`
        row. Counter-evidence is worse than no evidence.
        """
        manifest, texts, _ = self._generate(
            tmp_path,
            {"wages": WAGES, "benefits": {"td_weeks": 8}},
            documents={"format_mix": {"pdf": 1.0}},
        )
        settlement = manifest["caseFacts"]["money"]["settlement"]
        page = texts["ORDER_APPROVING_SETTLEMENT"]
        assert "ORDER APPROVING COMPROMISE AND RELEASE" in page
        assert "hereby, APPROVED" in page
        assert "unable to reach a settlement" not in page
        assert "Discovery is to be completed by" not in page
        assert settlement["approvalDate"] in page
        # And its own date is the approval date, not merely on or after it: the
        # order does not report the approval, it is the approval.
        dates = {d["subtype"]: d["documentDate"] for d in manifest["documents"]}
        assert dates["ORDER_APPROVING_SETTLEMENT"] == settlement["approvalDate"]

    def test_the_benefit_ledger_is_a_benefit_ledger(self, tmp_path: Path) -> None:
        """The funding carrier was a provider's medical bill.

        `BillingRecords` is a "STATEMENT OF CHARGES" with a doctor's letterhead,
        random CPT charges and a balance due, so a benefit-free settled case
        evidenced its settlement funding with a $16,724.23 medical bill. The
        problem was not the date; the document was about somebody else's money.
        """
        manifest, texts, _ = self._generate(
            tmp_path,
            {"wages": WAGES, "benefits": {"td_weeks": 8, "pd_advances": 2}},
            documents={"format_mix": {"pdf": 1.0}},
        )
        money = manifest["caseFacts"]["money"]
        page = texts["BENEFIT_PAYMENT_LEDGER"].replace(",", "")
        assert "BENEFIT PAYMENT LEDGER" in page
        assert "STATEMENT OF CHARGES" not in page
        assert "BALANCE DUE" not in page
        assert money["benefits"]["tdTotal"] in page
        assert money["benefits"]["pdTotal"] in page
        assert money["settlement"]["fundingDate"] in page

    def test_no_payment_record_reports_the_settlements_future(
        self, tmp_path: Path
    ) -> None:
        """The rule the release fix established, applied to the path it missed.

        `_rewrite_benefit_record` appended the approval and funding dates to
        every payment record. A record dated 2021-09-29 carried an approval of
        2023-12-27 — **819 days** in its own future.
        """
        manifest, texts, _ = self._generate(
            tmp_path,
            {"wages": WAGES, "benefits": {"td_weeks": 12, "pd_advances": 2}},
            documents={"format_mix": {"pdf": 1.0}},
        )
        settlement = manifest["caseFacts"]["money"]["settlement"]
        records = [
            document
            for document in manifest["documents"]
            if "PAYMENT_RECORD" in document["subtype"]
        ]
        assert records, "the probe needs payment records"
        early = 0
        for document in records:
            page = texts[document["subtype"]]
            assert "Settlement Approved:" not in page
            assert "Settlement Funded:" not in page
            if document["documentDate"] < settlement["approvalDate"]:
                early += 1
        assert early, "the probe needs at least one record predating the approval"

    def test_the_wage_statement_prints_the_periods_the_average_is_made_of(
        self, tmp_path: Path
    ) -> None:
        """Derivable means the operands are on the page, not only the answer."""
        seed = parse_case_seed(
            _seed_body(
                {"wages": WAGES},
                documents={
                    "include_only": [MONEY_WAGE_SUBTYPE],
                    "format_mix": {"pdf": 1.0},
                },
            )
        )
        plan = build_case_plan(seed)
        _manifest, texts, _ = self._generate(
            tmp_path,
            {"wages": WAGES},
            documents={
                "include_only": [MONEY_WAGE_SUBTYPE],
                "format_mix": {"pdf": 1.0},
            },
        )
        page = texts[MONEY_WAGE_SUBTYPE].replace(",", "")
        periods = plan.money_facts.wages.periods
        assert len(periods) >= 20, "the probe needs a real history behind it"
        for period in periods[:6]:
            assert f"{period.gross:.2f}" in page, period

    def test_the_payment_record_prints_the_gap_and_the_lateness(
        self, tmp_path: Path
    ) -> None:
        subtype = "TD_PAYMENT_RECORD_ONGOING"
        assert subtype in BENEFIT_RECORD_SUBTYPES
        manifest, texts, _ = self._generate(
            tmp_path,
            {
                "wages": WAGES,
                "benefits": {
                    "td_weeks": 24,
                    "td_gap_days": 75,
                    "late_payments": 2,
                    "max_days_late": 33,
                },
            },
            documents={"include_only": [subtype], "format_mix": {"pdf": 1.0}},
        )
        page = texts[subtype].replace(",", "")
        assert "NO BENEFITS PAID" in page
        assert "75" in page
        assert "33" in page
        assert manifest["caseFacts"]["money"]["benefits"]["tdTotal"] in page

    def test_the_settlement_gross_on_the_release_is_the_ledgers(
        self, tmp_path: Path
    ) -> None:
        subtype = "COMPROMISE_AND_RELEASE_STANDARD"
        manifest, texts, _ = self._generate(
            tmp_path,
            {"wages": WAGES, "settlement": {"gross_amount": 88000.0}},
            documents={"include_only": [subtype], "format_mix": {"pdf": 1.0}},
        )
        assert manifest["caseFacts"]["money"]["settlement"]["grossAmount"] == "88000.00"
        assert "88,000" in texts[subtype] or "88000" in texts[subtype].replace(",", "")

    def test_a_money_bearing_case_renders_identically_twice(self, tmp_path: Path) -> None:
        """Acceptance: double-render md5 compare is stable for a money case."""
        scenario = {
            "wages": dict(WAGES, pattern="irregular", overtime_share=0.15),
            "benefits": {"td_weeks": 24, "td_gap_days": 60, "late_payments": 2},
            "settlement": {"funding_days": 45},
        }
        first, _, dir_a = self._generate(tmp_path / "a", scenario)
        second, _, dir_b = self._generate(tmp_path / "b", scenario)
        assert [d["md5Checksum"] for d in first["documents"]] == [
            d["md5Checksum"] for d in second["documents"]
        ]
        assert first["caseFacts"] == second["caseFacts"]
        assert (dir_a / CASE_FACTS_NAME).read_bytes() == (
            dir_b / CASE_FACTS_NAME
        ).read_bytes()
        assert len(first["documents"]) > 10, "the probe needs a real case behind it"

    def test_validate_accepts_a_money_bearing_case(self, tmp_path: Path) -> None:
        self._generate(
            tmp_path,
            {"wages": WAGES, "benefits": {"td_weeks": 20}},
        )
        report = validate_output_tree(tmp_path)
        assert report.problems == []


# ---------------------------------------------------------------------------
# The anti-criterion
# ---------------------------------------------------------------------------


@requires_substrate
class TestTheGovernanceTableBindsBothWays:
    """A governance table that only refuses extras is half a table.

    For four review rounds the loop checked `set(section) - set(fields)` and
    nothing else, so deleting `settlement.grossAmount`, `wage.averageWeeklyWage`
    or `benefits.gaps` from a valid manifest was certified clean. Every field in
    the table is emitted unconditionally — nullable ones as `None`, never absent
    — so a missing key is a lost extraction label, not an optional one.
    """

    @staticmethod
    def _block() -> dict[str, Any]:
        facts = _facts(
            {
                "wages": WAGES,
                "benefits": {"td_weeks": 12, "pd_advances": 2},
                "settlement": {
                    "gross_amount": 88000,
                    "approval_date": "2025-01-06",
                    "funding_date": "2025-02-05",
                },
                "penalties": {},
            }
        )
        return {"money": money_manifest_block(facts)}

    def test_every_governed_field_is_required_not_merely_permitted(self) -> None:
        from wc_caseload_engine.manifests import _validate_money
        from wc_caseload_engine.money import GOVERNED_MONEY_FIELDS

        settlement = self._block()["money"]["settlement"]
        documents = _docs(
            MONEY_WAGE_SUBTYPE,
            MONEY_TD_SUBTYPE,
            MONEY_PD_SUBTYPE,
            settlement=settlement,
        )
        assert not _validate_money(self._block(), documents, "c")

        # Every field of every group, off the table rather than by hand — the
        # ISC-177 lesson, applied to the check that names the table.
        checked = 0
        for group, fields in GOVERNED_MONEY_FIELDS.items():
            for field in fields:
                block = self._block()
                assert field in block["money"][group], (
                    f"{group}.{field} is governed but not published, so the "
                    "table and the publisher disagree"
                )
                del block["money"][group][field]
                problems = _validate_money(block, documents, "c")
                assert any(
                    "missing governed field" in problem and field in problem
                    for problem in problems
                ), f"deleting {group}.{field} was accepted: {problems}"
                checked += 1
        assert checked == sum(len(f) for f in GOVERNED_MONEY_FIELDS.values())

    def test_every_published_label_is_checked_against_its_own_vocabulary(self) -> None:
        """`basisSource` was the one extraction label nothing validated.

        `method` and both bound tokens were checked; `basisSource` was not, so
        `"seed-ish"` was accepted as long as the manifest and the artifact
        agreed with each other. Two artifacts agreeing on a value outside the
        vocabulary is a copy, not a check.
        """
        from wc_caseload_engine.manifests import _validate_money

        documents = _docs(
            MONEY_WAGE_SUBTYPE,
            MONEY_TD_SUBTYPE,
            MONEY_PD_SUBTYPE,
            settlement=self._block()["money"]["settlement"],
        )
        assert not _validate_money(self._block(), documents, "c")
        for group, field, bad in (
            ("rate", "basisSource", "seed-ish"),
            ("wage", "method", "made-up-method"),
            ("rate", "tdBound", "sideways"),
        ):
            block = self._block()
            block["money"][group][field] = bad
            assert any(
                field in problem for problem in _validate_money(block, documents, "c")
            ), f"{group}.{field} = {bad!r} was accepted"

    def test_a_lag_between_two_stated_dates_is_a_fact_not_an_option(self) -> None:
        from wc_caseload_engine.manifests import _validate_money

        documents = _docs(
            MONEY_WAGE_SUBTYPE,
            MONEY_TD_SUBTYPE,
            MONEY_PD_SUBTYPE,
            settlement=self._block()["money"]["settlement"],
        )
        block = self._block()
        block["money"]["settlement"]["fundingLagDays"] = None
        assert any(
            "the interval is a fact" in problem
            for problem in _validate_money(block, documents, "c")
        )
        # The opposite draw: with no funding date, None is the honest answer.
        unfunded = self._block()
        unfunded["money"]["settlement"]["fundingDate"] = None
        unfunded["money"]["settlement"]["fundingLagDays"] = None
        assert not _validate_money(unfunded, documents, "c")


@requires_substrate
class TestASettlementIsLargeEnoughForItsOwnDocument:
    """`gross_amount: 0` and `1` were accepted and printed a $27,581 award.

    The floor answers two documents, not one. The stipulated award states two
    whole-dollar cash components summing to the gross, so it needs $2. The
    release subtracts a fee, costs and a set-aside and must still leave the
    applicant money, so it needs $3 — and that is the one that binds. The
    constant searches :func:`settlement_deductions` for the answer rather than
    stating it, so moving a divisor moves the floor with it.
    """

    def test_a_stated_gross_below_the_floor_is_refused(self) -> None:
        from wc_caseload_engine.seeds import (
            SETTLEMENT_GROSS_MINIMUM,
            settlement_deductions,
        )

        assert SETTLEMENT_GROSS_MINIMUM == 3
        # …and it is derived, not stated: one dollar below it, the release the
        # award's floor knows nothing about owes the applicant money.
        below = Decimal(SETTLEMENT_GROSS_MINIMUM - 1)
        fee, costs, set_aside = settlement_deductions(int(below))
        assert below - fee - costs - set_aside <= 0
        fee, costs, set_aside = settlement_deductions(SETTLEMENT_GROSS_MINIMUM)
        assert Decimal(SETTLEMENT_GROSS_MINIMUM) - fee - costs - set_aside > 0

        for gross in (0, 1, 2):
            with pytest.raises(SeedValidationError) as caught:
                _facts(
                    {"wages": WAGES, "settlement": {"gross_amount": gross}},
                    lifecycle={
                        "target_stage": "resolved",
                        "eval_type": "none",
                        "resolution": {"type": "stipulations"},
                    },
                )
            assert "too small" in str(caught.value), gross
            assert str(SETTLEMENT_GROSS_MINIMUM) in str(caught.value), gross

        # The control: the floor itself loads and publishes exactly.
        facts = _facts(
            {"wages": WAGES, "settlement": {"gross_amount": SETTLEMENT_GROSS_MINIMUM}},
            lifecycle={
                "target_stage": "resolved",
                "eval_type": "none",
                "resolution": {"type": "stipulations"},
            },
        )
        assert facts.settlement.gross_amount == Decimal(SETTLEMENT_GROSS_MINIMUM)

    def test_a_derived_gross_is_raised_to_the_floor_rather_than_published_short(
        self,
    ) -> None:
        """Reachable, and found by search rather than assumed.

        The derived gross is the permanent-disability rate over twenty to a
        hundred and twenty weeks, and that rate has a floor from the rate table
        — so no ordinary seed can drive it under $21. An **authored** basis can:
        `pd_min_weekly: 0` with `pd_max_weekly: 0.05` yields a rate of $0.05 and
        a raw gross under a dollar. A derivation is not an author's instruction,
        so it is raised rather than refused.
        """
        from wc_caseload_engine.seeds import SETTLEMENT_GROSS_MINIMUM

        facts = _facts(
            {
                "wages": {
                    "base_weekly_wage": 1,
                    "rate_basis": {"pd_min_weekly": 0.0, "pd_max_weekly": 0.05},
                },
                "benefits": {"td_weeks": 0, "pd_advances": 0},
            },
            rng_seed=11,
            lifecycle={
                "target_stage": "resolved",
                "eval_type": "none",
                "resolution": {"type": "stipulations"},
            },
        )
        assert facts.wages.rate.pd_weekly_rate < Decimal("0.10")
        assert facts.settlement.gross_amount == Decimal(SETTLEMENT_GROSS_MINIMUM)

        # The opposite draw: an ordinary case is nowhere near the floor, so the
        # probe is testing the clamp rather than a coincidence.
        ordinary = _facts(
            {"wages": WAGES, "benefits": {"td_weeks": 0, "pd_advances": 0}},
            rng_seed=11,
            lifecycle={
                "target_stage": "resolved",
                "eval_type": "none",
                "resolution": {"type": "stipulations"},
            },
        )
        assert ordinary.settlement.gross_amount > Decimal(1000)
        # …and it is published in whole dollars. The derivation is a weekly rate
        # with cents multiplied by a week count and added to a paid-to-date
        # total, so a raw derived gross almost always has cents in it: this one
        # is $32,668.47 before quantization. Mutation found the quantization
        # unguarded — removing it left every assertion above green, because
        # nothing here had ever looked at the cents. A gross with cents is not a
        # rounding nicety: the award splits it into two whole-dollar components
        # that must sum back to it exactly.
        # The `td_weeks: 0` case above cannot see this: its rate is a capped
        # whole $290 and its paid-to-date is zero, so the product is whole
        # whatever the week count. A file that was actually *paid* temporary
        # disability carries cents into the sum, and that is the reachable case.
        paid_file = _facts(
            {"wages": WAGES, "benefits": {"td_weeks": 32, "pd_advances": 2}},
            rng_seed=11,
            lifecycle={
                "target_stage": "resolved",
                "eval_type": "none",
                "resolution": {"type": "stipulations"},
            },
        )
        rate = paid_file.wages.rate.pd_weekly_rate
        paid = paid_file.benefits.td_total
        assert paid != paid.to_integral_value(), paid
        raw = [rate * Decimal(weeks) + paid for weeks in range(20, 121)]
        assert all(value != value.to_integral_value() for value in raw), (
            "no week count in the derivation's own range produces cents, so "
            "this probe cannot tell a quantized publication from an "
            "unquantized one"
        )
        for seed_value in range(11, 21):
            published = _facts(
                {"wages": WAGES, "benefits": {"td_weeks": 32, "pd_advances": 2}},
                rng_seed=seed_value,
                lifecycle={
                    "target_stage": "resolved",
                    "eval_type": "none",
                    "resolution": {"type": "stipulations"},
                },
            ).settlement.gross_amount
            assert published == published.to_integral_value(), (
                f"rng_seed {seed_value}: a derived gross of {published} was "
                "published with cents"
            )


@requires_substrate
class TestTheOrderIsDatedOnTheApprovalItIs:
    """An approving order does not report an approval; it is the approval.

    The floor re-dated forward only, which is right for a document that reports
    events and wrong for one that constitutes an event. An authored approval of
    2022-01-05 was evidenced by an order dated 2023-12-27 — 721 days later — and
    the on-or-after rule certified it.
    """

    def test_an_authored_approval_pins_the_order_in_both_directions(self) -> None:
        from wc_caseload_engine.planner import MONEY_APPROVAL_SUBTYPE

        # One authored approval before the walk's own order date and one after,
        # so the probe cannot pass by only ever moving the date one way.
        for approval in ("2022-01-05", "2025-06-30"):
            for resolution in ("c_and_r", "stipulations"):
                plan = build_case_plan(
                    parse_case_seed(
                        _seed_body(
                            {
                                "wages": WAGES,
                                "benefits": {"td_weeks": 10},
                                "settlement": {
                                    "gross_amount": 88000,
                                    "approval_date": approval,
                                },
                            },
                            lifecycle={
                                "target_stage": "resolved",
                                "eval_type": "qme",
                                "resolution": {"type": resolution},
                            },
                        )
                    )
                )
                orders = [
                    candidate.doc_date
                    for candidate in plan.documents
                    if candidate.subtype == MONEY_APPROVAL_SUBTYPE
                ]
                assert orders, f"{approval}/{resolution}: no approving order"
                assert all(
                    when == date.fromisoformat(approval) for when in orders
                ), f"{approval}/{resolution}: order dated {orders}, not on the approval"

    def test_the_whole_settlement_chain_is_ordered_not_just_each_link(self) -> None:
        """Pinning one node to an authored date broke the link before it.

        The chain is `instrument <= approval == order <= funding <= ledger`. The
        pin satisfied its own link and put the order **677 days** before the
        stipulations it recites as "filed herein" — every local relation held
        and the sequence was still impossible. A chain checked link by link
        still has to be a chain.
        """
        from wc_caseload_engine.planner import (
            MONEY_APPROVAL_SUBTYPE,
            MONEY_FUNDING_SUBTYPE,
            MONEY_INSTRUMENT_SUBTYPES,
        )

        seen = 0
        for approval in ("2022-01-05", "2023-03-30", "2025-06-30"):
            for resolution in ("c_and_r", "stipulations"):
                plan = build_case_plan(
                    parse_case_seed(
                        _seed_body(
                            {
                                "wages": WAGES,
                                "benefits": {"td_weeks": 10},
                                "settlement": {
                                    "gross_amount": 88000,
                                    "approval_date": approval,
                                    "funding_days": 14,
                                },
                            },
                            lifecycle={
                                "target_stage": "resolved",
                                "eval_type": "qme",
                                "resolution": {"type": resolution},
                            },
                        )
                    )
                )
                settlement = plan.money_facts.settlement
                where = f"{approval}/{resolution}"
                dated: dict[str, list[date]] = {}
                for candidate in plan.documents:
                    dated.setdefault(candidate.subtype, []).append(candidate.doc_date)

                instruments = [
                    when
                    for subtype in MONEY_INSTRUMENT_SUBTYPES
                    for when in dated.get(subtype, [])
                ]
                assert instruments, f"{where}: no settlement instrument planned"
                assert max(instruments) <= settlement.approval_date, (
                    f"{where}: instrument dated {max(instruments)} but approval is "
                    f"{settlement.approval_date} — the order would approve an "
                    "instrument that does not exist yet"
                )
                assert dated[MONEY_APPROVAL_SUBTYPE] == [settlement.approval_date]
                assert settlement.funding_date >= settlement.approval_date
                assert max(dated[MONEY_FUNDING_SUBTYPE]) >= settlement.funding_date
                seen += 1
        assert seen == 6

    def test_an_approval_the_file_could_not_have_reached_is_moved_and_reported(
        self,
    ) -> None:
        """The chain starts at the Application, and the floor belongs on the approval.

        Flooring the *instrument* was defeated by the clamp that kept the chain
        ordered: `min(filed, approval)` put a compromise and release on
        2021-06-15 for a case whose claim was filed 2021-06-27 and whose
        Application was filed 2021-10-05 — an instrument reciting a filing that
        would not exist for eleven weeks, and predating the claim itself.
        """
        from wc_caseload_engine.lifecycle_bridge import build_timeline
        from wc_caseload_engine.planner import MONEY_INSTRUMENT_SUBTYPES

        for resolution in ("c_and_r", "stipulations"):
            body = _seed_body(
                {
                    "wages": WAGES,
                    "settlement": {
                        "gross_amount": 88000,
                        "approval_date": "2021-06-15",
                        "funding_days": 14,
                    },
                },
                lifecycle={
                    "target_stage": "resolved",
                    "eval_type": "qme",
                    "resolution": {"type": resolution},
                },
            )
            seed = parse_case_seed(body)
            timeline = build_timeline(seed)
            plan = build_case_plan(seed)
            settlement = plan.money_facts.settlement

            # Moved forward, past the Application the instrument recites.
            assert settlement.approval_date > date(2021, 6, 15)
            assert settlement.approval_date > timeline.application_filed_date
            assert settlement.approval_date > timeline.claim_filed_date

            # …and said so, rather than adjusting a stated control in silence.
            assert any(
                "approval_date" in warning and "2021-06-15" in warning
                for warning in plan.warnings
            ), plan.warnings

            # A stated funding date is carried by the same shift. Leaving it
            # behind published `fundingLagDays: -117` — money moving four months
            # before the Board approved it, which is the impossibility ISC-179
            # paired these two fields to prevent.
            paired = build_case_plan(
                parse_case_seed(
                    _seed_body(
                        {
                            "wages": WAGES,
                            "settlement": {
                                "gross_amount": 88000,
                                "approval_date": "2021-06-15",
                                "funding_date": "2021-07-01",
                            },
                        },
                        lifecycle={
                            "target_stage": "resolved",
                            "eval_type": "qme",
                            "resolution": {"type": resolution},
                        },
                    )
                )
            ).money_facts.settlement
            assert paired.funding_date > paired.approval_date
            assert paired.funding_lag_days == 16, (
                "the authored interval was 16 days and must survive the move, "
                f"but the ledger records {paired.funding_lag_days}"
            )

            # The whole chain still holds, including the link that broke.
            dated: dict[str, list[date]] = {}
            for candidate in plan.documents:
                dated.setdefault(candidate.subtype, []).append(candidate.doc_date)
            instruments = [
                when
                for subtype in MONEY_INSTRUMENT_SUBTYPES
                for when in dated.get(subtype, [])
            ]
            assert instruments, resolution
            assert min(instruments) >= timeline.claim_filed_date, (
                f"{resolution}: instrument {min(instruments)} predates the claim "
                f"filed {timeline.claim_filed_date}"
            )
            assert max(instruments) <= settlement.approval_date

    def test_the_dropped_funding_warning_names_the_control_that_caused_it(
        self,
    ) -> None:
        """A warning that names the wrong knob is not followable.

        The dropped-funding warning knew only about `funding_days`, so a stated
        `funding_date` carried past the horizon by a forced approval was
        reported as "the funding lag for this adjuster" — a control the seed
        never mentioned and the author cannot act on.
        """
        plan = build_case_plan(
            parse_case_seed(
                _seed_body(
                    {
                        "wages": WAGES,
                        "settlement": {
                            "gross_amount": 88000,
                            "approval_date": "2021-06-15",
                            "funding_date": "2025-12-31",
                        },
                    },
                    lifecycle={
                        "target_stage": "resolved",
                        "eval_type": "qme",
                        "resolution": {"type": "c_and_r"},
                    },
                )
            )
        )
        assert plan.money_facts.settlement.funding_date is None
        dropped = [
            warning
            for warning in plan.warnings
            if "not yet funded" in warning
        ]
        assert dropped, plan.warnings
        assert any("funding_date of 2025-12-31" in warning for warning in dropped), dropped
        assert not any("for this adjuster" in warning for warning in dropped), dropped
        # …and it says *why* that date is out of range, which is not the date.
        # 2025-12-31 is comfortably inside the horizon; the approval shift is
        # what carried it out. A warning naming only the authored date advises
        # moving the approval earlier, which makes the shift larger — exactly
        # backwards. Mutation found this claim unguarded: zeroing the shift left
        # every other assertion here green.
        shift = (
            plan.money_facts.settlement.approval_date - date(2021, 6, 15)
        ).days
        assert shift > 0, shift
        assert any(
            f"carried {shift} day(s) forward" in warning for warning in dropped
        ), dropped

        # The opposite draw: with no stated date, the lag is what to name.
        by_lag = build_case_plan(
            parse_case_seed(
                _seed_body(
                    {
                        "wages": WAGES,
                        "settlement": {
                            "gross_amount": 88000,
                            "approval_date": "2025-12-31",
                            "funding_days": 400,
                        },
                    },
                    lifecycle={
                        "target_stage": "resolved",
                        "eval_type": "qme",
                        "resolution": {"type": "c_and_r"},
                    },
                )
            )
        )
        lagged = [w for w in by_lag.warnings if "not yet funded" in w]
        assert lagged and any("funding_days of 400" in w for w in lagged), lagged

    def test_an_approval_the_file_can_reach_is_left_alone(self) -> None:
        """The opposite draw: a feasible authored approval is honoured exactly."""
        plan = build_case_plan(
            parse_case_seed(
                _seed_body(
                    {
                        "wages": WAGES,
                        "settlement": {
                            "gross_amount": 88000,
                            "approval_date": "2023-03-30",
                        },
                    },
                    lifecycle={
                        "target_stage": "resolved",
                        "eval_type": "qme",
                        "resolution": {"type": "c_and_r"},
                    },
                )
            )
        )
        assert plan.money_facts.settlement.approval_date == date(2023, 3, 30)
        assert not any("approval_date" in warning for warning in plan.warnings)

    def test_the_validator_refuses_an_instrument_that_postdates_its_approval(
        self,
    ) -> None:
        from wc_caseload_engine.manifests import _validate_money

        facts = _facts(
            {
                "wages": WAGES,
                "settlement": {
                    "gross_amount": 88000,
                    "approval_date": "2025-01-06",
                    "funding_date": "2025-02-05",
                },
            }
        )
        block = {"money": money_manifest_block(facts)}

        def problems(instrument_date: str) -> list[str]:
            return [
                problem
                for problem in _validate_money(
                    block,
                    [
                        {"subtype": MONEY_WAGE_SUBTYPE, "documentDate": "2021-01-01"},
                        {
                            "subtype": "STIPULATIONS_WITH_REQUEST_FOR_AWARD",
                            "documentDate": instrument_date,
                        },
                        {
                            "subtype": "ORDER_APPROVING_SETTLEMENT",
                            "documentDate": "2025-01-06",
                        },
                        {
                            "subtype": "BENEFIT_PAYMENT_LEDGER",
                            "documentDate": "2025-02-05",
                        },
                    ],
                    "c",
                )
                if "does not exist yet" in problem
            ]

        assert problems("2025-01-07"), "an instrument after its own approval passed"
        assert not problems("2025-01-06")
        assert not problems("2024-12-16")

    def test_the_validator_refuses_an_order_dated_off_the_approval(self) -> None:
        from wc_caseload_engine.manifests import _validate_money

        facts = _facts(
            {
                "wages": WAGES,
                "settlement": {
                    "gross_amount": 88000,
                    "approval_date": "2025-01-06",
                    "funding_date": "2025-02-05",
                },
            }
        )
        block = {"money": money_manifest_block(facts)}

        def problems(order_date: str) -> list[str]:
            return [
                problem
                for problem in _validate_money(
                    block,
                    [
                        {"subtype": MONEY_WAGE_SUBTYPE, "documentDate": "2021-01-01"},
                        {
                            "subtype": "ORDER_APPROVING_SETTLEMENT",
                            "documentDate": order_date,
                        },
                        {
                            "subtype": "BENEFIT_PAYMENT_LEDGER",
                            "documentDate": "2025-02-05",
                        },
                    ],
                    "c",
                )
                if "cannot report its own future" in problem
            ]

        assert problems("2025-01-05"), "a day early was accepted"
        assert problems("2025-01-07"), "a day late was accepted — which >= allowed"
        assert not problems("2025-01-06")


@requires_substrate
class TestAFatalClaimPaysBenefitsThisLayerDoesNotModel:
    """Money on a death claim derived benefits the worker could not receive."""

    @staticmethod
    def _fatal(scenario: dict[str, Any] | None) -> dict[str, Any]:
        body = _seed_body(
            scenario,
            lifecycle={
                "target_stage": "resolved",
                "eval_type": "qme",
                "resolution": {"type": "stipulations"},
            },
        )
        body["injury"] = {
            "type": "death",
            "date_of_injury": "2023-01-19",
            "body_parts": [{"part": "head"}],
        }
        return body

    def test_a_fatal_injury_refuses_the_money_blocks(self) -> None:
        """Measured before this rule: a first TD period beginning three days after death."""
        for scenario in (
            {"wages": {"base_weekly_wage": 1200}},
            {"wages": WAGES, "benefits": {"td_weeks": 10}},
            {"wages": WAGES, "settlement": {"gross_amount": 88000}},
        ):
            with pytest.raises(Exception) as raised:
                parse_case_seed(self._fatal(scenario))
            assert "dependency benefits" in str(raised.value), scenario

    def test_a_fatal_injury_without_money_still_loads(self) -> None:
        """The opposite draw: death is not refused, money on death is."""
        plan = build_case_plan(parse_case_seed(self._fatal(None)))
        assert plan.money_facts is None


@requires_substrate
class TestTheBasisSaysHowMuchOfItWasAuthored:
    """`basisSource` had two values for three situations.

    A partial override — one authored figure merged into five defaulted ones —
    published `source: seed` for the whole binding, beside a `basisLabel` still
    naming the engine vintage the other five came from. An analyzer scored on
    that label would be learning that `seed` means "between one and six of these
    were authored", which is not a fact about anything.
    """

    def test_the_source_names_how_much_the_seed_actually_stated(self) -> None:
        every = {
            "td_fraction": 0.5,
            "pd_fraction": 0.5,
            "td_max_weekly": 900,
            "td_min_weekly": 100,
            "pd_max_weekly": 200,
            "pd_min_weekly": 50,
        }
        cases = [
            (None, "engine_default_table"),
            ({"td_fraction": 0.5}, "mixed"),
            ({"td_max_weekly": 900, "td_min_weekly": 100}, "mixed"),
            (every, "seed"),
            # Authority is prose *about* the numbers, not one of them, so it
            # cannot promote a partial binding to a wholly authored one.
            # Authority cannot promote a partial binding to a wholly authored
            # one — nor, found by review, make a binding "mixed" that states no
            # figure at all. The empty-block early return is keyed on *any*
            # change, and an authority-only block passes it.
            (dict(every, authority="Board bulletin 2021-04"), "seed"),
            ({"td_fraction": 0.5, "authority": "Board bulletin 2021-04"}, "mixed"),
            ({"authority": "Author prose only; no figures"}, "engine_default_table"),
        ]
        for override, expected in cases:
            wages = dict(WAGES) if override is None else dict(WAGES, rate_basis=override)
            rate = money_manifest_block(_facts({"wages": wages}))["rate"]
            assert rate["basisSource"] == expected, (
                f"rate_basis={override!r} published basisSource "
                f"{rate['basisSource']!r}, expected {expected!r}"
            )

    def test_a_partial_override_keeps_the_figures_it_did_not_state(self) -> None:
        """`mixed` is only honest if it is describing a real mixture."""
        from wc_caseload_engine.money import rate_basis_for

        table = rate_basis_for(date(2021, 6, 14))
        basis = _facts(
            {"wages": dict(WAGES, rate_basis={"td_fraction": 0.5})}
        ).wages.rate.basis
        assert basis.td_fraction == Decimal("0.5")
        for field in ("pd_fraction", "td_max_weekly", "td_min_weekly",
                      "pd_max_weekly", "pd_min_weekly"):
            assert getattr(basis, field) == getattr(table, field)


@requires_substrate
class TestASeedWithoutWagesProducesNoMoneyArtifacts:
    """ISC-21.5's shape, applied to money. Negative grep plus a code path.

    The negative grep alone would be weak: the strings it looks for are ones a
    substrate template could coincidentally produce. The code-path assertion is
    the load-bearing half — the money-aware subclass *is* dispatched for these
    subtypes, and it returns the substrate's own story untouched.
    """

    #: Strings only the money layer can emit. Chosen because no substrate
    #: template contains them: the method names are this package's vocabulary,
    #: and the two labels are literals defined in ``fact_templates``.
    MARKERS = (
        UNCONFIRMED_NOTICE,
        METHOD_LABEL,
        "NO BENEFITS PAID",
        *AWW_METHODS,
    )

    def test_no_money_marker_appears_anywhere_in_a_wage_free_case(
        self, tmp_path: Path
    ) -> None:
        seed = parse_case_seed(
            _seed_body(
                None,
                documents={
                    # An earned zero: the case is forced to hold exactly the
                    # documents the money layer would have governed, so their
                    # silence is evidence rather than an accident of emission.
                    "include_only": [
                        MONEY_WAGE_SUBTYPE,
                        "TD_PAYMENT_RECORD_ONGOING",
                        "PD_PAYMENT_RECORD_ADVANCE",
                        "COMPROMISE_AND_RELEASE_STANDARD",
                    ],
                    "format_mix": {"pdf": 1.0},
                },
            )
        )
        generate_case(seed, tmp_path, 1)
        directory = tmp_path / seed.case_id
        manifest = json.loads((directory / MANIFEST_NAME).read_text(encoding="utf-8"))

        assert len(manifest["documents"]) == 4, "the probe must witness all four"
        assert "money" not in manifest["caseFacts"]
        assert "money" not in (directory / CASE_FACTS_NAME).read_text(encoding="utf-8")

        for document in manifest["documents"]:
            text = extract_text(
                directory / "documents" / document["filename"], document["format"]
            )
            for marker in self.MARKERS:
                assert marker not in text, (document["subtype"], marker)

    def test_the_positive_control_fires(self, tmp_path: Path) -> None:
        """The same probe on a money-bearing case must find the markers.

        Without this the negative test could be passing because the extraction
        is broken, which is the vacuous-assertion class this suite has hit
        three times.
        """
        seed = parse_case_seed(
            _seed_body(
                {"wages": WAGES, "benefits": {"td_weeks": 20, "td_gap_days": 45}},
                documents={
                    # The carriers are part of a settled case's evidence, so an
                    # include_only that drops them produces a folder that cannot
                    # support its own manifest — which `validate --out` now says,
                    # correctly, and which is the same rule that has always
                    # applied to the wage statement.
                    "include_only": [
                        MONEY_WAGE_SUBTYPE,
                        "TD_PAYMENT_RECORD_ONGOING",
                        "ORDER_APPROVING_SETTLEMENT",
                        "BENEFIT_PAYMENT_LEDGER",
                    ],
                    "format_mix": {"pdf": 1.0},
                },
            )
        )
        generate_case(seed, tmp_path, 1)
        directory = tmp_path / seed.case_id
        manifest = json.loads((directory / MANIFEST_NAME).read_text(encoding="utf-8"))
        combined = "".join(
            extract_text(directory / "documents" / d["filename"], d["format"])
            for d in manifest["documents"]
        )
        assert "money" in manifest["caseFacts"]
        for marker in (UNCONFIRMED_NOTICE, METHOD_LABEL, "NO BENEFITS PAID"):
            assert marker in combined, marker

    def test_the_money_subclass_is_dispatched_and_delegates(self) -> None:
        """The code path, not the output. The half that makes the grep sound.

        The subtype resolves to the engine subclass either way — so "no money
        artifacts" is not achieved by dodging the registry, which would leave
        the guarantee resting on dispatch luck. It is achieved by the subclass
        returning the substrate's story when the ledger is ``None``.
        """
        for subtype in (MONEY_WAGE_SUBTYPE, "COMPROMISE_AND_RELEASE_STANDARD"):
            registered = fact_aware_templates()[subtype]
            resolved, _variant, _name = _load_template(subtype, fact_aware=True)
            assert resolved is registered
            plain, _variant, _name = _load_template(subtype, fact_aware=False)
            assert plain is not registered
            assert issubclass(registered, plain)


@requires_substrate
def test_the_demo_caseload_publishes_no_money(demo_manifests: dict[str, Any]) -> None:
    """No committed example seeds wages, so no committed manifest gains a key.

    The whole-corpus form of the anti-criterion, and the reason the byte
    accounting for this change is 0/353 rather than a list of explained
    differences.
    """
    assert demo_manifests, "the demo fixture produced nothing"
    for case_id, manifest in demo_manifests.items():
        assert "money" not in manifest.get("caseFacts", {}), case_id


# ---------------------------------------------------------------------------
# The validator's own controls
# ---------------------------------------------------------------------------


@requires_substrate
class TestTheValidatorRefusesAnUncheckableClaim:
    """Planted violations, so the rules are proved to fire rather than assumed."""

    @staticmethod
    def _generated(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
        seed = parse_case_seed(
            _seed_body(
                {"wages": WAGES, "benefits": {"td_weeks": 20}},
                documents={
                    # A settled case's approval and funding dates are evidenced
                    # by the order and the ledger, so an include_only that drops
                    # them yields a folder that cannot support its own manifest.
                    "include_only": [
                        MONEY_WAGE_SUBTYPE,
                        "TD_PAYMENT_RECORD_ONGOING",
                        "ORDER_APPROVING_SETTLEMENT",
                        "BENEFIT_PAYMENT_LEDGER",
                    ],
                    "format_mix": {"pdf": 1.0},
                },
            )
        )
        generate_case(seed, tmp_path, 1)
        directory = tmp_path / seed.case_id
        return directory, json.loads(
            (directory / MANIFEST_NAME).read_text(encoding="utf-8")
        )

    @staticmethod
    def _rewrite(directory: Path, manifest: dict[str, Any]) -> None:
        """Write the tampered manifest *and* the artifact, so only one rule fires.

        Rewriting the manifest alone would also trip the artifact-drift rule,
        and a test that cannot tell which rule caught it is not testing either.
        """
        import yaml

        (directory / MANIFEST_NAME).write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )
        header = (directory / CASE_FACTS_NAME).read_text(encoding="utf-8").split("\n")
        preamble = "\n".join(line for line in header if line.startswith("#"))
        (directory / CASE_FACTS_NAME).write_text(
            preamble + "\n" + yaml.safe_dump(manifest["caseFacts"], sort_keys=False),
            encoding="utf-8",
        )

    def test_a_clean_case_passes(self, tmp_path: Path) -> None:
        self._generated(tmp_path)
        assert validate_output_tree(tmp_path).problems == []

    def test_an_aww_with_no_wage_statement_is_refused(self, tmp_path: Path) -> None:
        directory, manifest = self._generated(tmp_path)
        manifest["documents"] = [
            d for d in manifest["documents"] if d["subtype"] != MONEY_WAGE_SUBTYPE
        ]
        self._rewrite(directory, manifest)
        problems = validate_output_tree(tmp_path).problems
        assert any("no wage statement" in problem for problem in problems), problems

    def test_an_ungoverned_money_field_is_refused(self, tmp_path: Path) -> None:
        directory, manifest = self._generated(tmp_path)
        manifest["caseFacts"]["money"]["wage"]["secretMultiplier"] = 1.7
        self._rewrite(directory, manifest)
        problems = validate_output_tree(tmp_path).problems
        assert any("ungoverned" in problem for problem in problems), problems

    def test_an_unknown_method_is_refused(self, tmp_path: Path) -> None:
        directory, manifest = self._generated(tmp_path)
        manifest["caseFacts"]["money"]["wage"]["method"] = "vibes"
        self._rewrite(directory, manifest)
        problems = validate_output_tree(tmp_path).problems
        assert any("vibes" in problem for problem in problems), problems

    def test_a_missing_confirmation_flag_is_refused(self, tmp_path: Path) -> None:
        directory, manifest = self._generated(tmp_path)
        del manifest["caseFacts"]["money"]["rate"]["counselConfirmed"]
        self._rewrite(directory, manifest)
        problems = validate_output_tree(tmp_path).problems
        assert any("counselConfirmed" in problem for problem in problems), problems

    def test_a_benefit_event_with_no_payment_record_is_refused(self) -> None:
        """Any event needs a document, not only a temporary-disability one.

        The rule was written for the half that had a probe: a case publishing
        four permanent-disability advances and no payment record at all passed
        `_validate_money` clean, which is the same asserted-not-derivable
        failure the TD rule exists to catch.
        """
        from wc_caseload_engine.manifests import _validate_money

        facts = _facts({"wages": WAGES, "benefits": {"td_weeks": 0, "pd_advances": 4}})
        block = {"money": money_manifest_block(facts)}
        assert block["money"]["benefits"]["pdAdvanceCount"] > 0
        problems = _validate_money(
            block,
            _docs(MONEY_WAGE_SUBTYPE, settlement=block["money"].get("settlement")),
            "probe-case",
        )
        # "benefit event", not "payment record": the settlement rule added later
        # also says "payment record", and a probe a *different* rule can satisfy
        # is not testing the rule it names. Found by re-running this campaign
        # after the settlement rule landed.
        assert any("benefit event" in p for p in problems), problems

        # The control: add the record and the same ledger passes.
        assert not any(
            "benefit event" in p
            for p in _validate_money(
                block,
                _docs(
                    MONEY_WAGE_SUBTYPE,
                    MONEY_PD_SUBTYPE,
                    settlement=block["money"].get("settlement"),
                ),
                "probe-case",
            )
        )

    def test_a_malformed_event_is_refused(self) -> None:
        """The ledger is the eval label. A label that is a bare string is broken, not lesser."""
        from wc_caseload_engine.manifests import _validate_money

        facts = _facts({"wages": WAGES, "benefits": {"td_weeks": 8}})
        block = {"money": money_manifest_block(facts)}
        documents = _docs(
            MONEY_WAGE_SUBTYPE,
            MONEY_TD_SUBTYPE,
            settlement=block["money"].get("settlement"),
        )
        assert not _validate_money(block, documents, "probe-case")

        block["money"]["benefits"]["tdPeriods"] = ["garbage"]
        block["money"]["benefits"]["tdPeriodCount"] = 1
        problems = _refusals(block, documents, "probe-case", given="a bare string event")
        assert any("str where a record was expected" in p for p in problems), problems

    def test_a_malformed_count_or_gap_is_refused_rather_than_crashing(self) -> None:
        """A validator that trusts its input crashes on the input it exists to reject.

        `tdPeriodCount: "one"` raised `TypeError` out of the event sum — and a
        crash is not a verdict. `gaps: ["garbage"]` was the one array nothing
        type-checked at all.
        """
        from wc_caseload_engine.manifests import _validate_money

        facts = _facts({"wages": WAGES, "benefits": {"td_weeks": 12, "td_gap_days": 30}})
        documents = _docs(
            MONEY_WAGE_SUBTYPE,
            MONEY_TD_SUBTYPE,
            settlement=money_manifest_block(facts).get("settlement"),
        )
        assert not _validate_money({"money": money_manifest_block(facts)}, documents, "c")

        broken_count = {"money": money_manifest_block(facts)}
        broken_count["money"]["benefits"]["tdPeriodCount"] = "one"
        problems = _refusals(broken_count, documents, "c", given='tdPeriodCount: "one"')
        assert any("expected a count of zero or more" in p for p in problems), problems

        broken_gaps = {"money": money_manifest_block(facts)}
        broken_gaps["money"]["benefits"]["gaps"] = ["garbage"]
        problems = _refusals(broken_gaps, documents, "c", given='gaps: ["garbage"]')
        assert any("gaps holds a str" in p for p in problems), problems

        miscounted = {"money": money_manifest_block(facts)}
        assert miscounted["money"]["benefits"]["gaps"], "the probe needs a gap"
        miscounted["money"]["benefits"]["gaps"][0]["days"] += 5
        problems = _validate_money(miscounted, documents, "c")
        assert any("records days" in p for p in problems), problems

        # `bool` is a subclass of `int`, so an isinstance check passed
        # `tdPeriodCount: True` and it then compared equal to a length of one.
        boolean = {"money": money_manifest_block(facts)}
        boolean["money"]["benefits"]["tdPeriods"] = boolean["money"]["benefits"][
            "tdPeriods"
        ][:1]
        boolean["money"]["benefits"]["tdPeriodCount"] = True
        problems = _validate_money(boolean, documents, "c")
        assert any("expected a count of zero or more" in p for p in problems), problems

        # And a reversed gap whose day count is negative: span and count agree,
        # which is two wrongs cancelling rather than a check passing.
        reversed_gap = {"money": money_manifest_block(facts)}
        reversed_gap["money"]["benefits"]["gaps"] = [
            {"start": "2025-01-10", "end": "2025-01-01", "days": -8}
        ]
        problems = _validate_money(reversed_gap, documents, "c")
        assert any("runs forwards" in p for p in problems), problems

    def test_an_unpaid_benefit_cannot_also_be_late(self) -> None:
        """Never paid is an interruption; late is a delay. There is no second date."""
        from wc_caseload_engine.manifests import _validate_money

        facts = _facts({"wages": WAGES, "benefits": {"td_weeks": 12}})
        block = {"money": money_manifest_block(facts)}
        documents = _docs(
            MONEY_WAGE_SUBTYPE,
            MONEY_TD_SUBTYPE,
            settlement=block["money"].get("settlement"),
        )
        assert not _validate_money(block, documents, "c")

        block["money"]["benefits"]["tdPeriods"][0]["datePaid"] = None
        block["money"]["benefits"]["tdPeriods"][0]["daysLate"] = 62
        problems = _validate_money(block, documents, "c")
        assert any("never paid" in p for p in problems), problems

        # The control: unpaid and not late is the ordinary interruption.
        block["money"]["benefits"]["tdPeriods"][0]["daysLate"] = 0
        assert not _validate_money(block, documents, "c")

    def test_a_lateness_that_does_not_follow_from_the_dates_is_refused(self) -> None:
        """Both ledgers, not just the one that had a probe."""
        from wc_caseload_engine.manifests import _validate_money

        facts = _facts(
            {
                "wages": WAGES,
                "benefits": {"td_weeks": 8, "pd_advances": 2, "late_payments": 3,
                             "max_days_late": 30},
            }
        )
        documents = _docs(
            MONEY_WAGE_SUBTYPE,
            MONEY_TD_SUBTYPE,
            MONEY_PD_SUBTYPE,
            settlement=money_manifest_block(facts).get("settlement"),
        )
        for array_key, word in (("tdPeriods", "temporary"), ("pdAdvances", "permanent")):
            block = {"money": money_manifest_block(facts)}
            assert not _validate_money(block, documents, "probe-case")
            events = block["money"]["benefits"][array_key]
            assert events, f"the probe needs a {array_key} record"
            events[0]["daysLate"] = events[0]["daysLate"] + 5
            problems = _validate_money(block, documents, "probe-case")
            assert any(word in p and "daysLate" in p for p in problems), (array_key, problems)

    def test_a_settlement_is_shape_checked_and_governed_like_everything_else(self) -> None:
        """The settlement group was skipped by the governance loop along with its absence.

        `if key == "settlement": continue` was meant to say "absent is fine" and
        said "never checked" — so `settlement: []` crashed the validator with
        `AttributeError`, `approvalDate: 1` crashed it with `TypeError`, and an
        ungoverned `settlement.surprise` was certified. A crash is not a verdict,
        and an ungoverned field is an extraction label no document promised.
        """
        from wc_caseload_engine.manifests import _validate_money

        facts = _facts({"wages": WAGES, "settlement": {"gross_amount": 88000}})
        documents = _docs(
            MONEY_WAGE_SUBTYPE,
            MONEY_TD_SUBTYPE,
            "COMPROMISE_AND_RELEASE_STANDARD",
            settlement=money_manifest_block(facts).get("settlement"),
        )
        assert not _validate_money({"money": money_manifest_block(facts)}, documents, "c")

        cases: list[tuple[str, Any, str]] = [
            ("settlement is a list", [], "not a mapping"),
            ("an ungoverned field", {"surprise": "x"}, "ungoverned"),
            ("a non-date approval", {"approvalDate": 1}, "not a date"),
            ("a wrong lag", {"fundingLagDays": 999}, "fundingLagDays"),
        ]
        for label, mutation, expected in cases:
            block = {"money": money_manifest_block(facts)}
            if isinstance(mutation, list):
                block["money"]["settlement"] = mutation
            else:
                block["money"]["settlement"].update(mutation)
            problems = _refusals(block, documents, "c", given=label)
            assert any(expected in p for p in problems), (label, problems)

    def test_penalties_are_shape_checked_and_governed_like_everything_else(self) -> None:
        """A present penalties group is checked instead of skipped as optional."""
        from wc_caseload_engine.manifests import _validate_money

        facts = _facts(
            {
                "wages": WAGES,
                "benefits": {
                    "td_weeks": 24,
                    "td_gap_days": 45,
                    "late_payments": 2,
                    "max_days_late": 45,
                },
                "penalties": {},
            }
        )
        clean = {"money": money_manifest_block(facts)}
        documents = _docs(
            MONEY_WAGE_SUBTYPE,
            MONEY_TD_SUBTYPE,
            settlement=clean["money"].get("settlement"),
        )
        assert not _validate_money(clean, documents, "c")

        cases: list[tuple[str, Any, str]] = [
            ("penalties is a list", [], "not a mapping"),
            ("an ungoverned field", {"surprise": "x"}, "ungoverned"),
        ]
        for label, mutation, expected in cases:
            block = {"money": money_manifest_block(facts)}
            if isinstance(mutation, list):
                block["money"]["penalties"] = mutation
            else:
                block["money"]["penalties"].update(mutation)
            problems = _refusals(block, documents, "c", given=label)
            assert any(expected in p for p in problems), (label, problems)

    def test_settlement_dates_need_a_document_that_could_know_them(self) -> None:
        """A carrier is a subtype *and* a date, and the first cut checked only the subtype.

        A settled case with no benefits published all three fields with no
        carrying document at all — `validate --out` passed it. The fix for that
        accepted a release or any payment record, and review showed both are
        anachronistic: the release is signed before the Board approves, and a
        temporary-disability payment record is dated years before the settlement
        it would be vouching for. Reproduced here at both ends.
        """
        from wc_caseload_engine.manifests import _validate_money

        facts = _facts(
            {
                "wages": WAGES,
                "benefits": {"td_weeks": 0, "pd_advances": 0},
                "settlement": {
                    "gross_amount": 88000,
                    "approval_date": "2025-01-06",
                    "funding_date": "2025-02-05",
                },
            }
        )
        block = {"money": money_manifest_block(facts)}
        assert block["money"]["settlement"]["approvalDate"]

        def problems(docs: list[dict[str, Any]]) -> list[str]:
            return [
                p
                for p in _validate_money(block, docs, "c")
                if "cannot report its own future" in p
            ]

        # Nothing in the folder to read either date from.
        assert len(problems(_docs(MONEY_WAGE_SUBTYPE, carriers=False))) == 2

        # The release and a payment record are not carriers, however they are
        # dated: neither is the document that effects either event.
        assert len(
            problems(
                [
                    {"subtype": MONEY_WAGE_SUBTYPE, "documentDate": "2026-01-01"},
                    {
                        "subtype": "COMPROMISE_AND_RELEASE_STANDARD",
                        "documentDate": "2026-01-01",
                    },
                    {"subtype": MONEY_TD_SUBTYPE, "documentDate": "2026-01-01"},
                ]
            )
        ) == 2

        # The right subtypes, dated before the events they would report, are
        # still refused — this is the half of the rule the first fix lacked.
        assert len(
            problems(
                [
                    {"subtype": MONEY_WAGE_SUBTYPE, "documentDate": "2021-01-01"},
                    {
                        "subtype": "ORDER_APPROVING_SETTLEMENT",
                        "documentDate": "2024-12-31",
                    },
                    {"subtype": "BENEFIT_PAYMENT_LEDGER", "documentDate": "2025-02-04"},
                ]
            )
        ) == 2

        # A document with no date of its own vouches for nothing. The wage
        # statement rides along because the AWW rule returns before this one,
        # and a probe that stops at an earlier rule is not testing this one.
        assert (
            len(
                problems(
                    [
                        {"subtype": MONEY_WAGE_SUBTYPE, "documentDate": "2021-01-01"},
                        {"subtype": "ORDER_APPROVING_SETTLEMENT"},
                        {"subtype": "BENEFIT_PAYMENT_LEDGER"},
                    ]
                )
            )
            == 2
        )

        # And the control: the right subtypes, dated on the events themselves.
        assert not problems(
            [
                {"subtype": MONEY_WAGE_SUBTYPE, "documentDate": "2021-01-01"},
                {"subtype": "ORDER_APPROVING_SETTLEMENT", "documentDate": "2025-01-06"},
                {"subtype": "BENEFIT_PAYMENT_LEDGER", "documentDate": "2025-02-05"},
            ]
        )

    def test_funding_before_approval_is_refused(self, tmp_path: Path) -> None:
        directory, manifest = self._generated(tmp_path)
        settlement = manifest["caseFacts"]["money"].get("settlement")
        assert settlement is not None, "the probe seed must settle"
        settlement["fundingDate"] = "1999-01-01"
        self._rewrite(directory, manifest)
        problems = validate_output_tree(tmp_path).problems
        assert any("before the Board approves" in problem for problem in problems), problems


def test_the_rate_derivation_takes_no_dependency_on_the_fabricated_rating() -> None:
    """ISC-169 — AJC-44 inherits a clean surface.

    ``case_facts.py`` still reaches its whole-person impairment by
    ``rng.randint(3, 24)`` and its permanent disability by multiplying that by
    1.4. Those are placeholders for a rating that never happened, and correcting
    them is a separate piece of work. Building the comp rate on top of them
    would make this layer's arithmetic depend on a number that is about to
    change — so the money module never reads either field, and this asserts it
    rather than trusting a reviewer to notice.

    Two probes, because either alone is weak. The source sweep would miss an
    indirect read through ``CaseFacts``; the behavioural sweep would miss a read
    that happens to agree across the values it tried.
    """
    import ast

    from wc_caseload_engine import money as money_module

    tree = ast.parse(Path(money_module.__file__).read_text(encoding="utf-8"))
    # Over the syntax tree, not the raw text: the module *documents* its
    # relationship to the clinical ledger in prose, and a substring sweep would
    # convict it for the docstring. What must be absent is a dependency.
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert "case_facts" not in (node.module or ""), ast.dump(node)
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "case_facts" not in alias.name, alias.name
        if isinstance(node, ast.Name):
            assert node.id not in {"CaseFacts", "derive_case_facts"}, node.id
        if isinstance(node, ast.Attribute):
            assert node.attr not in {"wpi", "pd"}, node.attr

    # Behavioural: the rating varies with eval_type (``none`` leaves wpi/pd
    # unset), and the money must not move with it.
    rates = set()
    for eval_type in ("qme", "ame", "none"):
        seed = parse_case_seed(
            _seed_body(
                {"wages": WAGES},
                lifecycle={"target_stage": "medical_legal", "eval_type": eval_type},
            )
        )
        timeline = build_timeline(seed)
        clinical = derive_case_facts(seed, timeline)
        facts = derive_money_facts(seed, timeline)
        rates.add((facts.aww, facts.wages.rate.td_weekly_rate))
        assert (clinical.wpi is None) == (eval_type == "none")
    assert len(rates) == 1, rates


def test_select_method_is_a_pure_function_of_the_wage_facts() -> None:
    """No RNG in the label. The rule has to be one a reader could reproduce."""
    seed = parse_case_seed(_seed_body({"wages": dict(WAGES, pattern="irregular")}))
    facts = derive_money_facts(seed, build_timeline(seed))
    for _ in range(5):
        assert select_method(seed.scenario.wages, facts.wages.periods) == (
            facts.wages.computation.method,
            facts.wages.computation.method_source,
            facts.wages.computation.method_reason,
        )
