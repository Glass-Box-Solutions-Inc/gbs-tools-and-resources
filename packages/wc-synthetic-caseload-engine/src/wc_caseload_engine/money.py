"""The money spine — wage facts, rate derivation, benefit ledger, settlement.

Money is the only part of a workers' compensation file where correctness is
*arithmetically* checkable. A comp rate either follows from the wage data or it
does not, and there is no register in which a wrong one reads as a judgement
call. That makes this the highest-signal surface in the corpus and, until this
module, the one entirely absent from it: the substrate's own wage statement
invents twelve pay periods with ``random.randint``, computes an average from
them, and prints a rate under a hardcoded fraction and a hardcoded ceiling that
no date of injury reaches.

Three roles, one schema — the same shape the clinical ledger has. Every object
here is simultaneously a **generation spec** (what the engine renders), an
**extraction target** (what the analyzer must recover from the document) and an
**eval label** (what the analyzer is scored against). Fields are therefore named
for what a reader must recover from paper, not for what is convenient to render.

Four guarantees hold this up.

**The gate is the wage block.** :func:`derive_money_facts` returns ``None`` for
any seed without ``scenario.wages``, and every consumer — planner, renderer,
manifest — short-circuits on that ``None``. A seed that says nothing about money
therefore takes the exact code path it took before this module existed, renders
byte for byte as it did, and publishes nothing. That is the anti-criterion, and
it is a code path rather than a promise.

**Every draw is namespaced.** Money derivation draws only from
``derive_seed(rng_seed, "money:...")`` — never the global stream the substrate
templates consume, never a ``facts:`` salt the clinical ledger already uses, and
never the wall clock. Same seed and same version give byte-identical money.

**Arithmetic is decimal.** Currency is :class:`~decimal.Decimal` throughout,
quantized to cents at exactly the points a payroll system would round, so the
numbers on the statement add up to the total printed under them. Seeds state
money as ordinary YAML numbers and are converted here through ``str``, because a
seed is a document a human writes.

**No number here is verified law.** Every fraction, ceiling and floor is
table-supplied and marked counsel-unconfirmed; see :data:`UNCONFIRMED_RATE_TABLE`
and :func:`rate_basis_for`, which is the seam a dated rate authority (KB-167,
different repository) plugs into. This module takes no dependency on that work
and asserts nothing about the law in the meantime.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import datetime as dt
import random
from contextlib import contextmanager
from decimal import ROUND_HALF_UP, Context, Decimal, localcontext
from typing import Any, Literal

import structlog
from pydantic import BaseModel, ConfigDict, Field

from wc_caseload_engine.seeds import (
    PAY_PERIODS_PER_YEAR,
    CaseSeed,
    WageScenario,
    derive_seed,
)

log = structlog.get_logger(__name__)

CENTS = Decimal("0.01")
"""Quantum every currency figure is rounded to."""

ZERO = Decimal("0.00")

_ARITHMETIC_CONTEXT = Context(prec=28, rounding=ROUND_HALF_UP)
"""Precision every inexact money operation runs under.

