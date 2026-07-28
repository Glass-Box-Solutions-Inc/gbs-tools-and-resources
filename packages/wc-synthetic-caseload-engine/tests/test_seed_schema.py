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


# ---------------------------------------------------------------------------
# AJC-35 #25 — a body part cannot be injured twice in one claim
# ---------------------------------------------------------------------------


class TestDuplicateBodyPartsAreRejected:
    """AJC-35 #25: ``[lumbar_spine, lumbar_spine]`` is not two impairments.

    The seed is where an impossible story gets rejected, and this one was
    getting through: two identical entries loaded fine and then counted as two
    for ``benson`` and ``kite``, whose whole premise is that there are two
    *distinct* impairments to apportion between or add together. A file could
    therefore argue Kite's synergistic effect between a body part and itself,
    with no warning, because the gate counted list entries rather than parts.
    """

    def _seed(self, parts: list[str]) -> dict[str, Any]:
        return {
            "case_id": "dupe-parts",
            "rng_seed": 42,
            "injury": {
                "type": "specific",
                "date_of_injury": "2022-04-11",
                "body_parts": [{"part": p, "icd10": "M54.5"} for p in parts],
            },
        }

    def test_a_repeated_part_is_refused_at_load(self) -> None:
        with pytest.raises(ValueError, match="lumbar_spine") as excinfo:
            seeds.parse_case_seed(self._seed(["lumbar_spine", "lumbar_spine"]))
        message = str(excinfo.value)
        assert "injury.body_parts" in message, "the error must name the offending field"
        assert "dupe-parts" in message, (
            "the error must name the case — a caseload spec fails one case at a "
            f"time and the reader needs to know which. Got: {message}"
        )
        assert "once" in message or "distinct" in message, (
            f"the error must say what to do about it, got: {message}"
        )

    def test_a_bare_injuryspec_cannot_hold_a_duplicate_either(self) -> None:
        """``InjurySpec`` is public API — it is in ``__all__``.

        The case-aware check on ``CaseSeed`` gives the better message, but it
        only fires when a seed is being built. A caller constructing an
        ``InjurySpec`` directly must not be able to hold a state the rest of the
        engine treats as impossible.
        """
        assert "InjurySpec" in seeds.__all__
        with pytest.raises(ValueError, match="same region twice"):
            seeds.InjurySpec(
                type="specific",
                date_of_injury=date(2022, 4, 11),
                body_parts=[
                    seeds.BodyPart(part="lumbar_spine"),
                    seeds.BodyPart(part="lumbar_spine"),
                ],
            )

    def test_the_seed_level_message_still_wins_over_the_injury_level_one(self) -> None:
        """Both layers fire; the one naming the case has to be the one seen.

        Pydantic validates a nested model before the outer model's ``after``
        validators, so this ordering is a real property to pin rather than an
        obvious one — it is why the seed check runs ``mode="before"``.
        """
        with pytest.raises(ValueError) as excinfo:
            seeds.parse_case_seed(self._seed(["lumbar_spine", "lumbar_spine"]))
        assert "dupe-parts" in str(excinfo.value)

    def test_the_case_is_named_even_inside_a_multi_case_spec(self) -> None:
        """The failure mode this guards: 'some case has a duplicate'."""
        spec = {
            "caseload_id": "multi",
            "cases": [
                self._seed(["lumbar_spine"]) | {"case_id": "healthy-one"},
                self._seed(["shoulder", "shoulder"]) | {"case_id": "the-broken-one"},
            ],
        }
        with pytest.raises(ValueError) as excinfo:
            seeds.resolve_caseload(seeds.parse_caseload_spec(spec))
        message = str(excinfo.value)
        assert "the-broken-one" in message, message
        assert "healthy-one" not in message, "the innocent case must not be implicated"

    def test_the_check_is_case_and_whitespace_insensitive(self) -> None:
        """``Lumbar_Spine`` and ``lumbar_spine`` are the same part written twice."""
        with pytest.raises(ValueError, match="body_parts"):
            seeds.parse_case_seed(self._seed(["lumbar_spine", " Lumbar_Spine "]))

    def test_genuinely_distinct_parts_still_load(self) -> None:
        seed = seeds.parse_case_seed(self._seed(["lumbar_spine", "cervical_spine"]))
        assert [p.part for p in seed.injury.body_parts] == ["lumbar_spine", "cervical_spine"]

    def test_body_part_count_counts_distinct_parts(self) -> None:
        """Belt and braces: the gate must not depend on the validator alone.

        ``DoctrineFacts`` is also built directly in ``lifecycle_bridge`` during
        auto-derivation, before any ``CaseSeed`` exists to validate.
        """
        from wc_caseload_engine.doctrine import DoctrineFacts

        facts = DoctrineFacts.from_seed(
            seeds.parse_case_seed(self._seed(["lumbar_spine", "cervical_spine"]))
        )
        assert facts.body_part_count == 2

        one_part = DoctrineFacts.from_seed(seeds.parse_case_seed(self._seed(["lumbar_spine"])))
        assert one_part.body_part_count == 1

    def test_benson_and_kite_reject_a_part_repeated(self) -> None:
        """The gates these duplicates were fooling, asserted directly.

        Built through ``DoctrineFacts`` rather than a seed, because the seed
        validator now refuses the input — this proves the second line of defence
        holds on its own.
        """
        from wc_caseload_engine.doctrine import DOCTRINE_CONTENT, DoctrineFacts

        repeated = DoctrineFacts(
            eval_type="qme",
            claim_response="accepted",
            injury_type="specific",
            body_part_count=1,
            has_psych_body_part=False,
            imr_filed=False,
        )
        for hook in ("benson", "kite"):
            requires = DOCTRINE_CONTENT[hook].requires
            assert requires is not None
            assert not requires.satisfied_by(repeated), (
                f"{hook} is satisfied by a single distinct impairment"
            )


