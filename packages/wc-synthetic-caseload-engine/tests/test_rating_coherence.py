"""R86 independent artifact-to-production rating coherence oracles."""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import shutil
import subprocess
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

import pytest

PACKAGE_ROOT = Path(__file__).parents[1]
DATA_ROOT = PACKAGE_ROOT / "src" / "wc_caseload_engine" / "data"
TABLES_PATH = DATA_ROOT / "pdrs_2005_tables.json"
SECTION4_PATH = DATA_ROOT / "pdrs_2005_section4_matrix.json"
DFEC_MIRROR_PATH = Path(__file__).with_name("fixtures") / (
    "dfec_1_4_table.pd_calculator.json"
)
# AJC-64 item 0b (round-1 finding F5): moved into package data so the artifact
# this module parses is the one PDRS_VENDORED_ARTIFACTS pins and the one
# tools/pdrs_extract.py derives from the vendored source PDF.
EXTRACTED_TEXT_PATH = DATA_ROOT / "pdrs-2005-extracted-text.txt"

TABLES_SHA256 = "a7177da9a12cda090a767f3dccd9e604f3686ba2ded7b0ff36e3dae6e6ca2791"
SECTION4_SHA256 = "23a56ded69f1cffd6ae9c2dc613c52d2e5750a9bd432a86fd5d00d50f3419e83"
EXTRACTED_TEXT_SHA256 = (
    "827d66440bc9161743aa6add355c823a6d7d5913162df140f38bc871f83f47b1"
)
DFEC_BACKEND_FILE_SHA256 = (
    "1633ad1a7c10bec6f2e9ce3a4d3c8dd23b55cfde200c7eae5036ed19ce62f7e7"
)
DFEC_DECLARATION_SHA256 = (
    "6738db05d1822fc14fe2067ed1399f6075368afa49c88a7c48b90251f6285c08"
)
DFEC_COMPACT_JSON_SHA256 = (
    "69cc49b6051a0bd766b17e26a21a6928748db7c939b3fa7bcea3138fa5ad61ce"
)

AGE_BANDS = (
    "<=21",
    "22-26",
    "27-31",
    "32-36",
    "37-41",
    "42-46",
    "47-51",
    "52-56",
    "57-61",
    ">=62",
)
VARIANTS = tuple("CDEFGHIJ")
R47_CARRIERS = frozenset(
    {
        "IMPAIRMENT_RATING_WORKSHEET",
        "PD_RATING_CALCULATION_WORKSHEET",
        "PD_RATING_CONVERSION",
    }
)
R49_RATING_HOOKS = frozenset(
    {
        "ogilvie",
        "almaraz_guzman",
        "escobedo",
        "benson",
        "kite",
        "lc4664_prior_award",
    }
)
R52_FORBIDDEN_FAMILIES = {
    "apportioned_pd_dollars": "Apportioned PD dollars: $",
    "benson_split": "Benson split:",
    "lc4664_offset": "§4664 offset:",
}
RATING_ROW_PATTERN = re.compile(
    r"(?P<impairment_number>\d{2}\.\d{2}\.\d{2}\.\d{2}) - "
    r"(?P<wpi>\d+) - \[(?P<adjustment>[^\]]+)\]"
    r"(?P<schedule_adjusted>\d+) - "
    r"(?P<occupation_group>\d{3})(?P<variant>[C-J]) - "
    r"(?P<occupation_adjusted>\d+) - (?P<age_adjusted>\d+)%"
)
RATING_SCAN_ROW_PATTERN = re.compile(
    r"(?P<impairment_number>\d{2}\.\d{2}\.\d{2}\.\d{2})\s*[-=]\s*"
    r"(?P<wpi>\d+)\s*[-=]\s*\[(?P<adjustment>[^\]]+)\]"
    r"(?P<schedule_adjusted>\d+)\s*[-=]\s*"
    r"(?P<occupation_group>\d{3})(?P<variant>[C-J])\s*[-=]\s*"
    r"(?P<occupation_adjusted>\d+)\s*[-=]\s*(?P<age_adjusted>\d+)%"
)


def _read_json(path: Path, expected_digest: str) -> dict[str, Any]:
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == expected_digest
    value = json.loads(raw)
    assert isinstance(value, dict)
    return value