:mod:`decimal`'s context is process- *and thread-local mutable state*: any
caller — this package is a library — can set ``getcontext().prec`` and every
division and square root after it answers differently. That is a determinism
leak of exactly the shape this engine has already been bitten by twice
(``PYTHONHASHSEED``, the substrate's ``date.today()``): correct on the machine
that wrote it, wrong somewhere else, and invisible to a same-process double run.

Pinned locally rather than globally, because setting the global context would
make this module the shared mutable state instead of curing it.
"""


@contextmanager
def _exact() -> Any:
    """Run a block under :data:`_ARITHMETIC_CONTEXT`."""
    with localcontext(_ARITHMETIC_CONTEXT):
        yield


def money(value: Any) -> Decimal:
    """Coerce *value* to a cents-quantized :class:`~decimal.Decimal`.

    Routed through ``str`` rather than constructed from the float directly.
    ``Decimal(1200.10)`` is the binary expansion and prints eighteen digits of
    noise; ``Decimal("1200.10")`` is the number the seed author wrote. Since a
    seed states money as an ordinary YAML number, ``str`` is the only conversion
    that preserves what they meant.
    """
    with _exact():
        return Decimal(str(value)).quantize(CENTS, rounding=ROUND_HALF_UP)


def _dollars(value: Decimal) -> str:
    """A currency figure as the manifest publishes it: an exact decimal string.

    Strings rather than floats, and this is not fussiness. A manifest is the
    eval label; a label that has been through binary floating point is a label
    that can disagree with the document it grades by a cent, and a cent is a
    real difference in an arithmetic check.
    """
    with _exact():
        return f"{value.quantize(CENTS, rounding=ROUND_HALF_UP):f}"


# ---------------------------------------------------------------------------
# Statutory bindings — every one of them unconfirmed
# ---------------------------------------------------------------------------


class RateBasis(BaseModel):
    """The statutory parameters a comp rate is computed under, for one vintage.

    Keyed to the date of injury, because that is the axis on which these numbers
    actually move: a caseload spans many years and the current figures are the
    wrong answer for most files in it. A rate table with no date on it is not a
    simplification, it is a different (and wrong) table for every case but the
    newest.

    ``counsel_confirmed`` is the field that keeps this module honest. Nothing
    the engine ships sets it true. It is published in the manifest so that no
    downstream consumer can mistake a placeholder binding for a verified one,
    and a seed that carries a genuinely verified authority says so itself.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    label: str
    """Human name of the vintage, e.g. ``"doi-2023"``."""

    effective_from: dt.date
    effective_to: dt.date | None = None

    td_fraction: Decimal
    """Fraction of AWW that becomes the temporary-disability weekly rate."""

    td_max_weekly: Decimal
    td_min_weekly: Decimal
    pd_fraction: Decimal
    pd_max_weekly: Decimal
    pd_min_weekly: Decimal

    authority: str
    """The citation these numbers are said to come from — prose, not a promise."""

    counsel_confirmed: bool = False
    """Whether counsel has verified this binding. False for everything shipped."""

    source: Literal["engine_default_table", "seed"] = "engine_default_table"
    """Where the numbers came from, so a reader can tell authored from defaulted."""

    def covers(self, when: dt.date) -> bool:
        if when < self.effective_from:
            return False
        return self.effective_to is None or when <= self.effective_to


UNCONFIRMED_RATE_TABLE: tuple[RateBasis, ...] = (
    RateBasis(
        label="doi-pre-2014",
        effective_from=dt.date(1900, 1, 1),
        effective_to=dt.date(2013, 12, 31),
        td_fraction=Decimal("0.6667"),
        td_max_weekly=money(1066.72),
        td_min_weekly=money(160.00),
        pd_fraction=Decimal("0.6667"),
        pd_max_weekly=money(270.00),
        pd_min_weekly=money(160.00),
        authority=(
            "Temporary and permanent disability indemnity rates for dates of injury "
            "before 2014. COUNSEL-UNCONFIRMED placeholder — the figures, the fraction "
            "and the bracket boundaries are all unverified."
        ),
    ),
    RateBasis(
        label="doi-2014-2018",
        effective_from=dt.date(2014, 1, 1),
        effective_to=dt.date(2018, 12, 31),
        td_fraction=Decimal("0.6667"),
        td_max_weekly=money(1215.27),
        td_min_weekly=money(182.29),
        pd_fraction=Decimal("0.6667"),
        pd_max_weekly=money(290.00),
        pd_min_weekly=money(160.00),
        authority=(
            "Temporary and permanent disability indemnity rates for dates of injury "
            "2014-2018. COUNSEL-UNCONFIRMED placeholder."
        ),
    ),
    RateBasis(
        label="doi-2019-2022",
        effective_from=dt.date(2019, 1, 1),
        effective_to=dt.date(2022, 12, 31),
        td_fraction=Decimal("0.6667"),
        td_max_weekly=money(1539.71),
        td_min_weekly=money(230.95),
        pd_fraction=Decimal("0.6667"),
        pd_max_weekly=money(290.00),
        pd_min_weekly=money(160.00),
        authority=(
            "Temporary and permanent disability indemnity rates for dates of injury "
            "2019-2022. COUNSEL-UNCONFIRMED placeholder."
        ),
    ),
    RateBasis(
        label="doi-2023-onward",
        effective_from=dt.date(2023, 1, 1),
        effective_to=None,
        td_fraction=Decimal("0.6667"),
        td_max_weekly=money(1619.15),
        td_min_weekly=money(242.86),
        pd_fraction=Decimal("0.6667"),
        pd_max_weekly=money(290.00),
        pd_min_weekly=money(160.00),
        authority=(
            "Temporary and permanent disability indemnity rates for dates of injury "
            "2023 onward. COUNSEL-UNCONFIRMED placeholder."
        ),
    ),
)
"""Engine-default rate vintages. **Every row is unverified.**

Shipped so that a seed need not restate the law to render a coherent document,
and named ``UNCONFIRMED_`` so that nobody reaches for it believing otherwise.
Three things follow from that name and are enforced by tests:

1. no row may set ``counsel_confirmed``;
2. every row's ``authority`` says so in its own text;
3. the manifest publishes the flag, so a consumer sees the caveat without
   reading this file.

The date brackets are themselves unverified. A vintage boundary is a legal
question — several provisions changed materially and the change is keyed to the
date of injury — and getting the boundary wrong is as consequential as getting
the number wrong. :func:`rate_basis_for` is the seam where a dated rate
authority (KB-167) replaces the whole table; nothing else in this package reads
it directly.
"""


def rate_basis_for(doi: dt.date) -> RateBasis:
    """The rate vintage covering *doi*. **The seam.**

    This function is the single point at which the engine asks "what are the
    statutory parameters for this date of injury", and the only reader of
    :data:`UNCONFIRMED_RATE_TABLE`. A verified dated authority replaces it by
    replacing this function's body — the caller passes a date and receives a
    :class:`RateBasis`, which is the whole contract.

    Deliberately no network, no import of an authority package, and no
    configuration hook: the seam is a function signature, so this ticket takes
    no dependency on work running in another repository, and that work needs no
    knowledge of this one beyond the shape it returns.

    Falls back to the earliest vintage for a date before the table opens, rather
    than raising. A synthetic corpus should not be un-generatable because a seed
    reached back further than the placeholder table does.
    """
    for basis in UNCONFIRMED_RATE_TABLE:
        if basis.covers(doi):
            return basis
    return UNCONFIRMED_RATE_TABLE[0]


def _apply_rate_basis_override(basis: RateBasis, seed: CaseSeed) -> RateBasis:
    """Fold a seed's ``rate_basis`` block over the table's answer.

    Field by field, so a seed that confirms one number does not have to restate
    the other five. ``source`` flips to ``seed`` when anything was overridden,
    because the point of recording the source is telling an authored binding
    from a defaulted one — and a partially authored one is authored.
    """
    wages = seed.scenario.wages
    override = wages.rate_basis if wages is not None else None
    if override is None:
        return basis

    changes: dict[str, Any] = {"source": "seed"}
    for name in (
        "td_fraction",
        "td_max_weekly",
        "td_min_weekly",
        "pd_fraction",
        "pd_max_weekly",
        "pd_min_weekly",
    ):
        value = getattr(override, name)
        if value is not None:
            changes[name] = money(value) if name.endswith("_weekly") else Decimal(str(value))
    if override.authority is not None:
        changes["authority"] = override.authority
    changes["counsel_confirmed"] = override.counsel_confirmed
    return basis.model_copy(update=changes)


# ---------------------------------------------------------------------------
# Wage facts
# ---------------------------------------------------------------------------


class EarningsPeriod(BaseModel):
    """One pay period as the wage statement prints it.

    The unit an analyzer extracts. Everything the average weekly wage is
    computed from is on this record, which is what makes the average
    *derivable* from the document rather than merely asserted beside it.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    period_start: dt.date
    period_end: dt.date
    weeks: Decimal
    """Weeks this period covers — the denominator's contribution."""

    regular_gross: Decimal
    overtime_gross: Decimal
    concurrent: bool = False
    """True when this period is a second, concurrent employer's payroll."""

    @property
    def gross(self) -> Decimal:
        """Total gross for the period. Overtime included, as payroll prints it."""
        with _exact():
            return (self.regular_gross + self.overtime_gross).quantize(
                CENTS, rounding=ROUND_HALF_UP
            )


class InKindWage(BaseModel):
    """Non-cash wages at their weekly value."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: str
    weekly_value: Decimal


class AwwComputation(BaseModel):
    """How the average weekly wage was reached, and by which named method.

    Carries its own inputs rather than only its result. The acceptance test for
    this whole layer is that a reader holding the wage statement can reproduce
    the number, so every operand is recorded: the periods considered, the weeks
    they cover, the gross over them, and whatever was added on top.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    method: str
    """The named method. Ground truth — the label the analyzer is scored against."""

    method_source: Literal["seed", "derived"]
    """Whether the seed named the method or the engine selected it."""

    method_reason: str
    """Why this method and not another — in words, for the document to print."""

    periods_considered: int
    weeks_considered: Decimal
    gross_considered: Decimal
    in_kind_weekly: Decimal
    aww: Decimal
    """The result. Cents-quantized, and the figure that reaches ``CaseFacts``."""


class CompRate(BaseModel):
    """The weekly indemnity rates, under a named method and a dated basis.

    Both bounds are recorded as *outcomes* (``td_bound``, ``pd_bound``) rather
    than left for a reader to re-derive. Whether a rate was capped is the single
    most consequential fact about it — a capped rate is the same number for every
    high earner in the corpus, so an analyzer that recovers the number without
    recovering the cap has learnt nothing about the wage behind it.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    aww: Decimal
    td_weekly_rate: Decimal
    td_bound: Literal["max", "min", "unbounded"]
    pd_weekly_rate: Decimal
    pd_bound: Literal["max", "min", "unbounded"]
    basis: RateBasis


def _bounded(
    raw: Decimal, floor: Decimal, ceiling: Decimal
) -> tuple[Decimal, Literal["max", "min", "unbounded"]]:
    """Clamp *raw* into ``[floor, ceiling]`` and say which bound bound it.

    Ceiling before floor. When a (mis-stated) basis inverts the two, the ceiling
    is the binding the statute is written around and the floor is the relief, so
    letting the floor win would produce a rate above the maximum — a number no
    file can contain. The seed validator rejects an inverted pair outright; this
    ordering is the belt behind that brace.
    """
    if raw > ceiling:
        return ceiling, "max"
    if raw < floor:
        return floor, "min"
    return raw, "unbounded"


class WageFacts(BaseModel):
    """The earnings history and everything computed from it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    periods: tuple[EarningsPeriod, ...] = ()
    in_kind: tuple[InKindWage, ...] = ()
    employment_start: dt.date | None = None
    concurrent_employment: bool = False
    pattern: str = "regular"
    computation: AwwComputation
    rate: CompRate

    @property
    def aww(self) -> Decimal:
        return self.computation.aww

    @property
    def primary_periods(self) -> tuple[EarningsPeriod, ...]:
        return tuple(p for p in self.periods if not p.concurrent)

    @property
    def concurrent_periods(self) -> tuple[EarningsPeriod, ...]:
        return tuple(p for p in self.periods if p.concurrent)


# ---------------------------------------------------------------------------
# Benefit ledger
# ---------------------------------------------------------------------------


class TdPeriod(BaseModel):
    """One stretch of temporary disability, and when it was actually paid."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    start: dt.date
    end: dt.date
    weeks: Decimal
    weekly_rate: Decimal
    amount: Decimal
    date_paid: dt.date | None = None
    """``None`` means the period was never paid — an interruption, not a delay."""

    days_late: int = Field(default=0, ge=0)
    """Days past the period's own due date. Zero for a timely payment."""

    @property
    def late(self) -> bool:
        return self.days_late > 0


class PdAdvance(BaseModel):
    """One permanent-disability advance paid before any award."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    date_paid: dt.date
    amount: Decimal
    weekly_rate: Decimal
    weeks: Decimal
    days_late: int = Field(default=0, ge=0)

    @property
    def late(self) -> bool:
        return self.days_late > 0


class BenefitGap(BaseModel):
    """A deliberate hole in the benefit series.

    Recorded as a fact rather than left implicit in the dates. A gap that a
    reader has to notice by subtracting two dates is a gap the eval cannot
    score, and this whole layer exists so that exposure is *known*.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    start: dt.date
    end: dt.date
    days: int = Field(ge=1)


class BenefitLedger(BaseModel):
    """Everything paid on the claim, with its interruptions and its lateness."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    td_periods: tuple[TdPeriod, ...] = ()
    pd_advances: tuple[PdAdvance, ...] = ()
    gaps: tuple[BenefitGap, ...] = ()

    @property
    def td_total(self) -> Decimal:
        with _exact():
            return sum((p.amount for p in self.td_periods), ZERO).quantize(
                CENTS, rounding=ROUND_HALF_UP
            )

    @property
    def pd_total(self) -> Decimal:
        with _exact():
            return sum((a.amount for a in self.pd_advances), ZERO).quantize(
                CENTS, rounding=ROUND_HALF_UP
            )

    @property
    def late_payment_count(self) -> int:
        return sum(1 for p in self.td_periods if p.late) + sum(
            1 for a in self.pd_advances if a.late
        )

    @property
    def max_days_late(self) -> int:
        everything = [p.days_late for p in self.td_periods] + [
            a.days_late for a in self.pd_advances
        ]
        return max(everything, default=0)

    @property
    def unpaid_period_count(self) -> int:
        return sum(1 for p in self.td_periods if p.date_paid is None)


# ---------------------------------------------------------------------------
# Settlement
# ---------------------------------------------------------------------------


class SettlementFact(BaseModel):
    """How the money ended: what kind, how much, approved when, funded when.

    ``approval_date`` and ``funding_date`` are separate fields, and that
    separation is the point of modelling this object in Wave 1 rather than in
    either lens ticket. They are separate events — a Board approves, and later
    somebody funds — and the interval between them is the whole substance of a
    late-funding argument. A single ``settlement_date`` would delete that
    argument from the corpus while looking like a simplification.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["c_and_r", "stipulations"]
    gross_amount: Decimal
    approval_date: dt.date | None = None
    funding_date: dt.date | None = None

    @property
    def funding_lag_days(self) -> int | None:
        """Days from approval to funding, or ``None`` while either is unknown."""
        if self.approval_date is None or self.funding_date is None:
            return None
        return (self.funding_date - self.approval_date).days


class MoneyFacts(BaseModel):
    """The money spine of one case, decided once.

    Derived at plan time beside :class:`~wc_caseload_engine.case_facts.CaseFacts`
    and carried on the plan, so the planner, the renderer and the manifest read
    one answer rather than three. Present only for a seed that asked for it.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    wages: WageFacts
    benefits: BenefitLedger = Field(default_factory=BenefitLedger)
    settlement: SettlementFact | None = None

    @property
    def aww(self) -> Decimal:
        return self.wages.aww

    @property
    def method(self) -> str:
        return self.wages.computation.method

    @property
    def td_weekly_rate(self) -> Decimal:
        return self.wages.rate.td_weekly_rate


# ---------------------------------------------------------------------------
# Derivation
# ---------------------------------------------------------------------------


def _rng(seed: CaseSeed, salt: str) -> random.Random:
    """A private stream under the ``money:`` namespace.

    A namespace of its own, not a ``facts:`` salt. The clinical ledger's streams
    are already consumed by documents that render today; borrowing one would move
    their bytes the moment a seed grew a wage block, turning a money knob into a
    silent change to a diagnostic report.
    """
    return random.Random(derive_seed(seed.rng_seed, f"money:{salt}"))


#: Weekly wage band a derived history varies around when the seed states none.
#:
#: Wide on purpose: a corpus whose earners all sit under the indemnity ceiling
#: never poses the capped-rate case, and one whose earners all sit above it never
#: poses the uncapped one. Both are ordinary files and the corpus needs both.
_DERIVED_WEEKLY_WAGE_RANGE: tuple[int, int] = (520, 2600)

#: How far a period's gross may stray from the base, per earnings pattern.
#:
#: ``irregular`` reaches zero — a week with no work at all is exactly what makes
#: method selection a live question rather than a formality — and reaches well
#: above the base, because irregular means irregular in both directions.
_PATTERN_SPREAD: dict[str, tuple[float, float]] = {
    "regular": (0.98, 1.02),
    "irregular": (0.00, 1.80),
    "seasonal": (0.35, 1.45),
}

#: Coefficient of variation above which a derived history counts as irregular.
#:
#: **An engine heuristic, not a legal test.** It decides which *label* this
#: package attaches when a seed does not name a method, so that the label is
#: produced by a stated rule rather than by a draw. A seed that disagrees names
#: its method and the seed wins.
IRREGULARITY_THRESHOLD: Decimal = Decimal("0.25")

#: Weeks of employment below which the short-history method is selected.
#:
#: Also an engine heuristic. Named and testable rather than buried in a
#: comparison, because the selection rule is itself ground truth: an analyzer is
#: scored on recovering the label, so the label has to be produced by something
#: a reader could in principle reproduce.
SHORT_HISTORY_WEEKS: Decimal = Decimal("26")


def _period_bounds(
    wages: WageScenario, doi: dt.date
) -> tuple[list[tuple[dt.date, dt.date, Decimal]], dt.date]:
    """Pay-period windows ending at the injury, newest last, with their weeks.

    Walks backwards from the day before the injury so no period straddles it,
    then reverses — a wage statement reads oldest first, and the analyzer reads
    it in that order.
    """
    per_year = PAY_PERIODS_PER_YEAR[wages.pay_frequency]
    days = round(365 / per_year)
    weeks = (Decimal(days) / Decimal(7)).quantize(Decimal("0.0001"))
    count = max(1, round(wages.lookback_weeks * per_year / 52))

    floor = wages.employment_start
    windows: list[tuple[dt.date, dt.date, Decimal]] = []
    cursor = doi - dt.timedelta(days=1)
    for _ in range(count):
        start = cursor - dt.timedelta(days=days - 1)
        if floor is not None and start < floor:
            # The employment had not begun. A partial first period would put a
            # fraction of a pay cycle on the statement, which no payroll system
            # prints; stopping is what makes ``employment_start`` produce a
            # genuinely short history rather than a diluted full one.
            break
        windows.append((start, cursor, weeks))
        cursor = start - dt.timedelta(days=1)
    windows.reverse()
    return windows, doi


def _derive_periods(
    seed: CaseSeed, wages: WageScenario, doi: dt.date
) -> tuple[EarningsPeriod, ...]:
    """Build the earnings history: the seed's own, or one drawn to its shape."""
    if wages.earnings:
        return tuple(
            EarningsPeriod(
                period_start=entry.period_start,
                period_end=entry.period_end,
                weeks=(
                    Decimal((entry.period_end - entry.period_start).days + 1) / Decimal(7)
                ).quantize(Decimal("0.0001")),
                regular_gross=money(entry.gross - entry.overtime),
                overtime_gross=money(entry.overtime),
                concurrent=entry.concurrent,
            )
            for entry in wages.earnings
        )

    windows, _ = _period_bounds(wages, doi)
    rng = _rng(seed, "earnings")
    per_year = PAY_PERIODS_PER_YEAR[wages.pay_frequency]
    base_weekly = money(
        wages.base_weekly_wage
        if wages.base_weekly_wage is not None
        else rng.randint(*_DERIVED_WEEKLY_WAGE_RANGE)
    )
    low, high = _PATTERN_SPREAD[wages.pattern]

    periods: list[EarningsPeriod] = []
    for index, (start, end, weeks) in enumerate(windows):
        if wages.pattern == "seasonal":
            # A season is a position in the year, not a coin. Derived from the
            # period's index so the same history always has its peak in the same
            # place — a "seasonal" pattern whose peak moved with the seed would
            # be indistinguishable from an irregular one.
            phase = (index % per_year) / per_year
            swing = Decimal(str(low)) + (Decimal(str(high)) - Decimal(str(low))) * Decimal(
                str(round(0.5 - 0.5 * _cosine(phase), 6))
            )
            factor = swing
        else:
            factor = Decimal(str(round(rng.uniform(low, high), 6)))
        gross = money(base_weekly * weeks * factor)
        overtime = money(gross * Decimal(str(wages.overtime_share)))
        periods.append(
            EarningsPeriod(
                period_start=start,
                period_end=end,
                weeks=weeks,
                regular_gross=money(gross - overtime),
                overtime_gross=overtime,
            )
        )

    if wages.concurrent_employment:
        concurrent_weekly = money(
            wages.concurrent_weekly_wage
            if wages.concurrent_weekly_wage is not None
            else rng.randint(_DERIVED_WEEKLY_WAGE_RANGE[0] // 2, _DERIVED_WEEKLY_WAGE_RANGE[0])
        )
        for start, end, weeks in windows:
            gross = money(concurrent_weekly * weeks)
            periods.append(
                EarningsPeriod(
                    period_start=start,
                    period_end=end,
                    weeks=weeks,
                    regular_gross=gross,
                    overtime_gross=ZERO,
                    concurrent=True,
                )
            )

    return tuple(periods)


def _cosine(phase: float) -> float:
    """``cos(2*pi*phase)`` without importing :mod:`math` for one call.

    A four-term Taylor expansion would drift; the real cosine is exact enough and
    deterministic, so this is simply :func:`math.cos` wrapped to keep the import
    local to the one place a seasonal history needs it.
    """
    import math

    return math.cos(2 * math.pi * phase)


def _coefficient_of_variation(periods: tuple[EarningsPeriod, ...]) -> Decimal:
    """Spread of per-week earnings relative to their mean, as a Decimal.

    Zero for a history with fewer than two periods or no earnings at all — a
    single period has no spread, and calling that "regular" is the honest read.
    """
    with _exact():
        weekly = [(p.gross / p.weeks) for p in periods if p.weeks > 0]
        if len(weekly) < 2:
            return Decimal("0")
        mean = sum(weekly, ZERO) / Decimal(len(weekly))
        if mean == 0:
            return Decimal("0")
        variance = sum(((value - mean) ** 2 for value in weekly), ZERO) / Decimal(len(weekly))
        return (variance.sqrt() / mean).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def select_method(
    wages: WageScenario, periods: tuple[EarningsPeriod, ...]
) -> tuple[str, Literal["seed", "derived"], str]:
    """Choose the named method, and say why. **The label the analyzer is scored on.**

    Returns ``(method, source, reason)``. A seed that names a method wins
    outright and the reason records that it was authored, because "the author
    said so" is a complete and checkable explanation.

    The derived rule is ordered, and the order is itself the ground truth:

    1. **concurrent employment** — earnings from more than one employer are
       aggregated before anything else is asked, because the question "is this
       history irregular" is meaningless over the wrong set of earnings;
    2. **short history** — an employment shorter than
       :data:`SHORT_HISTORY_WEEKS` cannot be averaged over the lookback without
       diluting it with weeks the applicant was not employed;
    3. **irregular earnings** — a coefficient of variation above
       :data:`IRREGULARITY_THRESHOLD`;
    4. otherwise **actual weekly earnings**.

    ``earning_capacity`` is never derived. It is the catch-all a human argues
    for when none of the arithmetic fits, and an engine that reached for it
    unprompted would be asserting a legal conclusion rather than computing.
    """
    if wages.method is not None:
        return wages.method, "seed", f"method stated in the seed as {wages.method!r}"

    if wages.concurrent_employment or any(p.concurrent for p in periods):
        return (
            "concurrent_aggregate",
            "derived",
            "earnings from concurrent employments are aggregated",
        )

    weeks = sum((p.weeks for p in periods if not p.concurrent), Decimal("0"))
    if weeks < SHORT_HISTORY_WEEKS:
        return (
            "short_history_projection",
            "derived",
            f"employment history of {weeks.normalize()} week(s) is shorter than the "
            f"{SHORT_HISTORY_WEEKS.normalize()}-week threshold",
        )

    variation = _coefficient_of_variation(tuple(p for p in periods if not p.concurrent))
    if variation > IRREGULARITY_THRESHOLD:
        return (
            "irregular_earnings_average",
            "derived",
            f"weekly earnings vary with a coefficient of {variation}, above the "
            f"{IRREGULARITY_THRESHOLD} irregularity threshold",
        )
    return (
        "actual_weekly_earnings",
        "derived",
        f"weekly earnings are steady (coefficient of variation {variation})",
    )


def compute_aww(
    wages: WageScenario, periods: tuple[EarningsPeriod, ...]
) -> AwwComputation:
    """Average weekly wage under the selected method, with every operand kept.

    Each method differs in *which earnings it counts and over how many weeks*,
    which is the only axis on which they can differ arithmetically:

    * ``actual_weekly_earnings`` — the primary employer's gross over the weeks
      the periods cover.
    * ``irregular_earnings_average`` — the same arithmetic over the same
      periods. Identical here **on purpose**: the two methods differ in the
      argument for using them, not in the sum, and inventing a difference so the
      numbers look distinct would make the label unrecoverable from the paper
      for the wrong reason. The distinction the corpus carries is the recorded
      label plus the spread of the underlying periods.
    * ``short_history_projection`` — gross over the weeks actually worked, so a
      history truncated by a hire date is not diluted by weeks before it.
    * ``concurrent_aggregate`` — every employer's gross over the weeks the
      *primary* employment covers, since concurrent periods overlap it rather
      than extending it.
    * ``earning_capacity`` — the stated figure. No arithmetic; the seed
      validator has already required the number.
    """
    method, source, reason = select_method(wages, periods)
    in_kind_weekly = sum((money(item.weekly_value) for item in wages.in_kind), ZERO)

    primary = tuple(p for p in periods if not p.concurrent)
    considered = periods if method == "concurrent_aggregate" else primary
    weeks = sum((p.weeks for p in primary), Decimal("0"))
    gross = sum((p.gross for p in considered), ZERO)

    with _exact():
        if method == "earning_capacity":
            base = money(wages.earning_capacity_weekly or 0)
        elif weeks <= 0 or not considered:
            # No history at all. Say zero rather than divide: an unearned number
            # here would be the asserted average this whole layer exists to remove.
            base = ZERO
        else:
            base = (gross / weeks).quantize(CENTS, rounding=ROUND_HALF_UP)

    return AwwComputation(
        method=method,
        method_source=source,
        method_reason=reason,
        periods_considered=len(considered),
        weeks_considered=weeks.quantize(Decimal("0.0001")),
        gross_considered=money(gross),
        in_kind_weekly=money(in_kind_weekly),
        aww=money(base + in_kind_weekly),
    )


def compute_comp_rate(aww: Decimal, basis: RateBasis) -> CompRate:
    """AWW to weekly indemnity rates under *basis*, recording which bound bound."""
    with _exact():
        td_raw = (aww * basis.td_fraction).quantize(CENTS, rounding=ROUND_HALF_UP)
        pd_raw = (aww * basis.pd_fraction).quantize(CENTS, rounding=ROUND_HALF_UP)
    td_rate, td_bound = _bounded(td_raw, basis.td_min_weekly, basis.td_max_weekly)
    pd_rate, pd_bound = _bounded(pd_raw, basis.pd_min_weekly, basis.pd_max_weekly)
    return CompRate(
        aww=aww,
        td_weekly_rate=td_rate,
        td_bound=td_bound,
        pd_weekly_rate=pd_rate,
        pd_bound=pd_bound,
        basis=basis,
    )


#: How much lateness each diligence band produces when the seed states none.
#:
#: ``(late payment count, worst lateness in days)``. Deliberately parallel to
#: :data:`~wc_caseload_engine.case_facts.DILIGENCE_WINDOW_FRACTIONS`, which does
#: the same job for benefit *notices*: one persona, driving both the paperwork
#: and the payments, so a file cannot describe an attentive administrator who
#: never paid anybody.
DILIGENCE_LATENESS: dict[str, tuple[int, int]] = {
    "attentive": (0, 0),
    "ordinary": (1, 9),
    "negligent": (3, 62),
}

#: Days after approval a settlement is funded, per diligence band.
DILIGENCE_FUNDING_DAYS: dict[str, int] = {
    "attentive": 14,
    "ordinary": 30,
    "negligent": 96,
}

#: Days after a temporary-disability period ends by which payment is due.
#:
#: **Counsel-unconfirmed**, like everything else here with a number attached. It
#: is the yardstick ``days_late`` is measured against, so it is named and
#: published rather than folded into an arithmetic expression: a lateness figure
#: whose baseline is invisible is not checkable.
TD_PAYMENT_DUE_DAYS: int = 14


def _derive_benefits(
    seed: CaseSeed,
    wages_facts: WageFacts,
    timeline: Any,
    diligence: str,
) -> BenefitLedger:
    """The payment history: what was paid, when, how late, and what was missed."""
    scenario = seed.scenario.benefits
    onset = getattr(timeline, "injury_date", None) or seed.injury.onset_date
    horizon = (
        getattr(timeline, "resolution_date", None)
        or getattr(timeline, "application_filed_date", None)
        or onset
    )
    rng = _rng(seed, "benefits")

    available_weeks = max(0, (horizon - onset).days // 7)
    stated_weeks = scenario.td_weeks if scenario is not None else None
    if stated_weeks is None:
        # Two thirds of the runway, capped, so a long file does not pay
        # temporary disability for its entire length. Drawn on the money stream
        # rather than fixed, because a corpus of identically-long TD runs is a
        # corpus with one TD fact in it.
        td_weeks = min(available_weeks, rng.randint(6, 52)) if available_weeks else 0
    else:
        td_weeks = min(stated_weeks, available_weeks) if available_weeks else 0

    late_count, worst_late = DILIGENCE_LATENESS[diligence]
    if scenario is not None and scenario.late_payments is not None:
        late_count = scenario.late_payments
    if scenario is not None and scenario.max_days_late is not None:
        worst_late = scenario.max_days_late
    elif late_count > 0 and worst_late == 0:
        # A seed asked for lateness on an attentive administrator. Honour the
        # count — an explicit control wins, loudly, per ISC-29 — and give it the
        # smallest lateness that is still lateness rather than silently zeroing.
        worst_late = 1

    gap_days = scenario.td_gap_days if scenario is not None else None
    if gap_days is None:
        gap_days = 0

    rate = wages_facts.rate.td_weekly_rate
    periods: list[TdPeriod] = []
    gaps: list[BenefitGap] = []

    # Paid in four-week blocks, which is how indemnity is actually issued and
    # what gives a gap something to sit between.
    block_weeks = 4
    cursor = onset + dt.timedelta(days=3)
    remaining = td_weeks
    block_index = 0
    gap_after_block = 1 if gap_days else -1

    while remaining > 0:
        weeks = min(block_weeks, remaining)
        start = cursor
        end = start + dt.timedelta(days=weeks * 7 - 1)
        due = end + dt.timedelta(days=TD_PAYMENT_DUE_DAYS)
        late = worst_late if block_index < late_count else 0
        paid = due + dt.timedelta(days=late)
        periods.append(
            TdPeriod(
                start=start,
                end=end,
                weeks=Decimal(weeks),
                weekly_rate=rate,
                amount=money(rate * Decimal(weeks)),
                date_paid=paid,
                days_late=late,
            )
        )
        remaining -= weeks
        block_index += 1
        cursor = end + dt.timedelta(days=1)
        if block_index == gap_after_block and gap_days and remaining > 0:
            gap_start = cursor
            cursor = cursor + dt.timedelta(days=gap_days)
            gaps.append(
                BenefitGap(start=gap_start, end=cursor - dt.timedelta(days=1), days=gap_days)
            )

    advances_wanted = scenario.pd_advances if scenario is not None else None
    if advances_wanted is None:
        advances_wanted = 2 if seed.lifecycle.resolution.type != "pending" else 0

    pd_rate = wages_facts.rate.pd_weekly_rate
    advances: list[PdAdvance] = []
    advance_cursor = (periods[-1].end if periods else onset) + dt.timedelta(days=15)
    for index in range(advances_wanted):
        if advance_cursor > horizon:
            # An advance past the file's own horizon is not a late advance, it
            # is one this case never reached. Same rule the clinical ledger
            # applies to a benefit notice, and for the same reason: clamping
            # would manufacture a payment out of a short runway.
            break
        late = worst_late if index < max(0, late_count - len(periods)) else 0
        advances.append(
            PdAdvance(
                date_paid=advance_cursor + dt.timedelta(days=late),
                amount=money(pd_rate * Decimal(4)),
                weekly_rate=pd_rate,
                weeks=Decimal(4),
                days_late=late,
            )
        )
        advance_cursor = advance_cursor + dt.timedelta(days=45)

    return BenefitLedger(
        td_periods=tuple(periods), pd_advances=tuple(advances), gaps=tuple(gaps)
    )


def _derive_settlement(
    seed: CaseSeed,
    wages_facts: WageFacts,
    benefits: BenefitLedger,
    timeline: Any,
    diligence: str,
) -> SettlementFact | None:
    """The settlement object, when this case settled.

    ``None`` for anything that did not — a trial award and a take-nothing are
    endings, but neither is a settlement anybody approves and funds, and giving
    them a settlement object would put an approval date in the ledger for an
    order the file does not contain.
    """
    resolution = seed.lifecycle.resolution.type
    if resolution not in ("c_and_r", "stipulations"):
        return None

    scenario = seed.scenario.settlement
    approval = getattr(timeline, "award_date", None) or getattr(
        timeline, "resolution_date", None
    )
    if scenario is not None and scenario.approval_date is not None:
        approval = scenario.approval_date

    if scenario is not None and scenario.gross_amount is not None:
        gross = money(scenario.gross_amount)
    else:
        # Anchored to the file's own money rather than drawn free: a settlement
        # is negotiated against the indemnity exposure, so a gross unrelated to
        # the comp rate would be the first number in this module that follows
        # from nothing.
        rng = _rng(seed, "settlement")
        weeks = Decimal(rng.randint(20, 120))
        gross = money(wages_facts.rate.pd_weekly_rate * weeks + benefits.td_total)

    funding: dt.date | None = None
    if approval is not None:
        if scenario is not None and scenario.funding_date is not None:
            funding = scenario.funding_date
        else:
            lag = (
                scenario.funding_days
                if scenario is not None and scenario.funding_days is not None
                else DILIGENCE_FUNDING_DAYS[diligence]
            )
            funding = approval + dt.timedelta(days=lag)

    return SettlementFact(
        kind="c_and_r" if resolution == "c_and_r" else "stipulations",
        gross_amount=gross,
        approval_date=approval,
        funding_date=funding,
    )


def derive_money_facts(
    seed: CaseSeed, timeline: Any, diligence: str = "ordinary"
) -> MoneyFacts | None:
    """Decide, once, what money this case involves. ``None`` when it involves none.

    Args:
        seed: the case seed. ``scenario.wages`` is the gate: no block, no money.
        timeline: the built ``CaseTimeline``, so payments hang off the same
            spine the documents do.
        diligence: the resolved adjuster persona, passed in rather than
            re-resolved so the money and the clinical ledger cannot disagree
            about who handled the file.

    Returns:
        A frozen :class:`MoneyFacts`, or ``None``. The ``None`` is load-bearing:
        every consumer short-circuits on it, which is what makes "a seed with no
        wage block produces zero money artifacts" a property of the code path
        rather than a claim about it.
    """
    wages = seed.scenario.wages
    if wages is None:
        return None

    with _exact():
        return _derive_money_facts(seed, wages, timeline, diligence)


def _derive_money_facts(
    seed: CaseSeed, wages: WageScenario, timeline: Any, diligence: str
) -> MoneyFacts:
    """The body of :func:`derive_money_facts`, under the pinned arithmetic context."""
    doi = getattr(timeline, "injury_date", None) or seed.injury.onset_date
    periods = _derive_periods(seed, wages, doi)
    computation = compute_aww(wages, periods)
    basis = _apply_rate_basis_override(rate_basis_for(doi), seed)
    rate = compute_comp_rate(computation.aww, basis)

    wage_facts = WageFacts(
        periods=periods,
        in_kind=tuple(
            InKindWage(kind=item.kind, weekly_value=money(item.weekly_value))
            for item in wages.in_kind
        ),
        employment_start=wages.employment_start,
        concurrent_employment=wages.concurrent_employment
        or any(p.concurrent for p in periods),
        pattern=wages.pattern,
        computation=computation,
        rate=rate,
    )

    benefits = _derive_benefits(seed, wage_facts, timeline, diligence)
    settlement = _derive_settlement(seed, wage_facts, benefits, timeline, diligence)

    facts = MoneyFacts(wages=wage_facts, benefits=benefits, settlement=settlement)
    log.debug(
        "money.derived",
        case_id=seed.case_id,
        method=facts.method,
        aww=str(facts.aww),
        td_rate=str(facts.td_weekly_rate),
        td_bound=facts.wages.rate.td_bound,
        periods=len(periods),
        td_periods=len(benefits.td_periods),
        settled=settlement is not None,
    )
    return facts


# ---------------------------------------------------------------------------
# Publication
# ---------------------------------------------------------------------------

#: The only money fields a manifest may publish, and the document that renders each.
#:
#: The same rule the clinical ledger holds itself to: a published fact is a
#: promise the documents keep, so a field nothing renders stays on the model and
#: out of the output. Every group below is printed on a governed document —
#: ``wage`` and ``rate`` on the wage statement, ``benefits`` on the payment
#: records, ``settlement`` on the compromise-and-release and the payment record
#: that funds it — which is what lets a reader check the manifest against the
#: folder beside it.
GOVERNED_MONEY_FIELDS: dict[str, tuple[str, ...]] = {
    "wage": (
        "method",
        "methodSource",
        "methodReason",
        "averageWeeklyWage",
        "periodsConsidered",
        "weeksConsidered",
        "grossConsidered",
        "inKindWeekly",
        "pattern",
        "concurrentEmployment",
    ),
    "rate": (
        "tdWeeklyRate",
        "tdBound",
        "pdWeeklyRate",
        "pdBound",
        "basisLabel",
        "basisAuthority",
        "counselConfirmed",
        "basisSource",
    ),
    "benefits": (
        "tdPeriods",
        "tdTotal",
        "pdAdvances",
        "pdTotal",
        "latePayments",
        "maxDaysLate",
        "gapDays",
    ),
    "settlement": ("kind", "grossAmount", "approvalDate", "fundingDate", "fundingLagDays"),
}


def money_manifest_block(facts: MoneyFacts) -> dict[str, Any]:
    """The ``caseFacts.money`` object a manifest publishes.

    Currency as exact decimal strings, never floats — see :func:`_dollars`.
    Restricted to :data:`GOVERNED_MONEY_FIELDS`, and the restriction is checked
    by the same validator that checks the clinical ledger's.
    """
    with _exact():
        return _money_manifest_block(facts)


def _money_manifest_block(facts: MoneyFacts) -> dict[str, Any]:
    """The body of :func:`money_manifest_block`, under the pinned context."""
    wage = facts.wages
    computation = wage.computation
    rate = wage.rate
    benefits = facts.benefits

    block: dict[str, Any] = {
        "wage": {
            "method": computation.method,
            "methodSource": computation.method_source,
            "methodReason": computation.method_reason,
            "averageWeeklyWage": _dollars(computation.aww),
            "periodsConsidered": computation.periods_considered,
            "weeksConsidered": f"{computation.weeks_considered.normalize():f}",
            "grossConsidered": _dollars(computation.gross_considered),
            "inKindWeekly": _dollars(computation.in_kind_weekly),
            "pattern": wage.pattern,
            "concurrentEmployment": wage.concurrent_employment,
        },
        "rate": {
            "tdWeeklyRate": _dollars(rate.td_weekly_rate),
            "tdBound": rate.td_bound,
            "pdWeeklyRate": _dollars(rate.pd_weekly_rate),
            "pdBound": rate.pd_bound,
            "basisLabel": rate.basis.label,
            "basisAuthority": rate.basis.authority,
            # Published so a consumer meets the caveat without reading the
            # source. Everything this engine ships is false here.
            "counselConfirmed": rate.basis.counsel_confirmed,
            "basisSource": rate.basis.source,
        },
        "benefits": {
            "tdPeriods": len(benefits.td_periods),
            "tdTotal": _dollars(benefits.td_total),
            "pdAdvances": len(benefits.pd_advances),
            "pdTotal": _dollars(benefits.pd_total),
            "latePayments": benefits.late_payment_count,
            "maxDaysLate": benefits.max_days_late,
            "gapDays": sum(gap.days for gap in benefits.gaps),
        },
    }
    if facts.settlement is not None:
        settlement = facts.settlement
        block["settlement"] = {
            "kind": settlement.kind,
            "grossAmount": _dollars(settlement.gross_amount),
            "approvalDate": (
                settlement.approval_date.isoformat() if settlement.approval_date else None
            ),
            "fundingDate": (
                settlement.funding_date.isoformat() if settlement.funding_date else None
            ),
            "fundingLagDays": settlement.funding_lag_days,
        }
    return block


__all__ = [
    "CENTS",
    "DILIGENCE_FUNDING_DAYS",
    "DILIGENCE_LATENESS",
    "GOVERNED_MONEY_FIELDS",
    "IRREGULARITY_THRESHOLD",
    "SHORT_HISTORY_WEEKS",
    "TD_PAYMENT_DUE_DAYS",
    "UNCONFIRMED_RATE_TABLE",
    "AwwComputation",
    "BenefitGap",
    "BenefitLedger",
    "CompRate",
    "EarningsPeriod",
    "InKindWage",
    "MoneyFacts",
    "PdAdvance",
    "RateBasis",
    "SettlementFact",
    "TdPeriod",
    "WageFacts",
    "compute_aww",
    "compute_comp_rate",
    "derive_money_facts",
    "money",
    "money_manifest_block",
    "rate_basis_for",
    "select_method",
]