class TestAutoDerivationNeverRepeatsABodyPart:
    """``_derive_body_parts`` promises distinct parts; it was not delivering.

    ``BODY_PART_CATALOG`` lists ``psyche`` twice, ``head`` twice and
    ``internal`` three times *within their own category*, so shuffling a
    category pool and slicing it returned the same part more than once. Roughly
    8% of auto-derived seeds carried a repeat — enough that ``kite`` could argue
    a synergistic effect between a body part and itself, with no warning,
    because the gate counted list entries.

    This is also why the seed-level validator alone is not enough: it would turn
    a silent modelling error into a hard crash of ``auto:`` derivation.
    """

    def test_no_derived_seed_names_a_part_twice(self) -> None:
        offenders: list[tuple[str, list[str]]] = []
        for rng_seed in range(1, 40):
            for seed in seeds.derive_auto_seeds(
                seeds.AutoSpec(count=25, rng_seed=rng_seed)
            ):
                names = [part.part for part in seed.injury.body_parts]
                if len(names) != len(set(names)):
                    offenders.append((seed.case_id, names))
        assert not offenders, (
            f"{len(offenders)} auto-derived seeds repeat a body part, e.g. "
            f"{offenders[:3]}"
        )

    def test_a_narrow_category_yields_fewer_parts_rather_than_repeats(self) -> None:
        """Distinctness wins over hitting the requested count."""
        import random

        parts = seeds._derive_body_parts(random.Random(7), "psyche", 5)
        names = [part.part for part in parts]
        assert len(names) == len(set(names)), names
        assert names[0] == "psyche", "the requested category still leads"


class TestTheCommonPathConsumesTheRngItAlwaysDid:
    """The reproducibility guarantee, pinned as control flow rather than bytes.

    Deduplicating ``_derive_body_parts`` had to not disturb seeds that never had
    a duplicate. The draft that did the obvious thing — build both pools,
    shuffle both, then dedupe across them — consumed an extra draw on the
    *common* path, which shifts every subsequent draw (eval_type, resolution,
    liens, doctrine hooks) for **every** auto-derived case. Measured against
    0.1.0: that draft moved all 975 derived seeds; the shipped version moves 75,
    exactly those that previously received a repeat.

    That comparison needs two revisions checked out, so it cannot live in the
    suite. What *can* live here is the property that produced the result: the
    fallback pool is shuffled only when the category pool came up short. Pin the
    control flow and the byte-level outcome follows.
    """

    class _CountingRandom:
        """A ``random.Random`` that records how many times it was shuffled."""

        def __init__(self, seed: int) -> None:
            import random

            self._rng = random.Random(seed)
            self.shuffles = 0

        def shuffle(self, seq: list[Any]) -> None:
            self.shuffles += 1
            self._rng.shuffle(seq)

        def __getattr__(self, name: str) -> Any:
            return getattr(self._rng, name)

    def test_a_sufficient_category_pool_shuffles_exactly_once(self) -> None:
        """``spine`` holds enough distinct parts, so the fallback is never built."""
        rng = self._CountingRandom(11)
        parts = seeds._derive_body_parts(rng, "spine", 2)  # type: ignore[arg-type]

        assert len(parts) == 2
        assert rng.shuffles == 1, (
            "the fallback pool was shuffled even though the category pool sufficed. "
            "That extra draw shifts every subsequent value for every auto-derived "
            "case, silently changing output for seeds this function did not need to "
            "touch."
        )

    def test_a_short_category_pool_shuffles_twice(self) -> None:
        """``psyche`` collapses to one distinct part, so the fallback is needed."""
        rng = self._CountingRandom(11)
        parts = seeds._derive_body_parts(rng, "psyche", 3)  # type: ignore[arg-type]

        names = [part.part for part in parts]
        assert names[0] == "psyche"
        assert len(names) == len(set(names)) == 3, names
        assert rng.shuffles == 2, (
            "the fallback pool was not reached, so a category that cannot supply "
            f"{len(names)} distinct parts returned repeats or came up short: {names}"
        )

    def test_the_category_pool_is_still_drawn_first_and_only_once(self) -> None:
        """A count the category alone satisfies must not touch other categories."""
        rng = self._CountingRandom(3)
        parts = seeds._derive_body_parts(rng, "lower_extremity", 1)  # type: ignore[arg-type]

        assert rng.shuffles == 1
        assert parts[0].part in {
            entry[0] for entry in seeds.BODY_PART_CATALOG["lower_extremity"]
        }


