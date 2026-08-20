"""AJC-64 item 0d — the invented settlement deductions say so on the page.

`seeds.py` carries `SETTLEMENT_FEE_RATE = 0.15`, `SETTLEMENT_COSTS_DIVISOR = 40`
(2.5%) and `SETTLEMENT_SET_ASIDE_DIVISOR = 5` (20%) — all invented, all uncited,
all printing as dollar lines on every compromise and release. This item labels
them `ENGINE_POLICY_UNCONFIRMED` and **changes nothing else** (M5-R41).

"Changes nothing else" is the whole claim, so it is the thing these oracles are
built to falsify:

* **the arithmetic is frozen node-by-node** against the S0-TREE syntax trees of
  all seven reachable calculation regions, with exactly one exemption class —
  the label string constants this item is required to edit, matched by their
  pre-edit values. Freezing whole ASTs would have contradicted the item itself;
  exempting whole functions would have let a re-round hide;
* **the reference figures are literal equations**, restated from the production
  source by reading it, never obtained by calling the production helper. An
  oracle that calls the function it checks agrees with any arithmetic the item
  happened to introduce;
* **the equations are per family**, because the fee base differs: the C&R path
  takes 15% of the gross, the stipulations path takes 15% of the *award
  component* left after a self-procured reimbursement. A gross-based oracle
  would reject correct stipulations output;
* **the property runs over arbitrary gross values on all eleven registry
  subtypes, MSA on and off**. A labelling change that accidentally re-rounded
  would move only some magnitudes on some subtypes, and a fixed grid on one
  subtype would miss it.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import ast
import copy
import json
import os
import random
import re
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Any, ClassVar

import pytest

from conftest import requires_substrate
from wc_caseload_engine import fact_templates, seeds
from wc_caseload_engine.fact_templates import (
    ENGINE_POLICY_UNCONFIRMED_LABEL,
    _fee_and_net,
    _reimbursement_nearest_five_percent,
    _wants_medicare_set_aside,
    fact_aware_templates,
)
from wc_caseload_engine.seeds import (
    SETTLEMENT_COSTS_DIVISOR,
    SETTLEMENT_FEE_RATE,
    SETTLEMENT_SET_ASIDE_DIVISOR,
    settlement_deductions,
)

LABEL = "[ENGINE_POLICY_UNCONFIRMED]"

S0_REGIONS_PATH = Path(__file__).parent / "fixtures" / "ajc64_item0d_s0_regions.json"

#: The eleven settlement subtypes in the `FactAware*` registry, as a literal.
#: Revision 7 counted six — the C&R block alone, mistaken for the whole family.
#: A label applied to six of eleven is exactly the defect this pin catches.
SETTLEMENT_REGISTRY_SUBTYPES = (
    "COMPROMISE_AND_RELEASE",
    "COMPROMISE_AND_RELEASE_DEPENDENCY",
    "COMPROMISE_AND_RELEASE_MSA",
    "COMPROMISE_AND_RELEASE_PD_ONLY",
    "COMPROMISE_AND_RELEASE_STANDARD",
    "COMPROMISE_AND_RELEASE_THIRD_PARTY",
    "ORDER_APPROVING_SETTLEMENT",
    "STIPS_WITH_REQUEST_FOR_AWARD_PACKAGE",
    "STIPULATIONS_WITH_REQUEST_FOR_AWARD",
    "STIPULATIONS_WITH_REQUEST_FOR_AWARD_FULL",
    "STIPULATIONS_WITH_REQUEST_FOR_AWARD_PARTIAL",
)

CR_FAMILY = tuple(
    s for s in SETTLEMENT_REGISTRY_SUBTYPES if s.startswith("COMPROMISE_AND_RELEASE")
)
STIPS_FAMILY = tuple(
    s
    for s in SETTLEMENT_REGISTRY_SUBTYPES
    if s.startswith(("STIPULATIONS", "STIPS"))
)
APPROVAL_FAMILY = ("ORDER_APPROVING_SETTLEMENT",)

#: The row labels `_restate_distribution` and `_restate_award_summary` build,
#: pre-edit. This is the closed exemption list for the AST freeze: exactly these
#: string-constant nodes may move, and only by gaining the label token.
LABELLED_ROWS = {
    "Less: Attorney Fees (15%)": "Less: Attorney Fees (15%) [ENGINE_POLICY_UNCONFIRMED]",
    "Less: Costs and Expenses": (
        "Less: Costs and Expenses [ENGINE_POLICY_UNCONFIRMED]"
    ),
    "Less: Medicare Set-Aside Allocation": (
        "Less: Medicare Set-Aside Allocation [ENGINE_POLICY_UNCONFIRMED]"
    ),
}

#: Row labels that must NOT gain the token: they are not deductions. The gross
#: is the settlement's own figure and the nets are derived from labelled rows —
#: labelling a derived total would say the engine invented the subtraction's
#: *result* rather than its rate.
UNLABELLED_ROWS = (
    "Gross Settlement Amount",
    "Net to Applicant",
    "Permanent Disability (Gross)",
    "Net Permanent Disability to Applicant",
    "Self-Procured Medical Reimbursement",
    "Settlement Gross",
)

GROSS_VALUES = (
    2,
    3,
    7,
    19,
    41,
    100,
    221,
    999,
    1_000,
    12_345,
    32_668,
    45_000,
    99_999,
    250_000,
    1_000_000,
)
"""Arbitrary grosses across the admissible range, chosen so the defect classes
this item can produce are each reachable somewhere in the grid rather than
merely covered on average:

* the **sub-$7 region**, where revision 7's asserted fee floor would have
  disagreed with correct code;
* **$2 through $41**, the only magnitudes where the `max(..., 1)` costs and
  set-aside floors bind — above $79 a floor change is invisible, and m24-61
  moves exactly that floor;
* **$19, $999 and $99,999**, where `total mod 20` lands in 10..19 so the
  self-procured reimbursement's half-up term actually rounds. Everywhere else
  flooring and rounding agree, and m24-146 would survive on any of them;
* **$32,668**, the live gross that printed a $4,900 fee beside the words "15%"
  for a true $4,900.20.

