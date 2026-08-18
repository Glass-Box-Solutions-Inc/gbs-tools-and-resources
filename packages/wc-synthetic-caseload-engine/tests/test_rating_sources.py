"""R27/R28/R44/R82/R83 literal oracles for the January 2005 PDRS bundle."""

from __future__ import annotations

import hashlib
import json
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).parents[1]
DATA_ROOT = PACKAGE_ROOT / "src" / "wc_caseload_engine" / "data"
TABLES_PATH = DATA_ROOT / "pdrs_2005_tables.json"
SECTION4_PATH = DATA_ROOT / "pdrs_2005_section4_matrix.json"
SECTION4_META_PATH = DATA_ROOT / "pdrs_2005_section4_matrix.meta.json"
DFEC_MIRROR_PATH = Path(__file__).with_name("fixtures") / (
    "dfec_1_4_table.pd_calculator.json"
)

OFFICIAL_TABLES_SHA256 = (
    "a7177da9a12cda090a767f3dccd9e604f3686ba2ded7b0ff36e3dae6e6ca2791"
)
OFFICIAL_SECTION4_SHA256 = (
    "23a56ded69f1cffd6ae9c2dc613c52d2e5750a9bd432a86fd5d00d50f3419e83"
)
OFFICIAL_SECTION4_META_SHA256 = (
    "7847c7410dc348de7092fd1283077c1645192b36e01b7e0ee5230cc3cacb52e6"
)
OFFICIAL_PDF_SHA256 = (
    "cfabf43b57533b90133f71aecf882c8b17a5dad3659db7aea6e810728f664201"
)
OFFICIAL_EXTRACTED_TEXT_SHA256 = (
    "827d66440bc9161743aa6add355c823a6d7d5913162df140f38bc871f83f47b1"
)

DFEC_BACKEND_FILE_SHA256 = (
    "1633ad1a7c10bec6f2e9ce3a4d3c8dd23b55cfde200c7eae5036ed19ce62f7e7"
)
DFEC_DECLARATION_SHA256 = (
    "6738db05d1822fc14fe2067ed1399f6075368afa49c88a7c48b90251f6285c08"
)
DFEC_PROJECTION_SHA256 = (
    "69cc49b6051a0bd766b17e26a21a6928748db7c939b3fa7bcea3138fa5ad61ce"
)

EXPECTED_GROUPS = (
    "110",
    "111",
    "112",
    "120",
    "210",
    "211",
    "212",
    "213",
    "214",
    "220",
    "221",
    "230",
    "240",
    "250",
    "251",
    "290",
    "310",
    "311",
    "320",
    "321",
    "322",
    "330",
    "331",
    "332",
    "340",
    "341",
    "350",
    "351",
    "360",
    "370",
    "380",
    "390",
    "420",
    "430",
    "460",
    "470",
    "480",
    "481",
    "482",
    "490",
    "491",
    "492",
    "493",
    "560",
    "590",
)
EXPECTED_VARIANTS = ("C", "D", "E", "F", "G", "H", "I", "J")


def _official_json() -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    """Read all official artifacts directly, without importing production rating code."""
    return (
        json.loads(TABLES_PATH.read_bytes()),
        json.loads(SECTION4_PATH.read_bytes()),
        json.loads(SECTION4_META_PATH.read_bytes()),
    )


def test_r27_official_bytes_and_pdf_text_provenance_are_literal_pins() -> None:
    payloads = {
        TABLES_PATH: OFFICIAL_TABLES_SHA256,
        SECTION4_PATH: OFFICIAL_SECTION4_SHA256,
        SECTION4_META_PATH: OFFICIAL_SECTION4_META_SHA256,
    }
    for path, expected_digest in payloads.items():
        raw = path.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == expected_digest
        assert isinstance(json.loads(raw), dict)

    meta = json.loads(SECTION4_META_PATH.read_bytes())
    assert meta["source_url"] == "https://www.dir.ca.gov/dwc/pdr.pdf"
    assert meta["sha256"] == OFFICIAL_PDF_SHA256
    assert OFFICIAL_EXTRACTED_TEXT_SHA256 == (
        "827d66440bc9161743aa6add355c823a6d7d5913162df140f38bc871f83f47b1"
    )