class TestFirefighterPresumptionCannotBeAutoDrawn:
    """A known coverage gap, pinned so it cannot close or widen silently.

    ``derive_case_seed`` builds :class:`DoctrineFacts` without ``occupation`` or
    ``industry`` — not an oversight, but because a derived seed carries no
    ``profile`` block at all: the cast is drawn later, in ``case_context``, and
    never written back into the seed. ``_SAFETY_MEMBER_PREREQUISITE`` reads
    exactly those two fields, so it can never be satisfied during derivation and
    the hook is filtered out of every draw.

    This fails *closed* — auto-derivation never produces a case arguing a
    presumption it cannot support — so it is a coverage gap, not the incoherence
    class of AJC-35 #24. Closing it needs an occupation/industry distribution
    and a profile in the materialized seed, which changes the bytes of every
    auto-derived caseload; that is tracked separately.

    Explicit seeds are unaffected: they carry a profile, so the hook works
    normally there (``showcase-firefighter-presumption`` proves it).
    """

    def test_derivation_draws_every_hook_except_the_one_it_structurally_cannot(
        self,
    ) -> None:
        drawn: set[str] = set()
        for rng_seed in range(1, 40):
            for seed in seeds.derive_auto_seeds(
                seeds.AutoSpec(count=25, rng_seed=rng_seed)
            ):
                drawn.update(seed.lifecycle.doctrine_hooks)

        never = set(seeds._DOCTRINE_POOL) - drawn
        assert never == {"firefighter_presumption"}, (
            "the set of never-auto-drawn hooks changed. If firefighter_presumption "
            "is now drawn, derivation learned to supply occupation/industry and this "
            "test should be deleted along with the comment in derive_case_seed. If a "
            f"different hook stopped being drawn, that is a new defect: {never}"
        )

    def test_an_explicitly_seeded_firefighter_case_still_works(self) -> None:
        """The gap is in derivation only — the gate itself is fine."""
        from wc_caseload_engine.doctrine import hook_is_supported

        seed = seeds.parse_case_seed(
            {
                "case_id": "fire-explicit",
                "rng_seed": 42,
                "profile": {"employer": {"industry": "government"}},
                "injury": {
                    "type": "specific",
                    "date_of_injury": "2022-04-11",
                    "body_parts": [{"part": "internal_organs", "icd10": "C34.90"}],
                },
                "lifecycle": {"doctrine_hooks": ["firefighter_presumption"]},
            }
        )
        assert hook_is_supported("firefighter_presumption", seed)


class TestTheShippedSpecsNameNoPartTwice:
    """The committed specs must survive the new validator."""

    @pytest.mark.parametrize("spec_name", ["demo-caseload.yaml", "doctrine-showcase.yaml"])
    def test_no_case_repeats_a_body_part(self, spec_name: str) -> None:
        spec_path = Path(__file__).resolve().parents[1] / "examples" / spec_name
        offenders: list[str] = []
        for seed in seeds.resolve_caseload(seeds.load_caseload_spec(spec_path)):
            names = [p.part.strip().lower() for p in seed.injury.body_parts]
            if len(names) != len(set(names)):
                offenders.append(f"{seed.case_id}: {names}")
        assert not offenders, f"{spec_name} repeats a body part: {offenders}"
