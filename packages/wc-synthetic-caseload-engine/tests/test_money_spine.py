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
    compute_aww,
    compute_comp_rate,
    derive_money_facts,
    money,
    money_manifest_block,
    rate_basis_for,
    select_method,
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

    @pytest.mark.parametrize("block", ["benefits", "settlement"])
    def test_money_without_a_wage_block_is_rejected(self, block: str) -> None:
        payload = {"td_weeks": 10} if block == "benefits" else {"gross_amount": 40000}
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
        """
        reached = set()
        for method in AWW_METHODS:
            wages = dict(WAGES, method=method)
            if method == "earning_capacity":
                wages["earning_capacity_weekly"] = 1500.0
            facts = _facts({"wages": wages})
            reached.add(facts.method)
        assert reached == set(AWW_METHODS)

    def test_a_seeded_method_wins_and_is_recorded_as_authored(self) -> None:
        facts = _facts({"wages": dict(WAGES, method="concurrent_aggregate")})
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
        with pytest.raises(SeedValidationError) as caught:
            _facts({"wages": dict(WAGES, rate_basis={"td_min_weekly": 5000.0})})
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

        calls = {
            "money": lambda: money(1234.567),
            "rate_basis_for": lambda: rate_basis_for(doi),
            "select_method": lambda: select_method(wages, periods),
            "compute_aww": lambda: compute_aww(wages, periods),
            "compute_comp_rate": lambda: compute_comp_rate(money(1234.56), basis),
            "derive_money_facts": lambda: derive_money_facts(seed, timeline, "ordinary"),
            "money_manifest_block": lambda: money_manifest_block(facts),
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
                    assert repr(call()) == baseline[name], (
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

    def test_the_aggregate_divides_by_the_weeks_both_employers_cover(self) -> None:
        """Both employers' earnings over one calendar, not over one employer's weeks.

        The denominator was the *primary* employment's own weeks for every
        method, which is only right when the two histories cover the same
        calendar — documented as an assumption and checked by nothing. A
        two-week primary period paying $2,000 beside a fifty-two-week concurrent
        history paying $52,000 published `grossConsidered: 54000.00` over
        `weeksConsidered: 2.0000`: an average weekly wage of **$27,000**, capped
        to the statutory maximum and recorded as `tdBound: max`.
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
        facts = _facts({"wages": {"earnings": primary + concurrent}})
        computation = facts.wages.computation
        assert computation.method == "concurrent_aggregate"
        assert computation.gross_considered == money(54000)
        # The union of covered days: 364 concurrent days, of which the primary
        # period's 14 are a subset.
        assert computation.weeks_considered == Decimal("52.0000")
        assert computation.aww == money(
            (computation.gross_considered / computation.weeks_considered).quantize(
                Decimal("0.01")
            )
        )
        assert facts.wages.rate.td_bound == "unbounded", (
            "an aggregate over the right weeks does not reach the statutory ceiling"
        )

        # The control: where the two histories *do* align — every derived history
        # and every well-formed listed one — the union is the primary's own span
        # and the answer is unchanged.
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
        assert "primary" in str(caught.value)

        # The control: add one primary period and the aggregate is real money.
        mixed = [
            {"period_start": "2021-01-04", "period_end": "2021-01-17", "gross": 2000.0},
            *concurrent,
        ]
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
        assert benefits["latePayments"] == sum(
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
        for group in ("wage", "rate"):
            for field in GOVERNED_MONEY_FIELDS[group]:
                value = block[group][field]
                if isinstance(value, bool):
                    # Published as the caveat text the reader of paper sees.
                    continue
                needle = " ".join(str(value).replace(",", "").split())
                assert needle in normalized, (
                    f"caseFacts.money.{group}.{field} publishes {value!r}, which the "
                    "wage statement never prints — a published fact is one a document "
                    "renders, or it is a label with nothing behind it"
                )

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
                    "include_only": [MONEY_WAGE_SUBTYPE, "TD_PAYMENT_RECORD_ONGOING"],
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
                    "include_only": [MONEY_WAGE_SUBTYPE, "TD_PAYMENT_RECORD_ONGOING"],
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
            block, [{"subtype": MONEY_WAGE_SUBTYPE}], "probe-case"
        )
        assert any("payment record" in p for p in problems), problems

        # The control: add the record and the same ledger passes.
        assert not any(
            "payment record" in p
            for p in _validate_money(
                block,
                [{"subtype": MONEY_WAGE_SUBTYPE}, {"subtype": MONEY_PD_SUBTYPE}],
                "probe-case",
            )
        )

    def test_a_malformed_event_is_refused(self) -> None:
        """The ledger is the eval label. A label that is a bare string is broken, not lesser."""
        from wc_caseload_engine.manifests import _validate_money

        facts = _facts({"wages": WAGES, "benefits": {"td_weeks": 8}})
        block = {"money": money_manifest_block(facts)}
        documents = [{"subtype": MONEY_WAGE_SUBTYPE}, {"subtype": MONEY_TD_SUBTYPE}]
        assert not _validate_money(block, documents, "probe-case")

        block["money"]["benefits"]["tdPeriods"] = ["garbage"]
        block["money"]["benefits"]["tdPeriodCount"] = 1
        problems = _validate_money(block, documents, "probe-case")
        assert any("str where a record was expected" in p for p in problems), problems

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
        documents = [
            {"subtype": MONEY_WAGE_SUBTYPE},
            {"subtype": MONEY_TD_SUBTYPE},
            {"subtype": MONEY_PD_SUBTYPE},
        ]
        for array_key, word in (("tdPeriods", "temporary"), ("pdAdvances", "permanent")):
            block = {"money": money_manifest_block(facts)}
            assert not _validate_money(block, documents, "probe-case")
            events = block["money"]["benefits"][array_key]
            assert events, f"the probe needs a {array_key} record"
            events[0]["daysLate"] = events[0]["daysLate"] + 5
            problems = _validate_money(block, documents, "probe-case")
            assert any(word in p and "daysLate" in p for p in problems), (array_key, problems)

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
