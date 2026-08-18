"""R109: the exact DIR table and exact two-thirds rate seam."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from decimal import Decimal
from fractions import Fraction
from itertools import pairwise

import pytest

from wc_caseload_engine.money import (
    MONEY_ERROR_CODES,
    MONEY_RATE_UNSUPPORTED_DOI,
    RATE_TABLE_ARTIFACT_PATH,
    RATE_TABLE_ERAS,
    UNCONFIRMED_RATE_TABLE,
    WEEKLY_BENEFIT_FRACTION,
    MoneyRateError,
    _apply_benefit_fraction,
    compute_comp_rate,
    rate_basis_for,
)


def test_r109_artifact_digest_shape_and_complete_half_open_windows() -> None:
    raw = RATE_TABLE_ARTIFACT_PATH.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == (
        "7a873d8048bcc9ae169528aec1f8b2e0ed12ac04ccc71add2de4e402bef3fc73"
    )
    payload = json.loads(raw)
    assert set(payload) == {
        "datasetId",
        "jurisdiction",
        "datasetVersion",
        "source",
        "coverage",
        "citations",
        "reviewStatus",
        "reviewNotes",
        "eras",
    }
    assert payload["datasetId"] == "ca_wc_td_pd_sjdb"
    assert payload["datasetVersion"] == "2026-07-30.1"
    assert payload["reviewStatus"] == "unverified"
    assert set(payload["source"]) == {
        "publisher",
        "title",
        "url",
        "retrievedAt",
        "snapshotFile",
        "snapshotSha256",
    }
    assert payload["source"]["url"] == "https://www.dir.ca.gov/dwc/WorkersCompensationBenefits.htm"
    assert payload["source"]["snapshotSha256"] == (
        "71d07c81b45e1a96cecdcce899ee5c6c3226b0aeaefe686327583f68109c5f2f"
    )
    assert set(payload["coverage"]) == {
        "dateOfInjuryFrom",
        "dateOfInjuryTo",
        "belowCoverageReason",
        "atOrAboveCoverageReason",
    }
    assert set(payload["citations"]) == {
        "temporaryDisability",
        "permanentDisability",
        "supplementalJobDisplacement",
    }
    assert len(payload["eras"]) == len(RATE_TABLE_ERAS) == len(UNCONFIRMED_RATE_TABLE) == 17
    for left, right in pairwise(RATE_TABLE_ERAS):
        assert left.effective_to == right.effective_from
    assert RATE_TABLE_ERAS[0].effective_from == date(2010, 1, 1)
    assert RATE_TABLE_ERAS[-1].effective_to == date(2027, 1, 1)
    pre_2013 = (
            (1, 14, "130.00", "230.00", "4000.00"),
            (15, 25, "130.00", "230.00", "6000.00"),
            (26, 49, "130.00", "230.00", "8000.00"),
            (50, 99, "130.00", "270.00", "10000.00"),
    )
    era_2013 = (
            (1, 54, "160.00", "230.00", "6000.00"),
            (55, 69, "160.00", "270.00", "6000.00"),
            (70, 99, "160.00", "290.00", "6000.00"),
    )
    era_2014 = (
            (1, 54, "160.00", "290.00", "6000.00"),
            (55, 69, "160.00", "290.00", "6000.00"),
            (70, 99, "160.00", "290.00", "6000.00"),
    )
    for raw_era, era in zip(payload["eras"], RATE_TABLE_ERAS, strict=True):
        assert era.effective_from.isoformat() == raw_era["effectiveFrom"]
        assert era.effective_to.isoformat() == raw_era["effectiveTo"]
        assert era.min_average_weekly_earnings == Decimal(str(raw_era["minAverageWeeklyEarnings"]))
        assert era.max_average_weekly_earnings == Decimal(str(raw_era["maxAverageWeeklyEarnings"]))
        assert era.td_min_weekly_rate == Decimal(str(raw_era["tdMinWeeklyRate"]))
        assert era.td_max_weekly_rate == Decimal(str(raw_era["tdMaxWeeklyRate"]))
        assert era.basis.effective_from == era.effective_from
        assert era.basis.effective_to == era.effective_to
        assert era.basis.td_fraction == WEEKLY_BENEFIT_FRACTION
        assert era.basis.pd_fraction == WEEKLY_BENEFIT_FRACTION
        expected = (
            pre_2013
            if era.effective_from.year < 2013
            else era_2013
            if era.effective_from.year == 2013
            else era_2014
        )
        assert tuple(
            (
                b.rating_from,
                b.rating_to,
                str(b.min_weekly_rate),
                str(b.max_weekly_rate),
                str(b.sjdb_voucher),
            )
            for b in era.pd_bands
        ) == expected
        assert era.pd_bands[0].rating_from == 1
        assert all(
            left.rating_to + 1 == right.rating_from
            for left, right in pairwise(era.pd_bands)
        )
        assert era.pd_bands[-1].rating_to == 99
    expected_era_keys = {
        "effectiveFrom",
        "effectiveTo",
        "sourceLabel",
        "minAverageWeeklyEarnings",
        "maxAverageWeeklyEarnings",
        "tdMinWeeklyRate",
        "tdMinDerivation",
        "tdMaxWeeklyRate",
        "tdMaxDerivation",
        "pdBands",
    }
    assert all(set(era) == expected_era_keys for era in payload["eras"])
    assert all(
        set(band) == {"ratingFrom", "ratingTo", "minWeeklyRate", "maxWeeklyRate", "sjdbVoucher"}
        for era in payload["eras"]
        for band in era["pdBands"]
    )


def test_r109_dir_twenty_independent_two_thirds_checks() -> None:
    # Hand-transcribed from KB-167's DIR_PUBLISHED literals (17 minima + 3 maxima).
    checks = (
        ("2010-01-01", "222", "148.00"),
        ("2011-01-01", "222", "148.00"),
        ("2012-01-01", "227.36", "151.57"),
        ("2013-01-01", "240", "160.00"),
        ("2014-01-01", "241.78", "161.19"),
        ("2015-01-01", "248.24", "165.49"),
        ("2016-01-01", "253.89", "169.26"),
        ("2017-01-01", "263.82", "175.88"),
        ("2018-01-01", "273.44", "182.29"),
        ("2019-01-01", "281.57", "187.71"),
        ("2020-01-01", "292.36", "194.91"),
        ("2021-01-01", "305.16", "203.44"),
        ("2022-01-01", "346.42", "230.95"),
        ("2023-01-01", "364.29", "242.86"),
        ("2024-01-01", "364.29", "242.86"),
        ("2025-01-01", "378.05", "252.03"),
        ("2026-01-01", "396.92", "264.61"),
    )
    for from_date, awe, td_min in checks:
        era = next(e for e in RATE_TABLE_ERAS if e.effective_from.isoformat() == from_date)
        assert (Decimal(awe) * 2 / 3).quantize(Decimal("0.01")) == Decimal(td_min)
        assert era.td_min_weekly_rate == Decimal(td_min)
    maxima = (
        ("2010-01-01", "1480.04", "986.69"),
        ("2011-01-01", "1480.04", "986.69"),
        ("2012-01-01", "1515.75", "1010.50"),
    )
    for from_date, awe, td_max in maxima:
        era = next(e for e in RATE_TABLE_ERAS if e.effective_from.isoformat() == from_date)
        assert (Decimal(awe) * 2 / 3).quantize(Decimal("0.01")) == Decimal(td_max)
        assert era.td_max_weekly_rate == Decimal(td_max)

    anchors = {
        2010: ("148.00", "986.69"),
        2012: ("151.57", "1010.50"),
        2013: ("160.00", "1066.72"),
        2018: ("182.29", "1215.27"),
        2022: ("230.95", "1539.71"),
        2023: ("242.86", "1619.15"),
        2025: ("252.03", "1680.29"),
        2026: ("264.61", "1764.11"),
    }
    for year, (td_min, td_max) in anchors.items():
        era = next(e for e in RATE_TABLE_ERAS if e.effective_from.year == year)
        assert (str(era.td_min_weekly_rate), str(era.td_max_weekly_rate)) == (td_min, td_max)


def test_r109_fraction_literal_and_independent_2428_72_oracle() -> None:
    assert Fraction(2, 3) == WEEKLY_BENEFIT_FRACTION
    assert not isinstance(WEEKLY_BENEFIT_FRACTION, (float, Decimal))
    raw = _apply_benefit_fraction(Decimal("2428.72"), WEEKLY_BENEFIT_FRACTION)
    assert raw == Decimal("1619.146666666666666666666667")
    rate = compute_comp_rate(Decimal("2428.72"), rate_basis_for(date(2023, 1, 1)))
    assert rate.td_weekly_rate == Decimal("1619.15")
    assert (Decimal("2428.72") * Decimal("0.6667")).quantize(Decimal("0.01")) == Decimal("1619.23")


@pytest.mark.parametrize("doi", (date(2009, 12, 31), date(2027, 1, 1)))
def test_r109_rate_seam_fails_closed_with_stable_code(doi: date) -> None:
    with pytest.raises(MoneyRateError) as raised:
        rate_basis_for(doi)
    assert raised.value.code == MONEY_RATE_UNSUPPORTED_DOI
    assert MONEY_RATE_UNSUPPORTED_DOI in str(raised.value)
    assert MONEY_RATE_UNSUPPORTED_DOI in MONEY_ERROR_CODES


def test_r109_rate_seam_positive_boundary_controls() -> None:
    assert rate_basis_for(date(2010, 1, 1)) is UNCONFIRMED_RATE_TABLE[0]
    assert rate_basis_for(date(2026, 12, 31)) is UNCONFIRMED_RATE_TABLE[-1]