def _dfec_policy_expectations() -> dict[str, int]:
    expected = {
        str(wpi): min(
            100,
            int(
                (Decimal(wpi) * Decimal("1.4")).to_integral_value(
                    rounding=ROUND_HALF_UP
                )
            ),
        )
        for wpi in range(1, 101)
    }
    cells = len(expected)
    assert cells == 100
    assert expected["8"] == 11
    assert expected["71"] == 99
    assert expected["72"] == 100
    assert min(int(key) for key, value in expected.items() if value == 100) == 72
    assert all(expected[str(wpi)] == 100 for wpi in range(72, 101))
    return expected


def _production_dfec_mismatches(expected: dict[str, int]) -> list[tuple[int, int, int]]:
    from wc_caseload_engine.rating import dfec_adjusted_rating

    return [
        (wpi, expected[str(wpi)], dfec_adjusted_rating(wpi))
        for wpi in range(1, 101)
        if dfec_adjusted_rating(wpi) != expected[str(wpi)]
    ]


def test_r86_dfec_mirror_then_policy_then_production_then_mirror() -> None:
    """m23-31: establish both independent sources before comparing either."""
    raw = DFEC_MIRROR_PATH.read_bytes()
    mirror = json.loads(raw)
    assert DFEC_BACKEND_FILE_SHA256 == (
        "1633ad1a7c10bec6f2e9ce3a4d3c8dd23b55cfde200c7eae5036ed19ce62f7e7"
    )
    assert DFEC_DECLARATION_SHA256 == (
        "6738db05d1822fc14fe2067ed1399f6075368afa49c88a7c48b90251f6285c08"
    )
    assert hashlib.sha256(raw).hexdigest() == DFEC_COMPACT_JSON_SHA256
    assert set(mirror) == {str(wpi) for wpi in range(1, 101)}
    assert len(mirror) == 100
    assert min(int(key) for key, value in mirror.items() if value == 100) == 72
    assert mirror["8"] == 11
    assert mirror["71"] == 99
    assert mirror["72"] == 100
    assert all(mirror[str(wpi)] == 100 for wpi in range(72, 101))

    expected = _dfec_policy_expectations()
    production_mismatches = _production_dfec_mismatches(expected)
    assert len(expected) == 100
    assert len(production_mismatches) == 0

    mirror_mismatches = [
        (wpi, expected[str(wpi)], mirror[str(wpi)])
        for wpi in range(1, 101)
        if mirror[str(wpi)] != expected[str(wpi)]
    ]
    assert len(mirror_mismatches) == 0


def test_r86_dfec_round_half_up_sweeps_all_100_values() -> None:
    """m23-52: ROUND_DOWN diverges from the independently fixed policy."""
    expected = _dfec_policy_expectations()
    assert len(_production_dfec_mismatches(expected)) == 0


def test_r86_dfec_cap_sweeps_all_100_values() -> None:
    """m23-53: removing the cap diverges at every WPI from 72 onward."""
    expected = _dfec_policy_expectations()
    assert len(_production_dfec_mismatches(expected)) == 0