A grid that merely looked broad would have left both m24-61 and m24-146
surviving — both did, on the first pass, and that is why the magnitudes are
justified here rather than assumed."""


# --------------------------------------------------------------------------
# The reference equations. Restated from the production source BY READING it.
# --------------------------------------------------------------------------


def reference_cr_deductions(gross: int, *, wants_msa: bool) -> dict[str, Decimal]:
    """C&R family, per M5-R41's literal equations.

    No `$1` floor on the fee: `seeds.py` computes it bare, and the `max(..., 1)`
    floors apply to costs and set-aside only. Revision 7 asserted a fee floor,
    so its oracle would have rejected correct code on a sub-$7 gross.
    """
    fee = (Decimal(gross) * Decimal("0.15")).quantize(Decimal("0.01"))
    costs = max(gross // 40, 1)
    set_aside = max(gross // 5, 1) if wants_msa else 0
    net = Decimal(gross) - fee - Decimal(costs) - Decimal(set_aside)
    return {
        "fee": fee,
        "costs": Decimal(costs),
        "set_aside": Decimal(set_aside),
        "net": net,
    }


def reference_stips_figures(gross: int) -> dict[str, Decimal]:
    """Stipulations family — an INDEPENDENT literal formula.

    The reference equation may not call the production helper it is supposed to
    check, so the nearest-five-percent rounding and both clamp arms are restated
    here. The fee base is the PD **award component**, not the gross.
    """
    reimbursement = max(
        1,
        min(
            int(Decimal(gross * 5) / Decimal(100) + Decimal("0.5")),
            gross - 1,
        ),
    )
    award = gross - reimbursement
    fee = (Decimal(award) * Decimal("0.15")).quantize(Decimal("0.01"))
    return {
        "reimbursement": Decimal(reimbursement),
        "award": Decimal(award),
        "fee": fee,
        "net_award": Decimal(award) - fee,
    }


# --------------------------------------------------------------------------
# AST freeze
# --------------------------------------------------------------------------


def _s0_regions() -> dict[str, str]:
    return json.loads(S0_REGIONS_PATH.read_text(encoding="utf-8"))


def _module_tree(module: Any) -> ast.Module:
    return ast.parse(Path(module.__file__).read_text(encoding="utf-8"))


def _find_function(tree: ast.Module, name: str, owner: str | None) -> ast.FunctionDef:
    if owner is not None:
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == owner:
                for inner in node.body:
                    if isinstance(inner, ast.FunctionDef) and inner.name == name:
                        return inner
        raise AssertionError(f"{owner}.{name} is gone")
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} is gone")


def _delabel_dump(node: ast.AST) -> tuple[str, int]:
    """Dump the region with the ONE exemption class undone, and count it.

    The exemption is a closed list of string-constant nodes matched by their
    **post-edit value**, reverted to their pre-edit value before the dump. Every
    other node — every arithmetic operation, `Decimal` call, comparison, branch
    and non-label constant — is compared as it stands, so the arithmetic-drift
    mutants keep their anchors.

    The count is returned so a caller can assert the exemption was actually
    applied. An exemption that matched nothing would make the freeze pass for a
    reason unrelated to the reason it was written.
    """
    clone = copy.deepcopy(node)
    applied = 0
    for inner in ast.walk(clone):
        if isinstance(inner, ast.Constant) and isinstance(inner.value, str):
            for pre, post in LABELLED_ROWS.items():
                if inner.value == post:
                    inner.value = pre
                    applied += 1
    return ast.dump(clone, annotate_fields=True, include_attributes=False), applied


REGION_TARGETS = (
    ("seeds.settlement_deductions", seeds, "settlement_deductions", None),
    ("fact_templates._fee_and_net", fact_templates, "_fee_and_net", None),
    (
        "fact_templates._restate_distribution",
        fact_templates,
        "_restate_distribution",
        None,
    ),
    (
        "fact_templates._restate_award_summary",
        fact_templates,
        "_restate_award_summary",
        None,
    ),
    (
        "fact_templates._reimbursement_nearest_five_percent",
        fact_templates,
        "_reimbursement_nearest_five_percent",
        None,
    ),
    (
        "fact_templates._wants_medicare_set_aside",
        fact_templates,
        "_wants_medicare_set_aside",
        None,
    ),
    (
        "fact_templates.FactAwareCompromiseAndRelease.build_story",
        fact_templates,
        "build_story",
        "FactAwareCompromiseAndRelease",
    ),
)


class TestSourceConstants:
    """The three invented rates, pinned as literals in the consuming test."""

    def test_the_rates_are_exactly_the_pinned_values(self) -> None:
        assert Decimal("0.15") == SETTLEMENT_FEE_RATE
        assert SETTLEMENT_COSTS_DIVISOR == 40
        assert SETTLEMENT_SET_ASIDE_DIVISOR == 5

    def test_the_rates_are_the_percentages_the_label_describes(self) -> None:
        assert Decimal(1) / SETTLEMENT_COSTS_DIVISOR == Decimal("0.025")
        assert Decimal(1) / SETTLEMENT_SET_ASIDE_DIVISOR == Decimal("0.20")


class TestArithmeticFreeze:
    """Node-by-node against S0-TREE, one exemption class wide."""

    @pytest.mark.parametrize(
        ("key", "module", "name", "owner"),
        [(k, m, n, o) for k, m, n, o in REGION_TARGETS],
        ids=[k for k, _, _, _ in REGION_TARGETS],
    )
    def test_the_region_is_unchanged_but_for_its_label_constants(
        self, key: str, module: Any, name: str, owner: str | None
    ) -> None:
        """m24-60/61/62/63/96/146 keep their anchors because of this."""
        baseline = _s0_regions()[key]
        current = _find_function(_module_tree(module), name, owner)
        dumped, _ = _delabel_dump(current)
        assert dumped == baseline, (
            f"{key} moved outside the label-constant exemption class"
        )

    def test_the_exemption_is_actually_exercised_where_it_is_claimed(self) -> None:
        """An exemption matching nothing would make the freeze pass vacuously.

        `_restate_distribution` builds all three deduction rows; the fee row is
        also built by `_restate_award_summary`, the stipulations path. Both are
        asserted to consume the exemption, and every other frozen region is
        asserted to consume **none** of it — a region that quietly gained a
        label would otherwise be exempted without anyone deciding it should be.
        """
        expected_uses = {
            "fact_templates._restate_distribution": 3,
            "fact_templates._restate_award_summary": 1,
        }
        for key, module, name, owner in REGION_TARGETS:
            current = _find_function(_module_tree(module), name, owner)
            _, applied = _delabel_dump(current)
            assert applied == expected_uses.get(key, 0), (
                f"{key} consumed {applied} exemptions, expected "
                f"{expected_uses.get(key, 0)}"
            )
        assert len(LABELLED_ROWS) == 3


class TestSubtypeRegistry:
    """Eleven entries, not six."""

    def test_the_settlement_family_is_exactly_eleven_entries(self) -> None:
        registry = fact_aware_templates()
        present = tuple(
            sorted(s for s in SETTLEMENT_REGISTRY_SUBTYPES if s in registry)
        )
        assert present == SETTLEMENT_REGISTRY_SUBTYPES
        assert len(SETTLEMENT_REGISTRY_SUBTYPES) == 11
        assert len(CR_FAMILY) == 6
        assert len(STIPS_FAMILY) == 4
        assert len(APPROVAL_FAMILY) == 1


class TestIdentityProperty:
    """Every figure on every subtype equals its literal reference value."""

    @pytest.mark.parametrize("gross", GROSS_VALUES)
    @pytest.mark.parametrize("wants_msa", [True, False])
    def test_the_cr_family_figures_match_the_literal_equations(
        self, gross: int, wants_msa: bool
    ) -> None:
        expected = reference_cr_deductions(gross, wants_msa=wants_msa)
        fee, costs, set_aside = settlement_deductions(gross)
        assert fee == expected["fee"]
        assert Decimal(costs) == expected["costs"]
        if wants_msa:
            assert Decimal(set_aside) == expected["set_aside"]
        printed_fee, _ = _fee_and_net(gross)
        # The fee that reaches paper comes from `_fee_and_net`, not from
        # `settlement_deductions`, whose fee the C&R path discards. Both are
        # asserted, so a divergence between them becomes a finding rather than
        # an invisible drift.
        assert printed_fee == expected["fee"]
        assert printed_fee == fee

    @pytest.mark.parametrize("gross", [g for g in GROSS_VALUES if g >= 2])
    def test_the_stips_family_figures_match_the_literal_equations(
        self, gross: int
    ) -> None:
        expected = reference_stips_figures(gross)
        reimbursement = _reimbursement_nearest_five_percent(gross)
        assert Decimal(reimbursement) == expected["reimbursement"]
        award = gross - reimbursement
        assert Decimal(award) == expected["award"]
        fee, net_award = _fee_and_net(award)
        assert fee == expected["fee"]
        assert net_award == expected["net_award"]

    @pytest.mark.parametrize("gross", GROSS_VALUES)
    def test_the_fee_quantisation_never_actually_rounds(self, gross: int) -> None:
        """`quantize` defaults to ROUND_HALF_EVEN, and it is unobservable here.

        `Decimal(int) * Decimal("0.15")` is exact to two places, so the mode is
        never exercised. Asserted directly rather than asserting a rounding mode
        that never fires — a rate change under SI-M5-007 would make it
        observable overnight.
        """
        raw = Decimal(gross) * Decimal("0.15")
        assert raw == raw.quantize(Decimal("0.01"))

    @pytest.mark.parametrize("gross", GROSS_VALUES)
    def test_the_reimbursement_clamps_hold_on_both_arms(self, gross: int) -> None:
        """The two cash components sum to the total and each is a whole dollar.

        Stated as the invariant rather than as a claim about which arm fires.
        Only the **lower** clamp is reachable in the admissible range: the upper
        arm binds where ``0.05*total + 0.5 > total - 1``, which needs a total
        below 1.58, and the smallest gross the documents can carry is larger
        than that. Asserting "both arms are exercised" would therefore have been
        a claim this fixture cannot support — the upper arm is defence in depth
        against a future rate change, and it is recorded as such instead.
        """
        reimbursement = _reimbursement_nearest_five_percent(gross)
        assert 1 <= reimbursement <= gross - 1
        assert reimbursement + (gross - reimbursement) == gross


class TestMedicareSetAsidePredicate:
    """m24-96: the label may not be implemented by re-shaping a branch."""

    def test_the_predicate_reads_the_render_context_flag(self) -> None:
        class Spec:
            def __init__(self, context: Any) -> None:
                self.context = context

        class Template:
            def __init__(self, context: Any) -> None:
                self.doc_spec = Spec(context)

        assert _wants_medicare_set_aside(Template({"medicare_set_aside": True})) is True
        assert (
            _wants_medicare_set_aside(Template({"medicare_set_aside": False})) is False
        )
        assert _wants_medicare_set_aside(Template({})) is False
        assert _wants_medicare_set_aside(Template(None)) is False

    def test_msa_off_drops_the_set_aside_from_the_literal_net(self) -> None:
        """The MSA-off literal m24-96 must contradict when the predicate flips."""
        off = reference_cr_deductions(100_000, wants_msa=False)
        on = reference_cr_deductions(100_000, wants_msa=True)
        assert off["set_aside"] == Decimal(0)
        assert on["set_aside"] == Decimal(20_000)
        assert off["net"] - on["net"] == Decimal(20_000)


class TestLabelPlacement:
    """Which rows carry the token, and which must not."""

    def test_the_token_is_the_pinned_string(self) -> None:
        assert ENGINE_POLICY_UNCONFIRMED_LABEL == LABEL

    @pytest.mark.parametrize("post", sorted(LABELLED_ROWS.values()))
    def test_every_deduction_row_carries_the_token(self, post: str) -> None:
        """m24-29: stripping the label from one line reddens here."""
        source = Path(fact_templates.__file__).read_text(encoding="utf-8")
        assert post in source

    @pytest.mark.parametrize("label", UNLABELLED_ROWS)
    def test_no_derived_or_gross_row_carries_the_token(self, label: str) -> None:
        """m24-62: misplacement is the reachable defect for a labelling item.

        Read from the syntax tree so a row label is matched as the whole string
        constant it is — a substring scan over the file would call
        ``"Net to Applicant"`` unlabelled while the constant beside it read
        ``"Net to Applicant [ENGINE_POLICY_UNCONFIRMED]"``.
        """
        tree = _module_tree(fact_templates)
        constants = {
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        assert label in constants, f"{label!r} is no longer a row label"
        assert f"{label} {LABEL}" not in constants, (
            f"{label!r} is not a policy-authored deduction and must not be labelled"
        )

    def test_exactly_the_three_deduction_labels_carry_the_token(self) -> None:
        """The anti-probe: no other string constant gained the token.

        Counted, not set-compared. The fee label is built twice — once by the
        C&R distribution table and once by the stipulations award summary — and
        a set comparison would have been satisfied by either one alone, which is
        precisely the "labelled six of eleven subtypes" defect one layer down.
        """
        tree = _module_tree(fact_templates)
        carriers = Counter(
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and LABEL in node.value
        )
        assert carriers == Counter(
            {
                # The C&R fee row and the stipulations fee row.
                "Less: Attorney Fees (15%) [ENGINE_POLICY_UNCONFIRMED]": 2,
                "Less: Costs and Expenses [ENGINE_POLICY_UNCONFIRMED]": 1,
                "Less: Medicare Set-Aside Allocation [ENGINE_POLICY_UNCONFIRMED]": 1,
                # The token constant's own definition.
                LABEL: 1,
            }
        )

    def test_the_approval_document_builds_no_deduction_rows(self) -> None:
        """ORDER_APPROVING_SETTLEMENT restates; it computes nothing of its own.

        A labelled line appearing on it would mean this item fabricated a
        breakdown, so its absence is asserted from the class body rather than
        from a rendered page — the absence is structural.
        """
        tree = _module_tree(fact_templates)
        target = None
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ClassDef)
                and node.name == "FactAwareOrderApprovingSettlement"
            ):
                target = node
        assert target is not None
        for inner in ast.walk(target):
            if isinstance(inner, ast.Constant) and isinstance(inner.value, str):
                assert LABEL not in inner.value
                for row in LABELLED_ROWS:
                    assert row not in inner.value


class TestDrawConsistencyWeeks:
    """The item-0d test/ledger-only diagnostic (F3-round-11), as a FORMULA guard.

    Round 1 repointed ``m24-147`` at an outward-leak probe on the grounds that
    the reimbursement clamp arm was unreachable. That analysis was about the
    wrong function: the clamp lives in
    ``_reimbursement_nearest_five_percent``, and ``draw_consistency_weeks`` is a
    reading of the **derived-gross** branch in ``money.py``, which has no clamp
    in it. Sol's finding stands and the repoint is withdrawn — the contractual
    formula is guarded here, and the leak probe keeps its own separate guard and
    its own mutant below.

    The contract, read from ``money.py:1785-1803``::

        weeks = rng.randint(20, 120)                        # money:settlement
        gross = money(pd_weekly_rate * weeks + td_total)    # anchored to the file
        gross = money(max(_whole_dollars(gross), SETTLEMENT_GROSS_MINIMUM))

    so the weeks the settlement was drawn against are recoverable EXACTLY from
    the published figures.

    **Round-2 finding R2-2: the recovery is exact, and nothing here computes the
    expectation.** Round 1 imported the production ``_rng`` to reproduce the
    draw and imported ``_whole_dollars``/``money`` to rebuild the gross, then
    allowed a one-dollar tolerance to absorb the rounding. Both moves are the
    Form A anti-pattern: an oracle that reaches into the module under test for
    its own expected value agrees with whatever arithmetic that module happens
    to contain, and a tolerance hides the rounding step rather than proving it.

    The fixtures below are chosen so the rounding is a **no-op** — the PD rate
    sits at the statutory 290.00 maximum and the temporary-disability total is a
    whole number of dollars, so ``pd_rate * weeks + td_total`` is already whole
    and already above the floor. The equation therefore holds with no slack at
    all, and every term is a literal recorded here: the drawn weeks, the rate
    and the TD total. They are pinned, not derived.
    """

    #: ``(case_id, rng_seed, pd_weekly_rate, td_total, gross, drawn_weeks)``.
    #:
    #: Every value is a LITERAL. The seed body is fixed and the engine is
    #: deterministic, so these are stable; they were read off a one-time probe
    #: and frozen here, which is what makes them an oracle rather than a
    #: restatement of the code. The engine's own outputs are asserted to equal
    #: the pinned rate, TD total and gross before the formula is exercised, so a
    #: fixture that silently stopped describing the case fails as a fixture
    #: rather than passing vacuously.
    #:
    #: Six distinct drawn-week values spanning the ``randint(20, 120)`` range,
    #: so the guard is not satisfied by one arithmetic coincidence.
    EXACT_FIXTURES = (
        ("draw-4242", 4242, "290.00", "2658.00", "9038.00", 22),
        ("draw-4074", 4074, "290.00", "2670.00", "9340.00", 23),
        ("draw-4084", 4084, "290.00", "2670.00", "13980.00", 39),
        ("draw-4376", 4376, "290.00", "2658.00", "18028.00", 53),
        ("draw-4230", 4230, "290.00", "2660.00", "21510.00", 65),
        ("draw-4234", 4234, "290.00", "2670.00", "22970.00", 70),
    )

    #: The wage that puts the PD rate on the statutory maximum and leaves the
    #: TD total whole. Both are what make the recovery exact.
    INTEGRAL_WAGE = 500.0
    INTEGRAL_TD_WEEKS = 8

    @classmethod
    def _derived_case(cls, case_id: str, rng_seed: int) -> Any:
        """A case whose gross is DERIVED — the branch this formula describes."""
        from test_money_spine import WAGES, _seed_body
        from wc_caseload_engine.lifecycle_bridge import build_timeline
        from wc_caseload_engine.money import derive_money_facts
        from wc_caseload_engine.seeds import parse_case_seed

        body = _seed_body(
            {
                "wages": {**WAGES, "base_weekly_wage": cls.INTEGRAL_WAGE},
                "benefits": {"td_weeks": cls.INTEGRAL_TD_WEEKS},
            },
            case_id=case_id,
            rng_seed=rng_seed,
            lifecycle={
                "target_stage": "resolved",
                "eval_type": "none",
                # No settlement.gross_amount: that is what selects the derived
                # branch. A stated gross would make this fixture vacuous.
                "resolution": {"type": "c_and_r"},
            },
        )
        seed = parse_case_seed(body)
        return derive_money_facts(seed, build_timeline(seed), "ordinary")

    @staticmethod
    def draw_consistency_weeks(
        gross: Decimal, td_total: Decimal, pd_rate: Decimal
    ) -> Decimal:
        """Recover the drawn weeks from the published figures.

        Restated from the derivation by reading it, never by calling it.
        """
        return (Decimal(gross) - Decimal(td_total)) / Decimal(pd_rate)

    @pytest.mark.parametrize(
        ("case_id", "rng_seed", "pd_rate", "td_total", "gross", "weeks"),
        EXACT_FIXTURES,
    )
    def test_the_derived_gross_recovers_its_drawn_weeks_exactly(
        self,
        case_id: str,
        rng_seed: int,
        pd_rate: str,
        td_total: str,
        gross: str,
        weeks: int,
    ) -> None:
        """m24-147: ``(gross - td_total) / pd_weekly_rate == drawn_weeks``.

        Exact equality, no tolerance, no production helper consulted.
        """
        facts = self._derived_case(case_id, rng_seed)

        # The fixture describes this case — asserted, not assumed.
        assert facts.wages.rate.pd_weekly_rate == Decimal(pd_rate)
        assert facts.benefits.td_total == Decimal(td_total)
        assert facts.settlement.gross_amount == Decimal(gross)
        assert facts.benefits.td_total > 0, (
            "a zero TD total would make the naive form identical to the "
            "contractual one, and m24-147 could not be distinguished"
        )

        recovered = self.draw_consistency_weeks(
            Decimal(gross), Decimal(td_total), Decimal(pd_rate)
        )
        assert recovered == Decimal(weeks), (
            f"{case_id}: (gross {gross} - td_total {td_total}) / {pd_rate} "
            f"recovers {recovered}, drawn weeks pinned at {weeks}"
        )
        assert 20 <= weeks <= 120, "outside the randint(20, 120) contract"

        # The naive form m24-147 installs misses by the whole TD total, which
        # is thousands of dollars — never confusable with the exact answer.
        naive = Decimal(gross) / Decimal(pd_rate)
        assert naive != Decimal(weeks)
        assert abs(naive - Decimal(weeks)) > 1

    def test_the_fixtures_span_the_draw_range_and_are_distinct(self) -> None:
        """One coincidence is not a property."""
        drawn = [row[5] for row in self.EXACT_FIXTURES]
        assert len(set(drawn)) == len(drawn)
        assert min(drawn) < 30 and max(drawn) > 60
        assert all(20 <= value <= 120 for value in drawn)

    def test_the_oracle_consults_no_production_expectation_helper(self) -> None:
        """R2-2, structurally: the Form A anti-pattern must stay out.

        m24-208 reintroduces the production ``_rng`` import that round 1 used to
        manufacture the expected weeks. The expectation must come from the
        literal table above and from nowhere else.
        """
        forbidden = {"_rng", "_whole_dollars", "SETTLEMENT_GROSS_MINIMUM"}
        module = ast.parse(Path(__file__).read_text(encoding="utf-8"))
        target = next(
            node
            for node in module.body
            if isinstance(node, ast.ClassDef)
            and node.name == "TestDrawConsistencyWeeks"
        )
        # Over the syntax tree, not the text: docstrings and comments naturally
        # NAME these helpers to explain why they are absent, and a text scan
        # would fire on the explanation. `ast` keeps docstrings as constants,
        # so identifiers are checked and prose is not.
        referenced: set[str] = set()
        for node in ast.walk(target):
            if isinstance(node, ast.Name):
                referenced.add(node.id)
            elif isinstance(node, ast.Attribute):
                referenced.add(node.attr)
            elif isinstance(node, ast.ImportFrom):
                referenced.update(alias.name for alias in node.names)
        leaked = forbidden & referenced
        assert not leaked, (
            f"the exact-recovery oracle references the production helper(s) "
            f"{sorted(leaked)}; its expectation must be the pinned literals"
        )


@requires_substrate
class TestDrawConsistencyDiagnosticStaysInternal:
    """The outward-boundary probe, kept as its own guard (round-1 finding F4).

    Sol rejected folding this into ``m24-147``, and rightly: a leak probe and a
    formula guard fail for different reasons and must be able to fail
    independently. It keeps its own mutant, ``m24-203``.

    ``draw_consistency_weeks`` is a **test/ledger-only** diagnostic: it is
    computed in this module and recorded in the evidence ledger, and per the
    spec it must reach no model, no truth-manifest channel, no rendered
    document, no export and no decision input.

    **Round-2 finding R2-3: this now inspects the surfaces, not the sources.**
    The first version grepped two production modules for the identifier, and
    ``m24-203`` "leaked" it by planting an unused helper in one of those exact
    files. That pairing is circular — it proved a string could be added to a
    file the test happened to read, which is not what the spec forbids. A
    diagnostic added to a module and never published leaks nothing; a field
    added to the truth manifest leaks even though no new module appears.

    So the boundary is enumerated as the artifacts a consumer actually
    receives, and the identifier is looked for in the KEY SETS and the rendered
    text of each. The mutant now adds the figure to the truth manifest's
    settlement block — a real outward path.
    """

    #: Every spelling the diagnostic could plausibly reach an artifact under.
    FORBIDDEN_NAMES = (
        "draw_consistency_weeks",
        "drawConsistencyWeeks",
        "drawnWeeks",
        "drawn_weeks",
    )

    @staticmethod
    def _keys(payload: Any) -> set[str]:
        """Every mapping key anywhere in a nested JSON-ish structure."""
        found: set[str] = set()
        stack = [payload]
        while stack:
            item = stack.pop()
            if isinstance(item, dict):
                for key, value in item.items():
                    found.add(str(key))
                    stack.append(value)
            elif isinstance(item, (list, tuple)):
                stack.extend(item)
        return found

    @staticmethod
    def _settled_plan() -> Any:
        from test_money_spine import WAGES, _seed_body
        from wc_caseload_engine.planner import build_case_plan
        from wc_caseload_engine.seeds import parse_case_seed

        return build_case_plan(
            parse_case_seed(
                _seed_body(
                    {"wages": WAGES, "benefits": {"td_weeks": 8}},
                    case_id="leak-probe",
                    lifecycle={
                        "target_stage": "resolved",
                        "eval_type": "none",
                        "resolution": {"type": "c_and_r", "msa": True},
                    },
                )
            )
        )

    def test_the_truth_manifest_publishes_no_draw_diagnostic(self) -> None:
        """m24-203: the scorer envelope is an outward surface.

        It is the surface most likely to absorb a diagnostic by accident,
        because it exists precisely to carry things documents do not.
        """
        from wc_caseload_engine.truth_manifest import build_case_truth_manifest

        envelope = build_case_truth_manifest(self._settled_plan())
        keys = self._keys(envelope)
        assert keys, "the envelope came back empty; this would pass vacuously"
        assert "settlement" in keys, (
            "the probe needs a settled case for the settlement block to exist"
        )
        leaked = sorted(name for name in self.FORBIDDEN_NAMES if name in keys)
        assert not leaked, (
            f"the truth manifest publishes the test-only draw diagnostic: {leaked}"
        )

    def test_the_money_models_carry_no_draw_diagnostic_field(self) -> None:
        """Models are an outward surface: everything downstream reads them."""
        from wc_caseload_engine import money

        fields: set[str] = set()
        for name in dir(money):
            candidate = getattr(money, name)
            model_fields = getattr(candidate, "model_fields", None)
            if isinstance(model_fields, dict):
                fields.update(model_fields)
        assert fields, "no pydantic models found; the probe would be vacuous"
        leaked = sorted(name for name in self.FORBIDDEN_NAMES if name in fields)
        assert not leaked, f"a money model carries the draw diagnostic: {leaked}"

    def test_no_generated_artifact_mentions_the_draw_diagnostic(
        self, tmp_path: Path
    ) -> None:
        """The delivered tree: manifest, case facts, and every rendered page."""
        from conftest import extract_text
        from wc_caseload_engine.manifests import (
            CASE_FACTS_NAME,
            MANIFEST_NAME,
            generate_case,
        )

        plan_seed = self._settled_plan().seed
        generate_case(plan_seed, tmp_path, 1)
        directory = tmp_path / plan_seed.case_id

        manifest = json.loads(
            (directory / MANIFEST_NAME).read_text(encoding="utf-8")
        )
        surfaces = {"manifest keys": self._keys(manifest)}

        facts_text = (directory / CASE_FACTS_NAME).read_text(encoding="utf-8")
        surfaces["case_facts.yaml"] = {facts_text}

        rendered = []
        for document in manifest["documents"]:
            rendered.append(
                extract_text(
                    directory / "documents" / document["filename"],
                    document["format"],
                )
            )
        assert rendered, "the case rendered nothing; the probe would be vacuous"
        surfaces["rendered documents"] = set(rendered)

        for surface, blobs in surfaces.items():
            for name in self.FORBIDDEN_NAMES:
                for blob in blobs:
                    assert name not in blob, (
                        f"{surface} carries the test-only draw diagnostic "
                        f"{name!r}"
                    )


# ==========================================================================
# Round-1 findings F2 and F3 — the RENDER-PATH oracles.
#
# Round 1 checked the label by reading `fact_templates.py`'s source and checked
# the arithmetic through helper calls. Both are one step removed from the claim:
# the claim is about what a generated settlement document says. These oracles
# render real cases and read the produced pages.
# ==========================================================================

RENDER_LABEL = "[ENGINE_POLICY_UNCONFIRMED]"

#: The subtypes a settlement case can actually emit, with the resolution that
#: produces each. The registry holds eleven settlement entries; a seed produces
#: the C&R family or the stipulations family plus the approval order, so the
#: property is exercised over both families and the approval document.
FAMILY_RESOLUTIONS = (
    ("c_and_r", True),
    ("c_and_r", False),
    ("stipulations", True),
    ("stipulations", False),
)


def _settlement_seed_body(
    case_id: str, gross: int, *, resolution: str, msa: bool
) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "rng_seed": 4242,
        "injury": {
            "type": "specific",
            "date_of_injury": "2021-06-14",
            "body_parts": [{"part": "lumbar_spine"}],
        },
        "lifecycle": {
            "target_stage": "resolved",
            "eval_type": "none",
            "resolution": {"type": resolution, "msa": msa},
        },
        "scenario": {
            "wages": {"pattern": "regular", "base_weekly_wage": 1000.0},
            "benefits": {"td_weeks": 0, "pd_advances": 0},
            "settlement": {"gross_amount": gross},
        },
        "output": {"formats": ["pdf"]},
        "documents": {"format_mix": {"pdf": 1.0}},
    }


def render_settlement_case(
    tmp_path: Path, case_id: str, gross: int, *, resolution: str, msa: bool
) -> dict[str, str]:
    """Generate one settlement case and return {subtype: extracted text}."""
    from conftest import extract_text
    from wc_caseload_engine.manifests import MANIFEST_NAME, generate_case
    from wc_caseload_engine.seeds import parse_case_seed

    seed = parse_case_seed(
        _settlement_seed_body(case_id, gross, resolution=resolution, msa=msa)
    )
    generate_case(seed, tmp_path, 1)
    directory = tmp_path / seed.case_id
    manifest = json.loads((directory / MANIFEST_NAME).read_text(encoding="utf-8"))
    return {
        document["subtype"]: " ".join(
            extract_text(
                directory / "documents" / document["filename"], document["format"]
            ).split()
        )
        for document in manifest["documents"]
    }


#: Every rendered sentence or row that states one of the three invented rates,
#: as it appears in EXTRACTED TEXT (markup already stripped). Each pattern
#: captures the figure and REQUIRES the label after it — an unlabelled
#: occurrence simply fails to match, and the anti-probe below turns a
#: no-match into a failure rather than a silent pass.
LABELLED_RENDER_SITES = {
    "cr_table_fee": re.compile(
        r"Less: Attorney Fees \(15%\) \[ENGINE_POLICY_UNCONFIRMED\] \(\$([\d,]+\.\d\d)\)"
    ),
    "cr_table_costs": re.compile(
        r"Less: Costs and Expenses \[ENGINE_POLICY_UNCONFIRMED\] \(\$([\d,]+\.\d\d)\)"
    ),
    "cr_table_msa": re.compile(
        r"Less: Medicare Set-Aside Allocation \[ENGINE_POLICY_UNCONFIRMED\] "
        r"\(\$([\d,]+\.\d\d)\)"
    ),
    "cr_prose_fee": re.compile(
        r"in the amount of \$([\d,]+\.\d\d) \[ENGINE_POLICY_UNCONFIRMED\] "
        r"\(15% of gross settlement\)"
    ),
    "cr_prose_costs": re.compile(
        r"plus costs of \$([\d,]+(?:\.\d\d)?) \[ENGINE_POLICY_UNCONFIRMED\]"
    ),
    "cr_prose_msa": re.compile(
        r"acknowledge that \$([\d,]+(?:\.\d\d)?) \[ENGINE_POLICY_UNCONFIRMED\] "
        r"of the settlement"
    ),
    "stips_table_fee": re.compile(
        r"Less: Attorney Fees \(15%\) \[ENGINE_POLICY_UNCONFIRMED\] \(\$([\d,]+\.\d\d)\)"
    ),
    "stips_prose_fee": re.compile(
        r"which equals \$([\d,]+\.\d\d) \[ENGINE_POLICY_UNCONFIRMED\]"
    ),
}

#: The bare forms. If one of these matches WITHOUT the label following it, an
#: invented rate reached paper unattributed — which is the whole defect.
UNLABELLED_RENDER_PROBES = {
    "cr_table_fee": re.compile(r"Less: Attorney Fees \(15%\) \(\$[\d,]+\.\d\d\)"),
    "cr_table_costs": re.compile(r"Less: Costs and Expenses \(\$[\d,]+\.\d\d\)"),
    "cr_table_msa": re.compile(
        r"Less: Medicare Set-Aside Allocation \(\$[\d,]+\.\d\d\)"
    ),
    "cr_prose_fee": re.compile(
        r"in the amount of \$[\d,]+\.\d\d \(15% of gross settlement\)"
    ),
    "cr_prose_costs": re.compile(r"plus costs of \$[\d,]+(?:\.\d\d)?\. These amounts"),
    "cr_prose_msa": re.compile(
        r"acknowledge that \$[\d,]+(?:\.\d\d)? of the settlement"
    ),
    "stips_prose_fee": re.compile(r"which equals \$[\d,]+\.\d\d, to be paid"),
}


class TestProseLabellingIsIdempotent:
    """R2-6: applying the pass twice must equal applying it once.

    The pass runs from ``_restate_fee_prose``, and nothing today calls that
    twice on one story — but "nothing calls it twice today" is a property of
    the callers, not of the function, and the function documented idempotence
    as its own guarantee. Round 2 found the guarantee was enforced by a check
    on the money token alone, which can never end with the label, so two of the
    four patterns double-labelled on a second pass.
    """

    @staticmethod
    def _paragraphs(text: str) -> list[Any]:
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import Paragraph

        return [Paragraph(text, getSampleStyleSheet()["Normal"])]

    #: One sentence per pattern in `_PROSE_DEDUCTIONS`, in its substrate form.
    PROSE_FORMS: ClassVar[dict[str, str]] = {
        "release_fee": (
            "attorney fees in the amount of $4,900.00 (15% of gross settlement) "
            "plus costs of $816.00. These amounts are approved."
        ),
        "award_fee": (
            "a fee of fifteen percent, which equals <b>$4,900.00</b>, to be paid "
            "from the award."
        ),
        "set_aside": (
            "The parties acknowledge that $6,533.00 of the settlement proceeds "
            "are allocated to a Medicare Set-Aside."
        ),
    }

    @pytest.mark.parametrize("name", sorted(PROSE_FORMS))
    def test_a_second_application_changes_nothing(self, name: str) -> None:
        from wc_caseload_engine.fact_templates import _label_prose_deductions

        story = self._paragraphs(self.PROSE_FORMS[name])
        _label_prose_deductions(story)
        once = story[0].text
        assert ENGINE_POLICY_UNCONFIRMED_LABEL in once, (
            f"{name}: the first pass labelled nothing, so this proves nothing"
        )
        _label_prose_deductions(story)
        twice = story[0].text
        assert twice == once, (
            f"{name}: a second pass changed the text — double-labelled.\n"
            f"  once:  {once}\n  twice: {twice}"
        )
        assert twice.count(ENGINE_POLICY_UNCONFIRMED_LABEL) == once.count(
            ENGINE_POLICY_UNCONFIRMED_LABEL
        )

    def test_every_pattern_carries_the_already_labelled_guard(self) -> None:
        """Structural: the property lives in the patterns, so check them all.

        m24-206 removes the guard from one pattern; without this the only
        witness is the behavioural test above, and a pattern added later would
        reintroduce the defect silently.
        """
        from wc_caseload_engine.fact_templates import (
            _NOT_ALREADY_LABELLED,
            _PROSE_DEDUCTIONS,
        )

        missing = [
            pattern.pattern
            for pattern in _PROSE_DEDUCTIONS
            if _NOT_ALREADY_LABELLED not in pattern.pattern
        ]
        assert not missing, (
            "prose-deduction pattern(s) without the already-labelled guard, "
            f"which will double-label on a second pass: {missing}"
        )


@requires_substrate
class TestRenderedLabelCoverage:
    """F2 — every printed deduction figure carries the label, on real pages.

    Round 1 asserted the label by reading the renderer's source. That proves a
    string exists in a module; it does not prove a generated document shows it,
    and it could not have caught the prose duplicates, which are produced by a
    different code path from the table rows.
    """

    @pytest.mark.parametrize(("resolution", "msa"), FAMILY_RESOLUTIONS)
    def test_no_settlement_document_prints_an_unlabelled_deduction(
        self, tmp_path: Path, resolution: str, msa: bool
    ) -> None:
        """The anti-probe, across every settlement variant a seed can emit."""
        case_id = f"f2-{resolution}-{'msa' if msa else 'nomsa'}"
        texts = render_settlement_case(
            tmp_path, case_id, 250_000, resolution=resolution, msa=msa
        )
        settlement_pages = {
            subtype: page
            for subtype, page in texts.items()
            if subtype in SETTLEMENT_REGISTRY_SUBTYPES
        }
        assert settlement_pages, f"{case_id} rendered no settlement document"
        for subtype, page in settlement_pages.items():
            for name, probe in UNLABELLED_RENDER_PROBES.items():
                assert not probe.search(page), (
                    f"{case_id}/{subtype} prints an UNLABELLED invented rate "
                    f"({name}): {probe.pattern}"
                )

    @pytest.mark.parametrize(("resolution", "msa"), FAMILY_RESOLUTIONS)
    def test_the_expected_labelled_sites_are_actually_present(
        self, tmp_path: Path, resolution: str, msa: bool
    ) -> None:
        """The positive control: absence-only probes pass on an empty page.

        Each family is asserted to CONTAIN its labelled sites, so a renderer
        that stopped emitting the rows entirely — which would satisfy every
        anti-probe above perfectly — fails here instead.
        """
        case_id = f"f2pos-{resolution}-{'msa' if msa else 'nomsa'}"
        texts = render_settlement_case(
            tmp_path, case_id, 250_000, resolution=resolution, msa=msa
        )
        joined = " ".join(
            page for subtype, page in texts.items()
            if subtype in SETTLEMENT_REGISTRY_SUBTYPES
        )
        if resolution == "c_and_r":
            required = ["cr_table_fee", "cr_table_costs", "cr_prose_fee",
                        "cr_prose_costs"]
            if msa:
                required.extend(["cr_table_msa", "cr_prose_msa"])
        else:
            required = ["stips_table_fee", "stips_prose_fee"]
        for name in required:
            assert LABELLED_RENDER_SITES[name].search(joined), (
                f"{case_id}: expected labelled site {name} is absent from the "
                "rendered settlement documents"
            )

    def test_the_approval_order_still_prints_no_deduction_breakdown(
        self, tmp_path: Path
    ) -> None:
        """ORDER_APPROVING_SETTLEMENT restates; it computes nothing of its own.

        A labelled line appearing here would mean item 0d fabricated a
        breakdown, so its absence is asserted on the rendered page and not only
        from the class body.
        """
        texts = render_settlement_case(
            tmp_path, "f2-approval", 250_000, resolution="c_and_r", msa=True
        )
        page = texts.get("ORDER_APPROVING_SETTLEMENT")
        assert page, "the settled case rendered no approval order"
        assert RENDER_LABEL not in page
        for row in LABELLED_ROWS:
            assert row not in page


#: How many arbitrary grosses each subtype/MSA cell draws.
#:
#: Measured budget, not a guess: one render costs ~0.147s on this machine, so
#: 22 cells x 50 samples is ~162s of the suite. That is the cost of actually
#: sampling the admissible range and it is paid deliberately.
PROPERTY_SAMPLES_PER_CELL = 50


def _property_seed() -> int:
    """The seed this run samples from — fresh per run, but recoverable.

    Round-3 finding R3-1. Rounds 1 and 2 both shipped a *frozen* sample: first
    eight sha256-hashed case ids, then a single seeded PRNG whose output was
    memoized into a six-element ``PROPERTY_GROSSES`` tuple at import. Both
    produce identical values on every run, which is a fixed grid however it is
    spelled — a property that has only ever been checked at six points is a
    property checked at six points.

    A property test earns its name by trying values nobody chose. So the seed
    is drawn fresh per run, and the contract that makes that safe is
    reproducibility on demand: the seed is reported in every failure message,
    and setting ``AJC64_PROPERTY_SEED`` replays that exact run. This is the
    standard property-testing bargain — new inputs each run, deterministic
    replay of any failure.
    """
    override = os.environ.get(PROPERTY_SEED_ENV)
    if override:
        return int(override, 0)
    return random.SystemRandom().getrandbits(64)


PROPERTY_SEED_ENV = "AJC64_PROPERTY_SEED"
PROPERTY_SEED = _property_seed()

#: The admissible range for a STATED settlement gross, read from the schema
#: rather than restated: ``seeds.py`` bounds the field ``ge=0, le=10_000_000``
#: and refuses anything below ``SETTLEMENT_GROSS_MINIMUM``. Round 2 sampled to
#: $400,000, leaving 96% of the admissible range — every gross a catastrophic
#: or structured settlement would carry — entirely unexercised.
PROPERTY_GROSS_CEILING = 10_000_000


def property_gross_bounds() -> tuple[int, int]:
    from wc_caseload_engine.seeds import SETTLEMENT_GROSS_MINIMUM

    return int(SETTLEMENT_GROSS_MINIMUM), PROPERTY_GROSS_CEILING


def boundary_grosses() -> tuple[int, ...]:
    """The edges, always tried — a uniform draw never lands on them."""
    floor, ceiling = property_gross_bounds()
    return (floor, floor + 1, ceiling - 1, ceiling)


def sample_grosses(cell: str, count: int = PROPERTY_SAMPLES_PER_CELL) -> list[int]:
    """Arbitrary admissible grosses for one subtype/MSA cell.

    Each cell draws its own values — derived from the run seed AND the cell
    name — so the subtypes are not all handed the same list, and the whole
    matrix explores far more of the range than any one cell does.
    """
    floor, ceiling = property_gross_bounds()
    generator = random.Random(f"{PROPERTY_SEED}:{cell}")
    drawn = [generator.randint(floor, ceiling) for _ in range(count)]
    return [*boundary_grosses(), *drawn]


#: Which family each of the eleven registry subtypes belongs to, as a literal
#: map. Every subtype is named here explicitly — R2-1 requires the property to
#: be forced onto each one rather than onto whichever page a generated case
#: happened to emit.
SUBTYPE_FAMILY = {
    "COMPROMISE_AND_RELEASE": "cr",
    "COMPROMISE_AND_RELEASE_DEPENDENCY": "cr",
    "COMPROMISE_AND_RELEASE_MSA": "cr",
    "COMPROMISE_AND_RELEASE_PD_ONLY": "cr",
    "COMPROMISE_AND_RELEASE_STANDARD": "cr",
    "COMPROMISE_AND_RELEASE_THIRD_PARTY": "cr",
    "ORDER_APPROVING_SETTLEMENT": "approval",
    "STIPS_WITH_REQUEST_FOR_AWARD_PACKAGE": "stips",
    "STIPULATIONS_WITH_REQUEST_FOR_AWARD": "stips",
    "STIPULATIONS_WITH_REQUEST_FOR_AWARD_FULL": "stips",
    "STIPULATIONS_WITH_REQUEST_FOR_AWARD_PARTIAL": "stips",
}

#: The full matrix the spec asks for: every subtype, set-aside on and off.
SUBTYPE_MSA_MATRIX = tuple(
    (subtype, msa)
    for subtype in sorted(SUBTYPE_FAMILY)
    for msa in (True, False)
)


def render_one_subtype(
    tmp_path: Path, subtype: str, gross: int, *, msa: bool
) -> str:
    """Render ONE named subtype and return its extracted text.

    Goes through ``renderer.render_document``, which is the production render
    path and takes the subtype explicitly. That is what makes forcing possible:
    a seed's planner emits only the two or three settlement subtypes its own
    story selects (standard, MSA, or dependency on a death claim), so a test
    driven by generated cases can never reach the other eight — and the
    previous version quietly accepted whichever page came out first via
    ``next(...)``, which is how a subtype could go unexercised while the test
    still looked like a sweep.
    """
    from conftest import extract_text
    from wc_caseload_engine.planner import build_case_plan
    from wc_caseload_engine.renderer import render_document
    from wc_caseload_engine.seeds import parse_case_seed

    resolution = "stipulations" if SUBTYPE_FAMILY[subtype] == "stips" else "c_and_r"
    seed = parse_case_seed(
        _settlement_seed_body(
            f"prop-{subtype.lower()}-{'msa' if msa else 'nomsa'}-{gross}",
            gross,
            resolution=resolution,
            msa=msa,
        )
    )
    plan = build_case_plan(seed)
    out_path = tmp_path / f"{subtype}.pdf"
    render_document(
        seed=seed,
        cast=plan.cast,
        subtype=subtype,
        doc_date=plan.timeline.horizon,
        doc_format="pdf",
        index=0,
        out_path=out_path,
        case_facts=plan.case_facts,
        money_facts=plan.money_facts,
    )
    return " ".join(extract_text(out_path, "pdf").split())


@requires_substrate
class TestEverySubtypeIsExercised:
    """R2-1: the matrix is complete, and it is checked as data.

    A coverage claim asserted in prose is the one most likely to rot, so the
    parametrization itself is compared against the registry.
    """

    def test_the_matrix_covers_all_eleven_subtypes_both_ways(self) -> None:
        covered = {subtype for subtype, _ in SUBTYPE_MSA_MATRIX}
        assert covered == set(SETTLEMENT_REGISTRY_SUBTYPES)
        assert len(covered) == 11
        for subtype in covered:
            states = {msa for name, msa in SUBTYPE_MSA_MATRIX if name == subtype}
            assert states == {True, False}, (
                f"{subtype} is not exercised with the set-aside both on and off"
            )
        assert len(SUBTYPE_MSA_MATRIX) == 22

    def test_every_subtype_has_a_declared_family(self) -> None:
        assert set(SUBTYPE_FAMILY) == set(SETTLEMENT_REGISTRY_SUBTYPES)
        assert {SUBTYPE_FAMILY[s] for s in CR_FAMILY} == {"cr"}
        assert {SUBTYPE_FAMILY[s] for s in STIPS_FAMILY} == {"stips"}
        assert SUBTYPE_FAMILY["ORDER_APPROVING_SETTLEMENT"] == "approval"

    def test_the_sample_covers_the_whole_admissible_range(self) -> None:
        """R3-1: the sampler must actually be a sampler.

        Guards the three ways this oracle has already been weakened: too few
        values, too narrow a range, and — twice now — a "sample" that is the
        same list on every run.
        """
        floor, ceiling = property_gross_bounds()
        assert (floor, ceiling) == (3, 10_000_000), (
            "bounds must track the seed schema (ge=0, le=10_000_000) and the "
            "stated-gross floor"
        )

        drawn = sample_grosses("COMPROMISE_AND_RELEASE_STANDARD-msa")
        assert len(drawn) >= PROPERTY_SAMPLES_PER_CELL >= 50
        assert all(floor <= value <= ceiling for value in drawn)

        # The edges are always tried; a uniform draw never lands on them.
        for edge in boundary_grosses():
            assert edge in drawn, f"boundary {edge} is not exercised"
        assert boundary_grosses() == (3, 4, 9_999_999, 10_000_000)

        # And the draw genuinely spans the range rather than clustering in the
        # first few percent, which is where rounds 1 and 2 both stopped.
        assert max(drawn) > 5_000_000, "nothing above the halfway mark drawn"
        assert len({value // 1_000_000 for value in drawn}) >= 5

    def test_each_cell_draws_its_own_values(self) -> None:
        """Otherwise every subtype is handed one list and 22 cells prove one."""
        first = sample_grosses("COMPROMISE_AND_RELEASE_STANDARD-msa")
        second = sample_grosses("STIPULATIONS_WITH_REQUEST_FOR_AWARD-nomsa")
        assert set(first) != set(second)

    def test_the_sample_is_not_frozen_across_runs(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The defect R3-1 names, asserted on the sampler itself (m24-209).

        Rounds 1 and 2 both shipped a memoized tuple — first hashed case ids,
        then a PRNG whose output was frozen into a module constant at import.
        Both spellings look like generation and behave like a fixed grid. So
        this drives ``sample_grosses`` under different run seeds and requires
        the draw to move.
        """
        import test_ajc64_item0d as module

        draws = []
        for seed in (11, 22, 33):
            monkeypatch.setattr(module, "PROPERTY_SEED", seed)
            draws.append(tuple(sample_grosses("cell")))
        assert len({tuple(d) for d in draws}) == 3, (
            "sample_grosses returns the same values regardless of the run "
            "seed — the sample is frozen, which is the R3-1 defect"
        )
        # The boundaries are the exception: they are meant to be constant.
        for draw in draws:
            assert draw[: len(boundary_grosses())] == boundary_grosses()

    def test_a_failure_is_reproducible_from_the_reported_seed(self) -> None:
        """The bargain that makes per-run sampling safe."""
        floor, ceiling = property_gross_bounds()
        os.environ[PROPERTY_SEED_ENV] = "12345"
        try:
            assert _property_seed() == 12345
        finally:
            del os.environ[PROPERTY_SEED_ENV]
        replay_a = random.Random("12345:cell").randint(floor, ceiling)
        replay_b = random.Random("12345:cell").randint(floor, ceiling)
        assert replay_a == replay_b


