"""Sweep 2 — the document/money-figure matrix, derived from the registry.

Ten rounds of review kept finding the same class of defect: a fix landed on the
document a reviewer named and missed the sibling that prints the same figure.
Round 2 fixed one half of a pair; round 6 found an older path round 5 had missed;
round 10 found the fee sentence round 9 had corrected on one of the two documents
that carry it. Each of those was found by someone looking. None of them was found
by a rule.

This module is the rule. It has two halves and they fail in opposite directions.

**The matrix** (:class:`TestEveryMoneyDrawingTemplateIsAccountedFor`) is derived
from ``pdf_templates.registry`` — deliberately *not* from the list of templates
the engine already overrides. A matrix built from what is governed can only
confirm what is governed, and that is exactly the blindness that let a
twenty-seven-subtype template family with nine money draws go five rounds
without anyone looking at it. Every substrate module that draws money is either
governed for every subtype routed to it, or listed below with a reason.

**The sweep** (:class:`TestAGovernedFigureIsTheSameOnEverySurface`) renders one
settled case and walks *every* document in it, not a named few. For each
governed money fact it finds every surface that prints it and asserts they
agree. A figure printed on N surfaces with fewer than N assertions is the
program's oldest defect class; here the surfaces are counted rather than
assumed, and a rule that matches nothing at all fails too — a label that moved
is how a sweep silently stops sweeping.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from conftest import extract_text, requires_substrate
from money_coherence import GOVERNED_ON_THE_PAGE, HOURLY_RATE, sweep
from wc_caseload_engine.manifests import MANIFEST_NAME, generate_case
from wc_caseload_engine.seeds import parse_case_seed
from wc_caseload_engine.substrate import install_substrate_path, substrate_path
from wc_caseload_engine.taxonomy import effective_taxonomy

# ---------------------------------------------------------------------------
# Half one — the matrix
# ---------------------------------------------------------------------------

#: A ``random.*`` call.
_RANDOM_CALL = re.compile(r"\brandom\.(randint|uniform|randrange|choice|choices)\b")

#: Names that read as money. Deliberately generous: a false positive costs a
#: line in the ledger below, a false negative costs a defect nobody sees.
_MONEY_NAME = re.compile(
    r"amount|gross|net|total|award|fee|cost|charge|bill|balance|due|wage|salary|"
    r"pay|rate|earning|settle|reimburs|aside|msa|lien|deduct|premium|price|sum|"
    r"dollar|benefit|advance|indemnit",
    re.IGNORECASE,
)

#: Money-drawing substrate modules the engine does **not** govern, and why.
#:
#: This is a ledger, not an excuse list. An entry says: these documents draw
#: figures the manifest does not publish, so there is no governed fact for them
#: to contradict. The moment one of them prints something the schema owns, its
#: entry is wrong and the entry is where the argument happens.
UNGOVERNED_MONEY_MODULES: dict[str, str] = {
    "pdf_templates.medical.billing_records": (
        "Provider charges and payments. The schema publishes no medical-charge "
        "fact, so a drawn charge contradicts nothing. BENEFIT_PAYMENT_LEDGER is "
        "the one subtype here that carries governed money and it is overridden; "
        "the other 28 are bills and liens."
    ),
    "pdf_templates.medical.treating_physician_report": (
        "Work-restriction and treatment-cost asides. No published counterpart."
    ),
    "pdf_templates.medical.qme_ame_report": (
        "Medical-legal fee and cost asides inside a narrative report."
    ),
    "pdf_templates.correspondence.adjuster_letter": (
        "Reserve and authorization figures in correspondence. No published "
        "counterpart; the letter's benefit statements are governed by the "
        "FactAwareAdjusterLetter override on the four subtypes that carry them."
    ),
    "pdf_templates.medical.utilization_review": (
        "Treatment-cost asides in a UR determination."
    ),
    "pdf_templates.medical.diagnostic_report": ("Imaging and lab charge asides."),
    "pdf_templates.medical.pharmacy_records": ("Prescription charges."),
    "pdf_templates.discovery.subpoenaed_records": ("Record-production costs."),
    "pdf_templates.legal.compromise_and_release": (
        "Fully governed on the six settlement subtypes; the remaining four are "
        "third-party and dependency variants the money layer does not model."
    ),
    "pdf_templates.legal.stipulations": (
        "Fully governed on the four award subtypes; the remaining three are "
        "lien-resolution variants that carry no published settlement."
    ),
}


def _money_draws(path: Path) -> int:
    """How many money-bearing random draws a substrate module makes."""
    lines = path.read_text(errors="replace").splitlines()
    found = 0
    for index, line in enumerate(lines, 1):
        if not _RANDOM_CALL.search(line):
            continue
        window = "\n".join(lines[max(0, index - 3) : index + 2])
        if _MONEY_NAME.search(line) or "$" in window:
            found += 1
    return found


def _matrix() -> dict[str, tuple[list[str], int, int]]:
    """module -> (subtypes routed to it, money draws, subtypes governed)."""
    install_substrate_path()
    from pdf_templates.registry import TEMPLATE_REGISTRY

    from wc_caseload_engine.fact_templates import fact_aware_templates

    governed = set(fact_aware_templates())
    routed: dict[str, list[str]] = defaultdict(list)
    for subtype in sorted(effective_taxonomy().subtypes):
        entry = TEMPLATE_REGISTRY.get(subtype)
        if entry is not None:
            routed[entry.module_path].append(subtype)

    root = substrate_path()
    out: dict[str, tuple[list[str], int, int]] = {}
    for module, subtypes in routed.items():
        path = root / (module.replace(".", "/") + ".py")
        if not path.exists():  # pragma: no cover - a registry typo
            continue
        draws = _money_draws(path)
        if draws:
            out[module] = (subtypes, draws, sum(1 for s in subtypes if s in governed))
    return out


@requires_substrate
class TestEveryMoneyDrawingTemplateIsAccountedFor:
    """No substrate template draws money without somebody having decided."""

    def test_every_money_drawing_module_is_governed_or_listed(self) -> None:
        """The whole point: derived from the registry, not from the overrides.

        ``settlement_memo`` backs twenty-seven registry subtypes, makes nine
        money draws, and had no fact-aware class at all. Any matrix built from
        the fact-aware list would have reported it as out of scope — which is
        how it survived ten rounds of review of the money layer.
        """
        matrix = _matrix()
        assert matrix, "no money-drawing modules found — the scan is broken"
        unaccounted = [
            module
            for module, (subtypes, _, governed) in matrix.items()
            if governed < len(subtypes) and module not in UNGOVERNED_MONEY_MODULES
        ]
        assert not unaccounted, (
            "substrate templates draw money for subtypes the engine does not "
            f"govern, and no entry says why: {sorted(unaccounted)}. Either give "
            "them a fact-aware override or add them to UNGOVERNED_MONEY_MODULES "
            "with the reason their figures contradict no published fact."
        )

    def test_the_ledger_names_no_module_that_is_fully_governed(self) -> None:
        """The ledger fails in the other direction too.

        An entry that has stopped being true is worse than no entry: it reads as
        a decision somebody made about live code.
        """
        matrix = _matrix()
        stale = [
            module
            for module in UNGOVERNED_MONEY_MODULES
            if module not in matrix
            or matrix[module][2] >= len(matrix[module][0])
        ]
        assert not stale, (
            f"UNGOVERNED_MONEY_MODULES names modules that are now fully governed "
            f"or draw no money: {sorted(stale)}. Delete the entries."
        )

    def test_the_settlement_memo_family_is_governed_from_the_registry(self) -> None:
        """Twenty-seven subtypes, bound by module rather than by hand.

        A hand-written list is exactly how four of them would be missed, which
        is the defect this binding was written for.

        Bound over the *canonical* subtypes, not the registry's whole list. Four
        of the thirty-one registry keys routing here are not classifier
        vocabulary, so the engine can never emit them, and mapping one would put
        a subtype in the fact-aware registry that no document can carry — which
        ``test_scenario_p2`` refuses, and refused on the first run of this
        binding.
        """
        install_substrate_path()
        from pdf_templates.registry import TEMPLATE_REGISTRY

        from wc_caseload_engine.fact_templates import (
            fact_aware_templates,
        )

        governed = fact_aware_templates()
        canonical = effective_taxonomy().subtypes
        memo = {
            subtype
            for subtype, entry in TEMPLATE_REGISTRY.items()
            if entry.module_path == "pdf_templates.summaries.settlement_memo"
            and subtype in canonical
        }
        assert len(memo) > 20, len(memo)
        missing = sorted(memo - set(governed))
        assert not missing, missing
        names = {governed[subtype].__name__ for subtype in memo}
        assert names == {"FactAwareSettlementMemo"}, names


# ---------------------------------------------------------------------------
# Half two — the sweep
# ---------------------------------------------------------------------------

_SEED: dict[str, Any] = {
    "case_id": "money-sweep",
    "rng_seed": 4301,
    "injury": {
        "type": "specific",
        "date_of_injury": "2021-03-08",
        "body_parts": [{"part": "lumbar_spine", "icd10": "M54.5"}],
    },
    "lifecycle": {
        "target_stage": "resolved",
        "eval_type": "qme",
        "resolution": {"type": "c_and_r", "msa": True},
    },
    "documents": {"format_mix": {"pdf": 1.0}},
    "scenario": {
        "wages": {
            "pattern": "regular",
            "base_weekly_wage": 1150,
            "lookback_weeks": 52,
            "pay_frequency": "biweekly",
        },
        "settlement": {"gross_amount": 32668},
    },
}

@requires_substrate
@pytest.mark.slow
class TestAGovernedFigureIsTheSameOnEverySurface:
    """One settled case, every document in it, every governed money fact."""

    @pytest.fixture(scope="class")
    def rendered(self, tmp_path_factory: pytest.TempPathFactory) -> tuple[dict, dict]:
        out = tmp_path_factory.mktemp("money-sweep")
        seed = parse_case_seed(_SEED)
        generate_case(seed, out, 1)
        directory = out / seed.case_id
        manifest = json.loads((directory / MANIFEST_NAME).read_text(encoding="utf-8"))
        texts = {
            document["subtype"]: " ".join(
                extract_text(
                    directory / "documents" / document["filename"], document["format"]
                ).split()
            )
            for document in manifest["documents"]
        }
        return manifest, texts

    def test_every_surface_printing_a_governed_figure_prints_the_same_one(
        self, rendered: tuple[dict, dict]
    ) -> None:
        """The sibling sweep, stated as an assertion instead of a habit.

        The settlement memo family printed ``$157,467 (138 weeks @
        $1141.07/week)`` on a case whose ledger published a temporary-disability
        rate of $767.59 and $28,400.83 paid — a governed fact contradicted on the
        same case, by a document nobody had looked at. The personnel file printed
        $42.79 an hour against a published average weekly wage of $1,151.33.
        Neither was reported by review; both fell out of walking the whole folder.
        """
        manifest, texts = rendered
        money = manifest["caseFacts"]["money"]
        result = sweep(texts, money, GOVERNED_ON_THE_PAGE)
        assert not result.disagreements, result.describe()
        # A rule that matches nothing is a rule that has stopped sweeping.
        dead = sorted(GOVERNED_ON_THE_PAGE.keys() - result.facts_found)
        assert not dead, (
            f"these labels appear on no document: {dead}. Either the label moved "
            "and the pattern needs re-pointing, or the document stopped carrying "
            "the figure — both are findings."
        )

    def test_no_document_prints_an_hourly_rate_above_the_published_wage(
        self, rendered: tuple[dict, dict]
    ) -> None:
        """The personnel file's promotion row was a raise above the current rate.

        ``align_employer_wage`` sets ``employer.hourly_rate`` from the published
        average weekly wage, which is where the hire and transfer rows come
        from. The promotion row was ``hourly_rate * random.uniform(1.05, 1.15)``
        — $32.02 an hour against a published $1,151.33 a week, which is $28.78.
        Incoherent twice over: it contradicts a governed fact, and since the
        promotion predates the injury it describes a pay cut nobody recorded.
        """
        manifest, texts = rendered
        published = (
            Decimal(manifest["caseFacts"]["money"]["wage"]["averageWeeklyWage"])
            / Decimal(40)
        ).quantize(Decimal("0.01"))
        seen: dict[str, list[Decimal]] = {}
        for subtype, text in sorted(texts.items()):
            rates = [
                Decimal(found.group(1).replace(",", ""))
                for found in HOURLY_RATE.finditer(text)
            ]
            if rates:
                seen[subtype] = rates
        assert seen, "no hourly rate on any document"
        for subtype, rates in seen.items():
            over = [rate for rate in rates if rate > published]
            assert not over, (
                f"{subtype}: prints {over} an hour against a published weekly "
                f"wage of {published} an hour"
            )
            assert max(rates) == published, (
                f"{subtype}: its highest rate is {max(rates)}, and the file says "
                f"the applicant was earning {published} an hour"
            )

    def test_a_settlement_range_row_adds_up_to_its_own_total(
        self, rendered: tuple[dict, dict]
    ) -> None:
        """A page whose arithmetic cannot be reproduced from the page.

        The substrate built the Optimistic row's Other column and its Total from
        two independent draws of the same range, so the row disagreed with
        itself: columns summing to $432,073 beside a printed total of $427,428.
        Round 10's negative-net class, one row wide.
        """
        _, texts = rendered
        row = re.compile(
            r"(Conservative|Expected|Optimistic) \$([\d,]+) \$([\d,]+) \$([\d,]+) \$([\d,]+)"
        )
        seen = 0
        for subtype, text in sorted(texts.items()):
            for found in row.finditer(text):
                seen += 1
                name, *figures = found.groups()
                pd_value, fmc, other, total = (
                    Decimal(figure.replace(",", "")) for figure in figures
                )
                assert pd_value + fmc + other == total, (
                    f"{subtype}: the {name} row prints {pd_value} + {fmc} + "
                    f"{other} = {pd_value + fmc + other} against a printed "
                    f"total of {total}"
                )
        assert seen >= 3, f"only {seen} settlement-range rows found"

    def test_the_recommended_target_is_the_settlement_the_file_executed(
        self, rendered: tuple[dict, dict]
    ) -> None:
        """A target twelve times the executed gross is a label, not a valuation.

        The memo recommended $387,466 on a file that settled for $32,668, and
        bracketed it with a comparable range of $309,972 to $464,959. A memo
        written before a settlement may legitimately propose a different figure;
        this corpus dates these documents into settled files, so an analyzer
        scored on them would be learning noise.
        """
        manifest, texts = rendered
        gross = Decimal(manifest["caseFacts"]["money"]["settlement"]["grossAmount"])
        comparable = re.compile(r"settled in the range of \$([\d,]+) to \$([\d,]+)")
        seen = 0
        for subtype, text in sorted(texts.items()):
            for found in comparable.finditer(text):
                seen += 1
                low, high = (Decimal(g.replace(",", "")) for g in found.groups())
                assert low <= gross <= high, (
                    f"{subtype}: the comparable range {low}-{high} does not "
                    f"contain the executed settlement of {gross}"
                )
        assert seen, "no comparable-range sentence found"
