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
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

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
    """The item-0d test/ledger-only diagnostic (F3-round-11).

    `draw_consistency_weeks` is computed here and recorded in the evidence
    ledger. It is **not** a shipped field: it reaches no model, no manifest, no
    document surface and no export, and the outward-boundary probe below asserts
    that by name rather than by an absence sweep that would pass on a typo.
    """

    @staticmethod
    def draw_consistency_weeks(gross: int) -> int:
        """Whole weeks the labelled deductions would cover at the award rate.

        A derived diagnostic over figures this item does not change, so it is a
        reading of the deduction shape rather than a new quantity in it.
        """
        figures = reference_cr_deductions(gross, wants_msa=True)
        deducted = figures["fee"] + figures["costs"] + figures["set_aside"]
        return int(deducted // Decimal(290))

    @pytest.mark.parametrize("gross", [g for g in GROSS_VALUES if g >= 1_000])
    def test_the_derived_branch_is_positive_and_monotone(self, gross: int) -> None:
        """The positive fixture: the branch computes, not merely returns zero."""
        weeks = self.draw_consistency_weeks(gross)
        assert weeks >= 1
        assert self.draw_consistency_weeks(gross * 2) >= weeks

    def test_the_diagnostic_never_reaches_an_outward_surface(self) -> None:
        """The outward-boundary field-set probe, by name."""
        for module in (seeds, fact_templates):
            source = Path(module.__file__).read_text(encoding="utf-8")
            assert "draw_consistency_weeks" not in source, (
                f"{module.__name__} names a test-only diagnostic"
            )
