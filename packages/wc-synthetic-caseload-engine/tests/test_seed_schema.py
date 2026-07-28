"""Seed schema tests — happy paths, actionable failures, defaults, derivation.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml

from wc_caseload_engine import seeds

# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_minimal_seed_parses_with_sensible_defaults(minimal_case: dict[str, Any]) -> None:
    seed = seeds.parse_case_seed(minimal_case)
    assert seed.case_id == "probe-001"
    assert seed.injury.date_of_injury == date(2023, 4, 12)
    assert seed.lifecycle.target_stage == "medical_legal"
    assert seed.lifecycle.liens.count == 0
    assert seed.documents.format_mix == dict(seeds.DEFAULT_FORMAT_MIX)
    assert seed.output.filename_style == "neutral"
    assert seed.profile.applicant.name is None


def test_full_surface_seed_parses(minimal_case: dict[str, Any]) -> None:
    payload = dict(minimal_case)
    payload["lifecycle"] = {
        "target_stage": "post_recon",
        "claim_response": "denied",
        "eval_type": "ame",
        "ur_dispute": {
            "enabled": True,
            "decision": "upheld",
            "imr": True,
            "imr_outcome": "overturned",
        },
        "resolution": {"type": "findings_award", "msa": True},
        "reconsideration": {
            "enabled": True,
            "outcome": "granted_remand",
            "post_recon": "settled",
        },
        "liens": {
            "count": 3,
            "claimants": ["medical_provider", "edd"],
            "resolution": "lien_resolution_agreement",
            "post_resolution_litigation": True,
        },
        "doctrine_hooks": ["ogilvie", "kite"],
    }
    payload["documents"] = {
        "global_cap": 60,
        "include_only": [],
        "exclude": ["SURVEILLANCE_REPORT"],
        "overrides": [
            {"subtype": "DEPOSITION_TRANSCRIPT", "count": 2},
            {"type": "MEDICAL_CLINICAL", "min": 8, "max": 25},
        ],
    }
    seed = seeds.parse_case_seed(payload)
    assert seed.lifecycle.reconsideration.post_recon == "settled"
    assert seed.documents.subtype_overrides == {"DEPOSITION_TRANSCRIPT": 2}
    assert seed.documents.type_bounds == {"MEDICAL_CLINICAL": (8, 25)}


def test_cumulative_trauma_requires_a_ct_window(minimal_case: dict[str, Any]) -> None:
    payload = dict(minimal_case)
    payload["injury"] = {
        "type": "cumulative_trauma",
        "ct_start": "2021-02-01",
        "ct_end": "2023-08-15",
        "body_parts": [{"part": "wrist", "icd10": "G56.00"}],
    }
    seed = seeds.parse_case_seed(payload)
    assert seed.injury.onset_date == date(2023, 8, 15)


# ---------------------------------------------------------------------------
# Actionable failures (ISC-19)
# ---------------------------------------------------------------------------


def test_unknown_field_is_rejected_and_named(minimal_case: dict[str, Any]) -> None:
    payload = dict(minimal_case) | {"lifecylce": {}}
    with pytest.raises(seeds.SeedValidationError) as excinfo:
        seeds.parse_case_seed(payload, source="probe.yaml")
    message = str(excinfo.value)
    assert "lifecylce" in message
    assert "unknown field" in message
    assert "probe.yaml" in message


def test_bad_enum_names_the_field_and_allowed_values(minimal_case: dict[str, Any]) -> None:
    payload = dict(minimal_case)
    payload["lifecycle"] = {"claim_response": "accpeted"}
    with pytest.raises(seeds.SeedValidationError) as excinfo:
        seeds.parse_case_seed(payload)
    message = str(excinfo.value)
    assert "lifecycle.claim_response" in message
    assert "accepted" in message and "delayed" in message and "denied" in message
    assert "'accpeted'" in message


def test_nested_list_errors_carry_the_index(minimal_case: dict[str, Any]) -> None:
    payload = dict(minimal_case)
    payload["documents"] = {"overrides": [{"subtype": "DEPOSITION_TRANSCRIPT"}]}
    with pytest.raises(seeds.SeedValidationError) as excinfo:
        seeds.parse_case_seed(payload)
    assert "documents.overrides.0" in str(excinfo.value)
    assert "requires 'count'" in str(excinfo.value)


@pytest.mark.parametrize(
    ("mutation", "needle"),
    [
        ({"injury": {"type": "specific", "body_parts": [{"part": "knee"}]}}, "date_of_injury"),
        (
            {
                "injury": {
                    "type": "cumulative_trauma",
                    "ct_start": "2023-01-01",
                    "ct_end": "2022-01-01",
                    "body_parts": [{"part": "knee"}],
                }
            },
            "ct_end must be on or after",
        ),
        ({"case_id": "../escape"}, "case_id"),
        ({"rng_seed": -1}, "rng_seed"),
        (
            {"lifecycle": {"target_stage": "post_recon"}},
            "reconsideration.enabled",
        ),
        (
            {"lifecycle": {"reconsideration": {"enabled": True, "outcome": "denied",
                                               "post_recon": "settled"}}},
            "affirmed_final",
        ),
        ({"lifecycle": {"liens": {"count": 0, "claimants": ["edd"]}}}, "liens.count is 0"),
        (
            {"lifecycle": {"ur_dispute": {"enabled": False, "imr": True}}},
            "ur_dispute",
        ),
        ({"documents": {"format_mix": {"tiff": 1.0}}}, "format_mix"),
        ({"documents": {"include_only": ["LIENS"], "exclude": ["LIENS"]}}, "both name"),
        ({"output": {"formats": []}}, "output.formats"),
        (
            {"injury": {"type": "specific", "date_of_injury": "2023-01-01",
                        "body_parts": []}},
            "body_parts",
        ),
    ],
)
def test_invalid_seeds_raise_with_the_offending_field(
    minimal_case: dict[str, Any], mutation: dict[str, Any], needle: str
) -> None:
    payload = dict(minimal_case) | mutation
    with pytest.raises(seeds.SeedValidationError) as excinfo:
        seeds.parse_case_seed(payload)
    assert needle in str(excinfo.value)


def test_more_body_parts_than_allowed_is_rejected(minimal_case: dict[str, Any]) -> None:
    payload = dict(minimal_case)
    payload["injury"] = {
        "type": "specific",
        "date_of_injury": "2023-04-12",
        "body_parts": [{"part": f"part_{i}"} for i in range(6)],
    }
    with pytest.raises(seeds.SeedValidationError) as excinfo:
        seeds.parse_case_seed(payload)
    assert "body_parts" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Deep merge of caseload defaults
# ---------------------------------------------------------------------------


def test_deep_merge_merges_mappings_and_replaces_lists() -> None:
    base = {"a": {"x": 1, "y": 2}, "list": [1, 2], "keep": True}
    override = {"a": {"y": 99, "z": 3}, "list": [9]}
    merged = seeds.deep_merge(base, override)
    assert merged == {"a": {"x": 1, "y": 99, "z": 3}, "list": [9], "keep": True}
    assert base == {"a": {"x": 1, "y": 2}, "list": [1, 2], "keep": True}


def test_caseload_defaults_are_deep_merged_under_each_case(
    minimal_case: dict[str, Any]
) -> None:
    spec = seeds.parse_caseload_spec(
        {
            "caseload_id": "probe-load",
            "defaults": {
                "documents": {"global_cap": 90},
                "lifecycle": {"claim_response": "accepted", "eval_type": "ame"},
                "output": {"filename_style": "corpus"},
            },
            "cases": [
                dict(minimal_case) | {"lifecycle": {"claim_response": "denied"}},
                dict(minimal_case) | {"case_id": "probe-002"},
            ],
        }
    )
    first, second = spec.cases
    # Case value wins over the default...
    assert first.lifecycle.claim_response == "denied"
    # ...while untouched sibling keys survive the merge.
    assert first.lifecycle.eval_type == "ame"
    assert first.documents.global_cap == 90
    assert first.output.filename_style == "corpus"
    assert second.lifecycle.claim_response == "accepted"


def test_caseload_rejects_duplicate_case_ids(minimal_case: dict[str, Any]) -> None:
    with pytest.raises(seeds.SeedValidationError) as excinfo:
        seeds.parse_caseload_spec(
            {"caseload_id": "dupes", "cases": [minimal_case, dict(minimal_case)]}
        )
    assert "duplicate case_id" in str(excinfo.value)


def test_empty_caseload_is_rejected() -> None:
    with pytest.raises(seeds.SeedValidationError) as excinfo:
        seeds.parse_caseload_spec({"caseload_id": "empty"})
    assert "at least one" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Auto derivation
# ---------------------------------------------------------------------------


def test_every_prd_distribution_is_available() -> None:
    assert set(seeds.DISTRIBUTIONS) == {
        "balanced",
        "early_stage",
        "settlement_heavy",
        "complex_litigation",
    }


def test_auto_derivation_is_deterministic() -> None:
    auto = seeds.AutoSpec(count=12, distribution="balanced", rng_seed=777)
    first = seeds.derive_auto_seeds(auto)
    second = seeds.derive_auto_seeds(seeds.AutoSpec(count=12, distribution="balanced",
                                                    rng_seed=777))
    assert [s.model_dump() for s in first] == [s.model_dump() for s in second]
    assert [s.seed_hash() for s in first] == [s.seed_hash() for s in second]


def test_a_different_rng_seed_changes_the_caseload() -> None:
    a = seeds.derive_auto_seeds(seeds.AutoSpec(count=8, rng_seed=1))
    b = seeds.derive_auto_seeds(seeds.AutoSpec(count=8, rng_seed=2))
    assert [s.rng_seed for s in a] != [s.rng_seed for s in b]


@pytest.mark.parametrize("distribution", sorted(seeds.DISTRIBUTIONS))
def test_derived_seeds_are_fully_materialized_and_valid(distribution: str) -> None:
    auto = seeds.AutoSpec(count=25, distribution=distribution, rng_seed=99)  # type: ignore[arg-type]
    derived = seeds.derive_auto_seeds(auto)
    assert len(derived) == 25
    for seed in derived:
        assert isinstance(seed, seeds.CaseSeed)
        assert 1 <= len(seed.injury.body_parts) <= 5
        assert all(part.icd10 for part in seed.injury.body_parts)
        assert seed.injury.mechanism != "auto"
        assert seed.lifecycle.target_stage in seeds.DISTRIBUTIONS[distribution].stages
        # round-trips through the loader unchanged
        assert seeds.parse_case_seed(yaml.safe_load(seeds.dump_case_seed(seed))) == seed


def test_early_stage_distribution_never_resolves_a_case() -> None:
    derived = seeds.derive_auto_seeds(
        seeds.AutoSpec(count=40, distribution="early_stage", rng_seed=5)
    )
    assert {s.lifecycle.target_stage for s in derived} <= {
        "intake",
        "active_treatment",
        "discovery",
        "medical_legal",
    }
    assert all(s.lifecycle.resolution.type == "pending" for s in derived)


def test_complex_litigation_produces_liens_and_recon() -> None:
    derived = seeds.derive_auto_seeds(
        seeds.AutoSpec(count=40, distribution="complex_litigation", rng_seed=11)
    )
    assert sum(1 for s in derived if s.lifecycle.liens.count > 0) >= 20
    assert sum(1 for s in derived if s.lifecycle.reconsideration.enabled) >= 5


def test_balanced_distribution_tracks_the_prd_injury_mix() -> None:
    derived = seeds.derive_auto_seeds(seeds.AutoSpec(count=200, distribution="balanced",
                                                     rng_seed=2026))
    specific = sum(1 for s in derived if s.injury.type == "specific") / len(derived)
    assert 0.60 <= specific <= 0.80  # PRD target 70%


def test_resolve_caseload_merges_explicit_and_derived(minimal_case: dict[str, Any]) -> None:
    spec = seeds.parse_caseload_spec(
        {
            "caseload_id": "mixed",
            "cases": [minimal_case],
            "auto": {"count": 3, "distribution": "balanced", "rng_seed": 4},
        }
    )
    resolved = seeds.resolve_caseload(spec)
    assert len(resolved) == 4
    assert resolved[0].case_id == "probe-001"
    assert len({s.case_id for s in resolved}) == 4


def test_derived_case_ids_never_collide_with_explicit_ones() -> None:
    auto = seeds.AutoSpec(count=3, rng_seed=8)
    derived = seeds.derive_auto_seeds(auto, existing_ids=["auto-001", "auto-002"])
    assert [s.case_id for s in derived] == ["auto-001-1", "auto-002-1", "auto-003"]


def test_derive_seed_is_stable_across_processes() -> None:
    """SHA-256 derivation, never PYTHONHASHSEED-dependent hash()."""
    assert seeds.derive_seed(777, "case:0") == seeds.derive_seed(777, "case:0")
    assert seeds.derive_seed(777, "case:0") != seeds.derive_seed(777, "case:1")
    assert 0 <= seeds.derive_seed(2**31, "x") < 2**32


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def test_dump_case_seed_round_trips(minimal_case: dict[str, Any]) -> None:
    seed = seeds.parse_case_seed(minimal_case)
    text = seeds.dump_case_seed(seed)
    assert text.startswith("# wc-caseload seed")
    reloaded = seeds.parse_case_seed(yaml.safe_load(text))
    assert reloaded == seed


def test_write_case_seed_creates_the_case_folder(
    tmp_path: Path, minimal_case: dict[str, Any]
) -> None:
    seed = seeds.parse_case_seed(minimal_case)
    written = seeds.write_case_seed(seed, tmp_path / seed.case_id / "seed.yaml")
    assert written.is_file()
    assert seeds.load_case_seed(written) == seed


def test_seed_hash_is_content_addressed(minimal_case: dict[str, Any]) -> None:
    seed = seeds.parse_case_seed(minimal_case)
    same = seeds.parse_case_seed(dict(minimal_case))
    other = seeds.parse_case_seed(dict(minimal_case) | {"rng_seed": 43})
    assert seed.seed_hash() == same.seed_hash()
    assert seed.seed_hash() != other.seed_hash()


def test_effective_format_mix_renormalizes_over_allowed_formats(
    minimal_case: dict[str, Any]
) -> None:
    seed = seeds.parse_case_seed(
        dict(minimal_case) | {"output": {"formats": ["pdf", "docx"]}}
    )
    mix = seed.effective_format_mix()
    assert set(mix) == {"pdf", "docx"}
    assert pytest.approx(sum(mix.values())) == 1.0
    assert mix["pdf"] > mix["docx"]


def test_format_mix_with_no_usable_weight_is_an_error(minimal_case: dict[str, Any]) -> None:
    seed = seeds.parse_case_seed(
        dict(minimal_case)
        | {"output": {"formats": ["docx"]}, "documents": {"format_mix": {"pdf": 1.0}}}
    )
    with pytest.raises(seeds.SeedError) as excinfo:
        seed.effective_format_mix()
    assert "format_mix" in str(excinfo.value)


def test_loader_reports_missing_and_malformed_files(tmp_path: Path) -> None:
    with pytest.raises(seeds.SeedError, match="file not found"):
        seeds.load_case_seed(tmp_path / "nope.yaml")

    empty = tmp_path / "empty.yaml"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(seeds.SeedError, match="empty"):
        seeds.load_case_seed(empty)

    scalar = tmp_path / "scalar.yaml"
    scalar.write_text("just-a-string\n", encoding="utf-8")
    with pytest.raises(seeds.SeedError, match="expected a YAML mapping"):
        seeds.load_case_seed(scalar)

    broken = tmp_path / "broken.yaml"
    broken.write_text("a: [1, 2\n", encoding="utf-8")
    with pytest.raises(seeds.SeedError, match="invalid YAML"):
        seeds.load_case_seed(broken)


def test_no_wall_clock_dependence_in_derived_dates() -> None:
    """Derived injury dates hang off the fixed anchor, never `today`."""
    derived = seeds.derive_auto_seeds(seeds.AutoSpec(count=10, rng_seed=3))
    for seed in derived:
        assert seed.injury.onset_date < seeds.ANCHOR_DATE
        assert seed.injury.onset_date > seeds.ANCHOR_DATE.replace(year=2020)