@requires_substrate
class TestForcedSubtypeFigureProperty:
    """R2-1 — the property M5-R41 actually states, on every subtype.

    "Every figure on every subtype byte-identical to its pre-item value" is a
    property over the whole registry, and the previous oracle satisfied none of
    the three quantifiers honestly: eight hashed literals for the grosses, one
    page picked by ``next(...)`` for the subtype, and the stipulations half run
    with the set-aside off only. This forces each of the eleven literal
    subtypes, with the set-aside on and off, over generated grosses, and reads
    every figure back off the rendered page.
    """

    @pytest.mark.parametrize(("subtype", "msa"), SUBTYPE_MSA_MATRIX)
    def test_the_subtype_prints_exactly_the_reference_figures(
        self, tmp_path: Path, subtype: str, msa: bool
    ) -> None:
        """m24-202: the printed figures equal the literal equations.

        Every sampled gross for this cell is tried, and the FIRST failure
        reports the run seed and the offending value, so any failure replays
        exactly via ``AJC64_PROPERTY_SEED``.
        """
        family = SUBTYPE_FAMILY[subtype]
        cell = f"{subtype}-{'msa' if msa else 'nomsa'}"
        grosses = sample_grosses(cell)
        assert len(grosses) >= PROPERTY_SAMPLES_PER_CELL, "sample budget shrank"

        for gross in grosses:
            page = render_one_subtype(tmp_path, subtype, gross, msa=msa)
            where = (
                f"{subtype} (gross {gross}, msa={msa}) — replay this run with "
                f"{PROPERTY_SEED_ENV}={PROPERTY_SEED}"
            )

            def printed(name: str, *, page: str = page, where: str = where) -> Decimal:
                found = LABELLED_RENDER_SITES[name].search(page)
                assert found, f"{where}: {name} is not on the rendered page"
                return Decimal(found.group(1).replace(",", ""))

            if family == "approval":
                # The approval order restates; it computes nothing of its own,
                # so a deduction breakdown here would mean item 0d invented one.
                assert RENDER_LABEL not in page, (
                    f"{where}: the approval order printed an engine-policy label"
                )
                for row in LABELLED_ROWS:
                    assert row not in page, f"{where}: approval printed {row!r}"
                continue

            if family == "cr":
                expected = reference_cr_deductions(gross, wants_msa=msa)
                assert printed("cr_table_fee") == expected["fee"], where
                assert printed("cr_table_costs") == expected["costs"], where
                # The signed paragraph must agree with the table it summarises.
                assert printed("cr_prose_fee") == expected["fee"], (
                    f"{where}: table and signed paragraph state different fees"
                )
                assert printed("cr_prose_costs") == expected["costs"], where
                if msa:
                    assert printed("cr_table_msa") == expected["set_aside"], where
                    assert printed("cr_prose_msa") == expected["set_aside"], where
                else:
                    assert not LABELLED_RENDER_SITES["cr_table_msa"].search(page), (
                        f"{where}: a set-aside row printed for msa=False"
                    )
                continue

            expected_stips = reference_stips_figures(gross)
            assert printed("stips_table_fee") == expected_stips["fee"], where
            assert printed("stips_prose_fee") == expected_stips["fee"], (
                f"{where}: the award table and its fee sentence disagree"
            )
            # The fee base is the AWARD component, never the gross — the
            # mistake a single universal equation makes.
            if expected_stips["reimbursement"] > 0:
                gross_based = (Decimal(gross) * Decimal("0.15")).quantize(
                    Decimal("0.01")
                )
                assert expected_stips["fee"] != gross_based, where

    @pytest.mark.parametrize(("subtype", "msa"), SUBTYPE_MSA_MATRIX)
    def test_the_subtype_prints_no_unlabelled_deduction(
        self, tmp_path: Path, subtype: str, msa: bool
    ) -> None:
        """F2's anti-probe, on every subtype rather than every seeded family."""
        page = render_one_subtype(tmp_path, subtype, 250_000, msa=msa)
        for name, probe in UNLABELLED_RENDER_PROBES.items():
            assert not probe.search(page), (
                f"{subtype} (msa={msa}) prints an UNLABELLED invented rate "
                f"({name}): {probe.pattern}"
            )
