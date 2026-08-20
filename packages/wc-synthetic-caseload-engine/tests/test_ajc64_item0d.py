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
import hashlib
import json
import re
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Any

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

    so the weeks the settlement was drawn against are recoverable from the
    published figures. The recovery is stated **independently** here rather than
    by calling the derivation, which is the whole point of a formula guard: an
    oracle that calls the function it checks agrees with any arithmetic that
    function happens to contain.

    The whole-dollar rounding is why the recovery is a bounded comparison rather
    than an exact division — ``(gross - td_total) / pd_weekly_rate`` lands within
    one dollar's worth of weeks of the drawn value, and the naive form that
    drops ``td_total`` misses by the entire temporary-disability total, which is
    thousands of dollars. The two are never confusable, and ``m24-147`` proves
    it.
    """

    CASE_IDS = ("draw-a", "draw-b", "draw-c", "draw-d")

    @staticmethod
    def _derived_case(case_id: str) -> tuple[Any, Any]:
        """A case whose gross is DERIVED — the branch this formula describes."""
        from test_money_spine import WAGES, _seed_body
        from wc_caseload_engine.lifecycle_bridge import build_timeline
        from wc_caseload_engine.money import derive_money_facts
        from wc_caseload_engine.seeds import parse_case_seed

        body = _seed_body(
            {"wages": WAGES, "benefits": {"td_weeks": 12}},
            case_id=case_id,
            lifecycle={
                "target_stage": "resolved",
                "eval_type": "none",
                # No settlement.gross_amount: that is what selects the derived
                # branch. A stated gross would make this fixture vacuous.
                "resolution": {"type": "c_and_r"},
            },
        )
        seed = parse_case_seed(body)
        return seed, derive_money_facts(seed, build_timeline(seed), "ordinary")

    @staticmethod
    def draw_consistency_weeks(gross: Decimal, td_total: Decimal, pd_rate: Decimal) -> Decimal:
        """Recover the drawn weeks from the published figures.

        Restated from the derivation by reading it, never by calling it.
        """
        return (Decimal(gross) - Decimal(td_total)) / Decimal(pd_rate)

    @pytest.mark.parametrize("case_id", CASE_IDS)
    def test_the_derived_gross_recovers_the_weeks_it_was_drawn_against(
        self, case_id: str
    ) -> None:
        """m24-147: the positive derived-branch fixture.

        The seeded draw is reproduced independently from the same
        ``money:settlement`` stream, so the expected value is not read out of
        the object under test.
        """
        from wc_caseload_engine.money import _rng

        seed, facts = self._derived_case(case_id)
        gross = facts.settlement.gross_amount
        td_total = facts.benefits.td_total
        pd_rate = facts.wages.rate.pd_weekly_rate
        drawn = Decimal(_rng(seed, "settlement").randint(20, 120))

        recovered = self.draw_consistency_weeks(gross, td_total, pd_rate)
        # Within one whole dollar's worth of weeks — that rounding is the only
        # slack the derivation introduces, and it is stated rather than absorbed
        # into a loose tolerance.
        assert abs(recovered - drawn) <= (Decimal(1) / pd_rate), (
            f"{case_id}: gross {gross} with td_total {td_total} at {pd_rate}/wk "
            f"recovers {recovered} weeks, drawn {drawn}"
        )
        assert 20 <= drawn <= 120
        # The td_total term is load-bearing: dropping it moves the answer by
        # thousands of dollars' worth of weeks, which is what m24-147 does.
        assert td_total > 0, "the fixture must carry temporary disability"
        naive = Decimal(gross) / Decimal(pd_rate)
        assert abs(naive - drawn) > 1, (
            f"{case_id}: the naive gross/rate form is not distinguishable here"
        )

    @pytest.mark.parametrize("case_id", CASE_IDS)
    def test_the_derived_gross_matches_the_restated_derivation_exactly(
        self, case_id: str
    ) -> None:
        """The full contract, including the whole-dollar floor step."""
        from wc_caseload_engine.money import (
            SETTLEMENT_GROSS_MINIMUM,
            _rng,
            _whole_dollars,
            money,
        )

        seed, facts = self._derived_case(case_id)
        drawn = Decimal(_rng(seed, "settlement").randint(20, 120))
        pd_rate = facts.wages.rate.pd_weekly_rate
        td_total = facts.benefits.td_total
        rebuilt = money(pd_rate * drawn + td_total)
        rebuilt = money(
            max(_whole_dollars(rebuilt), Decimal(SETTLEMENT_GROSS_MINIMUM))
        )
        assert facts.settlement.gross_amount == rebuilt


class TestDrawConsistencyDiagnosticStaysInternal:
    """The outward-boundary probe, kept as its own guard (round-1 finding F4).

    Sol rejected folding this into ``m24-147``, and rightly: a leak probe and a
    formula guard fail for different reasons and must be able to fail
    independently. It keeps its own mutant, ``m24-153``.

    ``draw_consistency_weeks`` is a **test/ledger-only** diagnostic: it is
    computed in this module and recorded in the evidence ledger, and it must
    reach no model, manifest, document surface or export.
    """

    def test_the_diagnostic_never_reaches_an_outward_surface(self) -> None:
        for module in (seeds, fact_templates):
            source = Path(module.__file__).read_text(encoding="utf-8")
            assert "draw_consistency_weeks" not in source, (
                f"{module.__name__} names a test-only diagnostic"
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

#: Deterministic gross values. Derived from the CASE ID by sha256 — never from
#: the wall clock and never from a bare `random.seed()` — so a failure is
#: reproducible from the case id printed beside it (F3's sampling rule).
PROPERTY_CASE_IDS = (
    "prop-alpha",
    "prop-bravo",
    "prop-charlie",
    "prop-delta",
    "prop-echo",
    "prop-foxtrot",
    "prop-golf",
    "prop-hotel",
)


def gross_for_case(case_id: str, *, low: int = 2, high: int = 400_000) -> int:
    """A gross drawn deterministically from the case id.

    Seeded from the id rather than from a clock so the same case always draws
    the same figure and a reported failure can be re-run verbatim. The span
    covers the floor-binding region and ordinary settlement magnitudes alike.
    """
    digest = hashlib.sha256(case_id.encode("utf-8")).digest()
    span = high - low + 1
    return low + (int.from_bytes(digest[:8], "big") % span)


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


@requires_substrate
class TestRenderedFigureProperty:
    """F3 — the identity property, computed from the RENDERED page.

    Round 1's oracle called `settlement_deductions` and `_fee_and_net` over a
    fixed fifteen-value grid. That checks the helpers agree with an equation; it
    does not check that the figure a document PRINTS is that value, which is the
    property M5-R41 actually states ("every figure on every subtype
    byte-identical to its pre-item value").

    Here every settlement figure is read back off the generated page and
    compared to the literal reference equations, for deterministically drawn
    grosses across both families with the set-aside on and off.
    """

    @pytest.mark.parametrize("case_id", PROPERTY_CASE_IDS)
    @pytest.mark.parametrize("msa", [True, False])
    def test_the_cr_page_prints_exactly_the_reference_figures(
        self, tmp_path: Path, case_id: str, msa: bool
    ) -> None:
        gross = gross_for_case(case_id)
        texts = render_settlement_case(
            tmp_path,
            f"{case_id}-cr-{'msa' if msa else 'nomsa'}",
            gross,
            resolution="c_and_r",
            msa=msa,
        )
        page = next(
            page for subtype, page in texts.items() if subtype in CR_FAMILY
        )
        expected = reference_cr_deductions(gross, wants_msa=msa)

        def printed(name: str) -> Decimal:
            found = LABELLED_RENDER_SITES[name].search(page)
            assert found, (
                f"{case_id} (gross {gross}, msa={msa}): {name} is not on the page"
            )
            return Decimal(found.group(1).replace(",", ""))

        assert printed("cr_table_fee") == expected["fee"]
        assert printed("cr_table_costs") == expected["costs"]
        assert printed("cr_prose_fee") == expected["fee"], (
            "the table and the signed paragraph state different fees"
        )
        assert printed("cr_prose_costs") == expected["costs"]
        if msa:
            assert printed("cr_table_msa") == expected["set_aside"]
        else:
            assert not LABELLED_RENDER_SITES["cr_table_msa"].search(page), (
                "a set-aside row printed for a seed that said msa: false"
            )

    @pytest.mark.parametrize("case_id", PROPERTY_CASE_IDS)
    def test_the_stips_page_prints_the_fee_on_the_award_component(
        self, tmp_path: Path, case_id: str
    ) -> None:
        """The fee base differs by family, and this is the half that proves it.

        A gross-based expectation would reject correct stipulations output: the
        award path reimburses a self-procured amount first and takes fifteen
        percent of what remains.
        """
        gross = gross_for_case(case_id)
        texts = render_settlement_case(
            tmp_path, f"{case_id}-stips", gross, resolution="stipulations", msa=False
        )
        page = next(
            page for subtype, page in texts.items() if subtype in STIPS_FAMILY
        )
        expected = reference_stips_figures(gross)
        found = LABELLED_RENDER_SITES["stips_table_fee"].search(page)
        assert found, f"{case_id} (gross {gross}): no labelled stips fee row"
        assert Decimal(found.group(1).replace(",", "")) == expected["fee"]
        # And it is NOT fifteen percent of the gross, which is the mistake a
        # single universal equation makes.
        gross_based = (Decimal(gross) * Decimal("0.15")).quantize(Decimal("0.01"))
        if expected["reimbursement"] > 0:
            assert expected["fee"] != gross_based

    def test_the_drawn_grosses_are_deterministic_and_spread(self) -> None:
        """Seeded from the case id, so a failure is reproducible verbatim."""
        first = [gross_for_case(case_id) for case_id in PROPERTY_CASE_IDS]
        second = [gross_for_case(case_id) for case_id in PROPERTY_CASE_IDS]
        assert first == second
        assert len(set(first)) == len(first)
        assert all(2 <= value <= 400_000 for value in first)
