"""AJC-44/AJC-45 Money W2 work-item-1 baseline instruments.

Every expected value here comes from the frozen pre-W2 fixture, never from the
production result under test.  The fixture contains the complete five golden
dictionaries and hashes of the exact seven ``money-showcase`` truth bytes.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import re
from collections.abc import Mapping
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest

from conftest import extract_text, requires_substrate
from money_coherence import GOVERNED_ON_THE_PAGE, sweep
from wc_caseload_engine import money as money_module
from wc_caseload_engine.case_facts import CaseFacts, derive_case_facts
from wc_caseload_engine.fact_templates import fact_aware_templates
from wc_caseload_engine.lifecycle_bridge import build_timeline
from wc_caseload_engine.manifests import generate_caseload
from wc_caseload_engine.money import RateBasis
from wc_caseload_engine.planner import build_case_plan
from wc_caseload_engine.rating import RatingFacts
from wc_caseload_engine.seeds import (
    load_caseload_spec,
    parse_case_seed,
    resolve_caseload,
)
from wc_caseload_engine.truth_manifest import (
    MONEY_CHANNEL_VERSION,
    build_case_truth_manifest,
)

PACKAGE = Path(__file__).resolve().parents[1]
BASELINE_PATH = PACKAGE / "tests" / "fixtures" / "money_w2_pre_w2_baseline.json"
MONEY_SHOWCASE_PATH = PACKAGE / "examples" / "money-showcase.yaml"

EXPECTED_GOLDEN_NAMES = (
    "demo-caseload",
    "doctrine-showcase",
    "medical-story-showcase",
    "money-showcase",
    "personas-showcase",
)

EXPECTED_MONEY_TRUTH_FILES = (
    "atypical-earner.truth.json",
    "capped-executive.truth.json",
    "irregular-earner.truth.json",
    "neglected-file.truth.json",
    "new-hire.truth.json",
    "steady-earner.truth.json",
    "two-jobs.truth.json",
)

EXPECTED_FACT_STREAMS = (
    "facts:adjuster",
    "facts:attorney",
    "facts:benefits",
    "facts:diagnostics",
    "facts:discovery",
    "facts:surgery",
    "facts:trajectory",
    "facts:treatment",
)

PRE_W2_UNRELATED_FACTS_SHA256 = "dfc884345df742c1729fa26faf54147c56954fcba91c0cce4b85ef103198c7bc"


def _baseline() -> dict[str, Any]:
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def _truth_bytes(payload: Mapping[str, Any]) -> bytes:
    """Mirror the writer's timeless JSON bytes without touching the filesystem."""
    return (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _path_child(path: str, key: str | int) -> str:
    return f"{path}[{key}]" if isinstance(key, int) else f"{path}.{key}"


def _scalar_differences(old: Any, current: Any, path: str = "$") -> dict[str, tuple[Any, Any]]:
    """Return scalar changes while rejecting an added/removed/reordered shape."""
    if isinstance(old, Mapping) and isinstance(current, Mapping):
        assert tuple(old) == tuple(current), path
        changes: dict[str, tuple[Any, Any]] = {}
        for key in old:
            changes.update(_scalar_differences(old[key], current[key], _path_child(path, key)))
        return changes
    if isinstance(old, list) and isinstance(current, list):
        assert len(old) == len(current), path
        changes: dict[str, tuple[Any, Any]] = {}
        for index, (old_item, current_item) in enumerate(zip(old, current, strict=True)):
            changes.update(_scalar_differences(old_item, current_item, _path_child(path, index)))
        return changes
    assert not isinstance(old, (Mapping, list)) and not isinstance(current, (Mapping, list)), path
    return {} if old == current else {path: (old, current)}


_OLD_RATE_AUTHORITY = {
    "pre-2014": (
        "Temporary and permanent disability indemnity rates for dates of injury "
        "before 2014. COUNSEL-UNCONFIRMED placeholder — the figures, the fraction "
        "and the bracket boundaries are all unverified."
    ),
    "2014-2018": (
        "Temporary and permanent disability indemnity rates for dates of injury "
        "2014-2018. COUNSEL-UNCONFIRMED placeholder."
    ),
    "2019-2022": (
        "Temporary and permanent disability indemnity rates for dates of injury "
        "2019-2022. COUNSEL-UNCONFIRMED placeholder."
    ),
    "2023-onward": (
        "Temporary and permanent disability indemnity rates for dates of injury "
        "2023 onward. COUNSEL-UNCONFIRMED placeholder."
    ),
}


_OLD_RATE_TABLE = (
    RateBasis(
        label="doi-pre-2014",
        effective_from=date.min,
        effective_to=date(2013, 12, 31),
        td_fraction=Fraction(6667, 10000),
        td_max_weekly=Decimal("1066.72"),
        td_min_weekly=Decimal("160.00"),
        pd_fraction=Fraction(6667, 10000),
        pd_max_weekly=Decimal("270.00"),
        pd_min_weekly=Decimal("160.00"),
        authority=_OLD_RATE_AUTHORITY["pre-2014"],
    ),
    RateBasis(
        label="doi-2014-2018",
        effective_from=date(2014, 1, 1),
        effective_to=date(2018, 12, 31),
        td_fraction=Fraction(6667, 10000),
        td_max_weekly=Decimal("1215.27"),
        td_min_weekly=Decimal("182.29"),
        pd_fraction=Fraction(6667, 10000),
        pd_max_weekly=Decimal("290.00"),
        pd_min_weekly=Decimal("160.00"),
        authority=_OLD_RATE_AUTHORITY["2014-2018"],
    ),
    RateBasis(
        label="doi-2019-2022",
        effective_from=date(2019, 1, 1),
        effective_to=date(2022, 12, 31),
        td_fraction=Fraction(6667, 10000),
        td_max_weekly=Decimal("1539.71"),
        td_min_weekly=Decimal("230.95"),
        pd_fraction=Fraction(6667, 10000),
        pd_max_weekly=Decimal("290.00"),
        pd_min_weekly=Decimal("160.00"),
        authority=_OLD_RATE_AUTHORITY["2019-2022"],
    ),
    RateBasis(
        label="doi-2023-onward",
        effective_from=date(2023, 1, 1),
        td_fraction=Fraction(6667, 10000),
        td_max_weekly=Decimal("1619.15"),
        td_min_weekly=Decimal("242.86"),
        pd_fraction=Fraction(6667, 10000),
        pd_max_weekly=Decimal("290.00"),
        pd_min_weekly=Decimal("160.00"),
        authority=_OLD_RATE_AUTHORITY["2023-onward"],
    ),
)


def _normalize_old_serialized_fractions(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Restore the W1 JSON spelling without changing its exact old arithmetic."""
    normalized = copy.deepcopy(payload)
    basis = normalized["channels"]["money"]["wage"]["rate"]["basis"]
    basis["tdFraction"] = "0.6667"
    basis["pdFraction"] = "0.6667"
    return normalized


@pytest.fixture(scope="module")
def money_showcase_truth() -> dict[str, tuple[bytes, dict[str, Any]]]:
    spec = load_caseload_spec(MONEY_SHOWCASE_PATH)
    observed: dict[str, tuple[bytes, dict[str, Any]]] = {}
    for case_number, seed in enumerate(resolve_caseload(spec), start=1):
        plan = build_case_plan(seed, case_number=case_number)
        payload = build_case_truth_manifest(plan)
        observed[f"{seed.case_id}.truth.json"] = (_truth_bytes(payload), payload)
    return {name: observed[name] for name in EXPECTED_MONEY_TRUTH_FILES}


def _old_money_showcase_truth(monkeypatch: pytest.MonkeyPatch) -> dict[str, dict[str, Any]]:
    """Rebuild W1 through its literal four-row table, including every dependency."""
    monkeypatch.setattr(money_module, "UNCONFIRMED_RATE_TABLE", _OLD_RATE_TABLE)
    spec = load_caseload_spec(MONEY_SHOWCASE_PATH)
    old: dict[str, dict[str, Any]] = {}
    for case_number, seed in enumerate(resolve_caseload(spec), start=1):
        payload = build_case_truth_manifest(build_case_plan(seed, case_number=case_number))
        old[f"{seed.case_id}.truth.json"] = _normalize_old_serialized_fractions(payload)
    return old


@pytest.fixture(scope="module")
def r109_rendered_money_showcase(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Path, Path]:
    """Render the literal old and R109 trees once each for the file-level oracle."""
    root = tmp_path_factory.mktemp("r109-money-showcase")
    spec = load_caseload_spec(MONEY_SHOWCASE_PATH)
    old_root = root / "old"
    current_root = root / "current"
    original_table = money_module.UNCONFIRMED_RATE_TABLE
    try:
        money_module.UNCONFIRMED_RATE_TABLE = _OLD_RATE_TABLE
        generate_caseload(spec.caseload_id, resolve_caseload(spec), old_root)
    finally:
        money_module.UNCONFIRMED_RATE_TABLE = original_table
    generate_caseload(spec.caseload_id, resolve_caseload(spec), current_root)
    return old_root, current_root


_GOVERNED_MONEY_TEMPLATE_NAMES = frozenset(
    {
        "FactAwareBenefitPaymentLedger",
        "FactAwareCompromiseAndRelease",
        "FactAwareOrderApprovingSettlement",
        "FactAwareSettlementMemo",
        "FactAwareStipulations",
        "FactAwareWageStatement",
    }
)

_R109_RENDERED_CAPTURES = {
    **GOVERNED_ON_THE_PAGE,
    "rate_basis_label": (
        re.compile(r"Rate Basis:\s*([^\s]+) — Statutory basis COUNSEL-UNCONFIRMED"),
        "money.rate.basisLabel",
    ),
    "rate_basis_authority": (
        re.compile(r"Rate Basis Authority:\s*(.+?)\s+Prepared by:"),
        "money.rate.basisAuthority",
    ),
    "self_procured_medical": (
        re.compile(r"Self-Procured Medical:\s*\$([\d,]+)"),
        "money.settlement.grossAmount",
    ),
    "memo_pd_indemnity": (
        re.compile(r"Total PD Indemnity:\s*\$([\d,]+\.\d\d)"),
        "money.rate.pdWeeklyRate",
    ),
    "settlement_range_pd_value": (
        re.compile(r"(?:Conservative|Expected|Optimistic)\s+(\$[\d,]+)\s+\$[\d,]+"),
        "money.rate.pdWeeklyRate",
    ),
    "a_settlement_range_rate_derived_tail": (
        re.compile(
            r"(?:Conservative|Expected|Optimistic)\s+\$[\d,]+\s+\$[\d,]+\s+(\$[\d,]+\s+\$[\d,]+)"
        ),
        "money.settlement.grossAmount",
    ),
    "settlement_comparable_range": (
        re.compile(r"settled in the range of (\$[\d,]+ to \$[\d,]+)"),
        "money.settlement.grossAmount",
    ),
    "release_distribution_gross": (
        re.compile(r"Gross Settlement Amount\s+(\$[\d,]+\.\d\d)"),
        "money.settlement.grossAmount",
    ),
    "release_distribution_fee": (
        re.compile(r"Less: Attorney Fees \(15%\)\s+(\(\$[\d,]+\.\d\d\))"),
        "money.settlement.grossAmount",
    ),
    "release_distribution_costs": (
        re.compile(r"Less: Costs and Expenses\s+(\(\$[\d,]+\.\d\d\))"),
        "money.settlement.grossAmount",
    ),
    "release_distribution_msa": (
        re.compile(r"Less: Medicare Set-Aside Allocation\s+(\(\$[\d,]+\.\d\d\))"),
        "money.settlement.grossAmount",
    ),
    "release_distribution_net": (
        re.compile(r"Net to Applicant\s+(\$[\d,]+\.\d\d)"),
        "money.settlement.grossAmount",
    ),
    "release_fee_prose": (
        re.compile(r"fees in (?:the )?amount of (\$[\d,]+(?:\.\d\d)?) \(15% of gross settlement\)"),
        "money.settlement.grossAmount",
    ),
    "release_prose_settlement_amount": (
        re.compile(r"total sum of (\$[\d,]+(?:\.\d\d)?) as full and complete compromise"),
        "money.settlement.grossAmount",
    ),
    "release_prose_costs": (
        re.compile(r"plus costs of (\$[\d,]+(?:\.\d\d)?)\. These amounts"),
        "money.settlement.grossAmount",
    ),
    "release_settlement_amount": (
        re.compile(r"Settlement Amount:?\s+(\$[\d,]+\.\d\d)"),
        "money.settlement.grossAmount",
    ),
    "stipulations_award": (
        re.compile(r"Permanent Disability \(Gross\)\s+(\$[\d,]+\.\d\d)"),
        "money.settlement.grossAmount",
    ),
    "stipulations_net": (
        re.compile(r"Net Permanent Disability to Applicant\s+(\$[\d,]+\.\d\d)"),
        "money.settlement.grossAmount",
    ),
    "stipulations_self_procured": (
        re.compile(r"Self-Procured Medical Reimbursement\s+(\$[\d,]+\.\d\d)"),
        "money.settlement.grossAmount",
    ),
    "stipulations_gross": (
        re.compile(r"Settlement Gross\s+(\$[\d,]+\.\d\d)"),
        "money.settlement.grossAmount",
    ),
    "stipulations_prose_award": (
        re.compile(r"indemnity is payable in the amount of (\$[\d,]+(?:\.\d\d)?), less"),
        "money.settlement.grossAmount",
    ),
    "stipulations_prose_fee": (
        re.compile(r"which equals (\$[\d,]+(?:\.\d\d)?), to be paid"),
        "money.settlement.grossAmount",
    ),
    "stipulations_prose_net": (
        re.compile(r"payable to applicant is (\$[\d,]+(?:\.\d\d)?)\."),
        "money.settlement.grossAmount",
    ),
    "stipulations_prose_self_procured": (
        re.compile(r"self-procured medical expenses in the amount of (\$[\d,]+(?:\.\d\d)?)"),
        "money.settlement.grossAmount",
    ),
    "stipulations_prose_td_rate": (
        re.compile(r"paid for \d+ weeks at the rate of (\$[\d,]+\.\d\d) per week"),
        "money.rate.tdWeeklyRate",
    ),
    "stipulations_prose_td_total": (
        re.compile(r"per week, totaling (\$[\d,]+\.\d\d), and no further"),
        "money.benefits.tdTotal",
    ),
}


def _registry_governed_money_subtypes() -> frozenset[str]:
    """Bind the controlled document set to the live template registry."""
    registry = fact_aware_templates()
    found = frozenset(
        subtype
        for subtype, template in registry.items()
        if template.__name__ in _GOVERNED_MONEY_TEMPLATE_NAMES
    )
    present_names = {template.__name__ for template in registry.values()}
    assert present_names >= _GOVERNED_MONEY_TEMPLATE_NAMES
    assert found
    return found


def _relative_files(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _path_value(value: Mapping[str, Any], path: str) -> Any:
    node: Any = value
    for part in path.removeprefix("money.").split("."):
        node = node[int(part)] if isinstance(node, list) else node[part]
    return node


def _payment_row_rules(money: Mapping[str, Any]) -> dict[str, tuple[re.Pattern[str], str]]:
    """Exact per-ordinal ledger cells; the printed rows are rate-derived facts."""
    rules: dict[str, tuple[re.Pattern[str], str]] = {
        "td_total_benefit_record": (
            re.compile(r"Total Temporary Disability Paid:\s*\$([\d,]+\.\d\d)"),
            "money.benefits.tdTotal",
        ),
        "pd_total_benefit_record": (
            re.compile(r"Permanent Disability Advances:\s*\$([\d,]+\.\d\d)"),
            "money.benefits.pdTotal",
        ),
    }
    for key, token in (("tdPeriods", "TD"), ("pdAdvances", "PD advance")):
        for ordinal, row in enumerate(money["benefits"][key]):
            start = date.fromisoformat(row["start"]).strftime("%m/%d/%y") if "start" in row else ""
            end = date.fromisoformat(row["end"]).strftime("%m/%d/%y") if "end" in row else ""
            due = date.fromisoformat(row["dateDue"]).strftime("%m/%d/%y")
            period = f"{start}-{end}" if start else due
            paid = (
                date.fromisoformat(row["datePaid"]).strftime("%m/%d/%y")
                if row["datePaid"]
                else "unpaid"
            )
            weeks = f"{Decimal(row['weeks']).normalize():f}"
            prefix = rf"{re.escape(period)}\s+{token}\s+{re.escape(weeks)}\s+"
            path_root = f"money.benefits.{key}.{ordinal}"
            rules[f"{key}_{ordinal}_weekly_rate"] = (
                re.compile(prefix + r"\$([\d,]+\.\d\d)\s+" + re.escape(due)),
                f"{path_root}.weeklyRate",
            )
            rules[f"{key}_{ordinal}_amount"] = (
                re.compile(
                    prefix
                    + r"\$[\d,]+\.\d\d\s+"
                    + re.escape(due)
                    + r"\s+"
                    + re.escape(paid)
                    + r"\s+(?:\d+|-)\s+\$([\d,]+\.\d\d)"
                ),
                f"{path_root}.amount",
            )
    return rules


def _benefit_ledger_rules(money: Mapping[str, Any]) -> dict[str, tuple[re.Pattern[str], str]]:
    """Anchor every rate-derived payment-ledger cell to its truth-manifest row."""
    rules: dict[str, tuple[re.Pattern[str], str]] = {
        "benefit_ledger_td_total": (
            re.compile(r"Temporary Disability Paid To Date\s+(\$[\d,]+\.\d\d)"),
            "money.benefits.tdTotal",
        ),
        "benefit_ledger_pd_total": (
            re.compile(r"Permanent Disability Paid To Date\s+(\$[\d,]+\.\d\d)"),
            "money.benefits.pdTotal",
        ),
    }
    ledger_rows = (
        ("tdPeriods", "Temporary Disability"),
        ("pdAdvances", "Permanent Disability Advance"),
    )
    for key, label in ledger_rows:
        for ordinal, row in enumerate(money["benefits"][key]):
            due = f"{row['start']} to {row['end']}" if key == "tdPeriods" else row["dateDue"]
            paid = row["datePaid"] or "unpaid"
            rules[f"benefit_ledger_{key}_{ordinal}_amount"] = (
                re.compile(
                    rf"{re.escape(label)}\s+{re.escape(due)}\s+{re.escape(paid)}\s+"
                    r"(\$[\d,]+\.\d\d)"
                ),
                f"money.benefits.{key}.{ordinal}.amount",
            )

    penalties = money.get("penalties")
    if penalties is not None:
        for assessment in penalties["assessments"]:
            ordinal = assessment["ordinal"]
            source = "TD period" if assessment["source"] == "td_period" else "PD advance"
            rules[f"benefit_ledger_penalty_{source}_{ordinal}"] = (
                re.compile(
                    rf"§4650\(d\) {re.escape(source)} {ordinal} Increase\s+"
                    r"(Principal \$[\d,]+\.\d\d; operational due \d\d/\d\d/\d\d\s+"
                    r"Statutory due \d\d/\d\d/\d\d; paid \d\d/\d\d/\d\d; "
                    r"\d+ statutory day\(s\) late\s+\$[\d,]+\.\d\d)"
                ),
                f"money.penalties.assessments.{ordinal - 1}.principal",
            )
        rules.update(
            {
                "benefit_ledger_penalty_principal": (
                    re.compile(r"§4650\(d\) Principal Assessed\s+(\$[\d,]+\.\d\d)"),
                    "money.penalties.principalAssessed",
                ),
                "benefit_ledger_penalty_total": (
                    re.compile(
                        r"§4650\(d\) Total Increase\s+(?:COUNSEL-UNCONFIRMED\s+)?"
                        r"(\$[\d,]+\.\d\d)"
                    ),
                    "money.penalties.totalIncrease",
                ),
            }
        )
    return rules


def _changed_governed_rules(
    old_money: Mapping[str, Any],
    current_money: Mapping[str, Any],
    capture_rules: Mapping[str, tuple[re.Pattern[str], str]] = _R109_RENDERED_CAPTURES,
) -> set[str]:
    changed: set[str] = set()
    for name, (_pattern, path) in capture_rules.items():
        try:
            old_value = _path_value(old_money, path)
            current_value = _path_value(current_money, path)
        except (IndexError, KeyError):
            continue
        if old_value != current_value:
            changed.add(name)
    return changed


def _normalize_changed_rate_captures(
    text: str,
    changed_rules: set[str],
    capture_rules: Mapping[str, tuple[re.Pattern[str], str]] = _R109_RENDERED_CAPTURES,
) -> str:
    """Erase only named, anchored R109 values; every other rendered byte stays visible."""
    for name in sorted(changed_rules):
        pattern, _path = capture_rules[name]

        def replace(match: Any, rule: str = name) -> str:
            start, end = match.span(1)
            return (
                match.group(0)[: start - match.start()]
                + f"<R109:{rule}>"
                + match.group(0)[end - match.start() :]
            )

        text = pattern.sub(replace, text)
    return " ".join(text.split())


def _non_rate_projection(value: Any) -> Any:
    """Strip only money/checksums and flat caseload's two R109-derived fields."""
    if isinstance(value, Mapping):
        return {
            key: _non_rate_projection(child)
            for key, child in value.items()
            if key
            not in {
                "money",
                "md5Checksum",
                "fileSize",
                "tdWeeklyRate",
                "settlementGrossAmount",
            }
        }
    if isinstance(value, list):
        return [_non_rate_projection(child) for child in value]
    return value


_R109_EXPECTED_TD_RATES = {
    "steady-earner.truth.json": "767.61",
    "irregular-earner.truth.json": "645.49",
    "new-hire.truth.json": "882.03",
    "two-jobs.truth.json": "783.19",
    "capped-executive.truth.json": "1251.38",
    "neglected-file.truth.json": "534.00",
    "atypical-earner.truth.json": "976.67",
}


def _money_rate_allowlist(payload: Mapping[str, Any]) -> set[str]:
    """Only W1 rate basis and values mechanically derived from it may move."""
    channel = payload["channels"]["money"]
    allowed: set[str] = set()
    root = "$.channels.money"
    for rate_path, basis_keys in (
        (
            f"{root}.wage.rate",
            (
                "label",
                "effectiveFrom",
                "effectiveTo",
                "tdFraction",
                "tdMaxWeekly",
                "tdMinWeekly",
                "pdFraction",
                "pdMaxWeekly",
                "pdMinWeekly",
                "authority",
                "counselConfirmed",
                "source",
            ),
        ),
        (
            f"{root}.published.rate",
            ("basisLabel", "basisAuthority", "counselConfirmed", "basisSource"),
        ),
    ):
        allowed.update(
            {
                f"{rate_path}.tdWeeklyRate",
                f"{rate_path}.tdBound",
                f"{rate_path}.pdWeeklyRate",
                f"{rate_path}.pdBound",
            }
        )
        if rate_path.endswith("wage.rate"):
            allowed.update(f"{rate_path}.basis.{key}" for key in basis_keys)
        else:
            allowed.update(f"{rate_path}.{key}" for key in basis_keys)

    for benefits_path, benefits in (
        (f"{root}.benefits", channel["benefits"]),
        (f"{root}.published.benefits", channel["published"]["benefits"]),
    ):
        allowed.update({f"{benefits_path}.tdTotal", f"{benefits_path}.pdTotal"})
        for index, _row in enumerate(benefits["tdPeriods"]):
            allowed.update(
                {
                    f"{benefits_path}.tdPeriods[{index}].weeklyRate",
                    f"{benefits_path}.tdPeriods[{index}].amount",
                }
            )
        for index, _row in enumerate(benefits["pdAdvances"]):
            allowed.update(
                {
                    f"{benefits_path}.pdAdvances[{index}].weeklyRate",
                    f"{benefits_path}.pdAdvances[{index}].amount",
                }
            )

    for settlement_path, settlement in (
        (f"{root}.settlement", channel.get("settlement")),
        (f"{root}.published.settlement", channel["published"].get("settlement")),
    ):
        if settlement is not None:
            allowed.add(f"{settlement_path}.grossAmount")

    for penalties_path, penalties in (
        (f"{root}.penalties", channel.get("penalties")),
        (f"{root}.published.penalties", channel["published"].get("penalties")),
    ):
        if penalties is not None:
            allowed.update(
                {f"{penalties_path}.totalIncrease", f"{penalties_path}.principalAssessed"}
            )
            for index, _assessment in enumerate(penalties["assessments"]):
                allowed.update(
                    {
                        f"{penalties_path}.assessments[{index}].principal",
                        f"{penalties_path}.assessments[{index}].amount",
                    }
                )
    return allowed


def _artifact_rate_for(doi: date, aww: Decimal) -> dict[str, str]:
    """Independent artifact + exact-fraction computation, never a MoneyFacts result."""
    artifact = json.loads(
        (PACKAGE / "src" / "wc_caseload_engine" / "data" / "benefit-rate-table.json").read_text(
            encoding="utf-8"
        ),
        parse_float=Decimal,
    )
    iso_doi = doi.isoformat()
    era = next(
        row
        for row in artifact["eras"]
        if row["effectiveFrom"] <= iso_doi < row["effectiveTo"]
    )
    raw = (aww * Decimal(2) / Decimal(3)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    td_min, td_max = Decimal(era["tdMinWeeklyRate"]), Decimal(era["tdMaxWeeklyRate"])
    pd_min = min(Decimal(band["minWeeklyRate"]) for band in era["pdBands"])
    pd_max = max(Decimal(band["maxWeeklyRate"]) for band in era["pdBands"])

    def bound(value: Decimal, low: Decimal, high: Decimal) -> tuple[Decimal, str]:
        if value < low:
            return low, "min"
        if value > high:
            return high, "max"
        return value, "unbounded"

    td_rate, td_bound = bound(raw, td_min, td_max)
    pd_rate, pd_bound = bound(raw, pd_min, pd_max)
    return {
        "label": f"doi-{era['sourceLabel'].replace('/', '-')}",
        "effectiveFrom": era["effectiveFrom"],
        "effectiveTo": era["effectiveTo"],
        "tdFraction": "2/3",
        "tdMinWeekly": f"{td_min:.2f}",
        "tdMaxWeekly": f"{td_max:.2f}",
        "pdFraction": "2/3",
        "pdMinWeekly": f"{pd_min:.2f}",
        "pdMaxWeekly": f"{pd_max:.2f}",
        "tdWeeklyRate": f"{td_rate:.2f}",
        "tdBound": td_bound,
        "pdWeeklyRate": f"{pd_rate:.2f}",
        "pdBound": pd_bound,
    }


def _defense_construction_paths(value: Any, path: str = "$") -> tuple[str, ...]:
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key == "defenseConstruction":
                found.append(child_path)
            found.extend(_defense_construction_paths(child, child_path))
    elif isinstance(value, list):
        for child in value:
            found.extend(_defense_construction_paths(child, f"{path}[]"))
    return tuple(found)


def _facts_stream_registry(source: str) -> set[str]:
    """Literal ``_rng(seed, <family>)`` calls are the production registry."""
    tree = ast.parse(source)
    return {
        f"facts:{node.args[1].value}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_rng"
        and len(node.args) > 1
        and isinstance(node.args[1], ast.Constant)
        and isinstance(node.args[1].value, str)
    }


def _rating_absent_seed(eval_type: str) -> Any:
    return parse_case_seed(
        {
            "case_id": f"money-w2-rating-absent-{eval_type}",
            "rng_seed": 44001,
            "injury": {
                "type": "specific",
                "date_of_injury": "2021-06-14",
                "body_parts": [{"part": "lumbar_spine"}],
            },
            "lifecycle": {
                "target_stage": "medical_legal",
                "eval_type": eval_type,
            },
            "scenario": {"treatment": {"status": "ongoing"}},
            "output": {"formats": ["pdf"]},
            "documents": {"format_mix": {"pdf": 1.0}},
        }
    )


def test_r109_controlled_money_showcase_golden_diff_allowlist() -> None:
    """R99: W1-derived digests are the only authorized golden re-record paths."""
    captured = _baseline()["goldenDictionaries"]
    assert tuple(captured) == EXPECTED_GOLDEN_NAMES
    actual = {
        name: json.loads(
            (PACKAGE / "tests" / "golden" / f"{name}.json").read_text(encoding="utf-8")
        )
        for name in EXPECTED_GOLDEN_NAMES
    }
    for name in EXPECTED_GOLDEN_NAMES:
        if name != "money-showcase":
            assert actual[name] == captured[name], name

    changes = _scalar_differences(captured["money-showcase"], actual["money-showcase"])
    allowed = {"$.corpusTree", "$.caseload"}
    for case_id in (
        "atypical-earner",
        "capped-executive",
        "irregular-earner",
        "neglected-file",
        "new-hire",
        "steady-earner",
        "two-jobs",
    ):
        allowed.update(
            {
                f"$.cases.{case_id}.tree",
                f"$.cases.{case_id}.documents",
                f"$.cases.{case_id}.manifest",
                f"$.cases.{case_id}.facts",
            }
        )
    assert set(changes) <= allowed, sorted(set(changes) - allowed)
    assert changes, "R109 must be an explicit, non-vacuous controlled re-record"


@requires_substrate
def test_rating_absence_registry_retirement_and_unrelated_stream_bytes(
    literal_rating_facts: RatingFacts,
) -> None:
    """R101/R111/m23-24 Forms B/C: one guard reports every restored defect."""
    source_path = PACKAGE / "src" / "wc_caseload_engine" / "case_facts.py"
    source = source_path.read_text(encoding="utf-8")
    actual_registry = _facts_stream_registry(source)
    expected_registry = set(EXPECTED_FACT_STREAMS)

    # Form B: compare the production registry to the literal first; every
    # subsequent stream check iterates that literal, never production output.
    problems: list[str] = []
    if actual_registry != expected_registry:
        problems.append(
            f"facts stream registry {sorted(actual_registry)!r}, not {sorted(expected_registry)!r}"
        )
    for stream in EXPECTED_FACT_STREAMS:
        if not stream.startswith("facts:") or stream == "facts:rating":
            problems.append(f"invalid retained literal stream {stream!r}")

    # Form C positive control: one added literal call must be observed as the
    # retired family and nothing else.  It parses only; no recursive call runs.
    planted = source.replace(
        "def _body_parts(seed: CaseSeed) -> list[str]:",
        '_rng(seed, "rating")\n\ndef _body_parts(seed: CaseSeed) -> list[str]:',
        1,
    )
    planted_registry = _facts_stream_registry(planted)
    if planted_registry != expected_registry | {"facts:rating"}:
        problems.append(f"rating-stream positive control missed: {sorted(planted_registry)!r}")

    for eval_type in ("qme", "ame", "none"):
        seed = _rating_absent_seed(eval_type)
        facts = derive_case_facts(seed, build_timeline(seed))
        if not (
            seed.scenario.rating is None
            and facts.rating is None
            and facts.wpi is None
            and facts.pd is None
        ):
            problems.append(
                f"{eval_type}: seed_rating={seed.scenario.rating!r}, "
                f"rating={facts.rating!r}, wpi={facts.wpi!r}, pd={facts.pd!r}"
            )
        if eval_type == "qme":
            unrelated = facts.model_dump(mode="json", exclude={"rating"})
            unrelated["adjuster_letter_types_allowed"] = sorted(
                unrelated["adjuster_letter_types_allowed"]
            )
            raw = json.dumps(
                unrelated,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
            digest = hashlib.sha256(raw).hexdigest()
            if digest != PRE_W2_UNRELATED_FACTS_SHA256:
                problems.append(
                    f"unrelated fact bytes {digest}, not {PRE_W2_UNRELATED_FACTS_SHA256}"
                )

    rated = CaseFacts(rating=literal_rating_facts)
    if not (
        rated.rating is literal_rating_facts
        and rated.wpi == literal_rating_facts.impairments[0].wpi == 10
        and rated.pd == literal_rating_facts.final_pd_percent == 19
    ):
        problems.append(
            f"literal rating projection diverged: rating={rated.rating!r}, "
            f"wpi={rated.wpi!r}, pd={rated.pd!r}"
        )

    assert "rating" in type(_rating_absent_seed("qme").scenario).model_fields
    assert not problems, "\n".join(problems)


@requires_substrate
def test_seven_money_truth_bytes_are_exactly_pre_w2_at_channel_1_1_0(
    money_showcase_truth: dict[str, tuple[bytes, dict[str, Any]]],
) -> None:
    """R99/R105/m23-13: W2 keeps its established wire version and shape."""
    expected = _baseline()["moneyTruthFiles"]
    assert tuple(expected) == EXPECTED_MONEY_TRUTH_FILES
    assert tuple(money_showcase_truth) == EXPECTED_MONEY_TRUTH_FILES
    assert MONEY_CHANNEL_VERSION == "1.1.0"

    problems: list[str] = []
    for filename in EXPECTED_MONEY_TRUTH_FILES:
        _raw, payload = money_showcase_truth[filename]
        channel = payload["channels"]["money"]
        pinned = expected[filename]
        if channel["channelVersion"] != "1.1.0":
            problems.append(
                f"{filename}: channelVersion {channel['channelVersion']!r}, not '1.1.0'"
            )
        if tuple(channel) != tuple(pinned["channelKeys"]):
            problems.append(
                f"{filename}: fields {tuple(channel)!r}, not {tuple(pinned['channelKeys'])!r}"
            )
    assert not problems, "\n".join(problems)


@requires_substrate
def test_pre_w2_literal_reconstruction_matches_all_seven_captured_hashes(
    money_showcase_truth: dict[str, tuple[bytes, dict[str, Any]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R99 Form A: literal W1 plans reproduce every frozen pre-W2 truth byte."""
    expected = _baseline()["moneyTruthFiles"]
    old_truth = _old_money_showcase_truth(monkeypatch)
    for filename in EXPECTED_MONEY_TRUTH_FILES:
        old = old_truth[filename]
        digest = hashlib.sha256(_truth_bytes(old)).hexdigest()
        assert digest == expected[filename]["sha256"], filename


@requires_substrate
def test_r109_rate_derived_truth_diff_is_complete_and_independently_recomputed(
    money_showcase_truth: dict[str, tuple[bytes, dict[str, Any]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R99 Forms A/D: only rate effects move, and each is independently coherent."""
    old_truth = _old_money_showcase_truth(monkeypatch)
    spec = load_caseload_spec(MONEY_SHOWCASE_PATH)
    seeds = {f"{seed.case_id}.truth.json": seed for seed in resolve_caseload(spec)}
    assert tuple(sorted(seeds)) == EXPECTED_MONEY_TRUTH_FILES

    for filename in EXPECTED_MONEY_TRUTH_FILES:
        current = money_showcase_truth[filename][1]
        old = old_truth[filename]
        changes = _scalar_differences(old, current)
        allowed = _money_rate_allowlist(old)
        assert set(changes) <= allowed, f"{filename}: {sorted(set(changes) - allowed)!r}"
        assert changes, f"{filename}: controlled rate correction changed nothing"

        channel = current["channels"]["money"]
        expected_rate = _artifact_rate_for(
            seeds[filename].injury.onset_date,
            Decimal(channel["wage"]["rate"]["averageWeeklyWage"]),
        )
        assert expected_rate["tdWeeklyRate"] == _R109_EXPECTED_TD_RATES[filename]
        assert expected_rate["pdWeeklyRate"] == "290.00"

        wage_rate = channel["wage"]["rate"]
        published_rate = channel["published"]["rate"]
        assert {
            key: wage_rate["basis"][key]
            for key in (
                "label",
                "effectiveFrom",
                "effectiveTo",
                "tdFraction",
                "tdMinWeekly",
                "tdMaxWeekly",
                "pdFraction",
                "pdMinWeekly",
                "pdMaxWeekly",
            )
        } == {
            key: expected_rate[key]
            for key in (
                "label",
                "effectiveFrom",
                "effectiveTo",
                "tdFraction",
                "tdMinWeekly",
                "tdMaxWeekly",
                "pdFraction",
                "pdMinWeekly",
                "pdMaxWeekly",
            )
        }
        assert wage_rate["basis"]["authority"] == (
            "DIR-published benefit-rate table; COUNSEL-UNCONFIRMED."
        )
        assert wage_rate["basis"]["counselConfirmed"] is False
        assert wage_rate["basis"]["source"] == "engine_default_table"
        assert published_rate["basisLabel"] == expected_rate["label"]
        assert published_rate["basisAuthority"] == (
            "DIR-published benefit-rate table; COUNSEL-UNCONFIRMED."
        )
        assert published_rate["counselConfirmed"] is False
        assert published_rate["basisSource"] == "engine_default_table"
        for rate in (wage_rate, published_rate):
            for key in ("tdWeeklyRate", "tdBound", "pdWeeklyRate", "pdBound"):
                assert rate[key] == expected_rate[key]

        for benefits in (channel["benefits"], channel["published"]["benefits"]):
            for rows, rate_key in (
                (benefits["tdPeriods"], "tdWeeklyRate"),
                (benefits["pdAdvances"], "pdWeeklyRate"),
            ):
                total = Decimal("0.00")
                for row in rows:
                    assert row["weeklyRate"] == expected_rate[rate_key]
                    amount = (Decimal(row["weeks"]) * Decimal(row["weeklyRate"])).quantize(
                        Decimal("0.01"), rounding=ROUND_HALF_UP
                    )
                    assert row["amount"] == f"{amount:.2f}"
                    total += amount
                total_key = "tdTotal" if rate_key == "tdWeeklyRate" else "pdTotal"
                if total_key in benefits:
                    assert benefits[total_key] == f"{total:.2f}"

        settlement = channel.get("settlement")
        if settlement is not None:
            old_published = old["channels"]["money"]["published"]
            old_td_total = Decimal(old_published["benefits"]["tdTotal"])
            old_pd_rate = Decimal(old_published["rate"]["pdWeeklyRate"])
            old_gross = Decimal(old_published["settlement"]["grossAmount"])
            old_weeks = [
                weeks
                for weeks in range(20, 121)
                if (old_td_total + old_pd_rate * weeks).quantize(
                    Decimal("1"), rounding=ROUND_HALF_UP
                )
                == old_gross
            ]
            assert len(old_weeks) == 1
            current_gross = (
                Decimal(channel["published"]["benefits"]["tdTotal"])
                + Decimal(expected_rate["pdWeeklyRate"]) * old_weeks[0]
            ).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            assert settlement["grossAmount"] == f"{current_gross:.2f}"
            assert channel["published"]["settlement"]["grossAmount"] == settlement["grossAmount"]

        for benefits, penalties in (
            (channel["benefits"], channel.get("penalties")),
            (channel["published"]["benefits"], channel["published"].get("penalties")),
        ):
            if penalties is None:
                continue
            principals: list[Decimal] = []
            increases: list[Decimal] = []
            for assessment in penalties["assessments"]:
                rows = (
                    benefits["tdPeriods"]
                    if assessment["source"] == "td_period"
                    else benefits["pdAdvances"]
                )
                principal = Decimal(rows[assessment["ordinal"] - 1]["amount"])
                increase = (
                    principal * Decimal(assessment["increaseFraction"])
                ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                assert assessment["principal"] == f"{principal:.2f}"
                assert assessment["amount"] == f"{increase:.2f}"
                principals.append(principal)
                increases.append(increase)
            assert penalties["principalAssessed"] == f"{sum(principals):.2f}"
            assert penalties["totalIncrease"] == f"{sum(increases):.2f}"


def test_r109_rate_capture_normalizer_has_a_live_non_rate_control() -> None:
    """Form C: the normalizer hides only its anchored controlled rate capture."""
    old = "Temporary Disability Rate: $767.65/week Narrative anchor: unchanged."
    current = "Temporary Disability Rate: $767.61/week Narrative anchor: unchanged."
    changed_rules = {"td_rate_statement"}
    assert _normalize_changed_rate_captures(old, changed_rules) == (
        _normalize_changed_rate_captures(current, changed_rules)
    )
    changed_non_rate = "Temporary Disability Rate: $767.61/week Narrative anchor: altered."
    assert _normalize_changed_rate_captures(old, changed_rules) != (
        _normalize_changed_rate_captures(changed_non_rate, changed_rules)
    )


def test_r109_non_rate_projection_has_a_live_nested_control() -> None:
    """Form C: only explicit money/checksum keys are removed from structured files."""
    old = {
        "money": {"rate": "old"},
        "tdWeeklyRate": "767.65",
        "settlementGrossAmount": "102616.00",
        "nested": {"md5Checksum": "old-md5", "fileSize": 10, "stable": "same"},
    }
    current = {
        "money": {"rate": "current"},
        "tdWeeklyRate": "767.61",
        "settlementGrossAmount": "102611.00",
        "nested": {"md5Checksum": "new-md5", "fileSize": 20, "stable": "same"},
    }
    assert _non_rate_projection(old) == _non_rate_projection(current)
    non_rate_drift = copy.deepcopy(current)
    non_rate_drift["nested"]["stable"] = "changed"
    assert _non_rate_projection(old) != _non_rate_projection(non_rate_drift)


@requires_substrate
def test_r109_rendered_money_showcase_changes_only_governed_rate_documents(
    r109_rendered_money_showcase: tuple[Path, Path],
) -> None:
    """R99: rendering keeps every file unless a governed money value actually moved."""
    import yaml

    old_root, current_root = r109_rendered_money_showcase
    old_files = _relative_files(old_root)
    current_files = _relative_files(current_root)
    assert tuple(old_files) == tuple(current_files)

    governed_subtypes = _registry_governed_money_subtypes()
    expected_non_document_changes = {"caseload_manifest.json", "truth/caseload.truth.json"}
    changed_documents = 0
    case_ids = tuple(
        filename.removesuffix(".truth.json") for filename in EXPECTED_MONEY_TRUTH_FILES
    )
    for case_id in case_ids:
        old_case = old_root / case_id
        current_case = current_root / case_id
        old_manifest = json.loads((old_case / "manifest.json").read_text(encoding="utf-8"))
        current_manifest = json.loads(
            (current_case / "manifest.json").read_text(encoding="utf-8")
        )
        old_documents = old_manifest["documents"]
        current_documents = current_manifest["documents"]
        assert _non_rate_projection(old_manifest) == _non_rate_projection(current_manifest)
        old_case_facts = yaml.safe_load((old_case / "case_facts.yaml").read_text(encoding="utf-8"))
        current_case_facts = yaml.safe_load(
            (current_case / "case_facts.yaml").read_text(encoding="utf-8")
        )
        assert _non_rate_projection(old_case_facts) == _non_rate_projection(current_case_facts)
        old_truth = json.loads((old_root / "truth" / f"{case_id}.truth.json").read_text())
        current_truth = json.loads(
            (current_root / "truth" / f"{case_id}.truth.json").read_text()
        )
        assert _non_rate_projection(old_truth) == _non_rate_projection(current_truth)
        assert len(old_documents) == len(current_documents)
        assert [
            (
                document["filename"],
                document["subtype"],
                document["documentDate"],
                document["format"],
            )
            for document in old_documents
        ] == [
            (
                document["filename"],
                document["subtype"],
                document["documentDate"],
                document["format"],
            )
            for document in current_documents
        ]
        expected_non_document_changes.update(
            {
                f"{case_id}/case_facts.yaml",
                f"{case_id}/manifest.json",
                f"truth/{case_id}.truth.json",
            }
        )

        old_money = old_truth["channels"]["money"]["published"]
        current_money = current_truth["channels"]["money"]["published"]
        payment_rules = _payment_row_rules(old_money)
        benefit_ledger_rules = _benefit_ledger_rules(old_money)
        rendered_rules = {
            **_R109_RENDERED_CAPTURES,
            **payment_rules,
            **benefit_ledger_rules,
        }
        changed_rules = _changed_governed_rules(old_money, current_money, rendered_rules)
        assert changed_rules, case_id
        for document in current_documents:
            filename = document["filename"]
            relative = f"{case_id}/documents/{filename}"
            if old_files[relative] == current_files[relative]:
                continue
            changed_documents += 1
            assert document["subtype"] in governed_subtypes, (case_id, document["subtype"])
            old_text = " ".join(
                extract_text(old_case / "documents" / filename, document["format"]).split()
            )
            current_text = " ".join(
                extract_text(current_case / "documents" / filename, document["format"]).split()
            )
            coherence_rules = {
                **GOVERNED_ON_THE_PAGE,
                **payment_rules,
            }
            old_result = sweep({document["subtype"]: old_text}, old_money, coherence_rules)
            current_result = sweep(
                {document["subtype"]: current_text}, current_money, coherence_rules
            )
            assert old_result.surfaces, (case_id, filename, "old document has no governed money")
            assert current_result.surfaces, (
                case_id,
                filename,
                "current document has no governed money",
            )
            assert not old_result.disagreements, old_result.describe()
            assert not current_result.disagreements, current_result.describe()
            assert {surface.fact for surface in current_result.surfaces} & changed_rules, (
                case_id,
                filename,
                changed_rules,
            )
            assert _normalize_changed_rate_captures(old_text, changed_rules, rendered_rules) == (
                _normalize_changed_rate_captures(current_text, changed_rules, rendered_rules)
            ), (case_id, filename)

    assert changed_documents, "R109 rendered no governed rate document"
    for relative in ("caseload_manifest.json", "truth/caseload.truth.json"):
        old_structured = json.loads((old_root / relative).read_text(encoding="utf-8"))
        current_structured = json.loads((current_root / relative).read_text(encoding="utf-8"))
        assert _non_rate_projection(old_structured) == _non_rate_projection(current_structured)
    for relative, old_bytes in old_files.items():
        if "/documents/" not in relative and old_bytes != current_files[relative]:
            assert relative in expected_non_document_changes, relative


@requires_substrate
def test_defense_absent_baseline_has_a_live_one_input_positive_neighbor(
    money_showcase_truth: dict[str, tuple[bytes, dict[str, Any]]],
) -> None:
    """R105/m23-25 Form C: absence plus a one-field planted neighbor."""
    baseline_filename = "new-hire.truth.json"
    _raw, payload = money_showcase_truth[baseline_filename]
    channel = payload["channels"]["money"]
    assert _defense_construction_paths(channel) == ()

    positive = copy.deepcopy(channel)
    positive["defenseConstruction"] = {"method": "fabricated"}
    assert _defense_construction_paths(positive) == ("$.defenseConstruction",)