def test_r28_official_table_dimensions_keysets_and_classifications() -> None:
    tables, _, _ = _official_json()
    assert set(tables) == {"fec", "imp", "occ", "age", "groups"}

    fec = tables["fec"]
    assert isinstance(fec, dict)
    assert len(fec) == 800
    assert set(fec) == {
        f"{rank}|{rating}" for rank in range(1, 9) for rating in range(1, 101)
    }
    assert all(type(value) is int and 1 <= value <= 100 for value in fec.values())

    impairment = tables["imp"]
    assert isinstance(impairment, dict)
    assert len(impairment) == 215
    assert all(
        isinstance(value, list)
        and len(value) == 2
        and type(value[0]) is int
        and 1 <= value[0] <= 8
        and isinstance(value[1], str)
        and value[1]
        for value in impairment.values()
    )

    occupational = tables["occ"]
    assert isinstance(occupational, dict)
    assert set(occupational) == {str(rating) for rating in range(101)}
    assert tuple("CDEFGHIJ") == EXPECTED_VARIANTS
    assert sum(len(row) for row in occupational.values()) == 808
    assert {len(row) for row in occupational.values()} == {len(EXPECTED_VARIANTS)}
    assert all(
        type(value) is int and 0 <= value <= 100
        for row in occupational.values()
        for value in row
    )

    age = tables["age"]
    assert isinstance(age, dict)
    assert set(age) == {str(rating) for rating in range(1, 101)}
    assert sum(len(row) for row in age.values()) == 1_000
    assert {len(row) for row in age.values()} == {10}
    assert all(
        type(value) is int and 1 <= value <= 100
        for row in age.values()
        for value in row
    )


def test_r83_exact_45_group_tuple_and_every_row_keyset() -> None:
    tables, matrix, _ = _official_json()
    groups = tables["groups"]
    assert isinstance(groups, list)
    assert tuple(groups) == EXPECTED_GROUPS
    assert len(groups) == 45
    assert all(isinstance(row, dict) and tuple(row) == EXPECTED_GROUPS for row in matrix.values())


def test_r83_section4_rows_cells_values_and_dual_parse_literal_oracle() -> None:
    _, matrix, meta = _official_json()
    assert len(matrix) == 113
    assert len(set(matrix)) == 113
    assert sum(len(row) for row in matrix.values()) == 5_085
    assert {len(row) for row in matrix.values()} == {45}
    assert {
        value for row in matrix.values() for value in row.values()
    } <= set("CDEFGHIJ")

    cross_check = meta["cross_check"]
    assert isinstance(cross_check, dict)
    assert {
        "rows": cross_check["rows"],
        "columns": cross_check["columns"],
        "cells": cross_check["cells"],
        "disagreements": cross_check["disagreements"],
        "agreement_rate": cross_check["agreement_rate"],
        "visually_resolved_cells": cross_check["visually_resolved_cells"],
    } == {
        "rows": 113,
        "columns": 45,
        "cells": 5_085,
        "disagreements": 0,
        "agreement_rate": 1.0,
        "visually_resolved_cells": 0,
    }


def test_r28_dfec_1_4_mirror_is_non_authoritative_and_policy_exact() -> None:
    raw = DFEC_MIRROR_PATH.read_bytes()
    mirror = json.loads(raw)
    assert hashlib.sha256(raw).hexdigest() == DFEC_PROJECTION_SHA256
    assert len(raw) == 816
    assert set(mirror) == {str(wpi) for wpi in range(1, 101)}
    assert len(mirror) == 100
    assert DFEC_BACKEND_FILE_SHA256 == (
        "1633ad1a7c10bec6f2e9ce3a4d3c8dd23b55cfde200c7eae5036ed19ce62f7e7"
    )
    assert DFEC_DECLARATION_SHA256 == (
        "6738db05d1822fc14fe2067ed1399f6075368afa49c88a7c48b90251f6285c08"
    )

    expected = {
        str(wpi): min(
            100,
            int(
                (Decimal(wpi) * Decimal("1.4")).quantize(
                    Decimal("1"), rounding=ROUND_HALF_UP
                )
            ),
        )
        for wpi in range(1, 101)
    }
    assert mirror == expected
    assert min(int(key) for key, value in mirror.items() if value == 100) == 72
    assert all(mirror[str(wpi)] == 100 for wpi in range(72, 101))
    assert sum(mirror[key] != value for key, value in expected.items()) == 0
    assert mirror["2"] == 3
    assert int(Decimal(2) * Decimal("1.4")) == 2


