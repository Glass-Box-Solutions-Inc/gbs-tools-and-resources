"""Canonical permanent-disability rating validation and derivation.

The authored scenario supplies only rating operands.  This module binds those
operands to the audited PDRS tables, stores every intermediate, combines the
row results, and returns the one canonical generation/extraction/scorer model.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal, NoReturn

from pydantic import BaseModel, ConfigDict, Field, model_validator

from wc_caseload_engine.rating_sources import (
    PDRS_2005_OCCUPATIONAL_VARIANTS,
    RATING_AGE_CELL_MISSING,
    RATING_COMBINATION_EXTREMITY_IDENTITY_REQUIRED,
    RATING_COMBINATION_UNSUPPORTED_OVERLAP,
    RATING_ERROR_CODES,
    RATING_FEC_CELL_MISSING,
    RATING_INVALID_AGE_INPUT,
    RATING_KITE_NEEDS_TWO_DISTINCT_ROWS,
    RATING_KITE_PAIR_INVALID,
    RATING_KITE_SCOPE_UNSUPPORTED,
    RATING_OCC_CELL_MISSING,
    RATING_REQUIRED_CARRIER_REMOVED,
    RATING_REQUIRES_EVALUATOR,
    RATING_REQUIRES_WAGES,
    RATING_SOURCE_BUNDLE_MISMATCH,
    RATING_UNKNOWN_IMPAIRMENT_NUMBER,
    RATING_UNKNOWN_OCCUPATION_GROUP,
    RATING_UNSUPPORTED_DOI,
    RATING_VARIANT_CROSS_REFERENCE_REQUIRED,
    RatingScheduleBinding,
    RatingSourceBundle,
    load_rating_source_bundle,
)

type AdjustmentMethod = Literal["fec_rank_table", "dfec_1_4"]
type AgeBand = Literal[
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
]

_STRICT_MODEL_CONFIG = ConfigDict(extra="forbid", frozen=True, validate_default=True)
_PDRS_START = date(2005, 1, 1)
_DFEC_START = date(2013, 1, 1)
_EXTREMITY_CLASSES = ("16.", "17.")
_SECTION4_CROSS_REFERENCE = "13.07.08.00"
RATING_CARRIER_SUBTYPES: frozenset[str] = frozenset(
    {
        "IMPAIRMENT_RATING_WORKSHEET",
        "PD_RATING_CALCULATION_WORKSHEET",
        "PD_RATING_CONVERSION",
    }
)
"""The complete canonical document surface allowed to carry W2 ratings."""

RATING_GROUNDED_DOCTRINE_HOOKS: frozenset[str] = frozenset(
    {
        "ogilvie",
        "almaraz_guzman",
        "escobedo",
        "benson",
        "kite",
        "lc4664_prior_award",
    }
)
"""Hooks whose numeric rating statements must project from RatingFacts."""

_AGE_BANDS: tuple[AgeBand, ...] = (
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


class RatingValidationError(ValueError):
    """One stable rating failure with its seed path and offending value."""

    def __init__(self, code: str, path: str, value: object, detail: str) -> None:
        self.code = code
        self.path = path
        self.value = value
        super().__init__(f"{code}: {path}={value!r} — {detail}")


def _fail(code: str, path: str, value: object, detail: str) -> NoReturn:
    raise RatingValidationError(code, path, value, detail)


class RatingImpairmentInput(BaseModel):
    """The four operands an author may state for one impairment."""

    model_config = _STRICT_MODEL_CONFIG

    id: str = Field(min_length=1)
    body_part: str = Field(min_length=1)
    impairment_number: str = Field(min_length=1)
    wpi: int = Field(ge=1, le=100)


class KiteAdditionInput(BaseModel):
    """The exact authored pair selected for a Kite additive rating."""

    model_config = _STRICT_MODEL_CONFIG

    impairment_ids: tuple[str, str]

    @model_validator(mode="after")
    def _pair_is_distinct(self) -> KiteAdditionInput:
        if self.impairment_ids[0] == self.impairment_ids[1]:
            _fail(
                RATING_KITE_NEEDS_TWO_DISTINCT_ROWS,
                "scenario.rating.kite_addition.impairment_ids",
                self.impairment_ids,
                "Kite addition needs two distinct impairment IDs",
            )
        return self


class RatingScenario(BaseModel):
    """Authored rating operands only; every result remains derived."""

    model_config = _STRICT_MODEL_CONFIG

    schedule: Literal["pdrs_2005"]
    occupation_group: str
    impairments: tuple[RatingImpairmentInput, ...]
    combination_method: Literal["single", "cvc"]
    kite_addition: KiteAdditionInput | None = None

    @model_validator(mode="after")
    def _validate_authored_shape(self) -> RatingScenario:
        ids = tuple(row.id for row in self.impairments)
        if len(set(ids)) != len(ids):
            duplicate = next(identifier for identifier in ids if ids.count(identifier) > 1)
            _fail(
                RATING_COMBINATION_UNSUPPORTED_OVERLAP,
                "scenario.rating.impairments[].id",
                duplicate,
                "impairment IDs must be unique",
            )

        if self.kite_addition is not None:
            if "kite_addition" not in self.model_fields_set:
                _fail(
                    RATING_KITE_PAIR_INVALID,
                    "scenario.rating.kite_addition",
                    self.kite_addition,
                    "Kite addition must be explicitly present in the authored rating block",
                )
            if len(self.impairments) < 2 or len(set(ids)) < 2:
                _fail(
                    RATING_KITE_NEEDS_TWO_DISTINCT_ROWS,
                    "scenario.rating.impairments",
                    ids,
                    "Kite addition needs at least two distinct ratable rows",
                )
            if self.combination_method != "cvc":
                _fail(
                    RATING_KITE_PAIR_INVALID,
                    "scenario.rating.combination_method",
                    self.combination_method,
                    "Kite addition requires combination_method='cvc'",
                )
            selected = self.kite_addition.impairment_ids
            if len(self.impairments) != 2 or set(selected) != set(ids):
                _fail(
                    RATING_KITE_PAIR_INVALID,
                    "scenario.rating.kite_addition.impairment_ids",
                    selected,
                    "the selected pair must equal the complete two-row impairment ID set",
                )

        if self.combination_method == "single" and len(self.impairments) != 1:
            _fail(
                RATING_COMBINATION_UNSUPPORTED_OVERLAP,
                "scenario.rating.impairments",
                len(self.impairments),
                "combination_method='single' requires exactly one impairment row",
            )
        if self.combination_method == "cvc" and len(self.impairments) < 2:
            code = (
                RATING_KITE_NEEDS_TWO_DISTINCT_ROWS
                if self.kite_addition is not None
                else RATING_COMBINATION_UNSUPPORTED_OVERLAP
            )
            _fail(
                code,
                "scenario.rating.impairments",
                len(self.impairments),
                "combination_method='cvc' requires at least two impairment rows",
            )

        duplicated_rows = {
            (row.body_part.strip().casefold(), row.impairment_number)
            for row in self.impairments
            if sum(
                other.body_part.strip().casefold() == row.body_part.strip().casefold()
                and other.impairment_number == row.impairment_number
                for other in self.impairments
            )
            > 1
        }
        if duplicated_rows:
            _fail(
                RATING_COMBINATION_UNSUPPORTED_OVERLAP,
                "scenario.rating.impairments",
                sorted(duplicated_rows)[0],
                "the same impairment number on the same body part cannot be combined twice",
            )

        normalized_parts = tuple(
            row.body_part.strip().casefold() for row in self.impairments
        )
        if len(set(normalized_parts)) != len(normalized_parts):
            duplicate = next(
                part for part in normalized_parts if normalized_parts.count(part) > 1
            )
            _fail(
                RATING_COMBINATION_UNSUPPORTED_OVERLAP,
                "scenario.rating.impairments[].body_part",
                duplicate,
                "CVC requires a unique body part for every impairment row",
            )

        for prefix in _EXTREMITY_CLASSES:
            same_class = [
                row.impairment_number
                for row in self.impairments
                if row.impairment_number.startswith(prefix)
            ]
            if len(same_class) > 1:
                _fail(
                    RATING_COMBINATION_EXTREMITY_IDENTITY_REQUIRED,
                    "scenario.rating.impairments[].impairment_number",
                    tuple(same_class),
                    f"multiple {prefix[:-1]}.* rows do not identify distinct extremities",
                )
        return self


class RatingImpairment(BaseModel):
    """One fully derived impairment row in the canonical rating result."""

    model_config = _STRICT_MODEL_CONFIG

    id: str
    body_part: str
    impairment_number: str
    wpi: int
    description: str
    adjustment_method: AdjustmentMethod
    fec_rank: int | None
    adjustment_factor: Decimal | None
    schedule_adjusted: int
    variant: Literal["C", "D", "E", "F", "G", "H", "I", "J"]
    occupation_adjusted: int
    age_band: AgeBand
    age_adjusted: int
    rating_string: str


class RatingFacts(BaseModel):
    """The one canonical generation, extraction, and scorer rating object."""

    model_config = _STRICT_MODEL_CONFIG

    schedule: RatingScheduleBinding
    date_of_injury: date
    applicant_age: int
    occupation_group: str
    occupation_title: str
    impairments: tuple[RatingImpairment, ...]
    combination_method: Literal["single", "cvc", "kite_addition"]
    kite_impairment_ids: tuple[str, str] | None
    scheduled_combined_rating: int
    combined_rating: int
    final_pd_percent: int
    rating_string: str

    @model_validator(mode="after")
    def _canonical_invariants(self) -> RatingFacts:
        method = rating_adjustment_method(
            self.date_of_injury, seed_path="rating.date_of_injury"
        )
        if self.applicant_age < 16 or self.applicant_age > 99:
            _fail(
                RATING_INVALID_AGE_INPUT,
                "rating.applicant_age",
                self.applicant_age,
                "the supported applicant age range is 16 through 99",
            )
        expected_band = age_band_for(self.applicant_age)
        for row in self.impairments:
            if row.adjustment_method != method:
                _fail(
                    RATING_UNSUPPORTED_DOI,
                    "rating.impairments[].adjustment_method",
                    row.adjustment_method,
                    f"date_of_injury {self.date_of_injury} selects {method!r}",
                )
            if method == "fec_rank_table":
                if row.fec_rank is None or row.adjustment_factor is not None:
                    _fail(
                        RATING_FEC_CELL_MISSING,
                        "rating.impairments[]",
                        row.id,
                        "2005-2012 rows require fec_rank and forbid adjustment_factor",
                    )
            elif row.fec_rank is not None or row.adjustment_factor != Decimal("1.4"):
                _fail(
                    RATING_FEC_CELL_MISSING,
                    "rating.impairments[]",
                    row.id,
                    "2013+ rows require adjustment_factor Decimal('1.4') and forbid fec_rank",
                )
            if row.age_band != expected_band:
                _fail(
                    RATING_INVALID_AGE_INPUT,
                    "rating.impairments[].age_band",
                    row.age_band,
                    f"applicant_age {self.applicant_age} requires age band {expected_band!r}",
                )

        ids = tuple(row.id for row in self.impairments)
        if self.combination_method == "single":
            if len(ids) != 1 or self.kite_impairment_ids is not None:
                _fail(
                    RATING_KITE_PAIR_INVALID,
                    "rating.kite_impairment_ids",
                    self.kite_impairment_ids,
                    "single ratings require one row and a null Kite pair",
                )
        elif self.combination_method == "cvc":
            if len(ids) < 2 or self.kite_impairment_ids is not None:
                _fail(
                    RATING_KITE_PAIR_INVALID,
                    "rating.kite_impairment_ids",
                    self.kite_impairment_ids,
                    "CVC ratings require at least two rows and a null Kite pair",
                )
        elif (
            len(ids) != 2
            or self.kite_impairment_ids is None
            or len(set(self.kite_impairment_ids)) != 2
            or set(self.kite_impairment_ids) != set(ids)
        ):
            _fail(
                RATING_KITE_PAIR_INVALID,
                "rating.kite_impairment_ids",
                self.kite_impairment_ids,
                "kite_addition requires the exact complete two-row impairment ID set",
            )
        return self


def age_band_for(age: int) -> AgeBand:
    """Return the literal PDRS age band for a validated applicant age."""
    if age < 16 or age > 99:
        _fail(
            RATING_INVALID_AGE_INPUT,
            "profile.applicant.age",
            age,
            "the supported applicant age range is 16 through 99",
        )
    if age <= 21:
        return "<=21"
    if age >= 62:
        return ">=62"
    lower = 22 + ((age - 22) // 5) * 5
    return f"{lower}-{lower + 4}"  # type: ignore[return-value]


def applicant_age_at_doi(date_of_injury: date, birth_date: date | None) -> int:
    """Calculate literal attained age at DOI from the resolved cast birthday."""
    if birth_date is None or birth_date > date_of_injury:
        _fail(
            RATING_INVALID_AGE_INPUT,
            "rating.birth_date",
            birth_date,
            "the resolved applicant birth date must exist and not follow the date of injury",
        )
    age = date_of_injury.year - birth_date.year - (
        (date_of_injury.month, date_of_injury.day)
        < (birth_date.month, birth_date.day)
    )
    age_band_for(age)
    return age


def rating_adjustment_method(
    date_of_injury: date, *, seed_path: str = "injury.date_of_injury"
) -> AdjustmentMethod:
    """Select the DOI branch without performing any adjustment arithmetic."""
    if date_of_injury < _PDRS_START:
        _fail(
            RATING_UNSUPPORTED_DOI,
            seed_path,
            date_of_injury.isoformat(),
            "the 1997 PDRS rating is unavailable; use a DOI on or after 2005-01-01",
        )
    return "fec_rank_table" if date_of_injury < _DFEC_START else "dfec_1_4"


def _section4_label_matches(label: str, impairment_number: str) -> bool:
    if " -- " in label:
        lower, upper = label.split(" -- ", 1)
        width = len(lower.split("."))
        candidate = tuple(int(part) for part in impairment_number.split(".")[:width])
        return tuple(int(part) for part in lower.split(".")) <= candidate <= tuple(
            int(part) for part in upper.split(".")
        )
    pattern = re.escape(label).replace("XX", r"\d{2}")
    return re.fullmatch(pattern, impairment_number) is not None


def section4_row_key(
    impairment_number: str, bundle: RatingSourceBundle | None = None
) -> str:
    """Resolve one audited Section 4 row, never a cross-reference fallback."""
    source = bundle if bundle is not None else load_rating_source_bundle()
    if impairment_number == _SECTION4_CROSS_REFERENCE:
        _fail(
            RATING_VARIANT_CROSS_REFERENCE_REQUIRED,
            "scenario.rating.impairments[].impairment_number",
            impairment_number,
            "the official Section 4 row cross-references 11.03.04.00, "
            "15.01.XX.XX, or 16.02.01.00; an authored choice is required and "
            "no fallback is permitted",
        )
    matches = [
        label
        for label in source.section4_matrix
        if _section4_label_matches(label, impairment_number)
    ]
    if len(matches) != 1:
        _fail(
            RATING_VARIANT_CROSS_REFERENCE_REQUIRED,
            "scenario.rating.impairments[].impairment_number",
            impairment_number,
            "the official Section 4 row is a cross-reference requiring an "
            "authored choice; no fallback is permitted",
        )
    return matches[0]


def validate_rating_inputs(
    rating: RatingScenario,
    *,
    date_of_injury: date,
    evaluator: str,
    injury_body_parts: tuple[str, ...],
    date_path: str = "injury.date_of_injury",
    bundle: RatingSourceBundle | None = None,
) -> AdjustmentMethod:
    """Validate every pre-arithmetic rating invariant and return its DOI branch."""
    source = bundle if bundle is not None else load_rating_source_bundle()
    method = rating_adjustment_method(date_of_injury, seed_path=date_path)
    if evaluator not in {"qme", "ame"}:
        _fail(
            RATING_REQUIRES_EVALUATOR,
            "lifecycle.eval_type",
            evaluator,
            "scenario.rating requires exactly 'qme' or 'ame'",
        )
    if rating.occupation_group not in source.occupational_groups:
        _fail(
            RATING_UNKNOWN_OCCUPATION_GROUP,
            "scenario.rating.occupation_group",
            rating.occupation_group,
            "the value is not an audited January 2005 PDRS occupation group",
        )

    allowed_parts = {part.strip().casefold() for part in injury_body_parts}
    for index, row in enumerate(rating.impairments):
        path = f"scenario.rating.impairments[{index}]"
        if row.body_part.strip().casefold() not in allowed_parts:
            _fail(
                RATING_COMBINATION_UNSUPPORTED_OVERLAP,
                f"{path}.body_part",
                row.body_part,
                f"the body part must exist in injury.body_parts {injury_body_parts!r}",
            )
        registered = source.impairment_register.get(row.impairment_number)
        if registered is None:
            _fail(
                RATING_UNKNOWN_IMPAIRMENT_NUMBER,
                f"{path}.impairment_number",
                row.impairment_number,
                "the value is not in the audited parsed.json.imp register",
            )
        section4_key = section4_row_key(row.impairment_number, source)
        section4_row = source.section4_matrix[section4_key]
        if rating.occupation_group not in section4_row:
            _fail(
                RATING_OCC_CELL_MISSING,
                f"{path}.impairment_number",
                row.impairment_number,
                f"Section 4 has no occupation cell for group {rating.occupation_group!r}",
            )
        if method == "fec_rank_table":
            fec_key = f"{registered[0]}|{row.wpi}"
            if fec_key not in source.fec_lookup:
                _fail(
                    RATING_FEC_CELL_MISSING,
                    f"{path}.wpi",
                    row.wpi,
                    f"the audited FEC table has no rank/WPI cell {fec_key!r}",
                )
    return method


def combine_cvc_ratings(values: Sequence[int]) -> int:
    """Combine scheduled row ratings in stable descending order."""
    if not values:
        _fail(
            RATING_COMBINATION_UNSUPPORTED_OVERLAP,
            "rating.impairments",
            tuple(values),
            "CVC requires at least one scheduled rating",
        )
    ordered = tuple(
        value
        for _index, value in sorted(
            enumerate(values), key=lambda item: (-item[1], item[0])
        )
    )
    result = ordered[0]
    for next_rating in ordered[1:]:
        combined = Decimal(result) + Decimal(next_rating) * (
            Decimal(1) - Decimal(result) / Decimal(100)
        )
        result = int(combined.to_integral_value(rounding=ROUND_HALF_UP))
    return result


def fec_adjusted_rating(
    fec_rank: int,
    wpi: int,
    bundle: RatingSourceBundle | None = None,
) -> int:
    """Return one literal FEC table cell."""
    source = bundle if bundle is not None else load_rating_source_bundle()
    key = f"{fec_rank}|{wpi}"
    try:
        return source.fec_lookup[key]
    except KeyError:
        _fail(
            RATING_FEC_CELL_MISSING,
            "rating.impairment.wpi",
            wpi,
            f"the audited FEC table has no rank/WPI cell {key!r}",
        )


def dfec_adjusted_rating(wpi: int) -> int:
    """Apply the post-2013 flat 1.4 policy with half-up rounding and cap.

    **Authority: Labor Code section 4660.1(b)**, which replaced the 2005
    schedule's diminished-future-earning-capacity adjustment with a flat 1.4
    multiplier for injuries on or after 2013-01-01. Register rows
    **SI-W2-001** and **SI-W2-003**, ANSWERED 08-17-2026.

    AJC-64 item 0b (M5-R42(c)) adds this citation and nothing else — no
    behavior and no value changes; ``grep 4660`` previously returned nothing in
    either ``rating.py`` or ``rating_sources.py``, so the one legal proposition
    this function embodies was attributed to no source at all.

    The three figures here do **not** share a class, and saying so is the point
    of the citation:

    * ``1.4`` is ``LEGAL_BINDING`` — it is the statute's own multiplier;
    * ``ROUND_HALF_UP`` is ``ENGINE_POLICY`` — §4660.1(b) prescribes no
      rounding mode (guarded by ``m23-52``);
    * the ``100`` cap is a separate ``ENGINE_POLICY`` (guarded by ``m23-53``).

    The statutory text is sha256-pinned by item 0e; an unpinned citation fails
    ``M5_STATUTE_PIN_MISSING``, so this docstring does not ship without that pin.

    *(The KB's SI-W2-003 note preferred "adopt the chart, not a bare multiply"
    while W2 implements the multiply. Recorded as a question for a future
    ticket; M5 does not change the arithmetic.)*
    """
    rounded = int(
        (Decimal(wpi) * Decimal("1.4")).to_integral_value(rounding=ROUND_HALF_UP)
    )
    return min(100, rounded)


def _lookup_adjusted_cell(
    table: dict[str, tuple[int, ...]],
    *,
    row_key: int,
    column_index: int,
    code: str,
    path: str,
    detail: str,
) -> int:
    row = table.get(str(row_key))
    if row is None or column_index >= len(row):
        _fail(code, path, row_key, detail)
    return row[column_index]


def occupation_adjusted_rating(
    schedule_adjusted: int,
    variant: str,
    bundle: RatingSourceBundle | None = None,
) -> int:
    """Return one exact C-through-J occupational adjustment cell."""
    source = bundle if bundle is not None else load_rating_source_bundle()
    if variant not in PDRS_2005_OCCUPATIONAL_VARIANTS:
        _fail(
            RATING_OCC_CELL_MISSING,
            "rating.impairment.variant",
            variant,
            "the variant is not one of the audited C-through-J columns",
        )
    return _lookup_adjusted_cell(
        source.occupational_adjustment,
        row_key=schedule_adjusted,
        column_index=PDRS_2005_OCCUPATIONAL_VARIANTS.index(variant),
        code=RATING_OCC_CELL_MISSING,
        path="rating.impairment.schedule_adjusted",
        detail=(
            "the audited occupation table has no cell for "
            f"rating {schedule_adjusted} and variant {variant!r}"
        ),
    )


def age_adjusted_rating(
    occupation_adjusted: int,
    age_band: AgeBand,
    bundle: RatingSourceBundle | None = None,
) -> int:
    """Return one exact occupational-rating/age-band adjustment cell."""
    source = bundle if bundle is not None else load_rating_source_bundle()
    return _lookup_adjusted_cell(
        source.age_adjustment,
        row_key=occupation_adjusted,
        column_index=_AGE_BANDS.index(age_band),
        code=RATING_AGE_CELL_MISSING,
        path="rating.applicant_age",
        detail=(
            "the audited age table has no cell for "
            f"rating {occupation_adjusted} and band {age_band!r}"
        ),
    )


def section4_variant(
    row_label: str,
    occupation_group: str,
    bundle: RatingSourceBundle | None = None,
) -> str:
    """Return the literal Section 4 value at the full three-digit group."""
    source = bundle if bundle is not None else load_rating_source_bundle()
    row = source.section4_matrix.get(row_label)
    variant = None if row is None else row.get(occupation_group)
    if variant not in PDRS_2005_OCCUPATIONAL_VARIANTS:
        _fail(
            RATING_OCC_CELL_MISSING,
            "rating.occupation_group",
            occupation_group,
            f"Section 4 row {row_label!r} has no full-group occupation cell",
        )
    return variant


def derive_rating_facts(
    rating: RatingScenario,
    *,
    date_of_injury: date,
    birth_date: date | None,
    occupation_title: str,
    bundle: RatingSourceBundle | None = None,
) -> RatingFacts:
    """Derive every PDRS row and the unapportioned scheduled result."""
    source = bundle if bundle is not None else load_rating_source_bundle()
    method = rating_adjustment_method(date_of_injury, seed_path="rating.date_of_injury")
    age = applicant_age_at_doi(date_of_injury, birth_date)
    age_band = age_band_for(age)

    if rating.occupation_group not in source.occupational_groups:
        _fail(
            RATING_UNKNOWN_OCCUPATION_GROUP,
            "scenario.rating.occupation_group",
            rating.occupation_group,
            "the value is not an audited January 2005 PDRS occupation group",
        )

    derived: list[RatingImpairment] = []
    for index, authored in enumerate(rating.impairments):
        path = f"scenario.rating.impairments[{index}]"
        registered = source.impairment_register.get(authored.impairment_number)
        if registered is None:
            _fail(
                RATING_UNKNOWN_IMPAIRMENT_NUMBER,
                f"{path}.impairment_number",
                authored.impairment_number,
                "the value is not in the audited parsed.json.imp register",
            )
        description = registered[1]

        if method == "fec_rank_table":
            fec_rank = registered[0]
            schedule_adjusted = fec_adjusted_rating(fec_rank, authored.wpi, source)
            adjustment_factor = None
            adjustment_token = f"[{fec_rank}]"
        else:
            fec_rank = None
            adjustment_factor = Decimal("1.4")
            schedule_adjusted = dfec_adjusted_rating(authored.wpi)
            adjustment_token = "[1.4]"

        section4_key = section4_row_key(authored.impairment_number, source)
        variant = section4_variant(section4_key, rating.occupation_group, source)
        occupation_adjusted = occupation_adjusted_rating(
            schedule_adjusted, variant, source
        )
        age_adjusted = age_adjusted_rating(
            occupation_adjusted, age_band, source
        )
        rating_string = (
            f"{authored.impairment_number} - {authored.wpi} - "
            f"{adjustment_token}{schedule_adjusted} - "
            f"{rating.occupation_group}{variant} - {occupation_adjusted} - "
            f"{age_adjusted}%"
        )
        derived.append(
            RatingImpairment(
                id=authored.id,
                body_part=authored.body_part,
                impairment_number=authored.impairment_number,
                wpi=authored.wpi,
                description=description,
                adjustment_method=method,
                fec_rank=fec_rank,
                adjustment_factor=adjustment_factor,
                schedule_adjusted=schedule_adjusted,
                variant=variant,
                occupation_adjusted=occupation_adjusted,
                age_band=age_band,
                age_adjusted=age_adjusted,
                rating_string=rating_string,
            )
        )

    if rating.combination_method == "single":
        combination_method = "single"
        kite_impairment_ids = None
        scheduled_combined = derived[0].age_adjusted
        combined = derived[0].age_adjusted
        aggregate_string = derived[0].rating_string
    else:
        scheduled_combined = combine_cvc_ratings(
            tuple(row.age_adjusted for row in derived)
        )
        aggregate_string = "\n".join(row.rating_string for row in derived)
        explicit_kite = (
            rating.kite_addition is not None
            and "kite_addition" in rating.model_fields_set
        )
        if explicit_kite:
            combination_method = "kite_addition"
            kite_impairment_ids = (derived[0].id, derived[1].id)
            combined = min(100, sum(row.age_adjusted for row in derived))
            id_a, id_b = kite_impairment_ids
            aggregate_string += (
                "\nCombined PD (Kite addition; explicit pair "
                f"{id_a}+{id_b}; scheduled CVC {scheduled_combined}%): {combined}%"
            )
        else:
            combination_method = "cvc"
            kite_impairment_ids = None
            combined = scheduled_combined
            aggregate_string += f"\nCombined PD (CVC): {combined}%"

    return RatingFacts(
        schedule=source.binding,
        date_of_injury=date_of_injury,
        applicant_age=age,
        occupation_group=rating.occupation_group,
        occupation_title=occupation_title,
        impairments=tuple(derived),
        combination_method=combination_method,
        kite_impairment_ids=kite_impairment_ids,
        scheduled_combined_rating=scheduled_combined,
        combined_rating=combined,
        final_pd_percent=combined,
        rating_string=aggregate_string,
    )


__all__ = [
    "RATING_AGE_CELL_MISSING",
    "RATING_CARRIER_SUBTYPES",
    "RATING_COMBINATION_EXTREMITY_IDENTITY_REQUIRED",
    "RATING_COMBINATION_UNSUPPORTED_OVERLAP",
    "RATING_ERROR_CODES",
    "RATING_FEC_CELL_MISSING",
    "RATING_GROUNDED_DOCTRINE_HOOKS",
    "RATING_INVALID_AGE_INPUT",
    "RATING_KITE_NEEDS_TWO_DISTINCT_ROWS",
    "RATING_KITE_PAIR_INVALID",
    "RATING_KITE_SCOPE_UNSUPPORTED",
    "RATING_OCC_CELL_MISSING",
    "RATING_REQUIRED_CARRIER_REMOVED",
    "RATING_REQUIRES_EVALUATOR",
    "RATING_REQUIRES_WAGES",
    "RATING_SOURCE_BUNDLE_MISMATCH",
    "RATING_UNKNOWN_IMPAIRMENT_NUMBER",
    "RATING_UNKNOWN_OCCUPATION_GROUP",
    "RATING_UNSUPPORTED_DOI",
    "RATING_VARIANT_CROSS_REFERENCE_REQUIRED",
    "KiteAdditionInput",
    "RatingFacts",
    "RatingImpairment",
    "RatingImpairmentInput",
    "RatingScenario",
    "RatingValidationError",
    "age_adjusted_rating",
    "age_band_for",
    "applicant_age_at_doi",
    "combine_cvc_ratings",
    "derive_rating_facts",
    "dfec_adjusted_rating",
    "fec_adjusted_rating",
    "occupation_adjusted_rating",
    "rating_adjustment_method",
    "section4_row_key",
    "section4_variant",
    "validate_rating_inputs",
]