def test_r86_post2013_never_reads_a_calculator_mirror(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from wc_caseload_engine.rating import RatingScenario, derive_rating_facts
    from wc_caseload_engine.rating_sources import load_rating_source_bundle

    source = load_rating_source_bundle()

    def forbid_file_access(_path: Path) -> bytes:
        raise AssertionError("2013+ attempted calculator-mirror file access")

    monkeypatch.setattr(Path, "read_bytes", forbid_file_access)
    facts = derive_rating_facts(
        RatingScenario.model_validate(
            {
                "schedule": "pdrs_2005",
                "occupation_group": "470",
                "impairments": [
                    {
                        "id": "cervical",
                        "body_part": "cervical_spine",
                        "impairment_number": "15.01.02.02",
                        "wpi": 8,
                    }
                ],
                "combination_method": "single",
            }
        ),
        date_of_injury=date(2013, 6, 15),
        birth_date=date(1983, 6, 15),
        occupation_title="Warehouse worker",
        bundle=source,
    )
    assert facts.impairments[0].schedule_adjusted == 11


def test_r86_all_official_source_cells_equal_production_lookups() -> None:
    tables = _read_json(TABLES_PATH, TABLES_SHA256)
    matrix = _read_json(SECTION4_PATH, SECTION4_SHA256)
    fec = tables["fec"]
    occupational = tables["occ"]
    age = tables["age"]
    groups = tables["groups"]
    assert isinstance(fec, dict)
    assert isinstance(occupational, dict)
    assert isinstance(age, dict)
    assert isinstance(groups, list)

    fec_expectations = {
        (rank, wpi): fec[f"{rank}|{wpi}"]
        for rank in range(1, 9)
        for wpi in range(1, 101)
    }
    occupation_expectations = {
        (rating, variant): occupational[str(rating)][column]
        for rating in range(101)
        for column, variant in enumerate(VARIANTS)
    }
    age_expectations = {
        (rating, band): age[str(rating)][column]
        for rating in range(1, 101)
        for column, band in enumerate(AGE_BANDS)
    }
    section4_expectations = {
        (label, group): row[group]
        for label, row in matrix.items()
        for group in groups
    }
    assert len(fec_expectations) == 800
    assert len(occupation_expectations) == 808
    assert len(age_expectations) == 1_000
    assert len(section4_expectations) == 5_085

    assert occupation_expectations[(50, "H")] == 56
    pd_calculator_synthetic_50_h = 75
    assert pd_calculator_synthetic_50_h == 75
    assert occupation_expectations[(50, "H")] != pd_calculator_synthetic_50_h
    assert section4_expectations[("15.01 -- 15.03", "470")] == "H"
    assert section4_expectations[("15.01 -- 15.03", "480")] == "I"

    from wc_caseload_engine.rating import (
        age_adjusted_rating,
        fec_adjusted_rating,
        occupation_adjusted_rating,
        section4_variant,
    )
    from wc_caseload_engine.rating_sources import load_rating_source_bundle

    source = load_rating_source_bundle()
    fec_mismatches = [
        (coordinate, literal, fec_adjusted_rating(*coordinate, source))
        for coordinate, literal in fec_expectations.items()
        if fec_adjusted_rating(*coordinate, source) != literal
    ]
    occupation_mismatches = [
        (coordinate, literal, occupation_adjusted_rating(*coordinate, source))
        for coordinate, literal in occupation_expectations.items()
        if occupation_adjusted_rating(*coordinate, source) != literal
    ]
    age_mismatches = [
        (coordinate, literal, age_adjusted_rating(*coordinate, source))
        for coordinate, literal in age_expectations.items()
        if age_adjusted_rating(*coordinate, source) != literal
    ]
    section4_mismatches = [
        (coordinate, literal, section4_variant(*coordinate, source))
        for coordinate, literal in section4_expectations.items()
        if section4_variant(*coordinate, source) != literal
    ]
    assert len(fec_mismatches) == 0
    assert len(occupation_mismatches) == 0
    assert len(age_mismatches) == 0
    assert len(section4_mismatches) == 0


def test_r86_full_group_section4_lookup_never_uses_first_digit() -> None:
    """m23-33: neighboring 4xx groups select different literal variants."""
    matrix = _read_json(SECTION4_PATH, SECTION4_SHA256)
    assert matrix["15.01 -- 15.03"]["470"] == "H"
    assert matrix["15.01 -- 15.03"]["480"] == "I"

    from wc_caseload_engine.rating import section4_variant

    assert section4_variant("15.01 -- 15.03", "470") == "H"
    assert section4_variant("15.01 -- 15.03", "480") == "I"


def _independent_section4_match(label: str, impairment_number: str) -> bool:
    label_parts = label.split(".")
    impairment_parts = impairment_number.split(".")
    if " -- " in label:
        lower, upper = label.split(" -- ", 1)
        lower_parts = tuple(int(part) for part in lower.split("."))
        upper_parts = tuple(int(part) for part in upper.split("."))
        candidate = tuple(
            int(part) for part in impairment_parts[: len(lower_parts)]
        )
        return lower_parts <= candidate <= upper_parts
    return len(label_parts) == len(impairment_parts) and all(
        expected == "XX" or expected == actual
        for expected, actual in zip(label_parts, impairment_parts, strict=True)
    )


def test_r86_compiled_section4_mapping_is_214_singletons_and_one_rejection() -> None:
    tables = _read_json(TABLES_PATH, TABLES_SHA256)
    matrix = _read_json(SECTION4_PATH, SECTION4_SHA256)
    impairments = tables["imp"]
    assert isinstance(impairments, dict)
    matches = {
        impairment: tuple(
            label
            for label in matrix
            if _independent_section4_match(label, impairment)
        )
        for impairment in impairments
    }
    assert len(matches) == 215
    assert sum(len(labels) == 1 for labels in matches.values()) == 214
    assert [impairment for impairment, labels in matches.items() if not labels] == [
        "13.07.08.00"
    ]
    assert all(len(labels) <= 1 for labels in matches.values())

    from wc_caseload_engine.rating import (
        RATING_VARIANT_CROSS_REFERENCE_REQUIRED,
        RatingValidationError,
        section4_row_key,
    )

    for impairment, labels in matches.items():
        if impairment == "13.07.08.00":
            with pytest.raises(RatingValidationError) as excinfo:
                section4_row_key(impairment)
            assert excinfo.value.code == RATING_VARIANT_CROSS_REFERENCE_REQUIRED
        else:
            assert section4_row_key(impairment) == labels[0]


def _literal_cvc_chart() -> dict[tuple[int, int], int]:
    raw = EXTRACTED_TEXT_PATH.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == EXTRACTED_TEXT_SHA256
    text = raw.decode("utf-8")
    section = text[text.index("SECTION 8 - COMBINED VALUES CHART") :]
    chart: dict[tuple[int, int], int] = {}
    for line in section.splitlines():
        tokens = line.split()
        if not tokens or any(not token.isdigit() for token in tokens):
            continue
        numbers = [int(token) for token in tokens]
        larger = numbers[0]
        if not 8 <= larger <= 99:
            continue
        column_count = min(larger, 50)
        if len(numbers) != column_count + 1:
            continue
        assert all((larger, smaller) not in chart for smaller in range(1, column_count + 1))
        chart.update(
            {
                (larger, smaller): literal
                for smaller, literal in enumerate(numbers[1:], start=1)
            }
        )
    assert len(chart) == 3_697
    return chart


def _independent_cvc_value(larger: int, smaller: int) -> int:
    value = Decimal(larger) + Decimal(smaller) * (
        Decimal(1) - Decimal(larger) / Decimal(100)
    )
    return int(value.to_integral_value(rounding=ROUND_HALF_UP))


def _assert_chart_formula_then_production() -> None:
    chart = _literal_cvc_chart()
    formula_mismatches = [
        (coordinate, literal, _independent_cvc_value(*coordinate))
        for coordinate, literal in chart.items()
        if _independent_cvc_value(*coordinate) != literal
    ]
    cells = len(chart)
    mismatches = len(formula_mismatches)
    assert cells == 3_697
    assert mismatches == 0
    assert chart[(50, 1)] == 51

    from wc_caseload_engine.rating import combine_cvc_ratings

    production_mismatches = [
        (coordinate, literal, combine_cvc_ratings(coordinate))
        for coordinate, literal in chart.items()
        if combine_cvc_ratings(coordinate) != literal
    ]
    assert len(production_mismatches) == 0


def test_r86_cvc_chart_and_section7_chain_round_each_step() -> None:
    """m23-35: chart cells pass, then the official multi-step chain stays 71."""
    _assert_chart_formula_then_production()
    from wc_caseload_engine.rating import combine_cvc_ratings

    assert combine_cvc_ratings((50, 32)) == 66
    assert combine_cvc_ratings((66, 13)) == 70
    assert combine_cvc_ratings((70, 4)) == 71
    assert combine_cvc_ratings((50, 32, 13, 4)) == 71


def test_r86_cvc_chart_half_ties_round_up() -> None:
    """m23-44: all chart cells include the literal 50 C 1 half tie."""
    _assert_chart_formula_then_production()
    from wc_caseload_engine.rating import combine_cvc_ratings

    assert combine_cvc_ratings((50, 1)) == 51


def test_r86_cvc_sorts_descending_instead_of_authored_order() -> None:
    """m23-34: the chart-backed 13,50,32 witness distinguishes ordering."""
    chart = _literal_cvc_chart()
    assert chart[(50, 32)] == 66
    assert chart[(66, 13)] == 70
    assert chart[(50, 13)] == 57
    assert chart[(57, 32)] == 71

    from wc_caseload_engine.rating import combine_cvc_ratings

    assert combine_cvc_ratings((13, 50, 32)) == 70


def _rated_carrier_seed(*, kite_addition: bool, hooks: tuple[str, ...] = ()):
    from wc_caseload_engine.seeds import parse_case_seed

    rating: dict[str, Any] = {
        "schedule": "pdrs_2005",
        "occupation_group": "470",
        "impairments": [
            {
                "id": "shoulder",
                "body_part": "shoulder",
                "impairment_number": "16.02.01.00",
                "wpi": 8,
            },
            {
                "id": "knee",
                "body_part": "knee",
                "impairment_number": "17.05.04.00",
                "wpi": 12,
            },
        ],
        "combination_method": "cvc",
    }
    if kite_addition:
        rating["kite_addition"] = {"impairment_ids": ["knee", "shoulder"]}
    return parse_case_seed(
        {
            "case_id": "rating-carrier-probe",
            "rng_seed": 2305,
            "injury": {
                "type": "specific",
                "date_of_injury": "2012-06-15",
                "body_parts": [{"part": "shoulder"}, {"part": "knee"}],
            },
            "profile": {
                "applicant": {"age": 30, "occupation": "Warehouse worker"}
            },
            "lifecycle": {
                "target_stage": "medical_legal",
                "eval_type": "qme",
                "doctrine_hooks": list(hooks),
            },
            "scenario": {"wages": {}, "rating": rating},
        }
    )


def _flat_rendered_text(value: str) -> str:
    without_markup = re.sub(r"<[^>]+>", " ", value)
    flattened = " ".join(html.unescape(without_markup).split())
    # Tesseract preserves every R39 character but occasionally drops spaces
    # around a printed ASCII hyphen. Restore only numeric rating separators;
    # this does not repair a changed token, digit, bracket, or dash glyph.
    return re.sub(r"(?<=[0-9A-J%])\s*-\s*(?=[0-9\[])", " - ", flattened)


def _ocr_scanned_pdf(path: Path) -> str:
    fitz = pytest.importorskip("fitz")
    executable = shutil.which("tesseract")
    if executable is None:
        pytest.skip("tesseract is required for the scanned-rating oracle")
    pages: list[str] = []
    with fitz.open(path) as document:
        for page in document:
            candidates: list[str] = []
            for scale in (2, 4):
                image = page.get_pixmap(
                    matrix=fitz.Matrix(scale, scale)
                ).tobytes("png")
                completed = subprocess.run(
                    [executable, "stdin", "stdout"],
                    input=image,
                    capture_output=True,
                    check=False,
                    timeout=60,
                    env={**os.environ, "OMP_THREAD_LIMIT": "1"},
                )
                assert completed.returncode == 0, completed.stderr.decode(
                    "utf-8", errors="replace"
                )
                candidates.append(
                    completed.stdout.decode("utf-8", errors="replace")
                )
            # Scan noise makes two-times clearer for some pages and four-times
            # clearer for others. Select by the independently declared R39
            # grammar, never by an expected production value.
            pages.append(
                max(
                    candidates,
                    key=lambda candidate: len(
                        RATING_ROW_PATTERN.findall(
                            _flat_rendered_text(candidate)
                        )
                    ),
                )
            )
    return "\n".join(pages)


def _extract_rating_text(path: Path, doc_format: str) -> str:
    if doc_format == "scanned_pdf":
        return _ocr_scanned_pdf(path)
    from conftest import extract_text

    return extract_text(path, doc_format)


@pytest.fixture(scope="module")
def rendered_rating_carriers(
    tmp_path_factory: pytest.TempPathFactory,
) -> dict[str, Any]:
    from wc_caseload_engine.planner import build_case_plan
    from wc_caseload_engine.renderer import FORMAT_EXTENSIONS, render_document
    from wc_caseload_engine.substrate import find_substrate

    if find_substrate() is None:
        pytest.skip("merus-test-data-generator substrate not on disk")
    seed = _rated_carrier_seed(kite_addition=True)
    plan = build_case_plan(seed)
    assert plan.case_facts is not None and plan.case_facts.rating is not None
    rating = plan.case_facts.rating
    root = tmp_path_factory.mktemp("rating-carriers")
    texts: dict[tuple[str, str], str] = {}
    results: dict[tuple[str, str], Any] = {}
    for subtype_index, subtype in enumerate(sorted(R47_CARRIERS)):
        for format_index, doc_format in enumerate(
            ("pdf", "scanned_pdf", "eml", "docx")
        ):
            extension = FORMAT_EXTENSIONS[doc_format]
            out_path = root / f"{subtype}-{doc_format}.{extension}"
            result = render_document(
                seed=seed,
                cast=plan.cast,
                subtype=subtype,
                doc_date=plan.timeline.horizon,
                doc_format=doc_format,
                # The same clean deterministic scan transform is applied to
                # all three same-layout carriers. Other formats retain unique
                # document indexes; this oracle is about their text surface.
                index=(
                    101
                    if doc_format == "scanned_pdf"
                    else 100 + subtype_index * 4 + format_index
                ),
                out_path=out_path,
                case_facts=plan.case_facts,
                money_facts=plan.money_facts,
            )
            assert result.doc_format == doc_format, result.fallback_reason
            results[(subtype, doc_format)] = result
            texts[(subtype, doc_format)] = _flat_rendered_text(
                _extract_rating_text(result.path, doc_format)
            )
    return {
        "seed": seed,
        "plan": plan,
        "rating": rating,
        "root": root,
        "texts": texts,
        "results": results,
    }


def _rating_paper_mismatches(
    text: str,
    rating: Any,
    *,
    row_pattern: re.Pattern[str] = RATING_ROW_PATTERN,
) -> set[str]:
    actual_rows = [match.groupdict() for match in row_pattern.finditer(text)]
    mismatches: set[str] = set()
    if len(actual_rows) != len(rating.impairments):
        mismatches.add("row_count")
        return mismatches
    for actual, expected in zip(actual_rows, rating.impairments, strict=True):
        expected_fields = {
            "impairment_number": expected.impairment_number,
            "wpi": str(expected.wpi),
            "adjustment": str(
                expected.fec_rank
                if expected.fec_rank is not None
                else expected.adjustment_factor
            ),
            "schedule_adjusted": str(expected.schedule_adjusted),
            "occupation_group": rating.occupation_group,
            "variant": expected.variant,
            "occupation_adjusted": str(expected.occupation_adjusted),
            "age_adjusted": str(expected.age_adjusted),
        }
        for field, expected_value in expected_fields.items():
            if actual[field] != expected_value:
                mismatches.add("fec_rank" if field == "adjustment" else field)
    if (
        f"Selected unapportioned permanent disability: "
        f"{rating.final_pd_percent}%" not in text
    ):
        mismatches.add("final_pd_percent")
    if rating.combination_method == "kite_addition":
        footer = (
            "Combined PD (Kite addition; explicit pair "
            f"{rating.kite_impairment_ids[0]}+{rating.kite_impairment_ids[1]}; "
            f"scheduled CVC {rating.scheduled_combined_rating}%): "
            f"{rating.combined_rating}%"
        )
        if footer not in text:
            mismatches.add("rating_footer")
    return mismatches


def test_r88_every_literal_carrier_and_format_renders_only_rating_facts(
    rendered_rating_carriers: dict[str, Any],
) -> None:
    rating = rendered_rating_carriers["rating"]
    texts = rendered_rating_carriers["texts"]
    assert set(R47_CARRIERS) == {
        "IMPAIRMENT_RATING_WORKSHEET",
        "PD_RATING_CALCULATION_WORKSHEET",
        "PD_RATING_CONVERSION",
    }
    assert len(texts) == 12
    for coordinate, text in texts.items():
        _subtype, doc_format = coordinate
        pattern = (
            RATING_SCAN_ROW_PATTERN
            if doc_format == "scanned_pdf"
            else RATING_ROW_PATTERN
        )
        assert (
            _rating_paper_mismatches(text, rating, row_pattern=pattern) == set()
        ), coordinate
        if doc_format != "scanned_pdf":
            for row in rating.impairments:
                assert row.rating_string in text, coordinate
        assert f"{rating.final_pd_percent}%" in text, coordinate

    plan = rendered_rating_carriers["plan"]
    planned = [document.subtype for document in plan.documents]
    assert "INFORMAL_PD_RATING_PRINTOUT" not in planned
    assert "PD_RATING_CALCULATION_WORKSHEET" in planned


def test_r48_added_carrier_copies_bind_the_same_rating_facts_object(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from wc_caseload_engine import manifests
    from wc_caseload_engine.seeds import parse_case_seed
    from wc_caseload_engine.substrate import find_substrate

    if find_substrate() is None:
        pytest.skip("merus-test-data-generator substrate not on disk")
    raw = _rated_carrier_seed(kite_addition=False).model_dump(mode="json")
    rating = raw["scenario"]["rating"]
    rating["impairments"] = rating["impairments"][:1]
    rating["combination_method"] = "single"
    raw["documents"] = {
        "include_only": ["PD_RATING_CALCULATION_WORKSHEET"],
        "overrides": [
            {"subtype": "PD_RATING_CALCULATION_WORKSHEET", "count": 3}
        ],
        "format_mix": {"pdf": 1.0},
    }
    seed = parse_case_seed(raw)
    captured: list[Any] = []
    original = manifests.render_document

    def capture_rating_binding(**kwargs: Any):
        captured.append(kwargs["case_facts"].rating)
        return original(**kwargs)

    monkeypatch.setattr(manifests, "render_document", capture_rating_binding)
    result = manifests.generate_case(seed, tmp_path)
    assert len(result.renders) == 3
    assert result.plan.case_facts is not None
    selected = result.plan.case_facts.rating
    assert selected is not None
    assert len(captured) == 3
    assert all(bound is selected for bound in captured)


def test_r88_each_rating_string_intermediate_has_a_named_mismatch(
    rendered_rating_carriers: dict[str, Any],
) -> None:
    rating = rendered_rating_carriers["rating"]
    text = rendered_rating_carriers["texts"][
        ("PD_RATING_CALCULATION_WORKSHEET", "pdf")
    ]
    first = rating.impairments[0]
    row_mutations = {
        "impairment_number": first.model_copy(
            update={"impairment_number": "16.02.01.01"}
        ),
        "wpi": first.model_copy(update={"wpi": first.wpi + 1}),
        "fec_rank": first.model_copy(update={"fec_rank": first.fec_rank + 1}),
        "schedule_adjusted": first.model_copy(
            update={"schedule_adjusted": first.schedule_adjusted + 1}
        ),
        "variant": first.model_copy(update={"variant": "C"}),
        "occupation_adjusted": first.model_copy(
            update={"occupation_adjusted": first.occupation_adjusted + 1}
        ),
        "age_adjusted": first.model_copy(
            update={"age_adjusted": first.age_adjusted + 1}
        ),
    }
    for field, mutated_row in row_mutations.items():
        mutated = rating.model_copy(
            update={"impairments": (mutated_row, *rating.impairments[1:])}
        )
        assert field in _rating_paper_mismatches(text, mutated), field

    changed_group = rating.model_copy(update={"occupation_group": "480"})
    assert "occupation_group" in _rating_paper_mismatches(text, changed_group)
    changed_final = rating.model_copy(
        update={"final_pd_percent": rating.final_pd_percent + 1}
    )
    assert "final_pd_percent" in _rating_paper_mismatches(text, changed_final)


def _forbidden_rating_families(root: Path) -> set[str]:
    found: set[str] = set()
    for path in root.rglob("*.txt"):
        text = path.read_text(encoding="utf-8")
        found.update(
            family
            for family, token in R52_FORBIDDEN_FAMILIES.items()
            if token in text
        )
    return found


def test_r89_rating_path_never_joins_pd_percent_to_dollars_or_offsets(
    rendered_rating_carriers: dict[str, Any],
) -> None:
    """m23-28: W2 stays an unapportioned percentage-only truth path."""
    root = rendered_rating_carriers["root"]
    clean = root / "r52-clean"
    clean.mkdir()
    for index, text in enumerate(rendered_rating_carriers["texts"].values()):
        (clean / f"carrier-{index}.txt").write_text(text, encoding="utf-8")
    assert _forbidden_rating_families(clean) == set()

    for family, token in R52_FORBIDDEN_FAMILIES.items():
        planted = root / f"r52-planted-{family}"
        shutil.copytree(clean, planted)
        (planted / "planted-positive.txt").write_text(token, encoding="utf-8")
        assert _forbidden_rating_families(planted) == {family}


def test_r49_literal_six_hooks_ground_only_the_selected_unapportioned_rating(
    tmp_path: Path,
) -> None:
    from wc_caseload_engine.planner import build_case_plan
    from wc_caseload_engine.renderer import render_document
    from wc_caseload_engine.substrate import find_substrate

    if find_substrate() is None:
        pytest.skip("merus-test-data-generator substrate not on disk")
    assert frozenset(
        {
            "ogilvie",
            "almaraz_guzman",
            "escobedo",
            "benson",
            "kite",
            "lc4664_prior_award",
        }
    ) == R49_RATING_HOOKS
    seed = _rated_carrier_seed(
        kite_addition=True, hooks=tuple(sorted(R49_RATING_HOOKS))
    )
    plan = build_case_plan(seed)
    assert plan.case_facts is not None and plan.case_facts.rating is not None
    rating = plan.case_facts.rating
    targets = {
        hook: (
            "APPORTIONMENT_WORKSHEET"
            if hook in {"benson", "escobedo"}
            else "PD_RATING_CALCULATION_WORKSHEET"
        )
        for hook in R49_RATING_HOOKS
    }
    for index, hook in enumerate(sorted(R49_RATING_HOOKS)):
        result = render_document(
            seed=seed,
            cast=plan.cast,
            subtype=targets[hook],
            doc_date=plan.timeline.horizon,
            doc_format="pdf",
            index=300 + index,
            out_path=tmp_path / f"{hook}.pdf",
            content_flags=(hook,),
            case_facts=plan.case_facts,
            money_facts=plan.money_facts,
        )
        assert result.content_flags == (hook,)
        text = _flat_rendered_text(_extract_rating_text(result.path, "pdf"))
        assert (
            f"Selected unapportioned permanent disability rating: "
            f"{rating.final_pd_percent}%." in text
        ), hook
        assert all(token not in text for token in R52_FORBIDDEN_FAMILIES.values())
        if hook == "kite":
            assert (
                "Explicit Kite addition selected; scheduled CVC comparator: "
                f"{rating.scheduled_combined_rating}%." in text
            )
        else:
            assert "scheduled CVC comparator" not in text


def test_r49_kite_hook_without_raw_opt_in_remains_scheduled_cvc(
    tmp_path: Path,
) -> None:
    from wc_caseload_engine.planner import build_case_plan
    from wc_caseload_engine.renderer import render_document
    from wc_caseload_engine.substrate import find_substrate

    if find_substrate() is None:
        pytest.skip("merus-test-data-generator substrate not on disk")
    seed = _rated_carrier_seed(kite_addition=False, hooks=("kite",))
    assert "kite_addition" not in seed.scenario.rating.model_fields_set
    plan = build_case_plan(seed)
    assert plan.case_facts is not None and plan.case_facts.rating is not None
    rating = plan.case_facts.rating
    assert rating.combination_method == "cvc"
    result = render_document(
        seed=seed,
        cast=plan.cast,
        subtype="PD_RATING_CALCULATION_WORKSHEET",
        doc_date=plan.timeline.horizon,
        doc_format="pdf",
        index=400,
        out_path=tmp_path / "kite-no-opt-in.pdf",
        content_flags=("kite",),
        case_facts=plan.case_facts,
        money_facts=plan.money_facts,
    )
    text = _flat_rendered_text(_extract_rating_text(result.path, "pdf"))
    assert f"Selected unapportioned permanent disability: {rating.final_pd_percent}%" in text
    assert (
        f"Selected unapportioned permanent disability rating: "
        f"{rating.final_pd_percent}%." in text
    )
    assert "Kite addition" not in text
    assert "scheduled CVC comparator" not in text


def test_r49_unrated_carrier_and_doctrine_path_is_byte_inert(
    tmp_path: Path,
) -> None:
    from wc_caseload_engine.planner import build_case_plan
    from wc_caseload_engine.renderer import render_document
    from wc_caseload_engine.seeds import parse_case_seed
    from wc_caseload_engine.substrate import find_substrate

    if find_substrate() is None:
        pytest.skip("merus-test-data-generator substrate not on disk")
    seed = parse_case_seed(
        {
            "case_id": "unrated-doctrine-control",
            "rng_seed": 2306,
            "injury": {
                "type": "specific",
                "date_of_injury": "2012-06-15",
                "body_parts": [{"part": "shoulder"}, {"part": "knee"}],
            },
            "lifecycle": {
                "target_stage": "medical_legal",
                "eval_type": "qme",
                "doctrine_hooks": ["ogilvie"],
            },
        }
    )
    plan = build_case_plan(seed)
    assert plan.case_facts is not None and plan.case_facts.rating is None
    shared = {
        "seed": seed,
        "cast": plan.cast,
        "subtype": "PD_RATING_CALCULATION_WORKSHEET",
        "doc_date": plan.timeline.horizon,
        "doc_format": "pdf",
        "index": 500,
        "content_flags": ("ogilvie",),
    }
    control = render_document(
        **shared,
        out_path=tmp_path / "unrated-control.pdf",
        case_facts=None,
        money_facts=None,
    )
    projected = render_document(
        **shared,
        out_path=tmp_path / "unrated-projected.pdf",
        case_facts=plan.case_facts,
        money_facts=plan.money_facts,
    )
    assert control.path.read_bytes() == projected.path.read_bytes()
    text = _flat_rendered_text(_extract_rating_text(projected.path, "pdf"))
    assert "Selected unapportioned permanent disability rating:" not in text
    assert "scheduled CVC comparator" not in text