def test_r44_binding_is_the_literal_official_contract_with_no_mirror_fields() -> None:
    expected = {
        "edition": "January 2005",
        "source_url": "https://www.dir.ca.gov/dwc/pdr.pdf",
        "pdf_sha256": "cfabf43b57533b90133f71aecf882c8b17a5dad3659db7aea6e810728f664201",
        "extracted_text_sha256": (
            "827d66440bc9161743aa6add355c823a6d7d5913162df140f38bc871f83f47b1"
        ),
        "tables_sha256": (
            "a7177da9a12cda090a767f3dccd9e604f3686ba2ded7b0ff36e3dae6e6ca2791"
        ),
        "section4_sha256": (
            "23a56ded69f1cffd6ae9c2dc613c52d2e5750a9bd432a86fd5d00d50f3419e83"
        ),
        "section4_meta_sha256": (
            "7847c7410dc348de7092fd1283077c1645192b36e01b7e0ee5230cc3cacb52e6"
        ),
        "counsel_status": "PDRS_2005_SOURCE_VERIFIED_POST2013_FACTOR_COUNSEL_RULED",
    }
    from wc_caseload_engine.rating_sources import RatingScheduleBinding

    assert RatingScheduleBinding().model_dump() == expected
    assert set(RatingScheduleBinding.model_fields) == set(expected)
    assert all("calculator" not in field.casefold() for field in expected)


def test_production_loader_accepts_only_the_complete_official_bundle() -> None:
    from wc_caseload_engine.rating_sources import load_rating_source_bundle

    bundle = load_rating_source_bundle()
    assert len(bundle.fec_lookup) == 800
    assert len(bundle.impairment_register) == 215
    assert len(bundle.occupational_adjustment) == 101
    assert sum(len(row) for row in bundle.occupational_adjustment.values()) == 808
    assert len(bundle.age_adjustment) == 100
    assert sum(len(row) for row in bundle.age_adjustment.values()) == 1_000
    assert bundle.occupational_groups == EXPECTED_GROUPS
    assert len(bundle.section4_matrix) == 113
    assert sum(len(row) for row in bundle.section4_matrix.values()) == 5_085


def test_production_loader_rejects_pdf_provenance_sha_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from wc_caseload_engine import rating_sources

    monkeypatch.setattr(rating_sources, "PDRS_2005_PDF_SHA256", "0" * 64)
    with pytest.raises(rating_sources.RatingSourceError) as raised:
        rating_sources.load_rating_source_bundle()
    assert str(raised.value) == "RATING_SOURCE_BUNDLE_MISMATCH"


def test_production_loader_rejects_tables_digest_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    from wc_caseload_engine import rating_sources

    monkeypatch.setattr(rating_sources, "PDRS_2005_TABLES_SHA256", "0" * 64)
    with pytest.raises(rating_sources.RatingSourceError) as raised:
        rating_sources.load_rating_source_bundle()
    assert str(raised.value) == "RATING_SOURCE_BUNDLE_MISMATCH"


def test_every_official_artifact_digest_failure_uses_the_registered_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from wc_caseload_engine import rating_sources

    for constant in (
        "PDRS_2005_SECTION4_SHA256",
        "PDRS_2005_SECTION4_META_SHA256",
    ):
        with monkeypatch.context() as context:
            context.setattr(rating_sources, constant, "0" * 64)
            with pytest.raises(rating_sources.RatingSourceError) as raised:
                rating_sources.load_rating_source_bundle()
            assert raised.value.code == "RATING_SOURCE_BUNDLE_MISMATCH"
            assert str(raised.value) == "RATING_SOURCE_BUNDLE_MISMATCH"
            assert raised.value.code in rating_sources.RATING_ERROR_CODES


def test_production_contains_no_test_mirror_loader_or_binding_field() -> None:
    # R27's prohibition covers production generally, so the sweep walks every
    # shipped module, not just rating_sources.py. The vendored meta.json is
    # data, not code, and is digest-pinned separately.
    for module in sorted(
        (PACKAGE_ROOT / "src" / "wc_caseload_engine").rglob("*.py")
    ):
        source = module.read_text(encoding="utf-8")
        assert "dfec_1_4_table.pd_calculator.json" not in source, module.name
        assert DFEC_PROJECTION_SHA256 not in source, module.name
        assert DFEC_BACKEND_FILE_SHA256 not in source, module.name
    assert DFEC_DECLARATION_SHA256 not in source
